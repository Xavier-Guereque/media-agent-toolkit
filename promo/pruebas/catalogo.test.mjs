// Pruebas del validador: mensajes accionables con ruta, sugerencias y normalización tipográfica.
import test from 'node:test';
import assert from 'node:assert/strict';
import { cargarCatalogo, cargarTema, temasDisponibles, validarSpec, normalizarTexto } from '../lib/catalogo.mjs';

const catalogo = cargarCatalogo();
const tema = cargarTema('neutro');
const temas = temasDisponibles();
const v = (spec) => validarSpec(spec, { catalogo, tema, temas });
const base = () => ({
  escenas: [
    { tipo: 'texto', texto: 'Hola *mundo*' },
    { tipo: 'cierre', lema: 'AI para *PROs.*', cta: { texto: 'Escríbenos' } },
  ],
});
const codigos = (r) => r.issues.map((x) => `${x.codigo}@${x.ruta}`);

test('spec mínimo válido y defaults aplicados', () => {
  const r = v(base());
  assert.deepEqual(r.issues.filter((x) => x.severidad === 'E'), []);
  assert.equal(r.spec.salida.duracion, 30);
  assert.equal(r.spec.audio.musica.tipo, 'procedural');
  assert.equal(r.spec.escenas[0].id, 'e1');
  assert.equal(r.spec.escenas[1].tinte, 'marino');
});

test('propiedad desconocida sugiere el nombre correcto', () => {
  const s = base();
  s.escenas[0].textto = 'x';
  const r = v(s);
  const e = r.issues.find((x) => x.codigo === 'E-ESQ-DESCONOCIDO');
  assert.equal(e.ruta, 'escenas[0].textto');
  assert.match(e.arreglo, /texto/);
});

test('texto largo con ruta exacta y cuántas palabras quitar', () => {
  const s = base();
  s.escenas[0].texto = 'uno dos tres cuatro cinco seis siete ocho nueve diez once doce';
  const e = v(s).issues.find((x) => x.codigo === 'E-TXT-LARGO');
  assert.equal(e.ruta, 'escenas[0].texto');
  assert.match(e.arreglo, /Quita 2/);
});

test('tipo de escena mal escrito', () => {
  const s = base();
  s.escenas[0].tipo = 'textos';
  assert.ok(codigos(v(s)).includes('E-ESQ-ESCENA@escenas[0].tipo'));
});

test('kicker prohibido por regla de la casa', () => {
  const s = base();
  s.escenas[0].kicker = '01 · SECCIÓN';
  assert.ok(codigos(v(s)).includes('E-ESTILO-KICKER@escenas[0].kicker'));
});

test('glifo sin cobertura y sugerencia', () => {
  const s = base();
  s.escenas[0].texto = 'Rápido → fácil';
  const e = v(s).issues.find((x) => x.codigo === 'E-TXT-GLIFO');
  assert.match(e.arreglo, /arrow-right/);
});

test('cierre solo al final; referencia a hecho inexistente', () => {
  const s = base();
  s.escenas.reverse();
  s.escenas[1].respaldo = ['h9'];
  const c = codigos(v(s));
  assert.ok(c.includes('E-ESTRUCTURA-CIERRE@escenas[0]'));
  assert.ok(c.includes('E-REF-HECHO@escenas[1].respaldo[0]'));
});

test('items del chat: unión por tipo con sugerencia', () => {
  const s = base();
  s.escenas.unshift({ tipo: 'chat', chat: { items: [{ tipo: 'usario', texto: 'hola' }] } });
  const e = v(s).issues.find((x) => x.ruta === 'escenas[0].chat.items[0].tipo');
  assert.match(e.arreglo, /usuario/);
});

test('normalización: comillas, puntos suspensivos, unidades y viudas', () => {
  assert.equal(normalizarTexto('"Hola"...'), '“Hola”…');
  assert.equal(normalizarTexto('Oficina de 400 m2 y 4 MP'), 'Oficina de 400 m² y 4 MP');
  assert.equal(normalizarTexto('Cotiza un proyecto en segundos', { antiViuda: true }), 'Cotiza un proyecto en segundos');
  assert.equal(normalizarTexto('AI para los *PROs.*', { antiViuda: true }), 'AI para los *PROs.*');
});
