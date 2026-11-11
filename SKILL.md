---
tags: [skills, catalogo, media-toolkit]
fecha_modificacion: 2026-11-01
estado: activo
---

# SKILL — Catálogo de skills

> Catálogo de capacidades del toolkit. Cada skill define: descripción, entradas, salidas, herramienta local, modelo de respaldo (clave de `config.json`) y ejemplo de comando.
> Reglas generales en `[[AGENT]]`. Parámetros y modelos en `config.json` (fuente de verdad).

---

## cortar-video

- **Descripción:** recorta un video entre dos puntos de tiempo.
- **Entradas:** video de origen, tiempo inicio (`-ss`), tiempo fin (`-to`).
- **Salidas:** video recortado (formato según `salida.formatos_video`).
- **Herramienta local:** `ffmpeg` (`herramientas.cortar_video`).
- **Modelo de respaldo:** ninguno (100% local).
- **Ejemplo:**
  ```bash
  ffmpeg -ss 00:00:10 -to 00:00:35 -i entrada.mp4 -c copy salida.mp4
  ```

## unir-clips

- **Descripción:** concatena varios clips en un solo video.
- **Entradas:** lista de clips (mismo códec/resolución para `-f concat`; si difieren, usar filtro `concat` con re-encode).
- **Salidas:** video unido.
- **Herramienta local:** `ffmpeg` (`herramientas.unir_clips`).
- **Modelo de respaldo:** ninguno.
- **Varios videos de origen (regla AGENT §14):** confirmar el orden con el usuario, normalizar cada fuente y unir con **fade de 500 ms** entre fuentes (salvo petición contraria).
- **Ejemplo:**
  ```bash
  printf "file 'a.mp4'\nfile 'b.mp4'\n" > lista.txt
  ffmpeg -f concat -safe 0 -i lista.txt -c copy unido.mp4
  ```
- **Ejemplo (2 fuentes distintas: normalizar a 1080p30 y unir con fade 500 ms):**
  ```bash
  # 1) Normalizar cada fuente
  ffmpeg -i fuente1.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p" -c:v libx264 -crf 18 -c:a aac -ar 48000 -ac 2 n1.mp4
  ffmpeg -i fuente2.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p" -c:v libx264 -crf 18 -c:a aac -ar 48000 -ac 2 n2.mp4
  # 2) Unir con fade 500 ms (offset = duración de n1 - 0.5)
  ffmpeg -i n1.mp4 -i n2.mp4 -filter_complex \
    "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=<DUR_N1-0.5>[v];[0:a][1:a]acrossfade=d=0.5[a]" \
    -map "[v]" -map "[a]" unido.mp4
  ```

## transiciones

- **Descripción:** aplica transiciones entre dos clips (video y audio).
- **Entradas:** dos clips, tipo de transición, duración en segundos.
- **Salidas:** video con transición.
- **Herramienta local:** `ffmpeg` filtros `xfade` (video) y `acrossfade` (audio) (`herramientas.transiciones`).
- **Parámetros:** tipos válidos en `transiciones.disponibles`; tipo y duración por defecto en `transiciones.tipo_default` (`fade`) y `transiciones.duracion_default` (`0.5` s). **Default obligatorio: desvanecimiento (fade) de 500 ms**; si el usuario pide otro tipo o duración, se le hace caso.
- **Modelo de respaldo:** ninguno.
- **Gotcha verificado (2026-09):** `xfade` exige **mismo fps y timebase en ambas entradas** o aborta (`frame rate (30/1) do not match (25/1)` / `timebase (1/15360) do not match (1/12800)`). Los clips originados en `lavfi` (`color`, `testsrc`…) salen a 25 fps / tb 12800 por defecto. Normalizar cada entrada en la cadena: `[i:v]fps=30,settb=AVTB[vi]`.
- **Ejemplo (fade de 1s entre dos clips de 10s):**
  ```bash
  ffmpeg -i a.mp4 -i b.mp4 -filter_complex \
    "[0:v][1:v]xfade=transition=fade:duration=1:offset=9[v];[0:a][1:a]acrossfade=d=1[a]" \
    -map "[v]" -map "[a]" salida.mp4
  ```

## agregar-marca-agua

- **Descripción:** incrusta un logo (imagen) o texto como marca de agua.
- **Entradas:** video, logo o texto, posición, opacidad, margen, escala.
- **Salidas:** video con marca de agua.
- **Herramienta local:** `ffmpeg` filtros `overlay` (imagen) o `drawtext` (texto) (`herramientas.marca_agua`).
- **Parámetros:** `marca_agua.*` en `config.json`. Posiciones válidas: `superior_izquierda`, `superior_derecha`, `inferior_izquierda`, `inferior_derecha`, `centro`.
- **Reglas:** si `marca_agua.tipo` es `imagen` y no existe `ruta_imagen`, avisar al usuario; si es `texto`, usar `marca_agua.texto`.
- **Modelo de respaldo:** ninguno.
- **Ejemplo (imagen, inferior_derecha, opacidad 0.6, margen 20, escala 15% del ancho):**
  ```bash
  ffmpeg -i entrada.mp4 -i assets/marca_agua.png -filter_complex \
    "[1]format=rgba,colorchannelmixer=aa=0.6,scale=iw*0.15:-1[logo];[0][logo]overlay=W-w-20:H-h-20" \
    salida.mp4
  ```
- **Ejemplo (texto):**
  ```bash
  ffmpeg -i entrada.mp4 -vf \
    "drawtext=text='Mi marca':fontsize=24:fontcolor=white@0.6:x=w-tw-20:y=h-th-20" \
    salida.mp4
  ```

## quitar-silencios

- **Cuándo:** quitar tiempos muertos de un video o audio con voz (tomas de celular, tutoriales, podcast).
  **Orden recomendado:** primero `silencios.py`, después `subtitulos.py` sobre el resultado (los
  subtítulos se calculan sobre el tiempo ya cortado; al revés quedarían desfasados).
- **Comando (uno solo):**
  ```bash
  python3 scripts/silencios.py <entrada> --reporte     # simulacro: cuánto quitaría, sin render
  python3 scripts/silencios.py <entrada> --proyecto proyectos/<slug>_<DDMMAAAA>
  # ajustes: --umbral auto|-38  --min-silencio 0.5  --margen 0.12  --dejar 0.2  --salida <archivo>
  ```
- **Qué hace:** detecta silencios con `silencedetect` en una copia mono 16 kHz (umbral `auto` = pico del
  piso de ruido + 6 dB, acotado a [-50, -25] dB), deja `margen` junto a la voz y `dejar` de cada pausa
  (no suena robótico), alinea los bordes a los cuadros y corta **video y audio en los mismos rangos**
  (`trim`/`atrim` + `concat`, `afade` de 10 ms por tramo). x264 crf 18 + AAC 192k 48 kHz, misma
  resolución/fps (VFR de celular → fps estándar). Con más de 150 tramos renderiza por partes.
- **Salida (≤ 6 líneas + `Siguiente:`):** `<nombre>_sin_silencios.mp4` (audio: misma extensión) en la raíz
  del proyecto o junto a la entrada, y `<nombre>_sin_silencios.cortes.json` (umbral, tramos conservados y
  eliminados) en `recursos/` o junto a la salida. Verifica A/V ±1 cuadro y duración = suma de tramos.
- **Errores frecuentes:** código 2 = corregir el comando (archivo inexistente, `--umbral` fuera de
  [-90, -5], sin pista de audio, proyecto inexistente); 3 = falta FFmpeg/`auto-editor` (preguntar al
  usuario); 1 = FFmpeg o verificación falló (reportar). "0 cortes" → `--umbral -30` o
  `--min-silencio 0.3`; si se comió finales de palabra → `--umbral -45` o `--margen 0.2`.
- **No usar** `silenceremove` + `-c:v copy` (receta anterior): recorta solo el audio y la imagen se
  desincroniza más con cada corte.
- **Alternativa:** `--motor auto-editor` solo si está instalado (no verificado en esta máquina).
  Diseño y límites en `[[Subtitulos-y-Silencios]]`.

## quitar-ruido

- **Descripción:** reduce ruido blanco/estacionario del audio (ventiladores, zumbido, hiss).
- **Entradas:** video o audio, intensidad de reducción.
- **Salidas:** video/audio con audio limpio.
- **Herramienta local:** `ffmpeg` filtro `afftdn` (`herramientas.quitar_ruido`).
- **Alternativa:** `deepfilternet` si está instalado (mayor calidad en voz con ruido complejo).
- **Modelo de respaldo:** ninguno.
- **Ejemplo:**
  ```bash
  ffmpeg -i entrada.mp4 -af "afftdn=nr=12:nf=-50" -c:v copy salida.mp4
  ```

## crear-subtitulos

- **Cuándo:** subtítulos `.srt`/`.vtt` desde el audio y, si se pide, quemados en el video. Correr
  **después** de `silencios.py` (ver `quitar-silencios`).
- **Comando (uno solo):**
  ```bash
  python3 scripts/subtitulos.py <video|audio> --quemar --glosario "ACME,HIKVISION,WhatsApp" \
      --proyecto proyectos/<slug>_<DDMMAAAA>
  # opciones: --idioma es  --formatos srt,vtt  --estilo pastilla|clasico  --posicion abajo|centro
  #           --max-car 32 (42 en horizontal)  --proveedor auto|whisper|openrouter|elevenlabs  --modelo <id>
  #           --salida <dir>  --desde-srt <archivo.srt>  (texto corregido a mano: re-quema sin transcribir)
  ```
- **Tiempos:** salen de las pausas medidas (`silencedetect`), **nunca** del LLM (sus marcas derivan ~4 s).
  El LLM (`modelos.vision` vía OpenRouter) solo transcribe fragmentos numerados; con `faster-whisper`
  instalado se usan sus marcas por palabra (`auto` lo prefiere). ElevenLabs solo si hay key **y** el
  usuario lo pide (AGENT §5).
- **Salida (≤ 8 líneas + `Siguiente:`):** `<nombre>.srt`, `<nombre>.vtt` y, con `--quemar`,
  `<nombre>_subtitulado.mp4` en la raíz del proyecto (o junto a la entrada). Intermedios y caché de la
  transcripción en `recursos/subtitulos/<nombre>/` (o `<nombre>_subt/`): repetir el comando no vuelve a
  pagar. Costo en `recursos/costos.jsonl` (tarea `subtitulos`), ~$0.0015 por 30 s de voz.
- **Errores frecuentes:** 2 = argumentos/entrada (`--quemar` con audio solo, `--formatos` inválido, sin
  voz); 3 = falta key/proveedor/libass (preguntar al usuario; nunca pedir la key de ElevenLabs); 4 = API
  caída → repetir el MISMO comando una vez; 1 = FFmpeg. `AVISO … car/s` = lectura rápida: revisar el
  SRT. Marca mal escrita → agregarla a `--glosario` (corrección fonética local: "Akme" → ACME).
- **Estilo quemado de `subtitulos.py` (verificado 2026-09-28, FFmpeg 7.1 + libass 0.17.3):** vertical
  1080×1920 → Helvetica Neue 56 px y la caja termina en y≈1495 (zona segura: 420 px abajo, 150 arriba);
  horizontal 1920×1080 → 46 px, margen 70. `pastilla` = `BorderStyle=4` (una caja por evento; con
  `BorderStyle=3` cada línea lleva su caja y el traslape se ve como franja oscura; `\blur` desenfoca
  también el texto). Las woff2 de `promo/temas/neutro/fuentes` no cargan en libass (FreeType sin
  brotli: "Error opening memory font"), por eso se usa una fuente del sistema.
