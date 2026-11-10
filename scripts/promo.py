#!/usr/bin/env python3
"""promo — el ÚNICO comando que usa el agente para los videos promo (HTML → cuadros → FFmpeg).

El agente solo escribe `proyectos/<slug>_<DDMMAAAA>/promo.json` (contenido) y corre una etapa:

  python3 scripts/promo.py nuevo   <slug> [--ejemplo asistente-ia-cta-whatsapp | demo-10s]
  python3 scripts/promo.py validar <proyecto>
  python3 scripts/promo.py voz     <proyecto> [--sin-verificar]      (solo con audio.voz)
  python3 scripts/promo.py cuadros <proyecto> [--t 1.2,3.4] [--ref video.mp4]
  python3 scripts/promo.py render  <proyecto> [--borrador] [--workers N] [--fondo]
  python3 scripts/promo.py audio   <proyecto> [--refrescar-cc0]
  python3 scripts/promo.py final   <proyecto>
  python3 scripts/promo.py todo    <proyecto> [--borrador] [--workers N] [--sin-verificar]
  python3 scripts/promo.py estado  <proyecto>
  python3 scripts/promo.py ayuda

<proyecto> = ruta de la carpeta o slug (o prefijo) bajo proyectos/. Opciones comunes:
--verbose (muestra el stderr de Node) y --raiz <dir> (carpeta que contiene proyectos/;
también por la variable PROMO_RAIZ; la usan las pruebas para no escribir en el repo).

Reparto: Node (promo/motor.mjs) valida, planea, hace QA, cuadros y render; Python (este
script + sonido.py) tiene la CLI del agente, llamadas pagadas, audio, mux final, checks y
costos. Salida corta a propósito: el orquestador paga por token.

Códigos de salida: 0 ok · 1 fallo interno · 2 corrige promo.json o argumentos ·
3 entorno (pregunta al usuario) · 4 API externa (reintenta una vez).
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import sonido  # noqa: E402
import voz  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Ejemplo de oro por defecto: con él y `ayuda`, el orquestador barato escribe un spec válido en
# 1 ronda (medido por el coordinador: 4 rondas con demo-10s, que sigue disponible con --ejemplo).
EJEMPLO_DEF = "asistente-ia-cta-whatsapp"
MAX_ISSUES = 8
MARCA_INI = "### promo final — inicio (lo reescribe scripts/promo.py final)"
MARCA_FIN = "### promo final — fin"
CREDITOS_INI = "### créditos de audio CC0 — inicio (lo reescribe scripts/promo.py audio)"
CREDITOS_FIN = "### créditos de audio CC0 — fin"
LIMITE_CORREO = 25_000_000      # bytes: Gmail admite 25 MB por correo (guía §11)


# ---------------------------------------------------------------- proyecto
class Proyecto:
    """Rutas del contrato de carpetas (AGENT §13 + motor promo)."""

    def __init__(self, carpeta):
        self.dir = os.path.abspath(carpeta)
        self.nombre = os.path.basename(self.dir)
        self.slug = re.sub(r"_\d{8}$", "", self.nombre)
        self.promo = os.path.join(self.dir, "promo.json")
        self.rec = os.path.join(self.dir, "recursos")
        self.lt = os.path.join(self.rec, "promo", "linea_tiempo.json")
        self.validacion = os.path.join(self.rec, "promo", "validacion.json")
        self.cuadros = os.path.join(self.rec, "cuadros")
        self.render_dir = os.path.join(self.rec, "render")
        self.video_mudo = os.path.join(self.render_dir, "video_mudo.mp4")
        self.render_log = os.path.join(self.render_dir, "render.log")
        self.render_pid = os.path.join(self.render_dir, "render.pid")
        self.render_json = os.path.join(self.render_dir, "render.json")
        self.audio_dir = os.path.join(self.rec, "audio")
        self.mezcla = os.path.join(self.audio_dir, "mezcla.wav")
        self.costos = os.path.join(self.rec, "costos.jsonl")
        self.info = os.path.join(self.dir, "info.txt")
        self.tiempos_voz = os.path.join(self.rec, "voz", "tiempos.json")
        self.creditos = os.path.join(self.audio_dir, "cc0", "creditos.json")

    def leer_lt(self):
        with open(self.lt, encoding="utf-8") as f:
            return json.load(f)

    def video_render(self):
        """(ruta, borrador) del último render exitoso según render.json; si no hay, video_mudo.mp4.
        Con --borrador el motor escribe video_borrador.mp4, así que la ruta no es fija."""
        try:
            with open(self.render_json, encoding="utf-8") as f:
                r = json.load(f)
            if r.get("codigo") == 0 and r.get("video") and os.path.exists(r["video"]):
                return r["video"], bool(r.get("borrador"))
        except (OSError, json.JSONDecodeError):
            pass
        return self.video_mudo, False

    def salida_final(self, lt=None):
        lt = lt or (self.leer_lt() if os.path.exists(self.lt) else {})
        return os.path.join(self.dir, lt.get("archivo_salida") or f"{self.slug}.mp4")

    def portada(self):
        return os.path.join(self.dir, f"{self.slug}_portada.jpg")

    def srt(self):
        return os.path.join(self.dir, f"{self.slug}.srt")

    def correo(self):
        return os.path.join(self.dir, f"{self.slug}_correo.mp4")

    def rel(self, ruta):
        return os.path.relpath(ruta, self.dir) if ruta else "-"


def ruta_cmd(ruta):
    """Ruta para pegar en un comando corrido desde la raíz del repo (relativa si cae dentro)."""
    ruta = os.path.abspath(ruta)
    return os.path.relpath(ruta, REPO) if ruta.startswith(REPO + os.sep) else ruta


def costos_cmd(p):
    log = ruta_cmd(p.costos)
    return (f"python3 scripts/costo_sesion_hermes.py --log {log} && "
            f"python3 scripts/costo_generacion.py --log {log}")


def raiz_proyectos(a):
    return os.path.join(os.path.abspath(a.raiz or os.environ.get("PROMO_RAIZ") or REPO), "proyectos")


def _fecha_nombre(nombre):
    m = re.search(r"_(\d{2})(\d{2})(\d{4})$", nombre)
    return (m.group(3) + m.group(2) + m.group(1)) if m else ""


def resolver_proyecto(ref, a):
    """Ruta existente, nombre exacto, slug exacto (el más reciente) o prefijo único.

    Un nombre SIN separador se busca primero en proyectos/: un slug como "promo" o "docs" no debe
    resolverse a la carpeta homónima del repo (el motor, la documentación…)."""
    es_ruta = os.sep in ref or ref.startswith(".") or os.path.isfile(os.path.join(ref, "promo.json"))
    if es_ruta and os.path.isdir(ref):
        return Proyecto(ref)
    base = raiz_proyectos(a)
    dirs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))) \
        if os.path.isdir(base) else []
    if ref in dirs:
        return Proyecto(os.path.join(base, ref))
    mismos = [d for d in dirs if re.sub(r"_\d{8}$", "", d) == ref]
    if mismos:
        return Proyecto(os.path.join(base, max(mismos, key=_fecha_nombre)))
    pref = [d for d in dirs if d.startswith(ref)]
    if len(pref) == 1:
        return Proyecto(os.path.join(base, pref[0]))
    if pref:
        print(f"ERROR proyecto ambiguo '{ref}': {', '.join(pref[:5])}. Usa el nombre completo.")
    else:
        print(f"ERROR no existe el proyecto '{ref}' en {base}. Crea uno: python3 scripts/promo.py nuevo <slug>")
    raise SystemExit(2)


def huella(ruta):
    """sha1 del contenido: validar puede reescribir la línea de tiempo sin cambiarla, y por
    mtime eso marcaría como viejo un render de 5 minutos que sigue siendo válido."""
    try:
        with open(ruta, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return None


def sellar(artefacto, lt_huella):
    with open(artefacto + ".huella", "w", encoding="utf-8") as f:
        f.write(lt_huella or "")


def vigente(artefacto, p):
    """'falta' | 'viejo' | 'ok' respecto de la línea de tiempo (sello de huella o, sin sello, mtime)."""
    if not artefacto or not os.path.exists(artefacto):
        return "falta"
    sello = artefacto + ".huella"
    if os.path.exists(sello) and os.path.exists(p.lt):
        with open(sello, encoding="utf-8") as f:
            return "ok" if f.read().strip() == huella(p.lt) else "viejo"
    if os.path.exists(p.lt) and os.path.getmtime(artefacto) < os.path.getmtime(p.lt):
        return "viejo"
    return "ok"


# ---------------------------------------------------------------- motor Node
def ruta_motor():
    return os.environ.get("PROMO_MOTOR") or os.path.join(REPO, "promo", "motor.mjs")


def _json_de(texto):
    """El motor imprime exactamente un objeto JSON en stdout; se tolera ruido previo."""
    texto = (texto or "").strip()
    for candidato in [texto] + texto.splitlines()[::-1]:
        try:
            obj = json.loads(candidato)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def correr_motor(cmd, proyecto_dir, extra=(), verbose=False, al_avance=None):
    """Corre `node promo/motor.mjs <cmd>` y devuelve (código, objeto JSON | None, cola de stderr)."""
    motor = ruta_motor()
    if not os.path.exists(motor):
        print(f"ERROR entorno: falta el motor Node ({motor}). ¿Repo incompleto? Actualiza el repo.")
        raise SystemExit(3)
    node = comun.buscar_node(REPO)
    args = [node, motor, cmd] + (["--proyecto", proyecto_dir] if proyecto_dir else []) + [str(x) for x in extra]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                         text=True, bufsize=1, cwd=REPO)
    salida = []
    hilo = threading.Thread(target=lambda: salida.append(p.stdout.read()), daemon=True)
    hilo.start()
    cola = []
    for linea in p.stderr:
        cola = (cola + [linea.rstrip()])[-40:]
        if verbose:
            print(linea, end="", file=sys.stderr, flush=True)
        if al_avance and "avance" in linea:
            al_avance(linea.strip())
    p.wait()
    hilo.join(timeout=10)
    obj = _json_de("".join(salida))
    codigo = p.returncode
    if obj is None:
        print(f"ERROR motor: `{cmd}` no devolvió JSON (código {codigo}). Últimas líneas:")
        for l in cola[-3:]:
            print("  " + l[:200])
        codigo = codigo or 1
    return codigo, obj, cola


def linea_issue(i):
    t = f" (t={i['t']})" if i.get("t") is not None else ""
    arreglo = f" {i['arreglo']}" if i.get("arreglo") else ""
    return f"{i.get('codigo', '?')}  {i.get('ruta', '-')}: {i.get('msg', '')}{arreglo}{t}"


def imprimir_issues(obj, limite=4):
    issues = (obj or {}).get("errores") or []
    for i in issues[:limite]:
        print(linea_issue(i))
    if len(issues) > limite:
        print(f"… y {len(issues) - limite} más")


def siguiente_fallo(codigo, p, etapa):
    """Qué hacer según el código de salida (contrato con el motor Node)."""
    if codigo == 2:
        return f"Siguiente: corrige promo.json y corre python3 scripts/promo.py validar {p.nombre}"
    if codigo == 3:
        return "Siguiente: problema de entorno; pregunta al usuario (zsh scripts/preflight.sh)."
    if codigo == 4:
        return f"Siguiente: falló una API externa; reintenta UNA vez: python3 scripts/promo.py {etapa} {p.nombre}"
    return f"Siguiente: error interno; repórtalo al usuario (detalle: python3 scripts/promo.py {etapa} {p.nombre} --verbose)"


def _plural(n, s, pl):
    return f"{n} {s if n == 1 else pl}"


# ---------------------------------------------------------------- etapas
def ejemplos_disponibles():
    base = os.path.join(REPO, "promo", "ejemplos")
    return sorted(d for d in os.listdir(base) if os.path.exists(os.path.join(base, d, "promo.json"))) \
        if os.path.isdir(base) else []


def etapa_nuevo(a):
    slug = a.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 60:
        print(f"ERROR slug inválido '{a.slug}': usa minúsculas, números y guiones (p. ej. promo-asistente-ia).")
        return 2
    hoy = datetime.date.today()
    p = Proyecto(os.path.join(raiz_proyectos(a), f"{slug}_{hoy.strftime('%d%m%Y')}"))
    if os.path.exists(p.dir):
        print(f"ERROR ya existe {p.dir}. Usa ese proyecto o elige otro slug.")
        return 2
    # El ejemplo se resuelve ANTES de crear carpetas: un nombre equivocado no deja un proyecto vacío.
    ejemplo = os.path.join(REPO, "promo", "ejemplos", a.ejemplo, "promo.json")
    disponibles = ejemplos_disponibles()
    if os.path.exists(ejemplo):
        with open(ejemplo, encoding="utf-8") as f:
            texto = f.read()
        # El nombre de la entrega es del proyecto, no del ejemplo (se reemplaza en el texto
        # para conservar el formato y los comentarios del ejemplo).
        viejo = (json.loads(texto).get("salida") or {}).get("archivo")
        if viejo:
            texto = texto.replace(json.dumps(viejo), json.dumps(f"{slug}.mp4"), 1)
        origen = f"ejemplo {a.ejemplo}"
    elif disponibles:
        print(f"ERROR no existe el ejemplo '{a.ejemplo}'. Disponibles: {', '.join(disponibles)}")
        return 2
    else:                                   # repo sin ejemplos: plantilla mínima
        texto = json.dumps({"version": 1, "formato": "promo_ui", "tema": "neutro", "escenas": []},
                           indent=2, ensure_ascii=False) + "\n"
        origen = "plantilla mínima (no hay ejemplos en promo/ejemplos/)"
    for d in (os.path.join(p.rec, "promo"), p.cuadros, p.render_dir, p.audio_dir):
        os.makedirs(d, exist_ok=True)
    with open(p.promo, "w", encoding="utf-8") as f:
        f.write(texto)
    with open(os.path.join(p.dir, "brief.md"), "w", encoding="utf-8") as f:
        f.write(PLANTILLA_BRIEF.format(slug=slug))
    with open(p.info, "w", encoding="utf-8") as f:
        f.write(PLANTILLA_INFO.format(slug=slug, fecha=hoy.strftime("%d/%m/%Y"), nombre=p.nombre))
    print(f"nuevo: {ruta_cmd(p.dir)}/ · promo.json desde {origen}")
    print(f"Siguiente: llena brief.md (hechos con fuente), edita promo.json y corre: "
          f"python3 scripts/promo.py validar {p.nombre}")
    return 0


def etapa_validar(a, p, siguiente=True):
    codigo, obj, _ = correr_motor("validar", p.dir, verbose=a.verbose)
    p.ultima_validacion = obj
    if obj is None:
        return codigo
    errs, avis = obj.get("errores") or [], obj.get("avisos") or []
    r = obj.get("resumen") or {}
    extra = ""
    if r.get("total") is not None:
        extra = f" · {r['total']:.1f} s, {r.get('cuadros', '?')} cuadros, {len(r.get('escenas') or [])} escenas"
    print(f"promo validar · {p.nombre} — {_plural(len(errs), 'error', 'errores')}, "
          f"{_plural(len(avis), 'aviso', 'avisos')}{extra}")
    todos = errs + avis
    for i in todos[:MAX_ISSUES]:
        print(linea_issue(i))
    if len(todos) > MAX_ISSUES:
        print(f"… y {len(todos) - MAX_ISSUES} más en recursos/promo/validacion.json")
    if siguiente or codigo:
        sig = "cuadros"
        if codigo == 0 and os.path.exists(p.lt) and (p.leer_lt().get("voz") or {}).get("pendiente"):
            sig = "voz"                          # primero las tomas reales; luego validar otra vez
        print(f"Siguiente: python3 scripts/promo.py {sig} {p.nombre}" if codigo == 0
              else siguiente_fallo(codigo, p, "validar"))
    return codigo


def etapa_cuadros(a, p, siguiente=True):
    extra = []
    if getattr(a, "t", None):
        extra += ["--t", a.t]
    if getattr(a, "ref", None):
        extra += ["--ref", os.path.abspath(a.ref)]
    lt_h = huella(p.lt)
    codigo, obj, _ = correr_motor("cuadros", p.dir, extra, verbose=a.verbose)
    if codigo != 0 or not obj:
        imprimir_issues(obj)
        print(siguiente_fallo(codigo or 1, p, "cuadros"))
        return codigo or 1
    if obj.get("hoja") and os.path.exists(obj["hoja"]):
        sellar(obj["hoja"], huella(p.lt) or lt_h)
    print(f"cuadros: {len(obj.get('cuadros') or [])} png · hoja: {p.rel(obj.get('hoja'))}")
    if siguiente:
        print(f"Siguiente: muestra la hoja al usuario (la QA del DOM ya revisó); si está bien: "
              f"python3 scripts/promo.py render {p.nombre} --fondo")
    return 0


def _args_render(a):
    cfg = comun.cargar_config(REPO).get("promo") or {}
    extra = ["--borrador"] if getattr(a, "borrador", False) else []
    return extra + ["--workers", str(getattr(a, "workers", None) or cfg.get("workers", 3))]


def _avance_tty():
    """Imprime el avance en pasos de 10 % solo en terminal (a un agente no le sirve el stream)."""
    vistos = set()

    def f(linea):
        m = re.search(r"avance\s+(\d+)%", linea)
        if m and sys.stdout.isatty() and int(m.group(1)) // 10 not in vistos:
            vistos.add(int(m.group(1)) // 10)
            print("  " + linea, flush=True)
    return f


def etapa_render(a, p, siguiente=True):
    os.makedirs(p.render_dir, exist_ok=True)
    if getattr(a, "fondo", False):
        en_curso, avance, _ = _render_en_curso(p)
        if en_curso:                         # no lanzar dos renders sobre la misma carpeta
            print(f"ya hay un render en curso ({avance or 'arrancando'}). "
                  f"Siguiente: python3 scripts/promo.py estado {p.nombre}")
            return 0
        # Semántica de `nohup … > log 2>&1 < /dev/null &`: sesión nueva, sin stdin y TODA la
        # salida al log; si no, la herramienta del agente se queda esperando hasta su límite.
        # El proceso desprendido es este mismo script en primer plano (con --verbose para que
        # el avance de Node quede en el log) para que al terminar selle la huella y el JSON.
        cmd = [sys.executable, "-u", os.path.abspath(__file__), "render", p.dir, "--verbose"] + \
              (["--borrador"] if a.borrador else []) + (["--workers", str(a.workers)] if a.workers else [])
        if a.raiz:
            cmd += ["--raiz", a.raiz]
        if os.path.exists(p.render_json):
            os.remove(p.render_json)
        with open(p.render_log, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, cwd=REPO)
        with open(p.render_pid, "w", encoding="utf-8") as f:
            f.write(f"{proc.pid}\n{time.time():.0f}\n")
        print(f"render en segundo plano (pid {proc.pid}) · log: {p.rel(p.render_log)}")
        print(f"Siguiente: python3 scripts/promo.py audio {p.nombre}  (mientras renderiza); "
              f"avance: python3 scripts/promo.py estado {p.nombre}")
        return 0
    lt_h = huella(p.lt)
    codigo, obj, _ = correr_motor("render", p.dir, _args_render(a), verbose=a.verbose, al_avance=_avance_tty())
    with open(p.render_json, "w", encoding="utf-8") as f:
        json.dump({"codigo": codigo, **(obj or {})}, f, ensure_ascii=False)
    if codigo != 0 or not obj:
        imprimir_issues(obj)
        print(siguiente_fallo(codigo or 1, p, "render"))
        return codigo or 1
    video = obj.get("video") or p.video_mudo
    if os.path.exists(video):
        sellar(video, lt_h)
    print(f"render: {p.rel(video)} · {obj.get('cuadros', '?')} cuadros · {obj.get('segundos', 0):.0f} s")
    if siguiente:
        sig = "final" if vigente(p.mezcla, p) == "ok" else "audio"
        print(f"Siguiente: python3 scripts/promo.py {sig} {p.nombre}")
    return 0


def _lt_lista(p, revisar_voz=True):
    """Verifica que exista una línea de tiempo vigente y sin errores; si no, dice qué correr.
    Con `revisar_voz`, también que se haya re-validado después de la última `voz` (las tomas
    reales cambian la duración de las escenas)."""
    if not os.path.exists(p.lt) or (os.path.exists(p.promo) and
                                    os.path.getmtime(p.lt) < os.path.getmtime(p.promo)):
        print(f"ERROR la línea de tiempo falta o es más vieja que promo.json. "
              f"Siguiente: python3 scripts/promo.py validar {p.nombre}")
        return False
    if revisar_voz and os.path.exists(p.tiempos_voz) and os.path.getmtime(p.tiempos_voz) > os.path.getmtime(p.lt):
        print(f"ERROR la voz cambió después de validar. Siguiente: python3 scripts/promo.py validar {p.nombre}")
        return False
    if os.path.exists(p.validacion):
        try:
            with open(p.validacion, encoding="utf-8") as f:
                if json.load(f).get("ok") is False:
                    print(f"ERROR la última validación tiene errores. "
                          f"Siguiente: corrige promo.json y corre python3 scripts/promo.py validar {p.nombre}")
                    return False
        except (OSError, json.JSONDecodeError):
            pass
    return True


def etapa_voz(a, p, siguiente=True):
    """TTS de los subtitulo (solo si promo.json trae audio.voz) → recursos/voz/tiempos.json."""
    if not _lt_lista(p, revisar_voz=False):
        return 2
    lt = p.leer_lt()
    if not (lt.get("audio") or {}).get("voz"):
        print("ERROR este proyecto no pide voz (audio.voz es null). La voz en off es opcional: "
              "solo si el usuario la pide.")
        return 2
    try:
        r = voz.generar_voz(p.rec, lt, REPO, verificar=not getattr(a, "sin_verificar", False))
    except voz.ErrorEntornoVoz as e:
        print(f"ERROR entorno: {e}")
        print(siguiente_fallo(3, p, "voz"))
        return 3
    except voz.ErrorTTS as e:
        print(f"ERROR {e}")
        print(siguiente_fallo(4, p, "voz"))
        return 4
    errs = [i for i in r["issues"] if i["severidad"] == "E"]
    avis = [i for i in r["issues"] if i["severidad"] != "E"]
    print(f"promo voz · {p.nombre} — {r['lineas']} líneas ({r['nuevas']} nuevas, {r['cache']} en caché) · "
          f"{r['total']:.1f} s de voz · {_plural(len(errs), 'error', 'errores')}, {_plural(len(avis), 'aviso', 'avisos')}")
    for i in (errs + avis)[:MAX_ISSUES]:
        print(linea_issue(i))
    if siguiente or r["codigo"]:
        print(f"Siguiente: python3 scripts/promo.py validar {p.nombre}  (re-planea con la duración real)"
              if r["codigo"] == 0 else siguiente_fallo(r["codigo"], p, "voz"))
    return r["codigo"]


def etapa_audio(a, p, siguiente=True, tp=None, imprimir=True):
    if not _lt_lista(p):
        return 2
    lt = p.leer_lt()
    if (lt.get("audio") or {}).get("voz") and (lt.get("voz") or {}).get("pendiente", True):
        print(f"ERROR la voz está pendiente (faltan tomas). Siguiente: python3 scripts/promo.py voz {p.nombre}")
        return 2
    lt_h = huella(p.lt)
    res = sonido.generar_audio(p.lt, p.mezcla, REPO, tp=tp, imprimir=imprimir,
                               refrescar_cc0=getattr(a, "refrescar_cc0", False))
    actualizar_creditos(p, res.get("creditos") or [])
    sellar(p.mezcla, lt_h)
    if siguiente:
        sig = "final" if vigente(p.video_render()[0], p) == "ok" else "render"
        print(f"Siguiente: python3 scripts/promo.py {sig} {p.nombre}" + (" --fondo" if sig == "render" else ""))
    return 0


# ---------------------------------------------------------------- final: mux + checks
def sondear(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
                        "stream=codec_type,codec_name,nb_read_packets,duration,pix_fmt,width,height,"
                        "color_primaries,color_transfer,color_space:format=duration",
                        "-of", "json", ruta], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    return v, float((d.get("format") or {}).get("duration") or 0)


def _color_ok(v):
    return (v.get("pix_fmt") == "yuv420p" and v.get("color_primaries") == "bt709"
            and v.get("color_transfer") == "bt709" and v.get("color_space") == "bt709")


def mux(p, video, salida):
    """Video mudo (copia) + mezcla → AAC 256k. Si al h264 le faltan etiquetas bt709, se agregan
    con el bsf h264_metadata (reescribe el VUI del SPS sin recodificar)."""
    v, _ = sondear(video)
    bsf = []
    if not _color_ok(v) and v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p":
        bsf = ["-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1"]
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", video, "-i", p.mezcla,
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"] + bsf +
              ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", salida])
    return bool(bsf)


def verificar(salida, lt, lufs, silencio=False):
    """Checks de entrega (guía §10): cuadros, duración ±1 cuadro, color, sonoridad post-AAC."""
    v, dur_fmt = sondear(salida)
    total, fps = float(lt["total"]), float(lt.get("fps", 30))
    tol = 1.0 / fps + 1e-3
    fallas = []
    cuadros = int(v.get("nb_read_packets") or 0)
    if cuadros != int(lt["cuadros"]):
        fallas.append(f"cuadros {cuadros}≠{lt['cuadros']}")
    dur_v = float(v.get("duration") or dur_fmt)
    for nombre, d in (("video", dur_v), ("contenedor", dur_fmt)):
        if abs(d - total) > tol:
            fallas.append(f"duración {nombre} {d:.3f}≠{total:.3f}")
    if not _color_ok(v):
        fallas.append(f"color {v.get('pix_fmt')}/{v.get('color_primaries', '?')}/"
                      f"{v.get('color_transfer', '?')}/{v.get('color_space', '?')}")
    med = comun.ebur128(salida)
    if not silencio:
        if abs(med["I"] - lufs) > 0.5:
            fallas.append(f"sonoridad {med['I']:.1f} LUFS (objetivo {lufs:g}±0.5)")
        if med["TP"] > -1.0:
            fallas.append(f"true peak {med['TP']:.1f} dBTP (>-1.0)")
    return {"fallas": fallas, "cuadros": cuadros, "duracion": dur_v, "I": med["I"], "TP": med["TP"],
            "LRA": med.get("LRA", 0.0), "w": v.get("width"), "h": v.get("height")}


def actualizar_info(p, bloque, marca_ini=MARCA_INI, marca_fin=MARCA_FIN):
    """Reemplaza (o agrega) un bloque de info.txt entre marcas; bloque vacío = lo quita."""
    previo = ""
    if os.path.exists(p.info):
        with open(p.info, encoding="utf-8") as f:
            previo = f.read()
    nuevo = f"{marca_ini}\n{bloque.rstrip()}\n{marca_fin}\n" if bloque else ""
    if marca_ini in previo and marca_fin in previo:
        ini, fin = previo.index(marca_ini), previo.index(marca_fin) + len(marca_fin)
        texto = previo[:ini] + nuevo.rstrip("\n") + previo[fin:]
    elif nuevo:
        texto = previo.rstrip("\n") + ("\n\n" if previo else "") + nuevo
    else:
        return
    with open(p.info, "w", encoding="utf-8") as f:
        f.write(texto.rstrip("\n") + "\n")


def actualizar_creditos(p, creditos):
    """Créditos CC0 en info.txt. CC0 no exige atribución, pero la trazabilidad es obligatoria:
    título, autor, licencia, URL de origen y sha256 de cada archivo usado."""
    lineas = ["CC0 1.0 (sin atribución obligatoria); se registra el origen de cada sonido."]
    for c in creditos:
        lineas.append(f"- {c.get('uso')}: {c.get('archivo')} · «{c.get('titulo')}» · {c.get('autor')} · "
                      f"{c.get('licencia')} · {c.get('origen_url')} · sha256 {str(c.get('sha256'))[:16]}")
    actualizar_info(p, "\n".join(lineas) if creditos else "", CREDITOS_INI, CREDITOS_FIN)


def escribir_srt(p, lt):
    """Subtítulos de la voz en off: una entrada por línea hablada (en → en+dur)."""
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    lineas = sorted((lt.get("voz") or {}).get("lineas") or [], key=lambda l: float(l["en"]))
    with open(p.srt(), "w", encoding="utf-8") as f:
        for k, l in enumerate(lineas, 1):
            f.write(f"{k}\n{ts(float(l['en']))} --> {ts(float(l['en']) + float(l['dur']))}\n"
                    f"{l['texto'].replace('*', '')}\n\n")
    return p.srt()


def version_correo(p, salida, lt):
    """Versión para correo (guía §11): x264 en 2 pasadas ~3.9 Mbps con hqdn3d (el grano del máster
    infla el peso), AAC 160k. Para piezas largas el bitrate baja lo necesario para quedar < 25 MB."""
    total = float(lt["total"])
    kbps = max(600, min(3900, int(0.92 * LIMITE_CORREO * 8 / total / 1000) - 160))
    correo, log = p.correo(), os.path.join(p.render_dir, "_correo")
    base = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", salida, "-vf", "hqdn3d", "-c:v", "libx264",
            "-preset", "medium", "-b:v", f"{kbps}k", "-pix_fmt", "yuv420p", "-passlogfile", log]
    comun.run(base + ["-pass", "1", "-an", "-f", "null", "-"])
    comun.run(base + ["-pass", "2", "-bsf:v",
                      "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
                      "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", correo])
    for f in glob.glob(log + "*"):
        os.remove(f)
    return correo, os.path.getsize(correo), kbps


def etapa_final(a, p, siguiente=True):
    if not _lt_lista(p):
        return 2
    lt = p.leer_lt()
    video, borrador = p.video_render()
    if vigente(video, p) != "ok":
        print(f"ERROR el video mudo {vigente(video, p)}. "
              f"Siguiente: python3 scripts/promo.py render {p.nombre} --fondo")
        return 2
    notas = []
    if vigente(p.mezcla, p) != "ok":                 # el audio es barato: se regenera solo
        codigo = etapa_audio(a, p, siguiente=False, imprimir=False)
        if codigo:
            return codigo
        notas.append("mezcla regenerada")
    cfg = (comun.cargar_config(REPO).get("promo") or {}).get("mezcla") or {}
    lufs = float(cfg.get("lufs", -14))
    audio = lt.get("audio") or {}
    # Sin música ni voz la mezcla no se sube a -14 LUFS (solo se limita): no aplica el check de I.
    silencio = (audio.get("musica") or {}).get("tipo") == "ninguna" and not audio.get("voz")
    salida = p.salida_final(lt)
    color_fix = mux(p, video, salida)
    chk = verificar(salida, lt, lufs, silencio)
    if not silencio and chk["TP"] > -1.0:
        # El AAC suele subir el true peak ~0.5–1 dB: se rehace la mezcla con más margen, una vez.
        etapa_audio(a, p, siguiente=False, tp=-2.0, imprimir=False)
        mux(p, video, salida)
        chk = verificar(salida, lt, lufs, silencio)
        notas.append("mezcla rehecha a -2.0 dBTP por el AAC")
    if color_fix:
        notas.append("etiquetas bt709 agregadas (h264_metadata)")
    if borrador:
        notas.append("BORRADOR (render --borrador)")
    portada = p.portada()
    t_port = min(max(0.0, float(lt.get("portada", 0.0))), float(lt["total"]) - 1.0 / float(lt.get("fps", 30)))
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", f"{t_port:.3f}", "-i", salida,
               "-frames:v", "1", "-q:v", "2", portada])
    srt = escribir_srt(p, lt) if audio.get("voz") else None
    correo, peso, kbps = version_correo(p, salida, lt)
    if peso >= LIMITE_CORREO:
        chk["fallas"].append(f"correo {peso / 1e6:.1f} MB (≥ 25 MB)")
    if os.path.exists(p.creditos):
        with open(p.creditos, encoding="utf-8") as f:
            actualizar_creditos(p, json.load(f))
    mus = audio.get("musica") or {}
    estado_chk = "ok" if not chk["fallas"] else "FALLAN: " + "; ".join(chk["fallas"])
    costos = costos_cmd(p).replace(" && ", "\n        ")
    actualizar_info(p, "\n".join([
        f"FECHA: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"ENTREGA: {os.path.basename(salida)} · portada: {os.path.basename(portada)} (t={t_port:.2f} s)"
        + (f" · subtítulos: {os.path.basename(srt)}" if srt else ""),
        f"CORREO: {os.path.basename(correo)} · {peso / 1e6:.1f} MB · {kbps} kbps video + AAC 160k (2 pasadas, hqdn3d)",
        f"DURACIÓN: {chk['duracion']:.3f} s · {chk['cuadros']} cuadros @ {lt.get('fps', 30)} fps · "
        f"{chk['w']}x{chk['h']}",
        f"AUDIO: {chk['I']:.1f} LUFS integrados · {chk['TP']:.1f} dBTP · LRA {chk['LRA']:.1f} LU (AAC 256k)",
        f"MÚSICA: {mus.get('tipo', 'procedural')} · SFX: {audio.get('sfx', 'sutil')} "
        f"({len(lt.get('cues') or [])} cues, {audio.get('sfx_fuente', 'procedural')})"
        + (f" · VOZ: {audio['voz'].get('voz', 'coral')} ({len((lt.get('voz') or {}).get('lineas') or [])} líneas)"
           if audio.get("voz") else ""),
        f"CHECKS: {estado_chk}" + (f" · {'; '.join(notas)}" if notas else ""),
        f"ARCHIVOS: {p.rel(video)}, {p.rel(p.mezcla)}, {p.rel(p.lt)}",
        f"COSTOS: {costos}",
    ]))
    print(f"final: {os.path.basename(salida)} · {chk['duracion']:.3f} s · {chk['cuadros']} cuadros · "
          f"{chk['I']:.1f} LUFS / {chk['TP']:.1f} dBTP")
    print(f"portada: {os.path.basename(portada)} (t={t_port:.2f} s)" + (f" · srt: {os.path.basename(srt)}" if srt else "")
          + " · info.txt actualizado")
    print(f"correo: {os.path.basename(correo)} · {peso / 1e6:.1f} MB ({kbps} kbps + AAC 160k)")
    print(f"checks: {estado_chk}" + (f" · {'; '.join(notas)}" if notas else ""))
    if siguiente:
        print(f"Costos: {costos_cmd(p)}")
        print("Siguiente: reporta al usuario (entrega, costos) y el aprendizaje continuo (AGENT §15)."
              if not chk["fallas"] else "Siguiente: revisa las fallas antes de entregar.")
    return 0 if not chk["fallas"] else 1


# ---------------------------------------------------------------- todo / estado / ayuda
def etapa_todo(a, p):
    codigo = etapa_validar(a, p, siguiente=False)        # si falla ya imprime su Siguiente
    if codigo:
        return codigo
    if (p.leer_lt().get("audio") or {}).get("voz"):
        # Voz en off: las tomas reales definen la duración de las escenas → validar otra vez.
        codigo = etapa_voz(a, p, siguiente=False)
        if codigo:
            return codigo
        codigo = etapa_validar(a, p, siguiente=False)
        tiempo = [i for i in (getattr(p, "ultima_validacion", None) or {}).get("errores") or []
                  if str(i.get("codigo", "")).startswith("E-TIEMPO")]
        if tiempo:
            print("Siguiente: la voz real no cabe en la duración: sube salida.duracion o acorta los "
                  f"subtitulo, y repite: python3 scripts/promo.py todo {p.nombre}")
            return 2
        if codigo:
            return codigo
        if (p.leer_lt().get("voz") or {}).get("pendiente", True):
            print(f"ERROR la voz sigue pendiente tras validar (¿cambió el texto?). "
                  f"Siguiente: python3 scripts/promo.py voz {p.nombre}")
            return 2
    codigo = etapa_cuadros(a, p, siguiente=False)
    if codigo:
        return codigo
    # Render (Node, minutos) ∥ audio (FFmpeg, segundos): el render corre en un hilo y el
    # audio en este proceso; ambos solo leen la línea de tiempo.
    res = {}
    a.fondo = False

    def render():
        try:
            res["r"] = etapa_render(a, p, siguiente=False)
        except SystemExit as e:              # en un hilo SystemExit se perdería en silencio
            res["r"] = e.code if isinstance(e.code, int) else 1
    hilo = threading.Thread(target=render)
    hilo.start()
    try:
        codigo_audio = etapa_audio(a, p, siguiente=False)
    except SystemExit as e:
        codigo_audio = e.code if isinstance(e.code, int) else 1
    hilo.join()                              # nunca dejar el render huérfano
    if res.get("r"):
        return res["r"]                      # etapa_render ya imprimió su Siguiente
    if codigo_audio:
        print(siguiente_fallo(codigo_audio, p, "audio"))
        return codigo_audio
    return etapa_final(a, p)


def _render_en_curso(p):
    """(en_curso, último avance, error) a partir del pid, el log y render.json."""
    avance, error = None, None
    if os.path.exists(p.render_log):
        with open(p.render_log, encoding="utf-8", errors="replace") as f:
            lineas = f.read().splitlines()
        for l in reversed(lineas):
            if re.search(r"avance\s+\d+%", l):
                avance = l.strip()
                break
    if os.path.exists(p.render_json):
        try:
            with open(p.render_json, encoding="utf-8") as f:
                r = json.load(f)
            if r.get("codigo"):
                e = (r.get("errores") or [{}])[0]
                error = f"{e.get('codigo', 'E')} {e.get('msg', '')}"[:160]
        except (OSError, json.JSONDecodeError):
            pass
        return False, avance, error
    if os.path.exists(p.render_pid):
        with open(p.render_pid, encoding="utf-8") as f:
            pid = int((f.readline() or "0").strip() or 0)
        try:
            os.kill(pid, 0)
            return True, avance, None
        except (OSError, ValueError):
            return False, avance, "el render se detuvo sin resultado (revisa render.log)"
    return False, avance, None


def siguiente_comando(p, est, en_curso):
    n = p.nombre
    if est["promo"] == "falta":
        return f"crea promo.json (copia promo/ejemplos/{EJEMPLO_DEF}/promo.json) y valida"
    if est["linea_tiempo"] in ("falta", "viejo"):
        return f"python3 scripts/promo.py validar {n}"
    if est["linea_tiempo"] == "con errores":
        return f"corrige promo.json y corre python3 scripts/promo.py validar {n}"
    if est.get("voz") == "pendiente":
        return f"python3 scripts/promo.py voz {n}"
    if est["cuadros"] != "ok" and not en_curso and not est["video_mudo"].startswith("ok"):
        return f"python3 scripts/promo.py cuadros {n}"
    if en_curso:
        return (f"python3 scripts/promo.py audio {n}  (el render sigue)" if est["mezcla"] != "ok"
                else f"espera el render: python3 scripts/promo.py estado {n}")
    if not est["video_mudo"].startswith("ok"):
        return f"python3 scripts/promo.py render {n} --fondo"
    if est["mezcla"] != "ok":
        return f"python3 scripts/promo.py audio {n}"
    if est["final"] != "ok":
        return f"python3 scripts/promo.py final {n}"
    return f"listo; costos: {costos_cmd(p)}"


def etapa_estado(a, p):
    est = {"promo": "ok" if os.path.exists(p.promo) else "falta"}
    lt = "falta"
    if os.path.exists(p.lt):
        lt = "viejo" if (os.path.exists(p.promo) and os.path.getmtime(p.lt) < os.path.getmtime(p.promo)) else "ok"
        if lt == "ok" and os.path.exists(p.validacion):
            try:
                with open(p.validacion, encoding="utf-8") as f:
                    if json.load(f).get("ok") is False:
                        lt = "con errores"
            except (OSError, json.JSONDecodeError):
                pass
    lt_obj = p.leer_lt() if os.path.exists(p.lt) else {}
    if (lt_obj.get("audio") or {}).get("voz"):
        est["voz"] = "pendiente" if (lt_obj.get("voz") or {}).get("pendiente", True) else "ok"
        if lt == "ok" and os.path.exists(p.tiempos_voz) and os.path.getmtime(p.tiempos_voz) > os.path.getmtime(p.lt):
            lt = "viejo"
    est["linea_tiempo"] = lt
    hojas = sorted(glob.glob(os.path.join(p.cuadros, "*.jpg")), key=os.path.getmtime)
    est["cuadros"] = vigente(hojas[-1], p) if hojas else "falta"
    en_curso, avance, error = _render_en_curso(p)
    video, borrador = p.video_render()
    est["video_mudo"] = "en curso" if en_curso else (vigente(video, p) + (" (borrador)" if borrador else ""))
    est["mezcla"] = vigente(p.mezcla, p)
    final = p.salida_final() if os.path.exists(p.lt) else None
    if final and os.path.exists(final):
        fuentes = [x for x in (video, p.mezcla) if os.path.exists(x)]
        est["final"] = "viejo" if any(os.path.getmtime(x) > os.path.getmtime(final) for x in fuentes) else "ok"
    else:
        est["final"] = "falta"
    print(f"estado · {p.nombre}")
    print(" · ".join(f"{k} {v}" for k, v in est.items()))
    if en_curso or error:
        print("render: " + ("en curso — " + (avance or "arrancando") if en_curso else f"FALLÓ — {error}"))
    elif avance and est["video_mudo"].startswith("ok"):
        print(f"render: terminado ({avance})")
    if final and est["final"] == "ok":
        print(f"entrega: {os.path.basename(final)} · portada: {os.path.basename(p.portada())}")
    print(f"Siguiente: {siguiente_comando(p, est, en_curso)}")
    return 0


USO = """Uso: python3 scripts/promo.py <etapa> <proyecto> [opciones]   (<proyecto> = ruta o slug)
  nuevo <slug> [--ejemplo NOMBRE]      crea proyectos/<slug>_<DDMMAAAA>/ (def. asistente-ia-cta-whatsapp; hay demo-10s)
  validar                              revisa promo.json y escribe la línea de tiempo
  voz [--sin-verificar]                solo con audio.voz: TTS de los subtitulo → recursos/voz/ (luego validar)
  cuadros [--t 1.2,3.4] [--ref mp4]    fotos de revisión + hoja de contactos (para el usuario)
  render [--borrador] [--workers N] [--fondo]   video mudo (--fondo: segundo plano, ver estado)
  audio [--refrescar-cc0]              música + SFX (+ voz) → mezcla -14 LUFS / -1.5 dBTP
  final                                mux + checks + portada + .srt (con voz) + versión correo + info.txt
  todo                                 validar [→ voz → validar] → cuadros → render ∥ audio → final
  estado                               qué falta o está viejo y el siguiente comando
