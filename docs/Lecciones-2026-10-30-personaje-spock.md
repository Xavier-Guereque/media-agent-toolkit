---
tags: [lecciones, imagen, personaje, gemini, openrouter, referencia, edicion, mflux, costos, escalado-modelo]
fecha_modificacion: 2026-10-31
estado: activo
---

# Lecciones — Personaje nuevo (Spock) en el estilo de una ilustración de referencia (2026-10-30)

**Pedido:** "Genera una animación similar a esta pero utiliza como referencia a Spock de Star Trek", con una ilustración
adjunta (científico de bata blanca con laptop, cuerpo entero, fondo crema `#f8f7f2`, 291×976). Se interpretó como
**ilustración estática en el mismo estilo**; una versión en video sería otro trabajo.
Proyecto: `proyectos/personaje-spock_30102026/`. Salida final `Xavier-vulcano.png` (768×1376, v11 de `google/gemini-3-pro-image`;
el nombre cambió a petición del usuario tras basar el rostro en su foto), `Xavier-vulcano-recorte.png` y el PNG con alfa
`recursos/xavier-vulcano-alfa.png` (539×1158) que se usó en el reel (`[[Lecciones-2026-10-30-reemplazo-personaje-reel]]`).
Candidatos, prompts y comparativas en `recursos/`. Skill: `[[SKILL#crear-imagen]]`, script nuevo `scripts/imagen.py`.
Cuatro rondas en el día (estilo → rostro y Air Mag → saludo vulcano a mano → saludo vulcano por Gemini 3 Pro):
**14 llamadas, 0.6505 USD** según `recursos/costos.jsonl` (12 × Flash 0.47 USD, 1 × Gemini 3 Pro 0.14 USD, 1 × Nano Banana 2.1 0.04 USD).

## Flujo que funcionó

```mermaid
flowchart LR
    A[Referencia + prompt.md] -->|imagen.py generar --referencia| B[v1: estilo y personaje OK<br/>logo Apple, piel verde, mano plana]
    B -->|edición puntual: v1 como referencia<br/>"keep everything, change ONLY…"| C[v2: logo→estrella, piel pálida,<br/>calcetines dispares]
    A -->|prompt reforzado, otra generación| D[v3: pose más fiel a la referencia,<br/>calcetines iguales]
    C -->|3 intentos de mano<br/>texto · emoji · imagen del gesto| E[v4, v5: mano idéntica]
    C --> F[v2 elegida en la ronda 1<br/>base de las rondas siguientes]
    B & C & D & E --> G[comparativa.png<br/>hstack + drawtext]
```

Cinco llamadas a `google/gemini-2.5-flash-image` vía OpenRouter: **0.1966 USD** en total (0.039 USD y ~8 s cada una).
Registro en `recursos/costos.jsonl` con `usage.cost` real (se pide `"usage": {"include": true}`).

## Qué se aprendió

1. **La referencia viaja con el prompt como `image_url`** y el modelo la usa como guía de estilo, proporciones y
   composición sin img2img ni parámetros extra. Basta acotarla en el texto ("use ONLY as a reference… do NOT reproduce
   that character"). En la primera llamada ya salió el estilo (línea fina, cel shading plano, fondo crema, sombra elíptica).
2. **Edición puntual conservando todo:** pasar la imagen generada como referencia y pedir "keep everything exactly as it
   is… change ONLY: 1) … 2) …" cambió logo, tono de piel y calcetines **sin mover nada más**. Es la forma barata de
   corregir: 0.039 USD por pasada frente a regenerar y volver a evaluar todo.
3. **Los gestos de manos no se corrigen en edición.** El saludo vulcano (dedos en V) quedó como palma plana en la
   generación y **no cambió en tres ediciones**: descripción anatómica, el emoji 🖖 y una imagen del gesto como segunda
   referencia (renderizada con Pillow desde `Apple Color Emoji.ttc`, `embedded_color=True`). Pedir el gesto en la
   generación inicial y regenerar si falla; no insistir en edición.
