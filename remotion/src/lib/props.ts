// Contrato de props entre scripts/remotion.py y las composiciones.
//
// remotion.py escribe recursos/remotion/props.json = spec.props + {duracion, ancho, alto, fps} y lo pasa
// con --props; `desdeProps` convierte esos cuatro campos en la metadata de la composición, así el spec
// del proyecto manda sobre los valores por defecto del TSX (que solo sirven para el Studio sin props).
import type { ComponentType } from 'react';

export type PropsBase = {
  duracion: number; // segundos
  ancho: number;
  alto: number;
  fps: number;
  [k: string]: unknown;
};

export type Meta = {
  fps: number;
  ancho: number;
  alto: number;
  duracion: number;
  props?: Record<string, unknown>;
};

export type Entrada = {
  id: string;
  component: ComponentType<PropsBase>;
  meta: Meta;
};

export type MetadataCalculada = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
};

const num = (v: unknown, def: number): number => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : def;
};

// Pura (sin importar remotion) para poder probarla con `node --test` (type stripping de Node 22.18+).
export function metadataDesde(props: Partial<PropsBase>, meta: Meta): MetadataCalculada {
  const fps = num(props.fps, meta.fps);
  const duracion = num(props.duracion, meta.duracion);
  return {
    fps,
    width: Math.round(num(props.ancho, meta.ancho)),
    height: Math.round(num(props.alto, meta.alto)),
    durationInFrames: Math.max(1, Math.round(duracion * fps)),
  };
}

export const propsPorDefecto = (meta: Meta): PropsBase => ({
  duracion: meta.duracion,
  ancho: meta.ancho,
  alto: meta.alto,
  fps: meta.fps,
  ...(meta.props ?? {}),
});
