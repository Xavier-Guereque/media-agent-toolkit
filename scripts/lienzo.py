#!/usr/bin/env python3
"""lienzo — utilidades PIL para lienzos gráficos de reels sin fotos (tarjetas, UI simulada, datos, cierres con logos).

Se importa desde el script de cada proyecto (`proyectos/<slug>/recursos/generar_canvas.py`):

    import sys, os
    sys.path.insert(0, os.path.join(<repo>, "scripts"))
    import lienzo as lz
    img = lz.fondo_degradado(1080, 1920, (8, 12, 28), (17, 23, 48))
    img = lz.resplandor(img, (540, 820), 800, (0, 215, 255), 66)
    img = lz.con_capa(img, lambda d: lz.tarjeta(d, (112, 596, 968, 1204)))
    d = ImageDraw.Draw(img); d.text((540, 640), "TITULAR", font=lz.fuente(100), fill=(255, 255, 255), anchor="ma")

Recetas verificadas (skill `armar-reel` de [[SKILL]], [[Lecciones-2026-09-28-reel-fluke-webinar-cobre]]):
  - `Image.alpha_composite` DEVUELVE una imagen nueva: todas las funciones que componen regresan la imagen y hay que
    reasignarla (`img = con_capa(img, fn)`); si no, lo translúcido se pierde sin error.
  - Todo lo translúcido (tarjetas, pastillas, palomitas) va en UNA capa con `con_capa`; el texto opaco se dibuja al
    final encima, directo sobre `img`.
  - Sobre fondo oscuro los alfas bajos no se ven: tarjeta con relleno 20 y borde 72 (valores por defecto).
  - Logos que vienen sobre blanco (o lockups negros/dorados) van dentro de una pastilla blanca (`logos_en_pastilla`);
    antes, recortarlos al contenido con `recortar_a_contenido`.
  - Con Ken Burns (`zoom_max` 1.10) el recorte es ~49 px por lado y ~87 px arriba/abajo en 1080x1920: verifica con
    `textos_caben` que ningún texto se salga de su contenedor.
Determinista: misma entrada → mismos píxeles. Solo Pillow.
"""
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

try:
    REMUESTREO = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    REMUESTREO = getattr(Image, "LANCZOS")

# Primero las de macOS (las verificadas); luego equivalentes de Linux y Windows.
FUENTES = {
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/System/Library/Fonts/HelveticaNeue.ttc",
             "/System/Library/Fonts/Supplemental/Arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf"],
    "regular": ["/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/HelveticaNeue.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
                "C:/Windows/Fonts/arial.ttf"],
}

VERDE = (34, 197, 94)
BLANCO = (255, 255, 255)
RELLENO_TARJETA = (255, 255, 255, 20)
BORDE_TARJETA = (255, 255, 255, 72)

_cache_fuentes = {}


def fuente(tam, peso="bold", rutas=None):
    """Primera fuente TrueType disponible de `rutas` (o de FUENTES[peso]); la de PIL si no hay ninguna."""
    rutas = tuple(rutas or FUENTES[peso])
    clave = (tam, rutas)
    if clave not in _cache_fuentes:
        f = None
        for p in rutas:
            if os.path.exists(p):
                try:
                    f = ImageFont.truetype(p, tam)
                    break
                except OSError:
                    continue
        _cache_fuentes[clave] = f or ImageFont.load_default()
    return _cache_fuentes[clave]


def fondo_degradado(w, h, arriba, abajo):
    """Degradado vertical RGB `arriba` → `abajo`, devuelto en RGBA (listo para alpha_composite)."""
    columna = Image.new("RGB", (1, h))
    px = columna.load()
    for y in range(h):
        t = y / (h - 1) if h > 1 else 0
        px[0, y] = tuple(int(arriba[i] + (abajo[i] - arriba[i]) * t) for i in range(3))
    return columna.resize((w, h), Image.NEAREST).convert("RGBA")


def _capa(img):
    return Image.new("RGBA", img.size, (0, 0, 0, 0))


def resplandor(img, centro, radio, color, alfa, pasos=42):
    """Glow radial suave (círculos concéntricos con caída cuadrática). Devuelve la imagen nueva."""
    capa = _capa(img)
    d = ImageDraw.Draw(capa)
    for i in range(pasos, 0, -1):
        r = radio * i / pasos
        a = int(alfa * (1 - i / pasos) ** 2.1)
        if a > 0:
            d.ellipse([centro[0] - r, centro[1] - r, centro[0] + r, centro[1] + r], fill=tuple(color) + (a,))
    return Image.alpha_composite(img, capa)


def destello(img, centro, n, rmin, rmax, color, alfa, grosor=2):
    """Líneas radiales (starburst) de intro; alterna alfa completo y medio. Devuelve la imagen nueva."""
    capa = _capa(img)
    d = ImageDraw.Draw(capa)
    for k in range(n):
        ang = 2 * math.pi * k / n + 0.12
        a = alfa if k % 2 == 0 else int(alfa * 0.5)
        d.line([centro[0] + rmin * math.cos(ang), centro[1] + rmin * math.sin(ang),
                centro[0] + rmax * math.cos(ang), centro[1] + rmax * math.sin(ang)],
               fill=tuple(color) + (a,), width=grosor)
    return Image.alpha_composite(img, capa)


