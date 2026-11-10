"""Pruebas de scripts/silencios.py (offline): cortes exactos, sincronía A/V, lista JSON, audio solo,
umbral auto y errores accionables.

  python3 -m unittest discover -s scripts/pruebas -p "test_s*.py" -v
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import silencios as sil  # noqa: E402

# Ráfagas de tono (voz simulada) y silencios exactos: 0-1, 3-4, 5-6, 6.3-7.3 → silencios de
# 2.0 s (1-3), 1.0 s (4-5), 0.3 s (6-6.3, menor que --min-silencio: se conserva) y 2.7 s al final.
PUERTA = "between(t,0,1)+between(t,3,4)+between(t,5,6)+between(t,6.3,7.3)"
SILENCIOS_IDEALES = [(1.0, 3.0), (4.0, 5.0), (7.3, 10.0)]
FPS = 30


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def crear_video(ruta, ruido=0.0):
    """testsrc2 + un cuadro indicador que se pone blanco EXACTAMENTE cuando suena el tono."""
    audio = f"aevalsrc='if({PUERTA},0.5*sin(2*PI*440*t),0)':s=48000:d=10"
    filtros = ("[0:v]drawbox=x=280:y=200:w=40:h=40:color=black:t=fill,"
               f"drawbox=x=280:y=200:w=40:h=40:color=white:t=fill:enable='{PUERTA}'[v]")
    args = ["-f", "lavfi", "-i", f"testsrc2=s=320x240:r={FPS}:d=10", "-f", "lavfi", "-i", audio]
    if ruido:
        args += ["-f", "lavfi", "-i", f"anoisesrc=a={ruido}:c=pink:r=48000:d=10"]
        filtros += ";[1:a][2:a]amix=inputs=2:normalize=0[a]"
    else:
        filtros += ";[1:a]anull[a]"
    ff(*args, "-filter_complex", filtros, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset",
       "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", "10", ruta)


def correr(argv):
    """main() capturando stdout; devuelve (código, líneas)."""
    buf = io.StringIO()
    codigo = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try:
            codigo = sil.main(argv) or 0
        except SystemExit as e:
            codigo = e.code
    return codigo, [l for l in buf.getvalue().splitlines() if l.strip()]


def inicios_audio(ruta):
    """Instantes en que arranca el tono (fin de cada silencio) medidos sobre la salida."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", ruta, "-map", "0:a:0",
                        "-af", "silencedetect=noise=-40dB:d=0.05", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", r.stderr)]


