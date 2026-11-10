#!/usr/bin/env python3
"""curso — cursos en video: el agente solo escribe curso.json; el oficio pedagógico y visual lo pone el motor.

  python3 scripts/curso.py nuevo <slug>                      crea proyectos/<slug>_<DDMMAAAA>/ desde cursos/ejemplo
  python3 scripts/curso.py validar <proyecto> [--json]       contrato + lints pedagógicos (sin LLM, 0 USD)
  python3 scripts/curso.py voz <proyecto> [--leccion id] [--solo-lint]     TTS por escena, tiempos medidos, .srt/.vtt
  python3 scripts/curso.py componer <proyecto> [--leccion id]              remotion.json y props por lección
  python3 scripts/curso.py qa <proyecto> [--leccion id] [--jev] [--umbral 0.7] [--sin-stills]
  python3 scripts/curso.py render <proyecto> [--leccion id] [--borrador] [--workers N|50%]
  python3 scripts/curso.py carta <proyecto>                  carta descriptiva, quiz y transcripciones
  python3 scripts/curso.py reproductor <proyecto>            reproductor.html: el video se pausa y el alumno responde
  python3 scripts/curso.py todo <proyecto> [--borrador] [--jev] [--qa]     validar → voz → componer → qa → render → carta → reproductor
  python3 scripts/curso.py estado <proyecto>  ·  ayuda

Salida: 0 ok · 1 interno · 2 corrige curso.json · 3 entorno · 4 API. Metodología: docs/Metodologia-Cursos-Video.md;
arquitectura y códigos: docs/Motor-Curso.md.
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import decision  # noqa: E402
import lint_voz  # noqa: E402
import narrar  # noqa: E402
import promo  # noqa: E402
import remotion  # noqa: E402
import sonido  # noqa: E402
import subtitulos  # noqa: E402
import voz  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_ISSUES = 8
MARCA_INI = "### curso render — inicio (lo reescribe scripts/curso.py render)"
MARCA_FIN = "### curso render — fin"
RE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TIPOS_LECCION = ("concepto", "procedimiento", "ejemplo-resuelto", "caso", "repaso")
TIPOS_ESCENA = ("gancho", "objetivo", "activacion", "preentrenamiento", "concepto", "pasos", "ejemplo", "caso",
                "screencast", "pregunta", "resumen", "cierre")
PANTALLA_REQ = {"gancho": ("texto",), "activacion": ("texto",), "preentrenamiento": ("terminos",), "concepto": ("elementos",),
                "pasos": ("pasos",), "ejemplo": ("enunciado", "solucion"), "caso": ("tarjetas",), "screencast": ("clip",),
                "resumen": ("puntos",)}
LISTAS = ("elementos", "pasos", "solucion", "tarjetas", "puntos", "terminos", "acciones", "marcas")
ICONOS = ("camara", "grabador", "switch", "router", "servidor", "pc", "telefono", "nube", "persona", "disco")
ACTORES = ("zona", "enlace", "dato", "panel", "imagen") + ICONOS
ACCIONES = ("aparece", "oculta", "mueve", "divide", "une", "conecta", "envia", "resalta", "llave", "enfoca", "escribe", "clic", "transforma", "copia")
SIN_ACTOR = ("enfoca", "clic")  # sin actor apuntan a un punto del mundo
ACCIONES_IMAGEN = ("aparece", "oculta", "mueve", "enfoca", "clic")
ESCENAS_CON_IMG = ("concepto", "pasos", "ejemplo", "caso", "resumen")  # las demás no tienen lugar para fotos
MODOS = {"proposito": ("aprendizaje", "presentacion"), "evaluacion": ("intercalada", "entre-lecciones", "ambas", "ninguna"),
         "visual": ("animado", "imagenes", "mixto")}
SFX_ACCION = {"aparece": "pop", "copia": "pop", "enfoca": "whoosh", "clic": "tick", "resalta": "tick", "llave": "tick", "escribe": "tecleo", "conecta": "tick"}
CAPITULOS = {"gancho": "Inicio", "objetivo": "Objetivo", "activacion": "Recuerda", "preentrenamiento": "Términos clave", "concepto": "Concepto",
             "pasos": "Paso a paso", "ejemplo": "Ejemplo", "caso": "Caso", "screencast": "Demostración", "pregunta": "Comprobación",
             "resumen": "Resumen", "cierre": "Cierre"}
TECNICAS = {"concepto": "exposición con dibujo dinámico", "pasos": "demostración paso a paso", "ejemplo": "ejemplo resuelto",
            "caso": "estudio de caso", "screencast": "demostración en pantalla", "pregunta": "preguntas de recuperación con retroalimentación",
            "resumen": "síntesis", "activacion": "activación de saberes previos", "preentrenamiento": "pre-entrenamiento de términos"}
SEGUNDA_PERSONA = re.compile(r"\b(tú|tu|tus|te|ti|vas|vamos|puedes|tienes|mira|elige|comprueba|fíjate|sigue|anota|practica)\b", re.I)
DEF_CURSOS = {"lufs": -16, "max_min_leccion": 10, "ideal_min_leccion": 6, "max_s_escena": 45, "max_s_sin_pregunta": 360,
              "lecciones_modulo": [3, 5], "horas_modulo": [1, 2], "min_preguntas_leccion": 1, "opciones_min": 2, "opciones_max": 4,
              "min_por_pregunta": 1.5, "max_puntos": 4, "max_palabras_punto": 8, "max_palabras_pantalla": 40,
              "max_car_linea_ejemplo": 42, "max_s_estatica": 8, "sonido": {"sfx": False, "sfx_lufs": -33}, "subtitulos": {"max_car": 42, "cps_max": 17}, "bloom": {}, "temas": {}, "tema": "claro",
              "aviso_ia": "", "acreditacion": {"minimo_pct": 80, "reintentos": 2}, "jev": {"umbral": 0.7}, "costo_voz_usd_min": {},
              "mezcla": {"voz_lufs": -16, "musica_lufs": -26}}


def cursos_cfg():
    cfg = comun.cargar_config(REPO)
    return cfg, {**DEF_CURSOS, **(cfg.get("cursos") or {})}


def raiz(a):
    return os.path.abspath(getattr(a, "raiz", None) or os.environ.get("CURSO_RAIZ") or REPO)


class Curso:
    """Rutas del contrato de carpetas de un curso (AGENT §13 + docs/Motor-Curso)."""

    def __init__(self, carpeta):
        self.dir = os.path.abspath(carpeta)
        self.nombre = os.path.basename(self.dir)
        self.slug = re.sub(r"_\d{8}$", "", self.nombre)
        self.spec = os.path.join(self.dir, "curso.json")
        self.rec = os.path.join(self.dir, "recursos")
        self.interno = os.path.join(self.rec, "curso")
        self.lecciones = os.path.join(self.dir, "lecciones")
        self.info = os.path.join(self.dir, "info.txt")
        self.costos = os.path.join(self.rec, "costos.jsonl")

    def leccion(self, lid, k=0, n=1, lufs=-16):
        p = remotion.Proyecto(os.path.join(self.lecciones, lid))
        p.avance_dir, p.avance_rango, p.etiqueta, p.lufs = self.rec, (100.0 * k / n, 100.0 * (k + 1) / n), f"lección {lid}", float(lufs)
        return p


def resolver(ref, a):
    if os.sep in ref or ref.startswith(".") or os.path.isfile(os.path.join(ref, "curso.json")):
        return Curso(ref)
    base = os.path.join(raiz(a), "proyectos")
    hay = [x for x in (os.listdir(base) if os.path.isdir(base) else []) if os.path.isfile(os.path.join(base, x, "curso.json"))]
    slug = lambda x: re.sub(r"_\d{8}$", "", x)  # noqa: E731
    d = [x for x in hay if x == ref] or [x for x in hay if slug(x) == ref] or [x for x in hay if x.startswith(ref)]
    if not d:
        print(f"ERROR no encuentro el curso '{ref}'. Siguiente: python3 scripts/curso.py nuevo <slug>")
        raise SystemExit(2)
    if len({slug(x) for x in d}) > 1:
        print(f"ERROR '{ref}' es ambiguo: {', '.join(sorted(d))}. Siguiente: usa el nombre completo.")
        raise SystemExit(2)
    d.sort(key=lambda x: (x[-4:], x[-6:-4], x[-8:-6]))      # DDMMAAAA no ordena por fecha como texto
    return Curso(os.path.join(base, d[-1]))


def cargar(c):
    if not os.path.exists(c.spec):
        print(f"ERROR falta {c.spec}. Siguiente: python3 scripts/curso.py nuevo <slug>")
        raise SystemExit(2)
    try:
        with open(c.spec, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as ex:
        print(f"E-CURSO-JSON  curso.json: {ex.msg} (línea {ex.lineno}). Corrige el JSON.")
        raise SystemExit(2)


def lecciones(spec):
    """[(ruta, módulo, lección)] de todo el curso."""
    return [(f"modulos[{i}].lecciones[{j}]", m, l) for i, m in enumerate(spec.get("modulos") or []) if isinstance(m, dict)
            for j, l in enumerate(m.get("lecciones") or []) if isinstance(l, dict)]


def filtradas(spec, a):
    todas = lecciones(spec)
    lid = getattr(a, "leccion", None)
    if not lid:
        return todas
    sel = [x for x in todas if x[2].get("id") == lid]
    if not sel:
        print(f"E-CURSO-ID  --leccion: no existe {lid!r}. Lecciones: {', '.join(str(x[2].get('id')) for x in todas)}.")
        raise SystemExit(2)
    return sel


def tema_de(spec, cur):
    est = (spec.get("curso") or {}).get("estilo") or {}
    nombre = est.get("tema") or cur["tema"]
    return {**(cur["temas"].get(nombre) or {}), **(est.get("colores") or {})}


def _lum(h):
    v = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def modo_de(spec):
    """Sin `curso.modo` el curso se valida como siempre; `visual` sin declarar no exige nada."""
    m = (spec.get("curso") or {}).get("modo")
    m = m if isinstance(m, dict) else {}
    proposito = m.get("proposito") or "aprendizaje"
    defecto = "ninguna" if proposito == "presentacion" else "intercalada"
    return {"proposito": proposito, "evaluacion": m.get("evaluacion") or defecto, "visual": m.get("visual")}


def expandir_escenas(leccion, cur=None):
    """Cada escena `pregunta` se vuelve dos: plantear (con pausa para pensar) y resolver (revela y explica)."""
    preguntas = {p.get("id"): p for p in leccion.get("preguntas") or [] if isinstance(p, dict)}
    salida = []
    for e in leccion.get("escenas") or []:
        if e.get("tipo") == "objetivo":
            e = {**e, "pantalla": {"objetivo": leccion.get("objetivo"), "criterio_exito": leccion.get("criterio_exito"), **(e.get("pantalla") or {})}}
        if e.get("tipo") != "pregunta":
            salida.append(e)
            continue
        q = preguntas.get(e.get("pregunta_ref")) or {}
        base = {"enunciado": q.get("enunciado"), "opciones": q.get("opciones"), "correcta": q.get("correcta")}
        salida.append({**e, "plantea": True, "pantalla": {**base, "revelar": False}})
        pant = {**base, "revelar": True, "retro": q.get("retro")}
        if e.get("retro_acciones"):
            pant["acciones"] = e["retro_acciones"]
        salida.append({"id": f"{e['id']}-r", "tipo": "pregunta", "min": 5, "tts": e.get("tts_retro") or q.get("retro"), "pantalla": pant})
    return salida


# ---------------------------------------------------------------- validar
def validar_curso(spec, c, cur, cfg, medidas=None):
    errs, avis = [], []

    def e(cod, ruta, msg, arreglo):
        errs.append({"codigo": cod, "severidad": "E", "ruta": ruta, "msg": msg, "arreglo": arreglo})

    def w(cod, ruta, msg, arreglo):
        avis.append({"codigo": cod, "severidad": "W", "ruta": ruta, "msg": msg, "arreglo": arreglo})

    if not isinstance(spec, dict):
        e("E-CURSO-JSON", "-", "curso.json no es un objeto", "Parte de cursos/ejemplo/curso.json.")
        return errs, avis
    if spec.get("version") != 1:
        e("E-CURSO-VERSION", "version", f"{spec.get('version')!r}", "Pon \"version\": 1.")
    k = spec.get("curso")
    if not isinstance(k, dict):
        e("E-CURSO-CAMPO", "curso", "falta el objeto curso", "Agrega curso {titulo, publico, …}.")
        k = {}
    modo = modo_de(spec)
    _validar_modo(k, modo, e, w)
    pres = modo["proposito"] == "presentacion"
    sin_eval = modo["evaluacion"] == "ninguna"
    campos = ["titulo", "publico", "objetivo_general"]
    if not pres:
        campos += ["perfil_ingreso", "duracion_h", "modalidad"] + ([] if sin_eval else ["evaluacion"])
    for campo in campos:
        if k.get(campo) in (None, ""):
            e("E-CURSO-CAMPO", f"curso.{campo}", "campo obligatorio ausente (carta descriptiva EC0301)", f"Agrega {campo}.")
    for campo in ("area_tematica", "tutor"):
        if not k.get(campo) and not pres and not sin_eval:
            w("W-CURSO-DC3", f"curso.{campo}", "lo pide la constancia DC-3 en cursos a distancia", f"Agrega {campo} si el curso respaldará una DC-3.")
    ev = k.get("evaluacion") if isinstance(k.get("evaluacion"), dict) else {}
    for campo in ("diagnostica", "formativa", "sumativa"):
        if k.get("evaluacion") and not ev.get(campo) and not pres:
            e("E-CURSO-CAMPO", f"curso.evaluacion.{campo}", "EC0301 pide los tres momentos de evaluación", f"Describe la evaluación {campo}.")
    est = k.get("estilo") or {}
    tema = tema_de(spec, cur)
    if not tema:
        e("E-CURSO-TEMA", "curso.estilo.tema", f"{est.get('tema')!r} no existe en config.json > cursos.temas", f"Usa {' | '.join(cur['temas'])}.")
    for nombre in ("texto", "tenue", "acento", "correcta"):
        if tema.get(nombre) and contraste(tema[nombre], tema["fondo"]) < 4.5:
            w("W-CURSO-CONTRASTE", f"estilo.{nombre}", f"contraste {contraste(tema[nombre], tema['fondo']):.1f}:1 contra el fondo (< 4.5:1, WCAG 1.4.3)", "Elige un color con más contraste.")
    if est.get("musica"):
        w("W-CURSO-MUSICA", "curso.estilo.musica", "la evidencia desaconseja música bajo narración", "Déjala en false salvo razón explícita.")
        if not est.get("cama") or not os.path.exists(os.path.join(c.rec, est["cama"])):
            e("E-CURSO-RECURSO", "curso.estilo.cama", "con música hace falta una cama en recursos/", "Copia el audio a recursos/ y pon su ruta en estilo.cama.")

    bloom = cur["bloom"]
    verbos = {v: n for n, lista in bloom.items() for v in lista}
    ids_mod, ids_lec = set(), set()
    mods = spec.get("modulos")
    if not isinstance(mods, list) or not mods:
        e("E-CURSO-CAMPO", "modulos", "falta la lista de módulos", "Agrega al menos un módulo.")
        mods = []
    for i, m in enumerate(mods):
        ruta = f"modulos[{i}]"
        if not isinstance(m, dict):
            e("E-CURSO-CAMPO", ruta, "no es un objeto", "Usa {id, titulo, objetivo, lecciones}.")
            continue
        for campo in ("id", "titulo", "lecciones") if pres else ("id", "titulo", "objetivo", "lecciones"):
            if not m.get(campo):
                e("E-CURSO-CAMPO", f"{ruta}.{campo}", "campo obligatorio ausente", f"Agrega {campo}.")
        _id(e, m.get("id"), f"{ruta}.id", ids_mod)
    objetivos = {str(m.get("id")) for m in mods if isinstance(m, dict)} | {str(l.get("id")) for _, _, l in lecciones(spec)}
    seg_mod = {}
    for ruta, m, l in lecciones(spec):
        _validar_leccion(l, ruta, m, cur, verbos, c, e, w, ids_lec, objetivos, seg_mod, medidas or {}, modo)
    if pres:
        return errs, avis
    lo, hi = cur["lecciones_modulo"]
    h_lo, h_hi = cur["horas_modulo"]
    total_seg = 0.0
    for i, m in enumerate(mods):
        if not isinstance(m, dict):
            continue
        n = len(m.get("lecciones") or [])
        seg = seg_mod.get(str(m.get("id")), 0.0)
        total_seg += seg
        horas = seg / 3600
        if not lo <= n <= hi or not h_lo <= horas <= h_hi:
            w("W-CURSO-MODULO", f"modulos[{i}]", f"{n} lecciones y {horas:.1f} h (convención: {lo}–{hi} lecciones, {h_lo}–{h_hi} h)", "Ajusta el módulo si el curso no es una muestra.")
    if isinstance(k.get("duracion_h"), (int, float)) and total_seg:
        est_h = total_seg / 3600
        if abs(k["duracion_h"] - est_h) > 0.3 * max(est_h, 1e-6):
            w("W-CURSO-HORAS", "curso.duracion_h", f"declara {k['duracion_h']} h y se estiman {est_h:.2f} h", f"Ajusta duracion_h a ≈ {est_h:.2f} (la DC-3 lleva las horas).")
    return errs, avis


def _validar_modo(k, modo, e, w):
    m = k.get("modo")
    if m is None:
        return
    if not isinstance(m, dict):
        e("E-CURSO-MODO", "curso.modo", "no es un objeto", "Usa {proposito, evaluacion, visual}.")
        return
    for campo, valor in m.items():
        if campo not in MODOS:
            e("E-CURSO-MODO", f"curso.modo.{campo}", "campo desconocido", f"Usa {' | '.join(MODOS)}.")
        elif valor not in MODOS[campo]:
            e("E-CURSO-MODO", f"curso.modo.{campo}", f"{valor!r}", f"Usa {' | '.join(MODOS[campo])}.")
    if modo["proposito"] == "aprendizaje" and modo["evaluacion"] == "ninguna":
        w("W-CURSO-SIN-EVALUACION", "curso.modo.evaluacion", "sin preguntas no hay efecto de recuperación (d ≈ 1.0–1.4, Szpunar 2013)", "Usa evaluacion intercalada, o proposito presentacion si no busca aprendizaje.")
    if modo["evaluacion"] in ("entre-lecciones", "ambas"):
        w("W-CURSO-PRUEBA-MP4", "curso.modo.evaluacion", "el test entre lecciones solo existe en reproductor.html y quiz.json", "Entrega el reproductor o carga el quiz en un LMS; el MP4 suelto no lo muestra.")


def _id(e, valor, ruta, vistos):
    if not isinstance(valor, str) or not RE_ID.match(valor) or len(valor) > 24:
        e("E-CURSO-ID", ruta, f"id inválido {valor!r}", "Minúsculas, cifras y guiones, ≤ 24 caracteres (p. ej. m1-l2).")
    elif valor in vistos:
        e("E-CURSO-ID", ruta, f"id repetido {valor!r}", "Cada id debe ser único.")
    else:
        vistos.add(valor)


def _validar_leccion(l, ruta, m, cur, verbos, c, e, w, ids_lec, objetivos, seg_mod, medidas, modo):
    pres = modo["proposito"] == "presentacion"
    evaluacion = modo["evaluacion"]
    en_video = evaluacion in ("intercalada", "ambas")
    campos = ["id", "titulo", "escenas"]
    if not pres:
        campos += ["objetivo", "nivel_bloom", "tipo"]
    if evaluacion != "ninguna":
        campos.append("preguntas")
    for campo in campos:
        if not l.get(campo):
            e("E-CURSO-CAMPO", f"{ruta}.{campo}", "campo obligatorio ausente", f"Agrega {campo}.")
    _id(e, l.get("id"), f"{ruta}.id", ids_lec)
    nivel = l.get("nivel_bloom")
    if nivel and nivel not in cur["bloom"]:
        e("E-CURSO-NIVEL", f"{ruta}.nivel_bloom", f"{nivel!r}", f"Usa {' | '.join(cur['bloom'])}.")
    if l.get("tipo") and l["tipo"] not in TIPOS_LECCION:
        e("E-CURSO-TIPO-LECCION", f"{ruta}.tipo", f"{l['tipo']!r}", f"Usa {' | '.join(TIPOS_LECCION)}.")
    obj = str(l.get("objetivo") or "")
    pal = obj.split()
    if pal and not pres:
        v = pal[0].lower().strip(",.;:")
        if v not in verbos:
            lista = ", ".join(cur["bloom"].get(nivel) or [])
            e("E-CURSO-OBJETIVO-VERBO", f"{ruta}.objetivo", f"«{pal[0]}» no es un verbo observable de la lista Bloom", f"Empieza con uno de: {lista}.")
        elif nivel in cur["bloom"] and verbos[v] != nivel:
            w("W-CURSO-BLOOM-NIVEL", f"{ruta}.objetivo", f"«{v}» es de nivel {verbos[v]}, se declaró {nivel}", f"Cambia nivel_bloom a {verbos[v]} o el verbo.")
        if sum(1 for p in pal[1:] if p.lower().strip(",.;:") in verbos) and " y " in obj:
            w("W-CURSO-OBJETIVO-DOBLE", f"{ruta}.objetivo", "parece tener dos objetivos", "Un objetivo por lección: divide la lección.")
    if not l.get("criterio_exito") and not pres:
        w("W-CURSO-CRITERIO", f"{ruta}.criterio_exito", "sin criterio de éxito visible (d = 0.64)", "Agrega «Lo sabrás cuando…».")
    if not l.get("practica") and not pres:
        w("W-CURSO-SIN-PRACTICA", f"{ruta}.practica", "el video rinde como complemento de la práctica (g 0.80 frente a 0.28)", "Agrega practica {consigna, rubrica, min}.")

    _validar_mundo(l.get("mundo"), f"{ruta}.mundo", c, e, w)

    # preguntas
    ids_p = set()
    preguntas = l.get("preguntas") if isinstance(l.get("preguntas"), list) else []
    if evaluacion != "ninguna" and len(preguntas) < cur["min_preguntas_leccion"]:
        e("E-CURSO-PREGUNTAS-MIN", f"{ruta}.preguntas", f"{len(preguntas)} pregunta(s)", f"Agrega al menos {cur['min_preguntas_leccion']} con retro.")
    for j, q in enumerate(preguntas):
        rq = f"{ruta}.preguntas[{j}]"
        if not isinstance(q, dict):
            e("E-CURSO-CAMPO", rq, "no es un objeto", "Usa {id, objetivo_ref, enunciado, opciones, correcta, retro}.")
            continue
        for campo in ("id", "objetivo_ref", "enunciado", "opciones", "retro"):
            if not q.get(campo):
                e("E-CURSO-CAMPO", f"{rq}.{campo}", "campo obligatorio ausente", f"Agrega {campo}.")
        _id(e, q.get("id"), f"{rq}.id", ids_p)
        ops = q.get("opciones") if isinstance(q.get("opciones"), list) else []
        if not cur["opciones_min"] <= len(ops) <= cur["opciones_max"] or len(set(map(str, ops))) != len(ops):
            e("E-CURSO-PREGUNTA-OPCIONES", f"{rq}.opciones", f"{len(ops)} opciones", f"Pon {cur['opciones_min']}–{cur['opciones_max']} opciones distintas.")
        cor = q.get("correcta")
        if not isinstance(cor, int) or isinstance(cor, bool) or not 0 <= cor < len(ops):
            e("E-CURSO-PREGUNTA-CORRECTA", f"{rq}.correcta", f"{cor!r}", "Índice base 0 dentro de opciones.")
        elif len(ops) > 1:
            resto = [len(str(o)) for n, o in enumerate(ops) if n != cor]
            if len(str(ops[cor])) > 1.5 * (sum(resto) / len(resto)) + 4:
                w("W-CURSO-DISTRACTOR", f"{rq}.opciones", "la correcta se delata por su longitud", "Iguala la longitud de las opciones.")
        ref = q.get("objetivo_ref")
        if ref and str(ref) not in objetivos:
            e("E-CURSO-PREGUNTA-REF", f"{rq}.objetivo_ref", f"{ref!r} no existe", "Apunta al id de una lección o módulo.")
        elif ref and str(ref) not in (str(l.get("id")), str(m.get("id"))):
            w("W-CURSO-PREGUNTA-AJENA", f"{rq}.objetivo_ref", f"evalúa {ref}, otra lección", "Muévela a la lección de ese objetivo.")

    final = l.get("prueba_final") if isinstance(l.get("prueba_final"), list) else []
    if evaluacion in ("entre-lecciones", "ambas") and not final:
        e("E-CURSO-MODO", f"{ruta}.prueba_final", f"evaluacion {evaluacion} pide test al terminar la lección", "Lista ids de preguntas en prueba_final.")
    if final and evaluacion in ("intercalada", "ninguna"):
        e("E-CURSO-MODO", f"{ruta}.prueba_final", f"evaluacion {evaluacion} no lleva test entre lecciones", "Quita prueba_final o cambia curso.modo.evaluacion.")
    for n, ref in enumerate(final):
        if ref not in ids_p:
            e("E-CURSO-PREGUNTA-REF", f"{ruta}.prueba_final[{n}]", f"{ref!r} no existe en preguntas", "Apunta al id de una pregunta de esta lección.")

    # escenas
    ids_e = set()
    escenas = l.get("escenas") if isinstance(l.get("escenas"), list) else []
    tipos = [x.get("tipo") for x in escenas if isinstance(x, dict)]
    lineas, usadas, t_acum, sin_preg, inicio_ok = [], set(), 0.0, 0.0, set()
    for j, s in enumerate(escenas):
        rs = f"{ruta}.escenas[{j}]"
        if not isinstance(s, dict):
            e("E-CURSO-CAMPO", rs, "no es un objeto", "Usa {id, tipo, tts, pantalla}.")
            continue
        _id(e, s.get("id"), f"{rs}.id", ids_e)
        tipo = s.get("tipo")
        if tipo not in TIPOS_ESCENA:
            e("E-CURSO-ESCENA-TIPO", f"{rs}.tipo", f"{tipo!r}", f"Usa {' | '.join(TIPOS_ESCENA)}.")
            continue
        pant = s.get("pantalla") or {}
        for campo in PANTALLA_REQ.get(tipo, ()):
            if not pant.get(campo):
                if pant.get("acciones") or (tipo == "concepto" and (pant.get("puntos") or s.get("imgs"))):
                    continue
                e("E-CURSO-ESCENA-PANTALLA", f"{rs}.pantalla.{campo}", f"la escena {tipo} lo requiere", f"Agrega pantalla.{campo}.")
        if tipo == "objetivo" and not l.get("objetivo"):
            e("E-CURSO-ESCENA-PANTALLA", rs, "la escena objetivo muestra el objetivo de la lección", "Agrega objetivo a la lección o quita la escena.")
        if tipo == "concepto" and pant.get("puntos") and not pant.get("elementos") and not pres:
            w("W-CURSO-VINETAS", f"{rs}.pantalla", "concepto con viñetas: voz sobre diapositiva fue el peor formato (Chen & Wu 2015)", "Usa pantalla.elementos con dibujo dinámico.")
        if tipo == "concepto" and pant.get("puntero") is False:
            w("W-CURSO-SIN-PUNTERO", f"{rs}.pantalla.puntero", "sin mano o puntero el dibujo no supera al diagrama terminado", "Quita puntero: false.")
        tts = (s.get("tts") or "").strip()
        if tts:
            lineas.append({"ruta": f"{rs}.tts", "texto": tts, "tts": tts})
        if s.get("tts_retro"):
            lineas.append({"ruta": f"{rs}.tts_retro", "texto": s["tts_retro"], "tts": s["tts_retro"]})
        if tipo == "pregunta":
            ref = s.get("pregunta_ref")
            usadas.add(ref)
            if not en_video:
                e("E-CURSO-MODO", f"{rs}.tipo", f"evaluacion {evaluacion} no lleva preguntas dentro del video", "Quita la escena o cambia curso.modo.evaluacion.")
            if ref not in ids_p:
                e("E-CURSO-PREGUNTA-REF", f"{rs}.pregunta_ref", f"{ref!r} no existe en preguntas", "Apunta al id de una pregunta de esta lección.")
        palabras = narrar.palabras_por_silabas(tts, 0, 1)
        for lista in LISTAS:
            desde = 0.0
            for n, it in enumerate(pant.get(lista) or []):
                en = it.get("en") if isinstance(it, dict) else None
                if en and not it.get("junto"):
                    t = narrar.tiempo_de(palabras, en, desde)
                    if t is None:
                        e("E-CURSO-SYNC", f"{rs}.pantalla.{lista}[{n}].en", f"«{en}» no se dice en el tts después del elemento previo", "Usa una palabra de la narración, en el orden en que se dice.")
                    else:
                        desde = t[1]
        if tipo == "concepto":
            for n, it in enumerate(pant.get("elementos") or []):
                if not isinstance(it, dict) or not it.get("en"):
                    e("E-CURSO-SYNC", f"{rs}.pantalla.elementos[{n}]", "elemento sin `en`", "Indica la palabra que lo nombra (contigüidad g = 0.74).")
                elif it.get("forma") not in ("caja", "circulo", "flecha", "linea", "texto"):
                    e("E-CURSO-ESCENA-PANTALLA", f"{rs}.pantalla.elementos[{n}].forma", f"{it.get('forma')!r}", "Usa caja|circulo|flecha|linea|texto.")
        _validar_acciones(pant, rs, l, tipo, tts, palabras, cur, e, w)
        if s.get("retro_acciones"):
            _validar_retro(s, rs, l, cur, e, w)
        planos = [x for lista in ("puntos", "pasos", "tarjetas") for x in (pant.get(lista) or [])]
        if len(planos) > cur["max_puntos"] or any(len(str(x.get("texto") if isinstance(x, dict) else x).split()) > cur["max_palabras_punto"] for x in planos):
            w("W-CURSO-PUNTOS", f"{rs}.pantalla", f"más de {cur['max_puntos']} ítems o de {cur['max_palabras_punto']} palabras", "Reduce el texto: narra, no leas.")
        for n, it in enumerate(pant.get("solucion") or []):
            if len(str(it.get("texto") if isinstance(it, dict) else it)) > cur["max_car_linea_ejemplo"]:
                w("W-CURSO-PUNTOS", f"{rs}.pantalla.solucion[{n}]", f"más de {cur['max_car_linea_ejemplo']} caracteres", "Divide la línea.")
        visibles = " ".join(str(v.get("texto", "") if isinstance(v, dict) else v) for lista in LISTAS for v in (pant.get(lista) or []))
        visibles += " " + " ".join(str(pant.get(x) or "") for x in ("titular", "texto", "enunciado", "definicion"))
        if len(visibles.split()) > cur["max_palabras_pantalla"]:
            w("W-CURSO-PALABRAS-PANTALLA", f"{rs}.pantalla", f"{len(visibles.split())} palabras en pantalla", "Reparte en dos escenas.")
        seg = narrar.estimar_duracion([s], cur)
        if seg > cur["max_s_escena"]:
            w("W-CURSO-ESCENA-LARGA", rs, f"~{seg:.0f} s en una sola pantalla", "Divide la escena.")
        if t_acum <= 60:
            inicio_ok.add(tipo)
        sin_preg = 0.0 if tipo == "pregunta" else sin_preg + seg
        if sin_preg > cur["max_s_sin_pregunta"] and en_video:
            w("W-CURSO-PREGUNTA-ESPACIO", rs, f"~{sin_preg / 60:.1f} min sin pregunta", "Intercala una pregunta cada ~5 min.")
            sin_preg = 0.0
        t_acum += seg
        for n, im in enumerate(s.get("imgs") or []):
            _recurso(e, c, im if isinstance(im, str) else im.get("clave"), f"{rs}.imgs[{n}]")
        if s.get("imgs") and (tipo not in ESCENAS_CON_IMG or pant.get("acciones")):
            w("W-CURSO-IMG-SIN-LUGAR", f"{rs}.imgs", f"una escena {tipo}{' con acciones' if pant.get('acciones') else ''} no muestra imgs", f"Usa {' | '.join(ESCENAS_CON_IMG)} sin acciones, o un actor imagen.")
        if tipo == "screencast" and pant.get("clip") and not os.path.exists(os.path.join(c.rec, pant["clip"])):
            e("E-CURSO-RECURSO", f"{rs}.pantalla.clip", f"no existe recursos/{pant['clip']}", "Copia el clip a recursos/.")
    for n, r in enumerate(l.get("recursos") or []):
        if not os.path.exists(os.path.join(c.rec, r)):
            e("E-CURSO-RECURSO", f"{ruta}.recursos[{n}]", f"no existe recursos/{r}", "Copia el archivo a recursos/.")
    for q in usadas & set(final):
        e("E-CURSO-MODO", f"{ruta}.prueba_final", f"{q} ya se plantea en el video", "Una pregunta va en una escena o en prueba_final, no en ambas.")
    for q in ids_p - usadas - set(final):
        w("W-CURSO-PREGUNTA-SIN-ESCENA", f"{ruta}.preguntas", f"{q} no se plantea en el video (queda solo en quiz)", "Agrega una escena pregunta si es el reactivo intercalado.")
    if escenas and "pregunta" not in tipos and en_video:
        w("W-CURSO-SIN-PREGUNTA-INTERCALADA", ruta, "sin pregunta intercalada", "Intercala una antes del cierre.")
    if escenas and not pres:
        if not {"gancho", "objetivo"} <= inicio_ok:
            w("W-CURSO-INICIO", ruta, "sin gancho y objetivo en los primeros 60 s", "Abre con gancho y objetivo.")
        if l.get("tipo") in ("concepto", "procedimiento", "ejemplo-resuelto") and "ejemplo" not in tipos and "pasos" not in tipos:
            w("W-CURSO-SIN-EJEMPLO", ruta, "sin ejemplo resuelto", "Agrega una escena ejemplo.")
        if not {"resumen", "cierre"} & set(tipos):
            w("W-CURSO-SIN-RESUMEN", ruta, "sin resumen ni cierre", "Cierra con 2–3 ideas y el puente a la siguiente lección.")
    textos = " ".join(x["tts"] for x in lineas)
    if textos and not SEGUNDA_PERSONA.search(textos) and not pres:
        w("W-CURSO-TONO", ruta, "guion sin segunda persona (personalización d = 0.30–0.54)", "Háblale al alumno: tú, vamos a, mira.")
    errs_voz = lint_voz.revisar(lineas, "")
    for i in errs_voz:
        (e if i["severidad"] == "E" else w)(i["codigo"], i["ruta"], i["msg"], i["arreglo"])
    lid = str(l.get("id"))
    medida = medidas.get(lid)
    seg = medida if medida else narrar.estimar_duracion(expandir_escenas(l) if all(isinstance(x, dict) and x.get("id") for x in escenas) else [], cur)
    origen = "medidos" if medida else "estimados"
    minutos = seg / 60
    if minutos > cur["max_min_leccion"]:
        e("E-CURSO-DURACION", ruta, f"{minutos:.1f} min {origen} (máx. {cur['max_min_leccion']})", "Divide la lección en dos.")
    elif minutos > cur["ideal_min_leccion"]:
        w("W-CURSO-DURACION", ruta, f"{minutos:.1f} min {origen} (ideal ≤ {cur['ideal_min_leccion']})", "Divide si hay un corte natural.")
    con_imagen = any(isinstance(x, dict) and x.get("imgs") for x in escenas) or any(
        isinstance(a, dict) and a.get("tipo") == "imagen" for a in ((l.get("mundo") or {}).get("actores") or []))
    if modo["visual"] in ("animado", "mixto") and not l.get("mundo"):
        e("E-CURSO-MODO", f"{ruta}.mundo", f"visual {modo['visual']} pide mundo continuo", "Agrega mundo.actores o cambia curso.modo.visual.")
    if modo["visual"] in ("imagenes", "mixto") and not con_imagen:
        e("E-CURSO-MODO", ruta, f"visual {modo['visual']} pide al menos una imagen", "Usa imgs en una escena o un actor imagen.")
    extra = len(preguntas) * cur["min_por_pregunta"] * 60 + float((l.get("practica") or {}).get("min") or 0) * 60
    seg_mod[str(m.get("id"))] = seg_mod.get(str(m.get("id")), 0.0) + seg + extra


def _validar_mundo(mundo, ruta, c, e, w):
    if not mundo:
        return
    actores = mundo.get("actores") if isinstance(mundo, dict) else None
    if not isinstance(actores, list) or not actores:
        e("E-CURSO-MUNDO", f"{ruta}.actores", "el mundo no tiene actores", "Usa {actores: [{id, tipo, x, y}]}.")
        return
    ids = set()
    for n, a in enumerate(actores):
        ra = f"{ruta}.actores[{n}]"
        if not isinstance(a, dict) or not a.get("id") or a.get("tipo") not in ACTORES:
            e("E-CURSO-MUNDO", ra, f"{a.get('tipo') if isinstance(a, dict) else a!r} no es un actor válido", f"Pon id y tipo: {' | '.join(ACTORES)}.")
            continue
        if a["id"] in ids:
            e("E-CURSO-MUNDO", f"{ra}.id", f"{a['id']!r} repetido", "Cada actor lleva un id único.")
        ids.add(a["id"])
        if a["tipo"] == "dato" and not a.get("partes"):
            e("E-CURSO-MUNDO", f"{ra}.partes", "un dato requiere partes", 'Usa partes: ["192", "168", "1", "20"].')
        if a["tipo"] == "imagen":
            if not a.get("clave"):
                e("E-CURSO-MUNDO", f"{ra}.clave", "una imagen requiere clave", "Usa la clave de creditos.json o el nombre del archivo en recursos/img/.")
            else:
                _recurso(e, c, a["clave"], f"{ra}.clave")
                if not _dato_credito(c, a["clave"]):
                    w("W-CURSO-IMG-CREDITO", f"{ra}.clave", "imagen sin crédito", "Regístrala en recursos/img/creditos.json con autor y licencia.")
    for n, a in enumerate(actores):
        if isinstance(a, dict) and a.get("tipo") == "enlace":
            for lado in ("de", "a"):
                if a.get(lado) not in ids:
                    e("E-CURSO-ACTOR", f"{ruta}.actores[{n}].{lado}", f"{a.get(lado)!r} no existe", "Apunta al id de otro actor.")


def _validar_retro(s, rs, l, cur, e, w):
    desde = 0.0
    tts = s.get("tts_retro") or ""
    palabras = narrar.palabras_por_silabas(tts, 0, 1)
    for n, it in enumerate(s["retro_acciones"]):
        if isinstance(it, dict) and it.get("en") and not it.get("junto"):
            t = narrar.tiempo_de(palabras, it["en"], desde)
            if t is None:
                e("E-CURSO-SYNC", f"{rs}.retro_acciones[{n}].en", f"«{it['en']}» no se dice en tts_retro después de la acción previa", "Usa una palabra de tts_retro, en orden.")
            else:
                desde = t[1]
    _validar_acciones({"acciones": s["retro_acciones"]}, f"{rs}.retro", l, "pregunta", tts, palabras, cur, e, w)


def _validar_acciones(pant, rs, l, tipo, tts, palabras, cur, e, w):
    """`palabras` son estimadas: bastan para detectar pantallas quietas antes de pagar la voz."""
    acciones = pant.get("acciones") or []
    actores = {a.get("id"): a for a in ((l.get("mundo") or {}).get("actores") or []) if isinstance(a, dict)} if isinstance(l.get("mundo"), dict) else {}
    if acciones and not actores:
        e("E-CURSO-MUNDO", f"{rs}.pantalla.acciones", "hay acciones pero la lección no define mundo", "Agrega mundo.actores a la lección.")
    for n, a in enumerate(acciones):
        ra = f"{rs}.pantalla.acciones[{n}]"
        if not isinstance(a, dict) or a.get("accion") not in ACCIONES:
            e("E-CURSO-ACCION", ra, f"{a.get('accion') if isinstance(a, dict) else a!r}", f"Usa {' | '.join(ACCIONES)}.")
            continue
        ref = a.get("actor")
        if (actores.get(ref) or {}).get("tipo") == "imagen" and a["accion"] not in ACCIONES_IMAGEN:
            e("E-CURSO-ACCION", ra, f"{a['accion']} no aplica a una imagen", f"Usa {' | '.join(ACCIONES_IMAGEN)}.")
        if actores and ((ref and ref not in actores) or (not ref and a["accion"] not in SIN_ACTOR)):
            e("E-CURSO-ACTOR", f"{ra}.actor", f"{ref!r} no existe en mundo.actores", f"Usa uno de: {', '.join(sorted(actores))}.")
        if a["accion"] == "copia" and actores and a.get("desde") not in actores:
            e("E-CURSO-ACTOR", f"{ra}.desde", f"{a.get('desde')!r} no existe", "Apunta al actor de origen.")
        if not a.get("en") and not a.get("junto"):
            w("W-CURSO-ANIM-SIN-EN", ra, "acción sin palabra que la nombre (contigüidad g = 0.74)", "Agrega `en`, o `junto: true` para acompañar a la acción previa.")
    if tipo in ("pregunta", "screencast") or not palabras:
        return
    cambios = []
    for lista in LISTAS:
        desde = 0.0
        for it in pant.get(lista) or []:
            hallado = narrar.tiempo_de(palabras, it["en"], desde) if isinstance(it, dict) and it.get("en") and not it.get("junto") else None
            if hallado:
                cambios.append(hallado[0])
                desde = hallado[1]
    seg = narrar.estimar_duracion([{"tts": tts, "tipo": tipo}], cur)
    if not cambios:
        return
    fin = palabras[-1]["b"]
    escala = seg / fin if fin else 1.0  # palabras_por_silabas reparte en [0, 1]
    marcas = sorted([0.0, *(t * escala for t in cambios), fin * escala])
    hueco = max(b - a for a, b in zip(marcas, marcas[1:]))
    if hueco > cur["max_s_estatica"]:
        w("W-CURSO-ESTATICA", rs, f"~{hueco:.0f} s sin cambio en pantalla", "Liga otra acción a una palabra de ese tramo: mueve, resalta o enfoca.")


def _recurso(e, c, ref, ruta):
    if not ref:
        return
    if not ruta_imagen(c, ref):
        e("E-CURSO-RECURSO", ruta, f"no existe la imagen {ref!r}", "Copia el archivo a recursos/img/ o agrégala a creditos.json.")


def creditos(c):
    p = os.path.join(c.rec, "img", "creditos.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def ruta_imagen(c, clave):
    """Archivo (dentro de recursos/img/) de una clave de creditos.json o de un nombre de archivo."""
    cr = creditos(c).get(clave) or {}
    nombre = cr.get("archivo") or clave
    return nombre if os.path.exists(os.path.join(c.rec, "img", nombre)) else None


def medidas_de(c, spec):
    d = {}
    for _, _, l in lecciones(spec):
        p = os.path.join(c.lecciones, str(l.get("id")), "recursos", "tiempos.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d[str(l.get("id"))] = json.load(f).get("duracion")
    return d


def imprimir(errs, avis, json_ruta=None):
    if json_ruta:
        os.makedirs(os.path.dirname(json_ruta), exist_ok=True)
        with open(json_ruta, "w", encoding="utf-8") as f:
            json.dump({"errores": errs, "avisos": avis}, f, ensure_ascii=False, indent=1)
    todos = errs + avis
    for i in todos[:MAX_ISSUES]:
        print(promo.linea_issue(i))
    if len(todos) > MAX_ISSUES:
        print(f"… y {len(todos) - MAX_ISSUES} más en recursos/curso/validacion.json")


def etapa_nuevo(a):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", a.slug):
        print(f"E-CURSO-ID  slug: {a.slug!r}. Usa minúsculas, cifras y guiones.")
        return 2
    destino = os.path.join(raiz(a), "proyectos", f"{a.slug}_{datetime.date.today():%d%m%Y}")
    if os.path.exists(destino):
        print(f"ERROR ya existe {destino}. Siguiente: python3 scripts/curso.py validar {os.path.basename(destino)}")
        return 2
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copytree(os.path.join(REPO, "cursos", "ejemplo"), destino)
    print(f"curso creado: {destino} (copia del ejemplo de oro)")
    print(f"Siguiente: edita curso.json y corre python3 scripts/curso.py validar {os.path.basename(destino)}")
    return 0


def etapa_validar(a, c, siguiente=True):
    spec = cargar(c)
    cfg, cur = cursos_cfg()
    errs, avis = validar_curso(spec, c, cur, cfg, medidas_de(c, spec))
    salida = [x[2] for x in lecciones(spec)]
    print(f"validar: {len(salida)} lecciones · {len(errs)} errores · {len(avis)} avisos")
    imprimir(errs, avis, os.path.join(c.interno, "validacion.json"))
    if getattr(a, "json", False):
        print(json.dumps({"errores": errs, "avisos": avis}, ensure_ascii=False))
    if errs:
        print("Siguiente: corrige curso.json y vuelve a validar.")
        return 2
    if siguiente:
        print(f"Siguiente: python3 scripts/curso.py voz {c.nombre}")
    return 0


def etapa_voz(a, c, siguiente=True):
    spec = cargar(c)
    cfg, cur = cursos_cfg()
    comun.AVANCE_DIR = c.rec
    k = spec.get("curso") or {}
    res = voz.resolver_voz(k.get("voz") or {}, cfg)
    sel = filtradas(spec, a)
    print(f"voz: {res['proveedor']} · {res['modelo']} · voice={res.get('voice') or '-'}")
    seg = sum(narrar.estimar_duracion(expandir_escenas(l), cur) for _, _, l in sel)
    tarifa = cur["costo_voz_usd_min"].get(res["proveedor"])
    if tarifa:
        print(f"W-CURSO-COSTO  -: hasta ~{seg / 60 * tarifa:.2f} USD de voz si no hay caché ({seg / 60:.1f} min).")
    for n, (_, m, l) in enumerate(sel):
        lec = c.leccion(l["id"])
        os.makedirs(lec.rec, exist_ok=True)
        r = narrar.narrar(expandir_escenas(l), lec.rec, res, repo=REPO, costos_dir=c.rec, opciones=cur,
                          solo_lint=getattr(a, "solo_lint", False), max_car=cur["subtitulos"].get("max_car", 42),
                          al_avance=lambda p, d, n=n: comun.avance("voz", (n + p / 100) * 100 / len(sel), f"{l['id']} {d}"))
        for i in r["issues"]:
            print(promo.linea_issue({**i, "ruta": f"lecciones[{l['id']}].{i['ruta']}"}))
        if r["codigo"]:
            comun.avance("voz", None, f"{l['id']} falló", estado="error")
            return r["codigo"]
        if not r["tiempos"]:
            continue
        narrar.escribir_subtitulos(r["cues"], os.path.join(lec.dir, f"{c.slug}_{l['id']}"))
        lentos = [x for x in r["cues"] if subtitulos.cps(x) > cur["subtitulos"].get("cps_max", 17)]
        if lentos:
            print(f"W-CURSO-CPS  lecciones[{l['id']}]: {len(lentos)} cues superan {cur['subtitulos'].get('cps_max', 17)} cps. Acorta esas frases.")
        if r["sync_estimada"] and not os.environ.get("PROMO_TTS_STUB"):
            print(f"W-CURSO-SYNC-ESTIMADA  lecciones[{l['id']}]: sin faster-whisper; la sincronía sale de las sílabas.")
        print(f"  {l['id']}: {r['nuevas']} nuevas · {r['cache']} en caché · {r['tiempos']['duracion'] / 60:.1f} min · {len(r['cues'])} cues")
    comun.avance("voz", 100, f"{len(sel)} lecciones", estado="listo")
    if siguiente:
        print(f"Siguiente: python3 scripts/curso.py componer {c.nombre}")
    return 0


def _credito(cr):
    return f"{cr.get('autor', '')} · {cr.get('licencia', '')}".strip(" ·")


def _dato_credito(c, clave):
    cr = creditos(c)
    nombre = ruta_imagen(c, clave)
    return cr.get(clave) or next((x for x in cr.values() if x.get("archivo") == nombre), {})


def _resolver_imgs(c, lec, s):
    salida = []
    for im in s.get("imgs") or []:
        clave, pie = (im, None) if isinstance(im, str) else (im.get("clave"), im.get("pie"))
        nombre = ruta_imagen(c, clave)
        _enlazar(os.path.join(c.rec, "img", nombre), os.path.join(lec.rec, "img", nombre))
        salida.append({"src": f"img/{nombre}", "credito": _credito(_dato_credito(c, clave)), "pie": pie})
    return salida


def _resolver_mundo(c, lec, mundo):
    """Los actores `imagen` llegan a Remotion ya enlazados a la lección y con su crédito."""
    if not mundo:
        return mundo
    salida = json.loads(json.dumps(mundo))
    for a in salida.get("actores") or []:
        if a.get("tipo") == "imagen":
            im = _resolver_imgs(c, lec, {"imgs": [{"clave": a["clave"], "pie": a.get("pie")}]})[0]
            a.update({"src": im["src"], "credito": im["credito"]})
    return salida


def _enlazar(origen, destino):
    """Hard link para no copiar cientos de MB por lección (el bundler copia el public-dir)."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if os.path.exists(destino):
        os.remove(destino)
    try:
        os.link(origen, destino)
    except OSError:
        shutil.copy2(origen, destino)


