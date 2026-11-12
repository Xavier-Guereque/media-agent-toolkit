"""Pruebas de scripts/lint_w3d.py (anclas W() de escenas 3D contra tiempos por palabra)."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import lint_w3d  # noqa: E402


def tiempos(texto, inicio=10.0):
    pal = [{"w": w, "a": inicio + 0.5 * i, "b": inicio + 0.5 * i + 0.4} for i, w in enumerate(texto.split())]
    return {"escenas": [{"id": "e1", "inicio": inicio, "fin": inicio + 9, "palabras": pal}]}


T = tiempos("Coloca el riel, luego otro riel y mide ochenta centímetros. Listo.")


def codigos(cuerpo):
    fuente = "def escena_e1(cam, mira):\n" + cuerpo + "\n\nESCENAS = {}\n"
    return [p["codigo"] for p in lint_w3d.revisar(fuente, T)]


class TestLintW3d(unittest.TestCase):
    def test_limpio(self):
        self.assertEqual(codigos('    entra(o, W("coloca"))\n    rotulo("x", p, W("mide"), hasta=W("listo"))'), [])

    def test_no_existe(self):
        self.assertIn("E-W-NOEXISTE", codigos('    entra(o, W("placa"))'))
        self.assertIn("E-W-NOEXISTE", codigos('    entra(o, W("riel", 3))'))

    def test_repetida_sin_n(self):
        self.assertIn("W-W-REPETIDA", codigos('    entra(o, W("riel"))'))
        self.assertNotIn("W-W-REPETIDA", codigos('    entra(o, W("riel", 2))'))

    def test_numero(self):
        self.assertIn("W-W-NUMERO", codigos('    entra(o, W("ochenta"))'))

    def test_hasta_antes_de_aparecer(self):
        self.assertIn("E-W-HASTA", codigos('    rotulo("x", p, W("mide"), hasta=W("luego"))'))

    def test_puntuacion_y_mayusculas(self):
        self.assertEqual(codigos('    entra(o, W("Listo"))'), [])


if __name__ == "__main__":
    unittest.main()
