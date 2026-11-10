#!/usr/bin/env python3
"""Sustituye un personaje/mascota estático de un video por otra ilustración (skill `reemplazar-personaje-video`).

El personaje original debe ser un asset fijo (misma pose) sobre fondo uniforme; puede entrar y salir deslizándose.
Tres subcomandos, todos con `~/.venvs/imagen/bin/python` (numpy + OpenCV + Pillow):

  rastrear  <video> <asset_viejo.png> --salida rastreo.json [--region x0,y0,x1,y1] [--calibrar n,n,…] [--escalas a,b,paso]
            Calibra la escala del asset por plantilla (TM_CCOEFF_NORMED sobre "distancia al fondo") en varios cuadros y
            rastrea posición, score, opacidad y margen libre a la derecha en todos los cuadros (a media resolución).
  solape    <video> <rastreo.json> <nuevo_alfa.png> --candidatos 0.55:-6,0.52:-6 [--pies N]
            Mide cuántos píxeles de contenido taparía el nuevo personaje por cuadro para cada (escala:x) candidato.
  reemplazar <video> <rastreo.json> <asset_viejo.png> <nuevo_alfa.png> <salida.mp4> --escala S --x X [--pies N]
            [--muestras n,n,…] [--umbral 0.45]   Pinta la silueta vieja con el fondo del cuadro y compone el PNG con alfa,
            alineando los pies a la base del viejo y siguiendo sus deslizamientos. Con --muestras no renderiza: exporta PNG
            antes|después en <salida sin extensión>_muestras/ (o en <salida> si no es un nombre de video).

El nuevo personaje se recorta con alfa a partir de un fondo uniforme (ver `[[SKILL]]`). Reporta avance al tablero (etapa
`rastreo` y `reemplazo`; avance.jsonl en la carpeta del rastreo.json). Códigos de salida: 1 ffmpeg, 2 argumentos.
"""
import argparse, collections, json, os, re, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402


def contenido(img, bg):
    return np.clip(np.abs(img.astype(np.int16) - bg).sum(2), 0, 255).astype(np.uint8)


def fondo_de(img):
    """Color de fondo (BGR int16) por la mediana de las cuatro esquinas."""
    h, w = img.shape[:2]; esq = np.concatenate([img[:8, :8].reshape(-1, 3), img[:8, w-8:].reshape(-1, 3),
                                                img[h-8:, :8].reshape(-1, 3), img[h-8:, w-8:].reshape(-1, 3)])
    return np.median(esq, axis=0).astype(np.int16)


def dims(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                          "-of", "csv=p=0", video], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip().split(",")
    num, den = out[2].split("/"); return int(out[0]), int(out[1]), float(num) / float(den)


def cuadro(video, n, w, h, escala=1.0):
    vf = f"select=eq(n\\,{n})" + (f",scale={int(w*escala)}:{int(h*escala)}" if escala != 1 else "")
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", vf, "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    return np.frombuffer(out, np.uint8).reshape(int(h * escala), int(w * escala), 3)


def flujo(video, w, h, escala=1.0):
    vf = ["-vf", f"scale={int(w*escala)}:{int(h*escala)}"] if escala != 1 else []
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, *vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, bufsize=10 ** 8)
    ww, hh = int(w * escala), int(h * escala)
    while True:
        buf = p.stdout.read(ww * hh * 3)
        if len(buf) < ww * hh * 3:
            break
        yield np.frombuffer(buf, np.uint8).reshape(hh, ww, 3)
    p.wait()


