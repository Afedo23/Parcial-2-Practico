# Análisis del Excel real (`data/CatalogoServicios.xlsx`, SHA-256 `de3b478a5fae…`)

Hoja única «Servicios Externos». Encabezados `A4:L4` correctos. Filas de datos 5–101; listas de opciones en `E112:H122` (con rótulo «OPCIONES» en la fila 111, fuera del rango de valores).
Dimensión declarada A1:X1000 (hay 76 rangos combinados); no hay contenido fuera de A:L salvo las listas.

## Hallazgos que condicionan el importador
1. **Combinaciones**: `A`/`B` combinadas por servicio de nivel 1 (p. ej. `A5:A9`); `C`/`D`/`J` combinadas por servicio de nivel 2 (p. ej. `C5:C7`). Las columnas `E:H` **no** están combinadas: las filas subordinadas repiten el mismo valor (S / A DEMANDA / Normal / Back End). Se deduplica por servicio.
2. **Filas de continuación sin código fuera de combinación**: filas **42** (tras `C40:C41`) y **67** (tras `C63:C66`) traen atributos (E:H) pero ninguna celda de código ni nombre y no pertenecen a ningún rango combinado de código. Se reportan (`FILA_SIN_CODIGO`) y no se asignan a otro servicio.
3. **SE.12 (filas 99–101)**: A99=`SE.12`/B99=«Suministrar Analitica»; A100=`SE.12`/B100=«Mantener Tableros de Control»; la fila 101 no trae código N1. El nombre «Mantener Tableros de Control» es **también el nombre del N2 `SE.12.3`** (D101), lo que indica que B100 es un valor copiado/desplazado; por eso el nombre canónico del N1 es «Suministrar Analitica» (primera aparición, fila 99) y el otro queda como evidencia. La fila 101 se asigna a `SE.12` derivando el prefijo del código (observación `N1_DERIVADO`).
4. **Atributos incompletos (filas 99–101)**: E:L vacíos → importados como desconocidos (`NULL`) con `estado_revision = REVISION`.
5. **Formato de códigos**: N2 normales usan dos dígitos (`SE.01.01`) pero SE.12 usa un dígito (`SE.12.1`). Se conservan tal cual, como texto. (También se detectó un posible error tipográfico original: «Análsis» en D100; se conserva.)
6. **Listas**: ACTIVO {S, N}; clase {A DEMANDA, RECURRENTE}; criticidad {Very Low … Very High}; tipo (11 valores). Coinciden con el enunciado.
7. Controles: 12 códigos N1 y 46 códigos N2 distintos → **se cumplen**.
8. Texto inusual: la celda `I5` contiene «Revele su rollo »; se importa como descripción (dato), sin interpretarlo.
