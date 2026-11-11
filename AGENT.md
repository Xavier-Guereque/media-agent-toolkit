---
tags: [agente, contexto, media-toolkit]
fecha_modificacion: 2026-11-09
estado: activo
---

<!-- v1.11.0: explicador-ilustrado (scripts/ilustrar.py + composición BASE Ilustrado: hoja de estilo, imagen/parallax/clip/video_ia, titular cinético, hervor 12 fps, papel) y animar-imagen (scripts/video_ia.py: imagen a video por OpenRouter /videos, precios del catálogo, topes); modelos.video*/imagen_ilustrado y config ilustrado; Blender opcional; investigación en docs/Investigacion-2026-11-10-estilo-ilustrado -->
<!-- v1.10.0: compatibilidad con Windows 11 (§3b): -/filter_complex en lugar de -filter_complex_script (eliminado en FFmpeg 8+), comun.pid_vivo/terminar_arbol/python_de_venv, UTF-8 en open() y subprocess, fuente de pantalla.py por plataforma, candado msvcrt en fetch_audio.py -->
<!-- v1.9.0: piezas comunes promovidas a la base: scripts/componer.py (props, mezcla con ducking, specs por orientación), scripts/lienzo.py (lienzos PIL), scripts/curso_spec.py (constructores de curso.json), créditos en commons.py, y en Remotion componentes/Karaoke+Texto y lib/movimiento|fuentes|karaoke; karaoke ya no desaparece en las pausas; remotion.licencia pasa a config.local.json -->
<!-- v1.8.0: cuestionario de arranque en crear-curso; curso.modo (propósito, evaluación, visual), test entre lecciones en el reproductor, actor imagen y voz_default/tema cine en la base -->
<!-- v1.7.0: crear-curso (scripts/curso.py, scripts/narrar.py, composición BASE Leccion, cursos/ejemplo) y docs/Metodologia-Cursos-Video: metodología con evidencia, STPS/CONOCER, estándares y formato visual -->
<!-- v1.6.0: remotion-video (remotion/ + scripts/remotion.py): segundo motor OPCIONAL para composiciones libres React → MP4; licencia Company con 4+ empleados; LongCat-Video-Avatar evaluado y no integrado (Lecciones-2026-10-31-remotion-y-longcat) -->
<!-- v1.5.0: reemplazar-personaje-video (scripts/reemplazar_personaje.py: rastreo por plantilla + composición con alfa) -->
<!-- v1.4.0: crear-imagen con scripts/imagen.py (referencias con el prompt + edición puntual) -->
<!-- v1.3.0: doblaje de video existente (scripts/doblar.py) + tablero local de avance (scripts/tablero.py, comun.avance) -->
<!-- v1.2.0: orientación obligatoria, proyectos/<slug>_<DDMMAAAA>, fade 500ms default,
     unión de varios videos, aprendizaje continuo, preferencias de usuario no versionadas,
     log de costos en proyectos/<slug>/recursos/costos.jsonl (sin carpeta trabajo/) -->

# AGENT — Contexto principal para agentes

> Este archivo es el **punto de entrada** para cualquier agente (Claude, Hermes, OpenCode, KiloCode, etc.) que inicie en este repositorio. Léelo completo antes de ejecutar cualquier tarea. Entradas específicas por agente: `[[CLAUDE]]`, `[[HERMES]]`.

## 1. Propósito

`media-agent-toolkit` estandariza y automatiza la edición de video: descargar video de YouTube, cortar video, unir clips, transiciones, marca de agua, quitar silencios, quitar ruido, subtítulos, traducir el texto sobrepuesto (rótulos incrustados) de un video existente, doblar un video a otro idioma (voz + captions), voz/audio (incl. clonación), imágenes, creación de video y conversión de formatos/resoluciones.

**Secuencia de arranque obligatoria del agente:**

0. **Auto-actualización (antes de todo; opt-in):** leer SOLO `actualizacion.auto_pull` de `config.json`. Si es `false` (default), saltar este paso. Si es `true`: `git fetch` y `git pull --ff-only`, y reportar el resultado. **Gate de revisión:** si el pull trajo cambios en `config.json`, `AGENT.md`, `SKILL.md` o `scripts/`, mostrar el resumen del diff al usuario y pedir confirmación antes de adoptar las nuevas instrucciones (en particular antes de correr `scripts/preflight.sh`). Si el pull falla (sin remote, sin upstream, o cambios locales que impiden el fast-forward), avisar y continuar sin tocar nada. **Nunca** hacer `push` (regla global vigente).
1. Leer `[[AGENT]]` (este archivo).
2. Leer `[[SKILL]]` — catálogo de skills con entradas, salidas y ejemplos.
3. Leer `config.json` — parámetros, modelos y herramientas (fuente de verdad).
4. Leer `.env` — API keys disponibles (nunca imprimir su contenido).

## 2. Aclaración previa (obligatoria)

Tras recibir la instrucción del usuario —y **antes de ejecutar nada**— hacer en **UNA sola llamada** todas las preguntas necesarias para concretar la tarea:

- **Orientación: ¿vertical u horizontal?** Preguntarla **siempre**, aunque parezca obvia (vertical = Reels/TikTok/Stories `salida.resoluciones.vertical`; horizontal = `1080p`/`720p`/`4k`).
- **Nombre del proyecto** (slug) para crear su carpeta en `proyectos/` (sección 13).
- **Resolución y formato** de salida (`salida.resoluciones`, `salida.formatos_*`).
- **Voz:** ¿TTS? ¿qué voz? ¿clonada? ¿sin voz? Si pide emoción, definir el arco emocional por sección (ver `crear-audio` en `[[SKILL]]`).
- **Música:** ¿con o sin? ¿fuente (`musica_libre.fuentes`)? ¿estilo?
- **Transiciones:** tipo (`transiciones.disponibles`) y duración. Si no especifica, aplicar el default: `fade` de 500 ms (sección 7).
- **Subtítulos:** ¿quemados en el video o archivo `.srt`/`.vtt` aparte?
- **Varios videos de origen:** si el usuario pasa más de un video, confirmar el orden; se pegan con transición fade de 500 ms entre fuentes (sección 14).
- **Duración objetivo** de la pieza final.
- **Efectos de presentación (importante):** el kicker de sección numerada (`01 · SECCIÓN`) y la barra de progreso por segmentos **no** se usan por defecto — se leen como una presentación de diapositivas, no como un reel. Solo se agregan si el usuario los pide explícitamente.

