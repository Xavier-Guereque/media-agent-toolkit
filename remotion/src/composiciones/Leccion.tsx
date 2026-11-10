// Lección de curso (BASE versionada): pinta `props.escenas` y `props.mundo`; no se edita por curso.
// Los props los escribe scripts/curso.py componer (curso.json + tiempos medidos). Una lección es UN mundo continuo que una
// cámara recorre: sin láminas ni fundidos. Lo que se mueve significa algo y ocurre sobre la palabra que lo nombra; decisiones
// y evidencia en docs/Metodologia-Cursos-Video.md (sin música bajo la voz, sin kicker numerado ni barra de progreso).
import React from 'react';
import { AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadFont } from '@remotion/google-fonts/Inter';
import { loadFont as cargarMono } from '@remotion/google-fonts/JetBrainsMono';
import type { Meta, PropsBase } from '../lib/props';
import {
  TEMA_DEF, TRAZO_S, centro, cueEn, elementoActivo, elementos as leerElementos, items, opacidadElemento, progreso, puntero, texto, textos, tramos,
} from '../lib/leccion';
import type { Cue, Elemento, Escena, Imagen, Item, Tema } from '../lib/leccion';
import { aislado, camara, clamp01, cursor, esEstacion, estacion, listaAcciones, pop, prog, tomasDe } from '../lib/mundo';
import type { Mundo, Vista } from '../lib/mundo';
import { Cursor, PintaActor, colorDe } from '../leccion/Actores';

const INTER = `${loadFont('normal', { weights: ['400', '500', '600', '700'], subsets: ['latin', 'latin-ext'] }).fontFamily}, Helvetica, Arial, sans-serif`;
const MONO = cargarMono('normal', { weights: ['600', '700'], subsets: ['latin'] }).fontFamily;

type Props = PropsBase & {
  curso?: { titulo?: string; aviso_ia?: string };
  leccion?: { titulo?: string; objetivo?: string; criterio_exito?: string; siguiente?: string | null };
  tema?: Tema;
  audio?: string;
  escenas?: Escena[];
  mundo?: Mundo | null;
  subtitulos?: Cue[];
  subtitulos_quemados?: boolean;
};

export const meta: Meta = {
  fps: 30,
  ancho: 1920,
  alto: 1080,
  duracion: 16,
  props: {
    curso: { titulo: 'Curso de muestra', aviso_ia: 'Voz sintética y contenido asistido por inteligencia artificial, con revisión humana.' },
    leccion: { titulo: 'Qué es una dirección IP', objetivo: 'Identificar las partes de una dirección IP', criterio_exito: 'Lo sabrás cuando separes red y equipo.' },
    tema: TEMA_DEF,
    escenas: [
      { id: 'e1', tipo: 'gancho', inicio: 0, fin: 5, voz_inicio: 0.35, pantalla: { texto: 'Dos cámaras con la misma dirección no se ven' } },
      { id: 'e2', tipo: 'concepto', inicio: 5, fin: 16, voz_inicio: 5.35, pantalla: { titular: 'Una dirección IP', elementos: [
        { t: 6, forma: 'caja', texto: '192.168.1', x: 15, y: 30, w: 34, h: 26 },
        { t: 8, forma: 'caja', texto: '20', x: 55, y: 30, w: 20, h: 26 },
        { t: 10, forma: 'flecha', x: 65, y: 80, x2: 65, y2: 58 },
      ] } },
    ],
    subtitulos: [],
    subtitulos_quemados: false,
  },
};

type Ctx = { k: number; tema: Tema; ancho: number; alto: number; ahora: number };
const CtxTema = React.createContext<Ctx>({ k: 1, tema: TEMA_DEF, ancho: 1920, alto: 1080, ahora: 0 });
const useCtx = () => React.useContext(CtxTema);

// Áreas seguras EBU R95: 5 % por borde para gráficos.
const Marco: React.FC<{ children: React.ReactNode; centrado?: boolean }> = ({ children, centrado }) => {
  const { ancho, alto } = useCtx();
  return (
    <AbsoluteFill style={{ padding: `${alto * 0.05 + 8}px ${ancho * 0.07}px`, display: 'flex', flexDirection: 'column', justifyContent: centrado ? 'center' : 'flex-start' }}>
      {children}
    </AbsoluteFill>
  );
};

