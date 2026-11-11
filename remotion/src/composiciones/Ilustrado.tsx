// Explicador ilustrado (composición BASE del motor ilustrado; la alimenta scripts/ilustrar.py, el agente no edita TSX).
//
// Cada toma es una ilustración (o un clip) con movimiento de cámara:
//   tipo 'imagen'   → una imagen con empuje/paneo de cámara (Ken Burns con curva suave)
//   tipo 'parallax' → 2–4 capas PNG (fondo … primer plano) que se desplazan según su profundidad `z` (0 lejos, 1 cerca)
//   tipo 'clip'     → un MP4 (imagen a video de OpenRouter, o un render de Blender) a pantalla completa
// Encima: titular cinético palabra por palabra con desenfoque de movimiento direccional (filtro SVG proporcional a la
// velocidad), subtítulo karaoke opcional, «hervor» del trazo a `fps_animacion` (desplazamiento con ruido que cambia de
// semilla cada 1/12 s, el look de animación a mano) y textura de papel en multiply que unifica imágenes, clips y renders.
//
// Firma de la casa (campos opcionales; sin ellos todo se ve como antes):
//   entrada 'entintado' → MP4 precalculado por scripts/entintado.py (la tinta se dibuja y luego entra el color); su
//                         último cuadro es la ilustración, así que el paso a la toma no salta
//   transicion 'mancha' → gota de tinta que se expande (clip-path con borde irregular y gotas satélite) y revela la toma
//   anotaciones         → círculo, subrayado o flecha a mano (stroke-dashoffset) en el color de acento, sincronizados
//   cierre              → sello estampado en tinta de acento con textura de goma
//   titulo *palabra*    → palabra en el color de acento
//
// Reglas de la casa: todo depende de useCurrentFrame() (determinista; nada de Math.random ni animaciones CSS).
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { Karaoke } from '../componentes/Karaoke';
import { FUENTE } from '../lib/fuentes';
import type { Palabra } from '../lib/karaoke';
import type { Meta, PropsBase } from '../lib/props';

type Par = [number, number];
type Camara = { escala?: Par; x?: Par; y?: Par; rot?: Par; curva?: 'suave' | 'lineal' | 'entrada' | 'salida' };
type Capa = { src: string; z: number };
type Titulo = { texto: string; en?: number; hasta?: number; pos?: 'arriba' | 'centro' | 'abajo'; tam?: number };
type Entrada = { src: string; dur: number }; // MP4 del entintado y su duración (s)
type Transicion = { tipo: 'mancha'; x?: number; y?: number; semilla?: number };
type Anotacion = {
  tipo: 'circulo' | 'subrayado' | 'flecha';
  x: number; // centro (círculo, subrayado) o punta (flecha), en fracción del cuadro
  y: number;
  w?: number;
  h?: number;
  desde?: Par; // flecha: punto de partida
  en: number; // s desde el inicio del <Sequence> de la toma
  dur?: number; // s que tarda en dibujarse
  color?: string;
  semilla?: number;
};
type Toma = {
  id: string;
  inicio: number;
  fin: number;
  tipo: 'imagen' | 'parallax' | 'clip';
  src?: string;
  imagen?: string; // clip con entrada: ilustración que se ve hasta que arranca el clip
  capas?: Capa[];
  camara?: Camara;
  titulo?: Titulo;
  palabras?: Palabra[];
  fundido?: number; // s de transición con la toma anterior
  transicion?: Transicion; // sin ella: fundido cruzado
  entrada?: Entrada;
  anotaciones?: Anotacion[];
  velocidad?: number; // clip: playbackRate
};
type Estilo = {
  tinta?: string; // color del titular y de la mancha
  papel?: string; // fondo y halo del titular
  acento?: string; // único color de la casa: *palabras* del titular, anotaciones, sello, karaoke
  textura?: number; // 0–1, intensidad del papel
  hervor?: number; // px de desplazamiento del trazo (0 = apagado)
  fps_animacion?: number; // frecuencia del hervor (12 = «a doses»)
  subtitulos?: boolean;
};
type Cierre = { texto?: string; imagen?: string | null; inicio: number; dur: number };
type Props = PropsBase & {
  tomas?: Toma[];
  voz?: string;
  musica?: string;
  musica_vol?: number;
  estilo?: Estilo;
  cierre?: Cierre;
};

