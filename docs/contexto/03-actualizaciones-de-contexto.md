# Actualizaciones del contexto (motivo, cambio y archivo afectado)

## Actualización 1 — 04/10/2026: llegó el Excel real (v1 → v2)
- **Motivo:** la v1 se escribió solo con el enunciado; al recibir el archivo real se contrastaron los supuestos.
- **Hallazgos que cambiaron el contexto:** listas con rótulo «OPCIONES» en fila 111; atributos E:H sin combinar y repetidos por fila; dos filas de continuación sin código (42 y 67); códigos con 2 dígitos salvo SE.12; justificación del nombre canónico de SE.12 basada en evidencia (B100 coincide con el nombre del N2 SE.12.3).
- **Archivos:** `01-analisis-excel.md` (nuevo contenido), `AGENTS.md` §7 regla 3 (filas sin código ⇒ observación, no asignación).
- **Verificación:** importación del archivo real → 12 N1 / 46 N2, 4 observaciones (`docs/evidencias/importacion_excel_real.txt`).

## Actualización 2 — 04/10/2026: ejecución local con Docker por el catedrático (v2 → v3)
- **Motivo (cambio de decisión):** el estudiante indicó que el catedrático clonará y ejecutará todo localmente con Docker.
- **Cambios:** todo comando de `AGENTS.md` §5 pasa a ejecutarse con `docker compose`; se añadió el perfil `test` con base separada `catalogo_test`; se agregó la regla «no ejecutar `down -v` ni `DROP SCHEMA` fuera de pruebas»; el CLI espera a la BD y migra al arrancar (`catalogo.cli servir`); las pruebas dejaron de depender de códigos concretos del Excel (tras ver que el real usa `SE.01.01` y no `SE.01.1`).
- **Archivos:** `compose.yaml`, `Dockerfile`, `AGENTS.md` §4–5, `tests/*`.
