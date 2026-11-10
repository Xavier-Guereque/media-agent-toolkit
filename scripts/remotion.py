#!/usr/bin/env python3
"""remotion — el ÚNICO comando que usa el agente para el motor Remotion (React → MP4). Motor OPCIONAL.

El agente escribe `proyectos/<slug>_<DDMMAAAA>/remotion.json` (spec) y la composición en
`remotion/src/composiciones/proyectos/<Nombre>.tsx` (skills oficiales /remotion-markup); luego corre una etapa:

  python3 scripts/remotion.py nuevo    <slug> [--composicion Nombre] [--orientacion vertical] [--duracion 3]
  python3 scripts/remotion.py validar  <proyecto>
  python3 scripts/remotion.py estudio  <proyecto> [--puerto 3000] [--detener]
  python3 scripts/remotion.py render   <proyecto> [--borrador] [--workers N]
  python3 scripts/remotion.py todo     <proyecto> [--borrador]
  python3 scripts/remotion.py estado   <proyecto>
  python3 scripts/remotion.py ayuda

<proyecto> = ruta de la carpeta o slug (o prefijo) bajo proyectos/. Opciones comunes: --verbose (muestra el
stderr de Node) y --raiz <dir> (carpeta que contiene proyectos/; también REMOTION_RAIZ; la usan las pruebas).
REMOTION_DIR apunta a otra copia del motor y REMOTION_MOTOR a otro motor.mjs (pruebas con stub).

Reparto: Node (remotion/motor.mjs) empaqueta y renderiza h264 yuv420p; Python (este script) valida el spec,
genera el registro de composiciones, inyecta duración/tamaño/fps en los props, reporta avance al tablero y
termina el MP4 con FFmpeg (BT.709, loudnorm −14 LUFS, +faststart) con checks de entrega.

Cuándo usarlo: SOLO para composiciones libres que el catálogo del motor promo no expresa (gráficas desde
datos, Lottie, mapas, layouts con metraje real, tipografía cinética). FFmpeg primero; promo-ui para la UI de
la casa (SKILL.md > remotion-video).

Licencia: Remotion es gratis para personas, ONG y empresas de hasta 3 personas; con 4+ hace falta la
Company License (https://remotion.pro/license). `validar` lo recuerda hasta fijar remotion.licencia en config.local.json (valor personal de cada copia).

Códigos de salida: 0 ok · 1 fallo interno · 2 corrige remotion.json o argumentos · 3 entorno (pregunta al usuario).
"""
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import promo  # noqa: E402  (ruta_cmd, linea_issue, actualizar_info, _color_ok: mismo contrato de salida)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_ISSUES = 8
MARCA_INI = "### remotion render — inicio (lo reescribe scripts/remotion.py render)"
MARCA_FIN = "### remotion render — fin"
ALIAS_ORIENTACION = {"horizontal": "1080p"}
EXT_RECURSO = re.compile(r"\.(mp4|mov|webm|wav|mp3|aac|m4a|png|jpe?g|webp|gif|svg|json|srt|vtt|ttf|otf|woff2?)$", re.I)
RE_ID = re.compile(r"^[A-Z][A-Za-z0-9]{0,40}$")
# Props por defecto de la composición de ejemplo (deben coincidir con `meta.props` de Ejemplo.tsx).
PROPS_EJEMPLO = {"titulo": "Composición libre", "subtitulo": "React → MP4 con Remotion",
                 "acento": "#3A74CD", "fondo": "#0F1115"}
CONFIG_DEF = {"fps": 30, "crf": 17, "x264_preset": "slow", "concurrencia": None, "licencia": None}
LICENCIA = ("Remotion: gratis para personas, ONG y empresas de hasta 3 personas; con 4+ empleados hace falta la "
            "Company License (https://remotion.pro/license). Fija remotion.licencia "
            "(\"gratuita\" | \"company\") en config.local.json (es personal de cada copia) para dejar de ver este aviso.")

PLANTILLA_BRIEF = """# Brief — {slug}

## Objetivo
(qué debe lograr el video; un enunciado)

## Público y canal
(para quién y dónde se publica: reel 9:16, YouTube 16:9…)

## Mensaje clave y datos (con fuente)
- …

## Recursos en recursos/
(clips, imágenes, voz, música: nombre de archivo → uso)

## Duración y formato
(segundos, orientación; coincide con remotion.json)
"""

PLANTILLA_INFO = """Proyecto: {nombre}
Fecha: {fecha}
Motor: Remotion (composición libre React → MP4; skill remotion-video). Spec: remotion.json.
Composición: remotion/src/composiciones/proyectos/{composicion}.tsx (no se versiona; recursos en recursos/).
Licencia Remotion: gratis para personas, ONG y empresas ≤ 3 personas; 4+ → Company License (remotion.pro/license).
"""


