---
tags: [agente, hermes, contexto, media-toolkit]
fecha_modificacion: 2026-09-28
estado: activo
---

# HERMES — Entrada para Hermes Agent

El contexto principal de este repositorio vive en `[[AGENT]]`. **Léelo y síguelo antes de ejecutar cualquier tarea.**

Reglas críticas para Hermes:

1. Cargar en orden: `[[AGENT]]` → `[[SKILL]]` → `config.json` → `.env`.
2. Hermes es "otro agente compatible con OpenRouter" (regla §4 de `[[AGENT]]`): usar la API del propio agente para razonar, y los modelos de `config.json > modelos` (vía `OPENROUTER_API_KEY` del `.env`) para visión, imagen, voz, clonación, guion y prompts.
3. FFmpeg es la herramienta base: si una tarea se puede hacer con FFmpeg, se hace con FFmpeg.
4. `ELEVENLABS_API_KEY` es opcional: solo usarla si está configurada y el usuario lo pide; nunca pedirla si falta.
5. Nunca commitear ni exponer `.env` ni el contenido de `muestras/`.
6. Proyectos en `proyectos/<slug>_<DDMMAAAA>/` (contenido gitignored; ver `[[AGENT]]` §13). Personalizaciones del usuario → `docs/Preferencias-Usuario.md` (gitignored); solo con "esto va en la versión base del repo" se tocan los archivos base (ver `[[AGENT]]` §16). Tras cada trabajo, aprendizaje continuo (ver `[[AGENT]]` §15).
7. Videos promo con UI animada (estilo de la casa): motor promo — escribir solo `promo.json` y usar `python3 scripts/promo.py` (skill `promo-ui` de `[[SKILL]]`, detalle en `[[Motor-Promo]]`). Música/SFX CC0 con `scripts/fetch_audio.py` (`[[Audio-CC0]]`).
8. Para elegir la skill de una petición nueva: `python3 scripts/enrutar.py "<petición>"` (JEV, ~0.00003 USD).

## Mapeo de herramientas nativas de Hermes

| Regla del toolkit | Herramienta nativa de Hermes |
|---|---|
| Aclaración previa (§2) | `clarify` — todas las preguntas en UNA sola llamada |
| Preflight (§3) | `terminal` (`zsh scripts/preflight.sh`) |
| Comandos FFmpeg / locales (§6) | `terminal`; scripts Python de varios pasos con `execute_code` |
| Render en background + avance (§9) | `terminal(background=true, notify=true)` con `-progress pipe:1 -nostats`; leer `out_time_ms` con `process(action="poll")` cada `render.reporte_avance_minutos` |
| Llamadas OpenRouter (visión, TTS, guion, imagen) | `execute_code` (requests/streaming SSE) o `terminal` con `curl`; registrar cada llamada en `costos.jsonl` (§10) |
| Verificación de TTS (transcribir WAVs) | `execute_code` con `modelos.vision` + `input_audio` (una llamada admite varios audios) |
| Reporte de costos (§10) | `terminal` (`python3 scripts/costo_sesion_hermes.py --log <log>` y luego `python3 scripts/costo_generacion.py`) — el primero suma el costo de la **sesión de Hermes** (tabla `session_model_usage` de `~/.hermes/state.db`) para que el reporte no subestime la pieza |
| Aprendizaje continuo (§15) | Actualizar docs del repo con `write_file`/`patch` y, además, guardar lecciones reutilizables con `skill_manage` en el perfil de Hermes |
| Motor promo (videos con UI animada) | `terminal`: `python3 scripts/promo.py validar <proyecto>` (corregir `promo.json` con `write_file`/`patch` según cada `E-…`), `cuadros` (revisar `recursos/cuadros/hoja.jpg` con `vision_analyze` si el modelo no ve imágenes) y `todo`; renders largos con `promo.py render <proyecto> --fondo` + `promo.py estado <proyecto>` |
| Memoria entre sesiones | `memory` solo para preferencias estables del usuario; lo demás va a `docs/` y `skills/` |
