// movimiento.js — primitivas de animación. SOLO escriben estilos (nunca leen layout),
// así cada cuadro depende únicamente de `t` y no de cuadros anteriores.
//
// El caché evita escrituras redundantes al DOM; como siempre se calcula el estado completo,
// el resultado es idéntico con o sin caché (determinismo intacto).

import { clamp, lerp } from './tiempo.js';

const cache = new WeakMap();

// Escribe propiedades CSS (camelCase o --variables) solo si cambiaron.
export function estilo(el, props) {
  if (!el) return;
  let prev = cache.get(el);
  if (!prev) {
    prev = {};
    cache.set(el, prev);
  }
  for (const k in props) {
    const v = props[k];
    if (prev[k] === v) continue;
    prev[k] = v;
    if (k.startsWith('--')) el.style.setProperty(k, v);
    else el.style[k] = v;
  }
}

const num = (x, d = 3) => +x.toFixed(d);

// Estado de aparición estándar del motor: opacidad + desplazamiento + desenfoque + escala.
// k: 0 (oculto) → 1 (en reposo). Sin wipes ni slides de "presentación".
export function aparecer(el, k, { dy = 24, dx = 0, blur = 8, escala = 1, rot = 0 } = {}) {
  k = clamp(k);
  const inv = 1 - k;
  const s = lerp(escala, 1, k);
  const tr = [];
  if (dx || dy) tr.push(`translate3d(${num(dx * inv, 2)}px,${num(dy * inv, 2)}px,0)`);
  if (s !== 1) tr.push(`scale(${num(s, 4)})`);
  if (rot) tr.push(`rotate(${num(rot * inv, 3)}deg)`);
  estilo(el, {
    opacity: String(num(k, 4)),
    transform: tr.length ? tr.join(' ') : 'none',
    filter: blur && inv > 0.002 ? `blur(${num(blur * inv, 2)}px)` : 'none',
    visibility: k <= 0.001 ? 'hidden' : 'visible',
  });
}

// Salida estándar (inversa suave): sube un poco y se desenfoca.
export function desaparecer(el, k, { dy = -16, blur = 8 } = {}) {
  k = clamp(k);
  estilo(el, {
    opacity: String(num(1 - k, 4)),
    transform: k > 0 ? `translate3d(0,${num(dy * k, 2)}px,0)` : 'none',
    filter: blur && k > 0.002 ? `blur(${num(blur * k, 2)}px)` : 'none',
    visibility: k >= 0.999 ? 'hidden' : 'visible',
  });
}

export function opacidad(el, k) {
  k = clamp(k);
  estilo(el, { opacity: String(num(k, 4)), visibility: k <= 0.001 ? 'hidden' : 'visible' });
}

export function transformar(el, { x = 0, y = 0, s = 1, r = 0 } = {}) {
  const tr = [];
  if (x || y) tr.push(`translate3d(${num(x, 2)}px,${num(y, 2)}px,0)`);
  if (s !== 1) tr.push(`scale(${num(s, 4)})`);
  if (r) tr.push(`rotate(${num(r, 3)}deg)`);
  estilo(el, { transform: tr.length ? tr.join(' ') : 'none' });
}

// Trazo de una línea SVG (stroke-dasharray/offset): k 0 → nada, 1 → completo.
export function trazar(el, k, largo) {
  estilo(el, { strokeDasharray: `${largo}`, strokeDashoffset: `${num(largo * (1 - clamp(k)), 2)}` });
}

// Recorte horizontal (revela de izquierda a derecha sin mover el contenido).
export function revelarX(el, k) {
  const r = num((1 - clamp(k)) * 100, 3);
  estilo(el, { clipPath: r <= 0 ? 'none' : `inset(0 ${r}% 0 0)` });
}

export function variable(el, nombre, valor) {
  estilo(el, { [nombre]: String(valor) });
}
