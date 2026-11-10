// Prueba estática: nada que rompa el determinismo en runtime/ ni en componentes/.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PROHIBIDO = [
  [/Date\.now\s*\(/, 'Date.now()'], [/Math\.random\s*\(/, 'Math.random()'], [/performance\.now\s*\(/, 'performance.now()'],
  [/\bsetTimeout\s*\(/, 'setTimeout'], [/\bsetInterval\s*\(/, 'setInterval'],
  [/@keyframes/, '@keyframes'], [/(^|[;{\s])transition\s*:/, 'transition:'], [/(^|[;{\s])animation\s*:/, 'animation:'],
  [/backdrop-filter/, 'backdrop-filter'], [/<video/, '<video'],
];
// requestAnimationFrame solo se permite en navegador.mjs (espera de pintado al capturar), no en runtime.
PROHIBIDO.push([/requestAnimationFrame/, 'requestAnimationFrame']);

function archivos(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
    const p = path.join(dir, d.name);
    return d.isDirectory() ? archivos(p) : /\.(js|css)$/.test(d.name) ? [p] : [];
  });
}

test('sin fuentes de no determinismo en runtime/ ni componentes/', () => {
  const fallas = [];
  for (const f of [...archivos(path.join(RAIZ, 'runtime')), ...archivos(path.join(RAIZ, 'componentes'))]) {
    const txt = fs.readFileSync(f, 'utf8').split('\n').filter((l) => !/^\s*(\/\/|\/\*|\*)/.test(l)).join('\n');
    const limpio = f.endsWith('base.css') ? txt.replace(/transition: none !important;|animation: none !important;/g, '') : txt;
    for (const [re, nombre] of PROHIBIDO) if (re.test(limpio)) fallas.push(`${path.relative(RAIZ, f)}: ${nombre}`);
  }
  assert.deepEqual(fallas, []);
});

test('cada componente con catálogo declara planear y montar', async () => {
  for (const tipo of fs.readdirSync(path.join(RAIZ, 'componentes'))) {
    if (!fs.existsSync(path.join(RAIZ, 'componentes', tipo, 'catalogo.json'))) continue;
    const m = await import(path.join(RAIZ, 'componentes', tipo, `${tipo}.js`));
    assert.equal(typeof m.planear, 'function', `${tipo}.planear`);
    assert.equal(typeof m.montar, 'function', `${tipo}.montar`);
  }
});

test('el esquema versionado está al día con el catálogo', async () => {
  const { generarEsquema } = await import('../lib/esquema.mjs');
  const actual = JSON.parse(fs.readFileSync(path.join(RAIZ, 'esquema', 'promo.schema.json'), 'utf8'));
  assert.deepEqual(actual, JSON.parse(JSON.stringify(generarEsquema())), 'Corre: node promo/motor.mjs esquema');
});
