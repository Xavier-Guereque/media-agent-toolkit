---
tags: [lecciones, tts, narracion, vision, subtitulos, xfade, sintesis, zsh]
fecha_modificacion: 2026-09-24
estado: activo
---

# Lecciones 2026-09-24 — Narración TTS y video narrado completo

Bitácora de una edición completa de prueba (video 4K HEVC de ~2.5 min, oficina → playa → oficina): intro con título, corte de silencios, narración TTS femenina sobre todo el recorrido, subtítulos duales ES/EN quemados, música procedural movida, outro animado y transiciones fade. Costo total de generación: **$0.036 USD** (visión + guion + 22 llamadas TTS).

Ritual cumplido según `[[AGENT]]` §15: las dos preguntas de aprendizaje, respondidas con la información generada.

## 1. ¿Cómo puedo optimizar la creación de videos similares a este?

1. **Una sola llamada de visión combinada.** Pedir en el mismo prompt: descripción + **mapa de escenas por rango explícito** (p. ej. `{"0-50": "oficina", ...}`) + guion con marcas de tiempo. En esta edición se hicieron dos llamadas porque la primera cubrió solo 70 de 149 s, y el guion narrativo **contradecía** el mapa de escenas (decía "de vuelta a la oficina" a los 90–120 s cuando la playa seguía hasta 130). Lección: **confiar en el mapa de escenas explícito y remapear las anclas de narración a ese mapa**, no a los tiempos del guion.
2. **Presupuestar la voz por duración medida de WAV, no por segundos del guion** (ver lección de pacing abajo). Pedir líneas de ≤10 palabras desde el primer intento evita una ronda de compresión y re-síntesis.
3. **Render de piezas en paralelo.** Las 5 piezas (intro, 3 tramos, outro) se renderizaron en 5 llamadas concurrentes: la decodificación 4K HEVC era el cuello de botella y correrlas en paralelo recortó el total a lo que tarda la pieza más larga.
4. **Reutilizar la pista de video para iterar solo la voz.** Con el cuerpo ensamblado (`cuerpo.mp4`), cambiar guion/voz/subtítulos solo requiere re-mezclar audio y re-quemar subtítulos — no volver a cortar ni a unir video. Mantener el cuerpo sin subtítulos quemados hasta el final.
5. **Scripts idempotentes.** El generador de voz saltaba los WAV ya existentes: re-correrlo tras ajustar una línea solo re-sintetiza lo nuevo. Ahorra llamadas API y minutos.

## 2. ¿Qué nuevas funciones utilicé?

- **TTS `gpt-audio-mini` por SSE** (`modalities:["text","audio"]`, `stream:true`, PCM16 24 kHz mono crudo) con conversión `ffmpeg -f s16le -ar 24000 -ac 1` → 48 kHz estéreo. Flujo documentado en `[[SKILL]]` → `crear-audio`; en esta sesión se confirmó de extremo a extremo.
- **Control de ánimo vía `system` prompt** (p. ej. "voz de mujer mexicana, cálida, ritmo pausado"): verificado que el modelo lo acepta; la intensidad es aproximada. El **arco emocional por sección** (un `system` distinto por tramo) quedó diseñado y documentado — **pendiente de verificación** en el próximo video.
- **Track de voz cosido por Python puro** (`array`/`wave`): colocar cada segmento en su ancla, empujando el siguiente si se solapa (`start = max(anchor, fin_prev + 0.25)`), y derivar los subtítulos de los tiempos reales medidos — voz y subtítulos siempre sincronizados.
- **Subtítulos ASS duales**: estilo ES (blanco, bold, `MarginV 100`) + estilo EN (cursiva, otro color, `MarginV 44`) en un mismo `.ass` quemado con el filtro `subtitles`; más `.srt` en español de respaldo. Verificado con libass + Arial del sistema.
- **Sintetizador procedural en Python puro** (sin numpy): kick 4-on-the-floor, hats en contratiempos, bajo en corcheas y arpegio en semicorcheas a 124 BPM (Am–F–C–G), limitador `tanh`, WAV estéreo 48 kHz. Alternativa más "movida" que la receta ambient de `[[Musica-Libre-de-Derechos]]`.
- **Cadena `xfade` de 5 piezas** (intro, 3 tramos, outro) con `acrossfade` en audio; regla verificada: cada `offset` < duración acumulada, y la duración total = Σpiezas − 0.5 s × nº de transiciones.
- **Verificación de subtítulos quemados vía PSNR** (`ffmpeg -i frame_con_subs -i frame_sin_subs -filter_complex psnr`): útil cuando el agente no puede ver imágenes; PSNR ~27 dB en luma = texto presente.
- **Gotcha zsh**: `set -- $r` **no** divide la variable en palabras (sí lo hace bash); `"$1"` quedó como `"0 45"` y ffmpeg falló con `Invalid duration`. No depender de word-splitting en zsh; usar args explícitos o `${=r}`. Además: `silencedetect`/`volumedetect` necesitan `-nostats` para grepear el log limpio.

## Lecciones operativas (registradas en el sistema de lecciones)

1. **Pacing TTS:** `gpt-audio-mini` habla ~40 % más lento de lo planeado (21 líneas "de máx 5 s" → 197 s). Presupuestar por WAV medido; líneas ≤10 palabras o ~60 % del slot.
2. **Visión en videos largos:** puede cubrir solo una parte y/o contradecir su propio mapa de escenas. Pedir clasificación de escena por rango y remapear anclas a ese mapa.
3. **Anclas tras cortes:** al quitar silencios (p. ej. 8 s en 45–53 s) y agregar intro, el mapeo origen→final cambia por tramos; definir la fórmula por pieza (`t_final = t_src ± Δ`) y aplicarla a todas las anclas.

## Enlaces

- `[[SKILL]]` — `crear-audio`, `crear-subtitulos`, `unir-clips`, `transiciones`, `musica-fondo`
- `[[Lecciones-2026-09-23-IMG_7347]]` — bitácora previa (HDR/rotación, TTS, mezcla)
- `[[Musica-Libre-de-Derechos]]` — receta procedural ambient
- `[[AGENT]]` — §15 aprendizaje continuo
- `[[Home]]` — índice de la bóveda
