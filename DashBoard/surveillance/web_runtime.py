from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from surveillance.config import (
    as_bool,
    normalize_camera_source,
)


@dataclass
class StreamState:
    status: str = "idle"  # idle | running | done | error
    frame_bgr: np.ndarray | None = None
    frame_seq: int = 0
    last_frame_ts: float = 0.0
    error: str = ""
    worker: threading.Thread | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_encoded_ts: float = 0.0
    last_worker_start_ts: float = 0.0
    restart_backoff_sec: float = 0.5
    active_clients: int = 0
    idle_deadline_ts: float = 0.0
    stop_event: threading.Event = field(default_factory=threading.Event)


@dataclass
class WebSettings:
    stream_fps: float = 12.0
    max_frame_width: int = 960
    max_frame_height: int = 540
    face_detect_every_n_frames: int | None = 5
    plate_detect_every_n_frames: int | None = 4
    face_det_size: tuple[int, int] | None = None
    face_confidence: float | None = None
    face_min_size: int | None = None
    plate_confidence: float | None = None
    overlay_scale: float = 1.0
    max_clients_per_camera: int = 4
    worker_min_restart_sec: float = 0.5
    worker_max_backoff_sec: float = 6.0
    worker_idle_shutdown_sec: float = 1.5
    run_without_viewers: bool = False
    always_on_cameras: tuple[str, ...] = ()
    preload_shared_resources: bool = True
    supervisor_poll_sec: float = 1.0
    save_outputs_enabled: bool = False
    ice_servers: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "urls": [
                    "stun:stun.cloudflare.com:3478",
                    "stun:stun.l.google.com:19302",
                ]
            },
        ]
    )
    ice_transport_policy: str = "all"
    default_camera: str = ""
    host: str = "0.0.0.0"
    port: int = 8001


@dataclass(frozen=True)
class CameraStreamDefinition:
    camera_name: str
    source: str
    transport: str
    low_latency: bool
    pass_through: bool


@dataclass
class StreamRuntime:
    web_settings: WebSettings
    cameras: dict[str, CameraStreamDefinition]
    states: dict[str, StreamState]

    def get_definition(self, camera_name: str) -> CameraStreamDefinition | None:
        return self.cameras.get(camera_name)

    def get_state(self, camera_name: str) -> StreamState | None:
        return self.states.get(camera_name)

    def get_source(self, camera_name: str, default: str = "") -> str:
        definition = self.get_definition(camera_name)
        return definition.source if definition is not None else default

    def get_transport(self, camera_name: str, default: str = "auto") -> str:
        definition = self.get_definition(camera_name)
        return definition.transport if definition is not None else default

    def is_low_latency(self, camera_name: str, default: bool = True) -> bool:
        definition = self.get_definition(camera_name)
        return definition.low_latency if definition is not None else default

    def is_pass_through(self, camera_name: str) -> bool:
        definition = self.get_definition(camera_name)
        return bool(definition is not None and definition.pass_through)


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_stream_transport(value: Any, default: str = "auto") -> str:
    raw = str(value or default).strip().lower()
    if raw in {"tcp", "udp", "auto"}:
        return raw
    return default


def normalize_pass_through_selection(raw_value: Any) -> tuple[bool, set[str]]:
    if isinstance(raw_value, str):
        requested = {raw_value.strip()} if raw_value.strip() else set()
    elif isinstance(raw_value, (list, tuple, set)):
        requested = {
            str(item).strip()
            for item in raw_value
            if str(item).strip()
        }
    else:
        requested = set()

    pass_through_all = "*" in requested or "all" in {
        item.strip().lower()
        for item in requested
    }
    return pass_through_all, requested


def camera_uses_pass_through(stream_cfg: dict[str, Any], camera_name: str) -> bool:
    if not isinstance(stream_cfg, dict):
        return False

    pass_through_all, requested = normalize_pass_through_selection(
        stream_cfg.get("pass_through_by_camera", [])
    )
    return pass_through_all or camera_name in requested


