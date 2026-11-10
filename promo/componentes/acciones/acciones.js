// acciones — "soporte en obra": pila de tarjetas de acción que aparecen una a una, como el bloque
// 15.5–19.5 s de la promo de referencia. Medidas de la referencia (1080×1920): tarjetas de 880×219 en
// x 100–980 desde y 604, separadas 23 px; recuadro de ícono 78 px; fila de estado de 57 px.
//
// Cada tarjeta es un grupo de beats: espera → aparece (pop) → proceso → listo (éxito) → lectura.
// Con un titular de N frases y N tarjetas, cada frase se ancla al inicio del grupo de su tarjeta
// (el planificador ancla cada frase al beat e{k}): la pregunta se escribe y ~0.4 s después aparece su respuesta.

import { P, E, clamp, resorte, mezclar, rgbCss } from '../../runtime/tiempo.js';
import { aparecer, estilo } from '../../runtime/movimiento.js';
import { construirPalabras } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';
import { girar } from '../../runtime/ui.js';
import * as titular from '../../runtime/titular.js';

const ICONOS = {
  llave: 'key-round', camion: 'truck', escudo: 'shield-check', archivo: 'file-text', descarga: 'download',
  paquete: 'package', herramienta: 'wrench', recibo: 'receipt', carrito: 'shopping-cart', calendario: 'calendar',
  ubicacion: 'map-pin', reloj: 'clock', soporte: 'headphones', camara: 'cctv', disco: 'hard-drive', verificado: 'badge-check',
};

// Glifos "llenos" como los de la referencia (llave, camión y escudo sólidos con detalles oscuros).
// Clase por hijo del SVG de Lucide: s = relleno sólido, h = detalle oscuro, a = aro (rueda), - = sin cambio.
// Los que no están aquí se dibujan en duotono (trazo + relleno tenue).
const SOLIDOS = {
  'key-round': 'sh', truck: 'sssaa', 'shield-check': 'sh', 'file-text': 'shhhh', package: 'shhh', wrench: 's',
  receipt: 'hhs', 'shopping-cart': '-saa', calendar: '--sh', 'map-pin': 'sa', clock: 'sh', 'hard-drive': 'hshh', 'badge-check': 'sh',
};

function solidificar(svg, spec) {
  if (!svg || !spec) return;
  const hijos = [...svg.children];
  hijos.forEach((h, i) => {
    if (spec[i] && spec[i] !== '-') h.classList.add(`ic-${spec[i]}`);
  });
  // Los rellenos van primero para que los detalles oscuros queden encima.
  svg.prepend(...hijos.filter((_, i) => spec[i] === 's'));
  svg.classList.add('ic-solido');
}

const ALTO = 219; // alto de tarjeta (px)
const SEP = 23; // separación vertical entre tarjetas
const VERDE = '#3ecf7a';

const suma = (xs) => xs.reduce((a, b) => a + b, 0);

// Necesidad de lectura de cada frase del titular (misma regla que el planificador).
function necesidadFrases(frases, tema) {
  return frases.map((f) => {
    const x = titular.planear(parsearEnfasis(f), tema);
    return { pref: Math.max(x.revelado + 0.8, x.lectura), min: Math.max(x.revelado + 0.5, 0.8 * x.lectura) };
  });
}

// Puro (Node). Un grupo de beats por tarjeta; si el titular trae una frase por tarjeta, cada grupo
// dura al menos lo que su frase necesita para leerse (los grupos son iguales, como el reparto del titular).
export function planear(props, tema) {
  const items = props.acciones || [];
  const n = items.length;
  const frases = Array.isArray(props.titular) ? props.titular : props.titular ? [props.titular] : [];
  let gPref = 0;
  let gMin = 0;
  if (n > 1 && frases.length === n) {
    const nec = necesidadFrases(frases, tema);
    gPref = suma(nec.map((x) => x.pref)) / n;
    gMin = suma(nec.map((x) => x.min)) / n;
  }
  const pasos = [];
  items.forEach((it, k) => {
    const base = [
      // La pregunta se empieza a leer; con frase propia, la tarjeta espera a que casi termine de escribirse.
      { id: `e${k}`, min: gPref ? 0.3 : 0.15, pref: gPref ? 0.45 : 0.3 },
      { id: `c${k}`, min: 0.25, pref: 0.35, cue: 'pop', g: 0.9 }, // aparece la tarjeta
      { id: `p${k}`, min: 0.45, pref: 0.7 }, // en proceso (giro) o avance de la pista
      { id: `l${k}`, min: 0.2, pref: 0.3, cue: it.tipo === 'rastreo' ? 'tick' : 'exito', g: 0.8 }, // listo
    ];
    const bPref = suma(base.map((p) => p.pref));
    const bMin = suma(base.map((p) => p.min));
    pasos.push(...base, { id: `h${k}`, min: Math.max(0.2, gMin - bMin), pref: Math.max(0.4, gPref - bPref) });
  });
  // Con una frase de titular por tarjeta, el planificador ancla la frase k al beat `e{k}`.
  const anclas = n > 1 && frases.length === n ? items.map((_, k) => `e${k}`) : undefined;
  return { pasos, reposo: { min: 0.3, pref: 0.5 }, frases: anclas };
}

