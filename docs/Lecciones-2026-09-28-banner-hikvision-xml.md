---
tags: [bitacora, lecciones, imagen, banner, gemini-flash-image, colorkey, drawtext]
fecha_modificacion: 2026-09-28
estado: activo
---

# Lecciones 2026-09-28 — Banner SYSCOM AI / Hikvision XML

Bitácora técnica del proyecto `proyectos/banner-hikvision-xml_28092026/`: banner web 1476×264 (robot SYSCOM AI manipulando un XML, para flujo de restablecimiento de contraseña Hikvision).

## ¿Cómo puedo optimizar la creación de piezas similares?

- **No pedir texto del titular al modelo de imagen.** `google/gemini-2.5-flash-image` deformó el español ("contraseña" → "contraserã") e ignoró el hex de fondo pedido. Patrón robusto y más barato a la segunda llamada:
  1. Generar **solo la ilustración** (mascota/iconos) sobre **fondo uniforme** y pedir explícitamente "no headline text; solo las palabras X e Y" (etiquetas cortas de 1–2 palabras sí las rinde bien: `SYSCOM AI`, `XML`).
  2. Extraer el sujeto con `colorkey` de FFmpeg sobre el color muestreado del fondo.
  3. Componer lienzo `color=c=0xHEX:s=WxH` + `overlay` + `drawtext` con fuente local (macOS: `/System/Library/Fonts/Supplemental/Arial Bold.ttf`). Ortografía y tipografía exactas, cero costo.
- **Muestrear colores con FFmpeg + xxd** (`crop=1:1:X:Y,format=rgb24 -f rawvideo - | xxd`): sirve tanto para copiar el color de marca de una referencia como para conocer el fondo real del asset generado (el modelo no obedece el hex solicitado: pidió `#4058BB`, entregó `#308AD4`).
- **Texto con acentos/ñ en `drawtext`:** sin problema pasando UTF-8 directo y `fontfile` con espacio escapado (`Arial\ Bold.ttf`).
- Para banners ultra-anchos (ratio ~5.6:1) el modelo solo entrega 1024×1024: **componer** (lienzo + overlay) en vez de recortar; un crop directo a ese ratio dejaría una franja de ~183 px de alto inútil.
- Script reutilizable: `recursos/generar_banner.py` acepta prompt y nombre de salida por `argv` y registra cada llamada en `costos.jsonl` (id + usage) sin intervención.

## ¿Qué nuevas funciones utilicé?

- **`colorkey` de FFmpeg** (`colorkey=0x308AD4:0.22:0.05`) para extraer un sujeto generado por IA de un fondo uniforme: verificado, extracción limpia en una pasada (similarity 0.22, blend 0.05). Aplica también el halo suave del sujeto si el fondo es uniforme.
- **Generación de imagen vía OpenRouter `chat/completions`** con `modalities: ["image","text"]` y respuesta en `choices[0].message.images[0].image_url.url` (data URL base64): flujo verificado end-to-end con log de costos (2 llamadas, 0.0775 USD total).
- **`drawtext` con expresiones de centrado parcial** (`x='330+(w-330-tw)/2'`) para centrar texto solo en el espacio libre a la derecha de un overlay.
- Gotcha propio: pasar `""` como argumento de prompt al script sobrescribía el default y la API respondía HTTP 400; corregido con `if arg.strip()`.

## Variante BA — desvincular dispositivo del P2P (2026-09-28)

Segundo banner con la misma receta, proyecto `proyectos/banner-hikvision-p2p_28092026/`
(par del AY: `Restablecer contraseña / Hikvision` → `Desvincular dispositivo / Hik-Connect`).
La receta se sostiene tal cual; lo que se afinó:

- **La mascota se regenera por contexto, no se reutiliza.** El robot del banner AY sostiene
  un XML (tiene sentido para "restablecer contraseña mediante XML"); para BA sostiene una
  nube con un eslabón roto y flotan una cámara de seguridad y un eslabón tachado. Reusar el
  robot del AY habría dejado un XML fuera de contexto. Costo: 1 llamada de imagen (0.0388 USD).
