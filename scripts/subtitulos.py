#!/usr/bin/env python3
"""subtitulos — subtítulos .srt/.vtt desde el audio de un video y, opcionalmente, quemados en él.

Regla de diseño: los TIEMPOS salen de las pausas medidas con `silencedetect` (o de las marcas por
palabra de faster-whisper/ElevenLabs), NUNCA de un LLM. Los modelos de chat con audio devuelven
marcas de tiempo que derivan ~4 s (ver docs/Lecciones-2026-09-23-IMG_7347.md §2); aquí el LLM solo
recibe fragmentos ya cortados en pausas y devuelve el TEXTO de cada uno.

Flujo:
1. WAV de análisis 16 kHz mono (misma línea de tiempo que silencios.py) y umbral auto.
2. Fragmentos de voz = huecos entre pausas ≥ 0.25 s. Los < 0.6 s se fusionan con el vecino más
   cercano (si el hueco ≤ 1 s); los > 7 s se parten en la pausa interna más larga (silencedetect más
   sensible dentro del fragmento) o, si no hay, en partes iguales ajustadas al mínimo de energía.
3. Transcripción: `auto` = faster-whisper si se puede importar (marcas por palabra), si no OpenRouter
   (`modelos.vision`, fragmentos numerados como input_audio, JSON validado, reintento de faltantes).
   ElevenLabs solo si hay ELEVENLABS_API_KEY y el usuario lo eligió (AGENT §5).
4. Cues de ≤ 2 líneas × --max-car (cortes equilibrados, nunca "250 | m"), tiempo repartido por
   sílabas dentro del fragmento; mínimo 0.8 s, máximo 6 s; aviso si > 20 caracteres/s.
5. `--quemar`: ASS acorde a la resolución (zona segura vertical: 420 px abajo, 150 arriba) → x264.

Uso:
  python3 scripts/subtitulos.py <video|audio> [--idioma es] [--formatos srt,vtt] [--quemar]
      [--estilo pastilla|clasico] [--posicion abajo|centro] [--max-car 32]
      [--glosario "ACME,HIKVISION,WhatsApp"] [--proveedor auto|whisper|openrouter|elevenlabs]
      [--modelo <id>] [--salida <dir>] [--proyecto <dir>] [--desde-srt <archivo.srt>]

La transcripción se guarda en caché (`transcripcion.json` en la carpeta de trabajo): repetir el
comando (p. ej. para cambiar estilo o quemar) no vuelve a pagar la API.

Códigos de salida: 0 ok · 1 fallo de FFmpeg (reportar) · 2 argumentos o entrada (corregir)
                   3 entorno: key/ffmpeg/proveedor (preguntar al usuario) · 4 API caída (reintentar 1 vez)
"""
import argparse
import base64
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import silencios as sil  # noqa: E402
from silencios import fallar, q  # noqa: E402

PAUSA_MIN = 0.25
TROZO_MIN, TROZO_MAX, HUECO_FUSION = 0.6, 7.0, 1.0
CUE_MIN, CUE_MAX, CPS_MAX = 0.8, 6.0, 20.0
LOTE = 20                  # fragmentos por petición a OpenRouter
PAD_AUDIO = 0.12           # audio extra por lado al mandar un fragmento (sin pisar al vecino)
ANTICIPO, RETENCION, SEPARACION = 0.05, 0.30, 0.04
ENDPOINT_OR = "https://openrouter.ai/api/v1/chat/completions"
ENDPOINT_EL = "https://api.elevenlabs.io/v1/speech-to-text"
# Las woff2 de promo/temas/neutro/fuentes NO sirven para libass aquí (verificado 2026-09-28 con
# FFmpeg 7.1 + libass 0.17.3: "Error opening memory font" — el FreeType de Homebrew no trae brotli
# para descomprimir WOFF2). Se usa una fuente del sistema; libass cae a Helvetica/Arial si falta.
FUENTE = "Helvetica Neue"
IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "it": "italiano",
           "de": "alemán"}
FUNCIONALES = {"de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "e", "o", "u",
               "en", "a", "al", "con", "por", "para", "que", "se", "su", "sus", "lo", "le", "les", "mi",
               "tu", "sin", "sobre", "entre", "como", "muy", "más", "ni", "si", "no"}
CONJUNCIONES = {"y", "e", "o", "u", "pero", "que", "porque", "pues", "aunque", "cuando", "donde",
                "mientras", "sino", "ni", "entonces"}
UNIDADES = {"%", "m", "cm", "mm", "km", "kg", "g", "mg", "l", "ml", "h", "hrs", "min", "s", "ms",
            "mp", "mpx", "megapíxeles", "megapixeles", "gb", "tb", "mb", "kb", "mbps", "gbps", "hz",
            "khz", "mhz", "ghz", "v", "vcd", "vca", "w", "kw", "kwh", "a", "ma", "mah", "°c", "°", "fps",
            "px", "p", "k", "pulgadas", "metros", "kilómetros", "kilos", "horas", "minutos", "segundos",
            "años", "días", "meses", "pesos", "dólares", "usd", "mxn", "canales", "cámaras", "puertos",
            "mil", "millones", "millón", "veces", "x"}
NUM_RE = re.compile(r"^[\$¿¡(«\"]?\d[\d.,:]*%?[)»\".,;:?!…]*$")


# ---------------------------------------------------------------- utilidades de texto
def _limpio(tok):
    return tok.lower().strip(".,;:?!¿¡…«»\"()")


def silabas(palabra):
    """Sílabas estimadas (heurística española): núcleos vocálicos; dos vocales fuertes = hiato, fuerte
    + débil = diptongo; í/ú acentuadas cuentan como fuertes. Cifras ≈ 2 sílabas por dígito, "%" = 3,
    siglas cortas en mayúsculas se deletrean (IP = i-pe)."""
    fuertes, debiles = set("aeoáéóíú"), set("iuü")
    letras = [c for c in palabra if c.isalpha()]
    n = 2 * sum(c.isdigit() for c in palabra) + (3 if "%" in palabra else 0)
    if letras and len(letras) <= 3 and "".join(letras).isupper():
        return n + len(letras)
    previa = None
    baja = palabra.lower()
    for k, c in enumerate(baja):
        # "y" entre consonantes suena "i" (SYSTEM = sis-tem); junto a vocal es parte del diptongo (muy)
        if c == "y" and (k == 0 or baja[k - 1] not in fuertes | debiles) and \
                (k + 1 == len(baja) or baja[k + 1] not in fuertes | debiles):
            c = "i"
        if c in fuertes or c in debiles:
            if previa is None or (previa in fuertes and c in fuertes):
                n += 1
            previa = c
        else:
            previa = None
    return max(1, n)


