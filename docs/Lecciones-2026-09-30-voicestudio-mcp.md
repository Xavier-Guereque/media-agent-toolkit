---
tags: [bitacora, voicestudio, mcp, clonacion-voz, tts-local, omnivoice]
fecha_modificacion: 2026-09-30
estado: verificado
---

# Lecciones 2026-09-30 — VoiceStudio local + MCP (clonación de voz sin nube)

> Instalación e integración de [VoiceStudio](https://github.com/debpalash/VoiceStudio) (Electron 0.5.6, AGPL-3.0)
> como **servicio local opcional** del toolkit: clonación de voz 100% local (las muestras de `muestras/` no salen
> del equipo, AGENT §11) y TTS a costo marginal $0. Validado a oído por el usuario en español mexicano.
> La integración concreta de ESTA máquina (binding, rutas) vive en `[[Preferencias-Usuario]]`.

## Topología verificada

- App Electron en `/Applications/VoiceStudio.app`; al abrirla levanta el **backend Python en `127.0.0.1:3900`**
  (data plane + API + MCP) y un sidecar Rust de control en `:3902` (dictado; no lo usa el toolkit).
- `GET /health` → `{"status":"ok","device":"mps"}` — verificar siempre que `device` no sea `cpu`.
- Discovery: `GET /.well-known/voicestudio-speech` → `voicestudio.speech.v1` (lista endpoints, incl. `mcp`).
- OpenAPI: `GET /openapi.json` (fuente de verdad de contratos).
- **El MCP solo responde con la app abierta.** Si está cerrada, Claude Code muestra el server desconectado y el
  toolkit sigue con OpenRouter sin romperse nada.

## Instalación (macOS Apple Silicon, verificado 2026-09-30)

1. `curl -fsSL https://voicestudio.sh/install | sh` — el script verifica SHA-256 contra el `SHA256SUMS.txt` del
   release antes de instalar (revisado: legítimo, solo HTTPS, backup de versión previa).
2. Primer arranque: `uv sync` descarga el runtime Python (~1.7 GB en `~/Library/Application Support/VoiceStudio`).
   Puede tardar 15-25 min según red; el backend no responde hasta terminar. **No confundir con un cuelgue.**
3. Modelo TTS default: `k2-fsa/OmniVoice` (0.6B params, 646 idiomas, zero-shot). `POST /models/install` con
   `{"repo_id":"k2-fsa/OmniVoice"}`; son **3.27 GB en disco** (el catálogo declara 2.4 GB lógicos).
   **Licencia CC-BY-NC: uso NO comercial.** Piezas comerciales siguen por fish-audio/ElevenLabs (AGENT §5).
4. Reinicios posteriores: backend listo en ~20 s.

## Clonación de voz — contrato y trampas (todo verificado)

- **La referencia debe ser UNA sola toma continua** (10-20 s). Con varias tomas encadenadas el engine crashea:
  `RuntimeError: TTS engine stopped mid-generation`. Para aislar la primera toma sin escucharla:
  `silencedetect=n=-30dB:d=0.2` y cortar en la pausa tras el último enunciado completo (+0.2 s de colchón,
  `afade` de salida para no cortar sílaba).
- **`ref_text` es obligatorio en la práctica.** Sin él, la síntesis aborta pidiendo un ASR instalado
  ("Automatic reference transcription needs an installed speech-to-text model"). Transcribir la muestra con
  `modelos.vision` (gemini-2.5-flash, `input_audio` mp3 base64 — flujo ya usado en `verificar_voz.py`);
  la ortografía fonética del ASR ("Javier", "Cyscom") es CORRECTA para el ref_text: lo que importa es la
  correspondencia sonido↔texto, no la grafía de marca.
- **Clonar = `POST /profiles`** (multipart: `name`, `ref_audio=@archivo`, `ref_text`, `language=Auto`) →
  devuelve `id` de 8 hex. Sintetizar con esa voz = **`POST /generate` con `profile_id`** (multipart).
- ⚠️ **`/v1/audio/speech` (compat-OpenAI) NO usa el `ref_text` del perfil** y falla pidiendo ASR. Solo sirve
  con las voces alias del sistema. Para clonación usar `/generate`.
- ⚠️ `PUT /profiles/{id}` es **JSON-only**; no acepta multipart para cambiar el audio. Para sustituir la
  referencia: `DELETE /profiles/{id}` + `POST /profiles` nuevo (2 llamadas, sin sorpresas).
- El encodeo de una referencia NUEVA cuesta una vez (~2 min la primera generación de ese perfil); después se
  cachea (`prompt_cache/`) y las siguientes tardan segundos.

## Rendimiento medido (M3, 16 GB, MPS)

| Caso | Espera | Audio | Nota |
|---|---|---|---|
| Voz default, 1ª gen | 50 s | 4.4 s | incluye carga del modelo (~8 s) + warmup Metal |
| Voz default, 2ª gen | 17.6 s | 6.3 s | caliente |
| Clonada, 1ª del perfil | 153 s | 3.7 s | encodeo de referencia nueva |
| Clonada, en caliente, **RAM presionada** | 36-38 s | ~3 s | swap 3.8 GB en uso |
| Clonada, en caliente, **RAM liberada** | **14.5 s** | 4.1 s | tras reiniciar la app |

- **La RAM es EL factor.** Síntoma de presión: el backend muere (connection refused en :3900 con la app
  aparentemente viva) o las generaciones se van a 40× tiempo real. Remedio: reabrir la app (~20 s) y cerrar
  apps pesadas antes de sesiones de voz. Con 16 GB, una generación a la vez — nada de paralelizar.
- Salida: WAV 24 kHz mono (convertir con FFmpeg al destino, p. ej. `-ar 48000 -ac 2` para los pipelines).

## MCP (la vía de integración elegida)

- Endpoint: `http://127.0.0.1:3900/mcp/` (**Streamable HTTP**, con sesión `Mcp-Session-Id`; hay que enviar
  `Accept: application/json, text/event-stream` y las respuestas vienen en SSE `event: message`).
- Tools: `generate_speech`, `clone_voice`, `transcribe`, `list_voices`, `list_languages`,
  `list_personalities`, `check_health`.
- Registro en Claude Code (scope usuario, NO toca el repo):
  `claude mcp add --transport http --scope user voicestudio http://127.0.0.1:3900/mcp/ --header "X-OmniVoice-Client-Id: claude-code"`
- **Voz por agente:** `PUT /api/mcp/bindings` con `{"client_id":"claude-code","profile_id":"<id>"}` → todo
  `generate_speech` de ese agente usa esa voz salvo `profile_id` explícito.
- **Modo files (recomendado):** `~/.config/omnivoice/env` con
  `OMNIVOICE_MCP_OUTPUT_MODE=files` y `OMNIVOICE_MCP_BASE_PATH=<repo>` → el audio se escribe a disco y el agente
  recibe `output_path` (el base64 no infla el contexto). Requiere reiniciar la app. Ojo: el WAV cae en la
  **raíz** del base path; el agente debe moverlo al `recursos/` del proyecto activo.
- `OMNIVOICE_MCP_BASE_PATH` es la frontera de seguridad: `transcribe`/`clone_voice` solo leen dentro de ella.

## Qué queda pendiente (no verificado hoy)

- **Doblaje de video** (Fase 3 aplazada): pipeline extracción → separación vocal → ASR → traducción → TTS por
  segmento → mezcla. En 16 GB hará ciclos de descarga/recarga TTS↔ASR; medir antes de prometer nada.
- `design_voice` (voz por descripción) y diarización: expuestas en la app, no probadas.
- Engines alternativos con licencia comercial permisiva (CosyVoice 3, IndexTTS 2.5) para piezas de SYSCOM:
  OmniVoice es CC-BY-NC; si la clonación se vuelve de producción, evaluar esos engines primero.

## Enlaces

- `[[AGENT]]` — reglas del toolkit (§5 voz, §11 privacidad de muestras)
- `[[Preferencias-Usuario]]` — config concreta de esta máquina (perfil clonado, binding, rutas)
- `[[Lecciones-2026-09-24-narracion-tts]]` — TTS por OpenRouter (la ruta nube, sigue siendo el default)
- `[[Home]]` — índice de la bóveda
