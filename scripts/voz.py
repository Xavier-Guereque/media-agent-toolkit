#!/usr/bin/env python3
"""voz — voz en off del motor promo (lo corre `python3 scripts/promo.py voz <proyecto>`).

Entrada: `recursos/promo/linea_tiempo.json > voz.lineas` (las frases `subtitulo` que se locutan).
Salida:  `recursos/voz/l{escena}_{frase}.wav` (48 kHz mono, 0.08 s de colchón inicial, sin
         silencio final) y `recursos/voz/tiempos.json`, que el planificador Node usa para dar a
         cada escena la duración real de su toma y encender el karaoke palabra por palabra.

Pasos por línea:
  1. Texto en pantalla → texto para el TTS con `promo/temas/<tema>/pronunciacion.json`
     (UN token → UN token: el conteo de palabras no cambia y el karaoke empata).
  2. Lint (scripts/lint_voz.py) ANTES de pagar: cifras, preguntas, dos puntos, marcas.
  3. TTS: por defecto **Fish** (`modelos.voz_tts` = fish-audio/s2-pro por `/audio/speech`): es un TTS
     puro, lee al pie de la letra y no "contesta" (medido 2026-09-28: gpt-audio-mini desarrolló 8 de
     13 subtítulos del ejemplo de oro, p. ej. "Descríbele tu proyecto y te arma" = 3.3 s/palabra).
     Alternativas: `gpt-audio` (gpt-audio-mini por SSE, receta de reel.py; admite `voz` y `estilo`)
     o ElevenLabs solo si `proveedor=elevenlabs` y hay ELEVENLABS_API_KEY (AGENT §5). Caché por hash de
     (texto tts, voz, modelo, estilo, proveedor): si no cambió, no se paga otra vez.
  4. Señal de alarma: > 0.6 s por palabra = el modelo "respondió" en vez de leer → se rehace una
     vez; si sigue, E-TTS-LENTO.
  5. Diff dirigido (scripts/verificar_voz.py) de las tomas nuevas → avisos W-TTS-DIFF.
  6. Tiempos por palabra: reparto ponderado por sílabas (grupos vocálicos del español) dentro de
     la región de habla; las pausas internas (silencedetect -40 dB, 0.12 s) se alinean con las
     comas y las demás pausas se descuentan.

Las pruebas sustituyen la red con `sintetizar=` (o PROMO_TTS_STUB=1 | lento en el entorno).
Solo librería estándar + ffmpeg.
"""
import base64
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import lint_voz  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
COLCHON = 0.08            # s de silencio antes de la voz: el PCM del TTS arranca sin ataque
SEG_POR_PALABRA_MAX = 0.6  # SKILL crear-audio: ~0.45 normal; > 0.6 = texto de más (referencia)
# Criterio real: segundos por SÍLABA. Por palabra castiga las palabras largas ("Desbloquea equipos
# HIKVISION" = 0.73 s/palabra pero 0.22 s/sílaba, habla normal). Medido 2026-09-28 con Fish: tomas
# buenas 0.15–0.29 s/sílaba; las de gpt-audio-mini que "contestaban", > 1 s/sílaba.
SEG_POR_SILABA_MAX = 0.38
UMBRAL_DB = -40.0
PAUSA_MIN = 0.12
SYSTEM_BASE = ("Eres locutor profesional de México. Repite verbatim el texto del usuario, sin "
               "confirmaciones, saludos ni palabras extra. Español de México, dicción clara.")
ELEVEN_VOZ_DEF = "21m00Tcm4TlvDq8ikWAM"   # voz prediseñada de ElevenLabs (sin verificar en esta cuenta)
ELEVEN_MODELO_DEF = "eleven_multilingual_v2"
FIN_DE_TRAMO = ",;:.!?…"


class ErrorTTS(Exception):
    """Falla de la API externa (código 4: reintentar una vez)."""


class ErrorEntornoVoz(Exception):
    """Falta una key o el proveedor no aplica (código 3: preguntar al usuario)."""


