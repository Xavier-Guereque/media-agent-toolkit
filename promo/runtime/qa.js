// qa.js — revisión determinista del DOM en un instante t (sin capturas, sin modelos de visión).
//
// El orquestador barato no ve imágenes: esta es la QA que sí puede "leer". Cada problema sale con
// código, ruta JSON del spec y un arreglo concreto. Se ejecuta DESPUÉS de seek(t) (aquí sí se lee layout).
//
// Atributos que ponen los componentes:
//   data-qa="texto|cta|contenido|aviso|decor"  data-qa-ruta="escenas[1].titular"
//   data-qa-grupo="titular|contenido|subtitulo|cta|..."  (grupos distintos no deben chocar)
//   data-qa-caja="1"  (caja de tamaño fijo: su contenido no debe desbordarse)
//   data-qa-lineas / data-qa-max-lineas / data-qa-no-cabe / data-qa-viuda / data-qa-fs  (los pone texto.ajustar)
//   data-qa-min-fs="18"  (tamaño mínimo efectivo permitido; por defecto 22 px)

function opacidadEfectiva(el, lienzo) {
  let o = 1;
  for (let n = el; n && n !== lienzo; n = n.parentElement) {
    const cs = getComputedStyle(n);
    if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
    o *= parseFloat(cs.opacity);
    if (o < 0.01) return 0;
  }
  return o;
}

// Caja ajustada al texto real: la unión de las palabras (.pal) si las hay; si no, el elemento.
function caja(el) {
  const pals = el.querySelectorAll('.pal');
  if (!pals.length) {
    // Sin palabras animadas: se mide el texto real con un Range (no la caja de ancho completo).
    if (el.dataset.qa === 'texto' || el.dataset.qa === 'aviso') {
      const rg = document.createRange();
      rg.selectNodeContents(el);
      const x = rg.getBoundingClientRect();
      if (x.width > 0.5) return x;
    }
    return el.getBoundingClientRect();
  }
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  for (const p of pals) {
    const x = p.getBoundingClientRect();
    if (x.width < 0.5) continue;
    l = Math.min(l, x.left); t = Math.min(t, x.top); r = Math.max(r, x.right); b = Math.max(b, x.bottom);
  }
  return l === Infinity ? el.getBoundingClientRect() : { left: l, top: t, right: r, bottom: b, width: r - l, height: b - t };
}

// Recorta la caja con los ancestros que ocultan desborde (p. ej. el cuerpo del chat): lo que ya
// subió bajo la cabecera no se ve y no debe contar como choque ni como zona invadida.
function visible(el, r, lienzo) {
  let { left, top, right, bottom } = r;
  for (let n = el.parentElement; n && n !== lienzo; n = n.parentElement) {
    const cs = getComputedStyle(n);
    if (cs.overflow === 'visible' && cs.overflowX === 'visible' && cs.overflowY === 'visible') continue;
    const c = n.getBoundingClientRect();
    left = Math.max(left, c.left); top = Math.max(top, c.top); right = Math.min(right, c.right); bottom = Math.min(bottom, c.bottom);
  }
  return right - left < 1 || bottom - top < 1 ? null : { left, top, right, bottom, width: right - left, height: bottom - top };
}

const corta = (s, n = 48) => {
  const x = (s || '').replace(/\s+/g, ' ').trim();
  return x.length > n ? `"${x.slice(0, n - 1)}…"` : `"${x}"`;
};

