---
tags: [lecciones, reel, vertical, ass, jev, logos, syscomexpo]
fecha_modificacion: 2026-09-28
estado: activo
---

# Lecciones 2026-09-28 — Reel SYSCOM Expo 2027 (45.8 s)

Bitácora de `proyectos/syscomexpo2027-reel_28092026/`: reel vertical 1080x1920 @ 30 fps de 45.8 s
(9 escenas con Ken Burns + TTS femenino + música procedural + captions ASS con barra de progreso),
armado con recursos de https://www.syscom.mx/syscomexpo2027.

## Respuestas obligatorias (AGENT §15)

### 1. ¿Cómo puedo optimizar la creación de videos similares?

- **Cortar la pieza en 9 escenas independientes y medir los WAV antes de decidir duraciones**
  funcionó otra vez: las duraciones por escena se derivaron de las líneas de voz (suma 32 s) +
  pausas, y el ensamblaje solo reencoda al final. Reescribir una escena cuesta segundos.
- **Dimensionar el lienzo al cuadro final, no a la foto.** El primer mosaico se armó con celdas
  9:16 completas (2x2 = 2100x3740) y `zoompan` mostraba solo un cuadrante. Regla: en un mosaico,
  cada celda mide (1080/cols) x (1920/rows).
- **Los scripts del proyecto ya son genéricos** (`generar_reel.py` etapas/mosaico/logos/cierre/segmentos,
  `generar_ass.py`, `build_audio.py`, `build_video.py`): separan assets, segmentos, subtítulos y
  ensamblaje con progreso. Candidatos a promover a `scripts/` del toolkit.
- **Gate con JEV antes del TTS** (coste ~0.00001 USD) evitó re-sintetizar: el guion se validó
  contra los datos oficiales antes de gastar en audio.
- **Verificación visual por rejilla de frames** (`hstack`/`vstack` de 9 fotogramas clave) siguió
  siendo el gate más barato: detectó stickers ausentes, mosaico mal dimensionado y tarjeta recortada
  en dos iteraciones sin ver el video completo.

### 2. ¿Qué nuevas funciones utilicé?

- **Decisions API de JEV (`typesafe/jev-1.13`) verificada end-to-end** (ver abajo el contrato exacto).
- **Barra de progreso dibujada en ASS** con `{\p1}m 0 0 l W 0 l W H l 0 H{\p0}` + `\pos`: una pista
  con `\alpha` y un evento de relleno por escena, sin drawtext ni overlays de FFmpeg.
- **Kickers numerados por sección** ("0N · SECCIÓN") como exige el estilo de `docs/Preferencias-Usuario.md`.
- **Tarjeta de logos de marca** con alfa compuesto por `overlay` (9 marcas) sobre fondo `boxblur`.
- **Música procedural con `-stream_loop`** de una progresión de 4 acordes en vez de `aloop`
  (`aloop` con `size` grande es frágil).

## Contrato verificado de la Decisions API (JEV)

`POST https://openrouter.ai/api/alpha/decisions` con `Authorization: Bearer $OPENROUTER_API_KEY`.

```json
{
  "model": "typesafe/jev-1.13",
  "state": { "tarea": "...", "guion": ["linea 1", "linea 2"] },
  "questions": {
    "gate_guion": { "type": "noul",  "instructions": "El guion cumple los criterios A, B y C." },
    "cierre":     { "type": "choice", "instructions": "¿Qué cierre conviene?",
                    "criteria": { "A": "URL + logo", "B": "solo logo" } },
    "hook":       { "type": "score",  "instructions": "Puntúa la claridad del hook:",
                    "criteria": ["el hook es claro y atractivo"] }
  }
}
```

Gotchas (todos verificados hoy con respuestas de error del servidor):

1. `questions` es un **registro** (`{"id": {...}}`), **no un array** — con array: `expected record`.
2. Cada pregunta exige `type` (`noul` | `choice` | `score`) **y** `instructions`
   (string | registro | array) — sin `instructions`: `invalid_union` en la ruta `instructions`.
3. `score` exige `criteria` como **array**; `choice` exige `criteria` como **registro** (opciones).
   `text`/`prompt`/`options` **no** son los nombres de campo correctos.
4. Respuesta: `answers.<id>` → `noul` devuelve **probabilidad** (0-1) de cumplimiento;
   `choice` devuelve la clave elegida + `probabilities`; `score` devuelve índice + `probabilities`.
5. Con un solo criterio en `score`, el `score` sale 0 y `probabilities` marca 1.0 en el índice 0:
   leer `probabilities`, no `score`.
6. Costo ~0.00001-0.00004 USD por llamada (`usage.cost`), registrar en `costos.jsonl` como `decisiones`.

## Gotchas verificados (importantes)

7. **ASS `\move(x1,y1,x2,y2,t1,t2)`: t1/t2 son milisegundos RELATIVOS al inicio del evento**, no al
   video. Con tiempos absolutos (`int(ini*1000+250)`) el movimiento arranca fuera del evento y el
   sticker queda **invisible** en su posición inicial (fuera de cuadro) durante toda su vida.
   Sintoma típico: "el sticker no aparece" sin ningún error de render.
