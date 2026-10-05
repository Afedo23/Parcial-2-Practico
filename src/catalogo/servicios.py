"""Catálogo de servicios: nivel 1 y nivel 2, búsqueda, filtros, validaciones y asignaciones."""
from .catalogos import TABLAS, listar as listar_catalogo
from .db import IntegrityError, ahora
from .errores import ErrorValidacion
from .util import entero, numero, paginar, texto

SELECT_N2 = """SELECT s.*, n1.codigo AS n1_codigo, n1.nombre AS n1_nombre, n1.activo AS n1_activo,
  cl.nombre AS clase, cr.nombre AS criticidad, ti.nombre AS tipo,
  sec.codigo AS seccion_codigo, sec.nombre AS seccion_nombre,
  u.nombre AS responsable_nombre, u.login AS responsable_login
  FROM servicio_n2 s JOIN servicio_n1 n1 ON n1.id = s.nivel1_id
  LEFT JOIN cat_clase cl ON cl.id = s.clase_id LEFT JOIN cat_criticidad cr ON cr.id = s.criticidad_id
  LEFT JOIN cat_tipo ti ON ti.id = s.tipo_id LEFT JOIN seccion sec ON sec.id = s.seccion_id
  LEFT JOIN usuario u ON u.id = s.usuario_id"""


def catalogos(db):
    return {c: listar_catalogo(db, c) for c in TABLAS}


def revision(reg):
    """'COMPLETO' solo si todos los atributos clave están informados; si no, 'REVISION'."""
    ok = reg.get("indicador_activo") and reg.get("clase_id") and reg.get("criticidad_id") and reg.get("tipo_id") and reg.get("metrica")
    return "COMPLETO" if ok else "REVISION"


# ------------------------------------------------------------------ nivel 1
def listar_n1(db, q=None, estado=None, pagina=1, por_pagina=20):
    where, params = ["1 = 1"], []
    if q:
        where.append("(LOWER(n1.codigo) LIKE ? OR LOWER(n1.nombre) LIKE ?)")
        params += [f"%{q.lower()}%"] * 2
    if estado in ("activo", "inactivo"):
        where.append("n1.activo = ?")
        params.append(estado == "activo")
    cond = " AND ".join(where)
    total = db.valor(f"SELECT COUNT(*) FROM servicio_n1 n1 WHERE {cond}", params)
    pg = paginar(total, pagina, por_pagina)
    filas = db.consultar(
        f"""SELECT n1.*, (SELECT COUNT(*) FROM servicio_n2 s WHERE s.nivel1_id = n1.id) AS cant_n2
            FROM servicio_n1 n1 WHERE {cond} ORDER BY n1.codigo LIMIT ? OFFSET ?""",
        params + [por_pagina, pg["offset"]],
    )
    return filas, pg


def todos_n1(db, solo_activos=True):
    cond = "WHERE activo = ?" if solo_activos else ""
    return db.consultar(f"SELECT id, codigo, nombre, activo FROM servicio_n1 {cond} ORDER BY codigo", [True] if solo_activos else [])


def obtener_n1(db, id_):
    return db.uno("SELECT * FROM servicio_n1 WHERE id = ?", (id_,))


def _datos_n1(db, form, actual=None):
    codigo = texto(form.get("codigo"), "Código", maximo=40)
    nombre = texto(form.get("nombre"), "Nombre", maximo=300)
    q, p = "SELECT id FROM servicio_n1 WHERE codigo = ?", [codigo]
    if actual:
        q, p = q + " AND id <> ?", p + [actual["id"]]
    if db.uno(q, p):
        raise ErrorValidacion(f"Ya existe un servicio de nivel 1 con el código «{codigo}».")
    return codigo, nombre


def crear_n1(db, form):
    codigo, nombre = _datos_n1(db, form)
    try:
        with db.tx():
            return db.insertar(
                "INSERT INTO servicio_n1 (codigo, codigo_original, nombre, activo, estado_revision) VALUES (?,?,?,?,?)",
                (codigo, codigo, nombre, True, "COMPLETO"),
            )
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: código duplicado.") from None


def actualizar_n1(db, id_, form):
    actual = obtener_n1(db, id_)
    if not actual:
        raise ErrorValidacion("El servicio no existe.")
    codigo, nombre = _datos_n1(db, form, actual)
    try:
        with db.tx():
            db.ejecutar("UPDATE servicio_n1 SET codigo = ?, nombre = ? WHERE id = ?", (codigo, nombre, id_))
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: código duplicado.") from None


