#!/usr/bin/env python3
"""sonido — audio del motor promo: música + efectos (SFX) + mezcla final.

Lee la línea de tiempo que escribe `node promo/motor.mjs validar`
(`recursos/promo/linea_tiempo.json`) y produce `recursos/audio/mezcla.wav`:

  1. Música (`audio.musica.tipo`):
     - `procedural` (v2, solo FFmpeg): cama "tech promo" en `musica.bpm` con kick suave en
       negras, hats a contratiempo, bajo en corcheas bombeado por el kick, pads cálidos con
       progresión Am–Fmaj7–C–G (un acorde por compás), arpegio tenue en el cuerpo, riser al
       final del intro y golpe suave + cola larga en el cierre. Se sintetiza por stems y se
       mezcla; es determinista (misma línea de tiempo → mismo WAV byte a byte).
     - `archivo`: pista del usuario (bucle si es corta), ventana elegida por energía si
       `inicio` es null, estéreo 48 kHz, fades 0.6 s / 1.9 s.
     - `ninguna`: cama de silencio (los SFX se mezclan igual).
  2. SFX: recetas `promo/sonidos/recetas.json` (aevalsrc), sintetizadas una vez en
     `recursos/audio/sfx/` y colocadas en `cues` con el pico (o el ataque) en el tiempo exacto.
  3. Mezcla, según el perfil:
     - solo_musica: música a -20 LUFS + SFX → limitador → loudnorm 2 pasadas (lineal) a
       -14 LUFS / -1.5 dBTP, duración exacta = `total`.
     - con voz (lt.voz con tomas de `promo.py voz`): voz -16 LUFS tras su cadena (highpass 80,
       +2.5 dB en 3 kHz, compresor 3:1) colocada en `en`; música a -24 LUFS con -6 dB en 2.5 kHz,
       ducking por sidechain (ratio 4) y compresor de bus 2:1; SFX nivelados contra la voz; mismo
       máster a -14 / -1.5. Verifica: voz ≥ 9 dB sobre la música atenuada y música ≥ -30 LUFS
       momentáneos en pausas y cola.
     - sin música (tipo ninguna, sin voz): los SFX quedan a su nivel (cama nominal de -20 LUFS) y
       solo se limitan a -1.5 dBTP; no se suben a -14 LUFS porque sonarían a golpes.
  Fuentes: música `procedural` | `archivo` | `cc0` (scripts/fetch_audio.py, cache primero,
  respaldo procedural) | `ninguna`; SFX `procedural` (recetas) | `cc0` (respaldo: la receta).

Uso:
  python3 scripts/sonido.py --linea-tiempo proyectos/<p>/recursos/promo/linea_tiempo.json \\
      --salida proyectos/<p>/recursos/audio/mezcla.wav [--repo <raíz>] [--tp -1.5]

Importado (así lo usa scripts/promo.py):
  from sonido import generar_audio
  res = generar_audio(lt_path, salida, repo)       # dict con I, TP, LRA, duracion…

Solo librería estándar + ffmpeg.
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

SR = 48000
SR_TONAL = 12000          # tasa de síntesis de los stems tonales (ver render_stem)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BITEXACT = ["-fflags", "+bitexact", "-flags:a", "+bitexact"]
FFMPEG = ["ffmpeg", "-y", "-v", "error", "-nostdin"]

# Tonalidad La menor, un acorde por compás. Voicings de pads en 110–440 Hz con conducción
# de voces por grado conjunto (así el cambio de acorde no "salta").
ACORDES = [
    # nombre, raíz del bajo (Hz), pads (Hz), arpegio (una octava arriba)
    ("Am",    55.00, (164.81, 220.00, 261.63, 329.63), (329.63, 440.00, 523.25, 659.25)),
    ("Fmaj7", 43.65, (174.61, 220.00, 261.63, 329.63), (349.23, 440.00, 523.25, 659.25)),
    ("C",     65.41, (164.81, 196.00, 261.63, 329.63), (329.63, 392.00, 523.25, 659.25)),
    ("G",     49.00, (146.83, 196.00, 246.94, 293.66), (293.66, 392.00, 493.88, 587.33)),
]
ACORDE_FINAL = (110.00, 164.81, 220.00, 246.94, 261.63, 329.63)   # Am(add9): resuelve en el cierre
PATRON_ARPEGIO = (0, 1, 2, 3, 1, 2, 3, 2)                          # 8 corcheas por compás

# Ganancias por stem (dB) antes de normalizar la cama a -20 LUFS. Calibradas midiendo la
# sonoridad K-ponderada de cada stem en el cuerpo (2026-09-28, 112 BPM), con objetivo relativo
# a los pads: bajo -2, kick -4 (marca sin retumbar), hats -13, arpegio -9 LU (textura), fx
# (riser/golpe) ~ -6 LU integrados con el pico momentáneo arriba al rematar.
GANANCIA_STEM = {"pads": 0.0, "bajo": 3.3, "kick": 7.8, "hats": 4.7, "arpegio": 0.0, "fx": 6.7}


def n(x):
    """Número con precisión fija para las expresiones (cadena estable → WAV determinista)."""
    return f"{x:.6f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


# ---------------------------------------------------------------- análisis de audio
def muestras_mono(path):
    """Muestras float32 mono (promedio de canales) vía ffmpeg → array('f')."""
    r = subprocess.run(FFMPEG[:-1] + ["-i", str(path), "-ac", "1", "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode(errors="replace")[-800:], file=sys.stderr)
        raise SystemExit(1)
    a = array("f")
    a.frombytes(r.stdout)
    return a


def momentanea_max(path):
    """Sonoridad momentánea máxima (LUFS, ventana 400 ms) de un archivo corto."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af",
                        "apad=pad_dur=0.5,ebur128=metadata=1,"
                        "ametadata=print:key=lavfi.r128.M:file=-", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    vals = [float(v) for v in re.findall(r"lavfi\.r128\.M=(-?[\d.]+)", r.stdout)]
    return max(vals) if vals else -70.0


def normalizar_ganancia(entrada, salida, lufs):
    """Lleva `entrada` a `lufs` con una ganancia pura (volume): conserva la dinámica tal cual."""
    m = comun.ebur128(entrada)
    if m["I"] <= -60:                       # silencio: no hay nada que normalizar
        shutil.copyfile(entrada, salida)
        return m
    comun.run(FFMPEG + ["-i", entrada, "-af", f"volume={lufs - m['I']:.4f}dB",
                        "-c:a", "pcm_f32le"] + BITEXACT + [salida])
    return m


# ---------------------------------------------------------------- plan musical
def _secciones(lt, total, bar):
    """(fin del intro, inicio del cierre) desde lt.musica.secciones, lt.escenas o proporciones."""
    secs = []
    for s in (lt.get("musica") or {}).get("secciones") or []:
        try:
            secs.append((max(0.0, float(s[0])), min(total, float(s[1])), str(s[2])))
        except (IndexError, TypeError, ValueError):
            continue
    if not secs:
        for e in lt.get("escenas") or []:
            if e.get("tipo") in ("intro", "cierre"):
                secs.append((float(e.get("ini", 0)), float(e.get("fin", total)), e["tipo"]))
    intros = [s for s in secs if s[2] == "intro"]
    cierres = [s for s in secs if s[2] == "cierre"]
    intro_fin = intros[0][1] if intros else (0.0 if secs else min(bar, 0.15 * total))
    cierre_ini = cierres[-1][0] if cierres else (total if secs else
                                                  total - min(max(2.5, 0.12 * total), 0.3 * total))
    return max(0.0, min(intro_fin, total)), max(intro_fin, min(cierre_ini, total))


