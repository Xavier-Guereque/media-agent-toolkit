#!/usr/bin/env python3
"""componer — piezas comunes para pasar de la voz medida a una composición Remotion: props por escena, cama musical,
mezcla con ducking, clips recortados de metraje y specs de las dos orientaciones.

Se importa desde el `recursos/componer.py` de cada proyecto, que solo declara textos, capturas y focos:

    sys.path.insert(0, os.path.join(<repo>, "scripts"))
    import componer as cp
    t = cp.leer_tiempos(REC)                                   # tiempos.json de scripts/narrar.py (MEDIDOS)
    escenas = cp.escenas_props(t, {"1": {"titulo": "*ACME IA* ya está en tu portal", "apoyo": "…"}})
    cama, desc = cp.cama_procedural(t["duracion"], escenas[0]["fin"], escenas[-1]["inicio"], 110, f"{REC}/mezcla", semilla=23)
    cp.mezclar(f"{REC}/mezcla.wav", t["duracion"], tomas=cp.tomas_de(t, REC), cama=cama)
    cp.escribir_specs(PROY, "MiComposicion", {"escenas": escenas, "audio": "mezcla.wav"}, t["duracion"],
                      {"vertical": "video-9x16.mp4", "horizontal": "video-16x9.mp4"})

Contratos (verificados en los videos animados de referencia y del Diseñador de Videovigilancia, [[Motor-Remotion]]):
  - Los tiempos NO se inventan: vienen de `tiempos.json` ({duracion, escenas: [{id, tipo, inicio, fin, wav, voz_inicio,
    palabras}]}) y las palabras se pasan RELATIVAS al inicio de su escena (el sistema de coordenadas del <Sequence>).
  - Niveles de la casa para explicadores: voz −15 LUFS, música −18 LUFS con ducking por sidechain (threshold 0.05,
    ratio 3, attack 25 ms, release 350 ms) y asplit explícito del bus de voz. El acabado a −14 LUFS lo hace remotion.py.
  - Para cursos (música bajo narración desaconsejada) se usa `narrar.mezclar_cama`, no este módulo.
Determinista: mismas entradas → mismos bytes de mezcla.
"""
import json
import os
import subprocess

import sonido

LUFS_VOZ = -15
LUFS_MUSICA = -18
DUCKING = "sidechaincompress=threshold=0.05:ratio=3:attack=25:release=350"


