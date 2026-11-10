#!/usr/bin/env python3
"""silencios — corta los tiempos muertos de un video o audio SIN desincronizar imagen y sonido.

Por qué existe (verificado 2026-09-28): la receta anterior de SKILL (`silenceremove` + `-c:v copy`)
recorta solo el audio; la imagen sigue completa, así que tras el primer corte la voz se adelanta
a los labios y el desfase crece con cada silencio. Aquí:

1. Se hace una copia de análisis (mono 16 kHz, pasa-altos 60 Hz contra offset DC/rumble) y se
   detectan los silencios con `silencedetect`.
2. Se calcula la lista de tramos a CONSERVAR (margen alrededor de la voz, parte de la pausa que se
   deja para que no suene robótico, fusión de tramos casi pegados).
3. En video, los bordes se alinean a la rejilla de cuadros (`fps=<detectado>`): así cada tramo dura
   exactamente N cuadros en imagen y en audio, y el desfase no se acumula corte tras corte.
4. Se cortan AMBAS pistas en los mismos rangos (`trim`/`atrim` + `setpts`/`asetpts` + `concat`), con
   `afade` de 10 ms por tramo (sin clics). Con más de 150 tramos se renderiza por partes con los
   mismos parámetros (audio PCM en las partes) y se unen con el demuxer concat.
5. Se verifica la salida: duración de video = audio (±1 cuadro) y total = suma de tramos (±0.05 s).

Umbral `auto`: `silencedetect` compara MUESTRA POR MUESTRA, no RMS. Con umbral = RMS del ruido + 10 dB
los picos del ruido (≈ RMS + 12 dB en medio segundo) rompen cada silencio y no se detecta ninguno
(medido: ruido rosa RMS -66 dB → 0 silencios a -56 dB, estables solo desde -51 dB). Por eso el piso se
mide con el PICO por ventana de 50 ms (percentil 10) y el umbral es piso + 6 dB (≈ RMS del ruido
+ 15 dB), acotado a [-50, -25] dB y nunca a menos de 15 dB de la voz (percentil 90 del RMS).

Uso:
  python3 scripts/silencios.py <entrada> [--umbral auto|-38] [--min-silencio 0.5] [--margen 0.12]
      [--dejar 0.2] [--salida <archivo>] [--reporte] [--proyecto <dir>] [--motor ffmpeg|auto-editor]

  --reporte   no renderiza: imprime antes/después, % quitado, cortes y los 5 silencios más largos.
  Siempre escribe `<salida>.cortes.json` (umbral, tramos conservados y eliminados) para trazabilidad.

Salida (sin --salida): `<nombre>_sin_silencios.mp4` junto a la entrada (audio: misma extensión); con
--proyecto, el final va en la raíz del proyecto y los intermedios en su recursos/ (AGENT §13).

Códigos de salida: 0 ok · 1 fallo de FFmpeg o de la verificación (reportar, no reintentar)
                   2 argumentos o entrada (corregir y repetir) · 3 entorno (preguntar al usuario)

Importable (lo usa subtitulos.py): sondear, extraer_analisis, perfil_niveles, umbral_auto,
detectar_silencios, tramos_a_conservar, ajustar_a_cuadros.
"""
import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

VENTANA_S = 0.05          # ventana del perfil de niveles (800 muestras a 16 kHz)
SR_ANALISIS = 16000
UMBRAL_MIN, UMBRAL_MAX = -50.0, -25.0
FUSION_S = 0.15           # un hueco a quitar menor que esto no vale el corte
MIN_TRAMO_S = 0.10        # un tramo a conservar menor que esto es un clic suelto
FADE_S = 0.010            # afade por tramo (8-12 ms): evita clics en cada unión
TROZO = 150               # tramos por render; más, y el filtergraph crece sin control
FPS_ESTANDAR = (23.976, 24.0, 25.0, 29.97, 30.0, 48.0, 50.0, 59.94, 60.0)
FPS_FRACCION = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001"}
AUDIO_EXT = {  # extensión → (códec, parámetros extra); la salida de audio conserva su tipo
    ".wav": ("pcm_s16le", []), ".m4a": ("aac", ["-b:a", "192k"]), ".aac": ("aac", ["-b:a", "192k"]),
    ".mp3": ("libmp3lame", ["-b:a", "192k"]), ".flac": ("flac", []),
}


