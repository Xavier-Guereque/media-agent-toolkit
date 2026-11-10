// intro — salto al hiperespacio (starburst radial) + título grande, luego aparece la marca.
// Como el arranque del video de referencia: título grande sobre líneas radiales → lockup de marca.
//
// Determinismo: los parámetros de cada línea salen de rng(semilla+id) una sola vez al montar;
// cada cuadro limpia el canvas y redibuja todo como función pura de t (sin estelas acumuladas).

import { P, E, clamp, resorte } from '../../runtime/tiempo.js';
import { aparecer, estilo, opacidad } from '../../runtime/movimiento.js';
import { construirPalabras, ajustar } from '../../runtime/texto.js';
import { parsearEnfasis } from '../../runtime/palabras.js';
import { crearMarca, ajustarMarca } from '../../runtime/marca.js';

const N_LINEAS = 900;
const STAGGER = 0.06;
const FADE = 0.28;

export function planear(props) {
  const n = parsearEnfasis(props.titulo).length;
  const rev = Math.max(0, n - 1) * STAGGER + FADE;
  const pasos = [
    { id: 'titulo', min: rev, pref: rev + 0.1 },
    { id: 'lectura', min: 0.45, pref: 0.8 },
    { id: 'salto', min: 0.35, pref: 0.45, cue: 'whoosh' },
  ];
  if (props.marca !== false) pasos.push({ id: 'marca', min: 0.6, pref: 0.8, cue: 'revelar' });
  // arranque 0: el gancho se ve desde el primer cuadro (lo que decide si el usuario se queda).
  return { pasos, reposo: { min: 0.35, pref: 0.7 }, arranque: 0 };
}

