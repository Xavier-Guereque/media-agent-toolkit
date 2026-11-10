// Determinismo en el navegador: el mismo t da el mismo cuadro sin importar el orden de visita.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { cargarCatalogo, cargarTema, temasDisponibles, validarSpec } from '../lib/catalogo.mjs';
import { planificar } from '../lib/planificador.mjs';
import { abrir } from '../lib/navegador.mjs';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('cuadros idénticos hacia adelante y hacia atrás (páginas distintas)', { timeout: 120000 }, async () => {
  const bruto = JSON.parse(fs.readFileSync(path.join(RAIZ, 'ejemplos', 'demo-10s', 'promo.json'), 'utf8'));
  const catalogo = cargarCatalogo();
  const tema = cargarTema('neutro');
  const { spec } = validarSpec(bruto, { catalogo, tema, temas: temasDisponibles() });
  const { lt } = await planificar(spec, { tema, catalogo, slug: 'demo' });
  const proyecto = fs.mkdtempSync(path.join(os.tmpdir(), 'promo-det-'));
  const tiempos = [0.3, 1.9, 3.1, 6.6, 9.5];
  const a = await abrir({ lt, proyecto });
  const b = await abrir({ lt, proyecto });
  try {
    assert.deepEqual(a.errores.filter((x) => x.severidad === 'E'), []);
    const ida = [];
    for (const t of tiempos) ida.push(await a.cuadro(t));
    const vuelta = [];
    for (const t of [...tiempos].reverse()) vuelta.unshift(await b.cuadro(t));
    tiempos.forEach((t, i) => assert.ok(ida[i].equals(vuelta[i]), `cuadro t=${t} distinto`));
  } finally {
    await a.cerrar();
    await b.cerrar();
  }
});