# ---------------------------------------------------------------- mensajes y errores
def fallar(msg, codigo=2, siguiente=None):
    """Error accionable en español: una línea de causa y, si aplica, la línea `Siguiente:`."""
    print(f"ERROR: {msg}", file=sys.stderr)
    if siguiente:
        print(f"Siguiente: {siguiente}", file=sys.stderr)
    raise SystemExit(codigo)


def verificar_entorno():
    for b in ("ffmpeg", "ffprobe"):
        if not shutil.which(b):
            fallar(f"no encuentro `{b}` en el PATH.", 3,
                   "pide al usuario instalar FFmpeg (brew install ffmpeg) y corre zsh scripts/preflight.sh")


def q(ruta):
    """Ruta citada para copiar y pegar en zsh (que no divide palabras, pero sí rompe con espacios)."""
    return shlex.quote(str(ruta))


def resolver_proyecto(repo, arg):
    """Carpeta del proyecto (ruta o slug bajo proyectos/). Crea recursos/ si falta; nunca el proyecto."""
    if not arg:
        return None
    for cand in (arg, os.path.join(repo, "proyectos", arg)):
        if os.path.isdir(cand):
            p = os.path.abspath(cand)
            os.makedirs(os.path.join(p, "recursos"), exist_ok=True)
            return p
    fallar(f"no existe el proyecto `{arg}`.", 2,
           "créalo con mkdir -p proyectos/<slug>_<DDMMAAAA>/recursos (AGENT §13) o pasa la ruta correcta")


# ---------------------------------------------------------------- sondeo
def _frac(txt):
    try:
        n, d = (txt or "0/0").split("/")
        return float(n) / float(d) if float(d) else 0.0
    except ValueError:
        return 0.0


def fps_normalizado(r_frame_rate, avg_frame_rate):
    """(fps float, texto para el filtro fps). VFR de teléfono → el estándar más cercano al promedio."""
    r, avg = _frac(r_frame_rate), _frac(avg_frame_rate)
    base = avg if avg > 0 else r
    if base <= 0:
        return 30.0, "30"
    cerca = min(FPS_ESTANDAR, key=lambda f: abs(f - base))
    if abs(cerca - base) / cerca <= 0.03:
        return (30000 / 1001 if cerca == 29.97 else 24000 / 1001 if cerca == 23.976
                else 60000 / 1001 if cerca == 59.94 else cerca), FPS_FRACCION.get(cerca, f"{cerca:g}")
    return float(round(base)), str(round(base))


