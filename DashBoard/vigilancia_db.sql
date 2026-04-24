/*
========================================================================================
ROBIOTEC ECUADOR S.A - Esquema base de vigilancia
Version limpia y mantenible
========================================================================================
*/

-- =====================================================================================
-- 0. CREACION AUTOMATICA DE BASE DE DATOS Y USUARIO (EJECUTAR COMO SUPERUSUARIO)
-- =====================================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dashboard') THEN
        PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE dashboard');
    END IF;
EXCEPTION WHEN OTHERS THEN
    -- Si dblink no está instalado, ignorar
    NULL;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dashboarduser') THEN
        CREATE USER dashboarduser WITH ENCRYPTED PASSWORD 'dashboardpass';
    END IF;
END$$;

GRANT ALL PRIVILEGES ON DATABASE dashboard TO dashboarduser;
-- IMPORTANTE: Ejecutar este bloque en la base 'dashboard' después de crearla
--
-- Otorgar permisos sobre el esquema public
GRANT USAGE, CREATE ON SCHEMA public TO dashboarduser;

BEGIN;

-- =====================================================================================
-- 1. ROLES
-- =====================================================================================

CREATE TABLE IF NOT EXISTS roles (
    id              SMALLSERIAL PRIMARY KEY,
    codigo          VARCHAR(30) UNIQUE NOT NULL,
    nombre          VARCHAR(50) NOT NULL,
    nivel_orden     SMALLINT NOT NULL,
    es_sistema      BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO roles (codigo, nombre, nivel_orden, es_sistema)
VALUES
    ('developer', 'Developer', 100, TRUE),
    ('admin', 'Administrador', 80, TRUE),
    ('engineer', 'Ingeniero', 50, TRUE),
    ('client', 'Cliente', 10, TRUE)
ON CONFLICT (codigo)
DO UPDATE SET
    nombre = EXCLUDED.nombre,
    nivel_orden = EXCLUDED.nivel_orden,
    es_sistema = EXCLUDED.es_sistema;

-- =====================================================================================
-- 2. USUARIOS
-- =====================================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id                      BIGSERIAL PRIMARY KEY,
    usuario                 VARCHAR(50) UNIQUE NOT NULL,
    email                   VARCHAR(120) UNIQUE NOT NULL,
    password_hash           TEXT NOT NULL,
    nombre                  VARCHAR(80) NOT NULL,
    apellido                VARCHAR(80),
    telefono                VARCHAR(25),
    rol_id                  SMALLINT NOT NULL REFERENCES roles(id),
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    cambiar_password        BOOLEAN NOT NULL DEFAULT FALSE,
    creado_por_usuario_id   BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    usuario_padre_id        BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    ultimo_login            TIMESTAMP,
    creado_en               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Debe existir un solo admin por defecto.
DELETE FROM usuarios
WHERE rol_id = (SELECT id FROM roles WHERE codigo = 'admin')
  AND usuario <> 'admin';

DELETE FROM usuarios
WHERE email = 'robiotec@grupominerobonanza.com'
    AND usuario <> 'admin';

INSERT INTO usuarios (
    usuario,
    email,
    password_hash,
    nombre,
    apellido,
    rol_id,
    activo,
    cambiar_password
)
VALUES (
    'admin',
    'robiotec@grupominerobonanza.com',
    'Robiotec@2026',
    'Admin',
    'Principal',
    (SELECT id FROM roles WHERE codigo = 'admin'),
    TRUE,
    FALSE
)
ON CONFLICT (usuario)
DO UPDATE SET
    email = EXCLUDED.email,
    password_hash = EXCLUDED.password_hash,
    nombre = EXCLUDED.nombre,
    apellido = EXCLUDED.apellido,
    rol_id = EXCLUDED.rol_id,
    activo = EXCLUDED.activo,
    cambiar_password = EXCLUDED.cambiar_password,
    actualizado_en = CURRENT_TIMESTAMP;

-- =====================================================================================
-- 3. ORGANIZACIONES
-- =====================================================================================

CREATE TABLE IF NOT EXISTS organizaciones (
    id                      BIGSERIAL PRIMARY KEY,
    nombre                  VARCHAR(150) NOT NULL,
    descripcion             TEXT,
    propietario_usuario_id  BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    creado_por_usuario_id   BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    activa                  BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nombre, propietario_usuario_id)
);

