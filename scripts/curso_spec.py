#!/usr/bin/env python3
"""curso_spec — constructores para escribir `curso.json` largos (cursos de muchas lecciones) sin repetir llaves.

Producen exactamente los diccionarios del contrato de `scripts/curso.py` (skill `crear-curso`, [[Motor-Curso]]):
actores del mundo continuo, acciones de cámara, escenas por tipo, preguntas y lecciones. Úsalos desde un script del
proyecto (`recursos/armar_curso.py`) cuando el curso tiene más de unas cuantas lecciones:

    sys.path.insert(0, os.path.join(<repo>, "scripts"))
    from curso_spec import *  # noqa: F403
    l1 = leccion("m1-l1", "Tres preguntas", "Nombrar color, insignia y silueta", "Lo sabrás cuando…", "recordar", "concepto",
                 actores=[imagen("oficial", "oficial-mando", -420, "Color e insignia"), dato("c", ["división"], -420, 330)],
                 escenas=[gancho("Ves una escena…", "Sin sonido, todo sigue a la vista.", [accion("aparece", "oficial", "escena")]),
                          objetivo("Al terminar vas a…", "Color", "silueta"), …],
                 preguntas=[pregunta("p1", "m1-l1", "¿Qué señal revela el rango?", ["El color", "La insignia"], 1, "…", ["…", "…"])],
                 consigna="…", rubrica="…")

Convenciones (verificadas en el curso de Star Trek de 21 lecciones, [[Lecciones-2026-11-01-muestra-star-trek-flota]]):
  - `en` de una acción es la PALABRA de la narración en la que ocurre (se sincroniza con los tiempos medidos).
  - Los ids de escena siguen la secuencia e1 gancho · e2 objetivo · e3/e4 concepto · e5 ejemplo · e6 pregunta ·
    e7 resumen · e8 cierre; cada constructor trae su id y duración mínima por defecto.
  - Los valores None se omiten: el JSON queda limpio y `curso.py validar` no ve campos vacíos.
"""

__all__ = ["accion", "junto", "plano_general", "enfoca", "imagen", "imagen_ancha", "dato", "panel", "fila_imagenes",
           "gancho", "objetivo", "concepto", "ejemplo", "pregunta_escena", "resumen", "cierre", "pregunta", "leccion"]


# ── acciones de cámara y actores ────────────────────────────────────────────────────────────────────────────────────
def accion(accion, actor=None, en=None, **k):
    """{"accion", "actor", "en", …extra} sin claves None. accion: aparece | resalta | enfoca | …"""
    return {a: b for a, b in {"accion": accion, "actor": actor, "en": en, **k}.items() if b is not None}


def junto(accion_, actor=None, **k):
    """Acción simultánea con la anterior (`junto: true`); acepta `retraso` en s."""
    return accion(accion_, actor, junto=True, **k)


def plano_general(en, d=1):
    """La cámara vuelve al plano general en la palabra `en` (duración `d` s)."""
    return accion("enfoca", None, en, d=d)


def enfoca(actor, en, z=2.0, **k):
    """Acercamiento `z`× al actor en la palabra `en`; `dx`/`dy` desplazan el punto (p. ej. al cuello de un uniforme)."""
    return accion("enfoca", actor, en, z=z, **k)


def imagen(id, clave, x, pie, w=340, h=510, y=-30, **k):
    """Actor imagen vertical (retrato/figura) de recursos/img/<clave>; x/y desde el centro del escenario."""
    return {"id": id, "tipo": "imagen", "clave": clave, "x": x, "y": y, "w": w, "h": h, "pie": pie, **k}


def imagen_ancha(id, clave, x, pie, w=660, h=440, y=-40, **k):
    """Actor imagen apaisada (naves, vehículos, equipos)."""
    return imagen(id, clave, x, pie, w, h, y, **k)


