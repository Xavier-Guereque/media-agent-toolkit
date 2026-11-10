// Lógica pura del «mundo continuo» de Leccion (sin remotion ni JSX) para probarla con `node --test`.
// Una lección ocurre en UN solo mundo: `mundo.actores` lo puebla, `pantalla.acciones` lo cambia sobre la palabra de la voz
// y una cámara virtual lo recorre. Todo estado es función pura de `t`: nada se guarda entre cuadros.
export type Actor = {
  id: string;
  tipo: string; // zona | enlace | dato | panel | imagen | un ícono de ICONOS
  x?: number; y?: number; w?: number; h?: number; // unidades de mundo: 1920x1080 con origen al centro
  texto?: string; etiqueta?: string;
  partes?: string[]; sep?: string; fs?: number; // dato
  de?: string; a?: string; // enlace
  titulo?: string; lineas?: string[]; // panel
  src?: string; pie?: string | null; credito?: string; // imagen: `src` lo resuelve curso.py desde `clave`
};
export type Accion = {
  t: number; accion: string; actor?: string;
  x?: number; y?: number; z?: number; d?: number; dx?: number; dy?: number;
  partes?: number[]; color?: string; texto?: string; a?: string; desde?: string;
  falla?: boolean; veces?: number; cada?: number; numera?: boolean; aisla?: boolean;
};
export type Vista = { x: number; y: number; z: number };
export type Toma = Vista & { t: number; d: number; arco?: boolean };
export type Mundo = { actores: Actor[]; vista?: Partial<Vista> };
type EscenaT = { inicio: number; pantalla?: Record<string, unknown> };

export const ICONOS = ['camara', 'grabador', 'switch', 'router', 'servidor', 'pc', 'telefono', 'nube', 'persona', 'disco'];
export const FORMAS_MUNDO = ['zona', 'enlace', 'dato', 'panel', 'imagen', ...ICONOS];
export const ACCIONES = ['aparece', 'oculta', 'mueve', 'divide', 'une', 'conecta', 'envia', 'resalta', 'llave', 'enfoca', 'escribe', 'clic', 'transforma', 'copia'];

export const SEP_ESTACION = 2300; // distancia entre estaciones: lejos para que el viaje se sienta, cerca para no marear
export const VUELO_S = 0.9;
export const PARQUE = { falla: 0.62 }; // punto del cable donde un paquete sin red se detiene

export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const suave = (x: number) => x * x * x * (x * (6 * x - 15) + 10);
export const prog = (ahora: number, t: number, d: number) => (d <= 0 ? (ahora >= t ? 1 : 0) : suave(clamp01((ahora - t) / d)));
// Entrada con rebote leve: da peso físico al objeto sin parpadear (el parpadeo perjudica, g = −0.56).
export const pop = (ahora: number, t: number, d = 0.45) => {
  const x = clamp01((ahora - t) / d);
  if (x <= 0) return 0;
  const c = 1.9;
  return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2);
};

export const listaAcciones = (escenas: EscenaT[]): Accion[] =>
  escenas
    .flatMap((e) => (Array.isArray(e.pantalla?.acciones) ? (e.pantalla.acciones as Accion[]) : []))
    .filter((a) => a && typeof a.t === 'number')
    .sort((a, b) => a.t - b.t);

export const delActor = (acciones: Accion[], id: string, nombres?: string[]) => acciones.filter((a) => a.actor === id && (!nombres || nombres.includes(a.accion)));
export const vistaDe = (m?: Mundo | null): Vista => ({ x: m?.vista?.x ?? 0, y: m?.vista?.y ?? 0, z: m?.vista?.z ?? 1 });

// Con mundo, las escenas se narran sobre él; sin mundo (o con plano: "estacion") cada una es un lugar al que se viaja.
export const esEstacion = (e: EscenaT, hayMundo: boolean) => !hayMundo || e.pantalla?.plano === 'estacion';
export const estacion = (i: number, hayMundo: boolean): Vista => ({ x: i * SEP_ESTACION, y: (i % 2 ? 1 : -1) * 240 + (hayMundo ? 3000 : 0), z: 1 });

export function posicion(actor: Actor, acciones: Accion[], ahora: number, actores: Actor[] = []): { x: number; y: number } {
  let x = actor.x ?? 0;
  let y = actor.y ?? 0;
  for (const a of delActor(acciones, actor.id)) {
    if (a.accion === 'mueve') {
      const p = prog(ahora, a.t, a.d ?? 0.8);
      x += ((a.x ?? x) - x) * p;
      y += ((a.y ?? y) - y) * p;
    }
    if (a.accion === 'copia' && a.desde) {
      const o = actores.find((c) => c.id === a.desde);
      if (o) {
        const de = posicion(o, acciones, a.t, actores);
        const p = prog(ahora, a.t, a.d ?? 0.8);
        x = de.x + (x - de.x) * p;
        y = de.y + (y - de.y) * p - Math.sin(p * Math.PI) * 90;
      }
    }
  }
  return { x, y };
}

