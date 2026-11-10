// planificador.mjs — spec normalizado → línea de tiempo resuelta (linea_tiempo.json).
//
// El LLM no escribe tiempos. Cada componente declara sus beats (min/pref) en planear(); aquí se
// calcula la duración natural de cada escena, se ajusta el total a salida.duracion comprimiendo o
// estirando SOLO lo flexible, y se cuantiza todo a la rejilla de cuadros (900 cuadros = 30.000 s).

import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { parsearEnfasis, sinMarcas } from '../runtime/palabras.js';
import * as titular from '../runtime/titular.js';
import * as subtitulo from '../runtime/subtitulo.js';
import { aCuadro } from '../runtime/tiempo.js';
import { RAIZ_MOTOR } from './catalogo.mjs';

const modulos = new Map();
export async function moduloComponente(tipo) {
  if (!modulos.has(tipo)) {
    const f = path.join(RAIZ_MOTOR, 'componentes', tipo, `${tipo}.js`);
    modulos.set(tipo, await import(pathToFileURL(f).href));
  }
  return modulos.get(tipo);
}

const suma = (xs) => xs.reduce((a, b) => a + b, 0);
const r3 = (x) => Math.round(x * 1000) / 1000;

function textosVisibles(v, out) {
  if (typeof v === 'string') out.push(sinMarcas(v));
  else if (Array.isArray(v)) v.forEach((x) => textosVisibles(x, out));
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) if (k !== 'notas' && k !== 'respaldo') textosVisibles(x, out);
  return out;
}

// Reparte `cantidad` entre elementos con capacidad `cap[i]` y peso `peso[i]` (llenado por niveles).
function repartir(cantidad, cap, peso) {
  const asig = cap.map(() => 0);
  let resto = cantidad;
  let activos = cap.map((c, i) => (c > 1e-9 ? i : -1)).filter((i) => i >= 0);
  while (resto > 1e-9 && activos.length) {
    const pt = suma(activos.map((i) => peso[i]));
    let usado = 0;
    const siguientes = [];
    for (const i of activos) {
      const q = (resto * peso[i]) / pt;
      const libre = cap[i] - asig[i];
      const d = Math.min(q, libre);
      asig[i] += d;
      usado += d;
      if (cap[i] - asig[i] > 1e-9) siguientes.push(i);
    }
    resto -= usado;
    if (usado < 1e-12) break;
    activos = siguientes;
  }
  return { asig, resto };
}

// Busca la toma de voz de la frase j de la escena i. No sirve si cambió el texto, o si las tomas son
// de otro proveedor/voz (p. ej. se pasó de gpt-audio a fish): se usan tiempos estimados hasta regenerar.
const normProv = (p) => (p === 'openrouter' ? 'gpt-audio' : p || 'fish');
function tomaVoz(voz, i, j, texto, pedida) {
  if (!voz || !Array.isArray(voz.lineas)) return null;
  if (pedida && normProv(voz.proveedor) !== normProv(pedida.proveedor)) return null;
  if (pedida && normProv(pedida.proveedor) === 'gpt-audio' && voz.voz && pedida.voz && voz.voz !== pedida.voz) return null;
  const x = voz.lineas.find((l) => l.escena === i && l.frase === j);
  return x && sinMarcas(x.texto).trim() === sinMarcas(texto).trim() ? x : null;
}

