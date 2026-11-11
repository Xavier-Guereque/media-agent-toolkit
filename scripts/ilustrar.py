#!/usr/bin/env python3
"""ilustrar — explicadores con animación de estilo ilustrado (skill `explicador-ilustrado`). El agente solo escribe
`proyectos/<slug>_<DDMMAAAA>/ilustrado.json`; este script genera imágenes con estilo fijo, voz, capas, clips de IA y
renderiza con la composición base `Ilustrado` de Remotion.

  python3 scripts/ilustrar.py nuevo    <slug> [--orientacion vertical|horizontal]
  python3 scripts/ilustrar.py validar  <proyecto>                 lints + costo estimado (sin gastar)
  python3 scripts/ilustrar.py estilo   <proyecto>                 hoja de estilo: recursos/estilo/ref_1.png si no hay referencias
  python3 scripts/ilustrar.py voz      <proyecto>                 narración por toma (tiempos medidos)
  python3 scripts/ilustrar.py imagenes <proyecto> [--rehacer t3,t5]   una ilustración por toma, con la hoja de estilo
  python3 scripts/ilustrar.py capas    <proyecto> [--rehacer …]   tomas parallax: fondo sin sujeto + sujeto recortado
  python3 scripts/ilustrar.py clips    <proyecto> [--rehacer …] [--borrador] [--confirmar]   imagen a video (OpenRouter)
  python3 scripts/ilustrar.py hoja     <proyecto>                 hoja de contacto de las ilustraciones (revisar antes de pagar clips)
  python3 scripts/ilustrar.py render   <proyecto> [--borrador]    Remotion (composición Ilustrado) + acabado FFmpeg
  python3 scripts/ilustrar.py todo     <proyecto> [--confirmar]

Tres niveles de movimiento por toma (del más barato al más caro), campo `movimiento`:
  imagen   → empuje/paneo de cámara sobre la ilustración (0 USD)
  parallax → capas fondo/sujeto con profundidad (0 USD de movimiento; +2 ediciones de imagen)
  clip     → MP4 propio (p. ej. render NPR de Blender) en `clip`
  video_ia → imagen a video por OpenRouter (`config.json > modelos.video`, ~0.03 USD/s a 720p): solo tomas «héroe»
Todas comparten el hervor del trazo a 12 fps y la textura de papel, que unifican el look.

Reglas: nunca texto dentro de las imágenes (los titulares los pone Remotion); estilo propio, no copiar fotogramas de
otro canal; `clips` se niega a pasar de `ilustrado.tope_usd_por_pieza` sin --confirmar.
Códigos de salida: 0 ok · 2 corrige ilustrado.json o argumentos · 3 entorno · 4 API.
"""
import argparse
import datetime
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = comun.raiz_repo(__file__)
PY = sys.executable
MOVIMIENTOS = ("imagen", "parallax", "clip", "video_ia")
ORIENT = {"vertical": ("9:16", "vertical"), "horizontal": ("16:9", "horizontal")}
RE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
CONFIG_DEF = {"usd_imagen": 0.04, "tope_usd_por_pieza": 5.0, "video_resolucion": "720p", "video_borrador": "480p",
              "textura": 0.35, "hervor": 2.2, "fps_animacion": 12, "fundido": 0.25}
REGLA_SIN_TEXTO = ("Absolutely no text, letters, numbers, signs with writing, logos or watermarks anywhere in the image. "
                   "Leave clean space where a headline could go.")
ESTILO_EJEMPLO = ("Hand-drawn editorial illustration for an explainer video: irregular dark ink outlines with slight wobble, "
                  "flat muted colors filled with visible colored-pencil hatching, warm cream paper grain, simple shapes, "
                  "gentle 3/4 perspective, soft limited palette (brick red, slate blue, mustard, cream, charcoal).")