export function tomasDe(escenas: EscenaT[], mundo: Mundo | null | undefined, acciones: Accion[]): Toma[] {
  const hay = Boolean(mundo?.actores?.length);
  const actores = mundo?.actores ?? [];
  const vista = vistaDe(mundo);
  const tomas: Toma[] = [];
  let previa: boolean | null = null;
  escenas.forEach((e, i) => {
    const est = esEstacion(e, hay);
    const t = i === 0 ? 0 : e.inicio - VUELO_S * 0.45;
    if (est) tomas.push({ ...estacion(i, hay), t, d: i === 0 ? 0 : VUELO_S, arco: i > 0 });
    else if (previa !== false) tomas.push({ ...vista, t, d: i === 0 ? 0 : VUELO_S, arco: i > 0 });
    previa = est;
  });
  for (const a of acciones) {
    if (a.accion !== 'enfoca') continue;
    const objetivo = actores.find((c) => c.id === a.actor);
    const p = objetivo ? posicion(objetivo, acciones, a.t + (a.d ?? 1), actores) : null;
    tomas.push({ t: a.t, d: a.d ?? 1, x: (p ? p.x + (a.dx ?? 0) : a.x ?? vista.x), y: (p ? p.y + (a.dy ?? 0) : a.y ?? vista.y), z: a.z ?? (p ? 1.6 : vista.z) });
  }
  return tomas.sort((a, b) => a.t - b.t);
}

// El zoom se interpola en escala logarítmica para que se sienta constante; `arco` aleja a medio viaje: se ve el mundo pasar.
export function camara(tomas: Toma[], ahora: number): Vista {
  const base = tomas[0] ?? { x: 0, y: 0, z: 1 };
  let { x, y, z } = base;
  let aleja = 1;
  for (const m of tomas.slice(1)) {
    const p = prog(ahora, m.t, m.d);
    x += (m.x - x) * p;
    y += (m.y - y) * p;
    z = Math.exp(Math.log(z) + (Math.log(m.z) - Math.log(z)) * p);
    if (m.arco && p > 0 && p < 1) aleja = 1 - 0.28 * Math.sin(p * Math.PI);
  }
  return { x, y, z: z * aleja };
}

// El aislamiento aparta el resto del mundo mientras la cámara está dentro de un dato; termina en el siguiente `enfoca`.
export function aislado(acciones: Accion[], ahora: number): { id: string | null; nivel: number } {
  const enf = acciones.filter((a) => a.accion === 'enfoca');
  let nivel = 0;
  let id: string | null = null;
  enf.forEach((a, i) => {
    if (!a.aisla) return;
    const fin = enf[i + 1];
    const v = prog(ahora, a.t + (a.d ?? 1) * 0.15, (a.d ?? 1) * 0.7) * (fin ? 1 - prog(ahora, fin.t, (fin.d ?? 1) * 0.7) : 1);
    if (v > nivel) { nivel = v; id = a.actor ?? null; }
  });
  return { id, nivel };
}

// Visible desde su `aparece`/`copia`; sin ninguna de esas acciones existe desde el inicio. `oculta` lo retira.
export function presencia(id: string, acciones: Accion[], ahora: number): number {
  const entradas = delActor(acciones, id, ['aparece', 'copia']).filter((a) => !a.partes);
  const salidas = delActor(acciones, id, ['oculta']);
  const parciales = delActor(acciones, id, ['aparece', 'copia']).filter((a) => a.partes);
  const t0 = [...entradas, ...parciales].map((a) => a.t).sort((a, b) => a - b)[0];
  const entra = t0 === undefined ? 1 : pop(ahora, t0);
  return Math.max(0, entra * (1 - salidas.reduce((m, a) => Math.max(m, prog(ahora, a.t, a.d ?? 0.4)), 0)));
}

// Un dato se compone de piezas con posición absoluta: así se separan, tiñen y vuelan sin reflujo de texto.
export type Pieza = { s: string; car: number; parte: number; sep: boolean };
export function piezasDato(partes: string[], sep = '.'): { piezas: Pieza[]; car: number } {
  const piezas: Pieza[] = [];
  let car = 0;
  partes.forEach((s, i) => {
    piezas.push({ s, car, parte: i, sep: false });
    car += s.length;
    if (i < partes.length - 1 && sep) {
      piezas.push({ s: sep, car, parte: i, sep: true });
      car += sep.length;
    }
  });
  return { piezas, car };
}
export const CAR_EM = 0.6; // ancho de carácter de JetBrains Mono

