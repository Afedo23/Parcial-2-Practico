import json

from flask import Blueprint, abort, g, render_template

from ..security import login_requerido

bp = Blueprint("importaciones", __name__, url_prefix="/importaciones")


@bp.route("/")
@login_requerido
def lista():
    filas = g.db.consultar("SELECT id, archivo, sha256, iniciada, estado, resumen FROM import_ejecucion ORDER BY id DESC LIMIT 50")
    for f in filas:
        f["datos"] = json.loads(f["resumen"]) if f["resumen"] else {}
    mapeos = g.db.consultar("SELECT campo, valor_origen, valor_destino, motivo FROM mapeo_etiquetas ORDER BY campo, valor_origen")
    return render_template("importaciones_lista.html", filas=filas, mapeos=mapeos)


@bp.route("/<int:id_>")
@login_requerido
def detalle(id_):
    ej = g.db.uno("SELECT * FROM import_ejecucion WHERE id = ?", (id_,))
    if not ej:
        abort(404)
    obs = g.db.consultar("SELECT * FROM import_observacion WHERE ejecucion_id = ? ORDER BY tipo, codigo", (id_,))
    return render_template("importaciones_detalle.html", ej=ej, datos=json.loads(ej["resumen"] or "{}"), obs=obs)