Códigos: 0 ok · 1 fallo interno · 2 corrige promo.json/args · 3 entorno (pregunta) · 4 API (reintenta 1 vez)"""


def etapa_ayuda(a):
    print(USO)
    try:
        codigo, obj, _ = correr_motor("ayuda", None, verbose=a.verbose)
    except SystemExit:
        print("(catálogo no disponible: falta Node >= 20 o el motor; corre zsh scripts/preflight.sh)")
        return 0
    if codigo == 0 and obj and obj.get("texto"):
        print(obj["texto"])
    return 0


# ---------------------------------------------------------------- plantillas
PLANTILLA_BRIEF = """# Brief — {slug}

> Llénalo ANTES de escribir promo.json: todo lo que diga el video sale de aquí.
> Reglas de contenido: solo funciones publicadas, datos ilustrativos marcados como tales,
> calificaciones y precios con fecha, sonidos propios.

## Objetivo
-

## Público
-

## Mensaje clave
- (una frase)

## Hechos confirmados (con fuente)
| id | hecho | fuente (URL, documento o persona) | fecha |
|---|---|---|---|
| h1 |  |  |  |

## CTA y contacto
- CTA:
- Contacto (teléfono, sitio, app):

## Tono
-

## Duración/formato
- Duración objetivo (s): (30 recomendado; el motor ajusta las escenas solo)
- Relación: 9:16 vertical (la única que soporta el motor promo por ahora)

