"""Pruebas de scripts/curso_spec.py: forma de cada constructor y una lección armada con ellos que pasa curso.validar."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
import curso  # noqa: E402
from curso_spec import (accion, cierre, concepto, dato, ejemplo, enfoca, fila_imagenes, gancho, imagen,  # noqa: E402
                        imagen_ancha, junto, leccion, objetivo, panel, plano_general, pregunta, pregunta_escena, resumen)


class TestConstructores(unittest.TestCase):
    def test_acciones_omiten_none(self):
        self.assertEqual(accion("aparece", "a", "hola"), {"accion": "aparece", "actor": "a", "en": "hola"})
        self.assertEqual(plano_general("ya"), {"accion": "enfoca", "en": "ya", "d": 1})
        self.assertEqual(junto("aparece", "b", retraso=0.2), {"accion": "aparece", "actor": "b", "junto": True, "retraso": 0.2})
        self.assertEqual(enfoca("a", "cuello", 3, dy=-175), {"accion": "enfoca", "actor": "a", "en": "cuello", "z": 3, "dy": -175})

    def test_actores(self):
        self.assertEqual(imagen("o", "of", -10, "Pie")["tipo"], "imagen")
        self.assertEqual((imagen_ancha("n", "nave", 0, "x")["w"], imagen_ancha("n", "nave", 0, "x")["h"]), (660, 440))
        self.assertEqual(dato("d", ["a", "b"], 0, 0)["sep"], " ")
        self.assertEqual(panel("p", 0, 0, "T")["lineas"], [])
        fila = fila_imagenes("tos", [("mando", "Mando"), ("ciencias", "Ciencias")])
        self.assertEqual([(a["id"], a["clave"], a["x"]) for a in fila], [("mando", "tos-mando", -520), ("ciencias", "tos-ciencias", 0)])

    def test_escenas_traen_ids_y_minimos_de_la_secuencia(self):
        ids = [gancho("t", "x", [])["id"], objetivo("t", "a")["id"], concepto("e3", "t", "T", [])["id"],
               ejemplo("t", "x", [], [])["id"], pregunta_escena("p1", "t", "r")["id"], resumen("t", [], [])["id"], cierre("t")["id"]]
        self.assertEqual(ids, ["e1", "e2", "e3", "e5", "e6", "e7", "e8"])
        self.assertEqual(objetivo("t", "Color", "silueta")["pantalla"]["marcas"],
                         [{"en": "Color", "texto": "Color", "color": "acento"}, {"en": "silueta", "texto": "silueta", "color": "alerta"}])


class TestLeccionValida(unittest.TestCase):
    def test_leccion_armada_con_constructores_pasa_validar(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"CURSO_RAIZ": tmp, "PROMO_TTS_STUB": "1"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(curso.main(["nuevo", "prueba"]), 0)
            base = os.path.join(tmp, "proyectos")
            c = curso.Curso(os.path.join(base, os.listdir(base)[0]))
            spec = curso.cargar(c)
            l0 = spec["modulos"][0]["lecciones"][0]
            l1 = leccion(
                l0["id"], "Tres señales", "Nombrar color, insignia y silueta como señales de lectura",
                "Lo sabrás cuando digas qué revela cada señal.", "recordar", "concepto",
                [dato("c", ["división"], -420, 0), dato("n", ["rango"], 0, 0), dato("s", ["clase"], 420, 0)],
                [gancho("Ves una escena sin sonido y aun así sabes quién manda.", "Todo está a la vista.",
                        [accion("aparece", "c", "escena")]),
                 objetivo("Al terminar vas a nombrar tres señales: color, insignia y silueta.", "color", "silueta"),
                 concepto("e3", "El color da la división, la insignia da el rango y la silueta da la clase.", "Tres señales",
                          [accion("aparece", "n", "insignia"), accion("aparece", "s", "silueta")]),
                 pregunta_escena("p1", "Comprueba lo que viste. Elige la señal del rango.",
                                 "La correcta es la insignia, porque el color indica la división."),
                 resumen("Ya lo tienes. Color, insignia y silueta.", [("Color: división", "Color"), ("Insignia: rango", "insignia")],
                         [plano_general("Ya")]),
                 cierre("En la siguiente lección vas a ubicar cada época.")],
                [pregunta("p1", l0["id"], "¿Qué señal revela el rango?", ["El color", "La insignia", "La silueta"], 1,
                          "La insignia indica el rango.", ["El color indica la división.", "Correcto: la insignia.",
                                                           "La silueta indica la clase."])],
                "Pausa una escena y escribe qué señal ves primero.", "Nombra las tres señales y lo que indica cada una.")
            spec["modulos"][0]["lecciones"][0] = {**l0, **l1}
            cfg, cur = curso.cursos_cfg()
            errores, _ = curso.validar_curso(spec, c, cur, cfg)
            self.assertEqual([e["codigo"] for e in errores], [])


if __name__ == "__main__":
    unittest.main()
