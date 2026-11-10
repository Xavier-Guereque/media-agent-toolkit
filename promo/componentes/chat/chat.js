// chat — tarjeta de app de chat (piel asistente_web o whatsapp) que crece desde abajo como un chat real.
//
// Cómo se anima sin leer layout en seek(t):
//   1. montar() construye TODAS las entradas (burbujas, pasos, tarjetas) desde el inicio.
//   2. medir() guarda la altura de cada entrada (después de cargar fuentes e imágenes).
//   3. actualizar(t) desplaza la pila hacia abajo la suma de las alturas que aún no "entran"
//      (FLIP precalculado): cada entrada nueva empuja a las anteriores hacia arriba con suavidad.

import { P, E, clamp, resorte, mezclar, rgbCss } from '../../runtime/tiempo.js';
import { aparecer, estilo, opacidad, transformar, revelarX } from '../../runtime/movimiento.js';
import { construirPalabras } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';
import { crearPaso, actualizarPaso, animarPuntos } from '../../runtime/ui.js';

const LADO_USUARIO = new Set(['usuario', 'imagen', 'nota_voz', 'archivo']);
const GAP = 16;

// ------------------------------------------------------------------ entradas y ritmo (puro, Node + navegador)
// Cada item se vuelve una o más "entradas" de la pila; `pasos` se abre en una por pastilla.
export function entradas(props) {
  const out = [];
  const piel = props.chat.piel || 'asistente_web';
  let prevUsuario = true;
  props.chat.items.forEach((it, k) => {
    const deUsuario = LADO_USUARIO.has(it.tipo) && it.de !== 'asistente';
    if (!deUsuario && prevUsuario && piel === 'asistente_web') out.push({ id: `l${k}`, tipo: 'etiqueta', k });
    if (it.tipo === 'pasos') it.pasos.forEach((_, j) => out.push({ id: `i${k}_${j}`, tipo: 'paso', k, j }));
    else out.push({ id: `i${k}`, tipo: it.tipo, k });
    prevUsuario = deUsuario;
  });
  return out;
}

const RITMO = {
  etiqueta: { min: 0.2, pref: 0.3 },
  usuario: { min: 0.45, pref: 0.6, cue: 'pop' },
  imagen: { min: 0.5, pref: 0.6, cue: 'pop' },
  nota_voz: { min: 0.45, pref: 0.55, cue: 'pop' },
  archivo: { min: 0.45, pref: 0.55, cue: 'pop' },
  paso: { min: 0.4, pref: 0.55, cue: 'tick', g: 0.7 },
  razonamiento: { min: 0.55, pref: 0.75 },
  productos: { min: 0.9, pref: 1.2, cue: 'pop' },
  ficha: { min: 0.7, pref: 0.9, cue: 'pop' },
  cotizacion: { min: 0.55, pref: 0.75, cue: 'pop' },
  toast: { min: 0.45, pref: 0.6, cue: 'exito' },
};

export function planear(props) {
  const pasos = [];
  for (const en of entradas(props)) {
    const it = props.chat.items[en.k];
    if (en.tipo === 'asistente') {
      const n = parsearEnfasis(it.texto).length;
      const tipeo = n * 0.035 + 0.3;
      pasos.push({ id: en.id, min: Math.max(0.45, tipeo), pref: Math.max(0.6, tipeo + 0.3) });
    } else {
      pasos.push({ id: en.id, ...RITMO[en.tipo] });
    }
    // Sub-beats: escaneo de la foto, reproducción de la nota, aviso de la ficha.
    if (en.tipo === 'imagen') pasos.push({ id: `${en.id}s`, min: 0.7, pref: 1.0 });
    if (en.tipo === 'nota_voz') pasos.push({ id: `${en.id}r`, min: 0.7, pref: 1.1 });
    if (en.tipo === 'ficha' && it.toast) pasos.push({ id: `${en.id}t`, min: 0.45, pref: 0.6, cue: 'exito' });
  }
  return { pasos, reposo: { min: 0.8, pref: 1.4 }, arranque: 0.25 };
}

