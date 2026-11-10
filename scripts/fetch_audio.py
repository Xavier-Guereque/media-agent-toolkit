#!/usr/bin/env python3
"""fetch_audio — busca y descarga música y efectos de sonido SOLO CC0 1.0 (Openverse / Freesound).

Política dura: la única licencia aceptada es CC0 1.0 (uso comercial, sin atribución obligatoria,
modificable). Cada item se verifica individualmente (`license.lower() == "cc0"` y URL de licencia
de dominio público) además de pedirlo en la consulta; lo que no cumple se descarta y se cuenta.
El filtro nunca se relaja para "obtener más resultados". Detalles en docs/Audio-CC0.md.

Hechos de las APIs verificados 2026-09 (no re-investigar):
  - Openverse `https://api.openverse.org/v1/audio/`: anónima, ~100 req/día. CC0 se pide con
    `license=cc0&license_type=all-cc` (license_type no acepta licencias finas → HTTP 400).
  - NUNCA combinar `category` con `license`: en el índice son conjuntos disjuntos (0 resultados).
  - Con CC0 casi todo viene de Freesound: efectos, loops y jingles cortos. Música larga CC0 no
    existe en la práctica (el catálogo musical está indexado como BY / BY-NC-ND).
  - Freesound solo con `FREESOUND_TOKEN` (gratis); con token simple se bajan previews HQ mp3.

Uso (CLI):
  python3 scripts/fetch_audio.py "whoosh transition" -n 6 --profile sfx
  python3 scripts/fetch_audio.py "click ui" -n 4 --profile sfx --max-dur 1
  python3 scripts/fetch_audio.py "riser" -n 3 --profile bgm --out proyectos/<slug>/recursos/audio
  python3 scripts/fetch_audio.py --verificar        # sha256 del manifest contra el disco

Uso (importado), el patrón del motor promo:
  from fetch_audio import obtener, ErrorRed
  try:
      cues = obtener("whoosh transition", n=2, perfil="sfx")   # cache primero
  except ErrorRed:
      cues = []                                                # → respaldo procedural
  ruta = cues[0]["ruta"] if cues else None

Salida en --out (default `config.json > audio_cc0.salida` o ~/Music/media-stock):
  <slug>_<n>.<ext>  audios (nunca se sobreescribe: sufijo numérico libre)
  credits.csv       una fila por archivo (append; encabezado solo al crear el archivo)
  manifest.json     {"politica_licencia": "CC0 1.0 unicamente", "items": [...]} con sha256

Códigos de salida: 0 ok · 1 rechazo de política (--license ≠ cc0) o sin resultados CC0 ·
2 uso/configuración (argumentos, falta FREESOUND_TOKEN, manifest ilegible) ·
3 verificación sha256 fallida · 4 falla de red/API tras reintentos.

Solo librería estándar. Nunca imprime el contenido del .env ni el token.
"""
import argparse
import collections
import contextlib
import csv
import datetime
import hashlib
import http.client
import itertools
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

try:
    import fcntl  # candado entre procesos para manifest/credits (macOS/Linux)
except ImportError:  # pragma: no cover
    fcntl = None

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LICENCIA = "cc0"
LICENCIA_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
POLITICA = "CC0 1.0 unicamente"
SALIDA_DEFAULT = "~/Music/media-stock"
USER_AGENT = "media-agent-toolkit/1.0 (+CC0 audio fetch)"

OPENVERSE_API = "https://api.openverse.org/v1/audio/"
OPENVERSE_PAGINA = 20  # máximo para uso anónimo
FREESOUND_API = "https://freesound.org/apiv2/search/text/"
FREESOUND_HOST = "freesound.org"  # único host que recibe el token
FREESOUND_PAGINA = 30
FREESOUND_FILTRO = 'license:"Creative Commons 0"'

PERFILES = {"sfx": (None, 6.0), "bgm": (30.0, None), "any": (None, None)}  # (min_s, max_s)
FUENTES = ("openverse", "freesound")

TIMEOUT_API = 30
TIMEOUT_DESCARGA = 90
REINTENTOS = 4
ESPERA_BASE = 1.5          # backoff exponencial: 1.5 s, 3 s, 6 s…
ESPERA_MAX = 30            # Retry-After mayor = límite (diario) agotado → fallar rápido
PAUSA_PAGINAS = 0.5        # cortesía entre páginas de la API
MIN_BYTES = 1024           # ≤1 KB = archivo corrupto o página de error
MAX_BYTES = 50 * 1024 * 1024
MARGEN_REPOSICION = 2      # items de reserva (de páginas ya pedidas) por si una descarga falla

EXT_AUDIO = ("mp3", "wav", "ogg", "oga", "flac", "m4a", "aac", "opus", "aif", "aiff", "webm")
TIPO_A_EXT = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
              "audio/wave": "wav", "audio/vnd.wave": "wav", "audio/ogg": "ogg", "audio/flac": "flac",
              "audio/x-flac": "flac", "audio/mp4": "m4a", "audio/aac": "aac", "audio/opus": "opus",
              "audio/aiff": "aiff", "audio/x-aiff": "aiff", "audio/webm": "webm"}