def _temporizar(e, t):
    """Pone el segundo de aparición a cada elemento: 150 ms antes de la palabra que lo nombra; sin `en`, repartidos."""
    pant = json.loads(json.dumps(e.get("pantalla") or {}))
    a = t["voz_inicio"] if t["voz_inicio"] is not None else t["inicio"]
    b = a + max(t["voz_dur"], 0.5)
    for lista in LISTAS:
        vals = pant.get(lista)
        if not vals:
            continue
        salida, desde = [], 0.0
        for n, it in enumerate(vals):
            d = dict(it) if isinstance(it, dict) else {"texto": str(it)}
            if d.get("junto") and salida:
                d["t"] = round(salida[-1]["t"] + float(d.get("retraso") or 0), 3)
                salida.append(d)
                continue
            hallado = narrar.tiempo_de(t["palabras"], d["en"], desde) if d.get("en") else None
            tw, desde = hallado if hallado else (a + (b - a) * n / len(vals), desde)
            d["t"] = round(max(t["inicio"], tw - 0.15) + float(d.get("retraso") or 0), 3)
            salida.append(d)
        pant[lista] = salida
    pant["fin_voz"] = round(b, 3)
    if pant.get("definicion"):
        pant["definicion_t"] = round(max(a, b - 1.5), 3)
    return pant