- **Subtítulos quemados con ASS (notas verificadas 2026-09):**
  - `MarginV` **no** desplaza eventos con Alignment central (4/5/6): dos estilos centrados simultáneos se traslapan. Para texto secundario persistente usar alineación de borde (p. ej. `Alignment=8` superior) o reposicionar eventos puntuales con `{\pos(x,y)}`.
  - Stickers animados: `{\move(x1,y1,x2,y2,t1,t2)\fad(in,out)}` en el texto del evento (ms relativos al evento) — más simple que `drawtext` animado.
  - **`t1`/`t2` de `\move` son ms RELATIVOS AL EVENTO, no al video (verificado 2026-09-28).** Si se pasan tiempos absolutos, el movimiento queda fuera de la vida del evento y el sticker **nunca aparece** (sin error de render). Síntoma: "el sticker no se ve". Usar siempre valores pequeños (`250`,`750`).
  - **Gráficos vectoriales dentro de ASS:** barra de progreso con `{\pos(x,y)\p1}m 0 0 l W 0 l W H l 0 H{\p0}` (estilo `Alignment=7`): una pista con alpha + un evento de relleno por escena; no requiere `drawtext` ni overlays.
  - **Zona segura vertical:** kicker/barra arriba conviene dejarlos en `y≈110-125` (no ~52) para no quedar bajo la UI de TikTok/Reels; el caption inferior centrado funciona en `y≈1560`.
  - Quemar con filtro `ass=subs.ass` (PlayRes acorde a la resolución destino, p. ej. 1080x1920).
- Diseño, límites y cómo mejorar los tiempos con faster-whisper en `[[Subtitulos-y-Silencios]]`.

## crear-audio

- **Descripción:** sintetiza voz (TTS) a partir de texto.
- **Entradas:** texto (guión; puede generarse con `modelos.guion`), formato de salida.
- **Salidas:** audio (según `salida.formatos_audio`).
- **Herramienta local:** ninguna por defecto.
- **Modelo principal:** `modelos.voz` (`openai/gpt-audio-mini`) vía OpenRouter `endpoints.voz` (`/chat/completions`). **Flujo verificado (2026-09):**
  - El modelo es de chat con salida de audio: enviar `modalities: ["text","audio"]` y `audio: {"voice": "...", "format": "pcm16"}`.
  - **Obligatorio `stream: true`** (SSE): el audio llega en chunks `choices[0].delta.audio.data` (base64); concatenar y decodificar.
  - En streaming solo admite `format: "pcm16"` → salida PCM crudo **24 kHz mono**; convertir con FFmpeg:
    `ffmpeg -f s16le -ar 24000 -ac 1 -i voz.pcm -ar 48000 -ac 2 voz.wav`
  - **Prompt:** usar mensaje `system` ("Repite verbatim el texto del usuario, sin confirmaciones ni palabras extra") y poner el texto desnudo en `user`. Si se le da una orden ("Di exactamente..."), el modelo antepone muletillas tipo "Claro,".
  - Voces disponibles: alloy, ash, ballad, coral, echo, fable, onyx, nova, sage, shimmer, verse.
- **Catálogo TTS de OpenRouter (verificado 2026-10-31):** `GET /models?output_modalities=speech` lista los modelos de texto a voz (38); todos van por `POST /audio/speech` con `model`, `input`, `voice`, `response_format` (`mp3`|`pcm`) e `instructions`. `fish-audio/s2-pro` (`modelos.voz_tts`) **sí admite `voice`** (id de 32 hex de su biblioteca, consultable sin key en `api.fish.audio/model?language=es&licensed=true`) **e `instructions`** (estilo en lenguaje natural; se cobran como caracteres). `microsoft/mai-voice-2.1`: `voice` = `es-MX-{Alejo|Grant|Harper|Valeria}:MAI-Voice-2.1`. `google/gemini-3.8-flash-tts`: 30 voces con nombre (Gacrux, Sulafat, Puck, Achird, Charon…), **solo `pcm`** 24 kHz. Casting comparado y costos por minuto en `[[Lecciones-2026-10-31-muestras-voz-curso]]`.
- **Control de estilo y ánimo (verificado 2026-09):**
  - No hay parámetros de emoción ni SSML: el estilo se pide en el `system` (p. ej. `"voz de mujer mexicana, cálida y natural, ritmo pausado"`) y el texto va desnudo en `user`. Funciona de forma **aproximada** — no hay garantía de intensidad ni consistencia entre llamadas.
  - **Arco emocional por sección:** como cada segmento de narración es una llamada TTS independiente, se puede dar un `system` distinto a cada sección (p. ej. oficina → directa/práctica; sueño → baja y soñadora; playa → luminosa y emocionada; cierre → motivada y enérgica). Para máxima emoción consistente, considerar ElevenLabs (regla ElevenLabs de `[[AGENT]]`).
- **Pacing medido:** `gpt-audio-mini` habla ~40 % más lento de lo planeado (21 líneas "de máx 5 s" → 197 s de audio). **Presupuestar la narración por duración medida de los WAV, no por segundos del guion**; pedir líneas de ≤10 palabras (o el ~60 % del slot) y verificar la duración total antes de colocar subtítulos.
- **El modelo RESPONDE preguntas del guion (verificado 2026-09):** si una línea es pregunta directa ("¿Buscas tu próximo gran proyecto?"), puede anteponer "Claro," o incluso responderla conversacionalmente, con cualquier `system`. **Escribir hooks como afirmaciones** ("Tu próximo gran proyecto está aquí."). **No basta con evitar interrogantes:** los fragmentos nominales con dos puntos ("Cuatro dudas: A, B y C.") también se leen como instrucción y el modelo los desarrolla en voz alta (medido 2026-09-28: 15.57 s para 7 palabras). Cada línea debe ser una **oración con sujeto y verbo conjugado**. Verificación objetiva: transcribir los WAV con `modelos.vision` (`gemini-2.5-flash`, campo `input_audio` con mp3 base64 en `messages` — una llamada admite varios audios) y comparar contra el guion antes de ensamblar.
- **Señal de alarma barata:** ~0.45 s por palabra es lo normal en el paso `audio`; por encima de 0.6 s/palabra hay texto de más. Para rehacer **solo** la línea mala, borrar `voz_N.wav` y `voz_N.pcm` y dejar `voz.regenerar=false` (regenerar las cinco cuesta más y no hace falta).
- **Verificación objetiva: diff dirigido, no transcripción cruda (2026-09-28).** Al transcribir los WAV con `gemini-2.5-flash`, la ASR confunde marcas y cifras con naturalidad ("ACME" → "Akme"/"Acné", "Banamex" → "Citibanamex", "250" → "550"). Pedir el texto esperado en el prompt y pedir **solo** (a) palabras extra/muletillas, (b) palabras faltantes, (c) la cifra clave, evita falsas alarmas; la transcripción literal mete ruido. Si una cifra queda en duda, re-sintetizar escribiéndola con letra ("doscientos cincuenta") y volver a verificar esa línea sola.
- Detalles y lecciones: `[[Lecciones-2026-09-24-narracion-tts]]`, `[[Lecciones-2026-09-24-syscomexpo-tiktok]]` y `[[Lecciones-2026-09-28-reel-syscomexpo2027]]`.
- **Recomendado para locución al pie de la letra: `modelos.voz_tts` = `fish-audio/s2-pro`** (TTS puro, no puede "contestar"). Medido 2026-09-28 en el ejemplo de oro del motor promo: gpt-audio-mini desarrolló 8 de 13 subtítulos (hasta 3.3 s/palabra); Fish leyó las 13 al pie de la letra (0.15–0.29 s/sílaba, diff dirigido limpio) por 0.0063 USD. Es el proveedor por defecto de `promo.py voz`. Criterio de toma mala: **> 0.38 s por sílaba** (por palabra castiga las palabras largas).
- **Alternativas OpenRouter por `/audio/speech` (verificadas 2026-09-28):** no aparecen en `/models`; se llaman con `POST /audio/speech` + `{"model","input","voice",...}`.
  - `fish-audio/s2-pro` ✅ — devuelve **PCM16 crudo 44.1 kHz mono** (sin encabezado): convertir con `ffmpeg -f s16le -ar 44100 -ac 1 -i voz.pcm`. Español verificado. Es también el modelo de clonación zero-shot (`modelos.voz_clonada`).
  - `minimax/speech-2.8-hd` ✅ — **requiere `response_format:"mp3"`** (con PCM da error 400) **y una `voice` explícita** (sin ella: 400 "An explicit voice is required"); entrega MP3 32 kHz mono. Español verificado.
  - `microsoft/mai-voice-2` ❌ error 400 del provider; `x-ai/grok-voice-tts` ❌ ID inexistente (verificado 2026-09-28 — no usarlos).
- **Opción ElevenLabs:** solo si aplica la regla ElevenLabs de `[[AGENT]]`.
- **Ejemplo (conceptual, OpenRouter):**
  ```bash
  curl https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "openai/gpt-audio-mini", "modalities": ["text","audio"],
         "audio": {"voice": "onyx", "format": "pcm16"}, "stream": true,
         "messages": [
           {"role": "system", "content": "Repite verbatim el texto del usuario, sin confirmaciones ni palabras extra."},
           {"role": "user", "content": "Texto a sintetizar"}
         ]}' \
    --no-buffer | # procesar SSE: extraer delta.audio.data (base64), concatenar y decodificar a voz.pcm
  ffmpeg -f s16le -ar 24000 -ac 1 -i voz.pcm -ar 48000 -ac 2 voz.wav
  ```

## clonar-voz

- **Descripción:** genera voz sintética a partir de una muestra de voz del usuario (clonación).
- **Entradas:** muestra de voz en `muestras/` (10–30 s, limpia), texto a sintetizar.
- **Salidas:** audio con la voz clonada.
- **Modelo principal:** `modelos.voz_clonada` (`fish-audio/s2-pro`, zero-shot) vía OpenRouter `/audio/speech`. **Síntesis verificada 2026-09-28** (PCM16 44.1 kHz mono, español OK); la **clonación con muestra de referencia sigue pendiente de verificación** (requiere muestra en `muestras/`).
- **Alternativa local:** `coqui-tts` XTTS v2 o `f5-tts` (open source, corre en local).
- **Opción ElevenLabs:** clonación instantánea, solo si aplica la regla ElevenLabs de `[[AGENT]]`.
- **Privacidad:** las muestras viven en `muestras/` (gitignored); nunca commitearlas ni exponerlas.

## musica-fondo

- **Descripción:** obtiene o genera música libre de derechos para fondo de video.
- **Entradas:** duración (segundos), estilo (ambient, corporativo, cinemático…), fuente (`musica_libre.fuentes`: `local`, `procedural`, `pixabay`).
- **Salidas:** audio `.wav` o `.mp3` (según `salida.formatos_audio`).
- **Herramienta local:** `ffmpeg` (procedural) o `curl` (descarga Pixabay).
- **Flujo por fuente:**
  - `local` → usar un archivo de `musica_libre.carpeta_local` (`assets/musica/`); si está vacía, avisar y proponer otra fuente.
  - `procedural` → generar con FFmpeg (receta verificada `aevalsrc` + `lowpass` + `aecho` + `loudnorm`; ver `[[Musica-Libre-de-Derechos]]`).
  - `pixabay` → descargar vía API con `PIXABAY_API_KEY` (`musica_libre.pixabay`); si falta la key, avisar y caer a `procedural` o `local`.
