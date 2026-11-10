#!/usr/bin/env python3
"""lint_voz — revisa líneas de voz en off ANTES de pagar el TTS (reutilizable por reel.py).

Reglas (modos de falla documentados en SKILL `crear-audio` y en la guía de videos promo):
  E-TTS-CIFRA       dígitos en la línea hablada: las cifras van solo en pantalla (el TTS y la
                    verificación confunden "250" con "550"); escríbela con letra o pásala al titular.
  E-TTS-PREGUNTA    '¿…?' con gpt-audio-mini: el modelo RESPONDE la pregunta ("Claro, …").
  E-TTS-DOS-PUNTOS  fragmento con dos puntos ("Cuatro dudas: A, B y C."): lo toma como
                    instrucción y lo desarrolla en voz alta (medido: 15.6 s para 7 palabras).
  E-TTS-VACIA       línea sin palabras.
  W-TTS-MARCA-INICIO   marca al inicio de la línea ("Sís-com Pro. Descárgala" sonó "Sí se compró"):
                       ponla a media frase.
  W-TTS-MARCA-REPETIDA la misma marca en dos líneas seguidas (suena a anuncio machacón).

Uso (CLI):
  python3 scripts/lint_voz.py --linea "Cotiza en segundos con ACME." --linea "…" [--modelo openai/gpt-audio-mini]
  python3 scripts/lint_voz.py --guion guion.txt [--pronunciacion promo/temas/neutro/pronunciacion.json]
Sale 2 si hay errores E-*, 0 si solo avisos o nada.

Importado:
  from lint_voz import revisar
  issues = revisar([{"ruta": "escenas[1].subtitulo[0]", "texto": "…", "tts": "…"}], modelo, marcas)
"""
import argparse
import json
import re
import sys

PUNTUACION = ".,;:!¡?¿…\"'«»()[]"


def nucleo(token):
    """Token sin la puntuación de los bordes ("ACME." → "ACME")."""
    return token.strip(PUNTUACION)


def palabras(texto):
    """Palabras como las cuenta el motor (parsearEnfasis): se separa SOLO por espacios normales;
    el espacio duro U+00A0 ("400 m²") une dos piezas en una palabra."""
    return [w for w in texto.replace("*", "").split(" ") if w]


def _marca(token, marcas):
    n = nucleo(token).lower()
    return next((m for m in marcas if m.lower() == n), None)


def revisar(lineas, modelo="openai/gpt-audio-mini", marcas=()):
    """lineas: [{"ruta", "texto" (pantalla), "tts" (hablado)}] → lista de issues del contrato."""
    issues = []

    def add(sev, codigo, ruta, msg, arreglo):
        issues.append({"codigo": codigo, "severidad": sev, "ruta": ruta, "msg": msg, "arreglo": arreglo})

    responde = "gpt-audio" in (modelo or "")
    previa = set()
    for ln in lineas:
        ruta, texto = ln.get("ruta", "-"), ln.get("texto", "")
        tts = ln.get("tts", texto)
        toks = palabras(texto)
        if not toks:
            add("E", "E-TTS-VACIA", ruta, "la línea no tiene palabras.", "Escribe la frase o quita el subtitulo.")
            previa = set()
            continue
        if re.search(r"\d", tts):
            add("E", "E-TTS-CIFRA", ruta, f"«{texto}» tiene cifras: las cifras van solo en pantalla.",
                "Escribe el número con letra o muévelo al titular.")
        if responde and ("?" in tts or "¿" in tts):
            add("E", "E-TTS-PREGUNTA", ruta, f"«{texto}» es pregunta: el modelo la responde en vez de leerla.",
                "Reescríbela como afirmación (sujeto + verbo).")
        if responde and re.search(r":\s*\S", tts):
            add("E", "E-TTS-DOS-PUNTOS", ruta, f"«{texto}» tiene dos puntos: el modelo lo toma como instrucción.",
                "Reescríbela como una oración con verbo conjugado, sin dos puntos.")
        m0 = _marca(toks[0], marcas)
        if m0:
            add("W", "W-TTS-MARCA-INICIO", ruta, f"la línea empieza con la marca {m0} (se oye mal al arranque).",
                "Ponla a media frase.")
        actuales = {m for m in (_marca(t, marcas) for t in toks) if m}
        for m in sorted(actuales & previa):
            add("W", "W-TTS-MARCA-REPETIDA", ruta, f"{m} aparece en dos líneas seguidas.",
                "Deja la marca en una sola de las dos.")
        previa = actuales
    return issues


def main():
    ap = argparse.ArgumentParser(description="Lint de líneas de voz en off (antes del TTS)")
    ap.add_argument("--linea", action="append", default=[], help="línea a revisar (repetible)")
    ap.add_argument("--guion", help="archivo con una línea por renglón")
    ap.add_argument("--modelo", default="openai/gpt-audio-mini")
    ap.add_argument("--pronunciacion", help="pronunciacion.json del tema (para la lista de marcas)")
    a = ap.parse_args()
    textos = list(a.linea)
    if a.guion:
        with open(a.guion, encoding="utf-8") as f:
            textos += [l.strip() for l in f if l.strip()]
    marcas = []
    if a.pronunciacion:
        with open(a.pronunciacion, encoding="utf-8") as f:
            marcas = json.load(f).get("marcas", [])
    issues = revisar([{"ruta": f"linea[{i + 1}]", "texto": t} for i, t in enumerate(textos)], a.modelo, marcas)
    for i in issues:
        print(f"{i['codigo']}  {i['ruta']}: {i['msg']} {i['arreglo']}")
    errores = sum(1 for i in issues if i["severidad"] == "E")
    print(f"lint voz: {len(textos)} líneas — {errores} errores, {len(issues) - errores} avisos")
    return 2 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
