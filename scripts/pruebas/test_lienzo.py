"""Pruebas de scripts/lienzo.py: determinismo, reasignación de alpha_composite, logos en pastilla, recorte y medidas."""
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from PIL import Image, ImageDraw  # noqa: E402

import lienzo as lz  # noqa: E402

ARRIBA, ABAJO = (8, 12, 28), (17, 23, 48)


class TestFondoYCapas(unittest.TestCase):
    def test_degradado_igual_al_calculo_por_fila(self):
        img = lz.fondo_degradado(40, 50, ARRIBA, ABAJO)
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.size, (40, 50))
        for y in (0, 17, 49):
            t = y / 49
            esperado = tuple(int(ARRIBA[i] + (ABAJO[i] - ARRIBA[i]) * t) for i in range(3)) + (255,)
            self.assertEqual(img.getpixel((0, y)), esperado)
            self.assertEqual(img.getpixel((39, y)), esperado)

    def test_resplandor_y_destello_devuelven_imagen_nueva_y_son_deterministas(self):
        base = lz.fondo_degradado(120, 120, ARRIBA, ABAJO)
        a = lz.destello(lz.resplandor(base, (60, 60), 50, (0, 215, 255), 66), (60, 60), 12, 10, 80, (0, 215, 255), 40)
        b = lz.destello(lz.resplandor(base, (60, 60), 50, (0, 215, 255), 66), (60, 60), 12, 10, 80, (0, 215, 255), 40)
        self.assertIsNot(a, base)
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertNotEqual(a.tobytes(), base.tobytes())
        self.assertEqual(base.getpixel((60, 60)), lz.fondo_degradado(120, 120, ARRIBA, ABAJO).getpixel((60, 60)))

    def test_con_capa_compone_lo_translucido(self):
        base = Image.new("RGBA", (100, 60), (0, 0, 0, 255))
        out = lz.con_capa(base, lambda d: lz.tarjeta(d, (10, 10, 90, 50), radio=8))
        self.assertEqual(base.getpixel((50, 30)), (0, 0, 0, 255))  # el original no se toca
        r, g, b, _ = out.getpixel((50, 30))
        self.assertTrue(15 <= r <= 25 and r == g == b)  # relleno blanco con alfa 20 sobre negro

    def test_palomita_y_pastilla_dibujan(self):
        out = lz.con_capa(Image.new("RGBA", (120, 60), (0, 0, 0, 255)),
                          lambda d: (lz.pastilla(d, (2, 2, 70, 58), (255, 0, 0, 255), (255, 0, 0, 255)),
                                     lz.palomita(d, 95, 30)))
        self.assertEqual(out.getpixel((36, 30))[:3], (255, 0, 0))
        self.assertGreater(out.getpixel((95 - 22, 30))[1], 100)  # aro verde


class TestLogos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.a = os.path.join(self.tmp, "a.png")
        self.b = os.path.join(self.tmp, "b.png")
        Image.new("RGBA", (400, 100), (200, 0, 0, 255)).save(self.a)
        Image.new("RGBA", (100, 100), (0, 0, 200, 255)).save(self.b)

    def test_logos_en_pastilla_escala_en_bloque_si_no_caben(self):
        caja = (0, 0, 300, 160)
        out = lz.logos_en_pastilla(Image.new("RGBA", (300, 160), (0, 0, 0, 255)), caja,
                                   [(self.a, 0.8), (self.b, 0.8)], radio=0)
        # alto útil 100 → a: 320x80, b: 80x80, total 446 > 240: se escala en bloque
        rojos = [x for x in range(300) if out.getpixel((x, 80))[:3] == (200, 0, 0)]
        azules = [x for x in range(300) if out.getpixel((x, 80))[:3] == (0, 0, 200)]
        self.assertTrue(rojos and azules)
        self.assertGreaterEqual(min(rojos), 30)
        self.assertLessEqual(max(azules), 270)
        self.assertLess(max(rojos), min(azules))  # orden y separación
        self.assertEqual(out.getpixel((5, 5))[:3], (255, 255, 255))  # fondo de la pastilla

    def test_recortar_a_contenido_sobre_blanco_y_con_alfa(self):
        blanco = Image.new("RGB", (100, 80), (255, 255, 255))
        ImageDraw.Draw(blanco).rectangle([20, 30, 59, 49], fill=(10, 10, 10))
        ent = os.path.join(self.tmp, "blanco.png")
        blanco.save(ent)
        self.assertEqual(lz.recortar_a_contenido(ent, os.path.join(self.tmp, "r1.png"), margen=6), (40 + 12, 20 + 12))
        alfa = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
        ImageDraw.Draw(alfa).rectangle([5, 6, 14, 15], fill=(255, 0, 0, 255))
        ent2 = os.path.join(self.tmp, "alfa.png")
        alfa.save(ent2)
        self.assertEqual(lz.recortar_a_contenido(ent2, os.path.join(self.tmp, "r2.png")), (10, 10))


class TestMedidas(unittest.TestCase):
    def test_fuente_cachea_y_textos_caben(self):
        self.assertIs(lz.fuente(40), lz.fuente(40))
        f = lz.fuente(40)
        res = lz.textos_caben([("corto", "Hola", f, 100, 1000), ("largo", "x" * 300, f, 100, 400),
                               ("centrado", "Hola", f, 540, 600)], centro_x=540)
        ok = {n: o for n, o, *_ in res}
        self.assertEqual(ok, {"corto": True, "largo": False, "centrado": True})


if __name__ == "__main__":
    unittest.main()
