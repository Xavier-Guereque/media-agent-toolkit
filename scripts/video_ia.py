#!/usr/bin/env python3
"""Imagen a video (o texto a video) con los modelos de video de OpenRouter (skill `animar-imagen`).

Misma key que todo el toolkit (`OPENROUTER_API_KEY`); no hace falta otro proveedor. Endpoints (verificado 2026-11-10):
`POST /api/v1/videos` → `{id, polling_url, status}`; `GET /api/v1/videos/<id>` hasta `completed|failed`;
descarga de `unsigned_urls[i]` con la cabecera Authorization; costo en `usage.cost`. Catálogo y precios en
`GET /api/v1/videos/models` (público): los precios se leen de ahí en cada llamada, nunca de la documentación.

  python3 scripts/video_ia.py modelos [--resolucion 720p] [--i2v]       catálogo con USD/s calculado
  python3 scripts/video_ia.py estimar --duracion 5 [--modelo id] [--resolucion 720p]
  python3 scripts/video_ia.py generar --primer-cuadro a.png [--ultimo-cuadro b.png] --prompt "slow dolly in…" \\
      --duracion 5 [--resolucion 720p] [--relacion 9:16] [--modelo id] [--borrador] [--semilla N] \\
      [--tope 1.0] [--confirmar] --salida proyectos/<p>/recursos/clips/toma.mp4
  python3 scripts/video_ia.py comparar --primer-cuadro a.png --prompt "…" --duracion 5 \\
      --modelos id1,id2,… --carpeta proyectos/<p>/recursos/comparar [--confirmar]

- `--borrador` = 480p (si el modelo lo admite) para iterar el prompt barato antes del clip final.
- Sin `--confirmar` se niega a gastar más de `--tope` USD (por defecto config.json > ilustrado.tope_usd_por_llamada).
- Sin audio por defecto (`generate_audio: false`): la voz y la música las pone el toolkit. `--audio` lo activa.
- Marca de agua visible apagada donde el proveedor lo permite (`watermark`/`aigc_watermark`).
- Privacidad: el video en OpenRouter NO admite Zero Data Retention. Nunca enviar fotos de personas reales sin
  permiso, ni material de `muestras/`.
- Códigos de salida: 0 OK · 2 argumentos · 3 entorno (key/config) · 4 API (402/403 presupuesto, 4xx/5xx, falló).
"""
import argparse
import base64
import concurrent.futures
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = comun.raiz_repo(__file__)
URL = "https://openrouter.ai/api/v1"
RELACIONES = ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21")
ALTO = {"480p": 480, "720p": 720, "768p": 768, "1080p": 1080, "1K": 1080, "2K": 1440, "4K": 2160}
CONFIG_DEF = {"video_resolucion": "720p", "video_borrador": "480p", "video_audio": False,
              "tope_usd_por_llamada": 1.0, "sondeo_s": 20, "espera_max_s": 1200}
# Pasan por `provider.options.<slug>` solo si el modelo los declara en allowed_passthrough_parameters.
SIN_MARCA = {"watermark": False, "aigc_watermark": False}


def config():
    cfg = comun.cargar_config(REPO)
    mod = cfg.get("modelos") or {}
    ilu = {**CONFIG_DEF, **(cfg.get("ilustrado") or {})}
    return mod, ilu


