#!/usr/bin/env python3
"""pantalla — reemplaza (traduce) el texto sobrepuesto de un video existente.

Detecta los rótulos del video (pastillas blancas con texto negro) por OCR, y regenera cada
uno con el texto nuevo en el mismo lugar y estilo, **cubriendo el original**. No agrega
subtítulos: sobre-escribe el texto que ya viene incrustado. Conserva el audio (música) y la
duración del video original.

Pasos:
  1) python3 scripts/pantalla.py detectar <video> --json caps.json
     → muestrea el video (fps), corre `tesseract` y agrupa los fotogramas con texto en
       rótulos: ventana (inicio/fin), texto OCR, bbox del texto y centro. Sale un JSON editable.
  2) Editar caps.json: en cada rótulo, poner `lineas` con la traducción (y ajustar
     `fuente_pt` / `centro` / `pad_x` si hace falta). Los rótulos que no se traduzcan se borran.
     **Revisar los tiempos**: el OCR detecta el rótulo cuando ya es legible, así que el original
     suele empezar 0.1–0.4 s antes del `inicio` detectado; si en la tabla se ve un salto raro
     (p. ej. un rótulo que arranca mucho después del anterior), corregir `inicio`.
  3) python3 scripts/pantalla.py generar caps.json --render
     → PNG RGBA por rótulo + comando ffmpeg (los fundidos caen FUERA de la ventana original,
       para que la pastilla esté opaca durante toda la vida del texto original) y, con
       --render, el mp4 final.

Las rutas del spec (`entrada`, `fuente`, `salida`) son relativas a la carpeta del propio JSON.

Regla de oro del fundido: el fundido de entrada debe TERMINAR en `inicio` y el de salida
EMPEZAR en `fin + desfase`; si no, al fundir se alcanza a ver el texto original debajo.

Requisitos: ffmpeg y tesseract (`brew install tesseract`). `generar` necesita Pillow; si el
`python3` en uso no lo trae, el script se re-ejecuta con otro intérprete que sí.

Códigos: 0 ok · 2 argumentos/datos · 3 entorno (falta ffmpeg/tesseract/Pillow) · 1 ffmpeg.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = comun.raiz_repo(os.path.abspath(__file__))
FPS_DEF = 10.0
CONF_MIN_DEF = 55
MIN_LETRAS_DEF = 3
GAP_DEF = 0.35          # s: separación máxima entre fotogramas con texto para unirlos en un rótulo
SALTO_DEF = 150         # px: salto del centro del bloque que fuerza un rótulo nuevo
MIN_DUR_DEF = 0.5       # s: bloques más cortos se descartan (ruido de OCR)
PAD_X_DEF, PAD_Y_DEF = 70, 28
RADIO_PCT_DEF = 0.32
# Arial Bold de macOS (la verificada) y sus equivalentes en Windows y Linux: la primera que exista.
FUENTES_SISTEMA = ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"),
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf")
FUENTE_SISTEMA = next((f for f in FUENTES_SISTEMA if os.path.isfile(f)), FUENTES_SISTEMA[0])
CANDIDATOS_PY = ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "python3.13", "python3.12",
                 "python3.11", "/usr/bin/python3", "py", "python")


# ------------------------------------------------------------------ utilidades
def _tiene_pillow(py):
    try:
        return subprocess.run([py, "-c", "import PIL"], capture_output=True).returncode == 0
    except OSError:
        return False


def asegurar_pillow():
    """Re-ejecuta este script con un intérprete que tenga Pillow (Pillow solo hace falta para
    dibujar la pastilla; el `python3` del sistema en macOS no lo trae)."""
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    for cand in CANDIDATOS_PY:
        py = shutil.which(cand) or (cand if os.path.exists(cand) else None)
        if not py or py == sys.executable:
            continue
        if _tiene_pillow(py):
            os.execv(py, [py, os.path.abspath(__file__)] + sys.argv[1:])
    print("ERROR falta Pillow y no encontré otro python3 con Pillow.\n"
          "  Opciones: /opt/homebrew/bin/python3 scripts/pantalla.py …\n"
          "  o: python3 -m venv ~/.venvs/pil && ~/.venvs/pil/bin/pip install pillow", file=sys.stderr)
    sys.exit(3)


def ocr_lineas(png, conf_min=CONF_MIN_DEF, min_letras=MIN_LETRAS_DEF):
    """OCR de un PNG → lista de líneas {texto, bbox}, agrupando palabras por (bloque,párrafo,línea)."""
    out = subprocess.run(["tesseract", png, "-", "--psm", "11", "tsv"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    grupos = {}
    for fila in out.splitlines()[1:]:
        p = fila.split("\t")
        if len(p) < 12 or not p[11].strip():
            continue
        try:
            conf = float(p[10])
        except ValueError:
            continue
        txt = p[11]
        if conf < conf_min or len(re.sub(r"[^A-Za-z]", "", txt)) < min_letras:
            continue
        x, y, w, h = (int(p[6]), int(p[7]), int(p[8]), int(p[9]))
        grupos.setdefault((p[2], p[3], p[4]), []).append((x, y, w, h, txt))
    lineas = []
    for _, ws in sorted(grupos.items()):
        ws.sort(key=lambda v: v[0])
        x0 = min(v[0] for v in ws); y0 = min(v[1] for v in ws)
        x1 = max(v[0] + v[2] for v in ws); y1 = max(v[1] + v[3] for v in ws)
        lineas.append({"texto": " ".join(v[4] for v in ws), "bbox": [x0, y0, x1, y1]})
    return lineas


def _unir(bboxes):
    return [min(b[0] for b in bboxes), min(b[1] for b in bboxes),
            max(b[2] for b in bboxes), max(b[3] for b in bboxes)]


def _cluster_dominante(lineas):
    """Bloque de texto más probable (el rótulo). Agrupa las líneas por vecindad vertical y se
    queda con el grupo que más texto aporta: así se descartan logotipos o rótulos sueltos en
    otra zona del cuadro (p. ej. un logotipo en una esquina)."""
    if not lineas:
        return None
    orden = sorted(lineas, key=lambda l: (l["bbox"][1] + l["bbox"][3]) / 2)
    alturas = [(l["bbox"][3] - l["bbox"][1]) for l in orden]
    alt = sorted(alturas)[len(alturas) // 2]
    grupos = [[orden[0]]]
    for l in orden[1:]:
        y_prev = (grupos[-1][-1]["bbox"][1] + grupos[-1][-1]["bbox"][3]) / 2
        y = (l["bbox"][1] + l["bbox"][3]) / 2
        if y - y_prev > 1.6 * max(alt, 1):
            grupos.append([l])
        else:
            grupos[-1].append(l)

    def peso(g):
        return sum(len(re.sub(r"[^A-Za-z]", "", l["texto"])) for l in g)

    mejor = max(grupos, key=peso)
    # poda: en un rótulo las líneas son de ancho comparable; una línea diminuta suele ser ruido
    if len(mejor) > 1:
        anc = max(l["bbox"][2] - l["bbox"][0] for l in mejor)
        mejor = [l for l in mejor if (l["bbox"][2] - l["bbox"][0]) >= 0.25 * anc] or mejor
    return {"texto": [l["texto"] for l in mejor], "bbox": _unir([l["bbox"] for l in mejor])}


def _centro(b):
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def _bbox_pastilla(png, bbox_texto, umbral=246, ratio=0.5, px=280, py=95):
    """Bbox de la pastilla blanca que contiene al texto, con solo Pillow.

    La pastilla es blanca (255) y el fondo de estas piezas es claro pero no blanco
    (p. ej. 239,245,255), así que `min(R,G,B) > umbral` aísla la pastilla. Se expande
    desde la columna/fila central del texto mientras las columnas/filas sigan siendo
    mayoritariamente blancas, de modo que un objeto blanco vecino (sensor, círculo) no
    estira el recuadro. Devuelve None si no encuentra pastilla."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    im = Image.open(png).convert("RGB")
    W, H = im.size
    x0, y0, x1, y1 = bbox_texto
    X0, Y0 = max(0, x0 - px), max(0, y0 - py)
    X1, Y1 = min(W, x1 + px), min(H, y1 + py)
    sub = im.crop((X0, Y0, X1, Y1))
    w, h = sub.size
    r, g, b = sub.split()
    m = ImageChops.multiply(ImageChops.multiply(r.point(lambda v: 255 if v > umbral else 0),
                                               g.point(lambda v: 255 if v > umbral else 0)),
                            b.point(lambda v: 255 if v > umbral else 0))
    pix = m.tobytes()
    cols = [0] * w
    rows = [0] * h
    for i, v in enumerate(pix):
        if v:
            cols[i % w] += 1
            rows[i // w] += 1
    cx, cy = min(max((x0 + x1) // 2 - X0, 0), w - 1), min(max((y0 + y1) // 2 - Y0, 0), h - 1)
    # umbrales referidos al tamaño del texto (la pastilla ≈ texto + relleno), no al recorte
    alto_min = 0.35 * ((y1 - y0) + 44)
    ancho_min = 0.35 * ((x1 - x0) + 44)
    if cols[cx] < alto_min or rows[cy] < ancho_min:
        return None
    a = cx
    while a > 0 and cols[a - 1] >= alto_min:
        a -= 1
    c = cx
    while c < w - 1 and cols[c + 1] >= alto_min:
        c += 1
    ancho = c - a + 1
    t = cy
    while t > 0 and rows[t - 1] >= ancho_min:
        t -= 1
    u = cy
    while u < h - 1 and rows[u + 1] >= ancho_min:
        u += 1
    return [X0 + a, Y0 + t, X0 + c, Y0 + u]


# ------------------------------------------------------------------ detectar
def detectar(a):
    asegurar_pillow()
    if not shutil.which("tesseract"):
        print("ERROR falta tesseract. Instálalo: brew install tesseract", file=sys.stderr)
        return 3
    if not os.path.isfile(a.video):
        print(f"ERROR no existe el video: {a.video}", file=sys.stderr)
        return 2
    dur = comun.dur(a.video)
    rec = os.path.join(os.path.dirname(os.path.abspath(a.video)), "pantalla_frames")
    os.makedirs(rec, exist_ok=True)
    for f in os.listdir(rec):
        os.remove(os.path.join(rec, f))
    comun.run(["ffmpeg", "-v", "error", "-ss", str(a.desde), "-i", a.video,
               "-vf", f"fps={a.fps}", "-y", os.path.join(rec, "f_%05d.png")], log=False)

    fotos = sorted(os.listdir(rec))
    muestras = []
    for i, f in enumerate(fotos):
        t = round(a.desde + i / a.fps, 3)
        ruta = os.path.join(rec, f)
        dom = _cluster_dominante(ocr_lineas(ruta, a.conf, a.min_letras))
        if dom:
            muestras.append({"t": t, "dom": dom, "png": ruta})

    # agrupar por hueco de tiempo Y por continuidad del bloque (mismo rótulo en el cuadro)
    grupos = []
    for m in muestras:
        nuevo = True
        if grupos:
            prev = grupos[-1][-1]
            cx0, cy0 = _centro(prev["dom"]["bbox"])
            cx1, cy1 = _centro(m["dom"]["bbox"])
            nuevo = (m["t"] - prev["t"] > a.gap
                     or abs(cx0 - cx1) > a.salto or abs(cy0 - cy1) > a.salto)
        if nuevo:
            grupos.append([m])
        else:
            grupos[-1].append(m)

    caps = []
    for g in grupos:
        if g[-1]["t"] + 1.0 / a.fps - g[0]["t"] < a.min_duracion:
            continue
        # descartar fotogramas cuyo bloque se sale del patrón (ruido de OCR en algún frame)
        cen = sorted(_centro(m["dom"]["bbox"])[0] for m in g)
        medx = cen[len(cen) // 2]
        ceny = sorted(_centro(m["dom"]["bbox"])[1] for m in g)[len(g) // 2]
        buenos = [m for m in g
                  if abs(_centro(m["dom"]["bbox"])[0] - medx) <= 70
                  and abs(_centro(m["dom"]["bbox"])[1] - ceny) <= 70] or g
        rep = max(buenos, key=lambda m: sum(len(l) for l in m["dom"]["texto"]))
        bbox = _unir([m["dom"]["bbox"] for m in buenos])
        lineas = rep["dom"]["texto"]
        rb = rep["dom"]["bbox"]
        pt = max(12, int(round((rb[3] - rb[1]) / max(1, len(lineas)) / 1.25)))
        past = _bbox_pastilla(rep["png"], bbox)
        cap = {
            "id": f"cap{len(caps) + 1}",
            "inicio": round(g[0]["t"], 2),
            "fin": round(g[-1]["t"] + 1.0 / a.fps, 2),
            "texto_ocr": lineas,
            "lineas": [],
            "fuente_pt": pt,
            "centro": list(_centro(past or bbox)),
            "bbox_texto": bbox,
        }
        if past:
            cap["bbox_pastilla"] = past
        caps.append(cap)

    destino = a.json or os.path.join(os.path.dirname(os.path.abspath(a.video)), "pantalla.json")
    base = os.path.dirname(os.path.abspath(destino))
    spec = {"entrada": os.path.relpath(os.path.abspath(a.video), base),
            "salida": a.salida or "", "fuente": a.fuente or "", "captions": caps}
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)

    print(f"# {len(caps)} rótulo(s) detectado(s) en {os.path.basename(a.video)} "
          f"(duración {dur:.2f} s, {a.fps:.0f} fps)")
    for c in caps:
        print(f"  {c['id']:5s} {c['inicio']:6.2f}–{c['fin']:6.2f}s  ~{c['fuente_pt']}pt  "
              f"centro {c['centro']}  «{' / '.join(c['texto_ocr'])}»")
    print(f"Siguiente: edita '{destino}' (pon `lineas` con la traducción en cada rótulo, borra los "
          f"que no sirvan) y corre: python3 scripts/pantalla.py generar {destino} --render")
    return 0


# ------------------------------------------------------------------ generar
def _make_overlay(cap, lineas, alto_px, ancho_px, fuente, colores):
    from PIL import Image, ImageDraw, ImageFont
    cxf, cyf = cap.get("centro") or [(cap["bbox_texto"][0] + cap["bbox_texto"][2]) // 2,
                                     (cap["bbox_texto"][1] + cap["bbox_texto"][3]) // 2]
    fuente = ImageFont.truetype(fuente, int(cap.get("fuente_pt", 44)))
    tmp = Image.new("RGBA", (10, 10)); d = ImageDraw.Draw(tmp)
    texto = "\n".join(lineas)
    spacing = int(cap.get("interlinea", 8))
    bb = d.multiline_textbbox((0, 0), texto, font=fuente, anchor="mm", align="center", spacing=spacing)
    ox0, oy0, ox1, oy1 = cap.get("bbox_pastilla") or cap["bbox_texto"]
    pw = int(max(bb[2] - bb[0] + 2 * cap.get("pad_x", PAD_X_DEF), (ox1 - ox0) + 44)) | 1
    ph = int(max(bb[3] - bb[1] + 2 * cap.get("pad_y", PAD_Y_DEF), (oy1 - oy0) + 44)) | 1
    img = Image.new("RGBA", (ancho_px, alto_px), (0, 0, 0, 0))
    dd = ImageDraw.Draw(img)
    r = int(min(max(ph * cap.get("radio_pct", RADIO_PCT_DEF), 24), 46))
    x0, y0 = int(cxf - pw / 2), int(cyf - ph / 2)
    dd.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=r, fill=colores["pastilla"])
    dd.multiline_text((cxf, cyf), texto, font=fuente, fill=colores["texto"],
                      anchor="mm", align="center", spacing=spacing)
    return img


def generar(a):
    asegurar_pillow()
    if not os.path.isfile(a.spec):
        print(f"ERROR no existe el spec: {a.spec}", file=sys.stderr)
        return 2
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    base = os.path.dirname(os.path.abspath(a.spec))
    entrada = spec["entrada"] if os.path.isabs(spec["entrada"]) else os.path.join(base, spec["entrada"])
    if not os.path.isfile(entrada):
        print(f"ERROR no existe el video de entrada: {entrada}", file=sys.stderr)
        return 2

    caps = [c for c in spec.get("captions", []) if c.get("lineas")]
    if not caps:
        print("ERROR ningún rótulo tiene `lineas` (traducción). Edita el spec.", file=sys.stderr)
        return 2

    fuente = spec.get("fuente") or FUENTE_SISTEMA
    if spec.get("fuente") and not os.path.isabs(fuente):
        fuente = os.path.join(base, fuente)
    if not os.path.isfile(fuente):
        print(f"ERROR no existe la fuente: {fuente}", file=sys.stderr)
        return 2

    dur_v = comun.dur(entrada)
    ancho, alto = 1920, 1080
    try:
        info = json.loads(comun.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                     "-show_entries", "stream=width,height", "-of", "json", entrada],
                                    log=False).stdout)
        s = info["streams"][0]; ancho, alto = int(s["width"]), int(s["height"])
    except Exception:
        pass

    carpeta = os.path.join(os.path.dirname(os.path.abspath(a.spec)), "overlays")
    os.makedirs(carpeta, exist_ok=True)
    colores = {"texto": tuple(spec.get("color_texto", [0, 0, 0, 255])),
               "pastilla": tuple(spec.get("color_pastilla", [255, 255, 255, 255]))}

    # cada rótulo produce una o más capas (etapas de revelado)
    capas = []
    for cap in caps:
        etapas = cap.get("etapas")
        if etapas:
            for i, et in enumerate(etapas):
                e = dict(et)
                e["_siguiente"] = etapas[i + 1]["inicio"] if i + 1 < len(etapas) else None
                e["_primera"] = (i == 0)
                capas.append({"cap": cap, "et": e})
        else:
            capas.append({"cap": cap,
                          "et": {"lineas": cap["lineas"], "inicio": cap["inicio"], "fin": cap["fin"]}})

    # PNG de cada capa: la pastilla se dimensiona con el rótulo COMPLETO (pastilla fija entre etapas)
    ref = {c["cap"]["id"]: {k: v for k, v in c["cap"].items() if k != "etapas"} for c in capas}
    n_capas = {}
    for c in capas:
        n_capas[c["cap"]["id"]] = n_capas.get(c["cap"]["id"], 0) + 1
    idx = {}
    for c in capas:
        idx[c["cap"]["id"]] = idx.get(c["cap"]["id"], 0) + 1
        sufijo = f"_s{idx[c['cap']['id']]}" if n_capas[c["cap"]["id"]] > 1 else ""
        c["png"] = os.path.join(carpeta, c["cap"]["id"] + sufijo + ".png")
        img = _make_overlay(ref[c["cap"]["id"]], c["et"]["lineas"], alto, ancho, fuente, colores)
        img.save(c["png"])

    # grafo ffmpeg
    fi = spec.get("fundido_in", 0.20)
    fo = spec.get("fundido_out", 0.20)
    desfase = spec.get("desfase_fin", 0.05)
    # el OCR detecta el rótulo cuando ya es legible: el original empieza a aparecer un poco
    # antes. Se adelanta el "opaco desde" para que la pastilla cubra también ese arranque.
    margen_in = spec.get("margen_inicio", 0.15)
    entradas, filtros, overlays, prev = [], [], [], "0:v"
    for k, c in enumerate(capas, start=1):
        entradas += ["-loop", "1", "-i", c["png"]]
        et = c["et"]
        inicio = et["inicio"]
        fin = et.get("fin", c["cap"].get("fin"))
        sgte = et.get("_siguiente")
        primera = et.get("_primera", True)
        ref_in = max(0.0, inicio - (margen_in if primera else 0.0))
        f_in = et.get("fundido_in", fi) if primera else et.get("fundido_in", 0.0)
        t_in = max(0.0, ref_in - f_in)
        partes = [f"[{k}:v]format=rgba"]
        if f_in > 0:
            partes.append(f"fade=t=in:st={t_in:.3f}:d={f_in}:alpha=1")
        if sgte is not None:
            # relevo entre etapas en el mismo instante (la pastilla es idéntica: sin hueco)
            enable = f"between(t,{t_in:.3f},{sgte:.3f})"
        elif fin is None:
            enable = f"gte(t,{t_in:.3f})"
        else:
            f_out = et.get("fundido_out", fo)
            dsf = et.get("desfase_fin", desfase)
            if f_out > 0:
                partes.append(f"fade=t=out:st={fin + dsf:.3f}:d={f_out}:alpha=1")
                enable = f"between(t,{t_in:.3f},{fin + dsf + f_out + 0.05:.3f})"
            else:
                enable = f"between(t,{t_in:.3f},{fin + dsf:.3f})"
        filtros.append(",".join(partes) + f"[o{k}]")
        overlays.append(f"[{prev}][o{k}]overlay=0:0:enable='{enable}'"
                        + (f"[v{k}]" if k < len(capas) else "[vout]"))
        prev = f"v{k}"

    salida = spec.get("salida") or "salida-es.mp4"
    if not os.path.isabs(salida):
        salida = os.path.join(os.path.dirname(os.path.abspath(a.spec)), salida)
    preset = spec.get("preset", "medium")
    crf = spec.get("crf", 18)
    cmd = (["ffmpeg", "-y", "-v", "error", "-i", entrada] + entradas
           + ["-filter_complex", ";".join(filtros + overlays),
              "-map", "[vout]", "-map", "0:a", "-c:v", "libx264", "-crf", str(crf),
              "-preset", preset, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
              "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "-t", f"{dur_v:.3f}", salida])

    print(f"# {len(capas)} capa(s) → {os.path.relpath(carpeta, REPO)}")
    print(" ".join(f"'{x}'" if " " in x else x for x in cmd))
    if not a.render:
        print("Siguiente: revisa el comando y repite con --render para renderizar.")
        return 0
    print(f"Renderizando {os.path.basename(salida)} …")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("ERROR ffmpeg falló.", file=sys.stderr)
        return 1
    print(f"OK {salida}  ({comun.dur(salida):.2f} s, original {dur_v:.2f} s)")
    print("Siguiente: verificá con OCR de los fotogramas de frontera que no quede texto original "
          "(ver la skill 'traducir-texto-en-pantalla' de SKILL.md).")
    return 0


# ------------------------------------------------------------------ fuente de woff2 → ttf
def fuente_cmd(a):
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError:
        print("ERROR falta fontTools. Instálalo, p. ej.:\n"
              "  uv run --with fonttools --with brotli python scripts/pantalla.py fuente "
              f"{a.entrada} {a.salida} --peso {a.peso}", file=sys.stderr)
        return 3
    f = TTFont(a.entrada)
    f.flavor = None
    if a.peso and "fvar" in f:
        instantiateVariableFont(f, {"wght": a.peso}, inplace=True)
    f.save(a.salida)
    print(f"OK {a.salida}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Reemplaza/traduce el texto sobrepuesto de un video")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detectar", help="OCR del video → JSON con ventanas y geometría de cada rótulo")
    d.add_argument("video")
    d.add_argument("--json", help="archivo de salida (por defecto <video>.pantalla.json)")
    d.add_argument("--salida", help="nombre del mp4 final que se anotará en el spec")
    d.add_argument("--fuente", help="ttf/otf a anotar en el spec")
    d.add_argument("--fps", type=float, default=FPS_DEF, help="fps de muestreo (default 10)")
    d.add_argument("--desde", type=float, default=0.0)
    d.add_argument("--gap", type=float, default=GAP_DEF, help="hueco máximo para unir fotogramas")
    d.add_argument("--salto", type=float, default=SALTO_DEF,
                   help="px: si el centro del bloque salta más, empieza otro rótulo")
    d.add_argument("--min-duracion", type=float, default=MIN_DUR_DEF,
                   help="s: descarta bloques más cortos (ruido de OCR)")
    d.add_argument("--conf", type=float, default=CONF_MIN_DEF)
    d.add_argument("--min-letras", type=int, default=MIN_LETRAS_DEF)
    d.set_defaults(fn=detectar)

    g = sub.add_parser("generar", help="spec JSON → overlays PNG (+ render del mp4)")
    g.add_argument("spec")
    g.add_argument("--render", action="store_true", help="correr ffmpeg (si no, solo imprime el comando)")
    g.set_defaults(fn=generar)

    c = sub.add_parser("fuente", help="convertir una woff2 variable del repo a ttf de un peso")
    c.add_argument("entrada"); c.add_argument("salida")
    c.add_argument("--peso", type=int, default=700)
    c.set_defaults(fn=fuente_cmd)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
