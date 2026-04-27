from __future__ import annotations

import logging
from pathlib import Path

from db.connection import DatabaseError, db
from surveillance.security import hash_password
from surveillance import settings


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_SUPERADMIN_USERNAME = settings.DEFAULT_SUPERADMIN_USERNAME
DEFAULT_SUPERADMIN_PASSWORD = settings.DEFAULT_SUPERADMIN_PASSWORD
DEFAULT_SUPERADMIN_EMAIL = settings.DEFAULT_SUPERADMIN_EMAIL
DEFAULT_DEMO_ORG_NAME = settings.DEFAULT_DEMO_ORG_NAME
DEFAULT_DEMO_VEHICLE_ID = settings.DEFAULT_DEMO_VEHICLE_UNIQUE_ID
DEFAULT_DEMO_CAMERA_ID = settings.DEFAULT_DEMO_CAMERA_UNIQUE_ID
BOOTSTRAP_ON_STARTUP = settings.DB_BOOTSTRAP_ON_STARTUP
VEHICLE_CONFIG_TABLE = settings.VEHICLE_TELEMETRY_CONFIG_TABLE


def ensure_bootstrap_seed() -> None:
    if not BOOTSTRAP_ON_STARTUP:
        return
    settings.require_runtime_secrets()

    _ensure_roles()
    superadmin_id = _ensure_superadmin_user()
    organization_id = _ensure_demo_organization(superadmin_id)
    vehicle_id = _ensure_demo_vehicle(superadmin_id, organization_id)
    _ensure_demo_camera(superadmin_id, organization_id, vehicle_id)


def _ensure_roles() -> None:
    roles = (
        ("superadmin", "Superadministrador", 100, True),
        ("administrador", "Administrador", 80, True),
        ("operador", "Operador", 30, True),
    )
    for code, name, level, is_system in roles:
        db.execute(
            """
            INSERT INTO roles (codigo, nombre, nivel_orden, es_sistema)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (codigo)
            DO UPDATE SET
                nombre = EXCLUDED.nombre,
                nivel_orden = EXCLUDED.nivel_orden,
                es_sistema = EXCLUDED.es_sistema;
            """,
            (code, name, level, is_system),
        )


def _ensure_superadmin_user() -> int:
    existing = db.fetch_one(
        """
        SELECT u.id
        FROM usuarios u
        WHERE LOWER(u.usuario) = LOWER(%s)
        LIMIT 1;
        """,
        (DEFAULT_SUPERADMIN_USERNAME,),
    )
    if existing and existing.get("id"):
        return int(existing["id"])

    created = db.execute_returning_one(
        """
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
            %s,
            %s,
            %s,
            %s,
            %s,
            (SELECT id FROM roles WHERE codigo = 'superadmin'),
            TRUE,
            FALSE
        )
        RETURNING id;
        """,
        (
            DEFAULT_SUPERADMIN_USERNAME,
            DEFAULT_SUPERADMIN_EMAIL,
            hash_password(DEFAULT_SUPERADMIN_PASSWORD),
            "Admin",
            "Robiotec",
        ),
    )
    if not created or "id" not in created:
        raise DatabaseError("No se pudo crear el superadmin inicial.")
    return int(created["id"])


def _ensure_demo_organization(superadmin_id: int) -> int:
    existing = db.fetch_one(
        """
        SELECT id
        FROM organizaciones
        WHERE LOWER(nombre) = LOWER(%s)
        LIMIT 1;
        """,
        (DEFAULT_DEMO_ORG_NAME,),
    )
    if existing and existing.get("id"):
        return int(existing["id"])

    created = db.execute_returning_one(
        """
        INSERT INTO organizaciones (
            nombre,
            descripcion,
            propietario_usuario_id,
            creado_por_usuario_id,
            activa
        )
        VALUES (%s, %s, %s, %s, TRUE)
        RETURNING id;
        """,
        (
            DEFAULT_DEMO_ORG_NAME,
            "Organizacion demo inicial para validacion del dashboard.",
            superadmin_id,
            superadmin_id,
        ),
    )
    if not created or "id" not in created:
        raise DatabaseError("No se pudo crear la organizacion demo.")
    return int(created["id"])