def inicios_video(ruta):
    """Instantes en que el cuadro indicador pasa de negro a blanco (luma media del recorte)."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", ruta, "-map", "0:v:0", "-vf",
                        "crop=40:40:280:200,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    t, cuadros = None, []
    for linea in r.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", linea)
        if m:
            t = float(m.group(1))
        elif "YAVG=" in linea:
            cuadros.append((t, float(linea.split("=")[1]) > 128))
    return [t for (t, on), (_, previo) in zip(cuadros[1:], cuadros[:-1]) if on and not previo]


class TestLogica(unittest.TestCase):
    def test_cortes_exactos_con_margen_y_pausa(self):
        tramos = sil.tramos_a_conservar(SILENCIOS_IDEALES, 10.0, margen=0.12, dejar=0.2)
        # colchón = margen + dejar/2 = 0.22 s por lado de la voz
        esperado = [[0.0, 1.22], [2.78, 4.22], [4.78, 7.52]]
        for (a, b), (x, y) in zip(tramos, esperado):
            self.assertAlmostEqual(a, x, places=6)
            self.assertAlmostEqual(b, y, places=6)
        quitado = 10.0 - sum(b - a for a, b in tramos)
        # 2.0 → 1.56, 1.0 → 0.56, cola 2.7 → 2.48 (en el extremo solo se deja el colchón)
        self.assertAlmostEqual(quitado, 1.56 + 0.56 + 2.48, places=6)

    def test_silencio_inicial_y_fusion_de_huecos_chicos(self):
        tramos = sil.tramos_a_conservar([(0.0, 1.5), (3.0, 3.55)], 6.0, margen=0.12, dejar=0.2)
        # inicio: se quita 0 → 1.28; el silencio de 0.55 s solo dejaría 0.11 s a quitar (< 0.15): no se corta
        self.assertEqual(len(tramos), 1)
        self.assertAlmostEqual(tramos[0][0], 1.28, places=6)
        self.assertAlmostEqual(tramos[0][1], 6.0, places=6)

    def test_tramo_diminuto_se_descarta(self):
        tramos = sil.tramos_a_conservar([(1.0, 3.0), (3.05, 5.0)], 6.0, margen=0.0, dejar=0.0)
        self.assertEqual([[round(a, 3), round(b, 3)] for a, b in tramos], [[0.0, 1.0], [5.0, 6.0]])

    def test_ajuste_a_cuadros(self):
        seg, cuadros = sil.ajustar_a_cuadros([[0.0, 1.22], [1.23, 2.0], [3.01, 9.99]], 30, 9.5)
        for a, b in seg:
            self.assertAlmostEqual(a * 30, round(a * 30), places=6)
            self.assertAlmostEqual(b * 30, round(b * 30), places=6)
        self.assertEqual(cuadros[0], [0, 60])      # 1.22→37 y 1.23→37 se tocan: se fusionan
        self.assertEqual(cuadros[-1], [90, 285])   # el final no pasa de piso(9.5·30)

    def test_umbral_auto(self):
        limpio = [(i * 0.05, -120.0, -120.0) for i in range(50)] + [(i, -6.0, -12.0) for i in range(50)]
        self.assertEqual(sil.umbral_auto(limpio)[0], -50.0)           # silencio digital → tope inferior
        ruidoso = [(i, -44.0, -54.0) for i in range(60)] + [(i, -6.0, -14.0) for i in range(40)]
        u, piso, _ = sil.umbral_auto(ruidoso)
        self.assertAlmostEqual(piso, -44.0, places=1)
        self.assertEqual(u, -38.0)                                     # pico del piso + 6 dB
        fuerte = [(i, -20.0, -30.0) for i in range(60)] + [(i, -3.0, -8.0) for i in range(40)]
        self.assertEqual(sil.umbral_auto(fuerte)[0], -25.0)           # tope superior
        continuo = [(i, -30.0, -20.0) for i in range(100)]             # casi sin pausas: guarda por la voz
        self.assertEqual(sil.umbral_auto(continuo)[0], -35.0)

    def test_fps_normalizado(self):
        self.assertEqual(sil.fps_normalizado("30/1", "30/1"), (30.0, "30"))
        f, txt = sil.fps_normalizado("120/1", "2987/100")               # VFR de teléfono
        self.assertEqual(txt, "30000/1001")
        self.assertAlmostEqual(f, 29.97, places=2)
        self.assertEqual(sil.fps_normalizado("0/0", "0/0"), (30.0, "30"))

    def test_filtergraph(self):
        g = sil.filtergraph([[0.0, 1.0], [2.0, 3.5]], 5.0, 48000, "30")
        self.assertIn("concat=n=2:v=1:a=1[v][a]", g)
        self.assertIn("atrim=start_sample=96000:end_sample=168000", g)
        self.assertIn("afade=t=in", g)
        self.assertIn("fps=30:start_time=0,split=2", g)
        self.assertNotIn("v=1", sil.filtergraph([[0.0, 1.0]], 2.0, 48000))


class TestRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = os.path.join(cls.tmp.name, "prueba.mp4")
        crear_video(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _validar_sincronia(self, salida):
        av = sil.duraciones(salida)
        self.assertLessEqual(abs(av["video"] - av["audio"]), 1 / FPS + 0.002)
        # silencedetect también reporta un silence_end al llegar al final del archivo: se descarta
        audio = [t for t in inicios_audio(salida) if t < av["audio"] - 0.05]
        video = inicios_video(salida)
        self.assertEqual(len(audio), 3, audio)   # los tonos 2, 3 y 4 (el 1 arranca en t=0)
        for t in audio:
            self.assertLessEqual(min(abs(t - v) for v in video), 1 / FPS + 0.01, (audio, video))

    def test_video_corte_sincronia_y_json(self):
        salida = os.path.join(self.tmp.name, "salida.mp4")
        codigo, lineas = correr([self.video, "--salida", salida])
        self.assertEqual(codigo, 0, lineas)
        self.assertLessEqual(len(lineas), 6)
        self.assertTrue(lineas[-1].startswith("Siguiente:"))
        with open(os.path.join(self.tmp.name, "salida.cortes.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["umbral_modo"], "auto")
        self.assertEqual(len(doc["eliminados"]), 3)
        ideal = sum(b - a for a, b in sil.tramos_a_conservar(SILENCIOS_IDEALES, 10.0))
        self.assertAlmostEqual(doc["duracion_final"], ideal, delta=0.07)   # 5.40 s ideal (±cuadros)
        self.assertAlmostEqual(sil.duraciones(salida)["audio"], doc["duracion_final"], delta=0.05)
        self._validar_sincronia(salida)

    def test_por_partes_da_lo_mismo(self):
        salida = os.path.join(self.tmp.name, "partes.mp4")
        codigo, lineas = correr([self.video, "--salida", salida, "--trozo", "2"])
        self.assertEqual(codigo, 0, lineas)
        entera = os.path.join(self.tmp.name, "entera.mp4")
        correr([self.video, "--salida", entera])
        self.assertAlmostEqual(sil.duraciones(salida)["video"], sil.duraciones(entera)["video"], delta=0.001)
        self._validar_sincronia(salida)

    def test_reporte_no_renderiza(self):
        salida = os.path.join(self.tmp.name, "reporte.mp4")
        codigo, lineas = correr([self.video, "--salida", salida, "--reporte"])
        self.assertEqual(codigo, 0)
        self.assertFalse(os.path.exists(salida))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "reporte.cortes.json")))
        self.assertTrue(lineas[0].startswith("REPORTE"))
        self.assertRegex(lineas[1], r"(1\.9\d|2\.0\d) s @1\.0")   # el silencio interno de ~2 s en el top
        self.assertLessEqual(len(lineas), 8)

    def test_solo_audio_conserva_tipo(self):
        for ext, codec in ((".wav", "pcm_s16le"), (".mp3", "mp3")):
            entrada = os.path.join(self.tmp.name, "voz" + ext)
            ff("-i", self.video, "-vn", *(["-c:a", "pcm_s16le"] if ext == ".wav" else ["-b:a", "192k"]), entrada)
            codigo, lineas = correr([entrada])
            self.assertEqual(codigo, 0, lineas)
            salida = os.path.join(self.tmp.name, "voz_sin_silencios" + ext)
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                                "-of", "csv=p=0", salida], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), f"{codec},audio")
            with open(os.path.join(self.tmp.name, f"voz_sin_silencios.cortes.json"), encoding="utf-8") as f:
                doc = json.load(f)
            tol = 0.002 if ext == ".wav" else 0.06   # mp3 agrega relleno de códec
            self.assertAlmostEqual(sil.duraciones(salida)["audio"], doc["duracion_final"], delta=tol)

    def test_umbral_auto_con_ruido(self):
        ruidoso = os.path.join(self.tmp.name, "ruido.mp4")
        crear_video(ruidoso, ruido=0.004)   # ruido rosa: RMS ≈ -63 dB, picos ≈ -53 dB
        codigo, lineas = correr([ruidoso, "--reporte"])
        self.assertEqual(codigo, 0)
        with open(os.path.join(self.tmp.name, "ruido_sin_silencios.cortes.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertTrue(-50 <= doc["umbral_db"] <= -25, doc["umbral_db"])
        self.assertGreater(doc["umbral_db"], doc["piso_ruido_db"])
        self.assertEqual(len(doc["eliminados"]), 3)   # detecta los mismos silencios pese al ruido

    def test_errores_accionables(self):
        self.assertEqual(correr([os.path.join(self.tmp.name, "no_existe.mp4")])[0], 2)
        self.assertEqual(correr([self.video, "--umbral", "fuerte"])[0], 2)
        self.assertEqual(correr([self.video, "--umbral", "-3"])[0], 2)
        self.assertEqual(correr([self.video, "--proyecto", os.path.join(self.tmp.name, "nada")])[0], 2)
        mudo = os.path.join(self.tmp.name, "mudo.mp4")
        ff("-i", self.video, "-an", "-c:v", "copy", mudo)
        self.assertEqual(correr([mudo])[0], 2)

    def test_proyecto_intermedios_en_recursos(self):
        proyecto = os.path.join(self.tmp.name, "demo_28092026")
        os.makedirs(proyecto)
        codigo, lineas = correr([self.video, "--proyecto", proyecto, "--reporte"])
        self.assertEqual(codigo, 0, lineas)
        self.assertTrue(os.path.exists(os.path.join(proyecto, "recursos", "prueba_sin_silencios.cortes.json")))
        self.assertEqual([n for n in os.listdir(os.path.join(proyecto, "recursos")) if n.startswith(".")], [])


if __name__ == "__main__":
    unittest.main()