// ------------------------------------------------------------------ DOM
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

function marcaTexto(ctx) {
  const m = ctx.marca;
  return `${m.nombre}${m.producto ? ' ' + m.producto : ''}`;
}

function cabecera(props, ctx) {
  const titulo = esc(props.chat.titulo || marcaTexto(ctx));
  if (props.chat.piel === 'whatsapp') {
    const ini = esc((ctx.marca.nombre || 'S').slice(0, 1));
    return `<div class="ui-cabecera ch-cab-wa">${ctx.icono('chevron-left', { tam: 30, trazo: 2.2 })}
      <span class="ch-avatar">${ini}</span>
      <span class="ch-wa-nombre"><b>${titulo}</b><small>en línea</small></span></div>`;
  }
  const chip = props.chat.chip ? `<span class="ui-chip">${esc(props.chat.chip)}</span>` : '';
  return `<div class="ui-cabecera">${ctx.icono('x', { tam: 30, trazo: 2 })}<span class="ui-titulo">${titulo}</span>${chip}
    <span class="ui-acciones">${ctx.icono('history', { tam: 30 })}${ctx.icono('maximize-2', { tam: 28 })}${ctx.icono('plus', { tam: 30 })}</span></div>`;
}

function entrada(props, ctx) {
  if (props.chat.piel === 'whatsapp') {
    return `<div class="ch-entrada ch-entrada-wa"><span class="ch-campo">Mensaje</span><span class="ch-mic-wa">${ctx.icono('mic', { tam: 30, trazo: 2.2 })}</span></div>`;
  }
  return `<div class="ch-entrada"><div class="ch-campo">${ctx.icono('paperclip', { tam: 28 })}${ctx.icono('mic', { tam: 28 })}
      <span class="ch-ph">Pregúntame sobre productos, tecnología o ${esc(ctx.marca.nombre)}…</span>
      <span class="ch-enviar">${ctx.icono('arrow-up', { tam: 30, trazo: 2.4 })}</span></div>
    <div class="ui-aviso-ia" data-qa="aviso" data-qa-min-fs="18" data-qa-ruta="tema.avisos.ia">${esc(ctx.tema.avisos.ia)}</div></div>`;
}

// Nombres de ícono en español (los mismos que usan los demás componentes) → íconos Lucide.
const ICONO = {
  camara: 'cctv', camara_foto: 'camera', disco: 'hard-drive', procesador: 'cpu', wifi: 'wifi', paquete: 'package',
  celular: 'smartphone', video: 'video', base_datos: 'database', capas: 'layers', herramienta: 'wrench',
};
const lucide = (n) => ICONO[n] || n || 'package';

const FORMATO = { xlsx: ['file-spreadsheet', '#1f8f4e'], pdf: ['file-text', '#c0453b'], doc: ['file-text', '#3b6fd6'], img: ['image', '#8a5cd6'] };

function imgOIcono(ctx, it, tam) {
  return it.imagen
    ? `<img src="${ctx.url(it.imagen)}" alt="">`
    : `<span class="ch-ico-prod">${ctx.icono(lucide(it.icono), { tam, trazo: 1.6 })}</span>`;
}

