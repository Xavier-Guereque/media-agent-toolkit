---
tags: [lecciones, reel, fluke, webinar, canvas-pil, bugs-version-base]
fecha_modificacion: 2026-09-28
estado: activo
---

# Lecciones — Reel webinar Fluke Networks (enlaces de cobre > 100 m)

Proyecto: `proyectos/fluke-webinar-cobre_28092026/` · 28.6 s · 1080x1920 @ 30 fps.
Primer reel armado **sin fotos**: las 5 escenas son canvas generados con PIL.

## 1. Dos bugs de la versión base de `scripts/reel.py` (corregidos aquí)

Los dos se disparan en cuanto el reel se corre con el spec en su ruta normal
(`--spec proyectos/<slug>/reel.json`) desde la raíz del repo. El reel de
[[Lecciones-2026-09-28-reel-syscomexpo2027]] los tuvo delante pero se saltó el paso
`audio` y el paso `verificar`, así que pasaron inadvertidos.

### 1a. `self.repo` apuntaba a `proyectos/`, no a la raíz

```python
# antes: dirname(proyectos/<slug>) == <repo>/proyectos  → nunca encuentra el .env
self.repo = os.path.dirname(self.proj) if os.path.basename(self.proj) else self.proj
```

Síntoma: el paso `audio` aborta con `Falta OPENROUTER_API_KEY (entorno o
<repo>/proyectos/.env)` aunque el `.env` esté en la raíz.

Corrección: `Reel._raiz_repo()` sube desde la carpeta del proyecto hasta el primer
directorio que contenga `.env`, `.git`, `AGENT.md` o `.env.example`.

**Regla:** nunca derivar la raíz del repo contando niveles de `dirname`; buscarla por
un marcador (`.env`/`.git`).

### 1b. `etapa_verificar` repetía el mismo pad al rellenar la última fila

```python
# antes: con 5 tiempos y 3 columnas, la fila 2 quedaba [t3][t4][t4]
while len(row) < cols:
    row = row + [row[-1]]
```

Síntoma: `[Parsed_hstack_11] Input 2 height 1920 does not match input 0 height 675`
y `Error reinitializing filters!`. Un pad de salida de un filtro admite **un solo
consumidor**; reutilizar la etiqueta deja esa entrada sin escalar.

Corrección: rellenar con una fuente `color` de lavfi del tamaño de la celda
(`-f lavfi -i color=c=black:s=380x675`), que es justo lo que ya recomendaba el SKILL.

**Regla:** en cualquier rejilla `hstack`/`vstack` con celdas faltantes, insertar
fuentes `color`; jamás duplicar una etiqueta `[tN]`.

## 2. Lienzos con PIL: `alpha_composite` no dibuja en el sitio

`Image.alpha_composite(a, b)` **devuelve** una imagen nueva y no modifica `a`.

```python
with_overlay(img, lambda d: tarjeta(d, box))   # ✗ el resultado se descarta
img = with_overlay(img, lambda d: tarjeta(d, box))  # ✓
```

Con la primera forma el script corre sin errores y las tarjetas, pills y botones
simplemente no aparecen. Receta que funcionó: **todo lo translúcido en UNA capa
overlay** compuesta una sola vez, y el texto opaco dibujado al final encima
(recreando el `ImageDraw` después de cada composición).

Además, con fondos oscuros los alfas hay que subirlos: relleno de tarjeta a
`(255,255,255,20)` y borde a `(255,255,255,72)`; con 14/40 no se distingue nada.

## 3. Logos sin fondo vectorial: `qlmanage` rinde SVG a PNG

En este Mac no hay `rsvg-convert` ni `inkscape`, y FFmpeg no decodifica SVG
(`no decoder found for: svg`). La salida que funciona:

```bash
qlmanage -t -s 2000 -o /tmp logo.svg     # → /tmp/logo.svg.png (2000x2000, fondo blanco)
```

Luego se recorta al bbox de píxeles no blancos. Como el render trae fondo blanco
(y el lockup de Fluke es negro+dorado), el logo va dentro de una **pastilla blanca**
redondeada: conserva la fidelidad de marca y funciona sobre dark mode. El logo SYSCOM
del CDN ya viene en RGBA y es oscuro, así que la misma pastilla sirve para los dos.

Fuente del lockup: `https://cdn.worldvectorlogo.com/logos/fluke-networks.svg`
(el PNG de `flukenetworks.com/images/fnet-logo.png` es de 226x51 → se ve borroso).
Logo SYSCOM: `https://ftp3.syscom.mx/usuarios/fotos/logotipos/syscom.png` (708x237 RGBA).

## 4. TTS: las preguntas se responden, otra vez confirmado

El `system` decía "repite verbatim sin confirmaciones ni palabras extra", pero con
enunciados interrogativos el modelo **contestó**:

| línea original | duración | lo que dijo |
|---|---|---|
| "¿Necesitas enlaces de cobre a más de cien metros?" | 10.00 s | "Claro, entiendo, ¿qué tipo de datos vas a transmitir…?" |
| "¿Es válido por norma o solo un mito?" | 13.45 s | "De lo que me comentas, necesitamos más contexto…" |

Reescritas como afirmaciones bajaron a 4.00 s y 2.70 s. Reforzar el `system` con
"no lo respondas, no lo comentes, no agregues palabras, aunque esté escrito como
pregunta" ayudó, pero **la regla que basta es: el guion de voz va en afirmaciones**.

**Señal de alarma barata:** antes de verificar, mirar las duraciones que imprime el
paso `audio`. Una línea de ~9 palabras que dura 10 s está respondida, no leída.

