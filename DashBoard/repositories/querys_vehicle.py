import json
import logging
import os
import re
import sys
from typing import Any, Optional

import psycopg

if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from db.connection import db as conn
else:
    from db.connection import db as conn

from surveillance import settings
from surveillance.vehicle_registry import VehicleRegistryEntry, VehicleRegistryStore


LOGGER = logging.getLogger(__name__)


def _safe_sql_identifier(value: str, *, default: str) -> str:
    candidate = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        return candidate
    return default


VEHICLE_TELEMETRY_CONFIG_TABLE = _safe_sql_identifier(
    settings.VEHICLE_TELEMETRY_CONFIG_TABLE,
    default="configuracion_mavlink",
)


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _normalize_bool(value: Any, *, default: bool) -> bool:
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


def _normalize_vehicle_category(type_code: str) -> str:
    normalized_code = str(type_code or "").strip().lower()
    if normalized_code.startswith("drone"):
        return "dron"
    return "automovil"


class VehicleRepository:
    def __init__(self) -> None:
        self._telemetry_config_table = VEHICLE_TELEMETRY_CONFIG_TABLE
        self._select_vehicle_types_query = """
            SELECT
                id,
                codigo,
                nombre
            FROM tipos_vehiculo
            ORDER BY id;
        """
        self._select_vehicle_type_by_code_query = """
            SELECT
                id,
                codigo,
                nombre
            FROM tipos_vehiculo
            WHERE LOWER(codigo) = LOWER(%s)
               OR LOWER(nombre) = LOWER(%s)
            LIMIT 1;
        """
        self._select_protocol_by_code_query = """
            SELECT
                id,
                codigo,
                nombre
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
        self._select_vehicle_identifier_duplicate_query = """
            SELECT
                v.id
            FROM vehiculos v
            LEFT JOIN {config_table} cfg ON cfg.vehiculo_id = v.id
            WHERE LOWER(
                COALESCE(
                    NULLIF(cfg.config_extra ->> 'identifier', ''),
                    NULLIF(v.placa, ''),
                    NULLIF(v.numero_serie, ''),
                    NULLIF(v.nombre, '')
                )
            ) = LOWER(%s)
            LIMIT 1;
        """.format(config_table=self._telemetry_config_table)
        self._select_camera_rows_query = """
            SELECT
                c.id,
                c.organizacion_id,
                c.nombre,
                c.codigo_unico,
                c.url_stream,
                c.activa,
                camera_type.codigo AS tipo_camara_codigo,
                camera_type.nombre AS tipo_camara_nombre,
                vehicle_link.vehiculo_id,
                vehicle_link.posicion AS vehiculo_posicion
            FROM camaras c
            JOIN tipos_camara camera_type ON camera_type.id = c.tipo_camara_id
            LEFT JOIN vehiculo_camaras vehicle_link ON vehicle_link.camara_id = c.id
            WHERE c.id = ANY(%s::bigint[])
            ORDER BY c.nombre ASC, c.id ASC;
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
                EXTRACT(EPOCH FROM v.creado_en)::DOUBLE PRECISION AS creado_ts,
                EXTRACT(EPOCH FROM COALESCE(v.actualizado_en, v.creado_en))::DOUBLE PRECISION AS ts,
                o.nombre AS organizacion_nombre,
                owner_user.usuario AS propietario_usuario,
                owner_user.email AS propietario_email,
                owner_user.nombre AS propietario_nombre,
                owner_user.apellido AS propietario_apellido,
                owner_role.codigo AS propietario_rol_codigo,
                owner_role.nombre AS propietario_rol_nombre,
                owner_role.nivel_orden AS propietario_nivel_orden,
                creator_user.usuario AS creado_por_usuario,
                creator_user.email AS creado_por_email,
                vehicle_type.codigo AS tipo_vehiculo_codigo,
                vehicle_type.nombre AS tipo_vehiculo_nombre,
                protocol.codigo AS protocolo_codigo,
                protocol.nombre AS protocolo_nombre,
                current_point.latitud AS geopunto_latitud,
                current_point.longitud AS geopunto_longitud,
                current_point.altitud_m AS geopunto_altitud_m,
                current_point.direccion AS geopunto_direccion,
                current_point.referencia AS geopunto_referencia,
                telemetry.lat AS telemetria_lat,
                telemetry.lon AS telemetria_lon,
                telemetry.altitud AS telemetria_altitud,
                cfg.config_extra,
                COALESCE(
                    NULLIF(cfg.config_extra ->> 'telemetry_mode', ''),
                    'manual'
                ) AS telemetry_mode,
                COALESCE(cfg.config_extra ->> 'api_base_url', '') AS api_base_url,
                COALESCE(cfg.config_extra ->> 'api_device_id', '') AS api_device_id,
                COALESCE(cfg.config_extra ->> 'identifier', '') AS identifier_extra,
                COALESCE(camera_links.camaras, '[]'::jsonb) AS camera_links
            FROM vehiculos v
            JOIN organizaciones o ON o.id = v.organizacion_id
            JOIN usuarios owner_user ON owner_user.id = v.propietario_usuario_id
            JOIN roles owner_role ON owner_role.id = owner_user.rol_id
            JOIN usuarios creator_user ON creator_user.id = v.creado_por_usuario_id
            JOIN tipos_vehiculo vehicle_type ON vehicle_type.id = v.tipo_vehiculo_id
            LEFT JOIN protocolos_comunicacion protocol ON protocol.id = v.protocolo_comunicacion_id
            LEFT JOIN geopuntos current_point ON current_point.id = v.geopunto_actual_id
            LEFT JOIN telemetria_actual telemetry ON telemetry.vehiculo_id = v.id
            LEFT JOIN {config_table} cfg ON cfg.vehiculo_id = v.id
            LEFT JOIN LATERAL (
                SELECT
                    JSONB_AGG(
                        JSONB_BUILD_OBJECT(
                            'camara_id', c.id,
                            'camara_nombre', c.nombre,
                            'camara_codigo_unico', c.codigo_unico,
                            'camara_tipo_codigo', camera_type.codigo,
                            'camara_tipo_nombre', camera_type.nombre,
                            'camara_url_stream', c.url_stream,
                            'camara_activa', c.activa,
                            'posicion', vc.posicion
                        )
                        ORDER BY c.nombre ASC, c.id ASC
                    ) AS camaras
                FROM vehiculo_camaras vc
                JOIN camaras c ON c.id = vc.camara_id
                JOIN tipos_camara camera_type ON camera_type.id = c.tipo_camara_id
                WHERE vc.vehiculo_id = v.id
            ) AS camera_links ON TRUE
            {where_clause}
            ORDER BY v.id;
        """.format(config_table=self._telemetry_config_table, where_clause="{where_clause}")
        self._select_all_vehicles_query = self._select_vehicles_query.format(where_clause="")
        self._select_vehicle_by_id_query = self._select_vehicles_query.format(where_clause="WHERE v.id = %s")
        self._insert_vehicle_query = """
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        self._update_vehicle_query = """
            UPDATE vehiculos
            SET
                organizacion_id = %s,
                propietario_usuario_id = %s,
                tipo_vehiculo_id = %s,
                nombre = %s,
                descripcion = %s,
                placa = %s,
                numero_serie = %s,
                marca = %s,
                modelo = %s,
                protocolo_comunicacion_id = %s,
                activo = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id;
        """
        self._upsert_vehicle_config_query = """
            INSERT INTO {config_table} (
                vehiculo_id,
                cadena_conexion,
                clave_fuente,
                system_id,
                component_id,
                autopilot_uid,
                baud_rate,
                config_extra
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (vehiculo_id)
            DO UPDATE SET
                cadena_conexion = EXCLUDED.cadena_conexion,
                clave_fuente = EXCLUDED.clave_fuente,
                system_id = EXCLUDED.system_id,
                component_id = EXCLUDED.component_id,
                autopilot_uid = EXCLUDED.autopilot_uid,
                baud_rate = EXCLUDED.baud_rate,
                config_extra = EXCLUDED.config_extra
            RETURNING id;
        """.format(config_table=self._telemetry_config_table)
        self._delete_vehicle_config_query = """
            DELETE FROM {config_table}
            WHERE vehiculo_id = %s;
        """.format(config_table=self._telemetry_config_table)
        self._delete_vehicle_camera_links_query = """
            DELETE FROM vehiculo_camaras
            WHERE vehiculo_id = %s;
        """
        self._delete_camera_links_from_other_vehicles_query = """
            DELETE FROM vehiculo_camaras
            WHERE camara_id = ANY(%s::bigint[])
              AND vehiculo_id <> %s;
        """
        self._insert_vehicle_camera_link_query = """
            INSERT INTO vehiculo_camaras (
                vehiculo_id,
                camara_id,
                posicion
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (vehiculo_id, camara_id)
            DO UPDATE SET
                posicion = EXCLUDED.posicion;
        """
        self._delete_vehicle_telemetry_query = """
            DELETE FROM telemetria_actual
            WHERE vehiculo_id = %s;
        """
        self._delete_vehicle_telemetry_history_query = """
            DELETE FROM telemetria_historial
            WHERE vehiculo_id = %s;
        """
        self._delete_vehicle_query = """
            DELETE FROM vehiculos
            WHERE id = %s
            RETURNING id;
        """

    def list_vehicle_types(self) -> list[dict[str, Any]]:
        rows = conn.fetch_all(self._select_vehicle_types_query)
        return [self._serialize_vehicle_type_row(row) for row in rows]

    def list_vehicles(self) -> list[dict[str, Any]]:
        rows = conn.fetch_all(self._select_all_vehicles_query)
        return [self._hydrate_vehicle_row(row) for row in rows]

    def get_vehicle_by_id(self, vehicle_id: int) -> Optional[dict[str, Any]]:
        row = conn.fetch_one(self._select_vehicle_by_id_query, (vehicle_id,))
        if row is None:
            return None
        return self._hydrate_vehicle_row(row)

    def list_vehicle_registry_entries(self) -> list[VehicleRegistryEntry]:
        entries: list[VehicleRegistryEntry] = []
        for row in self.list_vehicles():
            try:
                entries.append(self._build_registry_entry(row))
            except ValueError as exc:
                LOGGER.warning(
                    "Se omitio vehiculo invalido para telemetria (%s): id=%s nombre=%s",
                    exc,
                    row.get("id") or row.get("registration_id") or "",
                    row.get("nombre") or row.get("label") or "",
                )
        return entries

    def create_vehicle(
        self,
        *,
        organization_id: int,
        owner_user_id: int,
        created_by_user_id: int,
        vehicle_type_code: str,
        label: str,
        identifier: str,
        notes: str = "",
        telemetry_mode: str = "manual",
        api_base_url: str = "",
        api_device_id: str = "",
        active: bool = True,
        camera_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with conn.connection() as db_conn:
            with db_conn.cursor() as cur:
                payload = self._prepare_vehicle_payload(
                    cur,
                    organization_id=organization_id,
                    owner_user_id=owner_user_id,
                    created_by_user_id=created_by_user_id,
                    vehicle_type_code=vehicle_type_code,
                    label=label,
                    identifier=identifier,
                    notes=notes,
                    telemetry_mode=telemetry_mode,
                    api_base_url=api_base_url,
                    api_device_id=api_device_id,
                    active=active,
                    camera_links=camera_links,
                )
                created = cur.execute(
                    self._insert_vehicle_query,
                    (
                        payload["organization_id"],
                        payload["owner_user_id"],
                        payload["created_by_user_id"],
                        payload["vehicle_type_id"],
                        payload["label"],
                        payload["notes"],
                        payload["plate"],
                        payload["serial_number"],
                        None,
                        None,
                        payload["protocol_id"],
                        payload["active"],
                    ),
                ).fetchone()
                if created is None or "id" not in created:
                    raise ValueError("vehicle_registration_failed")
                vehicle_id = int(created["id"])
                self._sync_vehicle_config(cur, vehicle_id, payload)
                self._sync_vehicle_camera_links(cur, vehicle_id, payload["camera_links"])

        vehicle = self.get_vehicle_by_id(vehicle_id)
        if vehicle is None:
            raise ValueError("vehicle_registration_failed")
        return vehicle

    def update_vehicle(
        self,
        vehicle_id: int,
        *,
        organization_id: int,
        owner_user_id: int,
        vehicle_type_code: str,
        label: str,
        identifier: str,
        notes: str = "",
        telemetry_mode: str = "manual",
        api_base_url: str = "",
        api_device_id: str = "",
        active: bool = True,
        camera_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        existing = self.get_vehicle_by_id(vehicle_id)
        if existing is None:
            raise ValueError("vehicle_not_found")

        with conn.connection() as db_conn:
            with db_conn.cursor() as cur:
                payload = self._prepare_vehicle_payload(
                    cur,
                    organization_id=organization_id,
                    owner_user_id=owner_user_id,
                    created_by_user_id=_safe_int(existing.get("creado_por_usuario_id")) or 0,
                    vehicle_type_code=vehicle_type_code,
                    label=label,
                    identifier=identifier,
                    notes=notes,
                    telemetry_mode=telemetry_mode,
                    api_base_url=api_base_url,
                    api_device_id=api_device_id,
                    active=active,
                    camera_links=camera_links,
                    current_vehicle_id=vehicle_id,
                )
                updated = cur.execute(
                    self._update_vehicle_query,
                    (
                        payload["organization_id"],
                        payload["owner_user_id"],
                        payload["vehicle_type_id"],
                        payload["label"],
                        payload["notes"],
                        payload["plate"],
                        payload["serial_number"],
                        None,
                        None,
                        payload["protocol_id"],
                        payload["active"],
                        vehicle_id,
                    ),
                ).fetchone()
                if updated is None or "id" not in updated:
                    raise ValueError("vehicle_update_failed")
                self._sync_vehicle_config(cur, vehicle_id, payload)
                self._sync_vehicle_camera_links(cur, vehicle_id, payload["camera_links"])

        vehicle = self.get_vehicle_by_id(vehicle_id)
        if vehicle is None:
            raise ValueError("vehicle_update_failed")
        return vehicle

    def delete_vehicle(self, vehicle_id: int) -> dict[str, Any]:
        existing = self.get_vehicle_by_id(vehicle_id)
        if existing is None:
            raise ValueError("vehicle_not_found")

        try:
            with conn.connection() as db_conn:
                with db_conn.cursor() as cur:
                    cur.execute(self._delete_vehicle_camera_links_query, (vehicle_id,))
                    cur.execute(self._delete_vehicle_config_query, (vehicle_id,))
                    cur.execute(self._delete_vehicle_telemetry_query, (vehicle_id,))
                    cur.execute(self._delete_vehicle_telemetry_history_query, (vehicle_id,))
                    deleted = cur.execute(self._delete_vehicle_query, (vehicle_id,)).fetchone()
                    if deleted is None or "id" not in deleted:
                        raise ValueError("vehicle_delete_failed")
        except psycopg.errors.ForeignKeyViolation as exc:
            raise ValueError("vehicle_in_use") from exc

        return existing

    def _prepare_vehicle_payload(
        self,
        cur: Any,
        *,
        organization_id: int,
        owner_user_id: int,
        created_by_user_id: int,
        vehicle_type_code: str,
        label: str,
        identifier: str,
        notes: str,
        telemetry_mode: str,
        api_base_url: str,
        api_device_id: str,
        active: bool,
        camera_links: list[dict[str, Any]] | None,
        current_vehicle_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_organization_id = self._normalize_positive_int(
            organization_id,
            error_code="invalid_organization_id",
        )
        normalized_owner_user_id = self._normalize_positive_int(
            owner_user_id,
            error_code="invalid_owner_user_id",
        )
        normalized_created_by_user_id = self._normalize_positive_int(
            created_by_user_id,
            error_code="invalid_creator_user_id",
        )
        normalized_label = str(label or "").strip()
        normalized_identifier = str(identifier or "").strip()
        normalized_notes = str(notes or "").strip()
        normalized_active = _normalize_bool(active, default=True)

        if not normalized_label:
            raise ValueError("invalid_vehicle_label")
        if not normalized_identifier:
            raise ValueError("invalid_vehicle_identifier")

        type_row = self._resolve_catalog_row(
            cur,
            self._select_vehicle_type_by_code_query,
            self._normalize_vehicle_type_lookup(vehicle_type_code),
            error_code="invalid_vehicle_type",
        )
        normalized_vehicle_type_code = str(type_row["codigo"]).strip().lower()
        normalized_vehicle_category = _normalize_vehicle_category(normalized_vehicle_type_code)

        validated_entry = VehicleRegistryStore._build_entry(
            registration_id=str(current_vehicle_id or ""),
            created_ts=0.0,
            updated_ts=0.0,
            vehicle_type=normalized_vehicle_category,
            label=normalized_label,
            identifier=normalized_identifier,
            notes=normalized_notes,
            telemetry_mode=telemetry_mode,
            api_base_url=api_base_url,
            api_device_id=api_device_id,
        )

        if not self._record_exists(cur, self._select_user_exists_query, normalized_owner_user_id):
            raise ValueError("owner_user_not_found")
        if not self._record_exists(cur, self._select_user_exists_query, normalized_created_by_user_id):
            raise ValueError("creator_user_not_found")
        if not self._record_exists(cur, self._select_organization_exists_query, normalized_organization_id):
            raise ValueError("organization_not_found")

        duplicate_id = self._find_duplicate_identifier(cur, validated_entry.identifier)
        if duplicate_id is not None and duplicate_id != current_vehicle_id:
            raise ValueError("vehicle_already_exists")

        protocol_id = self._resolve_protocol_id(
            cur,
            telemetry_mode=validated_entry.telemetry_mode,
            api_base_url=validated_entry.api_base_url,
        )
        normalized_camera_links = self._normalize_camera_links(
            cur,
            camera_links=camera_links,
            organization_id=normalized_organization_id,
            vehicle_category=normalized_vehicle_category,
            current_vehicle_id=current_vehicle_id,
        )

        return {
            "organization_id": normalized_organization_id,
            "owner_user_id": normalized_owner_user_id,
            "created_by_user_id": normalized_created_by_user_id,
            "vehicle_type_id": int(type_row["id"]),
            "vehicle_type_code": normalized_vehicle_type_code,
            "vehicle_category": normalized_vehicle_category,
            "label": validated_entry.label,
            "identifier": validated_entry.identifier,
            "notes": validated_entry.notes,
            "plate": validated_entry.identifier if normalized_vehicle_category == "automovil" else None,
            "serial_number": validated_entry.identifier if normalized_vehicle_category == "dron" else None,
            "telemetry_mode": validated_entry.telemetry_mode,
            "protocol_id": protocol_id,
            "api_base_url": validated_entry.api_base_url,
            "api_device_id": validated_entry.api_device_id or validated_entry.identifier,
            "active": normalized_active,
            "camera_links": normalized_camera_links,
        }

    def _normalize_camera_links(
        self,
        cur: Any,
        *,
        camera_links: list[dict[str, Any]] | None,
        organization_id: int,
        vehicle_category: str,
        current_vehicle_id: int | None,
    ) -> list[dict[str, Any]]:
        raw_links = camera_links if isinstance(camera_links, list) else []
        ordered_camera_ids: list[int] = []
        positions_by_camera_id: dict[int, str] = {}

        for raw_link in raw_links:
            if not isinstance(raw_link, dict):
                raise ValueError("invalid_vehicle_camera_links")
            camera_id = self._normalize_positive_int(
                raw_link.get("camera_id") or raw_link.get("camara_id"),
                error_code="invalid_vehicle_camera_id",
            )
            if camera_id not in positions_by_camera_id:
                ordered_camera_ids.append(camera_id)
            positions_by_camera_id[camera_id] = str(
                raw_link.get("position") or raw_link.get("posicion") or ""
            ).strip()

        if not ordered_camera_ids:
            return []

        camera_rows = cur.execute(
            self._select_camera_rows_query,
            (ordered_camera_ids,),
        ).fetchall()
        rows_by_id = {int(row["id"]): row for row in camera_rows}
        if len(rows_by_id) != len(ordered_camera_ids):
            raise ValueError("camera_not_found")

        normalized_links: list[dict[str, Any]] = []
        for camera_id in ordered_camera_ids:
            row = rows_by_id[camera_id]
            if int(row["organizacion_id"]) != organization_id:
                raise ValueError("camera_organization_mismatch")
            camera_type_code = str(row.get("tipo_camara_codigo") or "").strip().lower()
            if camera_type_code == "static":
                raise ValueError("camera_vehicle_type_mismatch")
            if vehicle_category == "dron" and camera_type_code != "drone":
                raise ValueError("camera_vehicle_type_mismatch")
            if vehicle_category != "dron" and camera_type_code != "vehicle":
                raise ValueError("camera_vehicle_type_mismatch")

            linked_vehicle_id = _safe_int(row.get("vehiculo_id"))
            if linked_vehicle_id is not None and current_vehicle_id is not None and linked_vehicle_id == current_vehicle_id:
                linked_vehicle_id = None

            normalized_links.append(
                {
                    "camera_id": camera_id,
                    "position": positions_by_camera_id[camera_id] or None,
                    "linked_vehicle_id": linked_vehicle_id,
                    "camera_name": str(row.get("nombre") or "").strip(),
                    "camera_type_code": camera_type_code,
                }
            )
        return normalized_links

    def _sync_vehicle_config(self, cur: Any, vehicle_id: int, payload: dict[str, Any]) -> None:
        telemetry_mode = str(payload.get("telemetry_mode") or "manual").strip().lower() or "manual"
        if telemetry_mode == "manual":
            cur.execute(self._delete_vehicle_config_query, (vehicle_id,))
            return

        api_base_url = str(payload.get("api_base_url") or "").strip()
        api_device_id = str(payload.get("api_device_id") or "").strip()
        config_extra = {
            "telemetry_mode": telemetry_mode,
            "identifier": str(payload.get("identifier") or "").strip(),
        }
        if api_device_id:
            config_extra["api_device_id"] = api_device_id

        cur.execute(
            self._upsert_vehicle_config_query,
            (
                vehicle_id,
                None,
                api_device_id or str(payload.get("identifier") or "").strip() or None,
                None,
                None,
                None,
                None,
                json.dumps(config_extra, ensure_ascii=False),
            ),
        )

    def _sync_vehicle_camera_links(
        self,
        cur: Any,
        vehicle_id: int,
        camera_links: list[dict[str, Any]],
    ) -> None:
        cur.execute(self._delete_vehicle_camera_links_query, (vehicle_id,))
        if not camera_links:
            return

        camera_ids = [int(link["camera_id"]) for link in camera_links]
        cur.execute(
            self._delete_camera_links_from_other_vehicles_query,
            (camera_ids, vehicle_id),
        )
        for link in camera_links:
            cur.execute(
                self._insert_vehicle_camera_link_query,
                (
                    vehicle_id,
                    int(link["camera_id"]),
                    link.get("position"),
                ),
            )

    def _resolve_protocol_id(
        self,
        cur: Any,
        *,
        telemetry_mode: str,
        api_base_url: str,
    ) -> int | None:
        normalized_mode = str(telemetry_mode or "").strip().lower()
        if normalized_mode == "manual":
            return None

        scheme = str(api_base_url or "").strip().lower()
        protocol_code = "https" if scheme.startswith("https://") else "http"
        protocol_row = self._resolve_catalog_row(
            cur,
            self._select_protocol_by_code_query,
            protocol_code,
            error_code="vehicle_protocol_not_found",
        )
        return int(protocol_row["id"])

    def _find_duplicate_identifier(self, cur: Any, identifier: str) -> int | None:
        row = cur.execute(
            self._select_vehicle_identifier_duplicate_query,
            (identifier,),
        ).fetchone()
        if row is None:
            return None
        return _safe_int(row.get("id"))

    def _record_exists(self, cur: Any, query: str, record_id: int) -> bool:
        row = cur.execute(query, (record_id,)).fetchone()
        return row is not None

    def _resolve_catalog_row(
        self,
        cur: Any,
        query: str,
        value: str,
        *,
        error_code: str,
    ) -> dict[str, Any]:
        raw_value = str(value or "").strip()
        row = cur.execute(query, (raw_value, raw_value)).fetchone()
        if row is None:
            raise ValueError(error_code)
        return row

    def _normalize_vehicle_type_lookup(self, value: str) -> str:
        normalized_value = str(value or "").strip().lower()
        if normalized_value in {"dron", "drone", "drone_robiotec"}:
            return "drone_robiotec"
        if normalized_value in {"automovil", "auto", "vehiculo", "vehículo"}:
            return "auto"
        return normalized_value

    def _serialize_vehicle_type_row(self, row: dict[str, Any]) -> dict[str, Any]:
        type_code = str(row.get("codigo") or "").strip().lower()
        return {
            "id": _safe_int(row.get("id")),
            "codigo": type_code,
            "nombre": str(row.get("nombre") or "").strip(),
            "categoria": _normalize_vehicle_category(type_code),
        }

    def _hydrate_vehicle_row(self, row: dict[str, Any]) -> dict[str, Any]:
        hydrated = dict(row)
        type_code = str(hydrated.get("tipo_vehiculo_codigo") or "").strip().lower()
        category = _normalize_vehicle_category(type_code)
        identifier = str(hydrated.get("identifier_extra") or "").strip()
        if not identifier:
            identifier = (
                str(hydrated.get("placa") or "").strip()
                or str(hydrated.get("numero_serie") or "").strip()
                or str(hydrated.get("nombre") or "").strip()
                or str(hydrated.get("id") or "").strip()
            )

        telemetry_mode = str(hydrated.get("telemetry_mode") or "manual").strip().lower() or "manual"
        api_base_url = str(hydrated.get("api_base_url") or "").strip()
        api_device_id = str(hydrated.get("api_device_id") or "").strip()

        camera_links = hydrated.get("camera_links")
        if not isinstance(camera_links, list):
            camera_links = []
        normalized_camera_links: list[dict[str, Any]] = []
        for raw_link in camera_links:
            if not isinstance(raw_link, dict):
                continue
            normalized_camera_links.append(
                {
                    "camera_id": _safe_int(raw_link.get("camara_id")),
                    "camera_name": str(raw_link.get("camara_nombre") or "").strip(),
                    "camera_unique_code": str(raw_link.get("camara_codigo_unico") or "").strip(),
                    "camera_type_code": str(raw_link.get("camara_tipo_codigo") or "").strip(),
                    "camera_type_name": str(raw_link.get("camara_tipo_nombre") or "").strip(),
                    "camera_stream_url": str(raw_link.get("camara_url_stream") or "").strip(),
                    "camera_active": bool(raw_link.get("camara_activa")),
                    "position": str(raw_link.get("posicion") or "").strip(),
                }
            )

        hydrated["vehicle_type"] = category
        hydrated["vehicle_type_code"] = type_code
        hydrated["vehicle_type_name"] = str(hydrated.get("tipo_vehiculo_nombre") or "").strip()
        hydrated["registration_id"] = str(hydrated.get("id") or "").strip()
        hydrated["label"] = str(hydrated.get("nombre") or "").strip()
        hydrated["identifier"] = identifier
        hydrated["notes"] = str(hydrated.get("descripcion") or "").strip()
        hydrated["telemetry_mode"] = telemetry_mode
        hydrated["api_base_url"] = api_base_url
        hydrated["api_device_id"] = api_device_id or identifier
        hydrated["camera_links"] = normalized_camera_links
        hydrated["camera_name"] = normalized_camera_links[0]["camera_name"] if normalized_camera_links else ""
        hydrated["has_live_telemetry"] = telemetry_mode == "api" and bool(api_device_id or identifier)
        return hydrated

    def _build_registry_entry(self, row: dict[str, Any]) -> VehicleRegistryEntry:
        normalized_row = row if "registration_id" in row else self._hydrate_vehicle_row(row)
        entry_payload = {
            "registration_id": str(normalized_row.get("registration_id") or ""),
            "created_ts": float(normalized_row.get("creado_ts") or 0.0),
            "updated_ts": float(normalized_row.get("ts") or 0.0),
            "vehicle_type": str(normalized_row.get("vehicle_type") or ""),
            "label": str(normalized_row.get("label") or ""),
            "identifier": str(normalized_row.get("identifier") or ""),
            "notes": str(normalized_row.get("notes") or ""),
            "telemetry_mode": str(normalized_row.get("telemetry_mode") or "manual"),
            "api_base_url": str(normalized_row.get("api_base_url") or ""),
            "api_device_id": str(normalized_row.get("api_device_id") or ""),
        }
        validated_entry = VehicleRegistryStore._build_entry(**entry_payload)
        payload = validated_entry.to_storage_dict()
        payload.update(
            {
                "camera_name": str(normalized_row.get("camera_name") or ""),
                "owner_level": _safe_int(normalized_row.get("propietario_nivel_orden")),
                "organization_id": _safe_int(normalized_row.get("organizacion_id")),
                "organization_name": str(normalized_row.get("organizacion_nombre") or "").strip(),
            }
        )
        return VehicleRegistryEntry(**payload)

    def _normalize_positive_int(self, value: Any, *, error_code: str) -> int:
        normalized_value = _safe_int(value)
        if normalized_value is None or normalized_value <= 0:
            raise ValueError(error_code)
        return normalized_value
