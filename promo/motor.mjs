#!/usr/bin/env node
// motor.mjs — CLI del motor promo (lo invoca scripts/promo.py; el agente no lo llama directo).
//
//   node promo/motor.mjs validar --proyecto <dir>
//   node promo/motor.mjs cuadros --proyecto <dir> [--t 1.2,3.4] [--ref video.mp4]
//   node promo/motor.mjs render  --proyecto <dir> [--borrador] [--workers N]
//   node promo/motor.mjs ayuda
//   node promo/motor.mjs esquema        (regenera esquema/promo.schema.json desde el catálogo)
//   node promo/motor.mjs golden [--actualizar]   (regresión visual del ejemplo de oro)
//
// Contrato: stdout = UN objeto JSON; logs y avance en stderr.
// Salida: 0 ok · 2 errores del spec (el agente corrige promo.json) · 3 entorno · 4 API externa.

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { cargarCatalogo, cargarTema, temasDisponibles, validarSpec, lineaJson, RAIZ_MOTOR } from './lib/catalogo.mjs';
import { planificar } from './lib/planificador.mjs';
import { abrir } from './lib/navegador.mjs';
import { crearCodificador } from './lib/codificador.mjs';
import { generarEsquema } from './lib/esquema.mjs';
import { golden } from './lib/golden.mjs';

const REPO = path.resolve(RAIZ_MOTOR, '..');
const log = (...a) => process.stderr.write(a.join(' ') + '\n');

function opciones(argv) {
  const o = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
      o[k] = v;
    } else o._.push(a);
  }
  return o;
}

function configPromo() {
  const def = { fps: 30, crf: 17, preset: 'slow', grano: 4, workers: 3 };
  try {
    const c = JSON.parse(fs.readFileSync(path.join(REPO, 'config.json'), 'utf8'));
    return { ...def, ...(c.promo || {}) };
  } catch {
    return def;
  }
}

function terminar(obj, codigo = 0) {
  process.stdout.write(JSON.stringify(obj) + '\n');
  process.exit(codigo);
}

// Huella del motor: si cambia cualquier archivo del runtime/componentes/catálogo/tema, la validación caduca.
function huellaMotor(tema) {
  const h = crypto.createHash('sha1');
  const recorrer = (d) => {
    for (const f of fs.readdirSync(d).sort()) {
      const p = path.join(d, f);
      const st = fs.statSync(p);
      if (st.isDirectory()) recorrer(p);
      else if (/\.(js|mjs|css|json|svg|html)$/.test(f)) h.update(f + st.size + st.mtimeMs);
    }
  };
  for (const d of ['runtime', 'componentes', 'lib']) recorrer(path.join(RAIZ_MOTOR, d));
  h.update(fs.readFileSync(path.join(RAIZ_MOTOR, 'catalogo.json')));  // los catalogo.json de componentes entran por componentes/
  recorrer(path.join(RAIZ_MOTOR, 'temas', tema));
  return h.digest('hex').slice(0, 12);
}

const slugDe = (proyecto) => path.basename(proyecto).replace(/_\d{8}$/, '');
const rutasDe = (proyecto) => {
  const rec = path.join(proyecto, 'recursos');
  return {
    spec: path.join(proyecto, 'promo.json'),
    rec,
    promo: path.join(rec, 'promo'),
    lt: path.join(rec, 'promo', 'linea_tiempo.json'),
    val: path.join(rec, 'promo', 'validacion.json'),
    cuadros: path.join(rec, 'cuadros'),
    render: path.join(rec, 'render'),
  };
};

function deduplicar(issues) {
  const vistos = new Set();
  return issues.filter((x) => {
    const k = `${x.codigo}|${x.ruta}|${x.msg.replace(/\d+(\.\d+)?/g, '#')}`;
    if (vistos.has(k)) return false;
    vistos.add(k);
    return true;
  });
}