def plan_musical(lt, bpm):
    """Tiempos clave de la cama. La rejilla arranca en el inicio del cuerpo (el 'drop').

    Anclar el compás al corte de escena hace que el primer kick caiga justo en el cambio
    de pantalla; todo lo rítmico se prende/apaga en límites de pulso, donde las envolventes
    valen ~0, así que no hay clics aunque las compuertas sean duras.
    """
    total = float(lt["total"])
    B = 60.0 / bpm
    BAR = 4 * B
    intro_fin, cierre_ini = _secciones(lt, total, BAR)
    g0 = intro_fin
    hay_cuerpo = (cierre_ini - g0) >= B
    cs = min(total, g0 + round((cierre_ini - g0) / B) * B) if hay_cuerpo else g0
    resto = total - cs
    if hay_cuerpo and resto >= BAR + 1.5:
        th = cs + BAR                      # un compás de kick en el cierre y luego el golpe
    elif resto >= 0.5:
        th = cs
    else:
        th = None
    kend = th if th is not None else cs
    gp = g0 + 2 * BAR if (cs - g0) >= 4 * BAR else g0      # arpegio y hats 16avos: 2o bloque
    riser = min(2 * BAR, intro_fin) if hay_cuerpo else 0.0
    crash = min(BAR, th - g0) if (th is not None and hay_cuerpo) else 0.0
    fade_out = min(4.0, max(1.9, total - th - 0.2)) if th is not None else 1.9
    return {"total": total, "bpm": bpm, "B": B, "BAR": BAR, "g0": g0, "cs": cs, "th": th,
            "kend": kend, "gp": gp, "hay_cuerpo": hay_cuerpo, "riser": riser if riser >= 0.5 else 0.0,
            "crash": crash if crash >= 0.4 else 0.0, "fade_in": 0.8,
            "fade_out": min(fade_out, total / 2), "intro_fin": intro_fin, "cierre_ini": cierre_ini}


# ---------------------------------------------------------------- expresiones de stems
def _semilla(var_flag, var_estado, valor):
    """Siembra el ruido de random(var_estado) una sola vez (var_flag marca que ya se hizo)."""
    return f"if(ld({var_flag}),0,st({var_estado},{valor})+st({var_flag},1))"


def expr_kick(p):
    """Seno con envolvente de tono 150→50 Hz. Fase integrada de f(t)=f1+(f0-f1)e^(-kt):
    φ = 2π(f1·t + (f0-f1)/k·(1-e^(-kt))). Caída rápida (no retumba) y release al final del pulso."""
    G, B = n(p["g0"]), n(p["B"])
    return (f"if(between(t,{G},{n(p['kend'])}),st(1,mod(t-{G},{B}));"
            f"sin(2*PI*(50*ld(1)+100/32*(1-exp(-32*ld(1)))))*exp(-12*ld(1))"
            f"*clip(({B}-ld(1))/0.012,0,1),0)")


def expr_hats(p, semilla):
    """Hats cerrados a contratiempo (ruido blanco determinista, envolvente corta) y, desde el
    2o bloque del cuerpo, 16avos fantasma muy suaves. Un canal por semilla (estéreo abierto)."""
    G, B = n(p["g0"]), p["B"]
    return (f"{_semilla(8, 9, semilla)};if(between(t,{G},{n(p['cs'])}),st(1,random(9)*2-1);"
            f"st(2,mod(t-{G}-{n(B / 2)},{n(B)}));st(3,mod(t-{G},{n(B / 4)}));"
            f"ld(1)*(exp(-55*ld(2))+if(gte(t,{n(p['gp'])}),0.3*exp(-90*ld(3)),0)),0)")


def expr_bajo(p):
    """Bajo en corcheas sobre la raíz del acorde, con 2o y 3er armónico (se oye en teléfonos)
    y bombeo por el kick (1-0.8·e^(-9·t_pulso)). Cada nota abre y cierra en 0, así que el
    cambio de frecuencia en la barra de compás no hace clic."""
    G, B, BAR = n(p["g0"]), p["B"], n(p["BAR"])
    r = [a[1] for a in ACORDES]
    raiz = f"if(eq(ld(2),0),{r[0]},if(eq(ld(2),1),{r[1]},if(eq(ld(2),2),{r[2]},{r[3]})))"
    return (f"if(between(t,{G},{n(p['cs'])}),st(1,mod(t-{G},{n(B / 2)}));"
            f"st(2,mod(floor((t-{G})/{BAR}),4));st(3,{raiz});st(4,2*PI*ld(3)*(t-{G}));"
            f"(sin(ld(4))+0.5*sin(2*ld(4))+0.22*sin(3*ld(4)))*(1-exp(-ld(1)/0.004))"
            f"*exp(-2.5*ld(1))*clip(({n(B / 2)}-ld(1))/0.012,0,1)*(1-0.8*exp(-9*mod(t-{G},{n(B)}))),0)")


def _tono_pad(freqs, detune, amps=(0.85, 1.0, 0.95, 0.75)):
    """Suma de notas con 3 armónicos (1, 0.4, 0.15): cálido, sin brillo de sierra."""
    partes = []
    for f, a in zip(freqs, list(amps) + [0.8] * (len(freqs) - len(amps))):
        for h, w in ((1, 1.0), (2, 0.4), (3, 0.15)):
            partes.append(f"{n(round(a * w, 4))}*sin(2*PI*{n(round(f * h * detune, 4))}*t)")
    return "(" + "+".join(partes) + ")"


def _bombeo_pads(p):
    """Bombeo tipo sidechain mientras hay kick: 1-0.55·ataque(4 ms)·caída que vuelve
    EXACTAMENTE a 1 al final del pulso (sin escalón de ganancia en cada kick = sin clic)."""
    G, B = n(p["g0"]), p["B"]
    e6 = math.exp(-6 * B)
    return (f"if(between(t,{G},{n(p['kend'])}),st(3,mod(t-{G},{n(B)}));"
            f"1-0.55*(1-exp(-ld(3)/0.004))*(exp(-6*ld(3))-{n(e6)})/{n(1 - e6)},1)")


def expr_pad_acorde(p, k, detune):
    """Acorde k de la progresión (se repite cada 4 compases). Ventana de cruce sen/cos
    (potencia constante) centrada en la barra de compás con el acorde vecino; tras el golpe
    del cierre se apaga en 0.25 s para dar paso al acorde final."""
    G, BAR, R = p["g0"], p["BAR"], 0.3
    pads = ACORDES[k][2]
    env = (f"if(lt(ld(2),{n(R)}),sin(PI/2*ld(2)/{n(R)}),if(lt(ld(2),{n(BAR)}),1,"
           f"cos(PI/2*(ld(2)-{n(BAR)})/{n(R)})))")
    fin = f"*(1-clip((t-{n(p['th'])})/0.25,0,1))" if p["th"] is not None else ""
    return (f"st(2,mod(t-{n(G)}+{n(R / 2 - k * BAR)},{n(4 * BAR)}));"
            f"if(lt(ld(2),{n(BAR + R)}),{env}*{_tono_pad(pads, detune)}*{_bombeo_pads(p)}{fin},0)")


def expr_pad_final(p, detune):
    """Acorde final Am(add9) desde el golpe del cierre: resuelve la progresión en la tónica."""
    TH = n(p["th"])
    return (f"if(gte(t,{TH}),st(4,t-{TH});clip(ld(4)/0.02,0,1)*(0.6+0.4*exp(-0.8*ld(4)))*0.8*"
            f"{_tono_pad(ACORDE_FINAL, detune, (0.7, 0.85, 1.0, 0.6, 0.8, 0.7))},0)")


def expr_arpegio(p):
    """Pluck tenue en corcheas sobre tonos del acorde (octava arriba), solo en el cuerpo.

    Timbre de cuerda pulsada: armónicos 1..6 con amplitud 1/h y caída más rápida mientras
    más agudos (brilla en el ataque y se oscurece). Aporta la presencia de 2–6 kHz que
    pads (pasabajos 1800 Hz) y bajo no tienen; sin ella la cama suena opaca."""
    G, B, BAR = n(p["g0"]), p["B"], p["BAR"]
    timbre = "+".join(f"{n(round(1 / h, 4))}*sin(2*PI*{h}*ld(4)*ld(1))*exp(-{10 + 6 * h}*ld(1))"
                      for h in range(1, 7))
    sel = []
    for _, _, _, arp in ACORDES:
        s = str(arp[PATRON_ARPEGIO[-1]])
        for paso in range(len(PATRON_ARPEGIO) - 2, -1, -1):
            s = f"if(eq(ld(3),{paso}),{arp[PATRON_ARPEGIO[paso]]},{s})"
        sel.append(s)
    freq = f"if(eq(ld(2),0),{sel[0]},if(eq(ld(2),1),{sel[1]},if(eq(ld(2),2),{sel[2]},{sel[3]})))"
    return (f"if(between(t,{n(p['gp'])},{n(p['cs'])}),st(1,mod(t-{G},{n(B / 2)}));"
            f"st(2,mod(floor((t-{G})/{n(BAR)}),4));st(3,floor(mod(t-{G},{n(BAR)})/{n(B / 2)}));"
            f"st(4,{freq});({timbre})"
            f"*(1-exp(-ld(1)/0.0015))*clip(({n(B / 2)}-ld(1))/0.01,0,1),0)")


