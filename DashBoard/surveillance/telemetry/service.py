from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from surveillance.devices.catalog import DeviceCatalog
from surveillance.json_utils import to_jsonable


@dataclass
class TelemetryPoint:
    device_id: str
    lat: float
    lon: float
    altitude: float | None = None
    speed: float | None = None
    heading: float | None = None
    device_status: str = "online"
    source_ts: float | None = None
    received_ts: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, stale_after_sec: float, lost_after_sec: float) -> dict[str, Any]:
        payload = to_jsonable(asdict(self))
        payload["freshness"] = classify_freshness(
            self.received_ts,
            stale_after_sec=stale_after_sec,
            lost_after_sec=lost_after_sec,
        )
        return payload


def classify_freshness(
    received_ts: float,
    *,
    stale_after_sec: float,
    lost_after_sec: float,
) -> str:
    age = time.time() - received_ts
    if age >= lost_after_sec:
        return "lost"
    if age >= stale_after_sec:
        return "stale"
    return "fresh"


class TelemetryService:
    def __init__(self, stale_after_sec: float = 10.0, lost_after_sec: float = 30.0):
        self.stale_after_sec = stale_after_sec
        self.lost_after_sec = max(lost_after_sec, stale_after_sec + 1.0)
        self._points: dict[str, TelemetryPoint] = {}
        self._config_seed_ids: set[str] = set()
        self._registered_devices: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def seed_from_config(self, cfg_data: dict[str, Any], device_catalog: DeviceCatalog) -> None:
        telemetry_cfg = cfg_data.get("telemetry", {})
        if not isinstance(telemetry_cfg, dict):
            telemetry_cfg = {}

        try:
            self.stale_after_sec = float(telemetry_cfg.get("stale_after_sec", self.stale_after_sec))
        except (TypeError, ValueError):
            pass
        try:
            self.lost_after_sec = float(telemetry_cfg.get("lost_after_sec", self.lost_after_sec))
        except (TypeError, ValueError):
            pass
        self.lost_after_sec = max(self.lost_after_sec, self.stale_after_sec + 1.0)

        devices_cfg = telemetry_cfg.get("devices", {})
        if not isinstance(devices_cfg, dict):
            devices_cfg = {}

        next_points: dict[str, TelemetryPoint] = {}
        for device_id, payload in devices_cfg.items():
            if not isinstance(payload, dict):
                continue
            if device_catalog.get(device_id) is None:
                continue
            try:
                lat = float(payload["lat"])
                lon = float(payload["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            next_points[device_id] = TelemetryPoint(
                device_id=device_id,
                lat=lat,
                lon=lon,
                altitude=_safe_float(payload.get("altitude")),
                speed=_safe_float(payload.get("speed")),
                heading=_safe_float(payload.get("heading")),
                device_status=str(payload.get("device_status", "online")),
                source_ts=_safe_float(payload.get("source_ts")),
                received_ts=time.time(),
                extra=_extract_extra_payload(payload),
            )

        with self._lock:
            for device_id in self._config_seed_ids:
                self._points.pop(device_id, None)
            self._config_seed_ids = set(next_points.keys())
            self._points.update(next_points)

    def update(
        self,
        device_id: str,
        *,
        lat: float,
        lon: float,
        altitude: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        device_status: str = "online",
        source_ts: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> TelemetryPoint:
        point = TelemetryPoint(
            device_id=device_id,
            lat=lat,
            lon=lon,
            altitude=altitude,
            speed=speed,
            heading=heading,
            device_status=device_status,
            source_ts=source_ts,
            received_ts=time.time(),
            extra=dict(extra or {}),
        )
        with self._lock:
            self._points[device_id] = point
        return point

    def seed_registered_devices(self, entries: list[Any]) -> None:
        registered: dict[str, dict[str, Any]] = {}
        for entry in entries:
            vehicle_type = str(getattr(entry, "vehicle_type", "") or "").strip().lower()
            identifier = str(getattr(entry, "identifier", "") or "").strip()
            if vehicle_type not in {"dron", "automovil"} or not identifier:
                continue
            label = str(getattr(entry, "label", "") or "").strip()
            notes = str(getattr(entry, "notes", "") or "").strip()
            telemetry_mode = str(getattr(entry, "telemetry_mode", "") or "").strip().lower() or "manual"
            registered[identifier] = {
                "device_id": identifier,
                "camera_name": str(getattr(entry, "camera_name", "") or "").strip() or identifier,
                "display_name": label or identifier,
                "device_kind": "vehicle",
                "vehicle_type": vehicle_type,
                "notes": notes,
                "owner_level": _safe_int(getattr(entry, "owner_level", None)),
                "organization_id": _safe_int(getattr(entry, "organization_id", None)),
                "organization_name": str(getattr(entry, "organization_name", "") or "").strip(),
                "capabilities": {
                    "video": False,
                    "audio": False,
                    "telemetry": True,
                },
                "source": "vehicle_registry",
                "is_registered": True,
                "telemetry_mode": telemetry_mode,
                "api_base_url": str(getattr(entry, "api_base_url", "") or "").strip(),
                "api_device_id": str(getattr(entry, "api_device_id", "") or "").strip(),
                "has_live_telemetry": bool(getattr(entry, "has_live_telemetry", False)),
            }

        with self._lock:
            previous_registered_ids = set(self._registered_devices.keys())
            self._registered_devices = registered
            removable_ids = {
                device_id
                for device_id in previous_registered_ids
                if device_id not in registered
            }
            removable_ids.update(
                device_id
                for device_id, metadata in registered.items()
                if not bool(metadata.get("has_live_telemetry"))
            )
            for device_id in removable_ids:
                self._points.pop(device_id, None)

    def get_device_metadata(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            metadata = self._registered_devices.get(device_id)
            return dict(metadata) if metadata is not None else None

    def list_snapshot(self, device_catalog: DeviceCatalog) -> list[dict[str, Any]]:
        with self._lock:
            points_by_device = dict(self._points)
            registered_devices = {
                device_id: dict(payload)
                for device_id, payload in self._registered_devices.items()
            }

        result = []
        seen_device_ids: set[str] = set()
        for device in device_catalog.list_devices():
            point = points_by_device.get(device.device_id)
            if point is None:
                result.append(
                    {
                        "device_id": device.device_id,
                        "camera_name": device.camera_name,
                        "display_name": device.camera_name,
                        "freshness": "unavailable",
                        "device_kind": "camera",
                        "capabilities": device.capabilities,
                    }
                )
                seen_device_ids.add(device.device_id)
                continue
            payload = point.to_dict(self.stale_after_sec, self.lost_after_sec)
            payload["camera_name"] = device.camera_name
            payload["display_name"] = device.camera_name
            payload["device_kind"] = "camera"
            payload["capabilities"] = device.capabilities
            result.append(payload)
            seen_device_ids.add(device.device_id)

        for device_id, metadata in registered_devices.items():
            if device_id in seen_device_ids:
                continue
            point = points_by_device.get(device_id)
            if point is None:
                payload = {
                    "device_id": device_id,
                    "freshness": "unavailable",
                }
            else:
                payload = point.to_dict(self.stale_after_sec, self.lost_after_sec)
            payload["camera_name"] = metadata.get("camera_name", device_id)
            payload["display_name"] = metadata.get("display_name", device_id)
            payload["device_kind"] = metadata.get("device_kind", "vehicle")
            payload["vehicle_type"] = metadata.get("vehicle_type", "")
            payload["notes"] = metadata.get("notes", "")
            payload["owner_level"] = metadata.get("owner_level")
            payload["organization_id"] = metadata.get("organization_id")
            payload["organization_name"] = metadata.get("organization_name", "")
            payload["capabilities"] = metadata.get("capabilities", {"telemetry": True})
            payload["is_registered"] = bool(metadata.get("is_registered"))
            payload["source"] = metadata.get("source", "vehicle_registry")
            payload["telemetry_mode"] = metadata.get("telemetry_mode", "manual")
            payload["has_live_telemetry"] = bool(metadata.get("has_live_telemetry"))
            result.append(payload)
            seen_device_ids.add(device_id)

        for device_id, point in points_by_device.items():
            if device_id in seen_device_ids:
                continue
            payload = point.to_dict(self.stale_after_sec, self.lost_after_sec)
            payload["camera_name"] = device_id
            payload["display_name"] = device_id
            payload["device_kind"] = "telemetry"
            payload["capabilities"] = {"telemetry": True}
            result.append(payload)

        return result


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


def _extract_extra_payload(payload: dict[str, Any]) -> dict[str, Any]:
    base_keys = {
        "lat",
        "lon",
        "altitude",
        "speed",
        "heading",
        "device_status",
        "source_ts",
    }
    return to_jsonable({key: value for key, value in payload.items() if key not in base_keys})
