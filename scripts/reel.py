#!/usr/bin/env python3
"""reel — pipeline genérico de reels verticales narrados (versión base del toolkit).

Recetas verificadas 2026-09-28 (ver docs/Lecciones-2026-09-28-reel-syscomexpo2027.md):
  - escenas independientes con duración exacta y Ken Burns, unidas con xfade (fps=30,settb=AVTB)
  - tarjeta de logos con alfa compuesto por overlay (pad NO aplana el alfa)
  - mosaico dimensionado al cuadro final (celdas = W/cols x H/rows)
  - ASS con kickers numerados, barra de progreso (\\p1) y captions con resalte
    OJO: los tiempos de \\move son ms RELATIVOS al evento
  - audio: voz -15 LUFS + música procedural -18 LUFS con ducking suave (ratio 3)

Uso:
  python3 scripts/reel.py --spec proyectos/<slug>/reel.json todo
  etapas | segmentos | ass | audio | video | todo | verificar

El spec (JSON) describe salida, escenas, voz, música y ducking. Ver scripts/reel.ejemplo.json.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

FPS_DEF = 30
HL_ON, HL_OFF = r"{\c&H00D7FF&}", r"{\c&HFFFFFF&}"


# ---------------------------------------------------------------- utilidades
def run(cmd, log=True):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        if log:
            print("FALLO:", " ".join(str(c) for c in cmd[:10]))
        print(r.stderr[-1800:])
        raise SystemExit(1)
    return r


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", p], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip())


def api_key(repo, spec):
    v = spec.get("api_key_env", "OPENROUTER_API_KEY")
    if os.environ.get(v):
        return os.environ[v]
    env = os.path.join(repo, ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8") as f:
            for l in f:
                if l.startswith(v + "="):
                    return l.split("=", 1)[1].strip()
    raise SystemExit(f"Falta {v} (entorno o {env})")


class Reel:
    @staticmethod
    def _raiz_repo(desde):
        """Sube desde el proyecto hasta la raíz del toolkit (la que tiene .env/.git/AGENT.md).

        Antes se usaba `dirname(proyectos/<slug>)` = `proyectos/`, así que `api_key`
        buscaba el `.env` en el lugar equivocado y el paso `audio` fallaba siempre.
        """
        actual = os.path.abspath(desde)
        while True:
            if any(os.path.exists(os.path.join(actual, m))
                   for m in (".env", "AGENT.md", ".git", ".env.example")):
                return actual
            padre = os.path.dirname(actual)
            if padre == actual:
                return os.path.abspath(desde)
            actual = padre

    def __init__(self, spec_path):
        self.spec_path = os.path.abspath(spec_path)
        self.proj = os.path.dirname(self.spec_path)
        self.repo = self._raiz_repo(self.proj)
        self.spec = json.load(open(self.spec_path, encoding="utf-8"))
        s = self.spec.get("salida", {})
        self.W = s.get("w", 1080)
        self.H = s.get("h", 1920)
        self.FPS = s.get("fps", FPS_DEF)
        self.XF = s.get("xfade", 0.5)
        self.TRANS = s.get("transiciones", [])
        self.rec = os.path.join(self.proj, "recursos")
        self.seg = os.path.join(self.rec, "segmentos_")
        self.escenas = list(self.spec["escenas"])
        self.trans = [float(e.get("duracion", 5.0)) for e in self.escenas]
        self.total = sum(self.trans) - self.XF * (len(self.trans) - 1)

    # ------------------------------------------------------------ assets
    def p(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.rec, rel)

    def crop916(self, src, out):
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", self.p(src), "-vf",
             f"scale={self.W*2}:{self.H*2}:force_original_aspect_ratio=increase,"
             f"crop={self.W*2}:{self.H*2}", "-frames:v", "1", out])

    def etapa_assets(self):
        os.makedirs(self.seg, exist_ok=True)
        for i, e in enumerate(self.escenas):
            t = e.get("tipo", "foto")
            if t == "tarjeta_logos":
                self.canvas_tarjeta(e, os.path.join(self.seg, f"canvas_{i}.png"))
            elif t == "mosaico":
                self.canvas_mosaico(e, os.path.join(self.seg, f"canvas_{i}.png"))
            elif t == "cierre":
                self.canvas_cierre(e, os.path.join(self.seg, f"canvas_{i}.png"))
            elif t == "cortes":
                for j, f in enumerate(e["fuentes"]):
                    self.crop916(f, os.path.join(self.seg, f"p_{i}_{j}.png"))
            else:
                self.crop916(e["fuente"], os.path.join(self.seg, f"p_{i}.png"))
        print("assets listos")

    def canvas_tarjeta(self, e, out):
        """Tarjeta clara con logos. Los PNG de marca traen alfa: se compone con overlay."""
        logos = [self.p(x) for x in e["logos"]]
        cols = e.get("cols", 3)
        rows = (len(logos) + cols - 1) // cols
        cw, ch = e.get("celda", [280, 150])
        card_w = cols * cw + 40
        card_h = rows * ch + 50
        card_x, card_y = (self.W - card_w) // 2, (self.H - card_h) // 2
        ins = ["-f", "lavfi", "-i", f"color=c={e.get('color_tarjeta', '0xEFF2F7')}:s={card_w}x{card_h}"]
        for lg in logos:
            ins += ["-i", lg]
        ins += ["-i", self.p(e["fuente"])]
        bg = len(logos) + 1
        bl = e.get("blur", 26)
        filt = [f"[{bg}:v]scale={self.W}:{self.H}:force_original_aspect_ratio=increase,"
                f"crop={self.W}:{self.H},boxblur={bl}:2,"
                f"eq=brightness={e.get('brillo', -0.34)}:saturation={e.get('saturacion', 0.8)},"
                f"format=yuv420p[bg]",
                f"[bg][0:v]overlay={card_x}:{card_y}[base]"]
        prev = "base"
        for j, _ in enumerate(logos):
            col, row = j % cols, j // cols
            cx, cy = card_x + 20 + col * cw, card_y + 25 + row * ch
            mw, mh = e.get("logo_max", [190, 85])
            filt.append(f"[{j+1}:v]format=rgba,scale={mw}:{mh}:force_original_aspect_ratio=decrease[lg{j}]")
            last = j == len(logos) - 1
            out_tag = "out" if last else f"o{j}"
            filt.append(f"[{prev}][lg{j}]overlay=x={cx}+({cw}-w)/2:y={cy}+({ch}-h)/2[{out_tag}]")
            prev = out_tag
        filt.append("[out]format=yuv420p[final]")
        run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", ";".join(filt),
             "-map", "[final]", "-frames:v", "1", out])

    def canvas_mosaico(self, e, out):
        """Mosaico: cada celda se dimensiona al CUADRO FINAL, no a la foto completa."""
        fuentes, cols = e["fuentes"], e.get("cols", 2)
        rows = (len(fuentes) + cols - 1) // cols
        cw, ch = self.W // cols, self.H // rows
        ins, filt, tags = [], [], []
        for i, f in enumerate(fuentes):
            ins += ["-i", self.p(f)]
            filt.append(f"[{i}:v]scale={cw}:{ch}:force_original_aspect_ratio=increase,"
                        f"crop={cw}:{ch},setsar=1[v{i}]")
            tags.append(f"[v{i}]")
        rt = []
        for r in range(rows):
            row = tags[r * cols:(r + 1) * cols]
            while len(row) < cols:
                row = row + [row[-1]]
            filt.append("".join(row) + f"hstack=inputs={cols}[r{r}]")
            rt.append(f"[r{r}]")
        filt.append("".join(rt) + f"vstack=inputs={rows}[out]")
        run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", ";".join(filt),
             "-map", "[out]", "-frames:v", "1", out])

    def canvas_cierre(self, e, out):
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", self.p(e["fuente"]), "-vf",
             f"scale={self.W}:{self.H}:force_original_aspect_ratio=increase,crop={self.W}:{self.H},"
             f"boxblur={e.get('blur', 24)}:2,eq=brightness={e.get('brillo', -0.42)}:"
             f"saturation={e.get('saturacion', 0.85)},format=yuv420p",
             "-frames:v", "1", out])

    # ------------------------------------------------------------ segmentos
    def kb(self, png, out, d, movimiento="zoom_in", fuerza=0.0009, zmax=1.30):
        frames = int(round(d * self.FPS))
        W, H, F = self.W, self.H, self.FPS
        if movimiento == "zoom_in":
            vf = (f"zoompan=z='min(1.0+{fuerza}*on,{zmax})':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={F}")
        elif movimiento == "zoom_out":
            vf = (f"zoompan=z='max({zmax}-{fuerza}*on,1.0)':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={F}")
        elif movimiento == "pan_lr":
            vf = f"crop={W}:{H}:x='(iw-{W})*min(t/{d},1)':y='(ih-{H})/2',fps={F}"
        elif movimiento == "pan_rl":
            vf = f"crop={W}:{H}:x='(iw-{W})*(1-min(t/{d},1))':y='(ih-{H})/2',fps={F}"
        else:
            vf = f"scale={W}:{H},fps={F}"
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", str(d), "-i", png,
             "-vf", f"{vf},format=yuv420p", "-t", str(d), "-r", str(F),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])

    def etapa_segmentos(self):
        os.makedirs(self.seg, exist_ok=True)
        for i, e in enumerate(self.escenas):
            t = e.get("tipo", "foto")
            d = self.trans[i]
            out = os.path.join(self.seg, f"seg_{i}.mp4")
            if t == "cortes":
                n = len(e["fuentes"])
                sx = e.get("xfade_sub", 0.3)
                each = round((d + (n - 1) * sx) / n, 3)
                subs = []
                for j in range(n):
                    sp = os.path.join(self.seg, f"sub_{i}_{j}.mp4")
                    self.kb(os.path.join(self.seg, f"p_{i}_{j}.png"), sp, each,
                            "zoom_in" if j % 2 == 0 else "zoom_out",
                            e.get("fuerza", 0.0016), e.get("zoom_max", 1.20))
                    subs.append(sp)
                ins, filt, cur = [], [], None
                for j, sp in enumerate(subs):
                    ins += ["-i", sp]
                    filt.append(f"[{j}:v]fps={self.FPS},settb=AVTB[v{j}]")
                acum = 0.0
                cur = "[v0]"
                for j in range(1, n):
                    acum += each - sx
                    tag = "[vc]" if j == n - 1 else f"[c{j}]"
                    filt.append(f"{cur}[v{j}]xfade=transition=fade:duration={sx}:offset={round(acum,3)}{tag}")
                    cur = tag
                run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", ";".join(filt),
                     "-map", "[vc]", "-t", str(d), "-r", str(self.FPS),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])
            elif t == "cierre":
                canvas = os.path.join(self.seg, f"canvas_{i}.png")
                frames = int(round(d * self.FPS))
                ins = ["-loop", "1", "-t", str(d), "-i", canvas]
                filt = [f"[0:v]zoompan=z='min(1.0+{e.get('fuerza',0.0005)}*on,{e.get('zoom_max',1.12)})':"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={self.W}x{self.H}:fps={self.FPS}[bg]"]
                prev = "[bg]"
                if e.get("logo"):
                    ins += ["-loop", "1", "-t", str(d), "-i", self.p(e["logo"])]
                    lw = e.get("logo_ancho", 820)
                    ly = e.get("logo_y", 520)
                    filt.append(f"[1:v]format=rgba,scale={lw}:-1,fade=t=in:st=0:d={e.get('logo_fade',0.8)}:alpha=1[lg]")
                    filt.append(f"{prev}[lg]overlay=(W-w)/2:{ly}:enable='gte(t,{e.get('logo_delay',0.6)})'[v]")
                    prev = "[v]"
                filt.append(f"{prev}format=yuv420p[vout]")
                run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", ";".join(filt),
                     "-map", "[vout]", "-t", str(d), "-r", str(self.FPS),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])
            else:
                src = os.path.join(self.seg, f"canvas_{i}.png") if t in ("tarjeta_logos", "mosaico") \
                    else os.path.join(self.seg, f"p_{i}.png")
                self.kb(src, out, d, e.get("movimiento", "zoom_in"),
                        e.get("fuerza", 0.0009), e.get("zoom_max", 1.30))
            print(f"  {e.get('clave', i)}: {dur(out):.3f}s (objetivo {d})")

    # ------------------------------------------------------------ subtítulos
    def etapa_ass(self):
        s = self.spec["salida"]
        N = len(self.escenas)
        starts, acc = [], 0.0
        for i, d in enumerate(self.trans):
            starts.append(acc - i * self.XF)
            acc += d
        total = acc - (N - 1) * self.XF

        def ts(t):
            h = int(t // 3600); m = int((t % 3600) // 60); sec = t % 60
            return f"{h:d}:{m:02d}:{sec:05.2f}"

        def resaltar(txt):
            return txt.replace("{hl}", HL_ON).replace("{/hl}", HL_OFF)

        # La barra de progreso es OPT-IN: si el spec no trae `salida.barra`, no se dibuja.
        # Junto con los kickers numerados ("01 · SECCIÓN") es lo que hacía que los videos
        # se vieran como una presentación en vez de un reel.
        barra = s.get("barra") or {}
        con_barra = bool(barra)
        X0, BARW = barra.get("x", self.W // 2), barra.get("ancho", 480)
        Y0, BARH = barra.get("y", 124), barra.get("alto", 8)
        KX, KY = s.get("kicker_pos", [60, 112])
        CY = s.get("caption_y", 1560)
        ev = []
        if con_barra:
            ev.append(("BarraTrack", 0.3, total,
                       r"{\pos(%d,%d)\p1}m 0 0 l %d 0 l %d %d l 0 %d{\p0}"
                       % (X0, Y0, BARW, BARW, BARH, BARH)))
        for i, e in enumerate(self.escenas):
            ini = starts[i] + 0.05 if i else 0.0
            fin = starts[i] + self.trans[i] - 0.05
            if con_barra:
                w = int(BARW * (i + 1) / N)
                ev.append(("Barra", ini, fin,
                           r"{\pos(%d,%d)\p1}m 0 0 l %d 0 l %d %d l 0 %d{\p0}"
                           % (X0, Y0, w, w, BARH, BARH)))
            if e.get("kicker"):
                ev.append(("Kicker", starts[i] + 0.35, min(fin, starts[i] + self.trans[i] - 0.25),
                           r"{\pos(%d,%d)}" % (KX, KY) + e["kicker"]))
            if e.get("caption"):
                cini = max(0.0, ini + s.get("caption_delay", 0.45))
                cfin = min(total, cini + e.get("caption_dur", self.trans[i] - 0.6))
                ev.append(("Voz", cini, cfin, r"{\pos(%d,%d)}" % (self.W // 2, CY) + resaltar(e["caption"])))
            st = e.get("sticker")
            if st:
                zona = st.get("zona", "top")
                mv = r"{\move(540,-200,540,330,250,750)" if zona == "top" else r"{\move(540,2120,540,1230,250,750)"
                ev.append(("Sticker", starts[i] + st.get("delay", 0.0), fin,
                           mv + r"\fad(200,300)\c&H00D7FF&}" + st["texto"]))
        # lockup de cierre
        for i, e in enumerate(self.escenas):
            if e.get("tipo") != "cierre":
                continue
            ys = e.get("lockup_y", [1010, 1110, 1175])
            items = [e.get("url")] + list(e.get("lineas", []))
            for k, txt in enumerate([x for x in items if x]):
                estilo = "Cierre" if k == 0 else "CierreChico"
                y = ys[min(k, len(ys) - 1)]
                ev.append((estilo, starts[i] + 1.6 + 0.5 * k, total - 0.2,
                           r"{\pos(%d,%d)\fad(400,300)}" % (self.W // 2, y) + txt))
        ev.sort(key=lambda x: x[1])
        ass = f"""[Script Info]