def expr_fx(p, semilla):
    """Riser del intro (ruido con barrido de banda que remata en el drop), crash invertido
    hacia el golpe del cierre y golpe suave (bombo grave 95→40 Hz + lavado de ruido que se
    oscurece). Los barridos son pasabajos de un polo con coeficiente variable (st/ld)."""
    partes = [_semilla(8, 9, semilla)]
    G = p["g0"]
    if p["riser"]:
        A, D = G - p["riser"], p["riser"]
        partes.append(
            f"if(between(t,{n(A)},{n(G)}),st(1,random(9)*2-1);st(5,(t-{n(A)})/{n(D)});"
            f"st(6,1-exp(-2*PI*350*pow(20,ld(5))/{SR}));st(7,1-exp(-2*PI*120*pow(20,ld(5))/{SR}));"
            f"st(2,ld(2)+ld(6)*(ld(1)-ld(2)));st(3,ld(3)+ld(7)*(ld(1)-ld(3)));"
            f"(ld(2)-ld(3))*pow(ld(5),2.2)*clip(({n(G)}-t)/0.03,0,1),0)")
    if p["th"] is not None:
        TH = p["th"]
        if p["crash"]:
            A, D = TH - p["crash"], p["crash"]
            a_hi, a_lo = 1 - math.exp(-2 * math.pi * 12000 / SR), 1 - math.exp(-2 * math.pi * 2500 / SR)
            partes.append(
                f"if(between(t,{n(A)},{n(TH)}),st(1,random(9)*2-1);st(5,(t-{n(A)})/{n(D)});"
                f"st(2,ld(2)+{n(a_hi)}*(ld(1)-ld(2)));st(3,ld(3)+{n(a_lo)}*(ld(1)-ld(3)));"
                f"0.8*(ld(2)-ld(3))*pow(ld(5),3)*clip(({n(TH)}-t)/0.008,0,1),0)")
        partes.append(
            f"if(gte(t,{n(TH)}),st(4,t-{n(TH)});st(1,random(9)*2-1);"
            f"st(6,1-exp(-2*PI*(800+5200*exp(-3*ld(4)))/{SR}));st(2,ld(2)+ld(6)*(ld(1)-ld(2)));"
            f"(1-exp(-ld(4)/0.002))*(0.55*sin(2*PI*(40*ld(4)+55/18*(1-exp(-18*ld(4)))))*exp(-3.2*ld(4))"
            f"+0.5*ld(2)*exp(-2.2*ld(4))),0)")
    if len(partes) == 1:
        return "0"
    # La siembra devuelve 0; el resto se suma. `;` evalúa en orden y devuelve lo último.
    return partes[0] + ";" + "+".join(partes[1:])


def stems_procedurales(p, semilla):
    """Lista de stems: nombre, expresiones por canal y cadena de filtros (estéreo al final)."""
    B_ms = p["B"] * 1000
    mono = "pan=stereo|c0=c0|c1=c0"
    s = semilla * 7919 + 101
    # Pads: sin lodo en 150–300 Hz (ese rango es del bajo) y cálidos arriba (pasabajos 1800 Hz).
    pad = "highpass=f=110,lowshelf=f=260:g=-3,lowpass=f=1800,aecho=0.9:0.9:120|190:0.18|0.12"
    # Los pads se parten por acorde para sintetizarlos en paralelo (son el 90 % del costo).
    stems = [{"nombre": f"pads{k}", "grupo": "pads", "sr": SR_TONAL, "cadena": pad,
              "exprs": [expr_pad_acorde(p, k, 1 - 0.0018), expr_pad_acorde(p, k, 1 + 0.0018)]}
             for k in range(len(ACORDES))]
    if p["th"] is not None:
        stems.append({"nombre": "pads_final", "grupo": "pads", "sr": SR_TONAL, "cadena": pad,
                      "exprs": [expr_pad_final(p, 1 - 0.0018), expr_pad_final(p, 1 + 0.0018)]})
    if p["hay_cuerpo"]:
        stems += [
            {"nombre": "kick", "sr": SR_TONAL, "exprs": [expr_kick(p)], "cadena": f"highpass=f=40,{mono}"},
            {"nombre": "hats", "sr": SR, "exprs": [expr_hats(p, s + 1), expr_hats(p, s + 2)],
             "cadena": "highpass=f=6500:p=2,lowpass=f=14000"},
            {"nombre": "bajo", "sr": SR_TONAL, "exprs": [expr_bajo(p)], "cadena": f"lowpass=f=420,{mono}"},
            {"nombre": "arpegio", "sr": SR_TONAL, "exprs": [expr_arpegio(p)],
             "cadena": f"lowpass=f=6000,{mono},aecho=0.9:0.9:{B_ms * 0.75:.1f}|{B_ms * 1.5:.1f}:0.32|0.16"},
        ]
    if p["riser"] or p["th"] is not None:
        stems.append({"nombre": "fx", "sr": SR, "exprs": [expr_fx(p, s + 3), expr_fx(p, s + 4)],
                      "cadena": "highpass=f=35"})
    return stems


def render_stem(stem, duracion, carpeta):
    """Sintetiza un stem. Los tonales se evalúan a 12 kHz y se remuestrean a 48 kHz: su
    contenido queda bajo 1.4 kHz (Nyquist 6 kHz) y aevalsrc interpreta la expresión muestra
    por muestra, así que evaluar 4 veces menos muestras es 4 veces más rápido sin cambio audible."""
    salida = os.path.join(carpeta, f"{stem['nombre']}.wav")
    sr = stem.get("sr", SR)
    fuente = f"aevalsrc=exprs='{'|'.join(stem['exprs'])}':s={sr}:d={n(duracion)}"
    remuestreo = f"aresample={SR}," if sr != SR else ""
    comun.run(FFMPEG + ["-f", "lavfi", "-i", fuente, "-af",
                        remuestreo + stem["cadena"] + ",aformat=sample_fmts=flt:channel_layouts=stereo",
                        "-c:a", "pcm_f32le"] + BITEXACT + [salida])
    return salida


def musica_procedural(lt, bpm, carpeta, lufs, semilla):
    """Sintetiza los stems en paralelo, los mezcla con sus ganancias y normaliza a `lufs`."""
    p = plan_musical(lt, bpm)
    stems_dir = os.path.join(carpeta, "stems")
    os.makedirs(stems_dir, exist_ok=True)
    stems = stems_procedurales(p, semilla)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        rutas = list(ex.map(lambda s: render_stem(s, p["total"], stems_dir), stems))
    N = round(p["total"] * SR)
    ins, filt = [], []
    for i, (s, r) in enumerate(zip(stems, rutas)):
        ins += ["-i", r]
        filt.append(f"[{i}:a]volume={GANANCIA_STEM.get(s.get('grupo', s['nombre']), 0.0)}dB[s{i}]")
    fo = p["fade_out"]
    filt.append("".join(f"[s{i}]" for i in range(len(stems))) +
                f"amix=inputs={len(stems)}:normalize=0,"
                f"afade=t=in:st=0:d={p['fade_in']}:curve=qsin,"
                f"afade=t=out:st={p['total'] - fo:.4f}:d={fo:.4f}:curve=qsin,"
                f"apad=whole_len={N},atrim=end_sample={N}[cama]")
    cruda = os.path.join(carpeta, "musica_cruda.wav")
    comun.run(FFMPEG + ins + ["-filter_complex", ";".join(filt), "-map", "[cama]",
                              "-c:a", "pcm_f32le"] + BITEXACT + [cruda])
    salida = os.path.join(carpeta, "musica.wav")
    normalizar_ganancia(cruda, salida, lufs)
    desc = (f"procedural {bpm:g} BPM · intro 0–{p['g0']:.2f} · cuerpo {p['g0']:.2f}–{p['cs']:.2f}"
            + (f" · golpe {p['th']:.2f}" if p["th"] is not None else ""))
    return salida, desc