# ---------------------------------------------------------------- rutas
def dir_motor():
    return os.path.abspath(os.environ.get("REMOTION_DIR") or os.path.join(REPO, "remotion"))


def ruta_motor():
    return os.environ.get("REMOTION_MOTOR") or os.path.join(dir_motor(), "motor.mjs")


def dir_proyectos_tsx():
    return os.path.join(dir_motor(), "src", "composiciones", "proyectos")


def config():
    cfg = comun.cargar_config(REPO)
    rem = {**CONFIG_DEF, **(cfg.get("remotion") or {})}
    res = (cfg.get("salida") or {}).get("resoluciones") or {"vertical": "1080x1920", "1080p": "1920x1080"}
    formatos = (cfg.get("salida") or {}).get("formatos_video") or ["mp4"]
    return rem, res, formatos


class Proyecto:
    """Rutas del contrato de carpetas (AGENT §13 + motor Remotion)."""

    def __init__(self, carpeta):
        self.dir = os.path.abspath(carpeta)
        self.nombre = os.path.basename(self.dir)
        self.slug = re.sub(r"_\d{8}$", "", self.nombre)
        self.spec = os.path.join(self.dir, "remotion.json")
        self.rec = os.path.join(self.dir, "recursos")
        self.rem = os.path.join(self.rec, "remotion")
        self.props_json = os.path.join(self.rem, "props.json")
        self.motor_mp4 = os.path.join(self.rem, "motor.mp4")
        self.render_json = os.path.join(self.rem, "render.json")
        self.estudio_pid = os.path.join(self.rem, "estudio.pid")
        self.estudio_log = os.path.join(self.rem, "estudio.log")
        self.costos = os.path.join(self.rec, "costos.jsonl")
        self.info = os.path.join(self.dir, "info.txt")
        # Defaults = proyecto suelto. curso.py los cambia: cada lección reporta en el tablero del curso, en su tramo.
        self.avance_dir = self.rec
        self.avance_rango = (0.0, 100.0)
        self.etiqueta = "remotion"
        self.lufs = -14.0

    def leer_spec(self):
        with open(self.spec, encoding="utf-8") as f:
            return json.load(f)

    def salida(self, spec=None):
        spec = spec if spec is not None else (self.leer_spec() if os.path.exists(self.spec) else {})
        nombre = spec.get("salida") if isinstance(spec.get("salida"), str) else None
        return os.path.join(self.dir, nombre or f"{self.slug}.mp4")

    def rel(self, ruta):
        return os.path.relpath(ruta, self.dir) if ruta else "-"


def raiz_proyectos(a):
    return os.path.join(os.path.abspath(a.raiz or os.environ.get("REMOTION_RAIZ") or REPO), "proyectos")


def resolver_proyecto(ref, a):
    """Ruta existente, nombre exacto, slug exacto (el más reciente) o prefijo único (como promo.py)."""
    es_ruta = os.sep in ref or ref.startswith(".") or os.path.isfile(os.path.join(ref, "remotion.json"))
    if es_ruta and os.path.isdir(ref):
        return Proyecto(ref)
    base = raiz_proyectos(a)
    dirs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))) \
        if os.path.isdir(base) else []
    if ref in dirs:
        return Proyecto(os.path.join(base, ref))
    mismos = [d for d in dirs if re.sub(r"_\d{8}$", "", d) == ref]
    if mismos:
        return Proyecto(os.path.join(base, max(mismos, key=promo._fecha_nombre)))
    pref = [d for d in dirs if d.startswith(ref)]
    if len(pref) == 1:
        return Proyecto(os.path.join(base, pref[0]))
    if pref:
        print(f"ERROR proyecto ambiguo '{ref}': {', '.join(pref[:5])}. Usa el nombre completo.")
    else:
        print(f"ERROR no existe el proyecto '{ref}' en {base}. Crea uno: python3 scripts/remotion.py nuevo <slug>")
    raise SystemExit(2)


# ---------------------------------------------------------------- entorno y registro
def deps_ok():
    return os.path.isdir(os.path.join(dir_motor(), "node_modules", "@remotion", "cli"))


def navegador_ok():
    return os.path.isdir(os.path.join(dir_motor(), "node_modules", ".remotion", "chrome-headless-shell"))


ARREGLO_DEPS = "npm ci --prefix remotion && npx --prefix remotion remotion browser ensure"


def exigir_deps():
    if deps_ok():
        return 0
    print(f"ERROR entorno: faltan las dependencias del motor Remotion en {promo.ruta_cmd(dir_motor())}/node_modules.")
    print(f"Siguiente: pregunta al usuario y corre: {ARREGLO_DEPS}  (zsh scripts/preflight.sh lo avisa como opcional)")
    return 3


