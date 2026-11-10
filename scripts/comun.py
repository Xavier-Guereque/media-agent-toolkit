#!/usr/bin/env python3
"""comun — utilidades compartidas por los scripts del toolkit (promo.py, sonido.py…).

Copiadas y adaptadas de scripts/reel.py (que se deja intacto): localizar la raíz del repo,
leer config/.env, correr FFmpeg con reporte de fallo, medir duración y sonoridad, normalizar
en dos pasadas, registrar costos y localizar un Node >= 20.

Solo librería estándar. Nunca imprime el contenido del .env.
"""
import datetime
import functools
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading

MARCADORES_RAIZ = (".env", "AGENT.md", ".git", ".env.example")
NODE_MINIMO = 20

# Windows: stdout/stderr en UTF-8 (por defecto usan cp1252 al ir a una tubería y los acentos de los reportes
# llegan rotos a quien los lea; los subprocesos del toolkit se leen con encoding="utf-8").
if os.name == "nt":
    for _flujo in (sys.stdout, sys.stderr):
        try:
            _flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------- repo y configuración
def raiz_repo(desde):
    """Sube desde `desde` hasta la raíz del toolkit (la carpeta con .env/AGENT.md/.git).

    Se busca por marcadores y no con `dirname` fijo porque los scripts se invocan desde
    proyectos/<slug>/ o desde scripts/, y el .env siempre vive en la raíz.
    """
    actual = os.path.abspath(desde)
    if os.path.isfile(actual):
        actual = os.path.dirname(actual)
    inicio = actual
    while True:
        if any(os.path.exists(os.path.join(actual, m)) for m in MARCADORES_RAIZ):
            return actual
        padre = os.path.dirname(actual)
        if padre == actual:
            return inicio
        actual = padre