- **Niveles de mezcla:** la música va a **-18 LUFS** (`loudnorm`) cuando se mezcla bajo una voz a **-15 LUFS**, con ducking suave `sidechaincompress=threshold=0.05:ratio=3:attack=25:release=350` (verificado 2026-09 en `crear-video`). Con -21 LUFS + `ratio=8` la música queda **inaudible** (la voz dispara la compresión casi toda la pieza). **Verificar siempre con `volumedetect` en 3 ventanas:** bajo voz, pausa entre líneas y cola sin voz — la música debe quedar audible en las dos últimas.
- **Receta rítmica (piezas animadas, verificada 2026-09):** 3 capas — pads con progresión de acordes (4 `aevalsrc` unidos con `acrossfade` + `tremolo=f=2:d=0.35`), bajo pulsante (`(0.4*sin(2*PI*55*t)+0.28*sin(2*PI*82.41*t))*(0.55+0.45*sin(2*PI*2*t))` + `lowpass=f=320`) y hats (`anoisesrc=color=pink` + `highpass=f=7000` + `tremolo=f=8:d=0.8`); mezcla `amix` + `loudnorm=I=-18`.
- **Licencias:** solo fuentes de `config.json > musica_libre`; atribución cuando la licencia lo exija (ver `[[Musica-Libre-de-Derechos]]`).
- **Ejemplo (procedural, 60 s ambient suave):**
  ```bash
  ffmpeg -f lavfi -i "aevalsrc=0.15*sin(2*PI*220*t)+0.10*sin(2*PI*277.18*t)+0.08*sin(2*PI*329.63*t):d=60:s=48000" \
    -af "lowpass=f=900,aecho=0.8:0.7:60|120:0.4|0.2,loudnorm=I=-21:TP=-2:LRA=11" \
    musica_fondo.wav
  ```

## crear-imagen

- **Descripción:** genera imágenes a partir de un prompt (thumbnails, fondos, assets para video).
- **Entradas:** prompt (puede mejorarse con `modelos.prompts`), formato y tamaño.
- **Salidas:** imagen (según `salida.formatos_imagen`).
- **Herramienta local:** Stable Diffusion (ComfyUI / A1111) si está instalada.
- **Modelo principal:** `modelos.imagen` (`google/gemini-2.5-flash-image`) vía OpenRouter. Para series con estilo fijo (motor ilustrado) se usa `modelos.imagen_ilustrado` (`google/gemini-nano-banana-2.1`, hasta 14 referencias, ~0.04 USD).
- **Script (2026-10-30):** `python3 scripts/imagen.py generar --prompt-archivo <prompt.md> [--referencia <img> …] [--relacion 9:16] --salida proyectos/<p>/<nombre>.png`. Las referencias viajan como `image_url` en el mismo mensaje que el prompt: sirven para "misma composición y estilo, otro personaje" sin img2img aparte. Registra `recursos/costos.jsonl` (pide `usage.include` para recibir `usage.cost`) y reporta la etapa `imagen` al tablero (`[[SKILL#tablero-avance]]`). Códigos de salida 0/2/3/4 como `doblar.py`. Verificado 2026-10-30: 14 llamadas en un proyecto (12 × `gemini-2.5-flash-image` a 0.039 USD y ~8 s, 768×1344 con `--relacion 9:16`; 1 × `gemini-3-pro-image` a 0.14 USD, 768×1376; 1 × `gemini-nano-banana-2.1` a 0.04 USD, JPEG), 0.65 USD en total; `image_config.aspect_ratio` funciona en OpenRouter.
- **Personaje nuevo en el estilo de una ilustración de referencia (verificado 2026-10-30, ver `[[Lecciones-2026-10-30-personaje-spock]]`):** receta en tres llamadas.
  1. **Generar** con la referencia adjunta y un prompt que la acote: "use the attached illustration ONLY as a reference for art style, proportions and composition … do NOT reproduce that character" + descripción del personaje nuevo + composición (cuerpo entero, fondo uniforme, sin texto). Pedir en esta llamada **todo lo que no se puede corregir después** (gestos de manos, pose) y **prohibir logos de marca** ("generic laptop with NO brand logo"): sin eso el modelo puso un logo de Apple en la laptop. Los matices se exageran: "very faint green undertone" dio piel verde; hay que decir "must NOT look green".
  2. **Corregir detalles con una edición puntual:** la imagen generada como `--referencia` y un prompt "keep everything exactly as it is … change ONLY: 1) … 2) …". Conserva composición, estilo y colores (logo, tono de piel y calcetines cambiaron sin mover nada más).
  3. **Límite conocido de `gemini-2.5-flash-image`:** los **gestos de manos no los reescribe**: el saludo vulcano (dedos en V) no salió ni editando (descripción, emoji 🖖, foto real del gesto) ni como mano aislada: 6 llamadas, 0.23 USD, siempre palma con dedos juntos. **Sí lo resuelven los modelos mayores de OpenRouter** con la misma edición y una foto del gesto como segunda referencia: `--modelo google/gemini-3-pro-image` (0.14 USD, conservó todo lo demás; devuelve 768×1376) y `google/gemini-nano-banana-2.1` (0.04 USD, pero cambió el color del pantalón y devuelve JPEG). Regla: si Flash falla tres veces en el mismo detalle, subir de modelo, no de prompt. Plan C geométrico (cizalla afín de los pares de dedos) en `[[Lecciones-2026-10-30-personaje-spock]]`.
  Verificación: hoja comparativa `hstack` + `drawtext` (referencia y versiones a la misma altura) para decidir con los ojos; OCR `--psm 11` sobre ilustraciones da falsos positivos con stickers ("CA", "IES"), no sirve como prueba de "sin texto". Recorte tipo referencia: bbox de píxeles que difieren del color de fondo (Pillow, umbral 24) + margen 6 %/2.5 %.
- **Rostro de una persona real sobre el personaje (verificado 2026-10-30):** recortar la foto a cabeza y hombros y pasarla como segunda `--referencia` junto con la imagen a editar. Nombrar forma de cara, peinado y expresión ("fuller rounder face, soft cheeks, hair combed back with a side part, warm smile"): con solo "like the photo" el modelo conserva la cara del personaje base y le pone barba. Mejor parecido planteándolo como "cartoon caricature portrait of the person in the photo, using the second image as the exact template" (foto primero, personaje después). Revisar las manos: el tono nuevo no se propaga y hay que pedir "recolor ONLY that hand". Avisar al usuario de que su foto viaja al proveedor (OpenRouter → Google) y enviar solo el recorte.
- **Alternativas locales evaluadas (2026-10-30, Mac M3 16 GB, fichas de mflux 0.24.0):** Anima Turbo (2B, anime, 5.7 GB, pico 4.6 GB con `--low-ram`, sin img2img ni referencia) y Z-Image Turbo 4-bit (6B, img2img) caben; FLUX 3 Klein (20 GB, pico 18.5 GB en q4) y Qwen Image 2.1 edit (33 GB, licencia Qwen Research) no. Ninguna ve la referencia como Gemini: usarlas solo si no hay presupuesto. Nota: Google marca `gemini-2.5-flash-image` como deprecado (apagado 2027-03-15; sucesor Gemini 3.1 Flash Lite Image) → migrar `modelos.imagen` cuando OpenRouter lo liste.
- **Antes de llamar, comprobar saldo:** `GET https://openrouter.ai/api/v1/auth/key` → `limit_remaining`. Con el tope mensual agotado OpenRouter devuelve `403 Key limit exceeded (monthly limit)` con `resets_at` (día 1 del mes) y el remedio es subir el límite de la key en `openrouter.ai/settings/keys`. El API directo de Gemini **no** tiene nivel gratuito para `gemini-2.5-flash-image` (verificado 2026-10-30 en ai.google.dev/gemini-api/docs/pricing: 0.039 USD por imagen, pago).
- **Banners y botones con texto exacto (verificado 2026-09-28, ver `[[Lecciones-2026-09-28-banner-hikvision-xml]]`):** el modelo **deforma el español y desobedece el hex** del fondo, así que el titular nunca se le pide. Receta en tres pasos:
  1. Generar **solo la ilustración** (mascota/íconos) sobre fondo uniforme, con "no headline text" y como mucho etiquetas de 1–2 palabras.
  2. Muestrear el color real del fondo del propio render con `ffmpeg -vf "crop=1:1:X:Y,format=rgb24 -f rawvideo -"` + `xxd` y extraer el sujeto con `colorkey=0xCOLOR:0.22:0.05` (se lleva también la sombra elíptica).
  3. Componer con `color=c=0xHEX:s=WxH` + `overlay` + `drawtext` con fuente local (`/System/Library/Fonts/Supplemental/Arial Bold.ttf`), centrando el texto solo en la franja libre a la derecha del overlay (`x='330+(w-330-tw)/2'`). Elegir el `fontsize` **midiendo** con Pillow (o estimación por carácter), no a ojo.
  Geometría de referencia: lienzo 1476×264, fondo `0x3d58ba`, mascota a 232 px de alto en (60, 16), texto `0xFDFDFD`. Scripts reutilizables en `proyectos/banner-hikvision-p2p_28092026/recursos/` (`generar_banner.py` + `componer_banner.py`).
- **Logos con alfa:** SVG → PNG con `qlmanage -t -s 2000 -o <dir> logo.svg` (FFmpeg no decodifica SVG) y, si el render viene sobre blanco, colocarlos sobre una pastilla blanca.

## imagenes-libres

- **Descripción:** descarga imágenes libres de derechos para fondos, B-roll estático o assets de video.
- **Entradas:** query (búsqueda), cantidad, fuente (`imagenes_libres.fuentes`: `local`, `wikimedia`, `pexels`, `unsplash`, `pixabay`).
- **Salidas:** imágenes (según `salida.formatos_imagen`) guardadas en `imagenes_libres.carpeta_local` (`assets/imagenes/`).
- **Herramienta local:** `curl` (+ `jq` para parsear las APIs).
- **Flujo por fuente:**
  - `local` → usar archivos de `assets/imagenes/`; si está vacía, avisar y proponer otra fuente.
  - `wikimedia` → API de Wikimedia Commons (`imagenes_libres.wikimedia.url_base`), **sin key**; verificar la licencia CC de cada archivo y registrar la atribución.
  - **Script (2026-10-31):** `python3 scripts/commons.py buscar <consultas.json> <dir>` (filtra dominio público/CC0/CC BY/CC BY-SA por archivo, baja miniaturas y arma hojas de contactos) y `python3 scripts/commons.py bajar <elegidas.json> <dir>/candidatos.json <img_dir> [--pausa 10]` (originales ≤ 4700 px, fusiona la atribución en `creditos.json`). **El 429 de Commons lo provoca un User-Agent sin contacto, no el ritmo:** con `media-agent-toolkit/1.0 (<URL del repo>; …)` bajaron 51 fotos seguidas sin un solo 429 (verificado 2026-10-31; `[[Lecciones-2026-10-31-star-trek-cronologia]]`).
  - `pexels` / `unsplash` / `pixabay` → API con la key correspondiente (`PEXELS_API_KEY`, `UNSPLASH_ACCESS_KEY`, `PIXABAY_API_KEY`); si falta la key, avisar y caer a `wikimedia` o `local`.
- **Pexels también sirve videos libres de copyright:** endpoint `config.json > imagenes_libres.pexels.videos.url_base` (`https://api.pexels.com/videos/`, misma `PEXELS_API_KEY`, Pexels License) — útil para B-roll en movimiento:
  ```bash
  curl -s -H "Authorization: $PEXELS_API_KEY" \
    "https://api.pexels.com/videos/search?query=ocean&per_page=5&orientation=landscape" | jq '.videos[].video_files'
  ```
