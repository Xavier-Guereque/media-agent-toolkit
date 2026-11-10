#!/usr/bin/env python3
"""verificar_voz — verifica TTS contra el guion con diff dirigido (no transcripción cruda).

Verificado 2026-09-28: la transcripción literal de `gemini-2.5-flash` confunde marcas y cifras
("ACME" → "Akme"/"Acné", "Banamex" → "Citibanamex", "250" → "550") y produce falsas alarmas.
Por eso aquí se manda el texto esperado y se pregunta SOLO por:
  (a) palabras extra / muletillas (p. ej. "Claro," cuando el modelo responde en vez de leer),
  (b) palabras faltantes,
  (c) la cifra clave de cada línea (si se declara `cifras`).

Uso:
  python3 scripts/verificar_voz.py --guion guion.txt --wav-dir proyectos/<slug>/recursos \
      [--cifras "3=250" "6=3 y 4 de marzo"] [--log proyectos/<slug>/recursos/costos.jsonl]
  python3 scripts/verificar_voz.py --guion guion.txt --wavs a.wav b.wav [--tmp DIR] [--json]

`guion.txt`: una línea por línea de voz, en el mismo orden que voz_1.wav, voz_2.wav… (o que
`--wavs`). Los mp3 temporales van en `--tmp` (por defecto `<carpeta de los wav>/_verificar/`, dentro
del `recursos/` del proyecto, no en /tmp) y se borran al terminar. `--json` pide la respuesta como
lista JSON `[{"audio": 1, "extra": [...], "faltan": [...], "cifra_ok": true|null}]` (la usa promo.py).

Importado:
  from verificar_voz import verificar, parsear_json
  texto = verificar(lineas, wavs=[...], tmp=".../recursos/voz/_verificar", formato="json", log=...)
"""
import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import urllib.request

MODELO = "google/gemini-2.5-flash"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def _key(repo):
    v = os.environ.get("OPENROUTER_API_KEY")
    if v:
        return v
    env = os.path.join(repo, ".env")
    if os.path.exists(env):
        with open(env) as f:
            for l in f:
                if l.startswith("OPENROUTER_API_KEY="):
                    return l.split("=", 1)[1].strip()
    raise SystemExit("Falta OPENROUTER_API_KEY")


def verificar(lineas, wav_dir=None, repo=".", cifras=None, log=None, tmp=None, wavs=None,
              formato="texto", modelo=MODELO):
    """Diff dirigido de cada audio contra su texto esperado. `wavs` (rutas explícitas) tiene
    prioridad sobre `wav_dir`/voz_N.wav. Devuelve el texto de la respuesta del modelo."""
    cifras = cifras or {}
    wavs = list(wavs) if wavs else [os.path.join(wav_dir, f"voz_{i}.wav") for i in range(1, len(lineas) + 1)]
    if len(wavs) != len(lineas):   # zip truncaría en silencio y una toma quedaría sin revisar
        raise ValueError(f"{len(lineas)} líneas de guion pero {len(wavs)} audios: deben coincidir.")
    tmp = tmp or os.path.join(os.path.dirname(os.path.abspath(wavs[0])), "_verificar")
    os.makedirs(tmp, exist_ok=True)
    creados = []
    key = _key(repo)
    parts = [{"type": "text", "text":
              "A continuación audios breves en español mexicano, en orden, y el texto que cada uno "
              "debe decir. Nota: los nombres de marca se transcriben mal con frecuencia (ACME puede "
              "oírse como Siscom/Cisco), así que NO reportes esas confusiones.\n"}]
    for i, (l, wav) in enumerate(zip(lineas, wavs), 1):
        mp3 = os.path.join(tmp, f"vozv_{i}.mp3")
        creados.append(mp3)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                        "-ar", "16000", "-ac", "1", "-b:a", "32k", mp3], check=True)
        parts.append({"type": "text", "text": f"\nAudio {i} — texto esperado: «{l}»\n"})
        parts.append({"type": "input_audio",
                      "input_audio": {"data": base64.b64encode(open(mp3, "rb").read()).decode(),
                                      "format": "mp3"}})
    q = ("\nPara cada audio di SOLO: (a) si contiene palabras extra que no están en el texto esperado "
         "(muletillas tipo 'Claro,', respuestas conversacionales, frases añadidas) — sí/no y cuáles; "
         "(b) si faltan palabras del texto esperado — sí/no y cuáles; (c) si la cifra clave suena "
         "correcta" + (f" (audio(s) {', '.join(cifras)}: {', '.join(k + '=' + v for k, v in cifras.items())})" if cifras else "") +
         ". Formato: una línea por audio.")
    if formato == "json":
        q = q.replace("Formato: una línea por audio.",
                      'Responde SOLO una lista JSON, un objeto por audio: [{"audio": 1, "extra": ["…"], '
                      '"faltan": ["…"], "cifra_ok": true}] (listas vacías si no hay; cifra_ok null si no aplica).')
    parts.append({"type": "text", "text": q})
    body = {"model": modelo, "messages": [{"role": "user", "content": parts}]}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=300))
    finally:
        # Solo se borra lo que se creó aquí; la carpeta, únicamente si quedó vacía.
        for mp3 in creados:
            if os.path.exists(mp3):
                os.remove(mp3)
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    texto = resp["choices"][0]["message"]["content"]
    if log:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a") as f:
            f.write(json.dumps({"id": resp.get("id"), "modelo": modelo, "tarea": "verificacion_voz",
                                "ts": datetime.datetime.now().isoformat(),
                                "usage": resp.get("usage")}) + "\n")
    return texto


def parsear_json(texto):
    """Lista de resultados del modo --json; tolera cercas ```json y texto alrededor. None si no hay."""
    m = re.search(r"\[.*\]", texto or "", re.S)
    if not m:
        return None
    try:
        datos = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, list) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guion", required=True, help="guion.txt, una línea por audio")
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--wav-dir", help="carpeta con voz_1.wav, voz_2.wav…")
    grupo.add_argument("--wavs", nargs="+", help="rutas explícitas de los WAV, en el orden del guion")
    ap.add_argument("--tmp", help="carpeta para los mp3 temporales (default: junto a los wav)")
    ap.add_argument("--json", action="store_true", help="respuesta como lista JSON")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--cifras", nargs="*", default=[], help='p. ej. "3=250" "6=3 y 4 de marzo"')
    ap.add_argument("--log")
    a = ap.parse_args()
    lineas = [l for l in open(a.guion).read().strip().split("\n") if l.strip()]
    cifras = dict(c.split("=", 1) for c in a.cifras)
    print(verificar(lineas, a.wav_dir, a.repo, cifras, a.log, tmp=a.tmp, wavs=a.wavs,
                    formato="json" if a.json else "texto"))


if __name__ == "__main__":
    main()
