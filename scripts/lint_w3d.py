#!/usr/bin/env python3
"""Lint de anclas W() de un script de escenas 3D (Blender) contra los tiempos por palabra de la lección.

Las escenas 3D de un curso se sincronizan con la voz anclando cada animación a una palabra: `W("riel", 2)` es la
2.ª aparición de «riel» en la escena (ver docs/Lecciones-2026-11-11-drywall-vanos-animado). Antes de un render de
horas conviene revisar:
  E-W-NOEXISTE  la palabra (o su n-ésima aparición) no está en la narración de la escena → el script se detiene;
  W-W-NUMERO    ancla numérica: Whisper desordena los números («ochenta@24.0» antes de «en@24.5»);
  W-W-REPETIDA  la palabra se repite en la escena y la llamada no dice cuál (n implícito = 1);
  E-W-HASTA     `hasta=W(...)` cae antes de la aparición del mismo rótulo o cota → queda visible toda la escena.

Uso: python3 scripts/lint_w3d.py <escenas3d.py> <tiempos.json>     (sale con 1 si hay errores)
Convención: cada escena es `def escena_<id>(cam, mira):` y `<id>` coincide con el de tiempos.json.
"""
import json
import re
import sys

NUMEROS = set("cero uno una dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince veinte "
              "veinticuatro treinta cuarenta cincuenta sesenta setenta ochenta noventa cien ciento mil".split())
LLAMADA = re.compile(r'W\("([^"]+)"(?:\s*,\s*(\d+))?')
ESCENA = re.compile(r"def escena_(\w+)\(cam, mira\):(.*?)(?=\ndef |\n[A-Z_]+ = |\Z)", re.S)


def norm(w):
    return re.sub(r"[^\wáéíóúñü]", "", w.lower())


def _tiempo(escena, palabra, n):
    k = 0
    for p in escena["palabras"]:
        if norm(p["w"]) == norm(palabra):
            k += 1
            if k == n:
                return p["a"] - escena["inicio"]
    return None


def revisar(fuente, tiempos):
    """Devuelve [{codigo, escena, mensaje}] para el código fuente `fuente` y el dict de tiempos.json."""
    esc = {e["id"]: e for e in tiempos["escenas"]}
    out = []
    for m in ESCENA.finditer(fuente):
        eid, cuerpo = m.group(1), m.group(2)
        if eid not in esc:
            continue
        e = esc[eid]
        palabras = [norm(p["w"]) for p in e["palabras"]]
        for c in LLAMADA.finditer(cuerpo):
            w, n = c.group(1), int(c.group(2) or 1)
            if _tiempo(e, w, n) is None:
                out.append({"codigo": "E-W-NOEXISTE", "escena": eid, "mensaje": f"W({w!r}, {n}) no está en la voz"})
            if norm(w) in NUMEROS:
                out.append({"codigo": "W-W-NUMERO", "escena": eid, "mensaje": f"ancla numérica W({w!r})"})
            if palabras.count(norm(w)) > 1 and not c.group(2):
                out.append({"codigo": "W-W-REPETIDA", "escena": eid,
                            "mensaje": f"«{w}» aparece {palabras.count(norm(w))} veces: usa W({w!r}, n)"})
        for st in re.split(r"\n(?=    \S)", cuerpo):          # una sentencia por bloque de primer nivel
            if "hasta=W(" not in st:
                continue
            antes, despues = st.split("hasta=", 1)
            ws, h = LLAMADA.findall(antes), LLAMADA.search(despues)
            if not ws or not h:
                continue
            ta = _tiempo(e, ws[-1][0], int(ws[-1][1] or 1))
            th = _tiempo(e, h.group(1), int(h.group(2) or 1))
            if ta is not None and th is not None and th <= ta:
                out.append({"codigo": "E-W-HASTA", "escena": eid,
                            "mensaje": f"hasta=W({h.group(1)!r}) {th:.1f} s ≤ aparición W({ws[-1][0]!r}) {ta:.1f} s"})
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    fuente = open(argv[0], encoding="utf-8").read()
    tiempos = json.load(open(argv[1], encoding="utf-8"))
    problemas = revisar(fuente, tiempos)
    for p in problemas:
        print(f"{p['codigo']}  {p['escena']}: {p['mensaje']}")
    errores = sum(p["codigo"].startswith("E-") for p in problemas)
    print("lint W():", "limpio" if not problemas else f"{errores} errores · {len(problemas) - errores} avisos")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