// Tipografía cinética: cada palabra sube con un retraso breve. Se lee como un solo gesto, no como aparición palabra a palabra.
const Palabras: React.FC<{ texto: string; t0: number; marcas?: Item[]; paso?: number }> = ({ texto: s, t0, marcas = [], paso = 0.045 }) => {
  const { ahora, tema } = useCtx();
  return (
    <>
      {s.split(' ').map((w, i) => {
        const v = prog(ahora, t0 + i * paso, 0.45);
        const marca = marcas.find((m) => m.texto === w.replace(/[.,;:]$/, ''));
        const encendida = marca ? prog(ahora, marca.t, 0.3) : 0;
        return <span key={i} style={{ display: 'inline-block', opacity: v, translate: `0 ${(1 - v) * 26}px`, marginRight: '0.26em', color: encendida > 0.5 ? colorDe(tema, marca?.color) : undefined }}>{w}</span>;
      })}
    </>
  );
};

const Titular: React.FC<{ children: string; t0: number }> = ({ children, t0 }) => {
  const { k, tema } = useCtx();
  return <div style={{ fontSize: 60 * k, fontWeight: 700, color: tema.texto, lineHeight: 1.18, marginBottom: 34 * k }}><Palabras texto={children} t0={t0} /></div>;
};

// ---------------------------------------------------------------- dibujo dinámico (elementos en % del escenario)
// El SVG va en píxeles reales: escalar con preserveAspectRatio="none" rompe pathLength y el trazo sale punteado.
const FormaSvg: React.FC<{ e: Elemento; p: number; color: string; ancho: number; W: number; H: number }> = ({ e, p, color, ancho, W, H }) => {
  const trazo = { fill: 'none', stroke: color, strokeWidth: ancho, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, pathLength: 1, strokeDasharray: 1, strokeDashoffset: 1 - p };
  const x = (e.x * W) / 100;
  const y = (e.y * H) / 100;
  const w = ((e.w ?? 0) * W) / 100;
  const h = ((e.h ?? 0) * H) / 100;
  if (e.forma === 'caja') return <rect x={x} y={y} width={w} height={h} rx={12} {...trazo} />;
  if (e.forma === 'circulo') return <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} {...trazo} />;
  if (e.forma === 'linea' || e.forma === 'flecha') {
    const x2 = ((e.x2 ?? e.x) * W) / 100;
    const y2 = ((e.y2 ?? e.y) * H) / 100;
    const ang = Math.atan2(y2 - y, x2 - x);
    const punta = (d: number) => `${x2 - 26 * Math.cos(ang + d)},${y2 - 26 * Math.sin(ang + d)}`;
    return (
      <>
        <line x1={x} y1={y} x2={x2} y2={y2} {...trazo} />
        {e.forma === 'flecha' && p >= 1 ? <polyline points={`${punta(0.5)} ${x2},${y2} ${punta(-0.5)}`} {...trazo} pathLength={undefined} strokeDasharray={undefined} strokeDashoffset={undefined} /> : null}
      </>
    );
  }
  return null;
};

const Puntero: React.FC<{ x: number; y: number }> = ({ x, y }) => {
  const { k, tema } = useCtx();
  return (
    <svg viewBox="0 0 32 32" style={{ position: 'absolute', left: `${x}%`, top: `${y}%`, width: 44 * k, height: 44 * k, overflow: 'visible' }}>
      <path d="M2 2 L26 13 L15 16 L11 28 Z" fill={tema.acento} stroke={tema.fondo} strokeWidth={2} strokeLinejoin="round" />
    </svg>
  );
};

