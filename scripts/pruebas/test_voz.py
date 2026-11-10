"""Pruebas de scripts/voz.py (TTS simulado, sin red) y una prueba de humo EN LÍNEA opcional.

La prueba en línea corre todo el flujo real (TTS de OpenRouter → tiempos.json → validar → audio con
voz → final con .srt) y cuesta unos centavos: solo con PROMO_TTS_ONLINE=1.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(AQUI)
REPO = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import comun  # noqa: E402
import voz  # noqa: E402


def lt_voz(textos, proveedor="openrouter"):
    return {"tema_nombre": "neutro", "voz": {"voz": "coral", "proveedor": proveedor, "pendiente": True,
            "lineas": [{"escena": 1, "frase": j, "texto": t, "archivo": None, "en": 1.0 + 3 * j, "dur": 2.0}
                       for j, t in enumerate(textos)]}}


class Contador:
    """TTS simulado que cuenta llamadas y devuelve un id de generación (para el log de costos)."""

    def __init__(self, lento=False):
        self.llamadas, self.lento = [], lento

    def __call__(self, texto, system):
        self.llamadas.append((texto, system))
        pcm, sr, _, _ = voz.tts_simulado(texto, lento=self.lento)
        return pcm, sr, f"gen-{len(self.llamadas)}", {"cost": 0.001}


class TestVoz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = os.path.join(self.tmp.name, "recursos")
        os.makedirs(self.rec)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tomas_tiempos_y_cache(self):
        tts = Contador()
        textos = ["Cotiza con ACME AI, sin esperar.", "Pídelo por WhatsApp y listo."]
        r = voz.generar_voz(self.rec, lt_voz(textos), REPO, verificar=False, sintetizar=tts)
        self.assertEqual(r["codigo"], 0, r["issues"])
        self.assertEqual((r["nuevas"], r["cache"]), (2, 0))
        self.assertIn("Repite verbatim", tts.llamadas[0][1])
        self.assertEqual(tts.llamadas[0][0], "Cotiza con Ák-me Ei-Ái, sin esperar.")
        with open(os.path.join(self.rec, "voz", "tiempos.json"), encoding="utf-8") as f:
            t = json.load(f)
        self.assertEqual(t["version"], 1)
        for linea, texto in zip(t["lineas"], textos):
            wav = os.path.join(self.rec, linea["archivo"])
            self.assertTrue(linea["archivo"].startswith("voz/l1_"))
            r2 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
                                 "-of", "csv=p=0", wav], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r2.stdout.strip(), "48000,1")
            self.assertAlmostEqual(linea["dur"], comun.dur(wav), delta=0.002)
            self.assertEqual([p["w"] for p in linea["palabras"]], texto.split(" "))   # conteo de pantalla
            a = [p["a"] for p in linea["palabras"]]
            self.assertEqual(a, sorted(a))
            self.assertAlmostEqual(a[0], voz.COLCHON, delta=0.02)                       # colchón de 0.08 s
            self.assertLessEqual(linea["palabras"][-1]["b"], linea["dur"])
        # La coma coincide con la pausa del TTS: "sin" arranca después del hueco de 0.28 s.
        p = t["lineas"][0]["palabras"]
        self.assertGreater(p[4]["a"] - p[3]["b"], 0.2)
        # Costos: una línea por llamada, tarea tts.
        with open(os.path.join(self.rec, "costos.jsonl"), encoding="utf-8") as f:
            costos = [json.loads(l) for l in f]
        self.assertEqual([c["tarea"] for c in costos], ["tts", "tts"])
        # Caché: misma línea, misma voz → no se vuelve a pagar.
        r = voz.generar_voz(self.rec, lt_voz(textos), REPO, verificar=False, sintetizar=tts)
        self.assertEqual((r["nuevas"], r["cache"], len(tts.llamadas)), (0, 2, 2))

    def test_lento_se_rehace_y_luego_falla(self):
        tts = Contador(lento=True)
        r = voz.generar_voz(self.rec, lt_voz(["Cotiza hoy mismo en segundos."]), REPO, verificar=False, sintetizar=tts)
        self.assertEqual(len(tts.llamadas), 2)              # una segunda toma
        self.assertEqual(r["codigo"], 2)
        self.assertIn("E-TTS-LENTO", [i["codigo"] for i in r["issues"]])

    def test_lint_bloquea_antes_de_pagar(self):
        tts = Contador()
        r = voz.generar_voz(self.rec, lt_voz(["¿Cuánto cuestan 250 cámaras?"]), REPO, verificar=False, sintetizar=tts)
        self.assertEqual(r["codigo"], 2)
        self.assertEqual(tts.llamadas, [])
        self.assertTrue({"E-TTS-CIFRA", "E-TTS-PREGUNTA"} <= {i["codigo"] for i in r["issues"]})

    def test_elevenlabs_sin_key_es_error_de_entorno(self):
        viejo = os.environ.pop("ELEVENLABS_API_KEY", None)
        try:
            with self.assertRaises(voz.ErrorEntornoVoz):
                voz.proveedor({"proveedor": "elevenlabs"}, self.tmp.name, "x")
        finally:
            if viejo is not None:
                os.environ["ELEVENLABS_API_KEY"] = viejo

    def test_verificacion_a_avisos(self):
        tts = Contador()
        falso = lambda textos, wavs: [{"audio": 1, "extra": ["Claro"], "faltan": []}]   # noqa: E731
        r = voz.generar_voz(self.rec, lt_voz(["Cotiza con nosotros hoy."]), REPO, verificar=True,
                            sintetizar=tts, verificador=falso)
        self.assertEqual(r["codigo"], 0)
        self.assertIn("W-TTS-DIFF", [i["codigo"] for i in r["issues"]])

    def test_tiempos_descuentan_pausas_no_asignadas(self):
        # Sin comas, una pausa interna (respiración) no debe caer dentro de ninguna palabra.
        palabras = voz.tiempos_palabras(["uno", "dos", "tres", "cuatro"], ["uno", "dos", "tres", "cuatro"],
                                        0.1, 2.1, [(1.0, 1.3)])
        for p in palabras:
            self.assertFalse(p["a"] < 1.3 - 1e-6 and p["b"] > 1.0 + 1e-6, f"{p} cae dentro de la pausa 1.0–1.3")
        self.assertAlmostEqual(palabras[0]["a"], 0.1, places=3)
        self.assertAlmostEqual(palabras[-1]["b"], 2.1, places=3)


@unittest.skipUnless(os.environ.get("PROMO_TTS_ONLINE") == "1", "prueba en línea: PROMO_TTS_ONLINE=1 (cuesta centavos)")
class TestEnLinea(unittest.TestCase):
    def test_flujo_completo_con_voz(self):
        with tempfile.TemporaryDirectory() as raiz:
            correr = lambda *a: subprocess.run([sys.executable, os.path.join(SCRIPTS, "promo.py"), *a, "--raiz", raiz],  # noqa: E731
                                               capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO)
            self.assertEqual(correr("nuevo", "voz-en-linea").returncode, 0)
            proy = os.path.join(raiz, "proyectos", os.listdir(os.path.join(raiz, "proyectos"))[0])
            spec = {"version": 1, "formato": "promo_ui", "tema": "neutro", "semilla": 7,
                    "salida": {"relacion": "9:16", "duracion": 12, "archivo": "voz-en-linea.mp4"},
                    "marca": {"producto": "AI"},
                    "audio": {"musica": {"tipo": "procedural", "bpm": 112}, "sfx": "sutil",
                              "voz": {"voz": "coral", "proveedor": os.environ.get("PROMO_TTS_PROVEEDOR", "fish"), "estilo": "cálido y seguro"}},
                    "escenas": [{"tipo": "intro", "titulo": "AI para *PROs*"},
                                {"tipo": "chat", "chat": {"piel": "asistente_web", "items": [
                                    {"tipo": "usuario", "texto": "Cotiza ocho cámaras para una bodega."},
                                    {"tipo": "asistente", "texto": "*Listo:* ocho cámaras con existencia."}]},
                                 "subtitulo": ["Pide tu cotización en el chat,", "y recíbela con existencias reales."]},
                                {"tipo": "cierre", "lema": "AI para *PROs.*",
                                 "cta": {"texto": "Escríbele por WhatsApp", "icono": "whatsapp"},
                                 "contacto": "acme.example · App ACME PRO"}]}
            with open(os.path.join(proy, "promo.json"), "w", encoding="utf-8") as f:
                json.dump(spec, f, ensure_ascii=False, indent=1)
            r = correr("todo", os.path.basename(proy), "--borrador")
            print("\n" + r.stdout)
            conservar = os.environ.get("PROMO_TTS_CONSERVAR")        # para inspeccionar tomas y costos
            if conservar:
                shutil.copytree(proy, os.path.join(conservar, os.path.basename(proy)), dirs_exist_ok=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("(linear)", r.stdout)                    # la mezcla con voz no se recomprime
            with open(os.path.join(proy, "recursos", "voz", "tiempos.json"), encoding="utf-8") as f:
                t = json.load(f)
            self.assertEqual(len(t["lineas"]), 2)
            for l in t["lineas"]:
                self.assertEqual(len(l["palabras"]), len(l["texto"].split(" ")))
            with open(os.path.join(proy, "voz-en-linea.srt"), encoding="utf-8") as f:
                self.assertEqual(f.read().count(" --> "), 2)
            with open(os.path.join(proy, "recursos", "costos.jsonl"), encoding="utf-8") as f:
                tareas = [json.loads(l)["tarea"] for l in f]
            self.assertIn("tts", tareas)
            self.assertIn("verificacion_voz", tareas)
            m = comun.ebur128(os.path.join(proy, "voz-en-linea.mp4"))
            self.assertAlmostEqual(m["I"], -14.0, delta=0.5)
            self.assertTrue(os.path.exists(os.path.join(proy, "voz-en-linea_correo.mp4")))


if __name__ == "__main__":
    unittest.main()