export function revisar(t, { tema, w, h }) {
  const lienzo = document.getElementById('lienzo');
  const zs = tema.zonas_seguras;
  const issues = [];
  const add = (codigo, severidad, el, msg, arreglo) =>
    issues.push({ codigo, severidad, ruta: el.dataset.qaRuta || '?', t: +t.toFixed(2), msg, arreglo });

  const cand = [...lienzo.querySelectorAll('[data-qa]')]
    .map((el) => ({ el, o: opacidadEfectiva(el, lienzo) }))
    .filter((x) => x.o >= 0.5);

  const cajas = [];
  for (const { el, o } of cand) {
    const r = visible(el, caja(el), lienzo);
    if (!r) continue;
    const rol = el.dataset.qa;
    const txt = corta(el.textContent);
    const escena = el.closest('.escena');
    cajas.push({ el, r, o, rol, grupo: el.dataset.qaGrupo || null, escena: escena ? escena.dataset.id : null });

    if (el.dataset.qaNoCabe === '1') {
      add('E-QA-NO-CABE', 'E', el, `${txt} no cabe en ${el.dataset.qaMaxLineas} líneas ni con la letra mínima (${el.dataset.qaFs}px).`,
        'Acorta el texto (quita 2 a 4 palabras).');
    } else if (el.dataset.qaViuda === '1') {
      add('W-QA-VIUDA', 'W', el, `${txt}: la última línea queda con una sola palabra.`, 'Reordena o acorta una palabra.');
    }

    if (r.left < -2 || r.top < -2 || r.right > w + 2 || r.bottom > h + 2) {
      add('E-QA-FUERA', 'E', el, `${txt} se sale del cuadro.`, 'Acorta el texto o quita elementos de la escena.');
    }

    if (rol === 'texto' || rol === 'cta' || rol === 'aviso') {
      if (r.top < zs.arriba - 1) {
        add('E-QA-ZONA', 'E', el, `${txt} invade la zona segura superior (${Math.round(r.top)}px < ${zs.arriba}px).`, 'Acorta el texto para que ocupe menos líneas.');
      }
      if (r.bottom > h - zs.abajo + 1) {
        add('E-QA-ZONA', 'E', el, `${txt} invade la zona segura inferior (termina en ${Math.round(r.bottom)}px; límite ${h - zs.abajo}px).`, 'Acorta el texto o quita un elemento de la escena.');
      }
      if (r.right > w - zs.derecha + 1 && r.bottom > zs.derecha_desde_y && r.top < zs.derecha_hasta_y) {
        add('W-QA-ZONA-DER', 'W', el, `${txt} entra en la columna de íconos de la plataforma (derecha).`, 'Acorta el texto.');
      }
    }

    if (rol === 'texto' || rol === 'cta' || rol === 'aviso') {
      const fs = parseFloat(getComputedStyle(el).fontSize);
      // Escala acumulada (transform de cámara/entrada): caja transformada ÷ caja de layout.
      const escala = el.offsetWidth > 0 ? el.getBoundingClientRect().width / el.offsetWidth : 1;
      const efectivo = fs * escala;
      const minimo = parseFloat(el.dataset.qaMinFs || '22');
      if (efectivo < minimo - 0.1) {
        add('E-QA-TAMANO', 'E', el, `${txt} se ve a ${efectivo.toFixed(1)}px (mínimo ${minimo}px).`, 'Acorta el texto para que no tenga que achicarse.');
      }
    }

    if (el.dataset.qaCaja === '1' && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)) {
      add('E-QA-DESBORDE', 'E', el, `${txt} se desborda de su caja (${el.scrollWidth}×${el.scrollHeight} > ${el.clientWidth}×${el.clientHeight}).`,
        'Acorta el texto de ese elemento.');
    }
  }

  // Choques entre grupos distintos DE LA MISMA escena (titular vs contenido vs subtítulo vs CTA).
  // Entre escenas distintas solo hay cruce durante el fundido, que es por diseño: no se reporta
  // (antes W-QA-CRUCE: 9+ avisos no accionables por video que el orquestador pagaba en tokens).
  for (let i = 0; i < cajas.length; i++) {
    for (let j = i + 1; j < cajas.length; j++) {
      const a = cajas[i];
      const b = cajas[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ix = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const iy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (ix <= 4 || iy <= 4) continue;
      if (a.escena !== b.escena) continue;
      if (!a.grupo || !b.grupo || a.grupo === b.grupo) continue;
      add('E-QA-CHOQUE', 'E', a.el, `choca con ${b.el.dataset.qaRuta || b.grupo} (${Math.round(ix)}×${Math.round(iy)}px).`,
        'Acorta el titular o quita un elemento de la escena.');
    }
  }
  return issues;
}