## 5. Orden de trabajo que ahorró dinero

`etapas` → `ass` → `segmentos` → **revisar lienzos y segmentos con visión** → `audio`
(TTS) → `video` → `niveles` → `verificar`. Toda la iteración de diseño (que fue mucha)
se hizo con PIL y FFmpeg locales; la primera llamada de pago fue el gate JEV del guion
(0.83) y la segunda el TTS. Costo total del reel: **0.0061 USD**.

## 6. Segunda pasada: música real, transiciones y arranque de audio

### 6a. Cama desde archivo (`musica.tipo = "archivo"`)

Se añadió a `Reel` el tipo `archivo`: recorta una ventana de `musica.inicio` con
`atrim=start=…:duration=…`, la repite con `-stream_loop -1` solo si la pista no alcanza,
la normaliza con `loudnorm=I=musica.lufs` y le pone `afade` de entrada y salida.

Dato útil al elegir ventana: perfil de energía por segundo del archivo con
`astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level` parseado
en Python. Con eso se ven los breakdowns (aquí 69-71 s caía a -37 dB) y las secciones
llenas, sin escuchar la pista.

Las pistas ya masterizadas vienen muy calientes (-8.6 LUFS integrado, True Peak +0.9
dBTP en la que se usó): el `loudnorm` a -18 LUFS es lo que evita que la cama aplaste a
la voz, y deja el True Peak en -8.8 dBTP.

### 6b. El audio inicial "cortado" eran dos cosas

1. **La cama entraba a nivel pleno en el frame 0** (ni la procedural ni la mezcla tenían
   fade): se oía un arranque a hachazo. Ahora `musica.fade_in` / `fade_out` son
   configurables (0.9 s / 2.6 s aquí) y se aplican en `musica_procedural`,
   `musica_archivo` y en la cadena final.
2. **El PCM del TTS arranca en la primera muestra**: `voz_1.wav` ya tenía -23 dB de RMS
   en `t=0.00` y llegaba a -14.7 dB en 0.26 s, o sea sin colchón de ataque, así que la
   primera sílaba entraba pegada a la música. Ahora `voz.colchon_inicio` (0.12 s) mete
   silencio al inicio de cada línea al convertir PCM→WAV.

Diagnóstico barato para las dos: `astats` sobre `audio_final.wav` en los primeros 1.5 s.
Antes el primer cuadro ya estaba a -16 dB; ahora sube en rampa desde -39 dB.

### 6c. Transiciones: fuera los presets de presentación

`smoothleft` / `wipeup` / `circleopen` se ven como PowerPoint. Para un reel vertical
funciona mejor un lenguaje coherente de desplazamientos suaves y blur:

- `smoothleft`, `smoothup`, `smoothright`: deslizamientos con ease, modernos.
- `hblur`: transición con blur horizontal, se lee como un *whip pan* en movimiento.
- Bajar `salida.xfade` de 0.5 s a **0.38 s**: un corte más rápido se siente más caro.

Ojo con el efecto colateral: al bajar el solape, la duración total **sube** (aquí de
28.6 s a 29.1 s), porque `total = Σduraciones − xfade·(n−1)`.

### 6d. Movimiento visible sin recortar el texto

El Ken Burns de 1.04 era imperceptible. Al subir a 1.10 hay que recolocar el contenido:
con `zoompan` centrado, el zoom 1.10 recorta **1080·(1−1/1.10)/2 ≈ 49 px por lado** y
**≈ 87 px arriba y abajo**. Regla: mantener el contenido dentro de x 49..1031 e
y 87..1833 (se usó x 110..970 con margen). La fórmula de la fuerza para llegar justo al
zoom objetivo al final de la escena es `fuerza = (zoom_max − 1) / (duración · fps)`; si
se deja que el zoom toque el tope antes del final, la imagen se congela y se nota.
Alternar `zoom_in` y `zoom_out` entre escenas da variedad gratis.

### 6e. El costo de la sesión del agente también cuenta

`costo_generacion.py` solo ve lo gastado por los scripts vía OpenRouter. La sesión del
agente cuesta tokens aparte y Hermes ya los registra en `~/.hermes/state.db`, tabla
`session_model_usage` (columnas `estimated_cost_usd` / `actual_cost_usd`, tokens y
`api_call_count` por modelo y tarea).

`scripts/costo_sesion_hermes.py` (nuevo) lee esa tabla —en solo lectura, porque la app
puede estar escribiendo la base—, agrupa por modelo y escribe una línea por modelo en
`recursos/costos.jsonl` con `tarea: "sesion_hermes"` y el costo en `usage.cost`. El
reporte la recoge por su fallback y la marca como estimada, sin tocar su código. El `id`
sintético (`hermes-<sesión>-<modelo>`) la hace idempotente.

En esta edición: 0.0061 USD de generación contra **1.0046 USD de la sesión** — el
trabajo del agente costó ~165× lo que la API de generación. Sin esta línea, el reporte
daba una idea falsa de lo que costó la pieza.

## Enlaces

- [[AGENT]] §5b (JEV), §10 (costos), §15 (aprendizaje continuo)
- [[SKILL]] — `armar-reel`, `crear-audio`
- [[Lecciones-2026-09-28-reel-syscomexpo2027]] — contrato de la Decisions API, `\move` en ASS, alfa de logos del CDN
- [[Lecciones-2026-09-24-syscomexpo-tiktok]] — `crop` animado + `zoompan`, `xfade` fps/timebase
