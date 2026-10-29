from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from .. import cmdb
from ..errores import ErrorValidacion
from ..security import admin_requerido, login_requerido
from ..util import entero_seguro

bp = Blueprint("cmdb", __name__, url_prefix="/cmdb")


@bp.route("/")
@login_requerido
def lista():
    a = request.args
    filas, pg = cmdb.buscar_ci(g.db, a.get("q"), entero_seguro(a.get("clasificacion_id"), None), a.get("estado"),
                               entero_seguro(a.get("ubicacion_id"), None), a.get("origen"), entero_seguro(a.get("pagina")), current_app.config["POR_PAGINA"])
    return render_template("cmdb_lista.html", filas=filas, pg=pg, args=a, arbol=cmdb.arbol_clasificacion(g.db),
                           ubicaciones=g.db.consultar("SELECT id, nombre FROM cmdb_ubicacion ORDER BY nombre"),
                           estados=[r["estado_actual"] for r in g.db.consultar("SELECT DISTINCT estado_actual FROM cmdb_ci WHERE estado_actual IS NOT NULL ORDER BY estado_actual")])


@bp.route("/clasificacion/")
@login_requerido
def clasificacion():
    return render_template("cmdb_clasificacion.html", arbol=cmdb.arbol_clasificacion(g.db), rep=cmdb.reporte(g.db))


@bp.route("/<int:id_>")
@login_requerido
def ficha(id_):
    ci = cmdb.ficha_ci(g.db, id_)
    if not ci:
        abort(404)
    return render_template("cmdb_ficha.html", ci=ci, tipos=cmdb.TIPOS_REL)


@bp.route("/<int:id_>/relaciones", methods=["POST"])
@admin_requerido
def nueva_relacion(id_):
    codigo = (request.form.get("destino_codigo") or "").strip()
    destino = g.db.uno("SELECT id FROM cmdb_ci WHERE codigo = ?", (codigo,))
    try:
        if not destino:
            raise ErrorValidacion(f"No existe un CI con el código «{codigo}».")
        cmdb.crear_relacion(g.db, id_, destino["id"], request.form.get("tipo", ""))
        flash("Relación registrada.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return redirect(url_for("cmdb.ficha", id_=id_))