- **El colorkey se lleva también la sombra.** El render traía una elipse de sombra bajo el
  robot; con `colorkey=0x2a92cf:0.22:0.05` el bbox alfa terminó en y=799 en vez de 828, o sea
  que la sombra desapareció sola y no hubo que recortarla. Confirmar el color del fondo
  **muestreando el propio render** (el modelo entregó `#2a92cf` cuando se le pidió `#4058BB`).
- **Elegir el tamaño de fuente midiendo, no a ojo.** `recursos/componer_banner.py` calcula con
  Pillow el mayor tamaño que hace caber la línea más larga en la zona libre a la derecha de la
  mascota (x 330..1476−72) y compone con `drawtext` centrado en esa franja
  (`x='330+(w-330-tw)/2'`). Resultado: 94 px para "Desvincular dispositivo" (1055 px de ancho).
  El script cae a una estimación por carácter si Pillow no está (el `python3` del sistema no
  lo trae; el de Homebrew sí).
- **Dos entregables por si "botón" no significaba "banner":** el banner con mascota y una
  versión solo texto (`boton_desvincular_p2p.png`, 120 px, centrado) equivalente al
  `banner_abrir_syscom_ai.png` del proyecto AY.
- **Referencia rápida de la geometría:** lienzo 1476×264, fondo `0x3d58ba`, mascota escalada a
  232 px de alto en (60, 16), texto blanco `0xFDFDFD` en Arial Bold.

## Variante "botón con mascota" — Abrir SYSCOM AI (2026-09-28)

Petición: rehacer el botón genérico `Abrir SYSCOM AI` (que era solo texto) **agregándole el
dibujo de la mascota**, sin precisar cuál de los dos robots. Proyecto
`proyectos/boton-abrir-syscom-ai_28092026/`.

- **Reutilizar el PNG de la mascota cuesta 0 USD y es lo correcto cuando la pieza es genérica.**
  Un botón de entrada ("Abrir SYSCOM AI") no tiene flujo propio, así que ninguno de los dos
  robots le queda fuera de contexto por su prop: no hay razón para pagar otra generación.
  El criterio que ordena ambos casos: **la mascota se regenera cuando el prop cuenta el flujo
  del banner** (XML → restablecer contraseña; nube con eslabón roto → desvincular P2P) y **se
  reutiliza cuando la pieza es de entrada/genérica**.
- **Cuando el usuario no precisa cuál dibujo, entregar las dos variantes.** Son 2 s de FFmpeg
  cada una y evitan una ronda de preguntas: en la entrega va la recomendada y el alterno,
  nombrados por origen (`..._mascota_hikvision.png`, `..._mascota_p2p.png`).
- **Script paramétrico en vez de copia:** `recursos/componer_boton.py <robot.png> "<texto>" salida.png`
  (el de la variante BA tenía el robot y el fondo fijos en constantes). Con él, cambiar de mascota
  o de titular es un argumento, no una edición.
- **El texto se centra sobre la zona libre del titular, no sobre el lienzo**: `x='330+(w-330-tw)/2'`.
  Al añadir la mascota, el titular visible se corre a la derecha; es el comportamiento de toda la
  familia de banners y se mantiene aquí. Ancho del texto 835 px sobre 1074 px disponibles (96 px,
  el máximo que cabe), medido con Pillow.
- Verificación hecha con una **imagen de comparación** (las tres versiones apiladas, `recursos/comparacion.png`)
  revisada con visión: mascota sin halo ni fondo residual, texto completo y centrado.

## Enlaces

- `[[SKILL]]` → `crear-imagen`
- Proyecto BA: `proyectos/banner-hikvision-p2p_28092026/`
- `[[Lecciones-2026-09-24-syscomexpo-tiktok]]` — composición con overlays y texto local
