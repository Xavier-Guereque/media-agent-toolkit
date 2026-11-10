#!/usr/bin/env python3
"""decision — llamada a la Decisions API de OpenRouter (JEV) para decisiones estructuradas.

Contrato verificado 2026-09-28 (ver docs/Lecciones-2026-09-28-reel-syscomexpo2027.md):
  POST https://openrouter.ai/api/alpha/decisions   (NO /chat/completions)
  - `state`     : objeto con el contexto (guion, datos, criterios…)
  - `questions` : REGISTRO {"id": {...}} (un array devuelve `expected record`)
  - cada pregunta: `type` = noul | choice | score  +  `instructions` (string|registro|array)
      · noul   → devuelve `noul`: probabilidad 0-1 de que el criterio se cumpla
      · score  → exige `criteria` como ARRAY de criterios
      · choice → exige `criteria` como REGISTRO {clave: descripción}
  La respuesta llega en `answers.<id>` (§leer `noul`/`probabilities`, no `score`).

Uso (CLI):
  python3 scripts/decision.py --state estado.json --questions preguntas.json --log proyectos/<slug>/recursos/costos.jsonl

Uso (importado), el patrón que usan los scripts del toolkit:
  from decision import decidir
  res = decidir(state, {"gate": {"type": "noul", "instructions": "..."}}, repo)
  if res["answers"]["gate"]["noul"] < 0.7: ...

Key: variable OPENROUTER_API_KEY del entorno o del .env del repo.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODELO = "typesafe/jev-1.13"


def _key(repo="."):
    v = os.environ.get("OPENROUTER_API_KEY")
    if v:
        return v
    env = os.path.join(repo, ".env")
    if os.path.exists(env):
        with open(env) as f:
            for l in f:
                if l.startswith("OPENROUTER_API_KEY="):
                    return l.split("=", 1)[1].strip()
    raise SystemExit("Falta OPENROUTER_API_KEY (entorno o .env del repo)")


def decidir(state, questions, repo=".", modelo=MODELO, log=None):
    """Ejecuta la consulta. `questions` debe ser un registro; se valida antes de llamar."""
    if not isinstance(questions, dict):
        raise ValueError("`questions` debe ser un registro {'id': {...}}, no un array")
    for qid, q in questions.items():
        if q.get("type") not in ("noul", "choice", "score"):
            raise ValueError(f"{qid}: type debe ser noul|choice|score")
        if "instructions" not in q:
            raise ValueError(f"{qid}: falta `instructions` (string|registro|array)")
        if q["type"] == "score" and not isinstance(q.get("criteria"), list):
            raise ValueError(f"{qid}: score exige `criteria` como array")
        if q["type"] == "choice" and not isinstance(q.get("criteria"), dict):
            raise ValueError(f"{qid}: choice exige `criteria` como registro de opciones")
    payload = {"model": modelo, "state": state, "questions": questions}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {_key(repo)}",
                                          "Content-Type": "application/json"})
    try:
        res = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        raise SystemExit("Decisions API: " + e.read().decode()[:600])
    if log:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a") as f:
            f.write(json.dumps({"id": res.get("id"), "modelo": modelo, "tarea": "decisiones",
                                "ts": datetime.datetime.now().isoformat(),
                                "usage": res.get("usage")}) + "\n")
    return res


def resumen(res, umbral=0.7):
    """Devuelve {id: (valor, aprobado)} legible para gates."""
    out = {}
    for qid, a in (res.get("answers") or {}).items():
        if a.get("type") == "noul":
            out[qid] = (a.get("noul"), (a.get("noul") or 0) >= umbral)
        elif a.get("type") == "choice":
            probs = a.get("probabilities", {})
            elegido = a.get("choice")
            out[qid] = (elegido, probs.get(elegido, 0) >= umbral)
        else:
            probs = a.get("probabilities", {})
            out[qid] = (probs, bool(probs))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", help="archivo JSON con el estado (o '-' para stdin)")
    ap.add_argument("--questions", required=True, help="archivo JSON con las preguntas")
    ap.add_argument("--repo", default=".", help="raíz del repo (para leer .env)")
    ap.add_argument("--log", help="costos.jsonl donde registrar la llamada")
    a = ap.parse_args()
    state = json.load(open(a.state)) if a.state and a.state != "-" else json.load(sys.stdin)
    q = json.load(open(a.questions))
    res = decidir(state, q, a.repo, log=a.log)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print("\n-- resumen --")
    for k, (v, ok) in resumen(res).items():
        print(f"  {k}: {v} {'OK' if ok else 'NO CUMPLE'}")


if __name__ == "__main__":
    main()
