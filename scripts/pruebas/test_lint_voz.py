"""Pruebas de scripts/lint_voz.py y de la tabla de pronunciación del tema."""
import contextlib
import glob
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import lint_voz  # noqa: E402
import voz  # noqa: E402

REPO = os.path.dirname(os.path.dirname(AQUI))
MARCAS = ["ACME", "WhatsApp"]


def codigos(textos, modelo="openai/gpt-audio-mini"):
    lineas = [{"ruta": f"l{i}", "texto": t} for i, t in enumerate(textos)]
    return [i["codigo"] for i in lint_voz.revisar(lineas, modelo, MARCAS)]


class TestReglas(unittest.TestCase):
    def test_cifras(self):
        self.assertIn("E-TTS-CIFRA", codigos(["Cotiza 250 cámaras hoy."]))
        self.assertNotIn("E-TTS-CIFRA", codigos(["Cotiza doscientas cincuenta cámaras."]))

    def test_pregunta_y_dos_puntos_solo_con_gpt_audio(self):
        self.assertIn("E-TTS-PREGUNTA", codigos(["¿Buscas tu próximo proyecto?"]))
        self.assertIn("E-TTS-DOS-PUNTOS", codigos(["Cuatro dudas: norma, pruebas y reporte."]))
        self.assertEqual(codigos(["¿Buscas tu próximo proyecto?"], modelo="elevenlabs/x"), [])

    def test_marca_al_inicio_y_repetida(self):
        c = codigos(["ACME te ayuda a cotizar.", "Pídelo por WhatsApp con ACME."])
        self.assertIn("W-TTS-MARCA-INICIO", c)
        self.assertIn("W-TTS-MARCA-REPETIDA", c)
        self.assertEqual(codigos(["Cotiza con ACME hoy.", "Recibe todo al instante."]), [])

    def test_vacia(self):
        self.assertIn("E-TTS-VACIA", codigos(["  "]))

    def test_palabras_como_el_motor(self):
        # Espacio duro U+00A0 une piezas ("400 m²" es una palabra); el énfasis no cuenta.
        self.assertEqual(lint_voz.palabras("Cubre 400 m² *completos*"), ["Cubre", "400 m²", "completos"])

    def test_cli_sale_2_con_errores(self):
        sys.argv = ["lint_voz.py", "--linea", "¿Cuánto cuesta?"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(lint_voz.main(), 2)
        self.assertIn("E-TTS-PREGUNTA", buf.getvalue())


class TestPronunciacion(unittest.TestCase):
    def test_un_token_por_token_en_todas_las_tablas(self):
        """Regla dura del karaoke: cada entrada mapea UN token a UN token (guiones sí, espacios no)."""
        tablas = glob.glob(os.path.join(REPO, "promo", "temas", "*", "pronunciacion.json"))
        self.assertTrue(tablas)
        for ruta in tablas:
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
            for k, v in datos["palabras"].items():
                self.assertNotRegex(k, r"\s", f"{ruta}: clave con espacio «{k}»")
                self.assertNotRegex(v, r"\s", f"{ruta}: «{k}» → «{v}» tiene espacios")
                self.assertTrue(v.strip(), f"{ruta}: «{k}» vacío")

    def test_a_tts_conserva_conteo_y_puntuacion(self):
        pron = voz.cargar_pronunciacion(REPO, "neutro")
        texto = "Cotiza con ACME AI, y pídelo por WhatsApp."
        tts = voz.a_tts(texto, pron)
        self.assertEqual(tts, "Cotiza con Ák-me Ei-Ái, y pídelo por wátsap.")
        self.assertEqual(len(lint_voz.palabras(tts)), len(lint_voz.palabras(texto)))

    def test_silabas(self):
        for palabra, n in (("Cotiza", 3), ("día", 2), ("aeropuerto", 5), ("y", 1), ("hoy", 1),
                           ("Ák-me", 2), ("cuatro-ka", 3), ("PROs", 1)):
            self.assertEqual(voz.silabas(palabra), n, palabra)


if __name__ == "__main__":
    unittest.main()
