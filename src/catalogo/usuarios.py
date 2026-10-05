"""Gestión de usuarios. Nunca se devuelve ``password_hash`` a las vistas."""
from .db import IntegrityError, ahora
from .errores import ErrorValidacion
from .security import MIN_PASSWORD, ROLES, hash_password
from .util import LOGIN_RE, entero, paginar, texto

COLUMNAS = """u.id, u.nombre, u.login, u.rol, u.activo, u.puesto_id, u.creado,
  p.codigo AS puesto_codigo, p.nombre AS puesto_nombre, s.id AS seccion_id, s.codigo AS seccion_codigo,
  d.codigo AS depto_codigo, a.codigo AS area_codigo, e.codigo AS empresa_codigo, e.nombre AS empresa_nombre"""
JOINS = """JOIN puesto p ON p.id = u.puesto_id JOIN seccion s ON s.id = p.seccion_id
  JOIN departamento d ON d.id = s.departamento_id JOIN area a ON a.id = d.area_id JOIN empresa e ON e.id = a.empresa_id"""


def listar(db, q=None, estado=None, rol=None, pagina=1, por_pagina=20):
    where, params = ["1 = 1"], []
    if q:
        where.append("(LOWER(u.nombre) LIKE ? OR LOWER(u.login) LIKE ?)")
        params += [f"%{q.lower()}%"] * 2
    if estado in ("activo", "inactivo"):
        where.append("u.activo = ?")
        params.append(estado == "activo")
    if rol in ROLES:
        where.append("u.rol = ?")
        params.append(rol)
    cond = " AND ".join(where)
    total = db.valor(f"SELECT COUNT(*) FROM usuario u {JOINS} WHERE {cond}", params)
    pg = paginar(total, pagina, por_pagina)
    filas = db.consultar(
        f"SELECT {COLUMNAS} FROM usuario u {JOINS} WHERE {cond} ORDER BY u.nombre LIMIT ? OFFSET ?", params + [por_pagina, pg["offset"]]
    )
    return filas, pg


def obtener(db, id_):
    return db.uno(f"SELECT {COLUMNAS} FROM usuario u {JOINS} WHERE u.id = ?", (id_,))


def opciones_puesto(db, incluir_id=None):
    cond, params = "p.activo = ?", [True]
    if incluir_id:
        cond, params = "(p.activo = ? OR p.id = ?)", [True, incluir_id]
    return db.consultar(
        f"""SELECT p.id, p.codigo, p.nombre, e.codigo || ' / ' || a.codigo || ' / ' || d.codigo || ' / ' || s.codigo AS ruta
            FROM puesto p JOIN seccion s ON s.id = p.seccion_id JOIN departamento d ON d.id = s.departamento_id
            JOIN area a ON a.id = d.area_id JOIN empresa e ON e.id = a.empresa_id WHERE {cond} ORDER BY ruta, p.codigo""",
        params,
    )


def _validar_puesto(db, puesto_id, actual=None):
    p = db.uno("SELECT id, activo, seccion_id FROM puesto WHERE id = ?", (puesto_id,))
    if not p:
        raise ErrorValidacion("El puesto seleccionado no existe.")
    if not p["activo"] and not (actual and actual["puesto_id"] == puesto_id):
        raise ErrorValidacion("No se puede asignar un usuario a un puesto inactivo.")
    return p


def _validar_password(pw):
    if len(pw or "") < MIN_PASSWORD:
        raise ErrorValidacion(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres.")


def _admins_activos(db):
    return db.valor("SELECT COUNT(*) FROM usuario WHERE rol = ? AND activo = ?", ("administrador", True))


def crear(db, form):
    nombre = texto(form.get("nombre"), "Nombre", maximo=200)
    login = (texto(form.get("login"), "Usuario o correo", maximo=150) or "").lower()
    if not LOGIN_RE.match(login):
        raise ErrorValidacion("El usuario/correo solo admite letras, números y . _ @ + - (3 a 150 caracteres).")
    rol = form.get("rol")
    if rol not in ROLES:
        raise ErrorValidacion("Rol inválido.")
    puesto_id = entero(form.get("puesto_id"), "Puesto")
    _validar_puesto(db, puesto_id)
    _validar_password(form.get("password"))
    if db.uno("SELECT id FROM usuario WHERE login = ?", (login,)):
        raise ErrorValidacion(f"Ya existe un usuario «{login}».")
    try:
        with db.tx():
            return db.insertar(
                "INSERT INTO usuario (nombre, login, password_hash, rol, activo, puesto_id, creado) VALUES (?,?,?,?,?,?,?)",
                (nombre, login, hash_password(form["password"]), rol, True, puesto_id, ahora()),
            )
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: usuario duplicado o puesto inexistente.") from None


def _validar_consistencia_responsable(db, usuario_id, seccion_destino):
    n = db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE usuario_id = ? AND seccion_id <> ?", (usuario_id, seccion_destino))
    if n:
        raise ErrorValidacion(
            f"El usuario es responsable de {n} servicio(s) de otra sección; reasígnelos antes de cambiarlo de puesto."
        )


def actualizar(db, id_, form, actor_id):
    actual = db.uno("SELECT * FROM usuario WHERE id = ?", (id_,))
    if not actual:
        raise ErrorValidacion("El usuario no existe.")
    nombre = texto(form.get("nombre"), "Nombre", maximo=200)
    rol = form.get("rol")
    if rol not in ROLES:
        raise ErrorValidacion("Rol inválido.")
    puesto_id = entero(form.get("puesto_id"), "Puesto")
    p = _validar_puesto(db, puesto_id, actual)
    if puesto_id != actual["puesto_id"]:
        _validar_consistencia_responsable(db, id_, p["seccion_id"])
    if actual["rol"] == "administrador" and rol != "administrador" and actual["activo"] and _admins_activos(db) <= 1:
        raise ErrorValidacion("No se puede quitar el rol al último administrador activo.")
    pw = form.get("password")
    sets, params = ["nombre = ?", "rol = ?", "puesto_id = ?"], [nombre, rol, puesto_id]
    if pw:
        _validar_password(pw)
        sets.append("password_hash = ?")
        params.append(hash_password(pw))
    with db.tx():
        db.ejecutar(f"UPDATE usuario SET {', '.join(sets)} WHERE id = ?", params + [id_])
        if pw:  # al cambiar la contraseña se invalidan las sesiones abiertas
            db.ejecutar("DELETE FROM sesion WHERE usuario_id = ?", (id_,))


def cambiar_estado(db, id_, activo, actor_id):
    actual = db.uno("SELECT * FROM usuario WHERE id = ?", (id_,))
    if not actual:
        raise ErrorValidacion("El usuario no existe.")
    if activo:
        if not db.valor("SELECT activo FROM puesto WHERE id = ?", (actual["puesto_id"],)):
            raise ErrorValidacion("No se puede reactivar: su puesto está inactivo.")
    else:
        if id_ == actor_id:
            raise ErrorValidacion("No puede desactivar su propia cuenta.")
        if actual["rol"] == "administrador" and _admins_activos(db) <= 1:
            raise ErrorValidacion("No se puede desactivar al último administrador activo.")
        n = db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE usuario_id = ? AND activo = ?", (id_, True))
        if n:
            raise ErrorValidacion(f"No se puede desactivar: es responsable de {n} servicio(s) activos. Reasígnelos primero.")
    with db.tx():
        db.ejecutar("UPDATE usuario SET activo = ? WHERE id = ?", (activo, id_))
        if not activo:
            db.ejecutar("DELETE FROM sesion WHERE usuario_id = ?", (id_,))