// Valida + planea + (opcional) QA del DOM. Escribe linea_tiempo.json y validacion.json.
async function preparar(proyecto, { qaDom = true } = {}) {
  const R = rutasDe(proyecto);
  if (!fs.existsSync(R.spec)) {
    return { ok: false, codigo: 2, errores: [{ codigo: 'E-ESQ-SIN-SPEC', severidad: 'E', ruta: '(archivo)', msg: `no existe ${R.spec}.`, arreglo: 'Crea el proyecto con "promo.py nuevo <slug>".' }], avisos: [] };
  }
  const texto = fs.readFileSync(R.spec, 'utf8');
  let bruto;
  try {
    bruto = JSON.parse(texto);
  } catch (e) {
    const m = /position (\d+)/.exec(e.message);
    const donde = m ? lineaJson(texto, +m[1]) : null;
    return { ok: false, codigo: 2, errores: [{ codigo: 'E-ESQ-JSON', severidad: 'E', ruta: donde ? `línea ${donde.linea}, col ${donde.col}` : '(archivo)', msg: `JSON inválido: ${e.message.split('\n')[0]}`, arreglo: 'Revisa comas, comillas y llaves en ese punto.' }], avisos: [] };
  }
  const catalogo = cargarCatalogo();
  const temas = temasDisponibles();
  const nombreTema = bruto && typeof bruto === 'object' && temas.includes(bruto.tema) ? bruto.tema : 'neutro';
  const tema = cargarTema(nombreTema);
  const { spec, issues } = validarSpec(bruto, { catalogo, tema, temas, proyecto });
  let todos = [...issues];
  let lt = null;
  // Tomas de voz (las genera `promo.py voz`); cambian los tiempos, así que entran a la huella.
  const fVoz = path.join(R.rec, 'voz', 'tiempos.json');
  const voz = spec && spec.audio && spec.audio.voz && fs.existsSync(fVoz) ? JSON.parse(fs.readFileSync(fVoz, 'utf8')) : null;
  if (!todos.some((x) => x.severidad === 'E')) {
    const r = await planificar(spec, { tema, catalogo, slug: slugDe(proyecto), voz });
    todos.push(...r.issues);
    lt = r.lt;
  }
  if (lt && tema._logo === null) {
    todos.push({ codigo: 'W-MARCA-LOGO', severidad: 'W', ruta: 'tema', msg: 'el tema no tiene logo (se usa un wordmark tipográfico).', arreglo: `Copia el SVG a promo/temas/${nombreTema}/privado/${tema.marca.logo}.` });
  }

  if (lt && qaDom && !todos.some((x) => x.severidad === 'E')) {
    const t0 = Date.now();
    const b = await abrir({ lt, proyecto, registrar: log });
    try {
      todos.push(...b.errores);
      if (!b.errores.some((x) => x.severidad === 'E')) {
        for (const t of lt.qa.tiempos) todos.push(...(await b.qa(t)));
        // Determinismo: el mismo t debe dar el mismo estado sin importar el cuadro anterior.
        const muestras = [lt.qa.tiempos[1], lt.qa.tiempos[Math.floor(lt.qa.tiempos.length / 2)], lt.total - 0.5].filter((x) => x !== undefined);
        for (const t of muestras) {
          await b.seek(0);
          const h1 = await b.hash(t);
          await b.seek(lt.total - 1 / lt.fps);
          const h2 = await b.hash(t);
          if (h1 !== h2) {
            todos.push({ codigo: 'E-QA-DETERMINISMO', severidad: 'E', ruta: 'motor', t, msg: `el cuadro ${t}s depende del cuadro anterior.`, arreglo: 'Error del motor: repórtalo (no es del spec).' });
          }
        }
      }
    } finally {
      await b.cerrar();
    }
    log(`qa DOM: ${lt.qa.tiempos.length} instantes en ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  }

  todos = deduplicar(todos);
  const errores = todos.filter((x) => x.severidad === 'E');
  const avisos = todos.filter((x) => x.severidad !== 'E');
  fs.mkdirSync(R.promo, { recursive: true });
  const huella = crypto.createHash('sha1').update(texto).update(huellaMotor(nombreTema)).update(voz ? JSON.stringify(voz) : '').digest('hex').slice(0, 16);
  if (lt) fs.writeFileSync(R.lt, JSON.stringify(lt, null, 1));
  const val = { ok: errores.length === 0, qa_dom: qaDom, huella, errores, avisos, fecha: new Date().toISOString() };
  fs.writeFileSync(R.val, JSON.stringify(val, null, 1));
  const resumen = lt ? { total: lt.total, cuadros: lt.cuadros, escenas: lt.escenas.map((e) => ({ id: e.id, tipo: e.tipo, ini: e.ini, fin: e.fin })) } : null;
  return { ok: errores.length === 0, codigo: errores.length ? 2 : 0, errores, avisos, resumen, lt, huella, archivos: { linea_tiempo: lt ? R.lt : null, validacion: R.val } };
}

// Reutiliza la validación si sigue vigente (mismo spec y mismo motor); si no, la rehace.
async function vigente(proyecto, { qaDom = true } = {}) {
  const R = rutasDe(proyecto);
  try {
    const val = JSON.parse(fs.readFileSync(R.val, 'utf8'));
    const texto = fs.readFileSync(R.spec, 'utf8');
    const bruto = JSON.parse(texto);
    const tema = bruto && typeof bruto === 'object' && temasDisponibles().includes(bruto.tema) ? bruto.tema : 'neutro';
    const fVoz = path.join(R.rec, 'voz', 'tiempos.json');
    const voz = bruto && bruto.audio && bruto.audio.voz && fs.existsSync(fVoz) ? fs.readFileSync(fVoz, 'utf8') : null;
    const huella = crypto.createHash('sha1').update(texto).update(huellaMotor(tema)).update(voz ? JSON.stringify(JSON.parse(voz)) : '').digest('hex').slice(0, 16);
    if (val.huella === huella && val.ok && (val.qa_dom || !qaDom) && fs.existsSync(R.lt)) {
      return { ok: true, lt: JSON.parse(fs.readFileSync(R.lt, 'utf8')), errores: [], avisos: val.avisos };
    }
  } catch {
    /* sin validación previa */
  }
  return preparar(proyecto, { qaDom });
}

// ------------------------------------------------------------------ cuadros + hoja de contacto
function extraerRef(ref, t, destino) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-ss', String(t), '-i', ref, '-frames:v', '1', destino]);
  return r.status === 0 && fs.existsSync(destino);
}

function miniatura(png, ancho = 360) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-i', png, '-vf', `scale=${ancho}:-1:flags=lanczos`, '-f', 'image2pipe', '-c:v', 'mjpeg', '-q:v', '3', '-'], { maxBuffer: 64 << 20 });
  return r.status === 0 ? r.stdout.toString('base64') : null;
}

function escenaEn(lt, t) {
  const vivas = lt.escenas.filter((e) => t >= e.ini && t <= e.fin);
  return vivas[vivas.length - 1] || lt.escenas[lt.escenas.length - 1];
}

async function hojaContacto(b, celdas, salida, { columnas = 5, titulo = '' } = {}) {
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;background:#0d0f13;font:600 15px/1.2 -apple-system,Helvetica,sans-serif;color:#cfd4de}
    h1{font-size:17px;margin:14px 16px 4px;color:#fff} .g{display:grid;grid-template-columns:repeat(${columnas},auto);gap:12px;padding:12px 16px 16px;justify-content:start}
    .c{display:flex;flex-direction:column;gap:6px} .par{display:flex;gap:4px} img{width:${celdas[0]?.ref ? 220 : 300}px;display:block;border-radius:6px}
    .l{color:#9aa3b5;font-weight:500} .l b{color:#fff}</style></head><body><h1>${titulo}</h1><div class="g">${celdas.map((c) => `
    <div class="c"><div class="par"><img src="data:image/jpeg;base64,${c.img}">${c.ref ? `<img src="data:image/jpeg;base64,${c.ref}">` : ''}</div>
    <div class="l"><b>t=${c.t.toFixed(2)}</b> · ${c.etiqueta}${c.ref ? ' · <i>izq: motor · der: referencia</i>' : ''}</div></div>`).join('')}</div></body></html>`;
  const p = await b.pagina.context().newPage();
  await p.setViewportSize({ width: 1600, height: 200 }); // fullPage crece al contenido (sin franja vacía)
  await p.setContent(html);
  await p.screenshot({ path: salida, fullPage: true, type: 'jpeg', quality: 88 });
  await p.close();
}

async function cmdCuadros(proyecto, o) {
  const prep = await vigente(proyecto, { qaDom: false });
  if (!prep.ok) return terminar({ ok: false, errores: prep.errores, avisos: prep.avisos }, 2);
  const { lt } = prep;
  const R = rutasDe(proyecto);
  fs.mkdirSync(R.cuadros, { recursive: true });
  const tiempos = o.t ? String(o.t).split(',').map(Number).filter((x) => x >= 0 && x < lt.total) : lt.qa.tiempos;
  const b = await abrir({ lt, proyecto, registrar: log });
  try {
    if (b.errores.some((x) => x.severidad === 'E')) return terminar({ ok: false, errores: b.errores }, 2);
    const archivos = [];
    const celdas = [];
    for (const t of tiempos) {
      const f = path.join(R.cuadros, `c_${t.toFixed(2)}.png`);
      fs.writeFileSync(f, await b.cuadro(t));
      archivos.push(f);
      const e = escenaEn(lt, t);
      let ref = null;
      if (o.ref) {
        const fr = path.join(R.cuadros, `ref_${t.toFixed(2)}.png`);
        if (extraerRef(o.ref, t, fr)) ref = miniatura(fr, 220);
      }
      celdas.push({ t, img: miniatura(f, o.ref ? 220 : 300), ref, etiqueta: `${e.ruta} ${e.tipo}` });
    }
    const hoja = path.join(R.cuadros, o.ref ? 'hoja_ref.jpg' : 'hoja.jpg');
    await hojaContacto(b, celdas, hoja, { columnas: o.ref ? 4 : 5, titulo: `${path.basename(proyecto)} — ${tiempos.length} cuadros` });
    terminar({ ok: true, cuadros: archivos, hoja });
  } finally {
    await b.cerrar();
  }
}

// ------------------------------------------------------------------ render
async function cmdRender(proyecto, o) {
  const cfg = configPromo();
  const prep = await vigente(proyecto, { qaDom: true });
  if (!prep.ok) return terminar({ ok: false, errores: prep.errores, avisos: prep.avisos }, 2);
  const { lt } = prep;
  const R = rutasDe(proyecto);
  fs.mkdirSync(R.render, { recursive: true });
  const borrador = !!o.borrador;
  const salida = path.join(R.render, borrador ? 'video_borrador.mp4' : 'video_mudo.mp4');
  const N = Math.max(1, Math.min(8, parseInt(o.workers || cfg.workers, 10)));
  const total = lt.cuadros;
  const t0 = Date.now();

  // N procesos Chromium separados (no pestañas: comparten proceso de render y no escalan).
  const navs = await Promise.all(Array.from({ length: N }, () => abrir({ lt, proyecto, registrar: log })));
  const malos = navs.flatMap((b) => b.errores).filter((x) => x.severidad === 'E');
  if (malos.length) {
    await Promise.all(navs.map((b) => b.cerrar()));
    return terminar({ ok: false, errores: deduplicar(malos) }, 2);
  }
  const enc = crearCodificador({ salida, fps: lt.fps, crf: cfg.crf, preset: cfg.preset, grano: cfg.grano, borrador, w: lt.w, h: lt.h });

  // Cuadros intercalados (i ≡ k mod N) + búfer de reorden → el codificador los recibe en orden.
  const VENTANA = 2 * N + 2;
  const listos = new Map();
  let siguiente = 0;
  let esperando = [];
  let cadena = Promise.resolve();
  let ultimoPct = -1;
  let falloRender = null; // si ffmpeg o un navegador fallan, todos los trabajadores se detienen
  const despertar = () => {
    const w = esperando;
    esperando = [];
    w.forEach((f) => f());
  };
  const vaciar = () => {
    cadena = cadena.then(async () => {
      if (falloRender) return;
      try {
        while (listos.has(siguiente)) {
          const png = listos.get(siguiente);
          listos.delete(siguiente);
          await enc.escribir(png);
          siguiente++;
          const pct = Math.floor((siguiente / total) * 10) * 10;
          if (pct !== ultimoPct) {
            ultimoPct = pct;
            log(`avance ${String(pct).padStart(3)}% (${siguiente}/${total})`);
          }
        }
      } catch (e) {
        falloRender = falloRender || e;
      } finally {
        despertar(); // sin esto, un fallo dejaba a los trabajadores esperando para siempre
      }
    });
    return cadena;
  };
  async function trabajador(k) {
    const b = navs[k];
    try {
      for (let i = k; i < total; i += N) {
        while (i - siguiente >= VENTANA && !falloRender) await new Promise((f) => esperando.push(f));
        if (falloRender) throw falloRender;
        listos.set(i, await b.cuadro(i / lt.fps));
        vaciar();
      }
    } catch (e) {
      falloRender = falloRender || e;
      despertar();
      throw falloRender;
    }
  }
  try {
    await Promise.all(navs.map((_, k) => trabajador(k)));
    await vaciar();
    if (falloRender) throw falloRender;
    await enc.cerrar();
  } catch (e) {
    enc.abortar();
    fs.rmSync(salida, { force: true }); // no dejar un MP4 truncado que parezca bueno
    throw e;
  } finally {
    await Promise.all(navs.map((b) => b.cerrar().catch(() => {})));
  }
  const segundos = +((Date.now() - t0) / 1000).toFixed(1);
  terminar({ ok: true, video: salida, cuadros: total, segundos, workers: N, borrador });
}

// ------------------------------------------------------------------ ayuda (catálogo compacto)
// Resumen que el orquestador lee UNA vez: tipos de escena, props con límites y variantes de items.
function cmdAyuda() {
  const cat = cargarCatalogo();
  const tema = cargarTema('neutro');
  const lim = (d) => {
    const x = [];
    if (d.t === 'texto' || d.t === 'frases') {
      if (d.max_palabras) x.push(`≤${d.max_palabras} palabras`);
      if (d.max_car) x.push(`≤${d.max_car} car`);
      if (d.enfasis) x.push('*énfasis*');
      if (d.t === 'frases') x.push(`texto o lista de ≤${d.max_frases || 3}`);
    }
    if (d.t === 'enum') x.push((d.valores || Object.keys(tema.tintes)).join('|'));
    if (d.t === 'booleano') x.push(`true|false`);
    if (d.t === 'entero' || d.t === 'numero') x.push(`${d.t} ${d.min ?? ''}–${d.max ?? ''}`);
    if (d.t === 'imagen') x.push('ruta en recursos/');
    if (d.t === 'lista' && d.de && d.de.t !== 'objeto' && d.de.t !== 'union') x.push(`lista ${d.min ?? 0}–${d.max ?? '∞'} de (${lim(d.de)})`);
    if (d.defecto !== undefined && d.t !== 'objeto') x.push(`def ${JSON.stringify(d.defecto)}`);
    else if (d.opcional) x.push('opcional');
    return x.join(', ');
  };
  const lineas = [];
  const props = (obj, sangria, prefijo = '') => {
    for (const [k, p] of Object.entries(obj)) {
      if (p.t === 'objeto') props(p.props, sangria, `${prefijo}${k}.`);
      else if (p.t === 'lista' && p.de?.t === 'objeto') {
        lineas.push(`${sangria}${prefijo}${k}: lista ${p.min ?? 0}–${p.max ?? '∞'} de {…}${p.opcional ? ', opcional' : ''}`);
        props(p.de.props, sangria + '    ', `${prefijo}${k}[].`);
      } else if (p.t === 'lista' && p.de?.t === 'union') {
        const u = cat.uniones[p.de.nombre];
        lineas.push(`${sangria}${prefijo}${k}: lista ${p.min ?? 0}–${p.max ?? '∞'} de items {"tipo": …}:`);
        for (const [tipo, v] of Object.entries(u.variantes)) {
          const campos = Object.entries(v.props || {}).map(([k2, p2]) => (p2.t === 'objeto' || (p2.t === 'lista' && p2.de?.t === 'objeto') ? `${k2}{…}` : `${k2} (${lim(p2)})`));
          lineas.push(`${sangria}    · ${tipo}: ${campos.join('; ')}`);
          for (const [k2, p2] of Object.entries(v.props || {})) {
            if (p2.t === 'lista' && p2.de?.t === 'objeto') lineas.push(`${sangria}        ${k2}[]: ` + Object.entries(p2.de.props).map(([k3, p3]) => `${k3} (${lim(p3)})`).join('; '));
            if (p2.t === 'objeto') lineas.push(`${sangria}        ${k2}: ` + Object.entries(p2.props).map(([k3, p3]) => `${k3} (${lim(p3)})`).join('; '));
          }
        }
      } else lineas.push(`${sangria}${prefijo}${k}: ${lim(p)}`);
    }
  };
  lineas.push('Raíz de promo.json: salida.duracion (6–60, def 30) · salida.archivo · marca.producto/version · audio.musica.tipo (procedural|archivo|cc0|ninguna) · audio.sfx (ninguno|sutil|normal) · hechos {id: "hecho (fuente: …)"} · escenas[] en orden, SIN tiempos.');
  lineas.push('Comunes a toda escena: tipo · tinte (' + Object.keys(tema.tintes).join('|') + ') · respaldo [ids de hechos] · duracion (solo si hace falta fijarla).');
  for (const [tipo, d] of Object.entries(cat.escenas)) {
    const extra = [d.titular && 'titular (cita arriba, ≤16 palabras, texto o lista ≤3)', d.subtitulo && 'subtitulo (pastilla inferior, ≤8 palabras por frase, texto o lista ≤3)'].filter(Boolean);
    lineas.push(`- ${tipo}: ${d.doc}${extra.length ? ' Acepta ' + extra.join(' y ') + '.' : ''}`);
    props(d.props, '    ');
  }
  terminar({ ok: true, texto: lineas.join('\n') });
}

// ------------------------------------------------------------------ main
const [cmd, ...resto] = process.argv.slice(2);
const o = opciones(resto);
const proyecto = o.proyecto ? path.resolve(String(o.proyecto)) : null;

try {
  if (cmd === 'ayuda') cmdAyuda();
  else if (cmd === 'golden') {
    const res = await golden({ actualizar: !!o.actualizar });
    terminar({ ok: res.every((r) => r.ssim >= 0.98), cuadros: res }, res.every((r) => r.ssim >= 0.98) ? 0 : 2);
  } else if (cmd === 'esquema') {
    const f = path.join(RAIZ_MOTOR, 'esquema', 'promo.schema.json');
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, JSON.stringify(generarEsquema(), null, 1) + '\n');
    terminar({ ok: true, esquema: f });
  }
  else if (!proyecto) terminar({ ok: false, errores: [{ codigo: 'E-USO', severidad: 'E', ruta: '-', msg: 'falta --proyecto <dir>.' }] }, 3);
  else if (cmd === 'validar') {
    const r = await preparar(proyecto, { qaDom: !o['sin-qa'] });
    const { lt, codigo, ...salida } = r;
    terminar(salida, codigo);
  } else if (cmd === 'cuadros') await cmdCuadros(proyecto, o);
  else if (cmd === 'render') await cmdRender(proyecto, o);
  else terminar({ ok: false, errores: [{ codigo: 'E-USO', severidad: 'E', ruta: '-', msg: `comando desconocido: ${cmd}. Usa validar | cuadros | render | ayuda.` }] }, 3);
} catch (e) {
  const entorno = /Executable doesn't exist|browserType.launch|ENOENT.*ffmpeg|spawn ffmpeg/.test(String(e.message));
  terminar({ ok: false, errores: [{ codigo: entorno ? 'E-ENTORNO' : 'E-MOTOR', severidad: 'E', ruta: '-', msg: String(e.message).split('\n')[0].slice(0, 300), arreglo: entorno ? 'Corre: zsh scripts/preflight.sh' : 'Error interno del motor: repórtalo con el promo.json.' }] }, 3);
}