def con_capa(img, fn):
    """Dibuja `fn(ImageDraw)` en una capa translúcida y la compone. DEVUELVE la imagen nueva (hay que reasignar)."""
    capa = _capa(img)
    fn(ImageDraw.Draw(capa))
    return Image.alpha_composite(img, capa)


def tarjeta(d, caja, radio=44, relleno=RELLENO_TARJETA, borde=BORDE_TARJETA, grosor=3):
    """Tarjeta redondeada translúcida (usar dentro de `con_capa`)."""
    d.rounded_rectangle(caja, radius=radio, fill=relleno, outline=borde, width=grosor)


def pastilla(d, caja, relleno, borde, radio=None, grosor=3):
    """Pastilla (pill); por defecto radio = media altura."""
    r = radio if radio is not None else (caja[3] - caja[1]) // 2
    d.rounded_rectangle(caja, radius=r, fill=relleno, outline=borde, width=grosor)


def palomita(d, cx, cy, r=22, color=VERDE):
    """Círculo con palomita (check) de lista de beneficios (usar dentro de `con_capa`)."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(color) + (52,), outline=tuple(color) + (255,), width=3)
    d.line([cx - 10, cy + 1, cx - 3, cy + 9], fill=tuple(color) + (255,), width=5)
    d.line([cx - 3, cy + 9, cx + 11, cy - 8], fill=tuple(color) + (255,), width=5)


def logos_en_pastilla(img, caja, logos, radio=28, pad=30, sep=46, fondo=BLANCO):
    """Pastilla (blanca por defecto) con varios logos en fila, centrados verticalmente.

    `logos`: [(ruta_png, alto_relativo), …]; alto_relativo es la fracción del alto útil (caja − 2·pad), p. ej.
    [("aliado.png", 0.82), ("marca.png", 0.66)]. Si no caben a lo ancho, se escalan todos en bloque (con la
    separación) para conservar la proporción entre ellos. Devuelve la imagen nueva."""
    img = con_capa(img, lambda d: d.rounded_rectangle(caja, radius=radio, fill=tuple(fondo) + (255,)))
    alto = (caja[3] - caja[1]) - 2 * pad
    piezas = []
    for ruta, rel in logos:
        im = Image.open(ruta).convert("RGBA")
        h = int(alto * rel)
        piezas.append([im, int(im.width * h / im.height), h])
    ancho = caja[2] - caja[0] - 2 * pad
    total = sum(p[1] for p in piezas) + sep * (len(piezas) - 1)
    if total > ancho:
        k = ancho / total
        for p in piezas:
            p[1], p[2] = int(p[1] * k), int(p[2] * k)
        sep = int(sep * k)
        total = sum(p[1] for p in piezas) + sep * (len(piezas) - 1)
    x = caja[0] + ((caja[2] - caja[0]) - total) // 2
    yc = (caja[1] + caja[3]) // 2
    for im, w, h in piezas:
        img.alpha_composite(im.resize((w, h), REMUESTREO), (x, yc - h // 2))
        x += w + sep
    return img


def recortar_a_contenido(entrada, salida, umbral=244, margen=6):
    """Recorta un PNG al bbox de los píxeles no blancos (cualquier canal < umbral) más `margen`, o al de los no
    transparentes si trae alfa. Útil tras `qlmanage -t -s 2000` de un SVG. Devuelve el tamaño final (w, h)."""
    im = Image.open(entrada)
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        bbox = im.convert("RGBA").getbbox()
        rec = im.convert("RGBA").crop(bbox) if bbox else im.convert("RGBA")
    else:
        rgb = im.convert("RGB")
        # un píxel cuenta si CUALQUIER canal está bajo el umbral → máximo de las tres máscaras
        r, g, b = rgb.point(lambda v: 255 if v < umbral else 0).split()
        bbox = ImageChops.lighter(ImageChops.lighter(r, g), b).getbbox()
        if bbox:  # getbbox es exclusivo a la derecha/abajo
            x0, y0, x1, y1 = bbox
            bbox = (x0 - margen, y0 - margen, x1 + margen, y1 + margen)
        rec = rgb.crop(bbox) if bbox else rgb
    rec.save(salida)
    return rec.size


def textos_caben(pruebas, centro_x=None):
    """Mide textos contra su límite derecho. `pruebas`: [(nombre, texto, fuente, x, limite), …].

    Si `centro_x` se da y x == centro_x, el texto se considera centrado (ancla "ma"/"mm") y el ancho útil es
    2·(limite − centro_x). Devuelve [(nombre, ok, ancho_px, fin_px, limite)]; no imprime."""
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    res = []
    for nombre, txt, f, x, lim in pruebas:
        w = d.textlength(txt, font=f)
        if centro_x is not None and x == centro_x:
            ok, fin = w <= 2 * (lim - centro_x), centro_x + w / 2
        else:
            ok, fin = x + w <= lim, x + w
        res.append((nombre, ok, int(w), int(fin), lim))
    return res