def cues_sonido(escenas, mundo):
    """SFX solo como señal estructural (regla 10): viajes de cámara, entradas de objetos y la respuesta correcta."""
    hay = bool(mundo)
    crudos = []
    for n, e in enumerate(escenas):
        p = e.get("pantalla") or {}
        if n and (not hay or p.get("plano") == "estacion"):
            crudos.append((max(0.0, e["inicio"] - 0.2), "whoosh"))
        if e["tipo"] == "pregunta" and p.get("revelar"):
            crudos += [(e["inicio"] + 0.55, "tick"), (e["inicio"] + 0.65, "exito")]
        for a in p.get("acciones") or []:
            nombre = "exito" if a.get("accion") == "transforma" and a.get("a") == "vivo" else SFX_ACCION.get(a.get("accion"))
            if nombre:
                crudos.append((a["t"], nombre))
    salida = []
    for t, nombre in sorted(crudos):
        if not salida or t - salida[-1][0] >= 0.12:  # dos golpes casi juntos se oyen como ruido, no como señal
            salida.append((round(t, 3), nombre))
    return salida


def mezclar_sfx(voz_wav, cues, carpeta, salida, sfx_lufs):
    ctx = {"recetas": sonido.cargar_recetas(REPO), "sfx_dir": os.path.join(carpeta, "sfx")}
    info = {n: sonido.sfx_receta(n, ctx) for n in sorted({x[1] for x in cues})}
    nombres = sorted(info)
    entradas = ["-i", voz_wav]
    for n in nombres:
        entradas += ["-i", info[n]["ruta"]]
    grafo, etiquetas = [], ["[0:a]"]
    for i, (t, n) in enumerate(cues):
        ms = max(0, round((t - info[n]["pico" if info[n].get("ancla") == "pico" else "ataque"]) * 1000))
        ganancia = sfx_lufs - info[n]["M"]
        grafo.append(f"[{nombres.index(n) + 1}:a]aformat=channel_layouts=mono,volume={ganancia:.2f}dB,adelay={ms}:all=1[s{i}]")
        etiquetas.append(f"[s{i}]")
    grafo.append("".join(etiquetas) + f"amix=inputs={len(etiquetas)}:duration=first:normalize=0[o]")
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *entradas, "-filter_complex", ";".join(grafo), "-map", "[o]",
               "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", salida])
    return salida


