---
tags: [lecciones, reel, tts, qr, musica, costos, fluke]
fecha_modificacion: 2026-09-28
estado: activo
---

# Lecciones — 2026-09-28 · Reel de la publicación del webinar Fluke Networks

Pieza: `proyectos/fluke-webinar-post_28092026/fluke-webinar-post.mp4` (1080x1920 @30 fps,
29.5 s, 6.2 MB). Promueve la **publicación** en la que Bryan Vega (Fluke Networks) invita al
webinar *"Enlaces de cobre más allá de los 100 metros: mitos y realidades"* (1 de octubre 2026,
09:00–10:00 GMT-6, Microsoft Teams, registro sin costo).

Es el segundo reel del **mismo webinar**: el primero
(`[[Lecciones-2026-09-28-reel-fluke-webinar-cobre]]`) invitaba al evento; este promueve el post,
así que el ángulo son las **4 preguntas** del post y el **enlace de registro**.

---

## 1. El TTS no solo responde preguntas: también "responde" listas con dos puntos

**Síntoma:** la línea 2 del guion (`"Cuatro dudas: necesidad, norma, pruebas y reporte."`, 7
palabras, ~3.2 s esperados) salió en **15.57 s**. La verificación con `verificar_voz.py` la
transcribió así:

> "Entendido," … "Voy a plantear cada una de ellas a fondo de forma clara. Vamos con la primera,"
> … "Luego pasamos a la norma, las pruebas, y finalmente el reporte."

El modelo leyó el fragmento nominal como una **instrucción** ("cuatro dudas… plántalas") y
desarrolló el webinar en voz alta.

**Regla (amplía la de `[[SKILL]]` sobre preguntas):** no basta con evitar interrogantes. Cada línea
del guion debe ser una **oración con sujeto y verbo conjugado**; los **fragmentos nominales con dos
puntos** ("Cuatro dudas: A, B y C.") también disparan una respuesta. Reescritura aplicada:
`"Las dudas más comunes son norma, pruebas y reporte."` → 4.57 s.

**Señal de alarma barata:** ~0.45 s por palabra es lo normal; **por encima de 0.6 s/palabra** hay
palabras de más. Regenerar solo la línea afectada (borrar `voz_N.wav` y `voz_N.pcm` con
`voz.regenerar=false`) cuesta centavos en vez de repetir las cinco.

**El gate de JEV no lo detectó.** El criterio "¿todas las líneas son afirmaciones?" puntuó 0.84
(aprobado) y aun así la línea falló. El criterio útil es: *"cada línea tiene sujeto y verbo
conjugado y no es una lista con dos puntos"*. Un gate de estilo aprueba; la duración medida del WAV
es la prueba dura.

## 2. QR del enlace de registro: generar y **verificar en el MP4 final**

- El enlace de Teams Events es un identificador largo (114 caracteres) que no se puede mostrar como
  texto; se manda como **QR** en la escena de registro.
- Generación: paquete `qrcode` con `ERROR_CORRECT_H` y `box_size=8` → 57 módulos, 504 px. Con
  `pip` bloqueado por PEP 668 en el python de Homebrew, se instaló en un **venv** aparte
  (`/Users/xavier/.hermes/cache/scratch/qrenv`) y se usó ese intérprete solo para el QR.
- **Tamaño mínimo práctico:** el QR quedó a 410 px en un lienzo de 1080 → **~7.2 px por módulo**.
- **Verificación obligatoria (dos pasos):** decodificar con `cv2.QRCodeDetector` (a) el PNG y (b) un
  **frame del MP4 ya renderizado** (`ffmpeg -ss 19.5 -frames:v 1`). Solo el paso (b) prueba que el
  Ken Burns + x264 no rompieron el código; ambos devolvieron exactamente la URL del post.
  Ojo: recortar el QR y **reescalarlo** para decodificar da falsos negativos — recortar en tamaño
  nativo.

## 3. Elegir la ventana de música sin escuchar la pista

La cama se tomó del mismo archivo del reel anterior, pero en otra ventana para que no suene igual.
Perfil de energía por segundo con FFmpeg y un ranking automático de las ventanas de 30 s más parejas
(menor rango de RMS):

```bash
ffmpeg -v info -i pista.mp3 -af "aresample=48000,asetnsamples=n=48000,astats=metadata=1:reset=1,\
ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" -f null -
```