function construirEntrada(en, props, lt, ctx) {
  const it = props.chat.items[en.k];
  const ruta = `${lt.ruta}.chat.items[${en.k}]`;
  const el = document.createElement('div');
  el.className = `ch-en ch-${en.tipo}`;
  const qa = (campo, extra = '') => `data-qa="texto" data-qa-grupo="contenido" data-qa-ruta="${ruta}.${campo}" ${extra}`;
  const wa = props.chat.piel === 'whatsapp';
  switch (en.tipo) {
    case 'etiqueta':
      el.innerHTML = `<span class="ch-chispa">${ctx.icono('sparkles', { tam: 30, trazo: 1.8 })}</span><span>${esc(props.chat.titulo || marcaTexto(ctx))}</span>`;
      break;
    case 'usuario':
      el.innerHTML = `<div class="ch-burbuja usr" ${qa('texto')}>${esc(it.texto)}</div>`;
      break;
    case 'imagen':
      el.innerHTML = `<div class="ch-burbuja usr ch-foto"><div class="ch-foto-marco">${imgOIcono(ctx, it, 150)}
          <i class="ch-esq a"></i><i class="ch-esq b"></i><i class="ch-esq c"></i><i class="ch-esq d"></i><i class="ch-escaner"></i>
          ${it.escaneo ? `<span class="ch-foto-tag-pos"><span class="ch-foto-tag">${esc(it.escaneo)}</span></span>` : ''}</div>
          ${it.texto ? `<div class="ch-foto-pie" ${qa('texto', 'data-qa-min-fs="20"')}>${esc(it.texto)}</div>` : ''}</div>`;
      break;
    case 'nota_voz': {
      const rng = ctx.rng(`onda:${lt.id}:${en.k}`);
      const barras = Array.from({ length: 34 }, (_, i) => {
        const h = 10 + Math.round((0.35 + 0.65 * Math.abs(Math.sin(i * 0.9 + rng() * 2.4))) * 34 * (0.55 + 0.45 * rng()));
        return `<i style="height:${h}px"></i>`;
      }).join('');
      el.innerHTML = `<div class="ch-burbuja usr ch-voz${wa ? ' wa' : ''}"><span class="ch-avatar pq">${esc((ctx.marca.nombre || 'S').slice(0, 1))}</span>
          ${ctx.icono('play', { tam: 28, trazo: 2.2, clase: 'ch-play' })}<span class="ch-onda">${barras}</span>
          <span class="ch-voz-meta"><span class="ch-voz-t">${esc(it.duracion || '0:07')}</span><span class="ch-voz-h">10:24 ${ctx.icono('check-check', { tam: 22, trazo: 2.2 })}</span></span></div>
          ${it.transcripcion ? `<div class="ch-transc">“${esc(it.transcripcion)}”</div>` : ''}`;
      break;
    }
    case 'archivo': {
      const [ico, col] = FORMATO[it.formato || 'xlsx'];
      if (it.de === 'asistente') el.classList.add('ch-de-asistente');
      el.innerHTML = `<div class="ch-burbuja ${it.de === 'asistente' ? 'ent' : 'usr'} ch-arch${wa && it.de !== 'asistente' ? ' wa' : ''}"><span class="ch-arch-ico" style="background:${col}">${ctx.icono(ico, { tam: 30, trazo: 2 })}</span>
          <span class="ch-arch-txt"><b ${qa('nombre', 'data-qa-caja="1"')}>${esc(it.nombre)}</b>${it.detalle ? `<small>${esc(it.detalle)}</small>` : ''}</span>
          <span class="ch-voz-h">10:24 ${ctx.icono('check-check', { tam: 22, trazo: 2.2 })}</span></div>`;
      break;
    }
    case 'paso': {
      const p = crearPaso(it.pasos[en.j], { ruta: `${ruta}.pasos[${en.j}]` });
      el.appendChild(p);
      break;
    }
    case 'razonamiento':
      el.innerHTML = `<div class="ui-caja ch-razon"><span class="ch-rayo">${ctx.icono('zap', { tam: 26, trazo: 2 })}</span>
          <span ${qa('texto')}><b>Razonamiento:</b> ${esc(it.texto)}</span></div>`;
      break;
    case 'asistente':
      el.innerHTML = `<div class="ch-asist${wa ? ' ch-burbuja ent' : ''}" ${qa('texto')}></div>`;
      break;
    case 'productos': {
      const prods = it.productos.map((p, i) => `
        <div class="ch-prod"><div class="ch-prod-img">${imgOIcono(ctx, p, 64)}<span class="ui-punto"></span><span class="ui-insignia">×${p.cantidad}</span></div>
          <div class="ch-prod-nom" ${qa(`productos[${i}].nombre`, 'data-qa-caja="1"')}>${esc(p.nombre)}</div>
          ${p.modelo ? `<div class="ui-mono ch-prod-mod">${esc(p.modelo)}</div>` : ''}</div>`);
      const conectores = it.productos.slice(1).map((_, i) => `
        <div class="ch-con${i === 0 && it.conector ? ' etq' : ''}"><i class="ch-con-linea"></i>${i === 0 && it.conector ? `<span class="ch-con-etq">${esc(it.conector)}</span>` : ''}</div>`);
      const fila = prods.map((p, i) => p + (conectores[i] || '')).join('');
      const acc = (it.accesorios || []).map((a) => `
        <div class="ch-acc"><span class="ch-acc-ico">${ctx.icono(lucide(a.icono), { tam: 28, trazo: 1.8 })}</span><span class="ui-insignia">×${a.cantidad}</span>
          <span class="ch-acc-nom">${esc(a.nombre)}</span><span class="ui-punto"></span></div>`).join('');
      el.innerHTML = `<div class="ui-caja ch-prods"><div class="ch-fila-prods">${fila}</div>${acc ? `<div class="ch-accs">${acc}</div>` : ''}</div>`;
      break;
    }
    case 'ficha': {
      const ex = it.existencias.map((x) => `<div class="ch-ex"><span class="ui-punto"></span><span>${esc(x.lugar)}</span><b>${esc(x.cantidad)}</b></div>`).join('');
      el.innerHTML = `<div class="ui-caja ch-ficha"><div class="ch-ficha-img">${imgOIcono(ctx, it, 76)}</div>
          <div class="ch-ficha-txt"><span class="ch-ficha-marca">${esc(it.marca)}</span>
            <b ${qa('nombre')}>${esc(it.nombre)}</b>${it.modelo ? `<span class="ui-mono">${esc(it.modelo)}</span>` : ''}
            <div class="ch-exs">${ex}</div>
            <div class="ch-ficha-bot"><span class="ui-boton amarillo ch-agregar">${ctx.icono('shopping-cart', { tam: 24, trazo: 2.2 })}${esc(it.boton)}</span><span class="ui-boton fantasma">Ver</span></div>
          </div>${it.toast ? `<div class="ch-toast ch-toast-ficha">${ctx.icono('circle-check', { tam: 24, trazo: 2.2 })}${esc(it.toast)}</div>` : ''}</div>`;
      break;
    }
    case 'cotizacion':
      el.innerHTML = `<div class="ui-caja ch-cot"><span class="ch-cot-ico">${ctx.icono('file-text', { tam: 34, trazo: 2 })}</span>
          <span class="ch-cot-txt"><b ${qa('titulo', 'data-qa-caja="1"')}>${esc(it.titulo)}</b>${it.detalle ? `<small>${esc(it.detalle)}</small>` : ''}</span>
          <span class="ui-boton ch-cot-bot">${esc(it.boton)}</span></div>`;
      break;
    case 'toast':
      el.innerHTML = `<div class="ch-toast" ${qa('texto')}>${ctx.icono('circle-check', { tam: 26, trazo: 2.2 })}${esc(it.texto)}</div>`;
      break;
  }
  return el;
}

