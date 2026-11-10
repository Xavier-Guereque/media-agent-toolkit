"""Pruebas de scripts/promo.py con una raíz temporal (--raiz) y un motor Node simulado (PROMO_MOTOR).

Nunca escriben en el proyectos/ real del repo.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(AQUI)
REPO = os.path.dirname(SCRIPTS)
PROMO = os.path.join(SCRIPTS, "promo.py")
sys.path.insert(0, SCRIPTS)
import comun  # noqa: E402

# Motor simulado: responde según STUB_MODO, con el contrato de promo/motor.mjs (un JSON en stdout).
MOTOR_STUB = r"""
import fs from 'node:fs';
import path from 'node:path';
const modo = process.env.STUB_MODO || 'errores';
const out = (o, c) => { process.stdout.write(JSON.stringify(o) + '\n'); process.exit(c); };
process.stderr.write('log del motor que no debe verse sin --verbose\n');
if (modo === 'errores') out({ ok: false, errores: [{ codigo: 'E-TXT-LARGO', severidad: 'E',
  ruta: 'escenas[1].titular', t: 6.4, msg: '19 palabras (máx 16).', arreglo: 'Quita 3 palabras.' }],
  avisos: [{ codigo: 'W-QA-CRUCE', severidad: 'W', ruta: 'escenas[2].lema', msg: 'se encima.' }],
  resumen: { total: 10, cuadros: 300, escenas: [] } }, 2);
if (modo === 'ok') out({ ok: true, errores: [], avisos: [], resumen: { total: 10, cuadros: 300,
  escenas: [{ id: 'e1', tipo: 'intro', ini: 0, fin: 3 }] } }, 0);
if (modo === 'entorno') out({ ok: false, errores: [{ codigo: 'E-ENTORNO', severidad: 'E', ruta: '-',
  msg: 'falta el navegador.', arreglo: 'Corre: zsh scripts/preflight.sh' }] }, 3);
