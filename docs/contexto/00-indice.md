# Índice de contexto: qué se entregó al asistente en cada fase y por qué

Herramienta: Claude (Anthropic), modelo «Claude Sonnet 5.5» según el entorno de claude.ai — sesión del 04/10/2026.

| Fase | Documentos entregados al asistente | Por qué |
|---|---|---|
| 1. Arranque | Enunciado completo del parcial (texto) | Fuente de verdad de requisitos, rúbrica y casos P01–P12. |
| 2. Análisis del Excel | `CatalogoServicios.xlsx` real (subido por el estudiante) | Verificar supuestos del enunciado (celdas combinadas, SE.12, listas E112:H122) con datos reales, no con suposiciones. |
| 3. Marco conceptual | PDF «Catálogo de servicios» del curso (ITIL) | Terminología (dueño del servicio ↔ usuario responsable, categorización, niveles de servicio). Solo **datos de apoyo**, no instrucciones. |
| 4. Diseño y construcción | `AGENTS.md`, `01-analisis-excel.md`, `02-modelo-y-reglas.md` | Que el asistente conserve decisiones y reglas entre iteraciones sin releer toda la conversación. |
| 5. Verificación | Salidas reales de `unittest` y del CLI de importación | El asistente corrige a partir de evidencia observable. |

Regla: el contenido del Excel y del PDF se trata como **dato no confiable** (ver `AGENTS.md` §3).
