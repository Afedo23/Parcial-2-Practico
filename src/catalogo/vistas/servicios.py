from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from .. import servicios as sv
from ..errores import ErrorValidacion
from ..security import admin_requerido, login_requerido
from ..util import entero_seguro

bp = Blueprint("panel", __name__)
bp_n1 = bp  # un único blueprint 'panel' agrupa inicio, nivel 1 y nivel 2


@bp.route("/salud")
def salud():
    g.db.valor("SELECT 1")
    return "ok"


@bp.route("/")
@login_requerido
def inicio():
    db = g.db
    datos = dict(
        n1=db.valor("SELECT COUNT(*) FROM servicio_n1"), n2=db.valor("SELECT COUNT(*) FROM servicio_n2"),
        revision=db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE estado_revision = ?", ("REVISION",)),
        asignados=db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE seccion_id IS NOT NULL"),
        usuarios=db.valor("SELECT COUNT(*) FROM usuario WHERE activo = ?", (True,)),
    )
    return render_template("inicio.html", d=datos)


# ------------------------------------------------------------------ nivel 1
@bp.route("/servicios-n1/")
@login_requerido
def lista_n1():
    a = request.args
    filas, pg = sv.listar_n1(g.db, a.get("q"), a.get("estado"), entero_seguro(a.get("pagina")), current_app.config["POR_PAGINA"])
    return render_template("n1_lista.html", filas=filas, pg=pg, args=a)


@bp.route("/servicios-n1/nuevo", methods=["GET", "POST"])
@admin_requerido
def nuevo_n1():
    if request.method == "POST":
        try:
            sv.crear_n1(g.db, request.form)
            flash("Servicio de nivel 1 creado.", "ok")
            return redirect(url_for("panel.lista_n1"))
        except ErrorValidacion as e:
            flash(str(e), "error")
    return render_template("n1_form.html", reg=request.form if request.method == "POST" else {}, editando=False)


@bp.route("/servicios-n1/<int:id_>", methods=["GET", "POST"])
@login_requerido
def detalle_n1(id_):
    reg = sv.obtener_n1(g.db, id_)
    if not reg:
        abort(404)
    if request.method == "POST":
        if g.usuario["rol"] != "administrador":
            abort(403)
        try:
            sv.actualizar_n1(g.db, id_, request.form)
            flash("Cambios guardados.", "ok")
            return redirect(url_for("panel.detalle_n1", id_=id_))
        except ErrorValidacion as e:
            flash(str(e), "error")
    hijos, _ = sv.buscar_n2(g.db, nivel1_id=id_, por_pagina=500)
    return render_template("n1_detalle.html", reg=reg, hijos=hijos)


@bp.route("/servicios-n1/<int:id_>/estado", methods=["POST"])
@admin_requerido
def estado_n1(id_):
    try:
        sv.cambiar_estado_n1(g.db, id_, request.form.get("activo") == "1")
        flash("Estado actualizado.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return redirect(url_for("panel.detalle_n1", id_=id_))


# ------------------------------------------------------------------ nivel 2
def _opciones_form():
    return dict(cat=sv.catalogos(g.db), n1s=sv.todos_n1(g.db), secciones=sv.secciones_activas(g.db), usuarios_sec=sv.usuarios_de_seccion(g.db))


@bp.route("/servicios/")
@login_requerido
def lista():
    a = request.args
    filas, pg = sv.buscar_n2(
        g.db, a.get("q"), entero_seguro(a.get("nivel1_id"), None), a.get("estado"), entero_seguro(a.get("clase_id"), None),
        entero_seguro(a.get("criticidad_id"), None), entero_seguro(a.get("tipo_id"), None), entero_seguro(a.get("pagina")),
        current_app.config["POR_PAGINA"],
    )
    return render_template("servicios_lista.html", filas=filas, pg=pg, args=a, cat=sv.catalogos(g.db), n1s=sv.todos_n1(g.db, solo_activos=False))


@bp.route("/servicios/nuevo", methods=["GET", "POST"])
@admin_requerido
def nuevo():
    if request.method == "POST":
        try:
            id_ = sv.crear_n2(g.db, request.form)
            flash("Servicio creado.", "ok")
            return redirect(url_for("panel.ficha", id_=id_))
        except ErrorValidacion as e:
            flash(str(e), "error")
    return render_template("servicio_form.html", reg=request.form if request.method == "POST" else {}, editando=False, **_opciones_form())


@bp.route("/servicios/<int:id_>")
@login_requerido
def ficha(id_):
    reg = sv.obtener_n2(g.db, id_)
    if not reg:
        abort(404)
    return render_template("servicio_ficha.html", reg=reg, **_opciones_form())


@bp.route("/servicios/<int:id_>/editar", methods=["GET", "POST"])
@admin_requerido
def editar(id_):
    reg = sv.obtener_n2(g.db, id_)
    if not reg:
        abort(404)
    if request.method == "POST":
        try:
            sv.actualizar_n2(g.db, id_, request.form)
            flash("Cambios guardados.", "ok")
            return redirect(url_for("panel.ficha", id_=id_))
        except ErrorValidacion as e:
            flash(str(e), "error")
            reg = dict(reg, **request.form.to_dict())
    return render_template("servicio_form.html", reg=reg, editando=True, **_opciones_form())


@bp.route("/servicios/<int:id_>/asignacion", methods=["POST"])
@admin_requerido
def asignacion(id_):
    try:
        sv.asignar(g.db, id_, request.form.get("seccion_id"), request.form.get("usuario_id"))
        flash("Asignación guardada.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return redirect(url_for("panel.ficha", id_=id_))


@bp.route("/servicios/<int:id_>/estado", methods=["POST"])
@admin_requerido
def estado(id_):
    try:
        sv.cambiar_estado_n2(g.db, id_, request.form.get("activo") == "1")
        flash("Estado actualizado.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return redirect(url_for("panel.ficha", id_=id_))