def cmd_rastrear(a):
    W, H, fps = dims(a.video); PAD = a.pad
    comun.AVANCE_DIR = os.path.dirname(os.path.abspath(a.salida))
    total = max(1, int(round(comun.dur(a.video) * fps)))   # cuadros esperados: el flujo no sabe cuántos vienen
    tpl = cv2.imread(a.asset); bg = fondo_de(tpl); D = contenido(tpl, bg)
    ys, xs = np.where(D > 45); bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()); Dt = D[by0:by1 + 1, bx0:bx1 + 1]
    rx0, ry0, rx1, ry1 = [int(v) for v in a.region.split(",")] if a.region else (0, 0, W, H)
    e0, e1, paso = [float(v) for v in a.escalas.split(",")]
    def calibrar(n):
        Df = contenido(cuadro(a.video, n, W, H), bg)
        reg = cv2.copyMakeBorder(Df[ry0:ry1, rx0:rx1], 0, 0, PAD, 0, cv2.BORDER_CONSTANT, value=0); best = None
        for s in np.arange(e0, e1 + 1e-9, paso):
            t = cv2.resize(Dt, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            if t.shape[0] >= reg.shape[0] or t.shape[1] >= reg.shape[1]:
                continue
            r = cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED); _, mx, _, loc = cv2.minMaxLoc(r)
            if best is None or mx > best[0]:
                best = (round(float(mx), 3), round(float(s), 3), loc[0] - PAD + rx0, loc[1] + ry0)
        return best
    cal = {int(n): calibrar(int(n)) for n in a.calibrar.split(",")}
    for n, c in cal.items():
        print(f"calibración cuadro {n}: score {c[0]}, escala {c[1]}, x {c[2]}, y {c[3]}")
    escala = float(np.median([c[1] for c in cal.values()]))
    S = 0.5; t = cv2.resize(Dt, None, fx=escala * S, fy=escala * S, interpolation=cv2.INTER_AREA); th, tw = t.shape
    pad = int(PAD * S); mk = cv2.dilate((t > 20).astype(np.uint8), np.ones((5, 5), np.uint8))
    Y0, Y1, X0, X1 = int(ry0 * S), int(ry1 * S), int(rx0 * S), int(rx1 * S); filas = []
    for n, f in enumerate(flujo(a.video, W, H, S)):
        Df = contenido(f, bg)
        reg = cv2.copyMakeBorder(Df[Y0:Y1, X0:X1], 0, 0, pad, 0, cv2.BORDER_CONSTANT, value=0)
        r = cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED); _, mx, _, loc = cv2.minMaxLoc(r)
        x, y = loc[0] - pad + X0, loc[1] + Y0; xs0 = max(x, 0); dx = xs0 - x
        parche = Df[y:y + th, xs0:x + tw].astype(np.float32); tt = t[:, dx:dx + parche.shape[1]].astype(np.float32); fuerte = tt > 90
        op = float(np.median(parche[fuerte] / tt[fuerte])) if fuerte.sum() > 50 else 0.0
        Dz = Df.copy(); sub = Dz[y:y + th, xs0:x + tw]; sub[mk[:, dx:dx + sub.shape[1]] > 0] = 0
        cols = np.where((Dz[y:y + th, :] > 60).sum(0) > 2)[0]; cols = cols[cols > x + tw]
        filas.append({"n": n, "t": round(n / fps, 3), "score": round(float(mx), 3), "x": int(x / S), "y": int(y / S),
                      "op": round(op, 3), "margen": int(cols.min() / S) if len(cols) else W})
        if n % 30 == 0:
            comun.avance("rastreo", min(99.0, 100 * n / total), f"cuadro {n}/{total}")
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump({"escala": escala, "bbox_asset": [bx0, by0, bx1, by1], "plantilla": [int(tw / S), int(th / S)],
                   "fondo": [int(v) for v in bg], "video": [W, H, fps], "cuadros": filas}, f)
    comun.avance("rastreo", 100, f"{len(filas)} cuadros → {os.path.basename(a.salida)}", estado="listo")
    sc = np.array([r["score"] for r in filas]); pres = [r for r in filas if r["score"] > a.umbral]
    print(f"cuadros {len(filas)}; escala {escala}; score p5/p50/p95 {np.percentile(sc, [5, 50, 95]).round(3)}; presentes {len(pres)}")
    if pres:
        xm = collections.Counter(r["x"] for r in pres).most_common(1)[0][0]
        print(f"posición modal x={xm} y={collections.Counter(r['y'] for r in pres).most_common(1)[0][0]}; "
              f"cuadros desplazados {sum(1 for r in pres if r['x'] != xm)}; opacidad mín {min(r['op'] for r in pres):.2f}")