def cambiar_estado_n1(db, id_, activo):
    if not obtener_n1(db, id_):
        raise ErrorValidacion("El servicio no existe.")
    if not activo:
        n = db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE nivel1_id = ? AND activo = ?", (id_, True))
        if n:
            raise ErrorValidacion(f"No se puede desactivar: tiene {n} servicios de nivel 2 activos. Desactívelos primero.")
    with db.tx():
        db.ejecutar("UPDATE servicio_n1 SET activo = ? WHERE id = ?", (activo, id_))


# ------------------------------------------------------------------ nivel 2
def buscar_n2(db, q=None, nivel1_id=None, estado=None, clase_id=None, criticidad_id=None, tipo_id=None, pagina=1, por_pagina=20):
    where, params = ["1 = 1"], []
    if q:
        where.append("(LOWER(s.codigo) LIKE ? OR LOWER(s.nombre) LIKE ?)")
        params += [f"%{q.lower()}%"] * 2
    for col, val in (("nivel1_id", nivel1_id), ("clase_id", clase_id), ("criticidad_id", criticidad_id), ("tipo_id", tipo_id)):
        if val:
            where.append(f"s.{col} = ?")
            params.append(val)
    if estado in ("activo", "inactivo"):
        where.append("s.activo = ?")
        params.append(estado == "activo")
    cond = " AND ".join(where)
    total = db.valor(f"SELECT COUNT(*) FROM servicio_n2 s WHERE {cond}", params)
    pg = paginar(total, pagina, por_pagina)
    filas = db.consultar(f"{SELECT_N2} WHERE {cond} ORDER BY s.codigo LIMIT ? OFFSET ?", params + [por_pagina, pg["offset"]])
    return filas, pg


def obtener_n2(db, id_):
    return db.uno(f"{SELECT_N2} WHERE s.id = ?", (id_,))


def _ref_catalogo(db, campo, valor):
    id_ = entero(valor, campo, obligatorio=False)
    if id_ is None:
        return None
    if not db.uno(f"SELECT id FROM {TABLAS[campo]} WHERE id = ?", (id_,)):
        raise ErrorValidacion(f"El valor seleccionado en «{campo}» no existe en el catálogo.")
    return id_


def validar_asignacion(db, seccion_id, usuario_id, actual=None):
    """La sección debe existir y estar activa; el responsable debe pertenecer a esa sección."""
    if usuario_id and not seccion_id:
        raise ErrorValidacion("Para asignar un usuario responsable debe indicar la sección.")
    if seccion_id:
        sec = db.uno("SELECT id, activo FROM seccion WHERE id = ?", (seccion_id,))
        if not sec:
            raise ErrorValidacion("La sección indicada no existe.")
        if not sec["activo"] and not (actual and actual.get("seccion_id") == seccion_id):
            raise ErrorValidacion("No se puede asignar una sección inactiva.")
    if usuario_id:
        u = db.uno(
            "SELECT u.id, u.activo, p.seccion_id FROM usuario u JOIN puesto p ON p.id = u.puesto_id WHERE u.id = ?", (usuario_id,)
        )
        if not u:
            raise ErrorValidacion("El usuario responsable no existe.")
        if not u["activo"] and not (actual and actual.get("usuario_id") == usuario_id):
            raise ErrorValidacion("No se puede asignar un usuario inactivo.")
        if u["seccion_id"] != seccion_id:
            raise ErrorValidacion("El usuario responsable debe pertenecer a la sección responsable del servicio.")


