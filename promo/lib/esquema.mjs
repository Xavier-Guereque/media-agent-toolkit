// esquema.mjs — convierte el catálogo (DSL) a JSON Schema.
//
// Sirve para dos cosas: autocompletado/validación en el editor ("$schema" en promo.json) y
// `response_format: json_schema` cuando `promo.py borrador` pide el spec a un modelo. El validador
// propio (catalogo.mjs) sigue siendo la autoridad: da mensajes en español con arreglo concreto.

import { cargarCatalogo, cargarTema } from './catalogo.mjs';

function texto(def) {
  const s = { type: 'string' };
  if (def.max_car) s.maxLength = def.max_car + (def.enfasis ? 4 : 0);
  if (def.patron) s.pattern = def.patron;
  const partes = [];
  if (def.doc) partes.push(def.doc);
  if (def.max_palabras) partes.push(`Máximo ${def.max_palabras} palabras.`);
  if (def.enfasis) partes.push('Permite *énfasis* con asteriscos.');
  if (partes.length) s.description = partes.join(' ');
  return s;
}

export function esquemaDe(def, ctx) {
  const d = (s) => (def.doc && !s.description ? { ...s, description: def.doc } : s);
  switch (def.t) {
    case 'texto':
      return texto(def);
    case 'frases':
      return d({ anyOf: [texto(def), { type: 'array', items: texto(def), minItems: 1, maxItems: def.max_frases || 3 }] });
    case 'entero':
      return d({ type: 'integer', ...(def.min !== undefined && { minimum: def.min }), ...(def.max !== undefined && { maximum: def.max }) });
    case 'numero':
      return d({ type: 'number', ...(def.min !== undefined && { minimum: def.min }), ...(def.max !== undefined && { maximum: def.max }) });
    case 'booleano':
      return d({ type: 'boolean' });
    case 'nulo':
      return d({ type: 'null' });
    case 'enum':
      return d({ type: 'string', enum: def.de === 'tema.tintes' ? Object.keys(ctx.tema.tintes) : def.valores });
    case 'ref':
      return d({ type: 'string', description: `${def.doc || 'Id'} (clave de "hechos").` });
    case 'imagen':
      return d({ type: 'string', description: `${def.doc || 'Imagen'} Ruta relativa a recursos/ del proyecto.` });
    case 'lista':
      return d({ type: 'array', items: esquemaDe(def.de, ctx), ...(def.min !== undefined && { minItems: def.min }), ...(def.max !== undefined && { maxItems: def.max }) });
    case 'registro':
      return d({ type: 'object', additionalProperties: esquemaDe(def.de, ctx) });
    case 'objeto':
      return def.nulable ? d({ anyOf: [{ type: 'null' }, objeto(def.props, ctx)] }) : d(objeto(def.props, ctx));
    case 'union':
      return { $ref: `#/$defs/${def.nombre}` };
    default:
      throw new Error(`esquema: tipo desconocido ${def.t}`);
  }
}

function objeto(props, ctx, extra = {}) {
  const properties = {};
  const required = [];
  for (const [k, def] of Object.entries({ ...props, ...extra })) {
    properties[k] = esquemaDe(def, ctx);
    if (!def.opcional && def.defecto === undefined) required.push(k);
  }
  return { type: 'object', properties, ...(required.length && { required }), additionalProperties: false };
}

export function generarEsquema() {
  const catalogo = cargarCatalogo();
  const tema = cargarTema('neutro');
  const ctx = { tema };
  const defs = {};
  const escenas = [];
  for (const [tipo, cat] of Object.entries(catalogo.escenas)) {
    const extra = { ...catalogo.escena_comun, tipo: { t: 'enum', valores: [tipo], doc: cat.doc } };
    if (cat.titular) extra.titular = { t: 'frases', opcional: true, max_frases: 3, max_palabras: 16, max_car: 100, doc: 'Cita grande arriba.' };
    if (cat.subtitulo) extra.subtitulo = { t: 'frases', opcional: true, max_frases: 3, max_palabras: 8, max_car: 48, doc: 'Pastilla inferior tipo subtítulo.' };
    defs[`escena_${tipo}`] = { description: cat.doc, ...objeto(cat.props, ctx, extra) };
    escenas.push({ $ref: `#/$defs/escena_${tipo}` });
  }
  defs.escena = { anyOf: escenas };
  for (const [nombre, u] of Object.entries(catalogo.uniones || {})) {
    defs[nombre] = {
      anyOf: Object.entries(u.variantes).map(([tipo, v]) => ({
        ...(v.doc && { description: v.doc }),
        ...objeto(v.props || {}, ctx, { tipo: { t: 'enum', valores: [tipo] } }),
      })),
    };
  }
  const raiz = objeto(catalogo.raiz.props, ctx, { $schema: { t: 'texto', opcional: true } });
  return {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    $id: 'media-agent-toolkit/promo.schema.json',
    title: 'promo.json — spec del motor promo',
    description: 'Solo contenido: el motor calcula tiempos, posiciones y colores. Ver docs/Motor-Promo.md.',
    ...raiz,
    $defs: defs,
  };
}
