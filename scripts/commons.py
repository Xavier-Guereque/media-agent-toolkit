#!/usr/bin/env python3
"""commons — fotos libres de Wikimedia Commons para un proyecto, con licencia verificada por archivo y atribución.

Uso:
  python3 scripts/commons.py buscar <consultas.json> <dir_busqueda> [--por-consulta 8] [--min-ancho 800] [--sin-hoja]
      consultas.json: {"clave": "texto de búsqueda", …}. Escribe <dir>/candidatos.json, <dir>/thumbs/<clave>_<i>.jpg
      y, si hay Pillow, <dir>/hoja_<n>.png (hoja de contactos con el índice de cada miniatura).
  python3 scripts/commons.py bajar <elegidas.json> <dir_busqueda>/candidatos.json <dir_img> [--pausa 5]
      elegidas.json: {"nombre_destino": "clave_i", …}. Descarga a <dir_img>/<nombre>.<ext> y FUSIONA la atribución en
      <dir_img>/creditos.json ({nombre: {archivo, titulo, pagina, autor, licencia, licencia_url, credito, w, h}}).

Módulo: `autor_corto`, `licencia_corta`, `credito_foto` (rótulo junto a la foto) y `credito_lista` (créditos
finales) arman los créditos en pantalla desde creditos.json.

Solo licencias libres: dominio público, CC0, CC BY, CC BY-SA (`extmetadata.LicenseShortName`); CC BY y BY-SA exigen
crédito en pantalla. Ritmo que exige Commons (medido 2026-10-31, [[Lecciones-2026-10-31-star-trek-cronologia]]): ~20
consultas seguidas al API dan 429 → 2.5 s entre consultas; las miniaturas grandes (≥ 2560 px) se bloquean mucho antes
que los originales → se baja el ORIGINAL si mide ≤ 4700 px y el thumb de 1600 solo para gigapíxeles; 5 s entre
descargas y reintentos con espera creciente. Solo librería estándar (+ Pillow opcional para la hoja).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "media-agent-toolkit/1.0 (https://github.com/Xavier-Guereque/media-agent-toolkit; educational video)"   # solo ASCII (latin-1); Wikimedia pide un contacto real en el UA
API = "https://commons.wikimedia.org/w/api.php"
LIBRES = re.compile(r"^(Public domain|CC0.*|CC BY( |-SA )?\d(\.\d)?.*|CC-BY(-SA)?.*|CC BY \d\.\d|CC BY-SA \d\.\d)$", re.I)
PAUSA_CONSULTA = 2.5
PAUSA_DESCARGA = 5.0
MAX_ORIGINAL = 4700          # px de ancho: por encima, thumb de 1600 (el thumbor rechaza gigapíxeles)


def get(params, timeout=60):
    params.update({"format": "json", "formatversion": "2"})
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def bajar_bytes(url, intentos=3, espera=20):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == intentos - 1:
                raise
            print(f"   429 en {url.rsplit('/', 1)[-1][:50]}: espero {espera * (i + 1)} s", file=sys.stderr, flush=True)
            time.sleep(espera * (i + 1))
    return None


def limpiar(em, k, n=160):
    return re.sub("<[^>]+>", "", (em.get(k) or {}).get("value", "")).strip()[:n]


# ---------------------------------------------------------------- buscar
def buscar(consultas, salida, por_consulta=8, min_ancho=800, hoja=True):
    os.makedirs(os.path.join(salida, "thumbs"), exist_ok=True)
    ruta = os.path.join(salida, "candidatos.json")
    cands = json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else {}
    for clave, q in consultas.items():
        if clave in cands:
            continue
        for intento in range(3):
            try:
                d = get({"action": "query", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": "6",
                         "gsrlimit": "12", "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": "320"})
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or intento == 2:
                    print(f"!! {clave}: HTTP {e.code}", file=sys.stderr)
                    d = {}
                    break
                time.sleep(30 * (intento + 1))
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"!! {clave}: {e}", file=sys.stderr)
                d = {}
                break
        items = []
        for p in (d.get("query", {}).get("pages") or []):
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            lic = limpiar(em, "LicenseShortName", 60)
            if not LIBRES.match(lic) or ii.get("width", 0) < min_ancho or not (ii.get("mime") or "").startswith("image/"):
                continue
            items.append({"titulo": p["title"], "licencia": lic, "autor": limpiar(em, "Artist", 120),
                          "w": ii.get("width"), "h": ii.get("height"), "url": ii.get("url"), "thumb": ii.get("thumburl"),
                          "pagina": ii.get("descriptionurl"), "desc": limpiar(em, "ImageDescription", 160), "mime": ii.get("mime")})
            if len(items) >= por_consulta:
                break
        cands[clave] = items
        print(f"{clave}: {len(items)} libres", flush=True)
        json.dump(cands, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(PAUSA_CONSULTA)
    n = 0
    for clave, items in cands.items():
        for i, it in enumerate(items):
            dst = os.path.join(salida, "thumbs", f"{clave}_{i}.jpg")
            if it.get("thumb") and not os.path.exists(dst):
                try:
                    open(dst, "wb").write(bajar_bytes(it["thumb"]))
                    n += 1
                except Exception as e:  # noqa: BLE001
                    print(f"!! thumb {clave}_{i}: {str(e)[:80]}", file=sys.stderr)
                time.sleep(0.4)
    print(f"candidatos: {sum(len(v) for v in cands.values())} en {len(cands)} consultas · miniaturas nuevas: {n}")
    if hoja:
        hojas(cands, salida)
    return cands


def hojas(cands, salida, cols=8, w=240, h=180, por_hoja=48):
    try:
        from PIL import Image, ImageDraw  # noqa: PLC0415
    except ImportError:
        print("sin Pillow: no se arma la hoja de contactos (usa ~/.venvs/imagen o revisa thumbs/)", file=sys.stderr)
        return
    celdas = [(clave, i) for clave, items in cands.items() for i in range(len(items))]
    for n in range(0, len(celdas), por_hoja):
        sub = celdas[n:n + por_hoja]
        filas = (len(sub) + cols - 1) // cols
        hoja = Image.new("RGB", (cols * w, filas * (h + 18)), "#101010")
        d = ImageDraw.Draw(hoja)
        for k, (clave, i) in enumerate(sub):
            x, y = (k % cols) * w, (k // cols) * (h + 18)
            p = os.path.join(salida, "thumbs", f"{clave}_{i}.jpg")
            try:
                im = Image.open(p).convert("RGB")
                im.thumbnail((w - 4, h - 4))
                hoja.paste(im, (x + 2, y + 18))
            except Exception:  # noqa: BLE001
                pass
            d.text((x + 4, y + 3), f"{clave}_{i}", fill="#ffffff")
        ruta = os.path.join(salida, f"hoja_{n // por_hoja + 1}.png")
        hoja.save(ruta)
        print("hoja:", ruta, hoja.size)


# ---------------------------------------------------------------- bajar
def bajar(elegidas, cands, dir_img):
    os.makedirs(dir_img, exist_ok=True)
    ruta_cred = os.path.join(dir_img, "creditos.json")
    creditos = json.load(open(ruta_cred, encoding="utf-8")) if os.path.exists(ruta_cred) else {}
    pendientes = {}
    for dest, ref in elegidas.items():
        if dest in creditos and os.path.exists(os.path.join(dir_img, creditos[dest]["archivo"])):
            continue
        clave, idx = ref.rsplit("_", 1)
        try:
            pendientes[cands[clave][int(idx)]["titulo"]] = dest
        except (KeyError, IndexError, ValueError):
            print(f"!! {dest}: referencia {ref} no existe en candidatos", file=sys.stderr)
    titulos = list(pendientes)
    fallidas = []
    for i in range(0, len(titulos), 20):
        lote = titulos[i:i + 20]
        d = get({"action": "query", "titles": "|".join(lote), "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime",
                 "iiurlwidth": "1600"})
        for p in d["query"]["pages"]:
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            dest = pendientes.get(p["title"])
            if not dest or not ii.get("url"):
                continue
            grande = ii.get("width", 0) > MAX_ORIGINAL
            url = ii.get("thumburl") if grande else ii["url"]
            ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".jpg"
            archivo = dest + ext
            try:
                datos = bajar_bytes(url)
                open(os.path.join(dir_img, archivo), "wb").write(datos)
            except Exception as e:  # noqa: BLE001
                print(f"!! {dest}: {str(e)[:100]}", file=sys.stderr, flush=True)
                fallidas.append(dest)
                time.sleep(PAUSA_DESCARGA)
                continue
            creditos[dest] = {"archivo": archivo, "titulo": p["title"], "pagina": ii.get("descriptionurl"),
                              "autor": limpiar(em, "Artist", 120), "licencia": limpiar(em, "LicenseShortName", 60),
                              "licencia_url": limpiar(em, "LicenseUrl", 120), "credito": limpiar(em, "Credit", 160),
                              "w": (ii.get("thumbwidth") if grande else ii.get("width")),
                              "h": (ii.get("thumbheight") if grande else ii.get("height"))}
            print(f"{dest:26s} {creditos[dest]['licencia']:16s} {creditos[dest]['w']}x{creditos[dest]['h']}  {creditos[dest]['autor'][:40]}", flush=True)
            json.dump(creditos, open(ruta_cred, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            time.sleep(PAUSA_DESCARGA)
        time.sleep(PAUSA_CONSULTA)
    json.dump(creditos, open(ruta_cred, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"créditos: {len(creditos)} · nuevas: {len(pendientes) - len(fallidas)} · fallidas: {', '.join(fallidas) or 'ninguna'}")
    return fallidas


# ---------------------------------------------------------------- créditos en pantalla
def autor_corto(autor, largo=40):
    """Autor de creditos.json recortado para pantalla: primera línea, sin "from …", paréntesis ni coautores."""
    a = (autor or "").split("\n")[0]
    a = re.split(r"\s+from\s+|\s*\(|,", a)[0].strip()
    return a[:largo] or "autor desconocido"


def licencia_corta(licencia):
    """"Public domain…" → "Dominio público"; el resto, tal cual (CC BY 4.0, CC BY-SA 3.0, CC0…)."""
    return "Dominio público" if (licencia or "").lower().startswith("public domain") else licencia


def credito_foto(c):
    """Rótulo junto a la foto (CC BY y BY-SA lo exigen en pantalla): "Foto: <autor> · <licencia>"."""
    return f"Foto: {autor_corto(c['autor'])} · {licencia_corta(c['licencia'])}"


def credito_lista(c, largo_titulo=48):
    """Línea para los créditos finales: "<título> — <autor> — <licencia> · Wikimedia Commons"."""
    titulo = re.sub(r"^File:", "", c["titulo"]).rsplit(".", 1)[0][:largo_titulo]
    return f"{titulo} — {autor_corto(c['autor'])} — {licencia_corta(c['licencia'])} · Wikimedia Commons"


def main(argv):
    global PAUSA_DESCARGA
    if len(argv) < 2 or argv[0] not in ("buscar", "bajar"):
        raise SystemExit(__doc__)
    flags = {a for a in argv if a.startswith("--") and "=" not in a}
    pos = [a for a in argv[1:] if not a.startswith("--")]
    opt = lambda k, d: next((argv[i + 1] for i, a in enumerate(argv) if a == k and i + 1 < len(argv)), d)
    if argv[0] == "buscar":
        consultas = json.load(open(pos[0], encoding="utf-8"))
        buscar(consultas, pos[1], int(opt("--por-consulta", 8)), int(opt("--min-ancho", 800)), "--sin-hoja" not in flags)
    else:
        PAUSA_DESCARGA = float(opt("--pausa", PAUSA_DESCARGA))
        elegidas = json.load(open(pos[0], encoding="utf-8"))
        cands = json.load(open(pos[1], encoding="utf-8"))
        fallidas = bajar(elegidas, cands, pos[2])
        raise SystemExit(4 if fallidas else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
