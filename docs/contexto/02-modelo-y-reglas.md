# Modelo de datos y reglas (resumen operativo)

Ver diagrama ER y diccionario completo en `docs/RESOLUCION.md` §3. Tablas: `empresa`, `area`, `departamento`, `seccion`, `puesto`, `usuario`, `sesion`,
`cat_clase`, `cat_criticidad`, `cat_tipo`, `servicio_n1`, `servicio_n2`, `mapeo_etiquetas`, `import_ejecucion`, `import_observacion`, `migraciones`.

Decisiones: (1) SQL portable sin ORM para poder probar con SQLite y ejecutar en PostgreSQL; (2) sesiones en tabla propia (permite invalidar en el servidor);
(3) `indicador_activo` (columna ACTIVO del Excel, S/N/desconocido) es independiente de `activo` (baja lógica del sistema);
(4) usuario siempre pertenece a un puesto (su empresa se deduce de la jerarquía); (5) la política de desactivación es **bloquear** si hay dependientes activos.
