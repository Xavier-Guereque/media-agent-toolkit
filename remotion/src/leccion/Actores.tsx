// Catálogo visual del mundo: cada actor se dibuja desde su estado en `t`. Sin lógica de guion: eso vive en lib/mundo.ts.
import React from 'react';
import { Img, interpolateColors, staticFile } from 'remotion';
import type { Tema } from '../lib/leccion';
import {
  CAR_EM, curva, delActor, escrito, extremos, IMAGEN_DEF, medida, paquetes, parteVisible, piezasDato, pop, posicion, presencia, prog, separacion, textoParte,
} from '../lib/mundo';
import type { Accion, Actor } from '../lib/mundo';

export type Pinta = { tema: Tema; sans: string; mono: string; acciones: Accion[]; actores: Actor[]; ahora: number };
const panel = (t: Tema) => t.panel ?? '#FFFFFF';
const borde = (t: Tema) => t.borde ?? t.tenue;
const peligro = (t: Tema) => t.peligro ?? t.alerta;

export const colorDe = (tema: Tema, nombre?: string): string =>
  ({ acento: tema.acento, alerta: tema.alerta, correcta: tema.correcta, peligro: peligro(tema), texto: tema.texto, tenue: tema.tenue })[nombre ?? 'acento'] ?? nombre ?? tema.acento;

// Estado encendido/apagado: lo cambia `transforma` con a: "vivo".
const vivoDe = (id: string, p: Pinta) => delActor(p.acciones, id, ['transforma']).filter((a) => a.a === 'vivo').reduce((m, a) => Math.max(m, prog(p.ahora, a.t, 0.8)), 0);
const led = (v: number, t: Tema) => interpolateColors(v, [0, 1], [peligro(t), t.correcta]);

const svgIcono: Record<string, (c: string, t: Tema) => React.ReactNode> = {
  camara: (c) => (
    <>
      <path d="M-70 -62 h60 v22 h-60 z" fill="#232B47" />
      <path d="M-40 -40 v24" stroke="#3A466E" strokeWidth={12} />
      <rect x={-82} y={-20} width={150} height={66} rx={14} fill="#E9EDF7" />
      <rect x={-82} y={-20} width={150} height={20} rx={10} fill="#FFFFFF" />
      <rect x={62} y={-10} width={32} height={46} rx={7} fill="#1C2340" />
      <circle cx={78} cy={13} r={14} fill="#0B1022" />
      <circle cx={78} cy={13} r={7} fill={c} />
      <rect x={-66} y={22} width={60} height={8} rx={4} fill="#B9C2D8" />
    </>
  ),
  switch: (c) => (
    <>
      <rect x={-96} y={-30} width={192} height={60} rx={12} fill="#2A3353" stroke="#46527E" strokeWidth={3} />
      {[-70, -44, -18, 8, 34, 60].map((x) => <rect key={x} x={x} y={-12} width={18} height={16} rx={3} fill="#0E1324" />)}
      <circle cx={-78} cy={17} r={4} fill={c} /><circle cx={-62} cy={17} r={4} fill={c} />
    </>
  ),
  router: (c) => (
    <>
      <path d="M-50 -18 L-68 -72 M50 -18 L68 -72" stroke="#46527E" strokeWidth={9} strokeLinecap="round" />
      <rect x={-92} y={-20} width={184} height={68} rx={16} fill="#2A3353" stroke="#46527E" strokeWidth={3} />
      <circle cx={-58} cy={14} r={6} fill={c} /><circle cx={-32} cy={14} r={6} fill={c} /><circle cx={-6} cy={14} r={6} fill={c} />
    </>
  ),
  servidor: (c) => (
    <>
      {[-66, -14, 38].map((y) => (
        <g key={y}>
          <rect x={-78} y={y} width={156} height={44} rx={9} fill="#2A3353" stroke="#46527E" strokeWidth={3} />
          <circle cx={-54} cy={y + 22} r={6} fill={c} />
          <rect x={-30} y={y + 18} width={84} height={8} rx={4} fill="#0E1324" />
        </g>
      ))}
    </>
  ),
  pc: (c) => (
    <>
      <rect x={-96} y={-68} width={192} height={118} rx={12} fill="#0E1324" stroke="#46527E" strokeWidth={4} />
      <rect x={-82} y={-54} width={164} height={90} rx={6} fill={c} opacity={0.25} />
      <path d="M-24 50 h48 l10 22 h-68 z" fill="#2A3353" />
    </>
  ),
  telefono: (c) => (
    <>
      <rect x={-46} y={-78} width={92} height={156} rx={16} fill="#0E1324" stroke="#46527E" strokeWidth={4} />
      <rect x={-36} y={-64} width={72} height={124} rx={6} fill={c} opacity={0.25} />
    </>
  ),
  nube: (c) => (
    <path d="M-68 48 a44 44 0 0 1 -6 -88 a62 62 0 0 1 116 -18 a52 52 0 0 1 28 106 z" fill="#2A3353" stroke={c} strokeWidth={4} />
  ),
  persona: (c) => (
    <>
      <circle cx={0} cy={-36} r={36} fill="#E9EDF7" />
      <path d="M-68 70 a68 68 0 0 1 136 0 z" fill={c} />
    </>
  ),
  disco: (c) => (
    <>
      <ellipse cx={0} cy={-46} rx={78} ry={26} fill="#46527E" />
      <path d="M-78 -46 v92 a78 26 0 0 0 156 0 v-92" fill="#2A3353" />
      <circle cx={52} cy={38} r={6} fill={c} />
    </>
  ),
};

