"""Pruebas de scripts/remotion.py con raíz temporal (--raiz), copia mínima del motor (REMOTION_DIR) y motor Node
simulado (REMOTION_MOTOR). Nunca escriben en proyectos/ ni en remotion/src/composiciones/proyectos/ del repo.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(AQUI)
REPO = os.path.dirname(SCRIPTS)
REMOTION_PY = os.path.join(SCRIPTS, "remotion.py")
MOTOR_REAL = os.path.join(REPO, "remotion")
sys.path.insert(0, SCRIPTS)
import comun  # noqa: E402
import remotion  # noqa: E402

# Motor simulado con el contrato de remotion/motor.mjs (un JSON en stdout, avance en stderr).
MOTOR_STUB = r"""
import fs from 'node:fs';
const modo = process.env.STUB_MODO || 'ok';
const argv = process.argv.slice(2);
const out = (o, c) => { process.stdout.write(JSON.stringify(o) + '\n'); process.exit(c); };
if (process.env.STUB_ARGS) fs.writeFileSync(process.env.STUB_ARGS, JSON.stringify(argv));
process.stderr.write('log del motor que no debe verse sin --verbose\n');
const opt = (k) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : undefined; };
if (argv[0] === 'composiciones') out({ ok: true, ids: ['Ejemplo'] }, 0);
if (modo === 'errores') out({ ok: false, errores: [{ codigo: 'E-COMPOSICION', severidad: 'E', ruta: 'composicion',
  msg: "no existe la composición 'X'", arreglo: 'Revisa remotion.json.' }] }, 2);
if (modo === 'entorno') out({ ok: false, errores: [{ codigo: 'E-ENTORNO', severidad: 'E', ruta: '-',
  msg: 'falta el navegador.', arreglo: 'Corre: npx --prefix remotion remotion browser ensure' }] }, 3);
if (modo === 'basura') { process.stdout.write('esto no es json\n'); process.exit(0); }
for (const p of [10, 50, 100]) process.stderr.write(`avance ${String(p).padStart(3)}% (${p}/100)\n`);
fs.copyFileSync(process.env.STUB_VIDEO, opt('salida'));
const props = JSON.parse(fs.readFileSync(opt('props'), 'utf8'));
out({ ok: true, video: opt('salida'), cuadros: Math.round(props.duracion * props.fps), fps: props.fps,
  ancho: props.ancho, alto: props.alto, duracion: props.duracion, segundos: 1.5, borrador: argv.includes('--borrador') }, 0);
