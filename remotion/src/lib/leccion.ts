// Lógica pura de la composición Leccion (sin remotion ni JSX) para probarla con `node --test`.
// Los tiempos ya vienen medidos por scripts/curso.py: aquí no se decide nada del guion.
export type Tema = {
  fondo: string; texto: string; tenue: string; acento: string; correcta: string; alerta: string;
  panel?: string; borde?: string; peligro?: string; glow?: string[]; // opcionales: los usa el tema oscuro `cine`
};
export type Cue = { ini: number; fin: number; lineas: string[] };
export type Imagen = { src: string; credito?: string; w?: number; h?: number; pie?: string | null };
export type Elemento = {
  t: number; // segundo (de la lección) en que arranca el trazo: 100–200 ms antes de la palabra que lo nombra
  forma: 'caja' | 'circulo' | 'flecha' | 'linea' | 'texto';
  texto?: string;
  x: number; y: number; w?: number; h?: number; x2?: number; y2?: number; // % del escenario
};
export type Item = { t: number; texto: string; color?: string };
export type Escena = {
  id: string;
  tipo: string;
  inicio: number;
  fin: number;
  voz_inicio: number | null;
  pantalla?: Record<string, unknown>;
  imgs?: Imagen[];
};
export type Tramo = { from: number; dur: number };

export const FADE = 15; // cuadros: fundido de 0.5 s a 30 fps, default de la casa
export const TRAZO_S = 0.45; // stroke reveal de 300–600 ms (Metodologia-Cursos-Video)
export const ATENUADO = 0.35; // lo ya explicado baja a 0.3–0.4 para señalizar lo activo

export const TEMA_DEF: Tema = { fondo: '#FAFAF7', texto: '#1A1A1A', tenue: '#5A5A5A', acento: '#0072B2', correcta: '#007A5A', alerta: '#B34700' };

export function tramos(escenas: { inicio: number; fin: number }[], fps: number, fade = FADE): Tramo[] {
  return escenas.map((e, i) => {
    const from = Math.max(0, Math.round(e.inicio * fps) - (i > 0 ? fade : 0));
    return { from, dur: Math.max(1, Math.round(e.fin * fps) - from) };
  });
}

// `ini` inclusivo, `fin` exclusivo; null en los huecos.
export function cueEn(cues: Cue[], t: number): Cue | null {
  return cues.find((c) => t >= c.ini && t < c.fin) ?? null;
}

export function progreso(t0: number, ahora: number, dur = TRAZO_S): number {
  if (ahora <= t0) return 0;
  return Math.min(1, (ahora - t0) / dur);
}

// Índice del último elemento que ya empezó (-1 si ninguno): es el activo; los anteriores se atenúan.
export function elementoActivo(elementos: { t: number }[], ahora: number): number {
  let activo = -1;
  elementos.forEach((e, i) => {
    if (ahora >= e.t) activo = i;
  });
  return activo;
}

// Al terminar la voz todo recupera el contraste pleno: lo atenuado solo vale mientras se narra (WCAG 1.4.3).
export function opacidadElemento(i: number, activo: number, repaso = false): number {
  if (i > activo) return 0;
  if (repaso) return 1;
  return i === activo ? 1 : ATENUADO;
}

export function centro(e: Elemento): [number, number] {
  if (e.forma === 'flecha' || e.forma === 'linea') return [e.x2 ?? e.x, e.y2 ?? e.y];
  return [e.x + (e.w ?? 0) / 2, e.y + (e.h ?? 0) / 2];
}

// El puntero viaja al elemento activo DURANTE su trazo: se ve dibujar, no aparecer (Fiorella & Mayer 2016).
export function puntero(elementos: Elemento[], ahora: number): { x: number; y: number; visible: boolean } {
  const i = elementoActivo(elementos, ahora);
  if (i < 0) return { x: 50, y: 50, visible: false };
  const [x1, y1] = centro(elementos[i]);
  const [x0, y0] = i > 0 ? centro(elementos[i - 1]) : [x1, y1];
  const p = progreso(elementos[i].t, ahora);
  return { x: x0 + (x1 - x0) * p, y: y0 + (y1 - y0) * p, visible: true };
}

export const items = (v: unknown): Item[] =>
  Array.isArray(v)
    ? v.map((x, i) => {
        const o = (typeof x === 'object' && x ? x : { texto: String(x) }) as Record<string, unknown>;
        return { ...o, t: Number(o.t ?? i), texto: String(o.texto ?? '') };
      })
    : [];

export const elementos = (v: unknown): Elemento[] => (Array.isArray(v) ? (v as Elemento[]).filter((e) => e && typeof e.t === 'number') : []);
export const texto = (v: unknown, d = ''): string => (typeof v === 'string' ? v : d);
export const textos = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
