"""P01, P02, P03 + controles de seguridad adicionales."""
import unittest

from base import PW, AppTestCase


class TestAutenticacion(AppTestCase):
    def test_P01_login_valido_e_invalido(self):
        c = self.app.test_client()
        r = c.post("/login", data={"login": "admin.test", "password": PW})
        self.assertEqual(r.status_code, 302)
        self.assertIsNotNone(c.get_cookie("sid"))
        self.assertEqual(c.get("/").status_code, 200)
        for login, pw in (("admin.test", "incorrecta!!"), ("noexiste", PW), ("admin.test", "")):
            c2 = self.app.test_client()
            r = c2.post("/login", data={"login": login, "password": pw})
            self.assertEqual(r.status_code, 401, (login, pw))
            self.assertIsNone(c2.get_cookie("sid"))
            self.assertIn("incorrectos", self.texto(r))

    def test_P01_login_acepta_correo_y_es_insensible_a_mayusculas(self):
        self.crear_usuario("ana@empresa.com", "consulta", self.org["puesto"])
        r = self.app.test_client().post("/login", data={"login": "ANA@Empresa.com", "password": PW})
        self.assertEqual(r.status_code, 302)

    def test_hash_con_sal_y_nunca_texto_plano(self):
        fila = self.db.uno("SELECT password_hash FROM usuario WHERE login = ?", ("admin.test",))
        self.assertNotIn(PW, fila["password_hash"])
        self.assertTrue(fila["password_hash"].startswith("scrypt:"))
        otro = self.crear_usuario("otro.test", "consulta", self.org["puesto"])
        h2 = self.db.valor("SELECT password_hash FROM usuario WHERE id = ?", (otro,))
        self.assertNotEqual(fila["password_hash"], h2, "misma contraseña debe producir hash distinto (sal)")

    def test_token_de_sesion_no_se_guarda_en_claro(self):
        c = self.cliente("admin.test")
        token = c.get_cookie("sid").value
        self.assertIsNone(self.db.uno("SELECT 1 AS x FROM sesion WHERE token_hash = ?", (token,)))

    def test_P02_sin_sesion_se_rechazan_rutas_y_operaciones(self):
        c = self.app.test_client()
        for ruta in ("/", "/servicios/", "/usuarios/", "/org/empresa/", "/importaciones/", "/servicios/nuevo"):
            r = c.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertIn("/login", r.headers["Location"])
        r = c.post("/org/empresa/nuevo", data={"codigo": "X", "nombre": "X"})
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(self.db.uno("SELECT 1 AS x FROM empresa WHERE codigo = ?", ("X",)))

    def test_P02_cierre_de_sesion_invalida_la_credencial(self):
        c = self.cliente("admin.test")
        viejo = c.get_cookie("sid").value
        r = self.post(c, "/logout")
        self.assertEqual(r.status_code, 302)
        replay = self.app.test_client()
        replay.set_cookie("sid", viejo)
        r = replay.get("/servicios/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_P02_usuario_inactivo(self):
        c = self.cliente("consulta.test")
        self.assertEqual(c.get("/servicios/").status_code, 200)
        self.db.ejecutar("UPDATE usuario SET activo = ? WHERE login = ?", (False, "consulta.test"))
        self.assertEqual(c.get("/servicios/").status_code, 302, "la sesión previa debe dejar de servir")
        r = self.app.test_client().post("/login", data={"login": "consulta.test", "password": PW})
        self.assertEqual(r.status_code, 401)

    def test_sesion_expirada_se_rechaza(self):
        c = self.cliente("admin.test")
        self.db.ejecutar("UPDATE sesion SET expira = ?", ("2000-01-01 00:00:00",))
        self.assertEqual(c.get("/").status_code, 302)

    def test_P03_consulta_lee_pero_no_modifica(self):
        c = self.cliente("consulta.test")
        for ruta in ("/servicios/", "/org/empresa/", "/usuarios/", "/servicios-n1/"):
            self.assertEqual(c.get(ruta).status_code, 200, ruta)
        escrituras = [
            ("/org/empresa/nuevo", {"codigo": "ZZ", "nombre": "Z"}),
            (f"/org/empresa/{self.org['empresa']}/estado", {"activo": "0"}),
            ("/usuarios/nuevo", {"nombre": "x", "login": "xxx", "password": "12345678", "rol": "consulta", "puesto_id": self.org["puesto"]}),
            (f"/usuarios/{self.admin_id}/estado", {"activo": "0"}),
            ("/servicios-n1/nuevo", {"codigo": "N", "nombre": "N"}),
            ("/servicios/nuevo", {"codigo": "S", "nombre": "S"}),
        ]
        for ruta, datos in escrituras:
            self.assertEqual(self.post(c, ruta, datos).status_code, 403, ruta)
        self.assertEqual(c.get("/servicios/nuevo").status_code, 403)
        self.assertEqual(self.post(c, f"/org/empresa/{self.org['empresa']}", {"codigo": "E", "nombre": "hack"}).status_code, 403)
        self.assertEqual(self.db.valor("SELECT nombre FROM empresa WHERE id = ?", (self.org["empresa"],)), "Empresa A")
        self.assertTrue(self.db.valor("SELECT activo FROM usuario WHERE id = ?", (self.admin_id,)))

    def test_P03_consulta_no_ve_hashes_ni_secretos(self):
        c = self.cliente("consulta.test")
        for ruta in ("/usuarios/", f"/usuarios/{self.admin_id}"):
            cuerpo = self.texto(c.get(ruta))
            self.assertNotIn("scrypt", cuerpo)
            self.assertNotIn("password_hash", cuerpo)

    def test_csrf_obligatorio_en_operaciones_que_modifican(self):
        c = self.cliente("admin.test")
        r = c.post("/org/empresa/nuevo", data={"codigo": "CSRF", "nombre": "x"})
        self.assertEqual(r.status_code, 403)
        r = c.post("/org/empresa/nuevo", data={"codigo": "CSRF", "nombre": "x", "csrf_token": "falso"})
        self.assertEqual(r.status_code, 403)
        self.assertIsNone(self.db.uno("SELECT 1 AS x FROM empresa WHERE codigo = ?", ("CSRF",)))

    def test_redireccion_post_login_no_permite_sitios_externos(self):
        r = self.app.test_client().post("/login", data={"login": "admin.test", "password": PW, "siguiente": "https://malo.example"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("malo.example", r.headers["Location"])

    def test_no_se_puede_desactivar_al_ultimo_administrador(self):
        c = self.cliente("admin.test")
        r = self.post(c, f"/usuarios/{self.admin_id}/estado", {"activo": "0"}, follow_redirects=True)
        self.assertIn("propia cuenta", self.texto(r))


if __name__ == "__main__":
    unittest.main()
