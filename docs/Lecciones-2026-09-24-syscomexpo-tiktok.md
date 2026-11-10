---
tags: [lecciones, tiktok, vertical, ken-burns, ass, tts, procedural]
fecha_modificacion: 2026-09-24
estado: activo
---

# Lecciones 2026-09-24 — Invitación TikTok SYSCOM Expo 2027

Bitácora técnica de `proyectos/syscomexpo2027-invitacion_24092026/`: video vertical 1080x1920 de ~30 s
(Ken Burns sobre fotos oficiales + TTS femenino + música procedural + subtítulos quemados estilo TikTok).

## Respuestas obligatorias (AGENT §15)

### 1. ¿Cómo puedo optimizar la creación de videos similares?

- **Plantilla "slideshow narrado" reutilizable:** el flujo `guion.txt (n|línea)` → TTS por línea → medir WAVs →
  segmentos Ken Burns dimensionados con holgura → cadena xfade + ASS en una sola pasada funcionó completo.
  Candidato a script del toolkit: hoy el cálculo de offsets xfade y los `adelay` de voz se hizo a mano;
  un generador que lea duraciones con `ffprobe` y emita el `filter_complex` ahorraría ~10 min por video.
- **`recursos/tts_openrouter.py`** (TTS SSE con registro en `costos.jsonl`) quedó genérico: acepta texto,
  salida y `system` opcional. Si se repite, promoverlo a `scripts/` del toolkit.
- **Verificación visual por frames** (`-ss t -frames:v 1`) en 3-4 tiempos clave detectó el traslape de
  subtítulos sin ver el video completo: barato y efectivo como gate de calidad.
- Re-render tras corregir ASS costó ~25 s porque los 6 segmentos se conservaron: **separar generación de
  segmentos del ensamblaje** (en vez de un solo pipeline) pagó bien.

### 2. ¿Qué nuevas funciones utilicé?

- **Ken Burns por dos vías** (verificadas ambas): paneo con `crop` animado por `t`
  (`crop=1080:1920:x='(iw-1080)*t/D':y=...` tras `scale=-2:2160`) y zoom con `zoompan`
  (`z='min(zoom+0.0012,1.35)'` / `max(1.35-0.0012*on,1.05)` para zoom out) sobre crop previo 9:16.
- **CDN de syscom con parámetros** (`cdn-cgi/image/format=jpeg,quality=85,width=1920,...`): pedir
  `format=jpeg` en vez del `avif` por defecto → compatibilidad directa con FFmpeg sin conversión.
- **Música procedural con progresión de acordes** (A–F♯m–D–E): 4 `aevalsrc` unidos con `acrossfade d=1`
  + `tremolo=f=2:d=0.25` para pulso corporativo. Antes solo se había verificado pad estático.
- **Doble capa de texto en ASS** (voz centrada + URL persistente en capa superior simultánea).

## Gotchas verificados (importantes)

1. **zsh no hace word-splitting de variables:** `FF="ffmpeg -y -loglevel error"; $FF ...` falla con
   `command not found: ffmpeg -y -loglevel error`. En scripts zsh, escribir el comando completo inline
   (o usar `${=FF}`). Mismo tipo de gotcha ya reportado en [[Lecciones-2026-09-24-narracion-tts]].
2. **`crop` con tamaño fijo tras `scale=4000:-2` es frágil:** la altura escalada varía por redondeo al par
   (1278→2662 pero 1276→2658) y `crop=1498:2662` aborta con `Invalid too big or non positive size`.
   Forma robusta: `crop=1496:ih` (altura relativa a la entrada).
3. **ASS: `MarginV` no desplaza eventos con Alignment central (4/5/6).** Dos estilos centrados simultáneos
   se traslapan aunque tengan `MarginV` distinto. Para texto secundario persistente usar alineación de
   borde (p. ej. `Alignment=8` superior-centro con `MarginV=240`).
4. **`-loop 1 -t D -i foto.jpg` + `-t D` de salida** respeta la duración pedida aunque `zoompan d=N` genere
   N frames; verificar siempre con `ffprobe` (diferencias de ±1 frame por redondeo a 30 fps: pedir 9.2 s
   da 9.1667 s). Recalcular offsets xfade con las duraciones **reales**.
5. **URLs no se narran:** la voz dice el cierre ("Te esperamos. SYSCOM Expo 2027.") y la URL va solo en
   pantalla; narrar "diagonal" y "punto" alarga y suena mal.

## Gotchas v2 (video animado)