**Cursos en video:** en lugar de esta lista, usar el cuestionario de `crear-curso` en `[[SKILL]]`.

No ejecutar hasta tener respuestas o defaults explícitos. Si el usuario pide "usa los defaults", aplicar los de `config.json` y declararlos antes de empezar.

## 3. Preflight de software (obligatorio)

Antes de ejecutar cualquier comando de la edición, correr `zsh scripts/preflight.sh`:

- El script lee `config.json > software`, verifica cada herramienta (`command -v`, o import del módulo para `faster-whisper`) e **instala los requeridos faltantes solo si el comando declarado coincide exactamente con la allowlist fija del script**; cualquier otro valor se rechaza y se reporta. Los opcionales solo avisan.
- Los opcionales (`faster-whisper`, `yt-dlp`, `tesseract`, `voicestudio`, `remotion-deps`…) solo avisan; se instalan a mano con el comando que declara `config.json > software.opcional` cuando una skill los pide.
- Reportar al usuario qué se instaló.
- Si el preflight falla (un requerido no queda disponible), **detenerse** y pedir instrucción.
- Detalles en `[[Preflight-Software]]`.

## 3b. Windows

El toolkit se escribió en macOS, pero corre en Windows 11 (verificado 2026-11-10: las 232 pruebas de Python y las 27 del motor promo pasan). Instalación y gotchas en `[[Lecciones-2026-11-10-compatibilidad-windows]]`:

- **Software:** `winget install --id Gyan.FFmpeg -e`, `winget install --id jqlang.jq -e`, `python -m pip install --user pillow` y `npm ci --prefix promo` (usa el Chrome del sistema). Tras instalar, reiniciar la terminal/la app para que el PATH los vea.
- **Preflight:** `scripts/preflight.sh` depende de zsh y Homebrew y no corre en Windows; verificar a mano lo que declara `config.json > software` (`ffmpeg -version`, `jq --version`, `node --version` ≥ 20, `promo/node_modules`) y reportarlo.
- **Usar `python`** (o `py`) en lugar de `python3`, que en Windows suele ser el alias de la Tienda.
- **Código nuevo:** nunca `os.kill(pid, 0)` (en Windows termina el proceso) → `comun.pid_vivo` / `comun.terminar_arbol`; siempre `encoding="utf-8"` en `open()` de texto y en `subprocess` con `text=True`; venvs con `comun.python_de_venv`; para leer un filtro de archivo, `-/filter_complex <archivo>` (`-filter_complex_script` ya no existe en FFmpeg 8+).

## 4. Regla OpenRouter

- Si el agente es **Claude** → usar `OPENROUTER_API_KEY` del `.env` para los modelos complementarios de la tarea.
- Si es **otro agente compatible con OpenRouter** (p. ej. Hermes) → usar la API del propio agente (no pedir la key al usuario), pero el contexto debe indicarle que use los modelos definidos en `config.json > modelos`. Hermes tiene su propia entrada: `[[HERMES]]` (mapeo de sus herramientas nativas a las reglas de este toolkit).
- Una sola key cubre LLM, visión, imagen, voz y clonación.
- **Antes de una sesión con llamadas de nube, comprobar el presupuesto:** `GET https://openrouter.ai/api/v1/auth/key` → si `limit_remaining` es 0 (403 en las llamadas), la traducción la hace el propio agente y la voz va por VoiceStudio local o ElevenLabs (§5); no insistir contra el 403.
- URL base: `config.json > openrouter.url_base`. Endpoints: `openrouter.endpoints.chat` y `openrouter.endpoints.voz`.

## 5. Regla ElevenLabs (opcional)

- Solo se usa si `ELEVENLABS_API_KEY` existe en `.env` **y** el usuario lo pide explícitamente, o si OpenRouter no está disponible.
- Si la key falta: **nunca pedirla** — simplemente usar OpenRouter.
- Aplica únicamente a `voz`, `clonar_voz` y subtítulos (solo con `scripts/subtitulos.py --proveedor elevenlabs`) — ver `config.json > elevenlabs`.

## 5b. Regla JEV (decisiones estructuradas)

- **Usar JEV (`modelos.decisiones` = `typesafe/jev-1.13`) siempre que se pueda y aplique**: clasificar la tarea del usuario antes de elegir skill, gates de pasos costosos, verificación de criterios, routing entre herramientas.
- Va por la Decisions API (`openrouter.endpoints.decisiones`, `POST /api/alpha/decisions`) con `state` + preguntas tipadas (`noul`/`choice`/`score`). **No funciona en `/chat/completions`.**
- **Contrato verificado (2026-09-28; detalle y errores del servidor en `[[Lecciones-2026-09-28-reel-syscomexpo2027]]`):** `questions` es un **registro** `{"id": {...}}` (un array da `expected record`); cada pregunta lleva `type` (`noul`|`choice`|`score`) **y** `instructions` (string|registro|array); `score` exige `criteria` como **array** y `choice` como **registro** de opciones. La respuesta llega en `answers.<id>`: `noul` = probabilidad 0-1 de cumplimiento (leerla a ella, no `score`).
- **Enrutar la petición antes de elegir skill:** `python3 scripts/enrutar.py "<petición del usuario>"`
  (JEV `choice` sobre las rutas del toolkit: curso, promo_ui, remotion_video, explicador_ilustrado, animar_imagen, reel_fotos, subtitulos, quitar_silencios, voz,
  imagen, traducir_pantalla, editar_video, musica_sfx) imprime la skill y los comandos siguientes; si la
  probabilidad es < 0.55 pide preguntarle al usuario entre las dos mejores. Es el primer paso
  recomendado para orquestadores baratos.
- Verificado en la cuenta el 2026-09-28. Costo ínfimo (~$0.042/M input, output gratis; ~0.00001-0.00004 USD por llamada); igual registrar cada llamada en `costos.jsonl` (sección 10).

## 6. Prioridad de herramientas