const Dibujo: React.FC<{ lista: Elemento[]; repaso: boolean; alto: number }> = ({ lista, repaso, alto }) => {
  const { k, tema, ancho, ahora } = useCtx();
  const W = ancho * 0.86;
  const H = alto;
  const activo = elementoActivo(lista, ahora);
  const mano = puntero(lista, ahora);
  return (
    <div style={{ position: 'relative', width: W, height: H }}>
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
        {lista.map((e, i) => (
          <g key={i} opacity={opacidadElemento(i, activo, repaso)}>
            <FormaSvg e={e} p={progreso(e.t, ahora)} color={i === activo && !repaso ? tema.acento : tema.texto} ancho={4 * k} W={W} H={H} />
          </g>
        ))}
      </svg>
      {lista.map((e, i) => {
        if (!e.texto) return null;
        const [cx, cy] = e.forma === 'texto' ? [e.x, e.y] : centro(e);
        return (
          <div key={i} style={{ position: 'absolute', left: `${cx}%`, top: `${cy}%`, translate: e.forma === 'texto' ? undefined : '-50% -50%', opacity: opacidadElemento(i, activo, repaso) * progreso(e.t + TRAZO_S / 2, ahora, TRAZO_S / 2), fontSize: 42 * k, fontWeight: 600, color: i === activo && !repaso ? tema.acento : tema.texto, whiteSpace: 'pre', lineHeight: 1.2 }}>
            {e.texto}
          </div>
        );
      })}
      {mano.visible && !repaso ? <Puntero x={mano.x} y={mano.y} /> : null}
    </div>
  );
};

// ---------------------------------------------------------------- bloques
const Tarjeta: React.FC<{ activa: boolean; children: React.ReactNode; style?: React.CSSProperties }> = ({ activa, children, style }) => {
  const { k, tema } = useCtx();
  return (
    <div style={{ background: `${tema.panel ?? '#FFFFFF'}E6`, border: `${3 * k}px solid ${activa ? tema.acento : tema.borde ?? tema.tenue}`, borderRadius: 18 * k, padding: `${20 * k}px ${30 * k}px`, boxShadow: activa ? `0 0 ${46 * k}px ${tema.acento}44` : `0 ${14 * k}px ${34 * k}px #0003`, ...style }}>
      {children}
    </div>
  );
};

const Lista: React.FC<{ lista: Item[]; numerada?: boolean; repaso?: boolean; mono?: boolean }> = ({ lista, numerada, repaso, mono }) => {
  const { k, tema, ahora } = useCtx();
  const activo = elementoActivo(lista, ahora);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 * k, position: 'relative' }}>
      {lista.map((it, i) => {
        const v = pop(ahora, it.t, 0.5);
        const es = i === activo && !repaso;
        return (
          <div key={i} style={{ opacity: clamp01(v * 1.5) * (activo >= 0 && !es && !repaso ? 0.62 : 1), translate: `${(1 - v) * -60 * k}px 0`, scale: `${es ? 1.02 : 1}`, transformOrigin: 'left center' }}>
            <Tarjeta activa={es}>
              <div style={{ display: 'flex', gap: 24 * k, alignItems: 'center', fontSize: 42 * k, lineHeight: 1.25, color: tema.texto, fontWeight: es ? 700 : 500, fontFamily: mono ? MONO : undefined }}>
                {numerada ? <span style={{ flex: 'none', width: 56 * k, height: 56 * k, borderRadius: 56 * k, display: 'grid', placeItems: 'center', background: es ? tema.acento : 'transparent', color: es ? tema.fondo : tema.texto, border: `${3 * k}px solid ${es ? tema.acento : tema.tenue}`, fontWeight: 700, fontSize: 32 * k }}>{i + 1}</span> : null}
                <span>{it.texto}</span>
              </div>
            </Tarjeta>
          </div>
        );
      })}
    </div>
  );
};

const Fotos: React.FC<{ imgs: Imagen[] }> = ({ imgs }) => {
  const { k, tema } = useCtx();
  return (
    <div style={{ display: 'flex', flex: 1, gap: 24 * k, minHeight: 0, marginTop: 24 * k }}>
      {imgs.map((im, i) => (
        <div key={i} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Img src={staticFile(im.src)} style={{ width: '100%', flex: 1, minHeight: 0, objectFit: 'contain' }} />
          {im.pie ? <div style={{ fontSize: 30 * k, color: tema.texto, marginTop: 8 * k }}>{im.pie}</div> : null}
          {im.credito ? <div style={{ fontSize: 28 * k, color: tema.tenue, marginTop: 4 * k }}>{im.credito}</div> : null}
        </div>
      ))}
    </div>
  );
};

