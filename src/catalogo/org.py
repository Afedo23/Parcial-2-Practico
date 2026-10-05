"""Estructura organizacional: Empresa → Área → Departamento → Sección → Puesto.

Política de desactivación (baja lógica, nunca borrado):
  * No se puede desactivar un registro con dependientes ACTIVOS (hijos, usuarios o servicios
    asignados). El sistema lo rechaza y explica qué debe resolverse primero.
  * No se crean ni se mueven registros hacia padres inactivos, ni se reactiva un registro
    cuyo padre está inactivo.
"""
from .db import IntegrityError
from .errores import ErrorValidacion
from .util import entero, paginar, texto

NIVELES = ["empresa", "area", "departamento", "seccion", "puesto"]
PADRE = {
    "area": ("empresa", "empresa_id"),
    "departamento": ("area", "area_id"),
    "seccion": ("departamento", "departamento_id"),
    "puesto": ("seccion", "seccion_id"),
}
HIJO = {"empresa": "area", "area": "departamento", "departamento": "seccion", "seccion": "puesto"}
ETIQUETA = {"empresa": "Empresa", "area": "Área", "departamento": "Departamento", "seccion": "Sección", "puesto": "Puesto"}
PLURAL = {"empresa": "Empresas", "area": "Áreas", "departamento": "Departamentos", "seccion": "Secciones", "puesto": "Puestos"}


def _ruta(nivel, alias="t"):
    """Expresión SQL con la ruta de ancestros (códigos) y los JOIN necesarios."""
    joins, partes, actual, n, i = [], [], alias, nivel, 0
    while n in PADRE:
        pn, fk = PADRE[n]
        a = f"p{i}"
        joins.append(f"JOIN {pn} {a} ON {a}.id = {actual}.{fk}")
        partes.insert(0, f"{a}.codigo")
        actual, n, i = a, pn, i + 1
    return (" || ' / ' || ".join(partes) if partes else "''"), " ".join(joins)


def listar(db, nivel, q=None, estado=None, padre_id=None, pagina=1, por_pagina=20):
    ruta, joins = _ruta(nivel)
    where, params = ["1 = 1"], []
    if q:
        where.append("(LOWER(t.codigo) LIKE ? OR LOWER(t.nombre) LIKE ?)")
        params += [f"%{q.lower()}%"] * 2
    if estado in ("activo", "inactivo"):
        where.append("t.activo = ?")
        params.append(estado == "activo")
    if padre_id and nivel in PADRE:
        where.append(f"t.{PADRE[nivel][1]} = ?")
        params.append(padre_id)
    cond = " AND ".join(where)
    total = db.valor(f"SELECT COUNT(*) FROM {nivel} t {joins} WHERE {cond}", params)
    pg = paginar(total, pagina, por_pagina)
    filas = db.consultar(
        f"SELECT t.*, {ruta} AS ruta FROM {nivel} t {joins} WHERE {cond} ORDER BY ruta, t.codigo LIMIT ? OFFSET ?",
        params + [por_pagina, pg["offset"]],
    )
    return filas, pg


def obtener(db, nivel, id_):
    ruta, joins = _ruta(nivel)
    return db.uno(f"SELECT t.*, {ruta} AS ruta FROM {nivel} t {joins} WHERE t.id = ?", (id_,))


def opciones_padre(db, nivel, incluir_id=None):
    """Padres seleccionables: solo activos (más el actual al editar)."""
    pn, _ = PADRE[nivel]
    ruta, joins = _ruta(pn)
    cond, params = "t.activo = ?", [True]
    if incluir_id:
        cond, params = "(t.activo = ? OR t.id = ?)", [True, incluir_id]
    return db.consultar(
        f"SELECT t.id, t.codigo, t.nombre, {ruta} AS ruta FROM {pn} t {joins} WHERE {cond} ORDER BY ruta, t.codigo", params
    )


def _validar_padre(db, nivel, padre_id, padre_actual=None):
    pn, _ = PADRE[nivel]
    padre = db.uno(f"SELECT id, activo FROM {pn} WHERE id = ?", (padre_id,))
    if not padre:
        raise ErrorValidacion(f"El registro padre ({ETIQUETA[pn]}) no existe.")
    if not padre["activo"] and padre_id != padre_actual:
        raise ErrorValidacion(f"No se puede asociar a un {ETIQUETA[pn].lower()} inactivo.")


