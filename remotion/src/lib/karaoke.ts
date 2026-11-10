// Lógica pura del subtítulo karaoke y del texto con realce (sin React, se prueba con node --test).
//
// Las palabras traen tiempos MEDIDOS sobre la voz real ({w, a, b} en segundos, de scripts/narrar.py →
// tiempos.json), nunca estimados: así el realce cae en la palabra que se oye.

export type Palabra = { w: string; a: number; b: number };
export type Bloque = { desde: number; hasta: number };

/** Trocea la narración en ORACIONES completas: corta en `.`, `!`, `?` o `…`, o si el bloque llega a `porFrase`
 *  palabras. Cada bloque se queda en pantalla todo el tiempo de su oración (el texto no cambia mientras se
 *  habla; solo se mueve el realce). */
export const frases = (palabras: Palabra[], porFrase: number): Bloque[] => {
  const out: Bloque[] = [];
  let ini = 0;
  palabras.forEach((p, i) => {
    const cierra = /[.!?…]$/.test(p.w) || i - ini + 1 >= porFrase || i === palabras.length - 1;
    if (cierra) {
      out.push({ desde: ini, hasta: i });
      ini = i + 1;
    }
  });
  return out;
};

/** Índice de la palabra que suena en `t`. En una pausa entre palabras se queda la ÚLTIMA QUE YA SONÓ (antes de la
 *  primera, la primera): así el subtítulo no salta a otra oración durante los silencios. (Hasta 2026-11 se devolvía
 *  la última palabra de la escena en cualquier hueco y el subtítulo parpadeaba a la oración final en cada pausa.) */
export const palabraActiva = (palabras: Palabra[], t: number): number => {
  const hallado = palabras.findIndex((p) => t >= p.a && t <= p.b);
  if (hallado >= 0) return hallado;
  let ultima = 0;
  palabras.forEach((p, i) => {
    if (p.a <= t) ultima = i;
  });
  return ultima;
};

/** Bloque (oración) que contiene la palabra `idx`. */
export const bloqueDe = (bloques: Bloque[], idx: number): Bloque => {
  for (const b of bloques) if (idx <= b.hasta) return b;
  return bloques[bloques.length - 1];
};

/** Parte un texto por *asteriscos*: lo marcado (`f: true`) se resalta. "Hola *mundo*" → [Hola ][mundo✓]. */
export const segmentos = (t: string): { t: string; f: boolean }[] => {
  const partes: { t: string; f: boolean }[] = [];
  t.split('*').forEach((trozo, i) => {
    if (!trozo) return;
    partes.push({ t: trozo, f: i % 2 === 1 });
  });
  return partes;
};
