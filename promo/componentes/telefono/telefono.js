// telefono — la app móvil de la marca en un teléfono tipo iPhone (sin logos de Apple), como el bloque
// 22–24.5 s de la promo de referencia: barra "Pregunta a la IA" → toque al micrófono → "Escuchando" con onda
// de voz; widgets de pedidos y carrito; al final baja una notificación con la respuesta.
//
// El teléfono se construye en unidades lógicas de iPhone (pantalla 393×852 pt) dentro de un
// contenedor con CSS zoom (Z = 1.714 → 708 px de ancho en x 186–894, arriba en y 505), que mantiene
// el texto nítido (un transform: scale lo re-muestrearía). La parte baja se desvanece antes del subtítulo.

import { P, E, clamp, resorte } from '../../runtime/tiempo.js';
import { aparecer, estilo } from '../../runtime/movimiento.js';
import { construirPalabras, ajustar } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';

const Z = 1.714; // 413 pt (pantalla + bisel) → 708 px
const COLORES_PUNTO = ['#45c988', '#4d8bf6', '#96a0b0'];
const N_BARRAS = 5;

// Tamaño de letra más grande (de max a min, en pasos de 0.5) con el que el texto cabe en su caja.
function encoger(el, max, min) {
  for (let fs = max; fs >= min; fs -= 0.5) {
    el.style.fontSize = fs + 'px';
    if (el.scrollWidth <= el.clientWidth + 1) return;
  }
}

// Chispa de IA como la del original (estrella de 4 puntas + dos cruces a la izquierda); Lucide no la trae.
const CHISPA = (tam) => `<svg class="ico" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round">` +
  `<path d="M14.6 3.2c.75 5.1 1.9 6.9 8.2 8.8-6.3 1.9-7.45 3.7-8.2 8.8-.75-5.1-1.9-6.9-8.2-8.8 6.3-1.9 7.45-3.7 8.2-8.8z" fill="currentColor" stroke-width="1.2" stroke-linejoin="round"/>` +
  `<path d="M4.6 2.4v5.2M2 5h5.2M4.6 16.6v5M2.1 19.1h5"/></svg>`;

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// Puro (Node).
export function planear(props) {
  const nN = parsearEnfasis(props.notificacion.texto).length + parsearEnfasis(props.notificacion.titulo).length;
  return {
    pasos: [
      { id: 'telefono', min: 0.4, pref: 0.55 },
      { id: 'vista', min: 0.25, pref: 0.35 }, // la pantalla de inicio se lee antes del toque
      { id: 'mic', min: 0.3, pref: 0.4, cue: 'tick' },
      { id: 'escucha', min: 0.7, pref: 1.0 },
      { id: 'notif', min: 0.45, pref: 0.55, cue: 'notif' },
    ],
    // La notificación se deja lo suficiente para leerla por encima (el titular lleva la idea).
    reposo: { min: Math.max(0.7, 0.05 * nN + 0.2), pref: Math.max(1.2, 0.09 * nN + 0.4) },
  };
}

// Ícono de la app: la inicial del logo (primer glifo del SVG) sobre un recuadro oscuro, como el "S"
// de ACME PRO. Si el tema no tiene logo, la inicial del nombre en tipografía.
function htmlIcono(ctx, clase) {
  const m = ctx.marca;
  const letra = esc(String(m.nombre || 'A').slice(0, 1));
  return `<div class="tl-icono ${clase}">${m.svg ? `<span class="tl-mono">${m.svg}</span>` : `<span class="tl-mono-txt">${letra}</span>`}</div>`;
}

