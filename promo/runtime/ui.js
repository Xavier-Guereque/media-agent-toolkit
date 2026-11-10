// ui.js — piezas animadas compartidas por los componentes de UI (pasos, puntos de "pensando",
// giro de carga). Igual que el resto del motor: solo escriben estilos en función de t.

import { P, E, mezclar, rgbCss, clamp } from './tiempo.js';
import { aparecer, estilo } from './movimiento.js';

const ACTIVO = { fondo: '#1f2a52', borde: '#4a5fa8', texto: '#b9c7f5' };
const HECHO = { fondo: '#16301f', borde: '#2c6a44', texto: '#5bd98f' };

const CHECK_LLENO = `<svg width="28" height="28" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="currentColor"/>` +
  `<path d="m7.5 12.3 3 3 6-6.3" fill="none" stroke="#0f1a13" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// Pastilla de paso ("Buscando: bala IP 4 MP…"): entra activa (azul, puntos) y se vuelve hecha (verde, check).
export function crearPaso(texto, { ruta } = {}) {
  const el = document.createElement('div');
  el.className = 'ui-paso';
  if (ruta) {
    el.dataset.qa = 'texto';
    el.dataset.qaRuta = ruta;
    el.dataset.qaMinFs = '20';
  }
  el.innerHTML = `<span class="ui-paso-ico"><span class="ui-puntos"><i></i><i></i><i></i></span><span class="ui-check">${CHECK_LLENO}</span></span><span class="ui-paso-txt"></span>`;
  el.querySelector('.ui-paso-txt').textContent = texto;
  return el;
}

// kIn: aparición (0→1). tHecho: segundos desde que se completó (<0 = aún activo).
export function actualizarPaso(el, t, { ini, hecho }) {
  aparecer(el, P(t, ini, 0.32, E.outCubic), { dy: 12, blur: 4, escala: 0.98 });
  const k = P(t, hecho, 0.28, E.outCubic);
  const col = (a, b) => rgbCss(mezclar(a, b, k));
  estilo(el, { background: col(ACTIVO.fondo, HECHO.fondo), borderColor: col(ACTIVO.borde, HECHO.borde), color: col(ACTIVO.texto, HECHO.texto) });
  const puntos = el.querySelector('.ui-puntos');
  const check = el.querySelector('.ui-check');
  estilo(puntos, { opacity: String((1 - k).toFixed(3)) });
  estilo(check, { opacity: String(k.toFixed(3)), transform: `scale(${(0.6 + 0.4 * E.outBack(k)).toFixed(4)})` });
  animarPuntos(puntos, t);
}

// Tres puntos que "respiran" en secuencia (pensando / escribiendo).
export function animarPuntos(cont, t) {
  const dots = cont.children;
  for (let i = 0; i < dots.length; i++) {
    const f = 0.5 + 0.5 * Math.sin((t * 2.2 - i * 0.22) * Math.PI * 2);
    estilo(dots[i], { opacity: (0.3 + 0.7 * f).toFixed(3), transform: `translateY(${(-3 * f).toFixed(2)}px)` });
  }
}

// Giro de un ícono de carga (loader-circle) a velocidad constante.
export function girar(el, t, vueltasPorSeg = 1.1) {
  estilo(el, { transform: `rotate(${((t * vueltasPorSeg * 360) % 360).toFixed(2)}deg)` });
}

// Pulso suave 0..1 (brillos "en vivo").
export const pulso = (t, periodo = 1.6) => 0.5 + 0.5 * Math.sin((t / periodo) * Math.PI * 2);

export { clamp };
