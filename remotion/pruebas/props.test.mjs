// node --test (Node 22.18+ quita los tipos de .ts al importar; no cubre .tsx).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { metadataDesde, propsPorDefecto } from '../src/lib/props.ts';
import { REGISTRO_VACIO, asegurarRegistro } from '../motor.mjs';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const meta = { fps: 30, ancho: 1080, alto: 1920, duracion: 3, props: { titulo: 'x' } };

test('metadataDesde: los props del spec mandan sobre meta', () => {
  const m = metadataDesde({ duracion: 12, fps: 25, ancho: 1920, alto: 1080 }, meta);
  assert.deepEqual(m, { fps: 25, width: 1920, height: 1080, durationInFrames: 300 });
});

test('metadataDesde: sin props usa meta y redondea a cuadros enteros', () => {
  assert.deepEqual(metadataDesde({}, meta), { fps: 30, width: 1080, height: 1920, durationInFrames: 90 });
  assert.equal(metadataDesde({ duracion: 0.01 }, meta).durationInFrames, 1);
  assert.equal(metadataDesde({ duracion: 'nada', fps: -5 }, meta).durationInFrames, 90);
});

test('propsPorDefecto combina los cuatro campos base con los props de meta', () => {
  assert.deepEqual(propsPorDefecto(meta), { duracion: 3, ancho: 1080, alto: 1920, fps: 30, titulo: 'x' });
});

test('registro: Ejemplo está en BASE y registro.ts existe (remotion.py o `pretest` → motor.mjs registro)', () => {
  const indice = fs.readFileSync(path.join(RAIZ, 'src/composiciones/index.ts'), 'utf8');
  assert.match(indice, /id: 'Ejemplo'/);
  assert.match(indice, /id: 'Leccion'/);
  assert.ok(fs.existsSync(path.join(RAIZ, 'src/composiciones/proyectos/registro.ts')));
});

test('asegurarRegistro: crea un registro vacío solo si falta y no pisa uno existente', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'registro-'));
  const ruta = path.join(dir, 'proyectos', 'registro.ts');
  assert.equal(asegurarRegistro(ruta), true);
  assert.equal(fs.readFileSync(ruta, 'utf8'), REGISTRO_VACIO);
  assert.match(REGISTRO_VACIO, /export const PROYECTOS: Entrada\[\] = \[\n\];\n$/);
  fs.writeFileSync(ruta, 'otro');
  assert.equal(asegurarRegistro(ruta), false);
  assert.equal(fs.readFileSync(ruta, 'utf8'), 'otro');
  fs.rmSync(dir, { recursive: true });
});