// viewBox del primer glifo del logo: paths cuyo borde izquierdo cae dentro de 0.9 × alto del inicio.
function recortarMonograma(svg) {
  if (!svg) return;
  const piezas = [...svg.querySelectorAll('path,polygon,rect,circle,ellipse')]
    .map((el) => el.getBBox())
    .filter((b) => b.width > 0.5 && b.height > 0.5);
  if (!piezas.length) return;
  const arriba = Math.min(...piezas.map((b) => b.y));
  const abajo = Math.max(...piezas.map((b) => b.y + b.height));
  const alto = abajo - arriba;
  const x0 = Math.min(...piezas.map((b) => b.x));
  const primeras = piezas.filter((b) => b.x < x0 + 0.9 * alto);
  const l = Math.min(...primeras.map((b) => b.x));
  const r = Math.max(...primeras.map((b) => b.x + b.width));
  const t = Math.min(...primeras.map((b) => b.y));
  const bj = Math.max(...primeras.map((b) => b.y + b.height));
  const lado = Math.max(r - l, bj - t);
  const cx = (l + r) / 2;
  const cy = (t + bj) / 2;
  svg.setAttribute('viewBox', `${(cx - lado / 2).toFixed(2)} ${(cy - lado / 2).toFixed(2)} ${lado.toFixed(2)} ${lado.toFixed(2)}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
}

export function montar(raiz, props, lt, ctx) {
  const ruta = lt.ruta;
  const qa = (prop, extra = '') => `data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${ruta}.${prop}"${extra}`;
  const widgets = props.widgets;
  const solo = widgets.length === 1;

  const htmlWidget = (w, i) => {
    const r = `widgets[${i}]`;
    let cuerpo;
    if (w.tipo === 'lista') {
      cuerpo = w.lineas.map((l, j) => `<div class="tl-linea"><i style="background:${COLORES_PUNTO[j % 3]}"></i>` +
        `<span ${qa(`${r}.lineas[${j}]`, ' data-qa-caja="1" data-qa-min-fs="20"')}>${esc(l)}</span></div>`).join('');
    } else {
      cuerpo = `<div class="tl-cifra" ${qa(`${r}.cifra`)}>${esc(w.cifra)}</div>` +
        (w.detalle ? `<div class="tl-detalle" ${qa(`${r}.detalle`, ' data-qa-caja="1" data-qa-min-fs="20"')}>${esc(w.detalle)}</div>` : '') +
        (w.enlace ? `<div class="tl-enlace" ${qa(`${r}.enlace`, ' data-qa-caja="1" data-qa-min-fs="20"')}>${esc(w.enlace)}<span class="tl-chev">›</span></div>` : '');
    }
    return `<div class="tl-widget tl-w-${w.tipo}${solo ? ' tl-solo' : ''}" style="left:${solo ? 20 : 20 + i * 184}px">
        <div class="tl-w-titulo" ${qa(`${r}.titulo`, ' data-qa-caja="1" data-qa-min-fs="18"')}>${esc(w.titulo)}</div>
        <div class="tl-w-cuerpo">${cuerpo}</div>
      </div>`;
  };

  const logo = ctx.marca.svg
    ? `<span class="tl-marca" style="width:${(10 * (ctx.marca.proporcion_logo || 8.45)).toFixed(1)}px">${ctx.marca.svg}</span>`
    : `<span class="tl-marca tl-marca-txt">${esc(ctx.marca.nombre)}</span>`;
  const barras = Array.from({ length: N_BARRAS }, () => '<i></i>').join('');
  const gid = `tl-${lt.id}-brillo`;

  raiz.insertAdjacentHTML('beforeend', `
    <svg class="tl-defs" width="0" height="0" aria-hidden="true"><defs>
      <linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.55" stop-color="#e6e8ec"/><stop offset="1" stop-color="#9ea3ab"/></linearGradient>
    </defs></svg>
    <div class="tl-mascara">
      <div class="tl-ubic"><div class="tl-mov"><div class="tl-zoom" style="zoom:${Z}">
        <div class="tl-tel"><div class="tl-pantalla">
          <div class="tl-isla"></div>
          <div class="tl-hora">9:41</div>
          <div class="tl-senal">5G<i></i></div>
          <div class="tl-busca">
            ${logo}<span class="tl-div"></span>
            <span class="tl-chispas">${CHISPA(22)}</span>
            <span class="tl-estados">
              <span class="tl-guia" ${qa('busqueda', ' data-qa-caja="1"')}>${esc(props.busqueda)}</span>
              <span class="tl-escucha"><span class="tl-escucha-txt" ${qa('escucha')}>${esc(props.escucha)}</span><span class="tl-barras">${barras}</span></span>
            </span>
            <span class="tl-mic"><span class="tl-toque"></span><span class="tl-onda"></span>${ctx.icono('mic', { tam: 21, trazo: 2 })}</span>
          </div>
          ${widgets.map(htmlWidget).join('')}
          <div class="tl-app">${htmlIcono(ctx, 'tl-icono-app')}<div class="tl-app-txt" ${qa('app', ' data-qa-min-fs="20"')}></div></div>
          <div class="tl-notif">
            ${htmlIcono(ctx, 'tl-icono-notif')}
            <div class="tl-n-cab"><span class="tl-n-titulo" ${qa('notificacion.titulo', ' data-qa-caja="1"')}>${esc(props.notificacion.titulo)}</span><span class="tl-n-hora">ahora</span></div>
            <div class="tl-n-texto" ${qa('notificacion.texto')}></div>
          </div>
        </div></div>
      </div></div></div>
    </div>`);

  const q = (s) => raiz.querySelector(s);
  const qq = (s) => [...raiz.querySelectorAll(s)];
  for (const s of qq('.tl-mono svg')) s.style.fill = `url(#${gid})`;
  const appTxt = q('.tl-app-txt');
  const spansApp = construirPalabras(appTxt, parsearEnfasis(props.app));
  const nTexto = q('.tl-n-texto');
  const spansN = construirPalabras(nTexto, parsearEnfasis(props.notificacion.texto));
  const mov = q('.tl-mov');
  const guia = q('.tl-guia');
  const escucha = q('.tl-escucha');
  const barras_ = qq('.tl-barras i');
  const toque = q('.tl-toque');
  const onda = q('.tl-onda');
  const micIco = q('.tl-mic svg');
  const notif = q('.tl-notif');
  const bloques = [...qq('.tl-widget'), q('.tl-app')];
  const chispas = q('.tl-chispas');

  // Onda de voz: cada barra con su frecuencia y fase (azar determinista por escena).
  const rng = ctx.rng(`onda:${lt.id}`);
  const ondas = barras_.map(() => ({ f1: 2.2 + rng() * 2.6, f2: 5 + rng() * 4, fase: rng() * Math.PI * 2, base: 0.2 + rng() * 0.12 }));
  const p = lt.pasos;

  return {
    medir() {
      for (const s of qq('.tl-mono svg')) recortarMonograma(s);
      encoger(guia, 15.5, 14);
      ajustar(appTxt, spansApp, { max: 13, min: 11.5, paso: 0.5, lineas: 2 });
      ajustar(nTexto, spansN, { max: 14.5, min: 13, paso: 0.5, lineas: 3 });
    },
    actualizar(t) {
      // Entrada: sube un poco desde abajo con desenfoque, sin slide largo.
      aparecer(mov, P(t, p.telefono.ini, 0.6, E.outCubic), { dy: 46, blur: 10, escala: 0.975 });
      // Los widgets se asientan mientras el teléfono termina de subir (sin pantalla vacía).
      bloques.forEach((el, i) => aparecer(el, P(t, p.telefono.ini + 0.16 + i * 0.07, 0.42, E.outCubic), { dy: 8, blur: 4 }));

      // Toque al micrófono: resaltado que aparece con resorte y una onda que se expande una vez.
      const tm = t - p.mic.ini;
      const kT = tm > 0 ? resorte(tm, { zeta: 0.7, omega: 22 }) : 0;
      const oT = P(tm, 0, 0.08, E.lin) * (1 - P(tm, 0.32, 0.35, E.inOutQuad));
      estilo(toque, { opacity: String(+oT.toFixed(4)), transform: `scale(${(0.55 + 0.45 * kT).toFixed(4)})` });
      const kO = P(tm, 0.06, 0.75, E.outCubic);
      estilo(onda, { opacity: String(+(tm > 0.06 ? 0.75 * (1 - kO) : 0).toFixed(4)), transform: `scale(${(1 + 1.05 * kO).toFixed(4)})` });

      // Guía → "Escuchando" + onda de voz; al llegar la notificación vuelve la guía.
      const tn = t - p.notif.ini;
      const kE = P(tm, 0.1, 0.28, E.outCubic) * (1 - P(tn, 0.1, 0.3, E.inOutQuad));
      aparecer(guia, 1 - kE, { dy: 0, blur: 5 });
      aparecer(escucha, kE, { dy: 0, blur: 5 });
      barras_.forEach((b, i) => {
        const o = ondas[i];
        const v = 0.55 + 0.45 * Math.sin(t * o.f1 * Math.PI + o.fase) * (0.55 + 0.45 * Math.sin(t * o.f2 * Math.PI + o.fase * 1.7));
        const h = o.base + (1 - o.base) * clamp(v) * kE;
        estilo(b, { transform: `scaleY(${h.toFixed(4)})` });
      });
      estilo(micIco, { opacity: String(+(0.85 + 0.15 * kE).toFixed(4)) });
      estilo(chispas, { filter: kE > 0.01 ? `drop-shadow(0 0 ${(6 * kE).toFixed(2)}px rgba(77,139,246,${(0.7 * kE).toFixed(3)}))` : 'none' });

      // Notificación: baja desde arriba de la pantalla con resorte (leve rebote) y se enfoca.
      const kN = tn > 0 ? resorte(tn, { zeta: 0.68, omega: 13 }) : 0;
      const oN = P(tn, 0, 0.16, E.outQuad);
      const bN = P(tn, 0, 0.3, E.outCubic);
      estilo(notif, {
        opacity: String(+oN.toFixed(4)),
        visibility: oN <= 0.001 ? 'hidden' : 'visible',
        transform: `translate3d(0,${(-130 * (1 - kN)).toFixed(2)}px,0)`,
        filter: bN < 0.998 ? `blur(${(6 * (1 - bN)).toFixed(2)}px)` : 'none',
      });
    },
  };
}