PLANTILLA = {
    "version": 1,
    "titulo": "Título del explicador",
    "orientacion": "vertical",
    "voz": {},
    "musica": None,
    "estilo": {"prompt": ESTILO_EJEMPLO, "referencias": [], "muestra": "a quiet 19th-century street corner with a shop window",
               "tinta": "#2b2b30", "papel": "#f4ecd8", "subtitulos": False},
    "tomas": [
        {"id": "t1", "tts": "Primera frase de la narración.", "imagen": "Wide shot of …", "movimiento": "imagen",
         "camara": {"escala": [1.0, 1.12], "x": [0, 0], "y": [0, 0]}, "titulo": {"texto": "TITULAR CORTO", "pos": "arriba"}},
        {"id": "t2", "tts": "Segunda frase.", "imagen": "Medium shot of …", "movimiento": "parallax",
         "capas": {"sujeto": "the main object in the foreground"}, "camara": {"escala": [1.0, 1.08], "x": [0.03, -0.03]}},
        {"id": "t3", "tts": "Tercera frase, la toma héroe.", "imagen": "Close-up of …", "movimiento": "video_ia",
         "video": {"prompt": "Slow dolly-in toward the object; only the camera moves; keep the ink outlines and flat colors."}},
    ],
}


# ---------------------------------------------------------------- proyecto
class Proyecto:
    def __init__(self, carpeta):
        self.dir = os.path.abspath(carpeta)
        self.nombre = os.path.basename(self.dir)
        self.slug = re.sub(r"_\d{8}$", "", self.nombre)
        self.spec_path = os.path.join(self.dir, "ilustrado.json")
        self.rec = os.path.join(self.dir, "recursos")

    def r(self, *p):
        return os.path.join(self.rec, *p)

    def leer(self):
        with open(self.spec_path, encoding="utf-8") as f:
            return json.load(f)


def resolver(ref):
    if os.path.isdir(ref):
        return Proyecto(ref)
    base = os.path.join(REPO, "proyectos")
    dirs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))) if os.path.isdir(base) else []
    cand = [d for d in dirs if d == ref] or [d for d in dirs if re.sub(r"_\d{8}$", "", d) == ref] or \
           [d for d in dirs if d.startswith(ref)]
    if len(cand) >= 1 and (len(cand) == 1 or re.sub(r"_\d{8}$", "", cand[0]) == ref):
        return Proyecto(os.path.join(base, cand[-1]))
    print(f"ERROR no encuentro el proyecto '{ref}' (o es ambiguo: {', '.join(cand[:5])}).")
    raise SystemExit(2)


def config():
    cfg = comun.cargar_config(REPO)
    return cfg, {**CONFIG_DEF, **(cfg.get("ilustrado") or {})}


def ruta_img(t):
    return f"img/{t['id']}.png"


# ---------------------------------------------------------------- validar
def validar_spec(s, p):
    e, w = [], []

    def err(ruta, msg, arreglo):
        e.append(f"E  {ruta}: {msg}. {arreglo}")

    if s.get("version") != 1:
        err("version", f"{s.get('version')!r}", 'Pon "version": 1.')
    if s.get("orientacion", "vertical") not in ORIENT:
        err("orientacion", repr(s.get("orientacion")), "Usa vertical u horizontal.")
    est = s.get("estilo") or {}
    if len((est.get("prompt") or "").split()) < 12:
        err("estilo.prompt", "falta o es muy corto", "Describe trazo, relleno, papel y paleta (≥ 12 palabras); se repite igual en todas las tomas.")
    for i, ref in enumerate(est.get("referencias") or []):
        if not os.path.exists(p.r(ref)):
            err(f"estilo.referencias[{i}]", f"no existe recursos/{ref}", "Cópiala a recursos/ o quítala (estilo la genera).")
    if not est.get("referencias") and not est.get("muestra"):
        w.append("W  estilo: sin referencias ni `muestra`; `estilo` generará la hoja con el propio prompt.")
    tomas = s.get("tomas")
    if not isinstance(tomas, list) or not tomas:
        err("tomas", "vacío", "Agrega al menos una toma.")
        return e, w
    vistos = set()
    for i, t in enumerate(tomas):
        r = f"tomas[{i}]"
        tid = t.get("id")
        if not isinstance(tid, str) or not RE_ID.match(tid) or tid in vistos:
            err(f"{r}.id", repr(tid), "id único en minúsculas (t1, gancho, cierre…).")
        vistos.add(tid)
        mov = t.get("movimiento", "imagen")
        if mov not in MOVIMIENTOS:
            err(f"{r}.movimiento", repr(mov), f"Usa {'|'.join(MOVIMIENTOS)}.")
        if mov != "clip" and not (t.get("imagen") or "").strip():
            err(f"{r}.imagen", "falta el prompt de la ilustración", "Describe encuadre, sujeto y acción (sin texto).")
        if mov == "clip" and not (t.get("clip") and os.path.exists(p.r(t["clip"]))):
            err(f"{r}.clip", f"no existe recursos/{t.get('clip')}", "Copia el MP4 a recursos/clips/.")
        if mov == "parallax" and not (t.get("capas") or {}).get("sujeto"):
            err(f"{r}.capas.sujeto", "falta", "Nombra el sujeto que va al frente (se recorta del fondo).")
        if mov == "video_ia" and not (t.get("video") or {}).get("prompt"):
            err(f"{r}.video.prompt", "falta", "Describe SOLO el movimiento (cámara y acción), p. ej. «slow dolly-in…».")
        if re.search(r"\b(text|words?|letters?|caption|sign that says|written)\b", t.get("imagen") or "", re.I):
            w.append(f"W  {r}.imagen: pide texto dentro de la imagen; los modelos lo deforman. Ponlo en `titulo`.")
        tit = (t.get("titulo") or {}).get("texto") or ""
        if len(tit) > 34:
            w.append(f"W  {r}.titulo: {len(tit)} caracteres; un titular cinético legible tiene ≤ 34.")
        if not (t.get("tts") or "").strip() and not t.get("min"):
            err(f"{r}", "sin tts ni min", "Pon la narración en `tts` o una duración en `min` (s).")
    return e, w