4. **Logos de marca espontáneos:** la laptop salió con el logo de Apple aunque el prompt decía "no logos other than the
   delta insignia". Hay que prohibirlo por su nombre ("generic laptop with NO brand logo, no apple logo"). Relevante para
   publicar: una marca ajena en la imagen es un problema de derechos.
5. **Los matices se exageran:** "pale skin with a very faint green undertone" dio piel verde; "must NOT look green" lo
   corrigió. Con el modelo, el negativo explícito pesa más que el adjetivo atenuante.
6. **`image_config.aspect_ratio` funciona en OpenRouter** para este modelo: `9:16` → 768×1344. Sin él devuelve 1024×1024.
7. **Presupuesto:** la key principal estaba agotada (505 de 500 USD; renueva el día 1) y Xavier pasó una segunda key
   (tope 200 USD). `GET /api/v1/auth/key` → `limit_remaining` antes de cualquier llamada; el 403 trae `resets_at` y el
   remedio (`openrouter.ai/settings/keys`). El API directo de Gemini **no** tiene nivel gratuito para imagen (0.039 USD).
8. **Alternativas locales (mflux 0.24.0, M3 16 GB):** Anima Turbo (2B anime, 5.7 GB, pico 4.6 GB con `--low-ram`, sin
   referencia) y Z-Image Turbo 4-bit (6B, img2img) caben; FLUX 3 Klein (20 GB, pico 18.5 GB) y Qwen Image 2.1 edit
   (33 GB, licencia Qwen Research) no. Ninguna recibe la referencia como Gemini; son el plan B sin presupuesto.
9. **Verificación visual, no OCR:** `tesseract --psm 11` sobre la ilustración devolvió "CA", "IES" por los stickers de la
   laptop; para "sin texto" vale la hoja comparativa (`hstack` de referencia y versiones a la misma altura + `drawtext`).
10. **Recorte tipo referencia con Pillow:** bbox de los píxeles que difieren del color de fondo (umbral 24) + margen
    6 % / 2.5 %. Con brazos extendidos la relación queda 0.52 (la referencia es 0.30): es el personaje, no el encuadre.
11. **`.env` con `y#` al inicio** de la línea 1 rompía `source .env` en zsh ("no matches found"); el toolkit no lo notaba
    porque `comun.api_key` lee solo la línea de la variable. Corregido.
12. **Deprecación:** Google marca `gemini-2.5-flash-image` para apagado el 2027-03-15 (sucesor Gemini 3.1 Flash Lite
    Image). Migrar `config.json > modelos.imagen` cuando OpenRouter lo liste.

## Segunda ronda (mismo día): el rostro del usuario y los Nike Air Mag

Pedido a mitad del trabajo: "basa al vulcano en mi rostro y foto, no lo pongas con piel azul" + "los tenis Nike de Marty McFly".
Cuatro llamadas más (v6 → v8, 0.16 USD); total del proyecto **9 llamadas, ~0.35 USD**.

13. **Rostro de una persona real por edición:** recortar la foto a cabeza y hombros (sin letreros ni objetos) y pasarla como
    **segunda `--referencia`** junto con la imagen a editar. Decir solo "like the person in the photo" no basta: v6 conservó
    la cara delgada y seria del personaje base y le añadió barba. Hay que nombrar **forma de cara, peinado y expresión**
    ("fuller rounder face with soft cheeks, hair combed back with a side part, warm smile with a hint of teeth"). El mejor
    parecido salió planteándolo como **"cartoon caricature portrait of the person in the photo, using the second image as
    the exact template"** (v7b), con la foto como primera referencia y el personaje como segunda.
14. **El tono de piel nuevo no se propaga a las manos:** tras cambiar la cara, la mano que sostiene la laptop siguió gris
    verdosa; una edición "recolor ONLY that hand… same tone as the face" lo arregló a la primera. Regla: en edición los
    cambios de **color** funcionan (piel, calcetines, stickers); los de **forma de mano** no (lección 3).
