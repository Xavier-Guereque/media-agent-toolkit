// tiempo.js — matemática pura del motor (sin DOM). Se importa igual desde Node y desde el navegador.
//
// Regla de oro del motor: todo cuadro es una función pura de `t`. Nada de Date.now(),
// Math.random(), timers ni transiciones CSS. Si hace falta azar, `mulberry32(semilla)`.

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;
export const mapear = (x, a, b, c, d) => c + (d - c) * clamp((x - a) / (b - a));

// Curvas de easing (entrada 0..1 → salida 0..1).
export const E = {
  lin: (k) => k,
  inQuad: (k) => k * k,
  outQuad: (k) => 1 - (1 - k) * (1 - k),
  inOutQuad: (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2),
  inCubic: (k) => k * k * k,
  outCubic: (k) => 1 - Math.pow(1 - k, 3),
  inOutCubic: (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  outQuart: (k) => 1 - Math.pow(1 - k, 4),
  outExpo: (k) => (k >= 1 ? 1 : 1 - Math.pow(2, -10 * k)),
  inOutSine: (k) => -(Math.cos(Math.PI * k) - 1) / 2,
  outBack: (k, s = 1.4) => 1 + (s + 1) * Math.pow(k - 1, 3) + s * Math.pow(k - 1, 2),
};

// Avance 0→1 de algo que empieza en `a` y dura `d` (la función P de la guía).
export const P = (t, a, d, e = E.outCubic) => (d <= 0 ? (t >= a ? 1 : 0) : e(clamp((t - a) / d)));

// Entra en [a, a+d] y sale en [b, b+d2]: 0 → 1 → 0. Útil para destellos y estados temporales.
export const ventana = (t, a, d, b, d2 = d, e = E.outCubic) => Math.min(P(t, a, d, e), 1 - P(t, b, d2, E.inCubic));

// Resorte subamortiguado en forma cerrada (respuesta al escalón): 0 → 1 con rebote suave.
// `tt` en segundos desde el disparo. No acumula estado → determinista.
export function resorte(tt, { zeta = 0.62, omega = 16 } = {}) {
  if (tt <= 0) return 0;
  const wd = omega * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * omega * tt) * (Math.cos(wd * tt) + ((zeta * omega) / wd) * Math.sin(wd * tt));
}

// ------------------------------------------------------------------ azar determinista
export function hashTexto(s) {
  // FNV-1a de 32 bits.
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function mulberry32(semilla) {
  let a = semilla >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ------------------------------------------------------------------ color (mezcla en OKLab)
export function hexARgb(hex) {
  const h = hex.replace('#', '');
  const n = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
}

const aLineal = (c) => {
  const x = c / 255;
  return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
};
const aSrgb = (x) => {
  const v = x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;
  return Math.round(clamp(v) * 255);
};

export function rgbAOklab([r, g, b]) {
  const [R, G, B] = [aLineal(r), aLineal(g), aLineal(b)];
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

export function oklabARgb([L, A, B]) {
  const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
  const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
  const s = Math.pow(L - 0.0894841775 * A - 1.291485548 * B, 3);
  return [
    aSrgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    aSrgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    aSrgb(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

// Mezcla perceptual de dos colores hex. k=0 → c1, k=1 → c2. Devuelve [r,g,b].
export function mezclar(c1, c2, k) {
  if (k <= 0) return hexARgb(c1);
  if (k >= 1) return hexARgb(c2);
  const a = rgbAOklab(hexARgb(c1));
  const b = rgbAOklab(hexARgb(c2));
  return oklabARgb([lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)]);
}

export const rgbCss = ([r, g, b], a = 1) => (a >= 1 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${+a.toFixed(4)})`);

// Redondea a la rejilla de cuadros (evita que un límite de escena caiga entre dos cuadros).
export const aCuadro = (t, fps) => Math.round(t * fps) / fps;
