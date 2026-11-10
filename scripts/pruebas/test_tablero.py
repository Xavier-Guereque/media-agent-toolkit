"""Pruebas de scripts/tablero.py: elección del proyecto reciente y lectura de avance.jsonl (sin servidor)."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import tablero  # noqa: E402


class TestTablero(unittest.TestCase):
    def test_proyecto_reciente_ignora_enrutador_y_carpetas_sin_fecha(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nombre in ("viejo_01102026", "nuevo_30102026", "_enrutador", "sin_fecha", "a_b"):
                os.makedirs(os.path.join(tmp, "proyectos", nombre))
            ahora = time.time()
            os.utime(os.path.join(tmp, "proyectos", "nuevo_30102026"), (ahora - 100, ahora - 100))
            for nombre in ("_enrutador", "sin_fecha", "a_b"):   # los más recientes, pero no son proyectos
                os.utime(os.path.join(tmp, "proyectos", nombre), (ahora, ahora))
            os.utime(os.path.join(tmp, "proyectos", "viejo_01102026"), (ahora - 500, ahora - 500))
            with mock.patch.object(tablero, "REPO", tmp):
                self.assertEqual(os.path.basename(tablero.proyecto_reciente()), "nuevo_30102026")
            with mock.patch.object(tablero, "REPO", os.path.join(tmp, "vacio")):
                with self.assertRaises(SystemExit):
                    tablero.proyecto_reciente()

    def test_estado_termina_solo_con_estado_listo(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = os.path.join(tmp, "recursos")
            os.makedirs(rec)
            lineas = [{"ts": 1.0, "etapa": "imagen", "pct": 0, "detalle": "solicitando", "estado": "en_curso"},
                      {"ts": 9.0, "etapa": "imagen", "pct": 100, "detalle": "1 imagen", "estado": "listo"}]
            with open(os.path.join(rec, "avance.jsonl"), "w") as f:
                f.write("\n".join(json.dumps(l) for l in lineas) + "\n")
            with mock.patch.object(tablero, "PROYECTO", tmp):
                e = tablero.estado()
            self.assertTrue(e["terminado"])
            self.assertEqual((e["etapas"][0]["id"], e["etapas"][0]["pct"], e["etapas"][0]["fin"]), ("imagen", 100.0, 9.0))
            # un estado desconocido (p. ej. "ok") no cierra la etapa: así se detectó el fallo de imagen.py/reemplazar_personaje.py
            with open(os.path.join(rec, "avance.jsonl"), "a") as f:
                f.write(json.dumps({"ts": 10.0, "etapa": "reemplazo", "pct": 100, "detalle": "x", "estado": "ok"}) + "\n")
            with mock.patch.object(tablero, "PROYECTO", tmp):
                self.assertFalse(tablero.estado()["terminado"])


if __name__ == "__main__":
    unittest.main()
