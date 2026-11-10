#!/usr/bin/env python3
"""costo_sesion_hermes — suma el costo de la sesión de Hermes al log del proyecto.

El reporte de `costo_generacion.py` solo ve lo que se gastó por OpenRouter *desde los
scripts del toolkit* (TTS, visión, decisiones…). La sesión del agente también cuesta
tokens: este script lee la tabla `session_model_usage` de la base de Hermes
(`~/.hermes/state.db`), agrupa por modelo y tarea, y escribe una línea por grupo en el
`recursos/costos.jsonl` del proyecto con `tarea: "sesion_hermes"` y el costo en
`usage.cost`. Así aparece en el reporte normal (marcado como ESTIMADO, porque no hay
`id` de generación de OpenRouter que consultar).

Es idempotente: volver a correrlo para la misma sesión reemplaza sus líneas previas.

Uso:
  python3 scripts/costo_sesion_hermes.py --log proyectos/<slug>/recursos/costos.jsonl
  python3 scripts/costo_sesion_hermes.py --log <log> --session 20260928_125604_f01a96
  python3 scripts/costo_sesion_hermes.py --listar          # sesiones recientes y su costo

Sin `--session` toma la sesión con actividad más reciente. Solo librería estándar.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_DEFECTO = Path.home() / ".hermes" / "state.db"


def db_configurada():
    """Permite cambiar la ruta de la base en config.json > costos.sesion_hermes.db."""
    try:
        cfg = json.loads((REPO_ROOT / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DB_DEFECTO
    ruta = (cfg.get("costos", {}).get("sesion_hermes", {}) or {}).get("db")
    return Path(os.path.expanduser(ruta)) if ruta else DB_DEFECTO


def conectar(db):
    """Conexión de solo lectura: la app puede estar escribiendo la base en paralelo."""
    uri = f"file:{Path(db).as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def sesion_mas_reciente(con):
    fila = con.execute(
        "SELECT session_id, MAX(COALESCE(last_seen, 0)) AS ultimo "
        "FROM session_model_usage GROUP BY session_id ORDER BY ultimo DESC LIMIT 1"
    ).fetchone()
    return fila["session_id"] if fila else None


def uso_de_sesion(con, session_id):
    """Filas de uso de la sesión; el costo real manda sobre el estimado."""
    return con.execute(
        "SELECT model, task, billing_provider, api_call_count, input_tokens, output_tokens, "
        "       cache_read_tokens, cache_write_tokens, reasoning_tokens, "
        "       estimated_cost_usd, actual_cost_usd "
        "FROM session_model_usage WHERE session_id = ? "
        "ORDER BY (CASE WHEN actual_cost_usd > 0 THEN actual_cost_usd ELSE estimated_cost_usd END) DESC",
        (session_id,),
    ).fetchall()


def agrupar(filas):
    """Suma por modelo (la tarea del toolkit no distingue, así que se conserva como detalle)."""
    grupos = {}
    for f in filas:
        clave = f["model"]
        g = grupos.setdefault(clave, {"modelo": f["model"], "tareas": {}, "costo": 0.0,
                                      "llamadas": 0, "input_tokens": 0, "output_tokens": 0,
                                      "cache_read_tokens": 0, "cache_write_tokens": 0,
                                      "reasoning_tokens": 0})
        costo = f["actual_cost_usd"] or f["estimated_cost_usd"] or 0.0
        g["costo"] += float(costo)
        g["llamadas"] += int(f["api_call_count"] or 0)
        for k in ("input_tokens", "output_tokens", "cache_read_tokens",
                  "cache_write_tokens", "reasoning_tokens"):
            g[k] += int(f[k] or 0)
        tarea = f["task"] or "chat_completions"
        g["tareas"][tarea] = g["tareas"].get(tarea, 0.0) + float(costo)
    return grupos


def reemplazar_en_log(log, session_id, nuevas):
    """Quita las líneas previas de esta sesión y agrega las nuevas."""
    previas = []
    if os.path.isfile(log):
        with open(log, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    e = json.loads(linea)
                except json.JSONDecodeError:
                    previas.append(linea)
                    continue
                if e.get("session_id") == session_id and e.get("tarea") == "sesion_hermes":
                    continue
                previas.append(linea)
    with open(log, "w", encoding="utf-8") as f:
        for linea in previas:
            f.write(linea + "\n")
        for linea in nuevas:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Suma el costo de la sesión de Hermes al log del proyecto.")
    ap.add_argument("--log", help="costos.jsonl del proyecto (destino)")
    ap.add_argument("--session", help="id de sesión de Hermes (default: la más reciente)")
    ap.add_argument("--db", default=None, help=f"base de Hermes (default: {DB_DEFECTO})")
    ap.add_argument("--listar", action="store_true", help="muestra sesiones recientes y su costo")
    ap.add_argument("--silencioso", action="store_true", help="no imprime el resumen")
    args = ap.parse_args()

    db = Path(args.db) if args.db else db_configurada()
    if not db.exists():
        sys.exit(f"No encuentro la base de Hermes en {db}")

    with conectar(db) as con:
        if args.listar:
            filas = con.execute(
                "SELECT session_id, COUNT(*) AS modelos, SUM(api_call_count) AS llamadas, "
                "       SUM(COALESCE(NULLIF(actual_cost_usd,0), estimated_cost_usd)) AS costo, "
                "       MAX(COALESCE(last_seen,0)) AS ultimo "
                "FROM session_model_usage GROUP BY session_id ORDER BY ultimo DESC LIMIT 15"
            ).fetchall()
            print(f"{'sesión':<26} {'llamadas':>9} {'costo USD':>11}  última actividad")
            for f in filas:
                cuando = (datetime.fromtimestamp(f["ultimo"], tz=timezone.utc).astimezone()
                          .strftime("%Y-%m-%d %H:%M:%S") if f["ultimo"] else "-")
                print(f"{f['session_id']:<26} {int(f['llamadas'] or 0):>9} "
                      f"{float(f['costo'] or 0):>11.4f}  {cuando}")
            return 0

        session = args.session or sesion_mas_reciente(con)
        if not session:
            sys.exit("La base no tiene registros de uso todavía.")
        filas = uso_de_sesion(con, session)
        grupos = agrupar(filas)

    total = sum(g["costo"] for g in grupos.values())
    if not args.silencioso:
        print(f"Sesión de Hermes: {session}")
        for modelo, g in grupos.items():
            print(f"  {modelo:<45} {g['costo']:.4f}  "
                  f"({g['llamadas']} llamadas, in {g['input_tokens']} / out {g['output_tokens']} "
                  f"/ cache_read {g['cache_read_tokens']})")
        print(f"  {'TOTAL':<45} {total:.4f}")

    if not args.log:
        print("\n(sin --log: no se escribió nada en ningún proyecto)")
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    nuevas = []
    for modelo, g in grupos.items():
        if g["costo"] <= 0 and g["llamadas"] == 0:
            continue
        nuevas.append({
            "id": f"hermes-{session}-{modelo}",
            "modelo": modelo,
            "tarea": "sesion_hermes",
            "ts": ts,
            "session_id": session,
            "origen": "hermes/state.db:session_model_usage",
            "detalle_tareas": {k: round(v, 6) for k, v in g["tareas"].items()},
            "usage": {
                "cost": round(g["costo"], 6),
                "prompt_tokens": g["input_tokens"],
                "completion_tokens": g["output_tokens"],
                "cache_read_tokens": g["cache_read_tokens"],
                "cache_write_tokens": g["cache_write_tokens"],
                "reasoning_tokens": g["reasoning_tokens"],
            },
        })
    reemplazar_en_log(args.log, session, nuevas)
    print(f"\n{len(nuevas)} línea(s) de sesión escritas en {os.path.relpath(args.log, REPO_ROOT)} "
          f"(total {total:.4f} USD)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
