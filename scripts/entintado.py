#!/usr/bin/env python3
"""entintado — firma del motor ilustrado: la ilustración «se dibuja» (tinta) y luego «se pinta» (lavado de color)
delante del espectador. Todo local y determinista (Pillow + FFmpeg), 0 USD.

La tinta se extrae de la MISMA imagen (no de una edición IA): así el último cuadro del revelado es la ilustración
original píxel a píxel y el paso a la toma no salta. Se usa un «sombrero negro» morfológico (cierre − luminancia), que
aísla los trazos oscuros y finos con una sola línea por trazo (la detección de bordes da doble línea y parece filtro),
más los negros muy profundos.

El orden del revelado sale de un mapa en gris precalculado: barrido diagonal + ruido de baja frecuencia (tinta) y
distancia radial + ruido (lavado de color, «acuarela que se expande»). Cada paso de animación (a `fps_animacion`, 12 =
«a doses») umbraliza el mapa con borde suave. El resultado es un MP4 corto que Remotion reproduce como un clip más:
sin máscaras SVG por cuadro ni imágenes que cargar dentro de SVG.

  python3 scripts/entintado.py <imagen.png> <salida.mp4> [--dur 1.5] [--ancho 1080 --alto 1920] [--tinta #26262b]
"""
import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zlib

from PIL import Image, ImageChops, ImageFilter, ImageOps

VERSION = 1           # súbela si cambia el algoritmo: invalida los MP4 en caché de los proyectos
FASE_TINTA = 0.6     # fracción del revelado que dura la tinta
INICIO_COLOR = 0.45  # el color empieza antes de que acabe la tinta (solapados se leen como un solo gesto)


def semilla_de(texto):
    return zlib.crc32(texto.encode("utf-8")) & 0xFFFF


def cubrir(im, ancho, alto):
    """Igual que `object-fit: cover` centrado (lo que hace <Img> en la composición)."""
    w, h = im.size
    k = max(ancho / w, alto / h)
    im = im.resize((max(ancho, round(w * k)), max(alto, round(h * k))), Image.LANCZOS)
    x, y = (im.width - ancho) // 2, (im.height - alto) // 2
    return im.crop((x, y, x + ancho, y + alto))


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def extraer_tinta(im, umbral=10, ganancia=6, negro=38):
    """Alfa (L) de los trazos de tinta: sombrero negro (cierre − L) + negros profundos."""
    lum = im.convert("L")
    k = max(3, (round(im.width / 120) // 2) * 2 + 1)            # ~9 px a 1080 de ancho: más ancho que un trazo
    cierre = lum.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    trazos = ImageChops.subtract(cierre, lum).point(lambda v: max(0, min(255, (v - umbral) * ganancia)))
    profundos = lum.point(lambda v: 255 if v < negro else max(0, int(255 - (v - negro) * 255 / 24)) if v < negro + 24 else 0)
    return ImageChops.lighter(trazos, profundos).filter(ImageFilter.GaussianBlur(0.6))


def mapa_orden(ancho, alto, semilla, modo="barrido"):
    """Mapa 0–255 (oscuro = se revela primero), ecualizado para que el área revelada crezca lineal en el tiempo."""
    rnd = random.Random(semilla)
    w, h = max(8, ancho // 5), max(8, alto // 5)
    gx, gy = 7, max(7, round(7 * alto / ancho))
    ruido = Image.new("L", (gx, gy))
    ruido.putdata([rnd.randrange(256) for _ in range(gx * gy)])
    ruido = ruido.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(w / 28))
    rv = ruido.load()
    base = Image.new("L", (w, h))
    bv = base.load()
    if modo == "barrido":
        ang = math.radians(rnd.uniform(25, 65))
        c, s = math.cos(ang), math.sin(ang)
        tot = w * c + h * s
        for y in range(h):
            for x in range(w):
                bv[x, y] = int(255 * (0.62 * (x * c + y * s) / tot + 0.38 * rv[x, y] / 255))
    else:
        cx, cy = w * rnd.uniform(0.4, 0.6), h * rnd.uniform(0.4, 0.55)
        rmax = math.hypot(max(cx, w - cx), max(cy, h - cy))
        for y in range(h):
            for x in range(w):
                bv[x, y] = int(255 * min(1.0, 0.6 * math.hypot(x - cx, y - cy) / rmax + 0.4 * rv[x, y] / 255))
    return ImageOps.equalize(base.resize((ancho, alto), Image.BICUBIC))


def lut_umbral(k, suavidad):
    """Máscara 255 donde orden < k (con borde suave de `suavidad` en unidades de orden). k=0 → nada, k=1 → todo."""
    kk = k * (1 + suavidad)
    return [max(0, min(255, int(255 * (kk - v / 255) / suavidad))) for v in range(256)]


def revelar(imagen, salida, *, dur=1.5, ancho=1080, alto=1920, tinta="#26262b", papel="#f3ead6", fps_animacion=12,
            semilla=0):
    """Escribe `salida` (MP4 30 fps, h264 yuv420p) con el revelado; el último cuadro es `imagen` cubierta a ancho×alto."""
    im = cubrir(Image.open(imagen).convert("RGB"), ancho, alto)
    alfa = extraer_tinta(im)
    orden = mapa_orden(ancho, alto, semilla, "barrido")
    lavado = mapa_orden(ancho, alto, semilla + 1, "radial")
    fondo = Image.new("RGB", (ancho, alto), hex_rgb(papel))
    solido = Image.new("RGB", (ancho, alto), hex_rgb(tinta))
    n = max(2, round(dur * fps_animacion))
    tmp = tempfile.mkdtemp(prefix="entintado_")
    try:
        for i in range(n + 1):
            k = i / n
            kt = min(1.0, k / FASE_TINTA)
            kc = max(0.0, min(1.0, (k - INICIO_COLOR) / (1 - INICIO_COLOR)))
            m_tinta = ImageChops.multiply(alfa, orden.point(lut_umbral(kt, 0.08)))
            cuadro = Image.composite(solido, fondo, m_tinta)
            if kc > 0:
                cuadro = Image.composite(im, cuadro, lavado.point(lut_umbral(kc, 0.22)))
            if i == n:
                cuadro = im
            cuadro.save(os.path.join(tmp, f"f{i:03d}.png"), compress_level=1)
        os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-framerate", str(fps_animacion),
                            "-i", os.path.join(tmp, "f%03d.png"), "-vf", "fps=30,format=yuv420p",
                            "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-g", "15",
                            "-movflags", "+faststart", salida], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-800:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return (n + 1) / fps_animacion


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("imagen")
    ap.add_argument("salida")
    ap.add_argument("--dur", type=float, default=1.5)
    ap.add_argument("--ancho", type=int, default=1080)
    ap.add_argument("--alto", type=int, default=1920)
    ap.add_argument("--tinta", default="#26262b")
    ap.add_argument("--papel", default="#f3ead6")
    a = ap.parse_args(argv)
    d = revelar(a.imagen, a.salida, dur=a.dur, ancho=a.ancho, alto=a.alto, tinta=a.tinta, papel=a.papel,
                semilla=semilla_de(os.path.basename(a.imagen)))
    print(f"OK -> {a.salida} · {d:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
