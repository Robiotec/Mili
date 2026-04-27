from __future__ import annotations

import copy
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from db.connection import DatabaseError, db
from repositories.querys_camera import CameraRepository
from repositories.querys_vehicle import VehicleRepository
from surveillance import settings
from surveillance.config import (
    CONFIG_PATH,
    is_valid_camera_name,
    read_yaml,
    register_camera_source,
    validate_camera_viewer_source,
)
from surveillance.devices.catalog import DeviceCatalog, build_device_catalog
from surveillance.evidence.store import EvidenceStore
from surveillance.events.store import EventStore
from surveillance.telemetry.api_bridge import ApiTelemetryBridgeManager
from surveillance.telemetry.service import TelemetryService
from surveillance.web_runtime import build_stream_runtime


MEDIAMTX_WEBRTC_PORT = settings.MEDIAMTX_WEBRTC_PORT


class ApplicationContext:
    def __init__(self, config_path: Path | str = CONFIG_PATH):
        self.config_path = Path(config_path)
        self.event_store = EventStore()
        self.evidence_store = EvidenceStore()
        self.telemetry_service = TelemetryService()
        self.device_catalog = DeviceCatalog()
        self.vehicle_repository = VehicleRepository()
        self.api_bridge_manager = ApiTelemetryBridgeManager(
            self.telemetry_service,
            self.event_store,
        )
        self._lock = threading.Lock()
        self._initialized = False
        self.camera_records_by_name: dict[str, dict[str, Any]] = {}

    def resolve_device_id(self, camera_name: str) -> str:
        device = self.device_catalog.by_camera_name(camera_name)
        return device.device_id if device is not None else camera_name

    def ensure_initialized(self) -> None:
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            self._reload_runtime_state_locked()

    def reload_runtime_state(self) -> None:
        with self._lock:
            self._reload_runtime_state_locked()
            self._initialized = True

    def register_camera(
        self,
        camera_name: str,
        source: str,
        *,
        lat: float | None = None,
        lon: float | None = None,
    ) -> dict[str, object]:
        self.ensure_initialized()
        normalized_name = camera_name.strip()
        normalized_source = str(source or "").strip()
        if not is_valid_camera_name(normalized_name):
            raise ValueError("invalid_camera_name")
        source_error = validate_camera_viewer_source(normalized_source)
        if source_error is not None:
            raise ValueError(source_error)

        with self._lock:
            cfg_data = read_yaml(self.config_path)
            runtime = build_stream_runtime(cfg_data)
            if runtime.get_definition(normalized_name) is not None:
                raise ValueError("camera_already_exists")

            register_camera_source(
                self.config_path,
                camera_name=normalized_name,
                source=normalized_source,
                lat=lat,
                lon=lon,
            )
            cfg_data = read_yaml(self.config_path)
            runtime = build_stream_runtime(cfg_data)
            self.device_catalog = build_device_catalog(cfg_data, runtime)
            self.telemetry_service.seed_from_config(cfg_data, self.device_catalog)
            self._refresh_vehicle_registry_state()

            self.event_store.record(
                "camera_registered",
                camera_name=normalized_name,
                device_id=normalized_name,
                source="camera_registry",
                payload={
                    "source": normalized_source,
                    **(
                        {
                            "lat": lat,
                            "lon": lon,
                            "has_audio": False,
                        }
                        if lat is not None and lon is not None
                        else {"has_audio": False}
                    ),
                },
            )

            device = self.device_catalog.by_camera_name(normalized_name)
            if device is None:
                raise RuntimeError("camera_registration_failed")
            return device.to_dict()

    def list_registered_vehicles(self, *, vehicle_type: str | None = None) -> list[dict[str, Any]]:
        self.ensure_initialized()
        vehicles = self.vehicle_repository.list_vehicles() if db.is_open else []
        if vehicle_type:
            normalized_type = str(vehicle_type or "").strip().lower()
            vehicles = [
                vehicle
                for vehicle in vehicles
                if str(vehicle.get("vehicle_type") or "").strip().lower() == normalized_type
            ]
        return [self._serialize_registered_vehicle(vehicle) for vehicle in vehicles]

    def register_vehicle(
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
        self.ensure_initialized()
        with self._lock:
            vehicle = self.vehicle_repository.create_vehicle(
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
            self._refresh_vehicle_registry_state()

            payload = self._serialize_registered_vehicle(vehicle)
            self.event_store.record(
                "vehicle_registered",
                camera_name=str(payload.get("camera_name") or ""),
                device_id=str(payload.get("identifier") or ""),
                source="vehicle_registry",
                payload=payload,
            )
            return payload

    def update_registered_vehicle(
        self,
        registration_id: str,
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
        self.ensure_initialized()
        normalized_registration_id = _safe_int(registration_id)
        if normalized_registration_id is None or normalized_registration_id <= 0:
            raise ValueError("vehicle_not_found")
        with self._lock:
            vehicle = self.vehicle_repository.update_vehicle(
                normalized_registration_id,
                organization_id=organization_id,
                owner_user_id=owner_user_id,
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
            self._refresh_vehicle_registry_state()

            payload = self._serialize_registered_vehicle(vehicle)
            self.event_store.record(
                "vehicle_updated",
                camera_name=str(payload.get("camera_name") or ""),
                device_id=str(payload.get("identifier") or ""),
                source="vehicle_registry",
                payload=payload,
            )
            return payload

    def delete_registered_vehicle(self, registration_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        normalized_registration_id = _safe_int(registration_id)
        if normalized_registration_id is None or normalized_registration_id <= 0:
            raise ValueError("vehicle_not_found")
        with self._lock:
            vehicle = self.vehicle_repository.delete_vehicle(normalized_registration_id)
            self._refresh_vehicle_registry_state()

            payload = self._serialize_registered_vehicle(vehicle)
            self.event_store.record(
                "vehicle_deleted",
                camera_name=str(payload.get("camera_name") or ""),
                device_id=str(payload.get("identifier") or ""),
                source="vehicle_registry",
                payload=payload,
            )
            return payload

    def _refresh_vehicle_registry_state(self) -> None:
        entries = self.vehicle_repository.list_vehicle_registry_entries() if db.is_open else []
        self.telemetry_service.seed_registered_devices(entries)
        self.api_bridge_manager.reload_entries(entries)

    def _reload_runtime_state_locked(self) -> None:
        cfg_data = self._build_effective_config()
        runtime = build_stream_runtime(cfg_data)
        self.device_catalog = build_device_catalog(cfg_data, runtime)
        self.telemetry_service.seed_from_config(cfg_data, self.device_catalog)
        self._refresh_vehicle_registry_state()

    def _build_effective_config(self) -> dict[str, Any]:
        cfg_data = copy.deepcopy(read_yaml(self.config_path))
        camera_rows: list[dict[str, Any]] = []

        if db.is_open:
            try:
                camera_rows = CameraRepository().list_cameras(active_only=True)
            except DatabaseError:
                camera_rows = []

        self.camera_records_by_name = {
            str(row.get("nombre") or "").strip(): row
            for row in camera_rows
            if str(row.get("nombre") or "").strip()
        }
        return self._apply_database_camera_projection(cfg_data, camera_rows)

    def _serialize_registered_vehicle(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        normalized_vehicle = dict(vehicle)
        owner_username = str(normalized_vehicle.get("propietario_usuario") or "").strip()
        owner_display_name = " ".join(
            part
            for part in (
                str(normalized_vehicle.get("propietario_nombre") or "").strip(),
                str(normalized_vehicle.get("propietario_apellido") or "").strip(),
            )
            if part
        ) or owner_username
        return {
            "id": _safe_int(normalized_vehicle.get("id")),
            "registration_id": str(normalized_vehicle.get("registration_id") or ""),
            "ts": _safe_float(normalized_vehicle.get("ts")) or 0.0,
            "created_ts": _safe_float(normalized_vehicle.get("creado_ts")) or 0.0,
            "vehicle_type": str(normalized_vehicle.get("vehicle_type") or "").strip(),
            "vehicle_type_code": str(normalized_vehicle.get("vehicle_type_code") or "").strip(),
            "vehicle_type_name": str(normalized_vehicle.get("vehicle_type_name") or "").strip(),
            "label": str(normalized_vehicle.get("label") or "").strip(),
            "identifier": str(normalized_vehicle.get("identifier") or "").strip(),
            "notes": str(normalized_vehicle.get("notes") or "").strip(),
            "telemetry_mode": str(normalized_vehicle.get("telemetry_mode") or "manual").strip(),
            "api_base_url": str(normalized_vehicle.get("api_base_url") or "").strip(),
            "api_device_id": str(normalized_vehicle.get("api_device_id") or "").strip(),
            "has_live_telemetry": bool(normalized_vehicle.get("has_live_telemetry")),
            "organizacion_id": _safe_int(normalized_vehicle.get("organizacion_id")),
            "organizacion_nombre": str(normalized_vehicle.get("organizacion_nombre") or "").strip(),
            "propietario_usuario_id": _safe_int(normalized_vehicle.get("propietario_usuario_id")),
            "propietario_usuario": owner_username,
            "propietario_display_name": owner_display_name,
            "propietario_rol_codigo": str(normalized_vehicle.get("propietario_rol_codigo") or "").strip(),
            "propietario_rol_nombre": str(normalized_vehicle.get("propietario_rol_nombre") or "").strip(),
            "propietario_nivel_orden": _safe_int(normalized_vehicle.get("propietario_nivel_orden")),
            "protocolo_codigo": str(normalized_vehicle.get("protocolo_codigo") or "").strip(),
            "protocolo_nombre": str(normalized_vehicle.get("protocolo_nombre") or "").strip(),
            "activo": bool(normalized_vehicle.get("activo")),
            "placa": str(normalized_vehicle.get("placa") or "").strip(),
            "numero_serie": str(normalized_vehicle.get("numero_serie") or "").strip(),
            "marca": str(normalized_vehicle.get("marca") or "").strip(),
            "modelo": str(normalized_vehicle.get("modelo") or "").strip(),
            "latitud_actual": (
                _safe_float(normalized_vehicle.get("telemetria_lat"))
                if _safe_float(normalized_vehicle.get("telemetria_lat")) is not None
                else _safe_float(normalized_vehicle.get("geopunto_latitud"))
            ),
            "longitud_actual": (
                _safe_float(normalized_vehicle.get("telemetria_lon"))
                if _safe_float(normalized_vehicle.get("telemetria_lon")) is not None
                else _safe_float(normalized_vehicle.get("geopunto_longitud"))
            ),
            "camera_name": str(normalized_vehicle.get("camera_name") or "").strip(),
            "camera_links": list(normalized_vehicle.get("camera_links") or []),
        }

    def _apply_database_camera_projection(
        self,
        cfg_data: dict[str, Any],
        camera_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        web_cfg = cfg_data.get("web", {})
        if not isinstance(web_cfg, dict):
            web_cfg = {}
            cfg_data["web"] = web_cfg

        telemetry_cfg = cfg_data.get("telemetry", {})
        if not isinstance(telemetry_cfg, dict):
            telemetry_cfg = {}
            cfg_data["telemetry"] = telemetry_cfg

        cfg_data["IP_ADDRESS"] = {}
        telemetry_cfg["devices"] = {}
        cfg_data["camera_registry"] = {"cameras": {}}

        camera_names: list[str] = []
        for row in camera_rows:
            camera_name = str(row.get("nombre") or "").strip()
            stream_url = str(row.get("url_stream") or "").strip()
            rtsp_url = str(row.get("url_rtsp") or "").strip()
            inference_enabled = bool(row.get("hacer_inferencia"))
            effective_stream_url = _effective_inference_source_url(
                stream_url,
                inference_enabled=inference_enabled,
            )
            effective_rtsp_url = _effective_inference_source_url(
                rtsp_url,
                inference_enabled=inference_enabled,
            )
            source_url = effective_stream_url or effective_rtsp_url
            if not camera_name or not source_url:
                continue

            cfg_data["IP_ADDRESS"][camera_name] = source_url
            camera_names.append(camera_name)

            lat = _safe_float(row.get("latitud_mapa"))
            lon = _safe_float(row.get("longitud_mapa"))
            if lat is not None and lon is not None:
                telemetry_cfg["devices"][camera_name] = {
                    "lat": lat,
                    "lon": lon,
                    **(
                        {"altitude": alt}
                        if (alt := _safe_float(row.get("altitud_mapa"))) is not None
                        else {}
                    ),
                }

            cfg_data["camera_registry"]["cameras"][camera_name] = {
                "camera_id": _safe_int(row.get("id")),
                "organization_id": _safe_int(row.get("organizacion_id")),
                "vehicle_id": _safe_int(row.get("vehiculo_id")),
                "vehicle_name": str(row.get("vehiculo_nombre") or "").strip(),
                "vehicle_type": str(
                    row.get("vehiculo_tipo_codigo")
                    or row.get("vehiculo_tipo_nombre")
                    or ""
                ).strip(),
                "owner_role": str(
                    row.get("propietario_rol_codigo")
                    or row.get("propietario_rol_nombre")
                    or ""
                ).strip(),
                "owner_level": _safe_int(row.get("propietario_nivel_orden")),
                "camera_type": str(
                    row.get("tipo_camara_codigo")
                    or row.get("tipo_camara_nombre")
                    or ""
                ).strip(),
                "display_name": _build_effective_camera_display_name(
                    camera_name,
                    inference_enabled=inference_enabled,
                ),
                "inference_enabled": inference_enabled,
                "stream_url": effective_stream_url,
                "rtsp_url": effective_rtsp_url,
                "protocol": str(
                    row.get("protocolo_codigo")
                    or row.get("protocolo_nombre")
                    or ""
                ).strip(),
            }

        current_default_camera = str(web_cfg.get("default_camera") or "").strip()
        if current_default_camera not in camera_names:
            web_cfg["default_camera"] = camera_names[0] if camera_names else ""

        return cfg_data


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _strip_inference_camera_suffix(name: Any) -> str:
    return re.sub(r"\s*-\s*INF\s*$", "", str(name or ""), flags=re.IGNORECASE).strip()


def _build_effective_camera_display_name(
    name: Any,
    *,
    inference_enabled: bool,
) -> str:
    base_name = _strip_inference_camera_suffix(name)
    if not base_name:
        return ""
    return f"{base_name} - INF" if inference_enabled else base_name


def _is_managed_inference_source(raw_url: Any) -> bool:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return False

    parsed = urlparse(candidate)
    path = str(parsed.path or "").lower()
    return (
        parsed.scheme in {"http", "https"}
        and str(parsed.port or "") == MEDIAMTX_WEBRTC_PORT
        and not bool(re.search(r"/[^/?#]+\.[a-z0-9]+$", path))
    )


def _effective_inference_source_url(
    raw_url: Any,
    *,
    inference_enabled: bool,
) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate or not _is_managed_inference_source(candidate):
        return candidate

    parsed = urlparse(candidate)
    normalized_path = re.sub(r"/+INFERENCE/*$", "", str(parsed.path or ""), flags=re.IGNORECASE).rstrip("/")
    if inference_enabled:
        normalized_path = f"{normalized_path}/INFERENCE" if normalized_path else "/INFERENCE"
    elif not normalized_path:
        normalized_path = "/"

    return urlunparse(parsed._replace(path=normalized_path or "/"))