def estimar(s, ilu, cat=None):
    """(usd_imagenes, usd_video, n_imagenes, s_video) con 1 intento; el costo real lo fijan los reintentos."""
    n = 0 if (s.get("estilo") or {}).get("referencias") else 1
    s_vid, usd_vid = 0.0, 0.0
    for t in s.get("tomas", []):
        mov = t.get("movimiento", "imagen")
        if mov == "clip":
            continue
        n += 1 + (2 if mov == "parallax" else 0) + (1 if (t.get("video") or {}).get("ultimo") else 0)
        if mov == "video_ia":
            d = max(4, math.ceil(float(t.get("_dur") or t.get("min") or 5)))
            s_vid += d
            usd_vid += d * usd_s(t, ilu, cat)
    return n * ilu["usd_imagen"], usd_vid, n, s_vid


def usd_s(t, ilu, cat):
    import video_ia
    cfg = comun.cargar_config(REPO)
    mid = (t.get("video") or {}).get("modelo") or (cfg.get("modelos") or {}).get("video")
    if cat and mid in cat:
        v, _ = video_ia.precio_por_segundo(cat[mid], ilu["video_resolucion"], False, True, "9:16")
        if v:
            return v
    return 0.03


def etapa_validar(p, callado=False):
    s = p.leer()
    e, w = validar_spec(s, p)
    tiempos = leer_tiempos(p)
    if tiempos:
        for t in s["tomas"]:
            t["_dur"] = tiempos.get(t["id"], {}).get("dur")
    _, ilu = config()
    try:
        import video_ia
        cat = video_ia.catalogo()
    except Exception:  # noqa: BLE001 — sin red se estima con 0.03 USD/s
        cat = None
    ui, uv, n, sv = estimar(s, ilu, cat)
    for x in e + ([] if callado else w):
        print(x)
    if not callado or e:
        print(f"validar: {len(s.get('tomas', []))} tomas · {len(e)} errores · {len(w)} avisos · "
              f"estimado 1 intento: {n} imágenes ≈ {ui:.2f} USD + {sv:.0f} s de video IA ≈ {uv:.2f} USD "
              f"(total ≈ {ui + uv:.2f}; con 2 intentos ≈ {2 * (ui + uv):.2f})")
    return (2 if e else 0), s