def etapa_componer(a, c, siguiente=True):
    spec = cargar(c)
    cfg, cur = cursos_cfg()
    rem, res, formatos = remotion.config()
    k = spec.get("curso") or {}
    est = k.get("estilo") or {}
    todas = lecciones(spec)
    registrados = remotion.ids_base()
    tema = tema_de(spec, cur)
    for _, m, l in filtradas(spec, a):
        lec = c.leccion(l["id"])
        ruta_t = os.path.join(lec.rec, "tiempos.json")
        if not os.path.exists(ruta_t):
            print(f"E-CURSO-TIEMPOS  lecciones[{l['id']}]: falta tiempos.json. Corre python3 scripts/curso.py voz {c.nombre} --leccion {l['id']}")
            return 2
        with open(ruta_t, encoding="utf-8") as f:
            tiempos = json.load(f)
        por_id = {t["id"]: t for t in tiempos["escenas"]}
        escenas = []
        for e in expandir_escenas(l):
            t = por_id.get(e["id"])
            if not t:
                print(f"E-CURSO-TIEMPOS  lecciones[{l['id']}]: la escena {e['id']} no tiene voz. Corre voz de nuevo.")
                return 2
            d = {"id": e["id"], "tipo": e["tipo"], "inicio": t["inicio"], "fin": t["fin"], "voz_inicio": t["voz_inicio"], "pantalla": _temporizar(e, t)}
            ims = _resolver_imgs(c, lec, e)
            if ims:
                d["imgs"] = ims
            if d["pantalla"].get("clip"):
                _enlazar(os.path.join(c.rec, d["pantalla"]["clip"]), os.path.join(lec.rec, d["pantalla"]["clip"]))
            escenas.append(d)
        indice = next(i for i, x in enumerate(todas) if x[2].get("id") == l["id"])
        sig = todas[indice + 1][2].get("titulo") if indice + 1 < len(todas) else None
        cues = []
        srt = os.path.join(lec.dir, f"{c.slug}_{l['id']}.srt")
        if os.path.exists(srt):
            with open(srt, encoding="utf-8") as f:
                cues = [{"ini": x["ini"], "fin": x["fin"], "lineas": x["lineas"]} for x in subtitulos.leer_srt(f.read())]
        audio = "voz.wav"
        if est.get("musica"):
            narrar.mezclar_cama(os.path.join(lec.rec, "voz.wav"), os.path.join(c.rec, est["cama"]), os.path.join(lec.rec, "mezcla.wav"),
                                cur["mezcla"]["voz_lufs"], cur["mezcla"]["musica_lufs"])
            audio = "mezcla.wav"
        con_sfx = est.get("sonido", cur["sonido"].get("sfx", False))
        cues_sfx = cues_sonido(escenas, l.get("mundo")) if con_sfx else []
        if cues_sfx:
            mezclar_sfx(os.path.join(lec.rec, audio), cues_sfx, lec.rec, os.path.join(lec.rec, "mezcla_sfx.wav"), cur["sonido"].get("sfx_lufs", -33))
            audio = "mezcla_sfx.wav"
        props = {"curso": {"titulo": k.get("titulo"), "aviso_ia": cur["aviso_ia"]},
                 "modulo": {"id": m.get("id"), "titulo": m.get("titulo")},
                 "leccion": {"id": l["id"], "indice": indice + 1, "total": len(todas), "titulo": l.get("titulo"), "objetivo": l.get("objetivo"),
                             "criterio_exito": l.get("criterio_exito"), "siguiente": sig},
                 "tema": tema, "audio": audio, "escenas": escenas, "mundo": _resolver_mundo(c, lec, l.get("mundo")), "subtitulos": cues,
                 "subtitulos_quemados": bool(est.get("subtitulos_quemados", cur["subtitulos"].get("quemados", False)))}
        r_spec = {"version": 1, "composicion": "Leccion", "salida": f"{c.slug}_{l['id']}.mp4",
                  "orientacion": est.get("orientacion") or cur.get("orientacion", "horizontal"), "fps": rem["fps"],
                  "duracion": tiempos["duracion"], "props": props}
        errs, avis = remotion.validar_spec(r_spec, lec, registrados, rem, res, formatos)
        if errs:
            imprimir([{**i, "ruta": f"lecciones[{l['id']}].{i['ruta']}"} for i in errs], [])
            return 2
        with open(lec.spec, "w", encoding="utf-8") as f:
            json.dump(r_spec, f, ensure_ascii=False, indent=1)
        os.makedirs(lec.rem, exist_ok=True)
        with open(lec.props_json, "w", encoding="utf-8") as f:
            json.dump(remotion.props_render(r_spec, rem, res), f, ensure_ascii=False, indent=1)
        print(f"  {l['id']}: {len(escenas)} escenas · {tiempos['duracion']:.1f} s")
    if siguiente:
        print(f"Siguiente: python3 scripts/curso.py qa {c.nombre}")
    return 0


