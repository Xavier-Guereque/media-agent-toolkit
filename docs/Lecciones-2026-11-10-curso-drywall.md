---
tags: [lecciones, cursos, transcripcion, investigacion, drywall, windows]
fecha_modificacion: 2026-11-10
estado: activo
---

# Lecciones — curso de Drywall: de 13 h de material de referencia a plan de estudios y lección muestra

Proyecto `proyectos/curso-drywall_10112026/` (gitignored). Material de referencia de terceros: 44 videos (13.4 h)
y 27 PDF de un curso comprado. El usuario eligió **contenido original**: las transcripciones son investigación;
guion, diagramas y voz del curso son propios, sin clips ni textos del material.

## Flujo que funcionó

1. **Transcribir en lote con OpenRouter** (`recursos/transcribir.py` del proyecto): MP3 mono 16 kHz 32 kbps en
   fragmentos de 10 min con FFmpeg → `gemini-2.5-flash` con `input_audio` → texto con marcas `[mm:ss]` a las que
   se suma el desfase del fragmento. 5 hilos, caché por hash del MP3. **105 fragmentos, 0 fallas, 2.16 USD, ~35 min**
   (≈ 0.0027 USD/min de audio). En local, Whisper en un i7-1355U sin GPU habría tardado de 5 a 9 h.
   Prompt con glosario del oficio: los términos técnicos salen bien; quedan errores de oído («encuentro en D» por
   «en T», «estradista» por lentes) que se corrigen al escribir el guion.
2. **Fichas antes de diseñar** (`recursos/resumir.py`): 141 mil palabras no caben para leerlas. Una ficha JSON por
   video (temas, procedimientos, medidas, materiales, errores, nivel, «aprovechable», dudas) con
   `response_format: json_object` → 44 fichas, ~0.3 USD. El campo **`dudas_o_contradicciones`** fue lo más útil:
   marcó lo que es de marca, de un país (precios en soles) o contradictorio entre fuentes.
3. **Plan de estudios** desde las fichas: 9 módulos, 49 lecciones, 24 h, con objetivo Bloom, puntos clave y
   fuentes por lección, tabla de vocabulario por país y lista de «qué verificar». Entregado en Descargas.
4. **Lección muestra con el motor de cursos** (`armar_curso.py` + `curso_spec.py`): mundo continuo con 4
   diagramas propios dibujados con PIL (`recursos/diagramas.py`, CC0) y la cámara recorriéndolos; cursor `clic`
   con `dx/dy` para señalar cada pieza en la palabra que la nombra. 4.1 min, voz Achird.

## Gotchas

- **Diagramas técnicos: con código, no con IA de imagen.** Plantas y alzados a escala real (parante 89×38,
  placa 12.7 mm) con PIL salen exactos y gratis; la IA de imagen deforma medidas y texto. Primera versión a
  0.62 px/mm: la esquina, que era lo importante, no se distinguía; a 1.15 px/mm se lee a simple vista. Regla:
  dibujar **de cerca** el detalle que se enseña y dejar el muro completo para el alzado.
- **Coordenadas del cursor en una imagen del mundo:** `dx, dy` = (px en la PNG − centro) × (ancho en el mundo
  / ancho de la PNG). Medirlas en una hoja de revisión ya escalada da errores de ±10 px; aceptable para un cursor.
- **El QA cazó dos desbordes** que el validador no ve: `solucion` del ejemplo y `puntos` del resumen se
  disponen **en fila**; con más de ~25 caracteres por elemento se salen del cuadro. Mantenerlos cortos.
- **`W-CURSO-ESTATICA`** obliga a señalar algo cada ~8 s; en procedimientos largos un `dato` con las variantes
  (p. ej. tipos de fijación) que aparece parte por parte resuelve tramos enteros.
- **Dos acciones en la misma palabra** dan `E-CURSO-SYNC`: la segunda va con `junto: true`.
- **`curso.py qa` fallaba en un clon limpio** (`Can't resolve './proyectos/registro'`): `still` empaqueta sin
  pasar por `motor.mjs`, que es quien crea `registro.ts`. Arreglado en la base: `_stills` llama
  `remotion.generar_registro()` antes.
- **Windows:** `npx --prefix remotion remotion browser ensure` corrido desde la raíz del repo deja el Chrome
  Headless Shell en `./.remotion/` (fuera de `.gitignore` y de donde lo busca `remotion_deps_ok`). Moverlo a
  `remotion/node_modules/.remotion/` o correr el comando con `cwd` en `remotion/`.
