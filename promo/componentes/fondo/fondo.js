// fondo — base oscura con dos resplandores laterales cuyo color sigue el tinte de la escena
// (medido en la referencia: glow izquierdo bajo ~64 % y derecho ~47 % de la altura).
// Deriva lenta y determinista para que el fondo no se vea congelado.

import { estilo } from '../../runtime/movimiento.js';

export function montar(raiz, ctx) {
  raiz.innerHTML = '<div class="fondo-brillo"></div><div class="fondo-vineta"></div>';
  const b = raiz.querySelector('.fondo-brillo');
  return {
    actualizar(t, tinte) {
      estilo(b, {
        '--ta': tinte.a,
        '--tb': tinte.b,
        '--dx': (2.6 * Math.sin(t * 0.31)).toFixed(3) + '%',
        '--dy': (2.2 * Math.sin(t * 0.23 + 1.3)).toFixed(3) + '%',
      });
    },
  };
}
