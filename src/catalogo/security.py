"""Autenticación local: hash con sal (scrypt), sesiones en servidor, CSRF y autorización."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from functools import wraps

from flask import abort, current_app, g, redirect, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import ahora

COOKIE = "sid"
MIN_PASSWORD = 8
ROLES = ("administrador", "consulta")


def hash_password(password):
    """Hash especializado y con sal aleatoria (scrypt de Werkzeug). Nunca texto plano."""
    return generate_password_hash(password, method="scrypt")


def verificar_password(hash_guardado, password):
    return check_password_hash(hash_guardado, password)


# Hash falso para igualar tiempos cuando el usuario no existe.
HASH_FALSO = hash_password(secrets.token_urlsafe(16))


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(db, usuario_id, horas):
    token = secrets.token_urlsafe(32)
    t = ahora()
    with db.tx():
        db.ejecutar("DELETE FROM sesion WHERE expira <= ?", (t,))
        db.ejecutar(
            "INSERT INTO sesion (token_hash, usuario_id, creada, expira) VALUES (?, ?, ?, ?)",
            (_digest(token), usuario_id, t, t + timedelta(hours=horas)),
        )
    return token


def cerrar_sesion(db, token):
    if token:
        db.ejecutar("DELETE FROM sesion WHERE token_hash = ?", (_digest(token),))


def usuario_de_token(db, token):
    """Devuelve el usuario SOLO si la sesión existe, no expiró y el usuario sigue activo."""
    if not token:
        return None
    return db.uno(
        """SELECT u.id, u.nombre, u.login, u.rol, u.puesto_id
           FROM sesion s JOIN usuario u ON u.id = s.usuario_id
           WHERE s.token_hash = ? AND s.expira > ? AND u.activo = ?""",
        (_digest(token), ahora(), True),
    )


def csrf_token():
    sid = request.cookies.get(COOKIE)
    if not sid:
        return ""
    clave = current_app.config["SECRET_KEY"].encode()
    return hmac.new(clave, sid.encode(), hashlib.sha256).hexdigest()


def csrf_valido():
    enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    esperado = csrf_token()
    return bool(esperado) and hmac.compare_digest(enviado, esperado)


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if g.get("usuario") is None:
            return redirect(url_for("auth.login", siguiente=request.path))
        return vista(*args, **kwargs)

    return envoltura


def admin_requerido(vista):
    @wraps(vista)
    @login_requerido
    def envoltura(*args, **kwargs):
        if g.usuario["rol"] != "administrador":
            abort(403)
        return vista(*args, **kwargs)

    return envoltura
