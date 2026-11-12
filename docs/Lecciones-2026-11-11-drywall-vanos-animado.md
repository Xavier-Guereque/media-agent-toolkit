---
tags: [lecciones, cursos, blender, animacion, drywall]
fecha_modificacion: 2026-11-11
estado: activo
---

# Lecciones — lección «Vanos de puerta y ventana» con animación 3D mejorada

Proyecto `proyectos/curso-drywall_10112026/` (gitignored), lección `m3-l4`. Fuente de referencia: video CP03
«Puerta y ventana en un tabique» del material del cliente (solo investigación; guion, modelo 3D y voz son propios).
Sigue a [[Lecciones-2026-11-10-curso-drywall]] (lección m3-l3, encuentros en L y T).

## Qué cambió frente a m3-l3

- **6 de 12 escenas en 3D** (gancho, medir de metal a metal, trazo y rieles, jambas, dintel, ventana y alféizar):
  141 s de 238 s. El ejemplo resuelto usa un **alzado ortográfico del mismo modelo** (Blender) con cotas dibujadas
  con PIL, así el 2D y el 3D se ven iguales.
- **Tiempos por palabra, no a mano.** `W("riel", 2)` busca la 2.ª aparición de la palabra en
  `lecciones/<id>/recursos/tiempos.json` (tiempos absolutos de la lección; restar `inicio` de la escena). En m3-l3
  cada tiempo se copiaba a mano desde `palabras.json`.
- **Animación con más vida, gratis:** llegadas con rebote (`keyframe.interpolation = "BACK"`, `easing = "EASE_OUT"`),
  rótulos que «saltan», cotas que se dibujan de un extremo al otro (cilindro con origen en el extremo y `scale.z`),
  atornillador que viaja a cada tornillo y el tornillo entra girando, nivel con burbuja que endereza el parante,
  la pieza de riel que se corta y sale volando, la hoja de puerta que choca (o entra) en el vano, parantes que suben
  desde el piso y un cable que cruza las perforaciones.
- Reutilización: `escenas3d_vanos.py` ejecuta `escenas3d.py` sin su `main()` (`exec` del fuente) y redefine solo lo
  que cambia. Funciona porque las funciones del archivo base buscan los nombres globales al llamarse.

## Gotchas

- **Blender 5.x (acciones con ranuras):** `action.fcurves` ya no existe; usar
  `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, anim_data.action_slot).fcurves`.
- **Ocultar un objeto con hijos:** `hide_render` de un Empty no oculta a sus hijos. El atornillador se vio en toda la
  escena hasta usar `ocultar_hasta/ocultar_desde`, que recorren los hijos.
- **Resaltar y volver:** si el resalte cambia `Base Color`, hay que animar también la vuelta al color original; si
  no, la pieza se queda teñida.
- **Palabras repetidas:** «lado» («a cada lado del vano» antes que «por cada lado»), «sus» («con sus tramos» antes
  que «Sus parantes»). Un rótulo con `hasta` anterior a su aparición queda **visible toda la escena**. Revisar cada
  `W()` contra la lista de palabras de la escena (`tiempos.json`) antes de renderizar.
- **Whisper desordena los números** («ochenta@24.0» antes de «en@24.5»): anclar las animaciones a palabras no
  numéricas cercanas.
- **Freestyle (contorno de tinta) en Eevee:** hizo el cuadro varias veces más lento y se colgó (6.8 GB) cuando
  brotaban piezas a escala 0.001. Sobre el tema oscuro casi no se nota. Quedó opcional (`--tinta`), apagado por defecto.
- **Cámara:** para mostrar la cara del alma de una jamba, la cámara va de costado (azimut ≈ −28°), no de frente; de
  frente el alma se ve de canto.
- **Validación con clips pendientes:** `curso.py validar` exige que exista `pantalla.clip`. Crear marcadores de 1 s en
  negro con FFmpeg para poder generar la voz antes de animar; las animaciones se cronometran con esa voz.

## Costos y tiempos

- Voz: 14 tomas, 4.0 min, ~0.06 USD (Gemini TTS, Achird). Sin otras llamadas de nube.
- Fotos de revisión a 50 % y 12 muestras: ~1 s por foto sin Freestyle. Hoja de contacto por escena
  (`recursos/hoja3d.py`).
- Render 3D: 4 302 cuadros a 1080p, 20 muestras, **9 457 s reales (2 h 38 min, ~2.2 s/cuadro)** en el i7-1355U,
  en segundo plano con `recursos/render3d_vanos.py`, que reporta al tablero. Por escena: e1 850 s, e3 1 700 s,
  e4 1 985 s, e5 1 748 s, e7 1 361 s, e8 1 813 s. Los clips salen ~0.3 s más largos que su escena (margen correcto).

## Optimizar la próxima vez

- Promover a `scripts/` una librería de animación 3D para cursos (piezas de drywall, `W()`, rebote, cotas que se
  dibujan, atornillador, nivel, `destello`): hoy vive en dos scripts del proyecto.
- Un lint de `W()`: listar las palabras repetidas de cada escena y avisar cuando un `hasta` cae antes de su `t`.
- Escribir el guion pensando en palabras ancla únicas para cada acción.

## Enlaces

- [[Lecciones-2026-11-10-curso-drywall]] · [[Motor-Curso]] · [[Home]]
