---
tags: [lecciones, windows, ffmpeg, portabilidad, preflight]
fecha_modificacion: 2026-11-10
estado: activo
---

# Lecciones — el toolkit en Windows 11 (y FFmpeg 8+)

Primera instalación del toolkit en Windows 11 (Python 3.14, Node 24, FFmpeg 9.0.2 de gyan.dev vía winget).
Antes de los arreglos fallaban 31 de 232 pruebas de Python y 1 de 27 del motor promo; después pasan todas
(232 + 27), con y sin `PYTHONUTF8=1`. Los cuadros del ejemplo de oro del motor promo salen iguales a las
golden (SSIM) con el Google Chrome de Windows, sin tocar el motor.

## Instalación verificada (2026-11-10)

```powershell
winget install --id Gyan.FFmpeg -e      # full_build: libass, xfade, loudnorm, drawtext, sidechaincompress, afftdn
winget install --id jqlang.jq -e
python -m pip install --user pillow
npm ci --prefix promo                   # usa el Chrome del sistema (channel 'chrome' de Playwright)
copy .env.example .env                  # y pegar OPENROUTER_API_KEY
```

winget agrega FFmpeg y jq al PATH del **usuario**: las terminales (y la app de Claude) abiertas antes de la
instalación no los ven hasta reiniciarlas. En una sesión ya abierta:
`$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`.

## Lo que se rompía y por qué

1. **`-filter_complex_script` ya no existe en FFmpeg 8+** (no es de Windows: también pasará en una Mac que
   actualice FFmpeg). Error: `Unrecognized option 'filter_complex_script'` / `Error splitting the argument list`.
   Se cambia por `-/filter_complex <archivo>` (sintaxis `-/opción` para leer el valor de un archivo, desde FFmpeg
   7.0, así que funciona también con el 7.1 de macOS). Era la causa de 14 fallas en cascada en `narrar.py` →
   `curso.py voz/componer/render`.
2. **`os.kill(pid, 0)` en Windows MATA el proceso** (llama a `TerminateProcess`) en lugar de comprobar si vive.
   `promo.py estado` y `remotion.py estudio` lo usaban para saber si el render/Studio seguía corriendo: en Windows
   lo habrían terminado. Ahora `comun.pid_vivo(pid)` usa `OpenProcess` + `GetExitCodeProcess` en Windows.
   `os.killpg` no existe en Windows y `start_new_session` no aplica: `comun.terminar_arbol(pid)` usa
   `taskkill /PID … /T /F` ahí y el grupo de procesos en macOS/Linux.
3. **Codificación cp1252.** En Windows, `open()` sin `encoding=` y `subprocess.run(..., text=True)` usan la
   página de códigos del sistema (cp1252): los JSON/brief con acentos daban `UnicodeDecodeError` o mojibake
   (`Ã³`, y `mÃƒÂ¡x` cuando se encadenan dos decodificaciones). Se agregó `encoding="utf-8"` a todos los `open()`
   de texto, `encoding="utf-8", errors="replace"` a todos los `text=True`, y `comun.py` reconfigura
   stdout/stderr a UTF-8 en Windows para que los scripts que se llaman entre sí hablen igual.
4. **Fuentes de macOS fijas.** `pantalla.py` usaba `/System/Library/Fonts/Supplemental/Arial Bold.ttf`; ahora
   elige la primera que exista (macOS → `%WINDIR%\Fonts\arialbd.ttf` → DejaVu de Linux). `lienzo.py` ya tenía
   la cadena de respaldo.
5. **Venvs.** `~/.venvs/<n>/bin/python` es `~/.venvs/<n>/Scripts/python.exe` en Windows:
   `comun.python_de_venv("whisper")` (lo usan `doblar.py` y `narrar.py`).
6. **Candado de `fetch_audio.py`:** usaba solo `fcntl` (no existe en Windows) y quedaba sin candado entre
   procesos; ahora usa `msvcrt.locking` en Windows.
7. **Rutas en pruebas y validaciones.** `os.path.join("/r", "voz/1.wav")` da `/r\voz/1.wav` en Windows (válido
   para abrir, distinto al comparar cadenas); `import()` de Node exige `file://` (`pathToFileURL`), no
   `C:\…`; y `remotion.py validar` revisaba solo `os.sep` en `salida`, así que `carpeta/x.mp4` pasaba en
   Windows: ahora rechaza `/` y `\` en todas las plataformas.

## Pendiente

- `scripts/preflight.sh` depende de zsh y Homebrew: en Windows no corre. Mientras no haya un `preflight.ps1`,
  verificar a mano (`ffmpeg -version`, `jq --version`, `node --version` ≥ 20, `promo/node_modules`).
- Sin probar en Windows (no tienen pruebas que lo ejerciten aquí): `faster-whisper`, `tesseract`/`yt-dlp`,
  `reemplazar_personaje.py` (numpy/OpenCV), `remotion-deps` y el render real de Remotion, VoiceStudio.
- `subtitulos.py` quema con la familia "Helvetica Neue"; en Windows libass cae a la fuente de respaldo (Arial):
  no se verificó el aspecto contra la referencia de macOS.

## Enlaces

- [[AGENT]] — §3 preflight y §3b Windows
- [[Preflight-Software]]
- [[Home]]
