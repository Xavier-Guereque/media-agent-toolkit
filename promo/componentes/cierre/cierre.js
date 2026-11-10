// cierre — logo + lema + CTA + contacto + aviso legal, como el final del video de referencia.
// Columna flexible calibrada a la referencia (1080×1920): con lema de 1 línea queda marca y≈745,
// lema y≈872, CTA y≈1075 y contacto y≈1216; con lema de 2 líneas todo se recorre sin encimarse.
// El aviso ("Interfaz y datos ilustrativos.") sale del tema y va fijo en y≈1482.

import { P, E, resorte, mezclar, rgbCss } from '../../runtime/tiempo.js';
import { aparecer, estilo, opacidad } from '../../runtime/movimiento.js';
import { construirPalabras, ajustar } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';
import { crearMarca, ajustarMarca } from '../../runtime/marca.js';

const STAGGER = 0.06;
const FADE = 0.38;

export function planear(props, tema) {
  const n = parsearEnfasis(props.lema).length;
  const revLema = Math.max(0, n - 1) * STAGGER + FADE;
  const pasos = [
    { id: 'marca', min: 0.55, pref: 0.7, cue: 'revelar' },
    { id: 'lema', min: revLema, pref: revLema + 0.15 },
    { id: 'cta', min: 0.45, pref: 0.6, cue: 'pop' },
  ];
  if (props.contacto) pasos.push({ id: 'contacto', min: 0.25, pref: 0.35 });
  if (props.aviso !== false) pasos.push({ id: 'aviso', min: 0.2, pref: 0.3 });
  return { pasos, reposo: { min: 2.0, pref: 3.0 } }; // el CTA se sostiene en pantalla
}

export function montar(raiz, props, lt, ctx) {
  const icono = props.cta.icono === 'whatsapp'
    ? `<span class="ci-ico">${ctx.marcas.whatsapp || ''}</span>`
    : props.cta.icono && props.cta.icono !== 'ninguno'
      ? ctx.icono({ telefono: 'phone', web: 'globe', descarga: 'download', correo: 'mail' }[props.cta.icono] || 'arrow-right', { tam: 42, trazo: 2.2 })
      : '';
  raiz.insertAdjacentHTML('beforeend', `
    <div class="ci-rejilla"></div>
    <div class="ci-pila">
      <div class="ci-marca"></div>
      <div class="ci-lema" data-qa="texto" data-qa-grupo="lema" data-qa-ruta="${lt.ruta}.lema"></div>
      <div class="ci-cta" data-qa="cta" data-qa-grupo="cta" data-qa-ruta="${lt.ruta}.cta.texto">${icono}<span class="ci-cta-txt"></span></div>
      ${props.contacto ? `<div class="ci-contacto" data-qa="texto" data-qa-grupo="contacto" data-qa-ruta="${lt.ruta}.contacto"></div>` : ''}
    </div>
    ${props.aviso !== false ? `<div class="ci-pos ci-pos-aviso"><div class="ci-aviso" data-qa="aviso" data-qa-min-fs="18" data-qa-grupo="aviso" data-qa-ruta="tema.avisos.ilustrativo"></div></div>` : ''}
  `);
  const q = (s) => raiz.querySelector(s);
  const marca = crearMarca(ctx, { alto: 60 });
  q('.ci-marca').appendChild(marca.el);
  const lema = q('.ci-lema');
  const spans = construirPalabras(lema, parsearEnfasis(props.lema));
  const enf = spans.filter((s) => s.classList.contains('enf'));
  q('.ci-cta-txt').textContent = props.cta.texto;
  if (props.contacto) q('.ci-contacto').textContent = props.contacto;
  if (props.aviso !== false) q('.ci-aviso').textContent = ctx.tema.avisos.ilustrativo;
  const rejilla = q('.ci-rejilla');
  const cta = q('.ci-cta');
  const contacto = q('.ci-contacto');
  const aviso = q('.ci-aviso');
  const p = lt.pasos;
  const cAten = ctx.tema.colores.atenuado;

  return {
    medir() {
      ajustarMarca(marca, 900);
      ajustar(lema, spans, { max: 86, min: 60, lineas: 2 });
    },
    actualizar(t) {
      opacidad(rejilla, 0.9 * P(t, 0, 1.2, E.outCubic));

      // Marca: entra enfocándose; "AI" se desliza; la pastilla de versión rebota.
      const tm = t - p.marca.ini;
      aparecer(marca.logo, P(tm, 0, 0.6, E.outCubic), { blur: 14, escala: 0.94, dy: 0 });
      if (marca.prod) aparecer(marca.prod, P(tm, 0.12, 0.5, E.outCubic), { dx: -18, dy: 0, blur: 8 });
      if (marca.ver) {
        const k = resorte(tm - 0.32, { zeta: 0.55, omega: 18 });
        estilo(marca.ver, { opacity: String(Math.min(1, Math.max(0, (tm - 0.32) * 5)).toFixed(3)), transform: `scale(${(0.6 + 0.4 * k).toFixed(4)})` });
      }

      // Lema: palabras escalonadas; el énfasis pasa de atenuado a blanco con brillo.
      spans.forEach((s, i) => aparecer(s, P(t, p.lema.ini + i * STAGGER, FADE, E.outCubic), { dy: 16, blur: 8 }));
      const kE = P(t, p.lema.ini + p.lema.dur * 0.8, 0.55, E.outCubic);
      for (const s of enf) {
        estilo(s, {
          color: rgbCss(mezclar(cAten, '#ffffff', kE)),
          textShadow: `0 0 ${(kE * 26).toFixed(1)}px rgba(255,255,255,${(kE * 0.32).toFixed(3)})`,
        });
      }

      // CTA: pop con resorte y un pulso de brillo lento mientras se queda en pantalla.
      const tc = t - p.cta.ini;
      const kc = resorte(tc, { zeta: 0.6, omega: 15 });
      const pulso = tc > 0.6 ? 0.5 + 0.5 * Math.sin((tc - 0.6) * 2.4) : 0;
      estilo(cta, {
        opacity: String(Math.min(1, Math.max(0, tc * 4)).toFixed(3)),
        transform: `scale(${(0.86 + 0.14 * kc).toFixed(4)})`,
        boxShadow: `0 0 0 1px rgba(255,255,255,0.08) inset, 0 12px ${(38 + 16 * pulso).toFixed(1)}px rgba(39,196,110,${(0.26 + 0.14 * pulso).toFixed(3)})`,
      });

      if (p.contacto) aparecer(contacto, P(t, p.contacto.ini, 0.45, E.outCubic), { dy: 10, blur: 4 });
      if (p.aviso) aparecer(aviso, P(t, p.aviso.ini, 0.45, E.outCubic), { dy: 6, blur: 3 });
    },
  };
}