def _nuevo(ruta, escala):
    nv = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
    if nv is None or nv.shape[2] != 4:
        print("El PNG nuevo debe tener canal alfa.", file=sys.stderr); raise SystemExit(2)
    return cv2.resize(nv, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)


def cmd_solape(a):
    d = json.load(open(a.rastreo, encoding="utf-8")); filas = d["cuadros"]; W, H, fps = d["video"]; bg = np.array(d["fondo"], np.int16); tw, th = d["plantilla"]
    pres = [r for r in filas if r["score"] > a.umbral]; xm = collections.Counter(r["x"] for r in pres).most_common(1)[0][0]
    ym = collections.Counter(r["y"] for r in pres).most_common(1)[0][0]; base = ym + th; S = 0.5
    nv = cv2.imread(a.nuevo, cv2.IMREAD_UNCHANGED); cands = {}
    for c in a.candidatos.split(","):
        s, x = c.split(":"); s, x = float(s), int(x)
        al = cv2.resize(nv[:, :, 3], None, fx=s * S, fy=s * S, interpolation=cv2.INTER_AREA) > 128
        cands[(s, x)] = (al, int(round((base - a.pies * s) * S)), int(x * S))
    stats = {k: [] for k in cands}; ts = []
    for n, f in enumerate(flujo(a.video, W, H, S)):
        r = filas[n]
        if r["score"] <= a.umbral or r["x"] != xm:
            continue
        cont = contenido(f, bg) > 60; cont[int(ym*S) - 4:int((ym + th)*S) + 4, 0:int((xm + tw)*S) + 4] = False; ts.append(r["t"])
        for k, (al, y0, x0) in cands.items():
            h, w = al.shape; xs0 = max(x0, 0); sub = cont[y0:y0 + h, xs0:x0 + w]; aa = al[:sub.shape[0], xs0 - x0: xs0 - x0 + sub.shape[1]]
            stats[k].append(int((sub & aa).sum()) / (S * S))
    print("escala   x   alto  ancho  cuadros con solape  >1500px²  p90 px²  máx px²")
    for (s, x), v in stats.items():
        v = np.array(v); print(f"{s:5.2f} {x:4d}  {int(a.pies*s):4d}  {int(nv.shape[1]*s):4d}     {(v>0).mean()*100:5.1f} %        {(v>1500).mean()*100:5.1f} %   {np.percentile(v,90):6.0f}  {v.max():6.0f}")