6. **`gpt-audio-mini` RESPONDE las preguntas del guion en vez de leerlas** (v2, verificado por
   transcripción): con "¿Buscas tu próximo gran proyecto?" produjo primero "Claro, …" (system
   "Eres una locutora…") y luego una respuesta conversacional completa de 9.5 s (system
   "Repite verbatim…"). **Fix: escribir el hook como afirmación** ("Tu próximo gran proyecto está
   aquí.") — lectura literal a la primera. **Verificación objetiva obligatoria** para guiones con
   signos de interrogación: transcribir el WAV con `gemini-2.5-flash` (audio inline vía OpenRouter,
   campo `input_audio` con mp3 base64; ~0.0006 USD por llamada con 6 audios).
7. **Ducking con `ratio=8` deja la música inaudible:** voz −15 LUFS vs threshold 0.02 → ~16 dB de
   reducción casi permanente (la voz ocupa 80-90 % de la pieza). Configuración audible verificada:
   música loudnorm **−18 LUFS** + `sidechaincompress=threshold=0.05:ratio=3:attack=25:release=350`.
   **Verificar siempre con `volumedetect` en 3 ventanas**: bajo voz, pausa entre líneas y cola sin voz
   (la música sola medía −20 dB y en la mezcla de v1 la cola cayó a −27 dB: inaudible).
8. **`xfade` exige mismo fps Y timebase en ambas entradas** o aborta con
   `frame rate (30/1) do not match (25/1)` / `timebase (1/15360) do not match (1/12800)`. Los segmentos
   originados en `lavfi` (`color`, `aevalsrc` con video) salen a **25 fps / tb 12800** por defecto.
   Fix en el ensamblaje: `[i:v]fps=30,settb=AVTB[vi]` en cada entrada antes de la cadena xfade.
9. **Chrome headless (`--screenshot`) no sirve para páginas con auth/JS pesado:** syscom.mx devolvió
   403 sin CSS (y el proceso no termina solo: matar con timeout). Alternativa que funcionó: **componer
   la "página" como lienzo con FFmpeg** (color + hero + logo + drawtext + grid de imágenes del CDN,
   vstack) y animar el scroll con `crop` por `t` con ease in-out
   (`y='(in_h-H)*(0.5-0.5*cos(PI*min(t/D,1)))'`).
10. **Objetos en movimiento con `overlay`:** entradas escalonadas desde abajo con
    `y='1920+(YF-1920)*min(max(t-DELAY,0)/0.45,1)':enable='gte(t,DELAY)'` (delay +0.12 s por logo).
    Stickers de texto: mejor en ASS con `\move(x1,y1,x2,y2,t1,t2)\fad(in,out)` que con drawtext animado.
11. **Traslapes subtítulo↔escena:** con stickers y elementos propios de la escena (página simulada,
    grid), el subtítulo centrado estorba; reposicionar eventos puntuales con `{\pos(x,y)}` a zonas
    libres (zona baja ~1660-1700 queda libre en 1080x1920 y sobre la UI de TikTok).

## Datos de la edición

- Voz: 6 líneas TTS (`openai/gpt-audio-mini`, voz `coral`) = 26.7 s medidos para video de 29.97 s.
- Mezcla: voz −15 LUFS / música −21 LUFS, ducking `sidechaincompress` (patrón de [[SKILL]] `crear-video`).
- Costo: 6 llamadas TTS ≈ **0.0019 USD** (reporte `scripts/costo_generacion.py`).
- Sin marca de agua: `assets/marca_agua.png` no existe en esta copia (avisado al usuario en la entrega).

## Datos de la edición v2 (animada)

- Duración final 24.8 s; voz 21.2 s (hook reformulado como afirmación: 2.8 s).
- Música rítmica de 3 capas: pads A–F♯m–D–E (acrossfade 0.8 + tremolo 2 Hz) + bajo pulsante
  (55/82.41 Hz × LFO 2 Hz, lowpass 320) + hats (`anoisesrc=color=pink`, highpass 7 kHz, tremolo 8 Hz).
- Escenas nuevas: scroll de página simulada (lienzo 1080×3840 propio), grid de 9 logos animado,
  stickers ASS con `\move`/`\fad`, transiciones variadas (slideleft/wipeup/circleopen/zoomin).
- Costo v2: 2 TTS + 2 verificaciones gemini ≈ **0.0020 USD**.

## Cambio de infraestructura derivado (versión base v1.2.0)

A petición del usuario ("[codigo base]"): **el log de costos deja de vivir en `trabajo/`** y pasa a
`proyectos/<slug>_<fecha>/recursos/costos.jsonl` (regla: los intermedios de una edición van siempre
en el `recursos/` de su proyecto). Aplicado en:

- `config.json > costos.log` → `recursos/costos.jsonl` (relativo a la carpeta del proyecto).
- `scripts/costo_generacion.py` → por defecto usa el `proyectos/*/recursos/costos.jsonl` más
  reciente (proyecto activo); `--log` fuerza otra ruta; la rotación queda en la misma carpeta.
  Verificado end-to-end (reporte + rotación en `recursos/`).
- `.gitignore` → entrada `trabajo/` eliminada (`proyectos/*` ya cubre el log).
- `AGENT.md` §7/§10, `docs/Costos-y-Avance.md` → rutas y descripción actualizadas.
- Scripts del proyecto (`tts_openrouter.py`, `verificar_voz.py`) → escriben junto a sí mismos.

También se volcaron a `SKILL.md` las lecciones verificadas de esta sesión: TTS vs preguntas
(gotcha en `crear-audio`), ducking audible −18 LUFS/ratio 3 + verificación por ventanas
(`musica-fondo`, `crear-video`), `xfade` fps/timebase (`transiciones`), Ken Burns y objetos en
movimiento (`crear-video`), ASS `\pos`/`\move`/`\fad` (`crear-subtitulos`).

## Enlaces

- [[AGENT]] · [[SKILL]] · [[Home]]
- [[Lecciones-2026-09-24-narracion-tts]] — pacing TTS y ASS dual
- [[Musica-Libre-de-Derechos]] — receta procedural base