def _datos_n2(db, form, actual=None):
    codigo = texto(form.get("codigo"), "Código", maximo=40)
    nombre = texto(form.get("nombre"), "Nombre", maximo=300)
    nivel1_id = entero(form.get("nivel1_id"), "Servicio de nivel 1")
    n1 = obtener_n1(db, nivel1_id)
    if not n1:
        raise ErrorValidacion("El servicio de nivel 1 indicado no existe.")
    if not n1["activo"] and not (actual and actual["nivel1_id"] == nivel1_id):
        raise ErrorValidacion("No se puede asociar a un servicio de nivel 1 inactivo.")
    q, p = "SELECT id FROM servicio_n2 WHERE codigo = ?", [codigo]
    if actual:
        q, p = q + " AND id <> ?", p + [actual["id"]]
    if db.uno(q, p):
        raise ErrorValidacion(f"Ya existe un servicio de nivel 2 con el código «{codigo}».")
    ind = (form.get("indicador_activo") or "").strip().upper() or None
    if ind not in (None, "S", "N"):
        raise ErrorValidacion("El indicador ACTIVO debe ser S, N o quedar sin definir.")
    minimo, maximo = numero(form.get("minimo"), "Mínimo"), numero(form.get("maximo"), "Máximo")
    if minimo is not None and maximo is not None and minimo > maximo:
        raise ErrorValidacion("El mínimo no puede ser mayor que el máximo.")
    seccion_id = entero(form.get("seccion_id"), "Sección", obligatorio=False)
    usuario_id = entero(form.get("usuario_id"), "Responsable", obligatorio=False)
    validar_asignacion(db, seccion_id, usuario_id, actual)
    datos = {
        "codigo": codigo, "nombre": nombre, "nivel1_id": nivel1_id, "indicador_activo": ind,
        "clase_id": _ref_catalogo(db, "clase", form.get("clase_id")),
        "criticidad_id": _ref_catalogo(db, "criticidad", form.get("criticidad_id")),
        "tipo_id": _ref_catalogo(db, "tipo", form.get("tipo_id")),
        "descripcion": texto(form.get("descripcion"), "Descripción", obligatorio=False, maximo=4000),
        "metrica": texto(form.get("metrica"), "Métrica", obligatorio=False, maximo=500),
        "minimo": minimo, "maximo": maximo, "seccion_id": seccion_id, "usuario_id": usuario_id,
    }
    datos["estado_revision"] = revision(datos)
    return datos


def crear_n2(db, form):
    d = _datos_n2(db, form)
    t = ahora()
    d.update(codigo_original=d["codigo"], activo=True, creado=t, actualizado=t, origen_hoja="(alta manual)")
    cols = list(d)
    try:
        with db.tx():
            return db.insertar(f"INSERT INTO servicio_n2 ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [d[c] for c in cols])
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: código duplicado o referencia inexistente.") from None


def actualizar_n2(db, id_, form):
    actual = obtener_n2(db, id_)
    if not actual:
        raise ErrorValidacion("El servicio no existe.")
    d = _datos_n2(db, form, actual)
    d["actualizado"] = ahora()
    try:
        with db.tx():
            db.ejecutar(f"UPDATE servicio_n2 SET {', '.join(c + ' = ?' for c in d)} WHERE id = ?", list(d.values()) + [id_])
    except IntegrityError:
        raise ErrorValidacion("No se pudo guardar: código duplicado o referencia inexistente.") from None


def asignar(db, id_, seccion_id, usuario_id):
    actual = obtener_n2(db, id_)
    if not actual:
        raise ErrorValidacion("El servicio no existe.")
    seccion_id = entero(seccion_id, "Sección", obligatorio=False)
    usuario_id = entero(usuario_id, "Responsable", obligatorio=False)
    validar_asignacion(db, seccion_id, usuario_id, actual)
    with db.tx():
        db.ejecutar("UPDATE servicio_n2 SET seccion_id = ?, usuario_id = ?, actualizado = ? WHERE id = ?", (seccion_id, usuario_id, ahora(), id_))


def cambiar_estado_n2(db, id_, activo):
    actual = obtener_n2(db, id_)
    if not actual:
        raise ErrorValidacion("El servicio no existe.")
    if activo and not actual["n1_activo"]:
        raise ErrorValidacion("No se puede reactivar: su servicio de nivel 1 está inactivo.")
    with db.tx():
        db.ejecutar("UPDATE servicio_n2 SET activo = ?, actualizado = ? WHERE id = ?", (activo, ahora(), id_))


def secciones_activas(db):
    return db.consultar(
        """SELECT s.id, s.codigo, s.nombre, e.codigo || ' / ' || a.codigo || ' / ' || d.codigo AS ruta
           FROM seccion s JOIN departamento d ON d.id = s.departamento_id JOIN area a ON a.id = d.area_id
           JOIN empresa e ON e.id = a.empresa_id WHERE s.activo = ? ORDER BY ruta, s.codigo""",
        (True,),
    )


def usuarios_de_seccion(db):
    """Usuarios activos con su sección (para filtrar el selector de responsable)."""
    return db.consultar(
        """SELECT u.id, u.nombre, u.login, p.seccion_id FROM usuario u JOIN puesto p ON p.id = u.puesto_id
           WHERE u.activo = ? ORDER BY u.nombre""",
        (True,),
    )