def _datos(db, nivel, form, actual=None):
    codigo = texto(form.get("codigo"), "Código", maximo=30).upper()
    nombre = texto(form.get("nombre"), "Nombre", maximo=200)
    datos = {"codigo": codigo, "nombre": nombre}
    if nivel in PADRE:
        fk = PADRE[nivel][1]
        padre_id = entero(form.get(fk), ETIQUETA[PADRE[nivel][0]])
        _validar_padre(db, nivel, padre_id, actual[fk] if actual else None)
        datos[fk] = padre_id
    # unicidad: global (empresa) o dentro del padre
    params, cond = [codigo], "codigo = ?"
    if nivel in PADRE:
        cond += f" AND {PADRE[nivel][1]} = ?"
        params.append(datos[PADRE[nivel][1]])
    if actual:
        cond += " AND id <> ?"
        params.append(actual["id"])
    if db.uno(f"SELECT id FROM {nivel} WHERE {cond}", params):
        donde = "" if nivel == "empresa" else " dentro del mismo padre"
        raise ErrorValidacion(f"Ya existe un registro con el código «{codigo}»{donde}.")
    return datos


def crear(db, nivel, form):
    datos = _datos(db, nivel, form)
    cols = list(datos) + ["activo"]
    try:
        with db.tx():
            return db.insertar(
                f"INSERT INTO {nivel} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [datos[c] for c in datos] + [True],
            )
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: valor duplicado o referencia inexistente.") from None


def actualizar(db, nivel, id_, form):
    actual = db.uno(f"SELECT * FROM {nivel} WHERE id = ?", (id_,))
    if not actual:
        raise ErrorValidacion("El registro no existe.")
    datos = _datos(db, nivel, form, actual)
    if nivel == "puesto" and datos["seccion_id"] != actual["seccion_id"]:
        _validar_responsables_puesto(db, id_, datos["seccion_id"])
    try:
        with db.tx():
            sets = ", ".join(f"{c} = ?" for c in datos)
            db.ejecutar(f"UPDATE {nivel} SET {sets} WHERE id = ?", list(datos.values()) + [id_])
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: valor duplicado o referencia inexistente.") from None


def _validar_responsables_puesto(db, puesto_id, nueva_seccion):
    n = db.valor(
        """SELECT COUNT(*) FROM servicio_n2 s JOIN usuario u ON u.id = s.usuario_id
           WHERE u.puesto_id = ? AND s.seccion_id <> ?""",
        (puesto_id, nueva_seccion),
    )
    if n:
        raise ErrorValidacion(
            f"No se puede mover el puesto: {n} servicio(s) tienen como responsable a un usuario de este puesto "
            "y pertenecen a otra sección. Reasigne primero esos servicios."
        )


def dependencias_activas(db, nivel, id_):
    msgs = []
    if nivel in HIJO:
        hijo = HIJO[nivel]
        n = db.valor(f"SELECT COUNT(*) FROM {hijo} WHERE {PADRE[hijo][1]} = ? AND activo = ?", (id_, True))
        if n:
            msgs.append(f"{n} {PLURAL[hijo].lower()} activos")
    if nivel == "puesto":
        n = db.valor("SELECT COUNT(*) FROM usuario WHERE puesto_id = ? AND activo = ?", (id_, True))
        if n:
            msgs.append(f"{n} usuarios activos")
    if nivel == "seccion":
        n = db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE seccion_id = ? AND activo = ?", (id_, True))
        if n:
            msgs.append(f"{n} servicios activos asignados")
    return msgs


def cambiar_estado(db, nivel, id_, activo):
    actual = db.uno(f"SELECT * FROM {nivel} WHERE id = ?", (id_,))
    if not actual:
        raise ErrorValidacion("El registro no existe.")
    if activo:
        if nivel in PADRE:
            pn, fk = PADRE[nivel]
            if not db.valor(f"SELECT activo FROM {pn} WHERE id = ?", (actual[fk],)):
                raise ErrorValidacion(f"No se puede reactivar: su {ETIQUETA[pn].lower()} está inactivo.")
    else:
        deps = dependencias_activas(db, nivel, id_)
        if deps:
            raise ErrorValidacion(
                "No se puede desactivar porque tiene " + " y ".join(deps) + ". Desactive o reasigne primero esos registros."
            )
    with db.tx():
        db.ejecutar(f"UPDATE {nivel} SET activo = ? WHERE id = ?", (activo, id_))
