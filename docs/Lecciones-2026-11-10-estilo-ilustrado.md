---
tags: [lecciones, motor-ilustrado, video-ia, openrouter, seedance, parallax, remotion, nano-banana]
fecha_modificacion: 2026-11-10
estado: activo
---

# Lecciones — primer explicador ilustrado y prueba de 5 modelos de imagen a video (2026-11-10)

Pedido: hacer videos «como los Shorts de historia ilustrados» de forma práctica, barata y bonita, para la versión base.
Investigación previa en [[Investigacion-2026-11-10-estilo-ilustrado]]; motor resultante en [[Motor-Ilustrado]].
Proyecto de ejemplo: `proyectos/reloj-longitud_10112026/` (gitignored): «El reloj que salvó a los marineros», 52.6 s
en 9:16, 8 tomas (5 `imagen`, 2 `parallax`, 2 `video_ia`), tema y estilo propios.

## Lo que funcionó

- **OpenRouter genera video con la misma key** (`POST /api/v1/videos`, 33 modelos). El contrato de la documentación
  coincidió al pie de la letra: 202 con `polling_url`, sondeo hasta `completed`, `unsigned_urls` con `Authorization`,
  `usage.cost` en la respuesta final. Esperas de 40 s (Hailuo) a 165 s (Kling).
- **El precio calculado desde `pricing_skus` coincidió con lo cobrado:** Seedance 1.5 Pro 5 s 720p estimado 0.1307 →
  cobrado 0.1307; Grok Lite 0.16 → 0.16; Hailuo 0.40 → 0.40; Kling 0.56 → 0.56. Veo 3.1 Lite cobró 0.18 por 6 s
  (no acepta 5 s: `elegir_duracion` sube a la duración admitida siguiente).
- **Prueba comparativa (`video_ia.py comparar`, 1.43 USD, mismo cuadro de un mecanismo de reloj y mismo prompt):** los
  cinco conservaron el contorno de tinta, el relleno plano y la textura; ninguno se fue a 3D fotorrealista. Seedance,
  Veo y Grok hicieron el acercamiento pedido; Hailuo y Kling casi no movieron la cámara pero sí giraron los engranes;
  Grok **inventó engranes nuevos** al acercarse. **Decisión: `modelos.video` = Seedance 1.5 Pro** (el más barato de los
  que respetan dibujo y movimiento). Video lado a lado en `proyectos/reloj-longitud_10112026/comparar_modelos.mp4`.
- **Hoja de estilo como referencia en cada llamada** (`gemini-nano-banana-2.1`, ~0.04 USD/imagen): 8 escenas distintas
  (tormenta, retrato, carta náutica, parlamento, taller, mecanismo, cubierta, bodegón) con el mismo trazo y paleta.
- **Parallax con dos ediciones de la misma ilustración** («quita al capitán y pinta lo que había detrás» + «solo el capitán
  sobre verde #00FF00») + `colorkey` sobre el color muestreado en las esquinas: recorte limpio a la primera.
- **Titular cinético sin dependencias nuevas:** desenfoque horizontal por palabra con `feGaussianBlur stdDeviation="x 0"`
  proporcional a la velocidad del muelle. No hizo falta `@remotion/motion-blur` (experimental, multiplica el render).
- **Hervor del trazo a 12 fps + papel en multiply** igualan las ilustraciones fijas con los clips de IA.

## Gotchas

- **La hoja de estilo hereda su composición.** La primera `ref_1.png` dejó 60 % de papel vacío arriba; las escenas
  posteriores lo copiaron aunque el prompt decía «full-bleed». En 9:16 sirve de espacio para el titular, pero si se
  quiere sangre completa hay que pedirla en la propia hoja.
- **Parallax: nombrar solo el sujeto.** Con «the craftsman at the workbench» el recorte se llevó banco y herramientas, que
  también seguían en el fondo: al moverse se ven duplicados. Con «the man in the leather apron only (not the workbench…)»
  quedó bien. Lint pendiente: no hay forma barata de detectarlo sin mirar la hoja.
- **Clips de IA en `<OffthreadVideo>`: «No frame found at position…».** Seedance entrega 24 fps con marcas de tiempo que
  el compositor de Remotion no resuelve al estirar el clip. Arreglo en la base: `normalizar_clip` recodifica cada clip a
  30 fps CFR, al tamaño de salida (escala lanczos 720p → 1080p), GOP 15, antes de componer.
- **Tinte verde en el sujeto recortado** (manos del carpintero): el `colorkey` deja reflejo del fondo #00FF00 en los bordes. Arreglado en la base con `despill=type=green:mix=0.6` tras el `colorkey`.
- **Clip más corto que la toma:** se pide `ceil(toma + fundido)` al modelo, pero si se reutiliza un clip (p. ej. el de la
  comparación) se reproduce más lento (≥ 0.6×) para cubrir la toma.
- **Openverse no tiene música CC0 larga** (`fetch_audio.py --profile bgm` sin resultados): el motor usa
  `musica: "ambiental"` = `componer.cama_ambiental` + `componer.mezclar` con ducking. 0 USD.
- **`fetch_audio.py --help` truena en la consola de Windows** (cp1252 vs. caracteres de la ayuda): correr con
  `PYTHONIOENCODING=utf-8`.
- **Los modelos de imagen garabatean «escritura»** en papeles sueltos aunque se pida «no text»; no molesta en pequeño,
  pero para hojas en primer plano hay que pedirlas «blank».

## Costos y tiempos (i7-1355U, Windows 11)

| Partida | USD |
|---|---|
| Hoja de estilo + 8 ilustraciones + 6 ediciones de capas (Nano Banana 2.1) | 0.57 |
| Prueba de 5 modelos de video (5 s cada uno) | 1.43 |
| Clip Seedance 1.5 Pro 8 s 720p (tormenta) | 0.21 |
| Voz Gemini TTS (8 tomas, 52.6 s) | < 0.05 |
| **Total del ejemplo** | **≈ 2.25** (≈ 0.85 sin la prueba de modelos; el clip del mecanismo se reutilizó de la prueba) |

Render: borrador 540×960 en 102 s; final 1080×1920 en 591 s (motor 569 s) con otro render de Remotion en paralelo; checks ok (BT.709, −14 LUFS). El MP4 a CRF 17 pesa 116 MB: para mandarlo por mensajería, copia a CRF 25 (29 MB).

## Optimizar la próxima vez

- Pedir la hoja de estilo a sangre completa y con el tipo de encuadre dominante del video.
- Un lint visual barato para `parallax` (comparar área del sujeto recortado contra la del fondo) evitaría el duplicado.
- Probar `--borrador` (480p, ~0.012 USD/s) para iterar el prompt de movimiento antes del clip final.
- Toma `clip` con render NPR de Blender (Line Art + color plano, 12 fps) para lo técnico exacto: queda sin probar.

## Enlaces

- [[Motor-Ilustrado]] · [[Investigacion-2026-11-10-estilo-ilustrado]] · [[SKILL]] · [[Home]]
