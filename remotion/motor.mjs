#!/usr/bin/env node
// motor.mjs — CLI del motor Remotion (lo invoca scripts/remotion.py; el agente no lo llama directo).
//
//   node remotion/motor.mjs render --composicion <id> --props <props.json> --public-dir <recursos>
//        --salida <mp4> [--crf 17] [--x264-preset slow] [--concurrencia N|50%] [--borrador]
//   node remotion/motor.mjs composiciones [--props <props.json>]   (ids registrados tras empaquetar)
//   node remotion/motor.mjs registro        (crea src/composiciones/proyectos/registro.ts vacío si falta)
//   node remotion/motor.mjs ayuda
//
// Contrato (igual que promo/motor.mjs): stdout = UN objeto JSON; logs y "avance NN%" en stderr.
// Salida: 0 ok · 1 interno · 2 argumentos/spec (el agente corrige) · 3 entorno (faltan deps/navegador).
//
// Codec fijo de la casa: h264 yuv420p (CRF y preset vienen de config.json > remotion vía remotion.py);
// el acabado (BT.709, loudnorm, faststart) lo hace FFmpeg en scripts/remotion.py, no este motor.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.dirname(fileURLToPath(import.meta.url));
const ENTRADA = path.join(RAIZ, 'src', 'index.ts');
const RUTA_REGISTRO = path.join(RAIZ, 'src', 'composiciones', 'proyectos', 'registro.ts');
const log = (...a) => process.stderr.write(a.join(' ') + '\n');

// Igual, byte a byte, que generar_registro() de scripts/remotion.py sin TSX de proyecto (así Python no lo reescribe).
export const REGISTRO_VACIO = [
  '// GENERADO por scripts/remotion.py (validar/render): no editar a mano.',
  "import type { Entrada } from '../../lib/props';",
  '',
  'export const PROYECTOS: Entrada[] = [',
  '];',
  '',
].join('\n');

// index.ts importa ./proyectos/registro, generado y gitignored: en un clon limpio no existe hasta que corre
// remotion.py, y sin él fallan tsc, el Studio y `composiciones`. Devuelve true si lo creó.
export function asegurarRegistro(ruta = RUTA_REGISTRO) {
  if (fs.existsSync(ruta)) return false;
  fs.mkdirSync(path.dirname(ruta), { recursive: true });
  fs.writeFileSync(ruta, REGISTRO_VACIO);
  return true;
}

function terminar(obj, codigo = 0) {
  process.stdout.write(JSON.stringify(obj) + '\n');
  process.exit(codigo);
}

const error = (codigo, msg, arreglo, extra = {}) => ({ codigo, severidad: 'E', ruta: '-', msg, arreglo, ...extra });

function opciones(argv) {
  const o = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      const v = argv[i + 1] !== undefined && !argv[i + 1].startsWith('--') ? argv[++i] : true;
      o[k] = v;
    } else o._.push(a);
  }
  return o;
}

async function cargarRemotion() {
  try {
    const [{ bundle }, renderer] = await Promise.all([import('@remotion/bundler'), import('@remotion/renderer')]);
    return { bundle, ...renderer };
  } catch (e) {
    terminar({ ok: false, errores: [error('E-ENTORNO', `faltan las dependencias del motor Remotion (${e.code || e.message})`,
      'Corre: npm ci --prefix remotion && npx --prefix remotion remotion browser ensure')] }, 3);
  }
}

function leerProps(ruta) {
  if (!ruta) return {};
  try {
    return JSON.parse(fs.readFileSync(ruta, 'utf8'));
  } catch (e) {
    terminar({ ok: false, errores: [error('E-PROPS', `no se pudo leer --props ${ruta}: ${e.message}`,
      'Corre: python3 scripts/remotion.py validar <proyecto>')] }, 2);
  }
}

async function empaquetar(bundle, publicDir) {
  asegurarRegistro();
  let ultimo = -1;
  return bundle({
    entryPoint: ENTRADA,
    publicDir: publicDir || null,
    onProgress: (p) => {
      const d = Math.floor(p / 25) * 25;
      if (d !== ultimo) { ultimo = d; log(`empaquetando ${d}%`); }
    },
  });
}

function concurrencia(v) {
  if (v === undefined || v === true || v === 'auto' || v === 'null' || v === '') return null;
  return /^\d+%$/.test(String(v)) ? String(v) : Number(v);
}

async function cmdComposiciones(o) {
  const R = await cargarRemotion();
  const serveUrl = await empaquetar(R.bundle, o['public-dir']);
  const comps = await R.getCompositions(serveUrl, { inputProps: leerProps(o.props), logLevel: 'error' });
  terminar({ ok: true, ids: comps.map((c) => c.id), composiciones: comps.map((c) => ({
    id: c.id, fps: c.fps, ancho: c.width, alto: c.height, cuadros: c.durationInFrames })) });
}

