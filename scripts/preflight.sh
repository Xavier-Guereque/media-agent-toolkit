#!/usr/bin/env zsh
# preflight.sh — verifica (e instala) el software declarado en config.json > software.
# Uso: zsh scripts/preflight.sh
# Sale 0 si todo el software requerido queda disponible; 1 en caso contrario.
# Detalles en docs/Preflight-Software.md

set -u

SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h}"
CONFIG="$REPO_ROOT/config.json"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: no se encontró $CONFIG" >&2
  exit 1
fi

# jq es requisito del propio script: instalarlo primero si falta.
if ! command -v jq >/dev/null 2>&1; then
  echo "jq no está instalado; instalando con: brew install jq"
  if command -v brew >/dev/null 2>&1 && brew install jq; then
    echo "  INSTALADO jq"
  else
    echo "ERROR: no se pudo instalar jq (¿Homebrew disponible?)." >&2
    exit 1
  fi
fi

fail=0

# Allowlist fija de instalación: binario -> único comando permitido.
# config.json declara QUÉ se necesita; este script decide CÓMO se instala.
# Un valor de config.json que no coincida exactamente se RECHAZA (nunca se ejecuta).
typeset -A INSTALACION_PERMITIDA=(
  ffmpeg     "brew install ffmpeg"
  python3    "brew install python"
  jq         "brew install jq"
  curl       "sistema (macOS)"
  node       "manual (>=20; nvm o nodejs.org)"
  promo-deps "npm ci --prefix promo"
)

# Node >= 20 para el motor promo. Mismo orden que scripts/comun.py > buscar_node:
# config.json promo.node (si no es "auto") → PATH → shell de login (el Node de nvm/Homebrew
# solo aparece ahí cuando el script corre desde un agente) → nvm más reciente.
# Imprime la ruta del binario; sale 1 si no hay uno válido. Node nunca se instala solo.
node_bin() {
  local cand v cfg
  local -a cands nvm
  cfg="$(jq -r '.promo.node // "auto"' "$CONFIG" 2>/dev/null)"
  [[ -n "$cfg" && "$cfg" != "auto" ]] && cands+=("${~cfg}")
  cand="$(command -v node 2>/dev/null)" && cands+=("$cand")
  cand="$(zsh -lc 'command -v node' 2>/dev/null </dev/null | tail -n 1)"
  [[ "$cand" == /* ]] && cands+=("$cand")
  nvm=( ~/.nvm/versions/node/v*/bin/node(N) )
  nvm=( ${(On)nvm} )                       # orden numérico descendente: la versión más alta primero
  (( ${#nvm} )) && cands+=("${nvm[1]}")
  for cand in "${cands[@]}"; do
    [[ -x "$cand" ]] || continue
    v="$("$cand" --version 2>/dev/null)"
    v="${v#v}"
    v="${v%%.*}"
    if [[ "$v" == <-> ]] && (( v >= 20 )); then
      print -r -- "$cand"
      return 0
    fi
  done
  return 1
}

# Carpeta del navegador de respaldo del motor promo (Chromium headless shell de Playwright; el motor
# usa primero el Google Chrome del sistema, ver promo/lib/navegador.mjs).
# La revisión sale de promo/node_modules/playwright-core/browsers.json (1234 si no está).
navegador_dir() {
  local rev="" bj="$REPO_ROOT/promo/node_modules/playwright-core/browsers.json"
  [[ -f "$bj" ]] && rev="$(jq -r '.browsers[] | select(.name=="chromium-headless-shell") | .revision' "$bj" 2>/dev/null)"
  [[ -z "$rev" || "$rev" == null ]] && rev=1234
  # Caché por defecto de Playwright: macOS ~/Library/Caches, Linux ~/.cache (o $XDG_CACHE_HOME).
  local cache="$HOME/Library/Caches/ms-playwright"
  [[ "$(uname -s)" == Linux ]] && cache="${XDG_CACHE_HOME:-$HOME/.cache}/ms-playwright"
  print -r -- "${PLAYWRIGHT_BROWSERS_PATH:-$cache}/chromium_headless_shell-$rev"
}

promo_deps_ok() {
  [[ -d "$REPO_ROOT/promo/node_modules/playwright-core" && -d "$(navegador_dir)" ]]
}

# Motor Remotion (OPCIONAL, skill remotion-video): dependencias npm + el Chrome Headless Shell que Remotion
# guarda en node_modules/.remotion. Solo se avisa; se instala con config.json > software.opcional.remotion-deps.
remotion_deps_ok() {
  [[ -d "$REPO_ROOT/remotion/node_modules/@remotion/cli" && -d "$REPO_ROOT/remotion/node_modules/.remotion/chrome-headless-shell" ]]
}

# Verificación de disponibilidad. Casos especiales: faster-whisper es una
# librería de Python SIN CLI propio — se verifica importando el módulo (en el python3 del
# sistema o en el venv ~/.venvs/whisper / $WHISPER_PYTHON que usan subtitulos.py y doblar.py); node exige
# versión >= 20; promo-deps son las dependencias npm del motor promo + su navegador; remotion-deps (opcional)
# las del motor Remotion + su Chrome Headless Shell.
disponible() {
  case "$1" in
    faster-whisper) python3 -c "import faster_whisper" >/dev/null 2>&1 \
        || "${WHISPER_PYTHON:-$HOME/.venvs/whisper/bin/python}" -c "import faster_whisper" >/dev/null 2>&1 ;;
    node) node_bin >/dev/null ;;
    promo-deps) promo_deps_ok ;;
    remotion-deps) remotion_deps_ok ;;
    *) command -v "$1" >/dev/null 2>&1 ;;
  esac
}

