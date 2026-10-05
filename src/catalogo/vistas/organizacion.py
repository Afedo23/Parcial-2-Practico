from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from .. import org
from ..errores import ErrorValidacion
from ..security import admin_requerido, login_requerido
from ..util import entero_seguro

bp = Blueprint("org", __name__, url_prefix="/org")


def _nivel(nivel):
    if nivel not in org.NIVELES:
        abort(404)
    return nivel


@bp.route("/")
@login_requerido
def indice():
    conteos = {n: g.db.valor(f"SELECT COUNT(*) FROM {n}") for n in org.NIVELES}
    return render_template("org_indice.html", niveles=org.NIVELES, etiquetas=org.PLURAL, conteos=conteos)


@bp.route("/<nivel>/")
@login_requerido
def lista(nivel):
    _nivel(nivel)
    a = request.args
    filas, pg = org.listar(g.db, nivel, a.get("q"), a.get("estado"), entero_seguro(a.get("padre_id"), None),
                           entero_seguro(a.get("pagina")), current_app.config["POR_PAGINA"])
    return render_template("org_lista.html", nivel=nivel, filas=filas, pg=pg, args=a, etiqueta=org.PLURAL[nivel],
                           etiquetas=org.ETIQUETA, hijo=org.HIJO.get(nivel), padres=org.opciones_padre(g.db, nivel) if nivel in org.PADRE else [])


@bp.route("/<nivel>/nuevo", methods=["GET", "POST"])
@admin_requerido
def nuevo(nivel):
    _nivel(nivel)
    if request.method == "POST":
        try:
            org.crear(g.db, nivel, request.form)
            flash(f"{org.ETIQUETA[nivel]} creado correctamente.", "ok")
            return redirect(url_for("org.lista", nivel=nivel))
        except ErrorValidacion as e:
            flash(str(e), "error")
    return render_template("org_form.html", nivel=nivel, reg=request.form if request.method == "POST" else {}, etiqueta=org.ETIQUETA[nivel],
                           padres=org.opciones_padre(g.db, nivel) if nivel in org.PADRE else [], fk=org.PADRE.get(nivel, (None, None))[1],
                           padre_etiqueta=org.ETIQUETA.get(org.PADRE.get(nivel, (None,))[0]), editando=False)


@bp.route("/<nivel>/<int:id_>", methods=["GET", "POST"])
@login_requerido
def detalle(nivel, id_):
    """GET: ficha (todos). POST: edición (solo administrador)."""
    _nivel(nivel)
    reg = org.obtener(g.db, nivel, id_)
    if not reg:
        abort(404)
    if request.method == "POST":
        if g.usuario["rol"] != "administrador":
            abort(403)
        try:
            org.actualizar(g.db, nivel, id_, request.form)
            flash("Cambios guardados.", "ok")
            return redirect(url_for("org.detalle", nivel=nivel, id_=id_))
        except ErrorValidacion as e:
            flash(str(e), "error")
            reg = dict(reg, **{k: v for k, v in request.form.items() if k in reg})
    hijos = []
    if nivel in org.HIJO:
        hijos = g.db.consultar(f"SELECT id, codigo, nombre, activo FROM {org.HIJO[nivel]} WHERE {org.PADRE[org.HIJO[nivel]][1]} = ? ORDER BY codigo", (id_,))
    usuarios = g.db.consultar("SELECT id, nombre, login, activo FROM usuario WHERE puesto_id = ? ORDER BY nombre", (id_,)) if nivel == "puesto" else []
    fk = org.PADRE.get(nivel, (None, None))[1]
    return render_template("org_detalle.html", nivel=nivel, reg=reg, etiqueta=org.ETIQUETA[nivel], hijos=hijos, hijo=org.HIJO.get(nivel),
                           etiquetas=org.ETIQUETA, usuarios=usuarios, fk=fk, padre_etiqueta=org.ETIQUETA.get(org.PADRE.get(nivel, (None,))[0]),
                           padres=org.opciones_padre(g.db, nivel, reg.get(fk)) if fk else [])


@bp.route("/<nivel>/<int:id_>/estado", methods=["POST"])
@admin_requerido
def estado(nivel, id_):
    _nivel(nivel)
    try:
        org.cambiar_estado(g.db, nivel, id_, request.form.get("activo") == "1")
        flash("Estado actualizado.", "ok")
    except ErrorValidacion as e:
        flash(str(e), "error")
    return redirect(request.referrer or url_for("org.detalle", nivel=nivel, id_=id_))