def run(*a):
    """FFmpeg/FFprobe sin ruido; si falla, el error de FFmpeg viaja en la excepción."""
    r = subprocess.run(a, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise subprocess.CalledProcessError(r.returncode, a, stderr=r.stderr[-2000:])


def duracion(ruta):
    """Duración en segundos medida con ffprobe."""
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", ruta]))


# ── escenas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def leer_tiempos(rec):
    with open(os.path.join(rec, "tiempos.json"), encoding="utf-8") as f:
        return json.load(f)


def palabras_relativas(escena):
    """Palabras {w, a, b} de una escena de tiempos.json, con a/b relativos a su inicio (redondeo a ms)."""
    ini = escena["inicio"]
    return [{"w": p["w"], "a": round(p["a"] - ini, 3), "b": round(p["b"] - ini, 3)} for p in escena.get("palabras") or []]


def escenas_props(tiempos, campos=None, por_defecto=None):
    """Props por escena: {id, tipo, inicio, fin} + los campos del proyecto para ese id + palabras relativas.

    `campos`: {id: {"titulo": …, "apoyo": …, "captura": …}}; los valores None se omiten. `por_defecto` se aplica a
    las escenas sin entrada (p. ej. {"titulo": "", "apoyo": ""})."""
    campos = campos or {}
    out = []
    for e in tiempos["escenas"]:
        esc = {"id": e["id"], "tipo": e["tipo"], "inicio": e["inicio"], "fin": e["fin"]}
        for k, v in {**(por_defecto or {}), **campos.get(e["id"], {})}.items():
            if v is not None:
                esc[k] = list(v) if isinstance(v, tuple) else v
        if e.get("palabras"):
            esc["palabras"] = palabras_relativas(e)
        out.append(esc)
    return out


def tomas_de(tiempos, rec):
    """[(wav absoluto, voz_inicio)] de las escenas con voz, para `mezclar`."""
    return [(os.path.join(rec, e["wav"]), e["voz_inicio"]) for e in tiempos["escenas"] if e.get("wav")]


def encadenar_tomas(escenas, rec, tempo=1.0, entrada=0.15, respiro=0.25, cierre_min=0.0, fps=30):
    """Duraciones desde las tomas ya grabadas (`recursos/voz/<id>.wav`) cuando no hay tiempos.json: cada toma se ajusta
    con `atempo` a `recursos/mezcla/v<id>.wav`, la escena dura entrada + voz + respiro (la de tipo "cierre", al menos
    `cierre_min`) redondeada al cuadro, y las escenas se encadenan.

    `escenas`: [(id, tipo)]. Devuelve (tramos [{id, tipo, inicio, fin, dur}], tomas [(wav, inicio_voz)], total)."""
    os.makedirs(os.path.join(rec, "mezcla"), exist_ok=True)
    tramos, tomas, t = [], [], 0.0
    for id_, tipo in escenas:
        out = os.path.join(rec, "mezcla", f"v{id_}.wav")
        run("ffmpeg", "-y", "-i", os.path.join(rec, "voz", f"{id_}.wav"), "-af", f"aresample=48000,atempo={tempo}",
            "-ar", "48000", "-ac", "1", out)
        d = entrada + duracion(out) + respiro
        if tipo == "cierre":
            d = max(d, cierre_min)
        d = round(d * fps) / fps
        tramos.append({"id": id_, "tipo": tipo, "inicio": round(t, 3), "fin": round(t + d, 3), "dur": d})
        tomas.append((out, t + entrada))
        t += d
    return tramos, tomas, round(t, 3)


# ── música ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def cama_procedural(total, fin_intro, inicio_cierre, bpm, carpeta, lufs=LUFS_MUSICA, semilla=7):
    """Cama rítmica de la casa (`sonido.musica_procedural`): entra con la intro y anuncia el cierre.
    Devuelve (wav, descripción)."""
    lt = {"duracion": total, "total": total, "escenas": [
        {"tipo": "intro", "ini": 0, "fin": fin_intro},
        {"tipo": "cierre", "ini": inicio_cierre, "fin": total}]}
    return sonido.musica_procedural(lt, bpm, carpeta, lufs, semilla)


ACORDES_AMBIENTE = [(220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (261.63, 329.63, 392.00), (196.00, 246.94, 293.66)]


def cama_ambiental(total, salida, lufs=LUFS_MUSICA, semilla=7):
    """Cama documental suave (explicadores largos): pads Am–F–C–G de 16 s, bajo sub de 55 Hz y aire de ruido rosa
    filtrado, con fundidos de 3 s y 4 s. Sin derechos de terceros. Verificada en [[Lecciones-2026-10-31-star-trek-cronologia]].
    `semilla` fija el ruido de `anoisesrc` (sin ella FFmpeg usa una aleatoria y cada corrida sale distinta)."""
    carpeta = os.path.dirname(os.path.abspath(salida))
    os.makedirs(carpeta, exist_ok=True)
    capas = [f"aevalsrc='0.16*sin(2*PI*{r}*t)+0.11*sin(2*PI*{t}*t)+0.09*sin(2*PI*{q}*t)+0.05*sin(2*PI*{r * 2}*t)':d=16.5:s=48000,"
             f"afade=t=in:st=0:d=1.2,afade=t=out:st=15.3:d=1.2[p{i}]" for i, (r, t, q) in enumerate(ACORDES_AMBIENTE)]
    ciclo = os.path.join(carpeta, "ciclo.wav")
    run("ffmpeg", "-y", "-v", "error", "-nostdin", "-filter_complex",
        ";".join(capas) + ";" + "".join(f"[p{i}]" for i in range(4)) + "concat=n=4:v=0:a=1[ciclo]",
        "-map", "[ciclo]", "-c:a", "pcm_s16le", ciclo)
    run("ffmpeg", "-y", "-v", "error", "-nostdin", "-stream_loop", str(int(total // 66) + 2), "-i", ciclo,
        "-f", "lavfi", "-i", f"aevalsrc='0.10*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*0.08*t))':d={total}:s=48000",
        "-f", "lavfi", "-i", f"anoisesrc=color=pink:r=48000:a=0.012:d={total}:seed={semilla}",
        "-filter_complex",
        f"[0]atrim=duration={total},lowpass=f=1100,aecho=0.8:0.6:120|240:0.35|0.18,tremolo=f=0.25:d=0.25[pads];"
        "[1]lowpass=f=160[bajo];[2]bandpass=f=2400:w=900,tremolo=f=0.12:d=0.8,volume=0.6[aire];"
        f"[pads][bajo][aire]amix=inputs=3:normalize=0,afade=t=in:st=0:d=3,afade=t=out:st={total - 4.5}:d=4,"
        f"loudnorm=I={lufs}:TP=-2:LRA=9[m]",
        "-map", "[m]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", salida)
    return salida


# ── efectos de firma del motor ilustrado (procedurales, 0 USD, deterministas) ─────────────────────────────────────────
def sfx_lapiz(dur, salida, semilla=11):
    """Rasgueo de lápiz sobre papel: ruido blanco en banda 1.8–7 kHz con trazos irregulares (dos senos lentos
    multiplicados) y fundidos cortos. Se coloca bajo la voz, muy bajo, solo mientras se dibuja."""
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    trazos = "max(0,0.65*sin(2*PI*4.7*t)+0.45*sin(2*PI*2.9*t+1.3))*(0.75+0.25*sin(2*PI*11*t))"
    run("ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi",
        "-i", f"anoisesrc=color=white:r=48000:a=0.5:d={dur:.3f}:seed={semilla}",
        "-af", f"highpass=f=1800,lowpass=f=7000,volume='{trazos}':eval=frame,"
               f"afade=t=in:st=0:d=0.05,afade=t=out:st={max(0.0, dur - 0.18):.3f}:d=0.18,"
               "aformat=sample_rates=48000:channel_layouts=stereo",
        "-c:a", "pcm_s16le", salida)
    return salida


def sfx_sello(salida):
    """Golpe de sello de goma: grave amortiguado (62 + 124 Hz) y un chasquido de ruido corto."""
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    expr = ("st(1,random(9)*2-1);(1-exp(-t/0.002))*exp(-t*14)*(0.9*sin(2*PI*62*t)+0.4*sin(2*PI*124*t))"
            "+0.35*ld(1)*exp(-t*90)")
    run("ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", f"aevalsrc=exprs='{expr}':s=48000:d=0.6",
        "-af", "lowpass=f=3200,aformat=sample_rates=48000:channel_layouts=stereo", "-c:a", "pcm_s16le", salida)
    return salida


# ── mezcla ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def mezclar(salida, total, tomas, cama=None, sfx=(), voz_lufs=LUFS_VOZ, musica_lufs=None, ducking=DUCKING):
    """Mezcla final estéreo 48 kHz: tomas de voz colocadas en su inicio → loudnorm `voz_lufs` → ducking de la cama →
    SFX encima (sin ducking).

    `tomas`: [(wav, inicio_s)] (un `voz.wav` ya armado es [(voz.wav, 0)]). `cama`: wav ya nivelado (p. ej. de
    `cama_procedural`) o None para solo voz; si `musica_lufs` se da, la cama se renivela a ese valor.
    `sfx`: [(wav, inicio_s, volumen)], p. ej. whooshes CC0 en cada cambio de capítulo."""
    if not tomas:
        raise ValueError("mezclar: sin tomas de voz")
    ins, fil = [], []
    for k, (wav, ini) in enumerate(tomas):
        ms = int(ini * 1000)
        ins += ["-i", wav]
        fil.append(f"[{k}]adelay={ms}|{ms}[t{k}]")
    n = len(tomas)
    voz = (";".join(fil) + ";" + "".join(f"[t{k}]" for k in range(n)) +
           f"amix=inputs={n}:normalize=0,apad=whole_dur={total},atrim=duration={total},"
           f"loudnorm=I={voz_lufs}:TP=-1.5:LRA=11,aresample=48000")
    sig = n
    if cama:
        ins += ["-i", cama]
        nivel = f",loudnorm=I={musica_lufs}:TP=-2:LRA=9" if musica_lufs is not None else ""
        fc = (voz + ",asplit=2[v][sc];" +
              f"[{sig}]atrim=duration={total}{nivel}[m];[m][sc]{ducking}[md];")
        buses = "[v][md]"
        sig += 1
    else:
        fc = voz + "[v];"
        buses = "[v]"
    if sfx:
        partes = []
        for k, (wav, ini, vol) in enumerate(sfx):
            ms = int(max(0.0, ini) * 1000)
            ins += ["-i", wav]
            partes.append(f"[{sig + k}]aresample=48000,volume={vol},adelay={ms}|{ms}[w{k}]")
        fc += (";".join(partes) + ";" + "".join(f"[w{k}]" for k in range(len(sfx))) +
               f"amix=inputs={len(sfx)}:normalize=0,apad=whole_dur={total},atrim=duration={total}[sfx];")
        buses += "[sfx]"
    nb = buses.count("[")
    fc += (f"{buses}amix=inputs={nb}:normalize=0,aformat=channel_layouts=stereo[a]" if nb > 1
           else f"{buses}aformat=channel_layouts=stereo[a]")
    run("ffmpeg", "-y", *ins, "-filter_complex", fc, "-map", "[a]", "-ar", "48000", "-c:a", "pcm_s16le", salida)
    return salida


def nivel_medio(ruta, desde, dur):
    """mean_volume (dB) de una ventana con volumedetect: para comprobar que la música se oye en pausas y cola."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-nostdin", "-ss", str(desde), "-t", str(dur), "-i", ruta,
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for linea in r.stderr.splitlines():
        if "mean_volume:" in linea:
            return float(linea.split("mean_volume:")[1].split()[0])
    return None


# ── metraje y recursos ──────────────────────────────────────────────────────────────────────────────────────────────
def recortar_clip(origen, salida, ini, dur, vel=1.0, crop=None, fps=30, crf=14):
    """Clip sin audio de `dur` s de SALIDA desde `ini` de `origen`, acelerado `vel` veces y recortado (`crop` = "w:h:x:y"
    de FFmpeg). Se lee `dur·vel` s del origen. h264 yuv420p CRF 14: intermedio para Remotion, no entrega."""
    vf = ",".join(x for x in (f"crop={crop}" if crop else None, f"setpts=PTS/{vel}", f"fps={fps}") if x)
    run("ffmpeg", "-y", "-ss", str(ini), "-t", f"{dur * vel:.3f}", "-i", origen, "-an", "-vf", vf,
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p", salida)
    return salida


def logo_con_color(origen_svg, destino, color="#ffffff"):
    """Copia un SVG que usa `currentColor` fijando el color: <Img> de Remotion no hereda `color` de CSS."""
    with open(origen_svg, encoding="utf-8") as f:
        svg = f.read().replace('fill="currentColor"', f'fill="{color}"')
    with open(destino, "w", encoding="utf-8") as f:
        f.write(svg)
    return destino


# ── specs ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def escribir_specs(proyecto, composicion, props, total, salidas, fps=30, por_defecto="horizontal"):
    """Escribe remotion.<orientación>.json por cada entrada de `salidas` ({"vertical": "x-9x16.mp4", …}) y
    remotion.json = la orientación `por_defecto`. Devuelve {orientación: ruta}."""
    rutas = {}
    for orient, salida in salidas.items():
        spec = {"version": 1, "composicion": composicion, "salida": salida, "orientacion": orient,
                "fps": fps, "duracion": total, "props": props}
        rutas[orient] = os.path.join(proyecto, f"remotion.{orient}.json")
        with open(rutas[orient], "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=1)
    base = por_defecto if por_defecto in salidas else next(iter(salidas))
    with open(os.path.join(proyecto, "remotion.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "composicion": composicion, "salida": salidas[base], "orientacion": base,
                   "fps": fps, "duracion": total, "props": props}, f, ensure_ascii=False, indent=1)
    return rutas
