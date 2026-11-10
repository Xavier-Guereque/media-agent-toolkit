---
tags: [lecciones, cursos, cuestionario, reproductor, voz]
fecha_modificacion: 2026-11-01
estado: activo
---

# Lecciones — Cuestionario de arranque y modos de curso (2026-11-01)

**Pedido:** que el agente pregunte antes de crear un curso: evaluación, voz, visual y propósito. Tres opciones no existían, así que se extendió el motor además del prompt.

## Flujo que quedó

```mermaid
flowchart LR
    Q[Cuestionario en 3 bloques] --> M[curso.modo, voz, estilo]
    M --> V[validar con exenciones explícitas]
    V --> R[Render]
    R --> P[reproductor.html con prueba_final]
```

## Qué se aprendió

1. **Un prompt no debe ofrecer lo que el motor no hace:** revisar antes de redactar evitó publicar tres opciones falsas.
2. **Las exenciones viven en `curso.modo`:** el rigor solo se relaja por una decisión declarada; sin `modo`, el curso se valida igual que antes.
3. **`visual` sin declarar no exige nada:** `m1-l2` del ejemplo sigue sin mundo; declararlo habría roto la plantilla.
4. **`imgs` solo se veía en `caso`:** ahora también en `concepto`, `pasos`, `ejemplo` y `resumen`, y `W-CURSO-IMG-SIN-LUGAR` avisa si la escena no la muestra.
5. **Sin preguntas, el puntaje dividía entre cero:** la caja de avance se oculta.

## Medidas

| Prueba | Resultado |
|---|---|
| Pruebas Python (curso, narrar, remotion, enrutar, voz, comun, promo) | 99, 1 omitida, 0 fallas |
| `npm --prefix remotion test` | 19 de 19 |
| Humo con voz simulada: test entre lecciones, mixto, presentación | Los tres llegan a `reproductor.html` |
| Reproductor en navegador integrado, eventos simulados | Bloqueo, reintento y paso a la siguiente lección correctos |

## Preguntas de [[AGENT]] §15

**¿Cómo optimizar?** Probar el reproductor con `ended` simulado evita ver el video completo.

**¿Qué funciones nuevas usé?** Servidor con `Range` propio para el humo; `http.server` no lo trae. Conviene volverlo un comando del motor.

**Pendiente:** humo con voz real; revisar `.fila:disabled` en pantalla; `reproductor.html` contiene las respuestas correctas y el avance vive en `localStorage`, así que no sirve para constancias ni venta.

Relacionado: [[Motor-Curso]], [[Metodologia-Cursos-Video]], [[Lecciones-2026-11-01-cursos-mundo-continuo]].
