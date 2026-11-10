#!/usr/bin/env python3
"""narrar — voz en off por escena con tiempos medidos (nunca del guion): cursos y explicadores.

Toma una lista de escenas, las revisa con lint_voz ANTES de pagar, sintetiza una toma por escena con caché por huella,
mide cada WAV y deriva de ahí la duración de la escena, los tiempos por palabra y los subtítulos.

  dur = max(min, colchon_inicio + voz + pausa)      la voz entra `colchon_inicio` s después del inicio de la escena

Módulo (lo usa scripts/curso.py):
  r = narrar.narrar(escenas, rec, voz.resolver_voz(spec_voz, cfg), costos_dir=…, opciones=cfg["cursos"])
  → {"codigo": 0|2|3, "issues", "tiempos", "cues", "nuevas", "cache", "caracteres"}
  Escribe rec/voz/<id>.wav, rec/voz/cache.json, rec/tiempos.json, rec/voz.wav.

CLI (explicadores sueltos, mismo contrato que tenía el narrar.py del proyecto Star Trek):
  python3 scripts/narrar.py <proyecto> [--solo-lint]     lee recursos/guion.json {"voz", "escenas": [{id, tipo, min, tts}]}

Tiempos por palabra: `marcas_whisper` (faster-whisper en ~/.venvs/whisper, opcional) o reparto por sílabas.
"""
import difflib
import json
import os
import re
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import lint_voz  # noqa: E402
import subtitulos  # noqa: E402
import voz  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_WHISPER = os.path.expanduser("~/.venvs/whisper/bin/python")
OPCIONES = {"colchon_inicio": 0.35, "pausa_escena": 0.6, "pausa_pregunta": 5.0, "cola": 0.5, "seg_por_silaba": 0.20}
_SCRIPT_WHISPER = """
import json, sys, wave
import numpy as np
from faster_whisper import WhisperModel
with wave.open(sys.argv[1], "rb") as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
m = WhisperModel("small", device="cpu", compute_type="int8")
seg, _ = m.transcribe(audio, language="es", word_timestamps=True, beam_size=5, vad_filter=False)
print(json.dumps([[float(x.start), float(x.end), x.word.strip()] for s in seg for x in (s.words or []) if x.word.strip()]))
"""


def _leer(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _escribir(p, d, indent=1):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=indent)


def norm(palabra):
    """Minúsculas sin acentos ni puntuación: para buscar la palabra del guion en la toma."""
    t = unicodedata.normalize("NFD", lint_voz.nucleo(palabra).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def silabas_texto(texto):
    return sum(voz.silabas(tok) for tok in texto.split()) or 1


def pausa_de(e, op):
    if e.get("pausa") is not None:
        return float(e["pausa"])
    return op["pausa_pregunta"] if e.get("plantea") else op["pausa_escena"]


def estimar_duracion(escenas, opciones=None):
    """Segundos estimados de una lección antes de pagar el TTS (sílabas × s/sílaba de la voz)."""
    op = {**OPCIONES, **(opciones or {})}
    total = 0.0
    for e in escenas:
        tts = (e.get("tts") or "").strip()
        dv = silabas_texto(tts) * op["seg_por_silaba"] if tts else 0.0
        total += max(float(e.get("min") or 0), op["colchon_inicio"] + dv + pausa_de(e, op) if tts else 0.0)
    return total + op["cola"]


def palabras_por_silabas(tts, ini, fin):
    """[{w, a, b}] repartiendo el tramo de habla por sílabas (respaldo sin Whisper)."""
    toks = tts.split()
    pesos = [voz.silabas(t) for t in toks]
    total = sum(pesos) or 1
    t, salida = ini, []
    for tok, n in zip(toks, pesos):
        d = (fin - ini) * n / total
        salida.append({"w": tok, "a": round(t, 3), "b": round(t + d, 3)})
        t += d
    return salida


def alinear_marcas(tts, marcas, ini, fin):
    """Marcas de Whisper [(a, b, palabra)] → palabras del GUION: lo que dice el guion manda; lo que Whisper no
    reconoció hereda el reparto por sílabas."""
    base = palabras_por_silabas(tts, ini, fin)
    a, b = [norm(p["w"]) for p in base], [norm(m[2]) for m in marcas]
    for bloque in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(bloque.size):
            p, m = base[bloque.a + k], marcas[bloque.b + k]
            p["a"], p["b"] = round(ini + m[0], 3), round(ini + m[1], 3)
    return base


def marcas_whisper(wav):
    """Marcas por palabra de una toma, o None si faster-whisper no está. Caché junto a la toma."""
    cache = wav[:-4] + ".palabras.json"
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(wav):
        return _leer(cache)
    if not os.path.exists(PY_WHISPER):
        return None
    crudo = wav[:-4] + ".16k.wav"
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", wav, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", crudo])
    try:
        r = subprocess.run([PY_WHISPER, "-c", _SCRIPT_WHISPER, crudo], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    finally:
        if os.path.exists(crudo):
            os.remove(crudo)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    marcas = json.loads(r.stdout.strip().splitlines()[-1])
    _escribir(cache, marcas, indent=None)
    return marcas


def tiempo_de(palabras, frase, desde=0.0):
    """(inicio, fin) de la primera aparición de `frase` que arranca en `desde` o después, o None si no se dice.
    Para la siguiente mención, pasa como `desde` el fin devuelto."""
    objetivo = [norm(t) for t in frase.split() if norm(t)]
    if not objetivo:
        return None
    toks = [norm(p["w"]) for p in palabras]
    for i in range(len(toks) - len(objetivo) + 1):
        if toks[i:i + len(objetivo)] == objetivo and palabras[i]["a"] >= desde - 1e-6:
            return palabras[i]["a"], palabras[i + len(objetivo) - 1]["b"]
    return None


def _colocar_voz(tiempos, rec, total):
    """voz.wav: tomas colocadas en su inicio con adelay + amix sin normalizar."""
    con_voz = [x for x in tiempos if x["wav"]]
    salida = os.path.join(rec, "voz.wav")
    if not con_voz:
        comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                   "-t", f"{total:.3f}", "-c:a", "pcm_s16le", salida])
        return salida
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    for x in con_voz:
        cmd += ["-i", os.path.join(rec, x["wav"])]
    fc = "".join(f"[{i}]adelay={int(x['voz_inicio'] * 1000)}:all=1[a{i}];" for i, x in enumerate(con_voz))
    fc += "".join(f"[a{i}]" for i in range(len(con_voz)))
    fc += f"amix=inputs={len(con_voz)}:duration=longest:normalize=0,apad=whole_dur={total}[v]"
    script = os.path.join(rec, "voz", "mezcla_voz.txt")
    with open(script, "w", encoding="utf-8") as f:
        f.write(fc)
    comun.run(cmd + ["-filter_complex_script", script, "-map", "[v]", "-t", f"{total:.3f}", "-ar", "48000", "-ac", "1",
                     "-c:a", "pcm_s16le", salida])
    return salida


