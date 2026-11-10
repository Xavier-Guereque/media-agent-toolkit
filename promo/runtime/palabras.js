// palabras.js — parseo puro de texto con *énfasis* (sin DOM; lo usan Node y el navegador).
//
// "AI para *PROs.*" → [{w:'AI',e:false},{w:'para',e:false},{w:'PROs.',e:true}]
// El énfasis puede abarcar varias palabras: "*muy importante* hoy".
// Las palabras se separan solo por espacios normales: el espacio duro (U+00A0) que pone el
// normalizador en "400 m²" mantiene juntas esas dos piezas (no se parten ni se animan por separado).

export function parsearEnfasis(s) {
  const out = [];
  let dentro = false;
  for (const tok of String(s).split(/ +/)) {
    if (!tok) continue;
    let w = tok;
    let e = dentro;
    // Apertura con puntuación antes ("“*texto", "¿*algo") y cierre con puntuación después ("*texto*,").
    const ab = /^([“«(¿¡"']*)\*(.*)$/.exec(w);
    if (ab) {
      w = ab[1] + ab[2];
      e = true;
      dentro = true;
    }
    const ci = /^(.*)\*([.,;:!?…”»)"']*)$/.exec(w);
    if (ci) {
      w = ci[1] + ci[2];
      e = true;
      dentro = false;
    }
    if (w) out.push({ w, e });
  }
  return out;
}

export const contarPalabras = (s) => parsearEnfasis(s).length;

// ¿Quedó un asterisco sin pareja? (el validador lo reporta: se vería el "*" en pantalla).
export const enfasisDesbalanceado = (s) => (String(s).match(/\*/g) || []).length % 2 === 1;
export const sinMarcas = (s) => String(s).replace(/\*/g, '');