# ---------------------------------------------------------------- música desde archivo
def perfil_energia(archivo):
    """RMS por segundo (dB). `asetnsamples=n=48000` fija la ventana de astats en 1 s
    (sin él astats reporta por frame y el perfil no sirve; ver Lecciones reel-fluke-post §3)."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-v", "error", "-i", str(archivo), "-af",
                        "aresample=48000,aformat=channel_layouts=stereo,asetnsamples=n=48000,"
                        "astats=metadata=1:reset=1,"
                        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    vals = []
    for v in re.findall(r"lavfi\.astats\.Overall\.RMS_level=(\S+)", r.stdout):
        try:
            vals.append(max(-100.0, float(v)))
        except ValueError:                 # '-inf' o 'nan' = segundo en silencio
            vals.append(-100.0)
    return vals


def elegir_ventana(perfil, total):
    """Inicio (s) de la ventana de `total` s con más energía media y buen arranque.

    Puntaje = media − castigo por huecos (rango > 8 dB dentro de la ventana) − castigo si los
    2 primeros segundos quedan > 4 dB por debajo de la media (arrancar en silencio o en una
    intro floja se oye como audio cortado). Entre ventanas casi empatadas (≤ 0.25 dB) gana la
    más temprana: suele coincidir con el inicio de la sección fuerte, un límite de frase.
    """
    return mejor_ventana(perfil, total)[0]


def mejor_ventana(perfil, total):
    """(inicio, puntaje) de la mejor ventana (ver elegir_ventana). Pista corta: (0, media)."""
    L = max(1, math.ceil(total))
    if len(perfil) <= L:
        return 0.0, (sum(perfil) / len(perfil) if perfil else -100.0)
    puntajes = []
    for s in range(0, len(perfil) - L + 1):
        w = perfil[s:s + L]
        media = sum(w) / L
        huecos = max(0.0, (max(w) - min(w)) - 8.0)
        arranque = sum(w[:2]) / min(2, L)
        puntajes.append(media - 0.5 * huecos - max(0.0, (media - 4.0) - arranque))
    mejor = max(puntajes)
    inicio = next(s for s, p in enumerate(puntajes) if p >= mejor - 0.25)
    return float(inicio), puntajes[inicio]


def musica_archivo(m, total, carpeta, repo, lufs):
    """Cama desde una pista (copiado y adaptado de reel.py `musica_archivo`)."""
    archivo = m.get("archivo") or ""
    if not os.path.isabs(archivo):
        archivo = os.path.join(repo, archivo)
    if not os.path.exists(archivo):
        print(f"musica.archivo no existe: {archivo}", file=sys.stderr)
        raise SystemExit(2)
    largo = comun.dur(archivo)
    if m.get("inicio") is None:
        inicio = elegir_ventana(perfil_energia(archivo), total) if largo > total else 0.0
        origen = "ventana por energía"
    else:
        inicio = float(m["inicio"])
        origen = "inicio fijo"
    fi, fo = float(m.get("fade_in", 0.6)), float(m.get("fade_out", 1.9))
    bucle = ["-stream_loop", "-1"] if (largo - inicio) < total else []
    N = round(total * SR)
    cruda = os.path.join(carpeta, "musica_cruda.wav")
    comun.run(FFMPEG + bucle + ["-i", archivo, "-af",
              (f"atrim=start={inicio:.3f},asetpts=N/SR/TB,aformat=channel_layouts=stereo,"
               f"aresample={SR},atrim=end_sample={N},apad=whole_len={N},"
               f"afade=t=in:st=0:d={fi},afade=t=out:st={max(0.0, total - fo):.3f}:d={fo}"),
              "-c:a", "pcm_f32le"] + BITEXACT + [cruda])
    salida = os.path.join(carpeta, "musica.wav")
    normalizar_ganancia(cruda, salida, lufs)
    return salida, f"archivo {os.path.basename(archivo)} desde {inicio:.1f} s ({origen})"


def musica_silencio(total, carpeta):
    salida = os.path.join(carpeta, "musica.wav")
    comun.run(FFMPEG + ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-af",
                        f"atrim=end_sample={round(total * SR)}", "-c:a", "pcm_f32le"] + BITEXACT + [salida])
    return salida, "sin música"


# Una función por fuente de música: (audio.musica, ctx) → (musica.wav normalizada, descripción).
def musica_de_procedural(m, ctx):
    return musica_procedural(ctx["lt"], ctx["bpm"], ctx["carpeta"], ctx["lufs_musica"], ctx["semilla"])


def musica_de_archivo(m, ctx):
    return musica_archivo(m, ctx["total"], ctx["carpeta"], ctx["repo"], ctx["lufs_musica"])


def musica_de_ninguna(m, ctx):
    return musica_silencio(ctx["total"], ctx["carpeta"])


# ---------------------------------------------------------------- CC0 (scripts/fetch_audio.py)
CC0_BUSQUEDA_MUSICA = "corporate technology"
# Una búsqueda sin resultados se recuerda 24 h (Openverse anónimo ≈100 req/día): no se repite en
# cada render, pero tampoco se abandona para siempre. `--refrescar-cc0` reintenta ya.
CC0_REINTENTO_S = 24 * 3600
# Consultas por tipo de cue (docs/Audio-CC0.md § Uso desde el motor promo).
CC0_CONSULTAS_SFX = {"pop": "pop", "tick": "ui click", "whoosh": "whoosh transition",
                     "ping": "notification chime", "notif": "notification chime", "exito": "success chime",
                     "revelar": "riser", "tecleo": "keyboard typing"}


def _obtener_cc0(query, n, perfil, **kw):
    """Única puerta a fetch_audio (cache primero; Openverse anónimo ≈100 req/día).
    Las pruebas la sustituyen. Devuelve [] ante red caída o config inválida."""
    import fetch_audio
    try:
        return fetch_audio.obtener(query, n=n, perfil=perfil, **kw)
    except (fetch_audio.ErrorRed, fetch_audio.ErrorConfig) as e:
        print(f"AVISO CC0: {str(e)[:120]}", file=sys.stderr)
        return []


def _dir_cc0(ctx):
    d = os.path.join(ctx["carpeta"], "cc0")
    os.makedirs(d, exist_ok=True)
    return d


def _seleccion(ctx, clave=None, valor=None):
    """recursos/audio/cc0/seleccion.json: lo ya elegido no vuelve a consultar ni a analizar."""
    ruta = os.path.join(_dir_cc0(ctx), "seleccion.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        datos = {}
    if clave is None:
        return datos
    datos[clave] = valor
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    return datos


def _respaldo_vigente(ctx, previo, q):
    """True si esa búsqueda ya dio vacío hace menos de 24 h (y no se pidió refrescar)."""
    return (previo.get("busqueda") == q and previo.get("respaldo") and not ctx.get("refrescar_cc0")
            and time.time() - float(previo.get("ts", 0)) < CC0_REINTENTO_S)


def _respaldo(q):
    return {"busqueda": q, "respaldo": True, "ts": round(time.time())}


def _credito(ctx, uso, item, local):
    ctx["creditos"].append({"uso": uso, "archivo": os.path.basename(local),
                            **{k: item.get(k) for k in ("titulo", "autor", "licencia", "origen_url", "sha256")}})


def _copiar_local(ctx, item):
    """Copia el archivo del stock compartido a recursos/audio/cc0/ (el proyecto queda autocontenido)."""
    local = os.path.join(_dir_cc0(ctx), os.path.basename(item["ruta"]))
    if not os.path.exists(local):
        shutil.copyfile(item["ruta"], local)
    return local


def musica_de_cc0(m, ctx):
    """Pista/loop CC0: `obtener(busqueda, perfil="bgm")`; si nada cubre la duración, loops cortos
    (perfil any, ≥ 4 s) que se repiten. Entre candidatos gana el de mejor ventana de energía.
    Sin CC0 → cama procedural con un aviso en la línea de música."""
    q = m.get("busqueda") or CC0_BUSQUEDA_MUSICA
    total = ctx["total"]
    previo = _seleccion(ctx).get("musica") or {}
    local = os.path.join(_dir_cc0(ctx), os.path.basename(previo.get("local") or "_")) if previo.get("local") else None
    if previo.get("busqueda") == q and local and os.path.exists(local):
        item, inicio = previo["item"], previo["inicio"]    # 0 peticiones
    else:
        items = []
        if not _respaldo_vigente(ctx, previo, q):          # vacío reciente: no gastar cupo
            items = _obtener_cc0(q, 3, "bgm") or _obtener_cc0(q, 3, "any", min_dur=4.0)
            items = [it for it in items if it.get("ruta") and os.path.exists(it["ruta"])]
            if not items:
                _seleccion(ctx, "musica", _respaldo(q))
        if not items:
            ruta, desc = musica_de_procedural(m, ctx)
            return ruta, f"{desc} (AVISO sin CC0 para «{q}»: respaldo procedural)"
        mejor = None
        for it in items:
            largo = comun.dur(it["ruta"])
            perfil = perfil_energia(it["ruta"])
            # Una pista larga compite por su mejor ventana; un loop corto, por su media (-1 dB:
            # repetir se nota más que una pista continua).
            ini, puntaje = mejor_ventana(perfil, total) if largo > total else (0.0, mejor_ventana(perfil, largo)[1] - 1.0)
            if mejor is None or puntaje > mejor[0]:
                mejor = (puntaje, it, ini)
        _, item, inicio = mejor
        local = _copiar_local(ctx, item)
        _seleccion(ctx, "musica", {"busqueda": q, "item": item, "local": os.path.basename(local), "inicio": inicio})
    _credito(ctx, "musica", item, local)
    ruta, desc = musica_archivo({"archivo": local, "inicio": inicio}, total, ctx["carpeta"], ctx["repo"],
                                ctx["lufs_musica"])
    return ruta, desc.replace("archivo ", "cc0 ", 1).replace("(inicio fijo)", f"(«{q}»)")


FUENTES_MUSICA = {"procedural": musica_de_procedural, "archivo": musica_de_archivo,
                  "cc0": musica_de_cc0, "ninguna": musica_de_ninguna}


# ---------------------------------------------------------------- SFX
# Una función por fuente de efectos: nombre → info {ruta, pico, ataque, M, ancla} o None si la
# fuente no tiene ese efecto. Todas dejan un WAV estéreo float 48 kHz y lo pasan por
# analizar_sfx, así el bus coloca y nivela igual venga de donde venga.
def cargar_recetas(repo):
    with open(os.path.join(repo, "promo", "sonidos", "recetas.json"), encoding="utf-8") as f:
        return json.load(f)


def analizar_sfx(wav, ancla="pico", extra=None):
    """Mide el instante del pico, el del ataque (1er cruce del 50 % del pico) y la sonoridad
    momentánea máxima. La guía lo pide: medir dónde cae el pico para que suene justo en el cuadro."""
    absx = [abs(v) for v in muestras_mono(wav)]
    pico_v = max(absx) if absx else 0.0
    i_pico = absx.index(pico_v) if absx else 0
    i_ataque = next((i for i, v in enumerate(absx) if v >= 0.5 * pico_v), i_pico)
    info = {"ruta": wav, "pico": i_pico / SR, "ataque": i_ataque / SR, "M": momentanea_max(wav),
            "ancla": ancla}
    info.update(extra or {})
    return info


def sfx_receta(nombre, ctx):
    """Fuente `recetas`: sintetiza la receta de promo/sonidos/recetas.json (caché por hash)."""
    receta = (ctx["recetas"].get("recetas") or {}).get(nombre)
    if receta is None:
        return None
    carpeta = ctx["sfx_dir"]
    os.makedirs(carpeta, exist_ok=True)
    wav = os.path.join(carpeta, f"{nombre}.wav")
    meta = os.path.join(carpeta, f"{nombre}.json")
    firma = hashlib.sha1(json.dumps(receta, sort_keys=True).encode()).hexdigest()[:12]
    if os.path.exists(wav) and os.path.exists(meta):
        with open(meta, encoding="utf-8") as f:
            info = json.load(f)
        if info.get("firma") == firma:
            info["ruta"] = wav          # la caché sobrevive a mover/copiar la carpeta del proyecto
            return info
    d = max(0.25, float(receta.get("d", 0.5)))
    cadena = ",".join(x for x in (receta.get("filtros"), "pan=stereo|c0=c0|c1=c0",
                                  "aformat=sample_fmts=flt:channel_layouts=stereo") if x)
    comun.run(FFMPEG + ["-f", "lavfi", "-i", f"aevalsrc=exprs='{receta['expr']}':s={SR}:d={d}",
                        "-af", cadena, "-c:a", "pcm_f32le"] + BITEXACT + [wav])
    info = analizar_sfx(wav, receta.get("ancla", "pico"), {"firma": firma, "d": d, "fuente": "recetas"})
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    return info


def _cresta_db(wav):
    """Pico − RMS (dB) de todo el efecto: > 6 dB = transitorio claro (no un colchón plano)."""
    x = muestras_mono(wav)
    if not x:
        return 0.0, 0.0
    pico = max(abs(v) for v in x)
    rms = math.sqrt(sum(v * v for v in x) / len(x))
    if pico <= 1e-6 or rms <= 1e-9:
        return 0.0, 0.0
    return 20 * math.log10(pico / rms), len(x) / SR


def sfx_cc0(nombre, ctx):
    """Efecto CC0 por tipo de cue: el más corto con transitorio claro; si no hay, la receta."""
    q = CC0_CONSULTAS_SFX.get(nombre)
    receta = (ctx["recetas"].get("recetas") or {}).get(nombre) or {}
    if not q:
        return sfx_receta(nombre, ctx)
    clave = f"sfx:{nombre}"
    previo = _seleccion(ctx).get(clave) or {}
    if _respaldo_vigente(ctx, previo, q):
        ctx["avisos"].append(f"sin CC0 claro para '{nombre}' («{q}»): receta procedural")
        return sfx_receta(nombre, ctx)
    if previo.get("busqueda") == q and previo.get("info"):
        info = dict(previo["info"], ruta=os.path.join(_dir_cc0(ctx), f"sfx_{nombre}.wav"))
        if os.path.exists(info["ruta"]):
            _credito(ctx, clave, previo["item"], os.path.join(_dir_cc0(ctx), os.path.basename(previo["local"])))
            return info
    dir_cc0 = _dir_cc0(ctx)
    candidatos = []
    for it in _obtener_cc0(q, 3, "sfx"):
        if not (it.get("ruta") and os.path.exists(it["ruta"])):
            continue
        wav = os.path.join(dir_cc0, f"_prueba_{nombre}_{len(candidatos)}.wav")
        comun.run(FFMPEG + ["-i", it["ruta"], "-af",
                            "aformat=sample_fmts=flt:channel_layouts=stereo,aresample=48000,atrim=duration=6,"
                            "afade=t=in:st=0:d=0.005,areverse,afade=t=in:st=0:d=0.05,areverse",
                            "-c:a", "pcm_f32le"] + BITEXACT + [wav])
        cresta, dur = _cresta_db(wav)
        if cresta >= 6.0 and dur >= 0.15:
            candidatos.append((dur, it, wav))
        else:
            os.remove(wav)
    if not candidatos:
        _seleccion(ctx, clave, _respaldo(q))
        ctx["avisos"].append(f"sin CC0 claro para '{nombre}' («{q}»): receta procedural")
        return sfx_receta(nombre, ctx)
    candidatos.sort(key=lambda c: c[0])
    _, item, wav = candidatos[0]
    for _, _, otro in candidatos[1:]:
        os.remove(otro)
    final = os.path.join(dir_cc0, f"sfx_{nombre}.wav")
    os.replace(wav, final)
    local = _copiar_local(ctx, item)
    info = analizar_sfx(final, receta.get("ancla", "pico"), {"fuente": "cc0", "busqueda": q})
    _seleccion(ctx, clave, {"busqueda": q, "item": item, "local": os.path.basename(local), "info": info})
    _credito(ctx, clave, item, local)
    return info


# "recetas" se acepta como alias de "procedural" (nombre anterior de la fuente).
FUENTES_SFX = {"procedural": sfx_receta, "recetas": sfx_receta, "cc0": sfx_cc0}


def bus_sfx(lt, ctx, N):
    """Coloca los cues con adelay (en muestras, todos los canales) y ganancia por modo y `g`.
    Devuelve (ruta|None, n cues usados, avisos)."""
    audio = lt.get("audio") or {}
    modo = audio.get("sfx", "sutil")
    cues = lt.get("cues") or []
    if modo == "ninguno" or not cues:
        return None, 0, []
    fuente = audio.get("sfx_fuente", "procedural")
    obtener = FUENTES_SFX.get(fuente)
    if obtener is None:
        print(f"audio.sfx_fuente desconocida '{fuente}' (usa: {', '.join(FUENTES_SFX)})", file=sys.stderr)
        raise SystemExit(2)
    niveles = ctx["recetas"].get("niveles") or {}
    nivel = float(niveles.get(modo, niveles.get("sutil", -11)))
    total = N / SR
    avisos, usados, info = [], [], {}
    for c in cues:
        nombre, en, g = c.get("s"), float(c.get("en", -1)), min(1.5, float(c.get("g", 1.0)))
        if not (0 <= en < total) or g <= 0:
            avisos.append(f"cue '{nombre}' en {en:.2f} s fuera de rango o g<=0 (se omite)")
            continue
        if nombre not in info:
            info[nombre] = obtener(nombre, ctx)
        if info[nombre] is None:
            avisos.append(f"cue desconocido '{nombre}' en {en:.2f} s (se omite)")
            continue
        usados.append((nombre, en, g))
    if not usados:
        return None, 0, avisos
    orden = sorted({u[0] for u in usados})
    ins, filt, tags = [], [], []
    for i, nm in enumerate(orden):
        ins += ["-i", info[nm]["ruta"]]
        k = sum(1 for u in usados if u[0] == nm)
        filt.append(f"[{i}:a]asplit={k}" + "".join(f"[{nm}{j}]" for j in range(k)))
    cuenta = dict.fromkeys(orden, 0)
    for idx, (nm, en, g) in enumerate(usados):
        inf = info[nm]
        ancla = inf["ataque"] if inf["ancla"] == "ataque" else inf["pico"]
        inicio = round((en - ancla) * SR)       # en muestras: alineación exacta, sin redondeo a ms
        recorte = max(0, -inicio)              # cue antes del ancla del efecto: se recorta la cabeza
        gan = ctx["ref_sfx"] + nivel - inf["M"] + 20 * math.log10(g)
        j = cuenta[nm]
        cuenta[nm] += 1
        filt.append(f"[{nm}{j}]atrim=start_sample={recorte},asetpts=PTS-STARTPTS,volume={gan:.3f}dB,"
                    f"adelay=delays={max(0, inicio)}S:all=1[c{idx}]")
        tags.append(f"[c{idx}]")
    filt.append("".join(tags) + f"amix=inputs={len(tags)}:normalize=0,"
                f"apad=whole_len={N},atrim=end_sample={N}[sfx]")
    salida = os.path.join(ctx["carpeta"], "sfx_bus.wav")
    comun.run(FFMPEG + ins + ["-filter_complex", ";".join(filt), "-map", "[sfx]",
                              "-c:a", "pcm_f32le"] + BITEXACT + [salida])
    return salida, len(usados), avisos


# ---------------------------------------------------------------- mezcla
def _sumar(entradas, salida, N):
    """amix sin normalizar (suma pura) de WAVs, con longitud exacta N."""
    if len(entradas) == 1:
        shutil.copyfile(entradas[0], salida)
        return salida
    ins = []
    for e in entradas:
        ins += ["-i", e]
    comun.run(FFMPEG + ins + ["-filter_complex",
                              "".join(f"[{i}:a]" for i in range(len(entradas))) +
                              f"amix=inputs={len(entradas)}:normalize=0,apad=whole_len={N},atrim=end_sample={N}[m]",
                              "-map", "[m]", "-c:a", "pcm_f32le"] + BITEXACT + [salida])
    return salida


def masterizar(pre, salida, N, lufs, tp, carpeta):
    """Premezcla → limitador → loudnorm 2 pasadas (lineal) a `lufs`/`tp`, N muestras exactas.

    El techo del limitador se fija para que la ganancia lineal de loudnorm deje el pico
    0.8 dB por debajo del TP objetivo (margen para picos entre muestras y para el AAC).
    Sin ese techo el modo lineal sería imposible: una cama a -20 LUFS con kick tiene
    ~13 dB de pico sobre sonoridad, y subirla a -14 LUFS rebasaría -1.5 dBTP.
    """
    m = comun.ebur128(pre)
    if m["I"] <= -60:                       # todo en silencio: nada que normalizar
        comun.run(FFMPEG + ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-af",
                            f"atrim=end_sample={N}", "-c:a", "pcm_s24le"] + BITEXACT + [salida])
        return {"normalization_type": "silencio"}
    # loudnorm solo aplica una ganancia lineal si (true peak − sonoridad) de su entrada ≤ TP − LUFS
    # objetivo; si no, recomprime (modo dinámico). Se limita hasta cumplirlo con 0.3 dB de margen,
    # medido con la primera pasada de loudnorm (su medidor difiere de ebur128 hasta 0.5 LU con voz):
    #  - el limitador trabaja a 192 kHz: con voz, los picos ENTRE muestras rebasaron 1.1 dB un techo
    #    por muestra (medido 2026-09-28) y loudnorm cayó a modo dinámico;
    #  - limitar también baja la sonoridad, así que la ganancia de entrada se ajusta por pasos
    #    (secante sobre el pico-sonoridad medido; tope +12 dB sobre la normalización inicial).
    ref = -20.0
    plr_obj = tp - lufs - 0.3
    techo = min(1.0, max(0.0625, 10 ** ((ref + plr_obj - 0.5) / 20)))
    total = N / SR
    lim = os.path.join(carpeta, "_limitada.wav")
    base = ref - m["I"]
    gan, historia = base, []
    for _ in range(6):
        comun.run(FFMPEG + ["-i", pre, "-af",
                            f"volume={gan:.4f}dB,aresample=192000,"
                            f"alimiter=limit={techo:.5f}:level=0:latency=1:attack=5:release=80:asc=1,"
                            f"aresample={SR},"
                            f"afade=t=in:st=0:d=0.01,afade=t=out:st={max(0.0, total - 0.35):.4f}:d=0.35,"
                            f"apad=whole_len={N},atrim=end_sample={N}",
                            "-c:a", "pcm_f32le"] + BITEXACT + [lim])
        ml = comun.medir_loudnorm(lim, lufs, tp)          # el mismo medidor que decide el modo
        plr = ml["input_tp"] - ml["input_i"]
        historia.append((gan, plr))
        if plr <= plr_obj or gan - base >= 12.0:
            break
        paso = 1.5 * (plr - plr_obj)
        if len(historia) >= 2:
            (g1, p1), (g2, p2) = historia[-2:]
            pendiente = (p2 - p1) / (g2 - g1) if g2 != g1 else 0.0
            if pendiente < -0.05:
                paso = (plr_obj - plr) / pendiente
        gan += min(max(paso, 0.3), 6.0) + 0.1
    ln = os.path.join(carpeta, "_loudnorm.wav")
    res = comun.loudnorm_2p(lim, ln, I=lufs, TP=tp, LRA=11.0, sr=SR, muestras=N)
    # loudnorm mide con su propio medidor a 192 kHz y puede quedar ~0.2 LU lejos de lo que
    # mide ebur128 (el de los checks). Un retoque de ganancia pura lo deja en el objetivo
    # siempre que el true peak conserve 0.3 dB de margen.
    med = comun.ebur128(ln)
    corr = lufs - med["I"]
    if 0.05 <= abs(corr) <= 1.0 and med["TP"] + corr <= tp - 0.3:
        comun.run(FFMPEG + ["-i", ln, "-af", f"volume={corr:.3f}dB", "-c:a", "pcm_s24le"]
                  + BITEXACT + [salida])
        os.remove(ln)
        res["retoque_db"] = round(corr, 2)
    else:
        os.replace(ln, salida)
    os.remove(lim)
    return res


def mezclar_solo_musica(musica, sfx, salida, N, lufs, tp, carpeta):
    """Perfil solo_musica: música (-20 LUFS) + SFX → masterizar a -14 LUFS / -1.5 dBTP."""
    pre = _sumar([musica] + ([sfx] if sfx else []), os.path.join(carpeta, "_premezcla.wav"), N)
    res = masterizar(pre, salida, N, lufs, tp, carpeta)
    os.remove(pre)
    return res


def mezclar_sin_musica(sfx, salida, N, tp, carpeta):
    """Sin música ni voz: los SFX quedan a su nivel respecto de una cama nominal de -20 LUFS y solo
    se limitan a `tp`. No se suben a -14 LUFS: una pista de puros efectos a -14 suena a golpes."""
    if not sfx:
        comun.run(FFMPEG + ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-af",
                            f"atrim=end_sample={N}", "-c:a", "pcm_s24le"] + BITEXACT + [salida])
        return {"normalization_type": "silencio"}
    techo = 10 ** ((tp - 0.5) / 20)          # pico de muestra 0.5 dB bajo el TP: margen entre muestras
    comun.run(FFMPEG + ["-i", sfx, "-af", f"alimiter=limit={techo:.5f}:level=0:latency=1:attack=2:release=60,"
                        f"apad=whole_len={N},atrim=end_sample={N}", "-c:a", "pcm_s24le"] + BITEXACT + [salida])
    return {"normalization_type": "sin_loudnorm"}


def bus_voz(lt, lt_path, carpeta, N, voz_lufs):
    """Cada toma a `voz_lufs` (ganancia medida), highpass 80 Hz, +2.5 dB en 3 kHz y compresor 3:1
    (makeup 2), colocada en su `en` con adelay en muestras. Devuelve (ruta del bus, líneas)."""
    rec = os.path.dirname(os.path.dirname(os.path.abspath(lt_path)))
    lineas = [l for l in (lt.get("voz") or {}).get("lineas") or [] if l.get("archivo")]
    ins, filt, tags = [], [], []
    for i, l in enumerate(lineas):
        wav = os.path.join(rec, l["archivo"])
        if not os.path.exists(wav):
            print(f"falta la toma {l['archivo']}: corre python3 scripts/promo.py voz", file=sys.stderr)
            raise SystemExit(2)
        m = comun.ebur128(wav)
        gan = (voz_lufs - m["I"]) if m["I"] > -60 else 0.0
        ins += ["-i", wav]
        filt.append(f"[{i}:a]aresample={SR},volume={gan:.3f}dB,highpass=f=80,"
                    f"equalizer=f=3000:t=q:w=1:g=2.5,acompressor=ratio=3:makeup=2,"
                    f"pan=stereo|c0=c0|c1=c0,adelay=delays={round(float(l['en']) * SR)}S:all=1[v{i}]")
        tags.append(f"[v{i}]")
    salida = os.path.join(carpeta, "voz_bus.wav")
    crudo = os.path.join(carpeta, "_voz_bus_crudo.wav")
    filt.append("".join(tags) + f"amix=inputs={len(tags)}:normalize=0,"
                f"apad=whole_len={N},atrim=end_sample={N}[voz]")
    comun.run(FFMPEG + ins + ["-filter_complex", ";".join(filt), "-map", "[voz]",
                              "-c:a", "pcm_f32le"] + BITEXACT + [crudo])
    # El EQ y el makeup del compresor suben la voz ~5 dB: se normaliza el bus YA procesado, así
    # `voz_lufs` es el nivel real de la voz frente a la música (la brecha define el LRA final).
    normalizar_ganancia(crudo, salida, voz_lufs)
    os.remove(crudo)
    return salida, lineas


# Ducking y compresor de bus del perfil con voz (afinados 2026-09-28 con tomas reales de
# gpt-audio-mini; ver docs/Musica-Libre-de-Derechos.md § Niveles de mezcla). El umbral 0.03
# (≈ -30 dBFS) queda muy por debajo de la voz normalizada, así que el ducking entra en TODAS las
# líneas, incluidas las sílabas suaves; ratio 4 → ~10 dB de atenuación bajo la voz.
DUCKING = {"threshold": 0.03, "ratio": 4, "attack": 20, "release": 600}
# Compresor de bus suave antes del máster: acerca las secciones con voz a las de solo música
# (baja el LRA) sin tocar la inteligibilidad; umbral ≈ -20 dBFS, entre la música y la voz.
COMP_BUS = "acompressor=threshold=0.1:ratio=2:attack=20:release=250:knee=4:makeup=1"


def mezclar_con_voz(musica, sfx, lt, lt_path, salida, N, lufs, tp, carpeta, voz_lufs=-16.0):
    """Perfil con voz: voz -16 LUFS (medida tras su EQ/compresor); música (ya a
    `musica_con_voz_lufs`, -24) con -6 dB en 2.5 kHz para no pelear con la voz, ducking
    sidechaincompress (DUCKING) y compresor de bus suave (COMP_BUS) antes del máster.

    Dos reglas verificadas (SKILL crear-video): `asplit` EXPLÍCITO del bus de voz (con el split
    implícito el sidechain atenúa también la voz, ~-11 dB medidos) y sidechain con apad: el filtro
    corta la pista principal cuando el sidechain termina (aquí, relleno infinito; ver abajo)."""
    voz, lineas = bus_voz(lt, lt_path, carpeta, N, voz_lufs)
    pre = os.path.join(carpeta, "_premezcla.wav")
    duck = os.path.join(carpeta, "musica_duck.wav")      # diagnóstico: la música ya atenuada
    ins = ["-i", voz, "-i", musica] + (["-i", sfx] if sfx else [])
    d = DUCKING
    # sidechaincompress pierde la cola de la pista principal aunque voz y música midan
    # exactamente N muestras (medido 2026-09-28: 47 360 muestras menos en 30 s, y aún 18 688 con
    # el sidechain rellenado). Se rellenan AMBAS entradas (sidechain infinito, principal +1 s) y
    # se recorta a N después: la música llega completa al fade final.
    grafo = ("[0:a]asplit=2[vmain][vsc0];[vsc0]apad[vsc];"
             "[1:a]equalizer=f=2500:t=q:w=1:g=-6,apad=pad_dur=1[meq];"
             f"[meq][vsc]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:"
             f"attack={d['attack']}:release={d['release']},atrim=end_sample={N},asplit=2[duck][duckdiag];"
             "[vmain][duck]" + ("[2:a]" if sfx else "") +
             f"amix=inputs={3 if sfx else 2}:normalize=0,{COMP_BUS},apad=whole_len={N},atrim=end_sample={N}[m]")
    comun.run(FFMPEG + ins + ["-filter_complex", grafo, "-map", "[m]", "-c:a", "pcm_f32le"] + BITEXACT + [pre,
              "-map", "[duckdiag]", "-c:a", "pcm_f32le"] + BITEXACT + [duck])
    res = masterizar(pre, salida, N, lufs, tp, carpeta)
    os.remove(pre)
    res["inteligibilidad"] = inteligibilidad(salida, voz, duck, lineas, N / SR)
    return res


def _volumen(wav, ini, dur):
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-ss", f"{ini:.3f}", "-t", f"{dur:.3f}", "-i", wav,
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)", r.stderr)
    return _db_txt(m.group(1)) if m else float("-inf")


def _db_txt(t):
    return float("-inf") if "inf" in t else float(t)


def _momentanea(wav):
    """[(t, M LUFS)] de ebur128 (ventana de 400 ms que termina en t)."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", wav, "-af",
                        "ebur128=metadata=1,ametadata=print:key=lavfi.r128.M:file=-", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return list(zip([float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stdout)],
                    [float(x) for x in re.findall(r"lavfi\.r128\.M=(-?[\d.]+)", r.stdout)]))