TIPOS_NO_AUDIO = ("text/", "application/json", "application/xml", "application/xhtml")

CAMPOS_ITEM = ("id", "titulo", "autor", "licencia", "licencia_url", "origen_url", "descarga_url",
               "duracion_s", "formato", "proveedor", "api", "consulta")
CAMPOS_CSV = ["archivo", "id", "titulo", "autor", "licencia", "licencia_url", "origen_url",
              "duracion_s", "proveedor", "consulta", "bytes", "sha256", "fecha"]

AVISO_BGM = ("Música larga CC0 prácticamente no existe vía Openverse (el catálogo musical está "
             "indexado como BY / BY-NC-ND): espera loops, pads y jingles cortos de Freesound. "
             "Respaldo: cama procedural del motor o loop con ffmpeg (-stream_loop), ver docs/Audio-CC0.md.")

Respuesta = collections.namedtuple("Respuesta", "codigo tipo cuerpo reintentar_en")


class ErrorRed(Exception):
    """Falla de red o de la API tras los reintentos (CLI: exit 4)."""


class ErrorConfig(Exception):
    """Uso o configuración inválidos: falta token, manifest ilegible… (CLI: exit 2)."""


class _Descarte(Exception):
    """La descarga no es un audio válido (≤1 KB, HTML/JSON, demasiado grande)."""


# ---------------------------------------------------------------- configuración
def cargar_config():
    try:
        with open(os.path.join(REPO_ROOT, "config.json"), encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def salida_por_defecto():
    """`config.json > audio_cc0.salida` si existe (relativa a la raíz del repo), si no ~/Music/media-stock."""
    cfg = cargar_config().get("audio_cc0")
    ruta = cfg.get("salida") if isinstance(cfg, dict) else None
    ruta = os.path.expanduser(ruta if isinstance(ruta, str) and ruta.strip() else SALIDA_DEFAULT)
    return os.path.abspath(ruta if os.path.isabs(ruta) else os.path.join(REPO_ROOT, ruta))


def _token_freesound():
    """FREESOUND_TOKEN del entorno o del .env del repo. Nunca se imprime."""
    v = os.environ.get("FREESOUND_TOKEN", "").strip()
    if v:
        return v
    try:
        with open(os.path.join(REPO_ROOT, ".env"), encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea.startswith("FREESOUND_TOKEN="):
                    return linea.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


# ---------------------------------------------------------------- red
class _SoloHttps(urllib.request.HTTPRedirectHandler):
    """Sigue redirecciones solo hacia https y no reenvía el token a otro host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destino = urllib.parse.urlparse(newurl)
        if destino.scheme != "https":
            raise urllib.error.URLError(f"redirección no https rechazada ({destino.scheme}://{destino.hostname})")
        nuevo = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nuevo is not None and destino.hostname != urllib.parse.urlparse(req.full_url).hostname:
            nuevo.remove_header("Authorization")
        return nuevo


_OPENER = urllib.request.build_opener(_SoloHttps)


def _dormir(segundos):
    """Pausa entre reintentos/páginas (los tests la sustituyen para no esperar)."""
    time.sleep(segundos)


def _retry_after(cabeceras):
    try:
        v = cabeceras.get("Retry-After") if cabeceras is not None else None
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None  # formato fecha HTTP: se ignora y manda el backoff


def http_get(url, cabeceras=None, timeout=TIMEOUT_API):
    """Única puerta a la red (los tests la sustituyen). GET → `Respuesta`.

    Los códigos HTTP de error se DEVUELVEN para que `_pedir` decida si reintenta; los fallos de
    conexión/timeout se lanzan (OSError / http.client.HTTPException).
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(cabeceras or {})})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return Respuesta(r.status, r.headers.get("Content-Type", ""), r.read(MAX_BYTES + 1), None)
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read(2048)
        except (OSError, http.client.HTTPException):
            cuerpo = b""
        tipo = e.headers.get("Content-Type", "") if e.headers is not None else ""
        return Respuesta(e.code, tipo, cuerpo, _retry_after(e.headers))


def _host(url):
    try:
        return urllib.parse.urlparse(url or "").hostname or "?"
    except ValueError:
        return "?"


def _es_https(url):
    try:
        p = urllib.parse.urlparse(url or "")
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.hostname)


def _extracto(cuerpo):
    return re.sub(r"\s+", " ", (cuerpo or b"")[:400].decode("utf-8", "replace")).strip()[:160]


