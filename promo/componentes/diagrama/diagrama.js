// diagrama — "memoria": orígenes arriba (Web · WhatsApp · App) unidos por líneas punteadas que fluyen
// hacia una pastilla central con brillo; debajo, chips de contexto y un chat breve. Es el bloque
// 19.5–22 s de la promo de referencia. Medidas de la referencia (1080×1920): nodos 202×115 en y≈505,
// pastilla 302×110 en y≈712, chips de 42 px en y≈856 y tarjeta de chat hasta y≈1405.
//
// La geometría es fija (se calcula al montar a partir del número de nodos), así las líneas no
// dependen de medir el layout; en actualizar(t) solo se animan máscaras, desplazamientos y opacidades.

import { P, E, resorte } from '../../runtime/tiempo.js';
import { aparecer, estilo, trazar, opacidad } from '../../runtime/movimiento.js';
import { construirPalabras, ajustar } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';
import { animarPuntos, pulso } from '../../runtime/ui.js';

const NODO = { y: 510, h: 114 };
const REJILLA = { 2: { w: 232, sep: 170 }, 3: { w: 202, sep: 86 }, 4: { w: 190, sep: 40 } };
const CENTRO = { x: 389, y: 712, w: 302, h: 108 };
const CHIPS_Y = 856;
const CHAT = { y: 954, h: 446 }; // termina en y = 1400 (arriba del subtítulo)
const G_TEXTO = 12; // etiqueta del asistente → texto
const G_BURBUJA = 34; // burbuja → etiqueta del asistente
const PERIODO = 12.5; // periodo del punteado (px)
const GUION = 3.2; // largo de cada punto (más los remates redondos)

const ICONOS = {
  web: 'globe', telefono: 'phone', correo: 'mail', chat: 'message-circle', tienda: 'store', usuario: 'user', bot: 'bot',
  camara: 'cctv', carrito: 'shopping-cart', datos: 'database', calendario: 'calendar', app: 'smartphone',
};
const ICONO_CENTRO = { cerebro: 'brain', datos: 'database', capas: 'layers' }; // chispas = CHISPA propia

// Chispa de IA como la del original (estrella de 4 puntas + dos cruces a la izquierda); Lucide no la trae.
const CHISPA = (tam, clase = '') => `<svg class="ico chispa ${clase}" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round">` +
  `<path d="M14.6 3.2c.75 5.1 1.9 6.9 8.2 8.8-6.3 1.9-7.45 3.7-8.2 8.8-.75-5.1-1.9-6.9-8.2-8.8 6.3-1.9 7.45-3.7 8.2-8.8z" fill="currentColor" stroke-width="1.2" stroke-linejoin="round"/>` +
  `<path d="M4.6 2.4v5.2M2 5h5.2M4.6 16.6v5M2.1 19.1h5"/></svg>`;

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// Puro (Node).
export function planear(props) {
  const nR = parsearEnfasis(props.respuesta).length;
  const revR = Math.max(0, nR - 1) * 0.022 + 0.3;
  const pasos = [
    { id: 'tarjeta', min: 0.2, pref: 0.25 },
    { id: 'nodos', min: 0.3, pref: 0.45, cue: 'pop', g: 0.7 },
    { id: 'pregunta', min: 0.25, pref: 0.35, cue: 'tick', g: 0.8 },
    { id: 'conexion', min: 0.3, pref: 0.45 },
    { id: 'centro', min: 0.25, pref: 0.4, cue: 'pop' },
    { id: 'pensando', min: 0.35, pref: 0.55 },
  ];
  if (props.chips && props.chips.length) pasos.push({ id: 'chips', min: 0.25 + 0.06 * props.chips.length, pref: 0.3 + 0.1 * props.chips.length, cue: 'tick', g: 0.6 });
  pasos.push({ id: 'respuesta', min: revR, pref: revR + 0.15, cue: 'tecleo', g: 0.5 });
  // La respuesta es apoyo (el mensaje lo lleva el titular): se deja lo suficiente para hojearla.
  return { pasos, reposo: { min: Math.max(0.6, 0.04 * nR + 0.2), pref: Math.max(1.1, 0.07 * nR + 0.4) } };
}