def _stills(c, lec, lid):
    """Un still por escena al final de su animación + hoja de contactos."""
    with open(lec.props_json, encoding="utf-8") as f:
        props = json.load(f)
    carpeta = os.path.join(c.interno, "qa", lid)
    os.makedirs(carpeta, exist_ok=True)
    node = comun.buscar_node(REPO)
    cli = os.path.join(remotion.dir_motor(), "node_modules", "@remotion", "cli", "remotion-cli.js")
    fps = props["fps"]
    for n, e in enumerate(props["escenas"], 1):
        cuadro = max(0, round((e["fin"] - 0.6) * fps))
        png = os.path.join(carpeta, f"{n:03d}.png")
        r = subprocess.run([node, cli, "still", "src/index.ts", "Leccion", png, f"--frame={cuadro}", f"--props={lec.props_json}",
                            f"--public-dir={lec.rec}", "--scale=0.5", "--log=error"], cwd=remotion.dir_motor(),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            print(f"ERROR qa: still de {lid}/{e['id']} falló: {(r.stderr or r.stdout)[-400:]}")
            print("Siguiente: revisa la composición Leccion o repórtalo al usuario.")
            raise SystemExit(1)
        comun.avance("qa", 100 * n / len(props["escenas"]), f"{lid} {e['id']}")
    hoja = os.path.join(c.interno, "qa", f"{lid}.png")
    filas = (len(props["escenas"]) + 3) // 4
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-framerate", "1", "-i", os.path.join(carpeta, "%03d.png"),
               "-vf", f"scale=640:-1,tile=4x{filas}:padding=6", "-frames:v", "1", hoja])
    return hoja


