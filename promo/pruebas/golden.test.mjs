// Regresión visual del ejemplo de oro (sin logo privado). Actualizar a propósito con:
//   node promo/motor.mjs golden --actualizar
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { golden, DIR_GOLDEN } from '../lib/golden.mjs';

const UMBRAL = 0.98; // tolerancia al rasterizado de texto entre versiones de macOS

test('cuadros del ejemplo de oro iguales a las golden (SSIM)', { timeout: 180000 }, async (t) => {
  if (!fs.existsSync(DIR_GOLDEN) || !fs.readdirSync(DIR_GOLDEN).length) {
    t.skip('sin golden todavía: node promo/motor.mjs golden --actualizar');
    return;
  }
  const res = await golden();
  const malos = res.filter((r) => r.ssim < UMBRAL).map((r) => `${r.nombre} (t=${r.t}) SSIM ${r.ssim.toFixed(4)}`);
  assert.deepEqual(malos, [], 'Si el cambio visual es intencional: node promo/motor.mjs golden --actualizar');
});
