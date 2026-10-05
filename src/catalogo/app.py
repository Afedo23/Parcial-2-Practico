"""Fábrica de la aplicación Flask."""
import json

from flask import Flask, g, render_template, request

from .config import cargar_config
from .db import Conexion
from .security import COOKIE, csrf_token, csrf_valido, usuario_de_token


def create_app(config=None):
    app = Flask(__name__)
    cfg = cargar_config(config)
    app.config.update(cfg)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

    @app.before_request
    def preparar():
        g.db = Conexion(app.config["DATABASE_URL"])
        g.usuario = usuario_de_token(g.db, request.cookies.get(COOKIE))
        # CSRF: toda operación que modifica estado, salvo el inicio de sesión (aún sin sesión)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.endpoint != "auth.login":
            if g.usuario is None:
                from flask import redirect, url_for

                return redirect(url_for("auth.login"))
            if not csrf_valido():
                return render_template("error.html", codigo=403, mensaje="Token CSRF inválido o ausente."), 403

    @app.teardown_request
    def cerrar(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.cerrar()

    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.context_processor
    def contexto():
        return dict(csrf_token=csrf_token, usuario=g.get("usuario"), es_admin=bool(g.get("usuario") and g.usuario["rol"] == "administrador"))

    @app.template_filter("fecha")
    def fecha(v):
        if v is None:
            return "—"
        return v.strftime("%Y-%m-%d %H:%M") if hasattr(v, "strftime") else str(v)[:16]

    @app.template_filter("json_lista")
    def json_lista(v):
        try:
            return json.loads(v) if v else []
        except ValueError:
            return [v]

    @app.template_filter("numero")
    def numero(v):
        if v is None:
            return "—"
        return f"{v:g}"

    @app.errorhandler(403)
    def prohibido(_e):
        return render_template("error.html", codigo=403, mensaje="No tiene permisos para esta operación."), 403

    @app.errorhandler(404)
    def no_encontrado(_e):
        return render_template("error.html", codigo=404, mensaje="Recurso no encontrado."), 404

    from .vistas import auth, importaciones, organizacion, servicios, usuarios as vusuarios

    for modulo in (auth, organizacion, vusuarios, servicios, importaciones):
        app.register_blueprint(modulo.bp)
    return app