export function montar(raiz, props, lt, ctx) {
  const piel = props.chat.piel || 'asistente_web';
  raiz.insertAdjacentHTML('beforeend', `
    <div class="ch-pos"><div class="ui-tarjeta ch ch-piel-${piel}">
      ${cabecera(props, ctx)}
      <div class="ch-cuerpo"><div class="ch-pila"></div></div>
      ${entrada(props, ctx)}
    </div></div>`);
  const pila = raiz.querySelector('.ch-pila');
  const lista = entradas(props).map((en) => {
    const el = construirEntrada(en, props, lt, ctx);
    pila.appendChild(el);
    return { en, el, it: props.chat.items[en.k], h: 0 };
  });
  // Palabras de las respuestas del asistente (se "escriben" palabra por palabra) y referencias a
  // las piezas animadas de cada entrada: se buscan UNA vez aquí, nunca dentro de actualizar(t).
  for (const x of lista) {
    if (x.en.tipo === 'asistente') x.spans = construirPalabras(x.el.querySelector('.ch-asist'), parsearEnfasis(x.it.texto));
    x.r = referencias(x.el);
  }
  const P_ = lt.pasos;
  const beat = (id) => P_[id] || { ini: 0, dur: 0.5 };

  // Cuándo se completa cada paso: al entrar la siguiente entrada (o casi al final de su beat).
  lista.forEach((x, i) => {
    if (x.en.tipo !== 'paso') return;
    const sig = lista[i + 1];
    x.hecho = sig ? beat(sig.en.id).ini + 0.12 : beat(x.en.id).ini + beat(x.en.id).dur * 0.85;
  });

  return {
    medir() {
      for (const x of lista) x.h = x.el.offsetHeight;
    },
    actualizar(t) {
      // Pila anclada abajo: lo que aún no entra se queda "debajo" y empuja al entrar.
      let desplazo = 0;
      for (const x of lista) {
        const b = beat(x.en.id);
        const kEspacio = P(t, b.ini, 0.42, E.outCubic);
        desplazo += (1 - kEspacio) * (x.h + GAP);
      }
      transformar(pila, { y: desplazo });

      for (const x of lista) {
        const b = beat(x.en.id);
        const tl = t - b.ini;
        const k = P(t, b.ini + 0.04, 0.36, E.outCubic);
        const usr = LADO_USUARIO.has(x.en.tipo) && x.it.de !== 'asistente';
        if (x.en.tipo === 'paso') {
          actualizarPaso(x.el.firstChild, t, { ini: b.ini, hecho: x.hecho });
          opacidad(x.el, 1);
          continue;
        }
        aparecer(x.el, k, { dy: 16, blur: 6, escala: usr ? 0.96 : 0.985 });

        if (x.en.tipo === 'asistente') {
          x.spans.forEach((s, i) => opacidad(s, P(t, b.ini + 0.08 + i * 0.035, 0.18, E.outQuad)));
        } else if (x.en.tipo === 'productos') {
          animarProductos(x.r, t, b);
        } else if (x.en.tipo === 'imagen') {
          animarFoto(x.r, t, b, beat(`${x.en.id}s`));
        } else if (x.en.tipo === 'nota_voz') {
          animarVoz(x.r, t, beat(`${x.en.id}r`));
        } else if (x.en.tipo === 'ficha') {
          animarFicha(x.r, t, b, P_[`${x.en.id}t`]);
        } else if (x.en.tipo === 'cotizacion') {
          const bot = x.r.cotBot;
          const kb = resorte(tl - 0.3, { zeta: 0.6, omega: 16 });
          estilo(bot, { transform: `scale(${(0.85 + 0.15 * kb).toFixed(4)})`, opacity: String(clamp((tl - 0.3) * 5).toFixed(3)) });
        } else if (x.en.tipo === 'toast') {
          const kt = resorte(tl, { zeta: 0.55, omega: 17 });
          estilo(x.el.firstChild, { transform: `scale(${(0.8 + 0.2 * kt).toFixed(4)})` });
        }
      }
    },
  };
}