def inteligibilidad(final, voz_bus, musica_duck, lineas, total):
    """Criterios de la mezcla con voz (SKILL crear-video, afinados 2026-09-28):
      - margen: voz sobre la música YA atenuada bajo la línea más larga (volumedetect de cada bus) ≥ 9 dB;
      - pausa / cola: sonoridad momentánea mínima del final donde no hay voz ≥ -30 LUFS (la música
        debe seguir oyéndose; en la cola cuenta desde que termina la voz hasta 0.5 s antes del fin)."""
    tramos = sorted((float(l["en"]), float(l["en"]) + float(l.get("dur", 0))) for l in lineas)
    out = {}
    if not tramos:
        return {"avisos": []}
    a, b = max(tramos, key=lambda t: t[1] - t[0])
    out["margen"] = _volumen(voz_bus, a + 0.15, max(0.2, b - a - 0.25)) - _volumen(musica_duck, a + 0.15, max(0.2, b - a - 0.25))
    M = _momentanea(final)

    def minima(x, y):
        vals = [m for t, m in M if x + 0.45 <= t <= y]
        return min(vals) if vals else None
    huecos = [(tramos[i][1], tramos[i + 1][0]) for i in range(len(tramos) - 1) if tramos[i + 1][0] - tramos[i][1] >= 0.6]
    pausas = [v for v in (minima(x, y) for x, y in huecos) if v is not None]
    if pausas:
        out["pausa"] = min(pausas)
    if total - tramos[-1][1] >= 1.1:
        cola = minima(tramos[-1][1], total - 0.5)
        if cola is not None:
            out["cola"] = cola
    avisos = []
    if out["margen"] < 9:
        avisos.append(f"la voz solo queda {out['margen']:.1f} dB sobre la música (< 9)")
    if any(out.get(k, 0) < -30 for k in ("pausa", "cola")):
        avisos.append("la música casi no se oye sin voz (< -30 LUFS)")
    out["avisos"] = avisos
    return out


