"""P12 (nivel lógico): los datos sobreviven al cierre de todas las conexiones y al reinicio de la aplicación.

La comprobación con contenedores reales está en scripts/p12_persistencia.sh (docker compose restart).
"""
import unittest

from base import AppTestCase
from catalogo import create_app
from catalogo.db import Conexion, migrar


class TestPersistencia(AppTestCase):
    def test_P12_datos_persisten_tras_reiniciar_aplicacion_y_conexiones(self):
        self.importar_catalogo()
        c = self.cliente("admin.test")
        self.post(c, "/org/empresa/nuevo", {"codigo": "PERSIST", "nombre": "Debe sobrevivir"})
        self.db.cerrar()  # simula apagar la app
        app2 = create_app({"DATABASE_URL": self.url, "SECRET_KEY": "otra-clave-completamente-distinta", "POR_PAGINA": 20})
        nueva = Conexion(self.url)
        self.addCleanup(nueva.cerrar)
        migrar(nueva)  # reiniciar ejecuta migraciones: debe ser idempotente y no borrar nada
        self.assertEqual(nueva.valor("SELECT nombre FROM empresa WHERE codigo = ?", ("PERSIST",)), "Debe sobrevivir")
        self.assertEqual(nueva.valor("SELECT COUNT(*) FROM servicio_n2"), 46)
        self.assertIsNotNone(nueva.uno("SELECT 1 AS x FROM usuario WHERE login = ?", ("admin.test",)))
        r = app2.test_client().post("/login", data={"login": "admin.test", "password": "Prueba#2026"})
        self.assertEqual(r.status_code, 302)

    def test_migraciones_idempotentes(self):
        self.assertEqual(migrar(self.db), [])


if __name__ == "__main__":
    unittest.main()