- **Atribución:** obligatoria cuando la licencia lo exija (Wikimedia/CC): incluir autor, título y licencia en créditos o descripción de la entrega. Para créditos en pantalla desde `creditos.json`: `commons.credito_foto(c)` (rótulo junto a la foto, «Foto: autor · licencia») y `commons.credito_lista(c)` (línea de créditos finales); `autor_corto` y `licencia_corta` recortan autor y licencia.
- **Alfa en logos/PNG del CDN (verificado 2026-09-28):** los `log2_*.png` de topbrands y los de `fotos/logotipos/` traen **alfa con RGB basura** debajo (p. ej. `(72,112,75)` verde). `pad` **no** aplana el alfa y `format=yuv420p` descarta el canal → aparecen rectángulos verde olivo alrededor del logo. Componer siempre con `overlay` sobre una base opaca (`color=c=0xEFF2F7:s=WxH`) y centrar con `x=cx+(CELL-w)/2`. Para verificar cómo se ve un logo, montar una rejilla de prueba con FFmpeg (`hstack`/`vstack`) y revisarla con visión antes de armar la escena.
- **Detalles y licencias:** `[[Imagenes-Libres-de-Derechos]]`.
- **Ejemplo (Wikimedia Commons, buscar 5 imágenes):**
  ```bash
  curl -s "https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrsearch=cielo&gsrlimit=5&prop=imageinfo&iiprop=url|extmetadata" | jq '.query.pages'
  ```

## crear-video

- **Descripción:** ensambla un video completo a partir de imágenes, audio y subtítulos.
- **Entradas:** imágenes/clips, audio (voz o música), subtítulos (opcional), resolución y formato destino.
- **Salidas:** video final (según `salida.*`).
- **Herramienta local:** `ffmpeg` (`herramientas.ensamblar_video`).
- **Modelo de respaldo:** ninguno (ensamblaje 100% local).
- **Ejemplo (slideshow con audio):**
  ```bash
  ffmpeg -framerate 1/5 -i img_%03d.png -i voz.mp3 -c:v libx264 -pix_fmt yuv420p -shortest salida.mp4
  ```
- **Mezcla voz + música (patrón verificado 2026-09):** voz a `-15 LUFS` y música a `-18 LUFS` (`loudnorm` por pista); ducking suave con `sidechaincompress=threshold=0.05:ratio=3:attack=25:release=350` usando la voz como sidechain. **Tres reglas críticas:**
  1. Hacer `asplit=2` **explícito** en el bus de voz antes de usarlo como sidechain y como entrada de `amix` — con el split automático implícito el sidechain atenúa también la voz (~-11 dB medidos).
  2. Padrar el bus de voz (`apad,atrim`) a la duración total: `sidechaincompress` corta la pista principal cuando el sidechain termina.
  3. No pasarse de ducking: con `ratio=8` y música a -21 LUFS la música queda inaudible; verificar la mezcla con `volumedetect` en 3 ventanas (bajo voz / pausa / cola sin voz).
- **Ken Burns (verificado 2026-09):** paneo con `crop` animado por `t` (`scale=-2:2160,crop=1080:1920:x='(iw-1080)*t/D':y='(ih-1920)/2'`); zoom con `zoompan` sobre crop previo 9:16 (`scale=4000:-2,crop=1496:ih,zoompan=z='min(zoom+0.0012,1.35)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=FRAMES:s=1080x1920:fps=30`; zoom out con `z='max(1.35-0.0012*on,1.05)'`). Usar `crop=w:ih` (altura relativa): con tamaño fijo el redondeo de `scale=-2` aborta el filtro. Scroll de página sobre lienzo alto: `crop=1080:1920:y='(in_h-1920)*(0.5-0.5*cos(PI*min(t/D,1)))'` (ease in-out).
- **Objetos en movimiento (verificado 2026-09):** overlays con entrada escalonada `overlay=x=X:y='1920+(YF-1920)*min(max(t-DELAY,0)/0.45,1)':enable='gte(t,DELAY)'` (sumar +0.12 s de delay por elemento).
- **Mosaicos/collages dentro de un vertical (verificado 2026-09-28):** dimensionar **cada celda al cuadro final**, no a la foto completa — en 1080x1920 con 2x2 las celdas son 540x960 (`scale=540:960:force_original_aspect_ratio=increase,crop=540:960`). Si se arma el mosaico con celdas 9:16 completas (2100x3740), `zoompan` solo mostrará un cuadrante. Con lienzos propios (grids, tarjetas, páginas simuladas) usar zoom suave (`maxz` ≈ 1.05-1.10) para no recortar los bordes del contenido.
- **Rejilla de contactos para elegir escenas:** montar miniaturas con FFmpeg (`hstack` por filas + `vstack`, o `color` como relleno si faltan celdas) y revisarla con visión — más rápido que abrir 30 fotos una por una.

## armar-reel (pipeline genérico de reels verticales narrados)

- **Descripción:** arma un reel vertical narrado completo (escenas con Ken Burns + xfade variado +
  captions ASS quemados con kickers/barra de progreso + voz TTS + música procedural con ducking)
  a partir de un **spec JSON** del proyecto. Es la promoción a `scripts/` del flujo verificado en
  [[Lecciones-2026-09-28-reel-syscomexpo2027]].
- **Entradas:** `proyectos/<slug>_<DDMMAAAA>/reel.json` (ver plantilla `scripts/reel.ejemplo.json`) y
  los recursos del proyecto en su `recursos/` (fotos, logos, guion, `logo_*.png`).
- **Herramienta local:** `scripts/reel.py` (usa `ffmpeg` por debajo). Pasos:
  ```bash
  python3 scripts/reel.py --spec proyectos/<slug>_<DDMMAAAA>/reel.json todo
  # pasos sueltos: etapas | ass | segmentos | audio | video | niveles | verificar
  ```
  - `etapas` prepara recortes 9:16 y los lienzos (tarjeta de logos, mosaico, cierre).
  - `segmentos` genera un mp4 por escena con duración exacta; `ass` escribe `subs.ass` + `offsets.json`;
    `audio` sintetiza/reutiliza voz, música y mezcla con ducking; `video` ensambla y renderiza con avance.
  - `niveles` reporta LUFS/ventanas y `verificar` deja una rejilla de frames en `recursos/checks/rejilla.jpg`
    para revisarla con visión (gate barato antes de dar por buena la pieza).
- **Tipos de escena del spec:** `foto` (movimiento `zoom_in`/`zoom_out`/`pan_lr`/`pan_rl`), `mosaico`
  (`cols`, celdas dimensionadas al cuadro final), `tarjeta_logos` (`logos`, `cols`, `celda`, `logo_max`),
  `cortes` (varios sub-clips con `xfade_sub`) y `cierre` (fondo desenfocado + logo + `url` + `lineas`).
  Captions y kickers se declaran por escena; `{hl}…{/hl}` resalta una palabra en ámbar; `sticker.texto`
  + `sticker.zona` (`top`/`bottom`) añade el rótulo animado.
- **Kicker numerado y barra de progreso son OPT-IN:** la barra solo se dibuja si el spec trae
  `salida.barra`, y el kicker solo si la escena trae `kicker`. El valor por defecto (omitir
  ambos) es la pieza limpia: `01 · SECCIÓN` + barra de segmentos se lee como presentación de
  diapositivas, no como reel, y así lo señaló el usuario (ver `[[Preferencias-Usuario]]`).
  Usarlos solo si se piden explícitamente.
- **Escenas sin fotos (canvas con PIL, verificado 2026-09-28):** si la pieza es gráfica
  (tarjetas, UI simulada, datos), generar los lienzos con PIL en el tamaño final
  (1080x1920) y usarlos como escenas `foto` con zoom suave (`fuerza` 0.0003, `zoom_max` 1.04)
  para no recortar el texto. `alpha_composite` **devuelve** una imagen nueva: hay que
  reasignarla (`img = lienzo.con_capa(img, fn)`) o el dibujo translúcido se pierde sin error.
  Sobre fondo oscuro, subir los alfas (relleno 20, borde 72) o las tarjetas no se ven.
  Las utilidades viven en la versión base, **`scripts/lienzo.py`**: `fondo_degradado`,
  `resplandor` (glow), `destello` (starburst de intro), `con_capa`, `tarjeta`, `pastilla`,
  `palomita`, `logos_en_pastilla`, `recortar_a_contenido` y `textos_caben` (comprueba que ningún
  texto se salga de su contenedor antes de renderizar). El `recursos/generar_canvas.py` del
  proyecto solo define colores, textos y escenas.
- **Logos en escenas gráficas:** SVG → PNG con `qlmanage -t -s 2000 -o <dir> logo.svg`
  (FFmpeg no decodifica SVG; en macOS puede no haber `rsvg-convert`), recortar al bbox de
  píxeles no blancos (`lienzo.recortar_a_contenido`) y colocar sobre una **pastilla blanca**
  redondeada (`lienzo.logos_en_pastilla`) — así un lockup
  negro/dorado se lee sobre dark mode. Origen usado: `cdn.worldvectorlogo.com` y el CDN
  de logotipos del distribuidor.
- **Modelos:** voz `modelos.voz` (`openai/gpt-audio-mini`, voz `coral` por defecto) por `endpoints.voz`.
- **Música (`musica.tipo`):** `procedural_ritmica` (default, sin material con copyright),
  `sin_musica`, o **`archivo`** para una pista del usuario (`musica.archivo` absoluto o relativo
  a la raíz del repo, `musica.inicio`, `musica.lufs`). En los tres casos `musica.fade_in` y
  `musica.fade_out` (0.8 / 2.4 s por defecto) evitan que la cama entre a nivel pleno en el
  frame 0, que suena a audio cortado. Ojo: las pistas masterizadas vienen muy calientes
  (-9 LUFS, True Peak > 0 dBFS), así que el `loudnorm` a `-18 LUFS` no es opcional.
  Para elegir la ventana sin escucharla, perfilar la energía por segundo con
  `astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level`.
- **Transiciones:** los presets tipo presentación (`wipeup`, `circleopen`, `slideleft`) se ven
  baratos. Usar un lenguaje coherente de `smoothleft`/`smoothup`/`smoothright` con algún
  `hblur` (blur horizontal, se lee como whip pan) y `salida.xfade` de ~0.38 s. Al bajar el
  solape la duración total sube (total = Σduraciones − xfade·(n−1)).
- **Ken Burns visible:** con `zoom_max` > 1.05 hay que dejar zona segura: el recorte por lado
  es `W·(1−1/zoom)/2` (a 1.10 en 1080x1920 son ~49 px por lado y ~87 px arriba/abajo). Para que
  el zoom no se congele antes del final, `fuerza = (zoom_max − 1) / (duración · fps)`.
- **Voz:** `voz.colchon_inicio` (default 0.12 s) mete silencio al inicio de cada línea; el PCM
  del TTS arranca en la primera muestra y sin colchón la primera sílaba se oye cortada.
- **Voz Fish (lee al pie de la letra) en `armar-reel`:** `reel.py` solo sintetiza `modelos.voz`
  (gpt-audio-mini por SSE). Para usar `modelos.voz_tts` (`fish-audio/s2-pro`), pre-generar los
  `voz_N.wav` del proyecto en **48 kHz estéreo con 0.12 s de colchón** importando `voz.tts_fish` +
  `voz.a_tts` (mapa de pronunciación) de `scripts/voz.py`, con `lint_voz` como compuerta previa y
  las cifras escritas con letra; después `voz.regenerar=false` hace que `reel.py` los reutilice tal
  cual. Medir las tomas ANTES de fijar duraciones: `dur_i ≥ offset + línea_i + 0.15 s`; así el
  total cae a la primera (30 s: 8 escenas y 26.7 s de habla). Ejemplo:
  `recursos/generar_voz.py` del proyecto de [[Lecciones-2026-09-29-reel-syscomexpo-30s]].
- **Verificación visual del cierre:** la rejilla estándar (35 % de cada escena) no alcanza a mostrar
  el lockup del cierre (entra a start+1.6 s). Extraer 1–2 frames del final (`-ss` ≥ total − 1.5 s)
  antes de dar la pieza por buena.
