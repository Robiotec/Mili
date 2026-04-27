from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = Path(os.getenv("DASHBOARD_ENV_FILE", BASE_DIR / ".env")).expanduser()
load_dotenv(ENV_PATH)

TRUE_VALUES = {"1", "true", "yes", "on", "si", "sí"}


def env_str(name: str, default: str = "", *, strip: bool = True) -> str:
    value = os.getenv(name)
    if value is None:
        value = default
    return value.strip() if strip else value


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw_value = env_str(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw_value = env_str(name, str(default))
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().casefold() in TRUE_VALUES


def env_is_set(name: str) -> bool:
    return os.getenv(name) is not None


def env_path(name: str, default: str | Path) -> Path:
    return Path(env_str(name, str(default))).expanduser()


def _stream_api_base_url() -> str:
    explicit_url = env_str("STREAM_API_BASE_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    host = env_str("STREAM_API_HOST", "127.0.0.1") or "127.0.0.1"
    port = env_str("STREAM_API_PORT", "8004") or "8004"
    return f"http://{host}:{port}"


def _env_tuple(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in env_str(name).split(",")
        if item.strip()
    )


# Database
DB_HOST = env_str("DB_HOST", "127.0.0.1")
DB_PORT = env_int("DB_PORT", 5432, minimum=1, maximum=65535)
DB_NAME = env_str("DB_NAME", "dashboard")
DB_USER = env_str("DB_USER", "dashboarduser")
DB_PASSWORD = env_str("DB_PASSWORD", "", strip=False)
DB_MIN_SIZE = env_int("DB_MIN_SIZE", 1, minimum=1)
DB_MAX_SIZE = env_int("DB_MAX_SIZE", 10, minimum=DB_MIN_SIZE)
DB_TIMEOUT = env_int("DB_TIMEOUT", 10, minimum=1)
DB_CONNECT_TIMEOUT = env_int("DB_CONNECT_TIMEOUT", 5, minimum=1)
DB_BOOTSTRAP_ON_STARTUP = env_bool("DB_BOOTSTRAP_ON_STARTUP", True)
VEHICLE_TELEMETRY_CONFIG_TABLE = (
    env_str("VEHICLE_TELEMETRY_CONFIG_TABLE", "configuracion_mavlink")
    or "configuracion_mavlink"
)

# Bootstrap seed
DEFAULT_SUPERADMIN_USERNAME = env_str("DEFAULT_SUPERADMIN_USERNAME", "admin") or "admin"
DEFAULT_SUPERADMIN_PASSWORD = env_str("DEFAULT_SUPERADMIN_PASSWORD", "", strip=False)
DEFAULT_SUPERADMIN_EMAIL = (
    env_str("DEFAULT_SUPERADMIN_EMAIL", "admin@robiotec.local")
    or "admin@robiotec.local"
)
DEFAULT_DEMO_ORG_NAME = env_str("DEFAULT_DEMO_ORG_NAME", "ROBIOTEC DEMO") or "ROBIOTEC DEMO"
DEFAULT_DEMO_VEHICLE_UNIQUE_ID = (
    env_str("DEFAULT_DEMO_VEHICLE_UNIQUE_ID", "DEMO-CAR-001")
    or "DEMO-CAR-001"
)
DEFAULT_DEMO_CAMERA_UNIQUE_ID = (
    env_str("DEFAULT_DEMO_CAMERA_UNIQUE_ID", "DEMO-CAM-001")
    or "DEMO-CAM-001"
)

# Security
PASSWORD_HASH_ITERATIONS = env_int("PASSWORD_HASH_ITERATIONS", 390000, minimum=120000)
PASSWORD_SALT_BYTES = env_int("PASSWORD_SALT_BYTES", 16, minimum=16)
WEB_SESSION_COOKIE_NAME = env_str("WEB_SESSION_COOKIE_NAME", "robiotec_session")
WEB_SESSION_SECRET = env_str("WEB_SESSION_SECRET", "", strip=False)
WEB_SESSION_MAX_AGE_SECONDS = env_int("WEB_SESSION_MAX_AGE_SECONDS", 28800, minimum=60)
JWT_SECRET = env_str("JWT_SECRET", "", strip=False) or WEB_SESSION_SECRET
JWT_ACCESS_TOKEN_TTL_SECONDS = env_int("JWT_ACCESS_TOKEN_TTL_SECONDS", 3600, minimum=60)

# Web
WEB_HOST = env_str("WEB_HOST", "0.0.0.0") or "0.0.0.0"
WEB_PORT = env_int("WEB_PORT", 8001, minimum=1, maximum=65535)
WEB_LOG_FILE = env_str("WEB_LOG_FILE")
TELEMETRY_MAP_MIN_ZOOM = env_int("TELEMETRY_MAP_MIN_ZOOM", 6, minimum=1, maximum=24)
TELEMETRY_MAP_MAX_ZOOM = env_int(
    "TELEMETRY_MAP_MAX_ZOOM",
    18,
    minimum=TELEMETRY_MAP_MIN_ZOOM,
    maximum=24,
)
THUNDERFOREST_API_KEY = env_str("THUNDERFOREST_API_KEY")

# Stream API
STREAM_API_HOST = env_str("STREAM_API_HOST", "127.0.0.1")
STREAM_API_PORT = env_str("STREAM_API_PORT", "8004")
STREAM_API_BASE_URL = _stream_api_base_url()
STREAM_API_USERNAME = env_str("STREAM_API_USERNAME")
STREAM_API_PASSWORD = env_str("STREAM_API_PASSWORD", "", strip=False)
STREAM_REQUEST_TIMEOUT = env_float("STREAM_REQUEST_TIMEOUT", 10.0, minimum=1.0)
STREAM_VIEWER_MUTED = env_bool("STREAM_VIEWER_MUTED", False)
VIEWER_CACHE_MAX_AGE_SECONDS = env_int("VIEWER_CACHE_MAX_AGE_SECONDS", 86400, minimum=60)

# MediaMTX
MEDIAMTX_HOST = env_str("MEDIAMTX_HOST")
MEDIAMTX_WEBRTC_PORT = env_str("MEDIAMTX_WEBRTC_PORT", "8989") or "8989"
MEDIAMTX_RTSP_PORT = env_str("MEDIAMTX_RTSP_PORT", "8654") or "8654"
MEDIAMTX_HLS_PORT = env_str("MEDIAMTX_HLS_PORT", "8988") or "8988"
MEDIAMTX_RTMP_PORT = env_str("MEDIAMTX_RTMP_PORT", "1936") or "1936"
MEDIAMTX_SRT_PORT = env_str("MEDIAMTX_SRT_PORT", "8991") or "8991"

# Telemetry and external feeds
GPS_API_BASE_URL = (
    env_str("GPS_API_BASE_URL")
    or STREAM_API_BASE_URL
    or "http://127.0.0.1:8004"
)
API_TELEMETRY_DEFAULT_DRONE_ID = env_str("API_TELEMETRY_DEFAULT_DRONE_ID", "drone") or "drone"
TELEMETRY_REFRESH_SECONDS = env_float("TELEMETRY_REFRESH_SECONDS", 1.0, minimum=0.25)
DRONE_TRACKS_DIR = env_path("DRONE_TRACKS_DIR", BASE_DIR.parent / "trayectorias")
OPENSKY_DATA_FILE = env_path("OPENSKY_DATA_FILE", BASE_DIR.parent / "opensky" / "opensky_data.json")
AIRPLANES_API_URL = env_str(
    "AIRPLANES_API_URL",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
)
AIRPLANES_REQUEST_TIMEOUT_SEC = env_float("AIRPLANES_REQUEST_TIMEOUT_SEC", 8.0, minimum=1.0)
AIRPLANES_VIEWPORT_RADIUS_NM = env_int("AIRPLANES_VIEWPORT_RADIUS_NM", 180, minimum=25, maximum=250)
AIRPLANES_VIEWPORT_MAX_POINTS = env_int("AIRPLANES_VIEWPORT_MAX_POINTS", 9, minimum=1, maximum=12)
OBJETIVOS_DIR = env_path("OBJETIVOS_DIR", BASE_DIR.parent / "objetivos")
OBJETIVO_API_BASE_URL = env_str("OBJETIVO_API_BASE_URL", STREAM_API_BASE_URL).rstrip("/")

# ARCOM map layer
ARCOM_ENABLED = env_bool("ARCOM_ENABLED", False)
ARCOM_GPKG_PATH = env_path("ARCOM_GPKG_PATH", "/home/robiotec/ARCOM/arcom_catastro.gpkg")
ARCOM_MAX_FEATURES_PER_REQUEST = env_int("ARCOM_MAX_FEATURES_PER_REQUEST", 120, minimum=1)
ARCOM_MIN_ZOOM = env_int("ARCOM_MIN_ZOOM", 11, minimum=1, maximum=24)

# Remote plate/crop access
CROPS_SSH_HOST = env_str("CROPS_SSH_HOST")
CROPS_SSH_USER = env_str("CROPS_SSH_USER")
CROPS_SSH_PORT = env_int("CROPS_SSH_PORT", 22, minimum=1, maximum=65535)
CROPS_SSH_KEY_PATH = env_str("CROPS_SSH_KEY_PATH")
CROPS_REMOTE_MANIFEST_PATH = env_str("CROPS_REMOTE_MANIFEST_PATH")
CROPS_SSH_STRICT_HOST_KEY_CHECKING = (
    env_str("CROPS_SSH_STRICT_HOST_KEY_CHECKING", "accept-new")
    or "accept-new"
)
CROPS_CONNECT_TIMEOUT = env_int(
    "CROPS_CONNECT_TIMEOUT",
    env_int("CROPS_SSH_CONNECT_TIMEOUT", 10, minimum=1),
    minimum=1,
)
CROPS_COMMAND_TIMEOUT = env_int(
    "CROPS_COMMAND_TIMEOUT",
    env_int("CROPS_SSH_COMMAND_TIMEOUT", 20, minimum=1),
    minimum=1,
)
CROPS_MAX_RETRIES = env_int(
    "CROPS_MAX_RETRIES",
    env_int("CROPS_SSH_MAX_RETRIES", 2, minimum=1),
    minimum=1,
)
CROPS_RETRY_DELAY = env_int(
    "CROPS_RETRY_DELAY",
    env_int("CROPS_SSH_RETRY_DELAY", 2, minimum=0),
    minimum=0,
)
CROPS_MANIFEST_CACHE_TTL_SEC = env_float("CROPS_MANIFEST_CACHE_TTL_SEC", 30.0, minimum=0.0)

# Optional legacy values still consumed by deployments/scripts.
DJI_MQTT_BROKER = env_str("DJI_MQTT_BROKER")
DJI_MQTT_PORT = env_int("DJI_MQTT_PORT", 1883, minimum=1, maximum=65535)
STREAM_NAME = env_str("STREAM_NAME", "CAM3")
WEB_ALWAYS_ON_CAMERAS = _env_tuple("WEB_ALWAYS_ON_CAMERAS")


def require_runtime_secrets() -> None:
    missing = [
        name
        for name, value in {
            "WEB_SESSION_SECRET": WEB_SESSION_SECRET,
            "JWT_SECRET": JWT_SECRET,
            "DEFAULT_SUPERADMIN_PASSWORD": DEFAULT_SUPERADMIN_PASSWORD,
        }.items()
        if not str(value or "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Faltan variables obligatorias en .env: " + ", ".join(missing)
        )


def redact(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}***{text[-2:]}"
