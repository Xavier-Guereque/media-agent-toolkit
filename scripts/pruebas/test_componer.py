"""Pruebas de scripts/componer.py: props por escena, tomas encadenadas, mezcla con ducking/SFX, clips, logo y specs."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import componer as cp  # noqa: E402

TIEMPOS = {"duracion": 4.0, "escenas": [
    {"id": "1", "tipo": "gancho", "inicio": 0.0, "fin": 2.0, "wav": "voz/1.wav", "voz_inicio": 0.35,
     "palabras": [{"w": "Hola", "a": 0.4, "b": 0.8}, {"w": "mundo.", "a": 0.8, "b": 1.3}]},
    {"id": "2", "tipo": "cierre", "inicio": 2.0, "fin": 4.0, "wav": None, "voz_inicio": None},
]}


def tono(ruta, dur, freq=440, canales=1):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}:sample_rate=48000",
                    "-ac", str(canales), ruta], check=True)


class TestEscenas(unittest.TestCase):
    def test_props_relativas_campos_y_omision_de_none(self):
        esc = cp.escenas_props(TIEMPOS, {"1": {"titulo": "*Hola*", "captura": None, "foco": (0.5, 0.2)}},
                               por_defecto={"titulo": "", "apoyo": ""})
        self.assertEqual(esc[0], {"id": "1", "tipo": "gancho", "inicio": 0.0, "fin": 2.0, "titulo": "*Hola*", "apoyo": "",
                                  "foco": [0.5, 0.2], "palabras": [{"w": "Hola", "a": 0.4, "b": 0.8},
                                                                    {"w": "mundo.", "a": 0.8, "b": 1.3}]})
        self.assertEqual(esc[1], {"id": "2", "tipo": "cierre", "inicio": 2.0, "fin": 4.0, "titulo": "", "apoyo": ""})

    def test_palabras_relativas_redondean_a_ms(self):
        e = {"inicio": 1.0, "palabras": [{"w": "x", "a": 1.23456, "b": 2.0004}]}
        self.assertEqual(cp.palabras_relativas(e), [{"w": "x", "a": 0.235, "b": 1.0}])

    def test_tomas_de_salta_escenas_sin_voz(self):
        self.assertEqual(cp.tomas_de(TIEMPOS, "/r"), [("/r/voz/1.wav", 0.35)])


class TestAudioYVideo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "voz"))
        tono(os.path.join(self.tmp, "voz", "1.wav"), 1.0)
        tono(os.path.join(self.tmp, "voz", "2.wav"), 0.5, 660)

    def test_encadenar_tomas_con_tempo_respiro_y_cierre_minimo(self):
        tramos, tomas, total = cp.encadenar_tomas([("1", "gancho"), ("2", "cierre")], self.tmp, tempo=1.0,
                                                  entrada=0.15, respiro=0.25, cierre_min=2.0)
        self.assertAlmostEqual(tramos[0]["dur"], 1.4, places=1)
        self.assertEqual(tramos[1]["dur"], 2.0)  # cierre_min manda sobre 0.15 + 0.5 + 0.25
        self.assertEqual(tramos[1]["inicio"], tramos[0]["fin"])
        self.assertAlmostEqual(tomas[1][1], tramos[1]["inicio"] + 0.15, places=3)
        self.assertEqual(total, tramos[1]["fin"])
        self.assertAlmostEqual(tramos[0]["dur"] * 30, round(tramos[0]["dur"] * 30), places=6)  # al cuadro

    def test_mezclar_estereo_con_cama_y_sfx_dura_el_total(self):
        cama = os.path.join(self.tmp, "cama.wav")
        tono(cama, 5.0, 220, canales=2)
        sal = os.path.join(self.tmp, "mezcla.wav")
        cp.mezclar(sal, 3.0, [(os.path.join(self.tmp, "voz", "1.wav"), 0.5)], cama,
                   sfx=[(os.path.join(self.tmp, "voz", "2.wav"), 2.0, 0.5)])
        info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=channels,sample_rate",
                                                   "-of", "json", sal]))["streams"][0]
        self.assertEqual((info["channels"], info["sample_rate"]), (2, "48000"))
        self.assertAlmostEqual(cp.duracion(sal), 3.0, places=1)
        self.assertIsNotNone(cp.nivel_medio(sal, 0, 0.4))  # la cama suena antes de la voz

    def test_mezclar_es_determinista_y_funciona_sin_cama(self):
        a, b = os.path.join(self.tmp, "a.wav"), os.path.join(self.tmp, "b.wav")
        for s in (a, b):
            cp.mezclar(s, 2.0, [(os.path.join(self.tmp, "voz", "1.wav"), 0.2)])
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    def test_mezclar_sin_tomas_falla(self):
        with self.assertRaises(ValueError):
            cp.mezclar(os.path.join(self.tmp, "x.wav"), 1.0, [])

    def test_recortar_clip_acelera_y_recorta(self):
        origen = os.path.join(self.tmp, "o.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=4",
                        "-pix_fmt", "yuv420p", origen], check=True)
        sal = cp.recortar_clip(origen, os.path.join(self.tmp, "c.mp4"), 0.5, 1.0, vel=2.0, crop="160:120:0:0")
        info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                                                   "-of", "json", sal]))["streams"][0]
        self.assertEqual((info["width"], info["height"]), (160, 120))
        self.assertAlmostEqual(cp.duracion(sal), 1.0, places=1)


class TestRecursos(unittest.TestCase):
    def test_logo_con_color_y_specs(self):
        tmp = tempfile.mkdtemp()
        svg = os.path.join(tmp, "l.svg")
        with open(svg, "w", encoding="utf-8") as f:
            f.write('<svg><path fill="currentColor"/></svg>')
        cp.logo_con_color(svg, os.path.join(tmp, "b.svg"))
        with open(os.path.join(tmp, "b.svg"), encoding="utf-8") as f:
            self.assertIn('fill="#ffffff"', f.read())
        rutas = cp.escribir_specs(tmp, "Comp", {"escenas": []}, 4.0, {"vertical": "v.mp4", "horizontal": "h.mp4"},
                                  por_defecto="vertical")
        self.assertEqual(set(rutas), {"vertical", "horizontal"})
        with open(os.path.join(tmp, "remotion.json"), encoding="utf-8") as f:
            base = json.load(f)
        self.assertEqual((base["orientacion"], base["salida"], base["composicion"], base["duracion"]),
                         ("vertical", "v.mp4", "Comp", 4.0))
        with open(rutas["horizontal"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["salida"], "h.mp4")


if __name__ == "__main__":
    unittest.main()
