// catalogo.mjs — carga del catálogo/tema, normalización tipográfica y validación del spec.
//
// La validación produce errores ACCIONABLES en español, con la ruta JSON exacta y un arreglo
// concreto. Es lo que permite que un modelo barato corrija su propio promo.json en 1–2 vueltas.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { sinMarcas, enfasisDesbalanceado } from '../runtime/palabras.js';

export const RAIZ_MOTOR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// Raíz + props comunes en catalogo.json; cada componente de escena trae su componentes/<tipo>/catalogo.json.
// Así cada componente vive con su propia definición (y se agregan tipos sin tocar un archivo central).
export function cargarCatalogo() {
  const cat = JSON.parse(fs.readFileSync(path.join(RAIZ_MOTOR, 'catalogo.json'), 'utf8'));
  cat.escenas = {};
  cat.uniones = {};
  const dir = path.join(RAIZ_MOTOR, 'componentes');
  for (const tipo of fs.readdirSync(dir).sort()) {
    const f = path.join(dir, tipo, 'catalogo.json');
    if (!fs.existsSync(f)) continue;
    const { uniones, ...def } = JSON.parse(fs.readFileSync(f, 'utf8'));
    cat.escenas[tipo] = def;
    Object.assign(cat.uniones, uniones || {}); // uniones propias del componente (p. ej. items del chat)
  }
  return cat;
}

export function temasDisponibles() {
  return fs.readdirSync(path.join(RAIZ_MOTOR, 'temas')).filter((d) => fs.existsSync(path.join(RAIZ_MOTOR, 'temas', d, 'tema.json')));
}

export function cargarTema(nombre) {
  const dir = path.join(RAIZ_MOTOR, 'temas', nombre);
  const tema = JSON.parse(fs.readFileSync(path.join(dir, 'tema.json'), 'utf8'));
  const privado = path.join(dir, 'privado', tema.marca.logo);
  tema._logo = fs.existsSync(privado) ? 'privado' : fs.existsSync(path.join(dir, tema.marca.logo)) ? 'tema' : null;
  return tema;
}

// ------------------------------------------------------------------ tipografía
// Rangos Unicode cubiertos por las fuentes vendorizadas (subconjuntos latin + latin-ext de Fontsource).
const RANGOS = [
  [0x20, 0x7e], [0xa0, 0xff], [0x100, 0x2ba], [0x2bb, 0x2bc], [0x2bd, 0x2c5], [0x2c6, 0x2c6], [0x2c7, 0x2cc],
  [0x2ce, 0x2d7], [0x2da, 0x2da], [0x2dc, 0x2dc], [0x2dd, 0x2ff], [0x1e00, 0x1eff], [0x2010, 0x2027],
  [0x2030, 0x203a], [0x20ac, 0x20ac], [0x2122, 0x2122], [0x2191, 0x2191], [0x2193, 0x2193], [0x2212, 0x2212],
];
const SUGERENCIA_GLIFO = {
  '→': 'usa "a" o un ícono (arrow-right)', '✓': 'usa un ícono (check)', '✔': 'usa un ícono (check)',
  '★': 'usa un ícono (star)', '•': 'usa " · "', '⚡': 'usa un ícono (zap)',
};
const cubierto = (cp) => RANGOS.some(([a, b]) => cp >= a && cp <= b);

export function normalizarTexto(s, { antiViuda = false } = {}) {
  let x = String(s).replace(/[\t\r\n]+/g, ' ').replace(/ {2,}/g, ' ').trim();
  x = x.replace(/\.\.\./g, '…');
  x = x.replace(/"([^"]*)"/g, '“$1”').replace(/"/g, '”');
  x = x.replace(/(^|[\s(“])'/g, '$1‘').replace(/'/g, '’');
  // El número y su unidad nunca se separan en dos renglones ("400 m²", "4 MP", "30 %").
  x = x.replace(/(\d) (m²|m2|m³|MP|TB|GB|MB|km|kg|cm|mm|ms|m|min|h|%|W|V|Hz|fps|K)(?=$|[\s.,;:!?)”*])/g,
    (_, d, u) => `${d} ${u === 'm2' ? 'm²' : u}`);
  if (antiViuda) {
    const t = x.split(' ');
    const [pen, ult] = [t[t.length - 2], t[t.length - 1]];
    if (t.length >= 4 && !pen.includes('*') && !ult.includes('*') && sinMarcas(ult).length <= 9) {
      t.splice(t.length - 2, 2, `${pen} ${ult}`);
      x = t.join(' ');
    }
  }
  return x;
}

