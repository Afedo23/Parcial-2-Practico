"""CMDB: clasificación jerárquica, CI, relaciones, importador de CMDB.xlsx, generador sintético y recorridos.

Principios (ver docs/CMDB.md):
  * CMDB.xlsx es una FUENTE DE DATOS REAL (2 CI de ejemplo): se importa tal cual, no se usa como plantilla para inventar dispositivos.
  * Los 5,000 dispositivos son datos SINTÉTICOS requeridos por el proyecto: se generan aparte (origen = SINTETICO) y nunca se presentan como datos del Excel.
  * Un texto de «Relaciones» que no corresponde a un CI existente se conserva como texto y genera una observación; no se crea ninguna relación inventada.
"""
import hashlib
import json
import random
import re
import time
import unicodedata
from pathlib import Path

import openpyxl

from .db import ahora
from .errores import ErrorValidacion
from .importador import ErrorImportacion, limpio, norm
from .util import paginar, texto

HOJA = "CMDB"
FILA_ENCABEZADO, PRIMERA, COL0 = 4, 5, 2  # encabezados en B4:U4; datos desde la fila 5
ENCABEZADOS = [
    "Nombre del CI", "Tipo de CI", "Descripción", "Número de Serie", "Versión", "Fecha de Adquisición", "Estado Actual",
    "Relaciones", "Padres/Hijos", "Ubicación Física", "Propietario/Responsable", "Fecha de Cambio", "Descripción del Cambio",
    "Documentación relacionada", "Enlaces a Incidentes y Problemas", "Niveles de Seguridad", "Cumplimiento",
    "Estado de Configuración", "Número de Licencia", "Fecha de Vencimiento",
]
CAMPOS = ["nombre", "tipo", "descripcion", "numero_serie", "version", "fecha_adquisicion", "estado_actual", "relaciones", "padres_hijos",
          "ubicacion", "propietario", "fecha_cambio", "descripcion_cambio", "documentacion", "enlaces", "nivel_seguridad",
          "cumplimiento", "estado_configuracion", "numero_licencia", "fecha_vencimiento"]

# Tipos de relación técnica. Los de «dependencia» NO admiten ciclos; los simétricos/genéricos sí.
TIPOS_REL = ("depende_de", "alojado_en", "conectado_a", "relacionado_con")
TIPOS_SIN_CICLOS = ("depende_de", "alojado_en")

AVISO_IMPACTO = ("Servicios POTENCIALMENTE afectados: la dependencia registrada no implica siempre una interrupción efectiva "
                 "(puede existir redundancia o conmutación).")


def reparar_mojibake(s):
    """El Excel trae texto mal codificado (p. ej. «Configuraci√≥n»): se repara y la corrección queda en el mapeo."""
    if s and "√" in s:
        try:
            return s.encode("mac_roman").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", "-", s).strip("-") or "SIN-NOMBRE"


# ============================================================ clasificación jerárquica
def obtener_clasificacion(conn, id_):
    return conn.uno("SELECT * FROM cmdb_clasificacion WHERE id = ?", (id_,))


def ancestros(conn, id_):
    """IDs desde el nodo hasta la raíz (incluye el propio nodo). Protegido contra ciclos corruptos."""
    res, vistos, actual = [], set(), id_
    while actual is not None and actual not in vistos:
        vistos.add(actual)
        res.append(actual)
        fila = conn.uno("SELECT padre_id FROM cmdb_clasificacion WHERE id = ?", (actual,))
        actual = fila["padre_id"] if fila else None
    return res


def descendientes(conn, id_):
    res, cola = [], [id_]
    while cola:
        actual = cola.pop()
        res.append(actual)
        cola += [r["id"] for r in conn.consultar("SELECT id FROM cmdb_clasificacion WHERE padre_id = ?", (actual,))]
    return res


def ruta_clasificacion(conn, id_):
    nombres = []
    for a in reversed(ancestros(conn, id_)):
        nombres.append(conn.valor("SELECT nombre FROM cmdb_clasificacion WHERE id = ?", (a,)))
    return " / ".join(nombres)


def crear_clasificacion(conn, codigo, nombre, padre_id=None, origen="PROYECTO", detalle=None):
    codigo = (texto(codigo, "Código", maximo=40) or "").upper()
    nombre = texto(nombre, "Nombre", maximo=120)
    nivel = 1
    if padre_id is not None:
        padre = obtener_clasificacion(conn, padre_id)
        if not padre:
            raise ErrorValidacion("La clasificación padre no existe.")
        nivel = padre["nivel"] + 1
    if conn.uno("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", (codigo,)):
        raise ErrorValidacion(f"Ya existe una clasificación con el código «{codigo}».")
    with conn.tx():
        return conn.insertar(
            "INSERT INTO cmdb_clasificacion (codigo, nombre, padre_id, nivel, origen, origen_detalle, activo) VALUES (?,?,?,?,?,?,?)",
            (codigo, nombre, padre_id, nivel, origen, detalle, True),
        )


