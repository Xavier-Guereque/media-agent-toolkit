// vendorizar.mjs — copia al repo los recursos de terceros que el motor usa en render,
// para que el render sea 100 % offline y no dependa de node_modules en tiempo de ejecución.
//
//   node herramientas/vendorizar.mjs
//
// - Fuentes variables (OFL): Sora, Figtree, JetBrains Mono → temas/neutro/fuentes/ + licencias
// - Ícono de WhatsApp (Simple Icons, CC0) → temas/neutro/marcas/whatsapp.svg
// - Subconjunto de íconos Lucide (ISC) → runtime/iconos.js (el catálogo expone solo estos nombres)

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const NM = path.join(RAIZ, 'node_modules');
const TEMA = path.join(RAIZ, 'temas', 'neutro');

const FUENTES = [
  ['@fontsource-variable/sora', 'sora'],
  ['@fontsource-variable/figtree', 'figtree'],
  ['@fontsource-variable/jetbrains-mono', 'jetbrains-mono'],
];

// Íconos disponibles para los componentes (nombre en el spec → archivo de Lucide).
export const ICONOS = [
  'check', 'circle-check', 'check-check', 'loader-circle', 'search', 'file-text', 'file-spreadsheet', 'mic',
  'arrow-up', 'arrow-right', 'paperclip', 'globe', 'shield-check', 'truck', 'key-round', 'clock', 'history',
  'maximize-2', 'plus', 'x', 'chevron-left', 'zap', 'sparkles', 'camera', 'image', 'message-circle',
  'smartphone', 'bell', 'shopping-cart', 'package', 'map-pin', 'download', 'brain', 'database', 'wifi',
  'signal', 'battery-full', 'play', 'phone', 'mail', 'store', 'star', 'calendar', 'qr-code', 'wrench', 'cpu',
  'layers', 'scan-line', 'receipt', 'badge-check', 'rotate-cw', 'send', 'headphones', 'hard-drive', 'cctv',
  'video', 'building-2', 'user', 'bot', 'audio-lines',
];

function copiar(origen, destino) {
  fs.mkdirSync(path.dirname(destino), { recursive: true });
  fs.copyFileSync(origen, destino);
}

function fuentes() {
  const dest = path.join(TEMA, 'fuentes');
  for (const [pkg, base] of FUENTES) {
    for (const sub of ['latin', 'latin-ext']) {
      const f = `${base}-${sub}-wght-normal.woff2`;
      copiar(path.join(NM, pkg, 'files', f), path.join(dest, f));
    }
    copiar(path.join(NM, pkg, 'LICENSE'), path.join(dest, 'licencias', `${base}-OFL.txt`));
  }
  console.error(`fuentes → ${path.relative(RAIZ, dest)}`);
}

function marcas() {
  const svg = fs.readFileSync(path.join(NM, 'simple-icons', 'icons', 'whatsapp.svg'), 'utf8');
  const dest = path.join(TEMA, 'marcas', 'whatsapp.svg');
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  // Simple Icons es CC0; se deja constancia de la fuente en el propio archivo.
  fs.writeFileSync(dest, `<!-- Simple Icons (CC0 1.0) — https://simpleicons.org -->\n` +
    svg.replace('<svg ', '<svg fill="currentColor" '));
  console.error(`marcas → ${path.relative(RAIZ, dest)}`);
}

function iconos() {
  const salida = {};
  for (const n of ICONOS) {
    const svg = fs.readFileSync(path.join(NM, 'lucide-static', 'icons', `${n}.svg`), 'utf8');
    // Solo el contenido interno; el <svg> contenedor lo arma el runtime con el tamaño del componente.
    const cuerpo = svg.replace(/<!--[\s\S]*?-->/g, '').replace(/^[\s\S]*?<svg[\s\S]*?>/, '').replace(/<\/svg>\s*$/, '');
    salida[n] = cuerpo.replace(/\s+/g, ' ').trim();
  }
  const js = `// GENERADO por herramientas/vendorizar.mjs — no editar a mano.\n` +
    `// Íconos Lucide (ISC License, Copyright (c) Lucide Icons and Contributors).\n` +
    `export const ICONOS = ${JSON.stringify(salida, null, 0).replace(/","/g, '",\n  "')};\n`;
  fs.writeFileSync(path.join(RAIZ, 'runtime', 'iconos.js'), js);
  console.error(`iconos → runtime/iconos.js (${ICONOS.length})`);
}

fuentes();
marcas();
iconos();
