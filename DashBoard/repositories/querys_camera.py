import os
import sys
from typing import Any, Optional
from urllib.parse import urlsplit

if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from db.connection import db as conn
else:
    from db.connection import db as conn

from surveillance.config import validate_camera_source, validate_camera_viewer_source


class CameraRepository:
    def __init__(self) -> None:
        self._select_camera_types_query = """
            SELECT
                id,
                codigo,
                nombre
            FROM tipos_camara
            ORDER BY id;
        """
        self._select_protocols_query = """
            SELECT
                id,
                codigo,
                nombre,
                puerto_default,
                descripcion
            FROM protocolos_comunicacion
            ORDER BY id;
        """
        self._select_active_stream_server_query = """
            SELECT
                id,
                nombre,
                descripcion,
                ip_publica,
                activo
            FROM servidores_mediamtx
            WHERE activo = TRUE
              AND COALESCE(TRIM(ip_publica), '') <> ''
            ORDER BY id
            LIMIT 1;
        """
        self._select_vehicles_query = """
            SELECT
                v.id,
                v.organizacion_id,
                v.propietario_usuario_id,
                v.creado_por_usuario_id,
                v.tipo_vehiculo_id,
                v.nombre,
                v.descripcion,
                v.placa,
                v.numero_serie,
                v.marca,
                v.modelo,
                v.protocolo_comunicacion_id,
                v.geopunto_actual_id,
                v.activo,
                v.creado_en,
                v.actualizado_en,
                o.nombre AS organizacion_nombre,
                owner_user.usuario AS propietario_usuario,
                owner_user.email AS propietario_email,
                owner_user.nombre AS propietario_nombre,
                owner_user.apellido AS propietario_apellido,
                owner_role.codigo AS propietario_rol_codigo,
                owner_role.nombre AS propietario_rol_nombre,
                owner_role.nivel_orden AS propietario_nivel_orden,
                vehicle_type.codigo AS tipo_vehiculo_codigo,
                vehicle_type.nombre AS tipo_vehiculo_nombre,
                current_point.latitud AS geopunto_latitud,
                current_point.longitud AS geopunto_longitud,
                current_point.altitud_m AS geopunto_altitud_m,
                current_point.direccion AS geopunto_direccion,
                current_point.referencia AS geopunto_referencia,
                telemetry.lat AS telemetria_lat,
                telemetry.lon AS telemetria_lon,
                telemetry.altitud AS telemetria_altitud
            FROM vehiculos v
            JOIN organizaciones o ON o.id = v.organizacion_id
            JOIN usuarios owner_user ON owner_user.id = v.propietario_usuario_id
            JOIN roles owner_role ON owner_role.id = owner_user.rol_id
            JOIN tipos_vehiculo vehicle_type ON vehicle_type.id = v.tipo_vehiculo_id
            LEFT JOIN geopuntos current_point ON current_point.id = v.geopunto_actual_id
            LEFT JOIN telemetria_actual telemetry ON telemetry.vehiculo_id = v.id
            ORDER BY v.id;
        """
        self._select_cameras_query = """
            SELECT
                c.id,
                c.organizacion_id,
                c.propietario_usuario_id,
                c.creado_por_usuario_id,
                c.nombre,
                c.descripcion,
                c.tipo_camara_id,
                c.protocolo_id,
                c.codigo_unico,
                c.marca,
                c.modelo,
                c.numero_serie,
                c.url_stream,
                c.url_rtsp,
                c.ip_camaras_fijas,
                c.usuario_stream,
                c.password_stream,
                c.hacer_inferencia,
                c.geopunto_estatico_id,
                c.activa,
                c.creado_en,
                c.actualizado_en,
                org.nombre AS organizacion_nombre,
                owner_user.usuario AS propietario_usuario,
                owner_user.email AS propietario_email,
                owner_user.nombre AS propietario_nombre,
                owner_user.apellido AS propietario_apellido,
                owner_role.codigo AS propietario_rol_codigo,
                owner_role.nombre AS propietario_rol_nombre,
                owner_role.nivel_orden AS propietario_nivel_orden,
                creator_user.usuario AS creado_por_usuario,
                creator_user.email AS creado_por_email,
                camera_type.codigo AS tipo_camara_codigo,
                camera_type.nombre AS tipo_camara_nombre,
                protocol.codigo AS protocolo_codigo,
                protocol.nombre AS protocolo_nombre,
                static_point.latitud AS geopunto_latitud,
                static_point.longitud AS geopunto_longitud,
                static_point.altitud_m AS geopunto_altitud_m,
                static_point.direccion AS geopunto_direccion,
                static_point.referencia AS geopunto_referencia,
                vehicle_link.vehiculo_id,
                vehicle_link.posicion AS vehiculo_posicion,
                vehicle.nombre AS vehiculo_nombre,
                vehicle.descripcion AS vehiculo_descripcion,
                vehicle.placa AS vehiculo_placa,
                vehicle.numero_serie AS vehiculo_numero_serie,
                vehicle.marca AS vehiculo_marca,
                vehicle.modelo AS vehiculo_modelo,
                vehicle.activo AS vehiculo_activo,
                vehicle_type.codigo AS vehiculo_tipo_codigo,
                vehicle_type.nombre AS vehiculo_tipo_nombre,
                vehicle_owner.usuario AS vehiculo_propietario_usuario,
                vehicle_owner.nombre AS vehiculo_propietario_nombre,
                vehicle_owner.apellido AS vehiculo_propietario_apellido,
                vehicle_owner_role.codigo AS vehiculo_propietario_rol_codigo,
                vehicle_owner_role.nombre AS vehiculo_propietario_rol_nombre,
                vehicle_owner_role.nivel_orden AS vehiculo_propietario_nivel_orden,
                vehicle_point.latitud AS vehiculo_geopunto_latitud,
                vehicle_point.longitud AS vehiculo_geopunto_longitud,
                vehicle_point.altitud_m AS vehiculo_geopunto_altitud_m,
                telemetry.lat AS telemetria_lat,
                telemetry.lon AS telemetria_lon,
                telemetry.altitud AS telemetria_altitud,
                CASE
                    WHEN camera_type.codigo = 'static' THEN static_point.latitud
                    ELSE COALESCE(telemetry.lat, vehicle_point.latitud)
                END AS latitud_mapa,
                CASE
                    WHEN camera_type.codigo = 'static' THEN static_point.longitud
                    ELSE COALESCE(telemetry.lon, vehicle_point.longitud)
                END AS longitud_mapa,
                CASE
                    WHEN camera_type.codigo = 'static' THEN static_point.altitud_m
                    ELSE COALESCE(telemetry.altitud, vehicle_point.altitud_m)
                END AS altitud_mapa
            FROM camaras c
            JOIN organizaciones org ON org.id = c.organizacion_id
            JOIN usuarios owner_user ON owner_user.id = c.propietario_usuario_id
            JOIN roles owner_role ON owner_role.id = owner_user.rol_id
            JOIN usuarios creator_user ON creator_user.id = c.creado_por_usuario_id
            JOIN tipos_camara camera_type ON camera_type.id = c.tipo_camara_id
            JOIN protocolos_comunicacion protocol ON protocol.id = c.protocolo_id
            LEFT JOIN geopuntos static_point ON static_point.id = c.geopunto_estatico_id
            LEFT JOIN vehiculo_camaras vehicle_link ON vehicle_link.camara_id = c.id
            LEFT JOIN vehiculos vehicle ON vehicle.id = vehicle_link.vehiculo_id
            LEFT JOIN tipos_vehiculo vehicle_type ON vehicle_type.id = vehicle.tipo_vehiculo_id
            LEFT JOIN usuarios vehicle_owner ON vehicle_owner.id = vehicle.propietario_usuario_id
            LEFT JOIN roles vehicle_owner_role ON vehicle_owner_role.id = vehicle_owner.rol_id
            LEFT JOIN geopuntos vehicle_point ON vehicle_point.id = vehicle.geopunto_actual_id
            LEFT JOIN telemetria_actual telemetry ON telemetry.vehiculo_id = vehicle.id
            {where_clause}
            ORDER BY c.id;
        """
        self._select_camera_by_id_query = self._select_cameras_query.format(where_clause="WHERE c.id = %s")
        self._select_all_cameras_query = self._select_cameras_query.format(where_clause="")
        self._select_active_cameras_query = self._select_cameras_query.format(where_clause="WHERE c.activa = TRUE")
        self._select_camera_duplicate_query = """
            SELECT id
            FROM camaras
            WHERE organizacion_id = %s
              AND LOWER(nombre) = LOWER(%s)
            LIMIT 1;
        """
        self._select_camera_code_duplicate_query = """
            SELECT id
            FROM camaras
            WHERE codigo_unico IS NOT NULL
              AND LOWER(codigo_unico) = LOWER(%s)
            LIMIT 1;
        """
        self._select_camera_events_count_query = """
            SELECT COUNT(*)::INT AS total
            FROM eventos
            WHERE camara_id = %s;
        """
        self._select_camera_type_by_code_query = """
            SELECT id, codigo, nombre
            FROM tipos_camara
            WHERE LOWER(codigo) = LOWER(%s)
               OR LOWER(nombre) = LOWER(%s)
            LIMIT 1;
        """
        self._select_protocol_by_code_query = """
            SELECT id, codigo, nombre
            FROM protocolos_comunicacion
            WHERE LOWER(codigo) = LOWER(%s)
               OR LOWER(nombre) = LOWER(%s)
            LIMIT 1;
        """
        self._select_user_exists_query = """
            SELECT id
            FROM usuarios
            WHERE id = %s
            LIMIT 1;
        """
        self._select_organization_exists_query = """
            SELECT id
            FROM organizaciones
            WHERE id = %s
            LIMIT 1;
        """
        self._select_vehicle_by_id_query = """
            SELECT
                v.id,
                v.organizacion_id,
                v.propietario_usuario_id,
                vehicle_type.codigo AS tipo_vehiculo_codigo
            FROM vehiculos v
            JOIN tipos_vehiculo vehicle_type ON vehicle_type.id = v.tipo_vehiculo_id
            WHERE v.id = %s
            LIMIT 1;
        """
        self._insert_geopoint_query = """
            INSERT INTO geopuntos (
                latitud,
                longitud,
                altitud_m,
                direccion,
                referencia
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        self._update_geopoint_query = """
            UPDATE geopuntos
            SET
                latitud = %s,
                longitud = %s,
                altitud_m = %s,
                direccion = %s,
                referencia = %s
            WHERE id = %s
            RETURNING id;
        """
        self._delete_geopoint_query = """
            DELETE FROM geopuntos
            WHERE id = %s;
        """
        self._insert_camera_query = """
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
                numero_serie,
                url_stream,
                url_rtsp,
                ip_camaras_fijas,
                usuario_stream,
                password_stream,
                hacer_inferencia,
                geopunto_estatico_id,
                activa
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        self._update_camera_query = """
            UPDATE camaras
            SET
                organizacion_id = %s,
                propietario_usuario_id = %s,
                nombre = %s,
                descripcion = %s,
                tipo_camara_id = %s,
                protocolo_id = %s,
                codigo_unico = %s,
                marca = %s,
                modelo = %s,
                numero_serie = %s,
                url_stream = %s,
                url_rtsp = %s,
                ip_camaras_fijas = %s,
                usuario_stream = %s,
                password_stream = %s,
                hacer_inferencia = %s,
                geopunto_estatico_id = %s,
                activa = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id;
        """
        self._update_camera_inference_query = """
            UPDATE camaras
            SET
                hacer_inferencia = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id;
        """
        self._delete_camera_query = """
            DELETE FROM camaras
            WHERE id = %s
            RETURNING id;
        """
        self._upsert_vehicle_camera_query = """
            INSERT INTO vehiculo_camaras (
                vehiculo_id,
                camara_id,
                posicion
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (vehiculo_id, camara_id)
            DO UPDATE SET posicion = EXCLUDED.posicion
            RETURNING id;
        """
        self._delete_vehicle_camera_by_camera_query = """
            DELETE FROM vehiculo_camaras
            WHERE camara_id = %s;
        """

    def list_camera_types(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._select_camera_types_query)

    def list_protocols(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._select_protocols_query)

    def get_active_stream_server(self) -> Optional[dict[str, Any]]:
        return conn.fetch_one(self._select_active_stream_server_query)

    def list_vehicles(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._select_vehicles_query)

    def list_cameras(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        query = self._select_active_cameras_query if active_only else self._select_all_cameras_query
        return conn.fetch_all(query)

    def get_camera_by_id(self, camera_id: int) -> Optional[dict[str, Any]]:
        return conn.fetch_one(self._select_camera_by_id_query, (camera_id,))

    def create_camera(
        self,
        *,
        organization_id: int,
        owner_user_id: int,
        created_by_user_id: int,
        name: str,
        description: str | None,
        camera_type: str,
        protocol: str,
        stream_url: str,
        rtsp_url: str = "",
        fixed_camera_ip: str | None = None,
        unique_code: str | None = None,
        brand: str | None = None,
        model: str | None = None,
        serial_number: str | None = None,
        stream_username: str | None = None,
        stream_password: str | None = None,
        inference_enabled: bool = False,
        active: bool = True,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude_m: float | None = None,
        address: str | None = None,
        reference: str | None = None,
        vehicle_id: int | None = None,
        vehicle_position: str | None = None,
    ) -> dict[str, Any]:
        normalized_payload = self._normalize_camera_payload(
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            camera_type=camera_type,
            protocol=protocol,
            stream_url=stream_url,
            rtsp_url=rtsp_url,
            fixed_camera_ip=fixed_camera_ip,
            unique_code=unique_code,
            brand=brand,
            model=model,
            serial_number=serial_number,
            stream_username=stream_username,
            stream_password=stream_password,
            inference_enabled=inference_enabled,
            active=active,
            latitude=latitude,
            longitude=longitude,
            altitude_m=altitude_m,
            address=address,
            reference=reference,
            vehicle_id=vehicle_id,
            vehicle_position=vehicle_position,
            current_camera_id=None,
        )

        with conn.connection() as db_conn:
            with db_conn.cursor() as cur:
                geopoint_id = self._persist_static_geopoint(cur, normalized_payload, existing_geopoint_id=None)
                created = cur.execute(
                    self._insert_camera_query,
                    (
                        normalized_payload["organization_id"],
                        normalized_payload["owner_user_id"],
                        normalized_payload["created_by_user_id"],
                        normalized_payload["name"],
                        normalized_payload["description"],
                        normalized_payload["camera_type_id"],
                        normalized_payload["protocol_id"],
                        normalized_payload["unique_code"],
                        normalized_payload["brand"],
                        normalized_payload["model"],
                        normalized_payload["serial_number"],
                        normalized_payload["stream_url"],
                        normalized_payload["rtsp_url"],
                        normalized_payload["fixed_camera_ip"],
                        normalized_payload["stream_username"],
                        normalized_payload["stream_password"],
                        normalized_payload["inference_enabled"],
                        geopoint_id,
                        normalized_payload["active"],
                    ),
                ).fetchone()
                if not created or "id" not in created:
                    raise ValueError("camera_creation_failed")

                camera_id = int(created["id"])
                self._persist_vehicle_link(cur, camera_id, normalized_payload)

        camera = self.get_camera_by_id(camera_id)
        if camera is None:
            raise ValueError("camera_creation_failed")
        return camera

    def update_camera(
        self,
        camera_id: int,
        *,
        organization_id: int,
        owner_user_id: int,
        name: str,
        description: str | None,
        camera_type: str,
        protocol: str,
        stream_url: str,
        rtsp_url: str = "",
        fixed_camera_ip: str | None = None,
        unique_code: str | None = None,
        brand: str | None = None,
        model: str | None = None,
        serial_number: str | None = None,
        stream_username: str | None = None,
        stream_password: str | None = None,
        inference_enabled: bool = False,
        active: bool = True,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude_m: float | None = None,
        address: str | None = None,
        reference: str | None = None,
        vehicle_id: int | None = None,
        vehicle_position: str | None = None,
        preserve_stream_password: bool = True,
    ) -> dict[str, Any]:
        existing = self.get_camera_by_id(camera_id)
        if existing is None:
            raise ValueError("camera_not_found")

        normalized_payload = self._normalize_camera_payload(
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            created_by_user_id=int(existing.get("creado_por_usuario_id") or 0),
            name=name,
            description=description,
            camera_type=camera_type,
            protocol=protocol,
            stream_url=stream_url,
            rtsp_url=rtsp_url,
            fixed_camera_ip=fixed_camera_ip,
            unique_code=unique_code,
            brand=brand,
            model=model,
            serial_number=serial_number,
            stream_username=stream_username,
            stream_password=(
                existing.get("password_stream")
                if preserve_stream_password and (stream_password is None or not str(stream_password).strip())
                else stream_password
            ),
            inference_enabled=inference_enabled,
            active=active,
            latitude=latitude,
            longitude=longitude,
            altitude_m=altitude_m,
            address=address,
            reference=reference,
            vehicle_id=vehicle_id,
            vehicle_position=vehicle_position,
            current_camera_id=camera_id,
        )

        existing_geopoint_id = self._normalize_optional_positive_int(existing.get("geopunto_estatico_id"))

        with conn.connection() as db_conn:
            with db_conn.cursor() as cur:
                geopoint_id = self._persist_static_geopoint(
                    cur,
                    normalized_payload,
                    existing_geopoint_id=existing_geopoint_id,
                )
                updated = cur.execute(
                    self._update_camera_query,
                    (
                        normalized_payload["organization_id"],
                        normalized_payload["owner_user_id"],
                        normalized_payload["name"],
                        normalized_payload["description"],
                        normalized_payload["camera_type_id"],
                        normalized_payload["protocol_id"],
                        normalized_payload["unique_code"],
                        normalized_payload["brand"],
                        normalized_payload["model"],
                        normalized_payload["serial_number"],
                        normalized_payload["stream_url"],
                        normalized_payload["rtsp_url"],
                        normalized_payload["fixed_camera_ip"],
                        normalized_payload["stream_username"],
                        normalized_payload["stream_password"],
                        normalized_payload["inference_enabled"],
                        geopoint_id,
                        normalized_payload["active"],
                        camera_id,
                    ),
                ).fetchone()
                if not updated or "id" not in updated:
                    raise ValueError("camera_update_failed")

                self._persist_vehicle_link(cur, camera_id, normalized_payload)

                if normalized_payload["camera_type_code"] != "static" and existing_geopoint_id is not None:
                    cur.execute(self._delete_geopoint_query, (existing_geopoint_id,))

        camera = self.get_camera_by_id(camera_id)
        if camera is None:
            raise ValueError("camera_update_failed")
        return camera

    def set_camera_inference_enabled(
        self,
        camera_id: int,
        *,
        inference_enabled: bool,
    ) -> dict[str, Any]:
        existing = self.get_camera_by_id(camera_id)
        if existing is None:
            raise ValueError("camera_not_found")

        updated = conn.fetch_one(
            self._update_camera_inference_query,
            (
                self._normalize_bool(inference_enabled, default=False),
                camera_id,
            ),
        )
        if not updated or "id" not in updated:
            raise ValueError("camera_update_failed")

        camera = self.get_camera_by_id(camera_id)
        if camera is None:
            raise ValueError("camera_update_failed")
        return camera

    def delete_camera(self, camera_id: int) -> dict[str, Any]:
        existing = self.get_camera_by_id(camera_id)
        if existing is None:
            raise ValueError("camera_not_found")
        if self._count_events_for_camera(camera_id) > 0:
            raise ValueError("camera_in_use")

        geopoint_id = self._normalize_optional_positive_int(existing.get("geopunto_estatico_id"))

        with conn.connection() as db_conn:
            with db_conn.cursor() as cur:
                cur.execute(self._delete_vehicle_camera_by_camera_query, (camera_id,))
                deleted = cur.execute(self._delete_camera_query, (camera_id,)).fetchone()
                if not deleted:
                    raise ValueError("camera_delete_failed")
                if geopoint_id is not None:
                    cur.execute(self._delete_geopoint_query, (geopoint_id,))

        return existing

    def _normalize_camera_payload(
        self,
        *,
        organization_id: int,
        owner_user_id: int,
        created_by_user_id: int,
        name: str,
        description: str | None,
        camera_type: str,
        protocol: str,
        stream_url: str,
        rtsp_url: str,
        fixed_camera_ip: str | None,
        unique_code: str | None,
        brand: str | None,
        model: str | None,
        serial_number: str | None,
        stream_username: str | None,
        stream_password: str | None,
        inference_enabled: bool,
        active: bool,
        latitude: float | None,
        longitude: float | None,
        altitude_m: float | None,
        address: str | None,
        reference: str | None,
        vehicle_id: int | None,
        vehicle_position: str | None,
        current_camera_id: int | None,
    ) -> dict[str, Any]:
        normalized_organization_id = self._normalize_positive_int(organization_id, error_code="invalid_organization_id")
        normalized_owner_user_id = self._normalize_positive_int(owner_user_id, error_code="invalid_owner_user_id")
        normalized_creator_user_id = self._normalize_positive_int(created_by_user_id, error_code="invalid_creator_user_id")
        normalized_name = self._normalize_required_text(name, max_length=120, error_code="invalid_camera_name")
        normalized_description = self._normalize_optional_text(description, max_length=4000)
        normalized_stream_url = self._normalize_stream_url(stream_url)
        normalized_rtsp_url = self._normalize_rtsp_url(rtsp_url)
        normalized_fixed_camera_ip = self._normalize_camera_ip(fixed_camera_ip, normalized_rtsp_url)
        normalized_unique_code = self._normalize_optional_text(unique_code, max_length=100)
        normalized_brand = self._normalize_optional_text(brand, max_length=80)
        normalized_model = self._normalize_optional_text(model, max_length=80)
        normalized_serial_number = self._normalize_optional_text(serial_number, max_length=120)
        normalized_stream_username = self._normalize_optional_text(stream_username, max_length=120)
        normalized_stream_password = self._normalize_optional_text(stream_password, max_length=4000)
        normalized_inference_enabled = self._normalize_bool(inference_enabled, default=False)
        normalized_address = self._normalize_optional_text(address, max_length=4000)
        normalized_reference = self._normalize_optional_text(reference, max_length=4000)
        normalized_vehicle_position = self._normalize_optional_text(vehicle_position, max_length=50)
        normalized_active = self._normalize_bool(active, default=True)
        normalized_latitude = self._normalize_coordinate(latitude, minimum=-90.0, maximum=90.0, error_code="invalid_camera_location")
        normalized_longitude = self._normalize_coordinate(longitude, minimum=-180.0, maximum=180.0, error_code="invalid_camera_location")
        normalized_altitude = self._normalize_optional_float(altitude_m, error_code="invalid_camera_altitude")
        normalized_vehicle_id = self._normalize_optional_positive_int(vehicle_id)

        if not normalized_stream_url and not normalized_rtsp_url:
            raise ValueError("invalid_camera_stream_url")

        if not self._entity_exists(self._select_organization_exists_query, normalized_organization_id):
            raise ValueError("organization_not_found")
        if not self._entity_exists(self._select_user_exists_query, normalized_owner_user_id):
            raise ValueError("owner_user_not_found")
        if not self._entity_exists(self._select_user_exists_query, normalized_creator_user_id):
            raise ValueError("creator_user_not_found")

        camera_type_row = self._resolve_catalog_row(
            self._select_camera_type_by_code_query,
            camera_type,
            error_code="camera_type_not_found",
        )
        protocol_row = self._resolve_catalog_row(
            self._select_protocol_by_code_query,
            protocol,
            error_code="camera_protocol_not_found",
        )

        duplicate_camera_id = self._get_duplicate_camera_id(
            organization_id=normalized_organization_id,
            name=normalized_name,
        )
        if duplicate_camera_id is not None and duplicate_camera_id != current_camera_id:
            raise ValueError("camera_already_exists")

        if normalized_unique_code:
            duplicate_code_id = self._get_duplicate_camera_code_id(normalized_unique_code)
            if duplicate_code_id is not None and duplicate_code_id != current_camera_id:
                raise ValueError("camera_unique_code_already_exists")

        camera_type_code = str(camera_type_row["codigo"]).strip().lower()
        vehicle_row = None
        if camera_type_code == "static":
            if normalized_latitude is None or normalized_longitude is None:
                raise ValueError("static_camera_requires_location")
            normalized_vehicle_id = None
            normalized_vehicle_position = None
        elif camera_type_code in {"vehicle", "drone"}:
            if normalized_vehicle_id is None:
                raise ValueError("moving_camera_requires_vehicle")
            vehicle_row = self._get_vehicle_row(normalized_vehicle_id)
            if vehicle_row is None:
                raise ValueError("vehicle_not_found")
            if int(vehicle_row["organizacion_id"]) != normalized_organization_id:
                raise ValueError("vehicle_organization_mismatch")
            vehicle_type_code = str(vehicle_row.get("tipo_vehiculo_codigo") or "").strip().lower()
            is_drone_vehicle = vehicle_type_code.startswith("drone")
            if camera_type_code == "drone" and not is_drone_vehicle:
                raise ValueError("camera_vehicle_type_mismatch")
            if camera_type_code == "vehicle" and is_drone_vehicle:
                raise ValueError("camera_vehicle_type_mismatch")
            normalized_latitude = None
            normalized_longitude = None
            normalized_altitude = None
            normalized_address = None
            normalized_reference = None
        else:
            raise ValueError("camera_type_not_supported")

        return {
            "organization_id": normalized_organization_id,
            "owner_user_id": normalized_owner_user_id,
            "created_by_user_id": normalized_creator_user_id,
            "name": normalized_name,
            "description": normalized_description,
            "camera_type_id": int(camera_type_row["id"]),
            "camera_type_code": camera_type_code,
            "protocol_id": int(protocol_row["id"]),
            "protocol_code": str(protocol_row["codigo"]).strip().lower(),
            "unique_code": normalized_unique_code,
            "brand": normalized_brand,
            "model": normalized_model,
            "serial_number": normalized_serial_number,
            "stream_url": normalized_stream_url,
            "rtsp_url": normalized_rtsp_url,
            "fixed_camera_ip": normalized_fixed_camera_ip,
            "stream_username": normalized_stream_username,
            "stream_password": normalized_stream_password,
            "inference_enabled": normalized_inference_enabled,
            "active": normalized_active,
            "latitude": normalized_latitude,
            "longitude": normalized_longitude,
            "altitude_m": normalized_altitude,
            "address": normalized_address,
            "reference": normalized_reference,
            "vehicle_id": normalized_vehicle_id,
            "vehicle_position": normalized_vehicle_position,
        }

    def _persist_static_geopoint(
        self,
        cur,
        payload: dict[str, Any],
        *,
        existing_geopoint_id: int | None,
    ) -> int | None:
        if payload["camera_type_code"] != "static":
            return None

        if existing_geopoint_id is None:
            row = cur.execute(
                self._insert_geopoint_query,
                (
                    payload["latitude"],
                    payload["longitude"],
                    payload["altitude_m"],
                    payload["address"],
                    payload["reference"],
                ),
            ).fetchone()
        else:
            row = cur.execute(
                self._update_geopoint_query,
                (
                    payload["latitude"],
                    payload["longitude"],
                    payload["altitude_m"],
                    payload["address"],
                    payload["reference"],
                    existing_geopoint_id,
                ),
            ).fetchone()
        if not row or "id" not in row:
            raise ValueError("camera_geopoint_failed")
        return int(row["id"])

    def _persist_vehicle_link(self, cur, camera_id: int, payload: dict[str, Any]) -> None:
        cur.execute(self._delete_vehicle_camera_by_camera_query, (camera_id,))
        if payload["camera_type_code"] not in {"vehicle", "drone"} or payload["vehicle_id"] is None:
            return
        row = cur.execute(
            self._upsert_vehicle_camera_query,
            (
                payload["vehicle_id"],
                camera_id,
                payload["vehicle_position"],
            ),
        ).fetchone()
        if not row or "id" not in row:
            raise ValueError("camera_vehicle_link_failed")

    def _resolve_catalog_row(
        self,
        query: str,
        value: str,
        *,
        error_code: str,
    ) -> dict[str, Any]:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            raise ValueError(error_code)
        row = conn.fetch_one(query, (normalized_value, normalized_value))
        if row is None:
            raise ValueError(error_code)
        return row

    def _entity_exists(self, query: str, entity_id: int) -> bool:
        return conn.fetch_one(query, (entity_id,)) is not None

    def _get_vehicle_row(self, vehicle_id: int) -> Optional[dict[str, Any]]:
        return conn.fetch_one(self._select_vehicle_by_id_query, (vehicle_id,))

    def _get_duplicate_camera_id(self, *, organization_id: int, name: str) -> Optional[int]:
        row = conn.fetch_one(self._select_camera_duplicate_query, (organization_id, name))
        return self._read_optional_int(row, "id")

    def _get_duplicate_camera_code_id(self, unique_code: str) -> Optional[int]:
        row = conn.fetch_one(self._select_camera_code_duplicate_query, (unique_code,))
        return self._read_optional_int(row, "id")

    def _count_events_for_camera(self, camera_id: int) -> int:
        row = conn.fetch_one(self._select_camera_events_count_query, (camera_id,))
        return self._read_optional_int(row, "total") or 0

    def _normalize_stream_url(self, value: str) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return ""
        source_error = validate_camera_viewer_source(normalized_value)
        if source_error is not None:
            raise ValueError(source_error)
        return normalized_value

    def _normalize_rtsp_url(self, value: str) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return ""
        source_error = validate_camera_source(normalized_value)
        if source_error is not None:
            raise ValueError("invalid_camera_rtsp_url")
        if not normalized_value.lower().startswith("rtsp://"):
            raise ValueError("invalid_camera_rtsp_url")
        return normalized_value

    def _normalize_camera_ip(self, value: Any, rtsp_url: str) -> str | None:
        normalized_value = self._normalize_optional_text(value, max_length=255)
        if normalized_value:
            return normalized_value
        extracted_host = self._extract_rtsp_host(rtsp_url)
        return extracted_host or None

    def _extract_rtsp_host(self, rtsp_url: str) -> str:
        normalized_value = str(rtsp_url or "").strip()
        if not normalized_value:
            return ""
        try:
            parsed = urlsplit(normalized_value)
        except Exception:
            return ""
        return str(parsed.hostname or "").strip()

    def _normalize_required_text(self, value: str, *, max_length: int, error_code: str) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            raise ValueError(error_code)
        if len(normalized_value) > max_length:
            raise ValueError(error_code)
        return normalized_value

    def _normalize_optional_text(self, value: Any, *, max_length: int) -> str | None:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return None
        if len(normalized_value) > max_length:
            raise ValueError("invalid_camera_payload")
        return normalized_value

    def _normalize_positive_int(self, value: Any, *, error_code: str) -> int:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            raise ValueError(error_code) from None
        if normalized_value <= 0:
            raise ValueError(error_code)
        return normalized_value

    def _normalize_optional_positive_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            raise ValueError("invalid_camera_payload") from None
        if normalized_value <= 0:
            raise ValueError("invalid_camera_payload")
        return normalized_value

    def _normalize_optional_float(self, value: Any, *, error_code: str) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(error_code) from None

    def _normalize_coordinate(
        self,
        value: Any,
        *,
        minimum: float,
        maximum: float,
        error_code: str,
    ) -> float | None:
        if value in (None, ""):
            return None
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            raise ValueError(error_code) from None
        if numeric_value < minimum or numeric_value > maximum:
            raise ValueError(error_code)
        return numeric_value

    def _normalize_bool(self, value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized_value = value.strip().casefold()
            if normalized_value in {"1", "true", "si", "sí", "yes", "on", "activo", "activa"}:
                return True
            if normalized_value in {"0", "false", "no", "off", "inactivo", "inactiva"}:
                return False
        return default

    def _read_optional_int(self, row: Optional[dict[str, Any]], key: str) -> Optional[int]:
        if row is None:
            return None
        try:
            return int(row[key])
        except (KeyError, TypeError, ValueError):
            return None