def sondear(ruta):
    """Streams de la entrada con ffprobe. Sale con código 2 si no es un medio legible."""
    if not os.path.isfile(ruta):
        fallar(f"no existe el archivo `{ruta}`.", 2, "revisa la ruta (usa comillas si tiene espacios)")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,"
                        "avg_frame_rate,duration,sample_rate,channels,color_transfer:"
                        "stream_side_data=rotation:stream_disposition=attached_pic",
                        "-of", "json", ruta], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        fallar(f"FFmpeg no puede leer `{ruta}`: {r.stderr.strip()[:200]}", 2,
               "verifica que sea un video o audio válido (ffprobe <archivo>)")
    datos = json.loads(r.stdout or "{}")
    info = {"ruta": ruta, "duracion": float((datos.get("format") or {}).get("duration") or 0),
            "video": None, "audio": None}
    for s in datos.get("streams", []):
        tipo = s.get("codec_type")
        if tipo == "video" and info["video"] is None and not (s.get("disposition") or {}).get("attached_pic"):
            fps, fps_txt = fps_normalizado(s.get("r_frame_rate"), s.get("avg_frame_rate"))
            rot = 0
            for sd in s.get("side_data_list") or []:
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            w, h = int(s.get("width") or 0), int(s.get("height") or 0)
            if abs(rot) in (90, 270):
                w, h = h, w
            info["video"] = {"w": w, "h": h, "fps": fps, "fps_txt": fps_txt, "codec": s.get("codec_name"),
                             "vfr": abs(_frac(s.get("r_frame_rate")) - _frac(s.get("avg_frame_rate"))) > 0.01,
                             "dur": float(s.get("duration") or 0) or None,
                             "hdr": s.get("color_transfer") in ("arib-std-b67", "smpte2084")}
        elif tipo == "audio" and info["audio"] is None:
            info["audio"] = {"sr": int(s.get("sample_rate") or 48000), "canales": int(s.get("channels") or 2),
                             "codec": s.get("codec_name"), "dur": float(s.get("duration") or 0) or None}
    if info["duracion"] <= 0:
        info["duracion"] = max((x["dur"] or 0) for x in (info["video"], info["audio"]) if x) if (
            info["video"] or info["audio"]) else 0
    return info


# ---------------------------------------------------------------- análisis
def extraer_analisis(entrada, wav):
    """Copia mono 16 kHz con la MISMA línea de tiempo que el render (first_pts=0, huecos rellenos)."""
    comun.run(["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", entrada, "-map", "0:a:0", "-vn",
               "-af", f"aresample={SR_ANALISIS}:async=1:first_pts=0,highpass=f=60",
               "-ac", "1", "-c:a", "pcm_s16le", wav])
    return wav


def _db_txt(v):
    v = v.strip()
    return -120.0 if "inf" in v else max(-120.0, float(v))


def perfil_niveles(wav, ventana=VENTANA_S, sr=SR_ANALISIS):
    """[(t, pico_db, rms_db)] por ventana de `ventana` s (astats con reset por ventana)."""
    n = max(1, int(round(ventana * sr)))
    r = comun.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", wav, "-af",
                   f"asetnsamples=n={n}:p=0,astats=metadata=1:reset=1:measure_perchannel=none:"
                   "measure_overall=Peak_level+RMS_level,ametadata=print:file=-", "-f", "null", "-"])
    niveles, t, pico = [], 0.0, None
    for linea in r.stdout.splitlines():
        if linea.startswith("frame:"):
            m = re.search(r"pts_time:([\d.]+)", linea)
            t = float(m.group(1)) if m else t
        elif "Overall.Peak_level=" in linea:
            pico = _db_txt(linea.split("=", 1)[1])
        elif "Overall.RMS_level=" in linea and pico is not None:
            niveles.append((t, pico, _db_txt(linea.split("=", 1)[1])))
            pico = None
    return niveles


def percentil(valores, p):
    if not valores:
        return -120.0
    v = sorted(valores)
    k = (len(v) - 1) * p / 100.0
    i = int(math.floor(k))
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (k - i)


def umbral_auto(niveles):
    """(umbral_db, piso_db, voz_db). Ver el docstring del módulo para el porqué del pico + 6 dB."""
    piso = percentil([p for _, p, _ in niveles], 10)
    voz = percentil([r for _, _, r in niveles], 90)
    umbral = min(piso + 6.0, voz - 15.0)
    return round(min(UMBRAL_MAX, max(UMBRAL_MIN, umbral)), 1), round(piso, 1), round(voz, 1)


