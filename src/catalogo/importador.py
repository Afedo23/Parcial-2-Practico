"""Importador del catálogo desde CatalogoServicios.xlsx (hoja «Servicios Externos»).

Reglas (ver docs/RESOLUCION.md §4):
  * El Excel es solo una fuente de datos; nunca se modifica ni sus textos se interpretan como instrucciones.
  * Celdas combinadas: el valor efectivo de una celda es el de la celda principal de su rango.
  * Un servicio de nivel 2 se identifica por su código; las filas con el mismo código forman UN registro.
  * Filas sin código de nivel 2 con contenido propio: se omiten y se reportan (no se asignan a otro servicio).
  * Conflictos de nombre (p. ej. SE.12): gana el primer valor (fila menor); los demás quedan como evidencia.
  * Ausencias: se importan como desconocidas (NULL) con estado_revision = REVISION; nunca se rellenan ni se usa 0.
  * Idempotente: el código es la clave natural; repetir produce 0 creados / 0 actualizados.
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import openpyxl

from . import catalogos
from .db import ahora
from .servicios import revision

HOJA = "Servicios Externos"
FILA_ENCABEZADO, PRIMERA, ULTIMA = 4, 5, 101
LISTAS = (112, 122)  # filas de las listas de opciones (columnas E..H)
ENCABEZADOS = [
    "COD.N1", "SERVICIO - Nivel 1", "COD.N2", "SERVICIO - Nivel 2", "ACTIVO", "CLASE DE SERVICIO",
    "CRITICIDAD", "TIPO DE SERVICIO", "Descripción", "Métrica", "Minimo", "Maximo",
]
CONTROL_N1, CONTROL_N2 = 12, 46
COL = dict(n1c=1, n1n=2, n2c=3, n2n=4, activo=5, clase=6, criticidad=7, tipo=8, descripcion=9, metrica=10, minimo=11, maximo=12)


class ErrorImportacion(Exception):
    """El archivo no tiene la estructura esperada (código de salida 2)."""


def norm(v):
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[\s_\-]+", " ", s).strip()


def limpio(v, colapsar=True):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if colapsar:
        s = re.sub(r"[ \t]+", " ", s)
    return s or None


def rango_filas(filas):
    filas = sorted(set(filas))
    partes, ini, prev = [], None, None
    for f in filas:
        if ini is None:
            ini = prev = f
        elif f == prev + 1:
            prev = f
        else:
            partes.append(f"{ini}-{prev}" if ini != prev else f"{ini}")
            ini = prev = f
    if ini is not None:
        partes.append(f"{ini}-{prev}" if ini != prev else f"{ini}")
    return ",".join(partes)


class Hoja:
    """Lectura de celdas resolviendo combinaciones: el valor es el de la celda principal del rango."""

    def __init__(self, ws):
        self.ws = ws
        self.por_celda = {}
        for mr in ws.merged_cells.ranges:
            for r in range(mr.min_row, mr.max_row + 1):
                for c in range(mr.min_col, mr.max_col + 1):
                    self.por_celda[(r, c)] = mr

    def valor(self, r, c):
        mr = self.por_celda.get((r, c))
        return self.ws.cell(mr.min_row, mr.min_col).value if mr else self.ws.cell(r, c).value

    def propio(self, r, c):
        """Valor escrito físicamente en la celda (None si es una celda subordinada de una combinación)."""
        return self.ws.cell(r, c).value


class Informe:
    def __init__(self):
        self.obs = []  # dicts: entidad, codigo, tipo, rango, detalle

    def add(self, entidad, codigo, tipo, rango, detalle):
        self.obs.append(dict(entidad=entidad, codigo=codigo, tipo=tipo, rango=rango, detalle=detalle))


def _leer(path):
    path = Path(path)
    if not path.exists():
        raise ErrorImportacion(f"No existe el archivo {path}. Copie el Excel original a data/CatalogoServicios.xlsx.")
    try:
        wb = openpyxl.load_workbook(path, data_only=True)  # solo lectura lógica: no se guarda
    except Exception as exc:  # noqa: BLE001
        raise ErrorImportacion(f"No se pudo abrir el Excel: {exc}") from exc
    if HOJA not in wb.sheetnames:
        raise ErrorImportacion(f"No existe la hoja «{HOJA}». Hojas: {wb.sheetnames}")
    ws = wb[HOJA]
    for i, esperado in enumerate(ENCABEZADOS, start=1):
        real = ws.cell(FILA_ENCABEZADO, i).value
        if real is None or norm(real) != norm(esperado):
            raise ErrorImportacion(f"Encabezado inesperado en {openpyxl.utils.get_column_letter(i)}{FILA_ENCABEZADO}: {real!r} (esperado {esperado!r})")
    return path, Hoja(ws)


def _codigo(v, entidad, informe, fila, mapeos):
    """Los códigos se conservan como TEXTO. Solo se recortan espacios; si cambia, queda mapeo y observación."""
    if v is None:
        return None, None
    crudo = str(v)
    cod = crudo.strip()
    if isinstance(v, (int, float)):
        informe.add(entidad, cod, "CODIGO_NUMERICO", f"fila {fila}", f"El código venía como número ({crudo}); se convirtió a texto.")
    if not cod:
        return None, None
    if cod != crudo:
        mapeos.append((f"codigo_{entidad}", crudo, cod, "Espacios sobrantes eliminados"))
    return cod, crudo


def _listas_hoja(hoja, informe):
    """Lee las listas de opciones E112:H122 (sin asumirlas: se contrastan con el enunciado)."""
    res = {}
    for campo, col in (("activo", 5), ("clase", 6), ("criticidad", 7), ("tipo", 8)):
        vals = [limpio(hoja.propio(r, col)) for r in range(LISTAS[0], LISTAS[1] + 1)]
        vals = [v for v in vals if v]
        if vals and norm(vals[0]) == norm(ENCABEZADOS[col - 1]):
            vals = vals[1:]
        res[campo] = vals
    return res


def importar(conn, ruta, esperar_controles=True):
    """Ejecuta la importación completa en UNA transacción y devuelve el resumen."""
    path, hoja = _leer(ruta)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    informe, mapeos = Informe(), []
    ws = hoja.ws

    # ---- 1. catálogos (listas de opciones de la hoja vs. enunciado) -------------------------
    listas = _listas_hoja(hoja, informe)
    base = {"clase": catalogos.CLASES, "criticidad": catalogos.CRITICIDADES, "tipo": catalogos.TIPOS, "activo": catalogos.INDICADORES_ACTIVO}
    extra_catalogo = []
    for campo, vals in listas.items():
        faltan_en_hoja = [v for v in base[campo] if v not in vals]
        nuevos = [v for v in vals if v not in base[campo]]
        if faltan_en_hoja or nuevos:
            informe.add("catalogo", campo, "LISTA_DIFERENTE", f"E{LISTAS[0]}:H{LISTAS[1]}",
                        f"Lista «{campo}» distinta del enunciado. Solo en enunciado: {faltan_en_hoja or '-'}; solo en hoja: {nuevos or '-'}.")
        if campo != "activo":
            extra_catalogo += [(campo, v) for v in nuevos]

    # ---- 2. recorrido de filas: agrupar por código -------------------------------------------
    n1s, n2s = {}, {}
    leidas = vacias = sin_codigo = 0
    for r in range(PRIMERA, ULTIMA + 1):
        leidas += 1
        v = {k: hoja.valor(r, c) for k, c in COL.items()}
        if all(limpio(x) is None for x in v.values()):
            vacias += 1
            continue
        c1, c1_raw = _codigo(v["n1c"], "n1", informe, r, mapeos)
        c2, c2_raw = _codigo(v["n2c"], "n2", informe, r, mapeos)
        nombre1, nombre2 = limpio(v["n1n"]), limpio(v["n2n"])
        if c1:
            e = n1s.setdefault(c1, dict(raw=c1_raw, nombres=[], filas=[], rangos=set()))
            e["filas"].append(r)
            if nombre1:
                e["nombres"].append((nombre1, r))
            mr = hoja.por_celda.get((r, COL["n1c"]))
            e["rangos"].add(mr.coord if mr else f"A{r}")
        if c2:
            e = n2s.setdefault(c2, dict(raw=c2_raw, filas=[], n1=[], nombres=[], attrs={k: [] for k in ("activo", "clase", "criticidad", "tipo", "descripcion", "metrica", "minimo", "maximo")}))
            e["filas"].append(r)
            e["n1"].append((c1, r))
            if nombre2:
                e["nombres"].append((nombre2, r))
            for k in e["attrs"]:
                val = v[k]
                if limpio(val) is not None:
                    e["attrs"][k].append((val, r))
        else:
            propio = any(limpio(hoja.propio(r, COL[k])) is not None for k in ("n2n", "activo", "clase", "criticidad", "tipo", "descripcion", "metrica", "minimo", "maximo"))
            if propio:
                sin_codigo += 1
                informe.add("fila", None, "FILA_SIN_CODIGO", f"fila {r}",
                            "Fila con datos pero sin código de nivel 2 fuera de una combinación; se omite y no se asigna a ningún servicio.")

    # ---- 3. resolver N1 (conflictos de nombre) ---------------------------------------------------
    for c2, e in list(n2s.items()):
        distintos = list(dict.fromkeys(c for c, _ in e["n1"] if c))
        if not distintos:
            prefijo = c2.rsplit(".", 1)[0] if "." in c2 else None
            if prefijo and prefijo in n1s:
                e["n1_final"] = prefijo
                informe.add("n2", c2, "N1_DERIVADO", f"fila {rango_filas(e['filas'])}",
                            f"La fila no traía código de nivel 1; se derivó «{prefijo}» del prefijo del código (existe en el archivo).")
            else:
                e["n1_final"] = None
                informe.add("n2", c2, "SIN_N1", f"fila {rango_filas(e['filas'])}", "No se pudo determinar el servicio de nivel 1; se omite.")
        else:
            e["n1_final"] = distintos[0]
            if len(distintos) > 1:
                informe.add("n2", c2, "CONFLICTO_N1", f"fila {rango_filas(e['filas'])}",
                            f"Aparece con varios códigos de nivel 1 {distintos}; se usa el primero ({distintos[0]}).")
    for c2, e in n2s.items():  # N1 referenciado que no tuviera fila propia
        if e.get("n1_final") and e["n1_final"] not in n1s:
            n1s[e["n1_final"]] = dict(raw=e["n1_final"], nombres=[], filas=[], rangos=set())

    with conn.tx():
        ejec = conn.insertar(
            "INSERT INTO import_ejecucion (archivo, sha256, iniciada, estado) VALUES (?,?,?,?)", (path.name, sha, ahora(), "EN_CURSO")
        )
        for campo, v in extra_catalogo:
            catalogos.asegurar_valor(conn, campo, v)
        cat = {c: {norm(f["nombre"]): (f["id"], f["nombre"]) for f in catalogos.listar(conn, c)} for c in catalogos.TABLAS}

        stats = {"n1": dict(creados=0, actualizados=0, omitidos=0, observados=0), "n2": dict(creados=0, actualizados=0, omitidos=0, observados=0)}
        mapa_n1 = {}

        # ---- 4. nivel 1 ------------------------------------------------------------------------
        for cod, e in n1s.items():
            nombres = list(dict.fromkeys(n for n, _ in e["nombres"]))
            distintos = []
            for n in nombres:
                if norm(n) not in [norm(x) for x in distintos]:
                    distintos.append(n)
            canonico = distintos[0] if distintos else "(SIN NOMBRE)"
            fila_can = next((r for n, r in e["nombres"] if n == canonico), None)
            obs_n1 = []
            if not distintos:
                obs_n1.append(("NOMBRE_AUSENTE", "El código no trae nombre en el archivo."))
            if len(distintos) > 1:
                alt = [f"«{n}» (fila {r})" for n, r in e["nombres"] if norm(n) != norm(canonico)]
                obs_n1.append(("CONFLICTO_NOMBRE_N1",
                               f"Mismo código con varios nombres. Canónico: «{canonico}» (fila {fila_can}, primera aparición). "
                               f"Evidencia conservada: {', '.join(dict.fromkeys(alt))}."))
            for tipo, det in obs_n1:
                informe.add("n1", cod, tipo, f"fila {rango_filas(e['filas'])}", det)
            alternos = [n for n in distintos[1:]]
            valores = dict(
                codigo_original=e["raw"], nombre=canonico,
                estado_revision="REVISION" if obs_n1 else "COMPLETO",
                nombres_alternos=json.dumps(alternos, ensure_ascii=False) if alternos else None,
                origen_hoja=HOJA, origen_rango=",".join(sorted(e["rangos"])) or None,
                origen_json=json.dumps({"filas": sorted(set(e["filas"])), "nombres_vistos": e["nombres"]}, ensure_ascii=False),
                transformaciones="; ".join(t for t, _ in obs_n1) or None,
            )
            mapa_n1[cod] = _upsert(conn, "servicio_n1", cod, valores, stats["n1"])

        # ---- 5. nivel 2 ---------------------------------------------------------------------------
        for cod, e in n2s.items():
            if not e["n1_final"]:
                stats["n2"]["omitidos"] += 1
                continue
            rango = rango_filas(e["filas"])
            transf = []

            def primero(k):
                vals = e["attrs"][k]
                distintos = list(dict.fromkeys(limpio(x, colapsar=False) if k == "descripcion" else (limpio(x) if k not in ("minimo", "maximo") else x) for x, _ in vals))
                return vals, distintos

            # nombre
            nombres = list(dict.fromkeys(n for n, _ in e["nombres"]))
            distintos_n = []
            for n in nombres:
                if norm(n) not in [norm(x) for x in distintos_n]:
                    distintos_n.append(n)
            if not distintos_n:
                nombre = "(SIN NOMBRE)"
                informe.add("n2", cod, "NOMBRE_AUSENTE", f"fila {rango}", "El servicio no trae nombre; se marca para revisión.")
            else:
                nombre = distintos_n[0]
                if len(distintos_n) > 1:
                    informe.add("n2", cod, "CONFLICTO_NOMBRE_N2", f"fila {rango}", f"Varios nombres; se usa «{nombre}»; alternos: {distintos_n[1:]}.")
            # ACTIVO
            vals, dist = primero("activo")
            indicador = None
            if dist:
                bruto = dist[0]
                if norm(bruto) in ("s", "n"):
                    indicador = bruto.upper()
                    if indicador != bruto:
                        mapeos.append(("activo", bruto, indicador, "Normalización de mayúsculas"))
                else:
                    indicador = bruto
                    informe.add("n2", cod, "ACTIVO_DESCONOCIDO", f"fila {rango}", f"Valor de ACTIVO distinto de S/N conservado tal cual: «{bruto}».")
                if len(dist) > 1:
                    informe.add("n2", cod, "CONFLICTO_ACTIVO", f"fila {rango}", f"Valores distintos {dist}; se usa el primero.")
            # catálogos
            ids = {}
            for campo in ("clase", "criticidad", "tipo"):
                vals, dist = primero(campo)
                ids[campo] = None
                if not dist:
                    continue
                bruto = dist[0]
                hit = cat[campo].get(norm(bruto))
                if hit:
                    ids[campo] = hit[0]
                    if hit[1] != bruto:
                        mapeos.append((campo, bruto, hit[1], "Normalización de mayúsculas/espacios"))
                        transf.append(f"{campo}: «{bruto}»→«{hit[1]}»")
                else:
                    informe.add("n2", cod, "VALOR_FUERA_DE_CATALOGO", f"fila {rango}",
                                f"{campo.upper()} «{bruto}» no existe en el catálogo; queda sin definir (el valor original se conserva en origen_json).")
                if len(dist) > 1:
                    informe.add("n2", cod, f"CONFLICTO_{campo.upper()}", f"fila {rango}", f"Valores distintos {dist}; se usa el primero.")
            # descripción (varias filas = continuación: se concatenan) y métrica
            vals, dist = primero("descripcion")
            descripcion = "\n".join(d for d in dist if d) or None
            if len(dist) > 1:
                transf.append("descripcion: filas concatenadas")
                informe.add("n2", cod, "DESCRIPCION_MULTIFILA", f"fila {rango}", "Descripción en varias filas; se concatenó en orden.")
            vals, dist = primero("metrica")
            metrica = dist[0] if dist else None
            if len(dist) > 1:
                informe.add("n2", cod, "CONFLICTO_METRICA", f"fila {rango}", f"Valores distintos {dist}; se usa el primero.")
            # umbrales
            umbrales = {}
            for k, etiqueta in (("minimo", "Mínimo"), ("maximo", "Máximo")):
                vals, dist = primero(k)
                umbrales[k] = None
                if dist:
                    try:
                        umbrales[k] = float(str(dist[0]).replace(",", "."))
                    except ValueError:
                        informe.add("n2", cod, "UMBRAL_NO_NUMERICO", f"fila {rango}", f"{etiqueta} «{dist[0]}» no es numérico; queda vacío (no se asume 0).")
                    if len(dist) > 1:
                        informe.add("n2", cod, f"CONFLICTO_{k.upper()}", f"fila {rango}", f"Valores distintos {dist}; se usa el primero.")
            if umbrales["minimo"] is not None and umbrales["maximo"] is not None and umbrales["minimo"] > umbrales["maximo"]:
                informe.add("n2", cod, "UMBRAL_INVERTIDO", f"fila {rango}",
                            f"Mínimo ({umbrales['minimo']}) > máximo ({umbrales['maximo']}); ambos quedan vacíos y se conservan en origen_json.")
                umbrales = {"minimo": None, "maximo": None}
            valores = dict(
                codigo_original=e["raw"], nombre=nombre, nivel1_id=mapa_n1[e["n1_final"]], indicador_activo=indicador,
                clase_id=ids["clase"], criticidad_id=ids["criticidad"], tipo_id=ids["tipo"],
                descripcion=descripcion, metrica=metrica, minimo=umbrales["minimo"], maximo=umbrales["maximo"],
                nombres_alternos=json.dumps(distintos_n[1:], ensure_ascii=False) if len(distintos_n) > 1 else None,
                origen_hoja=HOJA, origen_rango=f"A{min(e['filas'])}:L{max(e['filas'])}",
                origen_json=json.dumps({"filas": e["filas"], "valores": {k: [x for x, _ in v] for k, v in e["attrs"].items()}}, ensure_ascii=False, default=str),
                transformaciones="; ".join(transf) or None,
            )
            valores["estado_revision"] = revision(dict(valores, indicador_activo=indicador))
            _upsert(conn, "servicio_n2", cod, valores, stats["n2"])

        for campo, origen, destino, motivo in dict.fromkeys(mapeos):
            if not conn.uno("SELECT id FROM mapeo_etiquetas WHERE campo = ? AND valor_origen = ?", (campo, origen)):
                conn.ejecutar("INSERT INTO mapeo_etiquetas (campo, valor_origen, valor_destino, motivo) VALUES (?,?,?,?)", (campo, origen, destino, motivo))

        # ---- 6. controles y resumen -------------------------------------------------------------------
        for ent in ("n1", "n2"):  # registros (códigos distintos) con al menos una observación
            stats[ent]["observados"] = len({o["codigo"] for o in informe.obs if o["entidad"] == ent and o["codigo"]})
        n1_obtenidos = conn.valor("SELECT COUNT(*) FROM servicio_n1")
        n2_obtenidos = conn.valor("SELECT COUNT(*) FROM servicio_n2")
        controles = dict(n1_esperado=CONTROL_N1, n1_distintos_en_archivo=len(n1s), n1_en_bd=n1_obtenidos,
                         n2_esperado=CONTROL_N2, n2_distintos_en_archivo=len(n2s), n2_en_bd=n2_obtenidos)
        controles["ok"] = len(n1s) == CONTROL_N1 and len(n2s) == CONTROL_N2
        if not controles["ok"]:
            informe.add("control", None, "CONTROL_DIFERENTE", "hoja", f"Se esperaban {CONTROL_N1} N1 y {CONTROL_N2} N2; el archivo produjo {len(n1s)} y {len(n2s)}.")
        for o in informe.obs:
            conn.ejecutar(
                "INSERT INTO import_observacion (ejecucion_id, entidad, codigo, tipo, hoja, rango, detalle) VALUES (?,?,?,?,?,?,?)",
                (ejec, o["entidad"], o["codigo"], o["tipo"], HOJA, o["rango"], o["detalle"]),
            )
        resumen = dict(
            ejecucion_id=ejec, archivo=path.name, sha256=sha, n1=stats["n1"], n2=stats["n2"],
            filas=dict(leidas=leidas, vacias=vacias, sin_codigo=sin_codigo), controles=controles, observaciones=len(informe.obs),
            por_tipo={t: sum(1 for o in informe.obs if o["tipo"] == t) for t in sorted({o["tipo"] for o in informe.obs})},
        )
        conn.ejecutar("UPDATE import_ejecucion SET estado = ?, resumen = ? WHERE id = ?",
                      ("OK" if controles["ok"] else "CONTROLES_FALLIDOS", json.dumps(resumen, ensure_ascii=False), ejec))
    return resumen, informe.obs


def _upsert(conn, tabla, codigo, valores, stats):
    """Crea, actualiza (si cambió algo) u omite. No toca asignaciones ni la baja lógica."""
    actual = conn.uno(f"SELECT * FROM {tabla} WHERE codigo = ?", (codigo,))
    if actual is None:
        cols = ["codigo"] + list(valores)
        extra = {}
        if tabla == "servicio_n2":
            extra = dict(creado=ahora(), actualizado=ahora())
        cols += list(extra)
        id_ = conn.insertar(
            f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [codigo] + list(valores.values()) + list(extra.values()),
        )
        stats["creados"] += 1
        return id_
    cambios = {k: v for k, v in valores.items() if actual.get(k) != v}
    if cambios:
        if tabla == "servicio_n2":
            cambios["actualizado"] = ahora()
        conn.ejecutar(f"UPDATE {tabla} SET {', '.join(k + ' = ?' for k in cambios)} WHERE id = ?", list(cambios.values()) + [actual["id"]])
        stats["actualizados"] += 1
    else:
        stats["omitidos"] += 1
    return actual["id"]