def _gate_jev(c, l, umbral):
    if not l.get("objetivo"):  # presentación sin objetivo: no hay contra qué medir
        return []
    state = {"objetivo": l.get("objetivo"), "nivel_bloom": l.get("nivel_bloom"), "tipo": l.get("tipo"),
             "escenas": [{"tipo": e.get("tipo"), "tts": e.get("tts"), "pantalla": e.get("pantalla")} for e in l.get("escenas") or []],
             "preguntas": l.get("preguntas")}
    questions = {
        "objetivo_contenido": {"type": "noul", "instructions": "La narración y las pantallas enseñan exactamente lo que promete el objetivo, ni otros temas ni menos."},
        "objetivo_pregunta": {"type": "noul", "instructions": "Cada pregunta evalúa el objetivo al nivel cognitivo declarado en nivel_bloom, no un dato accesorio."},
        "distractores": {"type": "noul", "instructions": "Las opciones incorrectas son plausibles para quien no domina el objetivo y la correcta no se delata por forma o longitud."},
        "retro": {"type": "noul", "instructions": "La retroalimentación explica por qué es correcta la respuesta."},
    }
    if not l.get("preguntas"):
        questions = {"objetivo_contenido": questions["objetivo_contenido"]}
    res = decision.decidir(state, questions, REPO, log=c.costos)
    ruta = os.path.join(c.interno, "jev", f"{l['id']}.json")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return [q for q, (_, ok) in decision.resumen(res, umbral).items() if not ok]