def _pedir(url, cabeceras=None, timeout=TIMEOUT_API, reintentos=REINTENTOS):
    """GET con la política de red: solo https; 429/5xx y fallos de conexión → backoff exponencial
    (respeta Retry-After ≤30 s); el resto de 4xx falla de inmediato. Lanza ErrorRed al agotar."""
    if not _es_https(url):
        raise ErrorRed(f"URL rechazada (solo https): {_host(url)}")
    host, espera, motivo = _host(url), ESPERA_BASE, ""
    for intento in range(1, reintentos + 1):
        pausa = espera
        try:
            r = http_get(url, cabeceras, timeout)
        except (OSError, http.client.HTTPException) as e:  # URLError y timeouts son OSError
            motivo = f"sin conexión con {host} ({getattr(e, 'reason', e)})"
        else:
            if 200 <= r.codigo < 300:
                return r
            if r.codigo != 429 and r.codigo < 500:
                raise ErrorRed(f"HTTP {r.codigo} de {host}: {_extracto(r.cuerpo)}")
            motivo = f"HTTP {r.codigo} de {host}"
            if r.reintentar_en:
                if r.reintentar_en > ESPERA_MAX:
                    raise ErrorRed(f"{motivo}: límite de peticiones agotado (Retry-After {r.reintentar_en:.0f} s)")
                pausa = max(pausa, r.reintentar_en)
        if intento < reintentos:
            _dormir(pausa)
            espera *= 2
    raise ErrorRed(f"{motivo} tras {reintentos} intentos")


def _json(url, cabeceras=None):
    r = _pedir(url, cabeceras)
    try:
        datos = json.loads(r.cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErrorRed(f"respuesta no JSON de {_host(url)}") from e
    if not isinstance(datos, dict):
        raise ErrorRed(f"respuesta inesperada de {_host(url)}")
    return datos


# ---------------------------------------------------------------- normalización
def _texto(v, maximo=200):
    """Texto de terceros apto para terminal/CSV: sin controles ni saltos, recortado."""
    if v is None:
        return ""
    s = re.sub(r"\s+", " ", str(v))
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s).strip()[:maximo]


def _norm_consulta(q):
    return _texto(q).lower()


def slug(titulo, maximo=60):
    """Título saneado para nombre de archivo: ascii, minúsculas, [a-z0-9-], ≤60 chars."""
    t = unicodedata.normalize("NFKD", _texto(titulo)).encode("ascii", "ignore").decode()
    t = re.sub(r"\.(%s)$" % "|".join(EXT_AUDIO), "", t, flags=re.I)  # "Woosh_02.wav" → "Woosh_02"
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t[:maximo].rstrip("-") or "audio"


def _formato(filetype, url):
    f = (filetype or "").lower().lstrip(".")
    if f in EXT_AUDIO:
        return f
    try:
        ext = os.path.splitext(urllib.parse.urlparse(url or "").path)[1].lower().lstrip(".")
    except ValueError:
        ext = ""
    return ext if ext in EXT_AUDIO else ""


def _duracion(valor, divisor=1.0):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
        return None
    return round(valor / divisor, 2)


def _id_respaldo(url):
    return "url-" + hashlib.sha1((url or "").encode()).hexdigest()[:16]


def _normalizar_openverse(it, consulta):
    url = it.get("url") or ""
    return {
        "id": str(it.get("id") or "") or _id_respaldo(url),
        "titulo": _texto(it.get("title")) or "audio",
        "autor": _texto(it.get("creator")) or "desconocido",
        "licencia": (it.get("license") or "").lower(),  # verificación literal: license.lower() == "cc0"
        "licencia_url": it.get("license_url") or "",
        "origen_url": it.get("foreign_landing_url") or "",
        "descarga_url": url,
        "duracion_s": _duracion(it.get("duration"), 1000.0),  # Openverse: milisegundos
        "formato": _formato(it.get("filetype"), url),
        "proveedor": _texto(it.get("provider") or it.get("source"), 60),
        "api": "openverse",
        "consulta": consulta,
    }


def _licencia_freesound(valor):
    """Freesound entrega la licencia como URL o nombre; solo 'publicdomain/zero' es CC0."""
    v = (valor or "").strip().lower()
    if "publicdomain/zero" in v or v in ("creative commons 0", "cc0"):
        return LICENCIA
    return v or "desconocida"


def _normalizar_freesound(it, consulta):
    lic = _licencia_freesound(it.get("license"))
    url = (it.get("previews") or {}).get("preview-hq-mp3") or ""
    return {
        "id": f"freesound-{it['id']}" if it.get("id") is not None else _id_respaldo(url),
        "titulo": _texto(it.get("name")) or "audio",
        "autor": _texto(it.get("username")) or "desconocido",
        "licencia": lic,
        "licencia_url": LICENCIA_URL if lic == LICENCIA else (it.get("license") or ""),
        "origen_url": it.get("url") or "",
        "descarga_url": url,
        "duracion_s": _duracion(it.get("duration")),  # Freesound: segundos
        "formato": "mp3",
        "proveedor": "freesound",
        "api": "freesound",
        "consulta": consulta,
    }


def _es_cc0(item):
    """Verificación por item: licencia cc0 y, si trae URL de licencia, que sea la de dominio público."""
    url = (item.get("licencia_url") or "").lower()
    return item.get("licencia") == LICENCIA and (not url or "publicdomain/zero" in url)


def _url_clave(u):
    u = (u or "").strip().rstrip("/").lower()
    return "https://" + u[len("http://"):] if u.startswith("http://") else u


def _origen(it):
    o = it.get("origen_url")
    if not o and str(it.get("fuente", "")).startswith("http"):  # manifest heredado del prototipo
        o = it["fuente"]
    return o or ""