Title: {s.get('titulo', 'Reel')}
ScriptType: v4.00+
PlayResX: {self.W}
PlayResY: {self.H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Voz, Arial, {s.get('fuente_caption', 62)}, &H00FFFFFF, &H00FFFFFF, &H00101010, &H80000000, 1, 0, 0, 0, 100, 100, 1, 0, 1, 6, 3, 5, 60, 60, 60, 1
Style: Kicker, Arial, {s.get('fuente_kicker', 40)}, &H00FFFFFF, &H00FFFFFF, &H00101010, &H80000000, 1, 0, 0, 0, 100, 100, 2, 0, 1, 4, 2, 7, 0, 0, 0, 1
Style: Sticker, Arial, {s.get('fuente_sticker', 92)}, &H00FFFFFF, &H00FFFFFF, &H00101010, &H80000000, 1, 0, 0, 0, 100, 100, 2, 0, 1, 6, 4, 5, 40, 40, 60, 1
Style: Cierre, Arial, {s.get('fuente_cierre', 66)}, &H00FFFFFF, &H00FFFFFF, &H00101010, &H80000000, 1, 0, 0, 0, 100, 100, 2, 0, 1, 5, 3, 5, 40, 40, 60, 1
Style: CierreChico, Arial, {s.get('fuente_cierre_chico', 44)}, &H00D7FFE8, &H00FFFFFF, &H00101010, &H80000000, 0, 0, 0, 0, 100, 100, 1, 0, 1, 4, 2, 5, 40, 40, 60, 1
Style: Barra, Arial, 20, &H0000D7FF, &H0000D7FF, &H00000000, &H00000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 0, 0, 7, 0, 0, 0, 1
Style: BarraTrack, Arial, 20, &H60FFFFFF, &H60FFFFFF, &H00000000, &H00000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 0, 0, 7, 0, 0, 0, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        for estilo, ini, fin, txt in ev:
            ass += f"Dialogue: 0,{ts(ini)},{ts(fin)},{estilo},,0,0,0,,{txt}\n"
        open(os.path.join(self.rec, "subs.ass"), "w", encoding="utf-8").write(ass)
        json.dump({"total": round(total, 3), "starts": [round(x, 3) for x in starts],
                   "offsets": [{"linea": i + 1, "offset": round(starts[i] + self.spec["voz"].get("offset", 0.6), 2)}
                               for i in range(N)]},
                  open(os.path.join(self.rec, "offsets.json"), "w", encoding="utf-8"), indent=2)
        print(f"subs.ass listo ({len(ev)} eventos) · total {total:.2f}s")

    # ------------------------------------------------------------ audio
    def tts(self, texto, pcm, voz):
        key = api_key(self.repo, self.spec)
        payload = {"model": self.spec.get("modelo_voz", "openai/gpt-audio-mini"),
                   "modalities": ["text", "audio"],
                   "audio": {"voice": voz, "format": "pcm16"}, "stream": True,
                   "messages": [{"role": "system",
                                 "content": self.spec["voz"].get("system",
                                            "Eres una locutora mexicana profesional. Repite verbatim el texto "
                                            "del usuario, sin confirmaciones ni palabras extra. Tono cálido, "
                                            "natural y energético, ritmo ágil, español de México.")},
                                {"role": "user", "content": texto}]}
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        import base64
        chunks, gid, usage = [], None, None
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ch = json.loads(data)
                except json.JSONDecodeError:
                    continue
                gid = gid or ch.get("id")
                usage = ch.get("usage") or usage
                for c in ch.get("choices", []):
                    a = (c.get("delta") or {}).get("audio") or {}
                    if a.get("data"):
                        chunks.append(a["data"])
        if not chunks:
            raise SystemExit("TTS: sin audio")
        open(pcm, "wb").write(base64.b64decode("".join(chunks)))
        import datetime
        with open(os.path.join(self.rec, "costos.jsonl"), "a", encoding="utf-8") as f:
            e = {"id": gid, "modelo": payload["model"], "tarea": "tts",
                 "ts": datetime.datetime.now().isoformat()}
            if usage:
                e["usage"] = usage
            f.write(json.dumps(e) + "\n")

    def etapa_audio(self):
        v = self.spec["voz"]
        off = json.load(open(os.path.join(self.rec, "offsets.json"), encoding="utf-8"))["offsets"]
        lineas = v["lineas"]
        voz = v.get("voz", "coral")
        ins, filt, tags = [], [], []
        for i, txt in enumerate(lineas, 1):
            wav = os.path.join(self.rec, f"voz_{i}.wav")
            if v.get("regenerar", False) or not os.path.exists(wav):
                pcm = os.path.join(self.rec, f"voz_{i}.pcm")
                self.tts(txt, pcm, voz)
                # Colchón de silencio: el PCM del TTS arranca en la primera muestra (sin
                # ataque), y la primera sílaba se oía cortada al entrar en la mezcla.
                colchon = int(round(float(v.get("colchon_inicio", 0.12)) * 1000))
                run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1",
                     "-i", pcm, "-af", f"adelay={colchon}:all=1",
                     "-ar", "48000", "-ac", "2", wav])
                print(f"  TTS línea {i}: {dur(wav):.2f}s")
            ins += ["-i", wav]
            ms = int(round(off[i - 1]["offset"] * 1000))
            filt.append(f"[{i-1}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
            tags.append(f"[a{i}]")
        total = json.load(open(os.path.join(self.rec, "offsets.json"), encoding="utf-8"))["total"]
        body = ";".join(filt) + ";" + "".join(tags) + \
            f"amix=inputs={len(tags)}:normalize=0[sum];" \
            f"[sum]loudnorm=I={v.get('lufs', -15)}:TP=-1.5:LRA=11,apad,atrim=0:{total}[voz]"
        voz_wav = os.path.join(self.rec, "voz_full.wav")
        run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", body, "-map", "[voz]", voz_wav])

        m = self.spec.get("musica", {})
        tipo = m.get("tipo", "procedural_ritmica")
        mus = os.path.join(self.rec, "musica.wav")
        if tipo == "sin_musica":
            run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                 f"anullsrc=r=48000:cl=stereo:d={total}", "-t", f"{total}",
                 "-ar", "48000", "-ac", "2", mus])
        elif tipo == "archivo":
            self.musica_archivo(m, total, mus)
        else:
            self.musica_procedural(m, total, mus)

        if tipo == "sin_musica":
            # Antes esto escribía SILENCIO como audio_final y se perdía la voz.
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", voz_wav, "-af", "alimiter=limit=0.95",
                 "-ar", "48000", "-ac", "2", os.path.join(self.rec, "audio_final.wav")])
            print("audio_final.wav listo (solo voz)")
            return

        dk = self.spec.get("ducking", {})
        body = (f"[0:a]apad,atrim=0:{total},asplit=2[vmain][vsc];[1:a]atrim=0:{total}[mus];"
                f"[mus][vsc]sidechaincompress=threshold={dk.get('threshold',0.05)}:"
                f"ratio={dk.get('ratio',3)}:attack={dk.get('attack',25)}:release={dk.get('release',350)}[duck];"
                f"[vmain][duck]amix=inputs=2:normalize=0,alimiter=limit=0.95[out]")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", voz_wav, "-i", mus, "-filter_complex", body,
             "-map", "[out]", "-ar", "48000", "-ac", "2", os.path.join(self.rec, "audio_final.wav")])
        print("audio_final.wav listo (voz + música con ducking)")

    def musica_procedural(self, m, total, mus):
        """Cama procedural (pads + bajo + hats) normalizada y con fade de entrada/salida.

        El fade es lo que evita que la música empiece de golpe en el frame 0.
        """
        chords = m.get("acordes", [["220.00", "277.18", "329.63"], ["185.00", "220.00", "277.18"],
                                   ["146.83", "185.00", "220.00"], ["164.81", "207.65", "246.94"]])
        cd = m.get("acorde_dur", 4)
        pads = os.path.join(self.rec, "pads.wav")
        ins, filt, tags = [], [], []
        for i, f in enumerate(chords):
            expr = "+".join(f"{m.get('peso', 0.14)}*sin(2*PI*{x}*t)" for x in f)
            ins += ["-f", "lavfi", "-i", f"aevalsrc={expr}:d={cd}:s=48000"]
            filt.append(f"[{i}:a]lowpass=f={m.get('pad_lowpass', 1200)},tremolo=f=2:d=0.30[p{i}]")
            tags.append(f"[p{i}]")
        body = ";".join(filt) + ";" + \
            f"{tags[0]}{tags[1]}acrossfade=d=0.4:c1=tri:c2=tri[c1];" \
            f"{tags[2]}{tags[3]}acrossfade=d=0.4:c1=tri:c2=tri[c2];[c1][c2]acrossfade=d=0.4:c1=tri:c2=tri[pad]"
        run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", body, "-map", "[pad]", pads])
        fi, fo = float(m.get("fade_in", 0.8)), float(m.get("fade_out", 2.4))
        run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "8", "-i", pads,
             "-f", "lavfi", "-i", f"aevalsrc=(0.42*sin(2*PI*55*t)+0.30*sin(2*PI*82.41*t))*(0.55+0.45*sin(2*PI*2*t)):d={self.total+1}:s=48000",
             "-f", "lavfi", "-i", f"anoisesrc=color=pink:seed=7:d={self.total+1}:s=48000",
             "-filter_complex",
             f"[0:a]atrim=0:{total},asetpts=N/SR/TB[pads];"
             f"[1:a]lowpass=f=320,aformat=channel_layouts=stereo[b];"
             f"[2:a]highpass=f=7000,tremolo=f=8:d=0.8,volume=0.16,aformat=channel_layouts=stereo[h];"
             f"[pads]aformat=channel_layouts=stereo,volume=1.1[pt];"
             f"[pt][b][h]amix=inputs=3:normalize=0[mx];"
             f"[mx]loudnorm=I={m.get('lufs', -18)}:TP=-1.5:LRA=11,"
             f"afade=t=in:st=0:d={fi},afade=t=out:st={max(0.0, total - fo):.3f}:d={fo},"
             f"atrim=0:{total}[mus]",
             "-map", "[mus]", "-ar", "48000", "-ac", "2", mus])

    def musica_archivo(self, m, total, mus):
        """Cama tomada de un archivo (música del usuario).

        Recorta una ventana de `total` segundos desde `musica.inicio`, la repite en bucle
        si la pista es más corta, la normaliza a `musica.lufs` y le pone fade de entrada y
        salida. `musica.archivo` puede ser ruta absoluta o relativa a la raíz del repo.

        Nota: pistas ya masterizadas suelen venir a -9 LUFS con True Peak > 0 dBFS; el
        loudnorm a -18 LUFS y el fade evitan que la cama aplaste a la voz.
        """
        archivo = m["archivo"]
        if not os.path.isabs(archivo):
            archivo = os.path.join(self.repo, archivo)
        if not os.path.exists(archivo):
            raise SystemExit(f"musica.archivo no existe: {archivo}")
        inicio = float(m.get("inicio", 0))
        fi, fo = float(m.get("fade_in", 0.8)), float(m.get("fade_out", 2.4))
        bucle = ["-stream_loop", "-1"] if (dur(archivo) - inicio) < total else []
        run(["ffmpeg", "-y", "-loglevel", "error"] + bucle + ["-i", archivo, "-t", f"{total:.3f}",
             "-af", (f"atrim=start={inicio:.3f}:duration={total:.3f},asetpts=N/SR/TB,"
                     f"aformat=channel_layouts=stereo,aresample=48000,"
                     f"loudnorm=I={m.get('lufs', -18)}:TP=-1.5:LRA=11,"
                     f"afade=t=in:st=0:d={fi},"
                     f"afade=t=out:st={max(0.0, total - fo):.3f}:d={fo}"),
             "-ar", "48000", "-ac", "2", mus])
        print(f"música: {os.path.basename(archivo)} desde {inicio:.1f}s -> {dur(mus):.2f}s")

    # ------------------------------------------------------------ ensamblaje
    def etapa_video(self):
        s = self.spec["salida"]
        salida = os.path.join(self.proj, s.get("archivo", "salida.mp4"))
        rutas = [os.path.join(self.seg, f"seg_{i}.mp4") for i in range(len(self.escenas))]
        ds = [dur(p) for p in rutas]
        total = sum(ds) - self.XF * (len(ds) - 1)
        ins, filt = [], []
        for i, p in enumerate(rutas):
            ins += ["-i", p]
            filt.append(f"[{i}:v]fps={self.FPS},settb=AVTB,format=yuv420p[v{i}]")
        ins += ["-i", os.path.join(self.rec, "audio_final.wav")]
        ai = len(rutas)
        body = ";".join(filt)
        acum, cur = 0.0, "[v0]"
        for i in range(1, len(rutas)):
            acum += ds[i - 1] - self.XF
            tag = f"[x{i}]" if i < len(rutas) - 1 else "[vpre]"
            trans = self.TRANS[i - 1] if i - 1 < len(self.TRANS) else "fade"
            body += f";{cur}[v{i}]xfade=transition={trans}:duration={self.XF}:offset={acum:.3f}{tag}"
            cur = tag
        body += f";[vpre]ass={os.path.join(self.rec, 'subs.ass')}[vout]"
        body += f";[{ai}:a]aresample=48000,aformat=channel_layouts=stereo[aout]"
        cmd = (["ffmpeg", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + ins +
               ["-filter_complex", body, "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
                "-r", str(self.FPS), "-c:v", "libx264", "-preset", s.get("preset", "medium"),
                "-crf", str(s.get("crf", 20)), "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", salida])
        print(f"RENDER START ({total:.2f}s -> {salida})")
        import time
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
        vistos, t0 = set(), time.time()
        for linea in p.stdout:                      # tolera out_time_ms=N/A al cerrar
            if linea.startswith("out_time_ms="):
                try:
                    ms = int((linea.split("=", 1)[1] or "0").strip())
                except ValueError:
                    continue
                pct = ms / 1_000_000 / total * 100
                if int(pct) // 10 not in vistos:
                    vistos.add(int(pct) // 10)
                    print(f"  avance {pct:5.1f}% ({ms/1_000_000:.1f}s)", flush=True)
        p.wait()
        if p.returncode != 0:
            print(p.stderr.read()[-2000:])
            raise SystemExit(1)
        print(f"RENDER OK -> {salida} en {time.time()-t0:.0f}s")

    # ------------------------------------------------------------ verificación
    def etapa_verificar(self, tiempos=None):
        """Rejilla de contactos de N tiempos clave para revisar con visión."""
        salida = os.path.join(self.proj, self.spec["salida"].get("archivo", "salida.mp4"))
        chk = os.path.join(self.rec, "checks")
        os.makedirs(chk, exist_ok=True)
        if not tiempos:
            starts, acc = [], 0.0
            for i, d in enumerate(self.trans):
                starts.append(acc - i * self.XF)
                acc += d
            tiempos = [round(s + d * 0.35, 2) for s, d in zip(starts, self.trans)]
        ins = []
        for i, t in enumerate(tiempos):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", salida,
                            "-frames:v", "1", f"{chk}/v{i}.jpg"], check=True)
            ins += ["-i", f"{chk}/v{i}.jpg"]
        cols = self.spec.get("rejilla_cols", 3)
        rows = (len(tiempos) + cols - 1) // cols
        tw, th = 380, int(380 * self.H / self.W)
        filt = [f"[{i}:v]scale={tw}:{th},setsar=1[t{i}]" for i in range(len(tiempos))]
        rt = []
        extra = len(tiempos)
        for r in range(rows):
            idx = list(range(r * cols, min((r + 1) * cols, len(tiempos))))
            # Relleno con `color`: repetir el mismo pad en un hstack rompe el grafo
            # ("Input 2 height ... does not match"), porque un pad solo admite un consumidor.
            while len(idx) < cols:
                ins += ["-f", "lavfi", "-i", f"color=c=black:s={tw}x{th}"]
                filt.append(f"[{extra}:v]setsar=1[t{extra}]")
                idx.append(extra)
                extra += 1
            filt.append("".join(f"[t{i}]" for i in idx) + f"hstack=inputs={cols}[r{r}]")
            rt.append(f"[r{r}]")
        filt.append("".join(rt) + f"vstack=inputs={rows}[out]")
        out = os.path.join(chk, "rejilla.jpg")
        run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", ";".join(filt),
             "-map", "[out]", "-frames:v", "1", out])
        print("rejilla:", out, "| tiempos:", tiempos)

    def etapa_niveles(self):
        a = os.path.join(self.rec, "audio_final.wav")
        r = subprocess.run(["ffmpeg", "-v", "info", "-i", a, "-af", "loudnorm=print_format=summary",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("\n".join(l.strip() for l in r.stderr.splitlines()
                        if "Input Integrated" in l or "Input True Peak" in l))
        for nombre, frac in (("bajo voz", 0.15), ("cola", 0.98)):
            t = self.total * frac
            rr = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(t), "-t", "1.5", "-i", a,
                                 "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            print(f"[{nombre} @{t:.1f}s] " + " | ".join(x.strip() for x in rr.stderr.splitlines()
                                                       if "max_volume" in x))


def main():
    ap = argparse.ArgumentParser(description="Pipeline de reels verticales narrados")
    ap.add_argument("--spec", required=True, help="ruta del reel.json del proyecto")
    ap.add_argument("pasos", nargs="+",
                    help="etapas | segmentos | ass | audio | video | verificar | niveles | todo")
    a = ap.parse_args()
    r = Reel(a.spec)
    if "todo" in a.pasos:
        r.etapa_assets()
        r.etapa_ass()
        r.etapa_segmentos()
        r.etapa_audio()
        r.etapa_video()
        r.etapa_niveles()
        r.etapa_verificar()
        return
    pasos = {"etapas": r.etapa_assets, "segmentos": r.etapa_segmentos, "ass": r.etapa_ass,
             "audio": r.etapa_audio, "video": r.etapa_video, "verificar": r.etapa_verificar,
             "niveles": r.etapa_niveles}
    for paso in a.pasos:
        fn = pasos.get(paso)
        if not fn:
            print(f"paso desconocido: {paso} (usa: {', '.join(pasos)} | todo)")
            continue
        fn()


if __name__ == "__main__":
    main()
