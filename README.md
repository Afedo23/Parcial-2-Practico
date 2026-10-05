# Parcial Software Avanzado — Sistema de gestión del catálogo de servicios de TI

Aplicación web (Python/Flask + PostgreSQL) que sistematiza el catálogo del Excel `data/CatalogoServicios.xlsx`,
incorpora la estructura organizacional (Empresa → Área → Departamento → Sección → Puesto → Usuario) y permite asignar
responsables a los servicios. Todo corre con Docker; no hace falta instalar Python ni PostgreSQL en el equipo.

- **Integrante:** _Carlos Alfredo Barrientos López_ — **Carné:** _202003948_
- **Rama de entrega:** `main` — **Etiqueta:** `parcial-v2.0` — **SHA final:** _(completar tras el último commit)_
- **Documentación de la resolución:** [`docs/RESOLUCION.md`](docs/RESOLUCION.md) · **Contexto para IA:** [`AGENTS.md`](AGENTS.md)

## Requisitos

| Herramienta | Versión mínima |
|---|---|
| Docker Engine / Docker Desktop | 24 |
| Docker Compose (plugin `docker compose`) | v2.20 |
| Puertos libres | `8000` (aplicación). PostgreSQL **no** se expone al host |

## Puesta en marcha (desde un clon limpio)

```bash
git clone <URL-del-repositorio> parcial-catalogo-servicios && cd parcial-catalogo-servicios
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
docker compose up --build -d
```

Al arrancar, el contenedor `app` espera a PostgreSQL (healthcheck), aplica las migraciones y sirve en **http://localhost:8000**.
Los valores de `.env.example` son de demostración y funcionan tal cual.

Luego cargue los datos (un solo comando que hace migrar → importar el Excel → crear cuentas → datos de demostración):

```bash
docker compose exec app python -m catalogo.cli demo
```

O por pasos:

```bash
docker compose exec app python -m catalogo.cli preparar          # migraciones (idempotente; también se ejecutan al arrancar)
docker compose exec app python -m catalogo.cli importar --detalle # importa data/CatalogoServicios.xlsx (repetible)
docker compose exec app python -m catalogo.cli cuentas            # crea administrador y consulta de evaluación
docker compose exec app python -m catalogo.cli datos-demo         # estructura de demostración + asignaciones de servicios
```

### Cuentas de evaluación

Se crean con las variables `DEMO_*` de `.env` (valores por defecto de `.env.example`):

| Rol | Usuario | Contraseña |
|---|---|---|
| administrador | `admin.demo` | `AdminDemo2026` |
| consulta | `consulta.demo` | `ConsultaDemo2026` |

`datos-demo` agrega los usuarios `ana.soporte` y `luis.monitoreo` (rol consulta, misma contraseña de consulta) y 4 servicios asignados
a secciones/responsables válidos. Son credenciales exclusivamente de demostración.

## Qué revisar en la interfaz

- **Servicios N2** (`/servicios/`): búsqueda por código y nombre, filtros (nivel 1, estado, clase, criticidad, tipo), paginación, ficha completa con trazabilidad y asignación de sección/usuario responsable.
- **Servicios N1**, **Organización** (5 niveles con altas, ediciones y bajas lógicas), **Usuarios** (solo el administrador modifica).
- **Importaciones**: resumen (creados/actualizados/omitidos/observados), controles 12/46, observaciones y mapeo de etiquetas.

## Pruebas

```bash
docker compose --profile test run --rm tests        # P01–P12 automatizados contra PostgreSQL (BD aislada «catalogo_test»)
bash scripts/p12_persistencia.sh                     # P12 de extremo a extremo: docker compose restart (PowerShell: scripts/p12_persistencia.ps1)
bash scripts/verificar.sh                            # rutina completa (compose config, build, pruebas, importación x2, demo, persistencia)
```

Las pruebas **no tocan** la base de datos de evaluación: usan `catalogo_test` y se niegan a operar sobre una base cuyo nombre no contenga «test».
Cobertura por escenario en [`docs/RESOLUCION.md`](docs/RESOLUCION.md#7-matriz-requisito--implementación--prueba--evidencia).

## Operación

```bash
docker compose logs -f app            # logs de la aplicación   (db: docker compose logs -f db)
docker compose ps                     # estado y healthchecks
docker compose stop                   # detener (conserva datos)
docker compose start                  # reanudar
docker compose restart                # reiniciar (conserva datos)
docker compose down                   # apagado NORMAL: elimina contenedores, CONSERVA el volumen pgdata
docker compose down -v                # REINICIO DESTRUCTIVO: borra también el volumen (todos los datos de prueba)
```

## Estructura

```
src/catalogo/      aplicación (app.py, db.py, security.py, org.py, usuarios.py, servicios.py, importador.py, cli.py, vistas/, templates/)
src/catalogo/migraciones/   SQL versionado (0001_inicial.sql)
tests/             pruebas unittest + generador del Excel de prueba (fixture_excel.py)
scripts/           harness: verificar.sh, p12_persistencia.sh/.ps1
data/CatalogoServicios.xlsx   Excel original (NO se modifica; se monta en solo lectura)
docs/              RESOLUCION.md, contexto/, prompts/, evidencias/
```

## Seguridad (resumen)

Contraseñas con **scrypt + sal aleatoria**; sesiones en servidor (token aleatorio, solo su SHA-256 en BD, invalidadas al cerrar sesión, al desactivar al usuario o al cambiar su contraseña); autorización por rol verificada en el servidor; CSRF en toda operación que modifica datos; cabeceras de seguridad. Detalle en `docs/RESOLUCION.md` §5.