def _claves_item(it):
    """Claves de deduplicación: id y URL de origen (misma obra vía Openverse o vía Freesound)."""
    return {k for k in (str(it.get("id") or ""), _url_clave(_origen(it))) if k}


def limites(perfil="any", min_dur=None, max_dur=None):
    """(min_s, max_s) del perfil; min_dur/max_dur explícitos anulan el preset (cada extremo aparte)."""
    if perfil not in PERFILES:
        raise ValueError(f"perfil inválido {perfil!r} (usa {', '.join(PERFILES)})")
    p_min, p_max = PERFILES[perfil]
    mn = p_min if min_dur is None else float(min_dur)
    mx = p_max if max_dur is None else float(max_dur)
    if mn is not None and mx is not None and mn > mx:
        raise ValueError(f"duración mínima ({mn:g} s) mayor que la máxima ({mx:g} s)")
    return mn, mx


def _en_rango(dur, mn, mx):
    if mn is None and mx is None:
        return True
    if not isinstance(dur, (int, float)):
        return False  # sin duración no se puede garantizar el perfil
    return (mn is None or dur >= mn) and (mx is None or dur <= mx)


def _contar(stats, clave, n=1):
    stats[clave] = stats.get(clave, 0) + n


# ---------------------------------------------------------------- búsqueda
def _paginas_openverse(query, pagina_max, stats):
    for pagina in range(1, pagina_max + 1):
        if pagina > 1:
            _dormir(PAUSA_PAGINAS)
        # Nunca `category`: con license=cc0 devuelve 0 resultados (verificado 2026-09).
        params = {"q": query, "license": LICENCIA, "license_type": "all-cc", "mature": "false",
                  "page_size": OPENVERSE_PAGINA, "page": pagina}
        _contar(stats, "consultas_api")
        datos = _json(OPENVERSE_API + "?" + urllib.parse.urlencode(params))
        crudos = [x for x in (datos.get("results") or []) if isinstance(x, dict)]
        yield [_normalizar_openverse(x, query) for x in crudos]
        try:
            ultima = int(datos.get("page_count") or pagina)
        except (TypeError, ValueError):
            ultima = pagina
        if len(crudos) < OPENVERSE_PAGINA or pagina >= ultima:
            return


def _num(x):
    return f"{x:g}"


def _paginas_freesound(query, mn, mx, pagina_max, stats):
    token = _token_freesound()
    if not token:
        raise ErrorConfig("Freesound requiere FREESOUND_TOKEN (gratis en https://freesound.org/apiv2/apply) "
                          "en el entorno o en .env; sin token usa --source openverse")
    filtro = FREESOUND_FILTRO
    if mn is not None or mx is not None:
        filtro += f" duration:[{_num(mn) if mn is not None else 0} TO {_num(mx) if mx is not None else '*'}]"
    for pagina in range(1, pagina_max + 1):
        if pagina > 1:
            _dormir(PAUSA_PAGINAS)
        params = {"query": query, "filter": filtro, "page_size": FREESOUND_PAGINA, "page": pagina,
                  "fields": "id,name,username,license,duration,previews,url"}
        url = FREESOUND_API + "?" + urllib.parse.urlencode(params)
        cab = {"Authorization": f"Token {token}"} if _host(url) == FREESOUND_HOST else {}
        _contar(stats, "consultas_api")
        datos = _json(url, cab)
        crudos = [x for x in (datos.get("results") or []) if isinstance(x, dict)]
        yield [_normalizar_freesound(x, query) for x in crudos]
        if not datos.get("next"):
            return


def buscar(query, n=5, perfil="any", min_dur=None, max_dur=None, fuente="openverse", pagina_max=3,
           *, excluir=(), reserva=0, stats=None):
    """Busca hasta `n` items CC0 verificados que cumplan el perfil de duración. NO descarga.

    Devuelve dicts normalizados: id, titulo, autor, licencia, licencia_url, origen_url,
    descarga_url, duracion_s, formato, proveedor (+ api, consulta).
    - Deduplica por id / URL de origen entre páginas; descarta y cuenta en `stats` lo que no es
      CC0 (`no_cc0`), queda fuera de duración, no trae URL https o está en `excluir` (ids/URLs).
    - `reserva`: items extra que se devuelven si ya venían en las páginas pedidas (no pide más).
    - Si la página 1 falla lanza ErrorRed; si falla una posterior devuelve lo reunido
      (`stats["aviso_red"]`). Sin token con fuente="freesound" lanza ErrorConfig.
    """
    query = _texto(query)
    if not query:
        raise ValueError("consulta vacía")
    if fuente not in FUENTES:
        raise ValueError(f"fuente inválida {fuente!r} (usa {', '.join(FUENTES)})")
    mn, mx = limites(perfil, min_dur, max_dur)
    stats = {} if stats is None else stats
    stats.setdefault("consultas_api", 0)
    n, pagina_max = int(n), max(1, int(pagina_max))
    if n < 1:
        return []
    excluir = {_url_clave(x) if str(x).startswith("http") else str(x) for x in excluir if x}
    paginas = (_paginas_openverse(query, pagina_max, stats) if fuente == "openverse"
               else _paginas_freesound(query, mn, mx, pagina_max, stats))
    vistos, out, ok_paginas = set(), [], 0
    while len(out) < n:
        try:
            lote = next(paginas)
        except StopIteration:
            break
        except ErrorRed as e:
            if not ok_paginas:
                raise
            stats["aviso_red"] = str(e)
            break
        ok_paginas += 1
        for it in lote:
            claves = _claves_item(it)
            if claves & vistos:
                _contar(stats, "duplicados")
                continue
            vistos |= claves
            if not _es_cc0(it):
                _contar(stats, "no_cc0")
                continue
            if claves & excluir:
                _contar(stats, "ya_locales")
                continue
            if not _es_https(it["descarga_url"]):
                _contar(stats, "sin_url")
                continue
            if not _en_rango(it["duracion_s"], mn, mx):
                _contar(stats, "fuera_duracion")
                continue
            it["licencia_url"] = it["licencia_url"] or LICENCIA_URL
            out.append(it)
            if len(out) >= n + max(0, reserva):
                break
    return out