export function montar(raiz, props, lt, ctx) {
  const { w, h } = ctx;
  raiz.insertAdjacentHTML('beforeend', `
    <canvas class="in-warp" width="${w}" height="${h}"></canvas>
    <div class="in-pos in-pos-titulo"><div class="in-titulo" data-qa="texto" data-qa-grupo="titulo" data-qa-ruta="${lt.ruta}.titulo"></div></div>
    ${props.marca !== false ? '<div class="in-pos in-pos-marca"><div class="in-marca"></div></div>' : ''}
  `);
  const canvas = raiz.querySelector('.in-warp');
  const g = canvas.getContext('2d');
  const tit = raiz.querySelector('.in-titulo');
  const spans = construirPalabras(tit, parsearEnfasis(props.titulo));
  const marca = props.marca !== false ? crearMarca(ctx, { alto: 70 }) : null;
  const contMarca = raiz.querySelector('.in-marca');
  if (marca) contMarca.appendChild(marca.el);

  // Campo de estrellas 3D: cada estrella tiene (x, y) en un plano y una profundidad que avanza
  // hacia la cámara; la proyección x/z produce el "hiperespacio" sin rayos que converjan a un punto.
  // En t=0 las estelas son casi puntos y se alargan al acelerar (como la referencia).
  const rng = ctx.rng(`warp:${lt.id}`);
  const estrellas = [];
  while (estrellas.length < N_LINEAS) {
    const x = (rng() * 2 - 1) * 1.7;
    const y = (rng() * 2 - 1) * 1.7;
    const d0 = rng();
    const vel = 0.75 + rng() * 0.5;
    const ancho = 1.0 + rng() * 2.2;
    const lum = 0.55 + rng() * 0.45;
    const lila = rng() < 0.35;
    if (Math.abs(x) < 0.02 && Math.abs(y) < 0.02) continue;
    estrellas.push({ x, y, d0, vel, ancho, lum, lila });
  }
  const cx = w / 2;
  const cy = h * 0.47;
  const F = h * 0.15;
  const p = lt.pasos;
  const tSalto = p.salto.ini;

  // Rapidez r(t) = a + b·(1 − e^(−t/τ)) + aceleración cúbica en el salto; s(t) = ∫r (forma cerrada).
  const A = 0.06, B = 0.85, TAU = 0.22, K = 1.8;
  const rapidez = (t) => A + B * (1 - Math.exp(-t / TAU)) + 3 * K * Math.pow(Math.max(0, t - tSalto), 2);
  const recorrido = (t) => A * t + B * (t - TAU * (1 - Math.exp(-t / TAU))) + K * Math.pow(Math.max(0, t - tSalto), 3);
  const proyectar = (e, d) => {
    const z = 1 - 0.94 * d;
    return [cx + (e.x / z) * F, cy + (e.y / z) * F];
  };

  function dibujar(t, alfa) {
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = 'source-over';
    g.clearRect(0, 0, w, h);
    if (alfa <= 0.002) return;
    g.fillStyle = `rgba(11,14,20,${alfa.toFixed(4)})`;
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'lighter';
    g.lineCap = 'round';
    const s = recorrido(t);
    const estela = 0.27 * rapidez(t);
    for (const e of estrellas) {
      const d = (e.d0 + e.vel * s * 0.3) % 1;
      const dCola = Math.max(0, d - e.vel * estela);
      const [x1, y1] = proyectar(e, d);
      const [x0, y0] = proyectar(e, dCola);
      if ((x1 < -50 && x0 < -50) || (x1 > w + 50 && x0 > w + 50) || (y1 < -50 && y0 < -50) || (y1 > h + 50 && y0 > h + 50)) continue;
      // Más brillante y gruesa cuanto más cerca; nace tenue al fondo.
      const a = alfa * e.lum * clamp(d / 0.2) * (0.5 + 0.5 * d);
      if (a < 0.01) continue;
      g.strokeStyle = e.lila ? `rgba(196,206,248,${a.toFixed(3)})` : `rgba(255,255,255,${a.toFixed(3)})`;
      g.lineWidth = e.ancho * (0.45 + 1.4 * d * d);
      g.beginPath();
      g.moveTo(x0, y0);
      // Longitud mínima de 1.5 px: en reposo se ven como estrellas, no desaparecen.
      const dx = x1 - x0, dy = y1 - y0, L = Math.hypot(dx, dy);
      if (L < 1.5) g.lineTo(x0 + (dx / (L || 1)) * 1.5, y0 + (dy / (L || 1)) * 1.5);
      else g.lineTo(x1, y1);
      g.stroke();
    }
  }

  return {
    medir() {
      if (marca) ajustarMarca(marca, 900);
      ajustar(tit, spans, { max: 116, min: 80, lineas: 2 });
    },
    actualizar(t) {
      // Las líneas siguen detrás del logo un momento y luego se desvanecen al fondo marino.
      const finWarp = p.marca ? p.marca.ini + 0.35 : p.salto.ini + p.salto.dur;
      const alfaWarp = 1 - P(t, finWarp, 0.6, E.inOutQuad);
      dibujar(t, alfaWarp);

      // Título: entra palabra por palabra; en el salto crece y se desenfoca (lo "atravesamos").
      spans.forEach((sp, i) => aparecer(sp, P(t, p.titulo.ini + i * STAGGER, FADE, E.outCubic), { dy: 18, blur: 12, escala: 0.96 }));
      const kS = P(t, tSalto, p.salto.dur + 0.1, E.inCubic);
      estilo(tit, {
        opacity: String((1 - kS).toFixed(4)),
        transform: kS > 0 ? `scale(${(1 + 0.35 * kS).toFixed(4)})` : 'none',
        filter: kS > 0.002 ? `blur(${(14 * kS).toFixed(2)}px)` : 'none',
      });

      if (marca) {
        const tm = t - p.marca.ini;
        aparecer(marca.logo, P(tm, 0, 0.55, E.outCubic), { blur: 18, escala: 1.12, dy: 0 });
        if (marca.prod) aparecer(marca.prod, P(tm, 0.1, 0.5, E.outCubic), { dx: -16, dy: 0, blur: 8 });
        if (marca.ver) {
          const k = resorte(tm - 0.34, { zeta: 0.55, omega: 18 });
          estilo(marca.ver, { opacity: String(clamp((tm - 0.34) * 5).toFixed(3)), transform: `scale(${(0.6 + 0.4 * k).toFixed(4)})` });
        }
        opacidad(contMarca, tm > -0.05 ? 1 : 0);
      }
    },
  };
}
