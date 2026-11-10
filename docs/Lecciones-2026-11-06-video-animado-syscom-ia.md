---
tags: [lecciones, remotion, motion-graphics, vertical, subtitulos]
fecha: 2026-11-06
estado: cerrado
---

# Lecciones — video animado de SYSCOM IA (motion graphics, 16:9 y 9:16)

Pieza: 88.7 s, 30 fps, **motion graphics puros** (sin metraje ni capturas: toda la UI del portal está
simulada con divs en el TSX), narrada, con música procedural y subtítulo quemado con realce por palabra.
Proyecto: `proyectos/syscom-ia-video_06112026/`. Salidas: `syscom-ia-video-16x9.mp4` (1920x1080) y
`syscom-ia-video-9x16.mp4` (1080x1920), ambas a −14 LUFS.

> **Actualización 2026-11-09:** `Karaoke`, `Titular`, `Apoyo`, las curvas de movimiento y las fuentes de esta pieza
> pasaron a la versión base (`remotion/src/componentes/`, `remotion/src/lib/`), y la conversión de tiempos, la mezcla
> y las specs a `scripts/componer.py` (ver [[Motor-Remotion]] § Piezas de la versión base). Al extraerlas apareció un
> fallo de esta entrega: en cada **pausa entre palabras** el subtítulo saltaba a la última oración de la escena, que aún
> no empezaba, y **desaparecía** hasta la siguiente palabra (15 pausas en v1, 20 en v2). Ya está corregido en la base;
> los MP4 entregados el 2026-11-06 lo conservan hasta que se vuelvan a renderizar.

## Lo que se reutilizó tal cual

- **Enrutado**: `scripts/enrutar.py` eligió `remotion-video` (0.95) sin discusión: la pieza es animación
  continua, no UI con catálogo de componentes.
- **Guion y voz**: `recursos/guion.json` → `lint_voz.py` (0 errores) → `narrar.py` (10 tomas, voz Achird)
  → `verificar_voz.py` (diff dirigido: 0 palabras extra, 0 faltantes, cifra clave presente).
  Los tiempos **no** se midieron a mano: `voz/tiempos.json` ya trae `inicio/fin`, `voz_inicio` y las
  palabras con tiempos absolutos. `componer.py` sólo los convierte a **relativos al inicio de su escena**,
  que es el sistema de coordenadas del `<Sequence>`.
- **Música y mezcla**: `sonido.musica_procedural(lt, 112, dir, -18, semilla)` + tomas con `adelay` +
  `sidechaincompress` sobre la cama, `loudnorm I=-15`; el acabado del motor vuelve a normalizar a −14.
- **Puertas JEV**: 7 rondas sobre el guion (no convergen si se pregunta "¿listo tal cual?"; sí convergen
  si se pregunta por el eje concreto: promesa, beneficio, claridad) y 1 sobre el borrador antes del
  render final (0.8, riesgo menor). Escribir las preguntas con **criterios** (`choice`/`score`), no sólo
  un `noul` global.

## Pitfalls nuevos (y cómo se resolvieron)

1. **`narrar.py` muere al final en este Mac** (`ffmpeg: Unrecognized option 'filter_complex_script'` al
   concatenar `voz.wav`). Las tomas por escena y `tiempos.json` sí quedan completas: el mezclado se hace
   aparte, en `componer.py`. No hay que regenerar la voz.
2. **Margen en `%` en vertical se resuelve contra el ANCHO** (regla CSS), no contra el alto: un
   `marginBottom: '21%'` daba 12% real y el subtítulo quedaba **encima** de las pastillas de la ventana.
   Usar **px** para el margen inferior del escenario (430 px en 1080x1920).
3. **El subtítulo necesita `maxWidth:'100%'` + `flexWrap:'wrap'`** y pocas palabras por bloque (5 en
   vertical, 9 en horizontal): sin eso el panel se desborda y el texto se **corta** en los bordes del
   cuadro.
4. **Un hijo `height:'100%'` dentro de un contenedor `display:flex` en fila NO se estira a lo ancho**:
   el cierre salía pegado a la izquierda con el logo diminuto. `flexDirection:'column'` en el contenedor.
