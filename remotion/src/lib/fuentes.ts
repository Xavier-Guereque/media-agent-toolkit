// Fuentes de la casa para motion graphics: Sora (titulares) y Figtree (UI), de Google Fonts vía @remotion/google-fonts
// (se empaquetan con el render: no dependen de lo instalado en la máquina).
//
// Pesos cargados: Sora 600/700/800 y Figtree 500/600/700 (los verificados en los videos animados de referencia). Un peso
// que no esté aquí lo sustituye el navegador por el más cercano: agrégalo antes de usarlo.
import { loadFont as cargarSora } from '@remotion/google-fonts/Sora';
import { loadFont as cargarFigtree } from '@remotion/google-fonts/Figtree';

export const SORA = cargarSora('normal', { weights: ['600', '700', '800'], subsets: ['latin', 'latin-ext'] }).fontFamily;
export const FIGTREE = cargarFigtree('normal', { weights: ['500', '600', '700'], subsets: ['latin', 'latin-ext'] }).fontFamily;

/** Pila para titulares, subtítulos y textos de apoyo. */
export const FUENTE = `'${SORA}','${FIGTREE}',system-ui,-apple-system,'Helvetica Neue',sans-serif`;
/** Pila para UI simulada (botones, tarjetas, menús). */
export const FUENTE_UI = `'${FIGTREE}','${SORA}',system-ui,-apple-system,'Helvetica Neue',sans-serif`;
