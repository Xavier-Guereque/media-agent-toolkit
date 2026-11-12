---
tags: [lecciones, cursos, blender, animacion, estilo, drywall]
fecha_modificacion: 2026-11-11
estado: activo
---

# Lecciones — «Refuerzos para cargas» en 3D a todo color

- **Proyecto:** `proyectos/curso-drywall_10112026/` (gitignored), lección `m3-l5`.
- **Fuente de referencia:** video CP05 «Colocación de un rack en un muro de drywall», solo como investigación. Guion, modelo 3D y voz son propios.
- **Lecciones anteriores:** sigue a [[Lecciones-2026-11-11-drywall-vanos-animado]] (m3-l4) y aplica sus mejoras.

## Qué se hizo

- **12 escenas, 5 en 3D:**
  - gancho: la tele colgada solo de la placa con taquetes; el yeso se agrieta y la tele cae;
  - muro abierto y altura;
  - listones de 3 × 2;
  - tabla de 1 × 10 al ras;
  - emplacar, colgar el rack y la tele.
- **Ejemplo resuelto** sobre el alzado ortográfico del mismo modelo, con cotas de PIL (`recursos/alzado_rack_cotas.py`).
- **Guion con palabras ancla únicas** por acción y sin anclas numéricas.
  - El lint solo encontró 3 repeticiones, contra 29 avisos de m3-l4 que ahora detecta `scripts/lint_w3d.py`.

## Estilo de la casa en 3D: a todo color

El usuario pidió explícitamente: «dale color a todo, no quiero que se vea así gris sin chiste», como una caricatura. Ahora es la regla de la base: `scripts/blender_estilo.py`.

- **Paleta por tipo de pieza:**

  | Pieza | Color |
  |---|---|
  | Parante | azul `#3FA9F5` |
  | Riel | morado `#B36BFF` |
  | Madera | naranja `#FF8C42` |
  | Tabla | amarillo `#FFC93C` |
  | Muro existente | coral `#FF6B8B` |
  | Placa | crema `#FFE6B8` |

  - Fondo de cielo `#7FD1FF` y piso verde con cuadrícula.
  - Se reconoce cada pieza sin rótulo.
- **Contorno de casco invertido** con un Solidify de normales volteadas y material oscuro con backface culling.
  - Es casi gratis en Eevee. Freestyle se descartó en m3-l4: se colgaba y era muy lento.
  - **Requisito:** malla con escala 1. Por eso `caja()` pone las medidas en la malla, y `contorno()` hornea la escala si no está animada. Con escala no uniforme, el contorno sale disparejo.
- **Grano:** con 20 muestras, las sombras suaves de las luces de área grandes llenaban de grano las caras lisas.
  - El filtro `hqdn3d` de FFmpeg no lo arregló.
  - La solución fue que **solo el sol proyecte sombra**. El relleno y la luz frontal van sin sombra y con poca energía (×0.45 y 220 W); si no, la imagen se quema.
  - Se reinició el render tras ~6 min.
- **Contraste de herramientas:** el nivel amarillo sobre la tabla amarilla no se distinguía, así que el nivel pasó a rojo.
- **Rótulos grandes:** a 38 px «casi no se ven», según el usuario.
  - Se escalaron ×1.7 los rótulos anclados y ×1.5 los títulos. Mínimos: 60 px y 66 px.
  - `verificar_textos()` sigue frenando los que no caben; hubo que acortar la nota del cliente.
- **Placa transparente solo donde importa:** si se vuelve transparente toda la placa, el muro entero se ve gris y sucio.
  - Se partió en 4 trozos opacos más una «ventana» sobre el refuerzo, que baja a α 0.28.
  - Se ve la tabla amarilla y los tornillos largos llegando a la madera.

## Gotchas

- **Agrupar para animar con pivote propio:** un Empty en el centro, y los hijos con `matrix_parent_inverse = raiz.matrix_world.inverted()`.
  - La tele y el rack caen juntos; los taquetes son hijos del rack.
- **Ocultar desde un Empty:** `hide_render` no se hereda; `ocultar_hasta` y `ocultar_desde` recorren los hijos (ya documentado).
- **Detener un render en segundo plano desde Git Bash con PowerShell:** el filtro `CommandLine -match 'escenas3d_rack'` también encontró la propia shell y la cerró a media cadena de comandos.
  - Filtra por `Name -eq 'blender.exe'` o corre el `Stop-Process` solo, en un paso aparte.
- **Whisper desordena palabras cercanas:** «presenta@8.0» salió antes de «Luego@8.4». Se ancló al sustantivo siguiente («rack»).

## Costos y tiempos

- **Voz:** 13 tomas, 3.0 min, ~0.04 USD (Gemini TTS, Achird). Sin otras llamadas de nube.
- **Fotos de revisión** a 50 % y 12 muestras: ~20 s por escena con el arranque de Blender.
- **Render 3D:** 2 611 cuadros a 1080p con 20 muestras. Ver «Resultado» más abajo.

## Resultado

- **Render 3D:** 5 clips, 2 611 cuadros a 1080p en 5 888 s (~1 h 38 min, ~2.25 s por cuadro con contorno y paleta). Es casi la misma velocidad que m3-l4 (~2.2 s por cuadro): el contorno de casco invertido y la paleta salen prácticamente gratis.
  - Cada clip quedó 0.3 s más largo que su escena; no hizo falta rellenar.
- **Video final:** 13 escenas, 179 s (~3 min), con QA sin errores.
- **Revisión visual:** la hoja de cuadros confirma color en todo el cuadro, contorno parejo y rótulos legibles. La ventana sobre el refuerzo deja ver la tabla y los tornillos sin agrisar el muro.
- **Optimizar la próxima vez:**
  - Empezar las escenas directamente con `blender_estilo.caricatura()` en lugar de corregir la luz después: se perdieron dos rondas de fotos de revisión y un reinicio del render.
  - Revisar la nota del HUD con `verificar_textos()` antes de escalar los rótulos.

## Enlaces

- [[Lecciones-2026-11-11-drywall-vanos-animado]] · [[Lecciones-2026-11-10-curso-drywall]] · [[Motor-Curso]] · [[Home]]
