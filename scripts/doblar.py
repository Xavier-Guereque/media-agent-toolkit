#!/usr/bin/env python3
"""doblar — doblaje de un video existente a otro idioma: voz nueva + captions nuevos en el estilo original.

Pipeline (skill `doblar-video` de SKILL.md; bitácora Lecciones-2026-10-30-doblaje-reel):

  1. transcribir <video> --proyecto <dir>      faster-whisper con tiempos por palabra →
                                               recursos/doblaje/transcripcion.json
  2. unidades <proyecto>                       agrupa palabras en oraciones ("unidades") con su hueco
                                               ("slot") hasta la siguiente → doblaje.json (spec editable)
     --- el agente traduce: llena `es` de cada unidad (o `doblar.py traducir` por OpenRouter) ---
  3. voz doblaje.json                          TTS por unidad (voicestudio local | fish | elevenlabs),
                                               ajuste al slot (duración objetivo / atempo), tiempos por
                                               palabra (ASR del wav nuevo) → recursos/doblaje/voz/,
                                               tiempos.json y voz_<idioma>.wav
  4. render doblaje.json                       captions en el estilo de la pieza (banda cubierta + texto
                                               con énfasis), rótulos estáticos traducidos y mezcla →
                                               <salida>.mp4 (misma duración que el original); con
                                               `cortinillas` en el spec → recursos/doblaje/cuerpo.mp4
  4b. cortinillas doblaje.json                 intro y/o cierre (tarjetas en el estilo de la pieza + voz)
                                               unidos al cuerpo con fade de 0.5 s → <salida>.mp4
  todo doblaje.json                            voz + render
  5. verificar doblaje.json                    duración, voz vs guion (ASR), rótulos y captions (OCR),
                                               loudness → código 5 si algo no cuadra

Marcado del texto traducido (`es`): `{palabra}` = palabra resaltada (caja), `*palabra*` = negrita.
El TTS recibe el texto sin marcas; `es_tts` (opcional) es lo que lee el TTS si la grafía del caption
no se pronuncia bien (siglas, marcas). Cajas contiguas se dibujan como una sola. Códigos de salida: 1 ffmpeg, 2 spec/entrada, 3 entorno
(whisper, Pillow, VoiceStudio cerrado), 4 API, 5 verificación con problemas.
Reporta avance al tablero (`comun.avance` → recursos/avance.jsonl; ver `scripts/tablero.py`).
Solo librería estándar + ffmpeg (+ Pillow para `render`, + venv de faster-whisper para los tiempos).
"""
import argparse
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
import uuid
import wave
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
WHISPER_PY_DEF = comun.python_de_venv("whisper")
VOICESTUDIO_URL_DEF = "http://127.0.0.1:3900"
FUENTES_DEF = os.path.join(REPO, "promo", "temas", "neutro", "fuentes")

# ----------------------------------------------------------------- utilidades


