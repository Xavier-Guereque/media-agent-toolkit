"""Pruebas de scripts/sonido.py: cama procedural + cues, determinismo y modo archivo."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import comun  # noqa: E402
import sonido  # noqa: E402
import voz  # noqa: E402

SR = 48000


def linea_tiempo(total=6.0, musica=None, sfx="sutil", cues=None):
    return {"version": 1, "fps": 30, "w": 1080, "h": 1920, "total": total, "cuadros": int(total * 30),
            "semilla": 7, "archivo_salida": "prueba.mp4", "portada": 1.0,
            "audio": {"musica": musica or {"tipo": "procedural", "bpm": 112}, "sfx": sfx, "voz": None},
            "escenas": [], "cues": cues if cues is not None else
            [{"s": "pop", "en": 0.8, "g": 1}, {"s": "whoosh", "en": 1.5, "g": 0.8}, {"s": "exito", "en": 4.8}],
            "musica": {"bpm": 112, "secciones": [[0, 1.5, "intro"], [1.5, 4.5, "cuerpo"], [4.5, total, "cierre"]]}}


def generar(tmp, nombre, lt):
    carpeta = os.path.join(tmp, nombre)
    os.makedirs(carpeta)
    ruta_lt = os.path.join(carpeta, "linea_tiempo.json")
    with open(ruta_lt, "w") as f:
        json.dump(lt, f)
    salida = os.path.join(carpeta, "audio", "mezcla.wav")
    return sonido.generar_audio(ruta_lt, salida, imprimir=False), salida


def sha1(ruta):
    with open(ruta, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


class TestProcedural(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.res, cls.salida = generar(cls.tmp.name, "a", linea_tiempo())
        cls.res_b, cls.salida_b = generar(cls.tmp.name, "b", linea_tiempo())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_duracion_exacta_estereo_48k(self):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,duration_ts",
                            "-of", "json", self.salida], capture_output=True, text=True)
        s = json.loads(r.stdout)["streams"][0]
        self.assertEqual(int(s["sample_rate"]), SR)
        self.assertEqual(int(s["channels"]), 2)
        self.assertAlmostEqual(int(s["duration_ts"]) / SR, 6.0, delta=0.001)

    def test_sonoridad_y_true_peak(self):
        m = comun.ebur128(self.salida)
        self.assertAlmostEqual(m["I"], -14.0, delta=0.5)
        self.assertLessEqual(m["TP"], -1.5 + 0.2)
        self.assertEqual(self.res["normalizacion"], "linear")
        self.assertEqual(self.res["cues"], 3)

    def test_determinista(self):
        self.assertEqual(sha1(self.salida), sha1(self.salida_b))

    def test_pico_del_cue_en_su_muestra(self):
        """El pico del pop (ancla 'pico') cae exactamente en la muestra del cue."""
        x = sonido.muestras_mono(os.path.join(os.path.dirname(self.salida), "sfx_bus.wav"))
        i0, i1 = int(0.6 * SR), int(1.0 * SR)
        seg = [abs(v) for v in x[i0:i1]]
        self.assertEqual(seg.index(max(seg)) + i0, round(0.8 * SR))


class TestPlanYVentana(unittest.TestCase):
    def test_plan_rejilla_anclada_al_cuerpo(self):
        p = sonido.plan_musical(linea_tiempo(total=30.0) | {"musica": {"secciones": [
            [0, 3.5, "intro"], [3.5, 24.5, "cuerpo"], [24.5, 30, "cierre"]]}}, 112)
        self.assertEqual(p["g0"], 3.5)
        pulsos = (p["cs"] - p["g0"]) / p["B"]
        self.assertAlmostEqual(pulsos, round(pulsos), places=6)      # el cierre cae en un pulso
        self.assertAlmostEqual(p["th"], p["cs"] + p["BAR"], places=6)  # 1 compás de kick y golpe

    def test_elegir_ventana(self):
        perfil = [-44.0] * 14 + [-15.0] * 12 + [-44.0] * 14
        self.assertEqual(sonido.elegir_ventana(perfil, 6.0), 14.0)
        self.assertEqual(sonido.elegir_ventana(perfil[:5], 6.0), 0.0)   # pista corta: desde 0 (bucle)



class TestArchivo(unittest.TestCase):
    def test_archivo_sin_inicio_elige_ventana_fuerte(self):
        with tempfile.TemporaryDirectory() as tmp:
            pista = os.path.join(tmp, "pista.wav")
            # 40 s: silencio relativo, zona fuerte 14–26 s, silencio relativo.
            comun.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                       "aevalsrc='(0.02+0.5*between(t,14,26))*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*2*t))':s=44100:d=40",
                       "-ac", "2", pista])
            lt = linea_tiempo(total=8.0, musica={"tipo": "archivo", "archivo": pista, "inicio": None},
                              cues=[{"s": "tick", "en": 2.0}])
            res, salida = generar(tmp, "arch", lt)
            inicio = float(res["musica"].split("desde ")[1].split(" s")[0])
            self.assertGreaterEqual(inicio, 14.0)
            self.assertLessEqual(inicio, 26.0 - 8.0)
            self.assertAlmostEqual(comun.ebur128(salida)["I"], -14.0, delta=0.5)
            self.assertAlmostEqual(comun.dur(salida), 8.0, delta=0.001)

    def test_ninguna_y_silencio(self):
        with tempfile.TemporaryDirectory() as tmp:
            res, salida = generar(tmp, "sil", linea_tiempo(total=3.0, musica={"tipo": "ninguna"}, sfx="ninguno"))
            self.assertEqual(res["normalizacion"], "silencio")
            self.assertAlmostEqual(comun.dur(salida), 3.0, delta=0.001)


class TestPerfiles(unittest.TestCase):
    """Mezcla con voz, sin música y fuentes CC0 (con la red sustituida)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = os.path.join(self.tmp.name, "recursos")
        os.makedirs(os.path.join(self.rec, "promo"))

    def tearDown(self):
        self.tmp.cleanup()

    def escribir_lt(self, lt):
        ruta = os.path.join(self.rec, "promo", "linea_tiempo.json")
        with open(ruta, "w") as f:
            json.dump(lt, f)
        return ruta

    def test_mezcla_con_voz_30s_6_lineas(self):
        """Criterios de aceptación del perfil con voz (2026-09-28): -14 ±0.5 LUFS, TP ≤ -1.5 ya en AAC,
        LRA ≤ 10, voz ≥ 9 dB sobre la música atenuada, música ≥ -30 LUFS en pausas, modo lineal."""
        os.makedirs(os.path.join(self.rec, "voz"))
        textos = ["Cotiza con nosotros, sin esperar.", "Recíbela al instante.", "Compara precios en segundos.",
                  "Todo con existencias reales.", "Pídela por el chat.", "Y llega a tu obra."]
        lineas = []
        for j, texto in enumerate(textos):
            pcm, sr, _, _ = voz.tts_simulado(texto)
            archivo = f"voz/l{j + 1}_0.wav"
            voz.guardar_toma(pcm, sr, os.path.join(self.rec, archivo), os.path.join(self.rec, "voz"))
            lineas.append({"escena": j + 1, "frase": 0, "texto": texto, "archivo": archivo, "en": 2.6 + 3.9 * j,
                           "dur": comun.dur(os.path.join(self.rec, archivo))})
        lt = linea_tiempo(total=30.0, cues=[{"s": "whoosh", "en": 2.4, "g": 0.55}, {"s": "pop", "en": 9.0}])
        lt["audio"]["voz"] = {"voz": "coral"}
        lt["voz"] = {"voz": "coral", "pendiente": False, "lineas": lineas}
        lt["musica"]["secciones"] = [[0, 2.5, "intro"], [2.5, 26.0, "cuerpo"], [26.0, 30.0, "cierre"]]
        salida = os.path.join(self.rec, "audio", "mezcla.wav")
        res = sonido.generar_audio(self.escribir_lt(lt), salida, imprimir=False)
        self.assertEqual(res["normalizacion"], "linear")
        self.assertAlmostEqual(res["duracion"], 30.0, delta=0.001)
        self.assertLessEqual(res["LRA"], 10.0)
        aac = os.path.join(self.rec, "audio", "m.m4a")
        comun.run(["ffmpeg", "-y", "-v", "error", "-i", salida, "-c:a", "aac", "-b:a", "256k", aac])
        m = comun.ebur128(aac)
        self.assertAlmostEqual(m["I"], -14.0, delta=0.5)
        self.assertLessEqual(m["TP"], -1.5)
        x = res["inteligibilidad"]
        self.assertGreaterEqual(x["margen"], 9.0)
        self.assertGreaterEqual(x["pausa"], -30.0)
        self.assertEqual(x["avisos"], [])
        # La música atenuada llega completa al final (sidechaincompress recortaba la cola).
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=duration_ts", "-of", "csv=p=0",
                            os.path.join(self.rec, "audio", "musica_duck.wav")], capture_output=True, text=True)
        self.assertEqual(int(r.stdout.strip()), 30 * SR)

    def test_voz_pendiente_sale_2(self):
        lt = linea_tiempo(total=4.0)
        lt["audio"]["voz"] = {"voz": "coral"}
        lt["voz"] = {"pendiente": True, "lineas": []}
        with self.assertRaises(SystemExit) as e:
            sonido.generar_audio(self.escribir_lt(lt), os.path.join(self.rec, "audio", "m.wav"), imprimir=False)
        self.assertEqual(e.exception.code, 2)

    def test_sin_musica_no_sube_a_menos_14(self):
        lt = linea_tiempo(total=4.0, musica={"tipo": "ninguna"}, cues=[{"s": "ping", "en": 1.0}, {"s": "exito", "en": 2.5}])
        res = sonido.generar_audio(self.escribir_lt(lt), os.path.join(self.rec, "audio", "m.wav"), imprimir=False)
        self.assertEqual(res["normalizacion"], "sin_loudnorm")
        self.assertLess(res["I"], -20.0)                           # efectos a su nivel, no a -14
        self.assertLessEqual(res["TP"], -1.5 + 0.2)

    def stock(self):
        d = os.path.join(self.tmp.name, "stock")
        os.makedirs(d)
        recetas = {"loop.mp3": ("0.3*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*1.87*t))", 5),
                   "golpe.mp3": ("0.8*exp(-t*30)*sin(2*PI*900*t)", 0.6), "plano.mp3": ("0.2*sin(2*PI*300*t)", 2)}
        for nombre, (expr, d_s) in recetas.items():
            comun.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={d_s}",
                       "-ac", "2", os.path.join(d, nombre)])
        return lambda n: {"ruta": os.path.join(d, n), "archivo": n, "titulo": n, "autor": "prueba",  # noqa: E731
                          "licencia": "cc0", "origen_url": f"https://freesound.org/{n}", "sha256": "0" * 64}

    def test_cc0_musica_en_bucle_sfx_y_respaldos(self):
        item = self.stock()
        llamadas = []

        def falso(q, n, perfil, **kw):
            llamadas.append((q, perfil))
            if perfil == "any":
                return [item("loop.mp3")]                          # nada ≥ total: loop corto
            if perfil == "sfx" and q == "pop":
                return [item("plano.mp3"), item("golpe.mp3")]       # gana el corto con transitorio
            if perfil == "sfx" and q == "ui click":
                return [item("plano.mp3")]                          # sin transitorio: receta
            return []
        original = sonido._obtener_cc0
        sonido._obtener_cc0 = falso
        try:
            lt = linea_tiempo(total=12.0, musica={"tipo": "cc0", "busqueda": "tech loop"},
                              cues=[{"s": "pop", "en": 2.0}, {"s": "tick", "en": 4.0}])
            lt["audio"]["sfx_fuente"] = "cc0"
            ruta_lt = self.escribir_lt(lt)
            salida = os.path.join(self.rec, "audio", "mezcla.wav")
            res = sonido.generar_audio(ruta_lt, salida, imprimir=False)
            self.assertIn("cc0 loop.mp3", res["musica"])
            self.assertAlmostEqual(comun.dur(salida), 12.0, delta=0.001)
            self.assertEqual({(c["uso"], c["archivo"]) for c in res["creditos"]},
                             {("musica", "loop.mp3"), ("sfx:pop", "golpe.mp3")})
            self.assertTrue(any("tick" in a for a in res["avisos"]))
            cc0 = os.path.join(self.rec, "audio", "cc0")
            for f in ("loop.mp3", "golpe.mp3", "creditos.json", "seleccion.json"):
                self.assertTrue(os.path.exists(os.path.join(cc0, f)), f)
            antes = len(llamadas)
            sonido.generar_audio(ruta_lt, salida, imprimir=False)
            self.assertEqual(len(llamadas), antes)                 # 2a corrida: 0 consultas (caché)
        finally:
            sonido._obtener_cc0 = original

    def test_cc0_vacio_se_reintenta_a_las_24h_o_con_refrescar(self):
        llamadas = []
        original = sonido._obtener_cc0
        sonido._obtener_cc0 = lambda q, n, perfil, **kw: llamadas.append((q, perfil)) or []
        try:
            lt = linea_tiempo(total=4.0, musica={"tipo": "cc0", "busqueda": "nada"}, cues=[{"s": "pop", "en": 1.0}])
            lt["audio"]["sfx_fuente"] = "cc0"
            ruta_lt, salida = self.escribir_lt(lt), os.path.join(self.rec, "audio", "m.wav")
            sonido.generar_audio(ruta_lt, salida, imprimir=False)
            primera = len(llamadas)
            self.assertEqual(primera, 3)                     # bgm + any (música) + sfx (pop)
            sonido.generar_audio(ruta_lt, salida, imprimir=False)
            self.assertEqual(len(llamadas), primera)         # < 24 h: no se repite
            sonido.generar_audio(ruta_lt, salida, imprimir=False, refrescar_cc0=True)
            self.assertEqual(len(llamadas), 2 * primera)     # --refrescar-cc0: ya
            sel = os.path.join(self.rec, "audio", "cc0", "seleccion.json")
            with open(sel) as f:
                datos = json.load(f)
            for v in datos.values():
                v["ts"] -= 25 * 3600                          # hace 25 h
            with open(sel, "w") as f:
                json.dump(datos, f)
            sonido.generar_audio(ruta_lt, salida, imprimir=False)
            self.assertEqual(len(llamadas), 3 * primera)     # vencido: se reintenta
        finally:
            sonido._obtener_cc0 = original

    def test_cc0_sin_resultados_respaldo_procedural(self):
        original = sonido._obtener_cc0
        sonido._obtener_cc0 = lambda q, n, perfil, **kw: []
        try:
            lt = linea_tiempo(total=6.0, musica={"tipo": "cc0"}, cues=[])
            res = sonido.generar_audio(self.escribir_lt(lt), os.path.join(self.rec, "audio", "m.wav"), imprimir=False)
            self.assertIn("procedural", res["musica"])
            self.assertIn("AVISO sin CC0", res["musica"])
            self.assertAlmostEqual(res["I"], -14.0, delta=0.5)
        finally:
            sonido._obtener_cc0 = original


if __name__ == "__main__":
    unittest.main()
