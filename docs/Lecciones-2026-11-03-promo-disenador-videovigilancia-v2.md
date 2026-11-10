---
tags: [lecciones, remotion, promo, metraje-real, grabacion-pantalla, recortes]
fecha_modificacion: 2026-11-03
estado: activo
---

# Lecciones 2026-11-03 — Promo v2 del Diseñador de Videovigilancia (9:16 y 16:9)

Promo de 54.4 s en 9:16 y 16:9 a partir de dos grabaciones de pantalla (56 s y 4:45 min).
Proyecto: `proyectos/disenador-videovigilancia-v2_03112026/`. Ver [[Motor-Remotion]] y
[[Lecciones-2026-11-02-promo-disenador-videovigilancia]].

## ¿Cómo optimizar videos similares?

1. **Medir los recortes con regla de píxeles en la toma elegida; nunca heredar coordenadas de otra
   grabación.** En esta grabación el panel PTZ vive en x 1225–1716 (contra ~660 en la del 2 de
   noviembre) y la hoja del reporte en x 0–1000 (contra 590–1450). Reusar las coordenadas del promo
   anterior costó dos ciclos de cortar y revisar. Regla: primero el cuadro con regla, luego el recorte.
2. **La regla solo sirve si se lee.** Sobre el cuadro completo (1716 px) la imagen llega al modelo a
   858 px y las etiquetas cada 100 px se leen mal: de ahí un error de ~280 px. Para zonas densas,
   recortar la mitad de la pantalla y ampliarla 1.8× antes de dibujar la regla.
3. **`-ss` antes de `-i` es exacto en estas grabaciones** (VFR/HEVC). El clip equivocado del reporte no
   fue por el seek sino por elegir mal el segundo de origen: conviene listar el tramo candidato con una
   rejilla cada 6 s antes de fijar el `ini`.
4. **Un recorte apretado es zoom gratis.** `1000:560:716:340` da 1.9× en 16:9 y deja legibles
   "Guardar posición" y "Preset 1/2/3", que en la fuente miden ~11 px.
5. **La ventana de metraje no es el lienzo.** La base del encuadre se calcula con el tamaño de la
   ventana (`base = max(ancho/fw, alto/fh)`) y `x = min(0, max(ancho − fw·s, ancho/2 − cx·s))`: para que
   el encuadre arranque en la columna 0 de la fuente hay que cumplir **`cx ≤ ancho/(2·s)`**. La ventana
   vertical es 1000×910 y la del reporte en 16:9 es 920×980: ahí manda el alto, la escala es ×2.07 y solo
   caben ~445 px de ancho del recorte. Con `cx` de más se cortan las etiquetas de una columna de UI.
   Revisar el mismo cuadro en las dos orientaciones antes del render final.
5b. **Recortar también lo que no se quiere contar.** El campo del reporte traía datos de prueba
   ("PRUEBA PRUEBASS PRUEBAS") legibles en el video: se midió la banda Y de la lista de opciones
   (miniaturas hasta y 950, campo desde y 995) y el recorte se cerró en y 960.
6. **Metraje que se desplaza:** si lo que se quiere mostrar es el **recorrido**, dejarlo a velocidad real
   (`vel=1.0`) y recortar el documento, no la columna lateral fija; con `vel` < 1 (`setpts`) el texto se
   lee mejor pero el recorrido pierde fuerza. Elegir según lo que pida el cliente, no por defecto.
6b. **Medir el recorte sobre el cuadro de la fuente, con regla de píxeles.** Dos veces se encuadró "el
   documento" en blanco porque las coordenadas venían de otro cuadro; y el campo con datos de prueba
   ("PRUEBA PRUEBASS PRUEBAS") solo se localizó bien midiendo sobre la toma: vive en y ≈ 1030, x 0–200.
   Truco de verificación sin renderizar: extraer del clip exactamente lo que mostrará la ventana
   (`ffmpeg -vf crop=<ancho/s>:<alto/s>:<x/s>:<y/s>`) y revisarlo con visión.
7. **El zoom mínimo lo fija `alto/fh`, y "sin zoom" se pide con el recorte más grande posible.** Para
   "se ve muy cerca" la solución no es ajustar `cx`/`cy` sino agrandar el recorte: con la pantalla completa
   (`1716:1046:0:0`) `base = max(ancho/fw, alto/fh)` cae por debajo de 1 (~0.87 en 9:16, ~0.96 en 16:9) y
   la ventana deja de amplificar. Un `zoom` explícito > 1 en el `foco` multiplica ese factor (1.10 en la
   escena 7 daba ×2.0) y es la causa típica de "está muy cerca". Aplica igual a vista simulada y reporte.
8. **Verificar el QR en el MP4 final**, no solo el PNG: `cv2.QRCodeDetector` sobre cuadros del cierre
   (50.5, 52.0 y 53.5 s) decodifica la URL exacta.

## ¿Qué funciones nuevas usé?

- Un solo TSX (`PromoDisenador2.tsx`) para 9:16 y 16:9, con `foco` por escena y orientación y recortes
  distintos por escena. Verificado en los dos renders.
- Rótulo de puente propio sobre el hueco real de la grabación (19.0–19.6 s), sin inventar interfaz:
  plano 2D → hueco → modelo 3D. Verificado en el MP4.
- `sonido.musica_procedural` fuera del motor promo con un `lt` mínimo. Verificado.
- `vel` < 1 en `componer.py` para cámara lenta de metraje de UI. Verificado.

## Problemas encontrados

- **`narrar.py` falla al final en este equipo:** `ffmpeg` responde `Unrecognized option
  'filter_complex_script'` al concatenar `voz.wav`. Los WAV por escena quedan completos y
  `componer.py` arma su propia mezcla, así que la pieza no se bloquea; el `voz.wav` sí queda sin
  generar.
- **`Titular` con `flexWrap` dentro de una columna flex necesita ancho acotado:** sin él las palabras no
  envuelven y el texto se sale del cuadro (el rótulo de puente perdía "3D"). Solución: envolverlo en un
  `div` con `width: '100%'` y `justifyContent: 'center'` dentro de un contenedor con padding lateral.
- **`glob` con el nombre completo del archivo no coincide:** `Grabaci*n 2026-10-12*.mov` no casa con
  "Grabación de pantalla 2026-10-12 a la(s)…" porque el `*` no cubre "de pantalla". Usar
  `Grabac*2026-10-12*.mov`.
- **La vista simulada de la cámara puede traer a la persona cortada por el borde de su propio marco**
  (el panel dice "Parcialmente visible"): es el comportamiento de la herramienta, no del recorte.
- `ffmpeg -h full | grep filter_complex_script` no lista la opción en este build; no hay arreglo local
  sin tocar `narrar.py`.

## Enlaces

- [[Lecciones-2026-11-02-promo-disenador-videovigilancia]] · [[AGENT]] · [[SKILL]] · [[Motor-Remotion]]
