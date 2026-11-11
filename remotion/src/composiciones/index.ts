// Registro de composiciones. BASE = las versionadas en el repo; PROYECTOS = las de cada proyecto
// (remotion/src/composiciones/proyectos/<Nombre>.tsx, gitignored), listadas en registro.ts, que
// scripts/remotion.py regenera en cada `validar`/`render`. No editar registro.ts a mano.
import type { Entrada } from '../lib/props';
import { Composicion as Ejemplo, meta as metaEjemplo } from './Ejemplo';
import { Composicion as Ilustrado, meta as metaIlustrado } from './Ilustrado';
import { Composicion as Leccion, meta as metaLeccion } from './Leccion';
import { PROYECTOS } from './proyectos/registro';

export const BASE: Entrada[] = [
  { id: 'Ejemplo', component: Ejemplo, meta: metaEjemplo },
  { id: 'Leccion', component: Leccion, meta: metaLeccion },
  { id: 'Ilustrado', component: Ilustrado, meta: metaIlustrado },
];

export const COMPOSICIONES: Entrada[] = [...BASE, ...PROYECTOS];
