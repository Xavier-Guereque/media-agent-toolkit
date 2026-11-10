// titular.js — cita grande arriba ("“Oficina de 400 m²…”"), palabra por palabra.
// Overlay que el gestor agrega a cualquier escena que traiga `titular`.
// Puede ser una frase o varias (la escena cambia de pregunta a mitad, como en "soporte en obra").

import { P, E } from './tiempo.js';
import { aparecer, desaparecer } from './movimiento.js';
import { construirPalabras, ajustar } from './texto.js';

// Puro (Node): cuánto tarda en revelarse y cuánto hay que dejarlo para leerlo.
export function planear(palabras, tema) {
  const { stagger, fade } = tema.movimiento.tipeo;
  const { pps, extra } = tema.movimiento.lectura;
  const n = palabras.length;
  return { revelado: Math.max(0, n - 1) * stagger + fade, lectura: n / pps + extra };
}

export function montar(raiz, esc, ctx) {
  const frases = esc.titular.map((f, j) => {
    const el = document.createElement('div');
    el.className = 'titular';
    el.dataset.qa = 'texto';
    el.dataset.qaGrupo = 'titular';
    el.dataset.qaRuta = esc.titular.length > 1 ? `${esc.ruta}.titular[${j}]` : `${esc.ruta}.titular`;
    raiz.appendChild(el);
    const spans = construirPalabras(el, f.palabras);
    return { f, el, spans };
  });
  const { stagger, fade } = ctx.tema.movimiento.tipeo;
  const cfg = ctx.tema.titular;

  return {
    medir() {
      for (const x of frases) ajustar(x.el, x.spans, { max: cfg.max, min: cfg.min, lineas: cfg.lineas, preferir: { lineas: 2, min: 56 } });
    },
    actualizar(t) {
      for (const { f, el, spans } of frases) {
        const vivo = t >= f.ini - 1e-6 && t < f.fin;
        if (!vivo) {
          el.style.display = 'none';
          continue;
        }
        el.style.display = '';
        // Salida propia solo si la escena sigue después (cambio de frase); si no, sale con la escena.
        const kSal = f.fin < esc.dur - 1e-3 ? P(t, f.fin - 0.28, 0.28, E.inCubic) : 0;
        desaparecer(el, kSal, { dy: -10, blur: 6 });
        spans.forEach((s, i) => {
          aparecer(s, P(t, f.ini + i * stagger, fade, E.outCubic), { dy: 12, blur: 6 });
        });
      }
    },
  };
}