def mover_clasificacion(conn, id_, nuevo_padre_id):
    """Cambia el padre validando existencia y rechazando ciclos en la jerarquía de clasificación."""
    c = obtener_clasificacion(conn, id_)
    if not c:
        raise ErrorValidacion("La clasificación no existe.")
    if c["origen"] == "EXCEL":
        raise ErrorValidacion("Las categorías de origen (Excel) no se reubican.")
    nivel = 1
    if nuevo_padre_id is not None:
        if nuevo_padre_id == id_:
            raise ErrorValidacion("Una clasificación no puede ser su propio padre.")
        padre = obtener_clasificacion(conn, nuevo_padre_id)
        if not padre:
            raise ErrorValidacion("La clasificación padre no existe.")
        if id_ in ancestros(conn, nuevo_padre_id):
            raise ErrorValidacion("Operación rechazada: crearía un ciclo en la jerarquía de clasificación.")
        nivel = padre["nivel"] + 1
    with conn.tx():
        conn.ejecutar("UPDATE cmdb_clasificacion SET padre_id = ?, nivel = ? WHERE id = ?", (nuevo_padre_id, nivel, id_))
        cola = [(id_, nivel)]
        while cola:
            actual, niv = cola.pop()
            for h in conn.consultar("SELECT id FROM cmdb_clasificacion WHERE padre_id = ?", (actual,)):
                conn.ejecutar("UPDATE cmdb_clasificacion SET nivel = ? WHERE id = ?", (niv + 1, h["id"]))
                cola.append((h["id"], niv + 1))


def _raiz_o_crear(conn, nombre_tipo, fila):
    codigo = "CLS-" + slug(nombre_tipo)
    fila_bd = conn.uno("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", (codigo,))
    if fila_bd:
        return fila_bd["id"], False
    return crear_clasificacion(conn, codigo, nombre_tipo, None, "EXCEL", f"{HOJA}!C{fila}"), True


# ============================================================ relaciones técnicas
def _alcanza(conn, desde, hasta, tipos):
    """¿Existe camino dirigido desde -> hasta usando relaciones de estos tipos?"""
    marcador = ",".join("?" * len(tipos))
    vistos, cola = set(), [desde]
    while cola:
        actual = cola.pop()
        if actual == hasta:
            return True
        if actual in vistos:
            continue
        vistos.add(actual)
        cola += [r["destino_id"] for r in conn.consultar(
            f"SELECT destino_id FROM cmdb_relacion WHERE origen_id = ? AND tipo IN ({marcador})", [actual, *tipos])]
    return False


def crear_relacion(conn, origen_id, destino_id, tipo, origen_dato="MANUAL"):
    if tipo not in TIPOS_REL:
        raise ErrorValidacion(f"Tipo de relación no válido. Use: {', '.join(TIPOS_REL)}.")
    if origen_id == destino_id:
        raise ErrorValidacion("Un CI no puede relacionarse consigo mismo.")
    for id_ in (origen_id, destino_id):
        if not conn.uno("SELECT id FROM cmdb_ci WHERE id = ?", (id_,)):
            raise ErrorValidacion("El CI indicado no existe.")
    if tipo in TIPOS_SIN_CICLOS and _alcanza(conn, destino_id, origen_id, TIPOS_SIN_CICLOS):
        raise ErrorValidacion(f"Relación rechazada: «{tipo}» no admite ciclos y esta relación cerraría uno.")
    if conn.uno("SELECT id FROM cmdb_relacion WHERE origen_id = ? AND destino_id = ? AND tipo = ?", (origen_id, destino_id, tipo)):
        raise ErrorValidacion("Esa relación ya existe.")
    with conn.tx():
        return conn.insertar("INSERT INTO cmdb_relacion (origen_id, destino_id, tipo, origen_dato) VALUES (?,?,?,?)",
                             (origen_id, destino_id, tipo, origen_dato))


def validar_aciclico(conn):
    """Algoritmo de Kahn sobre las relaciones sin ciclos permitidos. Lanza ErrorValidacion si hay un ciclo."""
    marcador = ",".join("?" * len(TIPOS_SIN_CICLOS))
    aristas = conn.consultar(f"SELECT origen_id, destino_id FROM cmdb_relacion WHERE tipo IN ({marcador})", list(TIPOS_SIN_CICLOS))
    grado, sig, nodos = {}, {}, set()
    for a in aristas:
        o, d = a["origen_id"], a["destino_id"]
        nodos |= {o, d}
        sig.setdefault(o, []).append(d)
        grado[d] = grado.get(d, 0) + 1
    cola, hechos = [n for n in nodos if grado.get(n, 0) == 0], 0
    while cola:
        n = cola.pop()
        hechos += 1
        for m in sig.get(n, []):
            grado[m] -= 1
            if grado[m] == 0:
                cola.append(m)
    if hechos != len(nodos):
        raise ErrorValidacion("Se detectó un ciclo en relaciones de dependencia (depende_de / alojado_en).")
    return len(aristas)