def tokenizar(texto):
    """Palabras atómicas: un número se pega a su unidad ("250 m", "20 por ciento") con espacio duro."""
    crudos = texto.split()
    out, i = [], 0
    while i < len(crudos):
        tok = crudos[i]
        if NUM_RE.match(tok) and not re.search(r"[.,;:?!…]$", tok):
            j = i + 1
            while j < len(crudos) and j - i <= 2:
                siguiente = _limpio(crudos[j])
                if siguiente == "por" and j + 1 < len(crudos) and _limpio(crudos[j + 1]) == "ciento":
                    tok += "\u00a0" + crudos[j] + "\u00a0" + crudos[j + 1]
                    j += 2
                    break
                if siguiente in UNIDADES:
                    tok += "\u00a0" + crudos[j]
                    j += 1
                    if re.search(r"[.,;:?!…]$", crudos[j - 1]):
                        break
                    continue
                break
            out.append(tok)
            i = j
        else:
            out.append(tok)
            i += 1
    return out


def clave_fonetica(texto):
    """Clave fonética española aproximada: "Akme", "Acme" y "ACME" → "akme"; "Jikvisión" y
    "Hik Vision" → "ikbision". Solo se compara contra los términos del glosario."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9ñ]", "", t)
    for a, b in (("ph", "f"), ("qu", "k"), ("ce", "se"), ("ci", "si"), ("c", "k"), ("z", "s"), ("x", "ks"),
                 ("y", "i"), ("v", "b"), ("w", "u"), ("h", ""), ("j", "")):
        t = t.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", t)


def corregir_glosario(texto, glosario):
    """Fuerza la escritura exacta de los nombres propios. Verificado 2026-09-28: aun con el glosario
    en el prompt, gemini-2.5-flash escribió "Akme" por ACME. Se reemplaza una palabra (o dos
    pegadas: "Hik Vision") cuando su clave fonética es IGUAL a la del término (no por parecido, para
    no convertir un "Cisco" legítimo)."""
    if not glosario:
        return texto
    claves = {clave_fonetica(t): t for t in glosario}
    palabras = texto.split()
    out, i = [], 0
    while i < len(palabras):
        hecho = False
        for n in (2, 1):
            grupo = palabras[i:i + n]
            if len(grupo) < n:
                continue
            # Dos palabras solo si ambas son "de peso": "y hikvision" daba i+ikbision → "ikbision"
            # (la y se colapsaba con la i y el término se tragaba la conjunción).
            if n == 2 and any(_limpio(w) in FUNCIONALES or len(clave_fonetica(w)) < 2 for w in grupo):
                continue
            m = re.fullmatch(r"([¿¡(«\"]*)(.*?)([.,;:?!…)»\"]*)", " ".join(grupo), re.S)
            termino = claves.get(clave_fonetica(m.group(2))) if m.group(2) else None
            if termino:
                out.append(m.group(1) + termino + m.group(3))
                i += n
                hecho = True
                break
        if not hecho:
            out.append(palabras[i])
            i += 1
    return " ".join(out)


def _largo(tokens):
    return len(" ".join(tokens))


def cortar_lineas(tokens, max_car):
    """[línea] o [l1, l2] equilibradas; None si no cabe en 2 líneas de `max_car`."""
    if _largo(tokens) <= max_car:
        return [" ".join(tokens)]
    mejor = None
    for k in range(1, len(tokens)):
        l1, l2 = _largo(tokens[:k]), _largo(tokens[k:])
        if l1 > max_car or l2 > max_car:
            continue
        costo = max(l1, l2) + 0.3 * abs(l1 - l2) - (1 if l2 >= l1 else 0)
        if _limpio(tokens[k - 1]) in FUNCIONALES:
            costo += 12
        if re.search(r"[.,;:?!…]$", tokens[k - 1]):
            costo -= 4
        if mejor is None or costo < mejor[0]:
            mejor = (costo, k)
    if mejor is None:
        return None
    k = mejor[1]
    return [" ".join(tokens[:k]), " ".join(tokens[k:])]


def dividir_en_cues(tokens, duracion, max_car, pesos=None):
    """Parte los tokens de un fragmento en grupos-cue (programación dinámica). Cada cue cabe en 2
    líneas; se prefiere cortar tras puntuación, nunca tras "de/la/el…", y se castiga que un cue dure
    más de CUE_MAX o menos de CUE_MIN (duración estimada por sílabas o por `pesos` dados)."""
    n = len(tokens)
    if n == 0:
        return []
    pesos = pesos or [silabas(t) + (2 if re.search(r"[.?!…]$", t) else 1 if re.search(r"[,;:]$", t) else 0)
                      for t in tokens]
    total = float(sum(pesos)) or 1.0
    acum = [0.0]
    for p in pesos:
        acum.append(acum[-1] + p)
    cabe = {}

    def costo(i, j):
        clave = (i, j)
        if clave not in cabe:
            cabe[clave] = cortar_lineas(tokens[i:j], max_car) is not None
        if not cabe[clave]:
            return 500.0 if j == i + 1 else math.inf
        c = 10.0
        if j < n:
            fin, sig = tokens[j - 1], _limpio(tokens[j])
            if re.search(r"[.?!…]$", fin):
                c += 0
            elif re.search(r"[,;:]$", fin):
                c += 3
            elif sig in CONJUNCIONES:
                c += 6
            else:
                c += 14
            if _limpio(fin) in FUNCIONALES:
                c += 25
            if _largo(tokens[i:j]) < 12:
                c += 8
        d = duracion * (acum[j] - acum[i]) / total
        if d > CUE_MAX:
            c += 200 * (d - CUE_MAX)
        if d < CUE_MIN and not (i == 0 and j == n):
            c += 40
        return c

    mejor = [0.0] + [math.inf] * n
    previo = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(max(0, j - 60), j):
            if mejor[i] == math.inf:
                continue
            c = mejor[i] + costo(i, j)
            if c < mejor[j]:
                mejor[j], previo[j] = c, i
    grupos, j = [], n
    while j > 0:
        grupos.append((previo[j], j))
        j = previo[j]
    return grupos[::-1]


# ---------------------------------------------------------------- segmentación por pausas
def complemento_voz(silencios, total):
    voz, t = [], 0.0
    for a, b in silencios:
        if a > t + 1e-3:
            voz.append([t, a])
        t = max(t, b)
    if total > t + 1e-3:
        voz.append([t, total])
    return voz


def fusionar_cortos(trozos, minimo=TROZO_MIN, hueco_max=HUECO_FUSION, maximo=TROZO_MAX):
    """Une cada fragmento < `minimo` con el vecino de hueco menor (si ese hueco ≤ `hueco_max`)."""
    trozos = [list(t) for t in trozos]
    cambio = True
    while cambio:
        cambio = False
        for i, (a, b) in enumerate(trozos):
            if b - a >= minimo:
                continue
            opciones = []
            if i > 0:
                opciones.append((a - trozos[i - 1][1], i - 1))
            if i + 1 < len(trozos):
                opciones.append((trozos[i + 1][0] - b, i + 1))
            opciones = [(h, j) for h, j in opciones if h <= hueco_max and
                        max(b, trozos[j][1]) - min(a, trozos[j][0]) <= maximo]
            if not opciones:
                continue
            _, j = min(opciones)
            trozos[j] = [min(a, trozos[j][0]), max(b, trozos[j][1])]
            del trozos[i]
            cambio = True
            break
    return trozos


def partir_largos(trozos, buscar_pausas, minimo_energia, maximo=TROZO_MAX, profundidad=0):
    """Parte los fragmentos > `maximo`: en la pausa interna más larga (a ≥ 1 s de los bordes) o, si no
    hay, en partes iguales movidas al mínimo de energía cercano. Recursivo."""
    out = []
    for a, b in trozos:
        if b - a <= maximo or profundidad > 6:
            out.append([a, b])
            continue
        pausas = [(s, e) for s, e in buscar_pausas(a, b) if a + 1.0 <= (s + e) / 2 <= b - 1.0]
        if pausas:
            medio = (a + b) / 2
            s, e = max(pausas, key=lambda p: (round(p[1] - p[0], 2), -abs((p[0] + p[1]) / 2 - medio)))
            piezas = [[a, s], [e, b]]
        else:
            n = int(math.ceil((b - a) / (maximo - 1.0)))
            cortes = [minimo_energia(a + (b - a) * k / n) for k in range(1, n)]
            bordes = [a] + sorted(cortes) + [b]
            piezas = [[bordes[k], bordes[k + 1]] for k in range(n) if bordes[k + 1] > bordes[k]]
        out.extend(partir_largos(piezas, buscar_pausas, minimo_energia, maximo, profundidad + 1))
    return out


def segmentar(wav, total, umbral, niveles):
    """Fragmentos [ini, fin] de voz, con los tiempos de las pausas medidas."""
    silencios = sil.detectar_silencios(wav, umbral, PAUSA_MIN, total=total)
    trozos = fusionar_cortos(complemento_voz(silencios, total))
    sensible = min(-20.0, umbral + 8.0)

    def buscar_pausas(a, b):
        return sil.detectar_silencios(wav, sensible, 0.12, desde=a, dur=b - a)

    def minimo_energia(t):
        ventana = [(abs(ti + sil.VENTANA_S / 2 - t), rms, ti) for ti, _, rms in niveles if abs(ti - t) <= 0.5]
        if not ventana:
            return t
        _, _, ti = min(ventana, key=lambda v: (v[1], v[0]))
        return ti + sil.VENTANA_S / 2

    return partir_largos(trozos, buscar_pausas, minimo_energia)


# ---------------------------------------------------------------- transcripción
class ErrorAPI(Exception):
    pass


def _post_json(url, cuerpo, headers, timeout=300):
    """POST con UN reintento interno para fallos transitorios (red, 429, 5xx)."""
    ultimo = ""
    for intento in (1, 2):
        req = urllib.request.Request(url, data=cuerpo, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            texto = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403):
                fallar(f"la API rechazó la key (HTTP {e.code}).", 3,
                       "pide al usuario revisar la key en .env (no la imprimas)")
            if e.code == 402:
                fallar("la cuenta no tiene crédito (HTTP 402).", 3, "pide al usuario recargar crédito")
            if e.code in (400, 404, 422):
                fallar(f"el modelo rechazó la petición (HTTP {e.code}): {texto}", 2,
                       "quita --modelo (usa el default) o elige un modelo que acepte audio")
            ultimo = f"HTTP {e.code}: {texto}"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            ultimo = str(e)[:200]
        if intento == 1:
            time.sleep(3)
    raise ErrorAPI(ultimo)


def enviar_openrouter(cuerpo, key):
    return _post_json(ENDPOINT_OR, json.dumps(cuerpo).encode(),
                      {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})


def instrucciones(idioma, glosario):
    lengua = IDIOMAS.get(idioma, idioma)
    nombres = (", ".join(glosario)) if glosario else "(ninguno)"
    return (f"Eres un transcriptor profesional. Recibirás fragmentos de audio numerados, en orden, de un "
            f"mismo video. Transcribe CADA fragmento de forma literal en {lengua}.\n"
            "Reglas:\n"
            "1. Escribe exactamente lo que se dice: sin resumir, sin traducir, sin agregar ni quitar palabras.\n"
            f"2. Respeta EXACTAMENTE la escritura de estos nombres propios: {nombres}.\n"
            "3. Puntuación y mayúsculas normales (¿? ¡!). Cifras con dígitos (250, 3.5, 20 %).\n"
            "4. Si un fragmento no tiene voz entendible, su texto es \"\".\n"
            "5. Sin marcas de tiempo, sin nombres de hablante, sin descripciones de sonidos.\n"
            "Responde SOLO JSON: {\"segmentos\":[{\"i\":<número del fragmento>,\"texto\":\"…\"}]} con un "
            "objeto por cada fragmento recibido.")


def _parsear_segmentos(contenido):
    m = re.search(r"\{.*\}", contenido or "", re.S)
    if not m:
        return {}
    try:
        datos = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for s in datos.get("segmentos") or []:
        try:
            out[int(s.get("i"))] = str(s.get("texto") or "").strip()
        except (TypeError, ValueError):
            continue
    return out


def _mp3_fragmento(wav, a, b, ruta):
    comun.run(["ffmpeg", "-nostdin", "-hide_banner", "-y", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
               "-i", wav, "-ac", "1", "-ar", "16000", "-b:a", "32k", ruta])
    with open(ruta, "rb") as f:
        return base64.b64encode(f.read()).decode()


def transcribir_openrouter(trozos, wav, trabajo, idioma, glosario, modelo, key, log_dir,
                           enviar=None, cache=None):
    """Texto de cada fragmento. Lotes de ≤ LOTE fragmentos; los índices que no vuelvan se piden una vez
    más. Devuelve (textos {índice 1-based: texto}, costo_usd, llamadas, faltantes). `cache` = dict
    "ini-fin" → texto; se consulta antes de pagar y se actualiza con cada respuesta."""
    enviar = enviar or enviar_openrouter  # se resuelve al llamar: las pruebas lo sustituyen
    cache = cache if cache is not None else {}
    claves = [f"{a:.3f}-{b:.3f}" for a, b in trozos]
    textos = {i + 1: cache[c] for i, c in enumerate(claves) if c in cache}
    pendientes = [i + 1 for i in range(len(trozos)) if (i + 1) not in textos]
    costo, llamadas = 0.0, 0
    sistema = instrucciones(idioma, glosario)
    os.makedirs(trabajo, exist_ok=True)
    for _ronda in (1, 2):
        faltan = []
        for k in range(0, len(pendientes), LOTE):
            lote = pendientes[k:k + LOTE]
            partes = [{"type": "text", "text": f"{len(lote)} fragmentos. Transcribe cada uno."}]
            creados = []
            for i in lote:
                a, b = trozos[i - 1]
                ini = max(0.0, a - min(PAD_AUDIO, (a - trozos[i - 2][1]) / 2 if i > 1 else PAD_AUDIO))
                fin = b + min(PAD_AUDIO, (trozos[i][0] - b) / 2 if i < len(trozos) else PAD_AUDIO)
                mp3 = os.path.join(trabajo, f"frag_{i:04d}.mp3")
                creados.append(mp3)
                partes.append({"type": "text", "text": f"Fragmento {i}:"})
                partes.append({"type": "input_audio",
                               "input_audio": {"data": _mp3_fragmento(wav, ini, fin, mp3), "format": "mp3"}})
            cuerpo = {"model": modelo, "temperature": 0, "response_format": {"type": "json_object"},
                      "usage": {"include": True},
                      "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": partes}]}
            try:
                resp = enviar(cuerpo, key)
            finally:
                for mp3 in creados:
                    if os.path.exists(mp3):
                        os.remove(mp3)
            llamadas += 1
            uso = resp.get("usage") or {}
            costo += float(uso.get("cost") or 0)
            comun.log_costo(log_dir, {"id": resp.get("id"), "modelo": modelo, "tarea": "subtitulos",
                                      "usage": uso or None})
            contenido = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            recibidos = _parsear_segmentos(contenido)
            for i in lote:
                if i in recibidos:
                    textos[i] = recibidos[i]
                    cache[claves[i - 1]] = recibidos[i]
                else:
                    faltan.append(i)
        pendientes = faltan
        if not pendientes:
            break
    return textos, costo, llamadas, pendientes


def transcribir_whisper(wav, idioma, glosario, modelo):
    """[(ini, fin, palabra)] con faster-whisper (marcas por palabra). Solo si se puede importar.

    El WAV ya viene a 16 kHz mono (`sil.extraer_analisis`), así que se lee con `wave` y se pasa un
    arreglo numpy: pasarle la RUTA a `m.transcribe()` revienta con
    `TypeError: open() got an unexpected keyword argument 'metadata_errors'` cuando PyAV y
    faster-whisper no empatan versiones (por eso el arreglo, que evita `decode_audio` por completo).
    """
    import wave  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415 — ya viene con faster-whisper
    from faster_whisper import WhisperModel  # noqa: PLC0415 — dependencia opcional
    with wave.open(str(wav), "rb") as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    m = WhisperModel(modelo or "small", device="cpu", compute_type="int8")
    segmentos, _ = m.transcribe(audio, language=idioma, word_timestamps=True, beam_size=5,
                                initial_prompt=(", ".join(glosario) or None), vad_filter=False)
    return [(float(w.start), float(w.end), w.word.strip()) for s in segmentos for w in (s.words or [])
            if w.word.strip()]


def transcribir_elevenlabs(wav, idioma, key, trabajo, log_dir, modelo=None):
    """[(ini, fin, palabra)] con speech-to-text de ElevenLabs (marcas por palabra)."""
    mp3 = os.path.join(trabajo, "elevenlabs.mp3")
    comun.run(["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", wav, "-ac", "1", "-b:a", "64k", mp3])
    limite = "----subt" + uuid.uuid4().hex
    campos = {"model_id": modelo or "scribe_v1", "language_code": idioma, "timestamps_granularity": "word",
              "tag_audio_events": "false"}
    cuerpo = b""
    for k, v in campos.items():
        cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    with open(mp3, "rb") as f:
        cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.mp3\"\r\n"
                   "Content-Type: audio/mpeg\r\n\r\n").encode() + f.read() + f"\r\n--{limite}--\r\n".encode()
    os.remove(mp3)
    resp = _post_json(ENDPOINT_EL, cuerpo, {"xi-api-key": key,
                                            "Content-Type": f"multipart/form-data; boundary={limite}"})
    comun.log_costo(log_dir, {"id": resp.get("transcription_id"), "modelo": campos["model_id"],
                              "tarea": "subtitulos"})
    return palabras_elevenlabs(resp)


def palabras_elevenlabs(resp):
    return [(float(w["start"]), float(w["end"]), str(w["text"]).strip()) for w in resp.get("words") or []
            if w.get("type", "word") == "word" and str(w.get("text", "")).strip()]


def asignar_palabras(trozos, palabras, tolerancia=0.15):
    """Reparte palabras con marca de tiempo entre los fragmentos (por su punto medio). Las que caen
    lejos de todo fragmento (voz bajo el umbral) forman fragmentos nuevos con sus propios tiempos."""
    grupos = [[] for _ in trozos]
    sueltas = []
    for p in palabras:
        medio = (p[0] + p[1]) / 2
        idx = next((i for i, (a, b) in enumerate(trozos) if a - tolerancia <= medio <= b + tolerancia), None)
        if idx is None:
            sueltas.append(p)
        else:
            grupos[idx].append(p)
    resultado = [(list(t), g) for t, g in zip(trozos, grupos) if g]
    actual = []
    for p in sueltas:
        if actual and p[0] - actual[-1][1] > 0.6:
            resultado.append(([actual[0][0], actual[-1][1]], actual))
            actual = []
        actual.append(p)
    if actual:
        resultado.append(([actual[0][0], actual[-1][1]], actual))
    return sorted(resultado, key=lambda r: r[0][0])


# ---------------------------------------------------------------- cues
def cues_de_fragmento(a, b, texto, max_car, palabras=None):
    """Cues [{ini, fin, lineas}] de un fragmento. Con `palabras` (whisper/ElevenLabs) los bordes internos
    salen de las marcas por palabra; sin ellas, del reparto por sílabas."""
    if palabras:
        tokens, tiempos = [], []
        for ini, fin, w in palabras:
            if tokens and NUM_RE.match(tokens[-1].split("\u00a0")[0]) and _limpio(w) in UNIDADES:
                tokens[-1] += "\u00a0" + w
                tiempos[-1] = (tiempos[-1][0], fin)
            else:
                tokens.append(w)
                tiempos.append((ini, fin))
        pesos = [max(0.05, f - i) for i, f in tiempos]
    else:
        tokens, tiempos, pesos = tokenizar(texto), None, None
    if not tokens:
        return []
    grupos = dividir_en_cues(tokens, b - a, max_car, pesos)
    total = float(sum(pesos)) if pesos else float(sum(silabas(t) for t in tokens))
    cues, acumulado = [], 0.0
    for gi, (i, j) in enumerate(grupos):
        lineas = cortar_lineas(tokens[i:j], max_car) or [" ".join(tokens[i:j])]
        if tiempos:
            ini = a if gi == 0 else (tiempos[i - 1][1] + tiempos[i][0]) / 2
            fin = b if gi == len(grupos) - 1 else (tiempos[j - 1][1] + tiempos[j][0]) / 2
        else:
            peso = sum(silabas(t) for t in tokens[i:j])
            ini = a + (b - a) * acumulado / total
            acumulado += peso
            fin = a + (b - a) * acumulado / total
        cues.append({"ini": ini, "fin": fin, "lineas": lineas, "ultimo": gi == len(grupos) - 1})
    return cues


def ajustar_tiempos(cues, total=None):
    """Anticipo/retención, mínimo CUE_MIN, máximo CUE_MAX, sin traslapes (≥ SEPARACION entre cues)."""
    cues = sorted(cues, key=lambda c: c["ini"])
    for k, c in enumerate(cues):
        previo_fin = cues[k - 1]["fin"] + SEPARACION if k > 0 else 0.0
        sig_ini = cues[k + 1]["ini"] - SEPARACION if k + 1 < len(cues) else (total or c["fin"] + 1.0)
        c["ini"] = max(previo_fin, c["ini"] - ANTICIPO)
        if c.get("ultimo", True):
            c["fin"] = min(sig_ini, c["fin"] + RETENCION)
        if c["fin"] - c["ini"] < CUE_MIN:
            c["fin"] = min(sig_ini, c["ini"] + CUE_MIN)
        if c["fin"] - c["ini"] < CUE_MIN:
            c["ini"] = max(previo_fin, c["fin"] - CUE_MIN)
        c["fin"] = min(c["fin"], c["ini"] + CUE_MAX, sig_ini if k + 1 < len(cues) else c["fin"])
        if total:
            c["fin"] = min(c["fin"], total)
    return [c for c in cues if c["fin"] > c["ini"]]


def cps(cue):
    return len(" ".join(cue["lineas"]).replace("\u00a0", " ")) / max(1e-3, cue["fin"] - cue["ini"])


# ---------------------------------------------------------------- formatos
def _ts(t, sep=","):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _plano(linea):
    return linea.replace("\u00a0", " ")


def a_srt(cues):
    bloques = [f"{i}\n{_ts(c['ini'])} --> {_ts(c['fin'])}\n" + "\n".join(_plano(l) for l in c["lineas"])
               for i, c in enumerate(cues, 1)]
    return "\n\n".join(bloques) + "\n"


def a_vtt(cues):
    bloques = [f"{i}\n{_ts(c['ini'], '.')} --> {_ts(c['fin'], '.')}\n" + "\n".join(_plano(l) for l in c["lineas"])
               for i, c in enumerate(cues, 1)]
    return "WEBVTT\n\n" + "\n\n".join(bloques) + "\n"


def leer_srt(texto):
    """Cues de un SRT (tolera BOM, CRLF, coma o punto en los ms, etiquetas <i>/{\\…})."""
    texto = texto.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    patron = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
    cues = []
    for bloque in re.split(r"\n\s*\n", texto.strip()):
        lineas = [l for l in bloque.split("\n")]
        for k, l in enumerate(lineas):
            m = patron.search(l)
            if m:
                g = [int(x) for x in m.groups()]
                ini = g[0] * 3600 + g[1] * 60 + g[2] + int(m.group(4).ljust(3, "0")) / 1000
                fin = g[4] * 3600 + g[5] * 60 + g[6] + int(m.group(8).ljust(3, "0")) / 1000
                cuerpo = [re.sub(r"<[^>]+>|\{[^}]*\}", "", x).strip() for x in lineas[k + 1:]]
                cuerpo = [x for x in cuerpo if x]
                if cuerpo and fin > ini:
                    cues.append({"ini": ini, "fin": fin, "lineas": cuerpo})
                break
    return cues


# ---------------------------------------------------------------- ASS y quemado
def version_libass():
    """Versión de libass del FFmpeg instalado (int 0xMMmmpp00) o None si no tiene libass."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-f", "lavfi", "-i", "color=s=16x16:d=0.04",
                        "-vf", "subtitles=filename=/dev/null", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"libass API version: 0x([0-9a-fA-F]+)", r.stderr)
    if m:
        return int(m.group(1), 16)
    return None if "No such filter" in r.stderr else 0