instalar() {
  local bin="$1" cmd="$2"
  local permitido="${INSTALACION_PERMITIDA[$bin]:-}"

  if [[ -z "$permitido" ]]; then
    echo "  AVISO   $bin no tiene instalación permitida en este script; instálalo manualmente."
    return 1
  fi
  if [[ "$cmd" != "$permitido" ]]; then
    echo "  ERROR   el comando declarado para $bin en config.json no coincide con la allowlist:"
    echo "            config.json: $cmd"
    echo "            allowlist:   $permitido"
    echo "          No se ejecuta nada. Corrige config.json o instala manualmente."
    return 1
  fi
  case "$permitido" in
    sistema*)
      echo "  AVISO   $bin debería venir con el sistema ($permitido); instálalo manualmente."
      return 1
      ;;
    manual*)
      echo "  AVISO   $bin se instala manualmente: ${permitido#manual }. Luego repite el preflight."
      return 1
      ;;
    "npm ci --prefix promo")
      local nb nodedir
      if ! nb="$(node_bin)"; then
        echo "  ERROR   $bin necesita Node >= 20 (instálalo primero)."
        return 1
      fi
      nodedir="${nb:h}"
      echo "  INSTALANDO $bin ($permitido)"
      # npm/npx del mismo Node, y ese Node primero en PATH (el shebang de npm usa `env node`).
      if ! ( cd "$REPO_ROOT" && PATH="$nodedir:$PATH" "$nodedir/npm" ci --prefix promo ); then
        echo "  ERROR   falló: $permitido"
        return 1
      fi
      if [[ ! -d "$(navegador_dir)" ]]; then
        echo "  INSTALANDO navegador (npx --prefix promo playwright-core install chromium-headless-shell)"
        if ! ( cd "$REPO_ROOT" && PATH="$nodedir:$PATH" "$nodedir/npx" --prefix promo \
               playwright-core install chromium-headless-shell ); then
          echo "  ERROR   falló la descarga del navegador"
          return 1
        fi
      fi
      if promo_deps_ok; then
        echo "  INSTALADO $bin"
        return 0
      fi
      echo "  ERROR   $bin sigue incompleto ($(navegador_dir))"
      return 1
      ;;
    brew\ install\ *)
      if ! command -v brew >/dev/null 2>&1; then
        echo "  ERROR   Homebrew no está instalado; no se pudo instalar $bin"
        return 1
      fi
      echo "  INSTALANDO $bin ($permitido)"
      brew install "${permitido#brew install }" \
        && { echo "  INSTALADO $bin"; return 0; } \
        || { echo "  ERROR   falló: $permitido"; return 1; }
      ;;
    *)
      echo "  ERROR   la allowlist no define cómo ejecutar: $permitido"
      return 1
      ;;
  esac
}

echo "== Software requerido =="
local bin cmd
for bin in ${(f)"$(jq -r '.software.requerido | keys[]' "$CONFIG")"}; do
  cmd="$(jq -r --arg b "$bin" '.software.requerido[$b]' "$CONFIG")"
  if disponible "$bin"; then
    echo "  OK      $bin"
  else
    echo "  FALTA   $bin → $cmd"
    instalar "$bin" "$cmd" || fail=1
  fi
done

echo ""
echo "== Software opcional (solo aviso, no se instala) =="
for bin in ${(f)"$(jq -r '.software.opcional | keys[]' "$CONFIG")"}; do
  cmd="$(jq -r --arg b "$bin" '.software.opcional[$b]' "$CONFIG")"
  if disponible "$bin"; then
    echo "  OK      $bin"
  else
    echo "  AVISO   $bin no instalado (opcional). Para instalarlo: $cmd"
  fi
done

echo ""
if (( fail == 0 )); then
  echo "Preflight OK: todo el software requerido está disponible."
else
  echo "Preflight FALLÓ: faltan componentes requeridos (ver arriba)." >&2
fi
exit $fail
