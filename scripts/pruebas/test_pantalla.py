#!/usr/bin/env python3
"""Pruebas de scripts/pantalla.py (lógica pura; la parte de render se salta si falta Pillow).

Se corre con el python3 del sistema (sin Pillow): las pruebas que lo necesitan se saltan igual
que en test_subtitulos.py.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
import pantalla  # noqa: E402


def linea(texto, x0, y0, x1, y1):
    return {"texto": texto, "bbox": [x0, y0, x1, y1]}


class TestGeometria(unittest.TestCase):
    def test_unir(self):
        self.assertEqual(pantalla._unir([[10, 20, 30, 40], [5, 25, 35, 45]]), [5, 20, 35, 45])

    def test_centro(self):
        self.assertEqual(pantalla._centro([0, 0, 100, 40]), (50, 20))

    def test_cluster_dominante_ignora_logo_lejano(self):
        # tres líneas de un rótulo + un logo de una línea muy arriba: gana el bloque del rótulo
        lineas = [
            linea("To easily add", 910, 645, 1260, 695),
            linea("occupancy and daylight sensing", 900, 700, 1500, 750),
            linea("to a plug-in sensor ready luminaire", 895, 780, 1775, 848),
            linea("sensorswitch", 1300, 170, 1770, 230),
        ]
        dom = pantalla._cluster_dominante(lineas)
        self.assertEqual(len(dom["texto"]), 3)
        self.assertEqual(dom["bbox"], [895, 645, 1775, 848])

    def test_cluster_dominante_poda_linea_diminuta(self):
        # una línea de ruido mucho más angosta que el rótulo se descarta
        lineas = [
            linea("No tools or wiring required", 722, 875, 1292, 943),
            linea("iif", 980, 990, 1050, 1050),
        ]
        dom = pantalla._cluster_dominante(lineas)
        self.assertEqual(dom["texto"], ["No tools or wiring required"])

    def test_cluster_dominante_vacio(self):
        self.assertIsNone(pantalla._cluster_dominante([]))


class TestPastillaSinPillow(unittest.TestCase):
    def test_sin_pillow_devuelve_none(self):
        try:
            import PIL  # noqa: F401
            self.skipTest("Pillow presente: esta prueba es para el caso sin Pillow")
        except ImportError:
            self.assertIsNone(pantalla._bbox_pastilla("/no/existe.png", [0, 0, 10, 10]))


class TestOverlay(unittest.TestCase):
    def test_pastilla_cubre_el_bbox_original_y_dibuja_texto(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("requiere Pillow")
        cap = {"bbox_texto": [400, 400, 900, 470], "centro": [650, 435], "fuente_pt": 40}
        img = pantalla._make_overlay(
            cap, ["Hola mundo"], 1080, 1920, pantalla.FUENTE_SISTEMA,
            {"texto": (0, 0, 0, 255), "pastilla": (255, 255, 255, 255)})
        self.assertEqual(img.size, (1920, 1080))
        pix = img.convert("RGBA")
        # la pastilla (opaca y blanca) tapa las esquinas del texto original y un margen
        for xy in [(400, 400), (899, 469), (390, 390), (910, 480)]:
            r, g, b, a = pix.getpixel(xy)
            self.assertEqual(a, 255, f"{xy} debería estar cubierto por la pastilla")
            self.assertEqual((r, g, b), (255, 255, 255))
        # hay texto oscuro dentro del área del rótulo
        negros = sum(1 for x in range(400, 900, 3) for y in range(410, 465, 3)
                     if pix.getpixel((x, y))[:3] == (0, 0, 0))
        self.assertGreater(negros, 50)
        # fuera de la pastilla el overlay es transparente
        self.assertEqual(pix.getpixel((20, 20))[3], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
