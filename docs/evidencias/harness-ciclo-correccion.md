# Evidencia de harness: ciclo completo tarea → cambio de IA → controles → fallo → corrección → éxito

> Fallo **no deliberado**: ocurrió durante la construcción (04/10/2026) y fue detectado por las pruebas.

1. **Tarea:** implementar autenticación y plantillas con protección CSRF.
2. **Cambio propuesto por la IA:** macros Jinja (`macros.html`) con `csrf_token()` importadas con `{% import "macros.html" as m %}`.
3. **Control ejecutado:** `python -m unittest discover -s tests -p "test_auth.py"`.
4. **Fallo detectado:** `FAILED (failures=5)`; las respuestas eran HTTP 500. Traza reproducida con `PROPAGATE_EXCEPTIONS`:
   `jinja2.exceptions.UndefinedError: 'csrf_token' is undefined` (las macros importadas no ven el contexto por defecto).
5. **Corrección:** `{% import "macros.html" as m with context %}` en `base.html`.
6. **Nueva ejecución:** `Ran 13 tests ... OK`. Posteriormente la suite completa: `Ran 45 tests ... OK (skipped=1)` (`pruebas_local_sqlite.txt`).

Otros controles del harness: `scripts/verificar.sh` (exit ≠ 0 ante fallo), reimportación idempotente comprobada por `grep`, y guardia que impide reiniciar bases cuyo nombre no contenga «test».