# ---------------------------------------------------------------- entrada principal
def generar_audio(lt_path, salida, repo=None, tp=None, imprimir=True, refrescar_cc0=False):
    """Genera la mezcla final de audio a partir de la línea de tiempo. Devuelve un dict.

    Perfiles: con voz (lt.voz con tomas) · solo_musica · sin música (tipo ninguna, sin voz:
    efectos a su nivel, sin subir a -14 LUFS)."""
    with open(lt_path, encoding="utf-8") as f:
        lt = json.load(f)
    repo = repo or REPO          # el toolkit que contiene este script (config y recetas)
    cfg = comun.cargar_config(repo).get("promo") or {}
    mez = cfg.get("mezcla") or {}
    lufs = float(mez.get("lufs", -14))
    tp = float(tp if tp is not None else mez.get("tp", -1.5))
    total = float(lt["total"])
    N = round(total * SR)
    audio = lt.get("audio") or {}
    con_voz = bool(audio.get("voz"))
    if con_voz and ((lt.get("voz") or {}).get("pendiente", True) or not (lt.get("voz") or {}).get("lineas")):
        print("la voz está pendiente: corre python3 scripts/promo.py voz <proyecto> y luego validar",
              file=sys.stderr)
        raise SystemExit(2)
    carpeta = os.path.dirname(os.path.abspath(salida))
    os.makedirs(carpeta, exist_ok=True)

    m = audio.get("musica") or {"tipo": "procedural"}
    tipo = m.get("tipo", "procedural")
    fuente = FUENTES_MUSICA.get(tipo)
    if fuente is None:
        print(f"audio.musica.tipo desconocido '{tipo}' (usa: {', '.join(FUENTES_MUSICA)})", file=sys.stderr)
        raise SystemExit(2)
    sola = float(mez.get("musica_sola_lufs", -20))
    voz_lufs = float(mez.get("voz_lufs", -16))
    ctx = {"lt": lt, "repo": repo, "carpeta": carpeta, "sfx_dir": os.path.join(carpeta, "sfx"),
           "total": total, "N": N, "semilla": int(lt.get("semilla", 7)),
           # Con voz la música baja a -24 LUFS y los SFX se nivelan contra la voz (-16);
           # sin voz, música y SFX se nivelan contra la cama de -20 LUFS.
           "lufs_musica": float(mez.get("musica_con_voz_lufs", -24)) if con_voz else sola,
           "ref_sfx": voz_lufs if con_voz else sola,
           "bpm": float((lt.get("musica") or {}).get("bpm") or m.get("bpm") or cfg.get("musica_bpm") or 112),
           "recetas": cargar_recetas(repo), "creditos": [], "avisos": [], "refrescar_cc0": refrescar_cc0}
    musica, desc = fuente(m, ctx)
    sfx, n_cues, avisos = bus_sfx(lt, ctx, N)
    avisos = ctx["avisos"] + avisos
    if con_voz:
        res = mezclar_con_voz(musica, sfx, lt, lt_path, salida, N, lufs, tp, carpeta, voz_lufs)
    elif tipo == "ninguna":
        res = mezclar_sin_musica(sfx, salida, N, tp, carpeta)
    else:
        res = mezclar_solo_musica(musica, sfx, salida, N, lufs, tp, carpeta)
    if ctx["creditos"]:
        with open(os.path.join(carpeta, "cc0", "creditos.json"), "w", encoding="utf-8") as f:
            json.dump(ctx["creditos"], f, ensure_ascii=False, indent=1)
    med = comun.ebur128(salida)
    duracion = comun.dur(salida)
    out = {"salida": salida, "duracion": duracion, "I": med["I"], "TP": med.get("TP"),
           "LRA": med.get("LRA"), "normalizacion": res.get("normalization_type"),
           "musica": desc, "cues": n_cues, "avisos": avisos, "creditos": ctx["creditos"],
           "inteligibilidad": res.get("inteligibilidad")}
    if imprimir:                     # ≤ 4 líneas: el orquestador paga por token
        modo = audio.get("sfx", "sutil")
        print(f"música: {desc}" + (f" → {ctx['lufs_musica']:g} LUFS pre-mezcla" if tipo != "ninguna" else ""))
        linea = f"sfx: {n_cues} cue{'' if n_cues == 1 else 's'} ({modo}, {audio.get('sfx_fuente', 'procedural')})"
        if avisos:
            linea += f" · AVISO {avisos[0]}" + (f" (+{len(avisos) - 1} más)" if len(avisos) > 1 else "")
        print(linea)
        if out["inteligibilidad"] is not None:
            print(linea_inteligibilidad(out["inteligibilidad"], len((lt.get("voz") or {}).get("lineas") or [])))
        print(f"{os.path.basename(salida)}: {duracion:.3f} s · {med['I']:.1f} LUFS · "
              f"{med.get('TP', float('nan')):.1f} dBTP · LRA {med.get('LRA', 0):.1f} LU "
              f"({out['normalizacion']})")
    return out


