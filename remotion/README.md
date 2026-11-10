# Motor Remotion (opcional) — composiciones libres React → MP4

Segundo motor de `media-agent-toolkit`, para motion graphics que el catálogo del motor promo no expresa. Lo maneja
`python3 scripts/remotion.py` (nunca se llama a mano `motor.mjs`); documentación en `docs/Motor-Remotion.md` y skill
`remotion-video` en `SKILL.md`.

- Instalar: `npm ci --prefix remotion && npx --prefix remotion remotion browser ensure` (desde la raíz del repo; Node ≥ 20).
- Skills oficiales para escribir composiciones: `npx skills add remotion-dev/skills -a claude-code -y` (Node ≥ 22.20).
- Pruebas: `npm test` (tsc + `node --test`); las de Python en `scripts/pruebas/test_remotion.py`.
- `src/composiciones/proyectos/` guarda los TSX de cada proyecto (gitignored) y `registro.ts` lo genera `remotion.py`; si falta, `node motor.mjs registro` (lo corren solos `npm test`, `npm run estudio` y `npm run composiciones`) crea uno vacío.

**Licencia de Remotion:** gratis para personas, ONG y empresas de hasta 3 personas; con 4 o más empleados hace falta la
Company License (https://remotion.pro/license). Ver `docs/Motor-Remotion.md`.