// Curva de un nodo (abajo al centro) a la parte alta de la pastilla: baja, se abre en diagonal suave y
// converge en el centro, como los "rayos" punteados del original.
function curva(x0, y0, x1, y1) {
  const dy = y1 - y0;
  return [[x0, y0], [x0, y0 + 0.55 * dy], [x1 - 0.3 * (x1 - x0), y1 - 0.35 * dy], [x1, y1]];
}
const dCurva = (c) => `M${c[0][0]} ${c[0][1]}C${c[1][0]} ${c[1][1]} ${c[2][0]} ${c[2][1]} ${c[3][0]} ${c[3][1]}`;
function largoCurva(c, n = 96) {
  const pt = (u) => {
    const v = 1 - u;
    return [0, 1].map((k) => v * v * v * c[0][k] + 3 * v * v * u * c[1][k] + 3 * v * u * u * c[2][k] + u * u * u * c[3][k]);
  };
  let L = 0;
  let prev = pt(0);
  for (let i = 1; i <= n; i++) {
    const q = pt(i / n);
    L += Math.hypot(q[0] - prev[0], q[1] - prev[1]);
    prev = q;
  }
  return L;
}

export function montar(raiz, props, lt, ctx) {
  const n = props.nodos.length;
  const rej = REJILLA[n] || REJILLA[3];
  const x0 = Math.round((ctx.w - (n * rej.w + (n - 1) * rej.sep)) / 2);
  const cx = CENTRO.x + CENTRO.w / 2;
  const yBajo = NODO.y + NODO.h;
  const uid = `dg-${lt.id}`;

  const nodosHtml = props.nodos.map((nd, i) => {
    const icono = nd.icono === 'whatsapp' && ctx.marcas.whatsapp
      ? `<span class="dg-ico-marca">${ctx.marcas.whatsapp}</span>`
      : ctx.icono(ICONOS[nd.icono] || (nd.icono === 'whatsapp' ? 'message-circle' : 'globe'), { tam: 34, trazo: 2 });
    return `<div class="dg-nodo dg-ico-${nd.icono}" style="left:${x0 + i * (rej.w + rej.sep)}px;width:${rej.w}px">
        <div class="dg-nodo-ico">${icono}</div>
        <div class="dg-nodo-txt" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.nodos[${i}].texto" data-qa-caja="1" data-qa-min-fs="20">${esc(nd.texto)}</div>
      </div>`;
  }).join('');

  const curvas = props.nodos.map((_, i) => curva(x0 + i * (rej.w + rej.sep) + rej.w / 2, yBajo, cx, CENTRO.y));
  const largos = curvas.map((c) => largoCurva(c));
  const svg = `<svg class="dg-lineas" width="${ctx.w}" height="${CENTRO.y + 20}" viewBox="0 0 ${ctx.w} ${CENTRO.y + 20}">
      <defs>
        <linearGradient id="${uid}-g" gradientUnits="userSpaceOnUse" x1="0" y1="${yBajo}" x2="0" y2="${CENTRO.y}">
          <stop offset="0" stop-color="#8d97b3" stop-opacity="0.7"/><stop offset="1" stop-color="#a9c2ff"/>
        </linearGradient>
        ${curvas.map((c, i) => `<mask id="${uid}-m${i}" maskUnits="userSpaceOnUse" x="0" y="0" width="${ctx.w}" height="${CENTRO.y + 20}">
          <path class="dg-mascara" d="${dCurva(c)}" fill="none" stroke="#fff" stroke-width="16" stroke-linecap="round"/></mask>`).join('')}
      </defs>
      ${curvas.map((c, i) => `<path class="dg-punteado" mask="url(#${uid}-m${i})" d="${dCurva(c)}" fill="none" stroke="url(#${uid}-g)" stroke-width="4.8" stroke-linecap="round" stroke-dasharray="${GUION} ${PERIODO - GUION}"/>`).join('')}
    </svg>`;

  const chips = props.chips || [];
  const marca = ctx.marca;
  const asistente = [marca.nombre, marca.producto].filter(Boolean).join(' ');
  const chispas = CHISPA(26, 'dg-chispas');

  raiz.insertAdjacentHTML('beforeend', `
    <div class="dg-aura"></div>
    ${svg}
    <div class="dg-union"></div>
    ${nodosHtml}
    <div class="dg-centro"><span class="dg-centro-ico">${ICONO_CENTRO[props.icono_centro] ? ctx.icono(ICONO_CENTRO[props.icono_centro], { tam: 36, trazo: 1.8 }) : CHISPA(38)}</span>
      <span class="dg-centro-txt" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.centro" data-qa-caja="1">${esc(props.centro)}</span></div>
    ${chips.length ? `<div class="dg-chips" data-qa="contenido" data-qa-ruta="${lt.ruta}.chips" data-qa-caja="1">${chips.map((_, i) =>
      `<span class="dg-chip" data-qa="texto" data-qa-grupo="contenido" data-qa-min-fs="18" data-qa-ruta="${lt.ruta}.chips[${i}]"><span class="dg-chip-txt"></span></span>`).join('')}</div>` : ''}
    <div class="dg-chat ui-tarjeta">
      <div class="dg-cuerpo">
        <div class="dg-pos dg-pos-burbuja"><div class="dg-burbuja" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.pregunta"></div></div>
        <div class="dg-pos dg-pos-asist"><div class="dg-asist">${chispas}<span class="dg-asist-txt">${esc(asistente)}</span></div></div>
        <div class="dg-pos dg-pos-pensando"><div class="dg-pensando">${props.pensando ? `<span class="dg-pensando-txt" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.pensando">${esc(props.pensando)}</span>` : ''}<span class="dg-puntos ui-puntos"><i></i><i></i><i></i></span></div></div>
        <div class="dg-respuesta" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.respuesta"></div>
      </div>
    </div>`);

  const q = (s) => raiz.querySelector(s);
  const qa = (s) => [...raiz.querySelectorAll(s)];
  const nodos = qa('.dg-nodo');
  const punteados = qa('.dg-punteado');
  const mascaras = qa('.dg-mascara');
  const centro = q('.dg-centro');
  const aura = q('.dg-aura');
  const union = q('.dg-union');
  const chipsEl = qa('.dg-chip');
  const chipsCaja = q('.dg-chips');
  chipsEl.forEach((el, i) => {
    const pals = construirPalabras(el.firstElementChild, parsearEnfasis(chips[i]));
    // Aire entre la etiqueta gris y el valor, como en la referencia.
    const k = pals.findIndex((s, j) => j > 0 && s.classList.contains('enf') && !pals[j - 1].classList.contains('enf'));
    if (k > 0) pals[k].classList.add('dg-valor');
  });
  const burbuja = q('.dg-burbuja');
  const spansB = construirPalabras(burbuja, parsearEnfasis(props.pregunta));
  const resp = q('.dg-respuesta');
  const spansR = construirPalabras(resp, parsearEnfasis(props.respuesta));
  const posB = q('.dg-pos-burbuja');
  const posA = q('.dg-pos-asist');
  const asist = q('.dg-asist');
  const pensando = q('.dg-pensando');
  const puntos = q('.dg-puntos');
  const chat = q('.dg-chat');
  const alto = { R: 120, P: 30, A: 30 };
  const p = lt.pasos;

  return {
    medir() {
      for (const el of qa('.dg-nodo-txt')) encoger(el, 22, 20);
      encoger(q('.dg-centro-txt'), 28, 24);
      // Chips: la fila completa debe caber; se baja la letra de todos por igual (21 → 18 px).
      if (chipsCaja) {
        for (let fs = 21; fs >= 18; fs -= 0.5) {
          chipsCaja.style.fontSize = fs + 'px';
          if (chipsCaja.scrollWidth <= chipsCaja.clientWidth + 1) break;
        }
      }
      ajustar(burbuja, spansB, { max: 27, min: 25, lineas: 2 });
      ajustar(resp, spansR, { max: 27, min: 24, lineas: 4 });
      alto.R = resp.offsetHeight;
      alto.P = pensando.offsetHeight;
      alto.A = asist.offsetHeight;
    },
    actualizar(t) {
      // Tarjeta de chat y nodos.
      aparecer(chat, P(t, p.tarjeta.ini, 0.45, E.outCubic), { dy: 22, blur: 8 });
      nodos.forEach((el, i) => aparecer(el, P(t, p.nodos.ini + i * 0.1, 0.42, E.outCubic), { dy: 16, blur: 8, escala: 0.96 }));

      // Líneas: se trazan (máscara) de cada nodo a la pastilla; el punteado fluye hacia el centro.
      const flujo = -((t * 30) % PERIODO);
      punteados.forEach((el) => estilo(el, { strokeDashoffset: flujo.toFixed(2) }));
      mascaras.forEach((el, i) => trazar(el, P(t, p.conexion.ini + i * 0.07, 0.55, E.inOutCubic), Math.ceil(largos[i] + 2)));

      // Pastilla central: pop con resorte, borde que se enciende y aura que respira.
      const tc = t - p.centro.ini;
      const kr = resorte(tc, { zeta: 0.55, omega: 15 });
      const ko = P(tc, 0, 0.2, E.outQuad);
      const kb = P(tc, 0, 0.32, E.outCubic);
      estilo(centro, {
        opacity: String(+ko.toFixed(4)),
        visibility: ko <= 0.001 ? 'hidden' : 'visible',
        transform: tc > 0 ? `scale(${(0.84 + 0.16 * kr).toFixed(4)})` : 'scale(0.84)',
        filter: kb < 0.998 ? `blur(${(8 * (1 - kb)).toFixed(2)}px)` : 'none',
      });
      const kA = P(tc, 0.05, 0.7, E.outCubic);
      const vivo = 0.82 + 0.18 * pulso(t, 2.4);
      opacidad(aura, kA * vivo);
      estilo(centro, { boxShadow: sombraCentro(kA, vivo) });
      const kU = P(t, p.conexion.ini + 0.45, 0.3, E.outCubic) * (1 - 0.5 * P(tc, 0.2, 0.5));
      opacidad(union, kU);

      // Chips de contexto, uno por uno.
      chipsEl.forEach((el, i) => {
        const tt = t - (p.chips.ini + i * 0.14);
        const k = P(tt, 0, 0.3, E.outCubic);
        const s = tt > 0 ? 0.92 + 0.08 * resorte(tt, { zeta: 0.6, omega: 17 }) : 0.92;
        estilo(el, {
          opacity: String(+k.toFixed(4)),
          visibility: k <= 0.001 ? 'hidden' : 'visible',
          transform: `translate3d(0,${(8 * (1 - k)).toFixed(2)}px,0) scale(${s.toFixed(4)})`,
          filter: k < 0.998 ? `blur(${(5 * (1 - k)).toFixed(2)}px)` : 'none',
        });
      });

      // Chat: la burbuja entra abajo; al "pensar" sube para dejar sitio y vuelve a subir con la respuesta.
      aparecer(burbuja, P(t, p.pregunta.ini, 0.36, E.outCubic), { dy: 14, blur: 6, escala: 0.97 });
      const k1 = E.inOutCubic(P(t, p.pensando.ini, 0.42));
      const kR = E.inOutCubic(P(t, p.respuesta.ini, 0.42));
      const H = alto.P + (alto.R - alto.P) * kR;
      estilo(posB, { transform: `translate3d(0,${(-k1 * (H + G_TEXTO + alto.A + G_BURBUJA)).toFixed(2)}px,0)` });
      estilo(posA, { transform: `translate3d(0,${(-(H + G_TEXTO)).toFixed(2)}px,0)` });
      aparecer(asist, P(t, p.pensando.ini + 0.08, 0.36, E.outCubic), { dy: 10, blur: 5 });
      const kP = P(t, p.pensando.ini + 0.12, 0.34, E.outCubic) * (1 - P(t, p.respuesta.ini, 0.18, E.inQuad));
      aparecer(pensando, kP, { dy: 8, blur: 4 });
      animarPuntos(puntos, t);
      spansR.forEach((s, i) => aparecer(s, P(t, p.respuesta.ini + 0.1 + i * 0.022, 0.3, E.outCubic), { dy: 8, blur: 5 }));
    },
  };
}

function sombraCentro(k, vivo) {
  const a = (0.32 * k * vivo).toFixed(3);
  return `0 0 0 1px rgba(75,103,214,${(0.22 * k).toFixed(3)}), 0 0 ${(42 * k).toFixed(1)}px rgba(75,103,214,${a}), 0 18px 44px rgba(0,0,0,0.4)`;
}

// Tamaño de letra más grande (de max a min) con el que el texto cabe en una línea de su caja.
function encoger(el, max, min) {
  for (let fs = max; fs >= min; fs -= 1) {
    el.style.fontSize = fs + 'px';
    if (el.scrollWidth <= el.clientWidth + 1) return;
  }
}

