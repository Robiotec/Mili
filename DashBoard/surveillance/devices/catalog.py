from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from surveillance.web_runtime import StreamRuntime

MANAGED_AUDIO_SOURCE_SUFFIXES = (
    ".m3u8",
    ".mp4",
    ".webm",
    ".ogg",
    ".ogv",
    ".mov",
    ".m4v",
)


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    camera_name: str
    source: str
    transport: str
    low_latency: bool
    pass_through: bool
    audio_source: str = ""
    viewer_url: str = ""
    capabilities: dict[str, bool] = field(default_factory=dict)
    address: str = ""
    channel: str = ""
    rtsp_path: str = ""
    lat: float | None = None
    lon: float | None = None
    camera_id: int | None = None
    organization_id: int | None = None
    vehicle_id: int | None = None
    vehicle_name: str = ""
    vehicle_type: str = ""
    owner_role: str = ""
    owner_level: int | None = None
    camera_type: str = ""
    protocol: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "camera_name": self.camera_name,
            "source": self.source,
            "transport": self.transport,
            "low_latency": self.low_latency,
            "pass_through": self.pass_through,
            "capabilities": dict(self.capabilities),
            "address": self.address,
            "channel": self.channel,
            "rtsp_path": self.rtsp_path,
            "has_audio_source": bool(self.audio_source),
            "viewer_url": self.viewer_url,
            "lat": self.lat,
            "lon": self.lon,
            "camera_id": self.camera_id,
            "organization_id": self.organization_id,
            "vehicle_id": self.vehicle_id,
            "vehicle_name": self.vehicle_name,
            "vehicle_type": self.vehicle_type,
            "owner_role": self.owner_role,
            "owner_level": self.owner_level,
            "camera_type": self.camera_type,
            "protocol": self.protocol,
        }


class DeviceCatalog:
    def __init__(self, devices: dict[str, DeviceRecord] | None = None):
        self._devices = devices or {}

    def get(self, device_id: str) -> DeviceRecord | None:
        return self._devices.get(device_id)

    def by_camera_name(self, camera_name: str) -> DeviceRecord | None:
        # Buscar por nombre o por codigo_unico
        device = self._devices.get(camera_name)
        if device:
            return device
        # Buscar por codigo_unico
        for dev in self._devices.values():
            if getattr(dev, "codigo_unico", None) == camera_name:
                return dev
        return None

    def list_devices(self) -> list[DeviceRecord]:
        return list(self._devices.values())

    def as_dicts(self) -> list[dict[str, Any]]:
        return [device.to_dict() for device in self.list_devices()]


def build_device_catalog(cfg_data: dict[str, Any], runtime: StreamRuntime) -> DeviceCatalog:
    cameras_cfg = cfg_data.get("IP_ADDRESS", {})
    if not isinstance(cameras_cfg, dict):
        cameras_cfg = {}

    channels_cfg = cfg_data.get("CHANNELS", {})
    if not isinstance(channels_cfg, dict):
        channels_cfg = {}

    rtsp_paths_cfg = cfg_data.get("RTSP_PATHS", {})
    if not isinstance(rtsp_paths_cfg, dict):
        rtsp_paths_cfg = {}

    telemetry_cfg = cfg_data.get("telemetry", {})
    if not isinstance(telemetry_cfg, dict):
        telemetry_cfg = {}
    telemetry_devices = telemetry_cfg.get("devices", {})
    if not isinstance(telemetry_devices, dict):
        telemetry_devices = {}

    audio_cfg = cfg_data.get("audio", {})
    if not isinstance(audio_cfg, dict):
        audio_cfg = {}
    audio_devices = set()
    raw_audio_devices = audio_cfg.get("devices", [])
    if isinstance(raw_audio_devices, list):
        audio_devices = {str(item).strip() for item in raw_audio_devices if str(item).strip()}
    audio_sources_cfg = audio_cfg.get("sources", {})
    if not isinstance(audio_sources_cfg, dict):
        audio_sources_cfg = {}

    web_cfg = cfg_data.get("web", {})
    if not isinstance(web_cfg, dict):
        web_cfg = {}
    viewer_sources_cfg = web_cfg.get("viewer_sources", {})
    if not isinstance(viewer_sources_cfg, dict):
        viewer_sources_cfg = {}

    registry_cfg = cfg_data.get("camera_registry", {})
    if not isinstance(registry_cfg, dict):
        registry_cfg = {}
    registry_devices = registry_cfg.get("cameras", {})
    if not isinstance(registry_devices, dict):
        registry_devices = {}

    devices: dict[str, DeviceRecord] = {}
    for camera_name, definition in runtime.cameras.items():
        configured_source = str(cameras_cfg.get(camera_name, "")).strip()
        effective_source = configured_source or definition.source
        audio_source = str(audio_sources_cfg.get(camera_name, "")).strip()
        if camera_name in audio_devices and not audio_source:
            audio_source = definition.source
        if not audio_source and _supports_managed_audio_source(effective_source):
            audio_source = effective_source
        has_audio = camera_name in audio_devices or bool(audio_source)
        viewer_url = str(viewer_sources_cfg.get(camera_name, "")).strip()
        location_payload = telemetry_devices.get(camera_name, {})
        if not isinstance(location_payload, dict):
            location_payload = {}
        registry_payload = registry_devices.get(camera_name, {})
        if not isinstance(registry_payload, dict):
            registry_payload = {}
        devices[camera_name] = DeviceRecord(
            device_id=camera_name,
            camera_name=camera_name,
            source=configured_source or definition.source,
            audio_source=audio_source,
            viewer_url=viewer_url,
            transport=definition.transport,
            low_latency=definition.low_latency,
            pass_through=definition.pass_through,
            capabilities={
                "video": True,
                "audio": has_audio,
                "telemetry": camera_name in telemetry_devices,
            },
            address=configured_source,
            channel=str(channels_cfg.get(camera_name, "")).strip(),
            rtsp_path=str(rtsp_paths_cfg.get(camera_name, "")).strip(),
            lat=_safe_float(location_payload.get("lat")),
            lon=_safe_float(location_payload.get("lon")),
            camera_id=_safe_int(registry_payload.get("camera_id")),
            organization_id=_safe_int(registry_payload.get("organization_id")),
            vehicle_id=_safe_int(registry_payload.get("vehicle_id")),
            vehicle_name=str(registry_payload.get("vehicle_name") or "").strip(),
            vehicle_type=str(registry_payload.get("vehicle_type") or "").strip(),
            owner_role=str(registry_payload.get("owner_role") or "").strip(),
            owner_level=_safe_int(registry_payload.get("owner_level")),
            camera_type=str(registry_payload.get("camera_type") or "").strip(),
            protocol=str(registry_payload.get("protocol") or "").strip(),
        )

    return DeviceCatalog(devices)


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


def _supports_managed_audio_source(source: str) -> bool:
    normalized = str(source or "").strip().lower()
    if not normalized.startswith(("http://", "https://")):
        return False
    return any(suffix in normalized for suffix in MANAGED_AUDIO_SOURCE_SUFFIXES)