// ------------------------------------------------------------------ animaciones por tipo
// Referencias a las piezas animadas de una entrada (se resuelven una vez, al montar).
function referencias(el) {
  const q = (s) => el.querySelector(s);
  const qa = (s) => [...el.querySelectorAll(s)];
  return {
    prods: qa('.ch-prod').map((p) => ({ p, ins: p.querySelector('.ui-insignia'), pt: p.querySelector('.ui-punto') })),
    cons: qa('.ch-con').map((c) => ({ linea: c.querySelector('.ch-con-linea'), etq: c.querySelector('.ch-con-etq') })),
    accs: qa('.ch-acc'),
    escaner: q('.ch-escaner'),
    esquinas: qa('.ch-esq'),
    tag: q('.ch-foto-tag'),
    barras: qa('.ch-onda i'),
    onda: q('.ch-onda'),
    exs: qa('.ch-ex'),
    agregar: q('.ch-agregar'),
    toastFicha: q('.ch-toast-ficha'),
    cotBot: q('.ch-cot-bot'),
  };
}

function animarProductos(r, t, b) {
  const tl = t - b.ini;
  r.prods.forEach(({ p, ins, pt }, i) => {
    const t0 = 0.12 + i * 0.16;
    aparecer(p, P(tl, t0, 0.34, E.outCubic), { dy: 12, blur: 5, escala: 0.92 });
    const ki = resorte(tl - t0 - 0.22, { zeta: 0.5, omega: 18 });
    estilo(ins, { transform: `scale(${(0.4 + 0.6 * ki).toFixed(4)})`, opacity: String(clamp((tl - t0 - 0.22) * 6).toFixed(3)) });
    opacidad(pt, P(tl, t0 + 0.4, 0.2));
  });
  r.cons.forEach(({ linea, etq }, i) => {
    const t0 = 0.28 + i * 0.16;
    revelarX(linea, P(tl, t0, 0.4, E.inOutQuad));
    // Datos "viajando" por el enlace (puntos que avanzan de forma continua).
    estilo(linea, { backgroundPosition: `${((tl * 46) % 24).toFixed(2)}px 50%` });
    if (etq) aparecer(etq, P(tl, t0 + 0.25, 0.3), { dy: 6, blur: 3, escala: 0.9 });
  });
  r.accs.forEach((a, i) => aparecer(a, P(tl, 0.55 + i * 0.12, 0.32), { dy: 10, blur: 4 }));
}

