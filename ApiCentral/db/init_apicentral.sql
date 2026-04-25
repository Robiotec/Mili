-- SQL para crear la base de datos y usuario para la API CENTRAL
-- Ejecutar como usuario postgres

-- Crear base de datos solo si no existe
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'apicentral') THEN
        PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE apicentral');
    END IF;
EXCEPTION WHEN OTHERS THEN
    -- Si dblink no está instalado, ignorar
    NULL;
END$$;

-- Crear usuario solo si no existe
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'apicentraluser') THEN
        CREATE USER apicentraluser WITH ENCRYPTED PASSWORD 'apicentralpass';
    END IF;
END$$;

-- Otorgar todos los privilegios al usuario sobre la base de datos
GRANT ALL PRIVILEGES ON DATABASE apicentral TO apicentraluser;
-- Otorgar permisos sobre el esquema public (ejecutar en la base apicentral)
GRANT USAGE, CREATE ON SCHEMA public TO apicentraluser;

-- Crear tabla roles si no existe
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    rol VARCHAR(50) UNIQUE NOT NULL
);

-- Insertar rol admin si no existe
INSERT INTO roles (rol)
VALUES ('admin')
ON CONFLICT (rol) DO NOTHING;

-- Crear tabla usuarios si no existe
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    rol_id INTEGER REFERENCES roles(id)
);

-- Insertar usuario admin con password Robiotec@2025 y rol admin
INSERT INTO usuarios (usuario, password, rol_id)
VALUES ('admin', 'Robiotec@2025', (SELECT id FROM roles WHERE rol = 'admin'))
ON CONFLICT (usuario) DO UPDATE SET password = EXCLUDED.password, rol_id = EXCLUDED.rol_id;
