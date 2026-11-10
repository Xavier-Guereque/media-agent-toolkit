// Pruebas del planificador: ajuste exacto al total, rejilla de cuadros y errores de tiempo.
import test from 'node:test';
import assert from 'node:assert/strict';
import { cargarCatalogo, cargarTema, temasDisponibles, validarSpec } from '../lib/catalogo.mjs';
import { planificar } from '../lib/planificador.mjs';

const catalogo = cargarCatalogo();
const tema = cargarTema('neutro');
const plan = async (spec) => {
  const { spec: s, issues } = validarSpec(spec, { catalogo, tema, temas: temasDisponibles() });
  assert.deepEqual(issues.filter((x) => x.severidad === 'E'), []);
  return planificar(s, { tema, catalogo, slug: 'prueba' });
};
const escenas = () => [
  { tipo: 'intro', titulo: 'AI para *PROs*' },
  { tipo: 'texto', texto: 'Cotiza un proyecto *completo* en segundos.' },
  { tipo: 'cierre', lema: 'AI para *PROs.*', cta: { texto: 'Escríbele por WhatsApp' } },
];

test('el total es exacto y los límites caen en la rejilla de cuadros', async () => {
  const { lt, issues } = await plan({ salida: { duracion: 12 }, escenas: escenas() });
  assert.deepEqual(issues, []);
  assert.equal(lt.total, 12);
  assert.equal(lt.cuadros, 360);
  assert.equal(lt.escenas.at(-1).fin, 12);
  for (const e of lt.escenas) assert.ok(Math.abs(e.ini * 30 - Math.round(e.ini * 30)) < 1e-6, `ini ${e.ini}`);
  for (let i = 1; i < lt.escenas.length; i++) assert.ok(lt.escenas[i].ini < lt.escenas[i - 1].fin, 'traslape');
});

test('los beats caben dentro de cada escena', async () => {
  const { lt } = await plan({ salida: { duracion: 14 }, escenas: escenas() });
  for (const e of lt.escenas) {
    for (const [id, b] of Object.entries(e.pasos)) assert.ok(b.ini + b.dur <= e.dur + 1e-6, `${e.id}.${id}`);
  }
});

const chatLargo = () => ({
  tipo: 'chat',
  chat: { items: [
    { tipo: 'usuario', texto: 'Cotiza doce cámaras con grabación de treinta días.' },
    { tipo: 'pasos', pasos: ['Buscando cámaras', 'Buscando grabador', 'Consultando existencias'] },
    { tipo: 'razonamiento', texto: 'Doce cámaras de cuatro megapíxeles con treinta días de grabación.' },
    { tipo: 'asistente', texto: '*Todo con existencia.* Te dejo la cotización.' },
    { tipo: 'cotizacion', titulo: 'Cotización' },
  ] },
});

test('W-TIEMPO-RAPIDO: acelera hasta el piso antes de fallar', async () => {
  const { lt, issues } = await plan({ salida: { duracion: 9 }, escenas: [escenas()[0], chatLargo(), escenas()[2]] });
  assert.ok(issues.find((x) => x.codigo === 'W-TIEMPO-RAPIDO'));
  assert.equal(lt.total, 9);
  const cierre = lt.escenas.at(-1);
  assert.ok(cierre.dur >= 3.5, 'el cierre no se acelera');
});

test('E-TIEMPO-EXCEDE nombra qué recortar', async () => {
  const { issues } = await plan({ salida: { duracion: 6 }, escenas: [escenas()[0], chatLargo(), chatLargo(), escenas()[2]] });
  const e = issues.find((x) => x.codigo === 'E-TIEMPO-EXCEDE');
  assert.ok(e);
  assert.match(e.arreglo, /Sube salida.duracion/);
});

test('E-TIEMPO-FALTA si el contenido no alcanza', async () => {
  const { issues } = await plan({ salida: { duracion: 60 }, escenas: escenas() });
  assert.ok(issues.find((x) => x.codigo === 'E-TIEMPO-FALTA'));
});

test('cues con whoosh en transiciones y secciones musicales', async () => {
  const { lt } = await plan({ salida: { duracion: 12 }, escenas: escenas() });
  assert.ok(lt.cues.some((c) => c.s === 'whoosh'));
  assert.deepEqual(lt.musica.secciones.map((x) => x[2]), ['intro', 'cuerpo', 'cierre']);
  assert.ok(lt.qa.tiempos.length >= 5);
});
