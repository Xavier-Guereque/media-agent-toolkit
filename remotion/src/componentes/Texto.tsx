// Titular y texto de apoyo animados para motion graphics (versión base; los usan las composiciones de proyecto).
//
//   <Titular texto="Tu *agente* de compras" frame={frame} fps={fps} tam={76} vertical={vertical} />
//   <Apoyo texto="Pregunta, compara y pide en un mismo lugar." frame={frame} fps={fps} tam={30} />
//
// Las palabras entre *asteriscos* se resaltan. Cada palabra del titular entra con su propio muelle (3.2 cuadros
// de desfase), y el contenedor es flex con `flexWrap`, así el titular se acomoda en vertical sin desbordarse.
import React from 'react';
import { FUENTE } from '../lib/fuentes';
import { segmentos } from '../lib/karaoke';
import { muelle, soltar } from '../lib/movimiento';

export type ColoresTitular = { texto: string; realce: string };
export const COLORES_TITULAR: ColoresTitular = { texto: '#f2f4f8', realce: '#9db6f7' };

export const Titular: React.FC<{
  texto: string;
  frame: number;
  fps: number;
  tam: number;
  vertical: boolean;
  /** Ancho del bloque (por defecto 100% en vertical, 96% en horizontal). */
  ancho?: string;
  colores?: ColoresTitular;
  fuente?: string;
}> = ({ texto, frame, fps, tam, vertical, ancho, colores = COLORES_TITULAR, fuente = FUENTE }) => {
  let k = 0;
  return (
    <div
      style={{
        fontFamily: fuente,
        fontWeight: 800,
        fontSize: tam,
        lineHeight: 1.12,
        letterSpacing: -0.7,
        width: ancho ?? (vertical ? '100%' : '96%'),
        display: 'flex',
        flexWrap: 'wrap',
      }}
    >
      {segmentos(texto).map((s, si) => (
        <React.Fragment key={si}>
          {s.t
            .split(' ')
            .filter(Boolean)
            .map((pal, pi) => {
              const p = muelle(frame, fps, k++ * 3.2, 20, 74);
              return (
                <span
                  key={pi}
                  style={{
                    display: 'inline-block',
                    whiteSpace: 'pre',
                    opacity: Math.min(1, p * 1.2),
                    transform: `translateY(${(1 - p) * tam * 0.4}px)`,
                    color: s.f ? colores.realce : colores.texto,
                  }}
                >
                  {pal}{' '}
                </span>
              );
            })}
        </React.Fragment>
      ))}
    </div>
  );
};

/** Texto de apoyo bajo el titular: aparece en el cuadro 22 de la escena con una rampa de 16. */
export const Apoyo: React.FC<{ texto?: string; frame: number; fps: number; tam: number; color?: string; fuente?: string }> = ({
  texto,
  frame,
  fps,
  tam,
  color = '#a7b0c0',
  fuente = FUENTE,
}) => {
  if (!texto) return null;
  const p = soltar(frame, fps, 22, 16);
  return (
    <div
      style={{
        fontFamily: fuente,
        fontSize: tam,
        lineHeight: 1.35,
        color,
        opacity: p * 0.95,
        transform: `translateY(${(1 - p) * 14}px)`,
      }}
    >
      {texto}
    </div>
  );
};
