"""Comandos operativos: ``python -m catalogo.cli <comando>``.

Códigos de salida: 0 éxito · 1 error inesperado · 2 archivo Excel inválido · 3 controles 12/46 no cumplidos
                   4 prerrequisito faltante (p. ej. no se ha importado) · 5 configuración faltante
"""
import argparse
import json
import os
import sys

from . import org, servicios, usuarios
from .db import Conexion, esperar_bd, migrar
from .errores import ErrorValidacion
from .importador import ErrorImportacion, importar

EMPRESA = ("DEMO", "Empresa Demo")


def _url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: falta DATABASE_URL (copie .env.example a .env).", file=sys.stderr)
        raise SystemExit(5)
    return url


def _conn():
    return Conexion(_url())


def cmd_preparar(_a):
    esperar_bd(_url())
    c = _conn()
    aplicadas = migrar(c)
    c.cerrar()
    print("Migraciones aplicadas:", aplicadas or "ninguna pendiente")
    return 0


def cmd_servir(a):
    cmd_preparar(a)
    args = ["gunicorn", "-b", f"0.0.0.0:{os.environ.get('PORT', '8000')}", "-w", os.environ.get("WEB_CONCURRENCY", "2"),
            "--access-logfile", "-", "catalogo:create_app()"]
    os.execvp("gunicorn", args)


def cmd_importar(a):
    esperar_bd(_url())
    c = _conn()
    migrar(c)
    ruta = getattr(a, "archivo", None) or os.environ.get("IMPORT_FILE", "data/CatalogoServicios.xlsx")
    try:
        resumen, obs = importar(c, ruta)
    except ErrorImportacion as e:
        print(f"ERROR de importación: {e}", file=sys.stderr)
        return 2
    finally:
        c.cerrar()
    print(f"Importación #{resumen['ejecucion_id']} de {resumen['archivo']} (sha256 {resumen['sha256'][:12]}…)")
    for k in ("n1", "n2"):
        s = resumen[k]
        print(f"  Nivel {k[1]}: creados={s['creados']} actualizados={s['actualizados']} omitidos={s['omitidos']} observados={s['observados']}")
    print("  Filas:", resumen["filas"])
    print("  Controles:", resumen["controles"])
    print(f"  Observaciones ({resumen['observaciones']}): {json.dumps(resumen['por_tipo'], ensure_ascii=False)}")
    if getattr(a, "detalle", False):
        for o in obs:
            print(f"   - [{o['tipo']}] {o['codigo'] or '-'} {o['rango']}: {o['detalle']}")
    if not resumen["controles"]["ok"]:
        print("ATENCIÓN: no se cumplen los controles 12 N1 / 46 N2 (los datos se guardaron; revise las observaciones).", file=sys.stderr)
        return 3
    return 0


def _id_o_crear(c, nivel, codigo, nombre, padre=None):
    fk = org.PADRE[nivel][1] if nivel in org.PADRE else None
    cond, p = "codigo = ?", [codigo]
    if fk:
        cond, p = cond + f" AND {fk} = ?", p + [padre]
    fila = c.uno(f"SELECT id FROM {nivel} WHERE {cond}", p)
    if fila:
        return fila["id"]
    form = {"codigo": codigo, "nombre": nombre}
    if fk:
        form[fk] = str(padre)
    return org.crear(c, nivel, form)


def _usuario(c, login, nombre, rol, puesto, password):
    if c.uno("SELECT id FROM usuario WHERE login = ?", (login,)):
        return False
    usuarios.crear(c, {"nombre": nombre, "login": login, "password": password, "rol": rol, "puesto_id": str(puesto)})
    return True


def cmd_cuentas(_a):
    """Crea (si no existen) la organización mínima y las cuentas de evaluación de ambos roles."""
    pw_admin, pw_cons = os.environ.get("DEMO_ADMIN_PASSWORD"), os.environ.get("DEMO_CONSULTA_PASSWORD")
    if not pw_admin or not pw_cons:
        print("ERROR: defina DEMO_ADMIN_PASSWORD y DEMO_CONSULTA_PASSWORD (ver .env.example).", file=sys.stderr)
        return 5
    esperar_bd(_url())
    c = _conn()
    migrar(c)
    try:
        e = _id_o_crear(c, "empresa", *EMPRESA)
        a = _id_o_crear(c, "area", "TI", "Tecnología", e)
        d = _id_o_crear(c, "departamento", "OPS", "Operaciones TI", a)
        s = _id_o_crear(c, "seccion", "SOP", "Soporte", d)
        p = _id_o_crear(c, "puesto", "ADM", "Administrador de plataforma", s)
        la, lc = os.environ.get("DEMO_ADMIN_LOGIN", "admin.demo"), os.environ.get("DEMO_CONSULTA_LOGIN", "consulta.demo")
        for login, nombre, rol, pw in ((la, "Administrador Demo", "administrador", pw_admin), (lc, "Consulta Demo", "consulta", pw_cons)):
            print(f"  {login} ({rol}):", "creado" if _usuario(c, login, nombre, rol, p, pw) else "ya existía (no se modifica)")
    except ErrorValidacion as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 1
    finally:
        c.cerrar()
    return 0


