# CMDB — fuentes, jerarquía, modelo y decisiones

## 1. Fuentes y cómo se usan
| Fuente | Qué aporta | Tratamiento |
|---|---|---|
| `data/CMDB.xlsx` (hoja «CMDB», encabezados B4:U4, datos filas 5–6) | **2 CI reales**: «Servidor1» (Hardware) y «Aplicación» (Software); 20 campos | Se importa como **fuente de datos real** (`catalogo.cli importar-cmdb`). **No** es plantilla para inventar dispositivos. |
| Presentación de Transición, diap. 12 (SACM/CMDB) | 9 grupos de campos que una CMDB «debería contemplar» | Se contrasta con los 20 encabezados del Excel (§3). |
| Presentación de Transición, diap. 14 | Anidamiento SKMS ⊃ CMS ⊃ CMDB y KEDB | Contexto conceptual; **no** es una clasificación de CI y no se modela como jerarquía de dispositivos. |
| Indicación recibida por nota de voz (28/10/2026) | Cómo tratar el Excel: validar encabezados; Hardware y Software como categorías de origen; código estable y referencia a la fila; «Base de Datos1» sin CI ⇒ texto + observación y **sin relación inventada**; los 5,000 dispositivos son sintéticos y se generan aparte | Implementado y probado. **Confirme su procedencia** (el audio no identifica al emisor) antes de citarla como instrucción del catedrático. |

## 2. Jerarquía de clasificación
- **Categorías de origen (Excel):** `Hardware` (`CLS-HARDWARE`) y `Software` (`CLS-SOFTWARE`), nivel 1, `origen = EXCEL`, tomadas del campo «Tipo de CI».
- **Subcategorías (Proyecto):** necesarias para repartir los dispositivos sintéticos; `origen = PROYECTO`, creadas por `generar-cmdb`.
  Hardware → Servidores {Servidor físico, Servidor virtual} · Equipos de red {Switch, Router, Firewall} · Puestos de usuario {Estación de trabajo, Laptop} · Periféricos {Impresora} · Infraestructura de soporte {Almacenamiento, UPS}. Software → Aplicación · Base de datos · Sistema operativo.
- **Limitación a resolver con el catedrático:** el enunciado pide reproducir «los niveles, denominaciones y relaciones de la lección 22 y de CMDB.xlsx». Los archivos disponibles solo dan Hardware/Software; la lección 22 no se recibió como material aparte y la propia nota del enunciado indica que no se pudo verificar. Las subcategorías de Proyecto **no** se presentan como transcripción de ninguna fuente. Si la lección 22 define otros niveles, se cargan cambiando los datos de `HARDWARE_ARBOL`/`SOFTWARE_ARBOL` en `cmdb.py` sin tocar el resto.
- Reglas: padre inexistente ⇒ rechazo; ciclos en la jerarquía ⇒ rechazo (`mover_clasificacion`); las categorías de origen no se reubican. Prueba P04.

## 3. Correspondencia Excel ↔ diapositiva 12 ↔ base de datos
| Grupo (diap. 12) | Columnas del Excel | Campos en `cmdb_ci` |
|---|---|---|
| Identificación (Id, Tipo) | B «Nombre del CI», C «Tipo de CI» | `nombre`, `clasificacion_id` (+ **`codigo`**, agregado: el Excel no trae Id) |
| Atributos | D Descripción, E Número de Serie, F Versión, G Fecha de Adquisición, H Estado Actual | `descripcion`, `numero_serie`, `version`, `fecha_adquisicion`, `estado_actual` |
| Relaciones y dependencias | I Relaciones, J Padres/Hijos | `relaciones_texto`, `padres_hijos_texto` (texto original) + tabla `cmdb_relacion` |
| Ubicación y asignación | K Ubicación Física, L Propietario/Responsable | `ubicacion_texto`, `propietario_texto` |
| Historial de cambios | M Fecha de Cambio, N Descripción del Cambio | `fecha_cambio`, `descripcion_cambio` |
| Documentación y enlaces | O Documentación relacionada, P Enlaces a Incidentes y Problemas | `documentacion_texto`, `enlaces_texto` |
| Seguridad y cumplimiento | Q Niveles de Seguridad, R Cumplimiento | `nivel_seguridad`, `cumplimiento` |
| Estado de configuración | S | `estado_configuracion` |
| Licencias | T Número de Licencia, U Fecha de Vencimiento | `numero_licencia`, `fecha_vencimiento` |