# ---------------------------------------------------------------- imagen
def generar_imagen(p, prompt, salida, refs, relacion, modelo=None):
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    tmp = salida + ".prompt.md"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(prompt)
    cmd = [PY, os.path.join(REPO, "scripts", "imagen.py"), "generar", "--prompt-archivo", tmp, "--relacion", relacion,
           "--salida", salida]
    for r in refs:
        cmd += ["--referencia", r]
    modelo = modelo or (comun.cargar_config(REPO).get("modelos") or {}).get("imagen_ilustrado")
    if modelo:
        cmd += ["--modelo", modelo]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    salida_real = None
    for linea in r.stdout.splitlines():
        if linea.startswith("OK -> "):
            salida_real = linea[6:].strip()
    if r.returncode != 0 or not salida_real:
        print((r.stdout + r.stderr).strip()[-800:])
        raise SystemExit(4 if r.returncode in (0, 4) else r.returncode)
    if os.path.abspath(salida_real) != os.path.abspath(salida):   # el modelo devolvió JPEG: normalizar a PNG
        comun.run(["ffmpeg", "-y", "-v", "error", "-i", salida_real, salida])
        os.remove(salida_real)
    costo = re.search(r"Costo: ([\d.]+)", r.stdout)
    return float(costo.group(1)) if costo else None


def prompt_estilo(s):
    est = s.get("estilo") or {}
    return f"STYLE (identical in every image): {est['prompt'].strip()}\n{REGLA_SIN_TEXTO}"


def refs_estilo(p, s):
    return [p.r(x) for x in ((s.get("estilo") or {}).get("referencias") or [])]


def etapa_estilo(p, s, a):
    est = s.setdefault("estilo", {})
    if est.get("referencias") and not a.rehacer:
        print(f"estilo: {len(est['referencias'])} referencia(s) ya fijadas.")
        return 0
    rel, _ = ORIENT[s.get("orientacion", "vertical")]
    salida = p.r("estilo", "ref_1.png")
    muestra = est.get("muestra") or "a simple everyday scene"
    prompt = (f"{prompt_estilo(s)}\n\nStyle reference sheet: {muestra}. Show the style clearly: outlines, hatching, "
              f"paper texture and palette. This image will be reused as the style reference for a whole video.")
    print(f"estilo: generando la hoja de estilo ({muestra})…")
    c = generar_imagen(p, prompt, salida, [], rel)
    est["referencias"] = ["estilo/ref_1.png"]
    guardar(p, s)
    print(f"estilo: recursos/estilo/ref_1.png" + (f" · {c:.3f} USD" if c else "") +
          " · revísala: si no es el look buscado, ajusta estilo.prompt y repite con --rehacer.")
    return 0


def etapa_imagenes(p, s, a):
    rel, _ = ORIENT[s.get("orientacion", "vertical")]
    refs = refs_estilo(p, s)
    if not refs:
        print("Falta la hoja de estilo: corre primero `ilustrar.py estilo`.")
        return 2
    rehacer = set((a.rehacer or "").split(","))
    gasto, hechas = 0.0, 0
    tomas = [t for t in s["tomas"] if t.get("movimiento", "imagen") != "clip"]
    comun.AVANCE_DIR = p.rec
    for k, t in enumerate(tomas):
        destino = p.r(ruta_img(t))
        if os.path.exists(destino) and t["id"] not in rehacer:
            continue
        prompt = (f"{prompt_estilo(s)}\n\nSCENE: {t['imagen'].strip()}\n\nFull-bleed composition that fills the entire "
                  "frame edge to edge: no empty paper margins, no vignette, no border. Match the style reference image.")
        print(f"imagenes: {t['id']}…")
        gasto += generar_imagen(p, prompt, destino, refs, rel) or 0
        hechas += 1
        comun.avance("imagenes", 100 * (k + 1) / len(tomas), t["id"])
        ult = (t.get("video") or {}).get("ultimo")
        if t.get("movimiento") == "video_ia" and ult:
            fin = p.r("img", f"{t['id']}_fin.png")
            pf = (f"{prompt_estilo(s)}\n\nSame scene, same drawing, same characters and colors as the reference image, "
                  f"only the camera/action changed: {ult.strip()}")
            gasto += generar_imagen(p, pf, fin, [destino] + refs[:2], rel) or 0
            hechas += 1
    print(f"imagenes: {hechas} nuevas · {gasto:.3f} USD · revisa con `ilustrar.py hoja` antes de pagar clips.")
    return 0