5. **La UI simulada en px no llena un marco vertical**: escalar la ventana **en bloque**
   (`width/height: 100/k %` + `transform: scale(k)`, `transformOrigin:'top left'`) con k≈1.32. Escalar
   sólo el contenido corta; escalar el contenedor sin compensar el tamaño lo desborda.
6. **Un layout radial se encima en 9:16** (el nodo central choca con las tarjetas): en vertical, variante
   apilada con conectores verticales y un punto que viaja.
7. **`scripts/remotion.py` render lee siempre `remotion.json`**: para dos orientaciones hay que
   intercambiar el spec (`cp remotion.vertical.json remotion.json`), renderizar, y **restaurar** el
   horizontal al final (el repo lo deja como canónico).
8. **Revisión de fotogramas**: hoja de contactos 5x2 por orientación en dos momentos de cada escena
   (≈32% y ≈75%) + **zoom a la franja crítica** (subtítulo y borde inferior de la ventana) a 2–3x. La
   hoja sola engaña: a 1/5 de resolución "lo" se lee "to" y parece un error del TTS que no existe.
9. **`Tile` con arte más alto en vertical cabe**: el recorte de tarjetas venía del layout, no del tamaño
   del arte. Antes de encoger contenido, revisar el zoom del borde de la ventana.
10. **El cierre pide su propio trato**: no lleva título ni subtítulo (no hay narración que realzar) y
    necesita el área completa; si se le deja el layout de escena, queda descentrado y con el logo chico.

## Copiar el diseño real de un sitio (segunda iteración)

El usuario rechazó la primera UI por no parecerse a `syscom.mx`. Lo que funcionó:

11. **`agent-browser` con perfil renderiza `www.syscom.mx` SIN CSS** aunque `curl` sí traiga la hoja
    (`aplicacion.css?v=7.4`, 200). No es bloqueo: es el navegador. Para leer estilos reales, usar el
    **Chrome ya abierto con CDP** (`127.0.0.1:9250` + `cdp_eval.py`), no `agent-browser`.
12. **Los tokens salen de las variables CSS del sitio** (`getComputedStyle(document.documentElement)`,
    filtrar `--*`): `--color-brand-*`, `--color-card`, `--color-bg-*`, `--color-border-*`, `--color-fg-*`.
    De ahí salió la paleta real (superficies `#ffffff`, lienzo `#f8f9fd`, líneas `#e2e6f0`, acento
    `#4a6ed9`, texto `#171e30`) y la tipografía **Figtree**. Nada inventado a ojo.
13. **La ventana del video va en tema claro aunque el lienzo exterior siga oscuro**: el contraste hace que
    la UI "flote" y se lea como captura real del portal, sin perder el fondo de marca.
14. **El subtítulo no debe fundirse a negro entre frases**: si `pOut` cae antes de que entre la siguiente,
    la franja queda vacía 2–7 cuadros y se ve como fallo. Quitar el fundido de salida (`p = pIn`); el
    escenario completo ya se desvanece al final, así que no queda texto colgado.

## Tercera iteración — v2 con capturas reales (63 s, 9 escenas)

Pedido: «animaciones y capturas reales (de la presentación), reducido a 1 minuto; diagramas sólo
cuando se explica el funcionamiento, y la imagen original cuando se habla de una sección».

15. **Las capturas del deck se recuperan con `pdfimages -png deck.pdf <dir>`**: las láminas embeben las
    pantallas reales a **1778x1046** (una por sección). Es más limpio que recapturar el sitio y no depende
    del WAF. Cada escena de sección apunta a `recursos/capturas/<seccion>.png`.
16. **La ventana conserva la proporción de la captura** (`alto = ancho / 1.70`) en las dos orientaciones:
    con `object-fit: cover` y una caja de proporción distinta, la captura se recorta arriba/abajo sin que
    se note por qué. En vertical, centrar el bloque título+ventana (`justifyContent:'center'` +
    `paddingBottom` para el subtítulo) reparte el aire mucho mejor que título arriba y ventana centrada.
17. **La anotación (recuadro + etiqueta) se posiciona midiendo la captura, no a ojo**: rejilla con PIL
    (`líneas cada 0.1` y `0.25`) sobre la captura, leer coordenadas con visión y pasarlas como `foco` y
    `region` en los props. A ojo, el recuadro del botón «AI» cayó sobre el panel de Noticias.
