---
tags: [lecciones, motor-ilustrado, firma, entintado, remotion]
fecha_modificacion: 2026-11-11
estado: activo
---

# Lecciones 2026-11-11 — firma de la casa del motor ilustrado

> Motor en [[Motor-Ilustrado]]. Parte del Short del reloj ([[Lecciones-2026-11-10-estilo-ilustrado]]), rehecho con las
> mismas imágenes, voz y clips para que la comparación aísle solo la animación.

## Qué se buscó

Una animación propia y reconocible, barata y bonita. Antes de construirla, una revisión crítica del plan cambió tres
cosas. Primero, el «se dibuja solo» es el cliché de los videos de pizarra, así que va solo en la apertura y en cambios de
capítulo. Segundo, la capa solo-tinta no se pide a la IA. Tercero, la firma más fuerte es el **acento de color único** con
una **hoja de estilo fija**, porque se reconoce hasta en la miniatura.

## Resultado (reloj v2, 54.4 s, 8 tomas)

- Entintado en t1 (sobre una toma `video_ia`: se dibuja, queda quieta y el clip entra encima) y en t7.
- Mancha en t2, t5 y t8.
- 3 anotaciones: círculo en el océano sin longitud, flecha a la bolsa de oro y círculo en el reloj.
- Acento en 5 titulares y sello «FIN».
- Render: 358 s (354 de motor) para 1632 cuadros, `checks: ok`, −13.9 LUFS. La firma no encarece el render: el
  entintado es un MP4 precalculado y la mancha y las anotaciones son geometría.
- Costo extra: 0 USD en el video; 0.075 USD de la hoja canónica de la casa, que se paga una sola vez.

## Lecciones

1. **La tinta se saca de la misma imagen.** Un «sombrero negro» morfológico (cierre MaxFilter→MinFilter de ~9 px menos
   la luminancia) aísla los trazos oscuros y finos con una sola línea por trazo. `edgedetect` da doble línea y parece
   filtro. Con los negros profundos sumados, funcionó a la primera en tormenta nocturna y en mapa claro. Último cuadro
   = ilustración: el paso a la toma no salta.
2. **Precalcular en vez de enmascarar por cuadro.** Las máscaras SVG con `<image>` cargan asíncronas dentro del render
   y pueden dejar cuadros vacíos. Un MP4 corto, hecho con Pillow a 12 fps y reproducido con `<OffthreadVideo>`, es
   robusto y no cuesta render.
3. **Ecualizar el mapa de orden después de escalarlo.** Si se ecualiza antes, el bicúbico vuelve a comprimir el
   histograma (p10/p90 = 60/177) y el revelado se acelera al final. Después da 25/229: el área crece pareja.
4. **La mancha necesita ~0.7 s.** Con 0.45 s y `Easing.out(cubic)`, el 80 % de la expansión cae en 2–3 cuadros y no
   se lee como gota. Funcionó con `out(quad)`, el frente de tinta 15 % por delante de la toma y un radio de 1.12× la
   esquina más lejana.
5. **La última toma debe cubrir la cola de la voz y el sello.** Si termina en su `fin` medido, los últimos 0.6 s (más
   el sello) quedan sobre papel vacío.
6. **Hoja canónica a sangre completa.** El primer intento repitió el hueco de papel arriba. Funcionó una segunda llamada
   con la primera como referencia, describiendo **qué ocupa el borde superior** («the top of the frame shows the stone
   vault…; NO blank paper area»).
7. **Niveles de los SFX.** El rasgueo de lápiz quedó a −38 LUFS con volumen 0.22: inaudible bajo la voz a −15. Se dejó
   en 0.4 (entintado) y 0.28 (anotaciones). El golpe del sello, a 0.55, ya cae sin voz.
8. **FFmpeg en Windows:** `drawtext` sin `fontfile` revienta (segfault; Fontconfig sin configuración). Pasar
   `fontfile='C\:/Windows/Fonts/arial.ttf'`.

## Pendiente o a vigilar

- La hoja de la casa es vertical; en 16:9 transfiere bien el estilo, pero conviene revisar la primera pieza horizontal.
- El entintado se lee como brochazo, no como trazo real. Si se quiere trazo real, el siguiente paso es esqueletizar la
  tinta y ordenar por recorrido (más caro de calcular, sigue siendo local).

## Enlaces

- [[Motor-Ilustrado]] · [[SKILL]] · [[Lecciones-2026-11-10-estilo-ilustrado]] · [[Home]]