const Grabador: React.FC<{ v: number; p: Pinta }> = ({ v, p }) => {
  const { tema, sans } = p;
  return (
    <div style={{ width: 460, fontFamily: sans }}>
      <div style={{ background: '#0E1324', border: `3px solid ${borde(tema)}`, borderRadius: 16, padding: 14, display: 'flex', gap: 12 }}>
        {[1, 2].map((n) => (
          <div key={n} style={{ flex: 1, height: 148, borderRadius: 10, overflow: 'hidden', position: 'relative', background: '#20273F' }}>
            <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(${150 + n * 40}deg, #1F6FA8, #123B62 55%, #0D5A52)`, clipPath: `inset(0 ${(1 - v) * 100}% 0 0)` }}>
              <div style={{ position: 'absolute', left: 16, top: 12, fontSize: 19, fontWeight: 700, color: '#fff' }}>● Cámara {n}</div>
              <div style={{ position: 'absolute', bottom: 0, left: `${18 + n * 20}%`, width: 74, height: 62, background: '#0A2137', borderRadius: '8px 8px 0 0' }} />
            </div>
            <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: peligro(tema), fontSize: 24, fontWeight: 700, opacity: 1 - v }}>Sin señal</div>
          </div>
        ))}
      </div>
      <div style={{ width: 90, height: 18, background: '#232B47', margin: '0 auto' }} />
      <div style={{ height: 58, background: 'linear-gradient(#303A5E, #1C2340)', borderRadius: 10, display: 'flex', alignItems: 'center', gap: 12, padding: '0 22px' }}>
        <span style={{ width: 12, height: 12, borderRadius: 12, background: led(v, tema) }} />
        <span style={{ flex: 1, height: 6, borderRadius: 3, background: '#0E1324' }} />
        <span style={{ fontSize: 22, fontWeight: 700, color: '#C6CDE0' }}>Grabador</span>
      </div>
    </div>
  );
};

// Halo de `resalta` en un objeto: crece una vez y se va; nunca parpadea.
const Halo: React.FC<{ a: Actor; p: Pinta }> = ({ a, p }) => {
  const [w, h] = medida(a.tipo);
  return (
    <>
      {delActor(p.acciones, a.id, ['resalta']).map((x, i) => {
        const v = Math.min(1, (p.ahora - x.t) / 1.1);
        if (v <= 0 || v >= 1) return null;
        return <div key={i} style={{ position: 'absolute', left: -w / 2 - 20, top: -h / 2 - 20, width: w + 40, height: h + 40, borderRadius: 26, border: `5px solid ${colorDe(p.tema, x.color)}`, opacity: 1 - v, scale: `${1 + v * 0.14}` }} />;
      })}
    </>
  );
};

const Icono: React.FC<{ a: Actor; p: Pinta; op: number }> = ({ a, p, op }) => {
  const pos = posicion(a, p.acciones, p.ahora, p.actores);
  const entra = presencia(a.id, p.acciones, p.ahora);
  const v = vivoDe(a.id, p);
  const [w, h] = medida(a.tipo);
  const color = led(v, p.tema);
  return (
    <div style={{ position: 'absolute', left: pos.x, top: pos.y, opacity: op * Math.min(1, entra * 1.5), scale: `${entra}` }}>
      <Halo a={a} p={p} />
      {a.tipo === 'grabador' ? (
        <div style={{ position: 'absolute', left: -w / 2, top: -h / 2 }}><Grabador v={v} p={p} /></div>
      ) : (
        <svg width={w} height={h} viewBox={`${-w / 2} ${-h / 2} ${w} ${h}`} style={{ position: 'absolute', left: -w / 2, top: -h / 2, overflow: 'visible' }}>
          {(svgIcono[a.tipo] ?? svgIcono.pc)(color, p.tema)}
        </svg>
      )}
      {a.etiqueta ? <div style={{ position: 'absolute', left: -200, width: 400, top: h / 2 + 10, textAlign: 'center', fontFamily: p.sans, fontSize: 28, fontWeight: 600, color: p.tema.texto }}>{a.etiqueta}</div> : null}
    </div>
  );
};