18. **Si el recuadro queda pegado al borde superior, la etiqueta va DEBAJO** (`arriba < 13%` → etiqueta
    debajo del rectángulo); encima se sale del marco.
19. **La narración debe describir lo que la captura muestra de verdad**: la escena del buscador decía
    «los filtros aparecen solos» y la captura sólo tiene la barra lateral de filtros del catálogo. Se
    reescribió la línea en vez de señalar con el recuadro algo que no existe en la imagen.
20. **El diagrama sólo se usa para el funcionamiento** (una escena de 4 piezas con conectores); el resto
    son capturas. Tarjetas de 384 px de ancho (icono 60, título 30) para que llenen el cuadro.
21. **Bloques de subtítulo más largos** (`porFrase` 16 horizontal / 11 vertical): con 13 palabras, una
    oración de 17 se partía y el bloque quedaba cojo («…trabajan» sin «juntos.»).

## Cuarta iteración — correcciones del usuario (marco de Mac, imagen quieta, recuadros)

22. **La captura va QUIETA**: el usuario rechazó el «zoom lento» (`scale` de 1.0→1.16 con respirar).
    Sin transformación, el recuadro de la anotación se calcula en coordenadas de la imagen y por tanto
    **las coordenadas medidas sobre el PNG son exactamente las del video** — se pueden verificar con PIL
    antes de renderizar (componer el PNG con el rectángulo y su etiqueta y mirarlo), sin gastar renders.
    Es la forma barata de cazar un recuadro mal puesto: 7 escenas verificadas en 4 llamadas de visión.
23. **La anotación a ojo falla sistemáticamente**: el botón «AI» está en `(0.495, 0.094)`, no en
    `(0.462, 0.088)`, y el de filtros en `x 0.03–0.21`, no en `0.02–0.17`. Se localiza por **color**
    (blob azul de marca con BFS en la franja del encabezado) o con **rejilla** cada 0.02 sobre un recorte
    ampliado; nunca estimando de memoria.
24. **El recuadro debe encerrar el elemento que nombra la etiqueta, no una vecindad**: la factura de la
    escena 7 quedaba FUERA del recuadro (que sólo cubría los pedidos); se movió a la fila `FA26 … Pagar`.
    Si la etiqueta es el título de una sección, el recuadro abarca la sección entera (ficha: título,
    tarjetas y precios). Y si el recuadro no encierra lo que la etiqueta dice, **se cambia la etiqueta**.
25. **Marco de Mac**: bisel de aluminio con **la muesca en el bisel, no sobre la captura** (encima del
    marco de pantalla), más la base del MacBook. En vertical la base al 104% obliga a bajar el ancho del
    cuerpo al 96% o se sale del cuadro. Alto del cuerpo = `(ancho − 2·bisel)/aspecto + 2·bisel + base`,
    para que la pantalla conserve la proporción exacta de la captura y `object-fit: cover` no recorte nada.
26. **La voz pronuncia mal una sigla pegada a la palabra anterior**: «ya tiene SYSCOM IA dentro» suena
    raro, pero «SYSCOM IA ya está ahí» (inicio de oración) suena bien. Arreglo: reescribir la línea para
    que la sigla **empiece oración** («…ya tiene acceso. SYSCOM IA está dentro del portal.»). Verificar
    con `~/.hermes/scripts/transcribir.sh voz/1.wav small es` y comparar con la escena que sí suena bien.
27. **`narrar.py` falla con el ffmpeg de `~/.hermes/tools` (9.0.1)**: `Unrecognized option
    'filter_complex_script'`. Ese binario no lo trae. Correr con `PATH="/opt/homebrew/bin:$PATH"`
    (ffmpeg 7.1 de brew sí lo soporta). `remotion.py` y `componer.py` no lo usan, por eso el render sí
    funcionaba con el otro.

## Quinta iteración — precios ocultos, recuadros por borde y escena de canales (72.9 s, 10 escenas)

Pedido: «acomoda los cuadros verdes al área correcta; haz énfasis en que todo eso lo puede hacer
SYSCOM IA; agrégale la animación de WhatsApp, chat y MCP del final de los otros videos; pixelea los
precios, no deben verse. Si es necesario sobrepasa el minuto».