def recortar(entrada, salida):
    """Sujeto sobre fondo uniforme → PNG con alfa: color muestreado en las esquinas + colorkey (receta del banner Hikvision)."""
    from PIL import Image
    im = Image.open(entrada).convert("RGB")
    w, h = im.size
    esquinas = [im.getpixel((x, y)) for x, y in ((3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4))]
    r, g, b = (sorted(c[i] for c in esquinas)[1] for i in range(3))
    color = f"0x{r:02X}{g:02X}{b:02X}"
    comun.run(["ffmpeg", "-y", "-v", "error", "-i", entrada, "-vf", f"colorkey={color}:0.22:0.05,despill=type=green:mix=0.6,format=rgba", salida])
    return color


def etapa_capas(p, s, a):
    rel, _ = ORIENT[s.get("orientacion", "vertical")]
    rehacer = set((a.rehacer or "").split(","))
    gasto = 0.0
    for t in s["tomas"]:
        if t.get("movimiento") != "parallax":
            continue
        base = p.r(ruta_img(t))
        if not os.path.exists(base):
            print(f"capas: falta {ruta_img(t)}; corre `imagenes` primero.")
            return 2
        sujeto = t["capas"]["sujeto"]
        fondo, crudo, alfa = (p.r("img", f"{t['id']}_{x}.png") for x in ("fondo", "sujeto_crudo", "sujeto"))
        if not os.path.exists(fondo) or t["id"] in rehacer:
            print(f"capas: {t['id']} fondo…")
            gasto += generar_imagen(p, (f"Keep this exact illustration, same framing, style and colors. Remove {sujeto} "
                                        f"completely and paint the background that was behind it, seamlessly. {REGLA_SIN_TEXTO}"),
                                    fondo, [base], rel) or 0
        if not os.path.exists(alfa) or t["id"] in rehacer:
            print(f"capas: {t['id']} sujeto…")
            gasto += generar_imagen(p, (f"Keep only {sujeto} from this illustration, exactly as drawn (same position, size, "
                                        f"outlines and colors), on a perfectly flat uniform pure green (#00FF00) background. "
                                        f"No shadow on the background. {REGLA_SIN_TEXTO}"),
                                    crudo, [base], rel) or 0
            color = recortar(crudo, alfa)
            print(f"capas: {t['id']} recortado sobre {color}")
    print(f"capas: listo · {gasto:.3f} USD")
    return 0


# ---------------------------------------------------------------- voz
def leer_tiempos(p):
    ruta = p.r("tiempos.json")
    if not os.path.exists(ruta):
        return {}
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    return {e["id"]: {**e, "dur": e["fin"] - e["inicio"]} for e in d["escenas"]} | {"_total": {"dur": d["duracion"]}}


def etapa_voz(p, s, a):
    import narrar
    import voz
    cfg, _ = config()
    comun.AVANCE_DIR = p.rec
    escenas = [{"id": t["id"], "tipo": "contenido", "min": t.get("min") or 0, "tts": t.get("tts") or ""} for t in s["tomas"]]
    res = voz.resolver_voz(s.get("voz") or {}, cfg)
    r = narrar.narrar(escenas, p.rec, res, opciones={"pausa_escena": 0.25, "cola": 0.6},
                      al_avance=lambda pct, d: comun.avance("voz", pct, d))
    for i in r["issues"]:
        print(f"{i['codigo']}  {i['ruta']}: {i['msg']} {i['arreglo']}")
    if r["codigo"]:
        return r["codigo"]
    print(f"voz: {r['nuevas']} nuevas · {r['cache']} en caché · {r['tiempos']['duracion']:.1f} s")
    return 0