const Dato: React.FC<{ a: Actor; p: Pinta; op: number }> = ({ a, p, op }) => {
  const { tema, acciones, ahora } = p;
  const fs = a.fs ?? 30;
  const car = fs * CAR_EM;
  const partes = a.partes ?? [a.texto ?? ''];
  const { piezas, car: total } = piezasDato(partes, a.sep ?? '.');
  const pos = posicion(a, acciones, ahora, p.actores);
  const sep = separacion(acciones, a.id, ahora);
  const paso = fs * 0.2;
  const grupo = (parte: number, esSep: boolean) => (parte + (esSep ? 0.5 : 0) - (partes.length - 1) / 2) * sep * paso;
  const ancho = total * car;
  const pres = presencia(a.id, acciones, ahora);
  const tinte = (i: number) => {
    let c = tema.texto;
    for (const x of delActor(acciones, a.id, ['resalta', 'copia'])) {
      if (x.color && (!x.partes || x.partes.includes(i))) c = interpolateColors(prog(ahora, x.t, 0.4), [0, 1], [c, colorDe(tema, x.color)]);
    }
    return c;
  };
  // Resaltar lo que ya tiene color debe verse igual: cada parte da un pulso breve, sin parpadeo.
  const pulso = (i: number) => delActor(acciones, a.id, ['resalta']).filter((x) => !x.partes || x.partes.includes(i)).reduce((m, x) => {
    const u = (ahora - x.t) / 0.55;
    return u > 0 && u < 1 ? Math.max(m, Math.sin(u * Math.PI)) : m;
  }, 0);
  const extra = (partes.length - 1) * sep * paso;
  return (
    <div style={{ position: 'absolute', left: pos.x, top: pos.y, opacity: op * Math.min(1, pres * 1.4), fontFamily: p.mono, fontWeight: 700, fontSize: fs, lineHeight: 1 }}>
      <div style={{ position: 'absolute', left: -ancho, top: -ancho * 0.7, width: ancho * 2, height: ancho * 1.4, background: `radial-gradient(closest-side, ${tema.acento}38, transparent)` }} />
      <div style={{ position: 'absolute', left: -ancho / 2 - fs * 0.55 - extra / 2, top: -fs * 0.8, width: ancho + fs * 1.1 + extra, height: fs * 1.6, borderRadius: fs / 3, background: `${panel(tema)}DD`, border: `2px solid ${borde(tema)}` }} />
      {piezas.map((z, i) => (
        <span key={i} style={{ position: 'absolute', left: -ancho / 2 + z.car * car + grupo(z.parte, z.sep), top: -fs / 2, whiteSpace: 'pre', color: tinte(z.parte), opacity: parteVisible(acciones, a.id, z.parte, ahora), scale: `${1 + 0.16 * pulso(z.parte)}` }}>
          {z.sep ? z.s : textoParte(acciones, a.id, z.parte, z.s, ahora)}
        </span>
      ))}
      {delActor(acciones, a.id, ['divide']).filter((x) => x.numera).flatMap((x) =>
        partes.map((_, i) => {
          const u = piezas.find((z) => z.parte === i && !z.sep)!;
          const cx = -ancho / 2 + (u.car + u.s.length / 2) * car + grupo(i, false);
          const s = pop(ahora, x.t + 0.05 + i * 0.1) * (1 - prog(ahora, x.t + (x.d ?? 1.3), 0.3));
          const r = fs * 0.27;
          return <div key={`${x.t}-${i}`} style={{ position: 'absolute', left: cx - r, top: -fs * 1.65, width: r * 2, height: r * 2, borderRadius: r * 2, background: tema.texto, color: tema.fondo, fontSize: r * 1.3, display: 'grid', placeItems: 'center', fontFamily: p.sans, scale: `${s}` }}>{i + 1}</div>;
        }),
      )}
      {delActor(acciones, a.id, ['llave']).map((x, n) => {
        const ids = x.partes ?? partes.map((_, i) => i);
        const prim = piezas.find((z) => z.parte === ids[0] && !z.sep)!;
        const ult = piezas.find((z) => z.parte === ids[ids.length - 1] && !z.sep)!;
        const x0 = -ancho / 2 + prim.car * car + grupo(ids[0], false);
        const x1 = -ancho / 2 + (ult.car + ult.s.length) * car + grupo(ids[ids.length - 1], false);
        const fin = delActor(acciones, a.id, ['une', 'oculta']).find((u) => u.t > x.t);
        const v = prog(ahora, x.t, 0.5) * (fin ? 1 - prog(ahora, fin.t, 0.4) : 1);
        const y = fs;
        const color = colorDe(tema, x.color);
        return (
          <React.Fragment key={n}>
            <svg width={10} height={10} style={{ position: 'absolute', overflow: 'visible' }}>
              <path d={`M${x0} ${y} v${fs * 0.3} H${x1} v${-fs * 0.3}`} fill="none" stroke={color} strokeWidth={fs * 0.08} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - v} opacity={v > 0 ? 1 : 0} />
            </svg>
            {x.texto ? <div style={{ position: 'absolute', left: x0, width: x1 - x0, top: fs * 1.45, textAlign: 'center', fontSize: fs * 0.52, color, opacity: prog(ahora, x.t + 0.25, 0.3) * v, fontFamily: p.sans, whiteSpace: 'nowrap' }}>{x.texto}</div> : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};

const Panel: React.FC<{ a: Actor; p: Pinta; op: number }> = ({ a, p, op }) => {
  const { tema, ahora } = p;
  const pos = posicion(a, p.acciones, ahora, p.actores);
  const pres = presencia(a.id, p.acciones, ahora);
  const w = a.w ?? 620;
  const h = a.h ?? 340;
  const lineas = delActor(p.acciones, a.id, ['escribe']).filter((x) => ahora >= x.t);
  const ultima = lineas[lineas.length - 1];
  return (
    <div style={{ position: 'absolute', left: pos.x - w / 2, top: pos.y - h / 2, width: w, height: h, opacity: op * Math.min(1, pres * 1.4), scale: `${pres}`, background: panel(tema), border: `2px solid ${borde(tema)}`, borderRadius: 18, overflow: 'hidden', boxShadow: '0 30px 70px #0006' }}>
      <div style={{ height: 50, display: 'flex', alignItems: 'center', gap: 9, padding: '0 18px', borderBottom: `2px solid ${borde(tema)}`, fontFamily: p.sans, fontSize: 24, fontWeight: 600, color: tema.tenue }}>
        {[peligro(tema), tema.alerta, tema.correcta].map((c) => <span key={c} style={{ width: 13, height: 13, borderRadius: 13, background: c }} />)}
        <span style={{ marginLeft: 10 }}>{a.titulo}</span>
      </div>
      <div style={{ padding: 20, fontFamily: p.mono, fontSize: 28, fontWeight: 600, lineHeight: 1.42, color: tema.texto, whiteSpace: 'pre-wrap' }}>
        {(a.lineas ?? []).map((l, i) => <div key={i}>{l}</div>)}
        {lineas.map((x, i) => <div key={`e${i}`} style={{ color: x.color ? colorDe(tema, x.color) : undefined }}>{escrito(x, ahora)}{x === ultima && (ahora - x.t) * 2 % 2 < 1.4 ? <span style={{ color: tema.acento }}>▌</span> : null}</div>)}
      </div>
    </div>
  );
};

const Foto: React.FC<{ a: Actor; p: Pinta; op: number }> = ({ a, p, op }) => {
  const { tema, ahora } = p;
  const pos = posicion(a, p.acciones, ahora, p.actores);
  const pres = presencia(a.id, p.acciones, ahora);
  const w = a.w ?? IMAGEN_DEF[0];
  const h = a.h ?? IMAGEN_DEF[1];
  if (!a.src) return null;
  return (
    <div style={{ position: 'absolute', left: pos.x - w / 2, top: pos.y - h / 2, width: w, opacity: op * Math.min(1, pres * 1.4), scale: `${pres}`, fontFamily: p.sans }}>
      <Img src={staticFile(a.src)} style={{ display: 'block', width: w, height: h, objectFit: 'contain', borderRadius: 18 }} />
      {a.pie ? <div style={{ fontSize: 28, fontWeight: 600, color: tema.texto, marginTop: 10, textAlign: 'center' }}>{a.pie}</div> : null}
      {a.credito ? <div style={{ fontSize: 22, color: tema.tenue, marginTop: 4, textAlign: 'center' }}>{a.credito}</div> : null}
    </div>
  );
};

const Zona: React.FC<{ a: Actor; p: Pinta }> = ({ a, p }) => {
  const { tema, ahora } = p;
  const entrada = delActor(p.acciones, a.id, ['aparece'])[0];
  const v = entrada ? prog(ahora, entrada.t, entrada.d ?? 1.1) : 1;
  const salida = delActor(p.acciones, a.id, ['oculta'])[0];
  const op = salida ? 1 - prog(ahora, salida.t, 0.5) : 1;
  const w = a.w ?? 1660;
  const h = a.h ?? 940;
  const x = (a.x ?? 0) - w / 2;
  const y = (a.y ?? 0) - h / 2;
  return (
    <div style={{ position: 'absolute', left: 0, top: 0, opacity: op }}>
      <svg width={10} height={10} style={{ position: 'absolute', overflow: 'visible' }}>
        <rect x={x} y={y} width={w} height={h} rx={46} fill={tema.acento} fillOpacity={0.05 * v} stroke={tema.acento} strokeWidth={4} strokeOpacity={0.85} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - v} />
      </svg>
      {a.texto ? <div style={{ position: 'absolute', left: x + 28, top: y + 22, fontFamily: p.mono, fontSize: 34, fontWeight: 700, color: tema.acento, whiteSpace: 'pre', opacity: prog(ahora, (entrada?.t ?? 0) + 0.7, 0.4) }}>{a.texto}</div> : null}
    </div>
  );
};

const Enlace: React.FC<{ a: Actor; p: Pinta; op: number }> = ({ a, p, op }) => {
  const { tema, acciones, actores, ahora } = p;
  const de = actores.find((x) => x.id === a.de);
  const al = actores.find((x) => x.id === a.a);
  if (!de || !al) return null;
  const pa = posicion(de, acciones, ahora, actores);
  const pb = posicion(al, acciones, ahora, actores);
  const [x0, y0, x1, y1] = extremos(de, al, pa, pb);
  const { d, en } = curva(x0, y0, x1, y1);
  const entrada = delActor(acciones, a.id, ['conecta'])[0];
  const v = entrada ? prog(ahora, entrada.t, entrada.d ?? 0.75) : 1;
  const vivo = vivoDe(a.id, p);
  const color = interpolateColors(vivo, [0, 1], ['#47557F', tema.correcta]);
  return (
    <svg width={10} height={10} style={{ position: 'absolute', overflow: 'visible', opacity: op }}>
      <path d={d} fill="none" stroke={color} strokeOpacity={0.85} strokeWidth={5} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - v} />
      {delActor(acciones, a.id, ['envia']).flatMap((x, i) => paquetes(x, ahora).map((q, n) => {
        const [cx, cy] = en(q.u);
        const c = x.falla && q.choque > 0 ? peligro(tema) : x.falla ? tema.texto : x.color ? colorDe(tema, x.color) : tema.correcta;
        const r = 12 + q.choque * 34;
        return (
          <g key={`${i}-${n}`} opacity={q.op}>
            <circle cx={cx} cy={cy} r={r * 2.3} fill={c} opacity={0.18} />
            <circle cx={cx} cy={cy} r={r} fill={c} />
          </g>
        );
      }))}
    </svg>
  );
};

export const PintaActor: React.FC<{ a: Actor; p: Pinta; op: number }> = ({ a, p, op }) => {
  if (a.tipo === 'zona') return <Zona a={a} p={p} />;
  if (a.tipo === 'enlace') return <Enlace a={a} p={p} op={op} />;
  if (a.tipo === 'dato') return <Dato a={a} p={p} op={op} />;
  if (a.tipo === 'panel') return <Panel a={a} p={p} op={op} />;
  if (a.tipo === 'imagen') return <Foto a={a} p={p} op={op} />;
  return <Icono a={a} p={p} op={op} />;
};

export const Cursor: React.FC<{ x: number; y: number; z: number; visible: number; pulso: number; tema: Tema }> = ({ x, y, z, visible, pulso, tema }) => (
  <div style={{ position: 'absolute', left: x, top: y, opacity: visible, scale: `${1 / z}`, transformOrigin: 'left top' }}>
    {pulso > 0 && pulso < 1 ? <div style={{ position: 'absolute', left: -46, top: -46, width: 92, height: 92, borderRadius: 92, border: `4px solid ${tema.acento}`, opacity: 1 - pulso, scale: `${0.3 + pulso}` }} /> : null}
    <svg viewBox="0 0 32 32" width={54} height={54} style={{ position: 'absolute', overflow: 'visible' }}>
      <path d="M2 2 L26 13 L15 16 L11 28 Z" fill={tema.texto} stroke={tema.fondo} strokeWidth={2} strokeLinejoin="round" />
    </svg>
  </div>
);