export async function planificar(spec, { tema, catalogo, slug, voz = null }) {
  const issues = [];
  const E = (codigo, ruta, msg, arreglo) => issues.push({ codigo, severidad: 'E', ruta, msg, arreglo });
  const fps = 30;
  const D = spec.salida.duracion;
  const mv = tema.movimiento;
  const T = aCuadro(mv.transicion, fps);
  const ARR = mv.arranque;
  const n = spec.escenas.length;

  // 1. Necesidades de cada escena.
  const info = [];
  for (let i = 0; i < n; i++) {
    const e = spec.escenas[i];
    const cat = catalogo.escenas[e.tipo];
    const mod = await moduloComponente(e.tipo);
    const plan = mod.planear(e.props || e, tema);
    const entrada = i === 0 ? 0 : T;
    const salida = i === n - 1 ? 0 : T;
    const frasesTxt = e.titular ? (Array.isArray(e.titular) ? e.titular : [e.titular]) : [];
    const frases = frasesTxt.map((f) => {
      const palabras = parsearEnfasis(f);
      return { palabras, ...titular.planear(palabras, tema) };
    });
    const arr = plan.arranque ?? ARR; // un componente puede arrancar en 0 (p. ej. el gancho del intro)
    const bPref = suma(plan.pasos.map((p) => p.pref));
    const bMin = suma(plan.pasos.map((p) => p.min));
    // El titular se lee desde su primera palabra: cada frase dura lo que tarde en leerse
    // (o en aparecer + un respiro, si es más largo).
    const tPref = frases.length ? ARR + suma(frases.map((f) => Math.max(f.revelado + 0.8, f.lectura))) : 0;
    // Mínimo al ritmo de la referencia (~4.5 palabras/s en titulares que se suceden): el gancho se
    // capta aunque no se lea completo; el preferido sigue siendo cómodo.
    const tMin = frases.length ? ARR + suma(frases.map((f) => Math.max(f.revelado + 0.4, f.palabras.length / 4.5 + 0.3))) : 0;
    // Subtítulo (karaoke): cada frase necesita su tiempo de lectura.
    // Con voz en off, el subtítulo ES lo que se locuta: su duración sale de la toma real (o se estima).
    const conVoz = !!spec.audio.voz;
    const subs = (e.subtitulo || []).map((f, j) => {
      const palabras = parsearEnfasis(f);
      if (!conVoz) return { palabras, ...subtitulo.planear(palabras) };
      const toma = tomaVoz(voz, i, j, f, spec.audio.voz);
      const dv = toma ? toma.dur : palabras.length / 2.5 + 0.35;
      return { palabras, toma, dv, pref: dv + 0.3, min: dv + 0.12 };
    });
    const sPref = subs.length ? ARR + suma(subs.map((f) => f.pref)) + (conVoz ? 0.3 : 0) : 0;
    const sMin = subs.length ? ARR + suma(subs.map((f) => f.min)) + (conVoz ? 0.15 : 0) : 0;
    const nat = Math.max(arr + bPref + plan.reposo.pref + salida, tPref + salida, sPref + salida, cat.duracion.min);
    const min = Math.max(arr + bMin + plan.reposo.min + salida, tMin + salida, sMin + salida, cat.duracion.min);
    const max = Math.max(cat.duracion.max, nat);
    const palabras = textosVisibles(e, []).join(' ').split(/\s+/).length;
    const fija = typeof e.duracion === 'number' ? e.duracion : null;
    if (fija !== null && fija < min - 1e-6) {
      E('E-TIEMPO-CORTA', `escenas[${i}].duracion`, `${fija}s no alcanza para su contenido (necesita ${min.toFixed(1)}s).`,
        `Quita "duracion" para que el motor la calcule, o súbela a ≥ ${Math.ceil(min * 10) / 10}.`);
    }
    info.push({ e, i, cat, plan, frases, subs, entrada, salida, nat, min, minOriginal: min, max, fija, arr, peso: 1 + palabras * 0.12 + plan.pasos.length * 0.3 });
  }
  if (issues.length) return { issues };

  // 2. Ajuste al total objetivo: Σd − T·(n−1) = D.
  const objetivo = D + T * (n - 1);
  const libres = info.filter((x) => x.fija === null);
  const fijo = suma(info.filter((x) => x.fija !== null).map((x) => x.fija));
  const necesario = objetivo - fijo;
  const sNat = suma(libres.map((x) => x.nat));
  const sMin = suma(libres.map((x) => x.min));
  for (const x of info) x.d = x.fija !== null ? x.fija : x.nat;

  // Si no cabe al ritmo mínimo, se permite acelerar hasta un 28 % más (ritmo de la referencia: escenas
  // de 2.5 s). Solo si ni así cabe es error. Acelerar se avisa con W-TIEMPO-RAPIDO.
  const PISO = 0.72;
  let rapido = false;
  if (sMin > necesario + 1e-6) {
    const piso = (x) => (x.cat.comprimible === false ? 1 : PISO); // p. ej. el cierre (CTA) no se acelera
    const sPiso = suma(libres.map((x) => x.min * piso(x)));
    if (sPiso > necesario + 1e-6) {
      const minTotal = sPiso + fijo - T * (n - 1);
      const pesadas = [...libres].sort((a, b) => b.min - a.min).slice(0, 2)
        .map((x) => `escenas[${x.i}] (${x.e.tipo}, mín ${(x.min * piso(x)).toFixed(1)}s)`).join(' y ');
      E('E-TIEMPO-EXCEDE', 'salida.duracion', `el contenido necesita al menos ${minTotal.toFixed(1)}s y el objetivo es ${D}s.`,
        `Sube salida.duracion a ${Math.ceil(minTotal)} o recorta texto/elementos en ${pesadas}.`);
      return { issues };
    }
    rapido = true;
    const k = (necesario - sPiso) / Math.max(1e-6, sMin - sPiso); // 0 = piso, 1 = mínimo normal
    for (const x of libres) {
      x.d = x.min * (piso(x) + (1 - piso(x)) * k);
      x.min = x.d; // de aquí en adelante la escena se reparte ya acelerada
    }
    issues.push({ codigo: 'W-TIEMPO-RAPIDO', severidad: 'W', ruta: 'salida.duracion',
      msg: `para caber en ${D}s el ritmo se aceleró ${Math.round((1 - (necesario / sMin)) * 100)} % sobre el mínimo cómodo.`,
      arreglo: `Aceptable en promos (la referencia es así de rápida); para un ritmo cómodo sube salida.duracion a ${Math.ceil(sMin + fijo - T * (n - 1))} o quita un item.` });
  }
  if (rapido) {
    /* ya repartido arriba */
  } else if (sNat > necesario) {
    const cap = libres.map((x) => x.nat - x.min);
    const { asig } = repartir(sNat - necesario, cap, cap.map(() => 1));
    libres.forEach((x, k) => (x.d = x.nat - asig[k]));
  } else if (sNat < necesario) {
    const cap = libres.map((x) => Math.min(x.max, x.nat + mv.estirar_max) - x.nat);
    const { asig, resto } = repartir(necesario - sNat, cap, libres.map((x) => x.peso));
    if (resto > 0.05) {
      const maxTotal = sNat + suma(cap) + fijo - T * (n - 1);
      E('E-TIEMPO-FALTA', 'salida.duracion', `al contenido le faltan ${resto.toFixed(1)}s para llegar a ${D}s (máximo natural ≈ ${maxTotal.toFixed(1)}s).`,
        `Baja salida.duracion a ${Math.floor(maxTotal)} o agrega una escena.`);
      return { issues };
    }
    libres.forEach((x, k) => (x.d = x.nat + asig[k]));
  }

  // 3. Cuantización: inicios en la rejilla de cuadros; el último termina exactamente en D.
  //    Con cama procedural (pulso conocido), cada cambio de escena se corre al beat más cercano si
  //    está a ≤0.15 s: las transiciones "caen" en el pulso sin alterar la duración total.
  const bpm = spec.audio.musica.tipo === 'procedural' ? spec.audio.musica.bpm : null;
  const beat = bpm ? 60 / bpm : null;
  let t = 0;
  const inis = [];
  for (let k = 0; k < n; k++) {
    let ini = t;
    if (beat && k > 0) {
      const alBeat = Math.round(ini / beat) * beat;
      if (Math.abs(alBeat - ini) <= 0.15) ini = alBeat;
    }
    inis.push(aCuadro(ini, fps));
    t += info[k].d - T;
  }
  const escenas = [];
  const cues = [];
  const vozLineas = [];
  const qa = new Set([0]);
  for (let k = 0; k < n; k++) {
    const x = info[k];
    const ini = inis[k];
    const fin = k < n - 1 ? r3(inis[k + 1] + T) : D;
    const dur = r3(fin - ini);

    // 4. Beats dentro de la escena: comprimir hacia min o estirar (35 % a los beats, resto a reposo).
    const { pasos, reposo } = x.plan;
    const bPref = suma(pasos.map((p) => p.pref));
    const espacio = dur - x.salida - x.arr;
    let durs;
    if (dur >= x.nat - 1e-6) {
      const extra = Math.max(0, espacio - bPref - reposo.pref);
      const f = Math.min(1.25, (bPref + extra * 0.35) / Math.max(bPref, 1e-6));
      durs = pasos.map((p) => p.pref * f);
    } else if (dur >= x.minOriginal - 1e-6) {
      const f = x.nat - x.minOriginal > 1e-6 ? Math.max(0, (dur - x.minOriginal) / (x.nat - x.minOriginal)) : 1;
      durs = pasos.map((p) => p.min + f * (p.pref - p.min));
    } else {
      // Ritmo acelerado: beats y reposo mínimos escalados por igual para caber en la escena.
      // Sin piso: con un piso fijo los últimos beats podían caer después de la salida de la escena.
      const g = Math.min(1, Math.max(0, espacio) / Math.max(1e-6, suma(pasos.map((p) => p.min)) + reposo.min));
      durs = pasos.map((p) => p.min * g);
    }
    const lp = {};
    let c = x.arr;
    pasos.forEach((p, j) => {
      lp[p.id] = { ini: r3(c), dur: r3(durs[j]) };
      if (p.cue) cues.push({ s: p.cue, en: r3(ini + c), g: p.g ?? 1 });
      c += durs[j];
    });

    // Titular: frases repartidas en el tiempo útil de la escena.
    let tit = null;
    if (x.frases.length) {
      const util = dur - x.salida - ARR;
      const tramo = util / x.frases.length;
      // Si el componente ancla cada frase a un beat (p. ej. una pregunta por tarjeta), se respeta;
      // si no, las frases se reparten en partes iguales del tiempo útil.
      const anclas = Array.isArray(x.plan.frases) && x.plan.frases.length === x.frases.length && x.plan.frases.every((id) => lp[id])
        ? x.plan.frases.map((id, j) => (j === 0 ? ARR : lp[id].ini))
        : null;
      tit = x.frases.map((f, j) => ({
        palabras: f.palabras,
        ini: r3(anclas ? anclas[j] : ARR + j * tramo),
        fin: j === x.frases.length - 1 ? dur : r3(anclas ? anclas[j + 1] : ARR + (j + 1) * tramo),
      }));
      tit.forEach((f) => qa.add(aCuadro(ini + Math.min(f.fin - 0.15, f.ini + x.frases[0].revelado + 0.3), fps)));
    }

    // Subtítulo: frases repartidas igual que el titular; cada palabra con su instante de karaoke.
    let sub = null;
    if (x.subs.length && !spec.audio.voz) {
      const util = dur - x.salida - ARR;
      const tramo = util / x.subs.length;
      sub = x.subs.map((f, j) => {
        const fi = r3(ARR + j * tramo);
        const ff = j === x.subs.length - 1 ? dur : r3(ARR + (j + 1) * tramo);
        return { palabras: subtitulo.tiemposKaraoke(f.palabras, fi, ff), ini: fi, fin: ff };
      });
    } else if (x.subs.length) {
      // Con voz: cada frase dura su toma + un respiro repartido; la pastilla entra 0.12 s antes de la voz
      // y cada palabra se enciende con su tiempo real (alineación de la toma) o estimado.
      const util = dur - x.salida - ARR;
      const holgura = Math.max(0, (util - suma(x.subs.map((f) => f.dv + 0.12))) / x.subs.length);
      let c = ARR;
      sub = x.subs.map((f, j) => {
        const fi = r3(c);
        const en = fi + 0.12;
        const ff = j === x.subs.length - 1 ? dur : r3(en + f.dv + holgura);
        c = ff;
        const palabras = f.toma && Array.isArray(f.toma.palabras) && f.toma.palabras.length === f.palabras.length
          ? f.palabras.map((p, k) => ({ ...p, a: r3(en + f.toma.palabras[k].a) }))
          : subtitulo.tiemposKaraoke(f.palabras, en - 0.12, en + f.dv).map((p) => ({ ...p, a: r3(p.a) }));
        vozLineas.push({ escena: k, frase: j, texto: sinMarcas(x.e.subtitulo[j]), archivo: f.toma ? f.toma.archivo : null,
          en: r3(ini + en), dur: r3(f.dv), ini_frase: r3(ini + fi), fin_frase: r3(ini + ff) });
        return { palabras, ini: fi, fin: ff };
      });
    }

    const { tipo, id, tinte, duracion, respaldo, notas, titular: _t, subtitulo: _s, ...props } = x.e;
    escenas.push({
      id, tipo, ruta: `escenas[${k}]`, ini, fin, dur, entrada: x.entrada, salida: x.salida, arranque: x.arr,
      tinte, props, pasos: lp, titular: tit, subtitulo: sub, respaldo: respaldo || [],
    });

    const asentada = Math.min(fin - x.salida - 0.12, ini + c + 0.35);
    qa.add(aCuadro(asentada, fps));
    if (k > 0) {
      qa.add(aCuadro(ini + T / 2, fps));
      cues.push({ s: 'whoosh', en: r3(ini + 0.04), g: 0.55 });
    }
  }
  if (spec.audio.voz) {
    const faltan = vozLineas.filter((l) => !l.archivo).length;
    if (!vozLineas.length) {
      issues.push({ codigo: 'W-VOZ-SIN-TEXTO', severidad: 'W', ruta: 'audio.voz', msg: 'pediste voz pero ninguna escena tiene `subtitulo` (es lo que se locuta).', arreglo: 'Agrega subtitulo a las escenas de demo o quita audio.voz.' });
    } else if (faltan) {
      issues.push({ codigo: 'W-VOZ-PENDIENTE', severidad: 'W', ruta: 'audio.voz', msg: `faltan ${faltan} de ${vozLineas.length} tomas de voz (tiempos estimados).`, arreglo: 'Corre: python3 scripts/promo.py voz <proyecto> y luego validar otra vez.' });
    }
  }
  const cuadros = Math.round(D * fps);
  qa.add(r3((cuadros - 1) / fps));

  // Quita whoosh duplicados (una transición + un beat con whoosh casi al mismo tiempo).
  cues.sort((a, b) => a.en - b.en);
  const cuesLimpios = cues.filter((q, i) => !(q.s === 'whoosh' && cues.some((o, j) => j !== i && o.s === 'whoosh' && Math.abs(o.en - q.en) < 0.3 && (o.g > q.g || (o.g === q.g && j < i)))));

  // Secciones musicales: intro (sin kick) / cuerpo / cierre.
  const secciones = [];
  const iniCuerpo = escenas[0].tipo === 'intro' ? r3(escenas[0].fin - T / 2) : 0;
  const ultimo = escenas[n - 1];
  const iniCierre = ultimo.tipo === 'cierre' ? r3(ultimo.ini + T / 2) : D;
  if (iniCuerpo > 0) secciones.push([0, iniCuerpo, 'intro']);
  secciones.push([iniCuerpo, iniCierre, 'cuerpo']);
  if (iniCierre < D) secciones.push([iniCierre, D, 'cierre']);

  const tiempos = [...qa].filter((x) => x >= 0 && x < D).sort((a, b) => a - b);
  const escPortada = escenas.find((x) => x.tipo !== 'intro') || escenas[0];
  const portada = tiempos.find((x) => x > escPortada.ini + 0.9 && x < escPortada.fin) ?? escPortada.ini + escPortada.dur / 2;

  const { _logo, _origen, ...temaLt } = tema;
  const lt = {
    version: 1,
    fps,
    w: 1080,
    h: 1920,
    total: D,
    cuadros,
    semilla: spec.semilla,
    tema: temaLt,
    tema_nombre: spec.tema,
    marca: spec.marca,
    archivo_salida: spec.salida.archivo || `${slug}.mp4`,
    audio: spec.audio,
    voz: spec.audio.voz ? { ...spec.audio.voz, lineas: vozLineas, pendiente: vozLineas.some((l) => !l.archivo) } : null,
    escenas,
    cues: cuesLimpios,
    musica: { bpm: spec.audio.musica.bpm, secciones },
    qa: { tiempos },
    portada: r3(portada),
    texto_total: [...new Set(textosVisibles(spec.escenas, []).concat(Object.values(tema.avisos), [tema.marca.nombre, spec.marca.producto || tema.marca.producto || '', spec.marca.version || tema.marca.version || '']).join(' '))].join(''),
  };
  return { lt, issues };
}
