"""P04, P05 y política de desactivación de la estructura organizacional."""
import unittest

from base import PW, AppTestCase
from catalogo import org, usuarios
from catalogo.errores import ErrorValidacion


class TestOrganizacion(AppTestCase):
    def test_P04_crear_jerarquia_completa_y_asignar_usuario_por_la_interfaz(self):
        c = self.cliente("admin.test")
        ids = {}
        pasos = [("empresa", {"codigo": "EMP1", "nombre": "Empresa Uno"}, None),
                 ("area", {"codigo": "ARE1", "nombre": "Área Uno"}, "empresa_id"),
                 ("departamento", {"codigo": "DEP1", "nombre": "Depto Uno"}, "area_id"),
                 ("seccion", {"codigo": "SEC1", "nombre": "Sección Uno"}, "departamento_id"),
                 ("puesto", {"codigo": "PUE1", "nombre": "Puesto Uno"}, "seccion_id")]
        previo = None
        for nivel, datos, fk in pasos:
            if fk:
                datos = dict(datos, **{fk: ids[previo]})
            r = self.post(c, f"/org/{nivel}/nuevo", datos)
            self.assertEqual(r.status_code, 302, self.texto(r)[:300])
            ids[nivel] = self.db.valor(f"SELECT id FROM {nivel} WHERE codigo = ?", (datos["codigo"],))
            previo = nivel
        r = self.post(c, "/usuarios/nuevo", {"nombre": "Pedro Pérez", "login": "pedro@x.com", "password": "Clave#12345", "rol": "consulta", "puesto_id": ids["puesto"]})
        self.assertEqual(r.status_code, 302)
        u = usuarios.obtener(self.db, self.db.valor("SELECT id FROM usuario WHERE login = ?", ("pedro@x.com",)))
        self.assertEqual((u["empresa_codigo"], u["area_codigo"], u["depto_codigo"], u["seccion_codigo"], u["puesto_codigo"]),
                         ("EMP1", "ARE1", "DEP1", "SEC1", "PUE1"))
        self.assertIn("PUE1", self.texto(c.get(f"/org/puesto/{ids['puesto']}")))
        self.assertIn("EMP1", self.texto(c.get(f"/org/area/{ids['area']}")) + self.texto(c.get("/org/area/")))

    def test_P05_codigo_duplicado_y_referencia_inexistente(self):
        c = self.cliente("admin.test")
        r = self.post(c, "/org/empresa/nuevo", {"codigo": "ea", "nombre": "Duplicada"})  # EA ya existe (mayúsculas normalizadas)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ya existe un registro con el código", self.texto(r))
        r = self.post(c, "/org/area/nuevo", {"codigo": "NUEVA", "nombre": "x", "empresa_id": "99999"})
        self.assertIn("no existe", self.texto(r))
        self.assertIsNone(self.db.uno("SELECT 1 AS x FROM area WHERE codigo = ?", ("NUEVA",)))
        r = self.post(c, "/org/area/nuevo", {"codigo": "", "nombre": "x", "empresa_id": self.org["empresa"]})
        self.assertIn("obligatorio", self.texto(r))
        r = self.post(c, "/usuarios/nuevo", {"nombre": "x", "login": "dup.test", "password": "12345678", "rol": "consulta", "puesto_id": "99999"})
        self.assertIn("no existe", self.texto(r))
        r = self.post(c, "/usuarios/nuevo", {"nombre": "x", "login": "admin.test", "password": "12345678", "rol": "consulta", "puesto_id": self.org["puesto"]})
        self.assertIn("Ya existe un usuario", self.texto(r))
        r = self.post(c, "/usuarios/nuevo", {"nombre": "x", "login": "corta.pw", "password": "123", "rol": "consulta", "puesto_id": self.org["puesto"]})
        self.assertIn("al menos 8", self.texto(r))

    def test_codigos_subordinados_unicos_solo_dentro_de_su_padre(self):
        otra = org.crear(self.db, "empresa", {"codigo": "OTRA", "nombre": "Otra"})
        org.crear(self.db, "area", {"codigo": "ARX", "nombre": "x", "empresa_id": otra})
        org.crear(self.db, "area", {"codigo": "ARX", "nombre": "x", "empresa_id": self.org["empresa"]})  # mismo código, otro padre: permitido
        with self.assertRaises(ErrorValidacion):
            org.crear(self.db, "area", {"codigo": "ARX", "nombre": "y", "empresa_id": otra})

    def test_politica_no_desactivar_con_dependientes_activos(self):
        with self.assertRaises(ErrorValidacion) as cm:
            org.cambiar_estado(self.db, "empresa", self.org["empresa"], False)
        self.assertIn("áreas activos", str(cm.exception).lower().replace("areas", "áreas"))
        with self.assertRaises(ErrorValidacion):
            org.cambiar_estado(self.db, "puesto", self.org["puesto"], False)  # tiene usuarios activos
        self.assertTrue(self.db.valor("SELECT activo FROM empresa WHERE id = ?", (self.org["empresa"],)), "no se pierde información")

    def test_baja_logica_ordenada_y_sin_asociar_a_padres_inactivos(self):
        for u in ("admin.test", "consulta.test"):
            self.db.ejecutar("DELETE FROM sesion")
        # nueva rama para no romper a los usuarios de prueba
        j = self.crear_jerarquia("B")
        for nivel in ("puesto", "seccion", "departamento", "area", "empresa"):
            org.cambiar_estado(self.db, nivel, j[nivel], False)
        self.assertFalse(self.db.valor("SELECT activo FROM empresa WHERE id = ?", (j["empresa"],)))
        with self.assertRaises(ErrorValidacion) as cm:
            org.crear(self.db, "area", {"codigo": "NEW", "nombre": "x", "empresa_id": j["empresa"]})
        self.assertIn("inactivo", str(cm.exception))
        with self.assertRaises(ErrorValidacion):
            org.cambiar_estado(self.db, "area", j["area"], True)  # padre inactivo
        with self.assertRaises(ErrorValidacion):
            usuarios.crear(self.db, {"nombre": "x", "login": "inactivo.test", "password": PW, "rol": "consulta", "puesto_id": str(j["puesto"])})
        org.cambiar_estado(self.db, "empresa", j["empresa"], True)
        org.cambiar_estado(self.db, "area", j["area"], True)  # ahora sí

    def test_no_se_pueden_crear_huerfanos_a_nivel_de_base_de_datos(self):
        from catalogo.db import IntegrityError

        with self.assertRaises(IntegrityError):
            self.db.ejecutar("INSERT INTO area (codigo, nombre, activo, empresa_id) VALUES (?,?,?,?)", ("H", "huérfana", True, 424242))

    def test_mover_puesto_no_deja_responsables_inconsistentes(self):
        j2 = self.crear_jerarquia("C")
        self.importar_catalogo()
        srv = self.db.valor("SELECT id FROM servicio_n2 ORDER BY codigo LIMIT 1")
        from catalogo import servicios

        servicios.asignar(self.db, srv, self.org["seccion"], self.consulta_id)
        with self.assertRaises(ErrorValidacion):
            org.actualizar(self.db, "puesto", self.org["puesto"], {"codigo": "PUA", "nombre": "p", "seccion_id": str(j2["seccion"])})
        with self.assertRaises(ErrorValidacion):
            usuarios.actualizar(self.db, self.consulta_id, {"nombre": "x", "rol": "consulta", "puesto_id": str(j2["puesto"])}, self.admin_id)


if __name__ == "__main__":
    unittest.main()