**FFmpeg es la herramienta base del toolkit**: si una tarea se puede hacer con FFmpeg, se hace con FFmpeg (cortes, unir clips, transiciones, marca de agua, quitar silencios, quitar ruido, ensamblaje, formatos/resoluciones, extracción de audio).

- **Videos promo con UI animada (estilo de la casa: chat del asistente, WhatsApp, tarjetas, teléfono,
  intro starburst y cierre con CTA):** usar el **motor promo** — `python3 scripts/promo.py <etapa> <proyecto>`
  (skill `promo-ui` de `[[SKILL]]`, arquitectura en `[[Motor-Promo]]`). El agente **solo escribe
  `promo.json` con contenido** y corrige lo que diga `promo.py validar` (errores con ruta y arreglo);
  tiempos, animación, audio y QA los pone el motor. Es la ruta pensada para orquestadores baratos
  (`modelos.razonamiento`): no escribir HTML/CSS/JS ni FFmpeg a mano para estas piezas.
  Render HTML → cuadros con Chromium (Playwright) y **codificación/mezcla con FFmpeg**.
  Música y SFX: cama procedural (FFmpeg), pista propia o **CC0 vía `scripts/fetch_audio.py`**
  (`[[Audio-CC0]]`, solo licencia CC0 1.0).
- **Cursos en video (objetivos, módulos, lecciones, evaluación):** `python3 scripts/curso.py nuevo|validar|voz|componer|qa|render|carta|todo <…>` (skill `crear-curso` de `[[SKILL]]`, metodología en `[[Metodologia-Cursos-Video]]`, motor en `[[Motor-Curso]]`). Primero el cuestionario de la skill. El agente **solo escribe `curso.json`**; lints pedagógicos, sincronía por palabra y diseño visual los pone el motor. Nunca presentar un curso como certificado o con validez oficial.
- **Composiciones libres que el catálogo promo no expresa (motion graphics a la medida: gráficas desde datos,
  Lottie, mapas, metraje real con animación, tipografía cinética):** `python3 scripts/remotion.py nuevo|validar|
  estudio|render <…>` (skill `remotion-video` de `[[SKILL]]`, arquitectura en `[[Motor-Remotion]]`). Es la
  **excepción, no la regla**: FFmpeg → motor promo → Remotion, y la salida siempre se termina con FFmpeg (BT.709,
  loudnorm, faststart). Motor opcional (`software.opcional.remotion-deps`); el agente sí escribe TSX aquí, con las
  skills oficiales `/remotion-*`. Antes de un render comercial, confirmar la elegibilidad de licencia (gratis solo
  para personas, ONG y empresas ≤ 3 personas).
- **Quitar silencios y subtítulos:** `python3 scripts/silencios.py <entrada> --proyecto <dir>` y después
  `python3 scripts/subtitulos.py <salida> --quemar --glosario "…" --proyecto <dir>` (skills `quitar-silencios` /
  `crear-subtitulos`, diseño en `[[Subtitulos-y-Silencios]]`). Los tiempos salen de las pausas medidas, nunca
  del LLM; **no usar `silenceremove` con `-c:v copy`** (corta el audio y no la imagen: desincroniza).
- **Descargar de YouTube y traducir el texto en pantalla:** `yt-dlp` (descarga, video+audio) y
  `python3 scripts/pantalla.py detectar|generar` (skill `traducir-texto-en-pantalla` de `[[SKILL]]`).
  Reemplaza los rótulos **incrustados** con su traducción en el mismo lugar y estilo, y conserva audio
  y duración; no confundir con `crear-subtitulos` (que agrega subtítulos nuevos). `yt-dlp` y
  `tesseract` son opcionales en `config.json > software` (no entran en la allowlist de instalación del
  preflight: `uv tool install yt-dlp` / `brew install tesseract`). Diseño y gotchas en
  `[[Lecciones-2026-10-07-traduccion-texto-en-pantalla]]`.
- **Crear una imagen, o un personaje nuevo en el estilo de una referencia:** `python3 scripts/imagen.py generar --prompt-archivo <prompt.md> [--referencia <img> …] [--relacion 9:16] --salida proyectos/<p>/<nombre>.png` (skill `crear-imagen` de `[[SKILL]]`). Las referencias viajan con el prompt; para corregir detalles se hace una segunda llamada con la imagen generada como referencia y "keep everything, change only…". Comprobar el saldo antes (§4).
- **Explicador o historia con animación de estilo ilustrado (tinta, lápiz de color, papel):** `python3 scripts/ilustrar.py
  nuevo|validar|estilo|voz|imagenes|capas|hoja|clips|render|todo <…>` (skill `explicador-ilustrado` de `[[SKILL]]`, motor en
  `[[Motor-Ilustrado]]`). El agente **solo escribe `ilustrado.json`**: hoja de estilo fija → una ilustración por toma →
  movimiento por toma del más barato al más caro (`imagen` cámara, `parallax` capas, `clip` propio/Blender, `video_ia`
  solo en tomas héroe) → composición base `Ilustrado` de Remotion (titular cinético, hervor a 12 fps, papel). Revisar
  `hoja` antes de `clips`; `clips` se niega a pasar del tope sin `--confirmar` (confirmar el gasto con el usuario).
- **Animar una imagen fija / clip corto de IA (imagen a video):** `python3 scripts/video_ia.py modelos|estimar|generar|comparar`
  (skill `animar-imagen`). Misma `OPENROUTER_API_KEY`; precios leídos de `/videos/models` en cada llamada. El video en
  OpenRouter no admite Zero Data Retention: nada de fotos de personas sin permiso ni material de `muestras/`.
