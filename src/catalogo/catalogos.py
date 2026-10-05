"""Catálogos controlados de clase, criticidad y tipo de servicio (valores del enunciado)."""

CLASES = ["A DEMANDA", "RECURRENTE"]
CRITICIDADES = ["Very Low", "Low", "Normal", "High", "Very High"]
TIPOS = [
    "Back End", "Demostration", "End User Service", "Front End", "IT Management",
    "IT Operational", "Other", "Project", "Reporting", "Training", "Underpinning Contract",
]
INDICADORES_ACTIVO = ["S", "N"]

TABLAS = {"clase": "cat_clase", "criticidad": "cat_criticidad", "tipo": "cat_tipo"}
VALORES = {"clase": CLASES, "criticidad": CRITICIDADES, "tipo": TIPOS}


def asegurar_valor(conn, campo, nombre):
    tabla = TABLAS[campo]
    fila = conn.uno(f"SELECT id FROM {tabla} WHERE nombre = ?", (nombre,))
    if fila:
        return fila["id"], False
    orden = (conn.valor(f"SELECT COALESCE(MAX(orden), 0) FROM {tabla}") or 0) + 1
    return conn.insertar(f"INSERT INTO {tabla} (nombre, orden) VALUES (?, ?)", (nombre, orden)), True


def asegurar_catalogos(conn):
    with conn.tx():
        for campo, valores in VALORES.items():
            for v in valores:
                asegurar_valor(conn, campo, v)


def listar(conn, campo):
    return conn.consultar(f"SELECT id, nombre FROM {TABLAS[campo]} ORDER BY orden, nombre")
