#!/usr/bin/env python3
"""Pruebas de scripts/fetch_audio.py (unittest, solo librería estándar).

Todas son offline: `fa.http_get` (la única puerta a la red) se sustituye por `RedFalsa`, que
responde páginas de Openverse/Freesound y descargas desde memoria, y `fa._dormir` se anula para
no esperar backoffs. La única prueba en línea está protegida por CC0_ONLINE=1.

Uso:
  python3 scripts/pruebas/test_fetch_audio.py -v
  CC0_ONLINE=1 python3 scripts/pruebas/test_fetch_audio.py -v PruebaEnLinea
"""
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_audio as fa  # noqa: E402

CDN = "https://cdn.prueba.org/"


def ov(i, licencia="cc0", dur_ms=2000, titulo=None, lic_url=None, url=None, origen=None):
    """Item crudo con la forma de la respuesta de Openverse."""
    if lic_url is None:
        lic_url = fa.LICENCIA_URL if licencia.lower() == "cc0" else f"https://creativecommons.org/licenses/{licencia}/4.0/"
    return {"id": f"ov-{i}", "title": titulo or f"Whoosh {i}", "creator": f"autor{i}", "license": licencia,
            "license_url": lic_url, "url": url or f"{CDN}{i}.mp3",
            "foreign_landing_url": origen or f"https://freesound.org/people/a/sounds/{i}",
            "duration": dur_ms, "filetype": "mp3", "provider": "freesound"}


def fs(i, licencia="http://creativecommons.org/publicdomain/zero/1.0/", dur=2.0):
    """Item crudo con la forma de la respuesta de Freesound."""
    return {"id": i, "name": f"Pop {i}", "username": f"user{i}", "license": licencia, "duration": dur,
            "url": f"https://freesound.org/people/user{i}/sounds/{i}/",
            "previews": {"preview-hq-mp3": f"https://cdn.freesound.org/previews/{i}-hq.mp3"}}


def audio_falso(url):
    return b"ID3\x03" + hashlib.sha256(url.encode()).digest() * 100  # ~3.2 KB, distinto por URL


