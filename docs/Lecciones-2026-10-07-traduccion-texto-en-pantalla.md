---
tags: [lecciones, video, traduccion, ocr, ffmpeg, pantalla]
fecha_modificacion: 2026-10-07
estado: activo
---

# Lecciones — Traducir el texto sobrepuesto de un video existente (2026-10-07)

Pieza: `proyectos/acuity-sensorswitch_07102026` — video de YouTube de Acuity (34 s, 1920×1080,
25 fps, solo animación y música) al que se le **reemplazó el texto en pantalla** por su versión en
español. No se agregaron subtítulos: se sobre-escribió el texto que ya venía incrustado.
Herramienta nueva: `scripts/pantalla.py` (skill `traducir-texto-en-pantalla` de [[SKILL]]).

## Resultado

6 rótulos traducidos, música y duración intactas (33.674 s → 33.680 s; `volumedetect` idéntico:
mean −29.1 dB / max −16.8 dB). Costo de APIs de generación: **0 USD** (todo local: yt-dlp,
tesseract, Pillow, FFmpeg); el costo total fue solo la sesión del agente (~0.20 USD).

## Pipeline que funcionó

1. **Descargar** con `yt-dlp` (no viene instalado: `uv tool install yt-dlp` o `brew install yt-dlp`).
2. **Detectar los rótulos sin gastar visión**: muestrear el video a 10 fps y correr
   `tesseract <png> - --psm 11 tsv`. Agrupar los fotogramas con texto en rótulos (por hueco de
   tiempo **y** por continuidad del bloque) y sacar ventana, texto y geometría. El script lo hace
   en un paso: `python3 scripts/pantalla.py detectar <video> --json caps.json`.
3. **Traducir** en el JSON (poner `lineas` por rótulo; borrar los que sean logotipos).
4. **Redibujar y componer**: `python3 scripts/pantalla.py generar caps.json --render`. Genera un
   PNG RGBA por rótulo (pastilla blanca con el texto nuevo) y encadena `overlay` con `fade` de alfa.
5. **Verificar** con OCR de los fotogramas de frontera + `volumedetect` + duración.

## Gotchas verificados (el valor de esta bitácora)

- **El fundido tiene que caer FUERA de la vida del texto original.** El fundido de entrada debe
  **terminar** en el inicio del rótulo y el de salida **empezar** en su fin. Si la pastilla se funde
  *durante* el mismo tiempo en que el texto original está visible, se ve el inglés por debajo
  (medido: a t=23.20 se leía «ListReady in second s»).
- **El OCR detecta el rótulo cuando ya es legible**, así que el original empieza a aparecer entre
  0.1 y 0.4 s antes de la primera detección. Por eso `generar` adelanta el «opaco desde»
  (`margen_inicio`, 0.15 s por defecto) **y** conviene revisar la tabla de `detectar`: en esta pieza
  el rótulo «Get it fast» salió con `inicio=26.80` cuando el original arrancaba en ~26.40.
- **Etapas de revelado (texto que aparece palabra por palabra):** hay que ponerlas en secuencia,
  sin fundido ni solape entre etapas. Con fundido cruzado y pastilla fija se ven **los dos textos
  duplicados** (medido: «ConviertGonviette de obra» a t=30.10). La pastilla es idéntica entre
  etapas, así que el relevo se hace en un mismo instante sin que se note.
- **`tesseract` pierde texto fino** («Ready in **seconds**» se leyó solo «Ready»). El bbox del texto
  queda corto y la pastilla nueva no cubriría lo que falta. Cota mejor: el **bbox de la pastilla**,
  que se aísla con `min(R,G,B) > 246` porque estas piezas tienen fondo claro pero **no blanco**
  (p. ej. 239,245,255); se expande desde el centro del texto mientras las columnas/filas sigan
  blancas, y así un objeto blanco vecino (el sensor, un círculo) no estira el recuadro.
- **Pillow no está en el `python3` del sistema** (CommandLineTools de macOS). El script se
  re-ejecuta solo con un intérprete que sí lo tenga (`/opt/homebrew/bin/python3`). Para generar PNG
  a mano, usar ese intérprete o un venv con `pip install pillow`.
- **La fuente:** las woff2 de `promo/temas/neutro/fuentes` no cargan tal cual (libass sin brotli,
  y Pillow necesita ttf/otf). Convertir con `scripts/pantalla.py fuente <in.woff2> <out.ttf> --peso 700`
  (necesita `fonttools`+`brotli`; se corre con `uv run --with fonttools --with brotli python …`).
- **YouTube puede entregar vp9+opus dentro de un .mp4.** Al re-codificar la salida a h264+AAC
  (estándar del toolkit) la música se conserva: comprobarlo con `volumedetect` antes/después
  (deben ser idénticos) y con la duración del contenedor.
- **Los logotipos de marca no se traducen** (`SensorSwitch™`, `CONTRACTOR SELECT`). Ojo: el logo en
  blanco con texto negro se detecta como si fuera un rótulo; se borra del spec.
- **Rutas del spec** (`entrada`, `fuente`, `salida`) se resuelven relativas a la carpeta del JSON.
- **Revisar el diseño en local antes de renderizar:** `generar` sin `--render` imprime el comando
  ffmpeg, y el chequeo barato es el OCR de los fotogramas de frontera (ini−0.1, ini, fin, fin+0.1,
  fin+0.2 y los huecos entre rótulos). La única palabra inglesa legítima es la marca.

## Cómo se verificó

- OCR de 26 fotogramas de frontera del MP4 final: **cero restos de inglés** (solo la marca).
- Recortes ampliados revisados con visión en los puntos dudosos (23.15, 23.25, 24.90, 26.45).
- `ffprobe` duración 33.680 s (original 33.674 s) y `volumedetect` idéntico.