def get_rtsp_auth_for_camera(
    cfg_data: dict[str, Any],
    camera_name: str,
) -> tuple[str, str]:
    auth_by_camera_cfg = cfg_data.get("RTSP_AUTH_BY_CAMERA", {})
    if not isinstance(auth_by_camera_cfg, dict):
        return "", ""

    camera_auth_cfg = auth_by_camera_cfg.get(camera_name, {})
    if not isinstance(camera_auth_cfg, dict):
        return "", ""

    username = camera_auth_cfg.get("username")
    password = camera_auth_cfg.get("password")
    if not isinstance(username, str) or not username.strip():
        return "", ""

    if not isinstance(password, str):
        password = ""

    return username.strip(), password.strip()


def collect_extra_video_sources(
    paths_cfg: dict[str, Any],
    existing_names: set[str],
) -> dict[str, str]:
    extras: dict[str, str] = {}

    for key, raw_value in paths_cfg.items():
        if not isinstance(key, str) or key == "video" or not re.fullmatch(r"video_\d+", key):
            continue

        source = str(raw_value).strip()
        if not source:
            continue

        camera_name = key
        while camera_name in existing_names or camera_name in extras:
            camera_name = f"{camera_name}_alt"

        extras[camera_name] = normalize_camera_source(source)

    return extras


def normalize_ice_servers(
    raw_value: Any,
    defaults: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list):
        return defaults

    servers: list[dict[str, Any]] = []
    for item in raw_value:
        if not isinstance(item, dict):
            continue

        raw_urls = item.get("urls")
        urls: list[str]
        if isinstance(raw_urls, str) and raw_urls.strip():
            urls = [raw_urls.strip()]
        elif isinstance(raw_urls, list):
            urls = [str(url).strip() for url in raw_urls if str(url).strip()]
        else:
            continue

        if not urls:
            continue

        normalized: dict[str, Any] = {"urls": urls}
        username = item.get("username")
        credential = item.get("credential")
        if isinstance(username, str) and username.strip():
            normalized["username"] = username.strip()
        if isinstance(credential, str) and credential.strip():
            normalized["credential"] = credential.strip()
        servers.append(normalized)

    return servers or defaults


def normalize_ice_transport_policy(raw_value: Any, default: str) -> str:
    if isinstance(raw_value, str):
        value = raw_value.strip().lower()
        if value in {"all", "relay"}:
            return value
    return default


def parse_optional_size(raw_value: Any) -> tuple[int, int] | None:
    if not isinstance(raw_value, (list, tuple)) or len(raw_value) != 2:
        return None
    try:
        width = clamp_int(int(raw_value[0]), 160, 1920)
        height = clamp_int(int(raw_value[1]), 160, 1920)
    except (TypeError, ValueError):
        return None
    return width, height