def servicios_potencialmente_afectados(conn, ci_id, tipos=TIPOS_SIN_CICLOS):
    """Recorrido inverso: quién depende (directa o indirectamente) del CI y a qué servicios están vinculados."""
    marcador = ",".join("?" * len(tipos))
    distancia, cola, camino = {ci_id: 0}, [ci_id], {ci_id: []}
    while cola:
        actual = cola.pop(0)
        for r in conn.consultar(f"SELECT origen_id, tipo FROM cmdb_relacion WHERE destino_id = ? AND tipo IN ({marcador})", [actual, *tipos]):
            if r["origen_id"] not in distancia:
                distancia[r["origen_id"]] = distancia[actual] + 1
                camino[r["origen_id"]] = camino[actual] + [(r["tipo"], actual)]
                cola.append(r["origen_id"])
    servicios = {}
    for id_, dist in distancia.items():
        for s in conn.consultar(
            """SELECT s.id, s.codigo, s.nombre, c.codigo AS ci_codigo FROM cmdb_ci_servicio v
               JOIN servicio_n2 s ON s.id = v.servicio_n2_id JOIN cmdb_ci c ON c.id = v.ci_id WHERE v.ci_id = ?""", (id_,)):
            previo = servicios.get(s["id"])
            if previo is None or dist < previo["distancia"]:
                servicios[s["id"]] = dict(s, distancia=dist)
    return dict(ci_alcanzados=len(distancia) - 1, servicios=sorted(servicios.values(), key=lambda x: (x["distancia"], x["codigo"])), aviso=AVISO_IMPACTO)


# ============================================================ consultas
def buscar_ci(conn, q=None, clasificacion_id=None, estado=None, ubicacion_id=None, origen=None, pagina=1, por_pagina=20):
    where, params = ["1 = 1"], []
    if q:
        where.append("(LOWER(c.codigo) LIKE ? OR LOWER(c.nombre) LIKE ? OR LOWER(COALESCE(c.numero_serie, '')) LIKE ?)")
        params += [f"%{q.lower()}%"] * 3
    if clasificacion_id:
        ids = descendientes(conn, clasificacion_id)
        where.append(f"c.clasificacion_id IN ({','.join('?' * len(ids))})")
        params += ids
    if estado:
        where.append("LOWER(c.estado_actual) = ?")
        params.append(estado.lower())
    if ubicacion_id:
        where.append("c.ubicacion_id = ?")
        params.append(ubicacion_id)
    if origen in ("EXCEL", "SINTETICO"):
        where.append("c.origen = ?")
        params.append(origen)
    cond = " AND ".join(where)
    total = conn.valor(f"SELECT COUNT(*) FROM cmdb_ci c WHERE {cond}", params)
    pg = paginar(total, pagina, por_pagina)
    filas = conn.consultar(
        f"""SELECT c.id, c.codigo, c.nombre, c.estado_actual, c.origen, c.numero_serie, k.nombre AS clasificacion,
            COALESCE(u.nombre, c.ubicacion_texto) AS ubicacion FROM cmdb_ci c JOIN cmdb_clasificacion k ON k.id = c.clasificacion_id
            LEFT JOIN cmdb_ubicacion u ON u.id = c.ubicacion_id WHERE {cond} ORDER BY c.codigo LIMIT ? OFFSET ?""",
        params + [por_pagina, pg["offset"]],
    )
    return filas, pg


def ficha_ci(conn, id_):
    ci = conn.uno("SELECT c.*, u.nombre AS ubicacion_nombre, r.nombre AS responsable_nombre FROM cmdb_ci c "
                  "LEFT JOIN cmdb_ubicacion u ON u.id = c.ubicacion_id LEFT JOIN usuario r ON r.id = c.responsable_usuario_id WHERE c.id = ?", (id_,))
    if not ci:
        return None
    ci["clasificacion_ruta"] = ruta_clasificacion(conn, ci["clasificacion_id"])
    ci["atributos"] = json.loads(ci["atributos_json"]) if ci["atributos_json"] else {}
    ci["sale"] = conn.consultar("SELECT r.tipo, r.origen_dato, d.id, d.codigo, d.nombre FROM cmdb_relacion r JOIN cmdb_ci d ON d.id = r.destino_id WHERE r.origen_id = ? ORDER BY r.tipo, d.codigo LIMIT 200", (id_,))
    ci["entra"] = conn.consultar("SELECT r.tipo, r.origen_dato, o.id, o.codigo, o.nombre FROM cmdb_relacion r JOIN cmdb_ci o ON o.id = r.origen_id WHERE r.destino_id = ? ORDER BY r.tipo, o.codigo LIMIT 200", (id_,))
    ci["servicios"] = conn.consultar("SELECT s.id, s.codigo, s.nombre FROM cmdb_ci_servicio v JOIN servicio_n2 s ON s.id = v.servicio_n2_id WHERE v.ci_id = ? ORDER BY s.codigo", (id_,))
    ci["impacto"] = servicios_potencialmente_afectados(conn, id_)
    return ci


def arbol_clasificacion(conn):
    """Clasificaciones con cantidad de CI en su subárbol (para vista y reportes)."""
    filas = conn.consultar("SELECT id, codigo, nombre, padre_id, nivel, origen FROM cmdb_clasificacion ORDER BY nivel, codigo")
    directos = {r["clasificacion_id"]: r["n"] for r in conn.consultar("SELECT clasificacion_id, COUNT(*) AS n FROM cmdb_ci GROUP BY clasificacion_id")}
    hijos = {}
    for f in filas:
        hijos.setdefault(f["padre_id"], []).append(f)
    def total(f):
        return directos.get(f["id"], 0) + sum(total(h) for h in hijos.get(f["id"], []))
    orden = []
    def recorrer(padre, prof):
        for f in sorted(hijos.get(padre, []), key=lambda x: x["codigo"]):
            orden.append(dict(f, prof=prof, directos=directos.get(f["id"], 0), total=total(f)))
            recorrer(f["id"], prof + 1)
    recorrer(None, 0)
    return orden


