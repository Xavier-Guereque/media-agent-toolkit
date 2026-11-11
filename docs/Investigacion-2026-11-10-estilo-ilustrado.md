---
tags: [investigacion, estilo-ilustrado, video-ia, parallax, remotion, blender, mcp]
fecha: 2026-11-10
estado: aplicado (ver [[Motor-Ilustrado]] y [[Lecciones-2026-11-10-estilo-ilustrado]])
---

# Investigación — videos explicativos con animación de estilo ilustrado

Alcance: investigación previa a la integración. Precios consultados el 2026-11-10; cambian cada pocas semanas: leerlos con `python3 scripts/video_ia.py modelos`, no de aquí.

> **Resultado (2026-11-10):** se integró casi todo lo de la sección 9: `scripts/video_ia.py`, `scripts/ilustrar.py`, la composición base `Ilustrado` y las claves `modelos.video*`, `modelos.imagen_ilustrado` e `ilustrado` de `config.json`. La prueba de la sección 8 se hizo (los 5 modelos conservaron el trazo); resultados en [[Lecciones-2026-11-10-estilo-ilustrado]]. No se integró: `@remotion/motion-blur` (el titular usa un desenfoque direccional SVG propio), mapa de profundidad, `rembg` ni fal.

**Cómo leer la confianza de cada dato**

- **[V]** verificado hoy en fuente primaria (API pública del proveedor o su documentación).
- **[S]** fuente secundaria (artículo, comparativa, directorio); puede estar desfasado.
- **[E]** estimación o cálculo mío; no medido.
- **Nada de lo que sigue se probó generando video o imágenes.** La calidad de cada modelo sobre ilustración de tinta es la mayor incógnita y se resuelve con una prueba de ~1 USD (sección 8).

---

## 1. Resumen ejecutivo

**Hallazgo que cambia el punto de partida:** OpenRouter ya expone generación de video (desde abril de 2026) con la misma `OPENROUTER_API_KEY`: `POST /api/v1/videos`, 33 modelos, imagen a video con primer y último cuadro, y costo devuelto en `usage.cost` [V]. `AGENT.md` §6 todavía dice «OpenRouter no tiene modelos de video»; está desactualizado. No hace falta ningún proveedor ni key nueva para el camino principal.

**Recomendación: pipeline híbrido de tres niveles de movimiento, todo dentro de lo que el repo ya tiene.**

1. **Imagen con estilo fijo** — `scripts/imagen.py` ya manda referencias. Usar una «hoja de estilo» (2–4 ilustraciones de referencia + un bloque de prompt idéntico en todas las tomas) con `google/gemini-nano-banana-2.1` (~0.034–0.04 USD por imagen, hasta 14 referencias). Alternativa especializada en estilo: `recraft/recraft-v4-styles` (0.035 USD, exige referencia de estilo).
2. **Movimiento por toma, del más barato al más caro:**
   - **Parallax 2.5D por capas en Remotion** (0 USD de movimiento): fondo, plano medio y figura como capas con perspectiva CSS 3D. Cubre la mayoría de las tomas (empujes de cámara, paneos, entradas de personaje).
   - **Blender NPR** (0 USD) para lo técnico exacto: la ganzúa dentro del candado. Line Art de Grease Pencil + sombreado plano, a 12 fps.
   - **IA de imagen a video solo en las tomas «héroe»** (el dolly de la calle al aparador): `bytedance/seedance-1-5-pro` a 720p sin audio, **~0.026 USD/s** [V, cálculo sobre precio por token], con primer y último cuadro. Respaldo: `google/veo-3.1-lite`, **0.03 USD/s** a 720p sin audio [V].
3. **Tipografía cinética con desenfoque de movimiento en Remotion**: viable hoy; la versión instalada (4.0.539) ya soporta `HtmlInCanvasMotionBlur` en render [V].
4. **Voz, música, subtítulos, mezcla y acabado**: lo que ya existe (`narrar.py`, `componer.py`, `Karaoke.tsx`, FFmpeg).

**Costo esperado** [E]: un Short de 60 s sale en **~1.5 USD** sin IA de video, **~3 USD** híbrido y **~21 USD** premium; un video de 4 min, **~6**, **~11** y **~85 USD** respectivamente (tabla en la sección 3).

**MCPs:** ninguno es necesario para la base. Los scripts que llaman REST directo son más deterministas y registran costos en `costos.jsonl`. El MCP oficial de fal y el de Comfy Cloud sirven para explorar modelos, no para producción.

**Antes de construir nada:** hacer la prueba comparativa de la sección 8 con una ilustración real del estilo. Si Seedance 1.5 Pro «derrite» el contorno de tinta, el orden de modelos cambia y el nivel parallax pesa más.

---

## 2. Cómo se hace hoy este estilo (pipelines reales)

La hipótesis se confirma en lo general, con fuentes secundarias; no encontré un desglose del canal de referencia en particular.