def cues_de(tiempos, tts_por_id, total, max_car=42):
    cues = []
    for x in tiempos:
        if x["wav"]:
            a = x["voz_inicio"] + voz.COLCHON
            cues += subtitulos.cues_de_fragmento(a, max(a + 0.3, x["voz_inicio"] + x["voz_dur"]), tts_por_id[x["id"]], max_car)
    return [{"ini": round(c["ini"], 3), "fin": round(c["fin"], 3), "lineas": c["lineas"]}
            for c in subtitulos.ajustar_tiempos(cues, total)]


def escribir_subtitulos(cues, ruta_sin_ext):
    srt, vtt = ruta_sin_ext + ".srt", ruta_sin_ext + ".vtt"
    with open(srt, "w", encoding="utf-8") as f:
        f.write(subtitulos.a_srt(cues))
    with open(vtt, "w", encoding="utf-8") as f:
        f.write(subtitulos.a_vtt(cues))
    return srt, vtt


def mezclar_cama(voz_wav, cama_wav, salida, voz_lufs=-16, musica_lufs=-26):
    """Opcional: música con ducking bajo la voz. La evidencia desaconseja música bajo narración (Metodologia-Cursos-Video)."""
    fc = (f"[0]loudnorm=I={voz_lufs}:TP=-2:LRA=11,asplit=2[v][k];[1]loudnorm=I={musica_lufs}:TP=-3:LRA=11[m];"
          "[m][k]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=300[d];"
          "[v][d]amix=inputs=2:duration=first:normalize=0[o]")
    comun.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", voz_wav, "-stream_loop", "-1", "-i", cama_wav,
               "-filter_complex", fc, "-map", "[o]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", salida])
    return salida