def diseno(w, h, estilo="pastilla", posicion="abajo"):
    """Parámetros del estilo según la resolución. Vertical 1080x1920: fuente 56 px y texto por encima de
    y≈1500 (zona segura de TikTok/Reels: 420 px abajo, 150 arriba). Horizontal 1920x1080: 46 px,
    margen 70. Se escala con el tamaño real del cuadro."""
    if h >= 1.3 * w:
        fs = 56 * w / 1080
        relleno = round(fs * 0.3)
        mv = round(420 * h / 1920) + relleno + 4
        ml = round(70 * w / 1080)
    elif w >= 1.3 * h:
        fs = 46 * h / 1080
        relleno = round(fs * 0.3)
        mv = round(70 * h / 1080)
        ml = round(120 * w / 1920)
    else:
        fs = 50 * min(w, h) / 1080
        relleno = round(fs * 0.3)
        mv = round(0.1 * h) + relleno
        ml = round(70 * w / 1080)
    return {"fs": round(fs), "relleno": relleno, "margen_v": 0 if posicion == "centro" else mv,
            "margen_lr": ml, "alineacion": 5 if posicion == "centro" else 2, "estilo": estilo}


def a_ass(cues, w, h, estilo="pastilla", posicion="abajo", fuente=FUENTE, libass=0x01703000):
    """ASS con PlayRes = resolución del video. `pastilla`: caja oscura semiopaca, texto blanco.
    Con libass ≥ 0.17 se usa BorderStyle=4 (UNA caja por evento, color = BackColour; verificado con
    0.17.3): con BorderStyle=3 cada línea lleva su caja y el traslape entre las dos líneas se ve como
    una franja más oscura. libass no redondea esquinas; `\\blur` en BorderStyle=3 desenfoca también
    el texto, así que no se usa. `clasico`: blanco con contorno negro y sombra."""
    d = diseno(w, h, estilo, posicion)
    fs, pad = d["fs"], d["relleno"]
    extra = ""
    if estilo == "clasico":
        borde, contorno, fondo, grosor, sombra = 1, "&H00000000", "&H80000000", round(fs * 0.065, 1), round(fs * 0.03, 1)
    elif libass and libass >= 0x01700000:
        borde, contorno, fondo, grosor, sombra = 4, "&HFF000000", "&H30000000", pad, 0
    else:  # libass viejo: una caja por línea; relleno vertical chico para que casi no se traslapen
        borde, contorno, fondo, grosor, sombra = 3, "&H30000000", "&H30000000", pad, 0
        extra = f"{{\\xbord{pad}\\ybord{max(2, pad // 4)}}}"
    cab = ("[Script Info]\n; generado por scripts/subtitulos.py\nScriptType: v4.00+\n"
           f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\nYCbCr Matrix: TV.709\n\n"
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
           "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
           f"Style: Sub,{fuente},{fs},&H00FFFFFF,&H000000FF,{contorno},{fondo},-1,0,0,0,100,100,0,0,"
           f"{borde},{grosor},{sombra},{d['alineacion']},{d['margen_lr']},{d['margen_lr']},{d['margen_v']},1\n\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

    def t(x):
        cs = int(round(max(0.0, x) * 100))
        hh, cs = divmod(cs, 360000)
        mm, cs = divmod(cs, 6000)
        ss, cs = divmod(cs, 100)
        return f"{hh}:{mm:02d}:{ss:02d}.{cs:02d}"

    def esc(linea):
        return linea.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\u00a0", "\\h")

    eventos = [f"Dialogue: 0,{t(c['ini'])},{t(max(c['fin'], c['ini'] + 0.01))},Sub,,0,0,0,,"
               + extra + "\\N".join(esc(l) for l in c["lineas"]) for c in cues]
    return cab + "\n".join(eventos) + "\n"


def escapar_ruta_filtro(ruta):
    """Ruta para `ass=filename=…`: dos niveles de escape de FFmpeg (valor de opción: \\ ' : ; luego el
    filtergraph: \\ ' [ ] , ;). Probado con espacios, dos puntos, comas, apóstrofos y corchetes."""
    n1 = re.sub(r"([\\':])", r"\\\1", ruta)
    return re.sub(r"([\\'\[\],;])", r"\\\1", n1)


def quemar(info, ass_ruta, salida):
    audio = info.get("audio")
    copiar = audio and audio.get("codec") in ("aac", "mp3", "alac")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", info["ruta"],
           "-vf", f"ass=filename={escapar_ruta_filtro(ass_ruta)}", "-map", "0:v:0", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "copy"] if copiar else ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"])
    cmd += ["-movflags", "+faststart", salida]
    comun.ffmpeg_con_progreso(cmd, info["duracion"], "quemado", imprimir=info["duracion"] >= 60)