"""


class TestRemotion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("sin node en PATH")
        cls.tmp_clase = tempfile.TemporaryDirectory()
        # Video del "motor": 3 s a 30 fps, 216x384, h264 SIN etiquetas de color y con un seno a -18 dBFS.
        cls.video = os.path.join(cls.tmp_clase.name, "motor.mp4")
        comun.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=30:d=3",
                   "-f", "lavfi", "-i", "aevalsrc=0.125*sin(2*PI*440*t):s=48000:d=3", "-c:v", "libx264",
                   "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", cls.video])

    @classmethod
    def tearDownClass(cls):
        cls.tmp_clase.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = os.path.join(self.tmp.name, "raiz")
        self.motor_dir = os.path.join(self.tmp.name, "remotion")
        comp = os.path.join(self.motor_dir, "src", "composiciones")
        os.makedirs(os.path.join(comp, "proyectos"))
        for rel in ("src/composiciones/index.ts", "src/composiciones/Ejemplo.tsx"):
            shutil.copy(os.path.join(MOTOR_REAL, rel), os.path.join(self.motor_dir, rel))
        os.makedirs(os.path.join(self.motor_dir, "node_modules", "@remotion", "cli"))
        os.makedirs(os.path.join(self.motor_dir, "node_modules", ".remotion", "chrome-headless-shell"))
        self.stub = os.path.join(self.tmp.name, "motor_stub.mjs")
        with open(self.stub, "w", encoding="utf-8") as f:
            f.write(MOTOR_STUB)
        self.args_json = os.path.join(self.tmp.name, "args.json")
        self.env = {"REMOTION_DIR": self.motor_dir, "REMOTION_MOTOR": self.stub, "STUB_VIDEO": self.video,
                    "STUB_ARGS": self.args_json}

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, *args, env=None):
        e = dict(os.environ, **self.env, **(env or {}))
        r = subprocess.run([sys.executable, REMOTION_PY, *args, "--raiz", self.raiz], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=e, cwd=REPO)
        return r.returncode, r.stdout, r.stderr

    def nuevo(self, slug="prueba-uno", *extra):
        codigo, out, err = self.correr("nuevo", slug, *extra)
        self.assertEqual(codigo, 0, out + err)
        base = os.path.join(self.raiz, "proyectos")
        return os.path.join(base, [d for d in os.listdir(base) if d.startswith(slug)][0])

    def tsx(self, nombre):
        return os.path.join(self.motor_dir, "src", "composiciones", "proyectos", nombre + ".tsx")

    def registro(self):
        with open(os.path.join(self.motor_dir, "src", "composiciones", "proyectos", "registro.ts"), encoding="utf-8") as f:
            return f.read()

    # ------------------------------------------------------------ nuevo
    def test_nuevo_crea_spec_tsx_y_registro(self):
        proy = self.nuevo()
        self.assertRegex(os.path.basename(proy), r"^prueba-uno_\d{8}$")
        for rel in ("remotion.json", "brief.md", "info.txt", "recursos/remotion"):
            self.assertTrue(os.path.exists(os.path.join(proy, rel)), rel)
        with open(os.path.join(proy, "remotion.json"), encoding="utf-8") as f:
            spec = json.load(f)
        self.assertEqual(spec["composicion"], "PruebaUno")
        self.assertEqual((spec["version"], spec["salida"], spec["orientacion"], spec["duracion"]), (1, "prueba-uno.mp4", "vertical", 3.0))
        self.assertEqual(set(spec["props"]), set(remotion.PROPS_EJEMPLO))
        with open(self.tsx("PruebaUno"), encoding="utf-8") as f:
            tsx = f.read()
        self.assertIn("export const Composicion", tsx)
        self.assertIn("export const meta", tsx)
        self.assertNotIn("Ejemplo de oro", tsx)                    # cabecera reemplazada
        self.assertIn("from '../../lib/props'", tsx)                # un nivel más abajo que Ejemplo.tsx
        self.assertNotIn("from '../lib/", tsx)
        self.assertIn("from './PruebaUno'", self.registro())
        self.assertIn("id: 'PruebaUno'", self.registro())
        # Nunca toca el proyectos/ ni el remotion/ reales.
        self.assertFalse(any(d.startswith("prueba-uno_") for d in os.listdir(os.path.join(REPO, "proyectos"))))
        self.assertFalse(os.path.exists(os.path.join(MOTOR_REAL, "src", "composiciones", "proyectos", "PruebaUno.tsx")))

    def test_nuevo_rechaza_argumentos_malos(self):
        self.nuevo()
        self.assertEqual(self.correr("nuevo", "prueba-uno")[0], 2)                               # ya existe
        self.assertEqual(self.correr("nuevo", "Mal Slug!")[0], 2)
        self.assertEqual(self.correr("nuevo", "otro", "--composicion", "mal nombre")[0], 2)
        self.assertEqual(self.correr("nuevo", "otro", "--orientacion", "diagonal")[0], 2)
        self.assertEqual(self.correr("nuevo", "otro", "--composicion", "Ejemplo")[0], 2)         # id de BASE
        self.assertEqual(self.correr("nuevo", "otro", "--duracion", "0")[0], 2)
        self.assertFalse(any(d.startswith("otro_") for d in os.listdir(os.path.join(self.raiz, "proyectos"))))

    # ------------------------------------------------------------ validar
    def test_validar_errores_con_ruta_y_arreglo(self):
        proy = self.nuevo()
        spec = {"composicion": "NoExiste", "orientacion": "cuadrado", "duracion": 0, "fps": 30,
                "props": {"clip": "x.mp4", "lista": [{"voz": "v.wav"}]}, "salida": "a/b.mp4"}
        with open(os.path.join(proy, "remotion.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f)
        codigo, out, _ = self.correr("validar", "prueba-uno")
        self.assertEqual(codigo, 2, out)
        lineas = out.strip().splitlines()
        self.assertIn("errores", lineas[0])
        for esperado in ("E-REMOTION-VERSION  version:", "E-REMOTION-REGISTRO  composicion:", "E-REMOTION-SALIDA  salida:",
                         "E-REMOTION-ORIENTACION  orientacion:", "E-REMOTION-DURACION  duracion:",
                         "E-REMOTION-RECURSO  props.clip:", "E-REMOTION-RECURSO  props.lista[0].voz:"):
            self.assertIn(esperado, out)
        self.assertLessEqual(len(lineas), remotion.MAX_ISSUES + 3)
        self.assertTrue(lineas[-1].startswith("Siguiente: corrige remotion.json"))
        # Arreglado (y el recurso existe): 0 errores con el resumen de cuadros.
        open(os.path.join(proy, "recursos", "voz.wav"), "wb").close()
        spec = {"version": 1, "composicion": "PruebaUno", "orientacion": "horizontal", "duracion": 2.5, "fps": 24,
                "props": {"voz": "voz.wav", "titulo": "Hola"}}
        with open(os.path.join(proy, "remotion.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f)
        codigo, out, _ = self.correr("validar", "prueba-uno")
        self.assertEqual(codigo, 0, out)
        self.assertIn("0 errores", out.splitlines()[0])
        self.assertIn("2.5 s, 60 cuadros, 1920x1080 @ 24 fps", out.splitlines()[0])
        if (comun.cargar_config(REPO).get("remotion") or {}).get("licencia") is None:
            self.assertIn("W-REMOTION-LICENCIA", out)
        self.assertTrue(out.strip().splitlines()[-1].startswith("Siguiente: python3 scripts/remotion.py render prueba-uno_"))

    def test_validar_sin_deps_sale_3(self):
        self.nuevo()
        shutil.rmtree(os.path.join(self.motor_dir, "node_modules", "@remotion"))
        codigo, out, _ = self.correr("validar", "prueba-uno")
        self.assertEqual(codigo, 3, out)
        self.assertIn("npm ci --prefix remotion", out)

    def test_validar_json_roto_y_proyecto_inexistente(self):
        proy = self.nuevo()
        with open(os.path.join(proy, "remotion.json"), "w", encoding="utf-8") as f:
            f.write("{esto no es json")
        codigo, out, _ = self.correr("validar", "prueba-uno")
        self.assertEqual(codigo, 2)
        self.assertIn("E-REMOTION-JSON", out)
        self.assertEqual(self.correr("estado", "nada-de-esto")[0], 2)

    # ------------------------------------------------------------ render (motor simulado)
    def test_render_construye_comando_y_acaba_con_ffmpeg(self):
        proy = self.nuevo()
        codigo, out, err = self.correr("render", "prueba-uno", env={"STUB_MODO": "ok"})
        self.assertEqual(codigo, 0, out + err)
        with open(self.args_json, encoding="utf-8") as f:
            argv = json.load(f)
        self.assertEqual(argv[:3], ["render", "--composicion", "PruebaUno"])
        self.assertTrue(argv[argv.index("--props") + 1].endswith(os.path.join("recursos", "remotion", "props.json")))
        self.assertTrue(argv[argv.index("--public-dir") + 1].endswith("recursos"))
        self.assertEqual(argv[argv.index("--crf") + 1], "17")
        self.assertEqual(argv[argv.index("--x264-preset") + 1], "slow")
        self.assertNotIn("--borrador", argv)
        with open(os.path.join(proy, "recursos", "remotion", "props.json"), encoding="utf-8") as f:
            props = json.load(f)
        self.assertEqual((props["duracion"], props["ancho"], props["alto"], props["fps"]), (3.0, 1080, 1920, 30))
        self.assertEqual(props["titulo"], "Prueba uno")
        salida = os.path.join(proy, "prueba-uno.mp4")
        self.assertTrue(os.path.exists(salida))
        v, au, _ = remotion.sondear(salida)
        self.assertEqual((v["pix_fmt"], v["color_primaries"], v["color_transfer"], v["color_space"]),
                         ("yuv420p", "bt709", "bt709", "bt709"))
        self.assertEqual(int(v["nb_read_packets"]), 90)
        self.assertIsNotNone(au)
        self.assertAlmostEqual(comun.ebur128(salida)["I"], -14.0, delta=0.5)
        lineas = out.strip().splitlines()
        self.assertLessEqual(len(lineas), 4)
        self.assertIn("checks: ok", out)
        self.assertIn("-14.0 LUFS", out.replace("−", "-"))
        self.assertTrue(lineas[-1].startswith("Siguiente:"))
        self.assertNotIn("log del motor", out + err)
        with open(os.path.join(proy, "recursos", "remotion", "render.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["codigo"], 0)
        with open(os.path.join(proy, "recursos", "avance.jsonl"), encoding="utf-8") as f:
            av = [json.loads(l) for l in f]
        self.assertEqual(av[-1]["etapa"], "render")
        self.assertEqual((av[-1]["pct"], av[-1]["estado"]), (100, "listo"))
        with open(os.path.join(proy, "info.txt"), encoding="utf-8") as f:
            self.assertIn(remotion.MARCA_INI, f.read())
        _, _, err = self.correr("render", "prueba-uno", "--verbose", env={"STUB_MODO": "ok"})
        self.assertIn("log del motor", err)

    def test_render_borrador(self):
        proy = self.nuevo()
        codigo, out, err = self.correr("render", "prueba-uno", "--borrador", "--workers", "50%", env={"STUB_MODO": "ok"})
        self.assertEqual(codigo, 0, out + err)
        with open(self.args_json, encoding="utf-8") as f:
            argv = json.load(f)
        self.assertIn("--borrador", argv)
        self.assertEqual(argv[argv.index("--concurrencia") + 1], "50%")
        self.assertIn("render (borrador)", out)
        self.assertTrue(os.path.exists(os.path.join(proy, "prueba-uno.mp4")))
        # --workers inválido se rechaza ANTES de arrancar Node (código 2, no 1 del motor).
        os.remove(self.args_json)
        codigo, out, _ = self.correr("render", "prueba-uno", "--workers", "muchos", env={"STUB_MODO": "ok"})
        self.assertEqual(codigo, 2, out)
        self.assertIn("--workers", out)
        self.assertFalse(os.path.exists(self.args_json))

    def test_render_propaga_codigos_del_motor(self):
        self.nuevo()
        codigo, out, _ = self.correr("render", "prueba-uno", env={"STUB_MODO": "errores"})
        self.assertEqual(codigo, 2)
        self.assertIn("E-COMPOSICION  composicion:", out)
        self.assertTrue(out.strip().splitlines()[-1].startswith("Siguiente: corrige"))
        self.assertEqual(self.correr("render", "prueba-uno", env={"STUB_MODO": "entorno"})[0], 3)
        codigo, out, _ = self.correr("render", "prueba-uno", env={"STUB_MODO": "basura"})
        self.assertEqual(codigo, 1)
        self.assertIn("no devolvió JSON", out)

    # ------------------------------------------------------------ estudio / estado / ayuda (en proceso)
    def test_estudio_lanza_en_background_y_se_detiene(self):
        proy = self.nuevo()
        with mock.patch.dict(os.environ, self.env), \
             mock.patch.object(comun, "buscar_node", return_value="/usr/bin/node"), \
             mock.patch.object(subprocess, "Popen") as popen:
            popen.return_value.pid = 4242
            a = remotion.construir_parser().parse_args(["estudio", proy, "--raiz", self.raiz, "--puerto", "3123"])
            with mock.patch.object(sys, "stdout", new_callable=__import__("io").StringIO) as so:
                self.assertEqual(remotion.etapa_estudio(a, remotion.Proyecto(proy)), 0)
            argv = popen.call_args.args[0]
            for esperado in ("studio", "--props", "--public-dir", "--port", "3123", "--no-open"):
                self.assertIn(esperado, argv)
            self.assertEqual(popen.call_args.kwargs.get("cwd"), self.motor_dir)
            self.assertIn("http://localhost:3123", so.getvalue())
            with open(os.path.join(proy, "recursos", "remotion", "estudio.pid"), encoding="utf-8") as f:
                self.assertEqual(f.readline().strip(), "4242")
            a = remotion.construir_parser().parse_args(["estudio", proy, "--raiz", self.raiz, "--detener"])
            with mock.patch.object(comun, "pid_vivo", return_value=True), \
                 mock.patch.object(comun, "terminar_arbol") as terminar, \
                 mock.patch.object(sys, "stdout", new_callable=__import__("io").StringIO):
                self.assertEqual(remotion.etapa_estudio(a, remotion.Proyecto(proy)), 0)
            terminar.assert_called_once_with(4242)
            self.assertFalse(os.path.exists(os.path.join(proy, "recursos", "remotion", "estudio.pid")))

    def test_generar_registro_es_determinista(self):
        with mock.patch.dict(os.environ, self.env):
            d = os.path.join(self.motor_dir, "src", "composiciones", "proyectos")
            for n in ("Beta.tsx", "Alfa.tsx", "malo-nombre.tsx", "notas.txt"):
                open(os.path.join(d, n), "w", encoding="utf-8").close()
            ids, malos = remotion.generar_registro()
            self.assertEqual((ids, malos), (["Alfa", "Beta"], ["malo-nombre"]))
            ruta = os.path.join(d, "registro.ts")
            texto = self.registro()
            self.assertIn("import { Composicion as C_Alfa, meta as M_Alfa } from './Alfa';", texto)
            self.assertLess(texto.index("'Alfa'"), texto.index("'Beta'"))
            m1 = os.path.getmtime(ruta)
            remotion.generar_registro()                          # sin cambios: no reescribe
            self.assertEqual(os.path.getmtime(ruta), m1)
            self.assertEqual(remotion.ids_base(), ["Ejemplo", "Leccion", "Ilustrado"])

    def test_registro_vacio_del_motor_coincide_con_python(self):
        """motor.mjs crea registro.ts si falta (clon limpio): debe ser idéntico al de generar_registro() sin TSX."""
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(remotion.generar_registro(), ([], []))
            texto_py = self.registro()
        motor = os.path.join(MOTOR_REAL, "motor.mjs")
        r = subprocess.run(["node", "--input-type=module", "-e",
                            f"import('{pathlib.Path(motor).as_uri()}').then(m => process.stdout.write(m.REGISTRO_VACIO))"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, texto_py)

    def test_estado_y_ayuda_cortos(self):
        self.nuevo()
        codigo, out, _ = self.correr("estado", "prueba-uno")
        self.assertEqual(codigo, 0, out)
        lineas = out.strip().splitlines()
        self.assertLessEqual(len(lineas), 6)
        self.assertIn("composición PruebaUno", lineas[0])
        self.assertTrue(lineas[-1].startswith("Siguiente: python3 scripts/remotion.py validar prueba-uno_"))
        codigo, out, _ = self.correr("ayuda")
        self.assertEqual(codigo, 0)
        self.assertLessEqual(len(out.strip().splitlines()), 20)
        self.assertIn("remotion.pro/license", out)


if __name__ == "__main__":
    unittest.main()