def ids_base():
    """Composiciones versionadas (BASE) según src/composiciones/index.ts."""
    try:
        with open(os.path.join(dir_motor(), "src", "composiciones", "index.ts"), encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        return []
    return re.findall(r"id:\s*'([A-Za-z0-9]+)'", texto)


def tsx_proyectos():
    d = dir_proyectos_tsx()
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".tsx")) if os.path.isdir(d) else []


def generar_registro():
    """Reescribe registro.ts con un import por TSX de proyectos/ (solo si cambió, para no invalidar cachés).
    Devuelve (ids registrados, nombres de archivo ignorados por no ser PascalCase)."""
    ids, malos = [], []
    for nombre in tsx_proyectos():
        (ids if RE_ID.match(nombre) else malos).append(nombre)
    lineas = ["// GENERADO por scripts/remotion.py (validar/render): no editar a mano.",
              "import type { Entrada } from '../../lib/props';"]
    lineas += [f"import {{ Composicion as C_{i}, meta as M_{i} }} from './{i}';" for i in ids]
    lineas += ["", "export const PROYECTOS: Entrada[] = ["]
    lineas += [f"  {{ id: '{i}', component: C_{i}, meta: M_{i} }}," for i in ids]
    lineas += ["];", ""]
    texto = "\n".join(lineas)
    ruta = os.path.join(dir_proyectos_tsx(), "registro.ts")
    previo = None
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            previo = f.read()
    if previo != texto:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
    return ids, malos


# ---------------------------------------------------------------- spec
def _issue(codigo, ruta, msg, arreglo, severidad="E"):
    return {"codigo": codigo, "severidad": severidad, "ruta": ruta, "msg": msg, "arreglo": arreglo}


def _rutas_en_props(valor, ruta="props"):
    """Strings dentro de props que parecen archivos de recursos/ (por extensión)."""
    if isinstance(valor, str):
        if EXT_RECURSO.search(valor) and not re.match(r"^(https?:|data:|/)", valor):
            yield ruta, valor
    elif isinstance(valor, dict):
        for k, v in valor.items():
            yield from _rutas_en_props(v, f"{ruta}.{k}")
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            yield from _rutas_en_props(v, f"{ruta}[{i}]")


def resolucion(spec, res):
    o = str(spec.get("orientacion") or "vertical")
    clave = ALIAS_ORIENTACION.get(o, o)
    if clave not in res:
        return None, None, clave
    w, h = res[clave].lower().split("x")
    return int(w), int(h), clave


def validar_spec(spec, p, registrados, rem, res, formatos):
    e, w = [], []
    if not isinstance(spec, dict):
        return [_issue("E-REMOTION-SPEC", "-", "remotion.json no es un objeto JSON",
                       "Vuelve a crearlo: python3 scripts/remotion.py ayuda")], w
    if spec.get("version") != 1:
        e.append(_issue("E-REMOTION-VERSION", "version", f"version {spec.get('version')!r} (se espera 1)", "Pon \"version\": 1."))
    comp = spec.get("composicion")
    if not isinstance(comp, str) or not RE_ID.match(comp):
        e.append(_issue("E-REMOTION-COMPOSICION", "composicion", f"id inválido {comp!r}",
                        "Usa PascalCase (p. ej. DemoProducto), igual que el archivo .tsx."))
    elif comp not in registrados:
        e.append(_issue("E-REMOTION-REGISTRO", "composicion", f"'{comp}' no está registrada",
                        f"Crea {promo.ruta_cmd(os.path.join(dir_proyectos_tsx(), comp + '.tsx'))} (exporta Composicion y meta). "
                        f"Registradas: {', '.join(registrados) or 'ninguna'}."))
    salida = spec.get("salida")
    if salida is not None and (not isinstance(salida, str) or os.sep in salida
                               or salida.rsplit(".", 1)[-1].lower() not in formatos):
        e.append(_issue("E-REMOTION-SALIDA", "salida", f"{salida!r}",
                        f"Nombre de archivo sin carpetas con extensión {'/'.join(formatos)} (p. ej. {p.slug}.mp4)."))
    ancho, alto, clave = resolucion(spec, res)
    if ancho is None:
        e.append(_issue("E-REMOTION-ORIENTACION", "orientacion", f"{spec.get('orientacion')!r} no está en config.json > salida.resoluciones",
                        f"Usa una de: {', '.join(sorted(res))} (o 'horizontal' = 1080p)."))
    fps = spec.get("fps", rem["fps"])
    if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 120:
        e.append(_issue("E-REMOTION-FPS", "fps", f"{fps!r}", "Entero entre 1 y 120 (30 por defecto)."))
    dur = spec.get("duracion")
    if not isinstance(dur, (int, float)) or isinstance(dur, bool) or not 0 < dur <= 600:
        e.append(_issue("E-REMOTION-DURACION", "duracion", f"{dur!r}", "Segundos (número > 0 y ≤ 600), p. ej. 12.0."))
    props = spec.get("props", {})
    if not isinstance(props, dict):
        e.append(_issue("E-REMOTION-PROPS", "props", "no es un objeto", "Pon \"props\": { … } con los datos de la composición."))
    else:
        for ruta, v in _rutas_en_props(props):
            if not os.path.exists(os.path.join(p.rec, v)):
                e.append(_issue("E-REMOTION-RECURSO", ruta, f"no existe recursos/{v}",
                                "Copia el archivo a recursos/ del proyecto (la composición lo lee con staticFile())."))
    if rem.get("licencia") is None:
        w.append(_issue("W-REMOTION-LICENCIA", "-", LICENCIA, "", "W"))
    if deps_ok() and not navegador_ok():
        w.append(_issue("W-REMOTION-NAVEGADOR", "-", "falta Chrome Headless Shell: se descargará en el primer render (~2 min)",
                        "Adelántalo: npx --prefix remotion remotion browser ensure", "W"))
    return e, w


