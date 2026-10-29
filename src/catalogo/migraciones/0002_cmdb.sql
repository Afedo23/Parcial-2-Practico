-- CMDB: clasificacion jerarquica, ubicaciones, CI, relaciones tecnicas y vinculo CI-servicio.
CREATE TABLE cmdb_clasificacion (
  id {{PK}},
  codigo VARCHAR(40) NOT NULL UNIQUE,
  nombre VARCHAR(120) NOT NULL,
  padre_id INTEGER REFERENCES cmdb_clasificacion(id),
  nivel INTEGER NOT NULL,
  origen VARCHAR(20) NOT NULL,
  origen_detalle VARCHAR(200),
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (padre_id IS NULL OR padre_id <> id)
);
CREATE TABLE cmdb_ubicacion (
  id {{PK}},
  nombre VARCHAR(160) NOT NULL UNIQUE,
  origen VARCHAR(20) NOT NULL
);
CREATE TABLE cmdb_ci (
  id {{PK}},
  codigo VARCHAR(60) NOT NULL UNIQUE,
  nombre VARCHAR(200) NOT NULL,
  clasificacion_id INTEGER NOT NULL REFERENCES cmdb_clasificacion(id),
  descripcion TEXT,
  numero_serie VARCHAR(80),
  version VARCHAR(60),
  fecha_adquisicion VARCHAR(10),
  estado_actual VARCHAR(60),
  relaciones_texto TEXT,
  padres_hijos_texto TEXT,
  ubicacion_texto VARCHAR(200),
  ubicacion_id INTEGER REFERENCES cmdb_ubicacion(id),
  propietario_texto VARCHAR(200),
  responsable_usuario_id INTEGER REFERENCES usuario(id),
  fecha_cambio VARCHAR(10),
  descripcion_cambio TEXT,
  documentacion_texto TEXT,
  enlaces_texto TEXT,
  nivel_seguridad VARCHAR(60),
  cumplimiento VARCHAR(60),
  estado_configuracion VARCHAR(80),
  numero_licencia VARCHAR(80),
  fecha_vencimiento VARCHAR(10),
  atributos_json TEXT,
  origen VARCHAR(20) NOT NULL,
  origen_hoja VARCHAR(100),
  origen_fila INTEGER,
  origen_json TEXT,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  creado {{TS}} NOT NULL,
  actualizado {{TS}} NOT NULL
);
CREATE INDEX ix_ci_clasificacion ON cmdb_ci(clasificacion_id);
CREATE INDEX ix_ci_nombre ON cmdb_ci(nombre);
CREATE INDEX ix_ci_origen ON cmdb_ci(origen);
CREATE INDEX ix_ci_ubicacion ON cmdb_ci(ubicacion_id);
CREATE TABLE cmdb_relacion (
  id {{PK}},
  origen_id INTEGER NOT NULL REFERENCES cmdb_ci(id),
  destino_id INTEGER NOT NULL REFERENCES cmdb_ci(id),
  tipo VARCHAR(30) NOT NULL CHECK (tipo IN ('depende_de', 'alojado_en', 'conectado_a', 'relacionado_con')),
  origen_dato VARCHAR(20) NOT NULL,
  UNIQUE (origen_id, destino_id, tipo),
  CHECK (origen_id <> destino_id)
);
CREATE INDEX ix_rel_destino ON cmdb_relacion(destino_id);
CREATE TABLE cmdb_ci_servicio (
  ci_id INTEGER NOT NULL REFERENCES cmdb_ci(id),
  servicio_n2_id INTEGER NOT NULL REFERENCES servicio_n2(id),
  PRIMARY KEY (ci_id, servicio_n2_id)
)
