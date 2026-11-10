// Pruebas de la matemática pura del motor (sin navegador).
import test from 'node:test';
import assert from 'node:assert/strict';
import { P, E, clamp, resorte, mulberry32, hashTexto, mezclar, aCuadro } from '../runtime/tiempo.js';
import { parsearEnfasis, contarPalabras } from '../runtime/palabras.js';

test('easings acotados en 0 y 1', () => {
  for (const [nombre, f] of Object.entries(E)) {
    assert.ok(Math.abs(f(0)) < 1e-9, `${nombre}(0)`);
    assert.ok(Math.abs(f(1) - 1) < 1e-9, `${nombre}(1)`);
  }
});

test('P: antes, durante y después', () => {
  assert.equal(P(0, 1, 2), 0);
  assert.equal(P(5, 1, 2), 1);
  assert.ok(P(2, 1, 2) > 0 && P(2, 1, 2) < 1);
  assert.equal(P(1, 1, 0), 1);
  assert.equal(clamp(3), 1);
});

test('resorte converge a 1 y es 0 antes del disparo', () => {
  assert.equal(resorte(-0.1), 0);
  assert.ok(Math.abs(resorte(3) - 1) < 1e-3);
});

test('azar determinista: misma semilla, misma secuencia', () => {
  const a = mulberry32(hashTexto('7:warp'));
  const b = mulberry32(hashTexto('7:warp'));
  for (let i = 0; i < 50; i++) assert.equal(a(), b());
  assert.notEqual(mulberry32(1)(), mulberry32(2)());
});

test('mezcla OKLab respeta los extremos', () => {
  assert.deepEqual(mezclar('#102030', '#ffffff', 0), [16, 32, 48]);
  assert.deepEqual(mezclar('#102030', '#ffffff', 1), [255, 255, 255]);
});

test('aCuadro redondea a la rejilla de 30 fps', () => {
  assert.equal(aCuadro(0.45, 30), 14 / 30);
});

test('énfasis de varias palabras y conteo', () => {
  assert.deepEqual(parsearEnfasis('AI para *PROs.*'), [{ w: 'AI', e: false }, { w: 'para', e: false }, { w: 'PROs.', e: true }]);
  assert.deepEqual(parsearEnfasis('*muy fácil* hoy').map((x) => x.e), [true, true, false]);
  assert.equal(contarPalabras('400 m² en total'), 3);
});
