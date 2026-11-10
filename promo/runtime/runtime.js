// runtime.js — arranque del lienzo en el navegador.
//
// Contrato con Node (lib/navegador.mjs):
//   window.__LT            línea de tiempo resuelta (la inyecta addInitScript antes de cargar)
//   window.READY           Promise<{ok, errores}>: fuentes cargadas, imágenes decodificadas, medidas hechas
//   window.seek(t)         dibuja el cuadro exacto del segundo t (función pura de t)
//   window.__qa(t)         seek(t) + revisión del DOM → Issue[]
//   window.__hash()        huella del estado animado (para probar determinismo)
//   window.CUES            efectos de sonido planeados (los mismos tiempos que el audio)

import { P, E, mulberry32, hashTexto } from './tiempo.js';
import * as mov from './movimiento.js';
import * as texto from './texto.js';
import { ICONOS } from './iconos.js';
import { Gestor } from './escena.js';
import { revisar } from './qa.js';

const LT = window.__LT;
const errores = [];

function cargarCss(href) {
  return new Promise((ok) => {
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = href;
    l.onload = () => ok(true);
    l.onerror = () => ok(false);
    document.head.appendChild(l);
  });
}

async function texto_o_null(url) {
  try {
    const r = await fetch(url);
    return r.ok ? await r.text() : null;
  } catch {
    return null;
  }
}

// El SVG del logo se inserta en línea para que `currentColor` lo pinte con el color del tema.
function limpiarSvg(s) {
  if (!s) return null;
  return s
    .replace(/<\?xml[\s\S]*?\?>/g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+="[^"]*"/gi, '')
    .trim();
}

function icono(nombre, { tam = 24, trazo = 2, clase = '' } = {}) {
  const cuerpo = ICONOS[nombre];
  if (!cuerpo) {
    errores.push({ codigo: 'E-RUNTIME-ICONO', severidad: 'E', ruta: '?', msg: `ícono desconocido: ${nombre}` });
    return '';
  }
  return `<svg class="ico ${clase}" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="${trazo}" stroke-linecap="round" stroke-linejoin="round">${cuerpo}</svg>`;
}

function aplicarVariables(tema) {
  const raiz = document.documentElement.style;
  raiz.setProperty('--w', LT.w + 'px');
  raiz.setProperty('--h', LT.h + 'px');
  for (const [k, v] of Object.entries(tema.colores)) raiz.setProperty(`--c-${k.replace(/_/g, '-')}`, v);
  raiz.setProperty('--f-titulo', `'${tema.fuentes.titulo}'`);
  raiz.setProperty('--f-texto', `'${tema.fuentes.texto}'`);
  raiz.setProperty('--f-mono', `'${tema.fuentes.mono}'`);
  raiz.setProperty('--titular-x', tema.titular.x + 'px');
  raiz.setProperty('--titular-y', tema.titular.y + 'px');
  raiz.setProperty('--titular-ancho', tema.titular.ancho + 'px');
}

let gestor = null;

async function iniciar() {
  const tema = LT.tema;
  aplicarVariables(tema);
  await cargarCss('/tema/tema.css');

  // Módulos de componentes (JS + CSS propios). El fondo siempre está.
  const tipos = [...new Set(['fondo', ...LT.escenas.map((e) => e.tipo)])];
  const modulos = {};
  for (const tipo of tipos) {
    modulos[tipo] = await import(`/componentes/${tipo}/${tipo}.js`);
    await cargarCss(`/componentes/${tipo}/${tipo}.css`);
  }

  const marca = {
    ...tema.marca,
    ...(LT.marca || {}),
    svg: limpiarSvg(await texto_o_null(`/tema/${tema.marca.logo}`)),
  };
  const marcas = { whatsapp: limpiarSvg(await texto_o_null('/tema/marcas/whatsapp.svg')) };

  const ctx = {
    tema,
    w: LT.w,
    h: LT.h,
    fps: LT.fps,
    P,
    E,
    mov,
    texto,
    icono,
    marca,
    marcas,
    url: (ruta) => '/p/' + String(ruta).split('/').map(encodeURIComponent).join('/'),
    rng: (clave) => mulberry32(hashTexto(`${LT.semilla}:${clave}`)),
    error: (e) => errores.push(e),
  };

  const fondo = modulos.fondo.montar(document.getElementById('fondo'), ctx);
  gestor = new Gestor({ raiz: document.getElementById('escenas'), lt: LT, ctx, modulos, fondo });
  gestor.montar();

  // Fuentes: document.fonts.ready solo espera las caras ya pedidas; se piden explícitamente
  // con el texto real del spec (así se bajan también los subconjuntos latin-ext que hagan falta).
  const muestra = LT.texto_total || 'AaÁáÉéÍíÓóÚúÑñ¿?¡!0123456789';
  await Promise.all(tema.fuentes.cargar.map((f) => document.fonts.load(f, muestra).catch(() => null)));
  await document.fonts.ready;
  for (const f of tema.fuentes.cargar) {
    if (!document.fonts.check(f, muestra)) {
      errores.push({ codigo: 'E-QA-FUENTE', severidad: 'E', ruta: 'tema', msg: `no cargó la fuente ${f}` });
    }
  }

  // Imágenes: decodificadas antes del primer cuadro; su src nunca cambia después.
  for (const img of document.querySelectorAll('img')) {
    try {
      await img.decode();
    } catch {
      errores.push({ codigo: 'E-QA-IMG', severidad: 'E', ruta: img.dataset.qaRuta || '?', msg: `no se pudo cargar la imagen ${img.getAttribute('src')}`, arreglo: 'Revisa que el archivo exista en recursos/.' });
    }
  }

  await gestor.medir();
  gestor.seek(0);
  window.CUES = LT.cues || [];
  return { ok: !errores.some((e) => e.severidad === 'E'), errores };
}

window.seek = (t) => {
  gestor.seek(t);
  return true;
};

window.__qa = (t) => {
  gestor.seek(t);
  return revisar(t, { tema: LT.tema, w: LT.w, h: LT.h });
};

window.__hash = () => {
  // Solo lo visible: las escenas ocultas (display:none) conservan estilos de su última visita,
  // pero no se pintan; contarlas daría falsos positivos de no determinismo.
  let s = '';
  const vivos = [document.getElementById('fondo'), ...document.querySelectorAll('#escenas > .escena')]
    .filter((e) => e.style.display !== 'none');
  const nodos = vivos.flatMap((e) => [e, ...e.querySelectorAll('*')]);
  for (const el of nodos) {
    const st = el.getAttribute('style');
    if (st) s += st + '|';
    if (el.tagName === 'CANVAS' && el.width && el.height) {
      // Muestra dispersa de píxeles: suficiente para detectar un canvas no determinista.
      const d = el.getContext('2d').getImageData(0, 0, el.width, el.height).data;
      for (let i = 0; i < d.length; i += 4099) s += d[i];
    }
  }
  return hashTexto(s).toString(16);
};

window.READY = iniciar().catch((e) => ({
  ok: false,
  errores: [...errores, { codigo: 'E-RUNTIME', severidad: 'E', ruta: '?', msg: String((e && e.stack) || e) }],
}));