def build_web_settings(cfg_data: dict[str, Any]) -> WebSettings:
    web_cfg = cfg_data.get("web", {})
    if not isinstance(web_cfg, dict):
        web_cfg = {}

    webrtc_cfg = cfg_data.get("webrtc", {})
    if not isinstance(webrtc_cfg, dict):
        webrtc_cfg = {}

    settings = WebSettings()

    try:
        settings.stream_fps = float(web_cfg.get("stream_fps", settings.stream_fps))
    except (TypeError, ValueError):
        pass
    settings.stream_fps = max(1.0, min(60.0, settings.stream_fps))

    try:
        settings.max_frame_width = int(
            web_cfg.get("max_frame_width", settings.max_frame_width)
        )
    except (TypeError, ValueError):
        pass
    settings.max_frame_width = clamp_int(settings.max_frame_width, 320, 3840)

    try:
        settings.max_frame_height = int(
            web_cfg.get("max_frame_height", settings.max_frame_height)
        )
    except (TypeError, ValueError):
        pass
    settings.max_frame_height = clamp_int(settings.max_frame_height, 240, 2160)

    raw_face_every = web_cfg.get("face_detect_every_n_frames")
    if raw_face_every is not None:
        try:
            settings.face_detect_every_n_frames = clamp_int(int(raw_face_every), 1, 60)
        except (TypeError, ValueError):
            settings.face_detect_every_n_frames = None

    raw_plate_every = web_cfg.get("plate_detect_every_n_frames")
    if raw_plate_every is not None:
        try:
            settings.plate_detect_every_n_frames = clamp_int(int(raw_plate_every), 1, 60)
        except (TypeError, ValueError):
            settings.plate_detect_every_n_frames = None

    settings.face_det_size = parse_optional_size(web_cfg.get("face_det_size"))

    raw_face_confidence = web_cfg.get("face_confidence")
    if raw_face_confidence is not None:
        try:
            settings.face_confidence = clamp_float(float(raw_face_confidence), 0.1, 0.99)
        except (TypeError, ValueError):
            settings.face_confidence = None

    raw_face_min_size = web_cfg.get("face_min_size")
    if raw_face_min_size is not None:
        try:
            settings.face_min_size = clamp_int(int(raw_face_min_size), 20, 400)
        except (TypeError, ValueError):
            settings.face_min_size = None

    raw_plate_confidence = web_cfg.get("plate_confidence")
    if raw_plate_confidence is not None:
        try:
            settings.plate_confidence = clamp_float(float(raw_plate_confidence), 0.1, 0.99)
        except (TypeError, ValueError):
            settings.plate_confidence = None

    raw_overlay_scale = web_cfg.get("overlay_scale")
    if raw_overlay_scale is not None:
        try:
            settings.overlay_scale = clamp_float(float(raw_overlay_scale), 0.75, 3.0)
        except (TypeError, ValueError):
            pass

    try:
        settings.max_clients_per_camera = int(
            web_cfg.get(
                "max_clients_per_camera",
                settings.max_clients_per_camera,
            )
        )
    except (TypeError, ValueError):
        pass
    settings.max_clients_per_camera = clamp_int(settings.max_clients_per_camera, 1, 20)

    try:
        settings.worker_min_restart_sec = float(
            web_cfg.get(
                "worker_min_restart_sec",
                settings.worker_min_restart_sec,
            )
        )
    except (TypeError, ValueError):
        pass
    settings.worker_min_restart_sec = max(
        0.2,
        min(5.0, settings.worker_min_restart_sec),
    )

    try:
        settings.worker_max_backoff_sec = float(
            web_cfg.get(
                "worker_max_backoff_sec",
                settings.worker_max_backoff_sec,
            )
        )
    except (TypeError, ValueError):
        pass
    settings.worker_max_backoff_sec = max(
        settings.worker_min_restart_sec,
        min(30.0, settings.worker_max_backoff_sec),
    )

    try:
        settings.worker_idle_shutdown_sec = float(
            web_cfg.get(
                "worker_idle_shutdown_sec",
                settings.worker_idle_shutdown_sec,
            )
        )
    except (TypeError, ValueError):
        pass
    settings.worker_idle_shutdown_sec = max(
        0.2,
        min(3600.0, settings.worker_idle_shutdown_sec),
    )

    settings.run_without_viewers = as_bool(
        web_cfg.get(
            "run_without_viewers",
            web_cfg.get("workers_always_on", settings.run_without_viewers),
        ),
        settings.run_without_viewers,
    )

    raw_always_on = web_cfg.get("always_on_cameras", settings.always_on_cameras)
    if isinstance(raw_always_on, list):
        normalized: list[str] = []
        for item in raw_always_on:
            camera_name = str(item).strip()
            if camera_name:
                normalized.append(camera_name)
        settings.always_on_cameras = tuple(dict.fromkeys(normalized))

    settings.preload_shared_resources = as_bool(
        web_cfg.get("preload_shared_resources", settings.preload_shared_resources),
        settings.preload_shared_resources,
    )

    try:
        settings.supervisor_poll_sec = float(
            web_cfg.get("supervisor_poll_sec", settings.supervisor_poll_sec)
        )
    except (TypeError, ValueError):
        pass
    settings.supervisor_poll_sec = max(0.5, min(60.0, settings.supervisor_poll_sec))

    settings.save_outputs_enabled = as_bool(
        web_cfg.get("save_outputs_enabled", settings.save_outputs_enabled),
        settings.save_outputs_enabled,
    )

    raw_host = web_cfg.get("host")
    if isinstance(raw_host, str) and raw_host.strip():
        settings.host = raw_host.strip()

    settings.ice_servers = normalize_ice_servers(
        webrtc_cfg.get("ice_servers"),
        settings.ice_servers,
    )
    settings.ice_transport_policy = normalize_ice_transport_policy(
        webrtc_cfg.get("ice_transport_policy"),
        settings.ice_transport_policy,
    )

    raw_default_camera = web_cfg.get("default_camera")
    if isinstance(raw_default_camera, str) and raw_default_camera.strip():
        settings.default_camera = raw_default_camera.strip()

    try:
        settings.port = int(web_cfg.get("port", settings.port))
    except (TypeError, ValueError):
        pass
    settings.port = clamp_int(settings.port, 1, 65535)

    return settings


