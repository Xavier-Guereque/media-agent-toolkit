// node --test: lógica pura del subtítulo karaoke (src/lib/karaoke.ts).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { bloqueDe, frases, palabraActiva, segmentos } from '../src/lib/karaoke.ts';

const P = (w, a, b) => ({ w, a, b });
// dos oraciones con una pausa de 0.9 s entre ellas (caso real de un video animado de referencia)
const palabras = [P('Tu', 0.3, 0.5), P('acceso.', 0.5, 0.9), P('ACME', 1.8, 2.1), P('responde', 2.1, 2.5), P('hoy.', 2.5, 2.8)];

test('frases corta en fin de oración y en el máximo de palabras', () => {
  assert.deepEqual(frases(palabras, 16), [{ desde: 0, hasta: 1 }, { desde: 2, hasta: 4 }]);
  assert.deepEqual(frases(palabras, 2), [{ desde: 0, hasta: 1 }, { desde: 2, hasta: 3 }, { desde: 4, hasta: 4 }]);
});

test('palabraActiva: la que suena, la primera antes de empezar y la última al terminar', () => {
  assert.equal(palabraActiva(palabras, 0.0), 0);
  assert.equal(palabraActiva(palabras, 2.2), 3);
  assert.equal(palabraActiva(palabras, 9), 4);
});

test('en una pausa entre oraciones el subtítulo se queda en la oración que acaba de sonar', () => {
  const idx = palabraActiva(palabras, 1.3);
  assert.equal(idx, 1);
  assert.deepEqual(bloqueDe(frases(palabras, 16), idx), { desde: 0, hasta: 1 });
});

test('segmentos: los *asteriscos* marcan el realce', () => {
  assert.deepEqual(segmentos('Tu *agente* de compras'), [
    { t: 'Tu ', f: false },
    { t: 'agente', f: true },
    { t: ' de compras', f: false },
  ]);
  assert.deepEqual(segmentos('*Todo*'), [{ t: 'Todo', f: true }]);
});