// ------------------------------------------------------------------ utilidades de mensajes
function distancia(a, b) {
  const m = a.length;
  const n = b.length;
  const d = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 1; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
  }
  return d[m][n];
}

function parecido(clave, opciones) {
  let mejor = null;
  let dm = Infinity;
  for (const o of opciones) {
    const d = distancia(clave.toLowerCase(), o.toLowerCase());
    if (d < dm) {
      dm = d;
      mejor = o;
    }
  }
  return dm <= Math.max(2, Math.floor(clave.length / 3)) ? mejor : null;
}

const citar = (s, n = 40) => {
  const x = String(s);
  return `"${x.length > n ? x.slice(0, n - 1) + '…' : x}"`;
};

export function lineaJson(texto, pos) {
  const antes = texto.slice(0, pos);
  const linea = antes.split('\n').length;
  const col = pos - antes.lastIndexOf('\n');
  return { linea, col };
}

// ------------------------------------------------------------------ validación
export function validarSpec(spec, { catalogo, tema, temas, proyecto = null }) {
  const issues = [];
  const E = (codigo, ruta, msg, arreglo) => issues.push({ codigo, severidad: 'E', ruta, msg, arreglo });
  const W = (codigo, ruta, msg, arreglo) => issues.push({ codigo, severidad: 'W', ruta, msg, arreglo });
  const hechos = spec && typeof spec.hechos === 'object' && spec.hechos ? spec.hechos : {};

  function valor(v, def, ruta) {
    switch (def.t) {
      case 'texto': {
        if (typeof v !== 'string') {
          E('E-ESQ-TIPO', ruta, `debe ser texto (llegó ${tipoDe(v)}).`, 'Escribe el valor entre comillas.');
          return v;
        }
        if (!def.enfasis && v.includes('*')) {
          E('E-TXT-ENFASIS', ruta, 'aquí no se permite *énfasis*.', 'Quita los asteriscos.');
        } else if (enfasisDesbalanceado(v)) {
          E('E-TXT-ENFASIS', ruta, 'hay un asterisco sin cerrar (se vería en pantalla).', 'Usa pares: *palabra*.');
        }
        const x = normalizarTexto(v, { antiViuda: def.anti_viuda });
        // Palabras reales: lo unido con espacio duro ("400 m²", anti-viuda) cuenta por separado.
        const palabras = sinMarcas(x).split(/[\s\u00A0]+/).filter(Boolean).length;
        const car = sinMarcas(x).length;
        if (!x) E('E-TXT-VACIO', ruta, 'está vacío.', 'Escribe el texto o quita la propiedad si es opcional.');
        if (def.max_palabras && palabras > def.max_palabras) {
          E('E-TXT-LARGO', ruta, `${citar(sinMarcas(x))}: ${palabras} palabras (máx ${def.max_palabras}).`, `Quita ${palabras - def.max_palabras} palabra(s).`);
        } else if (def.max_car && car > def.max_car) {
          E('E-TXT-LARGO', ruta, `${citar(sinMarcas(x))}: ${car} caracteres (máx ${def.max_car}).`, `Acórtalo ${car - def.max_car} caracteres.`);
        }
        if (def.patron && !new RegExp(def.patron).test(x)) {
          E('E-ESQ-FORMATO', ruta, `${citar(x)} no tiene el formato esperado (${def.patron}).`, 'Usa minúsculas, números y guiones, sin espacios.');
        }
        const raros = [...new Set([...x].filter((c) => !cubierto(c.codePointAt(0))))];
        if (raros.length) {
          E('E-TXT-GLIFO', ruta, `usa caracteres que la fuente no tiene: ${raros.join(' ')}.`,
            raros.map((c) => SUGERENCIA_GLIFO[c] || `quita ${c}`).join('; ') + '.');
        }
        return x;
      }
      case 'entero':
      case 'numero': {
        if (typeof v !== 'number' || Number.isNaN(v) || (def.t === 'entero' && !Number.isInteger(v))) {
          E('E-ESQ-TIPO', ruta, `debe ser ${def.t === 'entero' ? 'un entero' : 'un número'} (llegó ${tipoDe(v)}).`, 'Escribe el número sin comillas.');
          return v;
        }
        if ((def.min !== undefined && v < def.min) || (def.max !== undefined && v > def.max)) {
          E('E-ESQ-RANGO', ruta, `${v} fuera de rango (${def.min}–${def.max}).`, `Usa un valor entre ${def.min} y ${def.max}.`);
        }
        return v;
      }
      case 'booleano':
        if (typeof v !== 'boolean') E('E-ESQ-TIPO', ruta, `debe ser true o false (llegó ${tipoDe(v)}).`, 'Escribe true o false sin comillas.');
        return v;
      case 'nulo':
        if (v !== null) E('E-ESQ-NO-DISPONIBLE', ruta, 'esta función aún no está disponible.', 'Déjalo en null.');
        return null;
      case 'enum': {
        const valores = def.de === 'tema.tintes' ? Object.keys(tema.tintes) : def.de === 'temas' ? temas : def.valores;
        if (!valores.includes(v)) {
          const sug = typeof v === 'string' ? parecido(v, valores) : null;
          E('E-ESQ-ENUM', ruta, `${citar(v)} no es válido.`, sug ? `¿Quisiste decir "${sug}"?` : `Opciones: ${valores.join(', ')}.`);
        }
        return v;
      }
      case 'ref':
        if (typeof v !== 'string' || !(v in hechos)) {
          E('E-REF-HECHO', ruta, `${citar(v)} no está en "hechos".`, Object.keys(hechos).length ? `Ids disponibles: ${Object.keys(hechos).join(', ')}.` : 'Agrega el hecho en "hechos" con su fuente.');
        }
        return v;
      case 'lista': {
        if (!Array.isArray(v)) {
          E('E-ESQ-TIPO', ruta, `debe ser una lista [...] (llegó ${tipoDe(v)}).`, 'Usa corchetes.');
          return v;
        }
        if (def.min !== undefined && v.length < def.min) E('E-ESQ-LISTA', ruta, `tiene ${v.length} elemento(s) (mín ${def.min}).`, `Agrega ${def.min - v.length}.`);
        if (def.max !== undefined && v.length > def.max) E('E-ESQ-LISTA', ruta, `tiene ${v.length} elementos (máx ${def.max}).`, `Quita ${v.length - def.max}.`);
        return v.map((x, i) => valor(x, def.de, `${ruta}[${i}]`));
      }
      case 'registro': {
        if (typeof v !== 'object' || v === null || Array.isArray(v)) {
          E('E-ESQ-TIPO', ruta, `debe ser un objeto {"id": "texto"} (llegó ${tipoDe(v)}).`, 'Usa llaves.');
          return v;
        }
        const out = {};
        for (const [k, x] of Object.entries(v)) out[k] = valor(x, def.de, `${ruta}.${k}`);
        return out;
      }
      case 'frases': {
        // Un texto o una lista de textos (frases que se suceden dentro de la escena).
        const lista = Array.isArray(v) ? v : [v];
        if (!lista.length) E('E-ESQ-LISTA', ruta, 'está vacía.', 'Escribe al menos una frase o quita la propiedad.');
        if (def.max_frases && lista.length > def.max_frases) {
          E('E-ESQ-LISTA', ruta, `tiene ${lista.length} frases (máx ${def.max_frases}).`, `Quita ${lista.length - def.max_frases}.`);
        }
        return lista.map((x, i) => valor(x, { ...def, t: 'texto' }, Array.isArray(v) ? `${ruta}[${i}]` : ruta));
      }
      case 'imagen': {
        if (typeof v !== 'string' || !v) {
          E('E-ESQ-TIPO', ruta, 'debe ser la ruta de una imagen dentro de recursos/ del proyecto.', 'Ejemplo: "prod/bala.png".');
          return v;
        }
        if (/^(https?:)?\/\//.test(v) || v.includes('..')) {
          E('E-REC-RUTA', ruta, `${citar(v)}: solo se aceptan rutas locales dentro de recursos/.`, 'Descarga la imagen a recursos/ y usa la ruta relativa.');
          return v;
        }
        if (!/\.(png|jpe?g|webp|svg)$/i.test(v)) E('E-REC-FORMATO', ruta, `${citar(v)} no es PNG/JPG/WEBP/SVG.`, 'Convierte la imagen a PNG o JPG.');
        if (proyecto && !fs.existsSync(path.join(proyecto, 'recursos', v))) {
          E('E-REC-IMAGEN', ruta, `no existe recursos/${v}.`, 'Copia la imagen a esa ruta o quita la propiedad (se usará un ícono).');
        }
        return v;
      }
      case 'objeto':
        if (v === null && def.nulable) return null;
        return objeto(v, def.props, ruta);
      case 'union':
        return def.nombre === 'escena' ? escena(v, ruta) : variante(v, def.nombre, ruta);
      default:
        throw new Error(`catálogo: tipo desconocido ${def.t} en ${ruta}`);
    }
  }

  function objeto(v, props, ruta, extras = {}) {
    if (typeof v !== 'object' || v === null || Array.isArray(v)) {
      E('E-ESQ-TIPO', ruta || '(raíz)', `debe ser un objeto {...} (llegó ${tipoDe(v)}).`, 'Usa llaves.');
      return v;
    }
    const out = {};
    const todas = { ...props, ...extras };
    for (const k of Object.keys(v)) {
      if (k.startsWith('_') || k in todas) continue;
      if (k === 'kicker') {
        E('E-ESTILO-KICKER', `${ruta}.kicker`, 'el kicker numerado ("01 · SECCIÓN") está desactivado por regla de la casa.', 'Quita "kicker".');
        continue;
      }
      const sug = parecido(k, Object.keys(todas));
      E('E-ESQ-DESCONOCIDO', ruta ? `${ruta}.${k}` : k, 'propiedad desconocida.', sug ? `¿Quisiste decir "${sug}"?` : `Válidas: ${Object.keys(todas).join(', ')}.`);
    }
    for (const [k, def] of Object.entries(todas)) {
      const r = ruta ? `${ruta}.${k}` : k;
      if (v[k] === undefined) {
        if (def.defecto !== undefined) out[k] = def.t === 'objeto' && def.defecto !== null ? objeto(structuredClone(def.defecto), def.props, r) : structuredClone(def.defecto);
        else if (!def.opcional) E('E-ESQ-FALTA', r, 'falta y es obligatorio.', def.doc ? `Agrégalo: ${def.doc}` : 'Agrégalo.');
        continue;
      }
      out[k] = valor(v[k], def, r);
    }
    return out;
  }

  // Unión discriminada por `tipo` declarada por un componente (p. ej. items del chat).
  function variante(v, nombre, ruta) {
    const u = catalogo.uniones[nombre];
    if (!u) throw new Error(`catálogo: unión desconocida ${nombre}`);
    if (typeof v !== 'object' || v === null || Array.isArray(v)) {
      E('E-ESQ-TIPO', ruta, `debe ser un objeto con "tipo" (llegó ${tipoDe(v)}).`, `Tipos: ${Object.keys(u.variantes).join(', ')}.`);
      return v;
    }
    const tipos = Object.keys(u.variantes);
    if (!tipos.includes(v.tipo)) {
      const sug = typeof v.tipo === 'string' ? parecido(v.tipo, tipos) : null;
      E('E-ESQ-ENUM', `${ruta}.tipo`, `${citar(v.tipo)} no es un tipo válido.`, sug ? `¿Quisiste decir "${sug}"?` : `Tipos: ${tipos.join(', ')}.`);
      return v;
    }
    return objeto(v, u.variantes[v.tipo].props || {}, ruta, { tipo: { t: 'enum', valores: tipos } });
  }

  function escena(v, ruta) {
    if (typeof v !== 'object' || v === null || Array.isArray(v)) {
      E('E-ESQ-TIPO', ruta, `debe ser un objeto de escena (llegó ${tipoDe(v)}).`, 'Usa llaves con "tipo".');
      return v;
    }
    const tipos = Object.keys(catalogo.escenas);
    if (!tipos.includes(v.tipo)) {
      const sug = typeof v.tipo === 'string' ? parecido(v.tipo, tipos) : null;
      E('E-ESQ-ESCENA', `${ruta}.tipo`, `${citar(v.tipo)} no es un tipo de escena.`, sug ? `¿Quisiste decir "${sug}"?` : `Tipos: ${tipos.join(', ')}.`);
      return v;
    }
    const cat = catalogo.escenas[v.tipo];
    const extras = { ...catalogo.escena_comun, tipo: { t: 'enum', valores: tipos } };
    if (cat.titular) extras.titular = { t: 'frases', opcional: true, max_frases: 3, max_palabras: 16, max_car: 100, anti_viuda: true, doc: 'Cita grande arriba ("“Cotízalo.”"); una frase o varias que se suceden.' };
    if (cat.subtitulo) extras.subtitulo = { t: 'frases', opcional: true, max_frases: 3, max_palabras: 8, max_car: 48, doc: 'Pastilla inferior tipo subtítulo (karaoke); una o varias frases cortas.' };
    const out = objeto(v, cat.props, ruta, extras);
    out.tinte = out.tinte || cat.tinte_defecto || 'ninguno';
    return out;
  }

  if (typeof spec !== 'object' || spec === null || Array.isArray(spec)) {
    E('E-ESQ-TIPO', '(raíz)', 'el spec debe ser un objeto JSON {...}.', 'Copia el ejemplo de oro y edítalo.');
    return { spec, issues };
  }
  const out = objeto(spec, catalogo.raiz.props, '');

  if (Array.isArray(out.escenas)) {
    const vistos = new Set();
    out.escenas.forEach((e, i) => {
      if (!e || typeof e !== 'object') return;
      e.id = e.id || `e${i + 1}`;
      if (vistos.has(e.id)) E('E-ESQ-ID-DUP', `escenas[${i}].id`, `"${e.id}" está repetido.`, 'Usa ids únicos.');
      vistos.add(e.id);
    });
    const ult = out.escenas[out.escenas.length - 1];
    if (ult && ult.tipo !== 'cierre') {
      W('W-ESTRUCTURA-CIERRE', `escenas[${out.escenas.length - 1}]`, 'la última escena no es "cierre" (logo + CTA + aviso).', 'Termina con una escena tipo "cierre".');
    }
    out.escenas.forEach((e, i) => {
      if (e && e.tipo === 'cierre' && i !== out.escenas.length - 1) {
        E('E-ESTRUCTURA-CIERRE', `escenas[${i}]`, '"cierre" solo puede ir al final.', 'Muévela al final.');
      }
    });
  }
  // "Que el video no mienta": las escenas de demostración deben citar hechos confirmados con fuente.
  if (Array.isArray(out.escenas)) {
    const sinRespaldo = out.escenas
      .map((e, i) => ({ e, i }))
      .filter(({ e }) => e && catalogo.escenas[e.tipo] && catalogo.escenas[e.tipo].titular && !(e.respaldo && e.respaldo.length))
      .map(({ i }) => `escenas[${i}]`);
    if (sinRespaldo.length) {
      W('W-HECHOS-FALTAN', sinRespaldo.join(', '), `${sinRespaldo.length} escena(s) de demostración sin "respaldo".`,
        'Agrega en "hechos" lo confirmado con su fuente (brief.md) y cítalo en "respaldo" de cada escena.');
    }
  }
  // "ACME PRO" como producto duplica el logo ("ACME" + "ACME PRO"): el producto va sin la marca.
  const prod = out.marca && typeof out.marca.producto === 'string' ? out.marca.producto.trim() : '';
  const nombre = (tema.marca.nombre || '').trim();
  if (prod && nombre && prod.toLowerCase().startsWith(nombre.toLowerCase())) {
    const resto = prod.slice(nombre.length).trim();
    E('E-MARCA-REPETIDA', 'marca.producto', `"${prod}" repite la marca (el logo ya dice ${nombre}).`,
      resto ? `Usa solo "${resto}".` : 'Deja marca.producto vacío ("").');
  }
  const mus = out.audio && out.audio.musica;
  if (mus && mus.tipo === 'archivo' && !mus.archivo) {
    E('E-ESQ-FALTA', 'audio.musica.archivo', 'falta la ruta de la pista (tipo "archivo").', 'Agrega la ruta, p. ej. "assets/musica/mi-pista.mp3", o usa tipo "procedural".');
  }
  return { spec: out, issues };
}

function tipoDe(v) {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'una lista';
  return { string: 'texto', number: 'número', boolean: 'booleano', object: 'objeto' }[typeof v] || typeof v;
}
