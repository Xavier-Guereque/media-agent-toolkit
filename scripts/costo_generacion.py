#!/usr/bin/env python3
"""costo_generacion.py — reporte de costos de una edición.

Lee el log de generaciones del proyecto activo (por defecto el
`proyectos/<slug>_<fecha>/recursos/costos.jsonl` más reciente; patrón
configurable en `config.json > costos.log`, relativo a la carpeta del
proyecto) con líneas JSON del tipo:

    {"id": "gen-...", "modelo": "google/gemini-2.5-flash", "tarea": "vision", "ts": "..."}

Por cada `id` consulta `GET {url_base}/generation?id=...` (OpenRouter) con la
key del `.env` y suma `data.total_cost`. Si el endpoint falla y la línea trae
`usage.cost`, usa ese valor como ESTIMADO. Imprime desglose por tarea/modelo y
el total en USD (4 decimales). Ids duplicados en el log se cuentan una sola vez.

Al terminar el reporte, el log se ROTA (se renombra a costos-<timestamp>.jsonl,
en la misma carpeta recursos/ del proyecto) para que cada reporte cubra solo
la edición actual.

Seguridad: el header Authorization solo se envía a https://openrouter.ai; si
`config.json > openrouter.url_base` apunta a otro host o esquema, se rechaza y
se usa el default seguro.

Uso:  python3 scripts/costo_generacion.py [--log ruta/al/costos.jsonl]
Solo usa la librería estándar. Detalles en docs/Costos-y-Avance.md
"""

import argparse
import glob
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL_BASE_SEGURA = "https://openrouter.ai/api/v1"
HOST_PERMITIDO = "openrouter.ai"


def cargar_config():
    ruta = os.path.join(REPO_ROOT, "config.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def cargar_env():
    """Lee variables del .env del repo sin imprimir su contenido."""
    env = {}
    ruta = os.path.join(REPO_ROOT, ".env")
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                k, v = linea.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def url_base_segura(url_base):
    """Solo permite https://openrouter.ai como destino del Bearer token.

    `url_base` viene de config.json (mutable); si apunta a otro host o a un
    esquema que no sea https, se rechaza y se usa el default seguro.
    """
    try:
        p = urlparse(url_base or "")
    except ValueError:
        p = None
    if p is None or p.scheme != "https" or p.netloc.lower() != HOST_PERMITIDO:
        print(f"AVISO: url_base no permitida ({url_base!r}); se usa {URL_BASE_SEGURA}",
              file=sys.stderr)
        return URL_BASE_SEGURA
    return url_base.rstrip("/")


def costo_por_generacion(url_base, api_key, gen_id, timeout=10):
    """Devuelve total_cost (float) o None si el endpoint falla."""
    url = f"{url_base}/generation?id={gen_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        costo = (data.get("data") or {}).get("total_cost")
        return float(costo) if costo is not None else None
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            ValueError, TypeError, AttributeError, OSError):
        return None


def rotar_log(ruta_log):
    """Renombra el log ya reportado a costos-<timestamp>.jsonl para que el
    próximo reporte solo incluya llamadas nuevas. Devuelve la ruta destino o None."""
    try:
        if not os.path.isfile(ruta_log) or os.path.getsize(ruta_log) == 0:
            return None
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        base, ext = os.path.splitext(ruta_log)
        destino = f"{base}-{ts}{ext}"
        n = 1
        while os.path.exists(destino):
            n += 1
            destino = f"{base}-{ts}-{n}{ext}"
        os.replace(ruta_log, destino)
        return destino
    except OSError:
        return None


def log_proyecto_activo(nombre_log="costos.jsonl"):
    """Devuelve el log de costos del proyecto activo: el
    `proyectos/*/recursos/<nombre_log>` con la modificación más reciente.
    None si no existe ninguno."""
    patron = os.path.join(REPO_ROOT, "proyectos", "*", "recursos", nombre_log)
    candidatos = [p for p in glob.glob(patron) if os.path.isfile(p)]
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)


