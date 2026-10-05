-- Esquema inicial. {{PK}} y {{TS}} se traducen segun el motor (PostgreSQL o SQLite).
CREATE TABLE empresa (
  id {{PK}},
  codigo VARCHAR(30) NOT NULL UNIQUE,
  nombre VARCHAR(200) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE area (
  id {{PK}},
  codigo VARCHAR(30) NOT NULL,
  nombre VARCHAR(200) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  empresa_id INTEGER NOT NULL REFERENCES empresa(id),
  UNIQUE (empresa_id, codigo)
);
CREATE TABLE departamento (
  id {{PK}},
  codigo VARCHAR(30) NOT NULL,
  nombre VARCHAR(200) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  area_id INTEGER NOT NULL REFERENCES area(id),
  UNIQUE (area_id, codigo)
);
CREATE TABLE seccion (
  id {{PK}},
  codigo VARCHAR(30) NOT NULL,
  nombre VARCHAR(200) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  departamento_id INTEGER NOT NULL REFERENCES departamento(id),
  UNIQUE (departamento_id, codigo)
);
CREATE TABLE puesto (
  id {{PK}},
  codigo VARCHAR(30) NOT NULL,
  nombre VARCHAR(200) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  seccion_id INTEGER NOT NULL REFERENCES seccion(id),
  UNIQUE (seccion_id, codigo)
);
CREATE TABLE usuario (
  id {{PK}},
  nombre VARCHAR(200) NOT NULL,
  login VARCHAR(150) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  rol VARCHAR(20) NOT NULL CHECK (rol IN ('administrador', 'consulta')),
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  puesto_id INTEGER NOT NULL REFERENCES puesto(id),
  creado {{TS}} NOT NULL
);
CREATE TABLE sesion (
  token_hash VARCHAR(64) PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuario(id),
  creada {{TS}} NOT NULL,
  expira {{TS}} NOT NULL
);
CREATE TABLE cat_clase (id {{PK}}, nombre VARCHAR(100) NOT NULL UNIQUE, orden INTEGER NOT NULL);
CREATE TABLE cat_criticidad (id {{PK}}, nombre VARCHAR(100) NOT NULL UNIQUE, orden INTEGER NOT NULL);
CREATE TABLE cat_tipo (id {{PK}}, nombre VARCHAR(100) NOT NULL UNIQUE, orden INTEGER NOT NULL);
CREATE TABLE servicio_n1 (
  id {{PK}},
  codigo VARCHAR(40) NOT NULL UNIQUE,
  codigo_original VARCHAR(80),
  nombre VARCHAR(300) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  estado_revision VARCHAR(20) NOT NULL DEFAULT 'COMPLETO',
  nombres_alternos TEXT,
  origen_hoja VARCHAR(100),
  origen_rango VARCHAR(100),
  origen_json TEXT,
  transformaciones TEXT
);
CREATE TABLE servicio_n2 (
  id {{PK}},
  codigo VARCHAR(40) NOT NULL UNIQUE,
  codigo_original VARCHAR(80),
  nombre VARCHAR(300) NOT NULL,
  nivel1_id INTEGER NOT NULL REFERENCES servicio_n1(id),
  indicador_activo VARCHAR(40),
  clase_id INTEGER REFERENCES cat_clase(id),
  criticidad_id INTEGER REFERENCES cat_criticidad(id),
  tipo_id INTEGER REFERENCES cat_tipo(id),
  descripcion TEXT,
  metrica TEXT,
  minimo DOUBLE PRECISION,
  maximo DOUBLE PRECISION,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  seccion_id INTEGER REFERENCES seccion(id),
  usuario_id INTEGER REFERENCES usuario(id),
  estado_revision VARCHAR(20) NOT NULL DEFAULT 'REVISION',
  nombres_alternos TEXT,
  origen_hoja VARCHAR(100),
  origen_rango VARCHAR(100),
  origen_json TEXT,
  transformaciones TEXT,
  creado {{TS}} NOT NULL,
  actualizado {{TS}} NOT NULL,
  CHECK (minimo IS NULL OR maximo IS NULL OR minimo <= maximo)
);
CREATE INDEX ix_n2_nivel1 ON servicio_n2(nivel1_id);
CREATE INDEX ix_n2_seccion ON servicio_n2(seccion_id);
CREATE TABLE mapeo_etiquetas (
  id {{PK}},
  campo VARCHAR(60) NOT NULL,
  valor_origen VARCHAR(300) NOT NULL,
  valor_destino VARCHAR(300) NOT NULL,
  motivo VARCHAR(300) NOT NULL,
  UNIQUE (campo, valor_origen)
);
CREATE TABLE import_ejecucion (
  id {{PK}},
  archivo VARCHAR(300) NOT NULL,
  sha256 VARCHAR(64) NOT NULL,
  iniciada {{TS}} NOT NULL,
  estado VARCHAR(30) NOT NULL,
  resumen TEXT
);
CREATE TABLE import_observacion (
  id {{PK}},
  ejecucion_id INTEGER NOT NULL REFERENCES import_ejecucion(id),
  entidad VARCHAR(20) NOT NULL,
  codigo VARCHAR(80),
  tipo VARCHAR(60) NOT NULL,
  hoja VARCHAR(100),
  rango VARCHAR(100),
  detalle TEXT NOT NULL
)
