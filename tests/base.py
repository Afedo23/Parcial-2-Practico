"""Base común de las pruebas: BD aislada (SQLite temporal o PostgreSQL de pruebas), clientes y utilidades.

Seguridad del entorno: ``reiniciar_bd_de_pruebas`` se niega a tocar una base cuyo nombre no contenga «test».
"""
import hashlib
import hmac
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse, urlunparse

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))

from catalogo import create_app, org, servicios, usuarios  # noqa: E402
from catalogo.db import Conexion, es_sqlite, migrar, nombre_bd, reiniciar_bd_de_pruebas  # noqa: E402
from catalogo.importador import importar  # noqa: E402
from fixture_excel import crear_excel  # noqa: E402

SECRET = "clave-de-pruebas-0123456789"
PW = "Prueba#2026"
EXCEL_OFICIAL = RAIZ / "data" / "CatalogoServicios.xlsx"


def url_pruebas():
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    return "sqlite:///" + str(Path(tempfile.gettempdir()) / "catalogo_test.db")


def asegurar_bd_pruebas(url):
    """En PostgreSQL crea la base de pruebas si no existe (nunca toca la base de evaluación)."""
    if es_sqlite(url):
        return
    nombre = nombre_bd(url)
    if "test" not in nombre or not re.fullmatch(r"[a-z0-9_]+", nombre):
        raise RuntimeError(f"Nombre de base de pruebas no permitido: {nombre}")
    p = urlparse(url)
    admin = Conexion(urlunparse(p._replace(path="/postgres")))
    try:
        if not admin.uno("SELECT 1 AS x FROM pg_database WHERE datname = ?", (nombre,)):
            admin.ejecutar(f"CREATE DATABASE {nombre}")
    finally:
        admin.cerrar()


def archivo_para_importar():
    """Excel oficial si está en data/; si no, el de prueba generado (se informa para no confundirlos)."""
    if EXCEL_OFICIAL.exists() and os.environ.get("USAR_FIXTURE") != "1":
        return EXCEL_OFICIAL, False
    tmp = Path(tempfile.gettempdir()) / "CatalogoServicios_fixture.xlsx"
    crear_excel(tmp)
    return tmp, True


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.url = url_pruebas()
        asegurar_bd_pruebas(self.url)
        reiniciar_bd_de_pruebas(self.url)
        self.app = create_app({"DATABASE_URL": self.url, "SECRET_KEY": SECRET, "POR_PAGINA": 20})
        self.db = Conexion(self.url)
        self.addCleanup(self.db.cerrar)
        self.org = self.crear_jerarquia("A")
        self.admin_id = self.crear_usuario("admin.test", "administrador", self.org["puesto"])
        self.consulta_id = self.crear_usuario("consulta.test", "consulta", self.org["puesto"])

    # ---- datos --------------------------------------------------------------------------
    def crear_jerarquia(self, s):
        e = org.crear(self.db, "empresa", {"codigo": f"E{s}", "nombre": f"Empresa {s}"})
        a = org.crear(self.db, "area", {"codigo": f"AR{s}", "nombre": "Área", "empresa_id": e})
        d = org.crear(self.db, "departamento", {"codigo": f"DE{s}", "nombre": "Depto", "area_id": a})
        sec = org.crear(self.db, "seccion", {"codigo": f"SE{s}", "nombre": "Sección", "departamento_id": d})
        p = org.crear(self.db, "puesto", {"codigo": f"PU{s}", "nombre": "Puesto", "seccion_id": sec})
        return dict(empresa=e, area=a, departamento=d, seccion=sec, puesto=p)

    def crear_usuario(self, login, rol, puesto, password=PW):
        return usuarios.crear(self.db, {"nombre": login.title(), "login": login, "password": password, "rol": rol, "puesto_id": str(puesto)})

    def importar_catalogo(self):
        ruta, fixture = archivo_para_importar()
        self.usa_fixture = fixture
        resumen, obs = importar(self.db, ruta)
        return resumen, obs

    # ---- HTTP -----------------------------------------------------------------------------
    def cliente(self, login=None, password=PW):
        c = self.app.test_client()
        if login:
            r = c.post("/login", data={"login": login, "password": password})
            assert r.status_code == 302, f"login falló ({r.status_code})"
        return c

    def csrf(self, c):
        sid = c.get_cookie("sid").value
        return hmac.new(SECRET.encode(), sid.encode(), hashlib.sha256).hexdigest()

    def post(self, c, ruta, data=None, **kw):
        return c.post(ruta, data=dict(data or {}, csrf_token=self.csrf(c)), **kw)

    def texto(self, resp):
        return resp.get_data(as_text=True)