# ---------------------------------------------------------------- clips
def etapa_clips(p, s, a):
    import video_ia
    cfg, ilu = config()
    tiempos = leer_tiempos(p)
    if not tiempos:
        print("Falta la voz (tiempos medidos): corre `ilustrar.py voz` antes de `clips`.")
        return 2
    rel, _ = ORIENT[s.get("orientacion", "vertical")]
    rehacer = set((a.rehacer or "").split(","))
    cat = video_ia.catalogo()
    trabajos = []
    for t in s["tomas"]:
        if t.get("movimiento") != "video_ia":
            continue
        destino = p.r("clips", f"{t['id']}.mp4")
        if os.path.exists(destino) and t["id"] not in rehacer:
            continue
        primer = p.r(ruta_img(t))
        if not os.path.exists(primer):
            print(f"clips: falta {ruta_img(t)}; corre `imagenes` primero.")
            return 2
        mid = (t.get("video") or {}).get("modelo") or cfg["modelos"]["video"]
        m = cat.get(mid)
        if not m:
            print(f"clips: modelo desconocido {mid} (python3 scripts/video_ia.py modelos).")
            return 2
        dur = tiempos[t["id"]]["dur"] + (t.get("fundido") or ilu["fundido"])
        res = ilu["video_borrador"] if a.borrador else ilu["video_resolucion"]
        pl = video_ia.plan(m, duracion=math.ceil(dur), resolucion=res, relacion=rel, audio=False, i2v=True)
        fin = p.r("img", f"{t['id']}_fin.png")
        trabajos.append((t, m, pl, primer, fin if os.path.exists(fin) else None, destino))
    if not trabajos:
        print("clips: nada que generar.")
        return 0
    total = sum(pl["costo"] or 0.03 * pl["duracion"] for _, _, pl, *_ in trabajos)
    for t, m, pl, *_ in trabajos:
        print(f"  {t['id']}: {m['id']} · {pl['duracion']} s {pl['resolucion']} ≈ {pl['costo'] or 0:.3f} USD")
    print(f"clips: {len(trabajos)} clip(s) ≈ {total:.2f} USD (tope por pieza {ilu['tope_usd_por_pieza']:.2f})")
    if total > ilu["tope_usd_por_pieza"] and not a.confirmar:
        print("No se generó: supera el tope. Confírmalo con el usuario y repite con --confirmar.")
        return 2
    key = comun.api_key(REPO)
    comun.AVANCE_DIR = p.rec
    import concurrent.futures

    def uno(job):
        t, m, pl, primer, fin, destino = job
        prompt = (t["video"]["prompt"].strip() + " Keep the hand-drawn look exactly: irregular ink outlines, flat colors, "
                  "pencil texture, no photorealism, no 3D shading, no text.")
        return t["id"], video_ia.generar_uno(key, m, pl, prompt=prompt, relacion=rel, salida=destino, primer=primer,
                                             ultimo=fin, recursos=p.rec, etapa=f"clip {t['id']}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(trabajos))) as ex:
        res = list(ex.map(uno, trabajos))
    gasto, malos = 0.0, 0
    for tid, r in res:
        gasto += r.get("costo") or 0
        if r["ok"]:
            print(f"  OK {tid}: {r['duracion_clip']} s · {r['segundos']} s · {r.get('costo') or 0:.4f} USD")
        else:
            malos += 1
            print(f"  FALLA {tid}: {r['error'][:200]}")
    print(f"clips: gastado {gasto:.4f} USD")
    return 4 if malos else 0


# ---------------------------------------------------------------- hoja de contacto
def etapa_hoja(p, s, a):
    from PIL import Image, ImageDraw
    imgs = []
    for t in s["tomas"]:
        for nombre in (ruta_img(t), f"img/{t['id']}_fondo.png", f"img/{t['id']}_sujeto.png", f"img/{t['id']}_fin.png"):
            if os.path.exists(p.r(nombre)):
                imgs.append((nombre.split("/")[-1], p.r(nombre)))
    if not imgs:
        print("hoja: no hay imágenes todavía.")
        return 2
    cols = 4
    w = 360
    primera = Image.open(imgs[0][1])
    h = round(w * primera.height / primera.width)
    filas = math.ceil(len(imgs) / cols)
    hoja = Image.new("RGB", (cols * w, filas * (h + 30)), "#222")
    d = ImageDraw.Draw(hoja)
    for i, (nombre, ruta) in enumerate(imgs):
        im = Image.open(ruta).convert("RGBA")
        fondo = Image.new("RGBA", im.size, (255, 0, 255, 255))
        im = Image.alpha_composite(fondo, im).convert("RGB").resize((w, h))
        x, y = (i % cols) * w, (i // cols) * (h + 30)
        hoja.paste(im, (x, y + 30))
        d.text((x + 6, y + 8), nombre, fill="#fff")
    salida = os.path.join(p.dir, f"{p.slug}_hoja.jpg")
    hoja.save(salida, quality=88)
    print(f"hoja: {salida} (el magenta marca la transparencia de los sujetos recortados)")
    return 0


# ---------------------------------------------------------------- render
def normalizar_clip(p, clip, s):
    """Copia CFR 30 fps, h264 yuv420p, al tamaño de salida y con GOP corto: los clips de IA llegan a 24 fps con marcas
    de tiempo irregulares y `<OffthreadVideo>` falla con «No frame found at position…». Devuelve la ruta relativa."""
    w, h = (1080, 1920) if s.get("orientacion", "vertical") == "vertical" else (1920, 1080)
    origen = p.r(clip)
    rel = os.path.splitext(clip)[0] + "_30fps.mp4"
    destino = p.r(rel)
    if not os.path.exists(destino) or os.path.getmtime(destino) < os.path.getmtime(origen):
        comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", origen, "-an", "-vf",
                   f"fps=30,scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1,format=yuv420p",
                   "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-g", "15", "-movflags", "+faststart", destino])
    return rel