- **Sustituir la mascota fija de un video por otro personaje:** `~/.venvs/imagen/bin/python scripts/reemplazar_personaje.py rastrear|solape|reemplazar …` (skill `reemplazar-personaje-video` de `[[SKILL]]`): rastreo por plantilla del asset original, métrica de solape para elegir escala, silueta pintada con el fondo y PNG con alfa compuesto cuadro a cuadro; después `doblar.py render` + `cortinillas` con un spec copia.
- **Avatar parlante (foto + voz → video con labios sincronizados): no implementado.** Evaluado 2026-10-31 (LongCat-Video-Avatar 1.5: no cabe en 16 GB; en nube 0.04–0.08 USD/s con la foto y la voz saliendo de la máquina). **Corrección 2026-11-10:** OpenRouter **sí** tiene generación de video desde abril de 2026 (`POST /api/v1/videos`, `scripts/video_ia.py`), aunque sin avatar con labios sincronizados en esta evaluación: leer `[[Lecciones-2026-10-31-remotion-y-longcat]]` antes de volver a evaluarlo.
- **Doblar un video existente a otro idioma (voz + texto en pantalla):** `python3 scripts/doblar.py
  transcribir|unidades|voz|render|todo` (skill `doblar-video` de `[[SKILL]]`). La voz nueva se sintetiza
  **por unidad** y se ajusta al hueco de la original (duración objetivo / `atempo`), los captions se
  redibujan en el estilo de la pieza sobre la banda cubierta, y los rótulos estáticos se traducen; la
  duración no cambia. El agente traduce (llena `es` en `doblaje.json`); el TTS va por VoiceStudio local
  (no comercial), Fish por OpenRouter o ElevenLabs (§5). Gotchas en `[[Lecciones-2026-10-30-doblaje-reel]]`.
- **Reels verticales narrados:** usar el pipeline `scripts/reel.py --spec proyectos/<slug>_<DDMMAAAA>/reel.json`
  (skill `armar-reel` de `[[SKILL]]`): cubre escenas Ken Burns, xfade, captions ASS, voz, música y ducking.
  Complementos: `scripts/decision.py` (gates con JEV), `scripts/verificar_voz.py` (diff dirigido
  del TTS) y `scripts/costo_sesion_hermes.py` (suma el costo de la sesión del agente al reporte).

- Otras herramientas locales solo donde FFmpeg no llega: `faster-whisper` (transcripción) y `coqui-tts` / `f5-tts` (clonación local).
- **Blender (opcional, ≥ 5.1)** para animaciones técnicas 3D a escala (`blender -b --factory-startup -P escena.py -- …`, Eevee): piezas, montajes, cortes. Entran como escena `screencast` de un curso o toma `clip` del motor ilustrado. Receta (cámara por azimut/elevación, rótulos que siempre caben, transparencia) en `[[Lecciones-2026-11-10-curso-drywall]]`. El MCP oficial de Blender sirve para inspeccionar; el render va por la CLI.
- `auto-editor` y `deepfilternet` son alternativas opcionales, solo si están instaladas.
- Nube: OpenRouter principal; ElevenLabs opcional (regla ElevenLabs, sección 5).

## 7. Referencia a `config.json`

### `openrouter` / `elevenlabs`
| Clave | Uso |
|---|---|
| `url_base` | URL base de la API del proveedor |
| `variable_api_key` | Nombre de la variable de entorno con la key |
| `endpoints.chat` / `endpoints.voz` | Rutas para chat/completions y síntesis de voz |
| `elevenlabs.opcional` | Si es `true`, aplica la regla ElevenLabs (sección 5) |

### `modelos` — personalización de modelos por tarea
Cambiar un ID aquí cambia el comportamiento de todo el toolkit sin tocar documentación.

| Clave | Modelo por defecto | Tarea que lo consume |
|---|---|---|
| `razonamiento` | `deepseek/deepseek-v4.1-flash` | Orquestación del toolkit: planificación, decisiones complejas, análisis (1M ctx; upgrade de calidad: `deepseek/deepseek-v4-pro`) |
| `rapido` | `google/gemini-2.5-flash` | Tareas ligeras, respuestas rápidas |
| `imagen` | `google/gemini-2.5-flash-image` | `crear-imagen` (deprecado por Google: apagado 2027-03-15) |
| `imagen_ilustrado` | `google/gemini-nano-banana-2.1` | Motor ilustrado: ilustraciones con hoja de estilo (hasta 14 referencias, ~0.04 USD) |
| `video` | `bytedance/seedance-1-5-pro` | Imagen a video (`video_ia.py`, tomas `video_ia`): ~0.026 USD/s a 720p sin audio, primer + último cuadro |
| `video_respaldo` | `google/veo-3.1-lite` | Respaldo de `video` (0.03 USD/s a 720p sin audio; duraciones 4/6/8 s) |
| `video_premium` | `kwaivgi/kling-v3.0-pro` | Tomas premium (0.112 USD/s, 720p) |
| `vision` | `google/gemini-2.5-flash` | "Ver" video, subtítulos con comprensión de frame |
| `voz` | `openai/gpt-audio-mini` | `crear-audio` (TTS) |
| `voz_tts` | `fish-audio/s2-pro` | voz en off del motor promo (TTS puro por `/audio/speech`: lee al pie de la letra; verificado 2026-09-28) |
| `voz_clonada` | `fish-audio/s2-pro` | `clonar-voz` (zero-shot; síntesis verificada 2026-09-28, clonación con muestra pendiente) |
| `guion` | `google/gemini-2.5-pro` | Escritura de guiones y textos para voz |
| `prompts` | `google/gemini-2.5-flash` | Generación/mejora de prompts para imagen/video |
| `decisiones` | `typesafe/jev-1.13` | Decisiones estructuradas (routing, clasificación, gates). **No es chat**: va por `openrouter.endpoints.decisiones` (Decisions API, `POST /api/alpha/decisions`) con `state` + preguntas tipadas (`noul`/`choice`/`score`); no funciona en `/chat/completions`. Verificado 2026-09-28. Costo ínfimo (~$0.042/M input, output gratis); igual registrar la línea en `costos.jsonl`. |

### `herramientas` — mapeo tarea → ejecutor
- `tipo: "local"` → ejecutar el `comando` localmente (FFmpeg primero).
- `tipo: "modelo"` → llamar al modelo indicado en `clave_modelo` (vía OpenRouter, o ElevenLabs si aplica la regla ElevenLabs).
- `alternativa` / `alternativa_local` → usar solo si la vía principal no está disponible.

