import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ATENUADO, centro, cueEn, elementoActivo, elementos, items, opacidadElemento, progreso, puntero, tramos } from '../src/lib/leccion.ts';
import { PARQUE, aislado, camara, cursor, esEstacion, escrito, paquetes, parteVisible, piezasDato, posicion, presencia, tomasDe } from '../src/lib/mundo.ts';

test('tramos: la primera escena arranca en 0 y las demás adelantan el fundido', () => {
  const t = tramos([{ inicio: 0, fin: 2 }, { inicio: 2, fin: 5 }], 30, 15);
  assert.deepEqual(t, [{ from: 0, dur: 60 }, { from: 45, dur: 105 }]);
});

test('cueEn: ini inclusivo, fin exclusivo, null en huecos', () => {
  const c = [{ ini: 1, fin: 2, lineas: ['a'] }, { ini: 3, fin: 4, lineas: ['b'] }];
  assert.equal(cueEn(c, 1)?.lineas[0], 'a');
  assert.equal(cueEn(c, 2), null);
  assert.equal(cueEn(c, 3.5)?.lineas[0], 'b');
});

test('progreso se satura entre 0 y 1', () => {
  assert.equal(progreso(1, 0.5), 0);
  assert.ok(Math.abs(progreso(1, 1.225, 0.45) - 0.5) < 1e-9);
  assert.equal(progreso(1, 9), 1);
});

test('el elemento activo va a color y lo previo se atenúa', () => {
  const l = [{ t: 1 }, { t: 2 }, { t: 3 }];
  assert.equal(elementoActivo(l, 0), -1);
  assert.equal(elementoActivo(l, 2.5), 1);
  assert.deepEqual([0, 1, 2].map((i) => opacidadElemento(i, 1)), [ATENUADO, 1, 0]);
  assert.equal(opacidadElemento(0, 1, true), 1);
});

test('el puntero viaja del elemento anterior al activo durante el trazo', () => {
  const l = elementos([{ t: 1, forma: 'caja', x: 0, y: 0, w: 10, h: 10 }, { t: 2, forma: 'caja', x: 50, y: 0, w: 10, h: 10 }]);
  assert.equal(puntero(l, 0.5).visible, false);
  assert.deepEqual(centro(l[0]), [5, 5]);
  assert.equal(puntero(l, 1.5).x, 5);
  assert.ok(Math.abs(puntero(l, 2.225).x - 30) < 1e-9);
  assert.equal(puntero(l, 5).x, 55);
});

test('items acepta cadenas y objetos', () => {
  assert.deepEqual(items(['a']), [{ t: 0, texto: 'a' }]);
  assert.deepEqual(items([{ t: 3, texto: 'b' }]), [{ t: 3, texto: 'b' }]);
  assert.deepEqual(items(null), []);
});

test('la cámara llega a cada toma y el zoom es continuo', () => {
  const t = [{ t: 0, d: 0, x: 0, y: 0, z: 1 }, { t: 1, d: 1, x: 100, y: 0, z: 4 }];
  assert.deepEqual(camara(t, 0.5), { x: 0, y: 0, z: 1 });
  assert.equal(camara(t, 2).x, 100);
  assert.ok(Math.abs(camara(t, 2).z - 4) < 1e-9);
  assert.ok(Math.abs(camara(t, 1.5).z - 2) < 1e-9); // media geométrica: se siente constante
});

test('sin mundo cada escena es una estación; con mundo la cámara no viaja', () => {
  const esc = [{ inicio: 0, pantalla: {} }, { inicio: 5, pantalla: {} }];
  assert.equal(tomasDe(esc, null, []).length, 2);
  assert.equal(tomasDe(esc, { actores: [{ id: 'a', tipo: 'pc' }] }, []).length, 1);
  assert.equal(esEstacion({ inicio: 0, pantalla: { plano: 'estacion' } }, true), true);
});

test('un actor con aparece no existe antes; sin él, desde el inicio', () => {
  const ac = [{ t: 2, accion: 'aparece', actor: 'a' }];
  assert.equal(presencia('a', ac, 1), 0);
  assert.ok(presencia('a', ac, 3) > 0.99);
  assert.equal(presencia('b', ac, 0), 1);
});

test('las partes de un dato aparecen por separado y las piezas no se traslapan', () => {
  const ac = [{ t: 1, accion: 'copia', actor: 'd', partes: [0, 1] }, { t: 3, accion: 'aparece', actor: 'd', partes: [2] }];
  assert.ok(parteVisible(ac, 'd', 0, 2) > 0.99);
  assert.equal(parteVisible(ac, 'd', 2, 2), 0);
  const { piezas, car } = piezasDato(['192', '168', '1'], '.');
  assert.equal(car, 9);
  assert.deepEqual(piezas.map((p) => p.car), [0, 3, 4, 7, 8]);
});

test('un paquete sin red se detiene a medio cable y se apaga', () => {
  const a = { t: 0, accion: 'envia', falla: true, d: 1 };
  assert.ok(Math.abs(paquetes(a, 1.1)[0].u - PARQUE.falla) < 1e-9);
  assert.equal(paquetes(a, 2).length, 0);
  assert.equal(paquetes({ t: 0, accion: 'envia', d: 1 }, 1)[0].u, 1);
});

test('el aislamiento termina en el siguiente enfoca', () => {
  const ac = [{ t: 1, accion: 'enfoca', actor: 'd', aisla: true, d: 1 }, { t: 5, accion: 'enfoca', d: 1 }];
  assert.equal(aislado(ac, 3).nivel, 1);
  assert.equal(aislado(ac, 7).nivel, 0);
});

test('copia arranca en el actor de origen y termina en su lugar', () => {
  const actores = [{ id: 'o', tipo: 'dato', x: 0, y: 0 }, { id: 'd', tipo: 'dato', x: 100, y: 50 }];
  const ac = [{ t: 1, accion: 'copia', actor: 'd', desde: 'o', d: 1 }];
  assert.deepEqual(posicion(actores[1], ac, 1, actores), { x: 0, y: 0 });
  const fin = posicion(actores[1], ac, 2, actores);
  assert.ok(Math.abs(fin.x - 100) < 1e-9 && Math.abs(fin.y - 50) < 1e-9);
});

test('escrito revela el texto a ritmo de tecleo y cursor llega al clic', () => {
  assert.equal(escrito({ t: 0, accion: 'escribe', texto: 'abcd', d: 1 }, 0.5), 'ab');
  const c = cursor([{ t: 2, accion: 'clic', x: 10, y: 20 }], [], 2);
  assert.ok(Math.abs(c.x - 10) < 1e-9 && c.visible === 1);
});
