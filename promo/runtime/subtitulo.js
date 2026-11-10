// subtitulo.js — pastilla inferior tipo subtítulo con karaoke ("con existencias y cotización…"):
// la palabra ya dicha va en blanco y la que falta en gris. Sin voz, el avance sigue el ritmo de
// lectura; con voz (incremento de VO) cada palabra trae su tiempo real `a`.

import { P, E, mezclar, rgbCss } from './tiempo.js';
import { aparecer, desaparecer, estilo } from './movimiento.js';
import { construirPalabras, ajustar } from './texto.js';

const PPS_KARAOKE = 2.6; // palabras/s cuando no hay voz

// Puro (Node): tiempo que la frase necesita en pantalla.
export function planear(palabras) {
  const n = palabras.length;
  return { pref: Math.max(1.1, n / PPS_KARAOKE + 0.6), min: Math.max(0.7, n / 3.8 + 0.2) };
}

// Puro (Node): asigna a cada palabra el instante en que "se dice" (relativo a la escena).
export function tiemposKaraoke(palabras, ini, fin) {
  const n = palabras.length;
  const tramo = Math.min((fin - ini) * 0.75, n / PPS_KARAOKE);
  return palabras.map((p, i) => ({ ...p, a: +(ini + 0.12 + (tramo * i) / Math.max(1, n)).toFixed(3) }));
}

const GRIS = '#6f747d';
const BLANCO = '#ffffff';

export function montar(raiz, esc, ctx) {
  const frases = esc.subtitulo.map((f, j) => {
    const pos = document.createElement('div');
    pos.className = 'subt-pos';
    const el = document.createElement('div');
    el.className = 'subt';
    el.dataset.qa = 'texto';
    el.dataset.qaGrupo = 'subtitulo';
    el.dataset.qaRuta = esc.subtitulo.length > 1 ? `${esc.ruta}.subtitulo[${j}]` : `${esc.ruta}.subtitulo`;
    pos.appendChild(el);
    raiz.appendChild(pos);
    const spans = construirPalabras(el, f.palabras);
    return { f, pos, el, spans };
  });
  return {
    medir() {
      for (const x of frases) ajustar(x.el, x.spans, { max: 40, min: 32, lineas: 2 });
    },
    actualizar(t) {
      for (const { f, pos, el, spans } of frases) {
        const vivo = t >= f.ini - 1e-6 && t < f.fin;
        pos.style.display = vivo ? 'flex' : 'none';
        if (!vivo) continue;
        const kSal = f.fin < esc.dur - 1e-3 ? P(t, f.fin - 0.18, 0.18, E.inCubic) : 0;
        if (kSal > 0) desaparecer(el, kSal, { dy: -6, blur: 4 });
        else aparecer(el, P(t, f.ini, 0.24, E.outCubic), { dy: 10, blur: 4, escala: 0.97 });
        spans.forEach((s, i) => {
          const k = P(t, f.palabras[i].a, 0.12, E.outQuad);
          estilo(s, { color: rgbCss(mezclar(GRIS, BLANCO, k)) });
        });
      }
    },
  };
}
