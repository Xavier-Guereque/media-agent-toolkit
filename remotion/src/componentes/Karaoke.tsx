// Subtítulo karaoke por oración para motion graphics (versión base).
//
//   <Karaoke palabras={esc.palabras} frame={frame} fps={fps} vertical={vertical} />
//
// `palabras` son tiempos MEDIDOS relativos al inicio de la escena ({w, a, b} en s; ver lib/karaoke.ts). Se muestra
// la oración completa que se está diciendo y se realza la palabra que suena; la oración se queda fija hasta que
// arranca la siguiente (sin fundido de salida entre frases).
//
// Lecciones de layout ([[Lecciones-2026-11-06-video-animado-syscom-ia]]): el `padding` en % se resuelve contra el
// ANCHO del contenedor, por eso el margen inferior va en `bottom` y no en padding; `maxWidth: 100%` + `flexWrap`
// evitan que una oración larga se salga del cuadro en 9:16.
import React from 'react';
import { FUENTE } from '../lib/fuentes';
import { bloqueDe, frases, palabraActiva, type Palabra } from '../lib/karaoke';
import { soltar } from '../lib/movimiento';

export type ColoresKaraoke = { activo: string; resto: string; borde: string; fondo: string; brillo: string };
export const COLORES_KARAOKE: ColoresKaraoke = {
  activo: '#35c977',
  resto: '#c9d2e2',
  borde: '#282d36',
  fondo: 'rgba(6,8,12,.74)',
  brillo: 'rgba(53,201,119,.55)',
};

export const Karaoke: React.FC<{
  palabras?: Palabra[];
  frame: number;
  fps: number;
  vertical: boolean;
  /** Máximo de palabras por bloque si la oración no termina antes (por defecto 11 en vertical, 16 en horizontal). */
  porFrase?: number;
  /** Distancia al borde inferior (por defecto 6.5% en vertical, 5% en horizontal). */
  abajo?: string;
  /** Tamaño de letra (por defecto 27 en vertical, 30 en horizontal). */
  tam?: number;
  colores?: ColoresKaraoke;
  fuente?: string;
}> = ({ palabras, frame, fps, vertical, porFrase, abajo, tam, colores = COLORES_KARAOKE, fuente = FUENTE }) => {
  const t = frame / fps;
  if (!palabras || !palabras.length) return null;
  const idx = palabraActiva(palabras, t);
  const { desde, hasta } = bloqueDe(frases(palabras, porFrase ?? (vertical ? 11 : 16)), idx);
  const visibles = palabras.slice(desde, hasta + 1);
  const p = soltar(frame, fps, Math.max(0, Math.round(palabras[desde].a * fps) - 5), 9);
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: abajo ?? (vertical ? '6.5%' : '5%'),
        display: 'flex',
        justifyContent: 'center',
        padding: '0 4%',
        opacity: p,
      }}
    >
      <div
        style={{
          fontFamily: fuente,
          fontWeight: 600,
          fontSize: tam ?? (vertical ? 27 : 30),
          lineHeight: 1.32,
          maxWidth: '100%',
          boxSizing: 'border-box',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          columnGap: 9,
          background: colores.fondo,
          border: `1px solid ${colores.borde}`,
          borderRadius: 16,
          padding: vertical ? '14px 24px' : '11px 22px',
          textAlign: 'center',
          boxShadow: '0 18px 40px rgba(0,0,0,.5)',
        }}
      >
        {visibles.map((pal, i) => (
          <span
            key={i}
            style={{
              whiteSpace: 'pre',
              color: desde + i === idx ? colores.activo : colores.resto,
              textShadow: desde + i === idx ? `0 0 18px ${colores.brillo}` : 'none',
            }}
          >
            {pal.w}{' '}
          </span>
        ))}
      </div>
    </div>
  );
};