### `transiciones`
- `tipo_default`: `fade`. **Siempre** se usan transiciones con desvanecimiento por defecto; si el usuario pide otro tipo, se le hace caso.
- `duracion_default`: `0.5` s si el usuario no especifica duración.
- `disponibles`: tipos válidos del filtro `xfade` de FFmpeg.
- **Presets que se ven "viejos" (verificado 2026-09-28):** `wipeup`/`wipedown`, `slideleft` y `circleopen`/`circleclose` se leen como transiciones de presentación. Para piezas verticales cortas funciona mejor un lenguaje coherente de desplazamientos suaves (`smoothleft`, `smoothup`, `smoothright`, `smoothdown`) con algún `hblur` (blur horizontal, se lee como *whip pan*), y `xfade` en torno a **0.38 s**. Al bajar el solape la duración total sube, porque `total = Σduraciones − xfade·(n−1)`.

### `marca_agua`
| Clave | Uso |
|---|---|
| `tipo` | `imagen` (filtro `overlay`) o `texto` (filtro `drawtext`) |
| `ruta_imagen` | Ruta del logo (por defecto `assets/marca_agua.png`); si no existe, avisar al usuario |
| `texto` | Texto a incrustar cuando `tipo` es `texto` |
| `posicion` | `superior_izquierda`, `superior_derecha`, `inferior_izquierda`, `inferior_derecha`, `centro` |
| `opacidad` | 0.0 a 1.0 |
| `margen` | Píxeles de separación desde el borde |
| `escala` | Proporción respecto al ancho del video (0.15 = 15%) |

### `salida`
- `formatos_video`, `formatos_audio`, `formatos_imagen`, `formatos_subtitulos`: formatos permitidos de entrega.
- `resoluciones`: presets `1080p`, `720p`, `4k`, `vertical` (1080x1920), `cuadrada` (1080x1080).

### `actualizacion`
- `auto_pull`: default `false` (opt-in). Si es `true`, el agente ejecuta el paso 0 de la secuencia de arranque (fetch + pull `--ff-only`, con gate de revisión).

### `software`
- `requerido`: binario → comando de instalación. Lo verifica/instala `scripts/preflight.sh` (sección 3).
- `opcional`: binario → comando de instalación. El preflight solo avisa si falta.

### `musica_libre` / `imagenes_libres`
- `fuentes`: fuentes permitidas de assets libres de derechos (sección 8). **Solo estas; nunca material con copyright.**
- `carpeta_local`: dónde se guardan los assets (`assets/musica/`, `assets/imagenes/`).
- Por fuente: `url_base`, `variable_api_key` (nombre de la variable en `.env`) y `licencia`. Wikimedia no requiere key.

### `costos`
- `reporte`: si es `true`, al terminar cada edición se corre el reporte de costos (sección 10).
- `log`: ruta del JSONL de generaciones **relativa a la carpeta del proyecto** (`recursos/costos.jsonl` → vive en `proyectos/<slug>_<DDMMAAAA>/recursos/costos.jsonl`). No existe carpeta `trabajo/`: los intermedios de una edición van siempre en el `recursos/` de su proyecto.
- `moneda`: moneda del reporte (`USD`).
- `sesion_hermes.db`: ruta de la base de Hermes de donde `scripts/costo_sesion_hermes.py` lee el costo de la sesión del agente (`~/.hermes/state.db`). `incluir` documenta si esa partida entra al reporte.

### `render`
- `reporte_avance_minutos`: cada cuántos minutos reportar el % de avance de un render en background (default 5; sección 9).

> "Edición de video" = composición de `cortar_video` + `unir_clips` + `transiciones` + `marca_agua` + `quitar_silencios` + `ensamblar_video`.

### `cursos` (motor de cursos)

- `lufs`, topes (`max_min_leccion`, `ideal_min_leccion`, `max_s_escena`, `max_s_sin_pregunta`, `max_puntos`, `max_palabras_*`), pausas, `subtitulos`, `temas`, `bloom` (verbos por nivel), `acreditacion`, `jev.umbral`, `aviso_ia` y `costo_voz_usd_min`. Cada valor viene de `[[Metodologia-Cursos-Video]]`; detalle en `[[Motor-Curso]]`.

### `ilustrado` (motor ilustrado y `video_ia.py`)

- `usd_imagen` (estimación por imagen), `tope_usd_por_pieza` (clips sin `--confirmar`), `tope_usd_por_llamada` (`video_ia.py generar`), `video_resolucion` / `video_borrador`, `video_audio` (false: la voz la pone el toolkit), `sondeo_s`, `espera_max_s`, `textura`, `hervor`, `fps_animacion`, `fundido`. Detalle en `[[Motor-Ilustrado]]`.
- `openrouter.endpoints.video` / `video_modelos`: `/videos` y `/videos/models`.

### `remotion` (motor opcional de composiciones libres)

- `fps`, `crf`, `x264_preset`: codec del render de `scripts/remotion.py` (mismos valores que `promo`); `concurrencia`: `null` = automática (mitad de los hilos), `N` o `"50%"`.
- `licencia`: `null` (avisar en cada `validar`/`render`), `"gratuita"` (persona, ONG o empresa ≤ 3) o `"company"` (Company License contratada). El toolkit no puede verificarla: la fija cada usuario en su `config.local.json` (en `config.json` queda `null`).
- `software.opcional.remotion-deps`: `npm ci --prefix remotion && npx --prefix remotion remotion browser ensure` (nunca lo instala el preflight; solo avisa).

## 8. Recursos libres de derechos

- **Solo** usar las fuentes declaradas en `config.json > musica_libre` / `imagenes_libres`. Nunca material con copyright.
- **Música:** `local` (`assets/musica/`), `procedural` (generada con FFmpeg) o `pixabay` (requiere `PIXABAY_API_KEY`). Detalles y receta procedural en `[[Musica-Libre-de-Derechos]]`.
- **Imágenes:** `local` (`assets/imagenes/`), `wikimedia` (sin key), `pexels`/`unsplash`/`pixabay` (con key). Detalles en `[[Imagenes-Libres-de-Derechos]]`.
- **Atribución:** incluirla en la entrega (créditos o descripción) cuando la licencia lo exija (Wikimedia/CC).
- Skills asociados en `[[SKILL]]`: `musica-fondo` e `imagenes-libres`.

## 9. Avance de procesos largos (tablero)