// Rótulos sobre el mundo: mientras la cámara demuestra algo, el texto se reduce a etiquetas que no tapan la acción.
const Rotulos: React.FC<{ lista: Item[] }> = ({ lista }) => {
  const { k, tema, ahora, alto } = useCtx();
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: alto * 0.84, display: 'flex', justifyContent: 'center', gap: 24 * k }}>
      {lista.map((it, i) => {
        const v = pop(ahora, it.t, 0.5);
        return <div key={i} style={{ opacity: clamp01(v * 1.5), translate: `0 ${(1 - v) * 40 * k}px` }}><Tarjeta activa={i === elementoActivo(lista, ahora)}><span style={{ fontSize: 36 * k, fontWeight: 600, color: tema.texto, whiteSpace: 'nowrap' }}>{it.texto}</span></Tarjeta></div>;
      })}
    </div>
  );
};

// ---------------------------------------------------------------- escenas
const Texto: React.FC<{ arriba?: string; grande: string; abajo?: string; t0: number; marcas?: Item[]; bajo?: boolean }> = ({ arriba, grande, abajo, t0, marcas, bajo }) => {
  const { k, tema, ahora, alto } = useCtx();
  const v = prog(ahora, t0 + 0.5, 0.5);
  const contenido = (
    <>
      {arriba ? <div style={{ fontSize: 38 * k, fontWeight: 600, color: tema.acento, marginBottom: 22 * k, opacity: prog(ahora, t0, 0.4) }}>{arriba}</div> : null}
      <div style={{ fontSize: (bajo ? 60 : 84) * k, fontWeight: 700, color: tema.texto, lineHeight: 1.16 }}><Palabras texto={grande} t0={t0 + 0.08} marcas={marcas} /></div>
      {abajo ? <div style={{ fontSize: 40 * k, color: tema.tenue, marginTop: 28 * k, lineHeight: 1.26, opacity: v, translate: `0 ${(1 - v) * 16}px` }}>{abajo}</div> : null}
    </>
  );
  if (bajo) return <div style={{ position: 'absolute', left: 150 * k, right: 150 * k, top: alto * 0.61, textAlign: 'center' }}>{contenido}</div>;
  return <Marco centrado>{contenido}</Marco>;
};