- **Patrón dominante [S]:** imágenes fijas con un modelo de imagen que acepta referencias (Nano Banana / Nano Banana Pro, GPT Image) → imagen a video (Kling, Seedance, Veo) → voz (ElevenLabs) → edición en CapCut. Lo repiten tutoriales de [Kling + Nano Banana](https://lilys.ai/es/notes/nano-banana-pro-20260119/kling-nanobanana-ai-animated-stories), un [curso de Domestika sobre eventos históricos con Nano Banana Pro y Seedance](https://api-domestika.x-solutions.workers.dev/en/courses/6378-create-videos-of-historical-events-with-nano-banana-pro-and-seedance-in-higgsfield) y guías de [canales sin rostro](https://higgsfield.ai/blog/start-faceless-channel-with-ai).
- **Consistencia [S]:** hoja de personaje con varios ángulos antes de animar; un bloque fijo de referencias repetido palabra por palabra y solo cambia la descripción de la escena ([guía de consistencia de Nano Banana 2.1](https://runware.ai/docs/models/google-nano-banana-2-1/guides/subject-consistency)).
- **Primer y último cuadro [S]:** se usa para encadenar tomas y para controlar el destino del movimiento de cámara.
- **Precedente directo con Claude Code [V, README]:** [hassancs91/claude-faceless-shorts-creator](https://github.com/hassancs91/claude-faceless-shorts-creator) (MIT). Tres pistas: Remotion puro en TSX; pista generativa con un modelo de video de fal; y **pista «collage» estilo documental con capas de imagen IA recortadas (rembg) y cámara en movimiento**, que es justo el nivel parallax que propongo. Vale la pena leer su `ai-shorts/IDEAS.md` (tablas de costo por segundo y la regla de anunciar el costo antes de gastar).
- **Lo que no encontré:** ninguna fuente que documente cómo conservar un contorno de tinta irregular y textura de lápiz al pasar por imagen a video. Es el riesgo técnico principal.

---

## 3. Tabla de costos

### 3.1 Imagen a video en OpenRouter [V]

Fuente: `GET https://openrouter.ai/api/v1/videos/models` (consultado hoy, sin key) y la [comparativa del blog de OpenRouter](https://openrouter.ai/blog/insights/image-to-video-models-compared/) (actualizada 2026-10-15). Precio en USD por segundo de video generado.

| Modelo (id OpenRouter) | 480p | 720p | 1080p | Duración | Primer / último cuadro | 9:16 | Notas |
|---|---|---|---|---|---|---|---|
| `bytedance/seedance-1-5-pro` | ~0.012 | **~0.026** | ~0.058 | 4–12 s | sí / sí | sí | Sin audio; con audio el doble. Precio por token: ver nota |
| `google/veo-3.1-lite` | — | **0.03** | 0.05 | 4, 6 u 8 s | sí / sí | sí | Sin audio; con audio 0.05 / 0.08 |
| `x-ai/grok-imagine-video-1.5-lite` | 0.02 | 0.03 | 0.14 | 1–15 s | sí / no | sí | + 0.01 por imagen de entrada |
| `heygen/heygen-video-1` | 0.02 | 0.036 (768p) | 0.10 | 5–30 s | sí / no | sí | Con imágenes de referencia sube a 0.07–0.18 |
| `minimax/hailuo-3-max` | 0.05 | 0.08 (768p) | — | 5–15 s | sí / sí | sí | Sin audio |
| `bytedance/seedance-2.0-mini` | ~0.034 | ~0.076 | — | 4–15 s | sí / sí | sí | Acepta referencias de imagen, video y audio |
| `bytedance/seedance-2.0-fast` | ~0.040 | ~0.091 | — | 4–15 s | sí / sí | sí | |
| `kwaivgi/kling-v3.0-std` | — | 0.084 | — | 3–15 s | sí / sí | sí | Con audio 0.126 |
| `google/veo-3.1-fast` | — | 0.08 | 0.10 | 4–8 s | sí / sí | sí | Sin audio; 4K 0.25 |
| `alibaba/wan-3.0` | 0.05 | 0.10 | 0.20 | 2–30 s | sí / sí | sí | |
| `alibaba/wan-2.7` | — | 0.10 | 0.10 | 2–10 s | sí / sí | sí | |
| `kwaivgi/kling-v3.0-pro` | — | **0.112** | — | 3–15 s | sí / sí | sí | Con audio 0.168; solo 720p en OpenRouter |
| `runway/gen-4.5` | — | 0.12 | — | 2–10 s | sí / no | sí | |
| `minimax/hailuo-3` | — | — | 0.13 (2K) | 5–15 s | sí / sí | sí | + 0.04 por imagen de referencia |
| `bytedance/seedance-2.0` | ~0.067 | ~0.151 | ~0.374 | 4–15 s | sí / sí | sí | |
| `black-forest-labs/flux-3-video` | — | 0.17 | 0.29 | 5–20 s | sí / sí | sí | |
| `google/veo-3.1` | — | 0.20 | 0.20 | 4–8 s | sí / sí | sí | Con audio 0.40 |
| `bytedance/seedance-2.5` | ~0.103 | ~0.231 | — | 4–30 s | sí / sí | sí | Hasta 50 referencias |
| `tbc/mischief-1` | 0.005 | 0.01 | — | 3 o 5 s | sí / no | **no** (solo 16:9) | El más barato; modelo nuevo, sin referencias de calidad |

**Nota sobre Seedance [E sobre V]:** OpenRouter lo cobra por token de video (`video_tokens_without_audio`: 0.0000012 USD para 1.5 Pro). Tokens = ancho × alto × 24 fps × segundos / 1024. A 720p son 21 600 tokens/s. La fórmula reproduce los precios «desde» que publica OpenRouter a 480p (0.0115 y 0.0336), así que el cálculo a 720p y 1080p es fiable, pero conviene confirmarlo con el `usage.cost` de la primera llamada real.

**Control de cámara:** ninguna fuente oficial lo tabula. En todos se pide por prompt («slow dolly in…»); el control real viene del **primer + último cuadro**. Kling tiene además parámetros propios de cámara en su API directa, no expuestos en OpenRouter (solo `negative_prompt` y `cfg_scale` como passthrough) [V].

### 3.2 Otras vías de pago por uso

| Vía | Precios representativos (USD/s) | Confianza | Comentario |
|---|---|---|---|
| **fal.ai** | Kling 3.0 Pro 0.112; Kling 2.6 Pro 0.07; Veo 3.1 0.20; Veo 3.1 Fast 0.10; Grok Imagine 0.05–0.07; Seedance 2.0 0.30 a 720p con audio | [S] [artículo de fal, 2026-06-28](https://fal.ai/learn/tools/best-image-to-video-apis-2026) | Mismo precio que OpenRouter en Kling y Veo. Ventaja: catálogo más amplio (LoRA, capas, profundidad) y MCP oficial |
| **Replicate** | Veo 3.1 0.20; Veo 3.1 Fast 0.10; Wan 3.0 0.025–0.10 según tabla (listado contradictorio) | [S] | Sin ventaja de precio clara |
| **Kling directo** | 0.6 / 0.8 Units/s a 720p / 1080p = 0.084 / 0.112 con Unit a 0.14 | [S] [comparativa del 2026-10-18](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026) | Requiere comprar paquetes de Units; da 1080p y controles de cámara |
| **Google directo (Gemini API / Vertex)** | Veo 3.1 Lite 0.05 con audio, 0.03 sin audio en Vertex; Veo 3.1 Fast 0.10 | [S] | Igual que OpenRouter |
| **BytePlus (Seedance directo)** | 2.0: ~0.07 a 480p; 2.5: ~0.103 a 480p | [S, estimaciones de la propia página] | Igual que OpenRouter |
| **Alibaba Model Studio** | `wan2.6-i2v-flash` 0.025 a 720p sin audio; `wan2.2-i2v-flash` 0.015 a 480p | [S] | El más barato con marca conocida, pero key y cuenta aparte |
| **Runway** | Gen-4 Turbo 0.05; Gen-4.5 0.12; Aleph 2 0.28 | [S] | Gen-4.5 también está en OpenRouter |
| **Luma** | Ray2 ~0.06–0.24 según plan y resolución; 1.50 en Bedrock | [S, cifras contradictorias] | No recomendable por precio |
| **MiniMax directo** | Hailuo 2.3: 0.28 por clip de 6 s a 768p en Runware | [S] | Hailuo 3 Max ya está en OpenRouter |

**Conclusión:** OpenRouter iguala el precio directo en casi todo y evita keys nuevas. Solo fal aporta algo que OpenRouter no tiene (separación en capas, LoRA de estilo).

### 3.3 Imagen en OpenRouter

Fuente: `GET /api/v1/models?output_modalities=image` [V para el precio por token]. El precio por imagen de los modelos que cobran por `image_token` lo derivé con 4 175 tokens por imagen de ~1 MP [E]; coincide con el precio oficial de Recraft V4 Styles (0.035) y de Riverflow Pro (0.13).

| Modelo | USD por imagen (~1K) | Referencias de estilo | Comentario |
|---|---|---|---|
| `black-forest-labs/flux-3-image-klein` | ~0.008 [E] (0.009 oficial [S]) | Edición multirreferencia | Borradores baratos |
| `meta/muse-image` | ~0.010 [E] | Acepta imagen | Sin datos de calidad |
| `bytedance-seed/seedream-5-0-flash` | ~0.018 [E] | Acepta imagen | |
| `google/gemini-nano-banana-2.1` | **0.034** [S oficial Google] / 0.04 medido en el repo | **Hasta 14 imágenes** (4 personajes, 10 objetos) [S] | Recomendado. Devuelve JPEG y puede cambiar colores (bitácora Spock) |
| `recraft/recraft-v4-styles` | **0.035** [V docs Recraft] | **Obligatoria**: 1–10 imágenes o `style_id` reutilizable | Especialista en estilo. Cómo viaja la referencia por OpenRouter: sin verificar |
| `google/gemini-2.5-flash-image` (actual en `config.json`) | 0.039 [V repo] | Sí | Deprecado; se apaga 2027-03-15 según la skill `crear-imagen` |
| `google/gemini-3.1-flash-lite-image` | ~0.04 [E] | Sí | Sucesor barato |
| `black-forest-labs/flux-3-image` | ~0.041 [E] | Sí | |
| `openai/gpt-image-2` | 0.006 / 0.053 / 0.211 según calidad [S] | Sí | Caro en calidad alta |
| `recraft/recraft-v4-styles-pro` | 0.10 [V] | Obligatoria | 2K |
| `google/gemini-3-pro-image` | **0.134** [S] / 0.14 medido en el repo | Sí (objetos, personajes y estilo) | Premium: manos, gestos, detalle |

**Otras formas de fijar estilo:**

- **LoRA de estilo en fal:** ~2 USD por entrenamiento de 1 000 pasos (FLUX.1), 5 USD para FLUX.2 klein [S, páginas de fal](https://www.fal.ai/models/fal-ai/flux-lora-fast-training). Máxima consistencia, pero exige `FAL_KEY`, 15–30 imágenes propias del estilo y sale del camino OpenRouter. Reservarlo para una serie larga.
- **Midjourney `--sref`:** sin API oficial; no integrable.

### 3.4 Costo estimado por pieza [E]

Supuestos: una toma cada ~4 s (15 tomas por minuto); cada imagen se genera 2 veces de media; cada clip de IA de video se genera 2 veces (2.5 en premium); voz Gemini TTS y JEV despreciables (< 0.10 USD); música CC0 o procedural a 0 USD. No incluye el costo de la sesión del agente.

| Escenario | Qué usa | Short 60 s | Video 4 min |
|---|---|---|---|
| **Barato** — sin IA de video | Nano Banana 2.1 (30 imágenes) + parallax 2.5D + Blender NPR. Capas pidiendo fondo y figura por separado al mismo modelo (+10 imágenes) | **~1.5 USD** | **~6 USD** |
| **Equilibrado** — híbrido | Lo anterior + IA de video en el 40 % del metraje (24 s) con Seedance 1.5 Pro 720p: 48 s generados × 0.026 | **~3 USD** | **~11 USD** |
| Equilibrado, todo con IA de video barata | 120 s generados × 0.026 + imágenes | ~4.5 USD | ~17 USD |
| **Premium** | Gemini 3 Pro Image (30 × 0.134) + Kling 3.0 Pro en todo el metraje (150 s generados × 0.112) | **~21 USD** | **~85 USD** |
| Premium con Veo 3.1 completo | 150 s × 0.20 + imágenes | ~34 USD | ~135 USD |

El factor que más mueve el total es **cuántas veces se repite cada clip**, no el modelo. Con 4 intentos por clip el escenario equilibrado se duplica.

---

## 4. Alternativas sin IA de video

### 4.1 Parallax 2.5D por capas (recomendado como base)

- **Qué es:** cada ilustración se separa en 2–4 capas (cielo/fondo, plano medio, figura, primer plano) y se colocan a distinta profundidad con `perspective` + `translateZ` de CSS en Remotion. Al mover la cámara virtual, las capas se desplazan con perspectiva real. Es DOM puro: determinista, sin WebGL, y encaja con las reglas del TSX del repo.
- **Cómo obtener las capas, de menor a mayor dependencia:**
  1. **Pedirlas por separado al modelo de imagen** con la misma hoja de estilo: «solo el fondo, sin personajes» y «solo la figura sobre fondo uniforme», y recortar con `colorkey`. La receta ya está verificada en la skill `crear-imagen` (banner Hikvision). Sin software nuevo.
  2. **Recorte local con `rembg`** (MIT; modelos U2Net/BiRefNet en CPU) y rellenar el hueco del fondo con una edición puntual («remove the character, keep everything else»).
  3. **Qwen-Image-Layered en fal:** descompone una imagen en 1–10 capas RGBA por 0.05 USD [S, página de fal](https://fal.ai/models/fal-ai/qwen-image-layered). Lo más cómodo, pero requiere `FAL_KEY`.
- **Cuánto se acerca [E]:** muy bien en empujes, paneos y revelados con 3–4 capas; es lo que hace la animación documental tradicional. **No** produce cambio de punto de vista dentro de un objeto (rodear un aparador, entrar por una puerta): ahí hace falta IA de video o Blender.

### 4.2 Mapa de profundidad + desplazamiento

- **Qué es:** estimar profundidad de la imagen fija y desplazar los píxeles según la cámara.
- **Herramientas:** Depth Anything V2 **Small es Apache-2.0; Base, Large y Giant son CC-BY-NC** (no comerciales) [V, repo oficial](https://github.com/DepthAnything/Depth-Anything-V2). Hay exportaciones ONNX. En el i7-1355U estimo 0.5–2 s por imagen [E, sin benchmark]. `onnxruntime` no está instalado en esta máquina [V].
- **[DepthFlow](https://github.com/BrokenSource/DepthFlow):** hace exactamente esto con un shader; licencia **AGPL-3.0** [S] y pensado para GPU (su referencia es una RTX 3060); en Iris Xe está sin verificar. Mejor implementar el shader propio (20 líneas de GLSL en un `<canvas>` de Remotion) que depender de AGPL.
- **Cuánto se acerca [E]:** en ilustración plana da el típico «estirado» en los bordes de las figuras con movimientos de más de ~3–4 % del ancho. Sirve para dar vida sutil a una toma, no para un dolly. **Por debajo del parallax por capas en este estilo**; dejarlo como opción secundaria.
- **Con FFmpeg solo:** el filtro `displace` permite un desplazamiento básico, pero sin oclusión ni relleno; no lo recomiendo.

### 4.3 Animación de partes

- En Remotion: rotar o trasladar capas recortadas (un brazo, una llave) con pivote, y deformar con `transform` o mallas simples. Suficiente para gestos pequeños.
- En Blender: ganchos (Hook) y armaduras sobre planos con la ilustración como textura, o Grease Pencil. Más control, más trabajo por toma.
- Truco de bajo costo que acerca mucho al look: animar **a 12 fps** («a doses») y aplicar una textura de papel con un «hervor» leve del contorno. Unifica capas, clips de IA y renders de Blender.

---

## 5. Tipografía cinética con desenfoque de movimiento en Remotion: viable

- **`HtmlInCanvasMotionBlur`** (paquete `@remotion/motion-blur`): promedia varias muestras por cuadro; es la implementación que Remotion recomienda. Disponible desde 4.0.529; el render en servidor no necesita configuración; props `samples` (8 por defecto, 1–64) y `shutterAngle` (180 por defecto) [V, docs](https://www.remotion.dev/docs/motion-blur/html-in-canvas-motion-blur). El repo tiene `remotion` **4.0.539** [V, `remotion/package.json`], así que basta agregar `@remotion/motion-blur` en la misma versión.
- **Límites [V]:** la vista previa en Studio exige activar la bandera HTML-in-canvas de Chrome; la API subyacente es experimental; el componente que anima debe llamar `useCurrentFrame()` **dentro** del envoltorio ([error común](https://www.remotion.dev/docs/motion-blur/common-mistake)).
- **Costo [E]:** el render de esos cuadros se multiplica por `samples`. Mitigación: envolver solo la capa del titular y usar la prop `disabled` fuera de los 6–10 cuadros de entrada.
- **Respaldos:** `CameraMotionBlur` (funciona sin la bandera, puede alterar colores y opacidad) y `Trail` (estela estilizada) [V]. Alternativa casi gratuita: desenfoque direccional con filtro SVG `feGaussianBlur stdDeviation="x 0"` proporcional a la velocidad [E].
- Sin probar en esta máquina.

---

## 6. Blender para lo técnico exacto con look ilustrado

El MCP oficial de Blender ya está conectado (Blender Lab; v1.0.x en 2026, requiere Blender 5.1+ [S](https://www.strayspark.studio/blog/official-blender-mcp-server-comparison-2026)). Está orientado a inspección y scripting, que es justo lo que se necesita; el render final debe seguir yendo por `blender -b -P` como en la bitácora de drywall.

Receta NPR propuesta [E; técnicas estándar de Blender, sin probar en este equipo]:

- **Contorno:** objeto Grease Pencil con modificador **Line Art** sobre la colección, más modificador **Noise** con semilla por paso para el trazo irregular, y grosor variable. Alternativa: Freestyle. El manual avisa de que apilar varios Line Art alarga mucho la evaluación [V, manual](https://docs.blender.org/manual/en/latest/grease_pencil/modifiers/generate/line_art.html).
- **Color plano:** Shader to RGB + ColorRamp de 2 tonos (solo Eevee), sin sombras suaves ni AO.
- **Rendimiento:** con materiales planos se puede bajar Eevee a 1–4 muestras, y animar a 12 fps reduce los cuadros a la mitad. Frente a los 3–4.7 s por cuadro medidos con 20–32 muestras, espero una mejora grande, pero hay que medirla.
- **Textura de lápiz y papel:** mejor fuera de Blender, como capa `multiply` en Remotion compartida por toda la pieza.
- **Idea híbrida para la toma del candado:** render NPR de Blender como **primer y último cuadro geométricamente exactos** → una edición con el modelo de imagen para llevarlos al estilo de la casa → imagen a video con primer + último cuadro para interpolar. La exactitud viene de Blender; el acabado, de la IA. Costo: 2 imágenes + ~5 s de video ≈ 0.20 USD [E].

---

## 7. Herramientas y MCPs evaluados

| Herramienta | Qué es | Madurez | Licencia | Costo | Encaje |
|---|---|---|---|---|---|
| **API de video de OpenRouter** | `POST /api/v1/videos`, sondeo, descarga con la key | En producción desde abril de 2026 [V](https://openrouter.ai/docs/guides/overview/multimodal/video-generation) | Servicio | Tabla 3.1 | **Camino principal.** Misma key, `usage.cost` |
| [MCP de fal](https://fal.ai/docs/model-apis/mcp) | Servidor alojado `mcp.fal.ai/mcp`; busca modelos, lee esquema, ejecuta, sube archivos | Oficial [V docs]. Clave por cabecera; hay un relé OAuth más nuevo listado por terceros | Servicio | Uso de fal | Opcional: explorar modelos, capas, LoRA. Requiere `FAL_KEY` |
| [MCP de Replicate](https://mcp.replicate.com/) | Servidor alojado oficial + paquete local `replicate-mcp` | Oficial; en el registro MCP [S] | MIT según terceros | Uso de Replicate | Opcional; sin ventaja sobre fal |
| [Comfy Cloud MCP](https://support.comfy.org/articles/4321955727-agent-tools-mcp-comfy-cloud-mcp) | Ejecuta flujos de ComfyUI en GPU de nube | Beta pública desde 2026-06-30 [S] | ComfyUI GPL-3.0; servicio de pago | Gratis 400 créditos/mes; planes desde ~20 USD/mes [S] | Para flujos a medida (ControlNet de línea, Wan con LoRA). Suscripción: peor que pago por uso para piezas esporádicas. No guarda archivos en local |
| [RunComfy](https://www.runcomfy.com/pricing) | ComfyUI alojado, GPU por segundo | Comercial | Servicio | Por hora de GPU | Solo si se necesita un flujo ComfyUI concreto |
| MCP oficial de Blender | Inspección y `bpy` | v1.0.x, Blender Lab | GPL (Blender) | 0 USD | **Ya conectado.** Tomas técnicas NPR |
| Rive ([Polymation/`rivemcp`](https://www.npmjs.com/package/rivemcp) y otros) | Genera `.riv` desde un agente | Comunitarios; sin MCP oficial de Rive [S] | MIT (rivemcp) | 0 USD | Poco: Rive brilla en interactividad, no en video ilustrado |
| [LottieFiles MCP](https://lottiefiles.com/mcp) y Lottie Creator MCP | Gestionar y dibujar animaciones Lottie | Oficiales [S]; el Creator necesita una pestaña abierta | Servicio | Plan de LottieFiles | Marginal: íconos y adornos vectoriales; Remotion ya reproduce Lottie |
| [Manim MCP](https://github.com/abhiemj/manim-mcp-server) | Animación matemática por código | Comunitario | MIT [S] | 0 USD | Solo para explicaciones matemáticas; estética opuesta a la buscada |
| [Motion Canvas](https://motioncanvas.io/) | Animación por código sobre un canvas | Estable | MIT [S](https://www.remotion.dev/docs/compare/motion-canvas) | 0 USD | Alternativa libre a Remotion si la licencia de empresa llegara a estorbar; migrar ahora no compensa (dos motores ya construidos) |
| Remotion | Motor actual | 4.0.539 instalado | Gratis ≤ 3 personas; Company License para 4+ | 0 / 25 USD por asiento | **Se queda** como motor de composición |
| [VectCutAPI](https://github.com/sun-guannan/VectCutAPI) (CapCut) | Genera borradores de CapCut por API/MCP | ~2 mil estrellas [S] | Apache-2.0 | 0 USD | No: escribe borradores, no renderiza; FFmpeg + Remotion ya cubren la edición |
| [DepthFlow](https://github.com/BrokenSource/DepthFlow) | Parallax por mapa de profundidad | Activo | AGPL-3.0 [S] | 0 USD | Referencia de técnica; no integrar por licencia y GPU |
| [Depth Anything V2 Small](https://github.com/DepthAnything/Depth-Anything-V2) | Profundidad monocular | Estable | Apache-2.0 (solo Small) [V] | 0 USD | Opcional para el nivel de profundidad |
| `rembg` | Recorte de figura en CPU | Estable | MIT | 0 USD | Opcional para capas |
| [claude-faceless-shorts-creator](https://github.com/hassancs91/claude-faceless-shorts-creator) | Skills de Claude Code + Remotion + fal + ElevenLabs | Repo de referencia con 12 ejemplos | MIT | — | Fuente de ideas: pista collage, tabla de costos, regla de anunciar el gasto |

**Modelos locales de video (Wan, LTX, Hunyuan, ComfyUI):** no viables en Iris Xe; solo en nube, y ahí no mejoran el precio de Seedance 1.5 Pro o Veo 3.1 Lite. No buscados después Krita, Inkscape ni After Effects: no aportan a un pipeline por scripts.

---

## 8. Prueba comparativa previa (≈ 1 USD)

Antes de fijar `modelos.video`, con **una** ilustración real del estilo y el mismo prompt de dolly:

| Modelo | Config | Costo |
|---|---|---|
| `bytedance/seedance-1-5-pro` | 720×1280, 5 s, sin audio, primer + último cuadro | ~0.13 |
| `google/veo-3.1-lite` | 720p, 4 s, sin audio, primer + último cuadro | 0.12 |
| `x-ai/grok-imagine-video-1.5-lite` | 720p, 5 s | 0.16 |
| `minimax/hailuo-3-max` | 768p, 5 s | 0.40 |
| `kwaivgi/kling-v3.0-pro` (techo de calidad) | 720p, 5 s | 0.56 |

Criterios: ¿conserva el contorno de tinta y la textura?, ¿inventa volumen 3D o realismo?, ¿la cámara hace lo pedido?, ¿llega al último cuadro sin «fundido»? Esto, más una toma de parallax por capas de la misma imagen, decide el reparto real entre niveles.

---

## 9. Propuesta de integración en la base del repo

Requiere que el usuario diga «esto va en la versión base del repo» (AGENT §16). Sigue los patrones existentes: el agente escribe un JSON, el motor valida y renderiza, costos a `costos.jsonl`, avance al tablero.

### 9.1 Scripts nuevos

- **`scripts/video_ia.py`** — imagen a video por OpenRouter. Espejo de `imagen.py`.
  - `generar --primer-cuadro a.png [--ultimo-cuadro b.png] --prompt-archivo p.md --duracion 5 --resolucion 720p --relacion 9:16 [--modelo …] [--borrador] --salida …`
  - `POST /api/v1/videos` con `frame_images` (`frame_type`: `first_frame` / `last_frame`), `generate_audio: false`, `seed`; sondeo cada ~30 s; descarga de `unsigned_urls` con la cabecera de autorización [V].
  - `modelos` — lista `GET /videos/models` con precio por segundo calculado, para no fijar precios en la documentación.
  - `estimar` — costo previo; se niega a gastar por encima de un tope sin `--confirmar`.
  - `--borrador` = 480p (Seedance 1.5 Pro ~0.012 USD/s) para iterar el prompt antes del clip final.
  - Códigos de salida 0/2/3/4, `usage.cost` a `costos.jsonl`, etapa `video_ia` en el tablero. Código compatible con Windows (reglas de AGENT §3b).
- **`scripts/ilustrar.py`** — orquestador del explicador ilustrado; el agente solo escribe `ilustrado.json`.
  - `nuevo | validar | estilo | imagenes | capas | movimiento | componer | qa | render | todo`.
  - `estilo`: fija la hoja de estilo en `recursos/estilo/` (`estilo.md` con el bloque de prompt fijo + `ref_*.png`) y la reutiliza en todas las llamadas a `imagen.py`.
  - `capas`: fondo y figura por separado + `colorkey`; `rembg` o fal si están disponibles.
  - `movimiento` por toma: `fija` | `parallax` | `profundidad` | `video_ia` | `blender`.
  - `validar`: lints sin LLM (toda toma con estilo, texto nunca dentro de la imagen, duración de clip dentro de lo que soporta el modelo, costo estimado total).
  - Reutiliza `narrar.py` (tiempos medidos), `componer.py` (mezcla) y `remotion.py` (render y acabado).
- **`scripts/capas.py`** (opcional, puede vivir dentro de `ilustrar.py`): recorte, relleno de fondo y mapa de profundidad.

### 9.2 Remotion

- Composición BASE **`Ilustrado.tsx`** (declarativa, pinta `props.tomas` por tipo, como `Leccion`).
- Componentes: `Parallax25D.tsx` (capas con perspectiva CSS 3D y cámara con `muelle`), `ClipIA.tsx` (`OffthreadVideo`), `TituloCinetico.tsx` (palabra por palabra + `HtmlInCanvasMotionBlur`, con respaldo `CameraMotionBlur`), `TexturaPapel.tsx` (grano, `multiply`, hervor a 12 fps), `ProfundidadGL.tsx` (opcional).
- Dependencia nueva: `@remotion/motion-blur@4.0.539`.

### 9.3 `config.json`

```json
"openrouter": { "endpoints": { "video": "/videos", "video_modelos": "/videos/models" } },
"modelos": {
  "imagen": "google/gemini-nano-banana-2.1",
  "imagen_estilo": "recraft/recraft-v4-styles",
  "imagen_premium": "google/gemini-3-pro-image",
  "video": "bytedance/seedance-1-5-pro",
  "video_respaldo": "google/veo-3.1-lite",
  "video_premium": "kwaivgi/kling-v3.0-pro"
},
"ilustrado": {
  "fps_animacion": 12,
  "video_resolucion": "720p",
  "video_borrador": "480p",
  "video_audio": false,
  "intentos_max_por_toma": 3,
  "tope_usd_por_pieza": 5
},
"herramientas": { "video_ia": { … }, "explicador_ilustrado": { … } },
"software": { "opcional": { "rembg": "…", "onnxruntime + depth-anything-v2-small": "…", "blender": "…" } }
```

Los ids de `video` quedan pendientes de la prueba de la sección 8. Cambiar `modelos.imagen` es además necesario por la deprecación de `gemini-2.5-flash-image`.

### 9.4 Documentación y skills

- **Corregir** en `AGENT.md` §6 la frase «OpenRouter no tiene modelos de video» y la nota equivalente en `Lecciones-2026-10-31-remotion-y-longcat` (añadir aviso, no reescribir la bitácora).
- `AGENT.md`: §6 (nueva ruta), §7 (claves `modelos.video*`), §12 (rama «¿explicador ilustrado?» en el diagrama).
- `SKILL.md`: skills **`explicador-ilustrado`** (cuestionario: tema, estilo de referencia, orientación, duración, presupuesto, cuántas tomas héroe) y **`animar-imagen`** (uso suelto de `video_ia.py`).
- `docs/Motor-Ilustrado.md` (contratos, tipos de toma, receta NPR de Blender), `docs/Video-IA.md` (cómo refrescar precios, prompts de cámara, primer + último cuadro), bitácora `Lecciones-<fecha>-estilo-ilustrado.md`, enlaces en `Home.md`.
- `scripts/enrutar.py`: ruta `explicador_ilustrado` («video de historia ilustrado», «animación tipo dibujo»).
- `costo_generacion.py`: sumar las líneas `video_ia`.

### 9.5 Variables de entorno opcionales (nunca pedirlas)

- `FAL_KEY` — capas con Qwen-Image-Layered, LoRA de estilo, MCP de fal.
- `REPLICATE_API_TOKEN` — alternativa a fal.
- Ninguna es necesaria: el camino completo funciona con `OPENROUTER_API_KEY`.

---

## 10. Riesgos

**Calidad y consistencia**

- **Deriva de estilo en imagen a video (el principal, sin medir):** los modelos tienden a suavizar el trazo, añadir volumen o «hervir» texturas. Mitigar con clips de 4–5 s, primer + último cuadro, prompt que pida solo movimiento de cámara, y la capa de textura a 12 fps que iguala todo.
- **Consistencia entre tomas:** depende de repetir la hoja de estilo en cada llamada. Nano Banana 2.1 cambió colores en la bitácora de Spock; revisar con hojas de contacto.
- **Texto:** nunca dentro de la imagen ni del clip; siempre en Remotion (regla que el repo ya aplica).
- **`seed`:** OpenRouter advierte que no todos los proveedores lo respetan [V]; un borrador a 480p no garantiza el mismo movimiento a 720p.
- **Resolución:** el camino barato es 720p; en ilustración plana el escalado a 1080p con FFmpeg debería bastar [E], pero hay que verlo.

**Costo de iterar**

- El gasto real lo fija el número de reintentos. Poner tope por pieza, borrador a 480p y aprobación de la imagen fija **antes** de pagar su video.
- Los precios cambian cada pocas semanas (dos comparativas de octubre ya difieren en Kling Std). Leerlos de `/videos/models` en cada sesión, no de la documentación.
- Comprobar el saldo antes (`/auth/key`), como ya manda AGENT §4.

**Licencias y términos**

- **Derechos de uso comercial de las salidas:** no verifiqué las cláusulas de cada proveedor; las fuentes encontradas son secundarias. En general los proveedores no reclaman la propiedad pero tampoco garantizan originalidad ni exclusividad, y algunos (MiniMax) se reservan usar entradas y salidas para mejorar el servicio [S]. **Revisar los términos de ByteDance/BytePlus, Google y Kuaishou antes de un uso comercial.**
- **Privacidad:** el video en OpenRouter **no admite Zero Data Retention** [V]. No enviar imágenes con datos personales ni material de `muestras/`.
- **Marcas de agua:** Seedance expone `watermark` y Hailuo `aigc_watermark` como parámetros de proveedor [V]; fijarlos explícitamente. Veo incrusta marca invisible SynthID (conocimiento general, no verificado hoy).
- **YouTube:** desde el 2026-07-16 la política de «contenido inauténtico» se evalúa por canal; la IA no está prohibida, sí la producción en serie con poca aportación original [S](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/). Los requisitos exactos de divulgación de contenido sintético: consultar la ayuda oficial.
- **Estilo de un canal ajeno:** usar sus fotogramas como referencia de estilo para un producto propio tiene riesgo reputacional y legal. Mejor construir una hoja de estilo propia inspirada en la técnica (tinta, color plano, lápiz), no en sus imágenes.
- **Software:** Depth Anything V2 Base/Large son **no comerciales** (usar solo Small); DepthFlow es **AGPL-3.0**; Remotion exige Company License con 4+ empleados; ComfyUI es GPL-3.0; VoiceStudio sigue siendo CC-BY-NC.
- **Hechos históricos:** los modelos inventan vestuario, objetos y rótulos de época; hace falta revisión humana de cada imagen.

---

## 11. Fuentes principales

- OpenRouter — [catálogo de modelos de video (API)](https://openrouter.ai/api/v1/videos/models), [documentación de generación de video](https://openrouter.ai/docs/guides/overview/multimodal/video-generation), [comparativa de imagen a video](https://openrouter.ai/blog/insights/image-to-video-models-compared/), [anuncio](https://openrouter.ai/blog/announcements/video-generation/), [modelos de imagen (API)](https://openrouter.ai/api/v1/models?output_modalities=image)
- fal — [mejores API de imagen a video 2026](https://fal.ai/learn/tools/best-image-to-video-apis-2026), [MCP](https://fal.ai/docs/model-apis/mcp), [Qwen-Image-Layered](https://fal.ai/models/fal-ai/qwen-image-layered), [entrenamiento LoRA](https://www.fal.ai/models/fal-ai/flux-lora-fast-training)
- [Comparativa de precios de 19 proveedores, 2026-10-18](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- Recraft — [V4 Styles](https://www.recraft.ai/docs/api-reference/models/recraft-v4-styles)
- Google — [Nano Banana 2.1](https://ai.google.dev/gemini-api/docs/models/gemini-nano-banana-2.1)
- Remotion — [guía de motion blur](https://www.remotion.dev/docs/motion-blur-guide), [HtmlInCanvasMotionBlur](https://www.remotion.dev/docs/motion-blur/html-in-canvas-motion-blur), [frente a Motion Canvas](https://www.remotion.dev/docs/compare/motion-canvas)
- Comfy — [Comfy Cloud MCP](https://support.comfy.org/articles/4321955727-agent-tools-mcp-comfy-cloud-mcp), [precios](https://comfy.org/cloud/pricing); [RunComfy](https://www.runcomfy.com/pricing)
- [MCP de Replicate](https://mcp.replicate.com/); [LottieFiles MCP](https://lottiefiles.com/mcp); [manim-mcp-server](https://github.com/abhiemj/manim-mcp-server); [VectCutAPI](https://github.com/sun-guannan/VectCutAPI)
- [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2); [DepthFlow](https://github.com/BrokenSource/DepthFlow)
- [Blender — modificador Line Art](https://docs.blender.org/manual/en/latest/grease_pencil/modifiers/generate/line_art.html); [MCP oficial de Blender, comparativa](https://www.strayspark.studio/blog/official-blender-mcp-server-comparison-2026)
- [claude-faceless-shorts-creator](https://github.com/hassancs91/claude-faceless-shorts-creator)
- Repo: `AGENT.md`, `SKILL.md` (skills `crear-imagen`, `remotion-video`), `config.json`, `remotion/package.json`, `docs/Lecciones-2026-11-10-curso-drywall.md`
