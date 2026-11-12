---
tags: [moc, indice, media-toolkit]
fecha_modificacion: 2026-11-10
estado: activo
---

# Home — Índice de la bóveda

Mapa de contenido (MOC) de la documentación del `media-agent-toolkit`.

## Contexto para agentes (raíz del repo)

- [[AGENT]] — contexto principal, reglas y flujo de decisión
- [[SKILL]] — catálogo de skills con ejemplos
- [[CLAUDE]] — entrada para Claude Code
- [[HERMES]] — entrada para Hermes Agent
- [[README]] — descripción general del repo
- `config.json` — parámetros, modelos y herramientas (fuente de verdad)

## Operación del agente

- [[Preflight-Software]] — verificación e instalación de software antes de ejecutar
- [[Costos-y-Avance]] — reporte de costos por edición y avance de render cada 5 min

## Cursos en video

- [[Metodologia-Cursos-Video]] — metodología con evidencia científica, STPS/CONOCER/SEP, estándares internacionales, formato visual y checklist
- [[Motor-Curso]] — `scripts/curso.py`: contratos, códigos, decisiones y pruebas
- [[Fuentes-Cursos]] — notas de investigación con todas sus fuentes

## Motores de video

- [[Subtitulos-y-Silencios]] — subtítulos (SRT/VTT/quemados) con tiempos medidos y corte de tiempos muertos sin desincronizar
- [[Motor-Promo]] — HTML → cuadros → FFmpeg: arquitectura, contratos, determinismo, QA del DOM y códigos de error
- [[Motor-Ilustrado]] — explicadores con animación de estilo ilustrado: `ilustrado.json` → hoja de estilo, imagen/parallax/clip/video IA por toma, titular cinético, hervor a 12 fps y papel; `video_ia.py` (imagen a video por OpenRouter `/videos`, precios leídos del catálogo)
- [[Investigacion-2026-11-10-estilo-ilustrado]] — cómo se hacen los Shorts ilustrados, precios por segundo de 19 modelos de video, consistencia de estilo, MCPs evaluados (fal, Replicate, Comfy Cloud, Blender, Lottie, Rive) y riesgos de licencia
- [[Motor-Remotion]] — motor opcional de composiciones libres (React → MP4 con Remotion): cuándo sí y cuándo no frente a promo-ui y FFmpeg, contratos, acabado FFmpeg, Studio, skills oficiales, licencia

## Recursos libres de derechos

- [[Audio-CC0]] — descarga de música y efectos **solo CC0** (Openverse sin key; Freesound con token) con trazabilidad
- [[Musica-Libre-de-Derechos]] — fuentes (local, procedural, Pixabay), licencias y receta FFmpeg
- [[Imagenes-Libres-de-Derechos]] — fuentes (Wikimedia, Pexels **fotos y videos**, Unsplash, Pixabay), licencias y atribución

## Personalización local

- [[Preferencias-Usuario]] — preferencias locales no versionadas (gitignored; ver AGENT §16)

## Origen del repositorio

Importado el 2026-11-10 desde `SYSCOM-Labs/media-agent-toolkit` a `Xavier-Guereque/media-agent-toolkit` y desmarcado:

- Tema promo `syscom` → `neutro` (`promo/temas/neutro/`); `marca.nombre` = `"MARCA"` como marcador. Cada copia pone su logo en `privado/` (gitignored).
- Piel de chat `syscom_ai` → `asistente_web`; caché CC0 por defecto `~/Music/media-stock`.
- Ejemplos, glosarios y tests usan la marca ficticia `ACME` (`acme.example`).
- Las bitácoras `Lecciones-*` se conservan intactas como historial de proyectos reales.

## Bitácoras técnicas

