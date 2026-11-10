---
tags: [lecciones, motor-promo, orquestador, playwright, determinismo, qa]
fecha_modificacion: 2026-09-28
estado: activo
---

# Lecciones 2026-09-28 — Motor promo para orquestadores baratos

Contexto: se construyó el motor `promo/` + `scripts/promo.py` para que un orquestador barato
(`deepseek/deepseek-v4.1-flash`) produzca videos con el acabado del video de referencia de la casa
(promo de asistente IA con UI animada, 9:16, 30 s). Arquitectura en [[Motor-Promo]]; uso en la skill
`promo-ui` de [[SKILL]].

## 1. La calidad no se le pide al modelo: se le quita trabajo

- El modelo solo escribe contenido (`promo.json`). Tiempos, animación, color, audio y QA viven en código.
- **Medido con el arnés E2E** (`scripts/e2e_orquestador.py`, mismo brief):

  | Versión | Rondas hasta spec válido | Tokens (entrada + salida) | Costo |
  |---|---|---|---|
  | `ayuda` corta + ejemplo mínimo | 4 | 12 897 + 3 410 | 0.0046 USD |
  | `ayuda` con los items del chat + ejemplo de oro | **1** | 5 191 + 2 611 | **0.0018 USD** |

  Con la versión final, **tres briefs distintos** (app de pedidos 20 s, cotización Wi-Fi para hotel 25 s,
  soporte postventa 18 s) salieron válidos **a la primera** con 0.0018–0.0039 USD por spec.

  Lo que más ayudó fue que el catálogo compacto incluyera **las variantes de los items** (el modelo
  inventaba propiedades) y copiar un **ejemplo de oro**. Los mensajes con ruta y arreglo se corrigen
  en una sola ronda (p. ej. `E-TIEMPO-EXCEDE` → sube `salida.duracion`).
- Un error que el modelo **no puede** arreglar es un bug del motor: el toast del chat usaba 21 px y la
  QA exige 22 px. Regla: cada componente debe cumplir sus propios mínimos de QA con cualquier texto
  que su catálogo permita.

## 2. Revisar lo que produce el modelo barato encuentra huecos de la QA

- DeepSeek escribió `marca.producto: "SYSCOM PRO"`: el lockup se partió en dos líneas, se salió del
  cuadro y la cabecera del chat decía "SYSCOM SYSCOM PRO". La QA no lo vio porque el lockup no tenía
  `data-qa`. Se blindó en tres capas: validador (`E-MARCA-REPETIDA` con el arreglo "Usa solo PRO"),
  componente (lockup sin salto de línea y auto-escalado) y QA (el lockup ahora se vigila).
- El cierre con posiciones fijas chocaba con un lema de 2 líneas: se rehízo como columna flexible
  calibrada a la referencia.

- La prueba del hotel pidió que el asistente mandara el PDF por WhatsApp: `archivo` ganó `de: usuario|asistente`.
- El ejemplo de oro de 8 escenas no cabía en 30 s con mínimos "cómodos" (pedía 34.7 s): la referencia
  es más rápida. Se agregó compresión con aviso (`W-TIEMPO-RAPIDO`, hasta 28 %) protegiendo el cierre.

- **La visión no sirve como compuerta.** `scripts/revisar_hoja.py` (experimental) sobre una hoja de
  25 cuadros: gemini-2.5-flash vio el lockup cortado pero dio 24 falsos positivos en una hoja sana
  (confunde el tipeo progresivo y el scroll del chat con "texto cortado"); gemini-3.8-flash y
  deepseek-v4.1-flash dieron 0 falsos positivos pero no vieron el defecto. Conclusión: cada defecto
  visual real se convierte en una regla determinista de la QA del DOM.

## 3. Determinismo: probar píxeles, no solo estilos

- La huella de estilos dio un falso positivo: las escenas ocultas (`display:none`) conservan estilos
  de su última visita. La huella ahora cuenta solo lo visible; la prueba de píxeles (cuadros hacia
  adelante vs. hacia atrás en páginas distintas) es la verdad visual.

## 4. Render

