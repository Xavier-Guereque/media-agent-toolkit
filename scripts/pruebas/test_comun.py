"""Pruebas de scripts/comun.py (python3 -m unittest discover -s scripts/pruebas -v)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import comun  # noqa: E402

REPO = os.path.dirname(os.path.dirname(AQUI))

STDERR_EBUR128 = """[Parsed_ebur128_0 @ 0x90d005080] t: 3.9  TARGET:-23 LUFS    M: -21.8 S: -21.8     I: -21.8 LUFS
[Parsed_ebur128_0 @ 0x90d005080] Summary:

  Integrated loudness:
    I:         -14.2 LUFS
    Threshold: -24.3 LUFS

  Loudness range:
    LRA:         5.2 LU
    Threshold: -34.2 LUFS
    LRA low:   -18.1 LUFS
    LRA high:  -12.9 LUFS

  True peak:
    Peak:       -1.6 dBFS
[out#0/null @ 0x90d004c00] video:0KiB audio:345KiB
"""

STDERR_LOUDNORM = """size=N/A time=00:00:04.00 bitrate=N/A speed=86.4x
[Parsed_loudnorm_0 @ 0x8c3005080]
{
\t"input_i" : "-21.75",
\t"input_tp" : "-18.06",
\t"input_lra" : "0.00",
\t"input_thresh" : "-31.75",
\t"output_i" : "-13.95",
\t"output_tp" : "-10.27",
\t"output_lra" : "0.10",
\t"output_thresh" : "-23.95",
\t"normalization_type" : "linear",
\t"target_offset" : "-0.05"
}
[out#0/null @ 0x8c3004c00] video:0KiB audio:1500KiB
"""


class TestRaizRepo(unittest.TestCase):
    def test_desde_scripts_llega_a_la_raiz(self):
        raiz = comun.raiz_repo(AQUI)
        self.assertEqual(raiz, REPO)
        self.assertTrue(os.path.exists(os.path.join(raiz, "AGENT.md")))

    def test_desde_un_archivo(self):
        self.assertEqual(comun.raiz_repo(os.path.abspath(__file__)), REPO)

    def test_marcador_anidado_y_sin_marcadores(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = os.path.realpath(tmp)
            hondo = os.path.join(tmp, "proyectos", "x_01012026", "recursos")
            os.makedirs(hondo)
            # Sin marcadores (el tmp del sistema no tiene .git/AGENT.md): devuelve el inicio.
            self.assertEqual(comun.raiz_repo(hondo), hondo)
            open(os.path.join(tmp, "AGENT.md"), "w", encoding="utf-8").close()
            self.assertEqual(comun.raiz_repo(hondo), tmp)


class TestNode(unittest.TestCase):
    def test_buscar_node_version_minima(self):
        ruta = comun.buscar_node(REPO)
        self.assertTrue(os.path.exists(ruta))
        v = subprocess.run([ruta, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        self.assertGreaterEqual(int(v.lstrip("v").split(".")[0]), 20, v)


class TestParseo(unittest.TestCase):
    def test_ebur128(self):
        m = comun.parse_ebur128(STDERR_EBUR128)
        self.assertEqual(m, {"I": -14.2, "LRA": 5.2, "TP": -1.6})

    def test_ebur128_silencio(self):
        m = comun.parse_ebur128(STDERR_EBUR128.replace("-14.2 LUFS\n    Threshold: -24.3", "-70.0 LUFS\n    Threshold: -70.0")
                                .replace("-1.6 dBFS", "-inf dBFS"))
        self.assertEqual(m["I"], -70.0)
        self.assertEqual(m["TP"], float("-inf"))

    def test_ebur128_sin_resumen(self):
        with self.assertRaises(ValueError):
            comun.parse_ebur128("nada útil")

    def test_loudnorm_json(self):
        m = comun.parse_loudnorm_json(STDERR_LOUDNORM)
        self.assertEqual(m["input_i"], -21.75)
        self.assertEqual(m["input_tp"], -18.06)
        self.assertEqual(m["target_offset"], -0.05)
        self.assertEqual(m["normalization_type"], "linear")


class TestFFmpeg(unittest.TestCase):
    def test_ebur128_y_loudnorm_2p_reales(self):
        """Un seno a -18 dBFS normalizado en dos pasadas queda lineal en -14 LUFS."""
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "a.wav"), os.path.join(tmp, "b.wav")
            comun.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                       "aevalsrc=0.125*sin(2*PI*440*t):s=48000:d=5", "-ac", "2", src])
            res = comun.loudnorm_2p(src, out, I=-14, TP=-1.5, muestras=5 * 48000)
            self.assertEqual(res["normalization_type"], "linear")
            m = comun.ebur128(out)
            self.assertAlmostEqual(m["I"], -14.0, delta=0.5)
            self.assertAlmostEqual(comun.dur(out), 5.0, delta=0.001)

    def test_log_costo(self):
        with tempfile.TemporaryDirectory() as tmp:
            comun.log_costo(tmp, {"id": "gen-1", "modelo": "m/x", "tarea": "tts", "usage": {"cost": 0.1}})
            comun.log_costo(tmp, {"id": "gen-2", "modelo": "m/x", "tarea": "vision"})
            with open(os.path.join(tmp, "costos.jsonl"), encoding="utf-8") as f:
                lineas = [json.loads(l) for l in f]
            self.assertEqual(len(lineas), 2)
            self.assertEqual(set(lineas[0]), {"id", "modelo", "tarea", "ts", "usage"})
            self.assertNotIn("usage", lineas[1])


class TestMotorNode(unittest.TestCase):
    """comun.correr_motor_node: contrato stdout = UN JSON, avance en stderr, códigos 3 (sin motor) y 1 (sin JSON)."""

    def setUp(self):
        import shutil
        if not shutil.which("node"):
            self.skipTest("sin node en PATH")

    def motor(self, tmp, cuerpo):
        ruta = os.path.join(tmp, "motor.mjs")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(cuerpo)
        return ruta

    def test_json_y_avance(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.motor(tmp, "process.stderr.write('avance  50% (1/2)\\nruido\\n');"
                                "process.stdout.write('previo\\n' + JSON.stringify({ok: true, args: process.argv.slice(2)}) + '\\n');")
            lineas = []
            codigo, obj, cola = comun.correr_motor_node(m, ["render", "--x", 1], cwd=tmp, repo=REPO, al_avance=lineas.append)
            self.assertEqual(codigo, 0)
            self.assertEqual(obj, {"ok": True, "args": ["render", "--x", "1"]})
            self.assertEqual(lineas, ["avance  50% (1/2)"])
            self.assertIn("ruido", cola)

    def test_sin_json_es_1_y_sin_motor_es_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.motor(tmp, "process.stdout.write('esto no es json\\n'); process.exit(0);")
            import io
            from unittest import mock
            with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as so:
                codigo, obj, _ = comun.correr_motor_node(m, ["validar"], cwd=tmp, repo=REPO)
            self.assertEqual((codigo, obj), (1, None))
            self.assertIn("no devolvió JSON", so.getvalue())
            with mock.patch.object(sys, "stdout", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as cm:
                    comun.correr_motor_node(os.path.join(tmp, "no.mjs"), [], cwd=tmp, repo=REPO)
            self.assertEqual(cm.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