- **Si una etapa de ffmpeg gira sin avanzar, matarla y relanzarla.** Verificado 2026-09-29: el
  armado de `voz_full.wav` (8 entradas + `adelay` + `amix` + `loudnorm` + `apad,atrim`) se quedó
  ~10 min al 95 % de CPU con la salida congelada (livelock: hilo principal en `sch_wait`, hilo del
  grafo en `av_samples_set_silence`); el MISMO comando por separado tarda 2 s y, relanzado, terminó
  en 48 s. Criterio: >3× el tiempo razonable y salida sin crecer ⇒ matar y relanzar la etapa suelta
  (`audio` / `video`), no `todo` (reencadena y pierde lo ya renderizado).
- **Salida:** `<archivo>` en la raíz del proyecto (default `salida.archivo`), mp4 h264+aac faststart.
- **Complementos del toolkit:**
  - `scripts/decision.py` — gate/decisiones con JEV (`noul`/`choice`/`score`) validando el contrato
    antes de llamar; útil para aprobar el guion antes de gastar en TTS ([[AGENT]] §5b).
  - `scripts/verificar_voz.py` — verifica el TTS con **diff dirigido** contra el guion (palabras extra/
    faltantes + cifra clave), no con transcripción cruda.
  - `scripts/costo_sesion_hermes.py` — suma al `costos.jsonl` del proyecto el costo de la
    **sesión de Hermes** (tabla `session_model_usage` de `~/.hermes/state.db`), para que el
    reporte de `costo_generacion.py` no subestime la pieza: lo que gasta el agente suele ser
    órdenes de magnitud más que las llamadas de generación. `--listar` muestra sesiones y su costo.
- **Ejemplo:** ver el `reel.json` de [[Lecciones-2026-09-28-reel-syscomexpo2027]] (reel de 45.8 s, 9 escenas).

## promo-ui (videos promo con UI animada — motor HTML → cuadros)

<!-- promo-ui:inicio (el arnés scripts/e2e_orquestador.py usa este bloque tal cual como instrucciones) -->
- **Cuándo:** video promo vertical 9:16 (~30 s) de un producto o servicio con **UI simulada animada**
  (chat del asistente, WhatsApp, tarjetas de acción, diagrama, teléfono), intro con starburst y cierre
  con logo + CTA. Es el estilo de la casa. Para reels de **fotos** narrados usa `armar-reel`.
- **Qué escribes tú (agente):** SOLO `proyectos/<slug>_<DDMMAAAA>/promo.json`, con **contenido**. El motor
  pone tiempos, posiciones, colores, animación, audio y QA. **No escribas HTML/CSS/JS ni comandos ffmpeg**
  para esto y no leas el código de `promo/` (gasta tokens y no hace falta).
- **Pasos (un comando por paso):**
  1. Aclaración (`[[AGENT]]` §2) + **hechos reales con su fuente** (el video no puede prometer nada falso).
  2. `python3 scripts/promo.py nuevo <slug> --ejemplo asistente-ia-cta-whatsapp` (ejemplo de oro de 30 s;
     `demo-10s` es el mínimo). Copia la estructura: **cambia el contenido, no la forma**.
  3. `python3 scripts/promo.py ayuda` → catálogo compacto: tipos de escena, props y límites.
  4. Edita `promo.json` y corre `python3 scripts/promo.py validar <proyecto>`. Cada línea `E-…` trae la ruta
     JSON exacta y el arreglo: aplícalo **tal cual** y repite hasta 0 errores (los `W-…` son avisos).
  5. `python3 scripts/promo.py cuadros <proyecto>` → `recursos/cuadros/hoja.jpg` para que la **revise el
     usuario** (la compuerta es la QA del DOM de `validar`; los modelos de visión no son confiables como
     jueces: `scripts/revisar_hoja.py` es solo una segunda opinión experimental).
  6. `python3 scripts/promo.py todo <proyecto>` → render + audio + final (para renders largos:
     `render <proyecto> --fondo` y luego `estado <proyecto>`).
  7. Costos (`[[AGENT]]` §10) y aprendizaje continuo (§15).
- **Escenas:** `intro` (título corto + marca) · `texto` (enunciado puente) · `chat` (items: usuario, imagen,
  nota_voz, archivo, pasos, razonamiento, asistente, productos, ficha, cotizacion, toast; `piel`:
  asistente_web | whatsapp) · `acciones` · `diagrama` · `telefono` · `cierre` (siempre al final: lema + CTA +
  contacto; el aviso "Interfaz y datos ilustrativos." lo pone el tema).
- **Reglas de contenido:** `titular` = lo que pide el cliente, entre comillas (“…”); `subtitulo` = 1–3 frases
  de ≤8 palabras que cuentan el beneficio; cifras, folios y modelos **solo en pantalla**; tono positivo;
  solo funciones publicadas; *énfasis* con asteriscos en 1–2 palabras; sin emojis ni flechas (→ ✓): usa
  íconos. Prohibidos el kicker numerado y la barra de progreso (se ven como diapositivas).
- **Audio:** `audio.musica.tipo`: `procedural` (defecto, FFmpeg) | `archivo` (pista libre en
  `assets/musica/`) | `cc0` (descarga CC0 vía `scripts/fetch_audio.py`, ver `[[Audio-CC0]]`) | `ninguna`.
  `audio.sfx`: `ninguno` | `sutil` | `normal` (`audio.sfx_fuente`: `procedural` | `cc0`).
  **Voz en off solo si el usuario la pide:** `"audio": {"voz": {}}` (Fish, al pie de la letra; `{"proveedor": "gpt-audio",
  "voz": "coral"}` si quieren voz/estilo elegibles) — se locuta el texto de los
  `subtitulo` (frases que empiezan con sujeto y verbo, sin cifras, sin "¿?" ni listas con dos puntos, sin la
  marca al inicio). `todo` corre `validar → voz → validar` solo; a mano: `promo.py voz <proyecto>` y luego
  `validar` (el motor re-mide las escenas con la duración real de cada toma). Errores `E-TTS-*` = reescribe la frase.
- **Salida:** `0` ok · `2` corrige `promo.json` · `3` entorno (pregunta al usuario) · `4` API (reintenta 1 vez).
<!-- promo-ui:fin -->

- **Detalle técnico** (arquitectura, contratos, códigos de error, cómo agregar componentes):
  `[[Motor-Promo]]`.

## crear-curso (cursos en video con metodología; el agente solo escribe curso.json)

- **Cuándo:** curso, capacitación o lecciones con objetivos y evaluación. Para un video suelto, usa `remotion-video`.
- **Antes de escribir:** leer `[[Metodologia-Cursos-Video]]` (reglas con evidencia, plantilla a dos columnas y checklist). Partir de `cursos/ejemplo/curso.json`.
- **Aclaración previa (sustituye a AGENT §2 en cursos):** antes de `nuevo`, una sola ronda de hasta 3 bloques de 4 preguntas con `AskUserQuestion`, recomendación primero. Si el usuario dice «usa los defaults», no preguntes: declara los recomendados. Si ya respondió algo en su petición, no lo repitas.
  - **Bloque 1, qué es:** (1) propósito: curso para aprender (rec.), presentación, capacitación con DC-3; (2) público y conocimientos previos; (3) qué podrá hacer al terminar; (4) extensión: lección muestra (rec.), un módulo, curso completo.
  - **Bloque 2, evaluación y entrega (en presentación, solo si quiere test):** (5) evaluación: intercalada (rec.), entre lecciones, ambas, ninguna; (6) entrega: reproductor + MP4 (rec.), solo MP4, LMS con `quiz.json`. Solo MP4 no admite test entre lecciones; (7) umbral y reintentos: 80 % y 2 (rec.), personalizado; (8) quién revisa el contenido y, con DC-3, área temática y tutor.
  - **Bloque 3, voz y forma:** (9) voz: la de `voz_default` (rec.) o una de `voz_default.alternas`, leídas de la configuración, más «otra» para clonada u otro proveedor; (10) visual: animado (rec.), con imágenes, mixto; tema `cine` con poco texto, `claro` con texto denso; (11) sonido y subtítulos: SFX sin música y subtítulos activables (rec.), música en intro y cierre, subtítulos quemados; (12) orientación y slug: horizontal (rec.); vertical no está validada para mundo continuo.
  - **Cómo se escribe:** (1, 5, 10) van en `curso.modo` `{proposito, evaluacion, visual}`; (7) en `evaluacion.acreditacion`; (9) en `curso.voz`, p. ej. `{"proveedor": "speech", "voice": "Puck"}`; (10–12) en `curso.estilo`. Antes de `nuevo`, muestra una línea con lo elegido y el costo estimado de voz.
  - **Honestidad:** si elige «ninguna» en un curso para aprender, dile que pierde la práctica con mejor evidencia; en DC-3 la evaluación es obligatoria.
- **Comandos:** `python3 scripts/curso.py nuevo <slug>` → editar `curso.json` → `validar <proyecto>` → `voz` → `componer` → `qa [--jev]` → mostrar la hoja de stills al usuario → `render [--leccion id] [--borrador]` → `carta` → `reproductor`. `todo <proyecto> --qa` encadena todo. Levantar antes el tablero (AGENT §9).
- **Reglas que aplica `validar`:** objetivo con verbo Bloom observable; pregunta intercalada con opciones plausibles; elementos sincronizados por `en`; lección ideal ≤ 6 min y máximo 10; poco texto en pantalla; guion en segunda persona; `tts` con cifras en letra. `proposito: presentacion` omite lo pedagógico y la carta descriptiva, y `evaluacion` por defecto es `ninguna`; duración, sincronía y voz siguen aplicando.
- **Test entre lecciones:** con `evaluacion` `entre-lecciones` o `ambas`, cada lección lleva `prueba_final: ["id-pregunta", …]`. Son preguntas de `preguntas` sin escena; `reproductor.html` las aplica al final y bloquea la siguiente lección hasta aprobar o agotar reintentos.
- **Formato visual:** **mundo continuo** (recomendado): decide una metáfora, define `mundo.actores` y escribe `pantalla.acciones` ligadas a palabras del `tts`; todo movimiento debe explicar algo. Contrato y tabla de acciones en `[[Motor-Curso]]`; copia `m1-l1` del ejemplo. Autor: usa un modelo fuerte, porque el diseño visual vive en `curso.json`. Sin `mundo`, las escenas se vuelven estaciones. **Imágenes:** `imgs` en escenas `concepto`, `pasos`, `ejemplo`, `caso` o `resumen` sin acciones, o actor `imagen` (`clave`, `w`, `h`, `pie`) dentro del mundo; obténlas con `crear-imagen` o `imagenes-libres` y registra `recursos/img/creditos.json`. Sin viñetas en conceptos, sin música bajo la voz, sin avatar, sin kicker numerado ni barra de progreso.
- **Cursos largos (muchas lecciones):** en lugar de escribir cada diccionario a mano, armar `curso.json` desde un `recursos/armar_curso.py` del proyecto con los constructores de la versión base **`scripts/curso_spec.py`**: `leccion`, escenas `gancho`/`objetivo`/`concepto`/`ejemplo`/`pregunta_escena`/`resumen`/`cierre` (ids e1…e8 y mínimos por defecto), `pregunta`, actores `imagen`/`imagen_ancha`/`dato`/`panel`/`fila_imagenes` y acciones `accion`/`junto`/`enfoca`/`plano_general`. Producen el contrato exacto de `curso.py` (verificado con el curso de Star Trek de 21 lecciones).
- **Salidas:** por lección MP4 (−16 LUFS), `.srt`, `.vtt` y transcripción; por curso `carta-descriptiva.md` (no en presentación), `quiz.json` y `quiz.md` (si hay preguntas), `reproductor.html` e `interaccion.json`.
- **Qué NO afirmar:** nunca «certificado», «avalado por la STPS» ni «validez oficial». Sí «listo para DC-3» y «diseñado conforme a EC0301/EC0366». Sin RVOE hay que declararlo (LGE art. 150). El MP4 no obliga a responder; `reproductor.html` sí, pero no registra alumnos: para constancia, el quiz se carga en un LMS.
- **Costo:** voz ≈ 0.014 USD/min con Achird. Render ≈ 0.85 s por segundo de video en M3.
- **Detalle técnico:** contratos y códigos en `[[Motor-Curso]]`.