CREATE TABLE IF NOT EXISTS miembros_organizacion (
    id                  BIGSERIAL PRIMARY KEY,
    organizacion_id     BIGINT NOT NULL REFERENCES organizaciones(id) ON DELETE CASCADE,
    usuario_id          BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    rol_miembro         VARCHAR(30) NOT NULL DEFAULT 'miembro',
    fecha_union         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organizacion_id, usuario_id)
);

-- =====================================================================================
-- 4. CATALOGOS
-- =====================================================================================

CREATE TABLE IF NOT EXISTS tipos_camara (
    id      SMALLSERIAL PRIMARY KEY,
    codigo  VARCHAR(30) UNIQUE NOT NULL,
    nombre  VARCHAR(50) NOT NULL
);

INSERT INTO tipos_camara (codigo, nombre)
VALUES
    ('static', 'Estatica'),
    ('vehicle', 'Montada en vehiculo'),
    ('drone', 'Montada en dron')
ON CONFLICT (codigo)
DO UPDATE SET nombre = EXCLUDED.nombre;

CREATE TABLE IF NOT EXISTS protocolos_comunicacion (
    id              SMALLSERIAL PRIMARY KEY,
    codigo          VARCHAR(30) UNIQUE NOT NULL,
    nombre          VARCHAR(50) NOT NULL,
    puerto_default  INTEGER NOT NULL,
    descripcion     TEXT
);

INSERT INTO protocolos_comunicacion (codigo, nombre, puerto_default, descripcion)
VALUES
    ('webrtc', 'WebRTC', 8989, 'Transmision WebRTC'),
    ('hls', 'HLS', 8988, 'Transmision HLS'),
    ('rtsp', 'RTSP', 8654, 'Transmision RTSP'),
    ('rtmp', 'RTMP', 1936, 'Transmision RTMP'),
    ('http', 'HTTP', 80, 'HTTP'),
    ('https', 'HTTPS', 443, 'HTTPS'),
    ('dji', 'DJI', 5600, 'Integracion DJI')
ON CONFLICT (codigo)
DO UPDATE SET
    nombre = EXCLUDED.nombre,
    puerto_default = EXCLUDED.puerto_default,
    descripcion = EXCLUDED.descripcion;

CREATE TABLE IF NOT EXISTS tipos_vehiculo (
    id      SMALLSERIAL PRIMARY KEY,
    codigo  VARCHAR(30) UNIQUE NOT NULL,
    nombre  VARCHAR(50) NOT NULL
);

INSERT INTO tipos_vehiculo (codigo, nombre)
VALUES
    ('auto', 'Vehiculo terrestre'),
    ('drone_robiotec', 'Dron Robiotec'),
    ('drone_dji', 'Dron DJI')
ON CONFLICT (codigo)
DO UPDATE SET nombre = EXCLUDED.nombre;

-- =====================================================================================
-- 5. UBICACIONES Y STREAM SERVER
-- =====================================================================================