# ---------------------------------------------------------------- manifest y créditos
def _rutas(out_dir):
    return os.path.join(out_dir, "manifest.json"), os.path.join(out_dir, "credits.csv")


def _leer_manifest(ruta):
    if not os.path.exists(ruta):
        return {"politica_licencia": POLITICA, "items": []}
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErrorConfig(f"manifest.json ilegible ({ruta}); no se sobreescribe: {e}") from e
    if not isinstance(datos, dict) or not isinstance(datos.get("items", []), list):
        raise ErrorConfig(f"manifest.json con formato inesperado ({ruta}); no se sobreescribe")
    datos.setdefault("items", [])
    return datos


def _guardar_manifest(ruta, datos):
    datos["politica_licencia"] = POLITICA
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, ruta)  # escritura atómica: nunca queda un manifest a medias


def _csv(campo, valor):
    if valor is None:
        return ""
    s = str(valor)
    if campo in ("titulo", "autor", "consulta") and s[:1] in ("=", "+", "-", "@"):
        s = "'" + s  # datos de terceros: que Excel/Numbers no los interprete como fórmula
    return s


def _csv_reescribir(ruta, campos, filas):
    tmp = ruta + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    os.replace(tmp, ruta)


def _escribir_credits(ruta, filas):
    """Append a credits.csv (encabezado solo si no existía), sin duplicar por id.

    Solo reescribe el archivo (conservando todas las filas) si una fila ya existente cambió —
    re-descarga de un archivo borrado— o si el encabezado heredado no trae las columnas actuales.
    """
    nuevas = [{c: _csv(c, f.get(c)) for c in CAMPOS_CSV} for f in filas]
    if not os.path.exists(ruta):
        _csv_reescribir(ruta, CAMPOS_CSV, nuevas)
        return
    with open(ruta, newline="", encoding="utf-8") as fh:
        lector = csv.DictReader(fh)
        campos = list(lector.fieldnames or [])
        existentes = list(lector)
    faltan = [c for c in CAMPOS_CSV if c not in campos]
    reescribir, agregar = bool(faltan), []
    campos += faltan

    def clave(fila):
        return fila.get("id") or fila.get("archivo") or ""

    idx = {clave(f): i for i, f in enumerate(existentes)}
    for fila in nuevas:
        k = clave(fila)
        if k and k in idx:
            viejo = existentes[idx[k]]
            if any((viejo.get(c) or "") != fila[c] for c in CAMPOS_CSV):
                existentes[idx[k]] = {**viejo, **fila}
                reescribir = True
            continue
        idx[k] = len(existentes)
        existentes.append(fila)
        agregar.append(fila)
    if reescribir:
        _csv_reescribir(ruta, campos, existentes)
    elif agregar:
        with open(ruta, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=campos, restval="", extrasaction="ignore").writerows(agregar)


