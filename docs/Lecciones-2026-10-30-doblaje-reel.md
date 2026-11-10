---
tags: [lecciones, video, doblaje, tts, voicestudio, whisper, captions, ffmpeg, instagram, tablero, avance]
fecha_modificacion: 2026-10-30
estado: activo
---

# Lecciones — Doblar un reel de Instagram a español: voz + texto en pantalla (2026-10-30)

Pieza: `proyectos/reel-ig-DfCi2s4zNno_30102026` — reel de Instagram (cuenta virex.explains, 1080×1920,
30 fps, 128.5 s, vp9+aac, narración en inglés con captions tipo karaoke abajo y un rótulo de sección
arriba) **doblado a español**: narración nueva ajustada a los huecos de la original, captions
redibujados en el estilo de la pieza y los 20 rótulos de sección traducidos. Duración e imagen intactas.
Herramienta nueva: `scripts/doblar.py` (skill `doblar-video` de [[SKILL]]).

## Resultado

- `virex-tu-propia-ia-es.mp4` (128.492 s, idéntico al original; h264 crf 18 + aac 192k, 45 MB) y copia en
  `~/Movies/`. 37 unidades de voz en español con un solo timbre: ajuste medio 97.8 % del hueco, 6 con
  `speed` nativo, exceso máximo 0.06 s (imperceptible). Tiempos: whisper 80 s, voz 40 min (≈1 min por
  unidad en el M3 con 16 GB, dos generaciones en las que se pasaban), render 37 s, verificación 2 min.
- Captions nuevos (Figtree 71 px, gris + negritas + cajas azules con puntos) y 20 rótulos (JetBrains
  Mono 24 px) sobre la banda cubierta con el color de fondo de la pieza.
- Costo de APIs de generación: **0 USD** (yt-dlp, faster-whisper, VoiceStudio local, Pillow, FFmpeg).
  La traducción la hizo el propio agente.

## Pipeline que funcionó

1. **Descargar** con `yt-dlp` (`--no-playlist -f "bv*+ba/b" --merge-output-format mp4 --write-info-json`):
   Instagram entrega vp9 + aac y el `info.json` trae autor, fecha y descripción.
2. **Transcribir** con faster-whisper (`medium`, CPU int8, tiempos por palabra): 80 s para 128 s de audio.
3. **Unidades**: oraciones por puntuación; las que pasan de 6 s se parten en la mejor pausa interna (la
   que sigue a una coma gana). `slot_fin` = inicio de la siguiente − 0.08 s.
4. **Traducir** llenando `es` en `doblaje.json` (marcas `{resaltado}` y `*negrita*`; `es_tts` cuando la
   grafía del caption no se pronuncia bien, p. ej. `RAG` → `rag`).
5. **Voz** por unidad con VoiceStudio (`POST /generate`), ajuste al slot y tiempos por palabra con ASR.
6. **Render**: PNG por cue + `ffconcat` con `duration` como capa de overlay, rótulos en otra capa,
   voz nueva normalizada, h264/aac.

## Gotchas verificados (el valor de esta bitácora)

- **OpenRouter puede estar sin presupuesto.** `GET /auth/key` devolvió `limit_remaining: 0`
  (`spend_usd` 505 de 500, reinicio el 1.º del mes) y todas las llamadas daban **403**. Comprobarlo
  antes de planear una sesión con nube; el agente traduce por sí mismo y la voz va por VoiceStudio
  local (o ElevenLabs si hay key). AGENT §4 ya lo dice.
- **faster-whisper + PyAV ≥ 16 rompe `decode_audio`** (`open() got an unexpected keyword argument
  'metadata_errors'`). Solución sin fijar versiones: pasarle el audio como `numpy.float32` leído con
  `wave` (16 kHz mono PCM16 que prepara ffmpeg). `doblar.py` y la receta de `subtitulos.py` lo hacen así.
- **El venv de whisper**: `uv venv --python 3.12 ~/.venvs/whisper && uv pip install --python
  ~/.venvs/whisper/bin/python faster-whisper` (Python 3.14 del sistema no tiene ruedas de ctranslate2).
  `preflight.sh` ahora también busca el módulo ahí.
- **VoiceStudio (`/generate`, multipart):** `instruct` **solo admite los atributos de OmniVoice**
  (`male`, `female`, `child`, `teenager`, `young adult`, `middle-aged`, `elderly`, `very low/low/moderate/
  high/very high pitch`, `whisper`, acentos `american/british/australian/canadian/indian/chinese/japanese/
  korean/portuguese/russian accent`); cualquier otra palabra → 400 (`'clear' (unsupported)`). Separador
  «coma + espacio». `language=Spanish`. Respuesta `audio/wav` 24 kHz mono, sin silencio inicial.
- **`seed` es determinista para el mismo texto** (dos llamadas → bytes idénticos), pero en modo
  `instruct` (sin referencia) el timbre puede variar entre textos. **Para un doblaje de muchas unidades:
  diseñar la voz una vez y clonarla**: `POST /profiles` con `ref_audio` = esa toma y `ref_text` = su
  texto → `profile_id` estable para todas las unidades (perfil `bca97518` en esta máquina).
