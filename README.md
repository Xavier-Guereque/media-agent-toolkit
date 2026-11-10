# media-agent-toolkit

## Descripción

Toolkit para mejorar, automatizar y estandarizar la edición de video con agentes de IA: descargar video de YouTube, cortar video, unir clips, transiciones, marca de agua, quitar silencios, quitar ruido, subtítulos, traducir el texto sobrepuesto (rótulos incrustados) de un video existente, doblaje, voz en off (TTS con verificación contra el guion y clonación), música y efectos de sonido (procedurales o CC0) con mezcla y ducking, imágenes, reels narrados, promos con UI animada, cursos en video, composiciones con Remotion y conversión de formatos/resoluciones.

## Contexto para agentes

Este repositorio está diseñado para que un agente (Claude, OpenCode, KiloCode, etc.) cargue sus funciones al iniciar:

- `AGENT.md` — contexto principal, reglas y flujo de decisión
- `CLAUDE.md` — entrada para Claude Code (referencia a `AGENT.md`)
- `SKILL.md` — catálogo de skills con ejemplos
- `HERMES.md` — entrada para Hermes Agent (mapeo a sus herramientas nativas)
- `config.json` — parámetros, modelos y herramientas (fuente de verdad)
- `.env.example` — API keys requeridas/opcionales (copiar a `.env`)

## Instalación

