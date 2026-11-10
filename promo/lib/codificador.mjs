// codificador.mjs — UN solo proceso ffmpeg que recibe PNG en orden por stdin.
//
// Un único codificador evita las costuras de render por trozos (IDR en cada unión, edit lists,
// semilla de grano reiniciada). Conversión RGB→YUV explícita en BT.709 (lo que asumen los
// reproductores en HD) y grano leve DESPUÉS de pasar a YUV (c0 = luma) para evitar bandas.

import { spawn } from 'node:child_process';

export function argsCodificador({ salida, fps, crf = 17, preset = 'slow', grano = 4, borrador = false, w, h }) {
  const vf = [];
  if (borrador) vf.push(`scale=${Math.round(w / 2)}:${Math.round(h / 2)}:flags=bicubic`);
  vf.push('scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int', 'format=yuv420p');
  if (grano > 0 && !borrador) vf.push(`noise=c0s=${grano}:c0f=t:c0_seed=7`);
  // Etiqueta explícita: sin setparams el encoder deja primaries/transfer como "unknown".
  vf.push('setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv');
  return [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    '-vf', vf.join(','),
    '-c:v', 'libx264', '-preset', borrador ? 'veryfast' : preset, '-crf', String(borrador ? 23 : crf),
    '-profile:v', 'high', '-pix_fmt', 'yuv420p',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
    '-movflags', '+faststart', '-an', salida,
  ];
}

export function crearCodificador(opciones) {
  const ff = spawn('ffmpeg', argsCodificador(opciones), { stdio: ['pipe', 'ignore', 'pipe'] });
  let err = '';
  let fallo = null;
  let cerrado = false;
  const pendientes = new Set(); // escrituras esperando 'drain': si ffmpeg muere, se rechazan
  const fallar = (e) => {
    fallo = fallo || e;
    for (const mal of pendientes) mal(new Error(`ffmpeg: ${err.trim() || fallo.message}`));
    pendientes.clear();
  };
  ff.stderr.on('data', (d) => (err = (err + d).slice(-4000)));
  ff.stdin.on('error', fallar); // EPIPE si ffmpeg murió: se reporta con su stderr
  const fin = new Promise((ok, mal) => {
    ff.on('error', (e) => {
      fallar(e);
      mal(e);
    });
    ff.on('close', (code) => {
      cerrado = true;
      if (code === 0) ok();
      else {
        const e = new Error(`ffmpeg salió con ${code}: ${err.trim()}`);
        fallar(e);
        mal(e);
      }
    });
  });
  fin.catch(() => {}); // el rechazo se reporta al escribir o al cerrar, no como "unhandled"
  return {
    escribir(buf) {
      if (fallo || cerrado) return Promise.reject(new Error(`ffmpeg: ${err.trim() || (fallo && fallo.message) || 'terminó antes de tiempo'}`));
      return new Promise((ok, mal) => {
        if (ff.stdin.write(buf)) return ok();
        pendientes.add(mal);
        ff.stdin.once('drain', () => {
          pendientes.delete(mal);
          ok();
        });
      });
    },
    async cerrar() {
      ff.stdin.end();
      await fin;
    },
    // Si la captura falla a medias, ffmpeg se quedaría esperando datos: se mata y se ignora su error.
    abortar() {
      try {
        ff.stdin.destroy();
        ff.kill('SIGKILL');
      } catch {
        /* ya terminó */
      }
      fin.catch(() => {});
    },
  };
}