## Música
- procedural (default) | archivo: assets/musica/<pista> | cc0 (Openverse, docs/Audio-CC0.md) | ninguna
- Efectos (SFX): sutil (default) | normal | ninguno

## Voz en off (sí/no)
- no (default). Solo si el usuario la pide: se locuta el texto de los `subtitulo`
  (Fish TTS, lee al pie de la letra; frases con verbo, sin cifras ni preguntas).
"""

PLANTILLA_INFO = """PROYECTO: {slug}
FECHA: {fecha}
FORMATO: promo_ui (motor promo: HTML → cuadros → FFmpeg; scripts/promo.py)
ENTREGA: (pendiente: python3 scripts/promo.py final {nombre})

OBJETIVO Y DECISIONES
Ver brief.md. Anota aquí lo acordado con el usuario (orientación, música, SFX, voz).
"""


# ---------------------------------------------------------------- CLI
def construir_parser():
    ap = argparse.ArgumentParser(prog="promo.py", description="Motor de videos promo (etapas para el agente)")
    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--verbose", action="store_true", help="muestra el stderr de Node")
    comunes.add_argument("--raiz", help="carpeta que contiene proyectos/ (default: raíz del repo o $PROMO_RAIZ)")
    sub = ap.add_subparsers(dest="etapa", required=True, metavar="etapa")
    x = sub.add_parser("nuevo", parents=[comunes], help="crea proyectos/<slug>_<DDMMAAAA>/")
    x.add_argument("slug")
    x.add_argument("--ejemplo", default=EJEMPLO_DEF)
    for nombre in ("validar", "final", "estado"):
        sub.add_parser(nombre, parents=[comunes]).add_argument("proyecto")
    x = sub.add_parser("audio", parents=[comunes], help="música + SFX (+ voz) → recursos/audio/mezcla.wav")
    x.add_argument("proyecto")
    x.add_argument("--refrescar-cc0", action="store_true",
                   help="reintenta ya las búsquedas CC0 que dieron vacío (si no, se reintentan a las 24 h)")
    x = sub.add_parser("voz", parents=[comunes], help="TTS de los subtitulo (solo con audio.voz)")
    x.add_argument("proyecto")
    x.add_argument("--sin-verificar", action="store_true", help="no correr el diff dirigido de las tomas")
    x = sub.add_parser("cuadros", parents=[comunes])
    x.add_argument("proyecto")
    x.add_argument("--t", help="tiempos, p. ej. 1.2,3.4")
    x.add_argument("--ref", help="video de referencia para comparar")
    for nombre in ("render", "todo"):
        x = sub.add_parser(nombre, parents=[comunes])
        x.add_argument("proyecto")
        x.add_argument("--borrador", action="store_true")
        x.add_argument("--workers", type=int)
        if nombre == "render":
            x.add_argument("--fondo", action="store_true", help="desprende el render (log en recursos/render/)")
        else:
            x.add_argument("--sin-verificar", action="store_true", help="voz sin diff dirigido")
    sub.add_parser("ayuda", parents=[comunes])
    return ap


def main(argv=None):
    a = construir_parser().parse_args(argv)
    if a.etapa == "nuevo":
        return etapa_nuevo(a)
    if a.etapa == "ayuda":
        return etapa_ayuda(a)
    p = resolver_proyecto(a.proyecto, a)
    etapas = {"validar": etapa_validar, "voz": etapa_voz, "cuadros": etapa_cuadros, "render": etapa_render,
              "audio": etapa_audio, "final": etapa_final, "todo": etapa_todo, "estado": etapa_estado}
    return etapas[a.etapa](a, p)


if __name__ == "__main__":
    sys.exit(main())
