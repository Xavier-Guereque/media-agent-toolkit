---
tags: [lecciones, remotion, promo, metraje-real, grabacion-pantalla, privacidad]
fecha_modificacion: 2026-11-02
estado: activo
---

# Lecciones 2026-11-02 — Promo del Diseñador de Videovigilancia con metraje real

Promo de 32.8 s en 9:16 y 16:9 a partir de una grabación de pantalla de 4:45 min. Motor: Remotion, porque `promo-ui`
solo dibuja UI simulada. Proyecto: `proyectos/disenador-videovigilancia_02112026/`. Ver [[Motor-Remotion]] y [[Motor-Promo]].

## ¿Cómo optimizar videos similares?

1. **Hojas de contacto con marca de tiempo antes que nada.** `fps=1/6` + `drawtext` + `tile` localiza cada función de una
   grabación larga sin ver el video; después, tiras de 1 fps solo de los tramos candidatos.
2. **Revisar privacidad cuadro por cuadro antes de elegir tomas.** Esta grabación mostraba la foto de una persona en la
   vista simulada y correos reales en el formulario del reporte. Las tomas se recortan al lienzo (`1327:841:0:205`) y a la
   hoja del reporte (`860:1046:590:0`) desde `componer.py`, de modo que el dato nunca entra en la composición.
3. **Un TSX, dos orientaciones.** Cada escena declara su `foco` por orientación (`cx, cy, z0, z1`) y un `remotion.<orientación>.json`
   por salida. Con el mismo guion, la segunda orientación solo costó un borrador de revisión y su render.
4. **Tiempos desde la voz medida.** `dur = entrada + voz + respiro`; `atempo=1.08` bajó ~2 s sin regenerar el TTS.
5. **El borrador a 540x960 tarda ~33 s.** Conviene revisar ocho cuadros clave antes del render final.

## ¿Qué funciones nuevas usé?

- `sonido.musica_procedural` fuera del motor promo, con un `lt` mínimo (`duracion`, `total`, `escenas` intro/cierre). Verificado.
- Encuadre de `OffthreadVideo` por escala y posición absoluta, limitado para no mostrar fuera de la fuente. Verificado.
- Voz Achird con `narrar.py` en un promo comercial, no solo en cursos. Verificado.

## Problemas encontrados

- **Claude in Chrome:** el grupo de pestañas se perdía entre llamadas (`Tab … is not in Claude's tab group`) con la página
  3D abierta. Tras tres fallos se dejó de insistir y la fuente fue la grabación. Por HTTP sin sesión, la URL muestra el
  formulario de inicio de sesión de SYSCOM, de ahí que el CTA no diga «gratis».
- **`narrar.py` se quedó colgado** en `marcas_whisper`, en la toma 5 (proceso con 0 % de CPU por más de 6 minutos), después de sintetizar
  todas las tomas. Causa no diagnosticada. Rodeo: usar los WAV ya generados y verificar con faster-whisper, 4 hilos y un
  arreglo de numpy. `transcribe(ruta)` falla en `~/.venvs/whisper` (`av.open` sin `metadata_errors`).
- macOS no trae `timeout`.
- **`file_upload` de Claude in Chrome** admite menos de 10 MB por llamada: estos MP4 (10.9 y 14.1 MB) no entran y hay que subirlos
  de otra forma. El grupo de pestañas también se perdió durante el inicio de sesión de la app de destino.

## Enlaces

- [[AGENT]] · [[SKILL]] · [[Motor-Remotion]] · [[Lecciones-2026-10-31-star-trek-cronologia]]
