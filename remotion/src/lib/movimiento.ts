// Curvas de movimiento de la casa para composiciones libres (motion graphics).
//
// Todo depende solo de `frame` y `fps` (nada de reloj ni azar): el render es determinista.
// Verificadas en los videos animados de referencia ([[Lecciones-2026-11-06-video-animado-syscom-ia]]).
import type { CSSProperties } from 'react';
import { Easing, interpolate, spring } from 'remotion';

/** Muelle suave: amortiguación alta, así nada rebota de golpe. Devuelve 0→1 desde `atraso` (en cuadros). */
export const muelle = (frame: number, fps: number, atraso = 0, amort = 22, rig = 78): number =>
  spring({ frame: Math.max(0, frame - atraso), fps, config: { damping: amort, stiffness: rig, mass: 0.85 } });

/** Rampa 0→1 de `dur` cuadros con salida cúbica, saturada en ambos extremos. */
export const soltar = (frame: number, fps: number, atraso = 0, dur = 12): number =>
  interpolate(frame - atraso, [0, dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

/** Entrada estándar: sube `px` y aparece. */
export const entra = (frame: number, fps: number, atraso = 0, px = 26): CSSProperties => {
  const p = muelle(frame, fps, atraso);
  return { opacity: Math.min(1, p * 1.15), transform: `translateY(${(1 - p) * px}px)` };
};

/** Deslizamiento lateral de `px` (negativo = desde la izquierda). */
export const desliza = (frame: number, fps: number, atraso = 0, px = 40): CSSProperties => {
  const p = muelle(frame, fps, atraso);
  return { opacity: Math.min(1, p * 1.15), transform: `translateX(${(1 - p) * px}px)` };
};