## remotion-video (composiciones libres en React → MP4; motor opcional)

- **Cuándo:** motion graphics **a la medida** que el catálogo de `promo-ui` no expresa y FFmpeg no resuelve razonablemente: gráficas animadas desde datos, Lottie, mapas, layouts con metraje real y llamadas de atención, tipografía cinética, demos de producto. Regla de decisión, en este orden: (1) si FFmpeg lo hace (cortes, overlays, `drawtext`, `xfade`, Ken Burns, mezcla) → FFmpeg; (2) promo vertical con la UI de la casa → `promo-ui` (el agente no escribe código); (3) solo entonces → `remotion-video`. Aquí el agente **sí escribe TSX**: usar un modelo fuerte y las skills oficiales (abajo); cuesta más tokens que `promo-ui`. Verificado 2026-10-31 (`[[Lecciones-2026-10-31-remotion-y-longcat]]`).
- **Licencia (decirlo al usuario antes de un render comercial):** Remotion es gratuito para personas físicas, organizaciones sin fines de lucro, empresas de **hasta 3 personas** y evaluación sin uso comercial; una empresa con **4 o más empleados** necesita la **Company License** (https://remotion.pro/license; Creators desde 25 USD/asiento/mes). Este repo lo usan varias personas: `validar` y `render` avisan (`W-REMOTION-LICENCIA`) hasta fijar `remotion.licencia` (`"gratuita"` | `"company"`) en **`config.local.json`**: depende de quién renderiza, así que es valor personal de cada copia (AGENT §16) y `config.json` lo deja en `null`.
- **Entorno (opcional en el preflight):** Node ≥ 20 (ya requerido) y `npm ci --prefix remotion && npx --prefix remotion remotion browser ensure` (`software.opcional.remotion-deps`; ~850 MB con el Chrome Headless Shell, ~20 s). Remotion trae su propio FFmpeg para codificar; el acabado usa el FFmpeg del sistema.
- **Skills oficiales (no vendorizadas):** `npx skills add remotion-dev/skills -a claude-code -y` (CLI `skills`, Node ≥ 22.20) copia `/remotion-best-practices`, `/remotion-create`, `/remotion-markup`, `/remotion-render`, `/remotion-captions`, `/remotion-studio`, `/remotion-docs`, `/remotion-upgrade`… a `.claude/skills/` (gitignored; `skills-lock.json` sí se versiona y `npx skills experimental_install` las restaura). Para escribir el TSX: `/remotion-markup`.
- **Qué escribes tú (agente):** `proyectos/<slug>_<DDMMAAAA>/remotion.json` y `remotion/src/composiciones/proyectos/<Nombre>.tsx` (lo crea `nuevo` desde `Ejemplo.tsx`; exporta `Composicion` y `meta`). Spec:
  ```json
  {"version": 1, "composicion": "DemoProducto", "salida": "demo-producto.mp4", "orientacion": "vertical",
   "fps": 30, "duracion": 12.0, "props": {"titulo": "…", "clip": "clip1.mp4", "audio": "voz.wav"}}
  ```
  `orientacion` usa `config.json > salida.resoluciones` (`vertical` 1080x1920, `horizontal`/`1080p`, `720p`, `4k`, `cuadrada`). `props` son libres; las rutas de archivo son relativas a `recursos/` del proyecto y deben existir: la composición las lee con `staticFile()` porque el render pasa `--public-dir recursos/`. `duracion`, tamaño y `fps` del spec mandan sobre `meta` del TSX (`calculateMetadata`).
- **Comandos:** `nuevo <slug> [--composicion Nombre] [--orientacion …] [--duracion s]` → `validar <proyecto>` (spec + registro de composiciones + deps; errores `E-REMOTION-*` con ruta y arreglo) → `estudio <proyecto> [--puerto 3000]` (vista previa en http://localhost:3000 en segundo plano; `--detener`) → `render <proyecto> [--borrador] [--workers N|50%]` → `estado`, `ayuda`. `todo` = validar + render.
- **Qué hace `render`:** escribe `recursos/remotion/props.json` → `node remotion/motor.mjs render` (empaqueta con webpack, h264 yuv420p con `config.json > remotion` crf 17 / preset slow, avance en el tablero etapa `render`) → acabado FFmpeg **sin recodificar el video**: etiquetas BT.709 por `h264_metadata` (Remotion no las escribe), audio normalizado en dos pasadas a −14 LUFS → AAC 256k, `+faststart` → checks (cuadros, duración ±1 cuadro, color, sonoridad) → salida en la raíz del proyecto + bloque en `info.txt`. `--borrador`: mitad de resolución, CRF 28, sin acabado.
- **Reglas del TSX:** todo depende de `useCurrentFrame()`; `random(semilla)` de Remotion, nunca `Math.random`, timers ni CSS animations (el render es por cuadro); fuentes con `@remotion/google-fonts` o vendorizadas; sin logos de terceros; audio/video del proyecto con `<Audio>` / `<OffthreadVideo src={staticFile('…')} />`. Música y SFX como en promo: `sonido.py` / `fetch_audio.py` y mezcla FFmpeg.
- **Salida:** `0` ok · `2` corrige `remotion.json` o el TSX · `3` entorno (`npm ci --prefix remotion …`) · `1` interno (`--verbose` muestra el stderr de Node).
- **Límites:** sin QA del DOM ni planificador de tiempos como promo (lo que diga el TSX, eso sale); el Studio no guarda `defaultProps` (vienen calculados: se edita `remotion.json`); medido en M3 16 GB: ejemplo de 3 s en 4–6 s, el empaquetado (~3 s) domina en piezas cortas.
- **Cursos y lecciones:** usar `crear-curso`; `Leccion` es composición BASE y no se escribe TSX.
- **Explicadores largos narrados (verificado 2026-10-31, 6.6 min 1920x1080; ver `[[Lecciones-2026-10-31-star-trek-cronologia]]`):** guion en `recursos/guion.json` (escenas con `tts` en letra y datos en pantalla) → voz por toma con `scripts/narrar.py <proyecto>`, tiempos de escena = `max(min, 0.35 + voz + pausa)` → `tiempos.json`, `voz.wav` y `.srt` → mezcla FFmpeg (cama procedural + SFX CC0 + ducking) → `componer.py` escribe `remotion.json` **y** `recursos/remotion/props.json`; la composición es declarativa (pinta `props.escenas` por tipo) para regenerar sin tocar React. **QA barato antes del render:** `npx remotion still src/index.ts <Id> out.png --frame=N --props=recursos/remotion/props.json --public-dir=recursos/` (desde `remotion/`, ~10 s por cuadro) y hoja de contactos con FFmpeg. Fuentes: `@remotion/google-fonts` (instalado a 4.0.539; Orbitron + Inter). Clips de Pexels de 120 s pueden pesar 700–900 MB: recodificar con FFmpeg (`crf 27`) antes de `<OffthreadVideo>`.
- **Promos con metraje real (verificado 2026-11-02, 32.8 s en 9:16 y 16:9; ver `[[Lecciones-2026-11-02-promo-disenador-videovigilancia]]`):** si la pieza depende de una grabación real del producto, usar este motor y no `promo-ui`. Localizar tomas con hojas de contacto con marca de tiempo, excluir datos personales con `crop` al cortar cada clip, declarar `foco` por orientación en un solo TSX y escribir un `remotion.<orientación>.json` por salida. Receta en `[[Motor-Remotion]]`.
- **Piezas de la versión base (no reescribirlas en cada proyecto):**
  - **TSX** — `remotion/src/componentes/Karaoke.tsx` (subtítulo karaoke por oración con tiempos medidos; en las pausas se queda la oración que acaba de sonar), `componentes/Texto.tsx` (`Titular` con palabras entre `*asteriscos*` resaltadas y entrada palabra por palabra; `Apoyo`), `lib/movimiento.ts` (`muelle`, `soltar`, `entra`, `desliza`), `lib/fuentes.ts` (Sora y Figtree empaquetadas: `FUENTE`, `FUENTE_UI`) y `lib/karaoke.ts` (lógica pura: `frases`, `palabraActiva`, `segmentos`). Colores, tamaños y márgenes son props: el TSX del proyecto solo diseña sus escenas.
  - **Python** — el `recursos/componer.py` del proyecto importa `scripts/componer.py`: `escenas_props` (props por escena con palabras relativas a su inicio), `encadenar_tomas` (duraciones desde tomas grabadas sin `tiempos.json`), `cama_procedural` / `cama_ambiental`, `mezclar` (voz −15 LUFS, música −18 con ducking, SFX encima), `recortar_clip`, `logo_con_color` y `escribir_specs` (un `remotion.<orientación>.json` por salida + `remotion.json`).
- **Detalle técnico:** `[[Motor-Remotion]]`.

## explicador-ilustrado (historia o divulgación con animación de estilo ilustrado; el agente solo escribe ilustrado.json)

- **Cuándo:** explicadores narrados con look de ilustración a mano (tinta irregular, color plano con lápiz, papel), tipo
  Shorts de historia: cámara que recorre la ilustración, algún objeto que cobra vida, titulares cinéticos. Si es un curso
  con evaluación → `crear-curso`; si es UI de producto → `promo-ui`.
- **Cuestionario (una ronda, AGENT §2):** tema y fuente de los hechos; orientación (9:16 Short o 16:9); duración (Short ≤ 60 s
  ≈ 8–12 tomas de 4–7 s); estilo (tinta + lápiz por defecto, o la referencia del usuario: **propia**, nunca fotogramas de
  otro canal); cuántas tomas «héroe» con IA de video (0–3) y presupuesto; voz (`voz_default`) y música (`ambiental`).
  Sin respuesta sobre el estilo → **estilo de la casa** (sepia + un solo acento bermellón, hoja canónica).
- **Qué escribes tú:** `proyectos/<slug>_<DDMMAAAA>/ilustrado.json` (contrato en `[[Motor-Ilustrado]]`): `estilo.prompt`
  solo si el usuario pide otro look (≥ 12 palabras: trazo, relleno, papel, paleta, época; sin él va el estilo de la casa) y
  por toma `tts`, `imagen` (encuadre, sujeto y acción **sin texto**), `movimiento` (`imagen` | `parallax` + `capas.sujeto` |
  `clip` | `video_ia` + `video.prompt` solo de movimiento), `camara` y `titulo` (≤ 34 caracteres). Los hechos se verifican
  antes de narrar: los modelos inventan vestuario y objetos de época.
- **Firma de la casa (úsala siempre, con medida):** `entrada: {"tipo": "entintado"}` en la toma 1 y como mucho en un cambio
  de capítulo (≤ 25 % de las tomas; solo `imagen`/`video_ia`); `transicion: "mancha"` en los cambios de idea (el resto,
  fundido); 1 anotación (`circulo`, `subrayado`, `flecha`) cada 2–3 tomas sobre el dato que la voz dice, con `en` = esa
  palabra del `tts`; *una o dos palabras* del titular entre asteriscos (color de acento); `"cierre": true` (sello).
- **Comandos:** `python3 scripts/ilustrar.py nuevo <slug> [--orientacion vertical]` → `validar` (lints + costo estimado) →
  `estilo` (revisar `recursos/estilo/ref_1.png`) → `voz` → `imagenes` → `capas` → `hoja` (**revisar con los ojos antes de
  pagar video**; `--rehacer t3,t5` repite tomas) → `clips [--confirmar]` → `render [--borrador]`. `todo` encadena todo.
- **Reglas:** el texto nunca va dentro de la imagen (lo pone el titular); `parallax` nombra **solo** el sujeto ("the man
  only, not the workbench"); la hoja de estilo debe ir a sangre completa (su composición se hereda); clips solo donde el
  movimiento aporta (agua, fuego, mecanismos, multitudes); anunciar el costo antes de `clips --confirmar`.
- **Costo de referencia (2026-11-10, 52.6 s, 8 tomas):** ~0.5 USD de imágenes, 0.21 USD por un clip Seedance de 8 s,
  voz < 0.05 USD; ~0.9 USD por Short con dos tomas héroe. Bitácora en `[[Lecciones-2026-11-10-estilo-ilustrado]]`.
- **Detalle técnico:** `[[Motor-Ilustrado]]`. Investigación (precios, MCPs, alternativas): `[[Investigacion-2026-11-10-estilo-ilustrado]]`.

## animar-imagen (imagen a video con IA por OpenRouter)

- **Cuándo:** dar movimiento a una imagen fija o generar un clip corto (4–15 s) sin armar un video completo; también para
  elegir modelo antes de una producción.
- **Comandos:** `python3 scripts/video_ia.py modelos --i2v --relacion 9:16` (catálogo con USD/s leído al momento) →
  `estimar --duracion 5 [--modelo id]` → `generar --primer-cuadro a.png [--ultimo-cuadro b.png] --prompt "slow dolly-in…"
  --duracion 5 --relacion 9:16 [--borrador] --salida proyectos/<p>/recursos/clips/x.mp4`. `comparar --modelos a,b,c` corre
  el mismo cuadro en varios modelos en paralelo (prueba de ~1.4 USD con 5 modelos).
- **Prompt:** describir **solo el movimiento** (cámara y acción) y pedir conservar el estilo ("keep the hand-drawn look…
  no photorealism, no text"); el primer + último cuadro es el control de cámara más fiable.
- **Modelos (2026-11-10):** `modelos.video` = Seedance 1.5 Pro (~0.026 USD/s a 720p, el mejor precio con buen resultado),
  `video_respaldo` = Veo 3.1 Lite (0.03 USD/s), `video_premium` = Kling 3.0 Pro (0.112 USD/s). Sin audio por defecto.
- **Topes:** sin `--confirmar` no gasta más de `ilustrado.tope_usd_por_llamada`. Privacidad: el video de OpenRouter no
  admite Zero Data Retention; nunca fotos de personas sin permiso ni `muestras/`.

## descargar-video-youtube

- **Descripción:** descarga un video de YouTube (video + audio) a un archivo local del proyecto.
- **Entradas:** URL del video, formato/resolución destino.
- **Salidas:** video en `recursos/origen.<ext>` (mp4 por defecto).
- **Herramienta local:** `yt-dlp` (**no viene instalado**: `uv tool install yt-dlp` o `brew install yt-dlp`).
- **Modelo de respaldo:** ninguno (100% local).
- **Ejemplo:**
  ```bash
  yt-dlp -f "bv*+ba/b" --merge-output-format mp4 -o "recursos/origen.%(ext)s" "<url>"
  ```
- **Gotchas verificados (2026-10):**
  - YouTube puede entregar **vp9 + opus dentro de un contenedor `.mp4`**. Está bien: al re-codificar
    la salida a h264+AAC (estándar del toolkit) la música se conserva. Comprobar con `volumedetect`
    antes y después (deben ser idénticos) y con la duración del contenedor.
  - Sin un runtime de JavaScript instalado yt-dlp avisa («No supported JavaScript runtime…») y
    puede perderse formatos; en la práctica el merge funcionó igual. Si faltan formatos, ver
    <https://github.com/yt-dlp/yt-dlp/wiki/EJS>.
  - Uso legítimo: material propio o con permiso del titular. Respeta los términos del sitio.

## traducir-texto-en-pantalla

- **Cuándo:** traducir o cambiar el texto que ya viene **incrustado** en un video existente
  (rótulos/pastillas). No es subtitular: se sobre-escribe el texto en el mismo lugar y estilo, y se
  conservan el audio y la duración. Para subtítulos nuevos usar `crear-subtitulos`.
- **Comando (dos pasos):**
  ```bash
  python3 scripts/pantalla.py detectar <video> --json caps.json \
      [--salida salida-es.mp4] [--fuente <ttf>]      # → ventanas + geometría por rótulo
  # editar caps.json: `lineas` = la traducción de cada rótulo (borrar los que sean logotipos)
  python3 scripts/pantalla.py generar caps.json --render
  ```
  `generar` sin `--render` solo imprime el comando ffmpeg (revisar antes de pagar el render).
  Extra: `python3 scripts/pantalla.py fuente <in.woff2> <out.ttf> --peso 700` convierte las woff2
  del repo a una fuente usable (requiere `fonttools`+`brotli`).
- **Qué hace `detectar`:** muestrea a 10 fps, corre `tesseract --psm 11 tsv`, agrupa los fotogramas con
  texto en rótulos (por hueco de tiempo **y** por continuidad del bloque, para no partir un rótulo de
  tres líneas ni pegar uno con el logotipo de otra zona) y mide ventana, texto OCR, bbox del texto y
  **bbox de la pastilla** (blanco puro sobre fondo claro, sin numpy). Sale un JSON editable.
- **Qué hace `generar`:** un PNG RGBA por rótulo (pastilla blanca redondeada + texto, dimensionada a
  `máx(texto+relleno, pastilla original)`) y un `-filter_complex` de `overlay` encadenados con `fade`
  de alfa. **Regla de oro:** el fundido de entrada **termina** en el inicio del rótulo y el de salida
  **empieza** en su fin (`desfase_fin`), para que la pastilla esté opaca durante toda la vida del texto
  original; si no, al fundir se alcanza a ver el original por debajo.
- **Revisar antes de renderizar (importante):** el OCR detecta el rótulo cuando ya es legible, así que
  el original aparece 0.1–0.4 s antes; `generar` adelanta el «opaco desde» (`margen_inicio`, 0.15 s)
  pero **hay que revisar la tabla de `detectar`** y ajustar `inicio`/`fin` donde el original arranque
  antes. `tesseract` también pierde texto fino: el **bbox de la pastilla** es la cota buena para que
  la pastilla nueva cubra todo.
- **Texto que aparece palabra por palabra:** declararlo como `etapas` (`lineas` + `inicio`/`fin` por
  etapa, la última con `fin: null`). Las etapas van **en secuencia**, sin fundido cruzado ni solape
  (la pastilla es idéntica entre etapas): con solape se ven los dos textos duplicados.
- **Salida (≤ 6 líneas + `Siguiente:`):** en `generar`, la ruta del mp4 final (default `salida-es.mp4`
  junto al spec) y la duración vs el original. Intermedios en `overlays/` junto al spec.
- **Errores frecuentes:** 2 = spec/entrada inválidos o ningún rótulo con `lineas`; 3 = falta
  `tesseract`/Pillow (`brew install tesseract`; Pillow no está en el `python3` del sistema — el script
  se re-ejecuta con `/opt/homebrew/bin/python3` o hay que usar un venv); 1 = ffmpeg.
- **Verificar siempre con OCR de los fotogramas de frontera** (ini−0.1, ini, fin, fin+0.1, fin+0.2 y
  los huecos entre rótulos): la única palabra inglesa legítima es la marca. El detalle está en
  [[Lecciones-2026-10-07-traduccion-texto-en-pantalla]].
- **Relación con otras skills:** `descargar-video-youtube` para bajar la fuente; los **logotipos de
  marca no se traducen**; la fuente por defecto es una ttf/otf (convertir las woff2 del repo con
  `pantalla.py fuente`).

## doblar-video (traducir voz y texto de un video existente)

- **Cuándo:** el usuario pasa un video ya hecho (reel, explicativo, demo) y quiere la **misma pieza en otro
  idioma**: narración nueva **y** captions/rótulos en pantalla traducidos, sin cambiar duración ni imagen.
  Es la combinación de `descargar-video-youtube` (yt-dlp también baja reels de Instagram), transcripción con
  tiempos por palabra, traducción, TTS por unidad y composición de captions en el estilo original. Para un
  video que solo tenga rótulos incrustados (sin voz) basta `traducir-texto-en-pantalla`.
- **Comando (cuatro pasos + traducción del agente):**
  ```bash
  yt-dlp --no-playlist -f "bv*+ba/b" --merge-output-format mp4 --write-info-json \
      -o "proyectos/<slug>_<DDMMAAAA>/recursos/origen/original.%(ext)s" "<url>"
  python3 scripts/doblar.py transcribir proyectos/<p>/recursos/origen/original.mp4 --proyecto proyectos/<p>
  python3 scripts/doblar.py unidades proyectos/<p>          # → proyectos/<p>/doblaje.json
  # el agente traduce: llena `es` de cada unidad (o `es_tts` si la grafía no se pronuncia bien),
  # marca énfasis {resaltado} *negrita*, y declara `rotulos` (texto estático traducido) si los hay
  python3 scripts/doblar.py todo proyectos/<p>/doblaje.json   # = voz + render
  ```
  `voz` y `render` también se corren por separado; `render --solo-comando` imprime el ffmpeg sin pagar
  el render. `--sin-captions` dobla solo la voz. Al final, `doblar.py verificar <spec>` comprueba
  duración, voz contra guion (ASR), rótulos y captions (OCR) y loudness (código 5 si algo no cuadra).
  El OCR de captions grises claros falla a veces («OCR «»»): ante un aviso así, extraer la banda en ese
  instante y mirarla (verificado 2026-10-30: 2 de 8 avisos eran falsos negativos del OCR, el video estaba bien).
  Todas las etapas reportan al tablero (`tablero-avance`): lanzar `scripts/tablero.py` antes de `voz`.
- **Qué hace `unidades`:** agrupa las palabras de faster-whisper en oraciones y parte las que pasan de
  `--max-seg` (6 s) en la mejor pausa interna (prefiere la que sigue a una coma). Cada unidad lleva
  `inicio`, `fin` y `slot_fin` (= inicio de la siguiente − 0.08 s): la voz nueva **debe caber en el slot**
  para que la imagen siga sincronizada con lo que se dice.
- **Qué hace `voz`:** TTS por unidad con caché por (texto, proveedor, config); mide la región de habla
  (`silencedetect`) y la ajusta al slot en este orden: (1) VoiceStudio regenera con `duration` objetivo
  (= slot·0.97 + el silencio que el modelo pone alrededor), (2) `atempo` hasta `voz.atempo_max` (1.25),
  (3) si aún no cabe, `W-DOBLAJE-LARGO uNN +X.XXs` → acortar `es`. Luego transcribe los wav nuevos
  (un solo proceso de whisper) y alinea las palabras del guion con `difflib` para los tiempos del
  karaoke; ensambla `voz_<idioma>.wav` (cada unidad en su inicio, `loudnorm` a `voz.lufs` = −16).
- **Qué hace `render`:** cues de ≤ `max_palabras` (4) y ≤ 2 líneas con el ancho medido en la fuente real;
  cada cue es un PNG de la banda (`cubrir` tapa el caption original con el color de fondo) con texto
  normal gris, negritas y **cajas** (fondo + borde + dos puntos en las esquinas, estilo de la casa de
  estos reels) para las palabras `{resaltadas}` contiguas; los rótulos estáticos van en otra capa. Las
  capas entran a FFmpeg como **`ffconcat` de PNG con `duration`** (una entrada por capa, no un `overlay`
  por cue) y se mezclan con la voz nueva (`audio.modo` = `reemplazar` | `mezclar` con `original_db`).
- **Cortinillas (intro y cierre, opcionales):** declarar `cortinillas.intro` / `cortinillas.cierre` en el spec
  (`kicker`, `lineas` con marcas `{resaltado}` `*negrita*`, `sub`, `credito`, `voz`, `duracion_min`, `colchon`,
  `inicio_voz`) y correr `doblar.py cortinillas <spec>` (o `todo`). Cada una es una tarjeta en el estilo de la
  pieza (fondo liso, título que sube y se funde en 0.7 s, rótulo, subtítulo, crédito al autor original) con su
  línea de voz del mismo proveedor; se unen al cuerpo con `xfade`/`acrossfade` de `cortinillas.fade` (0.5 s,
  AGENT §7). Con cortinillas, `render` deja el cuerpo en `recursos/doblaje/cuerpo.mp4` y `cortinillas`
  escribe la `salida`. `--solo-tarjetas` genera las tarjetas sin voz para revisarlas antes de pagar TTS.
  `verificar` entiende el desfase de la intro al comparar voz, rótulos y captions.
- **Voz más o menos animada:** con VoiceStudio la energía la da la voz diseñada (`instruct` joven = más viva
  que `middle-aged`) y `speed` 1.05; diseñar la toma, clonarla a un perfil y fijar `profile_id` + `speed`.
  Cambiar la voz invalida la caché (la config entra al hash): son ~1 min por unidad otra vez.
- **Proveedores de voz (`voz.proveedor`):** `voicestudio` (local, $0, OmniVoice **CC-BY-NC**: solo
  piezas no comerciales; `instruct` admite únicamente los atributos de OmniVoice —`male`, `female`,
  `middle-aged`, `young adult`, `low/moderate/high pitch`, acentos— o un `profile_id`; `seed` fija la
  voz entre unidades), `fish` (`modelos.voz_tts` por OpenRouter, registra costo en `costos.jsonl`) y
  `elevenlabs` (regla AGENT §5). Si OpenRouter no está disponible (p. ej. presupuesto mensual agotado:
  `GET /auth/key` → `limit_remaining: 0`), VoiceStudio es la vía.
- **Salida (≤ 8 líneas + `Siguiente:`):** tabla por unidad (natural → final / slot, atempo, exceso),
  `recursos/doblaje/voz_<idioma>.wav`, `tiempos.json`, y en `render` la ruta del mp4 con su duración
  frente al original. Intermedios en `recursos/doblaje/` (`voz/`, `overlays/`).
- **Errores frecuentes:** 2 = spec (unidades sin `es`, fuente ttf faltante, rótulo sin `cubrir`);
  3 = entorno (sin faster-whisper, sin Pillow, VoiceStudio cerrado → abrir la app y esperar
  `GET /health` = `ok`); 4 = API (VoiceStudio 400 por `instruct` inválido, OpenRouter 403/429).
  `faster-whisper` con PyAV ≥ 16 falla al decodificar: el script le pasa el audio como arreglo (wave +
  numpy), no una ruta.
- **Límites:** traduce la narración y los textos **estáticos** declarados en `rotulos`; el texto que vive
  dentro de ilustraciones animadas (globos de chat, pantallas) **no** se traduce (cada uno sería un
  rótulo rastreado a mano). Material de terceros: solo con permiso del titular.
- **Avatar parlante (foto + voz → video con labios sincronizados): evaluado y NO integrado** (2026-10-31). LongCat-Video-Avatar 1.5 no cabe en 16 GB y en nube cuesta 0.04–0.08 USD/s con la foto y la voz saliendo de la máquina; cifras y cómo encajaría en `[[Lecciones-2026-10-31-remotion-y-longcat]]`. No volver a investigarlo sin cambio de hardware o presupuesto.
- Lecciones y medidas en [[Lecciones-2026-10-30-doblaje-reel]].

## reemplazar-personaje-video (sustituir una mascota fija por otro personaje)

- **Descripción:** cambia el personaje/mascota de un video existente por otra ilustración cuando el original es un **asset fijo** (misma pose; puede entrar y salir deslizándose) sobre fondo uniforme. Verificado 2026-10-30 en el reel doblado (`[[Lecciones-2026-10-30-reemplazo-personaje-reel]]`).
- **Entradas:** video, imagen del asset original tal cual aparece, PNG con alfa del nuevo personaje (recortado de un fondo uniforme) y, si el video ya está doblado, su spec de doblaje.
- **Salidas:** `recursos/origen/<nombre>-<personaje>.mp4` (mismo tamaño, fps y audio) y el doblaje re-renderizado con un spec copia. Si se entrega por el chat, copia a tasa fija en `recursos/entrega/<nombre>-chat.mp4` (tope 30 MiB; receta en `[[AGENT]]` §13).
- **Herramienta local:** `scripts/reemplazar_personaje.py` con `~/.venvs/imagen/bin/python` (uv, Python 3.12: numpy, pillow, opencv-python-headless).
- **Flujo:**
  1. Hojas de contacto para ver dónde y cómo aparece: `ffmpeg -vf "fps=1,scale=180:-2,drawtext=text='%{pts\:hms}',tile=8x4"`. Si cambia de pose o tiene animación propia, hace falta una plantilla por pose (no verificado).
  2. `rastrear <video> <asset> --salida rastreo.json --region x0,y0,x1,y1` → calibra la escala (barrido 0.55–1.0 en 3–4 cuadros) y da posición, score, opacidad y margen libre por cuadro (media resolución, ~1 min para 3 853 cuadros).
  3. `solape <video> rastreo.json <nuevo_alfa.png> --candidatos 0.55:-6,0.52:-6 --pies <fila de los pies>` → elegir la escala con menos contenido tapado (porcentaje de cuadros, p90 y máximo en px²).
  4. `reemplazar … <salida.mp4> --escala S --x X --pies N --muestras n,n` → PNG antes|después de 2–3 escenas y un deslizamiento en `<salida>_muestras/`; luego sin `--muestras` → MP4 (x264 CRF 16, audio copiado; etapas `rastreo` y `reemplazo` en el tablero, con `avance.jsonl` junto al `rastreo.json`).
  5. Doblaje: spec copia con `entrada` = video nuevo y `salida` nueva; respaldar `recursos/doblaje/cuerpo.mp4`; `doblar.py render` + `cortinillas` reutilizan voz y overlays (0 USD, ~2 min).
- **Detalles que importan:** la plantilla se compara sobre "distancia al fondo", no sobre RGB (el fondo claro domina la correlación); se pinta solo la silueta vieja dilatada 11 px con el fondo **muestreado en cada cuadro**; los pies del nuevo se alinean a la base del viejo; el deslizamiento se copia (`x_nuevo = x_reposo + x_medido − x_modal`). La opacidad se mide pero aún no se aplica (fundidos: pendiente).
- **Alfa del nuevo personaje:** fondo = mediana del borde de la imagen (los fondos "uniformes" de Gemini 3 Pro traen un gradiente de ±4 por canal), distancia máxima por canal con rampa 12→40 y solo componentes conectadas ≥ 200 px (sin motas: con rampa 6→30 el bbox se extendía a toda la imagen con 800 píxeles fantasma). Sombra y brillos quedan semitransparentes. `--pies` = primera fila desde abajo cuyo contenido opaco no es gris neutro (suela sobre la sombra).

## tablero-avance (dashboard local de progreso)

- **Cuándo:** siempre que se lance un proceso largo (TTS por unidades, render de FFmpeg, cuadros del motor
  promo, verificación con ASR/OCR). El usuario ve el avance en su navegador sin preguntar; el agente sigue
  trabajando. Es el **estándar de avance del toolkit** (AGENT §9).
- **Comando:**
  ```bash
  python3 scripts/tablero.py [proyectos/<slug>_<DDMMAAAA>] [--puerto 8765]   # sin ruta: el proyecto más reciente
  # abrir http://127.0.0.1:8765/  (en la app de Claude: vista previa `tablero` de .claude/launch.json)
  ```
- **Qué muestra:** anillo con el total; una fila por etapa (barra, porcentaje, duración o tiempo
  transcurrido, ETA por la pendiente de los últimos 3 min, sparkline del historial, chip
  pendiente/en curso/listo/con avisos/error); la gráfica **«valor vs límite»** cuando una etapa reporta
  `datos` (p. ej. cada toma de voz frente a su hueco, con las que se pasan marcadas ▲, tiles de resumen,
  tooltip por barra y tabla); y el registro reciente. Claro/oscuro según el sistema, sin red ni CDN.
- **Cómo reporta una etapa (contrato):** `comun.AVANCE_DIR = <proyecto>/recursos` una vez al arrancar y
  luego `comun.avance(etapa, pct, detalle, estado=None, datos=None)` → línea JSON en
  `recursos/avance.jsonl`. `ffmpeg_con_progreso` ya reporta la etapa `render` solo con fijar `AVANCE_DIR`.
  Etapas conocidas (orden fijo): descarga, transcripcion, unidades, traduccion, voz, render, verificacion;
  cualquier otra aparece después. `datos = {"etiqueta","valor","limite","unidad","nota"}` alimenta la gráfica.
- **Regla para scripts nuevos:** toda etapa de más de ~30 s reporta al menos inicio (`pct` 0-5), avances
  (cada ≥ 1 %) y fin (`pct` 100, `estado` listo|aviso|error). Sin `AVANCE_DIR` la llamada no hace nada,
  así que no rompe scripts viejos ni pruebas.
- **Mejora continua:** el tablero es genérico a propósito. Si una etapa nueva necesita otra lectura
  (p. ej. costo acumulado, cuadros/s), se agrega como `datos` y una vista en `tablero.py`, no un dashboard
  aparte. Anotar lo aprendido en la bitácora del trabajo (AGENT §15).

## convertir-formato / redimensionar

- **Descripción:** convierte entre formatos y resoluciones de salida.
- **Entradas:** archivo origen, formato destino, resolución destino.
- **Salidas:** archivo convertido (según `salida.formatos_*` y `salida.resoluciones`).
- **Herramienta local:** `ffmpeg` (`herramientas.convertir_formato`).
- **Modelo de respaldo:** ninguno.
- **Ejemplo (a vertical 1080x1920):**
  ```bash
  ffmpeg -i entrada.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" vertical.mp4
  ```
- **Notas verificadas con iPhone HLG portrait (2026-09, ver `[[Lecciones-2026-09-23-IMG_7347]]`):**
  - Los videos portrait de iPhone traen `rotation=-90` en metadata: al convertirlos, usar **`-display_rotation 0` como opción de INPUT** (antes del `-i`) para ignorar la rotación y trabajar los pixeles tal cual; luego rotar explícito con `transpose` si se necesita.
  - `tpad` (congelar frame al final) usa **`stop_duration`**, no `stop`.
  - En cadenas de `xfade`, cada `offset` debe ser **menor que la duración acumulada** del video resultante hasta ese punto, o la transición queda corrupta/cortada.

---

## Enlaces

- `[[AGENT]]` — reglas y flujo de decisión
- `[[CLAUDE]]` — entrada para Claude Code
- `config.json` — parámetros y modelos (fuente de verdad)
- `[[Musica-Libre-de-Derechos]]` — fuentes, licencias y receta procedural (skill `musica-fondo`)
- `[[Imagenes-Libres-de-Derechos]]` — fuentes, licencias y atribución (skill `imagenes-libres`)
- `[[Lecciones-2026-09-23-IMG_7347]]` — notas HDR/rotación, TTS y mezcla verificadas
- `[[Motor-Remotion]]` — motor opcional de composiciones libres React → MP4 (skill `remotion-video`): contratos, acabado FFmpeg, licencia
- `[[Lecciones-2026-10-31-remotion-y-longcat]]` — Remotion como segundo motor (medidas en M3) y evaluación de LongCat-Video-Avatar 1.5 (no integrado)
- `[[Lecciones-2026-10-07-traduccion-texto-en-pantalla]]` — traducir/reemplazar el texto sobrepuesto de un video existente (OCR con tesseract, pastilla blanca, fundidos fuera de la ventana original, etapas de revelado, verificación en los fotogramas de frontera)
