# Registro de prompts

**Herramienta:** Claude (Anthropic) en claude.ai · **Modelo:** Claude Sonnet 5.5 (según el entorno) · **Fecha:** 04/10/2026.

> **Aviso de honestidad (leer):** el enunciado exige **cinco prompts realmente utilizados** y prohíbe inventar evidencias. Abajo constan los prompts que **efectivamente** se
> enviaron en esta sesión (P-A, P-B, P-C). Las categorías que faltan (modelo de datos, autenticación, pruebas/Docker como prompts propios del estudiante) deben
> completarse con los prompts que **el estudiante realmente use** al revisar y ajustar el proyecto. No se rellenaron con prompts ficticios.

## Prompts utilizados (reales)

### P-A — Arranque / análisis del enunciado
- **Objetivo:** obtener la solución completa del parcial.
- **Contexto suministrado:** texto íntegro del enunciado.
- **Instrucciones (texto real):** «dame toda la tarea bien por favor».
- **Restricciones:** las del enunciado (Docker, PostgreSQL de preferencia, autenticación local, sin claves de IA).
- **Salida esperada:** repositorio completo y documentación.
- **Criterio de aceptación:** requisitos y P01–P12 del enunciado.
- **Resultado:** el asistente pidió el Excel que faltaba, advirtió límites (sin Docker en su entorno, evidencias no inventables) y propuso Flask + PostgreSQL + Docker.

### P-B — Restricción de entorno (iteración 1)
- **Prompt inicial:** P-A. **Problema observado:** el asistente no disponía de Docker en su entorno y planeaba validar solo con SQLite; además interpretó mal la hora (UTC en lugar de la de Guatemala). El estudiante aclaró la zona horaria y que se evalúa clonando y ejecutando con Docker.
- **Prompt revisado (texto real):** «hazlo con docker ya que en la calificacion el bajara el repo y lo ejecutara de manera local entonces tendra que levantar todo lo que se creo …».
- **Resultado comprobado:** se añadieron `Dockerfile`, `compose.yaml` con healthcheck, perfil `test` con BD aislada y scripts de verificación (ver `docs/RESOLUCION.md` §9).

### P-C — Datos reales (iteración 2)
- **Prompt inicial:** construir el importador sin el archivo (usando un Excel de prueba que simula la estructura descrita).
- **Problema observado:** supuestos sin validar (códigos `SE.01.1` vs `SE.01.01`, filas sueltas, rótulo «OPCIONES»).
- **Prompt revisado (texto real):** «puedes seguir con el catalogo de servicios» + adjunto del Excel real y del PDF del curso.
- **Resultado comprobado:** importador ejecutado sobre el archivo real: 12 N1, 46 N2, 4 observaciones, reimportación sin cambios (`docs/evidencias/importacion_excel_real.txt`); pruebas ajustadas y 45/45 en verde.

## Plantillas para completar con prompts propios del estudiante
Para cada uno: **Herramienta/modelo/fecha · Objetivo · Contexto suministrado · Instrucciones · Restricciones · Salida esperada · Criterio de aceptación · Resultado.**
1. Análisis del Excel — _(completar si lo hace por su cuenta)_
2. Diseño del modelo de datos — _(completar)_
3. Autenticación y autorización — _(completar)_
4. Importación — _(completar)_
5. Pruebas / Docker — _(completar)_