def main():
    config = cargar_config()
    cfg_costos = config.get("costos", {})
    url_base = url_base_segura(
        config.get("openrouter", {}).get("url_base", URL_BASE_SEGURA))
    moneda = cfg_costos.get("moneda", "USD")

    # costos.log es relativo a la carpeta del proyecto (p. ej. recursos/costos.jsonl)
    nombre_log = os.path.basename(cfg_costos.get("log", "recursos/costos.jsonl"))
    parser = argparse.ArgumentParser(description="Reporte de costos de generación (OpenRouter).")
    parser.add_argument("--log", default=None,
                        help="Ruta al archivo costos.jsonl (default: el del proyecto activo)")
    args = parser.parse_args()
    log_ruta = args.log or log_proyecto_activo(nombre_log)

    if not log_ruta or not os.path.isfile(log_ruta):
        print("Sin log de costos (no hay proyectos/*/recursos/costos.jsonl). Nada que reportar.")
        return 0
    args.log = log_ruta

    entradas = []
    with open(args.log, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                entradas.append(json.loads(linea))
            except json.JSONDecodeError:
                print(f"AVISO: línea {n} inválida, se omite.", file=sys.stderr)

    if not entradas:
        print("El log de costos está vacío. Nada que reportar.")
        return 0

    api_key = cargar_env().get(
        config.get("openrouter", {}).get("variable_api_key", "OPENROUTER_API_KEY"), "")

    por_tarea = defaultdict(float)
    por_modelo = defaultdict(float)
    total = 0.0
    estimados = 0
    sin_costo = 0
    duplicados = 0
    ids_vistos = set()

    for e in entradas:
        gen_id = e.get("id")
        if gen_id:
            if gen_id in ids_vistos:
                duplicados += 1
                continue
            ids_vistos.add(gen_id)

        costo = None
        estimado = False
        if gen_id and api_key:
            costo = costo_por_generacion(url_base, api_key, gen_id)
        if costo is None:
            # Fallback: estimar por usage.cost registrado en la línea, si existe.
            uso = e.get("usage") or {}
            if isinstance(uso, dict) and uso.get("cost") is not None:
                try:
                    costo = float(uso["cost"])
                    estimado = True
                except (TypeError, ValueError):
                    costo = None
        if costo is None:
            sin_costo += 1
            continue
        if estimado:
            estimados += 1
        tarea = e.get("tarea", "otros")
        modelo = e.get("modelo", "desconocido")
        por_tarea[tarea] += costo
        por_modelo[modelo] += costo
        total += costo

    print(f"== Reporte de costos ({moneda}) ==")
    print(f"Log: {os.path.relpath(args.log, REPO_ROOT)} — {len(entradas)} llamadas registradas\n")

    print("Por tarea:")
    for tarea, c in sorted(por_tarea.items(), key=lambda kv: -kv[1]):
        print(f"  {tarea:<20} {c:.4f}")

    print("\nPor modelo:")
    for modelo, c in sorted(por_modelo.items(), key=lambda kv: -kv[1]):
        print(f"  {modelo:<45} {c:.4f}")

    print(f"\nTOTAL: {total:.4f} {moneda}")
    if estimados:
        print(f"  ({estimados} llamada(s) con costo ESTIMADO por tokens: el endpoint /generation no respondió)")
    if sin_costo:
        print(f"  ({sin_costo} llamada(s) sin costo disponible: sin id, sin key o endpoint inaccesible)")
    if duplicados:
        print(f"  ({duplicados} línea(s) duplicada(s) omitida(s) por id)")

    destino_rotado = rotar_log(args.log)
    if destino_rotado:
        print(f"Log rotado a {os.path.relpath(destino_rotado, REPO_ROOT)}; el próximo reporte solo incluirá llamadas nuevas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