# ---------------------------------------------------------------- CLI
def _sha1(ruta):
    h = hashlib.sha1()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _elegir_proveedor(pedido):
    if pedido in ("auto", "whisper"):
        try:
            import faster_whisper  # noqa: F401,PLC0415
            return "whisper"
        except ImportError:
            if pedido == "whisper":
                fallar("faster-whisper no está instalado.", 3,
                       "usa --proveedor openrouter, o pide al usuario instalarlo en un venv (ver docs/Subtitulos-y-Silencios.md)")
    return "openrouter" if pedido in ("auto", "openrouter") else pedido


def main(argv=None):
    ap = argparse.ArgumentParser(description="Subtítulos .srt/.vtt (y quemados) con tiempos de las pausas medidas.")
    ap.add_argument("entrada", help="video o audio")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--formatos", default="srt,vtt", help="srt, vtt o srt,vtt")
    ap.add_argument("--quemar", action="store_true", help="además quema los subtítulos en el video")
    ap.add_argument("--estilo", choices=("pastilla", "clasico"), default="pastilla")
    ap.add_argument("--posicion", choices=("abajo", "centro"), default="abajo")
    ap.add_argument("--max-car", type=int, default=32, help="caracteres por línea (2 líneas por cue)")
    ap.add_argument("--glosario", default="", help='nombres propios exactos, p. ej. "ACME,HIKVISION,WhatsApp"')
    ap.add_argument("--proveedor", choices=("auto", "whisper", "openrouter", "elevenlabs"), default="auto")
    ap.add_argument("--modelo", help="id del modelo (OpenRouter), tamaño de whisper o modelo de ElevenLabs")
    ap.add_argument("--salida", help="carpeta de salida (default: la del proyecto o la de la entrada)")
    ap.add_argument("--proyecto", help="carpeta del proyecto (AGENT §13)")
    ap.add_argument("--desde-srt", help="usa este SRT (sin transcribir): solo convierte y/o quema")
    ap.add_argument("--fuente", default=FUENTE, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    formatos = [f.strip().lower().lstrip(".") for f in a.formatos.split(",") if f.strip()]
    if not formatos or any(f not in ("srt", "vtt") for f in formatos):
        fallar(f"--formatos `{a.formatos}` no es válido.", 2, "usa --formatos srt,vtt (o solo srt / vtt)")
    if not 16 <= a.max_car <= 60:
        fallar(f"--max-car {a.max_car} fuera de rango [16, 60].", 2, "usa 32 para vertical o 42 para horizontal")
    if not re.fullmatch(r"[a-z]{2,3}", a.idioma):
        fallar(f"--idioma `{a.idioma}` no es un código ISO.", 2, "usa p. ej. --idioma es")
    glosario = [g.strip() for g in a.glosario.split(",") if g.strip()]
    sil.verificar_entorno()
    repo = comun.raiz_repo(os.path.dirname(os.path.abspath(__file__)))
    proyecto = sil.resolver_proyecto(repo, a.proyecto)
    entrada = os.path.abspath(a.entrada)
    info = sil.sondear(entrada)
    nombre = os.path.splitext(os.path.basename(entrada))[0]
    destino = os.path.abspath(a.salida or proyecto or os.path.dirname(entrada))
    os.makedirs(destino, exist_ok=True)
    trabajo = (os.path.join(proyecto, "recursos", "subtitulos", nombre) if proyecto
               else os.path.join(destino, f"{nombre}_subt"))
    log_dir = os.path.join(proyecto, "recursos") if proyecto else destino
    if a.quemar and not info["video"]:
        fallar("--quemar necesita un video y la entrada no tiene imagen.", 2, "quita --quemar o pasa el video")
    libass = None
    if a.quemar:
        libass = version_libass()
        if libass is None:
            fallar("tu FFmpeg no tiene libass (filtro ass).", 3, "pide al usuario reinstalar FFmpeg: brew reinstall ffmpeg")

    avisos, costo, proveedor, modelo, llamadas = [], 0.0, "srt", None, 0
    if a.desde_srt:
        if not os.path.isfile(a.desde_srt):
            fallar(f"no existe `{a.desde_srt}`.", 2, "revisa la ruta del .srt")
        with open(a.desde_srt, encoding="utf-8-sig", errors="replace") as f:
            cues = leer_srt(f.read())
        if not cues:
            fallar(f"`{a.desde_srt}` no tiene cues válidos.", 2, "revisa el formato (HH:MM:SS,mmm --> HH:MM:SS,mmm)")
        fuera = [c for c in cues if c["ini"] >= info["duracion"]]
        if fuera:
            avisos.append(f"{len(fuera)} cues empiezan después del final ({info['duracion']:.1f} s): "
                          "¿el SRT es de otro video o de antes de quitar silencios?")
    else:
        if not info["audio"]:
            fallar("la entrada no tiene audio: no hay voz que transcribir.", 2, "pasa el video con audio o usa --desde-srt")
        os.makedirs(trabajo, exist_ok=True)
        wav = sil.extraer_analisis(entrada, os.path.join(trabajo, "audio_16k.wav"))
        niveles = sil.perfil_niveles(wav)
        umbral, _, _ = sil.umbral_auto(niveles)
        total = min(x for x in (info["audio"]["dur"], info["duracion"]) if x)
        trozos = segmentar(wav, total, umbral, niveles)
        if not trozos:
            fallar(f"no se detectó voz (umbral {umbral} dB).", 2, "revisa que el audio tenga voz audible")
        proveedor = _elegir_proveedor(a.proveedor)
        ruta_cache = os.path.join(trabajo, "transcripcion.json")
        firma = {"audio_sha1": _sha1(wav), "idioma": a.idioma, "glosario": glosario}
        try:
            with open(ruta_cache, encoding="utf-8") as f:
                previa = json.load(f)
        except (OSError, json.JSONDecodeError):
            previa = {}
        fragmentos = []  # [(ini, fin, texto, palabras|None)]
        if proveedor == "openrouter":
            modelo = a.modelo or (comun.cargar_config(repo).get("modelos") or {}).get("vision", "google/gemini-2.5-flash")
            firma.update(proveedor=proveedor, modelo=modelo)
            cache = previa.get("fragmentos", {}) if {k: previa.get(k) for k in firma} == firma else {}
            try:
                key = comun.api_key(repo)
            except SystemExit:
                fallar("no hay OPENROUTER_API_KEY para transcribir.", 3,
                       "pide al usuario agregarla al .env, o instalar faster-whisper (transcripción local)")
            try:
                textos, costo, llamadas, faltan = transcribir_openrouter(
                    trozos, wav, trabajo, a.idioma, glosario, modelo, key, log_dir, cache=cache)
            except ErrorAPI as e:
                fallar(f"OpenRouter no respondió tras 2 intentos ({e}).", 4,
                       "espera un minuto y repite el MISMO comando (lo ya transcrito queda en caché)")
            finally:
                with open(ruta_cache, "w", encoding="utf-8") as f:
                    json.dump({**firma, "fragmentos": cache}, f, ensure_ascii=False, indent=1)
            if faltan:
                avisos.append(f"{len(faltan)} fragmentos sin texto tras reintento: {faltan[:6]}")
            for i, (x, y) in enumerate(trozos, 1):
                texto = corregir_glosario(textos.get(i, ""), glosario)
                if texto and len(texto) / max(0.3, y - x) > 30:
                    avisos.append(f"fragmento {i} con texto excesivo para su duración (¿inventado?)")
                fragmentos.append((x, y, texto, None))
        else:
            modelo = a.modelo or ("small" if proveedor == "whisper" else "scribe_v1")
            firma.update(proveedor=proveedor, modelo=modelo)
            if {k: previa.get(k) for k in firma} == firma and previa.get("palabras"):
                palabras = [tuple(p) for p in previa["palabras"]]
            elif proveedor == "whisper":
                palabras = transcribir_whisper(wav, a.idioma, glosario, modelo)
            else:
                try:
                    key = comun.api_key(repo, "ELEVENLABS_API_KEY")
                except SystemExit:
                    fallar("--proveedor elevenlabs requiere ELEVENLABS_API_KEY y no está configurada "
                           "(AGENT §5: no pedirla).", 3, "usa --proveedor openrouter (o auto)")
                try:
                    palabras = transcribir_elevenlabs(wav, a.idioma, key, trabajo, log_dir, a.modelo)
                except ErrorAPI as e:
                    fallar(f"ElevenLabs no respondió tras 2 intentos ({e}).", 4, "espera un minuto y repite el comando")
                llamadas = 1
            with open(ruta_cache, "w", encoding="utf-8") as f:
                json.dump({**firma, "palabras": palabras}, f, ensure_ascii=False)
            palabras = [(i0, f0, corregir_glosario(w, glosario)) for i0, f0, w in palabras]
            for (x, y), ps in asignar_palabras(trozos, palabras):
                fragmentos.append((x, y, " ".join(p[2] for p in ps), ps))
        cues = []
        for x, y, texto, ps in fragmentos:
            if texto.strip():
                cues.extend(cues_de_fragmento(x, y, texto, a.max_car, ps))
        cues = ajustar_tiempos(cues, total)
        if not cues:
            fallar("la transcripción volvió vacía (sin voz entendible).", 2,
                   "revisa el audio; si es música o ruido no hay nada que subtitular")

    rapidos = [cps(c) for c in cues if cps(c) > CPS_MAX]
    if rapidos:
        avisos.append(f"{len(rapidos)} subtítulos > {CPS_MAX:.0f} car/s (máx {max(rapidos):.1f}): lectura rápida")
    archivos = []
    for fmt in formatos:
        ruta = os.path.join(destino, f"{nombre}.{fmt}")
        if a.desde_srt and os.path.abspath(a.desde_srt) == ruta:
            archivos.append(ruta)
            continue
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(a_srt(cues) if fmt == "srt" else a_vtt(cues))
        archivos.append(ruta)

    linea_video = None
    if a.quemar:
        os.makedirs(trabajo, exist_ok=True)
        v = info["video"]
        ass_ruta = os.path.join(trabajo, f"{nombre}.ass")
        with open(ass_ruta, "w", encoding="utf-8") as f:
            f.write(a_ass(cues, v["w"], v["h"], a.estilo, a.posicion, a.fuente, libass))
        salida = os.path.join(destino, f"{nombre}_subtitulado.mp4")
        quemar(info, ass_ruta, salida)
        dur_out = sil.duraciones(salida)["formato"]
        if abs(dur_out - info["duracion"]) > 0.1:
            fallar(f"el video quemado dura {dur_out:.2f} s y la entrada {info['duracion']:.2f} s.", 1,
                   "reporta al usuario (revisa el log de FFmpeg)")
        d = diseno(v["w"], v["h"], a.estilo, a.posicion)
        linea_video = (f"Video: {salida} ({v['w']}x{v['h']}, {a.estilo} {a.posicion}, "
                       f"{a.fuente} {d['fs']} px, {dur_out:.2f} s)")

    cubierto = sum(c["fin"] - c["ini"] for c in cues)
    etiqueta = {"srt": f"desde {os.path.basename(a.desde_srt or '')}"}.get(proveedor, f"{proveedor} ({modelo})")
    costo_txt = (f"${costo:.4f}" if proveedor == "openrouter" else "$0 (local)" if proveedor in ("whisper", "srt")
                 else "n/d (ver plan ElevenLabs)")
    if proveedor == "openrouter" and llamadas == 0:
        costo_txt = "$0 (caché)"
    print(f"OK subtítulos: {len(cues)} cues · {cubierto:.1f} s cubiertos de {info['duracion']:.1f} s · "
          f"{etiqueta} · costo {costo_txt}")
    print("Archivos: " + " · ".join(archivos))
    if linea_video:
        print(linea_video)
    for aviso in avisos[:3]:
        print(f"AVISO: {aviso}")
    srt_ruta = next((r for r in archivos if r.endswith(".srt")), archivos[0])
    extra = f" --proyecto {q(proyecto)}" if proyecto else ""
    if a.quemar:
        print(f"Siguiente: revisa 3 cuadros del video; para corregir texto edita {q(srt_ruta)} y corre "
              f"python3 scripts/subtitulos.py {q(entrada)}{extra} --desde-srt {q(srt_ruta)} --quemar")
    else:
        print(f"Siguiente: revisa {q(srt_ruta)}; para quemarlos: python3 scripts/subtitulos.py {q(entrada)}{extra} --quemar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