// Colores de la casa (los mismos que config.json > ilustrado.estilo_casa; ilustrar.py siempre los manda).
const TINTA = '#26262b';
const PAPEL = '#f3ead6';
const ACENTO = '#c8452d';

export const meta: Meta = {
  fps: 30,
  ancho: 1080,
  alto: 1920,
  duracion: 4,
  props: { tomas: [], estilo: {} },
};

const CURVAS = {
  suave: Easing.inOut(Easing.cubic),
  lineal: Easing.linear,
  entrada: Easing.out(Easing.cubic),
  salida: Easing.in(Easing.cubic),
};
const lerp = (p: Par | undefined, k: number, def: number) => (p ? p[0] + (p[1] - p[0]) * k : def);

/** Avance 0–1 de la cámara dentro de la toma. */
const progreso = (frame: number, dur: number, curva: Camara['curva']) =>
  CURVAS[curva ?? 'suave'](Math.min(1, Math.max(0, frame / Math.max(1, dur - 1))));

const Imagen: React.FC<{ src: string }> = ({ src }) =>
  /\.(mp4|mov|webm)$/i.test(src) ? (
    <OffthreadVideo src={staticFile(src)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
  ) : (
    <Img src={staticFile(src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
  );

/** Azar determinista (mulberry32): mismas semillas → mismos trazos en cada render. */
const azar = (semilla: number) => {
  let a = semilla >>> 0 || 1;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const VIDEO = { width: '100%', height: '100%', objectFit: 'cover' } as const;

/** Entintado: el MP4 del revelado tapa la toma hasta su último cuadro (que es la propia ilustración). */
const CapaEntrada: React.FC<{ e: Entrada }> = ({ e }) => {
  const { fps } = useVideoConfig();
  return (
    <Sequence durationInFrames={Math.max(1, Math.round(e.dur * fps))} layout="none" name="entintado">
      <AbsoluteFill>
        <OffthreadVideo src={staticFile(e.src)} muted style={VIDEO} />
      </AbsoluteFill>
    </Sequence>
  );
};

const TomaVista: React.FC<{ t: Toma; dur: number; estilo: Estilo }> = ({ t, dur, estilo }) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();
  const c = t.camara ?? {};
  const k = progreso(frame, dur, c.curva);
  const escala = lerp(c.escala, k, 1);
  const x = lerp(c.x, k, 0) * width; // x, y en fracción del ancho
  const y = lerp(c.y, k, 0) * width;
  const rot = lerp(c.rot, k, 0);
  const transform = `translate(${x}px, ${y}px) scale(${escala}) rotate(${rot}deg)`;
  const fEnt = t.entrada ? Math.round(t.entrada.dur * fps) : 0;
  const notas = t.anotaciones?.length ? <Anotaciones lista={t.anotaciones} estilo={estilo} /> : null;
  if (t.tipo === 'clip') {
    // Con entrada: se dibuja la ilustración, queda quieta y el clip (que arranca en ese mismo cuadro) entra encima en 6 cuadros.
    const aparicion = fEnt ? interpolate(frame, [fEnt, fEnt + 6], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
    return (
      <AbsoluteFill style={{ transform }}>
        {fEnt > 0 && t.imagen && frame < fEnt + 8 ? <Imagen src={t.imagen} /> : null}
        <Sequence from={fEnt} layout="none" name="clip">
          <AbsoluteFill style={{ opacity: aparicion }}>
            <OffthreadVideo src={staticFile(t.src ?? '')} muted playbackRate={t.velocidad ?? 1} style={VIDEO} />
          </AbsoluteFill>
        </Sequence>
        {t.entrada ? <CapaEntrada e={t.entrada} /> : null}
        {notas}
      </AbsoluteFill>
    );
  }
  if (t.tipo === 'parallax' && t.capas?.length) {
    // Cada capa se mueve y escala en proporción a su cercanía: el fondo casi quieto, el primer plano al doble.
    return (
      <AbsoluteFill style={{ overflow: 'hidden' }}>
        {t.capas.map((capa, i) => {
          const f = 0.35 + 1.3 * capa.z;
          const s = 1 + (escala - 1) * f + 0.06 * capa.z; // margen extra para que el primer plano no deje bordes
          return (
            <AbsoluteFill key={i} style={{ transform: `translate(${x * f}px, ${y * f}px) scale(${s}) rotate(${rot * f}deg)` }}>
              <Img src={staticFile(capa.src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </AbsoluteFill>
          );
        })}
        {notas ? <AbsoluteFill style={{ transform }}>{notas}</AbsoluteFill> : null}
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform }}>
        <Imagen src={t.src ?? ''} />
        {t.entrada ? <CapaEntrada e={t.entrada} /> : null}
        {notas}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ───────────────────────────────────────────── anotaciones a mano
type Pt = [number, number];
const trazo = (pts: Pt[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');

/** Trayectoria de cada anotación en px (con temblor determinista). Varios subtrazos se dibujan en orden. */
const rutaAnotacion = (a: Anotacion, W: number, H: number): string => {
  const r = azar(a.semilla ?? 5);
  const cx = a.x * W;
  const cy = a.y * H;
  const rx = ((a.w ?? 0.32) * W) / 2;
  const ry = ((a.h ?? 0.12) * H) / 2;
  if (a.tipo === 'circulo') {
    // Óvalo de una sola pasada que se pasa de largo ~13 % y no cierra: así lo dibuja una mano.
    const t0 = -Math.PI * (0.55 + 0.15 * r());
    const fase = r() * 6.28;
    const pts: Pt[] = [];
    for (let i = 0; i <= 64; i++) {
      const u = i / 64;
      const th = t0 + u * Math.PI * 2 * 1.13;
      const f = 0.95 + 0.09 * u + 0.025 * Math.sin(3 * th + fase);
      pts.push([cx + Math.cos(th) * rx * f, cy + Math.sin(th) * ry * f]);
    }
    return trazo(pts);
  }
  if (a.tipo === 'subrayado') {
    const caida = (r() - 0.5) * 0.06 * rx;
    const pts: Pt[] = [];
    for (let i = 0; i <= 24; i++) {
      const u = i / 24;
      pts.push([cx - rx + 2 * rx * u, cy + caida * u + Math.sin(Math.PI * u) * ry * 0.12 + Math.sin(u * 9 + r()) * 1.2]);
    }
    const [fx, fy] = pts[pts.length - 1];
    const vuelta: Pt[] = [[fx, fy], [fx - rx * 0.18, fy + ry * 0.35], [fx - rx * 0.42, fy + ry * 0.42]];
    return `${trazo(pts)} ${trazo(vuelta)}`;
  }
  // flecha: tallo curvo desde `desde` hasta la punta (x, y) y dos trazos de cabeza
  const [dx, dy] = a.desde ?? [Math.min(0.92, a.x + 0.16), Math.min(0.92, a.y + 0.14)];
  const sx = dx * W;
  const sy = dy * H;
  const largo = Math.hypot(cx - sx, cy - sy) || 1;
  const signo = r() < 0.5 ? -1 : 1;
  const qx = (sx + cx) / 2 + (-(cy - sy) / largo) * largo * 0.18 * signo;
  const qy = (sy + cy) / 2 + ((cx - sx) / largo) * largo * 0.18 * signo;
  const pts: Pt[] = [];
  for (let i = 0; i <= 28; i++) {
    const u = i / 28;
    pts.push([(1 - u) ** 2 * sx + 2 * (1 - u) * u * qx + u * u * cx, (1 - u) ** 2 * sy + 2 * (1 - u) * u * qy + u * u * cy]);
  }
  const ang = Math.atan2(cy - qy, cx - qx);
  const lc = Math.min(W, H) * 0.05;
  const cabeza = (d: number): Pt[] => [[cx, cy], [cx - Math.cos(ang + d) * lc, cy - Math.sin(ang + d) * lc]];
  return `${trazo(pts)} ${trazo(cabeza(0.5))} ${trazo(cabeza(-0.45))}`;
};

const Anotaciones: React.FC<{ lista: Anotacion[]; estilo: Estilo }> = ({ lista, estilo }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const paso = fps / (estilo.fps_animacion ?? 12);
  const fq = Math.floor(frame / paso) * paso; // se dibuja «a doses», como el hervor
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <svg width={width} height={height}>
        {lista.map((a, i) => {
          const k = Easing.out(Easing.quad)(clamp01((fq - a.en * fps) / ((a.dur ?? 0.5) * fps)));
          if (k <= 0) return null;
          return (
            <path key={i} d={rutaAnotacion(a, width, height)} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - k}
              fill="none" stroke={a.color ?? estilo.acento ?? ACENTO} strokeWidth={Math.min(width, height) * 0.012}
              strokeLinecap="round" strokeLinejoin="round" opacity={0.95} />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

// ───────────────────────────────────────────── transición «mancha»
/** Contorno de mancha de tinta: radio con tres armónicos (borde irregular) y, opcional, gotas satélite. */
const rutaMancha = (cx: number, cy: number, r: number, semilla: number, k: number, gotas: boolean) => {
  if (r <= 1) return 'M0 0Z';
  const rn = azar(semilla);
  const f1 = rn() * 6.28;
  const f2 = rn() * 6.28;
  const f3 = rn() * 6.28;
  const n = 64;
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const th = (i / n) * Math.PI * 2;
    const rr = r * (1 + 0.07 * Math.sin(3 * th + f1 + k * 0.6) + 0.045 * Math.sin(5 * th + f2) + 0.025 * Math.sin(11 * th + f3 - k));
    pts.push([cx + Math.cos(th) * rr, cy + Math.sin(th) * rr]);
  }
  const medio = (a: Pt, b: Pt): Pt => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const m0 = medio(pts[n - 1], pts[0]);
  let d = `M${m0[0].toFixed(1)} ${m0[1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const m = medio(pts[i], pts[(i + 1) % n]);
    d += ` Q${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)} ${m[0].toFixed(1)} ${m[1].toFixed(1)}`;
  }
  d += ' Z';
  if (gotas) {
    for (let g = 0; g < 7; g++) {
      const a = rn() * 6.28;
      const dist = r * (1.1 + 0.3 * rn());
      const gr = r * (0.03 + 0.045 * rn()) + 3;
      const gx = cx + Math.cos(a) * dist;
      const gy = cy + Math.sin(a) * dist;
      d += ` M${(gx + gr).toFixed(1)} ${gy.toFixed(1)} A${gr.toFixed(1)} ${gr.toFixed(1)} 0 1 0 ${(gx - gr).toFixed(1)} ${gy.toFixed(1)}` +
        ` A${gr.toFixed(1)} ${gr.toFixed(1)} 0 1 0 ${(gx + gr).toFixed(1)} ${gy.toFixed(1)} Z`;
    }
  }
  return d;
};

/** La gota de tinta cae y se expande; su frente oscuro va por delante y dentro aparece la toma nueva. */
const Mancha: React.FC<{ frames: number; tr: Transicion; tinta: string; children: React.ReactNode }> = ({ frames, tr, tinta, children }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  if (frame >= frames) return <AbsoluteFill>{children}</AbsoluteFill>;
  // La gota cae (arranque rápido) y se frena al empapar el papel; la toma nueva va un 15 % por detrás del frente de tinta.
  const k = Easing.out(Easing.quad)(clamp01(frame / frames));
  const cx = (tr.x ?? 0.5) * width;
  const cy = (tr.y ?? 0.45) * height;
  const R = Math.hypot(Math.max(cx, width - cx), Math.max(cy, height - cy)) * 1.12;
  const semilla = tr.semilla ?? 7;
  const rTinta = R * Math.min(1.05, 0.04 + k);
  const rToma = R * Math.max(0, k * 1.18 - 0.18);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ backgroundColor: tinta, clipPath: `path('${rutaMancha(cx, cy, rTinta, semilla, k, k < 0.85)}')` }} />
      <AbsoluteFill style={{ clipPath: `path('${rutaMancha(cx, cy, rToma, semilla + 1, k, false)}')` }}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};

// ───────────────────────────────────────────── sello de cierre
const Sello: React.FC<{ c: Cierre; estilo: Estilo }> = ({ c, estilo }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const D = Math.min(width, height) * 0.52;
  const acento = estilo.acento ?? ACENTO;
  const papel = estilo.papel ?? PAPEL;
  // Cae desde arriba (1.7×) y golpea en el cuadro 6; rebota apenas y se asienta.
  const caida = interpolate(frame, [0, 6], [1.7, 0.94], { extrapolateRight: 'clamp', easing: Easing.in(Easing.quad) });
  const asiento = spring({ frame: frame - 6, fps, config: { damping: 9, stiffness: 220 } });
  const escala = frame < 6 ? caida : 0.94 + 0.06 * asiento;
  const opacidad = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: 'clamp' });
  const velo = interpolate(frame, [0, 8], [0, 0.35], { extrapolateRight: 'clamp' });
  const texto = (c.texto ?? '').toUpperCase();
  const tam = Math.min(D * 0.26, (D * 1.45) / Math.max(3, texto.length));
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
      <AbsoluteFill style={{ backgroundColor: papel, opacity: velo }} />
      <svg width={0} height={0} style={{ position: 'absolute' }}>
        <filter id="ilu-goma">
          <feTurbulence type="fractalNoise" baseFrequency="0.6" numOctaves={2} seed={3} result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -7 0 0 0 4.4" result="m" />
          <feComposite in="SourceGraphic" in2="m" operator="in" />
        </filter>
      </svg>
      <div style={{ width: D * 1.12, height: D * 1.12, borderRadius: '50%', backgroundColor: papel, opacity: 0.9 * opacidad, position: 'absolute' }} />
      <div
        style={{
          width: D,
          height: D,
          borderRadius: '50%',
          border: `${D * 0.035}px solid ${acento}`,
          boxShadow: `inset 0 0 0 ${D * 0.03}px ${papel}, inset 0 0 0 ${D * 0.042}px ${acento}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transform: `scale(${escala}) rotate(-8deg)`,
          opacity: opacidad,
          filter: 'url(#ilu-goma)',
          position: 'absolute',
        }}
      >
        {c.imagen ? (
          <Img src={staticFile(c.imagen)} style={{ width: '62%', height: '62%', objectFit: 'contain' }} />
        ) : (
          <span style={{ fontFamily: FUENTE, fontWeight: 800, fontSize: tam, color: acento, letterSpacing: '0.04em', textAlign: 'center', lineHeight: 1 }}>
            {texto}
          </span>
        )}
      </div>
    </AbsoluteFill>
  );
};

/** Titular palabra por palabra: cada palabra entra desde un lado con muelle y desenfoque horizontal según su velocidad. */
const TituloCinetico: React.FC<{ t: Titulo; dur: number; estilo: Estilo; idBase: string }> = ({ t, dur, estilo, idBase }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const vertical = height > width;
  // *palabras* entre asteriscos (una o varias seguidas) van en el color de acento.
  let enAcento = false;
  const marcadas = t.texto.split(/\s+/).filter(Boolean).map((w) => {
    const abre = w.startsWith('*');
    const acento = enAcento || abre;
    enAcento = (enAcento || abre) && !(w.endsWith('*') && (w.length > 1 || !abre));
    return { w: w.replace(/^\*|\*$/g, ''), acento };
  });
  const palabras = marcadas.map((m) => m.w);
  const ini = Math.round((t.en ?? 0.15) * fps);
  const fin = t.hasta !== undefined ? Math.round(t.hasta * fps) : dur;
  const tam = t.tam ?? (vertical ? 92 : 104);
  const salida = interpolate(frame, [fin - 8, fin], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const pos = t.pos ?? 'arriba';
  const tinta = estilo.tinta ?? TINTA;
  const papel = estilo.papel ?? PAPEL;
  const acento = estilo.acento ?? ACENTO;
  return (
    <AbsoluteFill
      style={{
        justifyContent: pos === 'arriba' ? 'flex-start' : pos === 'abajo' ? 'flex-end' : 'center',
        alignItems: 'center',
        padding: vertical ? '15% 7% 22%' : '7% 8%',
        opacity: salida,
      }}
    >
      <svg width={0} height={0} style={{ position: 'absolute' }}>
        {palabras.map((_, i) => {
          const f = frame - ini - i * 4;
          const v = spring({ frame: f, fps, config: { damping: 16, stiffness: 170 } });
          const v2 = spring({ frame: f - 1, fps, config: { damping: 16, stiffness: 170 } });
          const blur = Math.min(26, Math.abs(v - v2) * 260); // proporcional a la velocidad
          return (
            <filter key={i} id={`${idBase}-mb${i}`} x="-50%" y="-20%" width="200%" height="140%">
              <feGaussianBlur stdDeviation={`${blur.toFixed(2)} 0`} />
            </filter>
          );
        })}
      </svg>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: `0 ${tam * 0.28}px`, maxWidth: '100%' }}>
        {palabras.map((w, i) => {
          const f = frame - ini - i * 4;
          const v = spring({ frame: f, fps, config: { damping: 16, stiffness: 170 } });
          const lado = i % 2 === 0 ? -1 : 1;
          return (
            <span
              key={i}
              style={{
                fontFamily: FUENTE,
                fontWeight: 800,
                fontSize: tam,
                lineHeight: 1.04,
                letterSpacing: '-0.01em',
                textTransform: 'uppercase',
                color: marcadas[i].acento ? acento : tinta,
                opacity: Math.min(1, v * 1.4),
                transform: `translateX(${(1 - v) * lado * 140}px)`,
                filter: `url(#${idBase}-mb${i})`,
                // Contorno de papel por detrás del relleno: legible sobre cielo oscuro y sobre papel claro.
                WebkitTextStroke: `${(tam * 0.1).toFixed(1)}px ${papel}`,
                paintOrder: 'stroke fill',
                textShadow: `0 ${tam * 0.04}px ${tam * 0.12}px rgba(0,0,0,.25)`,
                whiteSpace: 'nowrap',
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Ruido determinista para el hervor: semilla nueva cada 1/fps_animacion s. */
const Filtros: React.FC<{ hervor: number; semilla: number; textura: number }> = ({ hervor, semilla, textura }) => (
  <svg width={0} height={0} style={{ position: 'absolute' }}>
    <filter id="ilu-hervor" x="-2%" y="-2%" width="104%" height="104%">
      <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves={2} seed={semilla} result="ruido" />
      <feDisplacementMap in="SourceGraphic" in2="ruido" scale={hervor} xChannelSelector="R" yChannelSelector="G" />
    </filter>
    <filter id="ilu-papel">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={3} seed={7} result="grano" />
      <feColorMatrix in="grano" type="saturate" values="0" result="gris" />
      <feComponentTransfer in="gris">
        <feFuncA type="linear" slope={0} intercept={1} />
        <feFuncR type="linear" slope={0.5 * textura} intercept={1 - 0.5 * textura} />
        <feFuncG type="linear" slope={0.5 * textura} intercept={1 - 0.5 * textura} />
        <feFuncB type="linear" slope={0.5 * textura} intercept={1 - 0.48 * textura} />
      </feComponentTransfer>
    </filter>
  </svg>
);

export const Composicion: React.FC<Props> = (p) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const estilo = p.estilo ?? {};
  const tomas = p.tomas ?? [];
  const hervor = estilo.hervor ?? 2.2;
  const textura = estilo.textura ?? 0.35;
  const fa = estilo.fps_animacion ?? 12;
  const semilla = Math.floor((frame / fps) * fa) % 97;
  const vertical = height > width;
  return (
    <AbsoluteFill style={{ backgroundColor: estilo.papel ?? PAPEL }}>
      <Filtros hervor={hervor} semilla={semilla} textura={textura} />
      {p.voz ? <Audio src={staticFile(p.voz)} /> : null}
      {p.musica ? <Audio src={staticFile(p.musica)} volume={p.musica_vol ?? 0.12} /> : null}
      <AbsoluteFill style={{ filter: hervor > 0 ? 'url(#ilu-hervor)' : undefined }}>
        {tomas.map((t) => {
          const fundido = Math.round((t.fundido ?? 0) * fps);
          const desde = Math.max(0, Math.round(t.inicio * fps) - fundido);
          const dur = Math.max(1, Math.round(t.fin * fps) - desde);
          return (
            <Sequence key={t.id} from={desde} durationInFrames={dur} name={t.id}>
              {t.transicion?.tipo === 'mancha' && fundido > 0 ? (
                <Mancha frames={fundido} tr={t.transicion} tinta={estilo.tinta ?? TINTA}>
                  <TomaVista t={t} dur={dur} estilo={estilo} />
                </Mancha>
              ) : (
                <Fundido entrada={fundido}>
                  <TomaVista t={t} dur={dur} estilo={estilo} />
                </Fundido>
              )}
            </Sequence>
          );
        })}
      </AbsoluteFill>
      {textura > 0 ? (
        <AbsoluteFill style={{ mixBlendMode: 'multiply', pointerEvents: 'none' }}>
          <svg width={width} height={height}>
            <rect width="100%" height="100%" filter="url(#ilu-papel)" />
          </svg>
        </AbsoluteFill>
      ) : null}
      {tomas.map((t) => {
        const desde = Math.round(t.inicio * fps);
        const dur = Math.max(1, Math.round(t.fin * fps) - desde);
        return (
          <Sequence key={`txt-${t.id}`} from={desde} durationInFrames={dur} name={`texto ${t.id}`}>
            {t.titulo?.texto ? <TituloCinetico t={t.titulo} dur={dur} estilo={estilo} idBase={`t-${t.id}`} /> : null}
            {estilo.subtitulos && t.palabras?.length ? (
              <SubtituloToma palabras={t.palabras} vertical={vertical} acento={estilo.acento ?? ACENTO} />
            ) : null}
          </Sequence>
        );
      })}
      {p.cierre && (p.cierre.texto || p.cierre.imagen) ? (
        <Sequence from={Math.round(p.cierre.inicio * fps)} durationInFrames={Math.max(1, Math.round(p.cierre.dur * fps))} name="sello">
          <Sello c={p.cierre} estilo={estilo} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};

const Fundido: React.FC<{ entrada: number; children: React.ReactNode }> = ({ entrada, children }) => {
  const frame = useCurrentFrame();
  const o = entrada > 0 ? interpolate(frame, [0, entrada], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

const SubtituloToma: React.FC<{ palabras: Palabra[]; vertical: boolean; acento: string }> = ({ palabras, vertical, acento }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Karaoke
      palabras={palabras}
      frame={frame}
      fps={fps}
      vertical={vertical}
      colores={{ activo: acento, resto: '#ffffff', borde: '#1d1d22', fondo: 'rgba(25,22,18,.78)', brillo: `${acento}73` }}
    />
  );
};
