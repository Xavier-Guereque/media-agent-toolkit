---
tags: [lecciones, reel, vertical, tts, fish, ffmpeg, syscomexpo]
fecha_modificacion: 2026-09-29
estado: activo
---

# Lecciones 2026-09-29 — Reel SYSCOM Expo 2027 de 30 s (con voz Fish)

Bitácora de `proyectos/syscomexpo2027-reel-30s_29092026/`: reel vertical 1080x1920 @ 30 fps de
**30.05 s** (8 escenas con Ken Burns + voz en off de **Fish** + música procedural con ducking +
captions ASS sin kicker ni barra), armado con el pipeline `scripts/reel.py` y recursos de
https://www.syscom.mx/syscomexpo2027. Pieza distinta de la del 28/09 (45.8 s, 9 escenas,
gpt-audio-mini): aquí el objetivo era ~30 s con voz que lea al pie de la letra.

## Respuestas obligatorias (AGENT §15)

### 1. ¿Cómo puedo optimizar la creación de videos similares?

- **Generar la voz ANTES de decidir duraciones.** Las 8 tomas de Fish se midieron primero
  (26.69 s de habla) y de ahí salieron las duraciones: `dur_i ≥ offset (0.6) + línea_i + 0.15 s`.
  Con eso la suma de escenas cayó a 33.2 s y el total a 30.05 s **a la primera**, sin re-render por
  voz que se sale de la escena. Es más barato que fijar duraciones y luego recortar el guion.
- **Reutilizar `scripts/voz.py` en lugar de reimplementar Fish.** `tts_fish()`, `a_tts()` (mapa de
  pronunciación) y `lint_voz` ya existían: el script del proyecto son ~60 líneas y da lint previo,
  pronunciación y log de costos. Con `voz.regenerar=false`, `reel.py` reutiliza los WAV tal cual.
- **El lint de voz cuesta cero y atrapa fallas caras:** rechazó «SYSCOM Expo 2027» por llevar cifra;
  con las cifras escritas con letra, Fish las lee sin sorpresas (y el diff dirigido puede pedirlas).
- **Verificar con frames tardíos, no solo al 35 % de la escena.** El cierre entra su lockup a
  start+1.6 s; la rejilla estándar (35 % de la escena) no alcanza a mostrarlo. Dos frames extra a
  28.4 y 29.6 s confirmaron logo + URL + datos.

### 2. ¿Qué nuevas funciones utilicé?

- **`modelos.voz_tts` (Fish) dentro del pipeline `armar-reel`**, que por diseño solo conoce
  `modelos.voz` (gpt-audio-mini por SSE).
- **`voz.a_tts` + `pronunciacion.json` aplicados a un reel de fotos** (antes solo los usaba el motor
  promo): SYSCOM → "Sís-com", PROs → "pros", UN token → UN token.
- **`scripts/verificar_voz.py` con `--cifras` en español hablado** ("doscientos cincuenta").
- Transiciones `smooth*` + `hblur` con `xfade 0.45` en ocho escenas (lenguaje de desplazamientos, sin
  presets de presentación).

## Gotcha verificado: ffmpeg puede quedarse girando sin avanzar

Síntoma exacto, medido: en la etapa `audio` de `reel.py`, el `ffmpeg` del armado de `voz_full.wav`
(8 entradas + `adelay` + `amix=8` + `loudnorm` + `apad,atrim`) quedó **casi 10 minutos al 95 % de CPU
con el WAV de salida congelado** (mismo tamaño y mtime desde el primer segundo). El `sample` de macOS
mostró el hilo principal en `sch_wait` y el hilo del grafo (`fc0`) llamando `av_samples_set_silence`
en bucle: no era falta de disco (87 GB libres) ni de CPU (load 5.5, 60 % idle).

- **El mismo filtro, corrido aparte, terminó en 2 s** — es un livelock ocasional del build, no un
  error del gráfico.
- **Regla práctica:** si una etapa de ffmpeg tarda >3× lo razonable (≈2 s para 30 s de audio) y su
  archivo de salida no crece, **matarla y relanzar la MISMA etapa**; la segunda pasada terminó en
  48 s. Esperar no aporta. Para eso conviene correr las etapas sueltas (`audio`, `video`) en lugar de
  `todo`, que reencadena todo desde cero.
- Efecto colateral: `todo` había quedado a medias con los segmentos ya renderizados; relanzar
  `audio video niveles verificar` aprovechó esos segmentos y el render final salió en 22 s.

## Datos de la edición

- 30.05 s · 8 escenas · 7 transiciones de 0.45 s · 900 cuadros exactos.
- Audio: -14.5 LUFS integrado, TP -0.1 dBTP; música audible en pausas (-0.9 a -4.2 dB en ventanas
  de 0.7 s entre líneas).
- Voz: 8 tomas de Fish, 26.69 s, 0.17–0.25 s/sílaba; diff dirigido limpio (sin palabras extra ni
  faltantes; cifras clave correctas).
- Costo: **0.1438 USD** (sesión de Hermes 0.1366 + TTS 0.0061 + verificación 0.0011).

## Enlaces

- [[AGENT]] · [[SKILL]] · [[Home]] · [[Preferencias-Usuario]]
- [[Lecciones-2026-09-28-reel-syscomexpo2027]] — el reel de 45.8 s del mismo evento (contrato JEV, `\move` en ASS, alfa de logos, mosaicos)
- [[Lecciones-2026-09-28-motor-promo]] — motor promo (voz Fish por defecto, criterio s/sílaba)