// Solución local (propuesta para el planificador en el reporte): con N frases y N tarjetas, la frase j
// empieza donde empieza el grupo de la tarjeta j y termina donde empieza el siguiente. Se ajustan los
// mismos objetos que lee titular.js en cada cuadro, así que no depende del orden de montaje.

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

const GIRO = `<svg class="ac-giro" width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="10.5" fill="none" stroke="rgba(255,255,255,0.16)" stroke-width="3"/>` +
  `<path d="M14 3.5a10.5 10.5 0 0 1 10.5 10.5" fill="none" stroke="#e4e7ec" stroke-width="3" stroke-linecap="round"/></svg>`;
const CHECK = `<svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="13" fill="${VERDE}"/>` +
  `<path d="m8.6 14.4 3.6 3.5 7.2-7.6" fill="none" stroke="#0e1a13" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// Fija el tamaño de letra más grande (de max a min) con el que el texto cabe en su caja de una línea.
function encoger(el, max, min) {
  for (let fs = max; fs >= min; fs -= 1) {
    el.style.fontSize = fs + 'px';
    if (el.scrollWidth <= el.clientWidth + 1) return;
  }
}

export function montar(raiz, props, lt, ctx) {
  const items = props.acciones;
  const pila = document.createElement('div');
  pila.className = 'ac-pila';
  raiz.appendChild(pila);

  const tarjetas = items.map((it, k) => {
    const ruta = `${lt.ruta}.acciones[${k}]`;
    const qa = (prop, extra = '') => `data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${ruta}.${prop}" data-qa-caja="1"${extra}`;
    const el = document.createElement('div');
    el.className = `ac-tarjeta ui-tarjeta ac-${it.tipo}${it.detalle ? '' : ' ac-sin-detalle'}`;
    el.style.top = `${k * (ALTO + SEP)}px`;
    let fila;
    if (it.tipo === 'rastreo') {
      fila = `<div class="ac-fila ac-fila-rastreo">
          <span class="ac-ini" ${qa('inicio')}>${esc(it.inicio)}</span>
          <span class="ac-pista"><i class="ac-base"></i><i class="ac-relleno"></i><b class="ac-hito"></b><b class="ac-hito"></b><b class="ac-hito"></b><b class="ac-cabeza"></b></span>
          <span class="ac-fin" ${qa('fin')}>${esc(it.fin)}</span>
        </div>`;
    } else {
      fila = `<div class="ac-fila">
          <span class="ac-estado">${GIRO}<span class="ac-halo"></span><span class="ac-check">${CHECK}</span></span>
          <span class="ac-textos">
            <span class="ac-proceso" ${qa('proceso')}>${esc(it.proceso)}</span>
            <span class="ac-listo" ${qa('listo')}></span>
          </span>
          ${it.boton ? `<span class="ac-boton" ${qa('boton', ' data-qa-min-fs="20"')}>${esc(it.boton)}</span>` : ''}
        </div>`;
    }
    el.innerHTML = `
      <div class="ac-ico">${ctx.icono(ICONOS[it.icono] || 'badge-check', { tam: 42, trazo: 2 })}</div>
      <div class="ac-titulo" ${qa('titulo')}>${esc(it.titulo)}</div>
      ${it.detalle ? `<div class="ac-detalle" ${qa('detalle')}>${esc(it.detalle)}</div>` : ''}
      ${fila}`;
    pila.appendChild(el);
    const q = (s) => el.querySelector(s);
    solidificar(q('.ac-ico svg'), SOLIDOS[ICONOS[it.icono]]);
    const x = { it, k, el, titulo: q('.ac-titulo'), detalle: q('.ac-detalle') };
    if (it.tipo === 'rastreo') {
      const avance = clamp(it.avance ?? 0.75);
      Object.assign(x, { pista: q('.ac-pista'), relleno: q('.ac-relleno'), hitos: [...el.querySelectorAll('.ac-hito')], cabeza: q('.ac-cabeza'), fin: q('.ac-fin'), ancho: 300, avance, mitad: mitad(avance) });
    } else {
      const listo = q('.ac-listo');
      // El folio (*énfasis*) va en JetBrains Mono, como "0S-48213" en la referencia.
      construirPalabras(listo, parsearEnfasis(it.listo), { claseEnfasis: 'ac-folio' });
      Object.assign(x, { giro: q('.ac-giro'), check: q('.ac-check'), halo: q('.ac-halo'), proceso: q('.ac-proceso'), listo, boton: q('.ac-boton') });
    }
    return x;
  });

  const p = lt.pasos;

  return {
    medir() {
      for (const x of tarjetas) {
        encoger(x.titulo, 30, 26);
        if (x.detalle) encoger(x.detalle, 23, 22);
        if (x.it.tipo === 'rastreo') {
          x.ancho = x.pista.clientWidth;
        } else {
          encoger(x.proceso, 24, 22);
          encoger(x.listo, 24, 22);
        }
      }
    },
    actualizar(t) {
      for (const x of tarjetas) {
        const { k, el } = x;
        const tc = t - p[`c${k}`].ini;
        // Pop: opacidad rápida, subida corta con resorte y desenfoque que se limpia (sin slides).
        const kr = resorte(tc, { zeta: 0.78, omega: 15 });
        const ko = P(tc, 0, 0.26, E.outQuad);
        const kb = P(tc, 0, 0.34, E.outCubic);
        estilo(el, {
          opacity: String(+ko.toFixed(4)),
          visibility: ko <= 0.001 ? 'hidden' : 'visible',
          transform: ko >= 1 && kr > 0.9995 ? 'none' : `translate3d(0,${(20 * (1 - kr)).toFixed(2)}px,0) scale(${(0.97 + 0.03 * kr).toFixed(4)})`,
          filter: kb < 0.998 ? `blur(${(9 * (1 - kb)).toFixed(2)}px)` : 'none',
        });
        const tl = t - p[`l${k}`].ini;
        if (x.it.tipo === 'rastreo') actualizarRastreo(x, t, tc, tl);
        else actualizarTarea(x, t, tl);
      }
    },
  };

  function actualizarTarea(x, t, tl) {
    const kL = P(tl, 0, 0.3, E.outCubic);
    // Giro de carga → check verde con resorte y un halo que se expande una vez.
    girar(x.giro, t, 1.25);
    estilo(x.giro, { opacity: String(+(1 - P(tl, 0, 0.16, E.outQuad)).toFixed(4)) });
    const kc = resorte(tl, { zeta: 0.5, omega: 20 });
    estilo(x.check, {
      opacity: String(+P(tl, 0, 0.1, E.lin).toFixed(4)),
      transform: `scale(${(tl > 0 ? 0.4 + 0.6 * kc : 0.4).toFixed(4)})`,
    });
    const kh = P(tl, 0.02, 0.55, E.outCubic);
    estilo(x.halo, {
      opacity: String(+(tl > 0 ? 0.55 * (1 - kh) : 0).toFixed(4)),
      transform: `scale(${(1 + 1.1 * kh).toFixed(4)})`,
    });
    // Texto en proceso → texto listo (cruce corto con desenfoque, sin barrido).
    aparecer(x.proceso, 1 - P(tl, 0, 0.2, E.inQuad), { dy: -8, blur: 5 });
    aparecer(x.listo, P(tl, 0.06, 0.3, E.outCubic), { dy: 8, blur: 5 });
    if (x.boton) {
      // El botón se habilita al terminar: de tenue a pleno, con el borde encendido un instante.
      const kf = clamp(1 - P(tl, 0.15, 0.6, E.outQuad));
      estilo(x.boton, {
        opacity: String(+(0.42 + 0.58 * kL).toFixed(4)),
        borderColor: rgbCss([255, 255, 255], 0.12 + 0.2 * kL * kf),
      });
    }
  }

  function actualizarRastreo(x, t, tc, tl) {
    const av = x.avance;
    const pp = p[`p${x.k}`];
    // El relleno cruza el hito de en medio justo al empezar "listo" (ahí suena el tick y aparece el estado).
    const kAv = av * P(t - pp.ini, 0, pp.dur / x.mitad, E.inOutCubic);
    estilo(x.relleno, { transform: `scaleX(${kAv.toFixed(5)})` });
    // Hitos en 0, ½ y 1: se encienden en verde cuando el relleno los alcanza.
    x.hitos.forEach((h, i) => {
      const kh = i === 0 ? P(tc, 0.1, 0.25) : clamp((kAv - i / 2 + 0.02) / 0.04);
      estilo(h, {
        background: rgbCss(mezclar('#4a4c54', VERDE, kh)),
        boxShadow: `0 0 ${(10 * kh).toFixed(1)}px rgba(62,207,122,${(0.55 * kh).toFixed(3)})`,
      });
    });
    // Cabeza luminosa que viaja con el relleno (el envío) y se apaga al detenerse.
    const vivo = t > pp.ini ? 1 - P(t - pp.ini, pp.dur / x.mitad, 0.4, E.outQuad) : 0;
    estilo(x.cabeza, {
      transform: `translate3d(${(kAv * x.ancho).toFixed(2)}px,0,0)`,
      opacity: String(+(vivo * clamp(kAv / 0.04)).toFixed(4)),
    });
    aparecer(x.fin, P(tl, 0, 0.36, E.outCubic), { dy: 8, blur: 5 });
  }
}

// Fracción de la curva inOutCubic en la que el relleno cruza la mitad de la pista (o su final si avance < ½).
function mitad(av) {
  const meta = Math.min(0.5, av) / av;
  // Inversa de inOutCubic por bisección (pura y barata: 20 iteraciones).
  let a = 0;
  let b = 1;
  for (let i = 0; i < 20; i++) {
    const m = (a + b) / 2;
    if (E.inOutCubic(m) < meta) a = m;
    else b = m;
  }
  return (a + b) / 2;
}
