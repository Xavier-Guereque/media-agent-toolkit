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
type Toma = {
  id: string;
  inicio: number;
  fin: number;
  tipo: 'imagen' | 'parallax' | 'clip';
  src?: string;
  capas?: Capa[];
  camara?: Camara;
  titulo?: Titulo;
  palabras?: Palabra[];
  fundido?: number; // s de fundido cruzado con la toma anterior
  velocidad?: number; // clip: playbackRate
};
type Estilo = {
  tinta?: string; // color del titular
  papel?: string; // fondo y halo del titular
  textura?: number; // 0–1, intensidad del papel
  hervor?: number; // px de desplazamiento del trazo (0 = apagado)
  fps_animacion?: number; // frecuencia del hervor (12 = «a doses»)
  subtitulos?: boolean;
};
type Props = PropsBase & { tomas?: Toma[]; voz?: string; musica?: string; musica_vol?: number; estilo?: Estilo };

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

const TomaVista: React.FC<{ t: Toma; dur: number }> = ({ t, dur }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const c = t.camara ?? {};
  const k = progreso(frame, dur, c.curva);
  const escala = lerp(c.escala, k, 1);
  const x = lerp(c.x, k, 0) * width; // x, y en fracción del ancho
  const y = lerp(c.y, k, 0) * width;
  const rot = lerp(c.rot, k, 0);
  if (t.tipo === 'clip') {
    return (
      <AbsoluteFill style={{ transform: `translate(${x}px, ${y}px) scale(${escala}) rotate(${rot}deg)` }}>
        <OffthreadVideo src={staticFile(t.src ?? '')} muted playbackRate={t.velocidad ?? 1}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
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
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `translate(${x}px, ${y}px) scale(${escala}) rotate(${rot}deg)` }}>
        <Imagen src={t.src ?? ''} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** Titular palabra por palabra: cada palabra entra desde un lado con muelle y desenfoque horizontal según su velocidad. */
const TituloCinetico: React.FC<{ t: Titulo; dur: number; estilo: Estilo; idBase: string }> = ({ t, dur, estilo, idBase }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const vertical = height > width;
  const palabras = t.texto.split(/\s+/).filter(Boolean);
  const ini = Math.round((t.en ?? 0.15) * fps);
  const fin = t.hasta !== undefined ? Math.round(t.hasta * fps) : dur;
  const tam = t.tam ?? (vertical ? 92 : 104);
  const salida = interpolate(frame, [fin - 8, fin], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const pos = t.pos ?? 'arriba';
  const tinta = estilo.tinta ?? '#2b2b30';
  const papel = estilo.papel ?? '#f4ecd8';
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
                color: tinta,
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
    <AbsoluteFill style={{ backgroundColor: estilo.papel ?? '#f4ecd8' }}>
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
              <Fundido entrada={fundido}>
                <TomaVista t={t} dur={dur} />
              </Fundido>
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
            {estilo.subtitulos && t.palabras?.length ? <SubtituloToma palabras={t.palabras} vertical={vertical} /> : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const Fundido: React.FC<{ entrada: number; children: React.ReactNode }> = ({ entrada, children }) => {
  const frame = useCurrentFrame();
  const o = entrada > 0 ? interpolate(frame, [0, entrada], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

const SubtituloToma: React.FC<{ palabras: Palabra[]; vertical: boolean }> = ({ palabras, vertical }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Karaoke
      palabras={palabras}
      frame={frame}
      fps={fps}
      vertical={vertical}
      colores={{ activo: '#ffd25e', resto: '#ffffff', borde: '#1d1d22', fondo: 'rgba(25,22,18,.78)', brillo: 'rgba(255,210,94,.45)' }}
    />
  );
};
