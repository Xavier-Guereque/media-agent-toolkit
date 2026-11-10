"""Pruebas de scripts/curso.py con raíz temporal y TTS simulado; el render real se cubre con el humo documentado."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from unittest import mock

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import curso  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"CURSO_RAIZ": self.tmp.name, "PROMO_TTS_STUB": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.assertEqual(self.correr("nuevo", "prueba")[0], 0)
        base = os.path.join(self.tmp.name, "proyectos")
        self.c = curso.Curso(os.path.join(base, os.listdir(base)[0]))
        self.spec = curso.cargar(self.c)

    def correr(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                cod = curso.main(list(args))
            except SystemExit as ex:
                cod = ex.code
        return cod, out.getvalue()

    def validar(self, spec):
        cfg, cur = curso.cursos_cfg()
        e, w = curso.validar_curso(spec, self.c, cur, cfg)
        return {i["codigo"] for i in e}, {i["codigo"] for i in w}, e

    def lec(self, spec):
        return spec["modulos"][0]["lecciones"][0]


class TestModo(Base):
    def con_modo(self, **modo):
        s = copy.deepcopy(self.spec)
        s["curso"]["modo"] = modo
        return s

    def sin_preguntas(self, s):
        for _, _, l in curso.lecciones(s):
            l["escenas"] = [e for e in l["escenas"] if e["tipo"] != "pregunta"]
            l["preguntas"] = []
        return s

    def test_sin_modo_conserva_el_default(self):
        self.assertEqual(curso.modo_de({"curso": {}}), {"proposito": "aprendizaje", "evaluacion": "intercalada", "visual": None})

    def test_valor_invalido(self):
        self.assertIn("E-CURSO-MODO", self.validar(self.con_modo(evaluacion="oral"))[0])

    def test_ninguna_permite_cero_preguntas_y_avisa(self):
        cods, avisos, _ = self.validar(self.sin_preguntas(self.con_modo(evaluacion="ninguna")))
        self.assertFalse({"E-CURSO-PREGUNTAS-MIN", "E-CURSO-MODO"} & cods)
        self.assertIn("W-CURSO-SIN-EVALUACION", avisos)

    def test_ninguna_rechaza_escena_pregunta(self):
        self.assertIn("E-CURSO-MODO", self.validar(self.con_modo(evaluacion="ninguna"))[0])

    def test_presentacion_apaga_la_pedagogia(self):
        s = self.sin_preguntas(self.con_modo(proposito="presentacion"))
        del s["curso"]["perfil_ingreso"], s["curso"]["evaluacion"]
        for _, m, l in curso.lecciones(s):
            m.pop("objetivo", None)
            l["objetivo"] = None
            l["escenas"] = [e for e in l["escenas"] if e["tipo"] != "objetivo"]
            l["tipo"] = l["nivel_bloom"] = None
        cods, avisos, e = self.validar(s)
        self.assertFalse(cods, e)
        self.assertFalse({"W-CURSO-DC3", "W-CURSO-INICIO", "W-CURSO-SIN-PRACTICA", "W-CURSO-CRITERIO"} & avisos)

    def test_presentacion_no_genera_carta(self):
        with open(self.c.spec, "w", encoding="utf-8") as f:
            json.dump(self.sin_preguntas(self.con_modo(proposito="presentacion")), f)
        cod, out = self.correr("carta", self.c.dir)
        self.assertEqual(cod, 0, out)
        self.assertFalse(os.path.exists(os.path.join(self.c.dir, "carta-descriptiva.md")))
        self.assertFalse(os.path.exists(os.path.join(self.c.dir, "quiz.json")))

    def test_entre_lecciones_exige_prueba_final(self):
        s = self.con_modo(evaluacion="entre-lecciones")
        for _, _, l in curso.lecciones(s):
            l["escenas"] = [e for e in l["escenas"] if e["tipo"] != "pregunta"]
        cods, avisos, _ = self.validar(s)
        self.assertIn("E-CURSO-MODO", cods)
        for _, _, l in curso.lecciones(s):
            l["prueba_final"] = [q["id"] for q in l["preguntas"]]
        cods, avisos, e = self.validar(s)
        self.assertNotIn("E-CURSO-MODO", cods, e)
        self.assertIn("W-CURSO-PRUEBA-MP4", avisos)
        self.assertNotIn("W-CURSO-SIN-PREGUNTA-INTERCALADA", avisos)
        self.assertNotIn("W-CURSO-PREGUNTA-SIN-ESCENA", avisos)

    def test_prueba_final_ajena_o_duplicada(self):
        s = self.con_modo(evaluacion="ambas")
        l = self.lec(s)
        l["prueba_final"] = ["no-existe"]
        self.assertIn("E-CURSO-PREGUNTA-REF", self.validar(s)[0])
        l["prueba_final"] = [next(e["pregunta_ref"] for e in l["escenas"] if e["tipo"] == "pregunta")]
        self.assertTrue(any("ya se plantea" in i["msg"] for i in self.validar(s)[2]))

    def test_prueba_final_con_intercalada_es_error(self):
        s = copy.deepcopy(self.spec)
        self.lec(s)["prueba_final"] = [self.lec(s)["preguntas"][0]["id"]]
        self.assertIn("E-CURSO-MODO", self.validar(s)[0])

    def test_visual_exige_lo_declarado(self):
        s = self.con_modo(visual="animado")
        self.lec(s).pop("mundo", None)
        self.assertIn("E-CURSO-MODO", self.validar(s)[0])
        self.assertIn("E-CURSO-MODO", self.validar(self.con_modo(visual="mixto"))[0])

    def poner_imagen(self, s):
        os.makedirs(os.path.join(self.c.rec, "img"), exist_ok=True)
        with open(os.path.join(self.c.rec, "img", "foto.png"), "wb") as f:
            f.write(b"png")
        self.lec(s)["mundo"]["actores"].append({"id": "foto", "tipo": "imagen", "clave": "foto.png", "x": 0, "y": 0})

    def test_actor_imagen(self):
        s = copy.deepcopy(self.spec)
        self.lec(s)["mundo"]["actores"].append({"id": "foto", "tipo": "imagen", "clave": "nada.png"})
        self.assertIn("E-CURSO-RECURSO", self.validar(s)[0])
        s = copy.deepcopy(self.spec)
        self.poner_imagen(s)
        cods, avisos, e = self.validar(s)
        self.assertNotIn("E-CURSO-RECURSO", cods, e)
        self.assertIn("W-CURSO-IMG-CREDITO", avisos)

    def test_imagen_no_admite_acciones_de_dato(self):
        s = copy.deepcopy(self.spec)
        self.poner_imagen(s)
        pant = next(e["pantalla"] for e in self.lec(s)["escenas"] if (e.get("pantalla") or {}).get("acciones"))
        pant["acciones"].append({"accion": "divide", "actor": "foto", "junto": True})
        self.assertIn("E-CURSO-ACCION", self.validar(s)[0])

    def test_resolver_mundo_enlaza_y_acredita(self):
        s = copy.deepcopy(self.spec)
        self.poner_imagen(s)
        with open(os.path.join(self.c.rec, "img", "creditos.json"), "w", encoding="utf-8") as f:
            json.dump({"foto": {"archivo": "foto.png", "autor": "Ana", "licencia": "CC0"}}, f)
        lec = self.c.leccion(self.lec(s)["id"])
        mundo = curso._resolver_mundo(self.c, lec, self.lec(s)["mundo"])
        a = next(x for x in mundo["actores"] if x["tipo"] == "imagen")
        self.assertEqual((a["src"], a["credito"]), ("img/foto.png", "Ana · CC0"))
        self.assertTrue(os.path.exists(os.path.join(lec.rec, "img", "foto.png")))

    def test_imgs_sin_lugar_avisan(self):
        s = copy.deepcopy(self.spec)
        self.poner_imagen(s)
        self.lec(s)["escenas"][0]["imgs"] = ["foto.png"]
        self.assertIn("W-CURSO-IMG-SIN-LUGAR", self.validar(s)[1])


class TestValidar(Base):
    def test_ejemplo_de_oro_sin_errores(self):
        cod, out = self.correr("validar", self.c.dir)
        self.assertEqual(cod, 0, out)
        self.assertIn("0 errores", out)

    def test_errores_con_ruta_y_arreglo(self):
        s = copy.deepcopy(self.spec)
        l = self.lec(s)
        l["objetivo"] = "Conocer las direcciones"
        l["preguntas"][0]["correcta"] = 9
        l["escenas"][0]["tts"] = "Tiene 255 valores."
        l["escenas"][1]["id"] = "e1"
        l["escenas"][2]["pantalla"]["acciones"][1]["en"] = "inexistente"
        l["escenas"][2]["imgs"] = ["nada.png"]
        cods, _, e = self.validar(s)
        self.assertLessEqual({"E-CURSO-OBJETIVO-VERBO", "E-CURSO-PREGUNTA-CORRECTA", "E-TTS-CIFRA", "E-CURSO-ID", "E-CURSO-SYNC", "E-CURSO-RECURSO"}, cods)
        verbo = next(i for i in e if i["codigo"] == "E-CURSO-OBJETIVO-VERBO")
        self.assertEqual(verbo["ruta"], "modulos[0].lecciones[0].objetivo")
        self.assertIn("identificar", verbo["arreglo"])

    def test_avisos_pedagogicos(self):
        s = copy.deepcopy(self.spec)
        l = self.lec(s)
        l["nivel_bloom"] = "crear"
        l.pop("practica")
        l.pop("criterio_exito")
        l["preguntas"][0]["opciones"] = ["a", "b", "una respuesta correcta larguísima que se delata sola"]
        c = l["escenas"][2]
        c["pantalla"] = {"titular": "x", "puntos": ["uno", "dos", "tres", "cuatro", "cinco"]}
        l["escenas"] = [e for e in l["escenas"] if e["tipo"] not in ("gancho", "ejemplo")]
        _, w, _ = self.validar(s)
        self.assertLessEqual({"W-CURSO-BLOOM-NIVEL", "W-CURSO-SIN-PRACTICA", "W-CURSO-CRITERIO", "W-CURSO-DISTRACTOR",
                              "W-CURSO-VINETAS", "W-CURSO-PUNTOS", "W-CURSO-INICIO"}, w)

    def test_duracion(self):
        s = copy.deepcopy(self.spec)
        s["modulos"][0]["lecciones"][0]["escenas"][2]["tts"] = "Mira esta explicación larga. " * 400
        cods, _, _ = self.validar(s)
        self.assertIn("E-CURSO-DURACION", cods)

    def test_sin_preguntas_y_json_roto(self):
        s = copy.deepcopy(self.spec)
        self.lec(s)["preguntas"] = []
        self.assertIn("E-CURSO-PREGUNTAS-MIN", self.validar(s)[0])
        with open(self.c.spec, "w") as f:
            f.write("{")
        cod, out = self.correr("validar", self.c.dir)
        self.assertEqual(cod, 2)
        self.assertIn("E-CURSO-JSON", out)

    def test_contraste(self):
        self.assertGreater(curso.contraste("#000000", "#FFFFFF"), 20)
        s = copy.deepcopy(self.spec)
        s["curso"]["estilo"]["colores"] = {"acento": "#10121C"}
        self.assertIn("W-CURSO-CONTRASTE", self.validar(s)[1])


class TestMundo(Base):
    def test_actor_y_accion_invalidos(self):
        s = copy.deepcopy(self.spec)
        l = self.lec(s)
        l["escenas"][0]["pantalla"]["acciones"][0]["actor"] = "fantasma"
        l["escenas"][2]["pantalla"]["acciones"][0]["accion"] = "baila"
        l["mundo"]["actores"][4]["a"] = "nada"
        cods = self.validar(s)[0]
        self.assertLessEqual({"E-CURSO-ACTOR", "E-CURSO-ACCION"}, cods)

    def test_acciones_sin_mundo(self):
        s = copy.deepcopy(self.spec)
        del self.lec(s)["mundo"]
        self.assertIn("E-CURSO-MUNDO", self.validar(s)[0])

    def test_lints_de_animacion(self):
        s = copy.deepcopy(self.spec)
        l = self.lec(s)
        l["escenas"][0]["pantalla"]["acciones"][0].pop("en")
        self.assertIn("W-CURSO-ANIM-SIN-EN", self.validar(s)[1])
        e = l["escenas"][2]
        e["tts"] = " ".join(["Una dirección tiene cuatro números"] + ["y sigue hablando mucho tiempo de otras cosas"] * 8) + "."
        e["pantalla"]["acciones"] = [{"en": "cuatro", "accion": "divide", "actor": "ip1"}]
        self.assertIn("W-CURSO-ESTATICA", self.validar(s)[1])

    def test_junto_hereda_el_instante_y_cues_filtran_golpes(self):
        t = {"voz_inicio": 1.0, "voz_dur": 2.0, "inicio": 0.0, "palabras": [{"w": "hola", "a": 1.0, "b": 1.5}, {"w": "red", "a": 1.5, "b": 2.0}]}
        p = curso._temporizar({"pantalla": {"acciones": [{"en": "red", "accion": "une", "actor": "x"}, {"junto": True, "accion": "enfoca", "retraso": 0.2}]}}, t)
        self.assertEqual(p["acciones"][0]["t"], 1.35)
        self.assertEqual(p["acciones"][1]["t"], 1.55)
        cues = curso.cues_sonido([{"tipo": "concepto", "inicio": 0, "pantalla": {"acciones": [{"t": 1.0, "accion": "aparece"}, {"t": 1.05, "accion": "aparece"}, {"t": 2.0, "accion": "enfoca"}]}}], {"actores": [1]})
        self.assertEqual(cues, [(1.0, "pop"), (2.0, "whoosh")])

    def test_retro_acciones_llegan_a_la_escena_de_respuesta(self):
        e = curso.expandir_escenas(self.lec(self.spec))
        r = next(x for x in e if x["id"] == "e4-r")
        self.assertTrue(r["pantalla"]["acciones"])
        self.assertNotIn("acciones", next(x for x in e if x["id"] == "e4")["pantalla"])


class TestReproductor(Base):
    def preparar(self):
        self.assertEqual(self.correr("voz", self.c.dir, "--leccion", "m1-l1")[0], 0)
        lec = self.c.leccion("m1-l1")
        with open(lec.salida(), "wb") as f:
            f.write(b"x")
        return lec

    def test_sin_video_falla(self):
        cod, out = self.correr("reproductor", self.c.dir)
        self.assertEqual(cod, 2, out)

    def test_pausa_al_terminar_la_voz_y_reanuda_en_la_respuesta(self):
        lec = self.preparar()
        cod, out = self.correr("reproductor", self.c.dir)
        self.assertEqual(cod, 0, out)
        self.assertIn("W-CURSO-REPRODUCTOR", out)
        with open(os.path.join(self.c.dir, "interaccion.json"), encoding="utf-8") as f:
            d = json.load(f)
        with open(os.path.join(lec.rec, "tiempos.json"), encoding="utf-8") as f:
            t = {x["id"]: x for x in json.load(f)["escenas"]}
        q = d["lecciones"][0]["preguntas"][0]
        self.assertEqual(q["reanuda"], t["e4-r"]["inicio"])
        self.assertLess(q["pausa"], q["reanuda"])
        self.assertEqual(q["correcta"], 2)
        self.assertTrue(d["lecciones"][0]["vtt"])

    def test_datos_no_cierran_el_script(self):
        self.preparar()
        spec = curso.cargar(self.c)
        self.lec(spec)["titulo"] = "Lección </script><b>"
        with open(os.path.join(self.c.dir, "curso.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
        self.assertEqual(self.correr("reproductor", self.c.dir)[0], 0)
        with open(os.path.join(self.c.dir, "reproductor.html"), encoding="utf-8") as f:
            pagina = f.read()
        self.assertEqual(pagina.count("</script>"), 2)


class TestFlujo(Base):
    def test_expandir_pregunta_en_dos_escenas(self):
        e = curso.expandir_escenas(self.lec(self.spec))
        ids = [x["id"] for x in e]
        self.assertIn("e4-r", ids)
        p = e[ids.index("e4")]
        self.assertTrue(p["plantea"])
        self.assertTrue(e[ids.index("e4-r")]["pantalla"]["revelar"])

    def test_componer_sin_voz_falla(self):
        cod, out = self.correr("componer", self.c.dir)
        self.assertEqual(cod, 2)
        self.assertIn("E-CURSO-TIEMPOS", out)

    def test_voz_y_componer(self):
        self.assertEqual(self.correr("voz", self.c.dir, "--leccion", "m1-l1")[0], 0)
        lec = self.c.leccion("m1-l1")
        self.assertTrue(os.path.exists(os.path.join(lec.dir, f"{self.c.slug}_m1-l1.vtt")))
        with open(os.path.join(self.c.rec, "avance.jsonl")) as f:
            self.assertIn('"voz"', f.read())
        cod, out = self.correr("componer", self.c.dir, "--leccion", "m1-l1")
        self.assertEqual(cod, 0, out)
        spec = lec.leer_spec()
        self.assertEqual(spec["composicion"], "Leccion")
        p = spec["props"]
        concepto = next(e for e in p["escenas"] if e["tipo"] == "concepto")
        ts = [x["t"] for x in concepto["pantalla"]["acciones"]]
        self.assertEqual(ts, sorted(ts))
        self.assertLess(concepto["inicio"], ts[0])
        self.assertTrue(p["subtitulos"])
        caso = os.path.join(lec.rec, "voz.wav")
        self.assertTrue(os.path.exists(caso))

    def test_render_delega_en_remotion_con_lufs_y_tramo(self):
        self.correr("voz", self.c.dir)
        self.correr("componer", self.c.dir)
        vistos = []

        def falso(ns, p, siguiente=True):
            vistos.append((p.etiqueta, p.avance_rango, p.lufs, p.avance_dir, ns.borrador, siguiente))
            return 0
        with mock.patch.object(curso.remotion, "etapa_render", falso):
            self.assertEqual(self.correr("render", self.c.dir, "--borrador")[0], 0)
        self.assertEqual(vistos[0][:5], ("lección m1-l1", (0.0, 50.0), -16.0, self.c.rec, True))
        self.assertEqual(vistos[1][1], (50.0, 100.0))
        with open(self.c.info, encoding="utf-8") as f:
            self.assertRegex(f.read(), r"m1-l2: .* · ok ·")

    def test_render_propaga_entorno(self):
        self.correr("voz", self.c.dir)
        self.correr("componer", self.c.dir)
        with mock.patch.object(curso.remotion, "etapa_render", return_value=3):
            self.assertEqual(self.correr("render", self.c.dir)[0], 3)

    def test_gate_jev(self):
        res = {"answers": {"retro": {"type": "noul", "noul": 0.2}, "distractores": {"type": "noul", "noul": 0.9}}}
        with mock.patch.object(curso.decision, "decidir", return_value=res) as d:
            cod, out = self.correr("qa", self.c.dir, "--sin-stills", "--jev", "--leccion", "m1-l1")
        self.assertEqual(cod, 2)
        self.assertIn("E-CURSO-JEV-RETRO", out)
        self.assertEqual(d.call_args.kwargs["log"], self.c.costos)
        with mock.patch.object(curso.decision, "decidir") as d2:
            self.assertEqual(self.correr("qa", self.c.dir, "--sin-stills")[0], 0)
        d2.assert_not_called()

    def test_carta_quiz_transcripcion(self):
        self.assertEqual(self.correr("carta", self.c.dir)[0], 0)
        with open(os.path.join(self.c.dir, "carta-descriptiva.md"), encoding="utf-8") as f:
            carta = f.read()
        for texto in ("Matriz de alineación", "LGE art. 150", "valor curricular", "Criterios de acreditación", "m1-l1"):
            self.assertIn(texto, carta)
        self.assertNotIn("certificad", carta.lower())
        with open(os.path.join(self.c.dir, "quiz.json"), encoding="utf-8") as f:
            q = json.load(f)
        self.assertEqual((q["umbral_pct"], len(q["reactivos"])), (80, 2))
        t = os.path.join(self.c.lecciones, "m1-l1", f"{self.c.slug}_m1-l1-transcripcion.md")
        with open(t, encoding="utf-8") as f:
            self.assertIn("Aparece el texto", f.read())

    def test_resolver_toma_el_curso_mas_reciente_y_rechaza_ambiguos(self):
        base = os.path.dirname(self.c.dir)
        for n in ("x_31102026", "x_01112026", "ab_01112026", "ac_01112026"):
            os.makedirs(os.path.join(base, n))
            open(os.path.join(base, n, "curso.json"), "w").close()
        a = Namespace(raiz=self.tmp.name)
        self.assertEqual(curso.resolver("x", a).nombre, "x_01112026")
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            curso.resolver("a", a)

    def test_misma_palabra_dos_veces_y_credito_por_archivo(self):
        s = copy.deepcopy(self.spec)
        s["modulos"][0]["lecciones"][0]["escenas"][2]["pantalla"]["elementos"] = [
            {"en": "dirección", "forma": "texto", "texto": "a", "x": 1, "y": 1}, {"en": "dirección", "forma": "texto", "texto": "b", "x": 1, "y": 1}]
        self.assertIn("E-CURSO-SYNC", self.validar(s)[0])
        lec = self.c.leccion("m1-l1")
        self.assertEqual(curso._resolver_imgs(self.c, lec, {"imgs": ["diagrama-ip.png"]})[0]["credito"], "Diagrama propio · CC0")

    def test_render_de_una_leccion_conserva_las_demas(self):
        self.correr("voz", self.c.dir)
        self.correr("componer", self.c.dir)
        with mock.patch.object(curso.remotion, "etapa_render", return_value=0):
            self.correr("render", self.c.dir)
            self.correr("render", self.c.dir, "--leccion", "m1-l1")
        with open(self.c.info, encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("m1-l1:", texto)
        self.assertIn("m1-l2:", texto)

    def test_leccion_inexistente(self):
        cod, out = self.correr("voz", self.c.dir, "--leccion", "nada")
        self.assertEqual(cod, 2)

    def test_no_toca_el_repo(self):
        self.assertFalse(os.path.exists(os.path.join(REPO, "cursos", "ejemplo", "lecciones")))


if __name__ == "__main__":
    unittest.main()
