-- SQL para crear la base de datos y usuario para la API CENTRAL
-- Ejecutar como usuario postgres

-- Crear base de datos
CREATE DATABASE apicentral;

-- Crear usuario y asignar contraseña
CREATE USER apicentraluser WITH ENCRYPTED PASSWORD 'apicentralpass';

-- Otorgar todos los privilegios al usuario sobre la base de datos
GRANT ALL PRIVILEGES ON DATABASE apicentral TO apicentraluser;
