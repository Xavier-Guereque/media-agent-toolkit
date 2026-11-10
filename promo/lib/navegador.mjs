// navegador.mjs — Chromium sin ventana sirviendo el runtime desde un origen falso (http://promo.local).
//
// ¿Por qué page.route() y no file://? Chrome bloquea <script type=module> y fetch() en file://.
// Con route() cada petición se responde desde disco y TODO lo demás se aborta: render 100 % offline,
// sin abrir puertos, y un recurso faltante se vuelve un error claro en lugar de un cuadro roto.

import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { RAIZ_MOTOR } from './catalogo.mjs';

const ORIGEN = 'http://promo.local';
const TIPOS = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2', '.txt': 'text/plain',
};

const ARGS = [
  '--force-color-profile=srgb', // PNG en sRGB puro: sin esto los azules/verdes de marca se corren
  '--hide-scrollbars',
  '--mute-audio',
  '--disable-background-timer-throttling',
  '--disable-renderer-backgrounding',
  '--disable-backgrounding-occluded-windows',
];

function dentro(base, rel) {
  const f = path.resolve(base, '.' + path.sep + rel);
  return f.startsWith(path.resolve(base) + path.sep) ? f : null;
}

// Resuelve una URL del origen falso a un archivo en disco (o null).
function resolver(url, { proyecto, tema, sinPrivado }) {
  const u = new URL(url);
  const p = decodeURIComponent(u.pathname);
  const [, raiz, ...resto] = p.split('/');
  const rel = resto.join('/');
  if (raiz === 'runtime') return dentro(path.join(RAIZ_MOTOR, 'runtime'), rel);
  if (raiz === 'componentes') return dentro(path.join(RAIZ_MOTOR, 'componentes'), rel);
  if (raiz === 'tema') {
    const dir = path.join(RAIZ_MOTOR, 'temas', tema);
    const priv = sinPrivado ? null : dentro(path.join(dir, 'privado'), rel);
    if (priv && fs.existsSync(priv)) return priv; // el logo privado (no versionado) tiene prioridad
    return dentro(dir, rel);
  }
  if (raiz === 'p' && proyecto) return dentro(path.join(proyecto, 'recursos'), rel);
  return null;
}

// ¿Por qué el Chrome del sistema y no el Chromium que trae playwright-core? El fijado (rev 1234, v151)
// nunca recibe parches de seguridad; el de /Applications se actualiza solo. Medido: misma velocidad y
// SSIM ≥ 0.997 contra las golden. Si no hay Chrome instalado (Linux, CI) se usa el fijado con aviso.
// PROMO_NAVEGADOR=fijado fuerza el fijado (reproducir un render viejo cuadro por cuadro).
let avisado = false;
async function lanzar(registrar) {
  // chromiumSandbox: Playwright lo trae apagado (lanza con --no-sandbox); encendido, un fallo del
  // renderer queda contenido aunque el navegador tenga CVEs sin parchar.
  const opciones = { headless: true, chromiumSandbox: true, args: ARGS };
  if (process.env.PROMO_NAVEGADOR !== 'fijado') {
    try {
      return await chromium.launch({ ...opciones, channel: 'chrome' });
    } catch {
      if (!avisado) registrar('navegador: Chrome del sistema no disponible; uso el Chromium fijado de Playwright (sin parches de seguridad)');
      avisado = true;
    }
  }
  return chromium.launch(opciones);
}

// sinPrivado: ignora temas/<t>/privado/ (pruebas golden reproducibles en cualquier copia del repo).
export async function abrir({ lt, proyecto, escala = 1, registrar = () => {}, sinPrivado = false }) {
  const navegador = await lanzar(registrar);
  const contexto = await navegador.newContext({
    viewport: { width: Math.round(lt.w * escala), height: Math.round(lt.h * escala) },
    deviceScaleFactor: 1,
    serviceWorkers: 'block',
  });
  const faltantes = [];
  await contexto.route('**/*', async (ruta) => {
    const url = ruta.request().url();
    if (!url.startsWith(ORIGEN + '/')) return ruta.abort();
    const f = resolver(url, { proyecto, tema: lt.tema_nombre, sinPrivado });
    if (!f || !fs.existsSync(f) || !fs.statSync(f).isFile()) {
      // Los CSS de componente son opcionales; el resto se reporta.
      if (!url.endsWith('.css') && !url.includes('/tema/logo')) faltantes.push(url.slice(ORIGEN.length));
      return ruta.fulfill({ status: 404, body: '' });
    }
    return ruta.fulfill({ status: 200, body: fs.readFileSync(f), headers: { 'content-type': TIPOS[path.extname(f)] || 'application/octet-stream' } });
  });
  await contexto.addInitScript((datos) => {
    window.__LT = datos;
  }, lt);
  const pagina = await contexto.newPage();
  const consola = [];
  pagina.on('console', (m) => {
    if (m.type() === 'error') consola.push(m.text());
  });
  pagina.on('pageerror', (e) => consola.push(String(e)));
  await pagina.goto(`${ORIGEN}/runtime/index.html`, { waitUntil: 'load' });
  if (escala !== 1) {
    await pagina.addStyleTag({ content: `#lienzo{transform:scale(${escala});transform-origin:0 0}` });
  }
  // READY con tope: una imagen que nunca decodifica no debe colgar la validación ni el render.
  let reloj;
  const tope = new Promise((ok) => {
    reloj = setTimeout(() => ok({ ok: false, errores: [{ codigo: 'E-RUNTIME-TIEMPO', severidad: 'E', ruta: '?', msg: 'el lienzo no quedó listo en 45 s (fuentes o imágenes que no cargan).', arreglo: 'Revisa las imágenes en recursos/ (formato y tamaño).' }] }), 45000);
  });
  const listo = await Promise.race([pagina.evaluate(() => window.READY), tope]);
  clearTimeout(reloj);
  const cdp = await contexto.newCDPSession(pagina);

  const errores = [...(listo?.errores || [])];
  for (const f of faltantes) errores.push({ codigo: 'E-REC-FALTA', severidad: 'E', ruta: '?', msg: `recurso no encontrado: ${f}`, arreglo: 'Revisa la ruta (relativa a recursos/ del proyecto).' });
  for (const c of consola) errores.push({ codigo: 'E-RUNTIME', severidad: 'E', ruta: '?', msg: c.slice(0, 300) });
  if (errores.length) registrar(`navegador: ${errores.length} error(es) al preparar`);

  return {
    errores,
    async seek(t) {
      await pagina.evaluate((x) => window.seek(x), t);
    },
    // Captura del cuadro t: seek + doble rAF (garantiza que el compositor ya pintó el cambio) + PNG por CDP.
    async cuadro(t) {
      await pagina.evaluate(
        (x) =>
          new Promise((ok) => {
            window.seek(x);
            requestAnimationFrame(() => requestAnimationFrame(() => ok(true)));
          }),
        t,
      );
      const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true, captureBeyondViewport: false, fromSurface: true });
      return Buffer.from(data, 'base64');
    },
    async qa(t) {
      return pagina.evaluate((x) => window.__qa(x), t);
    },
    async hash(t) {
      return pagina.evaluate((x) => {
        window.seek(x);
        return window.__hash();
      }, t);
    },
    pagina,
    async cerrar() {
      await navegador.close();
    },
  };
}
