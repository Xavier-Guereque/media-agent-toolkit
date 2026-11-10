// marca.js — lockup de marca: logo SVG (currentColor) + producto ("AI") + pastilla de versión ("v5").
// Si el tema no tiene logo (privado/ ausente), cae a un wordmark tipográfico.

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export function crearMarca(ctx, { alto = 58, producto, version } = {}) {
  const m = ctx.marca;
  const prod = producto !== undefined ? producto : m.producto;
  const ver = version !== undefined ? version : m.version;
  const el = document.createElement('div');
  el.className = 'marca';
  // La QA vigila el lockup (se sale del cuadro o choca con el lema si el producto es largo).
  el.dataset.qa = 'texto';
  el.dataset.qaGrupo = 'marca';
  el.dataset.qaRuta = 'marca.producto';
  el.dataset.qaMinFs = '0'; // el contenedor no tiene letra propia; sus piezas ya están dimensionadas
  const ancho = Math.round(alto * (m.proporcion_logo || 8.45));
  const logo = m.svg
    ? `<span class="marca-logo" style="height:${alto}px;width:${ancho}px">${m.svg}</span>`
    : `<span class="marca-logo marca-logo-texto" style="font-size:${Math.round(alto * 1.18)}px">${esc(m.nombre)}</span>`;
  el.innerHTML =
    logo +
    (prod ? `<span class="marca-prod" style="font-size:${Math.round(alto * 1.42)}px">${esc(prod)}</span>` : '') +
    (ver ? `<span class="marca-ver" style="font-size:${Math.round(alto * 0.56)}px">${esc(ver)}</span>` : '');
  return {
    el,
    logo: el.querySelector('.marca-logo'),
    prod: el.querySelector('.marca-prod'),
    ver: el.querySelector('.marca-ver'),
  };
}

// Reduce el lockup (todas sus medidas por igual) hasta que quepa en `maxAncho`. Se llama en medir().
export function ajustarMarca(m, maxAncho) {
  const ancho = m.el.scrollWidth;
  if (ancho <= maxAncho) return 1;
  const f = maxAncho / ancho;
  const escalar = (el, props) => {
    if (!el) return;
    for (const k of props) {
      const v = parseFloat(el.style[k]);
      if (v) el.style[k] = `${(v * f).toFixed(2)}px`;
    }
  };
  escalar(m.logo, ['height', 'width', 'fontSize']);
  escalar(m.prod, ['fontSize']);
  escalar(m.ver, ['fontSize']);
  return f;
}