- **Color en Windows:** con `imageFormat: 'jpeg'` + `pixelFormat: 'yuv420p'`, el render salió `yuvj420p`, rango
  completo, matriz `bt470bg` (en macOS sí salía `yuv420p`), y el acabado solo corrige etiquetas cuando el video ya
  está en `yuv420p`: check `FALLAS color`. Arreglado en la base con `colorSpace: 'bt709'` en `renderMedia`
  (`remotion/motor.mjs`): Remotion convierte a rango TV y etiqueta BT.709 desde el codificador. Render de 4.1 min
  en el i7-1355U: ~15 min (motor 847 s), unas 3.4 s por segundo de video (≈ 4× el M3).
- **Licencia de Remotion:** un curso para vender es uso comercial; confirmar la elegibilidad (≤ 3 personas o
  Company License) antes de producir en serie.

## Segunda versión: animaciones 3D con Blender

El usuario no entendió los diagramas 2D animados («no se entienden las animaciones»). Se rehicieron 5 escenas
(gancho, piezas, rieles, L y T) como **animaciones 3D en Blender 5.2** (`recursos/escenas3d.py` del proyecto, CLI
`blender -b --factory-startup -P … -- <escena>`), metidas en la lección como escenas `screencast` con `pantalla.clip`.
La voz no cambió: la caché de `narrar.py` depende solo del texto, así que convertir el tipo de escena no paga voz.

- **Modelo a escala real con bmesh:** perfil C 89×38 con pestañas, riel U, placa 12.7 mm, tornillos. Los tiempos de
  cada animación salen de `voz/<escena>.palabras.json` (+0.35 s de entrada de la voz, de `tiempos.json`).
- **Cámara por objetivo + azimut/elevación/distancia** (no coordenadas sueltas): mucho más fácil de razonar. Para
  pasar del interior al exterior de un muro, una clave intermedia **por encima** del muro, o la cámara lo atraviesa.
- **Rótulos que siempre caben (pedido del usuario):** hijos de la cámara a 0.1 m, reubicados en cada cuadro sobre
  la proyección de su punto del mundo y recortados al cuadro con 28 px de margen (`ajustar_rotulos`). Tamaño fijo en
  píxeles: en un acercamiento no crecen. `verificar_textos()` aborta antes de renderizar si un texto no cabe.
- **Transparencia:** `DITHERED` deja grano con 16–20 muestras; las placas que se vuelven transparentes van en
  `BLENDED` + `use_transparency_overlap = False`.
- **Lo que no se ve, se cambia de punto de vista:** el borde «en el aire» se entiende desde el lado sin placa
  (exterior), no a través de una placa transparente; los tres parantes de la T se leen **en planta desde arriba**
  con el riel de techo transparente.
- **Costo y tiempo:** 0 USD (Blender local). Eevee en el i7-1355U (Iris Xe): ~3–4.7 s/cuadro en 1080p con 20–32
  muestras → ~3 h para 2 min de animación. Iterar con fotos sueltas a 50 % y 16 muestras (`--fotos t1,t2`).
  Medido: 3 635 cuadros en 5 escenas, de 20:00 a 22:34 (render en segundo plano reportando al tablero con un
  `reportero3d.py` que cuenta los JPEG). La voz no se volvió a pagar (14 tomas en caché). Lección final: 246.5 s, render
  Remotion 1 451 s, checks ok. Revisar que cada clip dure ≥ su escena (`tiempos.json`) antes de componer.
- **Siguiente paso posible:** look ilustrado en Blender (Line Art + color plano) para que estas escenas combinen con el
  [[Motor-Ilustrado]].
- El diagrama 2D `planta-encuentro-L.png` ubicaba mal el parante adicional (no quedaba bajo el borde de la placa
  interior); el modelo 3D lo corrige (alas de 92.5 a 130.5 mm, borde de placa en 101.7 mm).

## Optimizar la próxima vez

- Promover `transcribir.py` y `resumir.py` a `scripts/` como una skill «investigar material» (transcribir en
  lote + fichas): el patrón sirve para cualquier curso o explicador que parte de videos existentes.
- Hacer el QA de stills antes de pagar la voz no ahorra nada aquí (la voz cuesta 0.06 USD), pero sí el render.
- Generar las hojas de diagramas y revisarlas con los ojos antes de escribir acciones: las coordenadas del
  cursor dependen del dibujo final.

## Enlaces

- [[Metodologia-Cursos-Video]] · [[Motor-Curso]] · [[Lecciones-2026-11-10-compatibilidad-windows]] · [[Home]]