@contextlib.contextmanager
def _candado(out_dir):
    """Serializa descargas/escrituras entre procesos (el motor puede pedir varios cues a la vez)."""
    if fcntl is None:  # pragma: no cover
        yield
        return
    with open(os.path.join(out_dir, ".fetch_audio.lock"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _nombre_seguro(nombre):
    return (isinstance(nombre, str) and bool(nombre) and os.path.basename(nombre) == nombre
            and not nombre.startswith("."))


def _archivo_ok(out_dir, it):
    return _nombre_seguro(it.get("archivo")) and os.path.isfile(os.path.join(out_dir, it["archivo"]))


def _consultas_de(it):
    cs = list(it.get("consultas") or []) + [it.get("consulta"), it.get("query")]  # query: heredado
    return {_norm_consulta(c) for c in cs if isinstance(c, str) and c.strip()}


def _sumar_consulta(previo, consulta):
    """Registra que `previo` también sirve para `consulta` (mejora el cache). True si cambió."""
    if not consulta or _norm_consulta(consulta) in _consultas_de(previo):
        return False
    previo.setdefault("consultas", [c for c in (previo.get("consulta"), previo.get("query")) if c])
    previo["consultas"].append(consulta)
    return True


def _para_devolver(entrada, out_dir, reutilizado):
    return dict(entrada, ruta=os.path.join(out_dir, entrada["archivo"]), reutilizado=reutilizado)


def _ahora():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _parece_html(cuerpo):
    return (cuerpo or b"")[:64].lstrip()[:1] in (b"<", b"{")  # ningún audio empieza con < o {


def _extension(formato, tipo, url):
    f = (formato or "").lower()
    if f in EXT_AUDIO:
        return f
    return TIPO_A_EXT.get(tipo) or _formato(None, url) or "bin"


def _escribir_sin_pisar(out_dir, base, ext, cuerpo, ocupados, preferido=None):
    """Escribe `<base>_<n>.<ext>` con el primer n libre (en disco y en el manifest). Nunca pisa:
    la creación es exclusiva ('xb'). `preferido` = nombre previo de un archivo que se borró."""
    previos = [preferido] if _nombre_seguro(preferido) else []
    for nombre in itertools.chain(previos, (f"{base}_{i}.{ext}" for i in itertools.count(1))):
        if nombre in ocupados and nombre != preferido:
            continue
        ruta = os.path.join(out_dir, nombre)
        try:
            with open(ruta, "xb") as f:
                f.write(cuerpo)
            return nombre
        except FileExistsError:
            continue
        except OSError:
            with contextlib.suppress(OSError):
                os.remove(ruta)
            raise


def _bajar_uno(item, out_dir, ocupados, preferido=None):
    r = _pedir(item["descarga_url"], timeout=TIMEOUT_DESCARGA, reintentos=3)
    tipo = (r.tipo or "").split(";")[0].strip().lower()
    cuerpo = r.cuerpo or b""
    if tipo.startswith(TIPOS_NO_AUDIO) or _parece_html(cuerpo):
        raise _Descarte(f"no es audio (Content-Type {tipo or '?'})")
    if len(cuerpo) <= MIN_BYTES:
        raise _Descarte(f"≤1 KB ({len(cuerpo)} B): corrupto o página de error, descartado")
    if len(cuerpo) > MAX_BYTES:
        raise _Descarte("excede 50 MB, descartado")
    ext = _extension(item.get("formato"), tipo, item["descarga_url"])
    archivo = _escribir_sin_pisar(out_dir, slug(item.get("titulo")), ext, cuerpo, ocupados, preferido)
    nuevo = {"archivo": archivo, **{k: item.get(k) for k in CAMPOS_ITEM}}
    nuevo.update(formato=ext, bytes=len(cuerpo), sha256=hashlib.sha256(cuerpo).hexdigest(), fecha=_ahora(),
                 consultas=[item["consulta"]] if item.get("consulta") else [])
    return nuevo


def descargar(items, out_dir, *, maximo=None, stats=None):
    """Descarga items de `buscar()` a `out_dir` con trazabilidad y devuelve las entradas del manifest.

    Cada entrada devuelta trae además `ruta` (absoluta) y `reutilizado`. Por archivo nuevo agrega
    archivo, bytes, sha256 y fecha, hace append a credits.csv y a manifest.json (items).
    - Deduplica por id / URL de origen; un item ya presente en el manifest con su archivo en disco
      se REUTILIZA sin volver a descargarlo (y se anota la consulta nueva en `consultas`).
    - Vuelve a verificar CC0 (defensa en profundidad) y descarta ≤1 KB / HTML sin dejar archivo.
    - `maximo`: deja de descargar al reunir esa cantidad (los demás items son reserva).
    Fallas por item quedan en `stats["fallos"]`; no se lanza ErrorRed por una descarga.
    """
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    stats = {} if stats is None else stats
    ruta_man, ruta_csv = _rutas(out_dir)
    resultado = []
    with _candado(out_dir):
        manifest = _leer_manifest(ruta_man)
        indice = {}
        for pos, it in enumerate(manifest["items"]):
            for k in _claves_item(it):
                indice.setdefault(k, pos)
        ocupados = {it.get("archivo") for it in manifest["items"] if it.get("archivo")}
        vistos, consultas_nuevas = set(), False
        for item in items:
            if maximo is not None and len(resultado) >= maximo:
                break
            claves = _claves_item(item)
            if claves & vistos:
                _contar(stats, "duplicados")
                continue
            vistos |= claves
            if not _es_cc0(item):
                _contar(stats, "no_cc0")
                continue
            pos = next((indice[k] for k in claves if k in indice), None)
            previo = manifest["items"][pos] if pos is not None else None
            if previo is not None and _archivo_ok(out_dir, previo):
                consultas_nuevas |= _sumar_consulta(previo, item.get("consulta"))
                resultado.append(_para_devolver(previo, out_dir, True))
                continue
            try:
                nuevo = _bajar_uno(item, out_dir, ocupados, previo.get("archivo") if previo else None)
            except (ErrorRed, _Descarte) as e:
                _contar(stats, "fallos_red" if isinstance(e, ErrorRed) else "descartes_descarga")
                stats.setdefault("fallos", []).append((item.get("titulo") or "?", str(e)))
                continue
            ocupados.add(nuevo["archivo"])
            if previo is not None:  # estaba en el manifest pero su archivo ya no existía
                for c in sorted(_consultas_de(previo) - _consultas_de(nuevo)):
                    nuevo["consultas"].append(c)
                manifest["items"][pos] = nuevo
            else:
                manifest["items"].append(nuevo)
                pos = len(manifest["items"]) - 1
            for k in claves:
                indice[k] = pos
            _guardar_manifest(ruta_man, manifest)  # por archivo: trazabilidad aunque se interrumpa
            _escribir_credits(ruta_csv, [nuevo])
            resultado.append(_para_devolver(nuevo, out_dir, False))
        if consultas_nuevas:
            _guardar_manifest(ruta_man, manifest)
    return resultado


def obtener(query, n=5, perfil="any", out_dir=None, *, min_dur=None, max_dur=None, fuente="openverse",
            pagina_max=3, usar_cache=True, stats=None):
    """Cache primero: devuelve hasta `n` audios CC0 para `query` listos para usar (`ruta`).

    1) Busca en el manifest local items descargados antes para esa misma consulta (normalizada)
       que cumplan el perfil de duración y sigan en disco; si hay ≥ n, NO toca la API
       (Openverse anónimo ≈100 req/día).
    2) Si faltan, busca solo los faltantes (excluyendo los locales) y los descarga.
    Con `usar_cache=False` ignora el cache y trae archivos que aún no están en el manifest.
    Lanza ErrorRed solo si no hay nada que devolver por culpa de la red; si no hay CC0 → [].
    """
    out_dir = os.path.abspath(os.path.expanduser(out_dir or salida_por_defecto()))
    stats = {} if stats is None else stats
    stats.setdefault("consultas_api", 0)
    mn, mx = limites(perfil, min_dur, max_dur)
    n = int(n)
    if n < 1:
        return []
    manifest = _leer_manifest(_rutas(out_dir)[0])
    q = _norm_consulta(query)
    locales, excluir = [], set()
    for it in manifest["items"]:
        claves = _claves_item(it)
        if not usar_cache:
            excluir |= claves
            continue
        if claves & excluir:
            continue
        if (q in _consultas_de(it) and _es_cc0(it) and _en_rango(it.get("duracion_s"), mn, mx)
                and _archivo_ok(out_dir, it)):
            excluir |= claves
            locales.append(_para_devolver(it, out_dir, True))
    if len(locales) >= n:
        return locales[:n]
    faltan = n - len(locales)
    try:
        encontrados = buscar(query, faltan, perfil, min_dur, max_dur, fuente, pagina_max,
                             excluir=excluir, reserva=MARGEN_REPOSICION, stats=stats)
    except ErrorRed as e:
        if not locales:
            raise
        stats["aviso_red"] = str(e)
        encontrados = []
    nuevos = descargar(encontrados, out_dir, maximo=faltan, stats=stats) if encontrados else []
    res = locales + nuevos
    if not res and stats.get("fallos_red"):
        raise ErrorRed("ninguna descarga completó: " + stats["fallos"][0][1])
    return res[:n]


def _sha256_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def verificar_manifest(out_dir=None):
    """Compara el sha256 de cada item del manifest con su archivo en disco.

    Devuelve (ok_count, bad_list) con bad_list = [(archivo, motivo), ...].
    """
    out_dir = os.path.abspath(os.path.expanduser(out_dir or salida_por_defecto()))
    ok, malos = 0, []
    for it in _leer_manifest(_rutas(out_dir)[0])["items"]:
        archivo = it.get("archivo") or ""
        esperado = str(it.get("sha256") or "").lower()
        if not _nombre_seguro(archivo):
            malos.append((archivo or "?", "nombre de archivo inválido"))
        elif not os.path.isfile(os.path.join(out_dir, archivo)):
            malos.append((archivo, "no existe"))
        elif not esperado:
            malos.append((archivo, "sin sha256"))
        elif _sha256_archivo(os.path.join(out_dir, archivo)) != esperado:
            malos.append((archivo, "sha256 distinto"))
        else:
            ok += 1
    return ok, malos


# ---------------------------------------------------------------- CLI
ETIQUETAS_DESCARTE = (("no_cc0", "no-CC0"), ("fuera_duracion", "fuera de duración"),
                      ("duplicados", "duplicados"), ("sin_url", "sin URL https"),
                      ("ya_locales", "ya descargados"), ("descartes_descarga", "archivo inválido"),
                      ("fallos_red", "descarga fallida"))


def _rango_txt(mn, mx):
    if mn is not None and mx is not None:
        return f" de {mn:g}–{mx:g} s"
    if mx is not None:
        return f" de ≤{mx:g} s"
    if mn is not None:
        return f" de ≥{mn:g} s"
    return ""


def _linea(it):
    marca = "=" if it.get("reutilizado") else "+"
    b = it.get("bytes")
    if not isinstance(b, int):
        b = os.path.getsize(it["ruta"]) if os.path.isfile(it.get("ruta", "")) else 0
    d = it.get("duracion_s")
    dur = (f"{d:.2f} s" if d < 1 else f"{d:.1f} s") if isinstance(d, (int, float)) else "? s"
    return f"{marca} {it['archivo']}  {b / 1024:.0f} KB  {dur}  {it.get('licencia')}  {it.get('autor') or '?'}"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Descarga música y efectos CC0 1.0 (Openverse / Freesound). Solo CC0: sin BY/SA/NC/ND.")
    ap.add_argument("query", nargs="?", help='consulta, p. ej. "whoosh transition"')
    ap.add_argument("-n", type=int, default=5, help="cuántos archivos (default 5)")
    ap.add_argument("--profile", choices=list(PERFILES), default="any",
                    help="sfx = ≤6 s · bgm = ≥30 s · any = sin límite")
    ap.add_argument("--max-dur", type=float, help="segundos; anula el máximo del perfil")
    ap.add_argument("--min-dur", type=float, help="segundos; anula el mínimo del perfil")
    ap.add_argument("--out", help=f"carpeta de salida (default config.json > audio_cc0.salida o {SALIDA_DEFAULT})")
    ap.add_argument("--source", choices=FUENTES, default="openverse", help="freesound requiere FREESOUND_TOKEN")
    ap.add_argument("--license", default=LICENCIA, help="solo se acepta cc0 (existe para fallar explícito)")
    ap.add_argument("--paginas", type=int, default=3,
                    help="páginas máximas por búsqueda (default 3; Openverse anónimo ≈100 req/día)")
    ap.add_argument("--sin-cache", action="store_true",
                    help="no reutiliza lo ya descargado para la consulta: trae archivos nuevos")
    ap.add_argument("--verificar", action="store_true", help="solo verifica los sha256 del manifest contra el disco")
    a = ap.parse_args(argv)

    if (a.license or "").strip().lower() != LICENCIA:
        print(f"Rechazado: solo CC0. Esta herramienta no descarga licencia '{_texto(a.license, 40)}' "
              f"(política: {POLITICA}; sin BY, BY-SA, BY-NC ni BY-NC-ND).", file=sys.stderr)
        return 1
    out = os.path.abspath(os.path.expanduser(a.out)) if a.out else salida_por_defecto()
    ruta_man, ruta_csv = _rutas(out)

    if a.verificar:
        try:
            ok, malos = verificar_manifest(out)
        except ErrorConfig as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        for archivo, motivo in malos:
            print(f"! {archivo}: {motivo}")
        print(f"verificados: {ok} ok, {len(malos)} con problema · manifest: {ruta_man}")
        return 3 if malos else 0

    if not a.query or not _texto(a.query):
        ap.error("falta la consulta (o usa --verificar)")
    if not 1 <= a.n <= 100:
        ap.error("-n debe estar entre 1 y 100")
    if not 1 <= a.paginas <= 10:
        ap.error("--paginas debe estar entre 1 y 10")
    if any(v is not None and v < 0 for v in (a.min_dur, a.max_dur)):
        ap.error("las duraciones no pueden ser negativas")
    try:
        mn, mx = limites(a.profile, a.min_dur, a.max_dur)
    except ValueError as e:
        ap.error(str(e))

    stats = {}
    try:
        res = obtener(a.query, a.n, a.profile, out, min_dur=a.min_dur, max_dur=a.max_dur, fuente=a.source,
                      pagina_max=a.paginas, usar_cache=not a.sin_cache, stats=stats)
    except ErrorConfig as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ErrorRed as e:
        print(f"ERROR de red/API ({stats.get('consultas_api', 0)} consulta(s)): {e}", file=sys.stderr)
        return 4

    for it in res:
        print(_linea(it))
    for titulo, motivo in stats.get("fallos", []):
        print(f"! {titulo}: {motivo}")
    descartes = [f"{stats[k]} {txt}" for k, txt in ETIQUETAS_DESCARTE if stats.get(k)]
    if descartes:
        print("descartados: " + " · ".join(descartes))
    if stats.get("aviso_red"):
        print(f"AVISO de red: {stats['aviso_red']}")
    rango, bgm = _rango_txt(mn, mx), mn is not None and mn >= 30
    if not res:
        print(f"Sin resultados CC0{rango} para «{_texto(a.query)}» ({stats.get('consultas_api', 0)} consulta(s) "
              f"API, {a.paginas} página(s) máx.). No se descargó nada.", file=sys.stderr)
        if bgm:
            print(AVISO_BGM, file=sys.stderr)
        return 1
    if len(res) < a.n:
        print(f"AVISO: solo {len(res)} de {a.n} pedidos: no hay más CC0{rango} para «{_texto(a.query)}» "
              f"en {a.paginas} página(s). Prueba otra consulta o sube --paginas.")
        if bgm:
            print(AVISO_BGM)
    reus = sum(1 for it in res if it.get("reutilizado"))
    print(f"total: {len(res)} CC0 ({len(res) - reus} nuevos, {reus} reutilizados) · "
          f"{stats.get('consultas_api', 0)} consulta(s) API · {out}")
    print(f"créditos: {ruta_csv}")
    print(f"manifest: {ruta_man}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
