"""Configuración leída del entorno. Nunca se incluyen secretos reales en el código."""
import os


class ConfigError(RuntimeError):
    pass


def _bool(valor, defecto=False):
    if valor is None:
        return defecto
    return str(valor).strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def cargar_config(overrides=None):
    cfg = {
        "DATABASE_URL": os.environ.get("DATABASE_URL", ""),
        "SECRET_KEY": os.environ.get("SECRET_KEY", ""),
        "SESSION_HORAS": int(os.environ.get("SESSION_HORAS", "8")),
        "COOKIE_SECURE": _bool(os.environ.get("COOKIE_SECURE"), False),
        "IMPORT_FILE": os.environ.get("IMPORT_FILE", "data/CatalogoServicios.xlsx"),
        "POR_PAGINA": int(os.environ.get("POR_PAGINA", "20")),
    }
    if overrides:
        cfg.update(overrides)
    if not cfg["DATABASE_URL"]:
        raise ConfigError("Falta DATABASE_URL (copie .env.example a .env).")
    if len(cfg["SECRET_KEY"]) < 16:
        raise ConfigError("SECRET_KEY debe tener al menos 16 caracteres (revise .env).")
    return cfg