def construir_remotion(p, s):
    _, ilu = config()
    tiempos = leer_tiempos(p)
    if not tiempos:
        print("Falta la voz: corre `ilustrar.py voz`.")
        raise SystemExit(2)
    est = s.get("estilo") or {}
    tomas = []
    for i, t in enumerate(s["tomas"]):
        ti = tiempos[t["id"]]
        mov = t.get("movimiento", "imagen")
        x = {"id": t["id"], "inicio": ti["inicio"], "fin": ti["fin"],
             "fundido": 0 if i == 0 else t.get("fundido", ilu["fundido"])}
        if mov in ("clip", "video_ia"):
            clip = t["clip"] if mov == "clip" else f"clips/{t['id']}.mp4"
            if not os.path.exists(p.r(clip)):
                if mov == "video_ia" and os.path.exists(p.r(ruta_img(t))):
                    print(f"AVISO {t['id']}: sin clip de IA todavía; se usa la ilustración con cámara.")
                    x.update(tipo="imagen", src=ruta_img(t), camara=t.get("camara") or {"escala": [1.0, 1.15]})
                else:
                    print(f"ERROR {t['id']}: falta recursos/{clip}.")
                    raise SystemExit(2)
            else:
                clip = normalizar_clip(p, clip, s)
                x.update(tipo="clip", src=clip, camara=t.get("camara") or {})
                dc, dt = comun.dur(p.r(clip)), ti["fin"] - ti["inicio"] + x["fundido"]
                if dc < dt:                                       # clip corto: se estira (≥ 0.6×) para cubrir la toma
                    x["velocidad"] = round(max(0.6, dc / dt), 3)
        elif mov == "parallax":
            x.update(tipo="parallax", capas=[{"src": f"img/{t['id']}_fondo.png", "z": 0},
                                             {"src": f"img/{t['id']}_sujeto.png", "z": 1}],
                     camara=t.get("camara") or {"escala": [1.0, 1.08], "x": [0.03, -0.03]})
        else:
            x.update(tipo="imagen", src=ruta_img(t), camara=t.get("camara") or {"escala": [1.0, 1.12]})
        if t.get("titulo"):
            x["titulo"] = t["titulo"]
        x["palabras"] = [{"w": w["w"], "a": round(w["a"] - ti["inicio"], 3), "b": round(w["b"] - ti["inicio"], 3)}
                         for w in ti.get("palabras") or []]
        tomas.append(x)
    estilo = {"tinta": est.get("tinta", "#2b2b30"), "papel": est.get("papel", "#f4ecd8"),
              "textura": est.get("textura", ilu["textura"]), "hervor": est.get("hervor", ilu["hervor"]),
              "fps_animacion": est.get("fps_animacion", ilu["fps_animacion"]), "subtitulos": bool(est.get("subtitulos"))}
    props = {"tomas": tomas, "voz": mezclar_audio(p, s, tiempos["_total"]["dur"]), "estilo": estilo}
    spec = {"version": 1, "composicion": "Ilustrado", "orientacion": ORIENT[s.get("orientacion", "vertical")][1],
            "duracion": tiempos["_total"]["dur"], "salida": f"{p.slug}.mp4", "props": props}
    with open(os.path.join(p.dir, "remotion.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    return spec


def mezclar_audio(p, s, total):
    """Voz sola, o voz + cama con ducking (`componer.mezclar`): `musica` = "ambiental" (cama documental procedural, 0 USD)
    o un archivo de recursos/ (CC0 o propio). Devuelve la ruta relativa a recursos/ que pinta la composición."""
    mus = s.get("musica")
    if not mus:
        return "voz.wav"
    import componer
    if mus == "ambiental":
        cama, lufs = componer.cama_ambiental(total, p.r("audio", "cama.wav")), None
    else:
        cama, lufs = p.r(mus), componer.LUFS_MUSICA
        if not os.path.exists(cama):
            print(f"ERROR musica: no existe recursos/{mus} (o usa \"ambiental\").")
            raise SystemExit(2)
    componer.mezclar(p.r("mezcla.wav"), total, [(p.r("voz.wav"), 0)], cama=cama, musica_lufs=lufs)
    return "mezcla.wav"


def etapa_render(p, s, a):
    import remotion
    construir_remotion(p, s)
    ns = argparse.Namespace(verbose=a.verbose, borrador=a.borrador, workers=None, raiz=None)
    rp = remotion.Proyecto(p.dir)
    rp.etiqueta = "ilustrado"
    return remotion.etapa_render(ns, rp, siguiente=False)


# ---------------------------------------------------------------- nuevo / todo
def guardar(p, s):
    s = {**s, "tomas": [{k: v for k, v in t.items() if not k.startswith("_")} for t in s.get("tomas", [])]}
    with open(p.spec_path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


def etapa_nuevo(a):
    nombre = f"{a.slug}_{datetime.date.today():%d%m%Y}"
    d = os.path.join(REPO, "proyectos", nombre)
    if os.path.exists(os.path.join(d, "ilustrado.json")):
        print(f"ERROR ya existe {d}/ilustrado.json")
        return 2
    for sub in ("recursos/estilo", "recursos/img", "recursos/clips"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    s = json.loads(json.dumps(PLANTILLA))
    s["orientacion"] = a.orientacion
    guardar(Proyecto(d), s)
    print(f"nuevo: proyectos/{nombre}/ilustrado.json (plantilla). Escribe estilo, tomas y tts; luego "
          f"python3 scripts/ilustrar.py validar {nombre}")
    return 0


ETAPAS = {"estilo": etapa_estilo, "voz": etapa_voz, "imagenes": etapa_imagenes, "capas": etapa_capas,
          "clips": etapa_clips, "hoja": etapa_hoja, "render": etapa_render}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etapa", choices=["nuevo", "validar", "todo", *ETAPAS])
    ap.add_argument("objetivo", help="slug (nuevo) o proyecto")
    ap.add_argument("--orientacion", choices=list(ORIENT), default="vertical")
    ap.add_argument("--rehacer", default="", help="ids de tomas a regenerar (coma); en estilo, cualquier valor")
    ap.add_argument("--borrador", action="store_true")
    ap.add_argument("--confirmar", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.etapa == "nuevo":
        a.slug = a.objetivo
        return etapa_nuevo(a)
    p = resolver(a.objetivo)
    codigo, s = etapa_validar(p, callado=a.etapa != "validar")
    if codigo or a.etapa == "validar":
        return codigo
    orden = ["estilo", "voz", "imagenes", "capas", "clips", "hoja", "render"] if a.etapa == "todo" else [a.etapa]
    for e in orden:
        codigo = ETAPAS[e](p, s, a)
        if codigo:
            print(f"ilustrar {e}: se detuvo con código {codigo}.")
            return codigo
        s = p.leer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