- **Ajustar la toma al slot: `speed` nativo mejor que `atempo`.** `speed=1.25` dio 0.82 de la duración
  natural sin artefactos de time-stretch; `duration=<s>` también funciona (5.6 → 5.76 s) pero es menos
  predecible. `doblar.py` usa `speed = natural/slot·1.03` (tope `speed_max` 1.3) y solo después `atempo`
  (tope 1.25); si aún no cabe avisa `W-DOBLAJE-LARGO` para acortar el texto.
- **Pace del español vs inglés:** la narración original va a ~200 palabras/min (428 palabras en 127 s).
  El TTS en español sale a ~5.2 sílabas/s, así que una traducción literal se pasa 15–30 % del slot.
  Traducir **compacto** (quitar muletillas, "Así que" solo donde el ritmo lo permite) antes de confiar
  en `speed`; por encima de ~6.5 sílabas/s por slot hay que recortar.
- **La ASR en español lee "Claude" como "Cloud"** y a veces se come "IA": no es error del TTS, es
  pronunciación inglesa esperable; para verificar la lectura usar el diff dirigido de
  `verificar_voz.py` o comparar palabra a palabra con tolerancia, no la transcripción cruda.
- **Calibrar el estilo contra el fotograma original, no a ojo.** Medir en píxeles: altura de mayúsculas
  («GPT» 50 px → Figtree 71 px, no los 85 estimados a simple vista), ancho de una palabra gris, bbox de
  la caja azul incluyendo los puntos (relleno 14 px + radio 10), posición del rótulo (x 133, y 129, 24 px
  de JetBrains Mono). Componer un cue de prueba sobre el frame original y comparar bboxes: en dos
  iteraciones quedó dentro de ±7 px.
- **La banda de captions se cubre entera** (y 1405–1640, color de fondo 249/246/243 muestreado) en vez
  de rastrear cada caption original: las ilustraciones nunca bajan de y≈1380 (medido en 128 frames a
  1 fps y 1 285 a 10 fps); solo ~1 s de un "fantasma" de transición pasa por ahí.
- **Capas como `ffconcat` de PNG con `duration`** (una entrada por capa) en lugar de un `overlay` por
  cue: 150+ cues serían 150 entradas y decodificadores. El concat demuxer necesita repetir el último
  `file` sin `duration` y `format=rgba,setpts=PTS-STARTPTS` antes del `overlay`.
- **Rótulos de sección**: el cambio de sección se detecta por firma de píxeles del recorte a 10 fps
  (runs estables ≥ 0.5 s) y el texto con tesseract `--psm 7` sobre el recorte ampliado ×3; tesseract
  escupe bytes no UTF-8 por stderr → leer `stdout` como bytes y decodificar con `errors="replace"`.
  La pieza tiene una animación tipo "glitch" de ~1 s en cada cambio: se cubre y el texto nuevo entra
  directo.
- **Detección de música bajo la voz sin escuchar:** `silencedetect -35 dB` + `volumedetect` dentro de
  esos huecos (−52…−55 dB → no hay cama musical, solo voz) → `audio.modo = reemplazar`. Si hubiera
  música, `mezclar` con `original_db` o separar pistas (demucs) antes.
- **tesseract no puede abrir archivos en `/tmp` dentro del sandbox de Claude Code** («failed to open
  locally … image file not found»): el OCR devolvía vacío y la verificación marcaba 28 falsos problemas.
  Los PNG temporales del OCR van en `recursos/` del proyecto. (Los OCR del rótulo hechos con ffmpeg → archivo
  dentro del proyecto sí funcionaron desde el principio.)
- **Cifras en la verificación por ASR:** whisper escribe «50» donde el guion dice «cincuenta» y la unidad
  daba ratio 0.50. `normalizar()` convierte dígitos a letras (0-999 999) antes de comparar; vale también para
  alinear los tiempos por palabra («quinientos» ↔ «500»).
- **Límite honesto:** el texto dentro de las ilustraciones animadas (globos de chat, pantallas, sellos)
  no se traduce: cada elemento sería un rótulo rastreado a mano. Declarar `rotulos` solo para texto
  estático.

## Segunda vuelta: voz más animada + intro y cierre (mismo día)

- Resultado final: `virex-tu-propia-ia-es.mp4` de 138.70 s = intro 4.47 s + cuerpo 128.49 s + cierre 6.74 s
  − 2 × 0.5 s de xfade (44 MB), copiado a `~/Movies/`. Con la voz joven las 37 unidades cupieron en su hueco
  **sin ningún ajuste de velocidad** (la anterior, «middle-aged», necesitó 6); síntesis 35 min.