def build_camera_sources(cfg_data: dict[str, Any]) -> dict[str, str]:
    cameras_cfg = cfg_data.get("IP_ADDRESS", {})
    if not isinstance(cameras_cfg, dict):
        cameras_cfg = {}

    sources: dict[str, str] = {}
    for raw_name, raw_source in cameras_cfg.items():
        if not isinstance(raw_name, str) or not isinstance(raw_source, str):
            continue

        camera_name = raw_name.strip()
        camera_source = raw_source.strip()
        if not camera_name or not camera_source:
            continue

        sources[camera_name] = normalize_camera_source(camera_source)
    return sources


def build_stream_runtime(cfg_data: dict[str, Any]) -> StreamRuntime:
    web_settings = build_web_settings(cfg_data)
    sources = build_camera_sources(cfg_data)

    stream_cfg = cfg_data.get("stream", {})
    if not isinstance(stream_cfg, dict):
        stream_cfg = {}

    default_transport = normalize_stream_transport(stream_cfg.get("transport"), "auto")
    raw_transport_overrides = stream_cfg.get(
        "transport_by_camera",
        stream_cfg.get("transport_overrides", {}),
    )
    if not isinstance(raw_transport_overrides, dict):
        raw_transport_overrides = {}

    default_low_latency = as_bool(stream_cfg.get("low_latency"), True)
    raw_low_latency_overrides = stream_cfg.get("low_latency_by_camera", {})
    if not isinstance(raw_low_latency_overrides, dict):
        raw_low_latency_overrides = {}

    pass_through_all, requested_pass_through = normalize_pass_through_selection(
        stream_cfg.get("pass_through_by_camera", [])
    )

    cameras: dict[str, CameraStreamDefinition] = {}
    for camera_name, source in sources.items():
        cameras[camera_name] = CameraStreamDefinition(
            camera_name=camera_name,
            source=source,
            transport=normalize_stream_transport(
                raw_transport_overrides.get(camera_name),
                default_transport,
            ),
            low_latency=as_bool(
                raw_low_latency_overrides.get(camera_name),
                default_low_latency,
            ),
            pass_through=pass_through_all or camera_name in requested_pass_through,
        )

    states = {camera_name: StreamState() for camera_name in cameras}
    return StreamRuntime(
        web_settings=web_settings,
        cameras=cameras,
        states=states,
    )


def build_error_runtime(error: str) -> StreamRuntime:
    return StreamRuntime(
        web_settings=WebSettings(),
        cameras={
            "cam1": CameraStreamDefinition(
                camera_name="cam1",
                source="",
                transport="auto",
                low_latency=True,
                pass_through=False,
            )
        },
        states={
            "cam1": StreamState(
                status="error",
                error=error,
            )
        },
    )
