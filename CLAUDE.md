---
tags: [agente, claude, contexto, media-toolkit]
fecha_modificacion: 2026-09-28
estado: activo
---

# CLAUDE — Entrada para Claude Code

El contexto principal de este repositorio vive en `[[AGENT]]`. **Léelo y síguelo antes de ejecutar cualquier tarea.**

Reglas críticas para Claude:

1. Cargar en orden: `[[AGENT]]` → `[[SKILL]]` → `config.json` → `.env`.
2. Usar `OPENROUTER_API_KEY` del `.env` para los modelos complementarios de la tarea (visión, imagen, voz, clonación, guion, prompts), según `config.json > modelos`.
3. FFmpeg es la herramienta base: si una tarea se puede hacer con FFmpeg, se hace con FFmpeg.
4. `ELEVENLABS_API_KEY` es opcional: solo usarla si está configurada y el usuario lo pide; nunca pedirla si falta.
5. Nunca commitear ni exponer `.env` ni el contenido de `muestras/`.
6. Proyectos en `proyectos/<slug>_<DDMMAAAA>/` (contenido gitignored; ver `[[AGENT]]` §13). Personalizaciones del usuario → `docs/Preferencias-Usuario.md` (gitignored); solo con "esto va en la versión base del repo" se tocan los archivos base (ver `[[AGENT]]` §16). Tras cada trabajo, aprendizaje continuo (ver `[[AGENT]]` §15).
7. Videos promo con UI animada (estilo de la casa): motor promo — escribir solo `promo.json` y usar `python3 scripts/promo.py` (skill `promo-ui` de `[[SKILL]]`, detalle en `[[Motor-Promo]]`). Música/SFX CC0 con `scripts/fetch_audio.py` (`[[Audio-CC0]]`).
8. Para elegir la skill de una petición nueva: `python3 scripts/enrutar.py "<petición>"` (JEV, ~0.00003 USD).
9. Cursos en video: primero el cuestionario de la skill; escribir solo `curso.json` y usar `python3 scripts/curso.py` (skill `crear-curso`, metodología en `[[Metodologia-Cursos-Video]]`).