`asetnsamples=n=48000` es lo que fija la ventana en **1 segundo** (sin él, `astats` reporta por
frame y el perfil no sirve). Resultado: ventana de **36.0 s** (rango 2.1 dB, media −10.5 dB); la
zona de 70 s tenía un hueco de −18.5 dB que habría dejado un silencio audible.

## 4. Reutilizar recursos de un proyecto hermano del mismo tema

Copiar `recursos/logos/{fluke_networks,syscom}.png` y `musica_fuente.mp3` del reel anterior y
adaptar `generar_canvas.py` ahorró todo el trabajo de preparación de assets (los logos ya venían
recortados al bbox y con la receta de pastilla blanca). Coste de arranque del proyecto: minutos.

## 5. Revisar el diseño **antes** de pagar TTS

`ffmpeg` con `anullsrc` + los segmentos + `ass=subs.ass` produce un `preview.mp4` mudo en ~8 s que
ya tiene captions y stickers quemados. Revisado con visión se detectaron dos redundancias
(el sticker "LAS 4 DUDAS DEL POST" duplicaba el encabezado de la tarjeta; "REGISTRO GRATUITO"
aparecía en la tarjeta y en la caption) y se corrigieron **sin volver a tocar el audio**.

## 6. Otras verificaciones de esta pieza

- Día de la semana del evento comprobado con `date`/`datetime` (**jueves** 1 de octubre de 2026), no
  asumido.
- Anchos de texto medidos con Pillow antes de renderizar (`revisar_anchos`), incluidos los stickers
  ASS (64 px): el más largo, 763 px sobre un límite de 1000.
- Audio final: **-15.4 LUFS**, TP -2.9 dBTP; cama audible en los huecos (max -5.4 dB) y -25.6 dB en
  la cola por el fade out.
- Sin kicker numerado ni barra de progreso (opt-in omitidos, según
  `[[Preferencias-Usuario]]`).

## 7. Costos de la pieza

| Partida | USD |
|---|---|
| **Sesión del agente** (Hermes, deepseek-v4.1-flash + kimi-k3) | **0.2711** |
| TTS (5 líneas + 1 regenerada, gpt-audio-mini) | 0.0024 |
| Verificación de voz (gemini-2.5-flash, 2 pasadas) | 0.0022 |
| Gate JEV (typesafe/jev-1.13) | 0.00003 |
| **Total** | **0.2758** |

La orquestación del agente es el **98 %** del costo: si el reporte solo sumara las llamadas de
generación diría 0.005 USD y mentiría por un factor de ~55.

## 8. Respuestas de aprendizaje continuo (AGENT §15)

1. **¿Cómo optimizar la creación de videos similares?**
   - Guardar un `generar_canvas.py` parametrizable (colores, tarjetas, pills, QR) en vez de copiarlo:
     ya se usó dos veces con cambios menores.
   - El preview mudo antes del TTS es el paso que más ahorra: valida diseño, captions y stickers
     gratis.
   - Regenerar **una sola** línea de voz (borrar su WAV) en lugar de las cinco.
   - Para piezas del mismo evento, clonar el proyecto anterior y cambiar el ángulo, no el pipeline.
2. **¿Qué funciones nuevas se usaron?**
   - `qrcode` + verificación de QR con `cv2.QRCodeDetector` sobre un frame del MP4 final.
   - Perfil de energía por segundo con `asetnsamples=n=48000` + `astats=reset=1` para elegir la
     ventana de música.
   - Preview mudo (`anullsrc` + segmentos + `ass`) como revisión previa al TTS.
   - `adelay` del colchón de silencio por línea (ya en la versión base) y gate JEV sobre el guion
     antes de pagar TTS.

## Enlaces

- `[[AGENT]]` — reglas y flujo de decisión
- `[[SKILL]]` — catálogo de skills (crear-audio, armar-reel, crear-imagen)
- `[[Lecciones-2026-09-28-reel-fluke-webinar-cobre]]` — reel hermano del mismo webinar (lienzos PIL)
- `[[Lecciones-2026-09-28-reel-syscomexpo2027]]` — pipeline `scripts/reel.py`, JEV y mosaicos
- `[[Musica-Libre-de-Derechos]]` — fuentes y licencias de música
- `[[Costos-y-Avance]]` — reporte de costos y avance de render
- `[[Preferencias-Usuario]]` — preferencias locales no versionadas