function animarFoto(r, t, b, bs) {
  const ts = t - bs.ini;
  const k = clamp(ts / Math.max(0.3, bs.dur));
  const linea = r.escaner;
  // Línea de escaneo que baja y sube una vez durante el beat de escaneo.
  const y = 0.5 - 0.5 * Math.cos(k * Math.PI * 2);
  estilo(linea, { top: `${(6 + y * 84).toFixed(2)}%`, opacity: String((ts > 0 && k < 1 ? 1 : 0).toFixed(2)) });
  const kc = P(t, bs.ini - 0.1, 0.3, E.outBack);
  r.esquinas.forEach((q) => estilo(q, { opacity: String(clamp(kc).toFixed(3)), transform: `scale(${(1.25 - 0.25 * kc).toFixed(4)})` }));
  if (r.tag) aparecer(r.tag, P(t, bs.ini + bs.dur - 0.15, 0.3), { dy: 8, blur: 3, escala: 0.9 });
}

function animarVoz(r, t, br) {
  const tr = t - br.ini;
  const k = clamp(tr / Math.max(0.3, br.dur));
  const n = r.barras.length;
  r.barras.forEach((bar, i) => {
    const jugada = i / n < k;
    estilo(bar, { background: jugada ? '#e9fff6' : 'rgba(233,255,246,0.45)' });
  });
  // Cabezal de reproducción sobre la onda.
  estilo(r.onda, { '--k': k.toFixed(4) });
}

function animarFicha(r, t, b, bt) {
  const tl = t - b.ini;
  r.exs.forEach((x, i) => aparecer(x, P(tl, 0.25 + i * 0.1, 0.3), { dy: 8, blur: 3 }));
  if (bt) {
    // "Toque" en Agregar: se hunde un instante y aparece el aviso.
    const toque = Math.sin(clamp((t - bt.ini) / 0.22) * Math.PI);
    transformar(r.agregar, { s: 1 - 0.07 * toque });
    const kt = P(t, bt.ini + 0.12, 0.3, E.outCubic);
    aparecer(r.toastFicha, kt, { dy: 14, blur: 4, escala: 0.94 });
  }
}
