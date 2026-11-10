import React from 'react';
import { Composition } from 'remotion';
import { COMPOSICIONES } from './composiciones';
import { metadataDesde, propsPorDefecto, type PropsBase } from './lib/props';

// Una <Composition> por entrada del registro. La metadata real (duración, tamaño, fps) sale de los
// props que manda scripts/remotion.py; los valores de `meta` solo alimentan el Studio sin props.
export const Root: React.FC = () => (
  <>
    {COMPOSICIONES.map((c) => (
      <Composition
        key={c.id}
        id={c.id}
        component={c.component}
        fps={c.meta.fps}
        width={c.meta.ancho}
        height={c.meta.alto}
        durationInFrames={Math.max(1, Math.round(c.meta.duracion * c.meta.fps))}
        defaultProps={propsPorDefecto(c.meta)}
        calculateMetadata={({ props }) => ({ ...metadataDesde(props as Partial<PropsBase>, c.meta), props })}
      />
    ))}
  </>
);
