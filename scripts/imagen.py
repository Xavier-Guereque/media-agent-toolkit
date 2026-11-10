#!/usr/bin/env python3
"""Genera imágenes con el modelo de `config.json > modelos.imagen` vía OpenRouter (skill `crear-imagen`).

Uso típico:
  python3 scripts/imagen.py generar --prompt-archivo proyectos/x/recursos/prompt.md \
      --referencia proyectos/x/recursos/referencia/ref.jpg --relacion 9:16 \
      --salida proyectos/x/personaje.png

- Las referencias (0..n imágenes) viajan como `image_url` en el mismo mensaje que el prompt:
  el modelo las usa como guía de estilo/composición (edición guiada), no hace falta img2img aparte.
- La key viaja solo a https://openrouter.ai (`comun.post_openrouter`).
- Cada llamada queda en `recursos/costos.jsonl` del proyecto (AGENT §10) y reporta avance al tablero.
- Códigos de salida: 0 OK · 2 argumentos · 3 entorno (key/config) · 4 API (402/403 presupuesto, 4xx/5xx).
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

REPO = comun.raiz_repo(__file__)
RELACIONES = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


def leer_prompt(args):
    partes = []
    if args.prompt_archivo:
        with open(args.prompt_archivo, encoding="utf-8") as f:
            partes.append(f.read().strip())
    if args.prompt:
        partes.append(args.prompt.strip())
    if not partes:
        print("Falta --prompt o --prompt-archivo.", file=sys.stderr)
        raise SystemExit(2)
    return "\n\n".join(partes)


def data_uri(ruta):
    mime = mimetypes.guess_type(ruta)[0] or "image/png"
    with open(ruta, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def carpeta_recursos(salida):
    """`recursos/` del proyecto que contiene a `salida` (o `<carpeta de salida>/recursos` si no está en proyectos/)."""
    ruta = os.path.abspath(salida)
    while True:
        padre = os.path.dirname(ruta)
        if os.path.basename(padre) == "proyectos":
            return os.path.join(ruta, "recursos")
        if padre == ruta:
            return os.path.join(os.path.dirname(os.path.abspath(salida)), "recursos")
        ruta = padre


def guardar_imagenes(imagenes, salida):
    base, ext = os.path.splitext(salida)
    rutas = []
    for i, img in enumerate(imagenes):
        url = img.get("image_url", {}).get("url", "")
        if not url.startswith("data:"):
            print(f"Imagen {i}: formato de respuesta inesperado ({url[:40]}…).", file=sys.stderr)
            continue
        cabecera, b64 = url.split(",", 1)
        tipo = cabecera.split("/")[1].split(";")[0].lower() if "/" in cabecera else "png"
        ext_real = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "webp": ".webp"}.get(tipo)
        ruta = (salida if i == 0 else f"{base}-{i + 1}{ext}")
        # Solo se cambia la extensión si el formato real es otro (.jpg y .jpeg son el mismo): la ruta pedida se respeta.
        if ext_real and ext_real != (".jpg" if ext.lower() == ".jpeg" else ext.lower()):
            ruta = os.path.splitext(ruta)[0] + ext_real
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        with open(ruta, "wb") as f:
            f.write(base64.b64decode(b64))
        rutas.append(ruta)
    return rutas


def cmd_generar(args):
    cfg = comun.cargar_config(REPO)
    modelo = args.modelo or cfg.get("modelos", {}).get("imagen")
    if not modelo:
        print("config.json no define modelos.imagen y no se pasó --modelo.", file=sys.stderr)
        raise SystemExit(3)
    key = comun.api_key(REPO)
    prompt = leer_prompt(args)
    for ref in args.referencia:
        if not os.path.exists(ref):
            print(f"Referencia inexistente: {ref}", file=sys.stderr)
            raise SystemExit(2)
    recursos = carpeta_recursos(args.salida)
    comun.AVANCE_DIR = recursos
    comun.avance("imagen", 0, f"{modelo}: solicitando ({len(args.referencia)} referencia(s))")

    contenido = [{"type": "text", "text": prompt}]
    contenido += [{"type": "image_url", "image_url": {"url": data_uri(r)}} for r in args.referencia]
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": contenido}],
              "modalities": ["image", "text"], "usage": {"include": True}}
    if args.relacion:
        cuerpo["image_config"] = {"aspect_ratio": args.relacion}
    try:
        datos = comun.post_openrouter(cuerpo, key, timeout=args.timeout)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:600]
        if e.code in (402, 403):
            print(f"OpenRouter {e.code}: sin crédito/presupuesto para {modelo}. Comprobar "
                  "`GET https://openrouter.ai/api/v1/auth/key` (limit_remaining) o subir el límite mensual.",
                  file=sys.stderr)
        print(f"Respuesta: {detalle}", file=sys.stderr)
        comun.avance("imagen", 100, f"error HTTP {e.code}", estado="error")
        raise SystemExit(4)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"Sin respuesta de OpenRouter: {e}", file=sys.stderr)
        comun.avance("imagen", 100, "sin respuesta", estado="error")
        raise SystemExit(4)

    comun.log_costo(recursos, {"id": datos.get("id"), "modelo": modelo, "tarea": "imagen",
                               "usage": datos.get("usage")})
    mensaje = (datos.get("choices") or [{}])[0].get("message", {})
    imagenes = mensaje.get("images") or []
    if not imagenes:
        print("La respuesta no trajo imágenes. Texto del modelo:", file=sys.stderr)
        print((mensaje.get("content") or "")[:800], file=sys.stderr)
        comun.avance("imagen", 100, "sin imágenes", estado="error")
        raise SystemExit(4)
    rutas = guardar_imagenes(imagenes, args.salida)
    costo = (datos.get("usage") or {}).get("cost")
    comun.avance("imagen", 100, f"{len(rutas)} imagen(es)", estado="listo",
                 datos={"costo_usd": costo} if costo is not None else None)
    for r in rutas:
        print(f"OK -> {r}")
    if costo is not None:
        print(f"Costo: {costo:.4f} USD (id {datos.get('id')})")
    if mensaje.get("content"):
        print(f"Nota del modelo: {mensaje['content'][:300]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generar", help="genera una imagen (opcionalmente guiada por referencias)")
    g.add_argument("--prompt", help="texto del prompt")
    g.add_argument("--prompt-archivo", help="archivo con el prompt (se concatena con --prompt)")
    g.add_argument("--referencia", action="append", default=[], help="imagen de referencia (repetible)")
    g.add_argument("--salida", required=True, help="PNG/JPG de salida (en la raíz del proyecto)")
    g.add_argument("--modelo", help="id de OpenRouter; por defecto config.json > modelos.imagen")
    g.add_argument("--relacion", choices=RELACIONES, help="relación de aspecto (image_config.aspect_ratio)")
    g.add_argument("--timeout", type=int, default=240)
    g.set_defaults(fn=cmd_generar)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