15. **Objetos icónicos por descripción:** los Air Mag salieron reconocibles con rasgos ("gray high-tops, wide ankle strap,
    glowing electric-blue LED strips on strap and sole") más la referencia cultural; el modelo respetó los calcetines dispares.
    Marca registrada (Nike): uso personal.
16. **Privacidad:** la foto del usuario viaja al proveedor (OpenRouter → Google) dentro del prompt. Avisarlo y enviar solo el
    recorte necesario.

## Tercera ronda: el saludo vulcano, a mano

17. **Flash no dibuja el 🖖 de ninguna forma:** ni editando la mano (descripción, emoji, foto de Spock: v4, v5, v10) ni
    como mano aislada en su estilo (emoji, foto). Cinco llamadas registradas en `costos.jsonl` (0.20 USD), siempre palma con
    los dedos juntos. No insistir.
18. **Solución geométrica (`recursos/mano_vulcana.py`):** localizar contornos y separaciones de dedos por el perfil de
    píxeles oscuros por columna (x = 197, 206, 216, 227, 237; dedos de 10 px), seguir la línea central fila a fila (los
    dedos se estrechan), y **cizallar cada par hacia fuera** con una afín a 4x y remuestreo bicúbico desde la línea de
    nudillos (desplazamiento 0 en la base, 8 px en la punta), con un parche de piel bajo la base y el contorno interior del
    par derecho trazado a mano. El primer intento con desplazamientos enteros por fila salió escalonado: los trazos planos
    solo se deforman bien a 4x con interpolación. Cuidado con el signo de la afín de PIL (`x_in = x_out + b·y_out + c`):
    la primera versión cerró los pares en vez de abrirlos.

19. **Lo que sí lo resolvió: subir de modelo.** Con la misma edición y la foto de Spock como segunda referencia,
    `google/gemini-3-pro-image` (0.14 USD) dibujó el 🖖 con los pares bien separados y conservó todo lo demás (devuelve
    768×1376, no 768×1344); `google/gemini-nano-banana-2.1` (0.04 USD) también lo dibujó, pero cambió el pantalón a azul
    marino y devolvió JPEG. Versión final = Gemini 3 Pro (v11). Regla: tres fallos de Flash en el mismo detalle → cambiar
    de modelo (`--modelo`), no de prompt; la cizalla manual (18) queda como plan C sin costo.

## Preguntas de `[[AGENT]]` §15

**¿Cómo optimizar imágenes similares?** Pedir en la primera llamada todo lo que no se puede editar (gesto, pose) y
prohibir logos por su nombre; luego corregir detalles por edición puntual, nunca regenerando. Armar la comparativa desde
la segunda versión. Presupuesto esperado: 2–3 llamadas (0.08–0.12 USD) por personaje; con rostro real, 2 más (retrato + mano);
si hay un gesto de manos concreto, ir directo a `google/gemini-3-pro-image` (0.14 USD) en vez de gastar 5 × 0.039 USD en Flash.
Este proyecto costó 0.65 USD porque se aprendió sobre la marcha; repetido, serían ~0.35 USD.

**Entrega.** El PNG final se usó como asset del reel; el alfa limpio (fondo por mediana del borde, componentes ≥ 200 px) está
en `recursos/xavier-vulcano-alfa.png`. Las imágenes caben en el chat sin comprimir; el video no (ver la otra bitácora).

**¿Qué nuevas funciones se usaron?** `scripts/imagen.py` (referencias múltiples, `image_config.aspect_ratio`,
`usage.include` → costo real, avance en el tablero); edición guiada con la imagen generada como referencia; emoji
renderizado con Pillow como referencia visual (no sirvió para la mano, queda como técnica); recorte por bbox contra el
fondo. Verificado todo salvo las alternativas locales (solo evaluadas por ficha, no instaladas).

Relacionado: `[[Lecciones-2026-09-28-banner-hikvision-xml]]` (mismo modelo para ilustraciones sin texto),
`[[Lecciones-2026-10-30-doblaje-reel]]` (OpenRouter sin presupuesto el mismo día).
