// escena.js — gestor de escenas: ventanas de tiempo, entrada/salida traslapadas y tinte de fondo.
//
// Las escenas se traslapan `transicion` segundos: la saliente sube y se desenfoca mientras la
// entrante aparece. No hay cortes duros ni wipes. Cada componente recibe el tiempo LOCAL de su escena.

import { P, E, mezclar } from './tiempo.js';
import { aparecer, desaparecer } from './movimiento.js';
import * as titular from './titular.js';
import * as subtitulo from './subtitulo.js';

export class Gestor {
  constructor({ raiz, lt, ctx, modulos, fondo }) {
    this.raiz = raiz;
    this.lt = lt;
    this.ctx = ctx;
    this.modulos = modulos;
    this.fondo = fondo;
    this.items = [];
  }

  montar() {
    const n = this.lt.escenas.length;
    this.lt.escenas.forEach((e, i) => {
      const div = document.createElement('div');
      div.className = `escena escena-${e.tipo}`;
      div.dataset.id = e.id;
      this.raiz.appendChild(div);
      const inst = this.modulos[e.tipo].montar(div, e.props, e, this.ctx);
      const tit = e.titular && e.titular.length ? titular.montar(div, e, this.ctx) : null;
      const sub = e.subtitulo && e.subtitulo.length ? subtitulo.montar(div, e, this.ctx) : null;
      this.items.push({ e, div, inst, tit, sub, ultima: i === n - 1 });
    });
  }

  // Se mide con la escena en el flujo (display:block) pero invisible, después de cargar fuentes.
  async medir() {
    for (const it of this.items) {
      it.div.style.display = 'block';
      it.div.style.visibility = 'hidden';
      if (it.inst.medir) await it.inst.medir();
      if (it.tit) it.tit.medir();
      if (it.sub) it.sub.medir();
      it.div.style.display = 'none';
      it.div.style.visibility = '';
    }
  }

  vivas(t) {
    return this.items.filter(({ e, ultima }) => t >= e.ini - 1e-6 && (t < e.fin || (ultima && t <= e.fin + 1e-6)));
  }

  seek(t) {
    const vivas = new Set(this.vivas(t));
    let tinte = null;
    for (const it of this.items) {
      const { e, div, inst, tit, sub } = it;
      if (!vivas.has(it)) {
        div.style.display = 'none';
        continue;
      }
      div.style.display = 'block';
      const tl = t - e.ini;
      const kIn = e.entrada > 0 ? P(tl, 0, e.entrada, E.outCubic) : 1;
      const kOut = e.salida > 0 ? P(tl, e.dur - e.salida, e.salida, E.inCubic) : 0;
      if (kOut > 0) desaparecer(div, kOut, { dy: -18, blur: 8 });
      else aparecer(div, kIn, { dy: 28, blur: 10 });
      inst.actualizar(tl);
      if (tit) tit.actualizar(tl);
      if (sub) sub.actualizar(tl);

      // Tinte: la escena entrante domina según su avance de entrada (mezcla perceptual OKLab).
      const par = this.ctx.tema.tintes[e.tinte] || this.ctx.tema.tintes.ninguno;
      if (!tinte) tinte = { a: par[0], b: par[1], k: 1 };
      else tinte = { a: mixHex(tinte.a, par[0], kIn), b: mixHex(tinte.b, par[1], kIn), k: 1 };
    }
    if (this.fondo) this.fondo.actualizar(t, tinte || { a: this.ctx.tema.colores.base, b: this.ctx.tema.colores.base });
  }
}

function mixHex(c1, c2, k) {
  const [r, g, b] = mezclar(c1, c2, k);
  return '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
}