def narrar(escenas, rec, res, *, repo=REPO, costos_dir=None, sintetizar=None, marcas_lint=(), opciones=None,
           al_avance=None, solo_lint=False, usar_whisper=True, max_car=42):
    op = {**OPCIONES, **(opciones or {})}
    carpeta = os.path.join(rec, "voz")
    os.makedirs(carpeta, exist_ok=True)
    modelo = res["modelo"]
    habladas = [e for e in escenas if (e.get("tts") or "").strip()]
    issues = lint_voz.revisar([{"ruta": e["id"], "texto": e["tts"], "tts": e["tts"]} for e in habladas], modelo, marcas_lint)
    salida = {"codigo": 0, "issues": issues, "tiempos": None, "cues": [], "nuevas": 0, "cache": 0,
              "caracteres": sum(len(e["tts"]) for e in habladas), "sync_estimada": False}
    if any(i["severidad"] == "E" for i in issues):
        salida["codigo"] = 2
        return salida
    if solo_lint:
        return salida
    try:
        sint = sintetizar or voz.proveedor({}, repo, modelo, res)
    except voz.ErrorEntornoVoz as ex:
        salida["codigo"] = 3
        issues.append({"codigo": "E-ENTORNO", "severidad": "E", "ruta": "-", "msg": str(ex), "arreglo": ""})
        return salida
    ruta_cache = os.path.join(carpeta, "cache.json")
    cache = _leer(ruta_cache) if os.path.exists(ruta_cache) else {}
    for k, e in enumerate(habladas):
        h = voz.huella_linea(e["tts"], res["voz"], modelo, res["estilo"], res["proveedor"], res["voice"], res["instructions"])
        if os.environ.get("PROMO_TTS_STUB"):      # una toma simulada nunca debe pasar por voz real en la caché
            h = f"stub-{h}"
        wav = os.path.join(carpeta, f"{e['id']}.wav")
        ent = cache.get(e["id"])
        if ent and ent.get("hash") == h and os.path.exists(wav):
            salida["cache"] += 1
        else:
            buena = False
            for intento in range(2):
                pcm, sr, gid, usage = sint(e["tts"], res.get("estilo"))
                voz.guardar_toma(pcm, sr, wav, carpeta)
                if gid or usage:
                    comun.log_costo(costos_dir or rec, {"id": gid, "modelo": modelo, "tarea": "voz", "usage": usage})
                d = comun.dur(wav)
                sps = d / silabas_texto(e["tts"])
                if sps <= voz.SEG_POR_SILABA_MAX:
                    buena = True
                    break
            if not buena:
                issues.append({"codigo": "E-TTS-LENTO", "severidad": "E", "ruta": e["id"],
                               "msg": f"{sps:.2f} s/sílaba en dos intentos (> {voz.SEG_POR_SILABA_MAX}): el modelo agregó texto.",
                               "arreglo": "Reescribe la línea como oración con sujeto y verbo."})
                salida["codigo"] = 2
                cache.pop(e["id"], None)          # una toma mala no se cachea: el reintento debe volver a sintetizar
            else:
                cache[e["id"]] = {"hash": h, "dur": round(d, 3), "s_por_silaba": round(sps, 3)}
            _escribir(ruta_cache, cache)
            salida["nuevas"] += 1
        if al_avance:
            al_avance(100 * (k + 1) / len(habladas), e["id"])
    if salida["codigo"]:
        return salida
    t, tiempos = 0.0, []
    con_whisper = usar_whisper and habladas and not os.environ.get("PROMO_TTS_STUB")
    for e in escenas:
        tts = (e.get("tts") or "").strip()
        wav = os.path.join(carpeta, f"{e['id']}.wav")
        dv = comun.dur(wav) if tts else 0.0
        dur = round(max(float(e.get("min") or 0), (op["colchon_inicio"] + dv + pausa_de(e, op)) if tts else 0.0), 3)
        x = {"id": e["id"], "tipo": e.get("tipo"), "inicio": round(t, 3), "fin": round(t + dur, 3), "voz_inicio": None,
             "voz_dur": round(dv, 3), "wav": None, "palabras": []}
        if tts:
            x["voz_inicio"], x["wav"] = round(t + op["colchon_inicio"], 3), f"voz/{e['id']}.wav"
            a, b = x["voz_inicio"] + voz.COLCHON, x["voz_inicio"] + dv
            marcas = marcas_whisper(wav) if con_whisper else None
            if marcas:
                x["palabras"] = alinear_marcas(tts, marcas, x["voz_inicio"], b)
            else:
                x["palabras"] = palabras_por_silabas(tts, a, b)
                salida["sync_estimada"] = True
        tiempos.append(x)
        t += dur
    total = round(t + op["cola"], 3)
    doc = {"version": 1, "duracion": total,
           "voz": {"proveedor": res["proveedor"], "modelo": modelo, "voice": res.get("voice")}, "escenas": tiempos}
    _escribir(os.path.join(rec, "tiempos.json"), doc)
    _colocar_voz(tiempos, rec, total)
    salida["tiempos"] = doc
    salida["cues"] = cues_de(tiempos, {e["id"]: e.get("tts") for e in habladas}, total, max_car)
    return salida


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    proyecto = args[0] if os.path.isabs(args[0]) else os.path.join(REPO, args[0])
    rec = os.path.join(proyecto, "recursos")
    comun.AVANCE_DIR = rec
    guion = _leer(os.path.join(rec, "guion.json"))
    res = voz.resolver_voz(guion.get("voz") or {}, comun.cargar_config(REPO))
    r = narrar(guion["escenas"], rec, res, solo_lint="--solo-lint" in sys.argv,
               al_avance=lambda pct, d: comun.avance("voz", pct, d))
    for i in r["issues"]:
        print(f"{i['codigo']}  {i['ruta']}: {i['msg']} {i['arreglo']}")
    if r["tiempos"]:
        slug = re.sub(r"_\d{8}$", "", os.path.basename(proyecto.rstrip("/")))
        escribir_subtitulos(r["cues"], os.path.join(proyecto, slug))
        print(f"{r['nuevas']} nuevas · {r['cache']} en caché · {r['tiempos']['duracion']:.1f} s · {len(r['cues'])} cues")
    return r["codigo"]


if __name__ == "__main__":
    sys.exit(main())