def detectar_silencios(wav, umbral_db, min_dur, desde=None, dur=None, total=None):
    """[(ini, fin)] de `silencedetect` en segundos absolutos; opcionalmente solo en [desde, desde+dur]."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats"]
    if desde is not None:
        cmd += ["-ss", f"{desde:.6f}", "-t", f"{dur:.6f}"]
    cmd += ["-i", wav, "-af", f"silencedetect=noise={umbral_db}dB:d={min_dur}", "-f", "null", "-"]
    r = comun.run(cmd)
    base = desde or 0.0
    fin_rango = (base + dur) if dur is not None else total
    silencios, ini = [], None
    for linea in r.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.eE+-]+)", linea)
        if m:
            ini = max(0.0, float(m.group(1))) + base
            continue
        m = re.search(r"silence_end:\s*([\d.eE+-]+)", linea)
        if m and ini is not None:
            silencios.append((ini, float(m.group(1)) + base))
            ini = None
    if ini is not None:  # el archivo (o el rango) termina en silencio
        silencios.append((ini, fin_rango if fin_rango is not None else ini))
    if fin_rango is not None:
        silencios = [(a, min(b, fin_rango)) for a, b in silencios if b > a]
    return silencios


# ---------------------------------------------------------------- lista de cortes
def tramos_a_conservar(silencios, total, margen=0.12, dejar=0.2, fusion=FUSION_S, min_tramo=MIN_TRAMO_S):
    """Tramos [ini, fin] a conservar. De cada silencio se deja `margen` junto a la voz más `dejar/2`
    por lado (la pausa resultante dura 2·margen + dejar); en los extremos del archivo solo se deja
    margen + dejar/2 junto a la voz. Huecos < `fusion` no se cortan; tramos < `min_tramo` se quitan."""
    quitar = []
    colchon = margen + dejar / 2.0
    for s, e in silencios:
        ini = 0.0 if s <= 0.001 else s + colchon
        fin = total if e >= total - 0.001 else e - colchon
        if fin - ini >= fusion:
            quitar.append((ini, fin))
    conservar, t = [], 0.0
    for a, b in sorted(quitar):
        if a > t:
            conservar.append([t, a])
        t = max(t, b)
    if t < total:
        conservar.append([t, total])
    return [c for c in conservar if c[1] - c[0] >= min_tramo]


def ajustar_a_cuadros(tramos, fps, limite):
    """Bordes a la rejilla k/fps (redondeo), el final ≤ piso(limite·fps)/fps; fusiona los que se tocan."""
    k_max = int(math.floor(limite * fps + 1e-6))
    out = []
    for a, b in tramos:
        ka, kb = int(round(a * fps)), min(int(round(b * fps)), k_max)
        if kb <= ka:
            continue
        if out and ka <= out[-1][1]:
            out[-1][1] = max(out[-1][1], kb)
        else:
            out.append([ka, kb])
    return [[ka / fps, kb / fps] for ka, kb in out], [[ka, kb] for ka, kb in out]


def complemento(tramos, total):
    out, t = [], 0.0
    for a, b in tramos:
        if a - t > 1e-6:
            out.append([round(t, 4), round(a, 4)])
        t = b
    if total - t > 1e-6:
        out.append([round(t, 4), round(total, 4)])
    return out


# ---------------------------------------------------------------- render
def _cadena_audio(i, a, b, total, pad, sr):
    # Muestras exactas (no segundos): `atrim=start=` pasa por µs y pierde ~10 muestras por tramo
    # (medido), lo que con cientos de cortes acumularía desfase contra la imagen.
    s0, s1 = int(round(a * sr)), int(round(b * sr))
    largo = (s1 - s0) / sr
    f = [f"atrim=start_sample={s0}:end_sample={s1}", "asetpts=PTS-STARTPTS"]
    if a > 0.001 and largo > 3 * FADE_S:
        f.append(f"afade=t=in:st=0:d={FADE_S}")
    if b < total - 0.001 and largo > 3 * FADE_S:
        f.append(f"afade=t=out:st={largo - FADE_S:.6f}:d={FADE_S}")
    return f"[{pad}{i}]" + ",".join(f) + f"[at{i}]"


def filtergraph(tramos, total, sr, fps_txt=None, desfase=0.0):
    """Filtergraph trim/atrim + concat. `desfase` resta el inicio del trozo (entrada con -ss)."""
    k = len(tramos)
    partes = []
    if fps_txt:
        partes.append(f"[0:v]fps={fps_txt}:start_time=0,split={k}" + "".join(f"[v{i}]" for i in range(k)))
    partes.append(f"[0:a]aresample={sr}:async=1:first_pts=0,asplit={k}" + "".join(f"[a{i}]" for i in range(k)))
    for i, (a, b) in enumerate(tramos):
        a, b = a - desfase, b - desfase
        if fps_txt:
            partes.append(f"[v{i}]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[vt{i}]")
        partes.append(_cadena_audio(i, a, b, total - desfase, "a", sr))
    if fps_txt:
        partes.append("".join(f"[vt{i}][at{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=1[v][a]")
    else:
        partes.append("".join(f"[at{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[a]")
    return ";".join(partes)


def _params_video(fps_txt, canales):
    # `-r` fija la base de tiempo del codificador en 1/fps: tras `concat` la base es 1 µs y el muxer
    # pierde la duración del último cuadro (medido: 164 cuadros reportados como 163·1/30 s).
    p = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", fps_txt]
    return p, (["-ac", "2"] if canales > 2 else [])


def renderizar(info, tramos, salida, tmpdir, trozo=TROZO, imprimir=True):
    """Renderiza la lista de tramos. Devuelve la duración esperada (suma de tramos)."""
    total = sum(b - a for a, b in tramos)
    hay_video = info["video"] is not None
    fps_txt = info["video"]["fps_txt"] if hay_video else None
    canales = info["audio"]["canales"]
    ext = os.path.splitext(salida)[1].lower()
    if hay_video:
        sr = 48000
        vparams, ac = _params_video(fps_txt, canales)
        final_audio = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"] + ac
    else:
        codec, extra = AUDIO_EXT.get(ext, ("aac", ["-b:a", "192k"]))
        sr = 48000 if codec == "aac" else info["audio"]["sr"]
        vparams, ac = [], (["-ac", "2"] if canales > 2 else [])
        final_audio = ["-c:a", codec] + extra + ["-ar", str(sr)] + ac
    fin_archivo = info["duracion"]
    grupos = [tramos[i:i + trozo] for i in range(0, len(tramos), trozo)]
    mostrar = imprimir and total >= 60

    if len(grupos) == 1:
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", info["ruta"],
               "-filter_complex", filtergraph(tramos, fin_archivo, sr, fps_txt)]
        cmd += (["-map", "[v]", "-map", "[a]"] + vparams if hay_video else ["-map", "[a]"])
        cmd += final_audio + (["-movflags", "+faststart"] if ext in (".mp4", ".mov", ".m4v", ".m4a") else [])
        comun.ffmpeg_con_progreso(cmd + [salida], total, "render", imprimir=mostrar)
        return total

    # Por partes: mismo códec de video en todas (el concat demuxer copia sin recodificar) y audio PCM
    # en las partes para no acumular el retardo de cebado del AAC en cada unión.
    lista = os.path.join(tmpdir, "partes.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for j, grupo in enumerate(grupos, 1):
            x0 = grupo[0][0]
            largo = grupo[-1][1] - x0
            parte = os.path.join(tmpdir, f"parte_{j:03d}." + ("mov" if hay_video else "wav"))
            cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-ss", f"{x0:.6f}", "-t", f"{largo + 0.5:.6f}",
                   "-i", info["ruta"], "-filter_complex", filtergraph(grupo, fin_archivo, sr, fps_txt, x0)]
            cmd += (["-map", "[v]", "-map", "[a]"] + vparams if hay_video else ["-map", "[a]"])
            cmd += ["-c:a", "pcm_s16le", "-ar", str(sr)] + ac
            sub = sum(b - a for a, b in grupo)
            comun.ffmpeg_con_progreso(cmd + [parte], sub, f"parte {j}/{len(grupos)}", imprimir=mostrar)
            f.write("file '" + parte.replace("'", "'\\''") + "'\n")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", lista]
    cmd += (["-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy"] if hay_video else ["-map", "0:a:0"])
    cmd += final_audio + (["-movflags", "+faststart"] if ext in (".mp4", ".mov", ".m4v", ".m4a") else [])
    comun.ffmpeg_con_progreso(cmd + [salida], total, "unión", imprimir=mostrar)
    return total


def duraciones(ruta):
    """{video, audio, formato} en segundos (stream duration; si falta, la del formato)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
                        "-of", "json", ruta], capture_output=True, text=True, encoding="utf-8", errors="replace")
    datos = json.loads(r.stdout or "{}")
    fmt = float((datos.get("format") or {}).get("duration") or 0)
    out = {"formato": fmt, "video": None, "audio": None}
    for s in datos.get("streams", []):
        t = s.get("codec_type")
        if t in ("video", "audio") and out[t] is None:
            out[t] = float(s.get("duration") or fmt)
    return out


