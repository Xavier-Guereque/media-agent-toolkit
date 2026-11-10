#!/usr/bin/env python3
"""revisar_hoja — QA visual consultiva de una hoja de cuadros (recursos/cuadros/hoja.jpg).

EXPERIMENTAL y CONSULTIVO. La QA del DOM del motor es la autoridad (determinista y gratis). Este paso
manda la hoja a un modelo de visión con una lista de verificación fija y devuelve lo que vea en el formato
compacto de `promo.py validar`. Nunca bloquea (sale 0 aunque encuentre algo) y NO forma parte de `todo`.

Medido el 2026-09-28 (hoja de 25 cuadros): gemini-2.5-flash detectó un lockup cortado pero marcó 24 falsos
positivos en una hoja sana; gemini-3.8-flash y deepseek-v4.1-flash dieron 0 falsos positivos pero no vieron
el defecto. Úsalo como segunda opinión; cada defecto real que aparezca debe convertirse en una regla de la
QA del DOM (ver docs/Lecciones-2026-09-28-motor-promo.md).

Uso:
  python3 scripts/revisar_hoja.py proyectos/<slug>_<DDMMAAAA>/recursos/cuadros/hoja.jpg [--modelo …] [--log …]

Registra la llamada en el costos.jsonl del proyecto (tarea "revision_visual", AGENT §10).
"""
import argparse
import base64
import datetime
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INSTRUCCIONES = """Eres QA visual de videos verticales 9:16 para redes. Recibes una hoja de contacto: cada cuadro
tiene debajo una etiqueta "t=segundos · escenas[i] tipo". Reporta SOLO problemas visibles y concretos:
1. Texto cortado, partido de forma rara o que se sale del cuadro (incluido el logo y su producto/versión).
2. Textos que se enciman y se leen a la vez dentro de un mismo cuadro (IGNORA fundidos de transición entre escenas).
3. Palabras repetidas o duplicadas por error (p. ej. la marca dos veces seguidas: "ACME ACME").
4. Elementos que tapan el titular (arriba) o el subtítulo (pastilla abajo).
5. Íconos o imágenes rotas, vacías o deformadas; contraste ilegible.
NO son defectos (son animaciones intencionales, no los reportes):
- Un titular con solo las primeras palabras visibles o con palabras tenues: se está escribiendo palabra por palabra.
- Palabras grises en la pastilla del subtítulo: es karaoke (aún no "se dicen").
- Elementos semitransparentes, desenfocados o encimados en un cuadro de transición entre escenas.
- Mensajes de chat que suben y quedan recortados bajo la cabecera de la tarjeta: es el scroll normal del chat.
- Lo pequeño de las miniaturas: juzga la composición, no la nitidez.
Reporta solo lo que seguiría mal cuando la animación termina. Ante la duda, NO lo reportes.
No opines de estilo, copy ni diseño si no hay un defecto. Si no hay problemas, devuelve ok=true.
Responde SOLO JSON: {"ok": bool, "problemas": [{"t": número, "escena": "escenas[i]", "tipo": "cortado|encimado|duplicado|tapado|roto|contraste", "detalle": "…", "arreglo": "cambio concreto en promo.json"}]}"""


def revisar(hoja, modelo, key, log=None):
    with open(hoja, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    cuerpo = {
        "model": modelo,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "usage": {"include": True},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": INSTRUCCIONES},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    }
    res = comun.post_openrouter(cuerpo, key, timeout=180)   # con reintentos en 429/5xx
    if log:
        comun.log_costo(os.path.dirname(log), {"id": res.get("id"), "modelo": modelo, "tarea": "revision_visual",
                                               "ts": datetime.datetime.now().isoformat(), "usage": res.get("usage")})
    txt = res["choices"][0]["message"].get("content") or "{}"
    ini, fin = txt.find("{"), txt.rfind("}")
    return json.loads(txt[ini:fin + 1]), res.get("usage") or {}


def main():
    ap = argparse.ArgumentParser(description="QA visual consultiva de la hoja de cuadros")
    ap.add_argument("hoja")
    ap.add_argument("--modelo", help="default: config.json > promo.modelo_revision (o google/gemini-3.8-flash)")
    ap.add_argument("--log", help="costos.jsonl (default: el del proyecto de la hoja)")
    a = ap.parse_args()
    if not os.path.exists(a.hoja):
        print(f"ERROR no existe {a.hoja}. Corre antes: python3 scripts/promo.py cuadros <proyecto>")
        return 2
    cfg = comun.cargar_config(REPO)
    # Por defecto el modelo que no dio falsos positivos en la medición (ver docstring).
    modelo = a.modelo or cfg.get("promo", {}).get("modelo_revision", "google/gemini-3.8-flash")
    rec = os.path.dirname(os.path.dirname(os.path.abspath(a.hoja)))  # …/recursos
    log = a.log or os.path.join(rec, "costos.jsonl")
    try:
        r, u = revisar(a.hoja, modelo, comun.api_key(REPO), log)
    except (urllib.error.URLError, ValueError, KeyError) as e:
        print(f"AVISO la revisión visual no se pudo hacer ({e}); no bloquea: sigue con la QA del motor.")
        return 0
    probs = r.get("problemas") or []
    costo = float(u.get("cost") or 0)
    print(f"revisión visual · {modelo} · {len(probs)} problema(s) · {costo:.4f} USD")
    for p in probs[:8]:
        print(f"V-{str(p.get('tipo', 'visual')).upper()}  t={p.get('t')} {p.get('escena', '')}: {p.get('detalle', '')} {p.get('arreglo', '')}".rstrip())
    print("Siguiente: " + ("corrige promo.json y vuelve a validar." if probs else "si la QA del motor está en 0, sigue con render/todo."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
