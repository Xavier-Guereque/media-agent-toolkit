// texto — escena de enunciado: una frase grande al centro (gancho o puente) y una línea de apoyo.
// Las palabras entran escalonadas con desenfoque; las de *énfasis* se encienden en azul de marca.

import { P, E, clamp } from '../../runtime/tiempo.js';
import { aparecer, estilo, transformar } from '../../runtime/movimiento.js';
import { construirPalabras, ajustar } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';

const STAGGER = 0.07;
const FADE = 0.42;

export function planear(props, tema) {
  const n = parsearEnfasis(props.texto).length;
  const na = props.apoyo ? parsearEnfasis(props.apoyo).length : 0;
  const { pps, extra } = tema.movimiento.lectura;
  const revelado = Math.max(0, n - 1) * STAGGER + FADE;
  const pasos = [{ id: 'texto', min: revelado, pref: revelado + 0.15 }];
  if (na) pasos.push({ id: 'apoyo', min: 0.35, pref: 0.5 });
  // La lectura empieza con la primera palabra (no al terminar de aparecer): el reposo solo
  // completa lo que falte para leerlo todo, con un mínimo para que la frase "asiente".
  const lectura = (n + na) / pps + extra;
  const aparicion = revelado + (na ? 0.5 : 0);
  return { pasos, reposo: { min: Math.max(0.6, 0.75 * lectura - aparicion), pref: Math.max(1.0, lectura - aparicion) } };
}

export function montar(raiz, props, lt, ctx) {
  raiz.insertAdjacentHTML('beforeend', `
    <div class="tx"><div class="tx-mov">
      <div class="tx-texto" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.texto"></div>
      ${props.apoyo ? `<div class="tx-apoyo" data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${lt.ruta}.apoyo"></div>` : ''}
    </div></div>`);
  const mov = raiz.querySelector('.tx-mov');
  const elT = raiz.querySelector('.tx-texto');
  const elA = raiz.querySelector('.tx-apoyo');
  const spans = construirPalabras(elT, parsearEnfasis(props.texto));
  const spansA = elA ? construirPalabras(elA, parsearEnfasis(props.apoyo)) : [];
  const enf = spans.filter((s) => s.classList.contains('enf'));
  const pT = lt.pasos.texto;
  const pA = lt.pasos.apoyo;

  return {
    medir() {
      ajustar(elT, spans, { max: 104, min: 64, lineas: 3 });
      if (elA) ajustar(elA, spansA, { max: 42, min: 32, lineas: 2 });
    },
    actualizar(t) {
      // Empuje de cámara muy leve durante toda la escena: la frase "respira".
      transformar(mov, { s: 1 + 0.025 * clamp(t / lt.dur) });
      spans.forEach((s, i) => aparecer(s, P(t, pT.ini + i * STAGGER, FADE, E.outCubic), { dy: 22, blur: 12, escala: 0.97 }));
      const kE = P(t, pT.ini + pT.dur * 0.7, 0.5, E.outCubic);
      for (const s of enf) estilo(s, { textShadow: `0 0 ${(kE * 34).toFixed(1)}px rgba(152,182,245,${(kE * 0.55).toFixed(3)})` });
      if (elA) aparecer(elA, P(t, pA.ini, 0.5, E.outCubic), { dy: 14, blur: 6 });
    },
  };
}