def verificar_salida(salida, esperado, fps=None):
    """(ok, texto). A/V dentro de 1 cuadro y duración ≈ suma de tramos (±0.05 s)."""
    d = duraciones(salida)
    real = d["audio"] if d["audio"] is not None else d["formato"]
    delta_total = abs(real - esperado)
    ok = delta_total <= 0.05
    txt = f"duración {real:.3f} s vs tramos {esperado:.3f} s (Δ {delta_total:.3f})"
    if fps and d["video"] is not None and d["audio"] is not None:
        av = abs(d["video"] - d["audio"])
        ok = ok and av <= 1.0 / fps + 0.002
        txt = f"A/V Δ {av:.3f} s (≤ 1 cuadro = {1 / fps:.3f}); " + txt
    return ok, txt


# ---------------------------------------------------------------- auto-editor (opcional)
def via_auto_editor(entrada, salida, umbral_db, margen):
    """Alternativa si `auto-editor` está instalado (AGENT §6). No verificada en esta máquina."""
    if not shutil.which("auto-editor"):
        fallar("`auto-editor` no está instalado.", 3,
               "usa el motor por defecto (sin --motor) o pide al usuario instalarlo en un venv")
    lineal = 10 ** (umbral_db / 20.0)
    r = subprocess.run(["auto-editor", entrada, "--edit", f"audio:threshold={lineal:.4f}",
                        "--margin", f"{margen}s", "--no-open", "-o", salida],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print((r.stderr or r.stdout)[-1200:], file=sys.stderr)
        fallar("auto-editor falló (su CLI cambia entre versiones).", 1, "repite sin --motor (ruta FFmpeg)")


# ---------------------------------------------------------------- CLI
def _num_umbral(txt):
    if str(txt).lower() == "auto":
        return None
    try:
        v = float(str(txt).lower().replace("db", "").strip())
    except ValueError:
        fallar(f"--umbral `{txt}` no es válido.", 2, "usa --umbral auto o un número en dB, p. ej. --umbral -38")
    if not -90 <= v <= -5:
        fallar(f"--umbral {v} dB fuera de rango.", 2, "usa un valor entre -90 y -5 dB (típico -45 a -30)")
    return v


def rutas_salida(entrada, info, salida_arg, proyecto):
    base, ext = os.path.splitext(os.path.basename(entrada))
    if info["video"]:
        ext_out = ".mp4"
    else:
        ext_out = ext.lower() if ext.lower() in AUDIO_EXT else ".m4a"
    if salida_arg:
        salida = salida_arg if os.path.isabs(salida_arg) or not proyecto else os.path.join(proyecto, salida_arg)
    else:
        salida = os.path.join(proyecto or os.path.dirname(os.path.abspath(entrada)),
                              f"{base}_sin_silencios{ext_out}")
    salida = os.path.abspath(salida)
    nombre = os.path.splitext(os.path.basename(salida))[0]
    cortes = os.path.join(proyecto, "recursos", f"{nombre}.cortes.json") if proyecto else \
        os.path.join(os.path.dirname(salida), f"{nombre}.cortes.json")
    return salida, cortes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Corta tiempos muertos de video/audio sin desincronizar A/V.")
    ap.add_argument("entrada", help="video o audio de entrada")
    ap.add_argument("--umbral", default="auto", help="auto (piso de ruido + 6 dB) o dB, p. ej. -38")
    ap.add_argument("--min-silencio", type=float, default=0.5, help="silencio mínimo a considerar (s)")
    ap.add_argument("--margen", type=float, default=0.12, help="audio que se conserva junto a la voz (s)")
    ap.add_argument("--dejar", type=float, default=0.2, help="parte de cada pausa quitada que se deja (s)")
    ap.add_argument("--salida", help="archivo de salida (default <nombre>_sin_silencios.<ext>)")
    ap.add_argument("--reporte", action="store_true", help="simulacro: no renderiza, solo reporta")
    ap.add_argument("--proyecto", help="carpeta del proyecto (intermedios en recursos/, final en la raíz)")
    ap.add_argument("--motor", choices=("ffmpeg", "auto-editor"), default="ffmpeg")
    ap.add_argument("--trozo", type=int, default=TROZO, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    for nombre, v, lo, hi in (("--min-silencio", a.min_silencio, 0.1, 30), ("--margen", a.margen, 0, 2),
                              ("--dejar", a.dejar, 0, 5)):
        if not lo <= v <= hi:
            fallar(f"{nombre} {v} fuera de rango [{lo}, {hi}].", 2, "usa los defaults (0.5 / 0.12 / 0.2)")
    verificar_entorno()
    repo = comun.raiz_repo(os.path.dirname(os.path.abspath(__file__)))
    proyecto = resolver_proyecto(repo, a.proyecto)
    entrada = os.path.abspath(a.entrada)
    info = sondear(entrada)
    if not info["audio"]:
        fallar("la entrada no tiene pista de audio: no hay silencios que detectar.", 2,
               "pasa el video con su audio original")
    salida, ruta_cortes = rutas_salida(entrada, info, a.salida, proyecto)
    if salida == entrada:
        fallar("la salida no puede sobrescribir la entrada.", 2, "usa otro --salida")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    umbral_manual = _num_umbral(a.umbral)

    base_tmp = os.path.join(proyecto, "recursos") if proyecto else os.path.dirname(salida)
    with tempfile.TemporaryDirectory(prefix=".silencios_", dir=base_tmp) as tmp:
        wav = extraer_analisis(entrada, os.path.join(tmp, "analisis.wav"))
        niveles = perfil_niveles(wav)
        umbral, piso, voz = umbral_auto(niveles)
        if umbral_manual is not None:
            umbral = umbral_manual
        total = info["duracion"]
        dur_util = min(x for x in (info["audio"]["dur"], (info["video"] or {}).get("dur"), total) if x)
        silencios = detectar_silencios(wav, umbral, a.min_silencio, total=dur_util)
        crudos = tramos_a_conservar(silencios, dur_util, a.margen, a.dejar)
        fps = info["video"]["fps"] if info["video"] else None
        if fps:
            tramos, _ = ajustar_a_cuadros(crudos, fps, dur_util)
        else:
            tramos = [[round(x, 6), round(min(y, dur_util), 6)] for x, y in crudos if min(y, dur_util) > x]
        despues = sum(b - a_ for a_, b in tramos)
        cortes_n = len(complemento(tramos, dur_util))
        modo = "manual" if umbral_manual is not None else "auto"
        doc = {"entrada": entrada, "salida": None if a.reporte else salida, "motor": a.motor,
               "umbral_db": umbral, "umbral_modo": modo, "piso_ruido_db": piso, "voz_db": voz,
               "parametros": {"min_silencio": a.min_silencio, "margen": a.margen, "dejar": a.dejar,
                              "fusion": FUSION_S, "min_tramo": MIN_TRAMO_S, "fps": info["video"]["fps_txt"]
                              if info["video"] else None},
               "duracion_original": round(dur_util, 4), "duracion_final": round(despues, 4),
               "segmentos": [[round(x, 4), round(y, 4)] for x, y in tramos],
               "eliminados": complemento(tramos, dur_util),
               "silencios_detectados": [[round(x, 3), round(y, 3)] for x, y in silencios]}
        if a.motor == "auto-editor":
            doc["nota"] = "segmentos calculados por la ruta FFmpeg; auto-editor decide sus propios cortes"
        with open(ruta_cortes, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)

        if not tramos:
            fallar(f"todo el archivo quedó bajo el umbral {umbral} dB (nada que conservar).", 2,
                   "sube la sensibilidad con --umbral -50 o revisa que el audio tenga voz")
        pct = 100.0 * (dur_util - despues) / dur_util if dur_util else 0.0
        resumen = (f"{dur_util:.2f} s → {despues:.2f} s (−{pct:.1f} %), {cortes_n} cortes, "
                   f"umbral {umbral} dB ({modo}; piso {piso} dB)")
        sig_extra = f" --proyecto {q(proyecto)}" if proyecto else ""
        if a.reporte:
            largos = sorted(silencios, key=lambda s: s[1] - s[0], reverse=True)[:5]
            print(f"REPORTE (sin render): {resumen}")
            print("Silencios más largos: " + (" · ".join(f"{e - s:.2f} s @{s:.1f}" for s, e in largos) or "ninguno"))
            print(f"Lista de cortes: {ruta_cortes}")
            print(f"Siguiente: python3 scripts/silencios.py {q(entrada)}{sig_extra} "
                  "(sin --reporte) para renderizar; ajusta --umbral/--min-silencio si cortó de más")
            return 0
        if cortes_n == 0:
            print(f"OK sin cambios: {resumen}; no se generó salida.")
            print(f"Lista de cortes: {ruta_cortes}")
            print("Siguiente: usa la entrada tal cual, o prueba --umbral -30 / --min-silencio 0.3")
            return 0

        if a.motor == "auto-editor":
            via_auto_editor(entrada, salida, umbral, a.margen)
            d = duraciones(salida)
            ok = d["video"] is None or d["audio"] is None or abs(d["video"] - d["audio"]) <= 1.0 / (fps or 30) + 0.002
            print(f"{'OK' if ok else 'FALLO'} silencios (auto-editor): {d['formato']:.2f} s; umbral {umbral} dB")
            print(f"Salida: {salida}")
            print(f"Siguiente: python3 scripts/subtitulos.py {q(salida)}{sig_extra}")
            return 0 if ok else 1

        esperado = renderizar(info, tramos, salida, tmp, trozo=max(2, a.trozo))
    ok, txt = verificar_salida(salida, esperado, fps)
    if not ok:
        print(f"FALLO verificación: {txt}", file=sys.stderr)
        fallar("la salida no cuadra con la lista de cortes.", 1,
               f"reporta al usuario; la lista está en {ruta_cortes}")
    print(f"OK silencios: {resumen}")
    v = info["video"]
    print(f"Salida: {salida}" + (f" ({v['w']}x{v['h']}, {v['fps_txt']} fps"
                                   f"{', VFR normalizado' if v['vfr'] else ''})" if v else ""))
    print(f"Verificación: {txt}")
    print(f"Lista de cortes: {ruta_cortes}")
    if v and v["hdr"]:
        print("AVISO: fuente HDR (HLG/PQ) recodificada a yuv420p SDR sin tonemap: los colores pueden verse lavados.")
    print(f"Siguiente: python3 scripts/subtitulos.py {q(salida)}{sig_extra} --quemar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
