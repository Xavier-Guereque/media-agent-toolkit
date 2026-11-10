"""Pruebas de scripts/subtitulos.py. Offline por defecto (la transcripción se sustituye por stubs).

  python3 -m unittest discover -s scripts/pruebas -p "test_s*.py" -v
  SUBT_ONLINE=1 python3 -m unittest scripts/pruebas/test_subtitulos.py -v   # + prueba real (~$0.001)
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import comun  # noqa: E402
import silencios as sil  # noqa: E402
import subtitulos as st  # noqa: E402

# Ráfagas "tipo voz" (tono de 180 Hz modulado a 4 Hz, ritmo silábico) con pausas conocidas:
#   0.5-2.5 · 2.9-3.2 (corta: se fusiona) · 4.7-9.0 · [hueco de 0.2 s] · 9.2-13.7 · 15.7-16.2 (aislada)
PUERTA = ("between(t,0.5,2.5)+between(t,2.9,3.2)+between(t,4.7,9.0)+between(t,9.2,13.7)"
          "+between(t,15.7,16.2)")
ESPERADOS = [(0.5, 3.2), (4.7, 9.0), (9.2, 13.7), (15.7, 16.2)]
TEXTOS = ["Hola, bienvenidos al canal de acme.",
          "Hoy instalamos una cámara Hikvision de 4 megapíxeles a 250 m del grabador.",
          "Después configuramos la aplicación y el acceso remoto desde el teléfono.",
          "Gracias."]


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def crear_medio(ruta, video=True, dur=17.5, s="360x640"):
    audio = f"aevalsrc='if({PUERTA},0.35*sin(2*PI*180*t)*(0.55+0.45*sin(2*PI*4*t)),0)':s=48000:d={dur}"
    args = (["-f", "lavfi", "-i", f"testsrc2=s={s}:r=30:d={dur}"] if video else []) + ["-f", "lavfi", "-i", audio]
    cod = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"] if video else []
    ff(*args, *cod, "-c:a", "aac" if ruta.endswith((".mp4", ".m4a")) else "pcm_s16le", "-t", str(dur), ruta)


def correr(argv):
    buf, codigo = io.StringIO(), 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try:
            codigo = st.main(argv) or 0
        except SystemExit as e:
            codigo = e.code
    return codigo, [l for l in buf.getvalue().splitlines() if l.strip()]


def respuesta_falsa(textos_por_indice, faltantes=()):
    """Stub de enviar_openrouter: contesta el JSON de los fragmentos que vienen en la petición."""
    llamadas = []

    def enviar(cuerpo, key):
        partes = cuerpo["messages"][1]["content"]
        indices = [int(m.group(1)) for p in partes if p["type"] == "text"
                   for m in [re.match(r"Fragmento (\d+):", p["text"])] if m]
        llamadas.append({"indices": indices, "audios": sum(p["type"] == "input_audio" for p in partes),
                         "formato": cuerpo.get("response_format")})
        omitir = set(faltantes) if len(llamadas) == 1 else set()
        seg = [{"i": i, "texto": textos_por_indice(i)} for i in indices if i not in omitir]
        return {"id": f"gen-prueba-{len(llamadas)}", "usage": {"cost": 0.001, "prompt_tokens": 10},
                "choices": [{"message": {"content": "```json\n" + json.dumps({"segmentos": seg}) + "\n```"}}]}
    return enviar, llamadas


class TestTexto(unittest.TestCase):
    def test_silabas(self):
        for palabra, n in (("hola", 2), ("tarea", 3), ("ciudad", 2), ("país", 2), ("guerra", 2),
                           ("ACME", 2), ("IP", 2), ("250", 6), ("aplicación", 4), ("muy", 1), ("y", 1)):
            self.assertEqual(st.silabas(palabra), n, palabra)

    def test_tokenizar_pega_numero_y_unidad(self):
        self.assertEqual(st.tokenizar("a 250 m del grabador"), ["a", "250\u00a0m", "del", "grabador"])
        self.assertEqual(st.tokenizar("el 20 por ciento de"), ["el", "20\u00a0por\u00a0ciento", "de"])
        self.assertEqual(st.tokenizar("son 3.5 GB, y"), ["son", "3.5\u00a0GB,", "y"])
        self.assertEqual(st.tokenizar("en 2027 vamos"), ["en", "2027", "vamos"])

    def test_cortar_lineas_equilibrado(self):
        tokens = st.tokenizar("Primero conectamos el cable de red a 250 m del grabador.")
        lineas = st.cortar_lineas(tokens, 32)
        self.assertEqual(len(lineas), 2)
        self.assertTrue(all(len(l) <= 32 for l in lineas))
        self.assertFalse(lineas[0].split()[-1] in st.FUNCIONALES, lineas)
        self.assertFalse(any(l.endswith("250") or l.startswith("m ") for l in lineas))
        self.assertIsNone(st.cortar_lineas(st.tokenizar("x " * 40), 16))

    def test_dividir_en_cues(self):
        texto = ("Hoy vamos a instalar una cámara de cuatro megapíxeles, paso a paso, para que puedas "
                 "hacerlo tú mismo en casa o en tu negocio sin complicaciones.")
        tokens = st.tokenizar(texto)
        grupos = st.dividir_en_cues(tokens, 9.0, 32)
        self.assertGreaterEqual(len(grupos), 3)
        self.assertEqual(grupos[0][0], 0)
        self.assertEqual(grupos[-1][1], len(tokens))
        for i, j in grupos:
            self.assertIsNotNone(st.cortar_lineas(tokens[i:j], 32))
            self.assertNotIn(st._limpio(tokens[j - 1]), {"de", "la", "el", "una"})
        # un texto corto en un fragmento largo se parte para no pasar de 6 s
        largo = st.dividir_en_cues(st.tokenizar("Esto es una prueba larga, con pausa."), 7.0, 32)
        self.assertEqual(len(largo), 2)

    def test_glosario(self):
        self.assertEqual(st.corregir_glosario("Acme y hikvision por Whatsapp", ["ACME", "HIKVISION", "WhatsApp"]),
                         "ACME y HIKVISION por WhatsApp")

    def test_ajustar_tiempos(self):
        cues = [{"ini": 1.0, "fin": 1.3, "lineas": ["Sí."], "ultimo": True},
                {"ini": 1.5, "fin": 9.5, "lineas": ["largo"], "ultimo": True}]
        a, b = st.ajustar_tiempos(cues, total=10.0)
        self.assertGreaterEqual(b["ini"] - a["fin"], st.SEPARACION - 1e-9)   # sin traslape
        self.assertLessEqual(b["fin"] - b["ini"], st.CUE_MAX + 1e-9)
        # el siguiente cue no deja alargar el final: el mínimo de 0.8 s se logra adelantando el inicio
        self.assertAlmostEqual(a["fin"] - a["ini"], st.CUE_MIN)
        self.assertAlmostEqual(a["fin"], 1.5 - st.SEPARACION)
        solo = st.ajustar_tiempos([{"ini": 2.0, "fin": 2.3, "lineas": ["Ok."], "ultimo": True}], 10.0)
        self.assertAlmostEqual(solo[0]["ini"], 1.95)                        # anticipo de 50 ms
        self.assertGreaterEqual(solo[0]["fin"] - solo[0]["ini"], st.CUE_MIN - 1e-9)

    def test_srt_vtt_y_lectura(self):
        cues = [{"ini": 0.0, "fin": 1.5, "lineas": ["Hola,", "mundo 250\u00a0m"]},
                {"ini": 3661.25, "fin": 3662.0, "lineas": ["Fin."]}]
        srt = st.a_srt(cues)
        self.assertEqual(srt, "1\n00:00:00,000 --> 00:00:01,500\nHola,\nmundo 250 m\n\n"
                              "2\n01:01:01,250 --> 01:01:02,000\nFin.\n")
        vtt = st.a_vtt(cues)
        self.assertTrue(vtt.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.500\n"))
        leidos = st.leer_srt("\ufeff" + srt.replace("\n", "\r\n").replace("Fin.", "<i>Fin.</i>"))
        self.assertEqual(len(leidos), 2)
        self.assertEqual(leidos[1]["lineas"], ["Fin."])
        self.assertAlmostEqual(leidos[1]["ini"], 3661.25)
        self.assertEqual(len(st.leer_srt("1\n00:00:01.5 --> 00:00:02.0\nsin coma\n")), 1)

    def test_ass_vertical_y_horizontal(self):
        cues = [{"ini": 1.0, "fin": 2.5, "lineas": ["Hola {x}", "a 250\u00a0m"]}]
        v = st.a_ass(cues, 1080, 1920)
        self.assertIn("PlayResX: 1080\nPlayResY: 1920", v)
        estilo = [l for l in v.splitlines() if l.startswith("Style: Sub")][0].split(",")
        self.assertEqual(estilo[2], "56")                  # fuente 56 px
        self.assertEqual(estilo[15], "4")                  # BorderStyle 4: una caja por evento
        self.assertEqual(estilo[6], "&H30000000")          # caja oscura semiopaca
        margen_v, relleno = int(estilo[21]), int(estilo[16])
        self.assertLessEqual(1920 - margen_v + relleno, 1500)   # la caja queda arriba de y=1500
        self.assertIn("Dialogue: 0,0:00:01.00,0:00:02.50,Sub,,0,0,0,,Hola (x)\\Na 250\\hm", v)
        h = [l for l in st.a_ass(cues, 1920, 1080, "clasico").splitlines() if l.startswith("Style: Sub")][0].split(",")
        self.assertEqual((h[2], h[15], h[21]), ("46", "1", "70"))
        c = [l for l in st.a_ass(cues, 1080, 1920, posicion="centro").splitlines() if l.startswith("Style")][0]
        self.assertEqual(c.split(",")[18], "5")
        viejo = st.a_ass(cues, 1080, 1920, libass=0x01500000)
        self.assertIn(",3,17,0,2,", viejo)
        self.assertIn("\\ybord", viejo)

    def test_escape_de_ruta(self):
        self.assertEqual(st.escapar_ruta_filtro("/a b/c:d.ass"), "/a b/c\\\\:d.ass")
        self.assertEqual(st.escapar_ruta_filtro("/x,y[1]/z.ass"), "/x\\,y\\[1\\]/z.ass")


class TestSegmentacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.wav = os.path.join(cls.tmp.name, "rafagas.wav")
        crear_medio(cls.wav, video=False)
        cls.niveles = sil.perfil_niveles(sil.extraer_analisis(cls.wav, os.path.join(cls.tmp.name, "a16.wav")))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_fragmentos_por_pausas(self):
        a16 = os.path.join(self.tmp.name, "a16.wav")
        umbral = sil.umbral_auto(self.niveles)[0]
        trozos = st.segmentar(a16, 17.5, umbral, self.niveles)
        self.assertEqual(len(trozos), len(ESPERADOS), trozos)
        for (a, b), (x, y) in zip(trozos, ESPERADOS):
            self.assertAlmostEqual(a, x, delta=0.03)
            self.assertAlmostEqual(b, y, delta=0.03)

    def test_partir_parejo_sin_pausas(self):
        piezas = st.partir_largos([[0.0, 15.0]], lambda a, b: [], lambda t: round(t))
        self.assertEqual(len(piezas), 3)
        self.assertTrue(all(b - a <= st.TROZO_MAX for a, b in piezas))
        self.assertEqual(piezas[0][0], 0.0)
        self.assertEqual(piezas[-1][1], 15.0)

    def test_fusionar_respeta_huecos_grandes(self):
        self.assertEqual(st.fusionar_cortos([[0, 2], [2.3, 2.6], [5, 5.4]]), [[0, 2.6], [5, 5.4]])


class TestTranscripcion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.wav = os.path.join(cls.tmp.name, "a.wav")
        crear_medio(cls.wav, video=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lotes_validacion_y_reintento(self):
        trozos = [[i * 0.6, i * 0.6 + 0.5] for i in range(25)]
        enviar, llamadas = respuesta_falsa(lambda i: f"texto {i}", faltantes=(3,))
        log = os.path.join(self.tmp.name, "log")
        textos, costo, n, faltan = st.transcribir_openrouter(
            trozos, self.wav, os.path.join(self.tmp.name, "trab"), "es", ["ACME"], "modelo/prueba", "k", log,
            enviar=enviar)
        self.assertEqual(sorted(textos), list(range(1, 26)))
        self.assertEqual(faltan, [])
        self.assertEqual(n, 3)                                    # 2 lotes (20 + 5) + reintento del 3
        self.assertEqual([c["audios"] for c in llamadas], [20, 5, 1])
        self.assertEqual(llamadas[2]["indices"], [3])
        self.assertEqual(llamadas[0]["formato"], {"type": "json_object"})
        self.assertAlmostEqual(costo, 0.003)
        with open(os.path.join(log, "costos.jsonl"), encoding="utf-8") as f:
            lineas = [json.loads(l) for l in f]
        self.assertEqual({l["tarea"] for l in lineas}, {"subtitulos"})
        self.assertEqual(len(lineas), 3)
        self.assertEqual([x for x in os.listdir(os.path.join(self.tmp.name, "trab")) if x.endswith(".mp3")], [])

    def test_asignar_palabras(self):
        palabras = [(0.1, 0.4, "Hola"), (0.5, 0.9, "mundo"), (5.0, 5.4, "suelta"), (8.0, 8.5, "adiós")]
        res = st.asignar_palabras([[0.0, 1.0], [7.9, 9.0]], palabras)
        self.assertEqual([[w for _, _, w in ps] for _, ps in res], [["Hola", "mundo"], ["suelta"], ["adiós"]])
        self.assertEqual(res[1][0], [5.0, 5.4])

    def test_palabras_elevenlabs(self):
        resp = {"words": [{"text": "Hola", "start": 0.1, "end": 0.4, "type": "word"},
                          {"text": " ", "start": 0.4, "end": 0.5, "type": "spacing"}]}
        self.assertEqual(st.palabras_elevenlabs(resp), [(0.1, 0.4, "Hola")])


class TestMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = os.path.join(cls.tmp.name, "clip.mp4")
        crear_medio(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _stub(self):
        enviar, llamadas = respuesta_falsa(lambda i: TEXTOS[i - 1])
        return mock.patch.object(st, "enviar_openrouter", enviar), llamadas

    def test_openrouter_srt_vtt_quemado_y_cache(self):
        destino = os.path.join(self.tmp.name, "salida")
        parche, llamadas = self._stub()
        with parche, mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "prueba-offline"}):
            codigo, lineas = correr([self.video, "--proveedor", "openrouter", "--quemar", "--salida", destino,
                                     "--glosario", "ACME,HIKVISION"])
        self.assertEqual(codigo, 0, lineas)
        self.assertLessEqual(len(lineas), 8)
        self.assertTrue(lineas[-1].startswith("Siguiente:"))
        self.assertEqual(len(llamadas), 1)
        with open(os.path.join(destino, "clip.srt"), encoding="utf-8") as f:
            srt = f.read()
        cues = st.leer_srt(srt)
        self.assertIn("ACME.", srt)
        self.assertIn("HIKVISION", srt)
        self.assertTrue(all(len(l) <= 32 for c in cues for l in c["lineas"]))
        self.assertFalse(re.search(r"250\n", srt))                    # nunca "250 | m"
        for c in cues:                                                 # tiempos dentro de su fragmento
            dentro = [(a, b) for a, b in ESPERADOS if a - 0.1 <= c["ini"] and c["fin"] <= b + 0.5]
            self.assertTrue(dentro, c)
            self.assertGreaterEqual(c["fin"] - c["ini"], st.CUE_MIN - 0.002)
        with open(os.path.join(destino, "clip.vtt"), encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("WEBVTT"))
        quemado = os.path.join(destino, "clip_subtitulado.mp4")
        self.assertAlmostEqual(sil.duraciones(quemado)["formato"], sil.duraciones(self.video)["formato"], delta=0.05)
        self.assertGreater(self._pixeles_distintos(self.video, quemado, 1.5), 500)
        # segunda corrida: todo sale de la caché, sin llamadas
        parche, llamadas = self._stub()
        with parche, mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "prueba-offline"}):
            codigo, lineas = correr([self.video, "--proveedor", "openrouter", "--salida", destino,
                                     "--glosario", "ACME,HIKVISION", "--formatos", "srt"])
        self.assertEqual((codigo, len(llamadas)), (0, 0))
        self.assertIn("caché", lineas[0])

    @staticmethod
    def _pixeles_distintos(a, b, t):
        def cuadro(ruta):
            return subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(t), "-i", ruta, "-frames:v", "1",
                                   "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        x, y = cuadro(a), cuadro(b)
        return sum(1 for p, q in zip(x, y) if abs(p - q) > 40)

    def test_whisper_stub_usa_marcas_por_palabra(self):
        palabras = [(0.55, 0.9, "Hola,"), (1.0, 1.6, "bienvenidos"), (1.7, 2.4, "todos."),
                    (4.8, 5.5, "Segunda"), (5.6, 6.3, "parte.")]

        class Modelo:
            def __init__(self, *a, **k):
                pass

            def transcribe(self, *a, **k):
                seg = types.SimpleNamespace(words=[types.SimpleNamespace(start=s, end=e, word=" " + w)
                                                   for s, e, w in palabras])
                return iter([seg]), None
        falso = types.ModuleType("faster_whisper")
        falso.WhisperModel = Modelo
        destino = os.path.join(self.tmp.name, "whisper")
        with mock.patch.dict(sys.modules, {"faster_whisper": falso}):
            codigo, lineas = correr([self.video, "--salida", destino, "--formatos", "srt"])
        self.assertEqual(codigo, 0, lineas)
        self.assertIn("whisper (small)", lineas[0])
        with open(os.path.join(destino, "clip.srt"), encoding="utf-8") as f:
            cues = st.leer_srt(f.read())
        self.assertEqual([" ".join(c["lineas"]) for c in cues], ["Hola, bienvenidos todos.", "Segunda parte."])
        self.assertAlmostEqual(cues[1]["ini"], 4.7 - st.ANTICIPO, delta=0.03)

    def test_desde_srt_convierte_sin_transcribir(self):
        destino = os.path.join(self.tmp.name, "desde")
        os.makedirs(destino)
        srt = os.path.join(destino, "propio.srt")
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nHola\n")
        codigo, lineas = correr([self.video, "--desde-srt", srt, "--formatos", "vtt", "--salida", destino])
        self.assertEqual(codigo, 0, lineas)
        with open(os.path.join(destino, "clip.vtt"), encoding="utf-8") as f:
            self.assertIn("00:00:01.000 --> 00:00:02.000\nHola", f.read())

    def test_errores(self):
        audio = os.path.join(self.tmp.name, "solo.wav")
        crear_medio(audio, video=False, dur=3)
        self.assertEqual(correr([audio, "--quemar"])[0], 2)
        self.assertEqual(correr([self.video, "--formatos", "ass"])[0], 2)
        self.assertEqual(correr([self.video, "--max-car", "5"])[0], 2)
        with mock.patch.object(comun, "api_key", side_effect=SystemExit(3)):
            self.assertEqual(correr([self.video, "--proveedor", "elevenlabs",
                                     "--salida", os.path.join(self.tmp.name, "el")])[0], 3)
        with mock.patch.dict(sys.modules, {"faster_whisper": None}):
            self.assertEqual(correr([self.video, "--proveedor", "whisper",
                                     "--salida", os.path.join(self.tmp.name, "wh")])[0], 3)


@unittest.skipUnless(os.environ.get("SUBT_ONLINE") == "1", "prueba en línea: exporta SUBT_ONLINE=1 (~$0.001)")
class TestEnLinea(unittest.TestCase):
    def test_openrouter_con_voz_paulina(self):
        if not shutil.which("say"):
            self.skipTest("`say` solo existe en macOS")
        with tempfile.TemporaryDirectory() as tmp:
            for i, frase in enumerate(("Hola, bienvenidos al canal de ACME.",
                                       "Hoy instalamos una cámara HIKVISION en la oficina."), 1):
                subprocess.run(["say", "-v", "Paulina", "-o", os.path.join(tmp, f"f{i}.aiff"), frase], check=True)
            video = os.path.join(tmp, "voz.mp4")
            ff("-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=9", "-i", os.path.join(tmp, "f1.aiff"),
               "-i", os.path.join(tmp, "f2.aiff"), "-filter_complex",
               "[1:a]adelay=500:all=1,apad=pad_dur=1.2[a1];[a1][2:a]concat=n=2:v=0:a=1,apad=whole_dur=9[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-t", "9", video)
            codigo, lineas = correr([video, "--proveedor", "openrouter", "--glosario", "ACME,HIKVISION",
                                     "--formatos", "srt"])
            print("\n" + "\n".join(lineas))
            self.assertEqual(codigo, 0, lineas)
            with open(os.path.join(tmp, "voz.srt"), encoding="utf-8") as f:
                srt = f.read()
            print(srt)
            for palabra in ("bienvenidos", "ACME", "cámara", "HIKVISION"):
                self.assertIn(palabra.lower(), srt.lower())


if __name__ == "__main__":
    unittest.main()