- [[Lecciones-2026-09-23-IMG_7347]] — visión 404, TTS streaming/pcm16, rotación HLG portrait, mezcla voz+música, sidechaincompress
- [[Lecciones-2026-09-24-narracion-tts]] — pacing TTS, visión+guion con mapa de escenas, ASS dual ES/EN, sintetizador procedural 124 BPM, cadena xfade, gotchas zsh
- [[Lecciones-2026-09-24-syscomexpo-tiktok]] — Ken Burns (crop animado + zoompan), ASS MarginV/Alignment/\move/\fad, crop robusto tras scale, música rítmica procedural, ducking audible, TTS vs preguntas, xfade fps/timebase, página simulada con FFmpeg, TikTok vertical
- [[Lecciones-2026-09-28-banner-hikvision-xml]] — banner con IA sin texto deforme (ilustración + drawtext local), colorkey sobre fondo uniforme, muestreo de color con FFmpeg+xxd, composición de banner ultra-ancho
- [[Lecciones-2026-09-28-reel-syscomexpo2027]] — reel 45.8 s: contrato verificado de la Decisions API (JEV), `\move` en ASS relativo al evento, alfa de logos del CDN (pad no aplana), dimensionar mosaicos al cuadro final, barra de progreso en ASS, diff dirigido para verificar TTS
- [[Lecciones-2026-09-28-reel-fluke-webinar-cobre]] — reel 28.6 s **sin fotos** (canvas con PIL): `alpha_composite` hay que reasignarlo, qlmanage para renderizar SVG, logos sobre pastilla blanca, dos bugs de la versión base de `scripts/reel.py` (raíz del repo y relleno de la rejilla `hstack`), TTS que responde preguntas
- [[Lecciones-2026-09-28-reel-fluke-post]] — reel 29.5 s del **post** del mismo webinar: el TTS también "responde" listas con dos puntos, QR del enlace de registro verificado en un frame del MP4 final, ventana de música elegida con perfil de energía por segundo, preview mudo antes de pagar TTS
- [[Lecciones-2026-09-29-reel-syscomexpo-30s]] — reel 30.05 s del mismo evento con **voz Fish** dentro de `armar-reel` (pre-generar los WAV e importar `voz.tts_fish`, duraciones derivadas de las tomas medidas, livelock de ffmpeg que se resuelve relanzando la etapa, frames tardíos para el lockup del cierre)
- [[Lecciones-2026-09-28-motor-promo]] — motor promo para orquestadores baratos: E2E con DeepSeek Flash (4 → 1 ronda con catálogo completo + ejemplo de oro), lockup de marca blindado, determinismo por píxeles, x264 como cuello de botella, BT.709 con `setparams`, glifos fuera de cobertura
- [[Lecciones-2026-09-30-voicestudio-mcp]] — VoiceStudio local (Electron + backend :3900) integrado por MCP: clonación de voz sin nube (referencia de UNA toma + `ref_text` obligatorio, `/generate` con `profile_id` — no `/v1/audio/speech`), licencia OmniVoice CC-BY-NC, rendimiento medido en M3 16 GB y el rol de la RAM
- [[Lecciones-2026-10-07-traduccion-texto-en-pantalla]] — traducir el texto sobrepuesto de un video existente: `yt-dlp`, OCR con tesseract a 10 fps para hallar los rótulos, pastilla blanca detectada sin numpy, fundidos **fuera** de la ventana original, etapas de revelado sin solape, verificación por OCR en los fotogramas de frontera
- [[Lecciones-2026-10-30-doblaje-reel]] — doblar un reel (Instagram) a español: `scripts/doblar.py` (transcribir → unidades con slot → voz por unidad ajustada con `speed` nativo de VoiceStudio → captions redibujados como `ffconcat` de PNG), perfil de voz clonado desde una toma diseñada para mantener el timbre, calibración del estilo contra el fotograma original, OpenRouter sin presupuesto
- [[Lecciones-2026-10-30-personaje-spock]] — personaje nuevo (Spock) en el estilo de una ilustración de referencia con `scripts/imagen.py` (nuevo): referencia + prompt en una llamada, edición puntual que conserva todo, rostro de una persona real desde una foto recortada (retrato caricaturesco como plantilla), Flash no corrige gestos de manos ni con referencia visual pero `google/gemini-3-pro-image` sí (0.14 USD: subir de modelo tras tres fallos), logos de marca espontáneos, `image_config.aspect_ratio` verificado, mflux evaluado para 16 GB; 14 llamadas, 0.65 USD
- [[Lecciones-2026-10-30-reemplazo-personaje-reel]] — sustituir la mascota fija de un reel por otro personaje: `scripts/reemplazar_personaje.py` (rastreo por plantilla multiescala sobre distancia al fondo, opacidad y margen por cuadro, métrica de solape para elegir escala, pintar la silueta con el fondo muestreado y componer PNG alfa siguiendo deslizamientos), re-render del doblaje con spec copia; alfa limpio del PNG nuevo (mediana del borde + componentes ≥ 200 px); copia comprimida a tasa fija en `recursos/entrega/` para el tope de 30 MiB del chat
- [[Lecciones-2026-10-31-remotion-y-longcat]] — Remotion como segundo motor opcional (scaffold con registro generado, `motor.mjs` con el contrato de promo, `calculateMetadata` desde el spec, `--public-dir` → `staticFile()`, acabado FFmpeg porque Remotion no etiqueta BT.709, Studio, skills oficiales copiadas y `skills-lock.json`, Node 22.18 vs 22.22, medidas en M3) y evaluación de LongCat-Video-Avatar 1.5 (64 GB en MLX, 0.04–0.08 USD/s en WaveSpeed, Space HF de 5 s, OpenRouter sin video): no integrado
- [[Lecciones-2026-10-31-star-trek-cronologia]] — primer **explicador largo horizontal** (6 min 36 s, 1920x1080) con el motor Remotion: guion → voz Fish por tomas con tiempos medidos (`narrar.py`), composición declarativa por `props.escenas`, línea de tiempo con eje por tramos, zoom por siglo y acomodo automático de filas, fotos de Wikimedia Commons con licencia verificada por archivo (rate limit 429: originales ≤ 4700 px y pausas), B-roll de Pexels (UA de navegador, recodificar clips de 700–900 MB), cama procedural + whoosh CC0 del caché, QA con `npx remotion still` antes del render; **v2** la misma noche: 78 fotos (contrato `imgs`/`retratos`/`nave`/`tira`/`mosaico`), `scripts/commons.py` (el 429 era el User-Agent), voz Achird por `config.local.json`, cama cacheada a la duración vieja
- [[Lecciones-2026-10-31-muestras-voz-curso]] — **casting de voz** para cursos en línea: catálogo TTS de OpenRouter (`/models?output_modalities=speech`, 38 modelos), Fish S2 Pro con `voice` (id de su biblioteca) e `instructions` (se cobran como caracteres), biblioteca de Fish sin key con `licensed=true`, voces es-MX de Microsoft MAI-Voice 2.1, Gemini TTS solo PCM, 17 muestras a −16 LUFS verificadas en una llamada, compilado con anuncio hablado y página con reproductor por voz; 0.12 USD
- [[Lecciones-2026-11-01-metodologia-cursos]] — metodología y motor de cursos: pila de cinco capas, dibujo dinámico con puntero, sincronía con Whisper, `pathLength` en SVG, atenuado solo durante la voz, quiz aparte porque el MP4 no obliga a responder
- [[Lecciones-2026-11-01-cursos-mundo-continuo]] — cursos como mundo continuo: cámara virtual, actores y acciones en `curso.json`, reproductor con pregunta obligatoria
- [[Lecciones-2026-11-01-muestra-star-trek-flota]] — curso de Star Trek de 21 lecciones: plantilla y variantes de imagen, recortes con alfa, QA de rótulos y costo real desde `/auth/key`
- [[Lecciones-2026-11-02-promo-disenador-videovigilancia]] — promo 9:16 y 16:9 con metraje real en Remotion: hojas con marca de tiempo, recortes por privacidad, foco por orientación y voz Achird
- [[Lecciones-2026-11-11-firma-ilustrada]] — firma de la casa del motor ilustrado: entintado local que no salta, mancha, anotaciones, sello; hoja canónica a sangre completa
- [[Lecciones-2026-11-10-estilo-ilustrado]] — primer Short ilustrado (52.6 s, ~2.7 USD con la prueba de 5 modelos): hoja de estilo que hereda su composición, parallax que exige nombrar solo el sujeto, clips de IA a 24 fps que rompen `<OffthreadVideo>` hasta normalizarlos a 30 fps
- [[Lecciones-2026-11-10-curso-drywall]] — de 13 h de material de referencia a plan de estudios y lección muestra: transcripción en lote con `gemini-2.5-flash` (0.0027 USD/min), fichas JSON con dudas y contradicciones, diagramas técnicos a escala con PIL, cursor con `dx/dy` sobre imágenes del mundo, `qa` arreglado para clones limpios
- [[Lecciones-2026-11-11-drywall-vanos-animado]] — lección de vanos con animación 3D mejorada: tiempos por palabra `W()`, rebote BACK, cotas que se dibujan, atornillador, `action_get_channelbag_for_slot` en Blender 5, Freestyle descartado por lento
- [[Lecciones-2026-11-11-drywall-refuerzos-rack]] — lección de refuerzos (TV, muebles, racks) en 3D **a todo color**: `scripts/blender_estilo.py` (caricatura + contorno de casco invertido), `scripts/lint_w3d.py` antes del render, rótulos ≥ 60 px, placa transparente solo en la zona del refuerzo
- [[Lecciones-2026-11-10-compatibilidad-windows]] — el toolkit en **Windows 11**: instalación con winget, `-filter_complex_script` eliminado en FFmpeg 8+ (→ `-/filter_complex`), `os.kill(pid, 0)` que en Windows termina el proceso, UTF-8 en `open()`/`subprocess`, fuentes y venvs por plataforma; `preflight.sh` aún solo zsh
- [[Lecciones-2026-11-06-video-animado-syscom-ia]] — **motion graphics puros** (UI del portal simulada con divs, sin metraje) en 16:9 y 9:16 con subtítulo karaoke: margen `%` que se resuelve contra el ancho (el subtítulo tapaba la ventana), `maxWidth`+`flexWrap` en el subtítulo, contenedor flex en fila que no estira a lo ancho (cierre descentrado), escalado en bloque de la ventana en vertical, layout radial que se encima en 9:16, intercambio del spec para dos orientaciones y revisión por hojas + zoom de la franja crítica