- Verificación: cuerpo = original (128.492 s); voz 36/37 por ASR del video completo (u31 es la ventana de
  la ASR, el wav de la unidad se transcribe exacto: «Luego Nova responde mal y nadie sabe por qué»), líneas de
  intro y cierre leídas al pie de la letra, rótulos 18/20 (OCR «mep» y el último rótulo medido dentro del
  cierre: corregido en `verificar`, que ahora cierra el último rótulo con el cuerpo), captions con los dos
  falsos negativos de OCR ya conocidos, loudness −16.3 LUFS.
- El usuario pidió una voz «más animada» y una intro y un final. Voz: se diseñó una toma con
  `instruct = male, young adult, moderate pitch` (seed 11) y `speed` 1.05, se clonó a un perfil (`ef0f24f3`)
  y se regeneraron las 37 unidades (la caché se invalida sola porque la config entra al hash). La muestra
  alternativa `male, young adult, high pitch` quedó en `recursos/voz_prueba/animada_B.wav` por si se
  prefiere; con una voz más rápida casi ninguna unidad necesitó `speed` extra.
- Cortinillas: `doblar.py cortinillas` genera tarjetas (fondo liso, título con énfasis, rótulo `// 00 — intro`
  y `// 21 — cierre`, subtítulo y crédito al autor original) con un movimiento mínimo (el título sube 28 px y
  se funde en 0.7 s; nada más, para no competir con el estilo de la pieza), voz del mismo perfil y unión con
  `xfade`/`acrossfade` de 0.5 s. El cuerpo doblado vive en `recursos/doblaje/cuerpo.mp4` y la `salida` pasa a
  ser el video completo. `verificar` corrige los tiempos por el desfase de la intro.
- Gotcha: con `xfade` todas las entradas deben compartir fps, tamaño y formato de píxel; las tarjetas se
  generan con `color=` + `overlay` de PNG RGBA y `fade=…:alpha=1`, y se codifican como el cuerpo (h264
  yuv420p 30 fps, aac 48 kHz estéreo) antes de unir.

## Tablero local de avance (nuevo estándar, mismo día)

El usuario pidió «ver cómo va» sin preguntar y que se actualice solo. Resultado: `scripts/tablero.py`
(dashboard en `http://127.0.0.1:8765/`, se refresca cada 2 s, sin red) + `comun.avance()` como contrato de
reporte (`recursos/avance.jsonl`). Decisiones de diseño:

- **Un solo archivo JSONL por proyecto** en vez de parsear logs: cualquier script reporta con una línea
  y el tablero no sabe nada de la etapa. Los logs de `doblar.py` de esta misma sesión (anteriores al
  contrato) se leen como respaldo.
- **Qué se dibuja y por qué:** anillo con el total (una cifra héroe), una fila por etapa con barra,
  duración/ETA (pendiente de los últimos 3 min) y sparkline; la gráfica «valor vs límite» solo cuando una
  etapa manda `datos` (aquí: cada toma frente a su hueco, con las que se pasan en el color de aviso y ▲).
  Paleta y marcas según el skill `dataviz` (barras ≤ 24 px, un solo matiz, estados reservados con icono +
  texto, tabla alternativa, modo oscuro propio). Nada de librerías ni CDN.
- **`ffmpeg_con_progreso` reporta solo con fijar `comun.AVANCE_DIR`**, así que reel.py, promo.py y
  doblar.py ganan la barra de render sin tocarlos (promo.py puede además reportar `cuadros`).
- **`st_birthtime`, no `ctime`**, para la hora de inicio de un log en macOS (ctime cambia con cada
  escritura y daba «duró 0 s»).
- **`.claude/launch.json`** con la config `tablero` para abrirlo desde la vista previa de la app de Claude
  en un clic; sin argumento toma el proyecto más reciente.
- **Compacto a petición del usuario:** etapas en cuadrícula (tarjetas de ~300 px con barra, tiempo/ETA,
  sparkline y detalle en una línea), tiles en una sola fila, gráfica de 150 px, registro plegado con la
  última línea como resumen. Con 4 etapas y la gráfica cabe en ~900 px de alto sin scroll.

## Cómo se verificó

`python3 scripts/doblar.py verificar doblaje.json` (nuevo subcomando, código 5 si algo no cuadra):

- Duración 128.492 s = original.
- Voz vs guion por ASR de la salida: **37/37 unidades** (umbral 0.6 con cifras convertidas a letras).
- Rótulos por OCR en su punto medio: 19/20 (el «// 10 — mcp» lo lee «mep» a 24 px; visualmente correcto).
- Captions: OCR por bloque (`--psm 6`) de 8 cues de muestra + revisión visual de las bandas en los
  instantes dudosos (0.5, 41.2, 79.4, 94.9 s): todos los captions presentes, con énfasis y cajas.
- Loudness integrada −15.7 LUFS (objetivo −16), TP −4.5 dBTP.
- Hoja de contacto de 8 fotogramas del mp4 final (`recursos/frames/final/`) revisada con visión.

## Costos

Nube: 0 USD. Sesión del agente: ver reporte de `costo_generacion.py` en `recursos/costos.jsonl`.