def etapa_qa(a, c, siguiente=True):
    spec = cargar(c)
    cfg, cur = cursos_cfg()
    comun.AVANCE_DIR = c.rec
    sel = filtradas(spec, a)
    hojas, fallas = [], 0
    usar_stills = not getattr(a, "sin_stills", False)
    if usar_stills and (codigo := remotion.exigir_deps()):
        return codigo
    for _, _, l in sel:
        lec = c.leccion(l["id"])
        if usar_stills:
            if not os.path.exists(lec.props_json):
                print(f"E-CURSO-TIEMPOS  lecciones[{l['id']}]: falta componer. Corre python3 scripts/curso.py componer {c.nombre}")
                return 2
            hojas.append(_stills(c, lec, l["id"]))
        if getattr(a, "jev", False):
            umbral = a.umbral if getattr(a, "umbral", None) is not None else cur["jev"]["umbral"]
            try:
                malos = _gate_jev(c, l, umbral)
            except SystemExit as ex:
                print(f"W-CURSO-JEV-SIN-API  lecciones[{l['id']}]: {ex}. Reintenta una vez.")
                return 4
            for q in malos:
                fallas += 1
                print(f"E-CURSO-JEV-{q.upper().replace('_', '-')}  lecciones[{l['id']}]: bajo el umbral {umbral}. Detalle en recursos/curso/jev/{l['id']}.json")
    comun.avance("qa", 100, f"{len(sel)} lecciones", estado="listo" if not fallas else "aviso")
    for h in hojas:
        print(f"qa: {os.path.relpath(h, c.dir)}")
    if fallas:
        print("Siguiente: corrige la alineación en curso.json.")
        return 2
    if siguiente:
        print(f"Siguiente: muestra las hojas al usuario y corre python3 scripts/curso.py render {c.nombre}")
    return 0


def _registro_render(c, spec, nuevas):
    """Una línea por lección en orden del curso; conserva lo ya registrado de las que no se renderizaron ahora."""
    previas = {}
    if os.path.exists(c.info):
        with open(c.info, encoding="utf-8") as f:
            texto = f.read()
        if MARCA_INI in texto and MARCA_FIN in texto:
            previas = {x.split(":", 1)[0]: x for x in texto.split(MARCA_INI)[1].split(MARCA_FIN)[0].strip().splitlines()}
    return [v for v in ({**previas, **nuevas}.get(l["id"]) for _, _, l in lecciones(spec)) if v]


def etapa_render(a, c, siguiente=True):
    spec = cargar(c)
    cfg, cur = cursos_cfg()
    comun.AVANCE_DIR = c.rec
    sel = filtradas(spec, a)
    ns = argparse.Namespace(verbose=getattr(a, "verbose", False), borrador=getattr(a, "borrador", False), workers=getattr(a, "workers", None), raiz=None)
    peor, lineas = 0, {}
    for n, (_, _, l) in enumerate(sel):
        lec = c.leccion(l["id"], n, len(sel), cur["lufs"])
        if not os.path.exists(lec.spec):
            print(f"E-CURSO-TIEMPOS  lecciones[{l['id']}]: falta remotion.json. Corre python3 scripts/curso.py componer {c.nombre}")
            return 2
        codigo = remotion.etapa_render(ns, lec, siguiente=False)
        if codigo in (2, 3):
            return codigo
        peor = peor or codigo
        lineas[l["id"]] = f"{l['id']}: {datetime.datetime.now():%Y-%m-%d %H:%M} · {'ok' if not codigo else 'FALLAS'} · {os.path.relpath(lec.salida(), c.dir)}"
    registro = _registro_render(c, spec, lineas)
    promo.actualizar_info(c, "\n".join(registro), MARCA_INI, MARCA_FIN)
    if siguiente:
        print(f"Siguiente: python3 scripts/curso.py carta {c.nombre}" if not peor else "Siguiente: revisa las fallas o repórtalas al usuario.")
    return peor


# ---------------------------------------------------------------- carta, quiz, transcripción
def _texto_items(vals):
    return [str(v.get("texto", "")) if isinstance(v, dict) else str(v) for v in vals or []]


def minutos_de(l, cur, medidas):
    seg = medidas.get(str(l.get("id"))) or narrar.estimar_duracion(expandir_escenas(l), cur)
    return seg / 60


def carta(spec, cur, medidas):
    k = spec["curso"]
    ev = k.get("evaluacion") or {}
    acr = {**cur["acreditacion"], **(ev.get("acreditacion") or {})}
    sin_eval = modo_de(spec)["evaluacion"] == "ninguna"
    todas = lecciones(spec)
    video = sum(minutos_de(l, cur, medidas) for _, _, l in todas)
    activo = sum(len(l.get("preguntas") or []) * cur["min_por_pregunta"] + float((l.get("practica") or {}).get("min") or 0) for _, _, l in todas)
    horas = (video + activo) / 60
    tipos = sorted({e.get("tipo") for _, _, l in todas for e in l.get("escenas") or []} & set(TECNICAS))
    r = [f"# Carta descriptiva — {k['titulo']}", "",
         "> Diseñada conforme a la estructura de los estándares EC0301 y EC0366 (referencia voluntaria).", "",
         "## Datos generales", "",
         f"- **Nombre del curso:** {k['titulo']}", f"- **Modalidad:** {k.get('modalidad')}",
         f"- **Duración:** {k.get('duracion_h')} h declaradas · {horas:.2f} h estimadas ({video:.0f} min de video, {activo:.0f} min de actividad)",
         f"- **Área temática:** {k.get('area_tematica') or 'por definir'}", f"- **Instructor:** {k.get('instructor') or 'por definir'}",
         f"- **Tutor en línea:** {k.get('tutor') or 'por definir'}", f"- **Idioma:** {k.get('idioma') or 'es-MX'}", "",
         "## Objetivo general", "", str(k.get("objetivo_general")), "",
         "## Perfil de ingreso y público", "", f"**Público:** {k.get('publico')}", "", f"**Requisitos de ingreso:** {k.get('perfil_ingreso')}", "",
         "## Temario", "", "| Módulo | Lección | Objetivo | Nivel | Tipo | Min |", "|---|---|---|---|---|---|"]
    for _, m, l in todas:
        r.append(f"| {m.get('titulo')} | {l.get('titulo')} | {l.get('objetivo')} | {l.get('nivel_bloom')} | {l.get('tipo')} | {minutos_de(l, cur, medidas):.1f} |")
    r += ["", "## Técnicas didácticas", ""] + [f"- {TECNICAS[t].capitalize()}" for t in tipos]
    if sin_eval:
        r += ["", "## Evaluación", "", "Sin evaluación: material de consulta. No respalda acreditación ni constancia."]
    else:
        r += ["", "## Evaluación", "", f"- **Diagnóstica:** {ev.get('diagnostica')}", f"- **Formativa:** {ev.get('formativa')}",
              f"- **Sumativa:** {ev.get('sumativa')}", "", "## Criterios de acreditación", "",
              f"- Mínimo {acr['minimo_pct']} % en la evaluación sumativa, con hasta {acr['reintentos']} reintentos y retroalimentación.",
              "- Haber visto todas las lecciones." if acr.get("lecciones_completas") else "- Sin requisito de lecciones completas."]
    r += ["", "## Matriz de alineación", "", "| Objetivo | Criterio de éxito | Escenas | Preguntas | Práctica |", "|---|---|---|---|---|"]
    for _, _, l in todas:
        ids = ", ".join(str(e.get("id")) for e in l.get("escenas") or [])
        qs = ", ".join(f"{q.get('id')} → {q.get('objetivo_ref')}" for q in l.get("preguntas") or [])
        r.append(f"| {l.get('objetivo')} | {l.get('criterio_exito') or '-'} | {ids} | {qs} | {(l.get('practica') or {}).get('consigna') or '-'} |")
    r += ["", "## Materiales y recursos", ""]
    r += [f"- {l.get('titulo')}: video, subtítulos, transcripción" + "".join(f", {x}" for x in l.get("recursos") or []) for _, _, l in todas]
    r += ["", "## Bibliografía", ""] + [f"- {b}" for b in k.get("bibliografia") or ["Por definir"]]
    r += ["", "## Avisos legales y de transparencia", "",
          "- Este curso no cuenta con reconocimiento de validez oficial de estudios (LGE art. 150), salvo que se indique lo contrario con su acuerdo.",
          "- La constancia DC-3 solo puede expedirla un agente capacitador registrado (DC-5) o el patrón; requiere evaluación aprobada. La STPS no otorga valor curricular a este curso ni avala su contenido.",
          f"- {cur['aviso_ia']}", "- Imágenes y audio de terceros: ver créditos y licencia de cada recurso.", ""]
    return "\n".join(r)


def quiz(spec, cur):
    ev = (spec["curso"].get("evaluacion") or {})
    acr = {**cur["acreditacion"], **(ev.get("acreditacion") or {})}
    reactivos = [{**q, "id": f"{l.get('id')}-{q.get('id')}", "leccion": l.get("id"), "modulo": m.get("id"), "nivel_bloom": l.get("nivel_bloom")}
                 for _, m, l in lecciones(spec) for q in l.get("preguntas") or []]
    return {"curso": spec["curso"].get("titulo"), "umbral_pct": acr["minimo_pct"], "reintentos": acr["reintentos"], "reactivos": reactivos}


def quiz_md(q):
    r = [f"# Evaluación — {q['curso']}", "", f"Umbral de acreditación: {q['umbral_pct']} % · Reintentos: {q['reintentos']}", "",
         "> Un MP4 no puede obligar a responder: carga estos reactivos en tu LMS para que la pregunta sea obligatoria y quede registro de la evaluación aprobada.", ""]
    for n, x in enumerate(q["reactivos"], 1):
        r += [f"## {n}. {x['enunciado']}", ""]
        r += [f"- {chr(65 + i)}) {o}" + (" **(correcta)**" if i == x["correcta"] else "") for i, o in enumerate(x["opciones"])]
        r += ["", f"Retroalimentación: {x['retro']}"]
        r += [f"- Si elige {chr(65 + i)}: {t}" for i, t in enumerate(x.get("retro_opciones") or [])] + [""]
    return "\n".join(r)