def linea_inteligibilidad(x, n):
    partes = [f"voz +{x['margen']:.1f} dB sobre la música"] if "margen" in x else []
    partes += [f"{k} {x[k]:.1f} LUFS" for k in ("pausa", "cola") if k in x]
    aviso = f" · AVISO {'; '.join(x['avisos'])}" if x.get("avisos") else ""
    return f"voz: {n} líneas · {' · '.join(partes)}{aviso}"


def main():
    ap = argparse.ArgumentParser(description="Audio del motor promo (música + SFX + mezcla)")
    ap.add_argument("--linea-tiempo", required=True, help="recursos/promo/linea_tiempo.json del proyecto")
    ap.add_argument("--salida", required=True, help="WAV de salida (p. ej. recursos/audio/mezcla.wav)")
    ap.add_argument("--repo", help="raíz del toolkit (por defecto, la que contiene este script)")
    ap.add_argument("--tp", type=float, help="true peak objetivo (default config promo.mezcla.tp)")
    ap.add_argument("--refrescar-cc0", action="store_true", help="reintenta ya las búsquedas CC0 que dieron vacío")
    a = ap.parse_args()
    generar_audio(a.linea_tiempo, a.salida, a.repo, a.tp, refrescar_cc0=a.refrescar_cc0)


if __name__ == "__main__":
    main()