def _leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _fusionar(base, encima):
    """Fusión profunda: los dicts se combinan clave a clave, cualquier otro valor de `encima` sustituye al de `base`."""
    out = dict(base)
    for k, v in (encima or {}).items():
        out[k] = _fusionar(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def cargar_config(repo):
    """config.json del repo como dict ({} si falta o está roto: los defaults viven en el código).
    Si existe `config.local.json` (gitignored: personalizaciones de cada copia, AGENT §16), se fusiona encima
    clave a clave, p. ej. {"voz_default": {...}} fija la voz de la casa sin tocar config.json."""
    cfg = _leer_json(os.path.join(repo, "config.json"))
    local = _leer_json(os.path.join(repo, "config.local.json"))
    return _fusionar(cfg, local) if local else cfg


def api_key(repo, var="OPENROUTER_API_KEY"):
    """Key del entorno o, si falta, del .env del repo. Sale con código 3 (entorno) si no hay."""
    if os.environ.get(var):
        return os.environ[var]
    env = os.path.join(repo, ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea.startswith(var + "="):
                    return linea.split("=", 1)[1].strip().strip('"').strip("'")
    print(f"Falta {var} (entorno o {env}).", file=sys.stderr)
    raise SystemExit(3)


def log_costo(recursos_dir, entrada):
    """Agrega una línea {"id","modelo","tarea","ts","usage"} al costos.jsonl del proyecto (AGENT §10)."""
    os.makedirs(recursos_dir, exist_ok=True)
    linea = {"id": entrada.get("id"), "modelo": entrada.get("modelo"),
             "tarea": entrada.get("tarea"),
             "ts": entrada.get("ts") or datetime.datetime.now().isoformat()}
    if entrada.get("usage"):
        linea["usage"] = entrada["usage"]
    with open(os.path.join(recursos_dir, "costos.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    return linea


# ---------------------------------------------------------------- Avance (tablero)
AVANCE_DIR = None   # carpeta recursos/ del proyecto activo; la fija cada script (p. ej. doblar.py) al arrancar
_ULTIMO_AVANCE = {}


def avance(etapa, pct=None, detalle="", estado=None, datos=None, cada=1.0):
    """Reporta avance al tablero (scripts/tablero.py): una línea JSON en AVANCE_DIR/avance.jsonl.

    `etapa` (descarga|transcripcion|unidades|traduccion|voz|render|verificacion|…), `pct` 0-100 o None,
    `estado` en_curso|listo|aviso|error (por defecto: listo si pct >= 100, si no en_curso), `datos` opcional
    {"etiqueta","valor","limite","unidad","nota"} para la gráfica «valor vs límite». Con `cada` se omiten
    escrituras si el porcentaje no avanzó al menos ese valor desde la última (evita miles de líneas).
    Sin AVANCE_DIR configurado no hace nada (compatibilidad con scripts que no lo usan)."""
    if not AVANCE_DIR:
        return False
    if estado is None:
        estado = "listo" if (pct is not None and pct >= 100) else "en_curso"
    if pct is not None and datos is None and estado == "en_curso":
        prev = _ULTIMO_AVANCE.get(etapa)
        if prev is not None and abs(pct - prev) < cada:
            return False
    _ULTIMO_AVANCE[etapa] = pct
    linea = {"ts": round(datetime.datetime.now().timestamp(), 3), "etapa": etapa,
             "pct": None if pct is None else round(float(pct), 2), "detalle": detalle, "estado": estado}
    if datos:
        linea["datos"] = datos
    try:
        os.makedirs(AVANCE_DIR, exist_ok=True)
        with open(os.path.join(AVANCE_DIR, "avance.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except OSError:
        return False
    return True


# ---------------------------------------------------------------- OpenRouter
def post_openrouter(cuerpo, key, ruta="/chat/completions", timeout=240, reintentos=3):
    """POST JSON a OpenRouter con reintento exponencial en 429/5xx y errores de red.

    La key solo viaja a https://openrouter.ai (la ruta es fija, no se toma de datos externos).
    Devuelve el JSON de respuesta; en 4xx no reintentable o tras agotar reintentos lanza
    `urllib.error.URLError`/`HTTPError` para que el llamador decida su código de salida (4)."""
    import time
    import urllib.error
    import urllib.request
    url = "https://openrouter.ai/api/v1" + ruta
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "X-Title": "media-agent-toolkit"})
    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and intento < reintentos - 1:
                time.sleep(2 ** (intento + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if intento < reintentos - 1:
                time.sleep(2 ** (intento + 1))
                continue
            raise


def python_de_venv(nombre):
    """Intérprete del venv `~/.venvs/<nombre>`: bin/python en macOS/Linux, Scripts\\python.exe en Windows."""
    base = os.path.expanduser(os.path.join("~", ".venvs", nombre))
    return os.path.join(base, "Scripts", "python.exe") if os.name == "nt" else os.path.join(base, "bin", "python")


# ---------------------------------------------------------------- procesos (macOS/Linux/Windows)
def pid_vivo(pid):
    """¿Sigue vivo el proceso `pid`? En Windows `os.kill(pid, 0)` NO pregunta: termina el proceso
    (TerminateProcess), así que ahí se consulta con OpenProcess/GetExitCodeProcess."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminar_arbol(pid):
    """Termina `pid` y sus hijos: su grupo de procesos (lanzado con `start_new_session=True`) en macOS/Linux,
    `taskkill /T` en Windows (ahí `start_new_session` no aplica)."""
    import signal  # noqa: PLC0415
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        os.kill(pid, signal.SIGTERM)


# ---------------------------------------------------------------- FFmpeg
def run(cmd, log=True):
    """Corre un comando; si falla imprime la cola de stderr y sale con código 1."""
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        if log:
            print("FALLO:", " ".join(str(c) for c in cmd[:10]), file=sys.stderr)
        print(r.stderr[-1800:], file=sys.stderr)
        raise SystemExit(1)
    return r


def dur(path):
    """Duración del contenedor en segundos (ffprobe)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return float(r.stdout.strip())


def ffmpeg_con_progreso(cmd, total, etiqueta="ffmpeg", imprimir=True, etapa="render"):
    """Corre FFmpeg leyendo `-progress pipe:1` e imprime el avance en pasos de 10 %.

    Tolera `out_time_ms=N/A` (FFmpeg lo emite al cerrar). stderr se drena en un hilo para
    que el pipe no se llene y bloquee el proceso.
    """
    cmd = [str(c) for c in cmd]
    if "-progress" not in cmd:
        cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
    cola = []
    hilo = threading.Thread(target=lambda: cola.extend(p.stderr), daemon=True)
    hilo.start()
    vistos = set()
    for linea in p.stdout:
        if not linea.startswith("out_time_ms="):
            continue
        try:
            ms = int((linea.split("=", 1)[1] or "0").strip())
        except ValueError:
            continue
        pct = min(100.0, ms / 1_000_000 / max(total, 1e-6) * 100)
        avance(etapa, pct, f"{etiqueta} {pct:.0f}%")   # tablero (si el script fijó AVANCE_DIR); `etapa` la fija el llamador
        paso = int(pct) // 10
        if imprimir and paso not in vistos:
            vistos.add(paso)
            print(f"  {etiqueta} avance {pct:5.1f}%", flush=True)
    p.wait()
    hilo.join(timeout=5)
    if p.returncode != 0:
        print("".join(cola)[-1800:], file=sys.stderr)
        raise SystemExit(1)
    return p.returncode


def _db(txt):
    """'-14.2' → -14.2 ; '-inf' → -inf (silencio)."""
    txt = txt.strip()
    return float("-inf") if "inf" in txt else float(txt)


def parse_ebur128(stderr):
    """Extrae {I, LRA, TP} del bloque `Summary:` de `-af ebur128=peak=true`."""
    resumen = stderr.rsplit("Summary:", 1)[-1]
    out = {}
    for clave, patron in (("I", r"I:\s+(-?[\d.]+|-?inf)\s+LUFS"),
                          ("LRA", r"LRA:\s+(-?[\d.]+)\s+LU"),
                          ("TP", r"Peak:\s+(-?[\d.]+|-?inf)\s+dBFS")):
        m = re.search(patron, resumen)
        if m:
            out[clave] = _db(m.group(1))
    if "I" not in out:
        raise ValueError("ebur128: no se encontró el resumen en stderr")
    return out


def ebur128(path):
    """Sonoridad integrada (LUFS), rango (LU) y true peak (dBTP) de la primera pista de audio."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-vn",
                        "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        raise SystemExit(1)
    return parse_ebur128(r.stderr)


def parse_loudnorm_json(stderr):
    """Último objeto JSON que imprime `loudnorm=print_format=json`, con los números como float."""
    ini = stderr.rfind("{")
    fin = stderr.rfind("}")
    if ini < 0 or fin < ini:
        raise ValueError("loudnorm: no se encontró el JSON en stderr")
    crudo = json.loads(stderr[ini:fin + 1])
    out = {}
    for k, v in crudo.items():
        try:
            out[k] = _db(v) if k != "normalization_type" else v
        except (ValueError, AttributeError):
            out[k] = v
    return out


def medir_loudnorm(entrada, I=-14.0, TP=-1.5, LRA=11.0):
    """Primera pasada de loudnorm (input_i, input_tp, input_lra, input_thresh, target_offset).

    Ojo: su medidor interno (a 192 kHz) difiere del de `ebur128` hasta ~0.5 LU con voz (medido
    2026-09-28), y es ESTE el que decide si la segunda pasada puede ser lineal."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(entrada), "-af",
                        f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        raise SystemExit(1)
    return parse_loudnorm_json(r.stderr)


def loudnorm_2p(entrada, salida, I=-14.0, TP=-1.5, LRA=11.0, sr=48000, muestras=None,
                forzar_lineal=True):
    """Normaliza en dos pasadas con `loudnorm` en modo lineal.

    Por qué dos pasadas y `linear=true`: en una sola pasada loudnorm es un AGC dinámico
    (ventana de 3 s) que bombea y aplana la mezcla; con las mediciones de la primera pasada
    aplica UNA ganancia fija, como un fader. FFmpeg vuelve a modo dinámico si esa ganancia
    rompería el TP objetivo o si el LRA medido supera el LRA objetivo; con `forzar_lineal`
    el LRA objetivo se sube al medido (el LRA solo gobierna el modo dinámico, y una mezcla
    terminada no debe recomprimirse). loudnorm siempre sale a 192 kHz: se remuestrea a `sr`
    y, si se da `muestras`, se fija la longitud exacta con apad+atrim.
    """
    m = medir_loudnorm(entrada, I, TP, LRA)
    lra = max(LRA, m["input_lra"] + 0.1) if forzar_lineal else LRA
    # measured_LRA=0 loudnorm lo toma como "no medido" y cae a modo dinámico (verificado con
    # FFmpeg 7.1 en un seno estable): una cama muy pareja puede medir 0.0, así que se pasa ≥ 0.1.
    filtro = (f"loudnorm=I={I}:TP={TP}:LRA={lra:.1f}:measured_I={m['input_i']}:"
              f"measured_TP={m['input_tp']}:measured_LRA={max(0.1, m['input_lra'])}:"
              f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
              f"linear=true:print_format=json,aresample={sr}")
    if muestras:
        filtro += f",apad=whole_len={muestras},atrim=end_sample={muestras}"
    r = subprocess.run(["ffmpeg", "-y", "-nostats", "-hide_banner", "-i", str(entrada), "-af", filtro,
                        "-ar", str(sr), "-c:a", "pcm_s24le", "-fflags", "+bitexact",
                        "-flags:a", "+bitexact", str(salida)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        raise SystemExit(1)
    res = parse_loudnorm_json(r.stderr)
    res["medido"] = m
    if res.get("normalization_type") != "linear":
        print(f"AVISO loudnorm cayó a modo {res.get('normalization_type')} "
              f"(TP medido {m['input_tp']} dBTP, LRA {m['input_lra']} LU): la mezcla se comprimió.",
              file=sys.stderr)
    return res


# ---------------------------------------------------------------- Node
def _version_node(ruta):
    """Versión mayor de un binario node, o None si no corre."""
    try:
        r = subprocess.run([ruta, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.match(r"v(\d+)\.", r.stdout.strip())
    return int(m.group(1)) if (r.returncode == 0 and m) else None


def _candidatos_node(repo):
    cfg = (cargar_config(repo).get("promo") or {}).get("node", "auto")
    if cfg and cfg != "auto":
        yield os.path.expanduser(cfg)
    ruta = shutil.which("node")
    if ruta:
        yield ruta
    # Las herramientas del agente corren sin el perfil del usuario: el Node de nvm/Homebrew
    # solo aparece en un shell de login.
    try:
        r = subprocess.run(["zsh", "-lc", "command -v node"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=20, stdin=subprocess.DEVNULL)
        lineas = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("/")]
        if lineas:
            yield lineas[-1]
    except (OSError, subprocess.TimeoutExpired):
        pass

    def clave(p):
        m = re.search(r"/v(\d+)\.(\d+)\.(\d+)/", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    nvm = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/v*/bin/node")), key=clave)
    if nvm:
        yield nvm[-1]


@functools.lru_cache(maxsize=None)
def buscar_node(repo):
    """Ruta de un Node >= 20: config promo.node → PATH → shell de login → nvm más reciente.

    Sale con código 3 (problema de entorno, preguntar al usuario) si no hay uno válido.
    """
    vistos = []
    for ruta in _candidatos_node(repo):
        if not (ruta and os.path.exists(ruta)) or ruta in (v[0] for v in vistos):
            continue
        mayor = _version_node(ruta)
        vistos.append((ruta, mayor))
        if mayor is not None and mayor >= NODE_MINIMO:
            return ruta
    detalle = ", ".join(f"{r} (v{m})" for r, m in vistos) or "ninguno"
    print(f"ERROR entorno: se necesita Node >= {NODE_MINIMO}; encontrados: {detalle}.\n"
          f"Arreglo: instala Node 22 (nvm install 22 o nodejs.org), luego "
          f"`zsh scripts/preflight.sh`; o fija la ruta en config.json > promo.node.",
          file=sys.stderr)
    raise SystemExit(3)


# ---------------------------------------------------------------- Motores Node (promo, remotion)
def json_de_salida(texto):
    """Un motor Node imprime exactamente un objeto JSON en stdout; se tolera ruido previo."""
    texto = (texto or "").strip()
    for candidato in [texto] + texto.splitlines()[::-1]:
        try:
            obj = json.loads(candidato)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def correr_motor_node(motor, args, cwd, repo=None, verbose=False, al_avance=None, nombre="motor"):
    """Corre `node <motor> <args…>` con el contrato de los motores de la casa (promo/motor.mjs,
    remotion/motor.mjs): stdout = UN objeto JSON; logs y líneas "avance NN%" en stderr.

    Devuelve (código, objeto JSON | None, cola de stderr). Si el motor no existe sale con 3 (entorno);
    si no devuelve JSON, el código pasa a ser 1 como mínimo. `al_avance(linea)` recibe cada línea de
    stderr que contenga "avance" (para el tablero o la terminal); `verbose` reenvía todo el stderr."""
    if not os.path.exists(motor):
        print(f"ERROR entorno: falta el motor Node ({motor}). ¿Repo incompleto? Actualiza el repo.")
        raise SystemExit(3)
    node = buscar_node(repo or raiz_repo(os.path.dirname(os.path.abspath(motor))))
    cmd = [node, motor] + [str(x) for x in args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                         text=True, encoding="utf-8", errors="replace", bufsize=1, cwd=cwd)
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
    obj = json_de_salida("".join(salida))
    codigo = p.returncode
    if obj is None:
        print(f"ERROR {nombre}: `{' '.join(str(a) for a in args[:1])}` no devolvió JSON (código {codigo}). Últimas líneas:")
        for l in cola[-3:]:
            print("  " + l[:200])
        codigo = codigo or 1
    return codigo, obj, cola