def transcripcion(l):
    """Equivalente textual: lo que se oye y lo que solo se ve (WCAG 1.2.1 / 1.2.3)."""
    r = [f"# Transcripción — {l.get('titulo')}", ""] + ([f"**Objetivo:** {l['objetivo']}", ""] if l.get("objetivo") else [])
    for e in expandir_escenas(l):
        p = e.get("pantalla") or {}
        vis = [str(p[x]) for x in ("titular", "texto", "enunciado", "definicion", "objetivo") if p.get(x)]
        for lista in LISTAS:
            vis += [t for t in _texto_items(p.get(lista)) if t]
        vis += [f"Opción {chr(65 + i)}: {o}" for i, o in enumerate(p.get("opciones") or [])]
        if vis:
            r.append(f"*Aparece el texto: {' · '.join(vis)}*")
        if e.get("tts"):
            r.append(str(e["tts"]))
        r.append("")
    return "\n".join(r)


def etapa_carta(a, c, siguiente=True):
    spec = cargar(c)
    cfg, cur = cursos_cfg()
    med = medidas_de(c, spec)
    q = quiz(spec, cur)
    hechos = []
    if modo_de(spec)["proposito"] != "presentacion":
        with open(os.path.join(c.dir, "carta-descriptiva.md"), "w", encoding="utf-8") as f:
            f.write(carta(spec, cur, med))
        hechos.append("carta-descriptiva.md")
    if q["reactivos"]:
        with open(os.path.join(c.dir, "quiz.json"), "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=1)
        with open(os.path.join(c.dir, "quiz.md"), "w", encoding="utf-8") as f:
            f.write(quiz_md(q))
        hechos += ["quiz.json", "quiz.md"]
    for _, _, l in lecciones(spec):
        d = os.path.join(c.lecciones, l["id"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{c.slug}_{l['id']}-transcripcion.md"), "w", encoding="utf-8") as f:
            f.write(transcripcion(l))
    print(f"carta: {' · '.join(hechos + [f'{len(lecciones(spec))} transcripciones'])}")
    if siguiente:
        print("Siguiente: revisa con una persona experta; luego costos (AGENT §10) y aprendizaje (§15).")
    return 0


def interaccion(spec, c, cur):
    """Datos del reproductor. Solo lecciones con video: el resto no se puede ver todavía."""
    ev = (spec["curso"].get("evaluacion") or {})
    acr = {**cur["acreditacion"], **(ev.get("acreditacion") or {})}
    salida = []
    for _, _, l in lecciones(spec):
        lec = c.leccion(l["id"])
        ruta_t = os.path.join(lec.rec, "tiempos.json")
        if not os.path.exists(lec.salida()) or not os.path.exists(ruta_t):
            continue
        with open(ruta_t, encoding="utf-8") as f:
            por_id = {t["id"]: t for t in json.load(f)["escenas"]}
        qs = {q.get("id"): q for q in l.get("preguntas") or []}
        capitulos, preguntas = [], []
        for e in l.get("escenas") or []:
            t = por_id.get(e["id"])
            if not t:
                continue
            titulo = (e.get("pantalla") or {}).get("titular") or CAPITULOS.get(e["tipo"], e["tipo"])
            capitulos.append({"t": t["inicio"], "titulo": str(titulo)})
            r = por_id.get(f"{e['id']}-r")
            if e["tipo"] == "pregunta" and r:
                q = qs.get(e.get("pregunta_ref")) or {}
                preguntas.append({"id": str(q.get("id")), "enunciado": q.get("enunciado"), "opciones": q.get("opciones"), "correcta": q.get("correcta"),
                                  "retro": q.get("retro"), "retro_opciones": q.get("retro_opciones") or [],
                                  "pausa": round(t["voz_inicio"] + t["voz_dur"], 3), "reanuda": r["inicio"]})
        final = [{"id": str(q.get("id")), "enunciado": q.get("enunciado"), "opciones": q.get("opciones"), "correcta": q.get("correcta"),
                  "retro": q.get("retro"), "retro_opciones": q.get("retro_opciones") or []}
                 for q in (qs.get(ref) for ref in l.get("prueba_final") or []) if q]
        vtt = f"{c.slug}_{l['id']}.vtt"
        ruta_vtt = os.path.join(lec.dir, vtt)
        texto_vtt = None
        if os.path.exists(ruta_vtt):
            with open(ruta_vtt, encoding="utf-8") as f:
                texto_vtt = f.read()
        salida.append({"id": l["id"], "titulo": l.get("titulo"), "video": os.path.relpath(lec.salida(), c.dir).replace(os.sep, "/"),
                       "vtt": texto_vtt, "capitulos": capitulos, "preguntas": preguntas, "prueba_final": final})
    return {"curso": spec["curso"].get("titulo"), "umbral_pct": acr["minimo_pct"], "reintentos": acr["reintentos"], "lecciones": salida}


def etapa_reproductor(a, c, siguiente=True):
    spec = cargar(c)
    _, cur = cursos_cfg()
    datos = interaccion(spec, c, cur)
    if not datos["lecciones"]:
        print(f"E-CURSO-TIEMPOS  -: no hay lecciones renderizadas. Corre python3 scripts/curso.py render {c.nombre}")
        return 2
    with open(os.path.join(REPO, "scripts", "plantillas", "reproductor.html"), encoding="utf-8") as f:
        html_txt = f.read()
    tema = tema_de(spec, cur)
    pares = {"__TITULO__": html.escape(str(datos["curso"])), "__AVISO__": html.escape(cur["aviso_ia"]), "__FONDO__": tema["fondo"],
             "__PANEL__": tema.get("panel", tema["fondo"]), "__BORDE__": tema.get("borde", tema["tenue"]), "__TEXTO__": tema["texto"],
             "__TENUE__": tema["tenue"], "__ACENTO__": tema["acento"], "__OK__": tema["correcta"], "__MAL__": tema.get("peligro", tema["alerta"])}
    for k, v in pares.items():
        html_txt = html_txt.replace(k, v)
    # `</` escapado: un guion con «</script>» no debe poder cerrar el bloque de datos.
    html_txt = html_txt.replace("__DATOS__", json.dumps(datos, ensure_ascii=False).replace("</", "<\\/"))
    with open(os.path.join(c.dir, "reproductor.html"), "w", encoding="utf-8") as f:
        f.write(html_txt)
    with open(os.path.join(c.dir, "interaccion.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in datos.items()}, f, ensure_ascii=False, indent=1)
    n = sum(len(l["preguntas"]) + len(l["prueba_final"]) for l in datos["lecciones"])
    print(f"reproductor: reproductor.html · {len(datos['lecciones'])} lección(es) · {n} pregunta(s) obligatoria(s)")
    faltan = len(lecciones(spec)) - len(datos["lecciones"])
    if faltan:
        print(f"W-CURSO-REPRODUCTOR  -: {faltan} lección(es) sin video quedan fuera; renderízalas y vuelve a correr reproductor.")
    if siguiente:
        print("Siguiente: abre reproductor.html y pruébalo; las respuestas no salen del navegador (sin registro de alumnos).")
    return 0


def etapa_todo(a, c):
    if not getattr(a, "qa", False):
        a.sin_stills = True
    pasos = [etapa_validar, etapa_voz, etapa_componer]
    if getattr(a, "qa", False) or getattr(a, "jev", False):
        pasos.append(etapa_qa)
    pasos += [etapa_render, etapa_carta, etapa_reproductor]
    for paso in pasos:
        codigo = paso(a, c, siguiente=paso is etapa_reproductor)
        if codigo:
            return codigo
    return 0


def etapa_estado(a, c):
    spec = cargar(c)
    for _, _, l in lecciones(spec):
        lec = c.leccion(l["id"])
        fase = "render" if os.path.exists(lec.salida()) else "componer" if os.path.exists(lec.spec) else "voz" if os.path.exists(os.path.join(lec.rec, "tiempos.json")) else "pendiente"
        print(f"{l['id']}: {fase}")
    return 0


def parser():
    com = argparse.ArgumentParser(add_help=False)
    com.add_argument("--verbose", action="store_true")
    com.add_argument("--raiz")
    ap = argparse.ArgumentParser(description="Cursos en video")
    sub = ap.add_subparsers(dest="etapa", required=True)
    sub.add_parser("nuevo", parents=[com]).add_argument("slug")
    x = sub.add_parser("validar", parents=[com])
    x.add_argument("proyecto")
    x.add_argument("--json", action="store_true")
    x = sub.add_parser("voz", parents=[com])
    x.add_argument("proyecto")
    x.add_argument("--leccion")
    x.add_argument("--solo-lint", action="store_true")
    x = sub.add_parser("componer", parents=[com])
    x.add_argument("proyecto")
    x.add_argument("--leccion")
    x = sub.add_parser("qa", parents=[com])
    x.add_argument("proyecto")
    x.add_argument("--leccion")
    x.add_argument("--jev", action="store_true")
    x.add_argument("--umbral", type=float)
    x.add_argument("--sin-stills", action="store_true")
    x = sub.add_parser("render", parents=[com])
    x.add_argument("proyecto")
    x.add_argument("--leccion")
    x.add_argument("--borrador", action="store_true")
    x.add_argument("--workers")
    sub.add_parser("carta", parents=[com]).add_argument("proyecto")
    sub.add_parser("reproductor", parents=[com]).add_argument("proyecto")
    sub.add_parser("estado", parents=[com]).add_argument("proyecto")
    x = sub.add_parser("todo", parents=[com])
    x.add_argument("proyecto")
    x.add_argument("--borrador", action="store_true")
    x.add_argument("--workers")
    x.add_argument("--jev", action="store_true")
    x.add_argument("--qa", action="store_true")
    sub.add_parser("ayuda", parents=[com])
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    if a.etapa == "ayuda":
        print(__doc__)
        return 0
    if a.etapa == "nuevo":
        return etapa_nuevo(a)
    c = resolver(a.proyecto, a)
    etapas = {"validar": etapa_validar, "voz": etapa_voz, "componer": etapa_componer, "qa": etapa_qa, "render": etapa_render,
              "carta": etapa_carta, "reproductor": etapa_reproductor, "todo": etapa_todo, "estado": etapa_estado}
    return etapas[a.etapa](a, c)


if __name__ == "__main__":
    sys.exit(main())