28. **El recuadro se mide por el BORDE del elemento, no por su contenido**: leer una fila/columna y
    buscar el cambio de color del borde. Así salieron las tarjetas de colecciones (`x 0.175–0.795`), el
    borde derecho de la tabla del chat (`x 0.391`) y la fila de tarjetas de «Para Ti»
    (`0.046–0.168`, `0.177–0.297`, …). Buscar el contenido (`runs` de píxeles no blancos) da el mismo
    resultado para las tarjetas de producto (las imágenes son oscuras), pero **falla** con bordes claros
    (colecciones: el borde `#eaeaea` no lo detecta un umbral de 246). Los dos recuadros que el usuario
    rechazó venían de mezclar ambos: uno cortaba tarjetas y el otro se salía de la tabla hacia la captura
    del portal.
29. **Pixelear precios: la banda a ojo deja escapar el signo `$`**. La columna de precios del chat
    empieza en `x 0.31` (no 0.34) y la fila resumen de facturas está en `y 0.22` (no 0.13). Se localizan
    las filas con **texto oscuro por umbral** (`sum(RGB)/3 < 120` contando píxeles por fila en un rango
    `x` acotado) y se pinta un **mosaico en el PNG antes de renderizar** (`crop` + `resize` a 1/14 +
    `resize` con `NEAREST`): es determinista, se verifica con PIL y no depende de ningún desenfoque en
    tiempo de render. Guardar los originales en `capturas/_sin_pixelar/` (el script siempre lee de ahí,
    así que reejecutarlo es idempotente). Capturas con precios visibles: `parati` (banda `y 0.60–0.66`),
    `ficha` (`y 0.51–0.55`), `agente` (columna `x 0.31–0.40`) y `facturas` (cuatro bandas: resumen,
    dos pedidos y la fila de la factura). `home`, `buscador` y `conocimiento` no muestran importes.
30. **«Haz énfasis en que todo lo puede hacer SYSCOM IA» = la sigla al inicio de la oración en cada
    escena**, no repetirla más veces. Además encaja con la lección 26 (la sigla pegada a la palabra
    anterior se pronuncia mal). Una mención por escena, empezando oración o tras coma.
31. **Recuperar una animación de un video anterior es portar el componente, no rehacerlo**: la escena de
    canales (portal / WhatsApp / agente por MCP) ya existía como `EscCanales` en `SyscomIa.tsx`, envuelta
    en el marco de navegador. Se portó al tema oscuro del v2 (paleta `C`, sin `Ventana`), se enrutó con
    `tipo:'canales'` y se le hizo sitio reutilizando el layout de diagrama
    (`esDiagrama = tipo === 'como' || tipo === 'canales'`). El radial de 3 tarjetas tiene variante
    apilada para 9:16 (lección 6).
32. **Un radial de 3 tarjetas pesa hacia arriba**: la tarjeta superior va a `−R` y las dos inferiores a
    `+R·0.74·sen(30°)`, así que el grupo queda descentrado aunque el nodo esté centrado. Se compensa con
    un desplazamiento fijo del grupo (`DY`) aplicado al nodo, a las líneas (`top: calc(50% + DY)`) y a las
    tarjetas, y se ensanchan las tarjetas (320→344) para que «El botón «AI» del encabezado» no se parta.

## Cifras

- v1: 2662 cuadros por orientación; render final 88 s (vertical) y 108 s (horizontal) en M3.
  Costo de generación **0.0197 USD** (voz 0.0164, verificación 0.0029, decisiones 0.0003).
- v2: 1892 cuadros por orientación, **63.07 s**, 1920x1080 y 1080x1920, −14.1 LUFS, −1.5 dBTP.
  Costo de generación **0.0206 USD** (voz; el resto del guion se reusó de la caché por hash de línea).
- v3: 2188 cuadros por orientación, **72.93 s**, 1920x1080 y 1080x1920 @ 30 fps, −14.0 LUFS, checks ok.
  Costo de voz de esta iteración **0.0126 USD** (9 líneas nuevas; la escena 1 salió de caché).
- Costo de la sesión de Hermes de la jornada: **1.8905 USD** (572 llamadas) — incluye el deck de 19
  láminas y las dos iteraciones del video.