async function cmdRender(o) {
  const faltan = ['composicion', 'salida'].filter((k) => !o[k] || o[k] === true);
  if (faltan.length) terminar({ ok: false, errores: [error('E-ARGS', `faltan argumentos: ${faltan.map((k) => '--' + k).join(', ')}`,
    'Lo llama scripts/remotion.py; no se invoca a mano.')] }, 2);
  const R = await cargarRemotion();
  const inputProps = leerProps(o.props);
  const t0 = Date.now();
  const serveUrl = await empaquetar(R.bundle, o['public-dir']);
  let composition;
  try {
    composition = await R.selectComposition({ serveUrl, id: o.composicion, inputProps, logLevel: 'error' });
  } catch (e) {
    const comps = await R.getCompositions(serveUrl, { inputProps, logLevel: 'error' }).catch(() => []);
    terminar({ ok: false, errores: [error('E-COMPOSICION', `no existe la composición '${o.composicion}' (${e.message.split('\n')[0]})`,
      `Registradas: ${comps.map((c) => c.id).join(', ') || 'ninguna'}. Revisa remotion.json > composicion y el TSX en src/composiciones/proyectos/.`,
      { ruta: 'composicion' })] }, 2);
  }
  const borrador = o.borrador === true || o.borrador === 'true';
  const total = composition.durationInFrames;
  let ultimo = -1;
  fs.mkdirSync(path.dirname(o.salida), { recursive: true });
  try {
    await R.renderMedia({
      composition,
      serveUrl,
      codec: 'h264',
      outputLocation: o.salida,
      inputProps,
      crf: borrador ? 28 : Number(o.crf || 17),
      x264Preset: borrador ? 'veryfast' : (o['x264-preset'] || 'slow'),
      pixelFormat: 'yuv420p',
      // Sin esto, en Windows los cuadros JPEG llegan como yuvj420p (rango completo, BT.601) y el check de color falla.
      colorSpace: 'bt709',
      audioCodec: 'aac',
      imageFormat: 'jpeg',
      jpegQuality: borrador ? 70 : 95,
      scale: borrador ? 0.5 : 1,
      concurrency: concurrencia(o.concurrencia),
      overwrite: true,
      logLevel: 'error',
      onBrowserDownload: () => {
        log('descargando Chrome Headless Shell (primera vez; ~150 MB)');
        return { version: null, onProgress: () => {} };
      },
      onProgress: ({ progress, renderedFrames }) => {
        const pct = Math.floor(progress * 100);
        if (pct !== ultimo) { ultimo = pct; log(`avance ${String(pct).padStart(3)}% (${renderedFrames}/${total})`); }
      },
    });
  } catch (e) {
    const msg = String(e && e.message || e).split('\n')[0];
    const entorno = /browser|chrome|headless|ENOENT|spawn/i.test(msg);
    terminar({ ok: false, errores: [error(entorno ? 'E-ENTORNO' : 'E-RENDER', msg,
      entorno ? 'Corre: npx --prefix remotion remotion browser ensure (o zsh scripts/preflight.sh)'
              : 'Revisa el TSX (python3 scripts/remotion.py render <proyecto> --verbose muestra el detalle).')] },
      entorno ? 3 : 1);
  }
  terminar({ ok: true, video: path.resolve(o.salida), cuadros: total, fps: composition.fps,
    ancho: Math.round(composition.width * (borrador ? 0.5 : 1)), alto: Math.round(composition.height * (borrador ? 0.5 : 1)),
    duracion: total / composition.fps, segundos: (Date.now() - t0) / 1000, borrador });
}

// Solo despacha cuando se ejecuta como programa (las pruebas importan asegurarRegistro/REGISTRO_VACIO).
const esPrincipal = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (esPrincipal) {
  const o = opciones(process.argv.slice(2));
  const cmd = o._[0];
  if (cmd === 'render') cmdRender(o).catch((e) => terminar({ ok: false, errores: [error('E-INTERNO', String(e && e.stack || e).split('\n')[0], 'Repórtalo al usuario.')] }, 1));
  else if (cmd === 'composiciones') cmdComposiciones(o).catch((e) => terminar({ ok: false, errores: [error('E-INTERNO', String(e && e.message || e), 'Repórtalo al usuario.')] }, 1));
  else if (cmd === 'registro') terminar({ ok: true, registro: RUTA_REGISTRO, creado: asegurarRegistro() });
  else if (cmd === 'ayuda' || !cmd) terminar({ ok: true, uso: 'node remotion/motor.mjs render|composiciones|registro|ayuda (ver cabecera del archivo)' });
  else terminar({ ok: false, errores: [error('E-ARGS', `comando desconocido '${cmd}'`, 'Usa render, composiciones, registro o ayuda.')] }, 2);
}