def dato(id, partes, x, y, fs=44, sep=" ", **k):
    """Actor texto/dato: `partes` se escriben una tras otra separadas por `sep`."""
    return {"id": id, "tipo": "dato", "partes": partes, "x": x, "y": y, "fs": fs, "sep": sep, **k}


def panel(id, x, y, titulo, w=760, h=470, lineas=None):
    """Actor panel con título y líneas (tablas cortas, comparativas)."""
    return {"id": id, "tipo": "panel", "x": x, "y": y, "w": w, "h": h, "titulo": titulo, "lineas": lineas or []}


def fila_imagenes(prefijo, nombres, xs=(-520, 0, 520), **k):
    """Fila de imágenes `<prefijo>-<id>`: nombres = [(id, pie), …] en las posiciones `xs`."""
    return [imagen(c, f"{prefijo}-{c}", x, n, **k) for (c, n), x in zip(nombres, xs)]


# ── escenas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def gancho(tts, texto, acciones, id="e1", min=5):
    return {"id": id, "tipo": "gancho", "min": min, "tts": tts, "pantalla": {"texto": texto, "acciones": acciones}}


def objetivo(tts, *marcas, id="e2", min=5, colores=("acento", "alerta")):
    """Escena de objetivo en el plano "estacion"; cada marca es una palabra de la narración que se señala."""
    return {"id": id, "tipo": "objetivo", "min": min, "tts": tts,
            "pantalla": {"plano": "estacion", "marcas": [{"en": m, "texto": m, "color": c} for m, c in zip(marcas, colores)]}}


def concepto(id, tts, titular, acciones, min=8):
    return {"id": id, "tipo": "concepto", "min": min, "tts": tts, "pantalla": {"titular": titular, "acciones": acciones}}


def ejemplo(tts, enunciado, solucion, acciones, id="e5", min=8, titular="Ejemplo"):
    """`solucion` = [(texto, palabra_en), …]."""
    return {"id": id, "tipo": "ejemplo", "min": min, "tts": tts,
            "pantalla": {"titular": titular, "enunciado": enunciado, "solucion": [{"texto": t, "en": e} for t, e in solucion],
                         "acciones": acciones}}


def pregunta_escena(ref, tts, retro, id="e6", min=6):
    """Escena que plantea la pregunta `ref` y lee la retroalimentación `retro` tras responder."""
    return {"id": id, "tipo": "pregunta", "pregunta_ref": ref, "min": min, "tts": tts, "tts_retro": retro}


def resumen(tts, puntos, acciones, id="e7", min=6):
    """`puntos` = [(texto, palabra_en), …]."""
    return {"id": id, "tipo": "resumen", "min": min, "tts": tts,
            "pantalla": {"puntos": [{"texto": t, "en": e} for t, e in puntos], "acciones": acciones}}


def cierre(tts, id="e8", min=4):
    return {"id": id, "tipo": "cierre", "min": min, "tts": tts}


# ── preguntas y lecciones ───────────────────────────────────────────────────────────────────────────────────────────
def pregunta(id, objetivo_ref, enunciado, opciones, correcta, retro, retro_opciones):
    """Pregunta de opción múltiple; `correcta` es el índice (0…) y `retro_opciones` explica cada opción."""
    return {"id": id, "objetivo_ref": objetivo_ref, "enunciado": enunciado, "opciones": opciones, "correcta": correcta,
            "retro": retro, "retro_opciones": retro_opciones}


def leccion(id, titulo, objetivo, criterio, bloom, tipo, actores, escenas, preguntas, consigna, rubrica, min_practica=5):
    """Lección completa: mundo continuo con `actores`, escenas, preguntas y práctica con rúbrica."""
    return {"id": id, "titulo": titulo, "objetivo": objetivo, "criterio_exito": criterio, "nivel_bloom": bloom, "tipo": tipo,
            "mundo": {"actores": actores}, "escenas": escenas, "preguntas": preguntas,
            "practica": {"consigna": consigna, "rubrica": rubrica, "min": min_practica}}
