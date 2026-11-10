"""Pruebas del enrutador de skills (JEV simulado: sin red)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import enrutar  # noqa: E402


def respuesta(probs, choice=None):
    return {"answers": {"ruta": {"type": "choice", "choice": choice or max(probs, key=probs.get), "probabilities": probs}}}


class PruebaEnrutar(unittest.TestCase):
    def correr(self, probs, *args):
        with mock.patch.object(enrutar.decision, "decidir", return_value=respuesta(probs)) as m, \
                mock.patch.object(sys, "argv", ["enrutar.py", "petición de prueba", *args]):
            buf = io.StringIO()
            with redirect_stdout(buf):
                codigo = enrutar.main()
        return codigo, buf.getvalue(), m

    def test_preguntas_cumplen_el_contrato_de_decisions(self):
        q = enrutar.preguntas()
        self.assertIsInstance(q, dict)  # registro, no array
        self.assertEqual(q["ruta"]["type"], "choice")
        self.assertIsInstance(q["ruta"]["criteria"], dict)  # choice exige registro de opciones
        self.assertIn("instructions", q["ruta"])
        self.assertEqual(set(q["ruta"]["criteria"]), set(enrutar.RUTAS))

    def test_ruta_clara_imprime_skill_y_pasos(self):
        codigo, out, _ = self.correr({"promo_ui": 0.93, "reel_fotos": 0.05})
        self.assertEqual(codigo, 0)
        self.assertIn("ruta: promo_ui", out)
        self.assertIn("scripts/promo.py nuevo", out)
        self.assertLessEqual(len(out.strip().splitlines()), 6)

    def test_ruta_curso(self):
        codigo, out, _ = self.correr({"curso": 0.9, "remotion_video": 0.05})
        self.assertEqual(codigo, 0)
        self.assertIn("scripts/curso.py nuevo", out)
        self.assertLessEqual(len(out.strip().splitlines()), 6)

    def test_ruta_ambigua_pide_preguntar(self):
        codigo, out, _ = self.correr({"promo_ui": 0.48, "reel_fotos": 0.44})
        self.assertEqual(codigo, 0)
        self.assertIn("ambigua", out)
        self.assertIn("pregunta al usuario", out)

    def test_opcion_invalida_es_error_de_api(self):
        codigo, out, _ = self.correr({"inventada": 0.9})
        self.assertEqual(codigo, 4)

    def test_log_se_pasa_a_decidir(self):
        _, _, m = self.correr({"subtitulos": 0.9}, "--log", "/tmp/x.jsonl")
        self.assertEqual(m.call_args.kwargs.get("log"), "/tmp/x.jsonl")

    def test_sin_log_igual_se_registra(self):
        _, _, m = self.correr({"subtitulos": 0.9})
        self.assertTrue(m.call_args.kwargs.get("log", "").endswith(os.path.join("_enrutador", "recursos", "costos.jsonl")))


if __name__ == "__main__":
    unittest.main()