- **Estándar:** todo proceso de más de ~30 s (TTS por unidades, render, cuadros, verificación) reporta su avance
  con `comun.avance(etapa, pct, detalle, estado, datos)` tras fijar `comun.AVANCE_DIR = <proyecto>/recursos`.
  Eso escribe `recursos/avance.jsonl`, que lee el **tablero local** `python3 scripts/tablero.py [proyecto]`
  (http://127.0.0.1:8765/, se refresca solo; skill `tablero-avance` de `[[SKILL]]`). **Antes de lanzar un
  proceso largo, levantar el tablero** (en la app de Claude: vista previa `tablero` de `.claude/launch.json`)
  y decirle al usuario la URL; así no hay que preguntar «¿cómo va?».
- Lanzar los renders de FFmpeg **en background** con `-progress pipe:1 -nostats` (`comun.ffmpeg_con_progreso`
  ya lo hace y reporta la etapa `render` al tablero).
- Además, cada `render.reporte_avance_minutos` (default 5) reportar el % al usuario en el chat si no tiene el
  tablero abierto. Mecanismo detallado en `[[Costos-y-Avance]]`.
- El tablero se **mejora, no se duplica**: una lectura nueva (costo acumulado, cuadros/s, tomas que se pasan)
  entra como `datos` de la etapa y una vista en `tablero.py`.

## 10. Reporte de costos

- Cada llamada del agente a OpenRouter (visión, TTS, guion, imagen, prompts) registra una línea `{"id","modelo","tarea","ts"}` en el `costos.jsonl` del `recursos/` del proyecto activo (`costos.log`, relativo a la carpeta del proyecto). El `id` viene en la respuesta de la API; si la respuesta trae `usage`, guardarlo también en la línea (respaldo para estimación).
- Al terminar cada edición, si `costos.reporte` es `true`, correr primero `python3 scripts/costo_sesion_hermes.py --log <log>` para **sumar el costo de la sesión del agente** (que suele ser, con diferencia, la partida más grande) y luego `python3 scripts/costo_generacion.py` e informar el **total USD** y el desglose por tarea/modelo (visión, TTS, guion, sesión del agente, otros). El segundo script localiza por defecto el `proyectos/*/recursos/costos.jsonl` más reciente (el del proyecto activo; se puede forzar con `--log`) y lo rota tras el reporte, de modo que cada reporte cubre únicamente la edición actual.
- Si el endpoint `/generation` no responde, el script estima por `usage.cost` y lo marca como estimado (las líneas de `sesion_hermes` siempre entran así: no tienen `id` de generación que consultar). Detalles y contrato de la tabla `session_model_usage` en `[[Costos-y-Avance]]`.

## 11. Privacidad

- Las muestras de voz para clonación viven en `muestras/` (cubierto por `.gitignore`).
- **Nunca** commitear, subir ni exponer muestras de voz ni el contenido de `.env`.

## 12. Flujo de decisión

```mermaid
flowchart TD
    A[Tarea del usuario] --> EN[Enrutar con JEV: scripts/enrutar.py]
    EN --> Q[Preguntas aclaratorias: orientación, nombre de proyecto, resolución, voz, música, transiciones, subtítulos, unión de videos, duración]
    Q --> PR[Crear proyecto: proyectos/slug_DDMMAAAA con recursos/]
    PR --> PF[Preflight de software: scripts/preflight.sh]
    PF --> CU{¿Curso con lecciones y evaluación?}
    CU -- Sí --> CM[Motor de cursos: curso.json + curso.py validar/voz/componer/qa/render/carta]
    CM --> I
    CU -- No --> PU{¿Video promo con UI animada?}
    PU -- Sí --> PM[Motor promo: promo.json + promo.py validar/cuadros/todo]
    PM --> I
    PU -- No --> IL{¿Explicador con estilo ilustrado?}
    IL -- Sí --> IM[Motor ilustrado: ilustrado.json + ilustrar.py estilo/voz/imagenes/capas/hoja/clips/render]
    IM --> I
    IL -- No --> B{¿La resuelve FFmpeg?}
    B -- Sí --> C[Ejecutar FFmpeg local]
    B -- No --> RM{¿Motion graphics libre que promo no expresa?}
    RM -- Sí --> RE[Remotion: remotion.json + TSX → remotion.py render → acabado FFmpeg]
    RE --> R
    RM -- No --> D{¿Hay herramienta local en config.json?}
    D -- Sí --> E[Ejecutar herramienta local]
    D -- No --> F{¿Es voz o clonación y aplica regla ElevenLabs?}
    F -- Sí --> G[ElevenLabs API]
    F -- No --> H[OpenRouter: modelo según config.json > modelos]
    C --> R[Render en background con reporte de avance cada 5 min]
    E --> R
    G --> R
    H --> R
    R --> T[Tablero local: scripts/tablero.py lee recursos/avance.jsonl]
    T --> I[Entregar en la raíz del proyecto]
    I --> K[Reporte de costos: costo_sesion_hermes.py (sesión del agente) + costo_generacion.py]
    K --> L[Aprendizaje continuo: 2 preguntas + actualizar docs (sección 15)]
```

## 13. Estructura de proyectos

Cada video se trabaja en su propia carpeta dentro de `proyectos/`. La carpeta `proyectos/` **existe en blanco en GitHub** (solo con `.gitkeep`), pero su contenido **nunca se respalda** (está en `.gitignore`).

- **Nombrado:** `proyectos/<slug>_<DDMMAAAA>/` — p. ej. `proyectos/vacaciones-2026_24092026/`. El slug se pide al usuario en la aclaración previa (sección 2); la fecha es la del día en formato DDMMAAAA.
- **`recursos/`** (obligatoria dentro de cada proyecto): todo lo que la edición necesita o produce de forma intermedia — videos de origen (o copias), frames, guiones, WAVs/PCMs de voz, música generada, piezas/segmentos, subtítulos crudos.
- **Salidas en la raíz del proyecto:** el/los archivo(s) resultante(s) (`<nombre>.mp4`, `<nombre>.srt`, etc.) van directamente en `proyectos/<slug>_<DDMMAAAA>/`, no dentro de `recursos/`.
- **`recursos/entrega/`** (opcional): copias adaptadas a un canal con tope de tamaño (el envío por el chat de Remote Control rechaza más de 30 MiB): `<nombre>-chat.mp4` con tasa fija calculada para el tope (`(tope × 0.9 × 8) / duración − audio`), misma duración y resolución, `-movflags +faststart`. La salida completa de la raíz no se toca y al entregar se dice cuál es cuál. Receta en `[[Lecciones-2026-10-30-reemplazo-personaje-reel]]`.
- **Composiciones Remotion:** el TSX de cada proyecto vive en `remotion/src/composiciones/proyectos/<Nombre>.tsx` (gitignored) porque el bundler compila dentro de `remotion/`; el spec `remotion.json`, los recursos y la salida siguen en la carpeta del proyecto.
- **Cursos:** además de `recursos/`, cada lección vive en `lecciones/<id>/` como proyecto Remotion completo, con su MP4, subtítulos y transcripción (`[[Motor-Curso]]`).
- **`info.txt`** en la raíz del proyecto: metadata útil (nombre, fecha, fuentes, decisiones tomadas, costo de generación) para que cualquiera entienda el proyecto sin abrir el video.

## 14. Unir varios videos de origen

Si el usuario pasa varios videos, se **pegan en un solo video** antes de cualquier otra edición:

1. Confirmar el orden en la aclaración previa.
2. Normalizar cada fuente a la resolución/fps destino (`scale` + `pad`, `fps`, `yuv420p`, audio 48 kHz estéreo).
3. Unir con transición **fade de 500 ms** entre fuentes (`xfade` video + `acrossfade` audio) salvo que el usuario pida otra cosa (sección 7).
4. El resto de la edición opera sobre el video ya unido.

Ejemplo de cadena en `[[SKILL]]` → `unir-clips`.

## 15. Aprendizaje continuo (obligatorio tras cada trabajo)

Al terminar cada edición, además del reporte de costos, responder por escrito estas dos preguntas con toda la información generada en la sesión:

1. **¿Cómo puedo optimizar la creación de videos similares a este?** (ahorro de tiempo/costos, pasos evitables, scripts reutilizables)
2. **¿Qué nuevas funciones utilicé?** (filtros, flags, modelos o técnicas no usadas antes — verificadas o pendientes de verificación)

Con las respuestas, actualizar la documentación:

- Crear/actualizar la bitácora `docs/Lecciones-<fecha>-<tema>.md` (frontmatter YAML: `tags`, `fecha_modificacion`, `estado`).
- Si hubo cambios de comportamiento o parámetros, reflejarlos en `AGENT.md`, `SKILL.md` y/o `config.json`.
- Enlazar la bitácora en `AGENT.md` y `docs/Home.md`.

## 16. Preferencias del usuario (no versionadas)

Este repo lo descargan varias personas. Las mejoras o correcciones que pida **cada usuario para su propia copia** van en `docs/Preferencias-Usuario.md`, que está en `.gitignore` y **nunca se commitea** — así un `git pull` no pisa sus personalizaciones.

- **Regla:** por defecto, toda petición de personalización se documenta en `docs/Preferencias-Usuario.md` (y se aplica en la copia local si el usuario lo pide), sin tocar los archivos base.
- **Excepción:** solo cuando el usuario diga explícitamente **"esto va en la versión base del repo"**, el cambio se implementa como mejora general (modificando `AGENT.md`, `SKILL.md`, `config.json`, etc.) y listo para commit/push cuando lo autorice.
- Si `docs/Preferencias-Usuario.md` no existe en la copia local, crearlo con el frontmatter y la explicación de propósito (ver la plantilla en la historia del repo o pedirla al mantenedor).
- **Valores de configuración personales** (p. ej. otra voz por defecto en lugar de la de `config.json > voz_default`): van en `config.local.json` en la raíz del repo (gitignored); `comun.cargar_config` lo fusiona clave a clave sobre `config.json`, así que una copia local puede fijar `voz_default` (proveedor, modelo, `voice`, `instructions`; lo aplica `voz.resolver_voz`) o cambiar un modelo sin tocar los archivos base. Documentar igualmente la preferencia en `docs/Preferencias-Usuario.md`.

## Enlaces

- `[[SKILL]]` — catálogo de skills
- `[[CLAUDE]]` — entrada para Claude Code
- `[[HERMES]]` — entrada para Hermes Agent (mapeo de herramientas nativas)
- `[[README]]` — descripción general del repo
- `config.json` — parámetros y modelos (fuente de verdad)
- `[[Home]]` — índice de la bóveda `/docs`
- `[[Metodologia-Cursos-Video]]` — metodología de cursos en video: evidencia, STPS/CONOCER/SEP, estándares, formato visual y checklist
- `[[Motor-Curso]]` — motor de cursos (`scripts/curso.py`): contratos, códigos, decisiones
- `[[Motor-Promo]]` — motor de videos promo con UI animada (HTML → cuadros → FFmpeg) para orquestadores baratos
- `[[Motor-Remotion]]` — motor opcional de composiciones libres (React → MP4 con Remotion; skill `remotion-video`): contratos, acabado FFmpeg, licencia
- `[[Audio-CC0]]` — descarga de música/efectos solo CC0 con trazabilidad
- `[[Subtitulos-y-Silencios]]` — subtítulos con tiempos medidos (no del LLM) y corte de tiempos muertos sin desincronizar
- `[[Lecciones-2026-09-23-IMG_7347]]` — bitácora técnica (visión, TTS, HDR/rotación, mezcla)
- `[[Lecciones-2026-09-24-narracion-tts]]` — bitácora técnica (TTS emotivo/pacing, visión+guion, ASS dual, sintetizador procedural, cadena xfade)
- `[[Lecciones-2026-09-24-syscomexpo-tiktok]]` — bitácora técnica (Ken Burns crop/zoompan, ASS animado, crop robusto, música rítmica, ducking audible, TTS vs preguntas, xfade fps/tb, página simulada, TikTok vertical)
- `[[Lecciones-2026-09-28-banner-hikvision-xml]]` — bitácora técnica (banner con IA: texto del titular mejor local con drawtext, colorkey sobre fondo uniforme, muestreo de color, composición ultra-ancho)
- `[[Lecciones-2026-09-28-reel-syscomexpo2027]]` — bitácora técnica (reel 45.8 s: contrato de la Decisions API/JEV, `\move` de ASS relativo al evento, alfa de logos del CDN, mosaicos dimensionados al cuadro final, barra de progreso en ASS, verificación de TTS por diff dirigido)
- `[[Lecciones-2026-09-28-reel-fluke-webinar-cobre]]` — bitácora técnica (reel sin fotos: canvas con PIL y `alpha_composite` que hay que reasignar, `qlmanage` para SVG, música desde archivo con fades, transiciones `smooth*`/`hblur`, zona segura del Ken Burns, colchón de silencio del TTS, costo de la sesión del agente)
- `[[Lecciones-2026-09-28-reel-fluke-post]]` — bitácora técnica (reel del post del mismo webinar: el TTS también "responde" listas con dos puntos, QR del enlace de registro verificado decodificando un frame del MP4 final, elegir la ventana de música con perfil de energía por segundo, preview mudo antes de pagar TTS)
- `[[Lecciones-2026-09-29-reel-syscomexpo-30s]]` — bitácora técnica (reel 30.05 s con voz Fish dentro de `armar-reel`: pre-generar `voz_N.wav` con `voz.tts_fish` + pronunciación + lint y `regenerar=false`, duraciones derivadas de las tomas medidas, livelock de ffmpeg en `voz_full.wav` que se resuelve matando y relanzando la etapa, frames tardíos para revisar el lockup del cierre)
- `[[Lecciones-2026-10-07-traduccion-texto-en-pantalla]]` — bitácora técnica (traducir el texto sobrepuesto de un video existente: `yt-dlp`, OCR con tesseract a 10 fps, pastilla blanca detectada sin numpy, fundidos fuera de la ventana original, etapas de revelado sin solape, verificación en fotogramas de frontera)
- `[[Lecciones-2026-10-30-doblaje-reel]]` — bitácora técnica (doblar un reel de Instagram a español: `doblar.py`, unidades con slot, TTS local con VoiceStudio ajustado por `duration`, captions redibujados con `ffconcat` de PNG, calibración de estilo contra el fotograma original, OpenRouter sin presupuesto)
- `[[Lecciones-2026-10-30-personaje-spock]]` — bitácora técnica (personaje nuevo en el estilo de una ilustración de referencia con `scripts/imagen.py`: referencia + prompt, edición puntual que conserva la composición, límites con gestos de manos y logos espontáneos, escalado a `google/gemini-3-pro-image` cuando Flash falla tres veces en el mismo detalle, alternativas locales con mflux evaluadas para 16 GB, OpenRouter con tope mensual)
- `[[Lecciones-2026-10-30-reemplazo-personaje-reel]]` — bitácora técnica (sustituir la mascota fija de un reel: hojas de contacto, rastreo por plantilla sobre distancia al fondo, opacidad y margen por cuadro, solape por candidato, composición numpy ↔ ffmpeg por tuberías, re-render del doblaje con spec copia, copia comprimida en `recursos/entrega/` para el tope de 30 MiB del chat)
- `[[Lecciones-2026-10-31-remotion-y-longcat]]` — bitácora técnica (Remotion como segundo motor opcional: scaffold, motor.mjs con el contrato de promo, acabado FFmpeg, Studio, skills oficiales, licencia, medidas en M3; evaluación de LongCat-Video-Avatar 1.5: no cabe en 16 GB, costos en nube, sin modelos de video en OpenRouter)
- `[[Lecciones-2026-10-31-star-trek-cronologia]]` — bitácora técnica (explicador horizontal de 6.6 min con Remotion: guion → voz Fish por tomas y tiempos medidos, composición declarativa, línea de tiempo con eje por tramos y acomodo automático de filas, Wikimedia Commons con licencia por archivo y rate limit, Pexels videos con UA de navegador y recodificación, cama procedural + whoosh CC0, QA con `remotion still` antes del render)
- `[[Lecciones-2026-10-31-muestras-voz-curso]]` — bitácora técnica (casting de voz para cursos: catálogo TTS de OpenRouter, Fish S2 Pro con `voice` e `instructions`, biblioteca de Fish con `licensed=true`, voces es-MX de Microsoft, Gemini TTS solo PCM, 17 muestras normalizadas y verificadas, costos por minuto)
- `[[Lecciones-2026-11-01-metodologia-cursos]]` — bitácora técnica (metodología y motor de cursos: dibujo dinámico con puntero, sincronía con Whisper, `pathLength` en SVG, quiz aparte porque el MP4 no obliga a responder)
- `[[Lecciones-2026-11-01-cursos-mundo-continuo]]` — cursos como mundo continuo: cámara virtual, actores y acciones en `curso.json`, reproductor con pregunta obligatoria
- `[[Lecciones-2026-11-01-muestra-star-trek-flota]]` — bitácora técnica (curso de Star Trek de 21 lecciones: plantilla y variantes de imagen, recortes con alfa, QA de rótulos y costo real desde `/auth/key`)
- `[[Lecciones-2026-11-02-promo-disenador-videovigilancia]]` — bitácora técnica (promo 9:16 y 16:9 con metraje real en Remotion: hojas con marca de tiempo, recortes por privacidad, foco por orientación, voz Achird, narrar.py colgado en Whisper)
- `[[Musica-Libre-de-Derechos]]` — fuentes y receta procedural de música
- `[[Imagenes-Libres-de-Derechos]]` — fuentes y licencias de imágenes y videos
- `[[Preflight-Software]]` — verificación/instalación de software
- `[[Costos-y-Avance]]` — reporte de costos y avance de render
- `[[Preferencias-Usuario]]` — preferencias locales no versionadas (gitignored; sección 16)
- `[[Lecciones-2026-09-28-motor-promo]]` — bitácora técnica (motor promo: E2E con orquestador barato, lockup blindado, determinismo por píxeles, x264 cuello de botella, BT.709, glifos)
- `[[Lecciones-2026-11-10-curso-drywall]]` — bitácora técnica (curso a partir de 13 h de material de referencia: transcripción en lote por OpenRouter, fichas JSON por video, plan de estudios de 49 lecciones, lección muestra con diagramas a escala dibujados con PIL; `curso.py qa` en clones limpios)
- `[[Lecciones-2026-11-10-compatibilidad-windows]]` — bitácora técnica (el toolkit en Windows 11: winget, `-filter_complex_script` eliminado en FFmpeg 8+, `os.kill(pid, 0)` que mata en Windows, UTF-8 en `open()`/`subprocess`, fuentes y venvs por plataforma, candado con `msvcrt`)