def reporte(conn):
    """Cantidades por nivel y categoría. El total de «dispositivos» cuenta solo CI sintéticos bajo Hardware."""
    arbol = arbol_clasificacion(conn)
    hw = conn.uno("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("CLS-HARDWARE",))
    hw_ids = descendientes(conn, hw["id"]) if hw else []
    disp = 0
    if hw_ids:
        disp = conn.valor(f"SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'SINTETICO' AND clasificacion_id IN ({','.join('?' * len(hw_ids))})", hw_ids)
    por_nivel = {}
    for f in arbol:
        por_nivel.setdefault(f["nivel"], []).append(f)
    return dict(
        ci_total=conn.valor("SELECT COUNT(*) FROM cmdb_ci"),
        ci_excel=conn.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'EXCEL'"),
        ci_sinteticos=conn.valor("SELECT COUNT(*) FROM cmdb_ci WHERE origen = 'SINTETICO'"),
        dispositivos_sinteticos=disp,
        relaciones=conn.valor("SELECT COUNT(*) FROM cmdb_relacion"),
        por_categoria=[(f["nivel"], f["prof"], f["codigo"], f["nombre"], f["origen"], f["directos"], f["total"]) for f in arbol],
        por_nivel={n: sum(f["directos"] for f in fs) for n, fs in sorted(por_nivel.items())},
    )


# ============================================================ importador de CMDB.xlsx
def _fecha(valor, campo, codigo, fila, obs):
    v = limpio(valor)
    if v is None:
        return None
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    obs.append(dict(codigo=codigo, tipo="FECHA_NO_VALIDA", rango=f"fila {fila}", detalle=f"{campo} «{v}» no tiene formato AAAA-MM-DD; queda vacía (el valor original se conserva en origen_json)."))
    return None


def importar_cmdb(conn, ruta):
    """Importa la hoja única de CMDB.xlsx. Idempotente: el código estable del CI se deriva de su nombre."""
    path = Path(ruta)
    if not path.exists():
        raise ErrorImportacion(f"No existe el archivo {path}. Copie CMDB.xlsx a data/CMDB.xlsx.")
    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ErrorImportacion(f"No se pudo abrir el Excel: {exc}") from exc
    ws = wb[HOJA] if HOJA in wb.sheetnames else wb.worksheets[0]
    mapeos, obs = [], []
    for i, esperado in enumerate(ENCABEZADOS):
        crudo = ws.cell(FILA_ENCABEZADO, COL0 + i).value
        real = reparar_mojibake(crudo) if isinstance(crudo, str) else crudo
        if real is None or norm(real) != norm(esperado):
            col = openpyxl.utils.get_column_letter(COL0 + i)
            raise ErrorImportacion(f"Encabezado inesperado en {col}{FILA_ENCABEZADO}: {crudo!r} (esperado {esperado!r}).")
        if crudo != real:
            mapeos.append(("cmdb_encabezado", crudo.strip(), real.strip(), "Texto mal codificado en el Excel (Mac Roman/UTF-8)"))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    filas = []
    for r in range(PRIMERA, (ws.max_row or PRIMERA) + 1):
        crudos = {c: ws.cell(r, COL0 + i).value for i, c in enumerate(CAMPOS)}
        if all(limpio(v) is None for v in crudos.values()):
            continue
        filas.append((r, crudos))
    stats = dict(creados=0, actualizados=0, omitidos=0, observados=0)
    with conn.tx():
        ejec = conn.insertar("INSERT INTO import_ejecucion (archivo, sha256, iniciada, estado) VALUES (?,?,?,?)", (path.name, sha, ahora(), "EN_CURSO"))
        usados, ids_nombre, relaciones_pend = set(), {}, []
        for r, crudos in filas:
            v = {k: limpio(x, colapsar=False) for k, x in crudos.items()}
            nombre = limpio(crudos["nombre"])
            if not nombre:
                obs.append(dict(codigo=None, tipo="FILA_SIN_NOMBRE", rango=f"fila {r}", detalle="Fila con datos pero sin nombre de CI; se omite."))
                stats["omitidos"] += 1
                continue
            tipo = limpio(crudos["tipo"])
            if not tipo:
                obs.append(dict(codigo=None, tipo="TIPO_AUSENTE", rango=f"fila {r}", detalle=f"El CI «{nombre}» no trae Tipo de CI; se omite (no se inventa clasificación)."))
                stats["omitidos"] += 1
                continue
            codigo = "CI-XLS-" + slug(nombre)
            if codigo in usados:
                codigo = f"{codigo}-F{r}"
                obs.append(dict(codigo=codigo, tipo="NOMBRE_REPETIDO", rango=f"fila {r}", detalle="Nombre repetido en el archivo; el código estable lleva el sufijo de la fila."))
            usados.add(codigo)
            cls_id, _ = _raiz_o_crear(conn, tipo, r)
            ci_obs = []
            fecha_adq = _fecha(crudos["fecha_adquisicion"], "Fecha de Adquisición", codigo, r, ci_obs)
            fecha_cam = _fecha(crudos["fecha_cambio"], "Fecha de Cambio", codigo, r, ci_obs)
            fecha_ven = _fecha(crudos["fecha_vencimiento"], "Fecha de Vencimiento", codigo, r, ci_obs)
            if v["ubicacion"] and conn.uno("SELECT id FROM cmdb_ci WHERE LOWER(nombre) = ?", (v["ubicacion"].lower(),)):
                ci_obs.append(dict(codigo=codigo, tipo="UBICACION_ES_CI", rango=f"fila {r}", detalle=f"La ubicación «{v['ubicacion']}» coincide con el nombre de un CI; se conserva como texto sin crear relación."))
            if v["enlaces"] and "(url)" in v["enlaces"]:
                ci_obs.append(dict(codigo=codigo, tipo="ENLACE_MARCADOR", rango=f"fila {r}", detalle="Los enlaces contienen el marcador literal «(url)»; se conserva el texto."))
            valores = dict(
                nombre=nombre, clasificacion_id=cls_id, descripcion=v["descripcion"], numero_serie=v["numero_serie"], version=v["version"],
                fecha_adquisicion=fecha_adq, estado_actual=v["estado_actual"], relaciones_texto=v["relaciones"], padres_hijos_texto=v["padres_hijos"],
                ubicacion_texto=v["ubicacion"], propietario_texto=v["propietario"], fecha_cambio=fecha_cam, descripcion_cambio=v["descripcion_cambio"],
                documentacion_texto=v["documentacion"], enlaces_texto=v["enlaces"], nivel_seguridad=v["nivel_seguridad"], cumplimiento=v["cumplimiento"],
                estado_configuracion=reparar_mojibake(v["estado_configuracion"] or "") or None, numero_licencia=v["numero_licencia"], fecha_vencimiento=fecha_ven,
                origen="EXCEL", origen_hoja=ws.title, origen_fila=r,
                origen_json=json.dumps({k: (str(x) if x is not None else None) for k, x in crudos.items()}, ensure_ascii=False),
            )
            ids_nombre[nombre.lower()] = codigo
            accion = _upsert_ci(conn, codigo, valores)
            stats[accion] += 1
            obs.extend(ci_obs)
            if v["relaciones"]:
                relaciones_pend.append((codigo, r, v["relaciones"]))
            if not v["relaciones"] and v["padres_hijos"]:
                pass
        # Relaciones: solo se crean si el texto corresponde a un CI EXISTENTE; si no, texto + observación.
        for codigo, r, texto_rel in relaciones_pend:
            origen_id = conn.valor("SELECT id FROM cmdb_ci WHERE codigo = ?", (codigo,))
            for destino_nombre in [t.strip() for t in re.split(r"[;,]", texto_rel) if t.strip()]:
                destino = conn.uno("SELECT id, codigo FROM cmdb_ci WHERE LOWER(nombre) = ?", (destino_nombre.lower(),))
                if destino is None:
                    obs.append(dict(codigo=codigo, tipo="RELACION_SIN_CI", rango=f"fila {r}",
                                    detalle=f"«{destino_nombre}» (columna Relaciones) no corresponde a ningún CI existente; se conserva el texto y NO se crea relación."))
                elif destino["id"] == origen_id:
                    obs.append(dict(codigo=codigo, tipo="RELACION_A_SI_MISMO", rango=f"fila {r}", detalle="La relación apunta al propio CI; se ignora."))
                elif not conn.uno("SELECT id FROM cmdb_relacion WHERE origen_id = ? AND destino_id = ? AND tipo = 'relacionado_con'", (origen_id, destino["id"])):
                    crear_relacion(conn, origen_id, destino["id"], "relacionado_con", "EXCEL")
                    obs.append(dict(codigo=codigo, tipo="RELACION_SIN_TIPO", rango=f"fila {r}",
                                    detalle=f"El Excel no indica el tipo de relación con «{destino_nombre}»; se registró como «relacionado_con» (sin semántica de dependencia)."))
        for m in dict.fromkeys(mapeos):
            if not conn.uno("SELECT id FROM mapeo_etiquetas WHERE campo = ? AND valor_origen = ?", (m[0], m[1])):
                conn.ejecutar("INSERT INTO mapeo_etiquetas (campo, valor_origen, valor_destino, motivo) VALUES (?,?,?,?)", m)
        stats["observados"] = len({o["codigo"] for o in obs if o.get("codigo")})
        for o in obs:
            conn.ejecutar("INSERT INTO import_observacion (ejecucion_id, entidad, codigo, tipo, hoja, rango, detalle) VALUES (?,?,?,?,?,?,?)",
                          (ejec, "cmdb", o["codigo"], o["tipo"], ws.title, o["rango"], o["detalle"]))
        resumen = dict(ejecucion_id=ejec, archivo=path.name, sha256=sha, ci=stats, filas_con_datos=len(filas),
                       encabezados_corregidos=len(mapeos), observaciones=len(obs),
                       por_tipo={t: sum(1 for o in obs if o["tipo"] == t) for t in sorted({o["tipo"] for o in obs})})
        conn.ejecutar("UPDATE import_ejecucion SET estado = ?, resumen = ? WHERE id = ?", ("OK", json.dumps(resumen, ensure_ascii=False), ejec))
    return resumen, obs


def _upsert_ci(conn, codigo, valores):
    actual = conn.uno("SELECT * FROM cmdb_ci WHERE codigo = ?", (codigo,))
    if actual is None:
        t = ahora()
        cols = ["codigo", *valores, "activo", "creado", "actualizado"]
        conn.insertar(f"INSERT INTO cmdb_ci ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [codigo, *valores.values(), True, t, t])
        return "creados"
    cambios = {k: v for k, v in valores.items() if actual.get(k) != v}
    if cambios:
        cambios["actualizado"] = ahora()
        conn.ejecutar(f"UPDATE cmdb_ci SET {', '.join(k + ' = ?' for k in cambios)} WHERE id = ?", [*cambios.values(), actual["id"]])
        return "actualizados"
    return "omitidos"


# ============================================================ generador sintético (datos de PRUEBA, no del Excel)
HARDWARE_ARBOL = [
    ("HW-SERVIDORES", "Servidores", [("HW-SRV-FISICO", "Servidor físico", 300), ("HW-SRV-VIRTUAL", "Servidor virtual", 500)]),
    ("HW-RED", "Equipos de red", [("HW-SWITCH", "Switch", 250), ("HW-ROUTER", "Router", 60), ("HW-FIREWALL", "Firewall", 40)]),
    ("HW-PUESTOS", "Puestos de usuario", [("HW-ESTACION", "Estación de trabajo", 1800), ("HW-LAPTOP", "Laptop", 1500)]),
    ("HW-PERIFERICOS", "Periféricos", [("HW-IMPRESORA", "Impresora", 250)]),
    ("HW-INFRA", "Infraestructura de soporte", [("HW-ALMACENAMIENTO", "Almacenamiento", 100), ("HW-UPS", "UPS", 200)]),
]
SOFTWARE_ARBOL = [("SW-APLICACION", "Aplicación", 200), ("SW-BD", "Base de datos", 80), ("SW-SO", "Sistema operativo", 120)]
CLASES_CON_IP = {"HW-SRV-FISICO", "HW-SRV-VIRTUAL", "HW-SWITCH", "HW-ROUTER", "HW-FIREWALL", "HW-ALMACENAMIENTO"}  # impresora: IP opcional; resto sin IP
UBICACIONES = [f"{s} - {a}" for s in ("Sede Central", "Sede Norte", "Sede Sur") for a in ("Sala de Servidores", "Oficinas piso 1", "Oficinas piso 2", "Bodega TI")]
ESTADOS = ["Activo", "En mantenimiento", "Inactivo", "Retirado"]
SO_SRV, SO_PC = ["Linux Server 22", "Windows Server 2022", "Linux Server 24"], ["Windows 11", "Linux Desktop 24", "macOS 15"]
PREFIJO = {"HW-SRV-FISICO": "SRVF", "HW-SRV-VIRTUAL": "SRVV", "HW-SWITCH": "SW", "HW-ROUTER": "RT", "HW-FIREWALL": "FW", "HW-ESTACION": "WS", "HW-LAPTOP": "LT",
           "HW-IMPRESORA": "PR", "HW-ALMACENAMIENTO": "ST", "HW-UPS": "UPS", "SW-APLICACION": "APP", "SW-BD": "DB", "SW-SO": "OS"}


def _repartir(pesos, total):
    suma = sum(p for _, p in pesos)
    cant = {k: int(p * total / suma) for k, p in pesos}
    resto = total - sum(cant.values())
    for k, _ in sorted(pesos, key=lambda x: -x[1]):
        if resto <= 0:
            break
        cant[k] += 1
        resto -= 1
    return cant


def _hoja_arbol(conn):
    """Crea (si faltan) las subcategorías del PROYECTO bajo las raíces de origen Hardware y Software."""
    hw = conn.uno("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("CLS-HARDWARE",))
    sw = conn.uno("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", ("CLS-SOFTWARE",))
    if not hw or not sw:
        raise ErrorValidacion("Faltan las categorías de origen Hardware y Software: ejecute antes la importación de CMDB.xlsx.")
    ids = {}
    def asegurar(codigo, nombre, padre):
        fila = conn.uno("SELECT id FROM cmdb_clasificacion WHERE codigo = ?", (codigo,))
        ids[codigo] = fila["id"] if fila else crear_clasificacion(conn, codigo, nombre, padre, "PROYECTO", "Subcategoría de demostración definida por el proyecto")
    for cod, nom, hojas in HARDWARE_ARBOL:
        asegurar(cod, nom, hw["id"])
        for hcod, hnom, _ in hojas:
            asegurar(hcod, hnom, ids[cod])
    for cod, nom, _ in SOFTWARE_ARBOL:
        asegurar(cod, nom, sw["id"])
    return ids


def generar_sinteticos(conn, semilla=2026, dispositivos=5000):
    """Genera `dispositivos` equipos de hardware (más CI de software) con datos 100 % sintéticos y reproducibles.

    Los códigos NO dependen de la semilla (CI-SYN-<clase>-<n>): repetir la carga con la misma semilla no cambia nada;
    con otra semilla se ACTUALIZAN los atributos de los mismos CI (no se duplican). Las relaciones son deterministas.
    """
    t0 = time.perf_counter()
    usuarios = [r["id"] for r in conn.consultar("SELECT id FROM usuario WHERE activo = ? ORDER BY id", (True,))]
    servicios = [r["id"] for r in conn.consultar("SELECT id FROM servicio_n2 ORDER BY codigo")]
    if not usuarios or not servicios:
        raise ErrorValidacion("Faltan datos de referencia: se requieren usuarios activos y el catálogo de servicios importado.")
    with conn.tx():
        cls = _hoja_arbol(conn)
        for nombre in UBICACIONES:
            if not conn.uno("SELECT id FROM cmdb_ubicacion WHERE nombre = ?", (nombre,)):
                conn.ejecutar("INSERT INTO cmdb_ubicacion (nombre, origen) VALUES (?, ?)", (nombre, "SINTETICO"))
        ubic = [(r["id"], r["nombre"]) for r in conn.consultar("SELECT id, nombre FROM cmdb_ubicacion WHERE origen = 'SINTETICO' ORDER BY nombre")]
        pesos_hw = [(h[0], h[2]) for _, _, hs in HARDWARE_ARBOL for h in hs]
        cant = _repartir(pesos_hw, dispositivos)
        cant.update(_repartir([(c, p) for c, _, p in SOFTWARE_ARBOL], max(3, dispositivos * 400 // 5000)))
        nombres_cls = {h[0]: h[1] for _, _, hs in HARDWARE_ARBOL for h in hs} | {c: n for c, n, _ in SOFTWARE_ARBOL}
        filas, series, ip_n = {}, set(), 0
        for clase in list(PREFIJO):
            for i in range(1, cant.get(clase, 0) + 1):
                codigo = f"CI-SYN-{PREFIJO[clase]}-{i:05d}"
                rng = random.Random(f"{semilla}:{codigo}")
                at, serie = {}, hashlib.sha1(f"{semilla}:{codigo}".encode()).hexdigest()[:12].upper()
                while serie in series:
                    serie = hashlib.sha1((serie + "x").encode()).hexdigest()[:12].upper()
                series.add(serie)
                if clase in ("HW-SRV-FISICO", "HW-SRV-VIRTUAL"):
                    at = dict(so=rng.choice(SO_SRV), ram_gb=rng.choice([16, 32, 64, 128, 256]), cpu=rng.choice([4, 8, 16, 32, 64]))
                elif clase == "HW-SWITCH":
                    at = dict(puertos=rng.choice([24, 48]), capa=rng.choice(["L2", "L3"]))
                elif clase == "HW-ROUTER":
                    at = dict(interfaces=rng.choice([4, 8, 16]))
                elif clase == "HW-FIREWALL":
                    at = dict(throughput_gbps=rng.choice([1, 5, 10, 20]))
                elif clase in ("HW-ESTACION", "HW-LAPTOP"):
                    at = dict(so=rng.choice(SO_PC), ram_gb=rng.choice([8, 16, 32]))
                elif clase == "HW-IMPRESORA":
                    at = dict(color=rng.choice([True, False]), red=rng.random() < 0.5)
                elif clase == "HW-ALMACENAMIENTO":
                    at = dict(capacidad_tb=rng.choice([10, 20, 50, 100]))
                elif clase == "HW-UPS":
                    at = dict(capacidad_va=rng.choice([1000, 1500, 3000]))
                elif clase.startswith("SW-"):
                    at = dict(version_producto=f"{rng.randint(1, 15)}.{rng.randint(0, 9)}")
                if clase in CLASES_CON_IP or (clase == "HW-IMPRESORA" and at.get("red")):
                    ip_n += 1
                    at["ip"] = f"10.{(ip_n >> 16) & 255}.{(ip_n >> 8) & 255}.{ip_n & 255}"
                u_id, u_nom = rng.choice(ubic)
                ordinal = rng.randint(737060, 739890)  # 2018-01 .. 2025-12 aprox.
                fecha = __import__("datetime").date.fromordinal(ordinal).isoformat()
                filas[codigo] = (
                    f"{nombres_cls[clase]} {i:05d}", cls[clase], f"{nombres_cls[clase]} sintético para pruebas", serie, at.get("version_producto") or f"fw-{rng.randint(1, 9)}.{rng.randint(0, 9)}",
                    fecha, rng.choices(ESTADOS, weights=[82, 8, 6, 4])[0], u_nom, u_id, f"Equipo sintético {rng.randint(1, 20):02d}", rng.choice(usuarios),
                    rng.choice(["Alto", "Medio", "Bajo"]), rng.choice(["Cumple", "Cumple", "En revisión"]), rng.choice(["Aprobado", "Pendiente"]),
                    json.dumps(at, ensure_ascii=False, sort_keys=True), clase,
                )
        cols = ["nombre", "clasificacion_id", "descripcion", "numero_serie", "version", "fecha_adquisicion", "estado_actual", "ubicacion_texto", "ubicacion_id",
                "propietario_texto", "responsable_usuario_id", "nivel_seguridad", "cumplimiento", "estado_configuracion", "atributos_json"]
        existentes = {r["codigo"]: tuple(r[c] for c in cols) for r in conn.consultar(f"SELECT codigo, {', '.join(cols)} FROM cmdb_ci WHERE origen = 'SINTETICO'")}
        nuevos, cambios, omitidos, t = [], [], 0, ahora()
        for codigo, f in filas.items():
            val = f[:-1]
            if codigo not in existentes:
                nuevos.append((codigo, *val, "SINTETICO", True, t, t))
            elif existentes[codigo] != tuple(val):
                cambios.append((*val, t, codigo))
            else:
                omitidos += 1
        conn.ejecutar_muchos(f"INSERT INTO cmdb_ci (codigo, {', '.join(cols)}, origen, activo, creado, actualizado) VALUES ({', '.join('?' * (len(cols) + 5))})", nuevos)
        conn.ejecutar_muchos(f"UPDATE cmdb_ci SET {', '.join(c + ' = ?' for c in cols)}, actualizado = ? WHERE codigo = ?", cambios)
        id_de = {r["codigo"]: r["id"] for r in conn.consultar("SELECT id, codigo FROM cmdb_ci WHERE origen = 'SINTETICO'")}
        por_clase = {c: sorted(k for k, f in filas.items() if f[-1] == c) for c in PREFIJO}
        # Relaciones DETERMINISTAS por capas (sin ciclos): VM→host, endpoints→switch, switch→router→firewall, SW→servidor, app→BD
        rel = []
        def elegir(clase, i):
            lista = por_clase.get(clase) or []
            return lista[i % len(lista)] if lista else None
        servidores = por_clase["HW-SRV-FISICO"] + por_clase["HW-SRV-VIRTUAL"]
        for i, c in enumerate(por_clase["HW-SRV-VIRTUAL"]):
            rel.append((c, elegir("HW-SRV-FISICO", i), "alojado_en"))
        for i, c in enumerate(por_clase["HW-SRV-FISICO"] + por_clase["HW-ESTACION"] + por_clase["HW-LAPTOP"] + por_clase["HW-ALMACENAMIENTO"]):
            rel.append((c, elegir("HW-SWITCH", i), "conectado_a"))
        for i, c in enumerate(por_clase["HW-SWITCH"]):
            rel.append((c, elegir("HW-ROUTER", i), "depende_de"))
        for i, c in enumerate(por_clase["HW-ROUTER"]):
            rel.append((c, elegir("HW-FIREWALL", i), "depende_de"))
        for i, c in enumerate(por_clase["SW-APLICACION"] + por_clase["SW-BD"] + por_clase["SW-SO"]):
            if servidores:
                rel.append((c, servidores[i % len(servidores)], "alojado_en"))
        for i, c in enumerate(por_clase["SW-APLICACION"]):
            if por_clase["SW-BD"]:
                rel.append((c, elegir("SW-BD", i), "depende_de"))
        previas = {(r["o"], r["d"], r["t"]) for r in conn.consultar(
            "SELECT o.codigo AS o, d.codigo AS d, r.tipo AS t FROM cmdb_relacion r JOIN cmdb_ci o ON o.id = r.origen_id JOIN cmdb_ci d ON d.id = r.destino_id WHERE o.origen = 'SINTETICO'")}
        nuevas = [(id_de[o], id_de[d], tp, "SINTETICO") for o, d, tp in rel if o and d and o != d and (o, d, tp) not in previas]
        conn.ejecutar_muchos("INSERT INTO cmdb_relacion (origen_id, destino_id, tipo, origen_dato) VALUES (?,?,?,?)", nuevas)
        previos_s = {(r["c"], r["s"]) for r in conn.consultar("SELECT ci_id AS c, servicio_n2_id AS s FROM cmdb_ci_servicio")}
        vinculos = [(id_de[c], servicios[i % len(servicios)]) for i, c in enumerate(por_clase["SW-APLICACION"] + por_clase["SW-BD"]) if (id_de[c], servicios[i % len(servicios)]) not in previos_s]
        conn.ejecutar_muchos("INSERT INTO cmdb_ci_servicio (ci_id, servicio_n2_id) VALUES (?,?)", vinculos)
        aristas = validar_aciclico(conn)
    rep = reporte(conn)
    return dict(semilla=semilla, solicitados=dispositivos, creados=len(nuevos), actualizados=len(cambios), omitidos=omitidos,
                relaciones_nuevas=len(nuevas), vinculos_servicio_nuevos=len(vinculos), aristas_dependencia=aristas,
                dispositivos_en_bd=rep["dispositivos_sinteticos"], ci_sinteticos_en_bd=rep["ci_sinteticos"], segundos=round(time.perf_counter() - t0, 2))


def borrar_sinteticos(conn):
    """Borrado EXPLÍCITO de los datos sintéticos (nunca se ejecuta al arrancar). No toca los CI del Excel."""
    with conn.tx():
        conn.ejecutar("DELETE FROM cmdb_ci_servicio WHERE ci_id IN (SELECT id FROM cmdb_ci WHERE origen = 'SINTETICO')")
        conn.ejecutar("DELETE FROM cmdb_relacion WHERE origen_id IN (SELECT id FROM cmdb_ci WHERE origen = 'SINTETICO') OR destino_id IN (SELECT id FROM cmdb_ci WHERE origen = 'SINTETICO')")
        n = conn.ejecutar("DELETE FROM cmdb_ci WHERE origen = 'SINTETICO'")
    return n
