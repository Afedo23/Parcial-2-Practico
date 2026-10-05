"""P09, P10, P11 y mantenimiento del catálogo de servicios."""
import unittest
from unittest import mock

from base import PW, AppTestCase
from catalogo import cli, servicios
from catalogo.db import IntegrityError
from catalogo.errores import ErrorValidacion


class TestServicios(AppTestCase):
    def setUp(self):
        super().setUp()
        self.importar_catalogo()
        self.c = self.cliente("admin.test")
        self.n1 = self.db.valor("SELECT id FROM servicio_n1 ORDER BY codigo LIMIT 1")

    def form(self, **extra):
        d = {"codigo": "TEST.1", "nombre": "Servicio nuevo", "nivel1_id": self.n1}
        d.update(extra)
        return d

    def test_P09_minimo_mayor_que_maximo_no_se_guarda(self):
        r = self.post(self.c, "/servicios/nuevo", self.form(minimo="10", maximo="5"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("mínimo no puede ser mayor", self.texto(r))
        self.assertIsNone(self.db.uno("SELECT 1 AS x FROM servicio_n2 WHERE codigo = ?", ("TEST.1",)))
        sid = self.db.valor("SELECT id FROM servicio_n2 WHERE codigo = ?", ("SE.01.01",))
        r = self.post(self.c, f"/servicios/{sid}/editar", self.form(codigo="SE.01.01", minimo="99", maximo="1"))
        self.assertIn("mínimo no puede ser mayor", self.texto(r))
        r = self.post(self.c, "/servicios/nuevo", self.form(minimo="abc"))
        self.assertIn("debe ser un número", self.texto(r))

    def test_P09_restriccion_tambien_en_base_de_datos(self):
        with self.assertRaises(IntegrityError):
            self.db.ejecutar("UPDATE servicio_n2 SET minimo = ?, maximo = ? WHERE codigo = ?", (10, 5, "SE.01.01"))

    def test_P09_dato_ausente_no_se_convierte_en_cero_y_valido_se_guarda(self):
        r = self.post(self.c, "/servicios/nuevo", self.form(minimo="", maximo=""))
        self.assertEqual(r.status_code, 302)
        s = self.db.uno("SELECT * FROM servicio_n2 WHERE codigo = ?", ("TEST.1",))
        self.assertIsNone(s["minimo"])
        self.assertIsNone(s["maximo"])
        self.assertEqual(s["estado_revision"], "REVISION")
        r = self.post(self.c, "/servicios/nuevo", self.form(codigo="TEST.2", minimo="1,5", maximo="2.5"))
        self.assertEqual(r.status_code, 302)
        s = self.db.uno("SELECT minimo, maximo FROM servicio_n2 WHERE codigo = ?", ("TEST.2",))
        self.assertEqual((s["minimo"], s["maximo"]), (1.5, 2.5))

    def test_validaciones_servidor_obligatorios_y_referencias(self):
        for datos, msg in (
            (self.form(codigo=""), "obligatorio"),
            (self.form(nombre=""), "obligatorio"),
            (self.form(nivel1_id="99999"), "no existe"),
            (self.form(nivel1_id=""), "Debe seleccionar"),
            (self.form(clase_id="99999"), "no existe en el catálogo"),
            (self.form(indicador_activo="X"), "S, N"),
            (self.form(codigo="SE.01.01"), "Ya existe"),
        ):
            r = self.post(self.c, "/servicios/nuevo", datos)
            self.assertEqual(r.status_code, 200, datos)
            self.assertIn(msg, self.texto(r), datos)

    def test_ficha_muestra_todos_los_atributos(self):
        sid = self.db.valor("SELECT id FROM servicio_n2 WHERE codigo = ?", ("SE.01.01",))
        cuerpo = self.texto(self.c.get(f"/servicios/{sid}"))
        for esperado in ("SE.01.01", "SE.01", "Clase de servicio", "Criticidad", "Tipo de servicio", "Métrica", "Mínimo / Máximo", "Trazabilidad"):
            self.assertIn(esperado, cuerpo)

    def test_P10_busqueda_filtros_y_paginacion(self):
        filas, pg = servicios.buscar_n2(self.db, q="SE.03")
        self.assertTrue(filas and all(f["codigo"].startswith("SE.03") for f in filas))
        ref = self.db.uno("SELECT codigo, nombre FROM servicio_n2 WHERE codigo LIKE ? ORDER BY codigo LIMIT 1", ("SE.05%",))
        filas, _ = servicios.buscar_n2(self.db, q=ref["nombre"].upper()[:12])  # por nombre, sin distinguir mayúsculas
        self.assertIn(ref["codigo"], [f["codigo"] for f in filas])
        filas, _ = servicios.buscar_n2(self.db, q=ref["codigo"].lower())  # por código
        self.assertIn(ref["codigo"], [f["codigo"] for f in filas])
        n1 = self.db.valor("SELECT id FROM servicio_n1 WHERE codigo = ?", ("SE.02",))
        filas, _ = servicios.buscar_n2(self.db, nivel1_id=n1)
        self.assertEqual(len(filas), self.db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE nivel1_id = ?", (n1,)))
        self.assertTrue(all(f["n1_codigo"] == "SE.02" for f in filas))
        clase = self.db.valor("SELECT id FROM cat_clase WHERE nombre = ?", ("RECURRENTE",))
        filas, pg = servicios.buscar_n2(self.db, clase_id=clase)
        self.assertTrue(filas and all(f["clase"] == "RECURRENTE" for f in filas))
        crit = self.db.valor("SELECT id FROM cat_criticidad WHERE nombre = ?", ("High",))
        filas, _ = servicios.buscar_n2(self.db, clase_id=clase, criticidad_id=crit)
        self.assertTrue(all(f["clase"] == "RECURRENTE" and f["criticidad"] == "High" for f in filas))
        tipo = self.db.valor("SELECT id FROM cat_tipo WHERE nombre = ?", ("Reporting",))
        filas, _ = servicios.buscar_n2(self.db, tipo_id=tipo)
        self.assertTrue(all(f["tipo"] == "Reporting" for f in filas))
        primero = self.db.uno("SELECT id, codigo FROM servicio_n2 WHERE codigo LIKE ? ORDER BY codigo LIMIT 1", ("SE.02%",))
        servicios.cambiar_estado_n2(self.db, primero["id"], False)
        inact, _ = servicios.buscar_n2(self.db, estado="inactivo")
        self.assertEqual([f["codigo"] for f in inact], [primero["codigo"]])
        act, pg = servicios.buscar_n2(self.db, estado="activo")
        self.assertEqual(pg["total"], 45)
        p1, pg = servicios.buscar_n2(self.db, pagina=1)
        p3, _ = servicios.buscar_n2(self.db, pagina=3)
        self.assertEqual((len(p1), pg["paginas"], len(p3), pg["total"]), (20, 3, 6, 46))
        self.assertEqual(servicios.buscar_n2(self.db, q="zzz-no-existe")[1]["total"], 0)

    def test_P10_interfaz_de_busqueda_y_filtros(self):
        cuerpo = self.texto(self.c.get("/servicios/?q=SE.07&estado=activo"))
        cod07 = self.db.valor("SELECT codigo FROM servicio_n2 WHERE codigo LIKE ? ORDER BY codigo LIMIT 1", ("SE.07%",))
        self.assertIn(cod07, cuerpo)
        self.assertNotIn("SE.01.01", cuerpo)
        self.assertIn("Página 1 de 3", self.texto(self.c.get("/servicios/")))
        self.assertEqual(self.c.get("/servicios/?pagina=abc&nivel1_id=zz").status_code, 200)  # entradas basura no rompen

    def _segunda_seccion(self):
        j = self.crear_jerarquia("S")
        otro = self.crear_usuario("otro.seccion", "consulta", j["puesto"])
        return j, otro

    def test_P11_responsable_de_otra_seccion_se_rechaza(self):
        j, otro = self._segunda_seccion()
        sid = self.db.valor("SELECT id FROM servicio_n2 WHERE codigo = ?", ("SE.01.01",))
        r = self.post(self.c, f"/servicios/{sid}/asignacion", {"seccion_id": self.org["seccion"], "usuario_id": otro}, follow_redirects=True)
        self.assertIn("debe pertenecer a la sección", self.texto(r))
        row = self.db.uno("SELECT seccion_id, usuario_id FROM servicio_n2 WHERE id = ?", (sid,))
        self.assertEqual((row["seccion_id"], row["usuario_id"]), (None, None))
        with self.assertRaises(ErrorValidacion):
            servicios.asignar(self.db, sid, None, otro)  # responsable sin sección
        with self.assertRaises(ErrorValidacion):
            servicios.asignar(self.db, sid, 99999, None)  # sección inexistente

    def test_P11_asignacion_valida_y_cambio_de_seccion_con_responsable(self):
        j, otro = self._segunda_seccion()
        sid = self.db.valor("SELECT id FROM servicio_n2 WHERE codigo = ?", ("SE.01.01",))
        r = self.post(self.c, f"/servicios/{sid}/asignacion", {"seccion_id": j["seccion"], "usuario_id": otro}, follow_redirects=True)
        self.assertIn("Asignación guardada", self.texto(r))
        self.assertIn("Otro.Seccion", self.texto(self.c.get(f"/servicios/{sid}")))
        with self.assertRaises(ErrorValidacion):  # mover solo la sección dejaría un responsable ajeno
            servicios.asignar(self.db, sid, self.org["seccion"], otro)
        servicios.asignar(self.db, sid, self.org["seccion"], None)

    def test_asignacion_no_admite_seccion_ni_usuario_inactivos(self):
        j, otro = self._segunda_seccion()
        self.db.ejecutar("UPDATE usuario SET activo = ? WHERE id = ?", (False, otro))
        sid = self.db.valor("SELECT id FROM servicio_n2 WHERE codigo = ?", ("SE.01.01",))
        with self.assertRaises(ErrorValidacion):
            servicios.asignar(self.db, sid, j["seccion"], otro)
        self.db.ejecutar("UPDATE seccion SET activo = ? WHERE id = ?", (False, j["seccion"]))
        with self.assertRaises(ErrorValidacion):
            servicios.asignar(self.db, sid, j["seccion"], None)

    def test_datos_de_demostracion_incluyen_al_menos_tres_asignaciones_validas(self):
        entorno = {"DATABASE_URL": self.url, "DEMO_ADMIN_PASSWORD": "Admin#Demo2026", "DEMO_CONSULTA_PASSWORD": "Consulta#Demo2026"}
        with mock.patch.dict("os.environ", entorno):
            self.assertEqual(cli.main(["datos-demo"]), 0)
            self.assertEqual(cli.main(["datos-demo"]), 0)  # idempotente
        n = self.db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE seccion_id IS NOT NULL")
        self.assertGreaterEqual(n, 3)
        malas = self.db.valor(
            """SELECT COUNT(*) FROM servicio_n2 s JOIN usuario u ON u.id = s.usuario_id JOIN puesto p ON p.id = u.puesto_id
               WHERE p.seccion_id <> s.seccion_id""")
        self.assertEqual(malas, 0)
        self.assertGreaterEqual(self.db.valor("SELECT COUNT(*) FROM servicio_n2 WHERE usuario_id IS NOT NULL"), 3)

    def test_nivel1_alta_edicion_y_baja_logica_con_dependencias(self):
        r = self.post(self.c, "/servicios-n1/nuevo", {"codigo": "SE.99", "nombre": "Nuevo N1"})
        self.assertEqual(r.status_code, 302)
        r = self.post(self.c, "/servicios-n1/nuevo", {"codigo": "SE.99", "nombre": "Otra vez"})
        self.assertIn("Ya existe", self.texto(r))
        con_hijos = self.db.valor("SELECT id FROM servicio_n1 WHERE codigo = ?", ("SE.01",))
        with self.assertRaises(ErrorValidacion):
            servicios.cambiar_estado_n1(self.db, con_hijos, False)
        nuevo = self.db.valor("SELECT id FROM servicio_n1 WHERE codigo = ?", ("SE.99",))
        servicios.cambiar_estado_n1(self.db, nuevo, False)
        r = self.post(self.c, "/servicios/nuevo", self.form(nivel1_id=nuevo))
        self.assertIn("inactivo", self.texto(r))

    def test_baja_logica_de_servicio_no_elimina_informacion(self):
        sid = self.db.valor("SELECT id FROM servicio_n2 WHERE codigo LIKE ? ORDER BY codigo LIMIT 1", ("SE.04%",))
        antes = self.db.valor("SELECT nombre FROM servicio_n2 WHERE id = ?", (sid,))
        self.post(self.c, f"/servicios/{sid}/estado", {"activo": "0"})
        s = self.db.uno("SELECT activo, nombre FROM servicio_n2 WHERE id = ?", (sid,))
        self.assertFalse(s["activo"])
        self.assertEqual(s["nombre"], antes)
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM servicio_n2"), 46)


if __name__ == "__main__":
    unittest.main()