# ---------------------------------------------------------------- catálogo y precios
def catalogo(timeout=30):
    req = urllib.request.Request(URL + "/videos/models", headers={"X-Title": "media-agent-toolkit"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return {m["id"]: m for m in json.load(r).get("data", [])}


def _dims(m, resolucion, relacion):
    """(ancho, alto) para estimar tokens: de supported_sizes si cuadra, si no de la resolución y la relación."""
    alto = ALTO.get(resolucion, 720)
    a, b = (int(x) for x in (relacion or "16:9").split(":"))
    for s in m.get("supported_sizes") or []:
        w, h = (int(x) for x in s.split("x"))
        if min(w, h) == alto and abs(w / h - a / b) < 0.02:
            return w, h
    corto = alto
    return (round(corto * a / b), corto) if a >= b else (corto, round(corto * b / a))


def precio_por_segundo(m, resolucion="720p", audio=False, i2v=True, relacion="16:9"):
    """USD por segundo de video generado según `pricing_skus` (formatos vistos en el catálogo 2026-11).

    Devuelve (usd_s, origen) o (None, motivo). Admite: cents_per_video_output_second_<res>,
    [image_to_|text_to_]video_duration_seconds_<res>, duration_seconds[_with(out)_audio][_<res>] y
    video_tokens[_without_audio] (Seedance: tokens = ancho × alto × 24 × s / 1024)."""
    sk = m.get("pricing_skus") or {}
    if not sk:
        return None, "sin precios publicados"
    res = resolucion
    cand = []
    if f"cents_per_video_output_second_{res}" in sk:
        return float(sk[f"cents_per_video_output_second_{res}"]) / 100, f"cents_per_video_output_second_{res}"
    modo = "image_to_video" if i2v else "text_to_video"
    sonido = "with_audio" if audio else "without_audio"
    cand += [f"{modo}_duration_seconds_{res}", f"duration_seconds_{sonido}_{res}", f"duration_seconds_{res}",
             f"duration_seconds_{sonido}"]
    if not audio:
        cand.append("duration_seconds")
    else:
        cand.append("duration_seconds_with_audio")
    for k in cand:
        if k in sk:
            return float(sk[k]), k
    tok = "video_tokens" if audio else "video_tokens_without_audio"
    if tok in sk or "video_tokens" in sk:
        w, h = _dims(m, res, relacion)
        por_token = float(sk.get(tok) or sk["video_tokens"])
        return por_token * w * h * 24 / 1024, f"{tok} ({w}x{h})"
    return None, "formato de precio no reconocido: " + ", ".join(sorted(sk))


def costo_extra(m):
    """Cargos fijos por llamada (p. ej. cents_per_image_input)."""
    sk = m.get("pricing_skus") or {}
    return float(sk.get("cents_per_image_input", 0)) / 100


def elegir_resolucion(m, pedida):
    ok = m.get("supported_resolutions") or []
    if not ok or pedida in ok:
        return pedida
    alto = ALTO.get(pedida, 720)
    return min(ok, key=lambda r: abs(ALTO.get(r, 9999) - alto))


def elegir_duracion(m, pedida):
    ok = sorted(m.get("supported_durations") or [])
    if not ok or pedida in ok:
        return pedida
    mayores = [d for d in ok if d >= pedida]
    return mayores[0] if mayores else ok[-1]


# ---------------------------------------------------------------- HTTP con key
class _SinKeyFueraDeOpenRouter(urllib.request.HTTPRedirectHandler):
    """urllib reenvía los encabezados al seguir una redirección: si el destino no es openrouter.ai (p. ej. un
    almacenamiento firmado), se quita la key para que nunca salga del dominio."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        nueva = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nueva is not None and urllib.parse.urlsplit(newurl).hostname != "openrouter.ai":
            for h in list(nueva.headers):
                if h.lower() == "authorization":
                    del nueva.headers[h]
            nueva.unredirected_hdrs.pop("Authorization", None)
        return nueva


_ABRIR = urllib.request.build_opener(_SinKeyFueraDeOpenRouter).open


def _req(metodo, ruta, key, cuerpo=None, timeout=60):
    url = ruta if ruta.startswith("https://openrouter.ai/") else URL + ruta
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "X-Title": "media-agent-toolkit"})
    with _ABRIR(req, timeout=timeout) as r:
        return json.load(r)


def _descargar(url, key, salida, timeout=300):
    if not url.startswith("https://openrouter.ai/"):
        raise ValueError(f"URL de descarga inesperada: {url[:60]}")   # la key nunca sale de openrouter.ai
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "X-Title": "media-agent-toolkit"})
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    tmp = salida + ".part"
    with _ABRIR(req, timeout=timeout) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(tmp, salida)


def data_uri(ruta):
    mime = mimetypes.guess_type(ruta)[0] or "image/png"
    with open(ruta, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def carpeta_recursos(salida):
    ruta = os.path.abspath(salida)
    while True:
        padre = os.path.dirname(ruta)
        if os.path.basename(padre) == "proyectos":
            return os.path.join(ruta, "recursos")
        if padre == ruta:
            return os.path.join(os.path.dirname(os.path.abspath(salida)), "recursos")
        ruta = padre


# ---------------------------------------------------------------- núcleo
def plan(m, *, duracion, resolucion, relacion, audio, i2v):
    res = elegir_resolucion(m, resolucion)
    dur = elegir_duracion(m, duracion)
    usd_s, origen = precio_por_segundo(m, res, audio, i2v, relacion)
    costo = None if usd_s is None else usd_s * dur + (costo_extra(m) if i2v else 0)
    return {"modelo": m["id"], "resolucion": res, "duracion": dur, "usd_s": usd_s, "origen": origen, "costo": costo}


def cuerpo_peticion(m, p, *, prompt, relacion, primer=None, ultimo=None, audio=False, semilla=None):
    c = {"model": m["id"], "prompt": prompt, "duration": p["duracion"], "resolution": p["resolucion"]}
    if relacion and (not m.get("supported_aspect_ratios") or relacion in m["supported_aspect_ratios"]):
        c["aspect_ratio"] = relacion
    marcos = []
    soporta = m.get("supported_frame_images") or []
    if primer:
        marcos.append({"type": "image_url", "image_url": {"url": data_uri(primer)}, "frame_type": "first_frame"})
    if ultimo and "last_frame" in soporta:
        marcos.append({"type": "image_url", "image_url": {"url": data_uri(ultimo)}, "frame_type": "last_frame"})
    if marcos:
        c["frame_images"] = marcos
    if m.get("generate_audio") is not None:
        c["generate_audio"] = bool(audio)
    if semilla is not None and m.get("seed"):
        c["seed"] = int(semilla)
    pas = {k: v for k, v in SIN_MARCA.items() if k in (m.get("allowed_passthrough_parameters") or [])}
    if pas:
        # El slug del proveedor no se conoce de antemano: se manda a los habituales; OpenRouter reenvía solo el que enruta.
        c["provider"] = {"options": {s: dict(pas) for s in ("seed", "byteplus", "bytedance", "minimax", "fal")}}
    return c


def generar_uno(key, m, p, *, prompt, relacion, salida, primer=None, ultimo=None, audio=False, semilla=None,
                recursos=None, etapa="video_ia", sondeo=20, espera_max=1200, log=print):
    """Lanza, sondea y descarga un clip. Devuelve dict con ok, costo, id, salida o error."""
    cuerpo = cuerpo_peticion(m, p, prompt=prompt, relacion=relacion, primer=primer, ultimo=ultimo,
                             audio=audio, semilla=semilla)
    t0 = time.time()
    try:
        trabajo = _req("POST", "/videos", key, cuerpo, timeout=120)
    except urllib.error.HTTPError as e:
        det = e.read().decode(errors="replace")[:500]
        return {"ok": False, "modelo": m["id"], "error": f"HTTP {e.code}: {det}", "codigo_http": e.code}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "modelo": m["id"], "error": f"sin respuesta: {e}"}
    jid = trabajo.get("id")
    sondeo_url = trabajo.get("polling_url") or f"/videos/{jid}"
    log(f"  {m['id']}: trabajo {jid} ({trabajo.get('status')})")
    estado = trabajo
    while estado.get("status") not in ("completed", "failed", "cancelled", "expired"):
        if time.time() - t0 > espera_max:
            return {"ok": False, "modelo": m["id"], "id": jid, "error": f"sin terminar tras {espera_max} s"}
        time.sleep(sondeo)
        try:
            estado = _req("GET", sondeo_url, key, timeout=60)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log(f"  {m['id']}: sondeo falló ({e}); reintento")
            continue
        if recursos:
            comun.avance(etapa, min(95, 100 * (time.time() - t0) / max(60, espera_max / 4)),
                         f"{m['id']}: {estado.get('status')} · {time.time() - t0:.0f} s", cada=5)
    usage = estado.get("usage") or {}
    if recursos:
        comun.log_costo(recursos, {"id": estado.get("generation_id") or jid, "modelo": m["id"], "tarea": "video_ia",
                                   "usage": usage or None})
    if estado.get("status") != "completed":
        return {"ok": False, "modelo": m["id"], "id": jid, "error": str(estado.get("error") or estado.get("status")),
                "costo": usage.get("cost")}
    urls = estado.get("unsigned_urls") or []
    if not urls:
        return {"ok": False, "modelo": m["id"], "id": jid, "error": "completado sin unsigned_urls", "costo": usage.get("cost")}
    try:
        _descargar(urls[0], key, salida)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return {"ok": False, "modelo": m["id"], "id": jid, "error": f"descarga: {e}", "costo": usage.get("cost")}
    return {"ok": True, "modelo": m["id"], "id": jid, "salida": salida, "costo": usage.get("cost"),
            "segundos": round(time.time() - t0), "duracion_clip": round(comun.dur(salida), 3)}


def _cargar(args):
    try:
        cat = catalogo()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"No se pudo leer el catálogo de video de OpenRouter: {e}", file=sys.stderr)
        raise SystemExit(4)
    return cat


def _modelo(cat, mid):
    if mid not in cat:
        parecidos = [k for k in cat if mid.split("/")[-1].split("-")[0] in k][:6]
        print(f"Modelo de video desconocido: {mid}. Parecidos: {', '.join(parecidos) or '—'}. "
              f"Lista: python3 scripts/video_ia.py modelos", file=sys.stderr)
        raise SystemExit(2)
    return cat[mid]


def _validar_imagenes(*rutas):
    for r in rutas:
        if r and not os.path.exists(r):
            print(f"Imagen inexistente: {r}", file=sys.stderr)
            raise SystemExit(2)


# ---------------------------------------------------------------- comandos
def cmd_modelos(args):
    cat = _cargar(args)
    filas = []
    for m in cat.values():
        if args.i2v and "first_frame" not in (m.get("supported_frame_images") or []):
            continue
        res = elegir_resolucion(m, args.resolucion)
        usd, _ = precio_por_segundo(m, res, args.audio, True, args.relacion)
        filas.append((usd if usd is not None else 99, m["id"], res, usd, m))
    filas.sort()
    print(f"{'modelo':42} {'res':6} {'USD/s':>7}  {'durac.':10} {'cuadros':12} relaciones")
    for _, mid, res, usd, m in filas:
        dur = m.get("supported_durations") or []
        rango = f"{min(dur)}–{max(dur)} s" if dur else "?"
        marcos = "+".join(x.replace("_frame", "") for x in (m.get("supported_frame_images") or [])) or "—"
        print(f"{mid:42} {res:6} {('%.3f' % usd) if usd is not None else '  ?':>7}  {rango:10} {marcos:12} "
              f"{','.join(m.get('supported_aspect_ratios') or [])}")
    print(f"\n{len(filas)} modelos · precios leídos ahora de {URL}/videos/models · sin audio salvo --audio")


def cmd_estimar(args):
    mod, ilu = config()
    cat = _cargar(args)
    mid = args.modelo or mod.get("video")
    m = _modelo(cat, mid)
    res = ilu["video_borrador"] if args.borrador else (args.resolucion or ilu["video_resolucion"])
    p = plan(m, duracion=args.duracion, resolucion=res, relacion=args.relacion, audio=args.audio, i2v=True)
    if p["costo"] is None:
        print(f"{mid}: precio no calculable ({p['origen']}).")
        return
    print(f"{mid}: {p['duracion']} s a {p['resolucion']} ≈ {p['costo']:.3f} USD ({p['usd_s']:.4f} USD/s · {p['origen']})")


def _tope(args, ilu):
    return args.tope if args.tope is not None else float(ilu["tope_usd_por_llamada"])


def cmd_generar(args):
    mod, ilu = config()
    _validar_imagenes(args.primer_cuadro, args.ultimo_cuadro)
    prompt = args.prompt or ""
    if args.prompt_archivo:
        with open(args.prompt_archivo, encoding="utf-8") as f:
            prompt = (f.read().strip() + "\n\n" + prompt).strip()
    if not prompt:
        print("Falta --prompt o --prompt-archivo.", file=sys.stderr)
        raise SystemExit(2)
    cat = _cargar(args)
    m = _modelo(cat, args.modelo or mod.get("video"))
    if args.primer_cuadro and "first_frame" not in (m.get("supported_frame_images") or []):
        print(f"{m['id']} no acepta primer cuadro (imagen a video).", file=sys.stderr)
        raise SystemExit(2)
    if args.ultimo_cuadro and "last_frame" not in (m.get("supported_frame_images") or []):
        print(f"AVISO {m['id']} no acepta último cuadro: se ignora.", file=sys.stderr)
    res = ilu["video_borrador"] if args.borrador else (args.resolucion or ilu["video_resolucion"])
    audio = args.audio or bool(ilu["video_audio"]) and not args.sin_audio
    p = plan(m, duracion=args.duracion, resolucion=res, relacion=args.relacion, audio=audio, i2v=bool(args.primer_cuadro))
    est = f"{p['costo']:.3f} USD" if p["costo"] is not None else "precio desconocido"
    print(f"{m['id']}: {p['duracion']} s a {p['resolucion']} · estimado {est}")
    tope = _tope(args, ilu)
    if not args.confirmar and (p["costo"] is None or p["costo"] > tope):
        print(f"No se generó: el estimado ({est}) supera el tope de {tope:.2f} USD o no se conoce. "
              f"Confírmalo con el usuario y repite con --confirmar.", file=sys.stderr)
        raise SystemExit(2)
    key = comun.api_key(REPO)
    recursos = carpeta_recursos(args.salida)
    comun.AVANCE_DIR = recursos
    comun.avance("video_ia", 0, f"{m['id']}: enviando")
    r = generar_uno(key, m, p, prompt=prompt, relacion=args.relacion, salida=args.salida, primer=args.primer_cuadro,
                    ultimo=args.ultimo_cuadro, audio=audio, semilla=args.semilla, recursos=recursos,
                    sondeo=ilu["sondeo_s"], espera_max=ilu["espera_max_s"])
    if not r["ok"]:
        comun.avance("video_ia", 100, f"{m['id']}: {r['error'][:80]}", estado="error")
        if r.get("codigo_http") in (402, 403):
            print("OpenRouter sin crédito/presupuesto: revisa GET /api/v1/auth/key (limit_remaining).", file=sys.stderr)
        print(f"Falló: {r['error']}", file=sys.stderr)
        raise SystemExit(4)
    costo = r.get("costo")
    comun.avance("video_ia", 100, f"{m['id']}: listo", estado="listo",
                 datos={"costo_usd": costo} if costo is not None else None)
    print(f"OK -> {r['salida']} · {r['duracion_clip']} s · {r['segundos']} s de espera"
          + (f" · costo {costo:.4f} USD" if costo is not None else ""))


def cmd_comparar(args):
    mod, ilu = config()
    _validar_imagenes(args.primer_cuadro, args.ultimo_cuadro)
    cat = _cargar(args)
    ids = [x.strip() for x in args.modelos.split(",") if x.strip()]
    modelos = [_modelo(cat, i) for i in ids]
    res = ilu["video_borrador"] if args.borrador else (args.resolucion or ilu["video_resolucion"])
    planes = [plan(m, duracion=args.duracion, resolucion=res, relacion=args.relacion, audio=False, i2v=True)
              for m in modelos]
    total = sum(p["costo"] or 0 for p in planes)
    for p in planes:
        print(f"  {p['modelo']:40} {p['duracion']} s {p['resolucion']:5} ≈ "
              + (f"{p['costo']:.3f} USD" if p["costo"] is not None else "?"))
    print(f"Total estimado: {total:.3f} USD")
    if not args.confirmar:
        print("Repite con --confirmar para generar.", file=sys.stderr)
        raise SystemExit(2)
    key = comun.api_key(REPO)
    os.makedirs(args.carpeta, exist_ok=True)
    recursos = carpeta_recursos(os.path.join(args.carpeta, "x"))
    comun.AVANCE_DIR = recursos

    def uno(mp):
        m, p = mp
        nombre = re.sub(r"[^a-z0-9.-]+", "_", m["id"].lower()) + ".mp4"
        return generar_uno(key, m, p, prompt=args.prompt, relacion=args.relacion,
                           salida=os.path.join(args.carpeta, nombre), primer=args.primer_cuadro,
                           ultimo=args.ultimo_cuadro, recursos=recursos, etapa=f"comparar {m['id'].split('/')[-1]}",
                           sondeo=ilu["sondeo_s"], espera_max=ilu["espera_max_s"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(modelos))) as ex:
        resultados = list(ex.map(uno, zip(modelos, planes)))
    with open(os.path.join(args.carpeta, "comparar.json"), "w", encoding="utf-8") as f:
        json.dump({"prompt": args.prompt, "primer_cuadro": args.primer_cuadro, "resultados": resultados}, f,
                  ensure_ascii=False, indent=1)
    gasto = sum(r.get("costo") or 0 for r in resultados)
    for r in resultados:
        print(("OK   " if r["ok"] else "FALLA") + f" {r['modelo']:40} "
              + (f"{r.get('duracion_clip')} s · {r.get('segundos')} s · " if r["ok"] else f"{r.get('error', '')[:120]} · ")
              + (f"{r['costo']:.4f} USD" if r.get("costo") is not None else "costo ?"))
    print(f"Gastado: {gasto:.4f} USD · detalle en {os.path.join(args.carpeta, 'comparar.json')}")
    if not any(r["ok"] for r in resultados):
        raise SystemExit(4)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def comunes(x, con_res=True):
        if con_res:
            x.add_argument("--resolucion", help="480p|720p|1080p… (por defecto config.json > ilustrado.video_resolucion)")
        x.add_argument("--relacion", choices=RELACIONES, default="16:9")
        x.add_argument("--audio", action="store_true", help="pedir audio generado (más caro)")

    x = sub.add_parser("modelos", help="catálogo con USD/s calculado")
    x.add_argument("--resolucion", default="720p")
    x.add_argument("--relacion", choices=RELACIONES, default="16:9")
    x.add_argument("--audio", action="store_true")
    x.add_argument("--i2v", action="store_true", help="solo los que aceptan primer cuadro")
    x.set_defaults(fn=cmd_modelos)

    x = sub.add_parser("estimar", help="costo previo de un clip")
    comunes(x)
    x.add_argument("--duracion", type=int, required=True)
    x.add_argument("--modelo")
    x.add_argument("--borrador", action="store_true")
    x.set_defaults(fn=cmd_estimar)

    x = sub.add_parser("generar", help="genera un clip")
    comunes(x)
    x.add_argument("--primer-cuadro")
    x.add_argument("--ultimo-cuadro")
    x.add_argument("--prompt")
    x.add_argument("--prompt-archivo")
    x.add_argument("--duracion", type=int, default=5)
    x.add_argument("--modelo", help="id de OpenRouter; por defecto config.json > modelos.video")
    x.add_argument("--borrador", action="store_true", help="resolución de borrador (480p)")
    x.add_argument("--sin-audio", action="store_true")
    x.add_argument("--semilla", type=int)
    x.add_argument("--tope", type=float, help="USD máximos sin --confirmar")
    x.add_argument("--confirmar", action="store_true")
    x.add_argument("--salida", required=True)
    x.set_defaults(fn=cmd_generar)

    x = sub.add_parser("comparar", help="mismo cuadro y prompt en varios modelos, en paralelo")
    comunes(x)
    x.add_argument("--primer-cuadro", required=True)
    x.add_argument("--ultimo-cuadro")
    x.add_argument("--prompt", required=True)
    x.add_argument("--duracion", type=int, default=5)
    x.add_argument("--modelos", required=True, help="ids separados por coma")
    x.add_argument("--borrador", action="store_true")
    x.add_argument("--carpeta", required=True)
    x.add_argument("--confirmar", action="store_true")
    x.set_defaults(fn=cmd_comparar)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