def fallo(msg, codigo=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(codigo)


def aviso(msg):
    print(f"AVISO {msg}", file=sys.stderr)


def cargar_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fallo(f"no se pudo leer {ruta}: {e}")


def guardar_json(ruta, datos):
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def whisper_python(explicito=None):
    """Intérprete con faster-whisper: --whisper-python, $WHISPER_PYTHON o ~/.venvs/whisper (config.json > software)."""
    for cand in (explicito, os.environ.get("WHISPER_PYTHON"), WHISPER_PY_DEF):
        if cand and os.path.exists(os.path.expanduser(cand)):
            return os.path.expanduser(cand)
    return None


WHISPER_SCRIPT = r'''
import json, sys, wave, numpy as np
from faster_whisper import WhisperModel
ruta, idioma, modelo, salida = sys.argv[1:5]
# El audio entra como arreglo (wave + numpy): el decode_audio de faster-whisper falla con PyAV >= 16
# (open() got an unexpected keyword argument 'metadata_errors'). Siempre 16 kHz mono PCM16.
w = wave.open(ruta, "rb")
assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
m = WhisperModel(modelo, device="cpu", compute_type="int8")
segs, info = m.transcribe(audio, language=idioma, word_timestamps=True, vad_filter=True, beam_size=5)
out = []
for s in segs:
    out.append({"inicio": round(s.start, 3), "fin": round(s.end, 3), "texto": s.text.strip(),
                "palabras": [{"p": x.word.strip(), "i": round(x.start, 3), "f": round(x.end, 3)}
                             for x in (s.words or [])]})
json.dump({"idioma": info.language, "duracion": info.duration, "modelo": modelo, "segmentos": out},
          open(salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
'''

WHISPER_LOTE = r'''
import json, sys, wave, numpy as np
from faster_whisper import WhisperModel
idioma, modelo, salida = sys.argv[1:4]
m = WhisperModel(modelo, device="cpu", compute_type="int8")
res = {}
for ruta in sys.argv[4:]:
    w = wave.open(ruta, "rb")
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, info = m.transcribe(audio, language=idioma, word_timestamps=True, beam_size=5)
    res[ruta] = [{"p": x.word.strip(), "i": round(x.start, 3), "f": round(x.end, 3)}
                 for s in segs for x in (s.words or [])]
json.dump(res, open(salida, "w", encoding="utf-8"), ensure_ascii=False)
'''


def transcribir_lote(py, wavs, idioma, modelo):
    """Palabras con tiempos de varios wav en UN proceso de whisper (evita cargar el modelo por unidad)."""
    tmps = []
    for wv in wavs:
        t = wv + ".16k.wav"
        comun.run(["ffmpeg", "-v", "error", "-y", "-i", wv, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", t], log=False)
        tmps.append(t)
    salida = os.path.join(os.path.dirname(wavs[0]), "asr_lote.json")
    r = subprocess.run([py, "-I", "-c", WHISPER_LOTE, idioma, modelo, salida, *tmps], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for t in tmps:
        os.remove(t)
    if r.returncode != 0:
        fallo(f"faster-whisper falló: {r.stderr.strip()[-600:]}", 3)
    res = cargar_json(salida)
    return {wv: res.get(wv + ".16k.wav", []) for wv in wavs}



def transcribir_archivo(py, entrada, idioma, modelo, salida_json):
    """Transcribe cualquier audio/video con faster-whisper (tiempos por palabra). Devuelve el JSON."""
    tmp = salida_json + ".16k.wav"
    comun.run(["ffmpeg", "-v", "error", "-y", "-i", entrada, "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", tmp], log=False)
    r = subprocess.run([py, "-I", "-c", WHISPER_SCRIPT, tmp, idioma, modelo, salida_json],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    os.remove(tmp)
    if r.returncode != 0:
        fallo(f"faster-whisper falló: {r.stderr.strip()[-600:]}", 3)
    return cargar_json(salida_json)


def dur(path):
    return comun.dur(path)


_UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
             "trece", "catorce", "quince", "dieciseis", "diecisiete", "dieciocho", "diecinueve", "veinte"]
_DECENAS = ["", "", "veinti", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CIENTOS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
            "ochocientos", "novecientos"]


def numero_a_letras(n):
    """0-999999 en español sin acentos (para comparar guion vs ASR: «500» ≈ «quinientos»)."""
    if n >= 1000:
        miles = n // 1000
        pre = "mil" if miles == 1 else numero_a_letras(miles) + "mil"
        return pre + (numero_a_letras(n % 1000) if n % 1000 else "")
    if n == 100:
        return "cien"
    out = _CIENTOS[n // 100] if n >= 100 else ""
    n %= 100
    if n <= 20:
        out += _UNIDADES[n] if (n or not out) else ""
    elif n < 30:
        out += _DECENAS[2] + _UNIDADES[n - 20]
    else:
        out += _DECENAS[n // 10] + ("y" + _UNIDADES[n % 10] if n % 10 else "")
    return out


def normalizar(tok):
    tok = unicodedata.normalize("NFKD", tok.lower())
    tok = "".join(c for c in tok if not unicodedata.combining(c))
    tok = re.sub(r"[^a-z0-9ñ]", "", tok)
    if tok.isdigit() and len(tok) <= 6:
        tok = numero_a_letras(int(tok))
    return tok


def quitar_marcas(texto):
    return re.sub(r"[{}*]", "", texto)


def tokens_marcados(texto):
    """[(palabra_visible, estilo)] con estilo normal|negrita|resaltado a partir de {..} y *..*."""
    out = []
    for tok in texto.split():
        estilo = "normal"
        if "{" in tok or "}" in tok:
            estilo = "resaltado"
        elif "*" in tok:
            estilo = "negrita"
        vis = tok.replace("{", "").replace("}", "").replace("*", "")
        if vis:
            out.append((vis, estilo))
    return out


# ----------------------------------------------------------------- 1. transcribir


def cmd_transcribir(a):
    py = whisper_python(a.whisper_python)
    if not py:
        fallo("falta faster-whisper: uv venv --python 3.12 ~/.venvs/whisper && "
              "uv pip install --python ~/.venvs/whisper/bin/python faster-whisper", 3)
    if not os.path.exists(a.entrada):
        fallo(f"no existe {a.entrada}")
    proyecto = os.path.abspath(a.proyecto or os.path.dirname(a.entrada))
    comun.AVANCE_DIR = os.path.join(proyecto, "recursos")
    salida = os.path.join(proyecto, "recursos", "doblaje", "transcripcion.json")
    comun.avance("transcripcion", 5, f"faster-whisper {a.modelo} sobre {os.path.basename(a.entrada)}")
    d = transcribir_archivo(py, a.entrada, a.idioma, a.modelo, salida)
    comun.avance("transcripcion", 100, f"{len(d['segmentos'])} segmentos, {sum(len(x['palabras']) for x in d['segmentos'])} palabras")
    n = sum(len(s["palabras"]) for s in d["segmentos"])
    print(f"Transcripción: {salida}")
    print(f"  {len(d['segmentos'])} segmentos, {n} palabras, {d['duracion']:.1f} s, modelo {a.modelo}")
    for s in d["segmentos"][:5]:
        print(f"  [{s['inicio']:6.2f}-{s['fin']:6.2f}] {s['texto']}")
    if len(d["segmentos"]) > 5:
        print("  …")
    print(f"Siguiente: python3 scripts/doblar.py unidades {proyecto}")


# ----------------------------------------------------------------- 2. unidades


def partir_unidad(palabras, max_seg, min_mitad=1.5):
    """Parte una unidad larga en la mejor pausa interna (prefiere la que sigue a una coma)."""
    if not palabras or palabras[-1]["f"] - palabras[0]["i"] <= max_seg:
        return [palabras]
    mejor, puntaje = None, 0.0
    for k in range(1, len(palabras)):
        izq, der = palabras[:k], palabras[k:]
        if izq[-1]["f"] - izq[0]["i"] < min_mitad or der[-1]["f"] - der[0]["i"] < min_mitad:
            continue
        hueco = der[0]["i"] - izq[-1]["f"]
        if hueco < 0.12:
            continue
        p = hueco + (0.3 if izq[-1]["p"].rstrip().endswith((",", ";", ":")) else 0.0)
        if p > puntaje:
            mejor, puntaje = k, p
    if mejor is None:
        return [palabras]
    return partir_unidad(palabras[:mejor], max_seg) + partir_unidad(palabras[mejor:], max_seg)


def agrupar_unidades(transcripcion, max_seg):
    palabras = [w for s in transcripcion["segmentos"] for w in s["palabras"] if w["p"].strip()]
    oraciones, actual = [], []
    for w in palabras:
        actual.append(w)
        if w["p"].rstrip().endswith((".", "?", "!")):
            oraciones.append(actual)
            actual = []
    if actual:
        oraciones.append(actual)
    unidades = []
    for o in oraciones:
        unidades.extend(partir_unidad(o, max_seg))
    total = transcripcion["duracion"]
    out = []
    for k, u in enumerate(unidades):
        sig = unidades[k + 1][0]["i"] if k + 1 < len(unidades) else total
        out.append({"id": k + 1, "inicio": u[0]["i"], "fin": u[-1]["f"],
                    "slot_fin": round(max(u[-1]["f"], sig - 0.08), 3),
                    "en": " ".join(w["p"].strip() for w in u), "es": ""})
    return out


def estilo_captions_default(proyecto):
    fuentes = os.path.join(proyecto, "recursos", "fuentes")
    return {
        "activo": True,
        "fuente_normal": os.path.join(fuentes, "figtree-400.ttf"),
        "fuente_negrita": os.path.join(fuentes, "figtree-700.ttf"),
        "tamano": 71, "centro_y": 1509, "interlineado": 82, "ancho_max": 640, "max_palabras": 4,
        "max_lineas": 2,
        "color_normal": [145, 143, 146], "color_negrita": [26, 24, 25], "color_resaltado": [13, 24, 37],
        "caja_fondo": [207, 221, 244], "caja_borde": [58, 116, 205], "caja_puntos": [60, 120, 240],
        "caja_relleno": [14, 14], "caja_radio": 6, "caja_borde_px": 3, "punto_radio": 10,
        "cubrir": {"y0": 1405, "y1": 1640, "color": [249, 246, 243]},
        "fundido": 0.0,
    }


def cmd_unidades(a):
    proyecto = os.path.abspath(a.proyecto)
    tj = os.path.join(proyecto, "recursos", "doblaje", "transcripcion.json")
    if not os.path.exists(tj):
        fallo(f"falta {tj} (correr `doblar.py transcribir` primero)")
    tr = cargar_json(tj)
    comun.AVANCE_DIR = os.path.join(proyecto, "recursos")
    unidades = agrupar_unidades(tr, a.max_seg)
    entrada = a.entrada
    if not entrada:
        cands = [p for p in (os.path.join(proyecto, "recursos", "origen", "original.mp4"),) if os.path.exists(p)]
        entrada = cands[0] if cands else "recursos/origen/original.mp4"
    spec_ruta = os.path.join(proyecto, "doblaje.json")
    spec = {
        "entrada": os.path.relpath(entrada, proyecto) if os.path.isabs(entrada) else entrada,
        "salida": f"{os.path.basename(proyecto).split('_')[0]}-{a.idioma_destino}.mp4",
        "idioma_origen": tr.get("idioma", "en"), "idioma_destino": a.idioma_destino,
        "voz": {"proveedor": "voicestudio", "atempo_max": 1.25, "ajustar_duracion": True, "speed_max": 1.3,
                "margen_inicio": 0.05, "lufs": -16.0,
                "voicestudio": {"url": VOICESTUDIO_URL_DEF, "profile_id": None,
                                "instruct": "male, middle-aged, moderate pitch",
                                "language": "Spanish", "seed": 7, "speed": 1.0},
                "fish": {"modelo": "fish-audio/s2-pro"},
                "elevenlabs": {"voz_id": None}},
        "audio": {"modo": "reemplazar", "original_db": -20.0},
        "captions": estilo_captions_default(proyecto),
        "rotulos": [],
        "unidades": unidades,
    }
    if os.path.exists(spec_ruta) and not a.forzar:
        fallo(f"ya existe {spec_ruta} (usa --forzar para regenerarlo)")
    guardar_json(spec_ruta, spec)
    comun.avance("unidades", 100, f"{len(unidades)} unidades con slot")
    comun.avance("traduccion", 0, "pendiente: llenar `es` en doblaje.json")
    print(f"Spec: {spec_ruta}  ({len(unidades)} unidades)")
    for u in unidades:
        print(f"  u{u['id']:02d} [{u['inicio']:6.2f}-{u['fin']:6.2f}] slot {u['slot_fin'] - u['inicio']:4.1f}s  {u['en']}")
    print("Siguiente: llenar `es` de cada unidad (marcas: {resaltado} *negrita*), `rotulos` si hay texto "
          "estático en pantalla, y correr: python3 scripts/doblar.py voz " + spec_ruta)


# ----------------------------------------------------------------- 3. voz


def cargar_spec(ruta):
    ruta = os.path.abspath(ruta)
    spec = cargar_json(ruta)
    base = os.path.dirname(ruta)
    spec["_base"] = base
    spec["_ruta"] = ruta
    comun.AVANCE_DIR = os.path.join(base, "recursos")
    for k in ("entrada", "salida"):
        if spec.get(k) and not os.path.isabs(spec[k]):
            spec[k] = os.path.join(base, spec[k])
    if not os.path.exists(spec.get("entrada", "")):
        fallo(f"no existe la entrada {spec.get('entrada')}")
    if not spec.get("unidades"):
        fallo("el spec no tiene `unidades`")
    return spec


def multipart(campos):
    limite = "----doblar" + uuid.uuid4().hex
    cuerpo = bytearray()
    for k, v in campos.items():
        if v is None:
            continue
        cuerpo += f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode()
        cuerpo += str(v).encode("utf-8") + b"\r\n"
    cuerpo += f"--{limite}--\r\n".encode()
    return bytes(cuerpo), f"multipart/form-data; boundary={limite}"


def tts_voicestudio(texto, cfg, speed=None):
    """POST /generate de VoiceStudio (OmniVoice local, CC-BY-NC). Devuelve bytes de audio (wav) o fallo 3/4.
    `speed` (nativo del modelo) sustituye al de la config cuando hay que ajustar la toma al slot."""
    url = (cfg.get("url") or VOICESTUDIO_URL_DEF).rstrip("/")
    campos = {"text": texto, "language": cfg.get("language"), "profile_id": cfg.get("profile_id"),
              "instruct": None if cfg.get("profile_id") else cfg.get("instruct"),
              "seed": cfg.get("seed"), "speed": speed if speed is not None else cfg.get("speed"),
              "effect_preset": cfg.get("effect_preset")}
    cuerpo, ct = multipart(campos)
    req = urllib.request.Request(url + "/generate", data=cuerpo, headers={"Content-Type": ct})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            datos = r.read()
            tipo = r.headers.get("content-type") or ""
    except urllib.error.HTTPError as e:
        fallo(f"VoiceStudio {e.code}: {e.read()[:300]!r}", 4)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        fallo(f"VoiceStudio no responde en {url} (abrir la app y esperar `/health` = ok): {e}", 3)
    if "json" in tipo:
        try:
            j = json.loads(datos)
        except json.JSONDecodeError:
            fallo("VoiceStudio devolvió JSON ilegible", 4)
        ruta = j.get("audio_url") or j.get("url") or j.get("path")
        if not ruta:
            fallo(f"VoiceStudio sin audio en la respuesta: {str(j)[:200]}", 4)
        if ruta.startswith("/"):
            with urllib.request.urlopen(url + ruta, timeout=120) as r2:
                datos = r2.read()
        else:
            with open(ruta, "rb") as f:
                datos = f.read()
    if len(datos) < 1024:
        fallo("VoiceStudio devolvió un audio vacío", 4)
    return datos


def sintetizar(texto, spec, recursos, speed=None):
    """Devuelve (bytes_audio, formato_ffmpeg_args) según el proveedor. Loguea el costo si es de nube."""
    v = spec["voz"]
    prov = v.get("proveedor", "voicestudio")
    if prov == "voicestudio":
        return tts_voicestudio(texto, v.get("voicestudio") or {}, speed), []
    import voz as vozmod  # proveedores de nube ya verificados en voz.py
    if prov == "fish":
        key = comun.api_key(REPO)
        modelo = (v.get("fish") or {}).get("modelo", "fish-audio/s2-pro")
        try:
            pcm, sr, gid, usage = vozmod.tts_fish(texto, key, vozmod._url_speech(REPO), modelo)
        except vozmod.ErrorTTS as e:
            fallo(str(e), 4)
        comun.log_costo(recursos, {"id": gid, "modelo": modelo, "tarea": "doblaje_tts", "usage": usage})
        return pcm, ["-f", "s16le", "-ar", str(sr), "-ac", "1"]
    if prov == "elevenlabs":
        key = vozmod._key_opcional(REPO, "ELEVENLABS_API_KEY")
        if not key:
            fallo("ELEVENLABS_API_KEY no está configurada (AGENT §5: no pedirla; usar otro proveedor)", 3)
        voz_id = (v.get("elevenlabs") or {}).get("voz_id") or vozmod.ELEVEN_VOZ_DEF
        try:
            datos, sr, gid, usage = vozmod.tts_elevenlabs(texto, voz_id, key)
        except vozmod.ErrorTTS as e:
            fallo(str(e), 4)
        comun.log_costo(recursos, {"id": gid, "modelo": "elevenlabs", "tarea": "doblaje_tts", "usage": usage})
        return datos, []
    fallo(f"proveedor de voz desconocido: {prov}")


def region_habla(wav, umbral_db=-38.0, min_sil=0.08):
    """(inicio, fin) de la voz dentro del wav según silencedetect; si no hay silencios, todo el archivo."""
    total = dur(wav)
    r = subprocess.run(["ffmpeg", "-nostdin", "-i", wav, "-af",
                        f"silencedetect=n={umbral_db}dB:d={min_sil}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ini, fin = 0.0, total
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    if starts and starts[0] < 0.02 and ends:
        ini = ends[0]
    if starts and (not ends or starts[-1] > (ends[-1] if ends else 0)):
        fin = starts[-1]
    return max(0.0, ini), max(ini + 0.05, fin)


def recortar(wav_in, wav_out, ini, fin, atempo=1.0, colchon=0.05):
    """Deja solo la región de habla (+colchón), 48 kHz mono, opcionalmente acelerada."""
    filtros = []
    if abs(atempo - 1.0) > 0.005:
        filtros.append(f"atempo={atempo:.4f}")
    filtros.append(f"adelay={int(colchon * 1000)}|{int(colchon * 1000)}")
    comun.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ini:.3f}", "-to", f"{fin:.3f}", "-i", wav_in,
               "-af", ",".join(filtros), "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", wav_out], log=False)


def alinear_palabras(script_tokens, asr_palabras, dur_total):
    """Tiempos por palabra del guion a partir de la ASR del wav (difflib); las no emparejadas se interpolan."""
    a = [normalizar(t) for t in script_tokens]
    b = [normalizar(w["p"]) for w in asr_palabras]
    tiempos = [None] * len(a)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                tiempos[i1 + k] = (asr_palabras[j1 + k]["i"], asr_palabras[j1 + k]["f"])
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                tiempos[i1 + k] = (asr_palabras[j1 + k]["i"], asr_palabras[j1 + k]["f"])
    # interpolar huecos entre anclas (o entre 0 y dur_total)
    n = len(a)
    k = 0
    while k < n:
        if tiempos[k] is not None:
            k += 1
            continue
        j = k
        while j < n and tiempos[j] is None:
            j += 1
        t0 = tiempos[k - 1][1] if k > 0 else 0.0
        t1 = tiempos[j][0] if j < n else dur_total
        m = j - k
        pesos = [max(1, len(a[x])) for x in range(k, j)]
        tot = sum(pesos) or 1
        acc = t0
        for x in range(k, j):
            d = (t1 - t0) * pesos[x - k] / tot
            tiempos[x] = (acc, acc + d)
            acc += d
        k = j
    return tiempos


def cmd_voz(a):
    spec = cargar_spec(a.spec)
    base = spec["_base"]
    recursos = os.path.join(base, "recursos")
    carpeta = os.path.join(recursos, "doblaje", "voz")
    os.makedirs(carpeta, exist_ok=True)
    v = spec["voz"]
    prov = v.get("proveedor", "voicestudio")
    py = whisper_python(a.whisper_python)
    if not py:
        aviso("sin faster-whisper: los tiempos por palabra se repartirán por longitud (menos precisos)")
    pendientes = [u for u in spec["unidades"] if not (u.get("es") or "").strip()]
    n_u = len(spec["unidades"])
    comun.avance("traduccion", 100 * (n_u - len(pendientes)) / max(1, n_u), f"{n_u - len(pendientes)}/{n_u} unidades traducidas")
    if pendientes:
        fallo(f"{len(pendientes)} unidades sin `es` (p. ej. u{pendientes[0]['id']}): traducir antes de sintetizar")
    comun.avance("voz", 0, f"sintetizando {n_u} unidades con {prov}")
    total_video = dur(spec["entrada"])
    tiempos_json = os.path.join(recursos, "doblaje", "tiempos.json")
    previo = cargar_json(tiempos_json) if os.path.exists(tiempos_json) else {"unidades": {}}
    resultados = {}
    largas = []
    for u in spec["unidades"]:
        uid = f"u{u['id']:02d}"
        texto_tts = quitar_marcas(u.get("es_tts") or u["es"]).strip()
        slot = u["slot_fin"] - u["inicio"]
        huella_base = {"texto": texto_tts, "proveedor": prov, "cfg": v.get(prov)}
        h = hashlib.sha1(json.dumps(huella_base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
        crudo = os.path.join(carpeta, f"{uid}_{h}.raw.wav")
        if not os.path.exists(crudo) or a.regenerar:
            datos, fargs = sintetizar(texto_tts, spec, recursos)
            tmp = crudo + ".bin"
            with open(tmp, "wb") as f:
                f.write(datos)
            comun.run(["ffmpeg", "-v", "error", "-y", *fargs, "-i", tmp, "-ar", str(SR), "-ac", "1",
                       "-c:a", "pcm_s16le", crudo], log=False)
            os.remove(tmp)
        ini, fin = region_habla(crudo)
        natural = fin - ini
        atempo = 1.0
        fuente = crudo
        # 1) velocidad nativa (VoiceStudio `speed`, verificado 2026-10-30: 1.25 → 0.82 de la duración):
        #    regenerar con speed = natural/slot (tope voz.speed_max, 1.3) en vez de estirar con atempo
        if natural > slot and prov == "voicestudio" and v.get("ajustar_duracion", True) and natural / slot <= 1.6:
            base_speed = float((v.get("voicestudio") or {}).get("speed") or 1.0)
            factor = round(min(float(v.get("speed_max", 1.3)), natural / slot * 1.03) * base_speed, 3)
            ajustado = os.path.join(carpeta, f"{uid}_{h}_v{factor}.raw.wav")
            if not os.path.exists(ajustado) or a.regenerar:
                datos, fargs = sintetizar(texto_tts, spec, recursos, speed=factor)
                tmp = ajustado + ".bin"
                with open(tmp, "wb") as f:
                    f.write(datos)
                comun.run(["ffmpeg", "-v", "error", "-y", *fargs, "-i", tmp, "-ar", str(SR), "-ac", "1",
                           "-c:a", "pcm_s16le", ajustado], log=False)
                os.remove(tmp)
            i2, f2 = region_habla(ajustado)
            if (f2 - i2) < natural:
                fuente, ini, fin, natural = ajustado, i2, f2, f2 - i2
        # 2) atempo hasta atempo_max
        if natural > slot:
            atempo = min(natural / slot, float(v.get("atempo_max", 1.25)))
        final = os.path.join(carpeta, f"{uid}.wav")
        recortar(fuente, final, ini, fin, atempo, colchon=float(v.get("margen_inicio", 0.05)))
        d = dur(final)
        exceso = d - slot
        if exceso > 0.05:
            largas.append((uid, exceso, texto_tts))
        resultados[uid] = {"id": u["id"], "inicio": u["inicio"], "slot_fin": u["slot_fin"], "wav": final,
                           "duracion": round(d, 3), "natural": round(natural, 3), "atempo": round(atempo, 3),
                           "_es": u["es"]}
        marca = "" if exceso <= 0.05 else f"  ← +{exceso:.2f}s"
        print(f"  {uid} natural {natural:4.2f}s → {d:4.2f}s / slot {slot:4.2f}s  atempo {atempo:.2f}{marca}", flush=True)
        nota = (f"speed {fuente.rsplit('_v', 1)[1].split('.raw')[0]}" if "_v" in os.path.basename(fuente) else "") + (f" atempo {atempo:.2f}" if atempo > 1.0 else "")
        comun.avance("voz", 100 * u["id"] / n_u * 0.92, f"{uid} {d:.2f} s en un hueco de {slot:.2f} s",
                     estado="aviso" if exceso > 0.05 else "en_curso",
                     datos={"etiqueta": uid, "valor": round(d, 3), "limite": round(slot, 3), "unidad": "s", "nota": nota.strip() or None})
    # tiempos por palabra (ASR de los wav nuevos en un solo proceso; sin whisper, reparto por longitud)
    comun.avance("voz", 94, "tiempos por palabra (ASR de los wav nuevos)")
    asr = transcribir_lote(py, [r["wav"] for _, r in sorted(resultados.items())],
                           spec.get("idioma_destino", "es"), a.modelo) if py else {}
    for uid, r in resultados.items():
        marcados = tokens_marcados(r.pop("_es"))
        tiempos = alinear_palabras([t for t, _ in marcados], asr.get(r["wav"], []), r["duracion"])
        r["palabras"] = [{"p": tok, "estilo": est, "i": round(r["inicio"] + t[0], 3), "f": round(r["inicio"] + t[1], 3)}
                         for (tok, est), t in zip(marcados, tiempos)]
    # pista completa
    pista = os.path.join(recursos, "doblaje", f"voz_{spec.get('idioma_destino', 'es')}.wav")
    ensamblar_pista(resultados, total_video, pista, float(v.get("lufs", -16.0)))
    guardar_json(tiempos_json, {"unidades": resultados, "pista": pista, "duracion": total_video})
    comun.avance("voz", 100, f"pista de voz ensamblada ({total_video:.1f} s)" + (f", {len(largas)} unidades se pasan" if largas else ""),
                 estado="aviso" if largas else "listo")
    print(f"Pista de voz: {pista}  ({total_video:.2f} s)   tiempos: {tiempos_json}")
    for uid, exceso, texto in largas:
        aviso(f"W-DOBLAJE-LARGO {uid} se pasa {exceso:.2f}s de su slot: acortar `es` o subir atempo_max — «{texto[:70]}»")
    print(f"Siguiente: python3 scripts/doblar.py render {spec['_ruta']}")


def ensamblar_pista(resultados, total, salida, lufs):
    """Coloca cada unidad en su inicio dentro de una pista de silencio (48 kHz mono) y normaliza a `lufs`."""
    n_total = int(math.ceil(total * SR)) + SR
    buf = array("h", bytes(2 * n_total))
    for uid, r in sorted(resultados.items()):
        with wave.open(r["wav"], "rb") as w:
            assert w.getframerate() == SR and w.getnchannels() == 1
            datos = array("h", w.readframes(w.getnframes()))
        o = int(round(r["inicio"] * SR))
        fin = min(o + len(datos), n_total)
        tramo = buf[o:fin]
        if any(tramo):
            for k in range(fin - o):  # solape con la unidad anterior: sumar con tope
                buf[o + k] = max(-32768, min(32767, buf[o + k] + datos[k]))
        else:
            buf[o:fin] = datos[:fin - o]
    tmp = salida + ".crudo.wav"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(buf[:int(total * SR)].tobytes())
    comun.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
               "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", salida], log=False)
    os.remove(tmp)


# ----------------------------------------------------------------- 4. render


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        return True
    except ImportError:
        return False


def asegurar_pillow():
    if _pil():
        return
    alt = "/opt/homebrew/bin/python3"
    if os.path.exists(alt) and os.path.realpath(sys.executable) != os.path.realpath(alt) \
            and not os.environ.get("DOBLAR_REEXEC"):
        os.environ["DOBLAR_REEXEC"] = "1"
        os.execv(alt, [alt, "-I", *sys.argv])
    fallo("falta Pillow (pip install pillow en un intérprete con PIL, p. ej. /opt/homebrew/bin/python3)", 3)


def partir_cues(palabras, cap, medir):
    """Agrupa palabras en cues de ≤ max_palabras que quepan en ≤ max_lineas de ancho_max px."""
    maxp = int(cap.get("max_palabras", 4))
    maxl = int(cap.get("max_lineas", 2))
    ancho = int(cap.get("ancho_max", 640))
    cues, actual = [], []

    def cabe(ws):
        return len(partir_lineas(ws, ancho, medir)) <= maxl

    for w in palabras:
        prueba = actual + [w]
        if actual and (len(prueba) > maxp or not cabe(prueba)):
            cues.append(actual)
            actual = [w]
        else:
            actual = prueba
        if actual and actual[-1]["p"].endswith((".", "?", "!", ":", ";")) and len(actual) >= 2:
            cues.append(actual)
            actual = []
    if actual:
        cues.append(actual)
    return cues


def partir_lineas(ws, ancho, medir):
    lineas, linea = [], []
    for w in ws:
        prueba = linea + [w]
        if linea and medir(prueba) > ancho:
            lineas.append(linea)
            linea = [w]
        else:
            linea = prueba
    if linea:
        lineas.append(linea)
    return lineas


def dibujar_cue(ws, cap, fuentes, tam_banda, transparente=False):
    from PIL import Image, ImageDraw
    fn, fb = fuentes
    ancho_img, alto_img = 1080, tam_banda[1] - tam_banda[0]
    im = Image.new("RGBA", (ancho_img, alto_img), (0, 0, 0, 0) if transparente else tuple(cap["cubrir"]["color"]) + (255,))
    d = ImageDraw.Draw(im)
    esp = fn.getlength(" ")
    centro_y = cap["centro_y"] - tam_banda[0]
    inter = cap["interlineado"]

    def ancho_linea(ws_):
        return sum((fb if w["estilo"] != "normal" else fn).getlength(w["p"]) for w in ws_) + esp * (len(ws_) - 1)

    lineas = partir_lineas(ws, cap["ancho_max"], ancho_linea) if ws else []
    n = len(lineas)
    asc_n, desc_n = fn.getmetrics()
    cap_h = fb.getbbox("H")[3] - fb.getbbox("H")[1]
    rel_x, rel_y = cap.get("caja_relleno", [20, 24])
    for li, linea in enumerate(lineas):
        y_centro = centro_y + (li - (n - 1) / 2) * inter
        y_base = y_centro + cap_h / 2  # línea base: centro de las mayúsculas en y_centro
        x = (ancho_img - ancho_linea(linea)) / 2
        # cajas: un grupo de palabras resaltadas contiguas comparte una sola caja
        xs, grupos, gi = x, [], None
        for k, w in enumerate(linea):
            f = fb if w["estilo"] != "normal" else fn
            ancho_w = f.getlength(w["p"])
            if w["estilo"] == "resaltado":
                if gi is None:
                    gi = [xs, xs + ancho_w]
                    grupos.append(gi)
                else:
                    gi[1] = xs + ancho_w
            else:
                gi = None
            xs += ancho_w + esp
        for gx0, gx1 in grupos:
            x0, y0 = gx0 - rel_x, y_base - cap_h - rel_y
            x1, y1 = gx1 + rel_x, y_base + rel_y * 0.85
            d.rounded_rectangle([x0, y0, x1, y1], radius=cap.get("caja_radio", 6),
                                fill=tuple(cap["caja_fondo"]) + (255,),
                                outline=tuple(cap["caja_borde"]) + (255,), width=int(cap.get("caja_borde_px", 3)))
            r = cap.get("punto_radio", 11)
            for (px, py) in ((x0, y0), (x1, y1)):
                d.ellipse([px - r, py - r, px + r, py + r], fill=tuple(cap["caja_puntos"]) + (255,))
        for w in linea:
            f = fb if w["estilo"] != "normal" else fn
            ancho_w = f.getlength(w["p"])
            if w["estilo"] == "resaltado":
                color = tuple(cap["color_resaltado"])
            elif w["estilo"] == "negrita":
                color = tuple(cap["color_negrita"])
            else:
                color = tuple(cap["color_normal"])
            d.text((x, y_base), w["p"], font=f, fill=color + (255,), anchor="ls")
            x += ancho_w + esp
    return im


def dibujar_rotulo(rot, fuente, cubrir):
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = cubrir
    im = Image.new("RGBA", (x1 - x0, y1 - y0), tuple(rot.get("color_fondo") or [249, 246, 243]) + (255,))
    d = ImageDraw.Draw(im)
    d.text((rot["x"] - x0, rot["y"] - y0), rot["texto"], font=fuente, fill=tuple(rot["color"]) + (255,), anchor="lt")
    return im


def escribir_ffconcat(ruta, items, total, vacio):
    """items = [(inicio, fin, png)]; los huecos se rellenan con `vacio`. Duraciones a 1/30 s."""
    lineas = ["ffconcat version 1.0"]
    t = 0.0
    tramos = []
    for ini, fin, png in sorted(items):
        ini, fin = max(ini, t), max(ini, min(fin, total))
        if ini > t + 1e-3:
            tramos.append((t, ini, vacio))
        if fin > ini:
            tramos.append((ini, fin, png))
        t = max(t, fin)
    if t < total:
        tramos.append((t, total, vacio))
    for ini, fin, png in tramos:
        lineas.append(f"file '{png}'")
        lineas.append(f"duration {fin - ini:.4f}")
    lineas.append(f"file '{tramos[-1][2]}'")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def cmd_render(a):
    asegurar_pillow()
    from PIL import ImageFont
    spec = cargar_spec(a.spec)
    base = spec["_base"]
    recursos = os.path.join(base, "recursos")
    tiempos_json = os.path.join(recursos, "doblaje", "tiempos.json")
    if not os.path.exists(tiempos_json):
        fallo(f"falta {tiempos_json} (correr `doblar.py voz` primero)")
    tiempos = cargar_json(tiempos_json)
    total = dur(spec["entrada"])
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate", "-of", "csv=p=0", spec["entrada"]],
                           capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip().split(",")
    ancho, alto = int(probe[0]), int(probe[1])
    fps = probe[2]
    carpeta = os.path.join(recursos, "doblaje", "overlays")
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta)
    entradas = ["-i", spec["entrada"]]
    filtros = []
    etiqueta = "[0:v]"
    n_in = 1
    cap = spec.get("captions") or {}
    n_cues = 0
    if cap.get("activo", True) and not a.sin_captions:
        for k in ("fuente_normal", "fuente_negrita"):
            if not os.path.isabs(cap[k]):
                cap[k] = os.path.join(base, cap[k])
            if not os.path.exists(cap[k]):
                fallo(f"falta la fuente {cap[k]} (convertir con `pantalla.py fuente <woff2> <ttf> --peso N`)", 2)
        fn = ImageFont.truetype(cap["fuente_normal"], int(cap["tamano"]))
        fb = ImageFont.truetype(cap["fuente_negrita"], int(cap["tamano"]))
        banda = (int(cap["cubrir"]["y0"]), int(cap["cubrir"]["y1"]))
        esp = fn.getlength(" ")

        def medir(ws):
            return sum((fb if w["estilo"] != "normal" else fn).getlength(w["p"]) for w in ws) + esp * (len(ws) - 1)

        items = []
        unidades = sorted(tiempos["unidades"].values(), key=lambda r: r["inicio"])
        for idx, r in enumerate(unidades):
            cues = partir_cues(r["palabras"], cap, medir)
            sig_ini = unidades[idx + 1]["palabras"][0]["i"] if idx + 1 < len(unidades) and unidades[idx + 1]["palabras"] else total
            for ci, ws in enumerate(cues):
                ini = ws[0]["i"]
                fin = cues[ci + 1][0]["i"] if ci + 1 < len(cues) else min(ws[-1]["f"] + 0.25, sig_ini)
                png = os.path.join(carpeta, f"cue_{n_cues:04d}.png")
                dibujar_cue(ws, cap, (fn, fb), banda).save(png)
                items.append((ini, fin, png))
                n_cues += 1
        vacio = os.path.join(carpeta, "cue_vacio.png")
        dibujar_cue([], cap, (fn, fb), banda).save(vacio)
        concat = os.path.join(carpeta, "captions.ffconcat")
        escribir_ffconcat(concat, items, total, vacio)
        entradas += ["-f", "concat", "-safe", "0", "-i", concat]
        filtros.append(f"[{n_in}:v]format=rgba,setpts=PTS-STARTPTS[cap]")
        filtros.append(f"{etiqueta}[cap]overlay=0:{banda[0]}:format=auto:eof_action=pass[v{n_in}]")
        etiqueta = f"[v{n_in}]"
        n_in += 1
    rotulos = spec.get("rotulos") or []
    if rotulos:
        items = []
        cub = None
        for ri, rot in enumerate(rotulos):
            fr = rot.get("fuente") or os.path.join(recursos, "fuentes", "jetbrains-mono-400.ttf")
            if not os.path.isabs(fr):
                fr = os.path.join(base, fr)
            if not os.path.exists(fr):
                fallo(f"falta la fuente del rótulo {fr} (convertir con `pantalla.py fuente <woff2> <ttf> --peso N`)", 2)
            fuente = ImageFont.truetype(fr, int(rot.get("tamano", 30)))
            cub = rot.get("cubrir") or cub
            if not cub:
                fallo("cada rótulo (o el primero) necesita `cubrir`: [x0, y0, x1, y1]")
            png = os.path.join(carpeta, f"rot_{ri:03d}.png")
            dibujar_rotulo(rot, fuente, cub).save(png)
            items.append((float(rot["inicio"]), float(rot["fin"]) if rot.get("fin") is not None else total, png))
        vacio = os.path.join(carpeta, "rot_vacio.png")
        dibujar_rotulo({"texto": "", "x": 0, "y": 0, "color": [0, 0, 0]}, fuente, cub).save(vacio)
        concat = os.path.join(carpeta, "rotulos.ffconcat")
        escribir_ffconcat(concat, items, total, vacio)
        entradas += ["-f", "concat", "-safe", "0", "-i", concat]
        filtros.append(f"[{n_in}:v]format=rgba,setpts=PTS-STARTPTS[rot]")
        filtros.append(f"{etiqueta}[rot]overlay={cub[0]}:{cub[1]}:format=auto:eof_action=pass[v{n_in}]")
        etiqueta = f"[v{n_in}]"
        n_in += 1
    # audio
    pista = tiempos["pista"]
    entradas += ["-i", pista]
    a_in = n_in
    modo = (spec.get("audio") or {}).get("modo", "reemplazar")
    if modo == "mezclar":
        db = float((spec.get("audio") or {}).get("original_db", -20.0))
        filtros.append(f"[0:a]volume={db}dB[orig];[{a_in}:a][orig]amix=inputs=2:duration=first:normalize=0[a]")
        mapa_a = "[a]"
    else:
        mapa_a = f"{a_in}:a"
    filtros.append(f"{etiqueta}format=yuv420p[vout]")
    salida = ruta_cuerpo(spec) if spec.get("cortinillas") else spec["salida"]
    cmd = ["ffmpeg", "-y", "-nostdin", *entradas, "-filter_complex", ";".join(filtros),
           "-map", "[vout]", "-map", mapa_a, "-r", fps, "-c:v", "libx264", "-crf", str(a.crf), "-preset", a.preset,
           "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-t", f"{total:.3f}", "-movflags", "+faststart", salida]
    print(f"Overlays: {n_cues} cues + {len(rotulos)} rótulos en {carpeta}")
    comun.avance("render", 0, f"{n_cues} cues + {len(rotulos)} rótulos; codificando con FFmpeg")
    if a.solo_comando:
        print(" ".join(f"'{c}'" if " " in c or ";" in c else c for c in cmd))
        return
    comun.ffmpeg_con_progreso(cmd, total, etiqueta="render doblaje")
    comun.avance("render", 100, f"{os.path.basename(salida)} ({dur(salida):.2f} s)")
    print(f"Salida: {salida}  ({dur(salida):.2f} s; original {total:.2f} s; {ancho}x{alto} @ {fps})")
    if spec.get("cortinillas"):
        print(f"Siguiente: python3 scripts/doblar.py cortinillas {spec['_ruta']}  (intro + cierre → {spec['salida']})")
    else:
        print("Siguiente: revisar fotogramas de frontera y la sincronía voz/caption; copiar a la carpeta de entrega")


def cmd_todo(a):
    cmd_voz(a)
    cmd_render(a)
    if (cargar_json(a.spec).get("cortinillas") or {}).get("intro") or (cargar_json(a.spec).get("cortinillas") or {}).get("cierre"):
        cmd_cortinillas(a)


# ----------------------------------------------------------------- 4b. cortinillas (intro / cierre)


def ruta_cuerpo(spec):
    return os.path.join(spec["_base"], "recursos", "doblaje", "cuerpo.mp4")


def dibujar_tarjeta(cfg, cap, base, ancho, alto):
    """Tarjeta de intro/cierre en el estilo de la pieza: (capa_titulo RGBA, capa_fija RGBA).
    `lineas` usa las marcas {resaltado} *negrita*; `sub` y `credito` son texto plano."""
    from PIL import Image, ImageDraw, ImageFont
    tam = int(cfg.get("tamano") or round(cap["tamano"] * 1.25))
    fn = ImageFont.truetype(cap["fuente_normal"], tam)
    fb = ImageFont.truetype(cap["fuente_negrita"], tam)
    estilo = dict(cap)
    estilo.update({"tamano": tam, "interlineado": int(tam * 1.18), "ancho_max": int(cfg.get("ancho_max") or 880),
                   "centro_y": int(cfg.get("centro_y") or alto * 0.44), "max_lineas": 6,
                   "caja_relleno": [int(cap["caja_relleno"][0] * tam / cap["tamano"]), int(cap["caja_relleno"][1] * tam / cap["tamano"])],
                   "punto_radio": int(cap.get("punto_radio", 10) * tam / cap["tamano"])})
    # respeta los saltos pedidos en `lineas`; si una línea no cabe en ancho_max se parte en sublíneas
    esp = fn.getlength(" ")

    def medir(ws):
        return sum((fb if w["estilo"] != "normal" else fn).getlength(w["p"]) for w in ws) + esp * (len(ws) - 1)

    sublineas = []
    for ln in cfg.get("lineas") or []:
        ws = [{"p": t, "estilo": e} for t, e in tokens_marcados(ln)]
        sublineas.extend(partir_lineas(ws, estilo["ancho_max"], medir) if ws else [])
    titulo = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    n = len(sublineas)
    for i, ws in enumerate(sublineas):
        e2 = dict(estilo)
        e2["centro_y"] = estilo["centro_y"] + (i - (n - 1) / 2) * estilo["interlineado"]
        titulo.alpha_composite(dibujar_cue(ws, e2, (fn, fb), (0, alto), transparente=True))
    fija = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(fija)
    mono_ruta = cfg.get("fuente_mono") or os.path.join(base, "recursos", "fuentes", "jetbrains-mono-400.ttf")
    mono = ImageFont.truetype(mono_ruta, 24) if os.path.exists(mono_ruta) else fn
    gris = tuple(cap["color_normal"]) + (255,)
    if cfg.get("kicker"):
        d.text((129, 129), cfg["kicker"], font=mono, fill=(134, 132, 129, 255), anchor="lt")
    if cfg.get("sub"):
        fs = ImageFont.truetype(cap["fuente_normal"], int(tam * 0.55))
        y_sub = estilo["centro_y"] + (n / 2) * estilo["interlineado"] + int(tam * 0.55)
        d.text((ancho / 2, y_sub), cfg["sub"], font=fs, fill=gris, anchor="mm")
    if cfg.get("credito"):
        d.text((ancho / 2, alto - 150), cfg["credito"], font=mono, fill=(134, 132, 129, 255), anchor="mm")
    return titulo, fija


def render_cortinilla(nombre, cfg, spec, carpeta, ancho, alto, fps, solo_tarjetas=False):
    """Clip mp4 de la cortinilla: fondo liso + título que sube y se funde + capa fija + voz. Devuelve (ruta, dur)."""
    cap = spec["captions"]
    base = spec["_base"]
    recursos = os.path.join(base, "recursos")
    titulo, fija = dibujar_tarjeta(cfg, cap, base, ancho, alto)
    p_tit = os.path.join(carpeta, f"{nombre}_titulo.png")
    p_fija = os.path.join(carpeta, f"{nombre}_fija.png")
    titulo.save(p_tit)
    fija.save(p_fija)
    colchon = float(cfg.get("colchon", 0.8))
    voz_wav = None
    d_voz = 0.0
    if cfg.get("voz") and not solo_tarjetas:
        h = hashlib.sha1(json.dumps({"t": cfg["voz"], "c": spec["voz"].get(spec["voz"].get("proveedor"))}, sort_keys=True).encode()).hexdigest()[:10]
        crudo = os.path.join(recursos, "doblaje", "voz", f"cort_{nombre}_{h}.raw.wav")
        if not os.path.exists(crudo):
            datos, fargs = sintetizar(cfg["voz"], spec, recursos)
            tmp = crudo + ".bin"
            with open(tmp, "wb") as f:
                f.write(datos)
            comun.run(["ffmpeg", "-v", "error", "-y", *fargs, "-i", tmp, "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", crudo], log=False)
            os.remove(tmp)
        voz_wav = os.path.join(recursos, "doblaje", "voz", f"cort_{nombre}.wav")
        ini, fin = region_habla(crudo)
        recortar(crudo, voz_wav, ini, fin, 1.0, colchon=0.0)
        d_voz = dur(voz_wav)
    inicio_voz = float(cfg.get("inicio_voz", 0.6))
    D = max(float(cfg.get("duracion_min", 3.0)), inicio_voz + d_voz + colchon)
    fondo = "0x%02X%02X%02X" % tuple(cap["cubrir"]["color"])
    salida = os.path.join(carpeta, f"{nombre}.mp4")
    sube = float(cfg.get("subida_px", 28))
    entradas = ["-f", "lavfi", "-i", f"color=c={fondo}:s={ancho}x{alto}:r={fps}:d={D:.3f}", "-loop", "1", "-framerate", fps, "-t", f"{D:.3f}", "-i", p_tit,
                "-loop", "1", "-framerate", fps, "-t", f"{D:.3f}", "-i", p_fija]
    filtros = [f"[1:v]format=rgba,fade=t=in:st=0:d=0.6:alpha=1[t]", f"[2:v]format=rgba,fade=t=in:st=0.2:d=0.5:alpha=1[f]",
               f"[0:v][t]overlay=0:'{sube}*(1-min(t/0.7,1))':format=auto[v1]", "[v1][f]overlay=0:0:format=auto,format=yuv420p[v]"]
    if voz_wav:
        entradas += ["-i", voz_wav]
        filtros.append(f"[3:a]adelay={int(inicio_voz * 1000)}|{int(inicio_voz * 1000)},apad=whole_dur={D:.3f},loudnorm=I={spec['voz'].get('lufs', -16)}:TP=-1.5:LRA=11,aresample=48000[a]")
    else:
        entradas += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono:d={D:.3f}"]
        filtros.append("[3:a]anull[a]")
    cmd = ["ffmpeg", "-y", "-nostdin", *entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]",
           "-r", fps, "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
           "-t", f"{D:.3f}", salida]
    comun.run(cmd, log=False)
    return salida, dur(salida)


def cmd_cortinillas(a):
    asegurar_pillow()
    spec = cargar_spec(a.spec)
    cort = spec.get("cortinillas") or {}
    if not cort.get("intro") and not cort.get("cierre"):
        fallo("el spec no tiene `cortinillas.intro` ni `cortinillas.cierre`")
    cuerpo = ruta_cuerpo(spec)
    if not os.path.exists(cuerpo):
        if os.path.exists(spec["salida"]):
            shutil.copy2(spec["salida"], cuerpo)   # cuerpo renderizado antes de declarar cortinillas
        else:
            fallo(f"falta el cuerpo doblado {cuerpo} (correr `doblar.py render`)")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                            "-of", "csv=p=0", cuerpo], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip().split(",")
    ancho, alto, fps = int(probe[0]), int(probe[1]), probe[2]
    carpeta = os.path.join(spec["_base"], "recursos", "doblaje", "cortinillas")
    os.makedirs(carpeta, exist_ok=True)
    fade = float(cort.get("fade", 0.5))
    if not a.solo_tarjetas:
        comun.avance("cortinillas", 0, "tarjetas y voz de intro/cierre")
    piezas = []
    for nombre in ("intro", "cierre"):
        if cort.get(nombre):
            ruta, d = render_cortinilla(nombre, cort[nombre], spec, carpeta, ancho, alto, fps, a.solo_tarjetas)
            piezas.append((nombre, ruta, d))
            print(f"  {nombre}: {d:.2f} s")
    if a.solo_tarjetas:
        print(f"Tarjetas en {carpeta} (sin voz, sin unir)")
        return
    d_cuerpo = dur(cuerpo)
    orden = [(n, r, d) for n, r, d in piezas if n == "intro"] + [("cuerpo", cuerpo, d_cuerpo)] + [(n, r, d) for n, r, d in piezas if n == "cierre"]
    entradas = []
    for _, r, _ in orden:
        entradas += ["-i", r]
    filtros = []
    v_prev, a_prev, t_acum = "[0:v]", "[0:a]", orden[0][2]
    for k in range(1, len(orden)):
        off = t_acum - fade
        filtros.append(f"{v_prev}[{k}:v]xfade=transition=fade:duration={fade}:offset={off:.3f}[v{k}]")
        filtros.append(f"{a_prev}[{k}:a]acrossfade=d={fade}[a{k}]")
        v_prev, a_prev = f"[v{k}]", f"[a{k}]"
        t_acum = off + orden[k][2]
    salida = spec["salida"]
    cmd = ["ffmpeg", "-y", "-nostdin", *entradas, "-filter_complex", ";".join(filtros), "-map", v_prev, "-map", a_prev,
           "-r", fps, "-c:v", "libx264", "-crf", str(a.crf), "-preset", a.preset, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", salida]
    comun.avance("cortinillas", None, "uniendo intro + cuerpo + cierre (xfade)")
    comun.ffmpeg_con_progreso(cmd, t_acum, etiqueta="cortinillas", etapa="cortinillas")
    comun.avance("cortinillas", 100, f"{os.path.basename(salida)} ({dur(salida):.2f} s)")
    print(f"Salida: {salida}  ({dur(salida):.2f} s = {' + '.join(f'{n} {d:.1f}' for n, _, d in orden)} − {fade}·{len(orden) - 1} de xfade)")
    print(f"Siguiente: python3 scripts/doblar.py verificar {spec['_ruta']}")


# ----------------------------------------------------------------- 5. verificar


def ocr_recorte(video, t, caja, escala=3, carpeta=None, psm=7):
    """OCR (tesseract --psm 7) de un recorte [x0,y0,x1,y1] del fotograma en t. Devuelve texto o None.
    El PNG temporal va en `carpeta` (recursos/ del proyecto): en el sandbox tesseract no puede abrir /tmp."""
    if not shutil.which("tesseract"):
        return None
    x0, y0, x1, y1 = caja
    tmp = os.path.join(carpeta or os.path.dirname(video), f"ocr_tmp_{os.getpid()}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                    "-vf", f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0},scale=iw*{escala}:ih*{escala}", tmp],
                   capture_output=True)
    r = subprocess.run(["tesseract", tmp, "-", "--psm", str(psm)], capture_output=True)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return " ".join(r.stdout.decode("utf-8", "replace").split())


def cmd_verificar(a):
    spec = cargar_spec(a.spec)
    base = spec["_base"]
    salida = spec["salida"]
    if not os.path.exists(salida):
        fallo(f"no existe la salida {salida} (correr `doblar.py render`)")
    tiempos = cargar_json(os.path.join(base, "recursos", "doblaje", "tiempos.json"))
    problemas = []
    comun.avance("verificacion", 10, "ASR de la salida y OCR de muestras")
    d_in, d_out = dur(spec["entrada"]), dur(salida)
    desfase = 0.0   # con cortinillas, el cuerpo empieza tras la intro (menos el xfade)
    cort = spec.get("cortinillas") or {}
    d_cuerpo = d_out
    if cort:
        cuerpo = ruta_cuerpo(spec)
        d_cuerpo = dur(cuerpo) if os.path.exists(cuerpo) else d_in
        intro = os.path.join(base, "recursos", "doblaje", "cortinillas", "intro.mp4")
        desfase = (dur(intro) - float(cort.get("fade", 0.5))) if cort.get("intro") and os.path.exists(intro) else 0.0
        print(f"Duración: {d_out:.3f} s (cuerpo {d_cuerpo:.3f} s + cortinillas; original {d_in:.3f} s)")
        if abs(d_cuerpo - d_in) > 0.08:
            problemas.append(f"el cuerpo difiere del original {d_cuerpo - d_in:+.2f} s")
    else:
        print(f"Duración: {d_out:.3f} s (original {d_in:.3f} s)")
        if abs(d_in - d_out) > 0.08:
            problemas.append(f"duración difiere {d_out - d_in:+.2f} s")
    # voz: ASR de la salida vs guion por unidad
    py = whisper_python(a.whisper_python)
    if py:
        asr_json = os.path.join(base, "recursos", "doblaje", "verificacion_asr.json")
        asr = transcribir_archivo(py, salida, spec.get("idioma_destino", "es"), a.modelo, asr_json)
        palabras = [w for sg in asr["segmentos"] for w in sg["palabras"]]
        bajas = []
        for u in spec["unidades"]:
            esperado = [normalizar(t) for t, _ in tokens_marcados(u.get("es_tts") or u["es"])]
            oido = [normalizar(w["p"]) for w in palabras if u["inicio"] + desfase - 0.2 <= w["i"] <= u["slot_fin"] + desfase + 0.3]
            ratio = difflib.SequenceMatcher(a=esperado, b=oido, autojunk=False).ratio()
            if ratio < a.umbral:
                bajas.append((u["id"], ratio, " ".join(oido)[:80]))
        print(f"Voz: {len(spec['unidades']) - len(bajas)}/{len(spec['unidades'])} unidades coinciden con el guion (ASR, umbral {a.umbral})")
        for uid, ratio, texto in bajas:
            print(f"  u{uid:02d} ratio {ratio:.2f}: «{texto}»")
            problemas.append(f"u{uid:02d} voz/guion {ratio:.2f}")
    else:
        aviso("sin faster-whisper: no se verificó la voz contra el guion")
    # rótulos: OCR en el punto medio de cada uno
    rot = spec.get("rotulos") or []
    if rot:
        cub = None
        ok = 0
        for r in rot:
            cub = r.get("cubrir") or cub
            fin = float(r["fin"]) if r.get("fin") is not None else d_cuerpo   # el último rótulo acaba con el cuerpo
            t = (float(r["inicio"]) + fin) / 2 + desfase
            leido = ocr_recorte(salida, t, cub, carpeta=os.path.join(base, "recursos", "doblaje"))
            if leido is None:
                aviso("sin tesseract: no se verificaron los rótulos")
                break
            esp = [normalizar(x) for x in re.sub(r"[/—–-]", " ", r["texto"]).split() if normalizar(x)]
            got = [normalizar(x) for x in re.sub(r"[/—–-]", " ", leido).split() if normalizar(x)]
            ratio = difflib.SequenceMatcher(a=esp, b=got, autojunk=False).ratio()
            if ratio >= 0.6:
                ok += 1
            else:
                problemas.append(f"rótulo «{r['texto']}» leído «{leido}» en t={t:.1f}")
        else:
            print(f"Rótulos: {ok}/{len(rot)} legibles por OCR en su punto medio")
    # captions: OCR de una muestra de cues
    cap = spec.get("captions") or {}
    if cap.get("activo", True) and shutil.which("tesseract"):
        unidades = sorted(tiempos["unidades"].values(), key=lambda r: r["inicio"])
        muestra = unidades[:: max(1, len(unidades) // a.muestras)][: a.muestras]
        ok = 0
        for r in muestra:
            ws = r["palabras"][: min(3, len(r["palabras"]))]
            if not ws:
                continue
            t = (ws[0]["i"] + ws[-1]["f"]) / 2 + desfase
            leido = ocr_recorte(salida, t, [0, cap["cubrir"]["y0"], 1080, cap["cubrir"]["y1"]], escala=1,
                                carpeta=os.path.join(base, "recursos", "doblaje"), psm=6) or ""   # psm 6: captions de 2 líneas
            esp = [normalizar(w["p"]) for w in ws]
            got = [normalizar(x) for x in leido.split()]
            hits = sum(1 for e in esp if e and any(e in g or g in e for g in got if g))
            if hits >= max(1, len(esp) - 1):
                ok += 1
            else:
                problemas.append(f"caption u{r['id']:02d} t={t:.1f}: esperado «{' '.join(w['p'] for w in ws)}», OCR «{leido[:60]}»")
        print(f"Captions: {ok}/{len(muestra)} cues de muestra legibles en su instante")
    # loudness
    try:
        lufs = comun.ebur128(salida)
        print(f"Loudness: {lufs}")
    except Exception as e:  # noqa: BLE001
        aviso(f"no se midió loudness: {e}")
    if problemas:
        comun.avance("verificacion", 100, f"{len(problemas)} problemas", estado="aviso")
        print(f"Problemas ({len(problemas)}):")
        for pr in problemas:
            print(f"  - {pr}")
        raise SystemExit(5)
    comun.avance("verificacion", 100, "duración, voz, rótulos, captions y loudness OK")
    print("Verificación OK")


# ----------------------------------------------------------------- CLI


def main():
    p = argparse.ArgumentParser(description="Doblaje de un video: voz nueva + captions en el estilo original")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transcribir", help="faster-whisper con tiempos por palabra")
    t.add_argument("entrada")
    t.add_argument("--proyecto")
    t.add_argument("--idioma", default="en")
    t.add_argument("--modelo", default="medium")
    t.add_argument("--whisper-python")
    t.set_defaults(fn=cmd_transcribir)
    u = sub.add_parser("unidades", help="transcripción → doblaje.json (unidades con slot)")
    u.add_argument("proyecto")
    u.add_argument("--entrada")
    u.add_argument("--idioma-destino", default="es")
    u.add_argument("--max-seg", type=float, default=6.0)
    u.add_argument("--forzar", action="store_true")
    u.set_defaults(fn=cmd_unidades)
    for nombre, fn in (("voz", cmd_voz), ("render", cmd_render), ("cortinillas", cmd_cortinillas), ("todo", cmd_todo)):
        s = sub.add_parser(nombre)
        s.add_argument("spec")
        s.add_argument("--regenerar", action="store_true", help="ignorar la caché de TTS")
        s.add_argument("--modelo", default="medium", help="tamaño de whisper para los tiempos por palabra")
        s.add_argument("--whisper-python")
        s.add_argument("--sin-captions", action="store_true")
        s.add_argument("--solo-comando", action="store_true", help="imprimir el ffmpeg sin renderizar")
        s.add_argument("--solo-tarjetas", action="store_true", help="cortinillas: solo las tarjetas PNG/mp4 sin voz ni unión")
        s.add_argument("--crf", type=int, default=18)
        s.add_argument("--preset", default="medium")
        s.set_defaults(fn=fn)
    vf = sub.add_parser("verificar", help="duración, voz vs guion (ASR), rótulos y captions (OCR), loudness")
    vf.add_argument("spec")
    vf.add_argument("--modelo", default="medium")
    vf.add_argument("--whisper-python")
    vf.add_argument("--umbral", type=float, default=0.6)
    vf.add_argument("--muestras", type=int, default=8)
    vf.set_defaults(fn=cmd_verificar)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
