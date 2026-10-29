"""CMDB: importación de CMDB.xlsx (fuente real), jerarquía, 5,000 dispositivos sintéticos, relaciones y búsquedas (P03, P04, P14, P16)."""
import json
import os
import platform
import tempfile
import time
import unittest

import openpyxl
from base import RAIZ, AppTestCase
from catalogo import cmdb
from catalogo.errores import ErrorValidacion
from catalogo.importador import ErrorImportacion

CMDB_XLSX = RAIZ / "data" / "CMDB.xlsx"


@unittest.skipUnless(CMDB_XLSX.exists(), "Falta data/CMDB.xlsx")
class TestCmdbExcel(AppTestCase):
    def setUp(self):
        super().setUp()
        self.resumen, self.obs = cmdb.importar_cmdb(self.db, CMDB_XLSX)

    def test_excel_es_fuente_real_de_dos_ci_con_categorias_de_origen(self):
        cis = self.db.consultar("SELECT * FROM cmdb_ci ORDER BY origen_fila")
        self.assertEqual([c["codigo"] for c in cis], ["CI-XLS-SERVIDOR1", "CI-XLS-APLICACION"])
        self.assertTrue(all(c["origen"] == "EXCEL" for c in cis))
        self.assertEqual([c["origen_fila"] for c in cis], [5, 6])
        self.assertEqual(cis[0]["numero_serie"], "SN123456")
        self.assertEqual(cis[0]["fecha_adquisicion"], "2022-01-01")
        self.assertEqual(json.loads(cis[0]["origen_json"])["nombre"], "Servidor1")  # valores originales conservados
        raices = {r["nombre"]: r for r in self.db.consultar("SELECT * FROM cmdb_clasificacion")}
        self.assertEqual(set(raices), {"Hardware", "Software"})
        self.assertTrue(all(r["origen"] == "EXCEL" and r["padre_id"] is None and r["nivel"] == 1 for r in raices.values()))
        self.assertEqual(self.db.valor("SELECT nombre FROM cmdb_clasificacion WHERE id = ?", (cis[0]["clasificacion_id"],)), "Hardware")
        self.assertEqual(self.db.valor("SELECT nombre FROM cmdb_clasificacion WHERE id = ?", (cis[1]["clasificacion_id"],)), "Software")
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'SINTETICO'"), 0, "el Excel no genera dispositivos")

    def test_base_de_datos1_se_conserva_como_texto_sin_inventar_relacion(self):
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_relacion"), 0)
        self.assertIsNone(self.db.uno("SELECT id FROM cmdb_ci WHERE LOWER(nombre) = ?", ("base de datos1",)))
        textos = {c["codigo"]: c["relaciones_texto"] for c in self.db.consultar("SELECT codigo, relaciones_texto FROM cmdb_ci")}
        self.assertEqual(set(textos.values()), {"Base de Datos1"})
        tipos = [o["tipo"] for o in self.db.consultar("SELECT tipo FROM import_observacion WHERE entidad = 'cmdb'")]
        self.assertEqual(tipos.count("RELACION_SIN_CI"), 2)

    def test_encabezados_con_texto_mal_codificado_se_reparan_y_quedan_en_mapeo(self):
        m = self.db.consultar("SELECT valor_origen, valor_destino FROM mapeo_etiquetas WHERE campo = 'cmdb_encabezado'")
        self.assertTrue(any(x["valor_destino"] == "Estado de Configuración" for x in m), m)
        self.assertEqual(self.db.valor("SELECT estado_configuracion FROM cmdb_ci WHERE codigo = ?", ("CI-XLS-SERVIDOR1",)), "Aprobado")

    def test_reimportar_es_idempotente(self):
        r2, _ = cmdb.importar_cmdb(self.db, CMDB_XLSX)
        self.assertEqual((r2["ci"]["creados"], r2["ci"]["actualizados"], r2["ci"]["omitidos"]), (0, 0, 2))
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci"), 2)
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_clasificacion"), 2)

    def test_encabezados_invalidos_se_rechazan_sin_importar_nada(self):
        tmp = os.path.join(tempfile.gettempdir(), "cmdb_malo.xlsx")
        wb = openpyxl.load_workbook(CMDB_XLSX)
        wb.active["D4"] = "Otra cosa"
        wb.save(tmp)
        self.db.ejecutar("DELETE FROM cmdb_ci")
        with self.assertRaises(ErrorImportacion):
            cmdb.importar_cmdb(self.db, tmp)
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci"), 0)
        with self.assertRaises(ErrorImportacion):
            cmdb.importar_cmdb(self.db, "/no/existe.xlsx")

    def test_relacion_se_crea_solo_si_el_ci_existe(self):
        tmp = os.path.join(tempfile.gettempdir(), "cmdb_rel.xlsx")
        wb = openpyxl.load_workbook(CMDB_XLSX)
        wb.active["I6"] = "Servidor1"  # ahora sí existe un CI con ese nombre
        wb.save(tmp)
        cmdb.importar_cmdb(self.db, tmp)
        r = self.db.uno("SELECT r.tipo, o.codigo AS o, d.codigo AS d FROM cmdb_relacion r JOIN cmdb_ci o ON o.id = r.origen_id JOIN cmdb_ci d ON d.id = r.destino_id")
        self.assertEqual((r["o"], r["d"], r["tipo"]), ("CI-XLS-APLICACION", "CI-XLS-SERVIDOR1", "relacionado_con"))

    def test_P04_jerarquia_clasificacion_padre_inexistente_y_ciclos(self):
        hw = self.db.valor("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("CLS-HARDWARE",))
        hijo = cmdb.crear_clasificacion(self.db, "HW-TEST", "Hijo de prueba", hw)
        nieto = cmdb.crear_clasificacion(self.db, "HW-TEST-2", "Nieto de prueba", hijo)
        self.assertEqual([self.db.valor("SELECT nivel FROM cmdb_clasificacion WHERE id = ?", (i,)) for i in (hw, hijo, nieto)], [1, 2, 3])
        self.assertEqual(cmdb.ruta_clasificacion(self.db, nieto), "Hardware / Hijo de prueba / Nieto de prueba")
        with self.assertRaises(ErrorValidacion) as cm:
            cmdb.crear_clasificacion(self.db, "HW-X", "Huérfano", 999999)
        self.assertIn("no existe", str(cm.exception))
        with self.assertRaises(ErrorValidacion):
            cmdb.crear_clasificacion(self.db, "hw-test", "Duplicado", hw)
        with self.assertRaises(ErrorValidacion) as cm:
            cmdb.mover_clasificacion(self.db, hijo, nieto)  # ciclo: el hijo bajo su propio nieto
        self.assertIn("ciclo", str(cm.exception))
        with self.assertRaises(ErrorValidacion):
            cmdb.mover_clasificacion(self.db, hijo, hijo)
        with self.assertRaises(ErrorValidacion):
            cmdb.mover_clasificacion(self.db, hw, hijo)  # categoría de origen: no se reubica
        sw = self.db.valor("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("CLS-SOFTWARE",))
        cmdb.mover_clasificacion(self.db, hijo, sw)  # movimiento válido: recalcula niveles del subárbol
        self.assertEqual(self.db.valor("SELECT nivel FROM cmdb_clasificacion WHERE id = ?", (nieto,)), 3)
        self.assertEqual(cmdb.ruta_clasificacion(self.db, nieto), "Software / Hijo de prueba / Nieto de prueba")


@unittest.skipUnless(CMDB_XLSX.exists(), "Falta data/CMDB.xlsx")
class TestCmdbSintetico(AppTestCase):
    def setUp(self):
        super().setUp()
        self.importar_catalogo()
        cmdb.importar_cmdb(self.db, CMDB_XLSX)

    def test_P03_generar_5000_unicos_y_repetir_sin_duplicados(self):
        r1 = cmdb.generar_sinteticos(self.db, 7, 5000)
        self.assertEqual(r1["dispositivos_en_bd"], 5000)
        hw = self.db.valor("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("CLS-HARDWARE",))
        ids = cmdb.descendientes(self.db, hw)
        marcador = ",".join("?" * len(ids))
        self.assertEqual(self.db.valor(f"SELECT COUNT(DISTINCT codigo) FROM cmdb_ci WHERE origen = 'SINTETICO' AND clasificacion_id IN ({marcador})", ids), 5000)
        self.assertEqual(self.db.valor(f"SELECT COUNT(DISTINCT numero_serie) FROM cmdb_ci WHERE origen = 'SINTETICO' AND clasificacion_id IN ({marcador})", ids), 5000)
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'EXCEL'"), 2, "los 2 CI del Excel no cuentan como dispositivos")
        r2 = cmdb.generar_sinteticos(self.db, 7, 5000)
        self.assertEqual((r2["creados"], r2["actualizados"], r2["relaciones_nuevas"], r2["vinculos_servicio_nuevos"]), (0, 0, 0, 0))
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'SINTETICO'"), r1["ci_sinteticos_en_bd"])
        r3 = cmdb.generar_sinteticos(self.db, 8, 5000)  # otra semilla: mismos códigos, atributos distintos (actualización, no duplicados)
        self.assertEqual(r3["creados"], 0)
        self.assertGreater(r3["actualizados"], 0)
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'SINTETICO'"), r1["ci_sinteticos_en_bd"])

    def test_P03_semilla_igual_produce_atributos_iguales(self):
        cmdb.generar_sinteticos(self.db, 11, 600)
        a = self.db.consultar("SELECT codigo, numero_serie, estado_actual, atributos_json FROM cmdb_ci WHERE origen = 'SINTETICO' ORDER BY codigo")
        self.assertEqual(cmdb.borrar_sinteticos(self.db), len(a))
        cmdb.generar_sinteticos(self.db, 11, 600)
        b = self.db.consultar("SELECT codigo, numero_serie, estado_actual, atributos_json FROM cmdb_ci WHERE origen = 'SINTETICO' ORDER BY codigo")
        self.assertEqual(a, b)
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'EXCEL'"), 2, "el borrado explícito no toca los CI del Excel")

    def test_P03_integridad_ip_solo_en_clases_que_la_requieren_y_reporte_por_categoria(self):
        cmdb.generar_sinteticos(self.db, 5, 5000)
        sin_ip = {"HW-ESTACION", "HW-LAPTOP", "HW-UPS"}
        for clase in sin_ip:
            cls = self.db.valor("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", (clase,))
            for fila in self.db.consultar("SELECT atributos_json FROM cmdb_ci WHERE clasificacion_id = ? LIMIT 50", (cls,)):
                self.assertNotIn("ip", json.loads(fila["atributos_json"]), clase)
        ips = [json.loads(f["atributos_json"]).get("ip") for f in self.db.consultar("SELECT atributos_json FROM cmdb_ci WHERE origen = 'SINTETICO'")]
        ips = [i for i in ips if i]
        self.assertEqual(len(ips), len(set(ips)), "las IP sintéticas son únicas")
        self.assertEqual(self.db.valor("SELECT COUNT(*) FROM cmdb_ci c LEFT JOIN usuario u ON u.id = c.responsable_usuario_id WHERE c.origen='SINTETICO' AND u.id IS NULL"), 0)
        rep = cmdb.reporte(self.db)
        self.assertEqual(rep["dispositivos_sinteticos"], 5000)
        hw = next(f for f in rep["por_categoria"] if f[2] == "CLS-HARDWARE")
        self.assertEqual(hw[6], 5000 + 1)  # subárbol de Hardware: 5,000 sintéticos + el Servidor1 del Excel
        self.assertEqual(sum(rep["por_nivel"].values()), rep["ci_total"])

    def test_requisitos_de_referencia_se_validan(self):
        self.db.ejecutar("DELETE FROM cmdb_ci_servicio")
        self.db.ejecutar("UPDATE servicio_n2 SET seccion_id = NULL, usuario_id = NULL")
        self.db.ejecutar("DELETE FROM servicio_n2")
        with self.assertRaises(ErrorValidacion):
            cmdb.generar_sinteticos(self.db, 1, 100)

    def test_P14_recorrido_ci_servicio_y_manejo_de_ciclos_por_tipo(self):
        cmdb.generar_sinteticos(self.db, 3, 1000)
        # un servidor físico que aloja aplicaciones con servicio vinculado
        fila = self.db.uno("""SELECT d.id AS srv, d.codigo AS srv_codigo FROM cmdb_relacion r JOIN cmdb_ci a ON a.id = r.origen_id JOIN cmdb_ci d ON d.id = r.destino_id
                              JOIN cmdb_ci_servicio v ON v.ci_id = a.id WHERE r.tipo = 'alojado_en' AND a.codigo LIKE 'CI-SYN-APP-%' LIMIT 1""")
        self.assertIsNotNone(fila)
        res = cmdb.servicios_potencialmente_afectados(self.db, fila["srv"])
        self.assertTrue(res["servicios"])
        self.assertIn("POTENCIALMENTE", res["aviso"])
        self.assertGreaterEqual(res["ci_alcanzados"], 1)
        self.assertTrue(all(s["distancia"] >= 0 for s in res["servicios"]))
        # ciclos: depende_de / alojado_en NO los admiten; conectado_a y relacionado_con sí
        a, b, c = [self.db.valor("SELECT id FROM cmdb_ci WHERE codigo = ?", (k,)) for k in ("CI-SYN-LT-00001", "CI-SYN-WS-00001", "CI-SYN-PR-00001")]
        cmdb.crear_relacion(self.db, a, b, "depende_de")
        cmdb.crear_relacion(self.db, b, c, "depende_de")
        with self.assertRaises(ErrorValidacion) as cm:
            cmdb.crear_relacion(self.db, c, a, "depende_de")  # ciclo indirecto a→b→c→a
        self.assertIn("ciclos", str(cm.exception))
        with self.assertRaises(ErrorValidacion):
            cmdb.crear_relacion(self.db, b, a, "alojado_en")  # el ciclo se evalúa sobre el conjunto de dependencias
        cmdb.crear_relacion(self.db, a, b, "conectado_a")
        cmdb.crear_relacion(self.db, b, a, "conectado_a")  # simétrica: ciclo permitido
        cmdb.crear_relacion(self.db, a, b, "relacionado_con")
        cmdb.crear_relacion(self.db, b, a, "relacionado_con")
        with self.assertRaises(ErrorValidacion):
            cmdb.crear_relacion(self.db, a, a, "conectado_a")
        with self.assertRaises(ErrorValidacion):
            cmdb.crear_relacion(self.db, a, 999999999, "conectado_a")
        with self.assertRaises(ErrorValidacion):
            cmdb.crear_relacion(self.db, a, b, "inventada")
        self.assertGreater(cmdb.validar_aciclico(self.db), 0)

    def test_P16_filtros_y_paginacion_con_5000_dispositivos_con_tiempos_observados(self):
        cmdb.generar_sinteticos(self.db, 2026, 5000)
        medidas = {}
        def medir(nombre, **kw):
            t0 = time.perf_counter()
            filas, pg = cmdb.buscar_ci(self.db, **kw)
            medidas[nombre] = round((time.perf_counter() - t0) * 1000, 1)
            return filas, pg
        _, pg = medir("sin_filtros", pagina=1)
        self.assertEqual((pg["total"], pg["paginas"]), (5402 + 0 * 1, 271))  # 5,400 sintéticos + 2 del Excel
        f, pg_last = medir("ultima_pagina", pagina=271)
        self.assertEqual(len(f), 2)
        hw = self.db.valor("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("HW-RED",))
        f, pg = medir("por_clasificacion_con_subcategorias", clasificacion_id=hw)
        self.assertEqual(pg["total"], 250 + 60 + 40)
        self.assertTrue(all(x["clasificacion"] in ("Switch", "Router", "Firewall") for x in f))
        f, pg = medir("busqueda_texto", q="laptop 0123")
        self.assertTrue(f and all("0123" in x["nombre"] for x in f))
        _, pg_a = medir("estado_activo", estado="Activo")
        _, pg_i = medir("estado_inactivo", estado="Inactivo")
        self.assertGreater(pg_a["total"], pg_i["total"])
        ub = self.db.valor("SELECT id FROM cmdb_ubicacion ORDER BY nombre LIMIT 1")
        f, pg = medir("ubicacion", ubicacion_id=ub)
        self.assertTrue(pg["total"] > 0)
        _, pg_x = medir("solo_excel", origen="EXCEL")
        self.assertEqual(pg_x["total"], 2)
        f, pg = medir("combinado", clasificacion_id=self.db.valor("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("HW-PUESTOS",)), estado="Activo", q="lt-0")
        self.assertTrue(all(x["estado_actual"] == "Activo" for x in f))
        print(f"\n[P16] Tiempos observados (ms) en {platform.platform()} · Python {platform.python_version()} · motor {'SQLite' if self.db.sqlite else 'PostgreSQL'}: {medidas}")

    def test_interfaz_cmdb_lectura_para_consulta_y_escritura_solo_admin(self):
        cmdb.generar_sinteticos(self.db, 2026, 300)
        ci = self.db.valor("SELECT id FROM cmdb_ci WHERE codigo = ?", ("CI-SYN-SRVF-00001",))
        c = self.cliente("consulta.test")
        for ruta in ("/cmdb/", "/cmdb/clasificacion/", f"/cmdb/{ci}", "/cmdb/?q=srv&estado=Activo&pagina=2"):
            self.assertEqual(c.get(ruta).status_code, 200, ruta)
        self.assertIn("POTENCIALMENTE", self.texto(c.get(f"/cmdb/{ci}")))
        self.assertEqual(self.post(c, f"/cmdb/{ci}/relaciones", {"tipo": "conectado_a", "destino_codigo": "CI-SYN-LT-00001"}).status_code, 403)
        a = self.cliente("admin.test")
        r = self.post(a, f"/cmdb/{ci}/relaciones", {"tipo": "conectado_a", "destino_codigo": "CI-SYN-LT-00001"}, follow_redirects=True)
        self.assertIn("Relación registrada", self.texto(r))
        r = self.post(a, f"/cmdb/{ci}/relaciones", {"tipo": "conectado_a", "destino_codigo": "NO-EXISTE"}, follow_redirects=True)
        self.assertIn("No existe un CI", self.texto(r))
        self.assertEqual(self.cliente().get("/cmdb/").status_code, 302)


if __name__ == "__main__":
    unittest.main()