export function parteVisible(acciones: Accion[], id: string, parte: number, ahora: number): number {
  const ev = delActor(acciones, id, ['aparece', 'copia']);
  if (!ev.length) return 1;
  const propias = ev.filter((a) => !a.partes || a.partes.includes(parte));
  if (!propias.length) return 0;
  return pop(ahora, Math.min(...propias.map((a) => a.t)));
}

export function separacion(acciones: Accion[], id: string, ahora: number): number {
  let s = 0;
  for (const a of delActor(acciones, id, ['divide', 'une'])) {
    const p = prog(ahora, a.t, 0.45);
    s += ((a.accion === 'divide' ? 1 : 0) - s) * p;
  }
  return s;
}

export function textoParte(acciones: Accion[], id: string, parte: number, base: string, ahora: number): string {
  let s = base;
  for (const a of delActor(acciones, id, ['transforma'])) {
    if (a.texto !== undefined && (!a.partes || a.partes.includes(parte)) && ahora >= a.t) s = a.texto;
  }
  return s;
}

export function escrito(a: Accion, ahora: number): string {
  const s = a.texto ?? '';
  const d = a.d ?? Math.max(0.4, s.length * 0.045);
  return s.slice(0, Math.floor(clamp01((ahora - a.t) / d) * s.length));
}

export type Paquete = { u: number; op: number; choque: number };
export function paquetes(a: Accion, ahora: number): Paquete[] {
  const d = a.d ?? 0.95;
  const cada = a.cada ?? d * 0.9;
  const salida: Paquete[] = [];
  for (let i = 0; i < (a.veces ?? 1); i++) {
    const x = (ahora - a.t - i * cada) / d;
    if (x < 0 || x > 1.35) continue;
    const llegada = a.falla ? PARQUE.falla : 1;
    salida.push({ u: Math.min(x, 1) * llegada, op: x > 1 ? Math.max(0, 1 - (x - 1) / 0.35) : 1, choque: x > 1 ? x - 1 : 0 });
  }
  return salida;
}

// Cubica horizontal entre dos puntos: el cable sale y entra recto, como un cable real.
export function curva(x0: number, y0: number, x1: number, y1: number) {
  const m = (x0 + x1) / 2;
  const d = `M${x0} ${y0} C${m} ${y0} ${m} ${y1} ${x1} ${y1}`;
  const en = (u: number): [number, number] => {
    const v = 1 - u;
    return [v * v * v * x0 + 3 * v * v * u * m + 3 * v * u * u * m + u * u * u * x1, v * v * v * y0 + 3 * v * v * u * y0 + 3 * v * u * u * y1 + u * u * u * y1];
  };
  return { d, en };
}

export const MEDIDA: Record<string, [number, number]> = { grabador: [460, 300], camara: [200, 150], nube: [240, 160] };
export const medida = (tipo: string): [number, number] => MEDIDA[tipo] ?? [180, 150];
export const IMAGEN_DEF: [number, number] = [640, 400];
const anchoDe = (a: Actor) => (a.tipo === 'imagen' ? a.w ?? IMAGEN_DEF[0] : medida(a.tipo)[0]);

export function extremos(a: Actor, b: Actor, pa: { x: number; y: number }, pb: { x: number; y: number }): [number, number, number, number] {
  const wa = anchoDe(a);
  const wb = anchoDe(b);
  const s = pb.x >= pa.x ? 1 : -1;
  return [pa.x + (s * wa) / 2, pa.y, pb.x - (s * wb) / 2, pb.y];
}

export function cursor(acciones: Accion[], actores: Actor[], ahora: number): { x: number; y: number; visible: number; pulso: number } | null {
  const clics = acciones.filter((a) => a.accion === 'clic');
  if (!clics.length) return null;
  const lugar = (a: Accion) => {
    const c = actores.find((x) => x.id === a.actor);
    const p = c ? posicion(c, acciones, a.t, actores) : { x: a.x ?? 0, y: a.y ?? 0 };
    return { x: p.x + (a.dx ?? 0), y: p.y + (a.dy ?? 0) };
  };
  const i = clics.findIndex((a) => ahora < a.t + 0.9);
  const k = i < 0 ? clics.length - 1 : i;
  const a = clics[k];
  const fin = lugar(a);
  const ini = k > 0 && a.t - clics[k - 1].t < 2.5 ? lugar(clics[k - 1]) : { x: fin.x + 190, y: fin.y + 160 };
  const p = prog(ahora, a.t - 0.75, 0.75);
  const visible = prog(ahora, a.t - 0.85, 0.2) * (1 - prog(ahora, a.t + 0.65, 0.25));
  return { x: ini.x + (fin.x - ini.x) * p, y: ini.y + (fin.y - ini.y) * p, visible, pulso: clamp01((ahora - a.t) / 0.5) };
}