if (modo === 'basura') { process.stdout.write('esto no es json\n'); process.exit(0); }
if (modo === 'voz') {
  // 1a validación: línea de tiempo con voz pendiente; 2a (ya hay tomas): la voz real no cabe.
  const proy = process.argv[process.argv.indexOf('--proyecto') + 1];
  if (fs.existsSync(path.join(proy, 'recursos', 'voz', 'tiempos.json')))
    out({ ok: false, errores: [{ codigo: 'E-TIEMPO-EXCEDE', severidad: 'E', ruta: 'salida.duracion',
      msg: 'el contenido necesita al menos 14.2s y el objetivo es 12s.', arreglo: 'Sube salida.duracion a 15.' }],
      avisos: [] }, 2);
  const lt = { version: 1, fps: 30, total: 6, cuadros: 180, tema_nombre: 'neutro',
    audio: { musica: { tipo: 'procedural' }, sfx: 'sutil', voz: { voz: 'coral' } },
    voz: { voz: 'coral', pendiente: true, lineas: [{ escena: 1, frase: 0, texto: 'Cotiza con nosotros hoy.',
      archivo: null, en: 1, dur: 2 }] } };
  fs.writeFileSync(path.join(proy, 'recursos', 'promo', 'linea_tiempo.json'), JSON.stringify(lt));
  out({ ok: true, errores: [], avisos: [{ codigo: 'W-VOZ-PENDIENTE', severidad: 'W', ruta: 'audio.voz',
    msg: 'faltan 1 de 1 tomas.' }], resumen: { total: 6, cuadros: 180, escenas: [] } }, 0);
}
"""


def correr(*args, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run([sys.executable, PROMO, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=e, cwd=REPO)
    return r.returncode, r.stdout, r.stderr


class TestPromo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name
        self.stub = os.path.join(self.raiz, "motor_stub.mjs")
        with open(self.stub, "w", encoding="utf-8") as f:
            f.write(MOTOR_STUB)

    def tearDown(self):
        self.tmp.cleanup()

    def nuevo(self, slug="prueba-uno"):
        codigo, out, _ = correr("nuevo", slug, "--raiz", self.raiz)
        self.assertEqual(codigo, 0, out)
        base = os.path.join(self.raiz, "proyectos")
        return os.path.join(base, [d for d in os.listdir(base) if d.startswith(slug)][0])

    # ------------------------------------------------------------ nuevo
    def test_nuevo_crea_estructura(self):
        proy = self.nuevo()
        self.assertRegex(os.path.basename(proy), r"^prueba-uno_\d{8}$")
        for rel in ("promo.json", "brief.md", "info.txt", "recursos/promo", "recursos/cuadros",
                    "recursos/render", "recursos/audio"):
            self.assertTrue(os.path.exists(os.path.join(proy, rel)), rel)
        with open(os.path.join(proy, "brief.md"), encoding="utf-8") as f:
            brief = f.read()
        for seccion in ("Objetivo", "Público", "Mensaje clave", "Hechos confirmados (con fuente)",
                        "CTA y contacto", "Tono", "Duración/formato", "Música", "Voz en off (sí/no)"):
            self.assertIn(f"## {seccion}", brief)
        with open(os.path.join(proy, "promo.json"), encoding="utf-8") as f:
            spec = json.load(f)
        self.assertEqual(spec.get("formato"), "promo_ui")
        if (spec.get("salida") or {}).get("archivo"):
            self.assertEqual(spec["salida"]["archivo"], "prueba-uno.mp4")
        # Nunca toca el proyectos/ real.
        self.assertFalse(any(d.startswith("prueba-uno_") for d in os.listdir(os.path.join(REPO, "proyectos"))))

    def test_nuevo_rechaza_existente_slug_invalido_y_ejemplo_inexistente(self):
        self.nuevo()
        self.assertEqual(correr("nuevo", "prueba-uno", "--raiz", self.raiz)[0], 2)
        self.assertEqual(correr("nuevo", "Mal Slug!", "--raiz", self.raiz)[0], 2)
        codigo, out, _ = correr("nuevo", "otro", "--ejemplo", "no-existe", "--raiz", self.raiz)
        self.assertEqual(codigo, 2)
        self.assertIn("Disponibles:", out)
        self.assertFalse(any(d.startswith("otro_") for d in os.listdir(os.path.join(self.raiz, "proyectos"))))

    # ------------------------------------------------------------ estado / validar
    def test_estado_corto_y_con_siguiente(self):
        self.nuevo()
        codigo, out, _ = correr("estado", "prueba-uno", "--raiz", self.raiz)
        self.assertEqual(codigo, 0)
        lineas = out.strip().splitlines()
        self.assertLessEqual(len(lineas), 6)
        self.assertIn("promo.py validar prueba-uno_", lineas[-1])

    def test_validar_propaga_codigos_del_motor(self):
        self.nuevo()
        env = {"PROMO_MOTOR": self.stub}
        codigo, out, err = correr("validar", "prueba-uno", "--raiz", self.raiz, env=env | {"STUB_MODO": "errores"})
        self.assertEqual(codigo, 2)
        lineas = out.strip().splitlines()
        self.assertIn("1 error, 1 aviso", lineas[0])
        self.assertIn("E-TXT-LARGO  escenas[1].titular: 19 palabras (máx 16). Quita 3 palabras. (t=6.4)", out)
        self.assertTrue(lineas[-1].startswith("Siguiente: corrige promo.json"))
        self.assertNotIn("log del motor", out + err)                 # silencioso sin --verbose
        self.assertEqual(correr("validar", "prueba-uno", "--raiz", self.raiz,
                                env=env | {"STUB_MODO": "ok"})[0], 0)
        self.assertEqual(correr("validar", "prueba-uno", "--raiz", self.raiz,
                                env=env | {"STUB_MODO": "entorno"})[0], 3)
        codigo, out, _ = correr("validar", "prueba-uno", "--raiz", self.raiz, env=env | {"STUB_MODO": "basura"})
        self.assertEqual(codigo, 1)
        self.assertIn("no devolvió JSON", out)
        _, _, err = correr("validar", "prueba-uno", "--raiz", self.raiz, "--verbose",
                           env=env | {"STUB_MODO": "ok"})
        self.assertIn("log del motor", err)

    def test_audio_acepta_refrescar_cc0(self):
        sys.path.insert(0, SCRIPTS)
        import promo
        a = promo.construir_parser().parse_args(["audio", "x", "--refrescar-cc0"])
        self.assertTrue(a.refrescar_cc0)

    def test_proyecto_inexistente(self):
        self.assertEqual(correr("estado", "nada-de-esto", "--raiz", self.raiz)[0], 2)

    # ------------------------------------------------------------ audio + final (sin Node)
    def test_audio_y_final_con_video_sintetico(self):
        proy = self.nuevo("prueba-final")
        rec = os.path.join(proy, "recursos")
        lt = {"version": 1, "fps": 30, "w": 216, "h": 384, "total": 4.0, "cuadros": 120, "semilla": 3,
              "archivo_salida": "prueba-final.mp4", "portada": 1.5,
              "audio": {"musica": {"tipo": "procedural", "bpm": 112}, "sfx": "sutil", "voz": None},
              "escenas": [], "cues": [{"s": "pop", "en": 1.0}],
              "musica": {"bpm": 112, "secciones": [[0, 1.0, "intro"], [1.0, 3.0, "cuerpo"], [3.0, 4.0, "cierre"]]}}
        time.sleep(0.01)                      # la línea de tiempo debe ser más nueva que promo.json
        with open(os.path.join(rec, "promo", "linea_tiempo.json"), "w", encoding="utf-8") as f:
            json.dump(lt, f)
        # Video mudo SIN etiquetas de color: final debe agregarlas con h264_metadata.
        comun.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=30:d=4",
                   "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                   os.path.join(rec, "render", "video_mudo.mp4")])
        codigo, out, _ = correr("final", "prueba-final", "--raiz", self.raiz)
        self.assertEqual(codigo, 0, out)
        self.assertLessEqual(len(out.strip().splitlines()), 6)
        self.assertIn("checks: ok", out)
        for rel in ("prueba-final.mp4", "prueba-final_portada.jpg", "recursos/audio/mezcla.wav"):
            self.assertTrue(os.path.exists(os.path.join(proy, rel)), rel)
        m = comun.ebur128(os.path.join(proy, "prueba-final.mp4"))
        self.assertAlmostEqual(m["I"], -14.0, delta=0.5)
        self.assertLessEqual(m["TP"], -1.0)
        with open(os.path.join(proy, "info.txt"), encoding="utf-8") as f:
            info = f.read()
        self.assertIn("### promo final — inicio", info)
        self.assertIn("120 cuadros", info)
        codigo, out, _ = correr("estado", "prueba-final", "--raiz", self.raiz)
        self.assertIn("final ok", out)
        self.assertLessEqual(len(out.strip().splitlines()), 6)
        correo = os.path.join(proy, "prueba-final_correo.mp4")
        self.assertTrue(os.path.exists(correo))
        self.assertLess(os.path.getsize(correo), 25_000_000)
        self.assertFalse(os.path.exists(os.path.join(proy, "prueba-final.srt")))   # sin voz no hay srt

    def test_todo_con_voz_se_detiene_si_no_cabe(self):
        self.nuevo("prueba-todo")
        codigo, out, _ = correr("todo", "prueba-todo", "--raiz", self.raiz,
                                env={"PROMO_MOTOR": self.stub, "STUB_MODO": "voz", "PROMO_TTS_STUB": "1"})
        self.assertEqual(codigo, 2, out)
        self.assertIn("promo voz · prueba-todo_", out)                 # corrió la voz entre validaciones
        self.assertIn("E-TIEMPO-EXCEDE", out)
        self.assertIn("la voz real no cabe", out.strip().splitlines()[-1])

    # ------------------------------------------------------------ voz (TTS simulado, sin red)
    def test_voz_audio_y_final_con_srt(self):
        proy = self.nuevo("prueba-voz")
        rec = os.path.join(proy, "recursos")
        ruta_lt = os.path.join(rec, "promo", "linea_tiempo.json")
        lineas = [{"escena": 1, "frase": 0, "texto": "Pide tu cotización en el chat,", "archivo": None,
                   "en": 1.2, "dur": 2.0}, {"escena": 1, "frase": 1, "texto": "y recíbela al instante.",
                                            "archivo": None, "en": 3.6, "dur": 1.6}]
        lt = {"version": 1, "fps": 30, "w": 216, "h": 384, "total": 6.0, "cuadros": 180, "semilla": 3,
              "tema_nombre": "neutro", "archivo_salida": "prueba-voz.mp4", "portada": 2.0,
              "audio": {"musica": {"tipo": "procedural", "bpm": 112}, "sfx": "sutil", "voz": {"voz": "coral"}},
              "voz": {"voz": "coral", "proveedor": "openrouter", "pendiente": True, "lineas": lineas},
              "escenas": [], "cues": [],
              "musica": {"bpm": 112, "secciones": [[0, 1.0, "intro"], [1.0, 5.0, "cuerpo"], [5.0, 6.0, "cierre"]]}}
        time.sleep(0.01)
        with open(ruta_lt, "w", encoding="utf-8") as f:
            json.dump(lt, f)
        codigo, out, _ = correr("audio", "prueba-voz", "--raiz", self.raiz)
        self.assertEqual(codigo, 2)
        self.assertIn("promo.py voz", out)
        codigo, out, _ = correr("voz", "prueba-voz", "--raiz", self.raiz, env={"PROMO_TTS_STUB": "1"})
        self.assertEqual(codigo, 0, out)
        self.assertIn("2 líneas (2 nuevas, 0 en caché)", out)
        self.assertIn("promo.py validar", out.strip().splitlines()[-1])
        with open(os.path.join(rec, "voz", "tiempos.json"), encoding="utf-8") as f:
            tiempos = json.load(f)
        # Tras `voz` hay que re-validar: audio lo exige.
        codigo, out, _ = correr("audio", "prueba-voz", "--raiz", self.raiz)
        self.assertEqual((codigo, "voz cambió" in out), (2, True))
        # Lo que haría `validar` de Node: tomar archivo y duración reales de tiempos.json.
        for l, t in zip(lineas, tiempos["lineas"]):
            l.update(archivo=t["archivo"], dur=t["dur"])
        lt["voz"]["pendiente"] = False
        time.sleep(0.01)
        with open(ruta_lt, "w", encoding="utf-8") as f:
            json.dump(lt, f)
        comun.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=30:d=6",
                   "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                   os.path.join(rec, "render", "video_mudo.mp4")])
        codigo, out, _ = correr("final", "prueba-voz", "--raiz", self.raiz)
        self.assertEqual(codigo, 0, out)
        self.assertLessEqual(len(out.strip().splitlines()), 6)
        with open(os.path.join(proy, "prueba-voz.srt"), encoding="utf-8") as f:
            srt = f.read()
        self.assertEqual(srt.count(" --> "), 2)
        self.assertIn("00:00:01,200 --> ", srt)
        self.assertIn("Pide tu cotización en el chat,", srt)
        self.assertTrue(os.path.exists(os.path.join(proy, "prueba-voz_correo.mp4")))
        codigo, out, _ = correr("estado", "prueba-voz", "--raiz", self.raiz)
        self.assertIn("voz ok", out)


if __name__ == "__main__":
    unittest.main()