def _ensure_demo_vehicle(superadmin_id: int, organization_id: int) -> int:
    existing = db.fetch_one(
        """
        SELECT v.id
        FROM vehiculos v
        LEFT JOIN {config_table} cfg ON cfg.vehiculo_id = v.id
        WHERE LOWER(COALESCE(cfg.config_extra ->> 'identifier', v.numero_serie, v.placa, v.nombre)) = LOWER(%s)
        LIMIT 1;
        """.format(config_table=VEHICLE_CONFIG_TABLE),
        (DEFAULT_DEMO_VEHICLE_ID,),
    )
    if existing and existing.get("id"):
        return int(existing["id"])

    created = db.execute_returning_one(
        """
        INSERT INTO vehiculos (
            organizacion_id,
            propietario_usuario_id,
            creado_por_usuario_id,
            tipo_vehiculo_id,
            nombre,
            descripcion,
            placa,
            numero_serie,
            marca,
            modelo,
            protocolo_comunicacion_id,
            activo
        )
        VALUES (
            %s,
            %s,
            %s,
            (SELECT id FROM tipos_vehiculo WHERE codigo = 'auto'),
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            (SELECT id FROM protocolos_comunicacion WHERE codigo = 'http'),
            TRUE
        )
        RETURNING id;
        """,
        (
            organization_id,
            superadmin_id,
            superadmin_id,
            "Vehiculo Demo",
            "Vehiculo demo con telemetria API local.",
            "DEMO-001",
            DEFAULT_DEMO_VEHICLE_ID,
            "Robiotec",
            "Demo Tracker",
        ),
    )
    if not created or "id" not in created:
        raise DatabaseError("No se pudo crear el vehiculo demo.")

    vehicle_id = int(created["id"])
    db.execute(
        """
        INSERT INTO {config_table} (
            vehiculo_id,
            endpoint,
            baudrate,
            activo,
            config_extra
        )
        VALUES (
            %s,
            %s,
            %s,
            TRUE,
            %s::jsonb
        )
        ON CONFLICT (vehiculo_id)
        DO UPDATE SET
            endpoint = EXCLUDED.endpoint,
            baudrate = EXCLUDED.baudrate,
            activo = EXCLUDED.activo,
            config_extra = EXCLUDED.config_extra;
        """.format(config_table=VEHICLE_CONFIG_TABLE),
        (
            vehicle_id,
            f"http://127.0.0.1:8004/{DEFAULT_DEMO_VEHICLE_ID}/gps",
            0,
            (
                f'{{"telemetry_mode":"api","api_base_url":"http://127.0.0.1:8004",'
                f'"api_device_id":"{DEFAULT_DEMO_VEHICLE_ID}","identifier":"{DEFAULT_DEMO_VEHICLE_ID}"}}'
            ),
        ),
    )
    return vehicle_id


def _ensure_demo_camera(superadmin_id: int, organization_id: int, vehicle_id: int) -> None:
    existing = db.fetch_one(
        """
        SELECT id
        FROM camaras
        WHERE LOWER(codigo_unico) = LOWER(%s)
        LIMIT 1;
        """,
        (DEFAULT_DEMO_CAMERA_ID,),
    )
    if existing and existing.get("id"):
        return

    created = db.execute_returning_one(
        """
        INSERT INTO camaras (
            organizacion_id,
            propietario_usuario_id,
            creado_por_usuario_id,
            nombre,
            descripcion,
            tipo_camara_id,
            protocolo_id,
            codigo_unico,
            marca,
            modelo,
            url_stream,
            hacer_inferencia,
            activa
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            (SELECT id FROM tipos_camara WHERE codigo = 'vehicle'),
            (SELECT id FROM protocolos_comunicacion WHERE codigo = 'rtsp'),
            %s,
            %s,
            %s,
            %s,
            FALSE,
            TRUE
        )
        RETURNING id;
        """,
        (
            organization_id,
            superadmin_id,
            superadmin_id,
            "Camara Demo Movil",
            "Camara demo asociada al vehiculo inicial.",
            DEFAULT_DEMO_CAMERA_ID,
            "Demo",
            "Mobile Cam",
            f"rtsp://127.0.0.1:8654/{DEFAULT_DEMO_CAMERA_ID}",
        ),
    )
    if not created or "id" not in created:
        raise DatabaseError("No se pudo crear la camara demo.")

    camera_id = int(created["id"])
    db.execute(
        """
        INSERT INTO vehiculo_camaras (vehiculo_id, camara_id, posicion)
        VALUES (%s, %s, %s)
        ON CONFLICT (vehiculo_id, camara_id)
        DO UPDATE SET posicion = EXCLUDED.posicion;
        """,
        (vehicle_id, camera_id, "principal"),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db.open()
    try:
        ensure_bootstrap_seed()
        LOGGER.info("Bootstrap completado correctamente.")
    finally:
        db.close()
