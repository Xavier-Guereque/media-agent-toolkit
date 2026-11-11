"""Pruebas de la firma del motor ilustrado (entintado, mancha, anotaciones, estilo de la casa, sello): sin red."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import entintado  # noqa: E402
import ilustrar  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def dibujo(ruta, ancho=216, alto=384):
    """Ilustración mínima: papel crema, relleno de color y contornos oscuros finos."""
    im = Image.new("RGB", (ancho, alto), (240, 232, 214))
    d = ImageDraw.Draw(im)
    d.ellipse((40, 90, 176, 226), fill=(70, 110, 160), outline=(30, 30, 35), width=3)
    d.line((20, 300, 196, 330), fill=(30, 30, 35), width=2)
    im.save(ruta)
    return ruta


class PruebaEntintado(unittest.TestCase):
    def test_tinta_solo_en_los_trazos(self):
        with tempfile.TemporaryDirectory() as tmp:
            im = Image.open(dibujo(os.path.join(tmp, "a.png"))).convert("RGB")
        alfa = entintado.extraer_tinta(im)
        self.assertGreater(alfa.getpixel((40, 158)), 200)       # contorno del círculo
        self.assertLess(alfa.getpixel((108, 158)), 30)          # relleno azul: no es tinta
        self.assertLess(alfa.getpixel((10, 10)), 30)            # papel

    def test_mapa_determinista_y_ecualizado(self):
        a = entintado.mapa_orden(60, 100, 7)
        b = entintado.mapa_orden(60, 100, 7)
        self.assertEqual(list(a.getdata()), list(b.getdata()))
        datos = sorted(a.getdata())
        self.assertLess(datos[len(datos) // 10], 75)            # ecualizado: el área crece pareja con el umbral
        self.assertGreater(datos[9 * len(datos) // 10], 180)

    def test_lut_extremos(self):
        self.assertEqual(max(entintado.lut_umbral(0, 0.1)), 0)
        self.assertEqual(min(entintado.lut_umbral(1, 0.1)), 255)

    def test_ultimo_cuadro_es_la_ilustracion(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = dibujo(os.path.join(tmp, "a.png"))
            mp4 = os.path.join(tmp, "e.mp4")
            dur = entintado.revelar(src, mp4, dur=0.8, ancho=216, alto=384)
            self.assertAlmostEqual(dur, 11 / 12, places=3)
            ultimo = os.path.join(tmp, "u.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.05", "-i", mp4, "-frames:v", "1", ultimo], check=True)
            a = Image.open(src).convert("RGB")
            b = Image.open(ultimo).convert("RGB")
            dif = sum(abs(x - y) for p, q in zip(a.getdata(), b.getdata()) for x, y in zip(p, q)) / (216 * 384 * 3)
            self.assertLess(dif, 4)                              # solo la compresión h264


class PruebaFirmaEnSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = ilustrar.Proyecto(os.path.join(self.tmp, "demo_11112026"))
        os.makedirs(self.p.rec)

    def spec(self):
        return json.loads(json.dumps(ilustrar.PLANTILLA))

    def test_plantilla_usa_la_firma_y_valida(self):
        s = self.spec()
        self.assertTrue(s["cierre"])
        self.assertEqual(s["tomas"][0]["entrada"]["tipo"], "entintado")
        self.assertEqual(ilustrar.validar_spec(s, self.p)[0], [])

    def test_errores_de_firma(self):
        s = self.spec()
        s["tomas"][1]["entrada"] = {"tipo": "entintado"}                 # parallax: no aplica
        s["tomas"][0]["entrada"] = {"tipo": "entintado", "dur": 9}
        s["tomas"][2]["transicion"] = "barrido"
        s["tomas"][2]["anotaciones"] = [{"tipo": "estrella", "x": 0.5, "y": 0.5},
                                        {"tipo": "flecha", "x": 1.4, "y": 0.5, "desde": [0.1]}]
        e, _ = ilustrar.validar_spec(s, self.p)
        texto = "\n".join(e)
        for clave in ("tomas[1].entrada", "tomas[0].entrada.dur", "tomas[2].transicion", "anotaciones[0].tipo",
                      "anotaciones[1].x", "anotaciones[1].desde"):
            self.assertIn(clave, texto)

    def test_avisos_de_firma(self):
        s = self.spec()
        s["tomas"][0]["transicion"] = "mancha"
        s["tomas"][1]["anotaciones"][0]["en"] = "inexistente"
        for t in s["tomas"]:
            if t.get("movimiento") in ("imagen", "video_ia"):
                t["entrada"] = {"tipo": "entintado"}
        s["tomas"].append({"id": "t4", "tts": "x", "imagen": "y", "entrada": {"tipo": "entintado"}})
        _, w = ilustrar.validar_spec(s, self.p)
        texto = "\n".join(w)
        self.assertIn("tomas[0].transicion", texto)
        self.assertIn("inexistente", texto)
        self.assertIn("cansa", texto)

    def test_estilo_de_la_casa_y_propio(self):
        ilu = {**ilustrar.CONFIG_DEF, "estilo_casa": {"prompt": "casa", "acento": "#112233", "hoja": "h.jpg"}}
        casa = ilustrar.estilo_efectivo({"estilo": {}}, ilu)
        self.assertTrue(casa["casa"])
        self.assertEqual((casa["prompt"], casa["acento"], casa["hoja"]), ("casa", "#112233", "h.jpg"))
        propio = ilustrar.estilo_efectivo({"estilo": {"prompt": "mio", "papel": "#ffffff"}}, ilu)
        self.assertFalse(propio["casa"])
        self.assertIsNone(propio["hoja"])
        self.assertEqual((propio["papel"], propio["tinta"]), ("#ffffff", ilustrar.CASA_DEF["tinta"]))

    def test_tiempo_palabra(self):
        palabras = [{"w": "La", "a": 1.0}, {"w": "longitud,", "a": 1.4}, {"w": "Cinco", "a": 3.2}]
        self.assertEqual(ilustrar.tiempo_palabra(palabras, "Longitud"), 1.4)
        self.assertEqual(ilustrar.tiempo_palabra(palabras, "cinco segundos"), 3.2)
        self.assertEqual(ilustrar.tiempo_palabra(palabras, "long"), 1.4)
        self.assertIsNone(ilustrar.tiempo_palabra(palabras, "reloj"))

    def test_sello(self):
        ilu = {**ilustrar.CONFIG_DEF}
        self.assertIsNone(ilustrar.resolver_sello(self.p, {}, ilu))
        self.assertEqual(ilustrar.resolver_sello(self.p, {"cierre": True}, ilu), ("FIN", None, 1.8))
        self.assertEqual(ilustrar.resolver_sello(self.p, {"cierre": {"texto": "Hola", "dur": 2}}, ilu), ("Hola", None, 2.0))
        self.assertIsNone(ilustrar.resolver_sello(self.p, {"cierre": {"texto": ""}}, {**ilu, "sello": {}}))


if __name__ == "__main__":
    unittest.main()