# ---------------------------------------------------------------- pronunciación
def cargar_pronunciacion(repo, tema):
    ruta = os.path.join(repo, "promo", "temas", tema or "neutro", "pronunciacion.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        datos = {}
    return {"marcas": datos.get("marcas", []), "palabras": datos.get("palabras", {})}


def a_tts(texto, pron):
    """Reemplaza token por token (conserva la puntuación de los bordes)."""
    tabla = pron.get("palabras", {})
    menor = {k.lower(): v for k, v in tabla.items()}
    salida = []
    for tok in lint_voz.palabras(texto):
        n = lint_voz.nucleo(tok)
        dicho = tabla.get(n) or menor.get(n.lower())
        if n and dicho:
            i = tok.find(n)
            tok = tok[:i] + dicho + tok[i + len(n):]
        salida.append(tok)
    return " ".join(salida)


# ---------------------------------------------------------------- proveedores (única puerta a la red)
def _url_openrouter(repo):
    cfg = comun.cargar_config(repo)
    base = (cfg.get("openrouter") or {}).get("url_base", "https://openrouter.ai/api/v1")
    ruta = ((cfg.get("openrouter") or {}).get("endpoints") or {}).get("voz", "/chat/completions")
    url = base.rstrip("/") + ruta
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname != "openrouter.ai":   # la key solo viaja a openrouter.ai
        url = "https://openrouter.ai/api/v1/chat/completions"
    return url


def tts_openrouter(texto, voz, modelo, system, key, url):
    """gpt-audio-mini por SSE (receta verificada de reel.py): PCM16 24 kHz mono.
    Devuelve (pcm, sr, id, usage)."""
    payload = {"model": modelo, "modalities": ["text", "audio"],
               "audio": {"voice": voz, "format": "pcm16"}, "stream": True,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": texto}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    chunks, gid, usage = [], None, None
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                linea = raw.decode("utf-8", "replace").strip()
                if not linea.startswith("data:"):
                    continue
                data = linea[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ch = json.loads(data)
                except json.JSONDecodeError:
                    continue
                gid = gid or ch.get("id")
                usage = ch.get("usage") or usage
                for c in ch.get("choices", []):
                    a = (c.get("delta") or {}).get("audio") or {}
                    if a.get("data"):
                        chunks.append(a["data"])
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorTTS(f"OpenRouter TTS: {str(e)[:200]}")
    if not chunks:
        raise ErrorTTS("OpenRouter TTS: la respuesta no trajo audio")
    return base64.b64decode("".join(chunks)), 24000, gid, usage


def _url_speech(repo):
    cfg = comun.cargar_config(repo)
    base = (cfg.get("openrouter") or {}).get("url_base", "https://openrouter.ai/api/v1")
    url = base.rstrip("/") + "/audio/speech"
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname != "openrouter.ai":   # la key solo viaja a openrouter.ai
        url = "https://openrouter.ai/api/v1/audio/speech"
    return url


def tts_speech(texto, key, url, modelo="fish-audio/s2-pro", voice=None, instructions=None):
    """TTS puro por `/audio/speech` de OpenRouter (Fish S2 Pro, Gemini TTS, Microsoft MAI…): PCM16 crudo mono,
    sin encabezado; la tasa viene en el Content-Type (`rate=`) y, si falta, es 44.1 kHz en Fish y 24 kHz en los
    demás. Lee verbatim y no admite `system`. `voice` (Fish: id de 32 hex de su biblioteca; Gemini: nombre, p. ej.
    Achird; Microsoft: `es-MX-Valeria:MAI-Voice-2.1`) e `instructions` (estilo en lenguaje natural; en Fish se cobra
    como caracteres) son opcionales — verificado 2026-10-31. El id de generación viene en la cabecera."""
    body = {"model": modelo, "input": texto, "response_format": "pcm"}
    if voice:
        body["voice"] = voice
    if instructions:
        body["instructions"] = instructions
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            pcm = r.read()
            gid = r.headers.get("x-generation-id")
            tipo = r.headers.get("content-type") or ""
    except urllib.error.HTTPError as e:
        raise ErrorTTS(f"TTS {modelo} {e.code}: {e.read()[:200]!r}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorTTS(f"TTS {modelo}: {str(e)[:200]}")
    if len(pcm) < 2048 or "json" in tipo or "html" in tipo:
        raise ErrorTTS(f"TTS {modelo}: la respuesta no trajo audio")
    m = re.search(r"rate=(\d+)", tipo)
    sr = int(m.group(1)) if m else (44100 if modelo.startswith("fish-audio/") else 24000)
    return pcm, sr, gid, {"characters": len(texto) + len(instructions or "")}


def tts_fish(texto, key, url, modelo="fish-audio/s2-pro", voice=None, instructions=None):
    """Alias histórico de `tts_speech` (Fish por defecto)."""
    return tts_speech(texto, key, url, modelo, voice, instructions)


def tts_elevenlabs(texto, voz_id, key, modelo=ELEVEN_MODELO_DEF):
    """ElevenLabs text-to-speech en PCM 24 kHz (sin verificar en esta cuenta: no hay key)."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voz_id)}?output_format=pcm_24000"
    req = urllib.request.Request(url, data=json.dumps({"text": texto, "model_id": modelo}).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            pcm = r.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorTTS(f"ElevenLabs TTS: {str(e)[:200]}")
    return pcm, 24000, None, {"characters": len(texto)}


def tts_simulado(texto, lento=False):
    """TTS falso para pruebas: un tono por sílaba (0.11 s), 0.04 s entre palabras, 0.28 s de
    pausa tras coma/punto y 0.25 s de silencio final. Determinista y sin red."""
    sr, paso = 24000, (0.5 if lento else 0.11)  # lento = > 0.38 s/sílaba (modelo que agrega texto)
    muestras = array("h")
    toks = texto.split()
    for k, tok in enumerate(toks):
        dur = silabas(tok) * paso
        n = int(dur * sr)
        for i in range(n):
            env = min(1.0, i / 120, (n - i) / 120)
            muestras.append(int(9000 * env * math.sin(2 * math.pi * (180 + 20 * (k % 3)) * i / sr)))
        pausa = 0.28 if (tok[-1] in FIN_DE_TRAMO and k < len(toks) - 1) else 0.04
        muestras.extend([0] * int(pausa * sr))
    muestras.extend([0] * int(0.25 * sr))
    return muestras.tobytes(), sr, None, None


def _key_opcional(repo, var):
    if os.environ.get(var):
        return os.environ[var]
    try:
        with open(os.path.join(repo, ".env"), encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea.startswith(var + "="):
                    v = linea.split("=", 1)[1].strip().strip('"').strip("'")
                    return v or None
    except OSError:
        pass
    return None


def resolver_voz(spec_voz, cfg):
    """Proveedor, modelo y voz efectivos: spec del proyecto > `voz_default` (config.local.json, AGENT §16) > casa.
    Proveedores: `fish` y `speech` (ambos `/audio/speech`; `speech` sirve para Gemini TTS, Microsoft, etc.),
    `gpt-audio` y `elevenlabs`. `voice`/`instructions`/`voz`/`estilo` solo se heredan del default cuando el spec no
    fija otro proveedor (una voz de Gemini no aplica a Fish)."""
    d = cfg.get("voz_default") or {}
    modelos = cfg.get("modelos") or {}
    prov = spec_voz.get("proveedor") or d.get("proveedor") or "fish"
    hereda = not spec_voz.get("proveedor") or spec_voz.get("proveedor") == d.get("proveedor")

    def h(clave):
        return spec_voz.get(clave) or (d.get(clave) if hereda else None)

    if prov == "elevenlabs":
        modelo = ELEVEN_MODELO_DEF
    elif prov in ("fish", "speech"):
        modelo = h("modelo") or modelos.get("voz_tts", "fish-audio/s2-pro")
    else:
        modelo = h("modelo") or modelos.get("voz", "openai/gpt-audio-mini")
    return {"proveedor": prov, "modelo": modelo, "voice": h("voice"), "instructions": h("instructions"),
            "voz": h("voz") or "coral", "estilo": h("estilo")}


def proveedor(spec_voz, repo, modelo=None, res=None):
    """Función texto → (pcm, sr, id, usage) según el spec (resuelto con `resolver_voz`), o ErrorEntornoVoz."""
    stub = os.environ.get("PROMO_TTS_STUB")
    if stub:
        return lambda texto, system: tts_simulado(texto, lento=(stub == "lento"))
    res = res or resolver_voz(spec_voz, comun.cargar_config(repo))
    modelo = modelo or res["modelo"]
    voz, prov = res["voz"], res["proveedor"]
    if prov == "elevenlabs":
        key = _key_opcional(repo, "ELEVENLABS_API_KEY")
        if not key:
            raise ErrorEntornoVoz("proveedor elevenlabs sin ELEVENLABS_API_KEY en .env; cambia "
                                  "audio.voz.proveedor a openrouter (AGENT §5: la key no se pide).")
        cfg = comun.cargar_config(repo).get("elevenlabs") or {}
        voz_id = cfg.get("voz_id", ELEVEN_VOZ_DEF)
        return lambda texto, system: tts_elevenlabs(texto, voz_id, key, cfg.get("modelo", ELEVEN_MODELO_DEF))
    key = _key_opcional(repo, "OPENROUTER_API_KEY")
    if not key:
        raise ErrorEntornoVoz("falta OPENROUTER_API_KEY (entorno o .env).")
    if prov in ("fish", "speech"):
        url = _url_speech(repo)
        voice, instr = res["voice"], res["instructions"]
        return lambda texto, system: tts_speech(texto, key, url, modelo, voice, instr)
    url = _url_openrouter(repo)   # "gpt-audio" (o el antiguo "openrouter")
    return lambda texto, system: tts_openrouter(texto, voz, modelo, system, key, url)


# ---------------------------------------------------------------- toma y medición
def guardar_toma(pcm, sr_in, wav, carpeta):
    """PCM16 mono → WAV 48 kHz mono con 0.08 s de colchón y sin silencio final."""
    crudo = os.path.join(carpeta, os.path.basename(wav)[:-4] + ".pcm")
    with open(crudo, "wb") as f:
        f.write(pcm)
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "s16le", "-ar", str(sr_in), "-ac", "1",
               "-i", crudo, "-af",
               f"aresample={SR},areverse,silenceremove=start_periods=1:start_threshold=-45dB:"
               f"start_silence=0.05,areverse,adelay=delays={int(COLCHON * 1000)}:all=1",
               "-ac", "1", "-c:a", "pcm_s16le", "-fflags", "+bitexact", "-flags:a", "+bitexact", wav])
    os.remove(crudo)


def silencios(wav):
    """Intervalos de silencio (silencedetect -40 dB, ≥ 0.12 s)."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", wav, "-af",
                        f"silencedetect=noise={UMBRAL_DB:g}dB:d={PAUSA_MIN}", "-f", "null", "-"],
                       capture_output=True, text=True)
    ini = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    fin = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", r.stderr)]
    total = comun.dur(wav)
    return [(max(0.0, a), fin[i] if i < len(fin) else total) for i, a in enumerate(ini)]


def region_habla(wav):
    """(inicio, fin) de la voz por umbral de -40 dBFS en tramos de 10 ms (el colchón de 0.08 s
    es más corto que el mínimo de silencedetect, por eso los bordes se miden aparte)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-ac", "1", "-f", "f32le", "-"], capture_output=True)
    x = array("f")
    x.frombytes(r.stdout)
    umbral = 10 ** (UMBRAL_DB / 20)
    tramo = SR // 100
    vivos = [i for i in range(0, len(x), tramo) if max((abs(v) for v in x[i:i + tramo]), default=0) > umbral]
    if not vivos:
        return 0.0, len(x) / SR
    return vivos[0] / SR, min(len(x), vivos[-1] + tramo) / SR


def silabas(token):
    """Sílabas por grupos vocálicos del español (hiatos: fuerte+fuerte o débil con tilde)."""
    t = lint_voz.nucleo(token).lower()
    n = 0
    for g in re.findall(r"[aeiouáéíóúü]+", t):
        n += 1 + sum(1 for x, y in zip(g, g[1:])
                     if (x in "aeoáéó" and y in "aeoáéó") or x in "íú" or y in "íú")
    if t.endswith("y") and (len(t) == 1 or t[-2] not in "aeiouáéíóúü"):
        n += 1
    return max(1, n)


def _mapear(frac, intervalos, siguiente):
    """Fracción del tiempo de habla → tiempo real, saltando las pausas descontadas."""
    total = sum(b - a for a, b in intervalos)
    objetivo = frac * total
    acum = 0.0
    for k, (a, b) in enumerate(intervalos):
        largo = b - a
        if objetivo < acum + largo - 1e-9 or k == len(intervalos) - 1:
            return a + max(0.0, min(largo, objetivo - acum))
        if abs(objetivo - (acum + largo)) <= 1e-9:
            return intervalos[k + 1][0] if siguiente else b
        acum += largo
    return intervalos[-1][1]


def tiempos_palabras(pantalla, dichas, s0, s1, pausas):
    """[{w, a, b}] relativos al inicio de la toma.

    Pesos = sílabas + 0.25 por palabra. Toda pausa interna cae ENTRE palabras (nadie respira a
    media palabra): primero cada coma/punto toma la pausa más cercana a donde debería caer, luego
    cada pausa restante toma el límite entre palabras más cercano que respete el orden; las que
    sobren (más pausas que límites) se descuentan del tiempo de habla."""
    n = len(pantalla)
    pesos = [silabas(t) + 0.25 for t in dichas]
    W = sum(pesos)
    esperado = [s0 + (s1 - s0) * sum(pesos[:k + 1]) / W for k in range(n - 1)]   # fin de la palabra k
    internas = sorted(p for p in pausas if p[0] > s0 + 1e-3 and p[1] < s1 - 1e-3)
    asignadas = {}                                   # límite k → pausa

    def cabe(k, p):
        return all((k < k2) == (p[0] < p2[0]) for k2, p2 in asignadas.items())

    def centro(p):
        return (p[0] + p[1]) / 2

    for k in (k for k in range(n - 1) if pantalla[k][-1:] in FIN_DE_TRAMO):
        libres = [p for p in internas if p not in asignadas.values() and cabe(k, p)]
        if libres:
            asignadas[k] = min(libres, key=lambda p: abs(centro(p) - esperado[k]))
    for p in internas:
        if p in asignadas.values():
            continue
        limites = [k for k in range(n - 1) if k not in asignadas and cabe(k, p)]
        if limites:
            asignadas[min(limites, key=lambda k: abs(esperado[k] - centro(p)))] = p
    sobrantes = [p for p in internas if p not in asignadas.values()]
    tramos, ini, desde = [], s0, 0
    for k in sorted(asignadas):
        tramos.append((desde, k + 1, ini, asignadas[k][0]))
        desde, ini = k + 1, asignadas[k][1]
    tramos.append((desde, n, ini, s1))
    salida = []
    for d, h, a, b in tramos:
        intervalos, c = [], a
        for pa, pb in (p for p in sobrantes if a < p[0] and p[1] < b):
            intervalos.append((c, pa))
            c = pb
        intervalos.append((c, b))
        Wt = sum(pesos[d:h]) or 1.0
        acum = 0.0
        for k in range(d, h):
            ta = _mapear(acum / Wt, intervalos, True)
            acum += pesos[k]
            tb = _mapear(acum / Wt, intervalos, False)
            salida.append({"w": pantalla[k], "a": round(ta, 3), "b": round(max(ta, tb), 3)})
    return salida


def huella_linea(tts, voz, modelo, estilo, prov, voice=None, instructions=None):
    # Fish/speech no usan `voz` (nombre de gpt-audio) ni `estilo`: si entraran a la huella, cambiarlos regeneraría
    # (y cobraría) tomas idénticas; lo que sí cambia la toma ahí es `voice` + `instructions`. Sin ellos la huella
    # es la histórica, para no invalidar cachés existentes.
    if prov in ("fish", "speech"):
        voz, estilo = "", ""
    else:
        voice, instructions = None, None
    campos = [tts, voz, modelo, estilo or "", prov]
    if voice or instructions:
        campos += [voice or "", instructions or ""]
    return hashlib.sha1(json.dumps(campos, ensure_ascii=False).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- etapa
def generar_voz(rec, lt, repo=None, verificar=True, sintetizar=None, verificador=None):
    """Genera/reutiliza las tomas de `lt.voz.lineas` y escribe recursos/voz/tiempos.json.

    Devuelve {"codigo", "issues", "lineas", "nuevas", "cache", "total", "archivo"}.
    `sintetizar(texto, system)` y `verificador(textos, wavs)` sustituyen la red en las pruebas."""
    repo = repo or REPO
    spec = lt.get("voz") or {}
    lineas = spec.get("lineas") or []
    carpeta = os.path.join(rec, "voz")
    os.makedirs(carpeta, exist_ok=True)
    cfg = comun.cargar_config(repo)
    res = resolver_voz(spec, cfg)
    prov, modelo, voz, estilo = res["proveedor"], res["modelo"], res["voz"], res["estilo"]
    tema = lt.get("tema_nombre") or (lt["tema"].get("nombre") if isinstance(lt.get("tema"), dict) else lt.get("tema"))
    pron = cargar_pronunciacion(repo, tema)
    out = {"codigo": 0, "issues": [], "lineas": len(lineas), "nuevas": 0, "cache": 0, "total": 0.0,
           "archivo": os.path.join(carpeta, "tiempos.json")}
    if not lineas:
        out["issues"].append({"codigo": "E-VOZ-SIN-LINEAS", "severidad": "E", "ruta": "audio.voz",
                              "msg": "no hay líneas de voz (ninguna escena tiene subtitulo).",
                              "arreglo": "Agrega subtitulo a las escenas o quita audio.voz."})
        out["codigo"] = 2
        return out

    items = []
    for ln in lineas:
        texto = ln["texto"].replace("*", "").strip()
        items.append({"escena": ln["escena"], "frase": ln["frase"], "texto": texto,
                      "tts": a_tts(texto, pron), "ruta": f"escenas[{ln['escena']}].subtitulo[{ln['frase']}]"})
    out["issues"] = lint_voz.revisar(items, modelo, pron["marcas"])
    if any(i["severidad"] == "E" for i in out["issues"]):
        out["codigo"] = 2
        return out

    previo = {}
    try:
        with open(out["archivo"], encoding="utf-8") as f:
            for x in json.load(f).get("lineas", []):
                previo[x.get("hash")] = x
    except (OSError, json.JSONDecodeError):
        pass

    system = SYSTEM_BASE + (f" Estilo: {estilo}." if estilo else "")
    sintetizar = sintetizar or proveedor(spec, repo, modelo, res)
    nuevas_wavs, nuevas_txt = [], []
    for it in items:
        it["hash"] = huella_linea(it["tts"], voz, modelo, estilo, prov, res["voice"], res["instructions"])
        it["archivo"] = f"voz/l{it['escena']}_{it['frase']}.wav"
        wav = os.path.join(rec, it["archivo"])
        viejo = previo.get(it["hash"])
        if viejo and os.path.exists(os.path.join(rec, viejo["archivo"])):
            if viejo["archivo"] != it["archivo"]:
                shutil.copyfile(os.path.join(rec, viejo["archivo"]), wav)
            out["cache"] += 1
        else:
            for intento in (1, 2):             # una segunda toma si el modelo "respondió"
                pcm, sr_in, gid, usage = sintetizar(it["tts"], system)
                if gid or usage:
                    comun.log_costo(rec, {"id": gid, "modelo": modelo if prov != "elevenlabs" else f"elevenlabs/{modelo}",
                                          "tarea": "tts", "usage": usage})
                guardar_toma(pcm, sr_in, wav, carpeta)
                s0, s1 = region_habla(wav)
                spp = (s1 - s0) / max(1, len(lint_voz.palabras(it["texto"])))
                sps = (s1 - s0) / max(1, sum(silabas(t) for t in it["tts"].split()))
                if sps <= SEG_POR_SILABA_MAX:
                    break
            if sps > SEG_POR_SILABA_MAX:
                it["fallida"] = True   # no se registra: ni el planificador ni la caché deben usarla
                out["issues"].append({"codigo": "E-TTS-LENTO", "severidad": "E", "ruta": it["ruta"],
                                      "msg": f"«{it['texto']}» salió a {sps:.2f} s/sílaba ({spp:.2f} s/palabra) en 2 tomas: el modelo agregó texto.",
                                      "arreglo": "Reescríbela como afirmación corta con verbo conjugado."})
            out["nuevas"] += 1
            nuevas_wavs.append(wav)
            nuevas_txt.append(it["texto"])

    if verificar and nuevas_wavs and not os.environ.get("PROMO_TTS_STUB"):
        out["issues"] += verificar_tomas(nuevas_txt, nuevas_wavs, rec, repo, verificador)

    salida = []
    for it in items:
        if it.get("fallida"):
            continue
        wav = os.path.join(rec, it["archivo"])
        dur = comun.dur(wav)
        s0, s1 = region_habla(wav)
        pantalla, dichas = lint_voz.palabras(it["texto"]), lint_voz.palabras(it["tts"])
        palabras = tiempos_palabras(pantalla, dichas, s0, s1, silencios(wav))
        salida.append({"escena": it["escena"], "frase": it["frase"], "texto": it["texto"], "tts": it["tts"],
                       "archivo": it["archivo"], "dur": round(dur, 3), "palabras": palabras, "hash": it["hash"]})
        out["total"] += dur
    with open(out["archivo"], "w", encoding="utf-8") as f:
        json.dump({"version": 1, "voz": voz, "modelo": modelo, "proveedor": prov, "estilo": estilo,
                   "voice": res["voice"], "instructions": res["instructions"],
                   "generado": datetime.datetime.now().isoformat(timespec="seconds"), "lineas": salida},
                  f, ensure_ascii=False, indent=1)
    if any(i["severidad"] == "E" for i in out["issues"]):
        out["codigo"] = 2
    return out


def verificar_tomas(textos, wavs, rec, repo, verificador=None):
    """Diff dirigido (verificar_voz.py, modo JSON) → avisos W-TTS-DIFF. Nunca tumba la etapa."""
    import verificar_voz
    try:
        if verificador:
            datos = verificador(textos, wavs)
        else:
            crudo = verificar_voz.verificar(textos, repo=repo, wavs=wavs, tmp=os.path.join(rec, "voz", "_verificar"),
                                            formato="json", log=os.path.join(rec, "costos.jsonl"))
            datos = verificar_voz.parsear_json(crudo)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, SystemExit) as e:
        return [{"codigo": "W-TTS-SIN-VERIFICAR", "severidad": "W", "ruta": "audio.voz",
                 "msg": f"no se pudo verificar la voz ({str(e)[:80]}).", "arreglo": "Escucha las tomas nuevas."}]
    if datos is None:
        return [{"codigo": "W-TTS-SIN-VERIFICAR", "severidad": "W", "ruta": "audio.voz",
                 "msg": "la verificación no devolvió JSON legible.", "arreglo": "Escucha las tomas nuevas."}]
    issues = []
    for d in datos:
        try:
            k = int(d.get("audio", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= k < len(wavs)):
            continue
        extra, faltan = [x for x in d.get("extra") or [] if x], [x for x in d.get("faltan") or [] if x]
        if extra or faltan:
            partes = ([f"extra: {', '.join(extra)}"] if extra else []) + ([f"faltan: {', '.join(faltan)}"] if faltan else [])
            issues.append({"codigo": "W-TTS-DIFF", "severidad": "W", "ruta": os.path.basename(wavs[k]),
                           "msg": f"«{textos[k]}» — {'; '.join(partes)}.",
                           "arreglo": "Si es real, borra la toma y corre voz otra vez."})
    return issues
