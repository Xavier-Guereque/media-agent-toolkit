"""Pruebas de video_ia (precios del catálogo de OpenRouter) e ilustrar (validador): sin red."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ilustrar  # noqa: E402
import video_ia  # noqa: E402

# Entradas reales del catálogo /videos/models (2026-11-10), recortadas.
SEEDANCE = {"id": "bytedance/seedance-1-5-pro", "supported_resolutions": ["480p", "720p", "1080p"],
            "supported_sizes": ["720x1280", "1280x720", "480x854", "854x480"], "supported_durations": [4, 5, 6, 8, 12],
            "supported_frame_images": ["first_frame", "last_frame"], "generate_audio": True, "seed": True,
            "pricing_skus": {"video_tokens": "0.0000024", "video_tokens_without_audio": "0.0000012"},
            "allowed_passthrough_parameters": ["watermark", "req_key"]}
VEO_LITE = {"id": "google/veo-3.1-lite", "supported_resolutions": ["720p", "1080p"], "supported_durations": [8, 4, 6],
            "supported_frame_images": ["first_frame", "last_frame"], "generate_audio": True, "seed": True,
            "pricing_skus": {"duration_seconds_with_audio": "0.08", "duration_seconds_without_audio": "0.05",
                             "duration_seconds_with_audio_720p": "0.05", "duration_seconds_without_audio_720p": "0.03"},
            "allowed_passthrough_parameters": ["negativePrompt"]}
GROK = {"id": "x-ai/grok-imagine-video-1.5-lite", "supported_frame_images": ["first_frame"], "supported_durations": list(range(1, 16)),
        "pricing_skus": {"cents_per_image_input": "1", "cents_per_video_output_second_720p": "3"}}
KLING = {"id": "kwaivgi/kling-v3.0-pro", "supported_resolutions": ["720p"],
         "pricing_skus": {"duration_seconds": "0.112", "duration_seconds_with_audio": "0.168",
                          "image_to_video_duration_seconds_720p": "0.112"}}


class PruebaPrecios(unittest.TestCase):
    def test_seedance_por_tokens(self):
        usd, origen = video_ia.precio_por_segundo(SEEDANCE, "720p", False, True, "9:16")
        self.assertAlmostEqual(usd, 720 * 1280 * 24 / 1024 * 0.0000012, places=6)   # ~0.0259 (cobrado 0.1307 por 5 s)
        self.assertIn("720x1280", origen)

    def test_veo_sin_audio_por_resolucion(self):
        self.assertEqual(video_ia.precio_por_segundo(VEO_LITE, "720p")[0], 0.03)
        self.assertEqual(video_ia.precio_por_segundo(VEO_LITE, "720p", audio=True)[0], 0.05)

    def test_centavos_y_cargo_por_imagen(self):
        self.assertAlmostEqual(video_ia.precio_por_segundo(GROK, "720p")[0], 0.03)
        p = video_ia.plan(GROK, duracion=5, resolucion="720p", relacion="9:16", audio=False, i2v=True)
        self.assertAlmostEqual(p["costo"], 0.16)                                     # cobrado 0.16

    def test_kling_imagen_a_video(self):
        self.assertAlmostEqual(video_ia.precio_por_segundo(KLING, "720p")[0], 0.112)

    def test_duracion_y_resolucion_admitidas(self):
        self.assertEqual(video_ia.elegir_duracion(VEO_LITE, 5), 6)
        self.assertEqual(video_ia.elegir_duracion(VEO_LITE, 30), 8)
        self.assertEqual(video_ia.elegir_resolucion(KLING, "1080p"), "720p")

    def test_cuerpo_sin_marca_y_sin_audio(self):
        p = video_ia.plan(SEEDANCE, duracion=5, resolucion="720p", relacion="9:16", audio=False, i2v=False)
        c = video_ia.cuerpo_peticion(SEEDANCE, p, prompt="x", relacion="9:16", semilla=3)
        self.assertFalse(c["generate_audio"])
        self.assertEqual(c["seed"], 3)
        self.assertFalse(c["provider"]["options"]["byteplus"]["watermark"])
        self.assertNotIn("frame_images", c)

    def test_descarga_solo_a_openrouter(self):
        with self.assertRaises(ValueError):
            video_ia._descargar("https://otro.sitio/v.mp4", "k", os.path.join(tempfile.gettempdir(), "x.mp4"))


class PruebaValidarIlustrado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = ilustrar.Proyecto(os.path.join(self.tmp, "demo_10112026"))
        os.makedirs(self.p.rec)

    def spec(self, **cambios):
        s = json.loads(json.dumps(ilustrar.PLANTILLA))
        s.update(cambios)
        return s

    def test_plantilla_valida(self):
        e, _ = ilustrar.validar_spec(self.spec(), self.p)
        self.assertEqual(e, [])

    def test_errores_utiles(self):
        s = self.spec()
        s["estilo"]["prompt"] = "tinta"
        s["tomas"][1]["capas"] = {}
        s["tomas"][2]["video"] = {}
        s["tomas"].append({"id": "t1", "movimiento": "volar", "imagen": "x", "tts": "y"})
        e, _ = ilustrar.validar_spec(s, self.p)
        texto = "\n".join(e)
        for clave in ("estilo.prompt", "capas.sujeto", "video.prompt", "tomas[3].id", "tomas[3].movimiento"):
            self.assertIn(clave, texto)

    def test_aviso_texto_en_imagen_y_titular_largo(self):
        s = self.spec()
        s["tomas"][0]["imagen"] = "A sign that says OPEN"
        s["tomas"][0]["titulo"] = {"texto": "UN TITULAR DEMASIADO LARGO PARA LEERSE BIEN"}
        _, w = ilustrar.validar_spec(s, self.p)
        self.assertTrue(any("imagen" in x for x in w) and any("titulo" in x for x in w))

    def test_estimacion(self):
        ui, uv, n, sv = ilustrar.estimar(self.spec(), {**ilustrar.CONFIG_DEF, "video_resolucion": "720p"},
                                         {"bytedance/seedance-1-5-pro": SEEDANCE})
        self.assertEqual(n, 1 + 1 + 3 + 1)        # hoja de estilo + imagen + parallax (1 + 2 capas) + video_ia
        self.assertEqual(sv, 5)


if __name__ == "__main__":
    unittest.main()
