#!/usr/bin/env python3
"""e2e_orquestador — prueba de punta a punta del camino "orquestador barato".

Simula lo que hace el agente (Hermes/OpenCode con `modelos.razonamiento`) al producir un video promo:
recibe la skill `promo-ui` de SKILL.md (tal cual), el catálogo compacto (`promo.py ayuda`) y un
ejemplo de oro; escribe `promo.json` a partir de un brief; corre `promo.py validar` y, si hay errores,
recibe la salida del validador y corrige. Mide rondas, tokens y costo real (OpenRouter usage).

Uso:
  python3 scripts/e2e_orquestador.py --brief "Promo de la app de pedidos…" [--modelo deepseek/deepseek-v4.1-flash]
                                     [--ejemplo asistente-ia-cta-whatsapp] [--rondas 3] [--render]
                                     [--raiz <dir con proyectos/>] [--slug e2e-prueba]

Por defecto trabaja en una carpeta temporal (no escribe en proyectos/ del repo) y registra cada
llamada en recursos/costos.jsonl del proyecto (AGENT §10) con tarea "e2e_orquestador".
Salida: 0 si el spec quedó válido, 2 si no, 3 entorno, 4 API.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMO = os.path.join(REPO, "scripts", "promo.py")


def bloque_skill():
    """Extrae la skill promo-ui de SKILL.md entre sus marcas (las instrucciones reales, no una copia)."""
    txt = open(os.path.join(REPO, "SKILL.md"), encoding="utf-8").read()
    m = re.search(r"<!-- promo-ui:inicio.*?-->(.*?)<!-- promo-ui:fin -->", txt, re.S)
    if not m:
        raise SystemExit("SKILL.md no tiene el bloque promo-ui (marcas promo-ui:inicio/fin).")
    return m.group(1).strip()


def correr(args, env):
    r = subprocess.run([sys.executable, PROMO] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def extraer_json(texto):
    """El modelo debe devolver solo JSON; tolera cercas ``` por si acaso."""
    t = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    ini, fin = t.find("{"), t.rfind("}")
    return json.loads(t[ini:fin + 1])


def llamar(key, modelo, mensajes, esquema=None):
    fmt = {"type": "json_schema", "json_schema": {"name": "promo", "schema": esquema, "strict": False}} if esquema else {"type": "json_object"}
    cuerpo = {"model": modelo, "messages": mensajes, "response_format": fmt, "temperature": 0.4, "usage": {"include": True}}
    try:
        return comun.post_openrouter(cuerpo, key)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API {e.code}: {e.read()[:300]!r}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SystemExit(f"API sin respuesta: {e}")


def main():
    ap = argparse.ArgumentParser(description="Simula al orquestador barato escribiendo y corrigiendo promo.json")
    ap.add_argument("--brief", required=True, help="texto del brief o ruta a un .md")
    ap.add_argument("--modelo", help="modelo del orquestador (default: config.json > modelos.razonamiento)")
    ap.add_argument("--ejemplo", default="asistente-ia-cta-whatsapp")
    ap.add_argument("--rondas", type=int, default=3, help="máximo de rondas de corrección")
    ap.add_argument("--raiz", help="carpeta que contiene proyectos/ (default: temporal)")
    ap.add_argument("--slug", default="e2e-prueba")
    ap.add_argument("--esquema", action="store_true", help="usar response_format json_schema con promo.schema.json")
    ap.add_argument("--render", action="store_true", help="al quedar válido, correr `todo --borrador`")
    a = ap.parse_args()

    cfg = comun.cargar_config(REPO)
    modelo = a.modelo or cfg.get("modelos", {}).get("razonamiento", "deepseek/deepseek-v4.1-flash")
    key = comun.api_key(REPO)
    brief = open(a.brief, encoding="utf-8").read() if os.path.exists(a.brief) else a.brief
    raiz = a.raiz or tempfile.mkdtemp(prefix="promo-e2e-")
    os.makedirs(os.path.join(raiz, "proyectos"), exist_ok=True)
    env = {**os.environ, "PROMO_RAIZ": raiz}
    ejemplos = os.path.join(REPO, "promo", "ejemplos")
    ejemplo = a.ejemplo if os.path.exists(os.path.join(ejemplos, a.ejemplo, "promo.json")) else "demo-10s"

    codigo, out = correr(["nuevo", a.slug, "--ejemplo", ejemplo], env)
    if codigo != 0:
        print(out)
        return codigo
    proyecto = sorted(d for d in os.listdir(os.path.join(raiz, "proyectos")) if d.startswith(a.slug + "_"))[-1]
    pdir = os.path.join(raiz, "proyectos", proyecto)
    rec = os.path.join(pdir, "recursos")
    _, ayuda = correr(["ayuda"], env)
    oro = open(os.path.join(ejemplos, ejemplo, "promo.json"), encoding="utf-8").read()
    esquema = json.load(open(os.path.join(REPO, "promo", "esquema", "promo.schema.json"), encoding="utf-8")) if a.esquema else None

    sistema = ("Eres el orquestador del media-agent-toolkit. Tu única tarea es escribir el archivo promo.json "
               "del video. Sigue estas instrucciones del toolkit:\n\n" + bloque_skill() +
               "\n\n## Catálogo (promo.py ayuda)\n" + ayuda +
               f"\n\n## Ejemplo de oro ({ejemplo}) — copia su estructura, cambia el contenido\n" + oro +
               "\n\nResponde SIEMPRE con el JSON completo de promo.json y nada más (sin markdown ni explicaciones).")
    mensajes = [{"role": "system", "content": sistema},
                {"role": "user", "content": f"Brief del usuario:\n{brief}\n\nEscribe promo.json."}]

    t0 = time.time()
    rondas, tok_in, tok_out, costo, historial = 0, 0, 0, 0.0, []
    ok = False
    salida_val = ""
    for rondas in range(1, a.rondas + 2):
        r = llamar(key, modelo, mensajes, esquema)
        u = r.get("usage") or {}
        tok_in += u.get("prompt_tokens", 0)
        tok_out += u.get("completion_tokens", 0)
        costo += float(u.get("cost") or 0)
        comun.log_costo(rec, {"id": r.get("id"), "modelo": modelo, "tarea": "e2e_orquestador",
                              "ts": datetime.datetime.now().isoformat(), "usage": u})
        texto = r["choices"][0]["message"].get("content") or ""
        try:
            spec = extraer_json(texto)
        except (ValueError, json.JSONDecodeError) as e:
            historial.append({"ronda": rondas, "errores": ["respuesta sin JSON válido"]})
            mensajes += [{"role": "assistant", "content": texto[:4000]},
                         {"role": "user", "content": f"Tu respuesta no fue JSON válido ({e}). Devuelve solo el JSON completo."}]
            continue
        with open(os.path.join(pdir, "promo.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        codigo, salida_val = correr(["validar", proyecto], env)
        errores = [l.split()[0] for l in salida_val.splitlines() if l.startswith("E-")]
        # Rastro por ronda (spec + salida del validador) para diagnosticar qué entiende mal el modelo.
        os.makedirs(os.path.join(rec, "e2e"), exist_ok=True)
        with open(os.path.join(rec, "e2e", f"ronda_{rondas}.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        with open(os.path.join(rec, "e2e", f"ronda_{rondas}.txt"), "w", encoding="utf-8") as f:
            f.write(salida_val + "\n")
        historial.append({"ronda": rondas, "codigo": codigo, "errores": errores})
        if codigo == 0:
            ok = True
            break
        if codigo != 2 or rondas > a.rondas:
            break
        mensajes += [{"role": "assistant", "content": json.dumps(spec, ensure_ascii=False)},
                     {"role": "user", "content": "Resultado de `promo.py validar`:\n" + salida_val +
                      "\n\nCorrige exactamente lo que indica cada línea E-… y devuelve el JSON completo de promo.json."}]

    rep = {"modelo": modelo, "ok": ok, "rondas": rondas, "tokens_in": tok_in, "tokens_out": tok_out,
           "costo_usd": round(costo, 6), "segundos": round(time.time() - t0, 1), "proyecto": pdir,
           "historial": historial}
    if ok and a.render:
        codigo, out = correr(["todo", proyecto, "--borrador"], env)
        rep["render"] = {"codigo": codigo, "salida": out.splitlines()[-3:]}
    with open(os.path.join(rec, "e2e_reporte.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print(f"e2e · {modelo} · {'OK' if ok else 'FALLÓ'} en {rondas} ronda(s) · {tok_in}+{tok_out} tokens · "
          f"{costo:.4f} USD · {rep['segundos']} s")
    for h in historial:
        print(f"  ronda {h['ronda']}: {'válido' if h.get('codigo') == 0 else ', '.join(h['errores'][:6]) or 'sin errores E'}")
    if not ok:
        print("\n".join(salida_val.splitlines()[:10]))
    print(f"proyecto: {pdir}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
