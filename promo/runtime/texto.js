// texto.js — texto palabra por palabra, auto-ajuste de tamaño y conteo de líneas.
//
// Todo el texto se crea al montar; animar = cambiar opacidad/transform por palabra.
// Nunca se cambia textContent dentro de seek(t).
// `palabras` llega ya normalizado desde el planificador: [{w, e}] (e = énfasis).

export function construirPalabras(el, palabras, { claseEnfasis = 'enf' } = {}) {
  el.textContent = '';
  const spans = [];
  palabras.forEach((p, i) => {
    if (i > 0) el.appendChild(document.createTextNode(' '));
    const s = document.createElement('span');
    s.className = 'pal' + (p.e ? ' ' + claseEnfasis : '');
    s.textContent = p.w;
    s.dataset.i = String(i);
    el.appendChild(s);
    spans.push(s);
  });
  return spans;
}

// Cuenta líneas por la posición vertical de cada palabra (tolerancia de medio renglón).
export function contarLineas(spans) {
  const tops = [];
  for (const s of spans) {
    const y = s.offsetTop;
    if (!tops.some((t) => Math.abs(t - y) < s.offsetHeight * 0.5)) tops.push(y);
  }
  return tops.length;
}

// Palabras de la última línea (para detectar "viudas": una palabra sola al final).
export function palabrasUltimaLinea(spans) {
  if (!spans.length) return 0;
  const yUlt = spans[spans.length - 1].offsetTop;
  // Cuenta palabras reales: una pieza unida con espacio duro ("en\u00A0segundos.") son dos.
  return spans
    .filter((s) => Math.abs(s.offsetTop - yUlt) < s.offsetHeight * 0.5)
    .reduce((n, s) => n + s.textContent.split(/[\s\u00A0]+/).filter(Boolean).length, 0);
}

// Baja el tamaño de fuente desde `max` hasta `min` hasta que quepa en `lineas` y en el ancho.
// Marca el resultado en data-* para que la QA lo reporte con la ruta JSON del texto.
export function ajustar(el, spans, { max, min, paso = 2, lineas, preferir = null }) {
  let fs = max;
  let n = 0;
  // Preferencia opcional: menos líneas si el tamaño sigue siendo generoso (titulares de 2 renglones
  // se leen mejor que 3 renglones angostos).
  if (preferir) {
    for (let f = max; f >= preferir.min; f -= paso) {
      el.style.fontSize = f + 'px';
      if (contarLineas(spans) <= preferir.lineas && el.scrollWidth <= el.clientWidth + 1) {
        el.dataset.qaLineas = String(contarLineas(spans));
        el.dataset.qaMaxLineas = String(lineas);
        el.dataset.qaFs = String(f);
        el.dataset.qaViuda = spans.length > 3 && palabrasUltimaLinea(spans) === 1 ? '1' : '0';
        return { fs: f, lineas: preferir.lineas, ok: true };
      }
    }
  }
  for (; fs >= min; fs -= paso) {
    el.style.fontSize = fs + 'px';
    n = contarLineas(spans);
    const anchoOk = el.scrollWidth <= el.clientWidth + 1;
    if (n <= lineas && anchoOk) {
      el.dataset.qaLineas = String(n);
      el.dataset.qaMaxLineas = String(lineas);
      el.dataset.qaFs = String(fs);
      el.dataset.qaViuda = spans.length > 3 && palabrasUltimaLinea(spans) === 1 ? '1' : '0';
      return { fs, lineas: n, ok: true };
    }
  }
  fs = min;
  el.style.fontSize = fs + 'px';
  n = contarLineas(spans);
  el.dataset.qaLineas = String(n);
  el.dataset.qaMaxLineas = String(lineas);
  el.dataset.qaFs = String(fs);
  el.dataset.qaNoCabe = '1';
  return { fs, lineas: n, ok: false };
}
