from flask import Blueprint, current_app, flash, g, make_response, redirect, render_template, request, url_for

from ..security import COOKIE, HASH_FALSO, cerrar_sesion, crear_sesion, login_requerido, verificar_password

bp = Blueprint("auth", __name__)


def _destino_seguro(ruta):
    return ruta if ruta and ruta.startswith("/") and not ruta.startswith("//") else url_for("panel.inicio")


@bp.route("/login", methods=["GET", "POST"])
def login():
    siguiente = request.values.get("siguiente", "")
    if request.method == "POST":
        login_ = (request.form.get("login") or "").strip().lower()
        password = request.form.get("password") or ""
        u = g.db.uno("SELECT id, password_hash, activo FROM usuario WHERE login = ?", (login_,))
        ok = verificar_password(u["password_hash"] if u else HASH_FALSO, password)  # tiempo similar si no existe
        if u and ok and u["activo"]:
            token = crear_sesion(g.db, u["id"], current_app.config["SESSION_HORAS"])
            resp = make_response(redirect(_destino_seguro(siguiente)))
            resp.set_cookie(COOKIE, token, httponly=True, samesite="Lax", secure=current_app.config["COOKIE_SECURE"],
                            max_age=current_app.config["SESSION_HORAS"] * 3600)
            return resp
        flash("Usuario o contraseña incorrectos, o cuenta inactiva.", "error")
        return render_template("login.html", siguiente=siguiente), 401
    if g.usuario:
        return redirect(url_for("panel.inicio"))
    return render_template("login.html", siguiente=siguiente)


@bp.route("/logout", methods=["POST"])
@login_requerido
def logout():
    cerrar_sesion(g.db, request.cookies.get(COOKIE))
    resp = make_response(redirect(url_for("auth.login")))
    resp.delete_cookie(COOKIE)
    return resp