class RedFalsa:
    """Sustituto de fa.http_get: registra llamadas y responde desde memoria."""

    def __init__(self, paginas=None, freesound=None, descargas=None):
        self.paginas = paginas or {}      # {n_pagina: [items Openverse]}
        self.freesound = freesound or {}  # {n_pagina: [items Freesound]}
        self.descargas = descargas or {}  # {url: Respuesta}
        self.llamadas = []

    def __call__(self, url, cabeceras=None, timeout=None):
        self.llamadas.append((url, dict(cabeceras or {})))
        pag = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
        if url.startswith(fa.OPENVERSE_API):
            cuerpo = {"page": pag, "page_count": max(self.paginas or [1]), "results": self.paginas.get(pag, [])}
            return fa.Respuesta(200, "application/json", json.dumps(cuerpo).encode(), None)
        if url.startswith(fa.FREESOUND_API):
            sig = "https://freesound.org/apiv2/search/text/?page=%d" % (pag + 1) if pag < max(self.freesound or [1]) else None
            cuerpo = {"results": self.freesound.get(pag, []), "next": sig}
            return fa.Respuesta(200, "application/json", json.dumps(cuerpo).encode(), None)
        if url in self.descargas:
            return self.descargas[url]
        return fa.Respuesta(200, "audio/mpeg", audio_falso(url), None)

    def api(self):
        return [u for u, _ in self.llamadas if u.startswith((fa.OPENVERSE_API, fa.FREESOUND_API))]

    def bajadas(self):
        return [u for u, _ in self.llamadas if not u.startswith((fa.OPENVERSE_API, fa.FREESOUND_API))]


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = tmp.name
        self.red = RedFalsa()
        self.esperas = []
        for p in (mock.patch.object(fa, "http_get", new=lambda url, cab=None, t=None: self.red(url, cab, t)),
                  mock.patch.object(fa, "_dormir", new=self.esperas.append)):
            p.start()
            self.addCleanup(p.stop)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                codigo = fa.main(list(args))
            except SystemExit as e:
                codigo = e.code
        return codigo, out.getvalue(), err.getvalue()

    def manifest(self):
        with open(os.path.join(self.out, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def filas_csv(self):
        with open(os.path.join(self.out, "credits.csv"), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def audios(self):
        return sorted(x for x in os.listdir(self.out) if x.endswith(".mp3"))


class PruebaLicencias(Base):
    def test_solo_cc0_y_cuenta_descartes(self):
        mezcla = [ov(0), ov(1), ov(2), ov(3, "CC0"), ov(4, "by"), ov(5, "by-nc"), ov(6, "by-nc-nd"),
                  ov(7, "by-sa"), ov(8, "pdm", lic_url="https://creativecommons.org/publicdomain/mark/1.0/"),
                  ov(9, "cc0", lic_url="https://creativecommons.org/licenses/by/4.0/"),  # incoherente
                  ov(10, "")]
        self.red.paginas = {1: mezcla}
        stats = {}
        res = fa.buscar("whoosh", n=20, stats=stats)
        self.assertEqual([r["id"] for r in res], ["ov-0", "ov-1", "ov-2", "ov-3"])
        self.assertTrue(all(r["licencia"] == "cc0" for r in res))
        self.assertEqual(stats["no_cc0"], 7)
        self.assertEqual(stats["consultas_api"], 1)

    def test_consulta_pide_cc0_sin_category(self):
        self.red.paginas = {1: [ov(0)]}
        fa.buscar("whoosh", n=1)
        q = parse_qs(urlparse(self.red.api()[0]).query)
        self.assertEqual(q["license"], ["cc0"])
        self.assertEqual(q["license_type"], ["all-cc"])
        self.assertEqual(q["mature"], ["false"])
        self.assertNotIn("category", q)

    def test_descargar_revalida_cc0(self):
        item = fa._normalizar_openverse(ov(1, "by"), "whoosh")
        stats = {}
        self.assertEqual(fa.descargar([item], self.out, stats=stats), [])
        self.assertEqual(stats["no_cc0"], 1)
        self.assertEqual(self.red.bajadas(), [])


class PruebaPaginasYDuplicados(Base):
    def test_deduplica_entre_paginas(self):
        self.red.paginas = {1: [ov(i) for i in range(20)], 2: [ov(i) for i in range(10, 30)]}
        stats = {}
        res = fa.buscar("whoosh", n=30, stats=stats)
        ids = [r["id"] for r in res]
        self.assertEqual(len(ids), 30)
        self.assertEqual(len(set(ids)), 30)
        self.assertEqual(stats["duplicados"], 10)
        self.assertEqual(stats["consultas_api"], 2)
        self.assertEqual(self.esperas, [fa.PAUSA_PAGINAS])  # cortesía entre páginas

    def test_misma_obra_por_url_de_origen(self):
        self.red.paginas = {1: [ov(1), ov(2, origen="https://freesound.org/people/a/sounds/1/")]}
        stats = {}
        self.assertEqual(len(fa.buscar("x", n=5, stats=stats)), 1)
        self.assertEqual(stats["duplicados"], 1)

    def test_no_pide_mas_paginas_de_las_necesarias(self):
        self.red.paginas = {1: [ov(i) for i in range(20)], 2: [ov(i) for i in range(20, 40)]}
        fa.buscar("whoosh", n=5)
        self.assertEqual(len(self.red.api()), 1)


class PruebaDuraciones(Base):
    DURS = {0: 500, 1: 5000, 2: 6000, 3: 6500, 4: 30000, 5: 45000, 6: None}

    def setUp(self):
        super().setUp()
        self.red.paginas = {1: [ov(i, dur_ms=d) for i, d in self.DURS.items()]}

    def ids(self, **kw):
        return {r["id"] for r in fa.buscar("x", n=20, **kw)}

    def test_presets(self):
        self.assertEqual(fa.limites("sfx"), (None, 6.0))
        self.assertEqual(fa.limites("bgm"), (30.0, None))
        self.assertEqual(fa.limites("any"), (None, None))
        self.assertEqual(fa.limites("sfx", max_dur=1), (None, 1.0))
        self.assertEqual(fa.limites("bgm", min_dur=10), (10.0, None))
        self.assertEqual(fa.limites("sfx", min_dur=2), (2.0, 6.0))
        with self.assertRaises(ValueError):
            fa.limites("sfx", min_dur=10)
        with self.assertRaises(ValueError):
            fa.limites("largo")

    def test_sfx_max_6s_y_sin_duracion_fuera(self):
        stats = {}
        self.assertEqual({r["id"] for r in fa.buscar("x", n=20, perfil="sfx", stats=stats)}, {"ov-0", "ov-1", "ov-2"})
        self.assertEqual(stats["fuera_duracion"], 4)

    def test_bgm_min_30s(self):
        self.assertEqual(self.ids(perfil="bgm"), {"ov-4", "ov-5"})

    def test_flags_explicitos_anulan_preset(self):
        self.assertEqual(self.ids(perfil="sfx", max_dur=1), {"ov-0"})
        self.assertEqual(self.ids(perfil="bgm", min_dur=40), {"ov-5"})
        self.assertEqual(self.ids(perfil="any"), {f"ov-{i}" for i in self.DURS})

    def test_cli_perfil_sfx_max_dur(self):
        codigo, out, _ = self.cli("click", "-n", "4", "--profile", "sfx", "--max-dur", "1", "--out", self.out)
        self.assertEqual(codigo, 0)
        self.assertIn("solo 1 de 4", out)
        self.assertEqual(len(self.audios()), 1)


class PruebaNombres(Base):
    def test_slug(self):
        self.assertEqual(fa.slug("Woosh_Low_02.wav"), "woosh-low-02")
        self.assertEqual(fa.slug("Deep Whoosh #1"), "deep-whoosh-1")
        self.assertEqual(fa.slug("Ñandú  Pop!!"), "nandu-pop")
        self.assertEqual(fa.slug("../../etc/passwd"), "etc-passwd")
        self.assertEqual(fa.slug(""), "audio")
        self.assertEqual(fa.slug("🎵🎵"), "audio")
        self.assertLessEqual(len(fa.slug("a b " * 80)), 60)

    def test_sufijos_sin_sobreescribir(self):
        with open(os.path.join(self.out, "pop_1.mp3"), "wb") as f:
            f.write(b"del usuario")
        items = [fa._normalizar_openverse(ov(i, titulo="Pop"), "pop") for i in (1, 2)]
        res = fa.descargar(items, self.out)
        self.assertEqual([r["archivo"] for r in res], ["pop_2.mp3", "pop_3.mp3"])
        with open(os.path.join(self.out, "pop_1.mp3"), "rb") as f:
            self.assertEqual(f.read(), b"del usuario")

    def test_no_reusa_nombre_de_otro_item_del_manifest(self):
        fa.descargar([fa._normalizar_openverse(ov(1, titulo="Pop"), "pop")], self.out)
        os.remove(os.path.join(self.out, "pop_1.mp3"))  # borrado, pero sigue en el manifest
        res = fa.descargar([fa._normalizar_openverse(ov(2, titulo="Pop"), "pop")], self.out)
        self.assertEqual(res[0]["archivo"], "pop_2.mp3")


class PruebaDescartes(Base):
    def test_menor_o_igual_1kb_se_descarta(self):
        item = fa._normalizar_openverse(ov(1), "x")
        self.red.descargas[item["descarga_url"]] = fa.Respuesta(200, "audio/mpeg", b"ID3" + b"\0" * 1021, None)
        stats = {}
        self.assertEqual(fa.descargar([item], self.out, stats=stats), [])
        self.assertEqual(stats["descartes_descarga"], 1)
        self.assertEqual(self.audios(), [])
        self.assertFalse(os.path.exists(os.path.join(self.out, "manifest.json")))

    def test_html_se_rechaza(self):
        a, b = (fa._normalizar_openverse(ov(i), "x") for i in (1, 2))
        self.red.descargas[a["descarga_url"]] = fa.Respuesta(200, "text/html; charset=utf-8", b"x" * 5000, None)
        self.red.descargas[b["descarga_url"]] = fa.Respuesta(200, "application/octet-stream",
                                                             b"<!DOCTYPE html>" + b"x" * 5000, None)
        stats = {}
        self.assertEqual(fa.descargar([a, b], self.out, stats=stats), [])
        self.assertEqual(stats["descartes_descarga"], 2)
        self.assertEqual(os.listdir(self.out), [".fetch_audio.lock"])

    def test_solo_https(self):
        with self.assertRaises(fa.ErrorRed):
            fa._pedir("http://cdn.prueba.org/1.mp3")
        self.assertEqual(self.red.llamadas, [])
        self.red.paginas = {1: [ov(1, url="http://cdn.prueba.org/1.mp3"), ov(2)]}
        stats = {}
        self.assertEqual([r["id"] for r in fa.buscar("x", n=5, stats=stats)], ["ov-2"])
        self.assertEqual(stats["sin_url"], 1)

    def test_reposicion_con_reserva(self):
        self.red.paginas = {1: [ov(i) for i in range(5)]}
        self.red.descargas[f"{CDN}0.mp3"] = fa.Respuesta(200, "audio/mpeg", b"corto", None)
        res = fa.obtener("whoosh", n=2, out_dir=self.out)
        self.assertEqual([r["id"] for r in res], ["ov-1", "ov-2"])
        self.assertEqual(len(self.red.api()), 1)


class PruebaTrazabilidad(Base):
    def items(self):
        return [fa._normalizar_openverse(ov(i, titulo=t), "whoosh") for i, t in
                ((1, "Whoosh"), (2, "Swoosh"), (3, "=HYPERLINK(\"x\")"))]

    def test_manifest_y_credits_sin_duplicar_al_reejecutar(self):
        fa.descargar(self.items(), self.out)
        antes = self.manifest()
        self.assertEqual(antes["politica_licencia"], "CC0 1.0 unicamente")
        self.assertEqual(len(antes["items"]), 3)
        for it in antes["items"]:
            self.assertEqual(it["licencia"], "cc0")
            self.assertEqual(len(it["sha256"]), 64)
            for campo in ("titulo", "autor", "licencia_url", "origen_url", "duracion_s", "bytes", "fecha", "consulta"):
                self.assertIn(campo, it)
        n_bajadas = len(self.red.bajadas())
        res = fa.descargar(self.items(), self.out)  # re-ejecución
        self.assertTrue(all(r["reutilizado"] for r in res))
        self.assertEqual(len(self.red.bajadas()), n_bajadas)
        self.assertEqual(self.manifest()["items"], antes["items"])
        filas = self.filas_csv()
        self.assertEqual(len(filas), 3)
        self.assertTrue(all(f["licencia"] == "cc0" and f["sha256"] for f in filas))
        with open(os.path.join(self.out, "credits.csv"), encoding="utf-8") as f:
            self.assertEqual(sum(1 for l in f if l.startswith("archivo,")), 1)
        self.assertTrue(filas[2]["titulo"].startswith("'="))  # sin inyección de fórmulas
        self.assertEqual(len(self.audios()), 3)

    def test_append_conserva_entradas_previas(self):
        fa.descargar(self.items()[:1], self.out)
        fa.descargar(self.items()[1:], self.out)
        self.assertEqual(len(self.manifest()["items"]), 3)
        self.assertEqual([f["id"] for f in self.filas_csv()], ["ov-1", "ov-2", "ov-3"])

    def test_redescarga_si_el_archivo_se_borro(self):
        fa.descargar(self.items()[:1], self.out)
        os.remove(os.path.join(self.out, "whoosh_1.mp3"))
        res = fa.descargar(self.items()[:1], self.out)
        self.assertEqual(res[0]["archivo"], "whoosh_1.mp3")
        self.assertFalse(res[0]["reutilizado"])
        self.assertEqual(len(self.manifest()["items"]), 1)
        self.assertEqual(len(self.filas_csv()), 1)

    def test_verificacion_sha256(self):
        fa.descargar(self.items(), self.out)
        self.assertEqual(fa.verificar_manifest(self.out), (3, []))
        codigo, out, _ = self.cli("--verificar", "--out", self.out)
        self.assertEqual(codigo, 0)
        self.assertIn("3 ok, 0 con problema", out)
        with open(os.path.join(self.out, "whoosh_1.mp3"), "ab") as f:
            f.write(b"\0")
        os.remove(os.path.join(self.out, "swoosh_1.mp3"))
        ok, malos = fa.verificar_manifest(self.out)
        self.assertEqual(ok, 1)
        self.assertEqual(sorted(malos), [("swoosh_1.mp3", "no existe"), ("whoosh_1.mp3", "sha256 distinto")])
        self.assertEqual(self.cli("--verificar", "--out", self.out)[0], 3)

    def test_manifest_ilegible_no_se_sobreescribe(self):
        ruta = os.path.join(self.out, "manifest.json")
        with open(ruta, "w") as f:
            f.write("{roto")
        with self.assertRaises(fa.ErrorConfig):
            fa.descargar(self.items(), self.out)
        with open(ruta) as f:
            self.assertEqual(f.read(), "{roto")
        self.red.paginas = {1: [ov(1)]}
        self.assertEqual(self.cli("whoosh", "--out", self.out)[0], 2)

    def test_manifest_heredado_del_prototipo(self):
        legado = {"archivo": "Impact_1.mp3", "titulo": "Impact", "autor": "chriskalos", "licencia": "cc0",
                  "licencia_url": fa.LICENCIA_URL, "duracion_s": 2.6,
                  "fuente": "https://freesound.org/people/chriskalos/sounds/172779", "provider": "freesound",
                  "query": "whoosh transition", "descargado": "2026-09-28T17:32:10-0600", "bytes": 5000,
                  "sha256": "0" * 64}
        with open(os.path.join(self.out, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"politica_licencia": "CC0 1.0 unicamente", "items": [legado]}, f)
        with open(os.path.join(self.out, "credits.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["archivo", "titulo", "autor", "licencia", "query", "sha256"])
            w.writerow(["Impact_1.mp3", "Impact", "chriskalos", "cc0", "whoosh transition", "0" * 64])
        with open(os.path.join(self.out, "Impact_1.mp3"), "wb") as f:
            f.write(b"\0" * 5000)
        res = fa.obtener("whoosh transition", n=1, perfil="sfx", out_dir=self.out)
        self.assertEqual(res[0]["archivo"], "Impact_1.mp3")
        self.assertEqual(self.red.llamadas, [])
        # misma obra devuelta por la API (otro id, misma URL de origen) → se reutiliza, no se baja
        self.red.paginas = {1: [ov(9, origen="https://freesound.org/people/chriskalos/sounds/172779/"), ov(10)]}
        res = fa.obtener("impact", n=2, perfil="sfx", out_dir=self.out)
        self.assertEqual(sorted(r["reutilizado"] for r in res), [False, True])
        self.assertEqual(len(self.red.bajadas()), 1)
        filas = self.filas_csv()
        self.assertEqual([f["archivo"] for f in filas], ["Impact_1.mp3", "whoosh-10_1.mp3"])
        self.assertIn("id", filas[0])  # encabezado heredado ampliado, filas previas conservadas


class PruebaCache(Base):
    def test_obtener_usa_cache_antes_que_la_api(self):
        self.red.paginas = {1: [ov(i) for i in range(10)]}
        primero = fa.obtener("whoosh", n=2, perfil="sfx", out_dir=self.out)
        self.assertEqual(len(primero), 2)
        self.assertEqual(len(self.red.api()), 1)
        self.red.llamadas.clear()
        stats = {}
        segundo = fa.obtener("  Whoosh ", n=2, perfil="sfx", out_dir=self.out, stats=stats)
        self.assertEqual(self.red.llamadas, [])  # ni API ni descargas
        self.assertEqual(stats["consultas_api"], 0)
        self.assertEqual([r["id"] for r in segundo], [r["id"] for r in primero])
        self.assertTrue(all(r["reutilizado"] and os.path.isfile(r["ruta"]) for r in segundo))

    def test_solo_pide_los_faltantes(self):
        self.red.paginas = {1: [ov(i) for i in range(10)]}
        fa.obtener("whoosh", n=2, out_dir=self.out)
        self.red.llamadas.clear()
        res = fa.obtener("whoosh", n=3, out_dir=self.out)
        self.assertEqual(len(res), 3)
        self.assertEqual(sum(not r["reutilizado"] for r in res), 1)
        self.assertEqual(len(self.red.bajadas()), 1)
        self.assertEqual(len(self.manifest()["items"]), 3)

    def test_cache_respeta_perfil(self):
        self.red.paginas = {1: [ov(0, dur_ms=2000), ov(1, dur_ms=40000)]}
        fa.obtener("riser", n=1, perfil="sfx", out_dir=self.out)
        self.red.llamadas.clear()
        res = fa.obtener("riser", n=1, perfil="bgm", out_dir=self.out)
        self.assertEqual(res[0]["id"], "ov-1")
        self.assertEqual(len(self.red.api()), 1)

    def test_consulta_nueva_se_anota_en_item_reutilizado(self):
        self.red.paginas = {1: [ov(0)]}
        fa.obtener("whoosh", n=1, out_dir=self.out)
        fa.obtener("swoosh", n=1, out_dir=self.out)  # la API devuelve la misma obra
        self.assertEqual(self.manifest()["items"][0]["consultas"], ["whoosh", "swoosh"])
        self.red.llamadas.clear()
        fa.obtener("swoosh", n=1, out_dir=self.out)
        self.assertEqual(self.red.llamadas, [])

    def test_sin_cache_trae_archivos_nuevos(self):
        self.red.paginas = {1: [ov(i) for i in range(10)]}
        fa.obtener("whoosh", n=2, out_dir=self.out)
        stats = {}
        res = fa.obtener("whoosh", n=2, out_dir=self.out, usar_cache=False, stats=stats)
        self.assertTrue(all(not r["reutilizado"] for r in res))
        self.assertEqual(stats["ya_locales"], 2)
        self.assertEqual(len(self.manifest()["items"]), 4)

    def test_red_caida_con_cache_parcial_devuelve_lo_local(self):
        self.red.paginas = {1: [ov(0)]}
        fa.obtener("whoosh", n=1, out_dir=self.out)
        self.red = mock.Mock(side_effect=urllib.error.URLError("sin red"))
        stats = {}
        res = fa.obtener("whoosh", n=3, out_dir=self.out, stats=stats)
        self.assertEqual(len(res), 1)
        self.assertIn("sin conexión", stats["aviso_red"])


class PruebaRed(Base):
    def test_backoff_exponencial_en_429_y_5xx(self):
        respuestas = [fa.Respuesta(429, "", b"", None), fa.Respuesta(503, "", b"", None)]
        real = self.red

        def red(url, cab=None, t=None):
            return respuestas.pop(0) if respuestas else real(url, cab, t)
        self.red = red
        real.paginas = {1: [ov(1)]}
        self.assertEqual(len(fa.buscar("x", n=1)), 1)
        self.assertEqual(self.esperas, [1.5, 3.0])

    def test_retry_after_largo_falla_rapido(self):
        self.red = mock.Mock(return_value=fa.Respuesta(429, "", b"", 3600.0))
        with self.assertRaises(fa.ErrorRed) as cm:
            fa.buscar("x", n=1)
        self.assertIn("límite", str(cm.exception))
        self.assertEqual(self.red.call_count, 1)

    def test_4xx_no_se_reintenta(self):
        self.red = mock.Mock(return_value=fa.Respuesta(400, "application/json", b'{"detail":"bad"}', None))
        with self.assertRaises(fa.ErrorRed):
            fa.buscar("x", n=1)
        self.assertEqual(self.red.call_count, 1)

    def test_red_caida_exit_4(self):
        self.red = mock.Mock(side_effect=urllib.error.URLError("sin red"))
        codigo, _, err = self.cli("whoosh", "-n", "2", "--out", self.out)
        self.assertEqual(codigo, 4)
        self.assertIn("ERROR de red/API", err)
        self.assertEqual(self.red.call_count, fa.REINTENTOS)
        self.assertEqual(self.esperas, [1.5, 3.0, 6.0])

    def test_user_agent_y_redirecciones_seguras(self):
        self.assertIn("media-agent-toolkit", fa.USER_AGENT)
        h = fa._SoloHttps()
        req = urllib.request.Request("https://freesound.org/apiv2/x", headers={"Authorization": "Token t"})
        nuevo = h.redirect_request(req, None, 302, "Found", {}, "https://cdn.freesound.org/y.mp3")
        self.assertIsNone(nuevo.get_header("Authorization"))
        mismo = h.redirect_request(req, None, 302, "Found", {}, "https://freesound.org/apiv2/z")
        self.assertEqual(mismo.get_header("Authorization"), "Token t")
        with self.assertRaises(urllib.error.URLError):
            h.redirect_request(req, None, 302, "Found", {}, "http://freesound.org/y")


class PruebaFreesound(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(fa, "REPO_ROOT", self.out)  # sin .env real
        p.start()
        self.addCleanup(p.stop)
        e = mock.patch.dict(os.environ)
        e.start()
        self.addCleanup(e.stop)
        os.environ.pop("FREESOUND_TOKEN", None)

    def test_sin_token_exit_2(self):
        codigo, _, err = self.cli("pop", "--source", "freesound", "--out", self.out)
        self.assertEqual(codigo, 2)
        self.assertIn("FREESOUND_TOKEN", err)
        self.assertEqual(self.red.llamadas, [])

    def test_token_desde_env_del_repo(self):
        with open(os.path.join(self.out, ".env"), "w") as f:
            f.write('OTRA=1\nFREESOUND_TOKEN="abc123"\n')
        self.assertEqual(fa._token_freesound(), "abc123")

    def test_con_token_filtra_cc0_y_protege_token(self):
        os.environ["FREESOUND_TOKEN"] = "secreto"
        self.red.freesound = {1: [fs(1), fs(2, licencia="http://creativecommons.org/licenses/by/4.0/"),
                                  fs(3, licencia="https://creativecommons.org/publicdomain/zero/1.0/"),
                                  fs(4, licencia="http://creativecommons.org/licenses/by-nc/3.0/")]}
        stats = {}
        res = fa.obtener("pop", n=5, perfil="sfx", out_dir=self.out, fuente="freesound", stats=stats)
        self.assertEqual([r["id"] for r in res], ["freesound-1", "freesound-3"])
        self.assertEqual(stats["no_cc0"], 2)
        api_url, api_cab = self.red.llamadas[0]
        q = parse_qs(urlparse(api_url).query)
        self.assertIn('license:"Creative Commons 0"', q["filter"][0])
        self.assertIn("duration:[0 TO 6]", q["filter"][0])
        self.assertEqual(api_cab.get("Authorization"), "Token secreto")
        self.assertTrue(all("Authorization" not in cab for url, cab in self.red.llamadas[1:]))
        self.assertTrue(all(r["licencia_url"] == fa.LICENCIA_URL for r in res))


class PruebaCLI(Base):
    def test_license_by_rechazo_exit_1(self):
        codigo, _, err = self.cli("whoosh", "-n", "3", "--license", "by", "--out", self.out)
        self.assertEqual(codigo, 1)
        self.assertIn("solo CC0", err)
        self.assertEqual(self.red.llamadas, [])
        self.assertEqual(os.listdir(self.out), [])

    def test_salida_concisa(self):
        self.red.paginas = {1: [ov(1, titulo="Whoosh A"), ov(2, "by"), ov(3, titulo="Whoosh B")]}
        codigo, out, _ = self.cli("whoosh", "-n", "2", "--profile", "sfx", "--out", self.out)
        self.assertEqual(codigo, 0)
        lineas = out.strip().splitlines()
        self.assertRegex(lineas[0], r"^\+ whoosh-a_1\.mp3  \d+ KB  2\.0 s  cc0  autor1$")
        self.assertIn("descartados: 1 no-CC0", out)
        self.assertIn("total: 2 CC0 (2 nuevos, 0 reutilizados) · 1 consulta(s) API", out)
        self.assertTrue(lineas[-2].endswith(os.path.join(self.out, "credits.csv")))
        self.assertTrue(lineas[-1].endswith(os.path.join(self.out, "manifest.json")))
        codigo, out, _ = self.cli("whoosh", "-n", "2", "--profile", "sfx", "--out", self.out)
        self.assertIn("total: 2 CC0 (0 nuevos, 2 reutilizados) · 0 consulta(s) API", out)
        self.assertTrue(out.startswith("= whoosh-a_1.mp3"))

    def test_sin_resultados_exit_1_con_aviso_bgm(self):
        self.red.paginas = {1: [ov(1, dur_ms=3000)]}
        codigo, _, err = self.cli("riser", "-n", "3", "--profile", "bgm", "--out", self.out)
        self.assertEqual(codigo, 1)
        self.assertIn("Sin resultados CC0 de ≥30 s", err)
        self.assertIn("Música larga CC0", err)
        self.assertEqual(self.audios(), [])

    def test_argumentos_invalidos_exit_2(self):
        self.assertEqual(self.cli("--out", self.out)[0], 2)
        self.assertEqual(self.cli("x", "--profile", "sfx", "--min-dur", "10", "--out", self.out)[0], 2)
        self.assertEqual(self.cli("x", "-n", "0", "--out", self.out)[0], 2)

    def test_salida_por_defecto(self):
        with mock.patch.object(fa, "cargar_config", return_value={}):
            self.assertEqual(fa.salida_por_defecto(), os.path.expanduser("~/Music/media-stock"))
        with mock.patch.object(fa, "cargar_config", return_value={"audio_cc0": {"salida": "~/stock-cc0"}}):
            self.assertEqual(fa.salida_por_defecto(), os.path.expanduser("~/stock-cc0"))
        with mock.patch.object(fa, "cargar_config", return_value={"audio_cc0": {"salida": "assets/audio"}}):
            self.assertEqual(fa.salida_por_defecto(), os.path.join(fa.REPO_ROOT, "assets/audio"))


@unittest.skipUnless(os.environ.get("CC0_ONLINE") == "1", "prueba en línea: exporta CC0_ONLINE=1")
class PruebaEnLinea(unittest.TestCase):
    def test_humo_openverse(self):
        with tempfile.TemporaryDirectory() as d:
            stats = {}
            res = fa.obtener("whoosh", n=1, perfil="sfx", out_dir=d, stats=stats)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["licencia"], "cc0")
            self.assertLessEqual(res[0]["duracion_s"], 6)
            self.assertTrue(os.path.isfile(res[0]["ruta"]))
            self.assertEqual(fa.verificar_manifest(d), (1, []))
            self.assertLessEqual(stats["consultas_api"], 3)


if __name__ == "__main__":
    unittest.main()
