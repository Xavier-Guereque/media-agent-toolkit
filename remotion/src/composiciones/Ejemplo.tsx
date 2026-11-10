// Ejemplo de oro: plantilla de `python3 scripts/remotion.py nuevo` y humo del motor.
// Reglas de la casa: todo depende de useCurrentFrame() (nada de Math.random, timers ni CSS animations);
// los recursos del proyecto (recursos/) se leen con staticFile() gracias a --public-dir.
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type { Meta, PropsBase } from '../lib/props';

type Props = PropsBase & {
  titulo?: string;
  subtitulo?: string;
  acento?: string;
  fondo?: string;
  audio?: string; // ruta relativa a recursos/ del proyecto (p. ej. "voz.wav"); opcional
};

export const meta: Meta = {
  fps: 30,
  ancho: 1080,
  alto: 1920,
  duracion: 3,
  props: {
    titulo: 'Composición libre',
    subtitulo: 'React → MP4 con Remotion',
    acento: '#3A74CD',
    fondo: '#0F1115',
  },
};

export const Composicion: React.FC<Props> = (p) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width } = useVideoConfig();
  const entrada = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });
  const subtitulo = interpolate(frame, [10, 25], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const barra = interpolate(frame, [0, durationInFrames - 1], [0, width], { extrapolateRight: 'clamp' });
  const salida = interpolate(frame, [durationInFrames - 12, durationInFrames - 1], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ backgroundColor: p.fondo ?? '#0F1115', fontFamily: 'Helvetica, Arial, sans-serif' }}>
      {p.audio ? <Audio src={staticFile(p.audio)} /> : null}
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', padding: 120, opacity: salida }}>
        <div
          style={{
            color: 'white',
            fontSize: 112,
            fontWeight: 700,
            textAlign: 'center',
            lineHeight: 1.05,
            transform: `translateY(${(1 - entrada) * 80}px) scale(${0.9 + entrada * 0.1})`,
            opacity: entrada,
          }}
        >
          {p.titulo}
        </div>
        <div style={{ color: p.acento ?? '#3A74CD', fontSize: 52, marginTop: 40, opacity: subtitulo }}>
          {p.subtitulo}
        </div>
      </AbsoluteFill>
      <div style={{ position: 'absolute', left: 0, bottom: 0, height: 24, width: barra, backgroundColor: p.acento ?? '#3A74CD' }} />
    </AbsoluteFill>
  );
};