8. **`pad` NO aplana el alfa.** Los PNG de marca del CDN de SYSCOM traen alfa con RGB basura debajo
   (p. ej. `(72,112,75)` verde); `format=yuv420p` descarta el alfa y revela ese RGB → rectángulos
   verde olivo alrededor de los logos. Composición correcta: `[fondo][logo]overlay=x:y` sobre una
   tarjeta opaca (`color=c=0xEFF2F7:s=WxH`), centrada con `x=cx+(CELL-w)/2`.
9. **Verificación de TTS: comparar, no transcribir a secas.** La transcripción cruda de
   `gemini-2.5-flash` oye "Siscom"/"Cisco" por "SYSCOM", "Citibanamex" por "Banamex" y "550" por
   "250". Pedir el diff dirigido (solo palabras extra / faltantes + cifra clave) da señal útil;
   la transcripción literal genera falsas alarmas. Ante duda de cifra, re-sintetizar con la cifra
   escrita con letra ("doscientos cincuenta") y re-verificar.
10. **ASS + `\p1` para gráficos**: la barra de progreso necesita `Alignment=7` y `\pos`; los eventos
    de relleno se pueden escalonar por escena sin tocar FFmpeg.
11. **Zona segura vertical**: kicker y barra conviene dejarlos en y≈110-125 (no y≈52) para no quedar
    bajo la UI de TikTok/Reels.
12. **Renders largos**: un render de 45.8 s con 9 entradas `xfade` + `ass` tomó ~1 min con
    `preset medium`; el progreso por `-progress pipe:1` puede emitir `out_time_ms=N/A` al cerrar —
    el parser debe tolerar `N/A` o el script termina antes que FFmpeg.

## Mejora aplicada a la versión base (2026-09-28)

El propio análisis de esta sesión señaló que los scripts del proyecto eran reutilizables. Promovidos a
`scripts/` de la versión base y verificados regenerando este mismo reel:

| Script | Qué hace |
|---|---|
| `scripts/reel.py` | Pipeline completo desde un spec JSON: `etapas` (recortes y lienzos: tarjeta de logos, mosaico, cierre), `ass` (kickers, barra de progreso, captions con resalte, stickers, lockup), `segmentos` (Ken Burns con duración exacta, `cortes` internos), `audio` (voz + música procedural + ducking), `video` (xfade + ASS quemado + render con avance), `niveles` y `verificar` (rejilla de frames para gate visual) |
| `scripts/reel.ejemplo.json` | Plantilla del spec (tipos de escena, captions, stickers, voz, música, ducking) |
| `scripts/decision.py` | Gates con JEV (`noul`/`choice`/`score`) validando el contrato de la Decisions API antes de llamar; registra en `costos.jsonl` |
| `scripts/verificar_voz.py` | Verificación del TTS por diff dirigido contra el guion (palabras extra/faltantes + cifra clave) |

Prueba real: `python3 scripts/reel.py --spec proyectos/syscomexpo2027-reel_28092026/reel.json todo`
regeneró la pieza con **45.800 s exactos**, −15.3 LUFS, TP −0.5 dBTP y música audible en la cola
(−6.9 dB máx.); el render bajó de ~60 s a **15 s** (mismo `preset medium`, menos re-encodados). El
entregable del proyecto es ahora la salida de ese pipeline y los scripts locales quedaron en
`recursos/superseded/`. Documentado como skill `armar-reel` en `[[SKILL]]` y referenciado en
`[[AGENT]]` §6.

## Flujo que funcionó (reutilizable)

1. `clarify` en una sola llamada (orientación, slug, resolución, audio, subtítulos, duración, transiciones).
2. Preflight → proyecto `proyectos/<slug>_<DDMMAAAA>/recursos/`.
3. Recursos del CDN de SYSCOM con `format=jpeg` (fotos) y `format=png` (logos); rejilla de contactos
   con FFmpeg + `vision_analyze` para elegir escenas.
4. Gate JEV del guion → TTS por línea → verificación dirigida del audio.
5. Segmentos Ken Burns independientes (duraciones exactas) → `generar_ass.py` → `build_audio.py` → `build_video.py`.
6. Verificación por rejilla de frames → corrección → render final → reporte de costos.

## Datos de la edición

- Duración 45.8 s (9 escenas, 8 transiciones de 500 ms); voz 32.6 s en 9 líneas.
- Audio: -15.3 LUFS integrado, TP -0.5 dBTP; música audible en pausas (max ≈ -8 dB).
- Costo total: **0.0055 USD** (TTS 0.0026 + verificación 0.0029 + JEV ~0.0000).
- Sin marca de agua (`assets/marca_agua.png` no existe en esta copia).

## Enlaces

- [[AGENT]] · [[SKILL]] · [[Home]] · [[Preferencias-Usuario]]
- [[Lecciones-2026-09-24-syscomexpo-tiktok]] — Ken Burns, ASS animado, ducking audible, xfade fps/tb, TTS vs preguntas
- [[Musica-Libre-de-Derechos]] — recetas de música procedural