CREATE TABLE IF NOT EXISTS geopuntos (
    id              BIGSERIAL PRIMARY KEY,
    latitud         DOUBLE PRECISION NOT NULL,
    longitud        DOUBLE PRECISION NOT NULL,
    altitud_m       DOUBLE PRECISION,
    direccion       TEXT,
    referencia      TEXT,
    creado_en       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS servidores_mediamtx (
    id              BIGSERIAL PRIMARY KEY,
    nombre          VARCHAR(120) NOT NULL,
    descripcion     TEXT,
    ip_publica      VARCHAR(100),
    puerto          INTEGER NOT NULL DEFAULT 8989,
    usuario         VARCHAR(120),
    password        TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================================
-- 6. VEHICULOS Y TELEMETRIA
-- =====================================================================================

CREATE TABLE IF NOT EXISTS vehiculos (
    id                          BIGSERIAL PRIMARY KEY,
    organizacion_id             BIGINT NOT NULL REFERENCES organizaciones(id),
    propietario_usuario_id      BIGINT NOT NULL REFERENCES usuarios(id),
    creado_por_usuario_id       BIGINT NOT NULL REFERENCES usuarios(id),
    tipo_vehiculo_id            SMALLINT NOT NULL REFERENCES tipos_vehiculo(id),
    nombre                      VARCHAR(120),
    descripcion                 TEXT,
    placa                       VARCHAR(20),
    numero_serie                VARCHAR(120),
    marca                       VARCHAR(80),
    modelo                      VARCHAR(80),
    protocolo_comunicacion_id   SMALLINT REFERENCES protocolos_comunicacion(id),
    geopunto_actual_id          BIGINT REFERENCES geopuntos(id),
    activo                      BOOLEAN DEFAULT TRUE,
    creado_en                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vehiculo_camaras (
    id              BIGSERIAL PRIMARY KEY,
    vehiculo_id     BIGINT REFERENCES vehiculos(id) ON DELETE CASCADE,
    camara_id       BIGINT,
    posicion        VARCHAR(50),
    creado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (vehiculo_id, camara_id)
);

-- Nombre legado por compatibilidad con codigo existente.
CREATE TABLE IF NOT EXISTS configuracion_mavlink (
    id                  BIGSERIAL PRIMARY KEY,
    vehiculo_id         BIGINT UNIQUE REFERENCES vehiculos(id),
    cadena_conexion     VARCHAR(255),
    clave_fuente        VARCHAR(120),
    system_id           INTEGER,
    component_id        INTEGER,
    autopilot_uid       BIGINT,
    baud_rate           INTEGER,
    puerto_serial       VARCHAR(120),
    puerto_udp          INTEGER,
    puerto_tcp          INTEGER,
    config_extra        JSONB DEFAULT '{}'::jsonb,
    creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telemetria_actual (
    id                  BIGSERIAL PRIMARY KEY,
    vehiculo_id         BIGINT UNIQUE REFERENCES vehiculos(id),
    organizacion_id     BIGINT REFERENCES organizaciones(id),
    conectado           BOOLEAN DEFAULT FALSE,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    altitud             DOUBLE PRECISION,
    velocidad           DOUBLE PRECISION,
    bateria             INTEGER,
    datos_extra         JSONB DEFAULT '{}'::jsonb,
    actualizado_en      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telemetria_historial (
    id                  BIGSERIAL PRIMARY KEY,
    vehiculo_id         BIGINT REFERENCES vehiculos(id),
    organizacion_id     BIGINT REFERENCES organizaciones(id),
    fecha_registro      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    velocidad           DOUBLE PRECISION,
    datos_extra         JSONB DEFAULT '{}'::jsonb
);

-- =====================================================================================
-- 7. CAMARAS Y EVENTOS
-- =====================================================================================

CREATE TABLE IF NOT EXISTS camaras (
    id                      BIGSERIAL PRIMARY KEY,
    organizacion_id         BIGINT NOT NULL REFERENCES organizaciones(id) ON DELETE CASCADE,
    propietario_usuario_id  BIGINT NOT NULL REFERENCES usuarios(id),
    creado_por_usuario_id   BIGINT NOT NULL REFERENCES usuarios(id),
    nombre                  VARCHAR(120) NOT NULL,
    descripcion             TEXT,
    tipo_camara_id          SMALLINT NOT NULL REFERENCES tipos_camara(id),
    protocolo_id            SMALLINT NOT NULL REFERENCES protocolos_comunicacion(id),
    servidor_mediamtx_id    BIGINT REFERENCES servidores_mediamtx(id),
    codigo_unico            VARCHAR(100) UNIQUE,
    marca                   VARCHAR(80),
    modelo                  VARCHAR(80),
    numero_serie            VARCHAR(120),
    url_stream              TEXT,
    url_rtsp                TEXT,
    ip_camaras_fijas        VARCHAR(100),
    usuario_stream          VARCHAR(120),
    password_stream         TEXT,
    hacer_inferencia        BOOLEAN NOT NULL DEFAULT FALSE,
    geopunto_estatico_id    BIGINT REFERENCES geopuntos(id),
    activa                  BOOLEAN DEFAULT TRUE,
    creado_en               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Requiere camaras creada. Se agrega de forma idempotente.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'vehiculo_camaras_camara_fk'
    ) THEN
        ALTER TABLE vehiculo_camaras
            ADD CONSTRAINT vehiculo_camaras_camara_fk
            FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS eventos (
    id                  BIGSERIAL PRIMARY KEY,
    organizacion_id     BIGINT REFERENCES organizaciones(id),
    camara_id           BIGINT REFERENCES camaras(id),
    vehiculo_id         BIGINT REFERENCES vehiculos(id),
    tipo_evento         VARCHAR(50),
    fecha_evento        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    confianza           DOUBLE PRECISION,
    metadata            JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS auditoria (
    id              BIGSERIAL PRIMARY KEY,
    usuario_id      BIGINT REFERENCES usuarios(id),
    accion          VARCHAR(50),
    entidad         VARCHAR(80),
    entidad_id      VARCHAR(80),
    detalles        JSONB DEFAULT '{}'::jsonb,
    creado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
