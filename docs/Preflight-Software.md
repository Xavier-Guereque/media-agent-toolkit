---
tags: [preflight, software, instalacion, scripts, node, promo, remotion]
fecha_modificacion: 2026-10-31
estado: activo
---

# Preflight de software

Verificación (e instalación) del software que el toolkit necesita, declarado en `config.json > software`. Regla operativa en [[AGENT]] §3: se corre **antes de ejecutar** cualquier edición.

## Cómo correrlo

```bash
zsh scripts/preflight.sh
```

- Sale `0` si todo el software **requerido** queda disponible; `1` en caso contrario.
- Los requeridos faltantes se **instalan solos** y el script imprime qué instaló.
- **Allowlist fija:** el script solo ejecuta comandos de su propia tabla cerrada (`scripts/preflight.sh > INSTALACION_PERMITIDA`). Si el comando declarado en `config.json` no coincide exactamente, lo rechaza y lo reporta — nunca ejecuta strings arbitrarios del config.
- Los **opcionales** solo avisan si faltan (nunca se instalan automáticamente).

## Tabla de software

### Requerido

| Binario | Chequeo | Instalación (`config.json > software.requerido`) |
|---|---|---|
| `ffmpeg` | `command -v ffmpeg` | `brew install ffmpeg` |
| `python3` | `command -v python3` | `brew install python` |
| `curl` | `command -v curl` | `sistema (macOS)` — viene con el OS; si falta, el script solo avisa |
| `jq` | `command -v jq` | `brew install jq` (el propio script lo instala primero si falta, porque lo usa para leer `config.json`) |
| `node` | Node **≥ 20**, buscado como `scripts/comun.py > buscar_node`: `config.json > promo.node` (si no es `"auto"`) → `PATH` → shell de login (`zsh -lc 'command -v node'`, donde aparece el Node de nvm/Homebrew cuando el script corre desde un agente) → el `~/.nvm/versions/node/v*/bin/node` más reciente | `manual (>=20; nvm o nodejs.org)` — **nunca se instala solo**: el script avisa y el preflight falla hasta que el usuario lo instale |
| `promo-deps` | `promo/node_modules/playwright-core` existe **y** el navegador `~/Library/Caches/ms-playwright/chromium_headless_shell-<rev>` existe (`<rev>` sale de `promo/node_modules/playwright-core/browsers.json`; respeta `PLAYWRIGHT_BROWSERS_PATH`) | `npm ci --prefix promo` (desde la raíz del repo, con el npm del mismo Node ≥ 20) y, solo si falta el navegador, `npx --prefix promo playwright-core install chromium-headless-shell` (~95 MB) |

### Opcional (solo aviso)

| Binario | Chequeo | Instalación sugerida |
|---|---|---|
| `faster-whisper` | `python3 -c "import faster_whisper"` (librería sin CLI propio) | `pip install faster-whisper` |
| `auto-editor` | `command -v auto-editor` | `pip install auto-editor` |
| `deepFilter` | `command -v deepFilter` | `pip install deepfilternet` |
| `yt-dlp` | `command -v yt-dlp` | `uv tool install yt-dlp` (o `brew install yt-dlp`) |
| `tesseract` | `command -v tesseract` | `brew install tesseract` |
| `voicestudio` | `command -v voicestudio` (app local; backend en `127.0.0.1:3900`) | `curl -fsSL https://voicestudio.sh/install \| sh` — ver [[Lecciones-2026-09-30-voicestudio-mcp]] |
| `remotion-deps` | `remotion/node_modules/@remotion/cli` **y** `remotion/node_modules/.remotion/chrome-headless-shell` existen (Remotion guarda ahí su navegador) | `npm ci --prefix remotion && npx --prefix remotion remotion browser ensure` (~850 MB, ~20 s; motor opcional de [[Motor-Remotion]]) |

## Salida de ejemplo

```
== Software requerido ==
  OK      curl
  OK      ffmpeg
  OK      jq
  OK      node
  OK      promo-deps
  OK      python3

== Software opcional (solo aviso, no se instala) ==
  AVISO   auto-editor no instalado (opcional). Para instalarlo: pip install auto-editor
  AVISO   deepFilter no instalado (opcional). Para instalarlo: pip install deepfilternet
  AVISO   faster-whisper no instalado (opcional). Para instalarlo: pip install faster-whisper

Preflight OK: todo el software requerido está disponible.
```

## Notas

- La primera corrida puede tardar si brew/pip instalan paquetes; se reporta lo instalado.
- Si un requerido no queda disponible, el agente se **detiene** y pide instrucción (no sigue con la edición).
- Para agregar software **requerido**: editar `config.json > software`, la allowlist `INSTALACION_PERMITIDA` en `scripts/preflight.sh` y esta tabla. Para opcionales basta `config.json` y esta tabla.
- **Tipos de instalación de la allowlist:** `brew install …` (se ejecuta), `sistema …` y `manual …` (solo avisan y el preflight falla), y la rama exacta `npm ci --prefix promo` del motor promo. Cualquier otro valor se rechaza sin ejecutar nada.
- `remotion-deps` es **opcional**: `scripts/remotion.py` sale con código 3 si falta y dice el comando; si falta solo el navegador, Remotion lo descarga en el primer render (lento) y `validar` lo avisa (`W-REMOTION-NAVEGADOR`).
- `node` y `promo-deps` los usa el [[Motor-Promo]] (`scripts/promo.py` → `node promo/motor.mjs`). Si falta Node ≥ 20, `promo.py` sale con código 3 (entorno) y el mismo arreglo.

## Enlaces

- [[AGENT]] — sección 3 (preflight obligatorio)
- [[Motor-Promo]] — consumidor de `node` y `promo-deps`
- [[Motor-Remotion]] — consumidor opcional de `node` y `remotion-deps`
- [[Costos-y-Avance]] — otras automatizaciones de la edición
- [[Home]] — índice de la bóveda