const Pregunta: React.FC<{ e: Escena }> = ({ e }) => {
  const { k, tema, ahora } = useCtx();
  const p = e.pantalla ?? {};
  const correcta = Number(p.correcta);
  const revelar = Boolean(p.revelar);
  const finVoz = Number(p.fin_voz ?? e.fin);
  const clic = e.inicio + 0.55; // el cursor llega a la correcta: el video muestra cómo se responde
  const elegida = prog(ahora, clic, 0.3);
  const piensa = !revelar && e.fin - finVoz > 0.6 ? clamp01((ahora - finVoz) / (e.fin - finVoz)) : 0;
  return (
    <Marco centrado>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 36 * k, marginBottom: 34 * k }}>
        <div style={{ flex: 1, fontSize: 52 * k, fontWeight: 700, color: tema.texto, lineHeight: 1.2 }}><Palabras texto={texto(p.enunciado)} t0={e.inicio + 0.1} paso={revelar ? 0 : 0.045} /></div>
        {ahora >= finVoz && !revelar ? (
          <svg viewBox="-50 -50 100 100" width={96 * k} height={96 * k} style={{ flex: 'none' }}>
            <circle r={42} fill="none" stroke={tema.borde ?? tema.tenue} strokeWidth={8} />
            <circle r={42} fill="none" stroke={tema.acento} strokeWidth={8} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={piensa} transform="rotate(-90)" />
          </svg>
        ) : null}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 * k }}>
        {textos(p.opciones).map((o, i) => {
          const ok = revelar && i === correcta;
          const v = revelar ? 1 : pop(ahora, e.inicio + 0.5 + i * 0.14, 0.5);
          const apaga = revelar && !ok ? elegida : 0;
          return (
            <div key={i} style={{ opacity: clamp01(v * 1.5) * (1 - apaga * 0.55), translate: `${(1 - v) * 70 * k}px 0`, scale: `${ok ? 1 + 0.03 * elegida : 1}`, transformOrigin: 'left center', position: 'relative' }}>
              <Tarjeta activa={ok && elegida > 0.5} style={ok && elegida > 0.5 ? { borderColor: tema.correcta, boxShadow: `0 0 ${56 * k}px ${tema.correcta}66` } : undefined}>
                <div style={{ display: 'flex', gap: 26 * k, alignItems: 'center', fontSize: 42 * k, color: ok && elegida > 0.5 ? tema.correcta : tema.texto, fontWeight: ok ? 700 : 500 }}>
                  <span style={{ fontWeight: 700 }}>{String.fromCharCode(65 + i)}</span>
                  <span>{o}</span>
                  {ok ? <span style={{ marginLeft: 'auto', scale: `${pop(ahora, clic + 0.1)}`, display: 'inline-block' }}>✓</span> : null}
                </div>
              </Tarjeta>
              {ok && ahora < clic + 0.7 ? (
                <div style={{ position: 'absolute', right: 150 * k, top: 26 * k, translate: `${(1 - prog(ahora, e.inicio, clic - e.inicio)) * 240 * k}px ${(1 - prog(ahora, e.inicio, clic - e.inicio)) * 170 * k}px`, opacity: 1 - prog(ahora, clic + 0.4, 0.3) }}>
                  <Cursor x={0} y={0} z={1 / k} visible={1} pulso={clamp01((ahora - clic) / 0.5)} tema={tema} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      {revelar && p.retro ? <div style={{ fontSize: 38 * k, color: tema.texto, marginTop: 28 * k, lineHeight: 1.26 }}><Palabras texto={texto(p.retro)} t0={clic + 0.3} paso={0.02} /></div> : null}
    </Marco>
  );
};

// `t0` marca la entrada: en estación coincide con la llegada de la cámara.
const Cuerpo: React.FC<{ e: Escena; p: Props; t0: number; plano: 'mundo' | 'estacion' }> = ({ e, p, t0, plano }) => {
  const { k, tema, ahora, alto } = useCtx();
  const s = e.pantalla ?? {};
  const lec = p.leccion ?? {};
  const repaso = ahora >= Number(s.fin_voz ?? e.fin);
  const marcas = Array.isArray(s.marcas) ? items(s.marcas) : undefined;
  const fotos = e.imgs?.length ? <Fotos imgs={e.imgs} /> : null;
  switch (e.tipo) {
    case 'gancho':
      return <Texto arriba={lec.titulo} grande={texto(s.texto)} t0={t0} marcas={marcas} />;
    case 'objetivo':
      return <Texto arriba="Al terminar podrás" grande={texto(s.objetivo, lec.objetivo ?? '')} abajo={plano === 'mundo' ? undefined : texto(s.criterio_exito, lec.criterio_exito ?? '')} t0={t0} marcas={marcas} bajo={plano === 'mundo'} />;
    case 'activacion':
      return <Texto arriba="Recuerda" grande={texto(s.texto)} t0={t0} marcas={marcas} />;
    case 'preentrenamiento':
      return <Marco centrado><Titular t0={t0}>{texto(s.titular, 'Términos clave')}</Titular><Lista lista={items(s.terminos)} /></Marco>;
    case 'concepto':
      return (
        <Marco>
          <Titular t0={t0}>{texto(s.titular)}</Titular>
          {fotos ?? <Dibujo lista={leerElementos(s.elementos)} repaso={repaso} alto={alto * 0.9 - 16 - 96 * k - (s.definicion ? 72 * k : 0)} />}
          {s.definicion ? <div style={{ fontSize: 40 * k, color: tema.texto, opacity: progreso(Number(s.definicion_t ?? e.fin - 2), ahora), lineHeight: 1.26, marginTop: 12 * k }}>{texto(s.definicion)}</div> : null}
        </Marco>
      );
    case 'pasos':
      return <Marco centrado={!fotos}><Titular t0={t0}>{texto(s.titular)}</Titular><Lista lista={items(s.pasos)} numerada repaso={repaso} />{fotos}</Marco>;
    case 'ejemplo':
      return (
        <Marco centrado={!fotos}>
          <Titular t0={t0}>{texto(s.titular, 'Ejemplo')}</Titular>
          <div style={{ fontSize: 40 * k, color: tema.tenue, marginBottom: 26 * k, lineHeight: 1.26 }}><Palabras texto={texto(s.enunciado)} t0={t0 + 0.25} /></div>
          <Lista lista={items(s.solucion)} repaso={repaso} mono />
          {fotos}
        </Marco>
      );
    case 'caso':
      return <Marco><Titular t0={t0}>{texto(s.titular)}</Titular><Lista lista={items(s.tarjetas)} repaso={repaso} />{fotos}</Marco>;
    case 'pregunta':
      return <Pregunta e={e} />;
    case 'resumen':
      return <Marco centrado={!fotos}><Titular t0={t0}>{texto(s.titular, 'En resumen')}</Titular><Lista lista={items(s.puntos)} repaso={repaso} />{fotos}</Marco>;
    case 'cierre':
      return <Texto grande={texto(s.texto, lec.siguiente ? `Sigue: ${lec.siguiente}` : 'Fin de la lección')} abajo={p.curso?.aviso_ia} t0={t0} />;
    default:
      return null;
  }
};

const Fondo: React.FC<{ cam: Vista; f: number }> = ({ cam, f }) => {
  const { tema } = useCtx();
  const px = (-cam.x * 0.05) % 1400;
  const py = (-cam.y * 0.05) % 1400;
  const s = Math.pow(cam.z, 0.35);
  const [a, b, c] = tema.glow ?? [];
  return (
    <AbsoluteFill style={{ background: tema.fondo, overflow: 'hidden' }}>
      {a ? <div style={{ position: 'absolute', inset: -400, translate: `${px}px ${py}px`, scale: `${s}`, rotate: `${f * 0.008}deg`, background: `radial-gradient(760px 520px at 66% 42%, ${a}, transparent 70%), radial-gradient(640px 520px at 30% 66%, ${b}, transparent 70%), radial-gradient(520px 420px at 50% 20%, ${c}, transparent 70%)` }} /> : null}
      <div style={{ position: 'absolute', inset: -300, translate: `${(px * 2.2) % 64}px ${(py * 2.2) % 64}px`, scale: `${s * 1.2}`, backgroundImage: `radial-gradient(${tema.tenue}33 1.6px, transparent 1.7px)`, backgroundSize: '64px 64px' }} />
      {a ? <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 55%, #03050Bd0 100%)' }} /> : null}
    </AbsoluteFill>
  );
};

const Subtitulos: React.FC<{ cues: Cue[] }> = ({ cues }) => {
  const { k, alto, ahora } = useCtx();
  const c = cueEn(cues, ahora);
  if (!c) return null;
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: alto * 0.05, textAlign: 'center' }}>
      <span style={{ display: 'inline-block', whiteSpace: 'pre', background: 'rgba(0,0,0,0.72)', color: '#fff', fontSize: 46 * k, fontWeight: 500, lineHeight: 1.25, padding: `${6 * k}px ${20 * k}px`, borderRadius: 6 * k }}>
        {c.lineas.join('\n').replaceAll(' ', ' ')}
      </span>
    </div>
  );
};

export const Composicion: React.FC<Props> = (p) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const ahora = frame / fps;
  const escenas = p.escenas ?? [];
  const tema = p.tema ?? TEMA_DEF;
  const mundo = p.mundo?.actores?.length ? p.mundo : null;
  const hay = Boolean(mundo);
  const k = Math.min(width, height) / 1080;
  const acciones = React.useMemo(() => listaAcciones(escenas), [escenas]);
  const tomas = React.useMemo(() => tomasDe(escenas, mundo, acciones), [escenas, mundo, acciones]);
  const ts = tramos(escenas, fps);
  const cam = camara(tomas, ahora);
  const ajuste = hay ? Math.min(1, width / 1920) : 1; // el mundo mide 1920 de ancho; en vertical se encoge para caber
  const actores = mundo?.actores ?? [];
  const pinta = { tema, sans: INTER, mono: MONO, acciones, actores, ahora };
  const ais = aislado(acciones, ahora);
  const puntero2 = cursor(acciones, actores, ahora);
  const hudActivo = (e: Escena) => !esEstacion(e, hay) && (e.tipo === 'pregunta' || !(Array.isArray(e.pantalla?.acciones) && e.pantalla.acciones.length > 0));
  // Una pregunta con acciones suelta el panel en la primera: la respuesta se demuestra en el mundo. La última escena no sale.
  const finHud = (e: Escena) => (e === escenas[escenas.length - 1] ? Infinity : (Array.isArray(e.pantalla?.acciones) && e.tipo === 'pregunta' ? (e.pantalla.acciones as { t: number }[])[0].t : e.fin) - 0.3);
  const hudDe = (e: Escena) => prog(ahora, e.inicio - 0.2, 0.35) * (1 - prog(ahora, finHud(e), 0.3));
  const velo = hay ? escenas.reduce((m, e) => (hudActivo(e) && e.tipo !== 'objetivo' ? Math.max(m, hudDe(e)) : m), 0) : 0;
  return (
    <CtxTema.Provider value={{ k, tema, ancho: width, alto: height, ahora }}>
      <AbsoluteFill style={{ color: tema.texto, fontFamily: INTER }}>
        {p.audio ? <Audio src={staticFile(p.audio)} /> : null}
        <Fondo cam={cam} f={frame} />
        <div style={{ position: 'absolute', left: width / 2, top: height / 2, width: 0, height: 0, transform: `scale(${cam.z * ajuste}) translate(${-cam.x}px, ${-cam.y}px)` }}>
          {actores.map((a) => <PintaActor key={a.id} a={a} p={pinta} op={ais.id === a.id ? 1 : 1 - ais.nivel} />)}
          {puntero2 ? <Cursor {...puntero2} z={cam.z} tema={tema} /> : null}
          {escenas.map((e, i) => {
            if (!esEstacion(e, hay) || e.tipo === 'screencast' || ahora < e.inicio - 1.4 || ahora > e.fin + 1.2) return null;
            const st = estacion(i, hay);
            return (
              <div key={e.id} style={{ position: 'absolute', left: st.x - width / 2, top: st.y - height / 2, width, height, scale: `${1 / ajuste}` }}>
                <Cuerpo e={e} p={p} t0={i === 0 ? e.inicio + 0.1 : e.inicio} plano="estacion" />
              </div>
            );
          })}
        </div>
        {velo > 0 ? <AbsoluteFill style={{ background: tema.fondo, opacity: velo * 0.93 }} /> : null}
        {escenas.map((e) => {
          if (!hudActivo(e) || e.tipo === 'screencast' || ahora < e.inicio - 0.3 || ahora > finHud(e) + 0.4) return null;
          return <AbsoluteFill key={e.id} style={{ opacity: hudDe(e) }}><Cuerpo e={e} p={p} t0={e.inicio} plano="mundo" /></AbsoluteFill>;
        })}
        {escenas.map((e) => {
          const lista = items(e.pantalla?.solucion ?? e.pantalla?.puntos);
          if ((hudActivo(e) && e.tipo !== 'pregunta') || esEstacion(e, hay) || !lista.length || ahora < e.inicio - 0.3 || ahora > e.fin + 0.1) return null;
          return <AbsoluteFill key={e.id} style={{ opacity: 1 - prog(ahora, e.fin - 0.3, 0.3) }}><Rotulos lista={lista} /></AbsoluteFill>;
        })}
        {escenas.map((e, i) => (e.tipo === 'screencast' ? (
          <Sequence key={e.id} from={ts[i].from} durationInFrames={ts[i].dur} name={`${e.id} screencast`}>
            <AbsoluteFill style={{ background: tema.fondo }}><OffthreadVideo src={staticFile(texto(e.pantalla?.clip))} muted style={{ width: '100%', height: '100%', objectFit: 'contain' }} /></AbsoluteFill>
          </Sequence>
        ) : null))}
        {p.subtitulos_quemados ? <Subtitulos cues={p.subtitulos ?? []} /> : null}
      </AbsoluteFill>
    </CtxTema.Provider>
  );
};
