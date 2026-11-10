"""Pruebas de scripts/narrar.py con TTS simulado (sin red)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
import comun  # noqa: E402
import narrar  # noqa: E402
import subtitulos  # noqa: E402
import voz  # noqa: E402

RES = {"proveedor": "speech", "modelo": "x/tts", "voice": "Achird", "instructions": None, "voz": "coral", "estilo": None}
ESCENAS = [{"id": "e1", "tipo": "gancho", "min": 1, "tts": "Una dirección identifica a cada equipo en tu red."},
           {"id": "e2", "tipo": "resumen", "min": 2},
           {"id": "e3", "tipo": "pregunta", "plantea": True, "min": 1, "tts": "Elige la opción que describe una dirección privada."}]


class Contador:
    def __init__(self, gid=None, lento=False):
        self.n, self.gid, self.lento = 0, gid, lento

    def __call__(self, texto, system):
        self.n += 1
        pcm, sr, _, _ = voz.tts_simulado(texto, lento=self.lento)
        return pcm, sr, self.gid, {"cost": 0.001} if self.gid else None


class TestNarrar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rec = os.path.join(self.tmp.name, "recursos")
        os.makedirs(self.rec)

    def correr(self, escenas=ESCENAS, res=RES, sint=None, **kw):
        return narrar.narrar(escenas, self.rec, res, sintetizar=sint or Contador(), usar_whisper=False, **kw)

    def test_tiempos_y_voz_wav(self):
        t = self.correr()["tiempos"]
        for a, b in zip(t["escenas"], t["escenas"][1:]):
            self.assertEqual(a["fin"], b["inicio"])
        e = t["escenas"][0]
        self.assertAlmostEqual(e["fin"] - e["inicio"], max(1, 0.35 + e["voz_dur"] + 0.6), places=2)
        self.assertEqual(e["voz_inicio"], 0.35)
        self.assertIsNone(t["escenas"][1]["wav"])
        wav = os.path.join(self.rec, "voz.wav")
        self.assertAlmostEqual(comun.dur(wav), t["duracion"], delta=0.02)

    def test_pregunta_usa_pausa_larga(self):
        e = self.correr()["tiempos"]["escenas"][2]
        self.assertAlmostEqual(e["fin"] - e["inicio"], 0.35 + e["voz_dur"] + 5.0, places=2)

    def test_cache_por_huella(self):
        s = Contador()
        self.correr(sint=s)
        self.assertEqual(s.n, 2)
        r = self.correr(sint=s)
        self.assertEqual((s.n, r["nuevas"], r["cache"]), (2, 0, 2))
        self.correr(res={**RES, "voice": "Puck"}, sint=s)
        self.assertEqual(s.n, 4)

    def test_toma_lenta_se_rehace_y_marca_error(self):
        s = Contador(lento=True)
        r = self.correr(escenas=ESCENAS[:1], sint=s)
        self.assertEqual((s.n, r["codigo"]), (2, 2))
        self.assertEqual(r["issues"][-1]["codigo"], "E-TTS-LENTO")

    def test_toma_lenta_no_queda_en_cache(self):
        self.correr(escenas=ESCENAS[:1], sint=Contador(lento=True))
        s = Contador()
        r = self.correr(escenas=ESCENAS[:1], sint=s)
        self.assertEqual((s.n, r["codigo"]), (1, 0))

    def test_toma_simulada_no_sirve_como_real(self):
        s = Contador()
        with mock.patch.dict(os.environ, {"PROMO_TTS_STUB": "1"}):
            self.correr(escenas=ESCENAS[:1], sint=s)
        with mock.patch.dict(os.environ):
            os.environ.pop("PROMO_TTS_STUB", None)
            self.correr(escenas=ESCENAS[:1], sint=s)
        self.assertEqual(s.n, 2)

    def test_lint_bloquea_antes_de_pagar(self):
        s = Contador()
        r = self.correr(escenas=[{"id": "e1", "tts": "Tiene 255 valores posibles."}], sint=s)
        self.assertEqual((r["codigo"], s.n), (2, 0))
        self.assertEqual(r["issues"][0]["codigo"], "E-TTS-CIFRA")

    def test_cues_legibles(self):
        largo = [{"id": "e1", "tipo": "concepto", "tts": " ".join(["Esta oración explica con calma cómo funciona la red de tu instalación."] * 4)}]
        r = self.correr(escenas=largo)
        self.assertTrue(r["cues"])
        for a, b in zip(r["cues"], r["cues"][1:]):
            self.assertLessEqual(a["fin"], b["ini"])
        for c in r["cues"]:
            self.assertLessEqual(len(c["lineas"]), 2)
            self.assertTrue(all(len(l) <= 42 for l in c["lineas"]))
        srt, vtt = narrar.escribir_subtitulos(r["cues"], os.path.join(self.tmp.name, "lec"))
        with open(srt, encoding="utf-8") as f:
            self.assertEqual(len(subtitulos.leer_srt(f.read())), len(r["cues"]))
        self.assertTrue(os.path.exists(vtt))

    def test_costos_van_al_curso(self):
        otro = os.path.join(self.tmp.name, "curso")
        self.correr(sint=Contador(gid="g1"), costos_dir=otro)
        with open(os.path.join(otro, "costos.jsonl"), encoding="utf-8") as f:
            self.assertEqual(json.loads(f.readline())["tarea"], "voz")

    def test_estimar_duracion(self):
        medida = self.correr()["tiempos"]["duracion"]
        self.assertAlmostEqual(narrar.estimar_duracion(ESCENAS), medida, delta=medida * 0.3)

    def test_tiempo_de_y_alinear(self):
        p = narrar.palabras_por_silabas("La máscara separa la red, y la red manda.", 1.0, 3.0)
        a1, b1 = narrar.tiempo_de(p, "red")
        self.assertGreater(narrar.tiempo_de(p, "RÉD", desde=b1)[0], a1)
        self.assertIsNone(narrar.tiempo_de(p, "subred"))
        m = narrar.alinear_marcas("la máscara separa", [(0.1, 0.2, "la"), (0.5, 0.9, "máscara")], 1.0, 2.0)
        self.assertEqual(m[1]["a"], 1.5)

    def test_entorno_sin_key(self):
        with mock.patch.object(voz, "proveedor", side_effect=voz.ErrorEntornoVoz("falta key")):
            r = narrar.narrar(ESCENAS, self.rec, RES, usar_whisper=False)
        self.assertEqual(r["codigo"], 3)


if __name__ == "__main__":
    unittest.main()
