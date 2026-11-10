"""Pruebas de los créditos en pantalla de scripts/commons.py (sin red)."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import commons  # noqa: E402


class TestCreditos(unittest.TestCase):
    def test_autor_corto(self):
        self.assertEqual(commons.autor_corto("NASA from Washington, DC (Flickr)\nmás"), "NASA")
        self.assertEqual(commons.autor_corto("Ana Pérez, Juan"), "Ana Pérez")
        self.assertEqual(commons.autor_corto(""), "autor desconocido")
        self.assertEqual(len(commons.autor_corto("x" * 90)), 40)

    def test_licencia_corta(self):
        self.assertEqual(commons.licencia_corta("Public domain"), "Dominio público")
        self.assertEqual(commons.licencia_corta("CC BY-SA 4.0"), "CC BY-SA 4.0")

    def test_credito_foto_y_lista(self):
        c = {"titulo": "File:USS Enterprise (NCC-1701-D).jpg", "autor": "Paramount (studio)", "licencia": "Public domain"}
        self.assertEqual(commons.credito_foto(c), "Foto: Paramount · Dominio público")
        self.assertEqual(commons.credito_lista(c),
                         "USS Enterprise (NCC-1701-D) — Paramount — Dominio público · Wikimedia Commons")


if __name__ == "__main__":
    unittest.main()