def cmd_reemplazar(a):
    d = json.load(open(a.rastreo, encoding="utf-8")); filas = d["cuadros"]; W, H, fps = d["video"]; bg = np.array(d["fondo"], np.int16)
    bx0, by0, bx1, by1 = d["bbox_asset"]; esc_v = d["escala"]
    v = cv2.imread(a.viejo); Dv = contenido(v, bg)[by0:by1 + 1, bx0:bx1 + 1]
    mv = cv2.resize((Dv > 20).astype(np.uint8), None, fx=esc_v, fy=esc_v, interpolation=cv2.INTER_NEAREST)
    mv = cv2.dilate(mv, np.ones((11, 11), np.uint8)).astype(bool); mh, mw = mv.shape
    nv = _nuevo(a.nuevo, a.escala); nh, nw = nv.shape[:2]; alfa = nv[:, :, 3:4].astype(np.float32) / 255.0; rgb = nv[:, :, :3].astype(np.float32)
    pres = [r for r in filas if r["score"] > a.umbral]
    xm = collections.Counter(r["x"] for r in pres).most_common(1)[0][0]; ym = collections.Counter(r["y"] for r in pres).most_common(1)[0][0]
    y_nuevo = int(round(ym + mh - a.pies * a.escala))
    print(f"viejo: x modal {xm}, y {ym}, máscara {mw}x{mh}; nuevo: {nw}x{nh} en y {y_nuevo}, x reposo {a.x}")
    def procesar(frame, r):
        if r["score"] <= a.umbral:
            return frame
        fondo = np.median(frame[a.fondo_y0:a.fondo_y1, a.fondo_x0:a.fondo_x1].reshape(-1, 3), axis=0).astype(np.uint8)
        x, y = r["x"], r["y"]; x0, y0 = max(x, 0), max(y, 0); x1, y1 = min(x + mw, W), min(y + mh, H)
        if x1 > x0 and y1 > y0:
            sub = frame[y0:y1, x0:x1]; sub[mv[y0 - y:y1 - y, x0 - x:x1 - x]] = fondo
        nx, ny = a.x + (x - xm), y_nuevo; px0, py0 = max(nx, 0), max(ny, 0); px1, py1 = min(nx + nw, W), min(ny + nh, H)
        if px1 > px0 and py1 > py0:
            s = rgb[py0 - ny:py1 - ny, px0 - nx:px1 - nx]; al = alfa[py0 - ny:py1 - ny, px0 - nx:px1 - nx]
            reg = frame[py0:py1, px0:px1].astype(np.float32); frame[py0:py1, px0:px1] = (s * al + reg * (1 - al)).astype(np.uint8)
        return frame
    if a.muestras:
        # <salida.mp4> es el video final: las muestras van a una carpeta hermana para no ocupar su nombre.
        carpeta = os.path.splitext(a.salida)[0] + "_muestras" if re.search(r"\.(mp4|mov|webm|mkv)$", a.salida, re.I) else a.salida
        os.makedirs(carpeta, exist_ok=True)
        for n in [int(s) for s in a.muestras.split(",")]:
            f = cuadro(a.video, n, W, H).copy(); antes = f.copy(); f = procesar(f, filas[n])
            cv2.imwrite(os.path.join(carpeta, f"muestra-{n:04d}.png"), np.hstack([antes, f])); print("muestra", n, "t", filas[n]["t"])
        print(f"Muestras antes|después en {carpeta}/")
        return
    comun.AVANCE_DIR = os.path.dirname(os.path.abspath(a.rastreo))
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                            "-i", a.video, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", a.salida], stdin=subprocess.PIPE)
    total = len(filas); n = 0
    for f in flujo(a.video, W, H):
        f = f.copy()
        if n < total:
            f = procesar(f, filas[n])
        enc.stdin.write(f.tobytes()); n += 1
        if n % 30 == 0:
            comun.avance("reemplazo", 100 * n / total, f"cuadro {n}/{total}")
    enc.stdin.close(); enc.wait()
    if enc.returncode:
        raise SystemExit(1)
    comun.avance("reemplazo", 100, f"{n} cuadros → {os.path.basename(a.salida)}", estado="listo"); print(f"OK {n} cuadros → {a.salida}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rastrear"); r.add_argument("video"); r.add_argument("asset"); r.add_argument("--salida", required=True)
    r.add_argument("--region", help="x0,y0,x1,y1 de búsqueda a resolución completa"); r.add_argument("--pad", type=int, default=160, help="margen para assets parcialmente fuera por la izquierda")
    r.add_argument("--calibrar", default="300,1500,2400,3300", help="cuadros donde calibrar la escala"); r.add_argument("--escalas", default="0.55,1.0,0.005")
    r.add_argument("--umbral", type=float, default=0.45); r.set_defaults(fn=cmd_rastrear)
    s = sub.add_parser("solape"); s.add_argument("video"); s.add_argument("rastreo"); s.add_argument("nuevo"); s.add_argument("--candidatos", required=True)
    s.add_argument("--pies", type=int, required=True, help="fila de los pies en el PNG nuevo"); s.add_argument("--umbral", type=float, default=0.45); s.set_defaults(fn=cmd_solape)
    p = sub.add_parser("reemplazar"); p.add_argument("video"); p.add_argument("rastreo"); p.add_argument("viejo"); p.add_argument("nuevo"); p.add_argument("salida")
    p.add_argument("--escala", type=float, required=True); p.add_argument("--x", type=int, default=0); p.add_argument("--pies", type=int, required=True)
    p.add_argument("--muestras", default=""); p.add_argument("--umbral", type=float, default=0.45); p.add_argument("--crf", type=int, default=16)
    p.add_argument("--fondo-x0", type=int, default=400); p.add_argument("--fondo-x1", type=int, default=1000); p.add_argument("--fondo-y0", type=int, default=20); p.add_argument("--fondo-y1", type=int, default=80)
    p.set_defaults(fn=cmd_reemplazar)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
