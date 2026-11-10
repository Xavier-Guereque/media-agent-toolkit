---
tags: [costos, openrouter, render, avance, scripts]
fecha_modificacion: 2026-09-24
estado: activo
---

# Costos y avance de render

Dos automatizaciones de cada edición: el **reporte de costos** de las llamadas a OpenRouter y el **reporte de avance** de los renders largos. Reglas operativas en [[AGENT]] §9 y §10; configuración en `config.json > costos` y `render`.

## Reporte de costos

### Mecanismo de log

Cada llamada del agente a OpenRouter (visión, TTS, guion, imagen, prompts) registra una línea JSON en el `costos.jsonl` del `recursos/` del proyecto activo (`costos.log` en `config.json`, ruta **relativa a la carpeta del proyecto** → `proyectos/<slug>_<DDMMAAAA>/recursos/costos.jsonl`):

```json
{"id": "gen-abc123", "modelo": "google/gemini-2.5-flash", "tarea": "vision", "ts": "2026-09-24T16:00:00Z"}
```

- `id`: identificador de generación que devuelve la respuesta de OpenRouter (campo `id`).
- `tarea`: etiqueta libre para el desglose (`vision`, `tts`, `guion`, `imagen`, `prompts`, `otros`).
- Si la respuesta trae `usage`, guardarlo también en la línea (`"usage": {...}`): sirve de respaldo para estimar el costo si el endpoint falla.
- No existe carpeta `trabajo/`: el log vive en el `recursos/` del proyecto, y `proyectos/*` está en `.gitignore` — el log no se commitea.

### Cálculo

Al terminar la edición (si `costos.reporte` es `true`):

```bash
python3 scripts/costo_generacion.py
```

Por cada `id` del log, el script llama:

```
GET https://openrouter.ai/api/v1/generation?id=<id>
Authorization: Bearer $OPENROUTER_API_KEY
```

y suma `data.total_cost`. Si el endpoint no responde y la línea trae `usage.cost`, usa ese valor y lo marca como **estimado**. Los `id` duplicados en el log se omiten.

**Seguridad:** el `Authorization: Bearer` solo se envía a `https://openrouter.ai`. Si `config.json > openrouter.url_base` apunta a otro host o esquema, el script lo rechaza y usa el default seguro.

Tras imprimir el reporte, el script **rota** el `costos.jsonl` (lo renombra a `costos-<timestamp>.jsonl`, en la misma carpeta `recursos/` del proyecto). Así, cada reporte cubre únicamente la edición actual y no re-consulta ids de ediciones anteriores.

**Ubicación del log:** por defecto el script usa el `proyectos/*/recursos/costos.jsonl` con la modificación más reciente (el del proyecto activo); se puede forzar otra ruta con `--log ruta/al/costos.jsonl`.

### Ejemplo de reporte

```
== Reporte de costos (USD) ==
Log: proyectos/demo_24092026/recursos/costos.jsonl — 6 llamadas registradas

Por tarea:
  vision               0.0042
  tts                  0.0031
  guion                0.0018

Por modelo:
  google/gemini-2.5-flash                   0.0042
  openai/gpt-audio-mini                     0.0031
  google/gemini-2.5-pro                     0.0018

TOTAL: 0.0091 USD
```

### Costo de la sesión del agente (Hermes)

El reporte anterior solo ve lo que gastaron **los scripts** del toolkit vía OpenRouter (TTS, visión, decisiones, imagen). La **sesión del agente** también cuesta tokens y suele ser, con diferencia, la partida más grande: en una edición real de referencia, 0.0061 USD de generación contra **1.0046 USD de la sesión**. Reportar solo lo primero da una idea falsa de lo que costó la pieza.

Hermes ya registra ese consumo en `~/.hermes/state.db`, tabla `session_model_usage` (por modelo y tarea: `input_tokens`, `output_tokens`, `cache_read_tokens`, `api_call_count`, `estimated_cost_usd`, `actual_cost_usd`). Antes de correr el reporte, volcarlo al log del proyecto:

```bash
python3 scripts/costo_sesion_hermes.py --log proyectos/<slug>_<DDMMAAAA>/recursos/costos.jsonl
python3 scripts/costo_generacion.py --log proyectos/<slug>_<DDMMAAAA>/recursos/costos.jsonl
```

- Escribe **una línea por modelo** en el `costos.jsonl` con `tarea: "sesion_hermes"` y el costo en `usage.cost`. El reporte la recoge por su fallback y la marca como **estimada**, porque no hay `id` de generación que consultar.
- El `id` sintético (`hermes-<sesión>-<modelo>`) la hace **idempotente**: volver a correrlo para la misma sesión reemplaza sus líneas previas en vez de duplicarlas.
- Sin `--session` toma la sesión con actividad más reciente. `--listar` muestra las sesiones recientes y su costo sin escribir nada.
- Es un **total corrido de la sesión de chat**: si en la misma sesión se hicieron varias piezas, el costo aparece completo en el log de la última. Anotarlo así en el `info.txt` del proyecto.
- Abre la base en **solo lectura** (`file:...?mode=ro`): la app puede estar escribiéndola en paralelo.
- Ruta de la base configurable en `config.json > costos.sesion_hermes.db`.

## Avance de render

### Mecanismo

Los renders de FFmpeg se lanzan **en background** con progreso estructurado:

```bash
ffmpeg -i entrada.mp4 ... -progress pipe:1 -nostats salida.mp4
```

`-progress pipe:1` imprime bloques `clave=valor` por stdout; el campo útil es `out_time_ms` (microsegundos procesados).

### Reporte periódico

Cada `render.reporte_avance_minutos` (default **5** minutos):

1. Leer el último `out_time_ms` del progreso del render en background.
2. Calcular `% = out_time_ms / (duración_total_seg * 1_000_000)`.
3. Reportarlo como mensaje de avance al usuario (p. ej. "Render al 42%").

La duración total se obtiene antes con `ffprobe`:

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 entrada.mp4
```

## Enlaces

- [[AGENT]] — secciones 9 (avance) y 10 (costos)
- [[Preflight-Software]] — verificación previa de software
- [[Home]] — índice de la bóveda