1. Clonar el repo y copiar las variables de entorno: `cp .env.example .env` y rellenar al menos `OPENROUTER_API_KEY`.
2. Verificar el software requerido (FFmpeg, python3, curl, jq):

   ```bash
   zsh scripts/preflight.sh
   ```

   Para el **motor promo** (videos con UI animada) también hace falta **Node ≥ 20** (instalación manual:
   nvm o nodejs.org) y las dependencias de `promo/` (`npm ci --prefix promo`, que el preflight instala;
   renderiza con el Google Chrome del sistema, que se parchea solo, y si no está usa el Chromium de
   Playwright en caché).

   **Opcional — motor Remotion** (composiciones libres React → MP4, skill `remotion-video`): `npm ci --prefix remotion && npx --prefix remotion remotion browser ensure` (~850 MB con el Chrome Headless Shell) y, para que el agente escriba las composiciones con las skills oficiales, `npx skills add remotion-dev/skills -a claude-code -y`. Licencia de Remotion: gratis para personas, ONG y empresas de hasta 3 personas; con 4+ empleados hace falta la [Company License](https://remotion.pro/license). Cada copia fija la suya en `config.local.json` → `{"remotion": {"licencia": "gratuita"}}` (o `"company"`).

   El script instala lo requerido que falte (solo comandos de su allowlist fija; nunca ejecuta strings arbitrarios del config) y avisa de los opcionales (`faster-whisper`, `auto-editor`, `deepFilter`, `yt-dlp`, `tesseract`). Detalles en [docs/Preflight-Software.md](docs/Preflight-Software.md).

## Uso

El flujo lo ejecuta el agente al recibir una tarea de edición (ver `AGENT.md`):

1. **Auto-actualización (opt-in):** solo si `config.json > actualizacion.auto_pull` es `true` (default `false`), hace `git fetch` + `git pull --ff-only` al iniciar; si el pull toca `config.json`, `AGENT.md`, `SKILL.md` o `scripts/`, pide confirmación antes de adoptar los cambios.
2. **Elegir la skill:** `python3 scripts/enrutar.py "<petición>"` decide con JEV (~0.00003 USD) qué skill de `SKILL.md` aplica y qué comandos siguen; si la elección no es clara, el agente pregunta entre las dos mejores. Las decisiones estructuradas de los scripts usan `scripts/decision.py` (Decisions API de OpenRouter).
3. **Preguntas aclaratorias:** orientación (vertical/horizontal, siempre), nombre del proyecto, resolución, formato, voz, música, transiciones (default: fade 500 ms), subtítulos, unión de varios videos y duración objetivo — en una sola ronda, antes de ejecutar.
4. **Proyecto:** cada video se trabaja en `proyectos/<slug>_<DDMMAAAA>/` con `recursos/` para insumos/intermedios y las salidas en la raíz del proyecto. `proyectos/` existe en blanco en GitHub pero su contenido nunca se respalda (ver `AGENT.md` §13).
5. **Preflight:** corre `scripts/preflight.sh`.
6. **Edición** con FFmpeg primero y modelos de OpenRouter donde haga falta; música e imágenes/videos solo de fuentes libres de derechos ([docs/Musica-Libre-de-Derechos.md](docs/Musica-Libre-de-Derechos.md), [docs/Imagenes-Libres-de-Derechos.md](docs/Imagenes-Libres-de-Derechos.md) — Pexels incluye videos).
7. **Videos promo con UI animada:** el agente escribe solo `promo.json` (contenido) y corre
   `python3 scripts/promo.py validar | cuadros | todo <proyecto>`; el motor (`promo/`, HTML → cuadros →
   FFmpeg) pone tiempos, animación, audio y QA. Ver [docs/Motor-Promo.md](docs/Motor-Promo.md).
   Audio CC0 opcional con `scripts/fetch_audio.py` ([docs/Audio-CC0.md](docs/Audio-CC0.md)).
8. **Traducir el texto sobrepuesto de un video existente** (o bajar uno de YouTube): `yt-dlp` para la
   descarga y `python3 scripts/pantalla.py detectar <video> --json caps.json` → editar el JSON con la
   traducción → `python3 scripts/pantalla.py generar caps.json --render`. Reemplaza los rótulos
   incrustados conservando audio y duración (ver [docs/Lecciones-2026-10-07-traduccion-texto-en-pantalla.md](docs/Lecciones-2026-10-07-traduccion-texto-en-pantalla.md)).
9. **Render en background** con reporte de avance cada 5 minutos.
10. **Reporte de costos** al terminar: `python3 scripts/costo_sesion_hermes.py --log <log>` (si el agente es Hermes) y `python3 scripts/costo_generacion.py` (detalles en [docs/Costos-y-Avance.md](docs/Costos-y-Avance.md)).
11. **Aprendizaje continuo:** tras cada edición se responden las 2 preguntas de mejora y se actualiza la bitácora en `docs/` (ver `AGENT.md` §15).

> **Preferencias locales:** las personalizaciones de cada copia del repo van en `docs/Preferencias-Usuario.md` (gitignored, no se commitean); solo con "esto va en la versión base del repo" se modifican los archivos base (ver `AGENT.md` §16).

### Voz en off, música y efectos de sonido

```bash
python3 scripts/lint_voz.py --guion guion.txt          # antes de pagar el TTS: cifras, preguntas, dos puntos, marcas
python3 scripts/narrar.py proyectos/<p>                # recursos/guion.json → una toma por escena, tiempos medidos y .srt
python3 scripts/verificar_voz.py --guion guion.txt --wav-dir proyectos/<p>/recursos   # diff dirigido contra el guion
python3 scripts/promo.py voz proyectos/<p>             # voz del motor promo (Fish por defecto, karaoke por palabra)
python3 scripts/promo.py audio proyectos/<p>           # música procedural + SFX (+ voz) → recursos/audio/mezcla.wav
python3 scripts/fetch_audio.py "whoosh transition" -n 6 --profile sfx   # solo CC0 (Openverse / Freesound)
```

- **Voz por defecto:** `config.json > voz_default` (Gemini 3.8 Flash TTS, voz Achird; alternas Puck, Sulafat y Gacrux). Cada copia puede fijar otra en `config.local.json` (gitignored), y cada curso puede cambiarla con `"voz": {"proveedor": "speech", "voice": "Puck"}`. Locución al pie de la letra para promos: `modelos.voz_tts` (`fish-audio/s2-pro`); clonación zero-shot con `modelos.voz_clonada` y la muestra en `muestras/` (nunca se commitea). ElevenLabs solo si hay key y se pide.
- **Por qué hay lint y verificación:** los modelos de chat con audio a veces "contestan" el guion en vez de leerlo (preguntas, frases con dos puntos) y la transcripción confunde cifras y marcas. `lint_voz.py` frena esos casos antes de gastar, y `verificar_voz.py` pregunta solo por palabras extra, faltantes y la cifra clave. Señal de alarma: más de 0.6 s por palabra.
- **Mezcla:** `sonido.py` (lo corre `promo.py audio`) deja la voz a -16 LUFS, la música a -24 LUFS con ducking por sidechain y el máster a -14 LUFS / -1.5 dBTP, y verifica que la voz quede ≥ 9 dB sobre la música. La música procedural es solo FFmpeg y determinista.

Skills `crear-audio`, `clonar-voz` y `musica-fondo` en `SKILL.md`; política CC0 en [docs/Audio-CC0.md](docs/Audio-CC0.md) y casting de voces en [docs/Lecciones-2026-10-31-muestras-voz-curso.md](docs/Lecciones-2026-10-31-muestras-voz-curso.md).

### Subtítulos y silencios

```bash
python3 scripts/subtitulos.py <video|audio> --quemar --glosario "ACME,HIKVISION,WhatsApp"   # .srt/.vtt y, opcional, quemados
python3 scripts/silencios.py <entrada> --reporte                                              # simulacro: cuánto quitaría
python3 scripts/silencios.py <entrada> --proyecto proyectos/<slug>_<DDMMAAAA>                 # corta imagen y audio en los mismos rangos
```

Los tiempos de los subtítulos salen de pausas medidas (o de faster-whisper), nunca de un LLM; los cortes de silencio se alinean a la rejilla de cuadros para que la voz no se adelante a los labios. Detalle en [docs/Subtitulos-y-Silencios.md](docs/Subtitulos-y-Silencios.md).

### Reels verticales narrados

```bash
python3 scripts/reel.py --spec proyectos/<slug>_<DDMMAAAA>/reel.json todo   # etapas | segmentos | ass | audio | video | todo | verificar
```

Escenas con Ken Burns y `xfade`, rótulos ASS, voz -15 LUFS y música procedural con ducking. Spec de ejemplo en `scripts/reel.ejemplo.json`; skill `armar-reel` en `SKILL.md`.

### Fotos libres de Wikimedia Commons

```bash
python3 scripts/commons.py buscar consultas.json proyectos/<p>/recursos/busqueda          # candidatos + hoja de contactos
python3 scripts/commons.py bajar elegidas.json proyectos/<p>/recursos/busqueda/candidatos.json proyectos/<p>/recursos/img
```

Licencia verificada por archivo (dominio público, CC0, CC BY, CC BY-SA) y atribución en `recursos/img/creditos.json`; CC BY y BY-SA exigen crédito en pantalla. Skill `imagenes-libres` en `SKILL.md`.

### Doblar un video existente y ver el avance

```bash
python3 scripts/doblar.py transcribir proyectos/<p>/recursos/origen/original.mp4 --proyecto proyectos/<p>
python3 scripts/doblar.py unidades proyectos/<p>      # → doblaje.json; el agente traduce `es`
python3 scripts/tablero.py                            # http://127.0.0.1:8765/ (se actualiza solo)
python3 scripts/doblar.py todo proyectos/<p>/doblaje.json && python3 scripts/doblar.py verificar proyectos/<p>/doblaje.json
```

Skills `doblar-video` y `tablero-avance` en `SKILL.md`; estándar de avance en `AGENT.md` §9.

### Crear una imagen o un personaje en el estilo de una referencia

```bash
python3 scripts/imagen.py generar --prompt-archivo proyectos/<p>/recursos/prompt.md \
    --referencia proyectos/<p>/recursos/referencia/ref.jpg --relacion 9:16 --salida proyectos/<p>/imagen.png
# corregir detalles sin perder la composición: la imagen generada como referencia + "keep everything, change only…"
python3 scripts/imagen.py generar --prompt "…" --referencia proyectos/<p>/imagen.png --relacion 9:16 --salida proyectos/<p>/imagen-v2.png
```

Skill `crear-imagen` en `SKILL.md` (modelo `config.json > modelos.imagen`, ~0.04 USD por imagen).

### Sustituir la mascota fija de un video por otro personaje

```bash
PY=~/.venvs/imagen/bin/python   # uv venv --python 3.12 ~/.venvs/imagen && uv pip install numpy pillow opencv-python-headless
$PY scripts/reemplazar_personaje.py rastrear proyectos/<p>/recursos/origen/original.mp4 asset-viejo.png --salida rastreo.json --region 0,300,600,1500
$PY scripts/reemplazar_personaje.py solape proyectos/<p>/recursos/origen/original.mp4 rastreo.json nuevo-alfa.png --candidatos 0.55:-6,0.52:-6 --pies 1120
$PY scripts/reemplazar_personaje.py reemplazar proyectos/<p>/recursos/origen/original.mp4 rastreo.json asset-viejo.png nuevo-alfa.png proyectos/<p>/recursos/origen/original-nuevo.mp4 --escala 0.52 --x -6 --pies 1120
```

Skill `reemplazar-personaje-video` en `SKILL.md`; luego `doblar.py render` + `cortinillas` con un spec copia si el video estaba doblado.

### Composiciones libres con Remotion (motor opcional)

```bash
python3 scripts/remotion.py nuevo demo-producto --duracion 12          # remotion.json + remotion/src/composiciones/proyectos/DemoProducto.tsx
# editar el TSX (skill /remotion-markup) y remotion.json (props; rutas relativas a recursos/ del proyecto)
python3 scripts/remotion.py validar demo-producto
python3 scripts/remotion.py estudio demo-producto                        # vista previa en http://localhost:3000 (--detener para parar)
python3 scripts/remotion.py render demo-producto                         # h264 yuv420p + acabado FFmpeg (BT.709, -14 LUFS, faststart)
```

Skill `remotion-video` en `SKILL.md` (solo para motion graphics que `promo-ui` no expresa; FFmpeg primero), detalle en [docs/Motor-Remotion.md](docs/Motor-Remotion.md). Recetas verificadas:

- **Explicadores largos narrados:** `narrar.py` para la voz y la duración de cada escena, y una composición declarativa que pinta `props.escenas`, de modo que se regenera sin tocar React.
- **Promos con metraje real** (grabación de pantalla del producto): tomas localizadas con hojas de contacto, datos personales excluidos con `crop` al cortar cada clip, un solo TSX con `foco` por orientación y un `remotion.<orientación>.json` por salida (9:16 y 16:9).
- **Piezas comunes en la base:** subtítulo karaoke, titular animado, curvas de movimiento y fuentes en `remotion/src/componentes/` y `remotion/src/lib/`; props, mezcla con ducking y specs por orientación en `scripts/componer.py`; lienzos PIL para reels sin fotos en `scripts/lienzo.py`; constructores de `curso.json` en `scripts/curso_spec.py`. El código de cada proyecto solo declara diseño y contenido.

### Cursos en video

```bash
python3 scripts/curso.py nuevo mi-curso      # copia el ejemplo de oro a proyectos/
python3 scripts/curso.py validar mi-curso    # lints pedagógicos, sin costo
python3 scripts/curso.py todo mi-curso --qa  # voz, stills, render, carta, quiz y transcripciones
```

Etapas sueltas: `validar → voz → componer → qa [--jev] → render [--leccion id] [--borrador] → carta → reproductor`.

- **Cuestionario de arranque:** antes de `nuevo`, el agente hace una sola ronda de preguntas (propósito, público, evaluación, entrega, voz y forma) y lo elegido se escribe en `curso.modo` `{proposito, evaluacion, visual}`, `curso.voz` y `curso.estilo`. Con «usa los defaults» no pregunta.
- **Mundo continuo:** en lugar de láminas, cada lección es un mundo con cámara y actores (`mundo.actores`, incluido el actor `imagen`) que se mueven con `pantalla.acciones` ligadas a palabras del guion; todo movimiento debe explicar algo.
- **Evaluación:** preguntas intercaladas y, con `evaluacion` `entre-lecciones` o `ambas`, un `prueba_final` por lección; `reproductor.html` obliga a responder y bloquea la siguiente lección hasta aprobar o agotar reintentos.
- **Salidas:** por lección MP4 (-16 LUFS), `.srt`, `.vtt` y transcripción; por curso `carta-descriptiva.md`, `quiz.json`/`quiz.md` (para un LMS) y `reproductor.html`.

Skill `crear-curso` en `SKILL.md`. Metodología con evidencia, STPS/CONOCER/SEP y formato visual en [docs/Metodologia-Cursos-Video.md](docs/Metodologia-Cursos-Video.md); contratos en [docs/Motor-Curso.md](docs/Motor-Curso.md).

## Configuración

- `config.json` — fuente de verdad: modelos por tarea, herramientas, transiciones, marca de agua, salida, software, fuentes de música/imágenes libres, costos y render. Incluye `version` y `construccion`.
- `config.local.json` — valores personales de cada copia (gitignored), fusionados clave a clave sobre `config.json`: p. ej. otra `voz_default` u otro modelo sin tocar los archivos base.
- `.env` — API keys: `OPENROUTER_API_KEY` (requerida para Claude), `ELEVENLABS_API_KEY` (opcional, voz/clonación), `PIXABAY_API_KEY` / `PEXELS_API_KEY` / `UNSPLASH_ACCESS_KEY` (opcionales, assets libres; sin ellas se usan las fuentes sin key: local, procedural, wikimedia), `FREESOUND_TOKEN` (opcional, SFX CC0 de Freesound con `fetch_audio.py --source freesound`; sin él se usa Openverse).
- Índice completo de la documentación en [docs/Home.md](docs/Home.md).

## Licencia

Ver [LICENSE](LICENSE).