def cmd_datos_demo(_a):
    """Completa la estructura de demostración y crea asignaciones válidas de servicios (mínimo 3)."""
    pw = os.environ.get("DEMO_CONSULTA_PASSWORD")
    if not pw:
        print("ERROR: defina DEMO_CONSULTA_PASSWORD (ver .env.example).", file=sys.stderr)
        return 5
    esperar_bd(_url())
    c = _conn()
    migrar(c)
    try:
        if not c.valor("SELECT COUNT(*) FROM servicio_n2"):
            print("ERROR: no hay servicios; ejecute primero el comando importar.", file=sys.stderr)
            return 4
        if cmd_cuentas(_a) != 0:
            return 5
        e = c.valor("SELECT id FROM empresa WHERE codigo = ?", (EMPRESA[0],))
        a = c.valor("SELECT id FROM area WHERE codigo = ? AND empresa_id = ?", ("TI", e))
        d = c.valor("SELECT id FROM departamento WHERE codigo = ? AND area_id = ?", ("OPS", a))
        sop = c.valor("SELECT id FROM seccion WHERE codigo = ? AND departamento_id = ?", ("SOP", d))
        mon = _id_o_crear(c, "seccion", "MON", "Monitoreo", d)
        p_ana = _id_o_crear(c, "puesto", "ANL", "Analista de soporte", sop)
        p_ope = _id_o_crear(c, "puesto", "OPE", "Operador de monitoreo", mon)
        _usuario(c, "ana.soporte", "Ana Soporte", "consulta", p_ana, pw)
        _usuario(c, "luis.monitoreo", "Luis Monitoreo", "consulta", p_ope, pw)
        u_ana = c.valor("SELECT id FROM usuario WHERE login = ?", ("ana.soporte",))
        u_luis = c.valor("SELECT id FROM usuario WHERE login = ?", ("luis.monitoreo",))
        candidatos = c.consultar("SELECT id, codigo FROM servicio_n2 WHERE seccion_id IS NULL AND activo = ? ORDER BY codigo LIMIT 4", (True,))
        plan = [(sop, u_ana), (mon, u_luis), (sop, None), (mon, u_luis)]
        for srv, (sec, usr) in zip(candidatos, plan):
            servicios.asignar(c, srv["id"], sec, usr)
            print(f"  {srv['codigo']} → sección {sec}, responsable {usr or 'sin responsable'}")
        print("Asignaciones totales:", c.valor("SELECT COUNT(*) FROM servicio_n2 WHERE seccion_id IS NOT NULL"))
    except ErrorValidacion as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 1
    finally:
        c.cerrar()
    return 0


def cmd_demo(a):
    """Atajo: migrar + importar + cuentas + datos de demostración."""
    for f in (cmd_preparar, cmd_importar, cmd_datos_demo):
        codigo = f(a)
        if codigo not in (0, 3):  # 3 = controles; se informa pero se continúa
            return codigo
    return 0


def cmd_persistencia(a):
    """Apoyo a P12: crea / verifica un registro marcador que debe sobrevivir al reinicio de contenedores."""
    esperar_bd(_url())
    c = _conn()
    migrar(c)
    try:
        if a.accion == "crear":
            _id_o_crear(c, "empresa", "PERSIST-P12", "Marcador de persistencia P12")
            print("Marcador creado.")
            return 0
        ok = c.uno("SELECT id FROM empresa WHERE codigo = ?", ("PERSIST-P12",)) is not None
        print("Marcador presente tras el reinicio." if ok else "FALLO: el marcador no existe.")
        return 0 if ok else 1
    finally:
        c.cerrar()


def main(argv=None):
    p = argparse.ArgumentParser(prog="catalogo.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preparar", help="espera la BD y aplica migraciones").set_defaults(f=cmd_preparar)
    sub.add_parser("servir", help="prepara y arranca gunicorn").set_defaults(f=cmd_servir)
    i = sub.add_parser("importar", help="importa data/CatalogoServicios.xlsx (repetible)")
    i.add_argument("--archivo")
    i.add_argument("--detalle", action="store_true", help="imprime cada observación")
    i.set_defaults(f=cmd_importar)
    sub.add_parser("cuentas", help="crea cuentas de evaluación (administrador y consulta)").set_defaults(f=cmd_cuentas)
    sub.add_parser("datos-demo", help="estructura de demostración y asignaciones").set_defaults(f=cmd_datos_demo)
    sub.add_parser("demo", help="preparar + importar + cuentas + datos-demo").set_defaults(f=cmd_demo)
    pe = sub.add_parser("persistencia", help="marcador para la prueba P12")
    pe.add_argument("accion", choices=["crear", "verificar"])
    pe.set_defaults(f=cmd_persistencia)
    a = p.parse_args(argv)
    try:
        return a.f(a)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR inesperado: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