**Campos agregados por el proyecto (no vienen del Excel):** `codigo`, `origen`, `origen_hoja`, `origen_fila`, `origen_json`, `ubicacion_id` (catálogo de ubicaciones), `responsable_usuario_id`, `atributos_json` (atributos técnicos por clase, solo sintéticos), `activo` (baja lógica), `creado`, `actualizado`; tablas `cmdb_clasificacion`, `cmdb_ubicacion`, `cmdb_relacion`, `cmdb_ci_servicio`.

## 4. Importación de CMDB.xlsx (reglas)
1. Valida los 20 encabezados (B4:U4). Dos vienen con mala codificación («Configuraci√≥n», «N√∫mero»): se reparan y la corrección queda en `mapeo_etiquetas`. Encabezado distinto ⇒ error (código de salida 2) y no se importa nada.
2. «Tipo de CI» ⇒ categoría de origen. Fila sin nombre o sin tipo ⇒ se omite con observación.
3. **Código estable:** `CI-XLS-<NOMBRE>` (p. ej. `CI-XLS-SERVIDOR1`); guarda hoja y fila de origen y los valores originales (`origen_json`). Repetir la importación no crea ni actualiza nada.
4. **«Base de Datos1»** (columna Relaciones de las dos filas): no existe CI con ese nombre ⇒ se conserva el texto y se registra `RELACION_SIN_CI`; **no se crea relación**. Si un texto coincidiera con un CI existente, se crea una relación `relacionado_con` (el Excel no indica el tipo) con observación `RELACION_SIN_TIPO`.
5. Otras observaciones reales: `UBICACION_ES_CI` («Servidor1» como ubicación del CI «Aplicación», se conserva como texto) y `ENLACE_MARCADOR` (enlaces con el marcador literal «(url)»).
6. Resultado sobre el archivo real: 2 CI creados, 2 categorías, 0 relaciones, 5 observaciones (`docs/evidencias/importacion_cmdb.txt`).

## 5. Datos sintéticos (aparte, `origen = SINTETICO`)
- `python -m catalogo.cli generar-cmdb --semilla 2026 --dispositivos 5000`: **5,000 dispositivos de hardware** (más 400 CI de software que no cuentan como «dispositivos»). Requiere haber importado el catálogo de servicios, CMDB.xlsx y tener usuarios (códigos de salida 4/3 si no).
- **Reproducible:** los códigos (`CI-SYN-<clase>-<n>`) no dependen de la semilla; los atributos sí, derivados de `Random(semilla:código)`. Misma semilla ⇒ 0 cambios. Otra semilla ⇒ **actualiza** los mismos CI (no duplica). Las relaciones y vínculos con servicios son deterministas y solo se agregan.
- Atributos coherentes por clase (p. ej. IP única solo en servidores, switches, routers, firewalls, almacenamiento e impresoras de red; estaciones, laptops y UPS **sin IP**). Sin datos personales (propietarios «Equipo sintético NN»; responsables = usuarios existentes).
- **Borrado explícito, separado del arranque:** `borrar-cmdb-sinteticos --confirmar` (no toca los CI del Excel).
- Reporte: `reporte-cmdb` (cantidades por nivel y categoría; el total de dispositivos cuenta solo hardware sintético, no filas de catálogos ni relaciones).

## 6. Relaciones y recorrido
- Tipos: `depende_de`, `alojado_en` (**sin ciclos**, validados juntos como dirección de dependencia), `conectado_a` y `relacionado_con` (**admiten ciclos**). `crear_relacion` rechaza ciclos directos e indirectos; `validar_aciclico` (Kahn) comprueba todo el grafo tras la carga.
- Recorrido inverso (`servicios_potencialmente_afectados`): desde un CI, quién depende de él directa o indirectamente y qué servicios tienen vinculados; muestra distancia y el aviso de que la dependencia **no implica** una interrupción efectiva.
- Pendiente: vinculación CI–ticket (el módulo de tickets no forma parte de esta entrega).

## 7. Pruebas (`tests/test_cmdb.py`)
| ID | Qué verifica |
|---|---|
| P03 | 5,000 dispositivos únicos (códigos y series), repetición sin duplicados, misma semilla ⇒ mismos datos, IP solo donde aplica |
| P04 | Categorías de origen del Excel, padre inexistente y ciclos de clasificación rechazados |
| P14 | Recorrido CI–servicio; ciclos según tipo de relación |
| P16 | Filtros y paginación sobre 5,000 dispositivos, con **tiempos medidos** y entorno impresos por la prueba (SQLite local; repetir en Docker/PostgreSQL antes de citar cifras) |
| — | Excel: relación no inventada, encabezados inválidos, mojibake, idempotencia; interfaz y permisos |