- Chrome bloquea módulos ES en `file://`: el runtime se sirve con `page.route()` en un origen falso
  (`http://promo.local`), 100 % offline.
- **El cuello de botella es x264, no la captura**: captura ≈ 65 ms/cuadro por navegador; x264 `slow`
  con grano ≈ 70 ms/cuadro usando 6.6 núcleos. Con 3 navegadores el render de 10 s pasa de 35 s a
  34 s. `medium` ahorra ~30 %; se mantiene `slow` por la regla "calidad sobre rapidez".
- Sin `setparams` el MP4 queda con `color_primaries/transfer = unknown`; con él, BT.709 completo.
- El grano anti-banding sube el bitrate (~33 Mbps): un master de 10 s pesa 41.5 MB y no pasa el
  límite de 30 MB de la vista en teléfono. `final` genera además `<slug>_correo.mp4` (~3.9 Mbps).
- `playwright-core` se fija a **1.62.1** porque es la que usa el Chromium ya en caché (rev 1234);
  1.63 pide la rev 1243 y descargaría otro navegador.

## 5. Tipografía

- Los subconjuntos "latin" de Fontsource no incluyen → (U+2192), ✓ ni ≈: el validador los rechaza
  (`E-TXT-GLIFO`) y sugiere un ícono. La referencia los usaba con otra fuente.
- Contar palabras "reales" (el espacio duro de "400 m²" o del anti-viuda no debe ocultar palabras).
- Titulares: preferir 2 líneas anchas a 3 angostas si la letra sigue ≥ 56 px.

## 6. Voz en off: TTS puro, no modelo de chat

- Con `gpt-audio-mini` (modelo de chat con salida de audio) **8 de 13** subtítulos del ejemplo de oro se
  "contestaron" o desarrollaron: "Descríbele tu proyecto y te arma" suena a orden para el modelo, y los
  fragmentos ("la solución completa,") los completa. Los subtítulos son fragmentos por diseño.
- `fish-audio/s2-pro` por `/audio/speech` (TTS puro) leyó las 13 al pie de la letra a la primera, con diff
  dirigido limpio, por 0.0063 USD. Es el proveedor por defecto de `promo.py voz` (`modelos.voz_tts`).
- El detector de "toma mala" pasó de s/palabra a **s/sílaba** (> 0.38): "Desbloquea equipos HIKVISION"
  daba 0.73 s/palabra con habla normal (0.22 s/sílaba). Tomas buenas medidas: 0.15–0.29 s/sílaba.
- Una toma fallida no se registra en `tiempos.json` y las tomas de otro proveedor se ignoran: si no, el
  planificador dimensionaba escenas con tomas de 20 s y `todo` se bloqueaba antes de regenerarlas.
- Mezcla con voz: LRA de 16.8 → 6.5 LU normalizando la voz DESPUÉS de su compresor, música a −24 LUFS con
  ducking 4:1 y un compresor de bus 2:1. `sidechaincompress` recortaba la cola de la música: se rellenan
  ambas entradas y se recorta a N muestras.

## 7. Audio CC0

- Openverse anónimo (~100 solicitudes/día) casi solo devuelve efectos de Freesound: la música larga
  CC0 prácticamente no existe ahí. La cama procedural sigue siendo el respaldo. Detalle en [[Audio-CC0]].

## Las 2 preguntas (AGENT §15)

1. **¿Qué habría hecho esto más rápido/barato?** Tener desde el inicio el ejemplo de oro y un
   catálogo compacto con TODAS las variantes; medir con el arnés E2E en cada cambio del catálogo.
2. **¿Qué cambia en la versión base?** Nueva ruta `promo-ui` (AGENT §6/§12, SKILL), motor `promo/`,
   CLI `scripts/promo.py`, audio `scripts/sonido.py`, descarga CC0 `scripts/fetch_audio.py`, arnés
   `scripts/e2e_orquestador.py`, preflight con Node y `promo-deps`.

## Enlaces

- [[Motor-Promo]] · [[SKILL]] · [[AGENT]] · [[Audio-CC0]] · [[Home]]
