// golden.mjs — regresión visual: cuadros del ejemplo de oro comparados por SSIM contra imágenes
// versionadas en pruebas/golden/. Se renderizan SIN el logo privado (wordmark de respaldo) para que
// cualquier copia del repo obtenga lo mismo y el logo nunca llegue a git.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { cargarCatalogo, cargarTema, temasDisponibles, validarSpec, RAIZ_MOTOR } from './catalogo.mjs';
import { planificar } from './planificador.mjs';
import { abrir } from './navegador.mjs';

export const DIR_GOLDEN = path.join(RAIZ_MOTOR, 'pruebas', 'golden');
const EJEMPLO = path.join(RAIZ_MOTOR, 'ejemplos', 'asistente-ia-cta-whatsapp', 'promo.json');

async function lineaDeOro() {
  const catalogo = cargarCatalogo();
  const tema = cargarTema('neutro');
  const { spec } = validarSpec(JSON.parse(fs.readFileSync(EJEMPLO, 'utf8')), { catalogo, tema, temas: temasDisponibles() });
  const { lt } = await planificar(spec, { tema, catalogo, slug: 'golden' });
  return lt;
}

// Un cuadro "asentado" por escena (último beat + 0.35 s), el mismo criterio de la QA.
function tiemposGolden(lt) {
  return lt.escenas.map((e) => {
    const fin = Math.max(...Object.values(e.pasos).map((b) => b.ini + b.dur), 0);
    return +Math.min(e.fin - e.salida - 0.12, e.ini + fin + 0.35).toFixed(3);
  });
}

function aJpg(png, destino) {
  const r = spawnSync('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-i', png, '-vf', 'scale=540:-1:flags=lanczos', '-q:v', '3', destino]);
  if (r.status !== 0) throw new Error(`ffmpeg: ${r.stderr}`);
}

function ssim(a, b) {
  const r = spawnSync('ffmpeg', ['-nostdin', '-hide_banner', '-i', a, '-i', b, '-lavfi', '[0:v][1:v]ssim', '-f', 'null', '-'], { encoding: 'utf8' });
  const m = /All:([\d.]+)/.exec(r.stderr || '');
  return m ? +m[1] : 0;
}

// actualizar=true reescribe las golden; si no, compara y devuelve [{nombre, t, ssim}].
export async function golden({ actualizar = false } = {}) {
  const lt = await lineaDeOro();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'promo-golden-'));
  const b = await abrir({ lt, proyecto: tmp, sinPrivado: true });
  const res = [];
  try {
    fs.mkdirSync(DIR_GOLDEN, { recursive: true });
    const tiempos = tiemposGolden(lt);
    for (let i = 0; i < tiempos.length; i++) {
      const nombre = `${String(i).padStart(2, '0')}_${lt.escenas[i].tipo}.jpg`;
      const png = path.join(tmp, `c${i}.png`);
      fs.writeFileSync(png, await b.cuadro(tiempos[i]));
      const jpg = path.join(tmp, nombre);
      aJpg(png, jpg);
      const ref = path.join(DIR_GOLDEN, nombre);
      if (actualizar || !fs.existsSync(ref)) {
        fs.copyFileSync(jpg, ref);
        res.push({ nombre, t: tiempos[i], ssim: 1, nuevo: true });
      } else {
        res.push({ nombre, t: tiempos[i], ssim: ssim(jpg, ref) });
      }
    }
  } finally {
    await b.cerrar();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  return res;
}