def props_render(spec, rem, res):
    ancho, alto, _ = resolucion(spec, res)
    return {**(spec.get("props") or {}), "duracion": float(spec["duracion"]), "ancho": ancho, "alto": alto,
            "fps": int(spec.get("fps", rem["fps"]))}


# ---------------------------------------------------------------- etapas
def _pascal(slug):
    return "".join(w.capitalize() for w in re.split(r"[-_]+", slug) if w)


def etapa_nuevo(a):
    rem, res, _ = config()
    slug = a.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 60:
        print(f"ERROR slug inválido '{a.slug}': usa minúsculas, números y guiones (p. ej. demo-producto).")
        return 2
    comp = (a.composicion or _pascal(slug)).strip()
    if not RE_ID.match(comp):
        print(f"ERROR composición inválida '{comp}': PascalCase sin espacios (p. ej. DemoProducto).")
        return 2
    orient = a.orientacion or "vertical"
    if ALIAS_ORIENTACION.get(orient, orient) not in res:
        print(f"ERROR orientación '{orient}': usa una de {', '.join(sorted(res))} (o 'horizontal').")
        return 2
    if a.duracion is not None and not 0 < a.duracion <= 600:
        print("ERROR --duracion en segundos (> 0 y ≤ 600).")
        return 2
    hoy = datetime.date.today()
    p = Proyecto(os.path.join(raiz_proyectos(a), f"{slug}_{hoy.strftime('%d%m%Y')}"))
    if os.path.exists(p.dir):
        print(f"ERROR ya existe {p.dir}. Usa ese proyecto o elige otro slug.")
        return 2
    destino = os.path.join(dir_proyectos_tsx(), comp + ".tsx")
    if os.path.exists(destino) or comp in ids_base():
        print(f"ERROR la composición '{comp}' ya existe ({promo.ruta_cmd(destino)}). Elige otro nombre con --composicion.")
        return 2
    ejemplo = os.path.join(dir_motor(), "src", "composiciones", "Ejemplo.tsx")
    if not os.path.exists(ejemplo):
        print(f"ERROR entorno: falta {promo.ruta_cmd(ejemplo)}. ¿Repo incompleto? Actualiza el repo.")
        return 3
    with open(ejemplo, encoding="utf-8") as f:
        tsx = f.read()
    tsx = re.sub(r"\A(// .*\n)+", f"// Composición del proyecto {p.nombre} (copiada de Ejemplo.tsx por scripts/remotion.py nuevo).\n"
                                   "// Exporta `Composicion` y `meta`; los recursos del proyecto se leen con staticFile('archivo').\n"
                                   "// Reglas: todo depende de useCurrentFrame(); nada de Math.random, timers ni CSS animations.\n", tsx)
    # proyectos/ está un nivel más abajo que Ejemplo.tsx: los imports relativos suben un nivel más.
    tsx = tsx.replace("from '../", "from '../../")
    os.makedirs(dir_proyectos_tsx(), exist_ok=True)
    os.makedirs(p.rem, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(tsx)
    spec = {"version": 1, "composicion": comp, "salida": f"{slug}.mp4", "orientacion": orient,
            "fps": rem["fps"], "duracion": float(a.duracion if a.duracion is not None else 3.0),
            "props": {**PROPS_EJEMPLO, "titulo": slug.replace("-", " ").capitalize()}}
    with open(p.spec, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(p.dir, "brief.md"), "w", encoding="utf-8") as f:
        f.write(PLANTILLA_BRIEF.format(slug=slug))
    with open(p.info, "w", encoding="utf-8") as f:
        f.write(PLANTILLA_INFO.format(nombre=p.nombre, fecha=hoy.strftime("%d/%m/%Y"), composicion=comp))
    generar_registro()
    print(f"nuevo: {promo.ruta_cmd(p.dir)}/ · remotion.json ({orient}, {spec['duracion']:g} s) · "
          f"composición {promo.ruta_cmd(destino)}")
    print(f"Siguiente: llena brief.md, edita el TSX (/remotion-markup) y remotion.json; luego "
          f"python3 scripts/remotion.py validar {p.nombre}")
    return 0


def _cargar_spec(p):
    if not os.path.exists(p.spec):
        print(f"ERROR falta {p.rel(p.spec)}. Siguiente: python3 scripts/remotion.py nuevo <slug> (o python3 scripts/remotion.py ayuda)")
        raise SystemExit(2)
    try:
        return p.leer_spec()
    except json.JSONDecodeError as ex:
        print(f"E-REMOTION-JSON  remotion.json: {ex.msg} (línea {ex.lineno}). Corrige el JSON.")
        raise SystemExit(2)


def etapa_validar(a, p, siguiente=True, callado=False):
    rem, res, formatos = config()
    spec = _cargar_spec(p)
    ids, malos = generar_registro()
    errs, avis = validar_spec(spec, p, ids_base() + ids, rem, res, formatos)
    for m in malos:
        avis.append(_issue("W-REMOTION-ARCHIVO", "-", f"{m}.tsx ignorado: el nombre debe ser PascalCase", "Renómbralo.", "W"))
    if not deps_ok():
        errs.append(_issue("E-ENTORNO", "-", f"faltan las dependencias del motor ({promo.ruta_cmd(dir_motor())}/node_modules)",
                           f"Corre: {ARREGLO_DEPS}"))
    codigo = 3 if any(i["codigo"] == "E-ENTORNO" for i in errs) else (2 if errs else 0)
    if callado and codigo == 0:
        return 0, spec
    ancho, alto, _ = resolucion(spec, res)
    extra = ""
    if codigo == 0:
        fps = int(spec.get("fps", rem["fps"]))
        extra = f" · {spec['duracion']:g} s, {round(spec['duracion'] * fps)} cuadros, {ancho}x{alto} @ {fps} fps"
    print(f"remotion validar · {p.nombre} — {promo._plural(len(errs), 'error', 'errores')}, "
          f"{promo._plural(len(avis), 'aviso', 'avisos')}{extra}")
    todos = errs + avis
    for i in todos[:MAX_ISSUES]:
        print(promo.linea_issue(i))
    if len(todos) > MAX_ISSUES:
        print(f"… y {len(todos) - MAX_ISSUES} más")
    if siguiente or codigo:
        print(f"Siguiente: python3 scripts/remotion.py render {p.nombre}  (vista previa: estudio {p.nombre})"
              if codigo == 0 else siguiente_fallo(codigo, p, "validar"))
    return codigo, spec


def siguiente_fallo(codigo, p, etapa):
    if codigo == 2:
        return f"Siguiente: corrige remotion.json o el TSX y corre python3 scripts/remotion.py validar {p.nombre}"
    if codigo == 3:
        return f"Siguiente: problema de entorno; pregunta al usuario ({ARREGLO_DEPS}; zsh scripts/preflight.sh)."
    return f"Siguiente: error interno; repórtalo al usuario (detalle: python3 scripts/remotion.py {etapa} {p.nombre} --verbose)"


def _reportar(p, pct, detalle, estado=None):
    """comun.avance('render') con el 0-100 del motor mapeado al tramo de p; 'listo' solo si el tramo llega a 100."""
    lo, hi = p.avance_rango
    if pct is not None:
        pct = lo + pct * (hi - lo) / 100
        if hi < 100 and estado in (None, "listo"):
            estado = "en_curso"
    return comun.avance("render", pct, f"{p.etiqueta}{detalle}", estado=estado)


def _avance_render(p):
    """stderr del motor → tablero (etapa render) y, en terminal, pasos de 10 %."""
    vistos = set()

    def f(linea):
        m = re.search(r"avance\s+(\d+)%", linea)
        if not m:
            return
        pct = int(m.group(1))
        _reportar(p, pct, "")
        if sys.stdout.isatty() and pct // 10 not in vistos:
            vistos.add(pct // 10)
            print("  " + linea, flush=True)
    return f


def sondear(ruta):
    """(stream de video, stream de audio | None, duración del contenedor)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
                        "stream=codec_type,codec_name,nb_read_packets,duration,pix_fmt,width,height,r_frame_rate,"
                        "color_primaries,color_transfer,color_space:format=duration", "-of", "json", ruta],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    au = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    return v, au, float((d.get("format") or {}).get("duration") or 0)


def acabar(p, video, salida, lufs=-14.0, borrador=False):
    """Acabado FFmpeg del h264 del motor: etiquetas BT.709 (bsf, sin recodificar), audio normalizado a `lufs`
    en dos pasadas → AAC 256k, +faststart. Devuelve (hay_audio, bsf_aplicado)."""
    v, au, _ = sondear(video)
    if borrador:
        comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", video, "-c", "copy", "-movflags", "+faststart", salida])
        return au is not None, False
    bsf = []
    if not promo._color_ok(v) and v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p":
        bsf = ["-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1"]
    if au is None:
        comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", video, "-map", "0:v:0", "-c:v", "copy"] + bsf +
                  ["-an", "-movflags", "+faststart", salida])
        return False, bool(bsf)
    crudo, mezcla = os.path.join(p.rem, "audio_crudo.wav"), os.path.join(p.rem, "mezcla.wav")
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", video, "-vn", "-map", "0:a:0", "-ar", "48000",
               "-c:a", "pcm_s24le", crudo])
    comun.loudnorm_2p(crudo, mezcla, I=lufs, TP=-1.5, muestras=round(comun.dur(crudo) * 48000))
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", video, "-i", mezcla, "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy"] + bsf + ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest",
                                        "-movflags", "+faststart", salida])
    os.remove(crudo)
    return True, bool(bsf)


def verificar(salida, cuadros, duracion, fps, lufs, hay_audio):
    """Checks de entrega: cuadros, duración ±1 cuadro, color BT.709, sonoridad post-AAC."""
    v, _, dur_fmt = sondear(salida)
    fallas = []
    n = int(v.get("nb_read_packets") or 0)
    if n != cuadros:
        fallas.append(f"cuadros {n}≠{cuadros}")
    tol = 1.0 / fps + 1e-3
    dur_v = float(v.get("duration") or dur_fmt)
    if abs(dur_v - duracion) > tol:
        fallas.append(f"duración {dur_v:.3f}≠{duracion:.3f}")
    if not promo._color_ok(v):
        fallas.append(f"color {v.get('pix_fmt')}/{v.get('color_primaries', '?')}/{v.get('color_transfer', '?')}/{v.get('color_space', '?')}")
    med = {"I": None, "TP": None}
    if hay_audio:
        med = comun.ebur128(salida)
        if abs(med["I"] - lufs) > 0.5:
            fallas.append(f"sonoridad {med['I']:.1f} LUFS (objetivo {lufs:g}±0.5)")
        if med["TP"] > -1.0:
            fallas.append(f"true peak {med['TP']:.1f} dBTP (>-1.0)")
    return {"fallas": fallas, "cuadros": n, "duracion": dur_v, "I": med["I"], "TP": med["TP"],
            "w": v.get("width"), "h": v.get("height"), "pix_fmt": v.get("pix_fmt")}


def etapa_render(a, p, siguiente=True):
    rem, res, _ = config()
    codigo, spec = etapa_validar(a, p, siguiente=False, callado=True)
    if codigo:
        return codigo
    os.makedirs(p.rem, exist_ok=True)
    props = props_render(spec, rem, res)
    with open(p.props_json, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=1)
    comun.AVANCE_DIR = p.avance_dir
    borrador = bool(getattr(a, "borrador", False))
    args = ["render", "--composicion", spec["composicion"], "--props", p.props_json, "--public-dir", p.rec,
            "--salida", p.motor_mp4, "--crf", rem["crf"], "--x264-preset", rem["x264_preset"]]
    conc = getattr(a, "workers", None) or rem.get("concurrencia")
    if conc:
        if not re.fullmatch(r"[1-9]\d*%?", str(conc)):
            print(f"ERROR --workers/concurrencia inválida {conc!r}: usa un entero (p. ej. 4) o un porcentaje (50%).")
            print(siguiente_fallo(2, p, "render"))
            return 2
        args += ["--concurrencia", conc]
    if borrador:
        args.append("--borrador")
    if rem.get("licencia") is None:
        print("AVISO " + LICENCIA.split(". Fija")[0] + ".")
    _reportar(p, 0, ": empaquetando")
    t0 = time.time()
    codigo, obj, _ = comun.correr_motor_node(ruta_motor(), args, cwd=dir_motor(), repo=REPO, verbose=a.verbose,
                                             al_avance=_avance_render(p), nombre="motor remotion")
    with open(p.render_json, "w", encoding="utf-8") as f:
        json.dump({"codigo": codigo, "borrador": borrador, **(obj or {})}, f, ensure_ascii=False)
    if codigo != 0 or not obj or not obj.get("ok"):
        promo.imprimir_issues(obj)
        _reportar(p, None, " falló", estado="error")
        print(siguiente_fallo(codigo or 1, p, "render"))
        return codigo or 1
    video = obj.get("video") or p.motor_mp4
    salida = p.salida(spec)
    hay_audio, bsf = acabar(p, video, salida, lufs=p.lufs, borrador=borrador)
    segundos = time.time() - t0
    cuadros, fps = int(obj.get("cuadros") or 0), int(obj.get("fps") or props["fps"])
    if borrador:
        _reportar(p, 100, " borrador listo", estado="listo")
        print(f"render (borrador): {p.rel(salida)} · {cuadros} cuadros · {obj.get('ancho')}x{obj.get('alto')} · {segundos:.0f} s")
        if siguiente:
            print(f"Siguiente: revisa el borrador; render final: python3 scripts/remotion.py render {p.nombre}")
        return 0
    chk = verificar(salida, cuadros, cuadros / fps, fps, p.lufs, hay_audio)
    _reportar(p, 100, " listo", estado="listo" if not chk["fallas"] else "aviso")
    son = f"{chk['I']:.1f} LUFS" if hay_audio else "sin audio"
    estado = "ok" if not chk["fallas"] else "FALLAS " + "; ".join(chk["fallas"])
    linea = (f"render: {p.rel(salida)} · {chk['cuadros']} cuadros · {chk['duracion']:.2f} s · {chk['w']}x{chk['h']} @ {fps} fps · "
             f"{chk['pix_fmt']}/bt709 · {son} · motor {obj.get('segundos', 0):.0f} s, total {segundos:.0f} s · checks: {estado}")
    print(linea)
    promo.actualizar_info(p, f"{datetime.datetime.now():%Y-%m-%d %H:%M} · {linea}\n"
                             f"composición {spec['composicion']} · spec remotion.json · props recursos/remotion/props.json · "
                             f"acabado FFmpeg: {'BT.709 por bsf, ' if bsf else ''}{f'loudnorm −{abs(p.lufs):g} LUFS + AAC 256k, ' if hay_audio else ''}+faststart",
                          MARCA_INI, MARCA_FIN)
    if siguiente:
        print("Siguiente: muestra el video al usuario; luego costos (AGENT §10) y aprendizaje (§15)." if not chk["fallas"]
              else f"Siguiente: revisa las fallas (python3 scripts/remotion.py render {p.nombre} --verbose) o repórtalas al usuario.")
    return 0 if not chk["fallas"] else 1


def _pid_vivo(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            pid = int(f.readline().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def etapa_estudio(a, p):
    pid = _pid_vivo(p.estudio_pid)
    if getattr(a, "detener", False):
        if pid:
            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
            print(f"estudio detenido (pid {pid}).")
        else:
            print("estudio: no había ninguno corriendo.")
        if os.path.exists(p.estudio_pid):
            os.remove(p.estudio_pid)
        print(f"Siguiente: python3 scripts/remotion.py render {p.nombre}")
        return 0
    if exigir_deps():
        return 3
    rem, res, _ = config()
    codigo, spec = etapa_validar(a, p, siguiente=False, callado=True)
    if codigo:
        return codigo
    os.makedirs(p.rem, exist_ok=True)
    with open(p.props_json, "w", encoding="utf-8") as f:
        json.dump(props_render(spec, rem, res), f, ensure_ascii=False, indent=1)
    puerto = int(getattr(a, "puerto", None) or 3000)
    url = f"http://localhost:{puerto}"
    if pid:
        print(f"estudio ya corre (pid {pid}): {url} · log: {p.rel(p.estudio_log)}")
        print(f"Siguiente: ábrelo en el navegador; para parar: python3 scripts/remotion.py estudio {p.nombre} --detener")
        return 0
    node = comun.buscar_node(REPO)
    cli = os.path.join(dir_motor(), "node_modules", "@remotion", "cli", "remotion-cli.js")
    cmd = [node, cli, "studio", "src/index.ts", "--props", p.props_json, "--public-dir", p.rec,
           "--port", str(puerto), "--no-open"]
    with open(p.estudio_log, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, cwd=dir_motor())
    with open(p.estudio_pid, "w", encoding="utf-8") as f:
        f.write(f"{proc.pid}\n{time.time():.0f}\n")
    print(f"estudio: {url} (pid {proc.pid}, tarda ~10 s en arrancar) · composición {spec['composicion']} · log: {p.rel(p.estudio_log)}")
    print(f"Siguiente: revisa en el navegador; para parar: python3 scripts/remotion.py estudio {p.nombre} --detener; "
          f"render: python3 scripts/remotion.py render {p.nombre}")
    return 0


def etapa_estado(a, p):
    rem, res, _ = config()
    spec = _cargar_spec(p)
    ancho, alto, _ = resolucion(spec, res)
    print(f"estado · {p.nombre} · composición {spec.get('composicion')} · {spec.get('duracion')} s · {ancho}x{alto} · "
          f"deps {'ok' if deps_ok() else 'FALTAN'} · navegador {'ok' if navegador_ok() else 'falta (se descarga al renderizar)'}")
    salida = p.salida(spec)
    r = {}
    if os.path.exists(p.render_json):
        with open(p.render_json, encoding="utf-8") as f:
            r = json.load(f)
    if r:
        print(f"render: código {r.get('codigo')} · {r.get('cuadros', '?')} cuadros · motor {r.get('segundos', 0):.0f} s"
              f"{' · borrador' if r.get('borrador') else ''} · salida {'ok' if os.path.exists(salida) else 'falta'}: {p.rel(salida)}")
    pid = _pid_vivo(p.estudio_pid)
    if pid:
        print(f"estudio corriendo (pid {pid}) · log: {p.rel(p.estudio_log)}")
    sig = "render" if not os.path.exists(salida) or r.get("codigo") != 0 else "estado"
    print(f"Siguiente: python3 scripts/remotion.py {'validar' if not r else sig} {p.nombre}")
    return 0


def etapa_todo(a, p):
    codigo, _ = etapa_validar(a, p, siguiente=False)
    if codigo:
        return codigo
    return etapa_render(a, p)


def etapa_ayuda(a):
    print("""remotion-video — composiciones libres React → MP4 (motor OPCIONAL; FFmpeg primero, promo-ui para la UI de la casa)
Spec proyectos/<slug>_<DDMMAAAA>/remotion.json:
  {"version": 1, "composicion": "DemoProducto", "salida": "demo-producto.mp4", "orientacion": "vertical",
   "fps": 30, "duracion": 12.0, "props": {"titulo": "…", "clip": "clip1.mp4", "voz": "voz.wav"}}
  orientacion: vertical (1080x1920) | 1080p/horizontal (1920x1080) | 720p | 4k | cuadrada. props: libres;
  las rutas de archivo son relativas a recursos/ del proyecto y deben existir (la composición usa staticFile()).
Composición: remotion/src/composiciones/proyectos/<Nombre>.tsx exporta `Composicion` (React.FC<PropsBase & …>)
  y `meta` ({fps, ancho, alto, duracion, props}); duración/tamaño/fps reales los manda remotion.json.
  Reglas: todo depende de useCurrentFrame(); nada de Math.random/timers/CSS animations; sin logos ajenos.
Flujo: nuevo → editar TSX (/remotion-markup) y remotion.json → validar → estudio (vista previa) → render → final.
Render: motor h264 yuv420p (config.json > remotion: crf, x264_preset) + acabado FFmpeg (BT.709, loudnorm −14 LUFS,
  AAC 256k, +faststart) y checks; salida en la raíz del proyecto; avance en el tablero (etapa render).
Entorno: node ≥ 20 y `npm ci --prefix remotion && npx --prefix remotion remotion browser ensure` (opcional en preflight).
Skills oficiales (no vendorizadas): npx skills add remotion-dev/skills -a claude-code -y  (Node ≥ 22.20).
Licencia: gratis para personas, ONG y empresas ≤ 3 personas; 4+ → Company License (https://remotion.pro/license).
Códigos: 0 ok · 1 interno · 2 corrige remotion.json/TSX · 3 entorno.""")
    return 0


# ---------------------------------------------------------------- CLI
def construir_parser():
    ap = argparse.ArgumentParser(prog="remotion.py", description="Motor Remotion (composiciones libres) — etapas para el agente")
    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--verbose", action="store_true", help="muestra el stderr de Node")
    comunes.add_argument("--raiz", help="carpeta que contiene proyectos/ (default: raíz del repo o $REMOTION_RAIZ)")
    sub = ap.add_subparsers(dest="etapa", required=True, metavar="etapa")
    x = sub.add_parser("nuevo", parents=[comunes], help="crea proyectos/<slug>_<DDMMAAAA>/ y el TSX desde Ejemplo")
    x.add_argument("slug")
    x.add_argument("--composicion", help="id PascalCase (default: el slug en PascalCase)")
    x.add_argument("--orientacion", help="vertical (default) | horizontal | 1080p | 720p | 4k | cuadrada")
    x.add_argument("--duracion", type=float, help="segundos (default 3)")
    for nombre in ("validar", "estado"):
        sub.add_parser(nombre, parents=[comunes]).add_argument("proyecto")
    x = sub.add_parser("estudio", parents=[comunes], help="Remotion Studio en segundo plano (vista previa)")
    x.add_argument("proyecto")
    x.add_argument("--puerto", type=int, default=3000)
    x.add_argument("--detener", action="store_true")
    for nombre in ("render", "todo"):
        x = sub.add_parser(nombre, parents=[comunes])
        x.add_argument("proyecto")
        x.add_argument("--borrador", action="store_true", help="mitad de resolución, CRF 28, sin acabado")
        x.add_argument("--workers", help="concurrencia del render (N o 50%%)")
    sub.add_parser("ayuda", parents=[comunes])
    return ap


def main(argv=None):
    a = construir_parser().parse_args(argv)
    if a.etapa == "nuevo":
        return etapa_nuevo(a)
    if a.etapa == "ayuda":
        return etapa_ayuda(a)
    p = resolver_proyecto(a.proyecto, a)
    etapas = {"validar": lambda a, p: etapa_validar(a, p)[0], "estudio": etapa_estudio, "render": etapa_render,
              "todo": etapa_todo, "estado": etapa_estado}
    return etapas[a.etapa](a, p)


if __name__ == "__main__":
    sys.exit(main())
