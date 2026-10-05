from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from .. import usuarios
from ..errores import ErrorValidacion
from ..security import ROLES, admin_requerido, login_requerido
from ..util import entero_seguro

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


@bp.route("/")
@login_requerido
def lista():
    a = request.args
    filas, pg = usuarios.listar(g.db, a.get("q"), a.get("estado"), a.get("rol"), entero_seguro(a.get("pagina")), current_app.config["POR_PAGINA"])
    return render_template("usuarios_lista.html", filas=filas, pg=pg, args=a, roles=ROLES)


@bp.route("/nuevo", methods=["GET", "POST"])
@admin_requerido
def nuevo():
    if request.method == "POST":
        try:
            usuarios.crear(g.db, request.form)
            flash("Usuario creado correctamente.", "ok")
            return redirect(url_for("usuarios.lista"))
        except ErrorValidacion as e:
            flash(str(e), "error")
    return render_template("usuarios_form.html", reg=request.form if request.method == "POST" else {}, roles=ROLES, puestos=usuarios.opciones_puesto(g.db), editando=False)


@bp.route("/<int:id_>", methods=["GET", "POST"])
@login_requerido
def detalle(id_):
    reg = usuarios.obtener(g.db, id_)
    if not reg:
        abort(404)
    if request.method == "POST":
        if g.usuario["rol"] != "administrador":
            abort(403)
        try:
            usuarios.actualizar(g.db, id_, request.form, g.usuario["id"])
            flash("Cambios guardados.", "ok")
            return redirect(url_for("usuarios.detalle", id_=id_))
        except ErrorValidacion as e:
            flash(str(e), "error")
    servicios = g.db.consultar("SELECT id, codigo, nombre FROM servicio_n2 WHERE usuario_id = ? ORDER BY codigo", (id_,))
    return render_template("usuarios_detalle.html", reg=reg, roles=ROLES, puestos=usuarios.opciones_puesto(g.db, reg["puesto_id"]), servicios=servicios)


@bp.route("/<int:id_>/estado", methods=["POST"])
@admin_requerido
def estado(id_):
    try:
        usuarios.cambiar_estado(g.db, id_, request.form.get("activo") == "1", g.usuario["id"])
        flash("Estado actualizado.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return redirect(url_for("usuarios.detalle", id_=id_))
