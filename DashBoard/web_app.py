from __future__ import annotations

import asyncio
import base64
import errno
import hashlib
import html
import hmac
import json
import logging
import math
import os
import re
import shlex
import socket
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from controllers.register_cameras.register_camera import (
    CameraRTSPConfig,
    RTSPGenerator,
    RTSPGeneratorError,
    get_rtsp_brand_presets,
    normalize_rtsp_brand,
)
from controllers.cropts_embeding.crops_reading import (
    RobustSSHClient,
    SSHError,
    build_default_crops_ssh_config,
    get_default_crops_remote_manifest_path,
    iter_remote_path_candidates,
    parse_unique_plate_file_records,
)
from db.connection import DatabaseError, db
from db.bootstrap import ensure_bootstrap_seed
from controllers.api_protect_stream.protect_stream import (
    DEFAULT_API_BASE_URL,
    DEFAULT_API_PASSWORD,
    DEFAULT_API_USERNAME,
    DEFAULT_REQUEST_TIMEOUT,
    ProtectedStreamViewerClient,
    StreamViewerError,
    ViewerCredentials,
    ViewerLaunchOptions,
    build_patched_protected_viewer_html,
)
from repositories.querys_camera import CameraRepository
from repositories.querys_organitation import OrganizationRepository
from repositories.querys_user import UserRepository
from repositories.querys_vehicle import VehicleRepository
from surveillance.app_context import ApplicationContext
from surveillance.arcom import ArcomConcessionStore, ArcomLookupError
from surveillance.config import is_valid_camera_name, read_yaml, validate_camera_viewer_source
from surveillance.jwt_utils import JWT_ACCESS_TOKEN_TTL_SEC, decode_jwt, issue_access_token
from surveillance.json_utils import to_jsonable
from surveillance.web_runtime import build_web_settings


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
ICONS_DIR = Path(__file__).resolve().parent / "src" / "icons"
ASSETS_DIR = Path(__file__).resolve().parent / "src" / "assets"
APP_CONTEXT = ApplicationContext()
LOGGER = logging.getLogger(__name__)
CROPS_SSH_QUIET_LOGGER = logging.getLogger(f"{__name__}.crops_ssh_quiet")
CROPS_SSH_QUIET_LOGGER.setLevel(logging.CRITICAL)
SESSION_COOKIE_NAME = os.getenv("WEB_SESSION_COOKIE_NAME", "robiotec_session")
SESSION_MAX_AGE_SEC = int(os.getenv("WEB_SESSION_MAX_AGE_SECONDS", "28800"))
SESSION_SECRET = os.getenv("WEB_SESSION_SECRET", "robiotec-dev-session-secret")
MEDIAMTX_WEBRTC_PORT = os.getenv("MEDIAMTX_WEBRTC_PORT", "8989")
API_TELEMETRY_DEFAULT_DRONE_ID = os.getenv("API_TELEMETRY_DEFAULT_DRONE_ID", "drone").strip() or "drone"
TELEMETRY_REFRESH_SECONDS = max(float(os.getenv("TELEMETRY_REFRESH_SECONDS", "1")), 0.25)
ARCOM_GPKG_PATH = Path(os.getenv("ARCOM_GPKG_PATH", "/home/robiotec/ARCOM/arcom_catastro.gpkg")).expanduser()
ARCOM_MAX_FEATURES_PER_REQUEST = max(1, int(os.getenv("ARCOM_MAX_FEATURES_PER_REQUEST", "120")))
ARCOM_ENABLED = os.getenv("ARCOM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
ARCOM_CONCESSION_STORE = ArcomConcessionStore(ARCOM_GPKG_PATH)
CROPS_MANIFEST_CACHE_TTL_SEC = max(float(os.getenv("CROPS_MANIFEST_CACHE_TTL_SEC", "30")), 0.0)
PUBLIC_PATHS = frozenset({"/login", "/api/login", "/api/logout"})
PUBLIC_PATH_PREFIXES = ("/static", "/icons", "/assets")
TEMPLATE_INCLUDE_PATTERN = re.compile(r"__INCLUDE:([A-Za-z0-9_./-]+)__")

_CROPS_MANIFEST_CACHE_LOCK = threading.Lock()
_CROPS_MANIFEST_CACHE: dict[str, object] = {
    "plate_values": [],
    "updated_at": 0.0,
    "refreshing": False,
}


def _json_response(data, *, status: int = 200) -> web.Response:
    return web.json_response(
        to_jsonable(data),
        status=status,
        dumps=lambda value: json.dumps(value, ensure_ascii=False),
        headers={"Cache-Control": "no-store"},
    )


def _static_asset_version() -> str:
    asset_paths = (
        STATIC_DIR / "web_app.css",
        STATIC_DIR / "perfil.css",
        STATIC_DIR / "web_app.js",
        STATIC_DIR / "web_app" / "modules" / "camera_playback.js",
        STATIC_DIR / "web_app" / "modules" / "layout.js",
        STATIC_DIR / "web_app" / "modules" / "telemetry_overlay.js",
        ICONS_DIR / "camara_on.png",
        ICONS_DIR / "camara_off.png",
        ICONS_DIR / "Dron_potition.png",
        ICONS_DIR / "carro_espia.png",
        ASSETS_DIR / "LoogoBlanco.png",
        ASSETS_DIR / "logoSimplificadoC.png",
    )
    mtimes: list[int] = []
    for path in asset_paths:
        try:
            mtimes.append(path.stat().st_mtime_ns)
        except OSError:
            continue
    if mtimes:
        return str(max(mtimes))
    return str(time.time_ns())


def _template_file_path(template_name: str) -> Path:
    template_root = TEMPLATES_DIR.resolve()
    template_path = (template_root / template_name).resolve()
    try:
        template_path.relative_to(template_root)
    except ValueError as exc:
        raise ValueError(f"Invalid template path: {template_name}") from exc
    return template_path


def _read_template_source(template_name: str, *, seen: set[Path] | None = None) -> str:
    template_path = _template_file_path(template_name)
    seen_paths = set() if seen is None else set(seen)
    if template_path in seen_paths:
        raise ValueError(f"Circular template include detected: {template_name}")

    seen_paths.add(template_path)
    template = template_path.read_text(encoding="utf-8")

    def _replace_include(match: re.Match[str]) -> str:
        include_name = match.group(1)
        return _read_template_source(include_name, seen=seen_paths)

    return TEMPLATE_INCLUDE_PATTERN.sub(_replace_include, template)


def _html_response(
    template_name: str,
    *,
    request: web.Request | None = None,
    replacements: dict[str, str] | None = None,
) -> web.Response:
    merged_replacements = _default_template_replacements()
    if request is not None:
        merged_replacements.update(_build_authenticated_shell_replacements(request))
    if replacements:
        merged_replacements.update(replacements)
    return web.Response(
        body=_render_template(template_name, request=request, replacements=merged_replacements),
        content_type="text/html",
        charset="utf-8",
        headers={"Cache-Control": "no-store"},
    )

def _sign_session_payload(encoded_payload: str) -> str:
    return hmac.new(
        SESSION_SECRET.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _normalize_role_name(role: object) -> str:
    if not isinstance(role, str):
        return ""

    cleaned_role = role.strip()
    if not cleaned_role:
        return ""

    normalized_role = re.sub(r"[\s-]+", "_", cleaned_role).casefold()
    role_aliases = {
        "superadmin": "desarrollador",
        "super_admin": "desarrollador",
        "admin": "admin",
        "administrador": "admin",
        "administrator": "admin",
        "administrador_principal": "admin",
        "admin_principal": "admin",
        "developer": "desarrollador",
        "desarrollador": "desarrollador",
        "engineer": "ingeniero",
        "enginer": "ingeniero",
        "engenir": "ingeniero",
        "ingeniero": "ingeniero",
        "client": "cliente",
        "cliente": "cliente",
        "cliente_normal": "cliente",
        "operator": "operador",
        "operador": "operador",
        "analyst": "analista",
        "analista": "analista",
        "supervisor": "supervisor",
    }
    return role_aliases.get(normalized_role, normalized_role)


def _resolve_user_role(user: dict[str, object]) -> str:
    for key in ("rol", "rol_codigo", "rol_nombre"):
        normalized_role = _normalize_role_name(user.get(key))
        if normalized_role:
            return normalized_role
    return ""


def _normalize_user_record(user: dict[str, object]) -> dict[str, object]:
    normalized_user = dict(user)
    normalized_role = _resolve_user_role(normalized_user)
    if normalized_role:
        normalized_user["rol"] = normalized_role
    return normalized_user


def _coerce_bool(value: object, *, default: bool = False) -> bool:
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


def _safe_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _serialize_role_record(role: dict[str, object]) -> dict[str, object]:
    code = str(role.get("codigo") or role.get("rol") or "").strip()
    name = str(role.get("nombre") or "").strip() or code.replace("_", " ").strip().title()
    return {
        "id": _safe_int(role.get("id")),
        "codigo": code,
        "nombre": name,
        "rol": code,
        "label": name,
        "nivel_orden": _safe_int(role.get("nivel_orden")),
        "es_sistema": bool(role.get("es_sistema")),
        "usuarios_asignados": _safe_int(role.get("usuarios_asignados")),
    }


def _serialize_user_record(user: dict[str, object]) -> dict[str, object]:
    username = str(user.get("usuario") or "").strip()
    first_name = str(user.get("nombre") or "").strip()
    last_name = str(user.get("apellido") or "").strip()
    role_code = str(user.get("rol_codigo") or user.get("rol") or "").strip()
    role_name = str(user.get("rol_nombre") or "").strip()
    normalized_role = _normalize_role_name(role_code or role_name)
    display_name = " ".join(part for part in (first_name, last_name) if part) or _display_name_from_username(username)
    role_label = role_name or {
        "admin": "Administrador",
        "desarrollador": "Desarrollador",
        "developer": "Developer",
        "ingeniero": "Ingeniero",
        "engineer": "Ingeniero",
        "cliente": "Cliente",
        "client": "Cliente",
        "operador": "Operador",
        "analista": "Analista",
        "supervisor": "Supervisor",
    }.get((role_code or normalized_role).casefold(), (role_code or normalized_role or "sin rol").replace("_", " ").title())
    return {
        "id": _safe_int(user.get("id")),
        "usuario": username,
        "email": str(user.get("email") or "").strip(),
        "nombre": first_name,
        "apellido": last_name,
        "telefono": str(user.get("telefono") or "").strip(),
        "activo": bool(user.get("activo")),
        "cambiar_password": bool(user.get("cambiar_password")),
        "rol": role_code or normalized_role,
        "rol_codigo": role_code or normalized_role,
        "rol_nombre": role_name or role_label,
        "rol_label": role_label,
        "rol_normalizado": normalized_role,
        "display_name": display_name,
    }


def _serialize_organization_record(organization: dict[str, object]) -> dict[str, object]:
    name = str(organization.get("nombre") or "").strip()
    owner_username = str(organization.get("propietario_usuario") or "").strip()
    owner_first_name = str(organization.get("propietario_nombre") or "").strip()
    owner_last_name = str(organization.get("propietario_apellido") or "").strip()
    owner_display_name = " ".join(
        part for part in (owner_first_name, owner_last_name) if part
    ) or _display_name_from_username(owner_username)
    owner_role_code = str(organization.get("propietario_rol_codigo") or "").strip()
    owner_role_name = str(organization.get("propietario_rol_nombre") or "").strip()
    normalized_owner_role = _normalize_role_name(owner_role_code or owner_role_name)
    return {
        "id": _safe_int(organization.get("id")),
        "nombre": name,
        "descripcion": str(organization.get("descripcion") or "").strip(),
        "activa": bool(organization.get("activa")),
        "propietario_usuario_id": _safe_int(organization.get("propietario_usuario_id")),
        "propietario_usuario": owner_username,
        "propietario_email": str(organization.get("propietario_email") or "").strip(),
        "propietario_nombre": owner_first_name,
        "propietario_apellido": owner_last_name,
        "propietario_display_name": owner_display_name,
        "propietario_rol_codigo": owner_role_code or normalized_owner_role,
        "propietario_rol_nombre": owner_role_name or (owner_role_code or normalized_owner_role or "sin rol").replace("_", " ").title(),
        "propietario_rol_normalizado": normalized_owner_role,
        "propietario_nivel_orden": _safe_int(organization.get("propietario_nivel_orden")),
        "creado_por_usuario_id": _safe_int(organization.get("creado_por_usuario_id")),
        "creado_por_usuario": str(organization.get("creado_por_usuario") or "").strip(),
    }


def _serialize_camera_type_record(camera_type: dict[str, object]) -> dict[str, object]:
    return {
        "id": _safe_int(camera_type.get("id")),
        "codigo": str(camera_type.get("codigo") or "").strip(),
        "nombre": str(camera_type.get("nombre") or "").strip(),
    }


def _serialize_protocol_record(protocol: dict[str, object]) -> dict[str, object]:
    return {
        "id": _safe_int(protocol.get("id")),
        "codigo": str(protocol.get("codigo") or "").strip(),
        "nombre": str(protocol.get("nombre") or "").strip(),
        "puerto_default": _safe_int(protocol.get("puerto_default")),
        "descripcion": str(protocol.get("descripcion") or "").strip(),
    }


def _serialize_stream_server_record(server: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(server, dict):
        return None
    return {
        "id": _safe_int(server.get("id")),
        "nombre": str(server.get("nombre") or "").strip(),
        "descripcion": str(server.get("descripcion") or "").strip(),
        "ip_publica": str(server.get("ip_publica") or "").strip(),
        "activo": bool(server.get("activo")),
    }


def _serialize_vehicle_type_record(vehicle_type: dict[str, object]) -> dict[str, object]:
    return {
        "id": _safe_int(vehicle_type.get("id")),
        "codigo": str(vehicle_type.get("codigo") or "").strip(),
        "nombre": str(vehicle_type.get("nombre") or "").strip(),
        "categoria": str(vehicle_type.get("categoria") or "").strip(),
    }


def _serialize_vehicle_record(vehicle: dict[str, object]) -> dict[str, object]:
    owner_username = str(vehicle.get("propietario_usuario") or "").strip()
    owner_display_name = " ".join(
        part
        for part in (
            str(vehicle.get("propietario_nombre") or "").strip(),
            str(vehicle.get("propietario_apellido") or "").strip(),
        )
        if part
    ) or _display_name_from_username(owner_username)
    return {
        "id": _safe_int(vehicle.get("id")),
        "nombre": str(vehicle.get("nombre") or "").strip(),
        "descripcion": str(vehicle.get("descripcion") or "").strip(),
        "organizacion_id": _safe_int(vehicle.get("organizacion_id")),
        "organizacion_nombre": str(vehicle.get("organizacion_nombre") or "").strip(),
        "propietario_usuario_id": _safe_int(vehicle.get("propietario_usuario_id")),
        "propietario_usuario": owner_username,
        "propietario_display_name": owner_display_name,
        "propietario_rol_codigo": str(vehicle.get("propietario_rol_codigo") or "").strip(),
        "propietario_rol_nombre": str(vehicle.get("propietario_rol_nombre") or "").strip(),
        "propietario_nivel_orden": _safe_int(vehicle.get("propietario_nivel_orden"), default=-1),
        "tipo_vehiculo_codigo": str(vehicle.get("tipo_vehiculo_codigo") or "").strip(),
        "tipo_vehiculo_nombre": str(vehicle.get("tipo_vehiculo_nombre") or "").strip(),
        "placa": str(vehicle.get("placa") or "").strip(),
        "numero_serie": str(vehicle.get("numero_serie") or "").strip(),
        "marca": str(vehicle.get("marca") or "").strip(),
        "modelo": str(vehicle.get("modelo") or "").strip(),
        "activo": bool(vehicle.get("activo")),
        "latitud_actual": (
            _safe_float(vehicle.get("telemetria_lat"))
            if _safe_float(vehicle.get("telemetria_lat")) is not None
            else _safe_float(vehicle.get("geopunto_latitud"))
        ),
        "longitud_actual": (
            _safe_float(vehicle.get("telemetria_lon"))
            if _safe_float(vehicle.get("telemetria_lon")) is not None
            else _safe_float(vehicle.get("geopunto_longitud"))
        ),
        "registration_id": str(vehicle.get("registration_id") or vehicle.get("id") or "").strip(),
        "vehicle_type": str(vehicle.get("vehicle_type") or "").strip(),
        "vehicle_type_code": str(vehicle.get("vehicle_type_code") or "").strip(),
        "vehicle_type_name": str(vehicle.get("vehicle_type_name") or "").strip(),
        "label": str(vehicle.get("label") or vehicle.get("nombre") or "").strip(),
        "identifier": str(vehicle.get("identifier") or "").strip(),
        "notes": str(vehicle.get("notes") or vehicle.get("descripcion") or "").strip(),
        "telemetry_mode": str(vehicle.get("telemetry_mode") or "").strip(),
        "api_base_url": str(vehicle.get("api_base_url") or "").strip(),
        "api_device_id": str(vehicle.get("api_device_id") or "").strip(),
        "has_live_telemetry": bool(vehicle.get("has_live_telemetry")),
        "camera_name": str(vehicle.get("camera_name") or "").strip(),
        "camera_links": list(vehicle.get("camera_links") or []),
        "ts": _safe_float(vehicle.get("ts")),
    }


def _serialize_camera_record(camera: dict[str, object]) -> dict[str, object]:
    owner_username = str(camera.get("propietario_usuario") or "").strip()
    owner_display_name = " ".join(
        part
        for part in (
            str(camera.get("propietario_nombre") or "").strip(),
            str(camera.get("propietario_apellido") or "").strip(),
        )
        if part
    ) or _display_name_from_username(owner_username)
    return {
        "id": _safe_int(camera.get("id")),
        "nombre": str(camera.get("nombre") or "").strip(),
        "descripcion": str(camera.get("descripcion") or "").strip(),
        "organizacion_id": _safe_int(camera.get("organizacion_id")),
        "organizacion_nombre": str(camera.get("organizacion_nombre") or "").strip(),
        "propietario_usuario_id": _safe_int(camera.get("propietario_usuario_id")),
        "propietario_usuario": owner_username,
        "propietario_display_name": owner_display_name,
        "propietario_rol_codigo": str(camera.get("propietario_rol_codigo") or "").strip(),
        "propietario_rol_nombre": str(camera.get("propietario_rol_nombre") or "").strip(),
        "propietario_nivel_orden": _safe_int(camera.get("propietario_nivel_orden"), default=-1),
        "creado_por_usuario": str(camera.get("creado_por_usuario") or "").strip(),
        "tipo_camara_codigo": str(camera.get("tipo_camara_codigo") or "").strip(),
        "tipo_camara_nombre": str(camera.get("tipo_camara_nombre") or "").strip(),
        "protocolo_codigo": str(camera.get("protocolo_codigo") or "").strip(),
        "protocolo_nombre": str(camera.get("protocolo_nombre") or "").strip(),
        "codigo_unico": str(camera.get("codigo_unico") or "").strip(),
        "marca": str(camera.get("marca") or "").strip(),
        "modelo": str(camera.get("modelo") or "").strip(),
        "numero_serie": str(camera.get("numero_serie") or "").strip(),
        "url_stream": str(camera.get("url_stream") or "").strip(),
        "url_rtsp": str(camera.get("url_rtsp") or "").strip(),
        "ip_camaras_fijas": str(camera.get("ip_camaras_fijas") or "").strip(),
        "usuario_stream": str(camera.get("usuario_stream") or "").strip(),
        "tiene_password_stream": bool(str(camera.get("password_stream") or "").strip()),
        "hacer_inferencia": bool(camera.get("hacer_inferencia")),
        "geopunto_estatico_id": _safe_int(camera.get("geopunto_estatico_id")),
        "latitud": _safe_float(camera.get("geopunto_latitud")),
        "longitud": _safe_float(camera.get("geopunto_longitud")),
        "altitud_m": _safe_float(camera.get("geopunto_altitud_m")),
        "direccion": str(camera.get("geopunto_direccion") or "").strip(),
        "referencia": str(camera.get("geopunto_referencia") or "").strip(),
        "vehiculo_id": _safe_int(camera.get("vehiculo_id")),
        "vehiculo_nombre": str(camera.get("vehiculo_nombre") or "").strip(),
        "vehiculo_tipo_codigo": str(camera.get("vehiculo_tipo_codigo") or "").strip(),
        "vehiculo_tipo_nombre": str(camera.get("vehiculo_tipo_nombre") or "").strip(),
        "vehiculo_posicion": str(camera.get("vehiculo_posicion") or "").strip(),
        "latitud_mapa": _safe_float(camera.get("latitud_mapa")),
        "longitud_mapa": _safe_float(camera.get("longitud_mapa")),
        "altitud_mapa": _safe_float(camera.get("altitud_mapa")),
        "activa": bool(camera.get("activa")),
    }


ROLE_LEVEL_FALLBACKS: dict[str, int] = {
    "desarrollador": 100,
    "superadmin": 100,
    "admin": 80,
    "ingeniero": 50,
    "operador": 30,
    "analista": 20,
    "supervisor": 20,
    "cliente": 10,
}


def _role_identity_tokens(role: dict[str, object]) -> set[str]:
    tokens: set[str] = set()
    for key in ("codigo", "rol", "nombre", "label"):
        normalized_role = _normalize_role_name(role.get(key))
        if normalized_role:
            tokens.add(normalized_role)
    return tokens


def _role_level(role: dict[str, object]) -> int:
    return _safe_int(role.get("nivel_orden"), default=-1)


def _resolve_request_role_level(
    request: web.Request,
    roles: list[dict[str, object]],
) -> int | None:
    current_user = _get_authenticated_user(request) or {}
    current_role = _normalize_role_name(current_user.get("rol"))
    if not current_role:
        return None

    matching_levels = [
        _role_level(role)
        for role in roles
        if current_role in _role_identity_tokens(role)
    ]
    if matching_levels:
        return max(matching_levels)
    return ROLE_LEVEL_FALLBACKS.get(current_role)


def _find_role_record(
    roles: list[dict[str, object]],
    role_value: object,
) -> dict[str, object] | None:
    raw_role = str(role_value or "").strip()
    if not raw_role:
        return None

    raw_role_folded = raw_role.casefold()
    for role in roles:
        for key in ("codigo", "rol", "nombre", "label"):
            candidate = str(role.get(key) or "").strip()
            if candidate and candidate.casefold() == raw_role_folded:
                return role

    normalized_role = _normalize_role_name(raw_role)
    if not normalized_role:
        return None

    for role in roles:
        if normalized_role in _role_identity_tokens(role):
            return role
    return None


def _filter_manageable_roles(
    request: web.Request,
    roles: list[dict[str, object]],
) -> list[dict[str, object]]:
    if _has_developer_access(request):
        return list(roles)

    current_role_level = _resolve_request_role_level(request, roles)
    if current_role_level is None:
        return []

    return [
        role
        for role in roles
        if _role_level(role) >= 0 and _role_level(role) <= current_role_level
    ]


def _filter_manageable_users(
    request: web.Request,
    users: list[dict[str, object]],
    roles: list[dict[str, object]],
) -> list[dict[str, object]]:
    if _has_developer_access(request):
        return list(users)

    current_role_level = _resolve_request_role_level(request, roles)
    if current_role_level is None:
        return []

    return [
        user
        for user in users
        if _safe_int(user.get("nivel_orden"), default=-1) >= 0
        and _safe_int(user.get("nivel_orden"), default=-1) <= current_role_level
    ]


def _filter_manageable_organizations(
    request: web.Request,
    organizations: list[dict[str, object]],
    roles: list[dict[str, object]],
) -> list[dict[str, object]]:
    if _has_developer_access(request):
        return list(organizations)

    current_role_level = _resolve_request_role_level(request, roles)
    if current_role_level is None:
        return []

    return [
        organization
        for organization in organizations
        if _safe_int(organization.get("propietario_nivel_orden"), default=-1) >= 0
        and _safe_int(organization.get("propietario_nivel_orden"), default=-1) <= current_role_level
    ]


def _filter_manageable_vehicles(
    request: web.Request,
    vehicles: list[dict[str, object]],
    roles: list[dict[str, object]],
) -> list[dict[str, object]]:
    if _has_developer_access(request):
        return list(vehicles)

    current_role_level = _resolve_request_role_level(request, roles)
    if current_role_level is None:
        return []

    return [
        vehicle
        for vehicle in vehicles
        if _safe_int(vehicle.get("propietario_nivel_orden"), default=-1) >= 0
        and _safe_int(vehicle.get("propietario_nivel_orden"), default=-1) <= current_role_level
    ]


def _filter_manageable_cameras(
    request: web.Request,
    cameras: list[dict[str, object]],
    roles: list[dict[str, object]],
) -> list[dict[str, object]]:
    if _has_developer_access(request):
        return list(cameras)

    current_role_level = _resolve_request_role_level(request, roles)
    if current_role_level is None:
        return []

    return [
        camera
        for camera in cameras
        if _safe_int(camera.get("propietario_nivel_orden"), default=-1) >= 0
        and _safe_int(camera.get("propietario_nivel_orden"), default=-1) <= current_role_level
    ]


def _request_role_level(request: web.Request | None) -> int | None:
    if request is None:
        return None

    current_user = _get_authenticated_user(request) or {}
    explicit_level = current_user.get("nivel_orden")
    if isinstance(explicit_level, int) and explicit_level > 0:
        return explicit_level

    current_role = _normalize_role_name(current_user.get("rol"))
    if not current_role:
        return None
    return ROLE_LEVEL_FALLBACKS.get(current_role)


def _device_owner_level(device: object) -> int | None:
    if isinstance(device, dict):
        owner_level = device.get("owner_level")
    else:
        owner_level = getattr(device, "owner_level", None)
    if owner_level is None:
        return None
    try:
        return int(owner_level)
    except (TypeError, ValueError):
        return None


def _device_visible_for_request(request: web.Request | None, device: object) -> bool:
    if request is None or _has_developer_access(request):
        return True

    request_role_level = _request_role_level(request)
    if request_role_level is None:
        return False

    owner_level = _device_owner_level(device)
    if owner_level is None or owner_level < 0:
        return True
    return owner_level <= request_role_level


def _filter_visible_device_dicts(
    request: web.Request | None,
    devices: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [device for device in devices if _device_visible_for_request(request, device)]


def _visible_camera_names_for_request(request: web.Request | None) -> set[str]:
    visible_names: set[str] = set()
    for device in APP_CONTEXT.device_catalog.list_devices():
        if _device_visible_for_request(request, device):
            visible_names.add(device.camera_name)
    return visible_names


def _role_scope_forbidden_response() -> web.Response:
    return _json_response(
        {
            "error": "role_scope_forbidden",
            "message": "Solo puedes gestionar usuarios con prioridad igual o inferior a la de tu rol.",
        },
        status=403,
    )


def _organization_scope_forbidden_response() -> web.Response:
    return _json_response(
        {
            "error": "organization_scope_forbidden",
            "message": "Solo puedes gestionar organizaciones cuyo propietario este dentro de tu jerarquia.",
        },
        status=403,
    )


def _camera_scope_forbidden_response() -> web.Response:
    return _json_response(
        {
            "error": "camera_scope_forbidden",
            "message": "Solo puedes gestionar camaras cuyo propietario este dentro de tu jerarquia.",
        },
        status=403,
    )


def _vehicle_scope_forbidden_response() -> web.Response:
    return _json_response(
        {
            "error": "vehicle_scope_forbidden",
            "message": "Solo puedes gestionar vehiculos cuyo propietario este dentro de tu jerarquia.",
        },
        status=403,
    )


def _encode_session(user: dict[str, object], *, expires_at: int | None = None) -> str:
    issued_at = int(time.time())
    normalized_role = _resolve_user_role(user)
    normalized_level = _safe_int(
        user.get("nivel_orden"),
        default=ROLE_LEVEL_FALLBACKS.get(normalized_role or str(user.get("rol") or ""), 0),
    )
    payload = {
        "user_id": user["id"],
        "usuario": user["usuario"],
        "rol": normalized_role or user["rol"],
        "nivel_orden": normalized_level if normalized_level > 0 else None,
        "iat": issued_at,
        "exp": expires_at if expires_at is not None else issued_at + SESSION_MAX_AGE_SEC,
    }
    
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(serialized).decode("ascii").rstrip("=")
    signature = _sign_session_payload(encoded_payload)
    return f"{encoded_payload}.{signature}"


def _decode_session(session_value: str | None) -> dict[str, object] | None:
    if not session_value or "." not in session_value:
        return None

    encoded_payload, signature = session_value.rsplit(".", 1)
    expected_signature = _sign_session_payload(encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        padded_payload = encoded_payload + ("=" * (-len(encoded_payload) % 4))
        raw_payload = base64.urlsafe_b64decode(padded_payload.encode("ascii"))
        payload = json.loads(raw_payload.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at <= int(time.time()):
        return None

    return payload


def _get_bearer_token(request: web.Request | None) -> str | None:
    if request is None:
        return None
    headers = getattr(request, "headers", None)
    if not headers:
        return None
    authorization = headers.get("Authorization") or headers.get("authorization")
    if not isinstance(authorization, str):
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    normalized_token = token.strip()
    return normalized_token or None


def _decode_bearer_token(token_value: str | None) -> dict[str, object] | None:
    payload = decode_jwt(token_value)
    if payload is None:
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    username = str(payload.get("usuario") or "").strip()
    role = _normalize_role_name(payload.get("rol"))
    expires_at = payload.get("exp")
    issued_at = payload.get("iat")
    role_level = _safe_int(payload.get("nivel_orden"), default=ROLE_LEVEL_FALLBACKS.get(role, 0))
    if not username or not role or not isinstance(expires_at, int) or not isinstance(issued_at, int):
        return None
    return {
        "id": user_id,
        "usuario": username,
        "rol": role,
        "nivel_orden": role_level if isinstance(role_level, int) and role_level > 0 else ROLE_LEVEL_FALLBACKS.get(role),
        "session_started_at": issued_at,
        "session_expires_at": expires_at,
    }


def _get_authenticated_user(request: web.Request) -> dict[str, object] | None:
    cached_user = request.get("auth_user")
    if isinstance(cached_user, dict):
        return cached_user

    bearer_user = _decode_bearer_token(_get_bearer_token(request))
    if bearer_user is not None:
        request["auth_user"] = bearer_user
        return bearer_user

    payload = _decode_session(request.cookies.get(SESSION_COOKIE_NAME))
    if payload is None:
        return None

    user_id = payload.get("user_id")
    username = payload.get("usuario")
    role = _normalize_role_name(payload.get("rol"))
    role_level = payload.get("nivel_orden")
    expires_at = payload.get("exp")
    issued_at = payload.get("iat")
    if not isinstance(user_id, int) or not isinstance(username, str) or not role:
        return None
    if not isinstance(expires_at, int):
        return None
    if not isinstance(issued_at, int):
        issued_at = expires_at - SESSION_MAX_AGE_SEC

    user = {
        "id": user_id,
        "usuario": username,
        "rol": role,
        "nivel_orden": role_level if isinstance(role_level, int) and role_level > 0 else ROLE_LEVEL_FALLBACKS.get(role),
        "session_started_at": issued_at,
        "session_expires_at": expires_at,
    }
    request["auth_user"] = user
    return user


def _set_auth_cookie(response: web.Response, user: dict[str, object]) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        _encode_session(user),
        httponly=True,
        max_age=SESSION_MAX_AGE_SEC,
        path="/",
        samesite="Lax",
    )


def _clear_auth_cookie(response: web.Response) -> None:
    response.del_cookie(SESSION_COOKIE_NAME, path="/")


def _build_access_token_response(user: dict[str, object]) -> dict[str, object]:
    normalized_user = _normalize_user_record(user)
    normalized_role = _resolve_user_role(normalized_user)
    role_level = _safe_int(
        normalized_user.get("nivel_orden"),
        default=ROLE_LEVEL_FALLBACKS.get(normalized_role or str(normalized_user.get("rol") or ""), 0),
    )
    access_token, expires_in = issue_access_token(
        user_id=int(normalized_user["id"]),
        username=str(normalized_user["usuario"]),
        role=normalized_role or str(normalized_user.get("rol") or ""),
        role_level=role_level if role_level > 0 else None,
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "user": _serialize_user_record(normalized_user),
    }


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in PUBLIC_PATH_PREFIXES
    )


def _ensure_database_ready() -> None:
    if not db.is_open:
        db.open()
    ensure_bootstrap_seed()


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if _is_public_path(request.path):
        return await handler(request)

    if _get_authenticated_user(request) is not None:
        return await handler(request)

    if request.path.startswith("/api/") or request.path.startswith("/webrtc/"):
        return _json_response(
            {
                "error": "authentication_required",
                "message": "Debes iniciar sesión para continuar.",
            },
            status=401,
        )

    raise web.HTTPFound("/login")


def _query_value(request: web.Request, name: str) -> str | None:
    raw = request.query.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _query_limit(request: web.Request, default: int = 100, maximum: int = 500) -> int:
    raw = request.query.get("limit")
    if raw is None:
        return default
    try:
        return max(1, min(int(raw), maximum))
    except (TypeError, ValueError):
        return default


def _safe_float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_coordinate(payload: dict[str, object], key: str, *, minimum: float, maximum: float) -> float | None:
    raw = payload.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("invalid_camera_location") from None
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError("invalid_camera_location")
    return value


def _parse_optional_int(payload: dict[str, object], key: str, *, minimum: int | None = None) -> int | None:
    raw = payload.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"invalid_{key}") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"invalid_{key}")
    return value


def _camera_dom_id(camera_name: str, idx: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", camera_name)
    return f"cam_{idx}_{base}" if base else f"cam_{idx}"


def _get_web_settings():
    return build_web_settings(read_yaml(APP_CONTEXT.config_path))


def _snapshot_stream_states() -> list[tuple[str, str, str, int]]:
    return [
        (device.camera_name, "available", "", 0)
        for device in APP_CONTEXT.device_catalog.list_devices()
    ]


def _is_likely_managed_viewer_source(raw_url: object) -> bool:
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


def _resolve_authorized_stream_name(camera_name: str, *source_candidates: object) -> str:
    normalized_camera_name = str(camera_name or "").strip()
    for source in source_candidates:
        candidate = str(source or "").strip()
        if not _is_likely_managed_viewer_source(candidate):
            continue
        path = str(urlparse(candidate).path or "").strip("/")
        if path:
            return path
    return normalized_camera_name


def _request_authorized_viewer_url_for_camera(camera_name: str) -> str:
    normalized_camera_name = str(camera_name or "").strip()
    if not normalized_camera_name:
        raise StreamViewerError("invalid_camera_name")

    device = APP_CONTEXT.device_catalog.by_camera_name(normalized_camera_name)
    if device is None:
        raise StreamViewerError("camera_not_found")

    stream_name = _resolve_authorized_stream_name(
        normalized_camera_name,
        getattr(device, "viewer_url", ""),
        getattr(device, "source", ""),
    )
    client = ProtectedStreamViewerClient(
        api_base_url=DEFAULT_API_BASE_URL,
        credentials=ViewerCredentials(
            username=DEFAULT_API_USERNAME,
            password=DEFAULT_API_PASSWORD,
        ),
        request_timeout=DEFAULT_REQUEST_TIMEOUT,
    )
    try:
        return client.request_stream_viewer_url(stream_name)
    finally:
        client.close()


def _request_authorized_viewer_payload_for_camera(
    camera_name: str,
    *,
    muted: bool,
    controls: bool,
) -> dict[str, str]:
    normalized_camera_name = str(camera_name or "").strip()
    if not normalized_camera_name:
        raise StreamViewerError("invalid_camera_name")

    device = APP_CONTEXT.device_catalog.by_camera_name(normalized_camera_name)
    if device is None:
        return {
            "camera_name": normalized_camera_name,
            "viewer_url": None,
            "viewer_html": "<div class='viewer-error'>Cámara no encontrada o no registrada en MediaMTX.</div>",
            "error": "camera_not_found"
        }

    stream_name = _resolve_authorized_stream_name(
        normalized_camera_name,
        getattr(device, "viewer_url", ""),
        getattr(device, "source", ""),
    )
    client = ProtectedStreamViewerClient(
        api_base_url=DEFAULT_API_BASE_URL,
        credentials=ViewerCredentials(
            username=DEFAULT_API_USERNAME,
            password=DEFAULT_API_PASSWORD,
        ),
        request_timeout=DEFAULT_REQUEST_TIMEOUT,
    )
    try:
        try:
            viewer_url = client.request_stream_viewer_url(stream_name)
            viewer_cookies = [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "path": cookie.path or "/",
                }
                for cookie in client.session.cookies
                if str(cookie.name or "").startswith("stream_session_")
            ]
        except Exception as exc:
            return {
                "camera_name": normalized_camera_name,
                "viewer_url": None,
                "viewer_html": f"<div class='viewer-error'>Error autenticando o cargando el stream: {str(exc)}</div>",
                "error": "auth_error"
            }
    finally:
        client.close()

    return {
        "camera_name": normalized_camera_name,
        "viewer_url": viewer_url,
        "viewer_html": "",
        "viewer_cookies": viewer_cookies,
        "error": None
    }


def _rewrite_viewer_url_for_request_host(viewer_url: str, request: web.Request) -> str:
    candidate = str(viewer_url or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return candidate

    request_host = str(request.headers.get("Host") or "").strip()
    if not request_host:
        return candidate

    browser_hostname = request_host.rsplit("@", 1)[-1].split(":", 1)[0].strip()
    if not browser_hostname:
        return candidate

    api_base = urlparse(DEFAULT_API_BASE_URL)
    api_port = str(api_base.port or os.getenv("STREAM_API_PORT", "8004")).strip() or "8004"
    return parsed._replace(netloc=f"{browser_hostname}:{api_port}").geturl()


def _visible_device_by_camera_id_for_request(
    request: web.Request | None,
    camera_id: int,
):
    if camera_id <= 0:
        return None

    for device in APP_CONTEXT.device_catalog.list_devices():
        if getattr(device, "camera_id", None) != camera_id:
            continue
        if _device_visible_for_request(request, device):
            return device
    return None


def _camera_item_payload(camera_name: str, dom_id: str) -> dict[str, object]:
    device = APP_CONTEXT.device_catalog.by_camera_name(camera_name)
    camera_record = APP_CONTEXT.camera_records_by_name.get(camera_name, {})
    return {
        "name": camera_name,
        "dom_id": dom_id,
        "camera_id": _safe_int(camera_record.get("id")),
        "hacer_inferencia": bool(camera_record.get("hacer_inferencia")),
        "capabilities": dict(device.capabilities) if device is not None else {},
        "organization_name": str(camera_record.get("organizacion_nombre") or "").strip(),
    }


def _format_ui_datetime(timestamp: int | None) -> str:
    if not isinstance(timestamp, int) or timestamp <= 0:
        return "No disponible"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _display_name_from_username(username: str) -> str:
    clean_username = re.sub(r"[_\-.]+", " ", username).strip()
    if not clean_username:
        return "Operador"
    return " ".join(part.capitalize() for part in clean_username.split())


def _initials_from_label(label: str) -> str:
    parts = [part for part in re.split(r"\s+", label.strip()) if part]
    if not parts:
        return "RB"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[1][0]}".upper()


def _database_status_label() -> str:
    try:
        _ensure_database_ready()
    except DatabaseError:
        return "No disponible"
    return "Conectada" if db.health_check() else "Sin respuesta"


def _build_plate_preview_replacements(plates: list[object] | None = None) -> dict[str, str]:
    unique_plates: list[dict[str, str]] = []
    seen_plates: set[str] = set()

    for item in plates or []:
        if isinstance(item, dict):
            raw_plate = item.get("plate")
            raw_file = item.get("file")
        else:
            raw_plate = item
            raw_file = ""

        normalized_plate = str(raw_plate or "").strip().upper()
        if not normalized_plate or normalized_plate in seen_plates:
            continue
        seen_plates.add(normalized_plate)
        unique_plates.append(
            {
                "plate": normalized_plate,
                "file": str(raw_file or "").strip(),
            }
        )

    selected_plate = unique_plates[0]["plate"] if unique_plates else ""
    selected_file = unique_plates[0]["file"] if unique_plates else ""
    if unique_plates:
        choice_blocks = []
        for idx, item in enumerate(unique_plates):
            plate = item["plate"]
            safe_plate = html.escape(plate, quote=True)
            safe_file = html.escape(item["file"], quote=True)
            active_class = " is-active" if idx == 0 else ""
            pressed = "true" if idx == 0 else "false"
            choice_blocks.append(
                (
                    f'<button class="plate-preview-choice{active_class}" type="button" '
                    f'data-plate-value="{safe_plate}" data-plate-file="{safe_file}" '
                    f'aria-pressed="{pressed}">{safe_plate}</button>'
                )
            )
        choices_markup = "\n".join(choice_blocks)
    else:
        choices_markup = '<span class="plate-preview-empty">Sin placas detectadas.</span>'

    return {
        "__PLATE_PREVIEW_CHOICES__": choices_markup,
        "__PLATE_PREVIEW_SELECTED__": html.escape(selected_plate, quote=True),
        "__PLATE_PREVIEW_SELECTED_FILE__": html.escape(selected_file),
    }


def _default_template_replacements() -> dict[str, str]:
    return {
        "__AUTH_USERNAME__": "Operador",
        "__DEVELOPER_MENU_LINK__": "",
        "__CAMERA_PAGE_ACTION__": "",
        "__CAMERA_ADMIN_MODAL__": "",
        "__TELEMETRY_FOCUS_RAIL__": _read_template_source("partials/telemetry_focus_rail.html"),
        "__USER_ADMIN_MODE_LABEL__": "Modo Desarrollador",
        "__USER_ADMIN_SCOPE_LABEL__": "Desarrolladores",
        "__USER_ADMIN_SCOPE_ROLE__": "desarrollador",
        "__ROLE_ADMIN_HERO_CARD__": _read_template_source("partials/user_admin_role_hero_card.html"),
        "__ROLE_ADMIN_SECTION__": _read_template_source("partials/user_admin_role_section.html"),
        "__USER_ADMIN_ACCESS_NOTE__": "Solo el rol desarrollador puede acceder a este panel administrativo.",
        "__ORGANIZATION_ADMIN_ACCESS_NOTE__": "Solo veras organizaciones cuyo propietario este dentro de tu jerarquia operativa.",
        "__CAMERA_ADMIN_ACCESS_NOTE__": "Solo veras camaras cuyo propietario este dentro de tu jerarquia operativa.",
        **_build_plate_preview_replacements(),
    }


def _has_developer_access(request: web.Request) -> bool:
    user = _get_authenticated_user(request) or {}
    return _normalize_role_name(user.get("rol")) == "desarrollador"


def _has_admin_access(request: web.Request) -> bool:
    user = _get_authenticated_user(request) or {}
    return _normalize_role_name(user.get("rol")) == "admin"


def _has_engineer_access(request: web.Request) -> bool:
    user = _get_authenticated_user(request) or {}
    return _normalize_role_name(user.get("rol")) == "ingeniero"


def _has_user_admin_access(request: web.Request) -> bool:
    return _has_developer_access(request) or _has_admin_access(request) or _has_engineer_access(request)


def _developer_sidebar_link_markup() -> str:
    return (
        '<a class="sidebar-link" href="/usuarios">'
        '<span class="sidebar-icon" aria-hidden="true">◧</span>'
        '<span class="sidebar-link-copy">'
        "<strong>Usuarios</strong>"
        "<span>CRUD de accesos</span>"
        "</span>"
        '<span class="sidebar-link-tooltip" aria-hidden="true">Usuarios</span>'
        "</a>"
        '<a class="sidebar-link" href="/registros">'
        '<span class="sidebar-icon" aria-hidden="true">▥</span>'
        '<span class="sidebar-link-copy">'
        "<strong>Registros</strong>"
        "<span>Organizaciones y cámaras</span>"
        "</span>"
        '<span class="sidebar-link-tooltip" aria-hidden="true">Registros</span>'
        "</a>"
    )


def _ensure_user_admin_page_access(request: web.Request) -> None:
    if _has_user_admin_access(request):
        return
    raise web.HTTPFound("/")


def _ensure_developer_page_access(request: web.Request) -> None:
    if _has_developer_access(request):
        return
    raise web.HTTPFound("/")


def _user_admin_api_guard(request: web.Request) -> web.Response | None:
    if _has_user_admin_access(request):
        return None
    return _json_response(
        {
            "error": "forbidden",
            "message": "Solo los roles administrador, ingeniero y desarrollador pueden acceder a esta sección.",
        },
        status=403,
    )


def _developer_api_guard(request: web.Request) -> web.Response | None:
    if _has_developer_access(request):
        return None
    return _json_response(
        {
            "error": "forbidden",
            "message": "Solo el rol desarrollador puede acceder a esta sección.",
        },
        status=403,
    )


def _parse_user_target_id(request: web.Request) -> int | None:
    raw_user_id = str(request.match_info.get("user_id", "")).strip()
    if not raw_user_id:
        return None
    try:
        return int(raw_user_id)
    except (TypeError, ValueError):
        return None


def _parse_role_target_id(request: web.Request) -> int | None:
    raw_role_id = str(request.match_info.get("role_id", "")).strip()
    if not raw_role_id:
        return None
    try:
        return int(raw_role_id)
    except (TypeError, ValueError):
        return None


def _parse_organization_target_id(request: web.Request) -> int | None:
    raw_organization_id = str(request.match_info.get("organization_id", "")).strip()
    if not raw_organization_id:
        return None
    try:
        return int(raw_organization_id)
    except (TypeError, ValueError):
        return None


def _parse_camera_target_id(request: web.Request) -> int | None:
    raw_camera_id = str(request.match_info.get("camera_id", "")).strip()
    if not raw_camera_id:
        return None
    try:
        return int(raw_camera_id)
    except (TypeError, ValueError):
        return None


def _build_authenticated_shell_replacements(request: web.Request) -> dict[str, str]:
    user = _get_authenticated_user(request) or {}
    username = str(user.get("usuario") or "operador").strip() or "operador"
    replacements = {
        "__AUTH_USERNAME__": html.escape(username),
        "__DEVELOPER_MENU_LINK__": "",
        "__CAMERA_PAGE_ACTION__": "",
        "__CAMERA_ADMIN_MODAL__": "",
    }
    if _has_user_admin_access(request):
        replacements["__DEVELOPER_MENU_LINK__"] = _developer_sidebar_link_markup()
        replacements["__CAMERA_PAGE_ACTION__"] = (
            '<button class="camera-register-open" id="camera-register-open" type="button">'
            "Registrar nueva cámara"
            "</button>"
        )
        replacements["__CAMERA_ADMIN_MODAL__"] = _build_camera_admin_modal_markup(request)
    return replacements


def _build_camera_admin_modal_markup(request: web.Request) -> str:
    modal_markup = _read_template_source("partials/camera_admin_modal.html")
    camera_admin_note = _build_user_admin_replacements(request).get(
        "__CAMERA_ADMIN_ACCESS_NOTE__",
        _default_template_replacements()["__CAMERA_ADMIN_ACCESS_NOTE__"],
    )
    return modal_markup.replace("__CAMERA_ADMIN_ACCESS_NOTE__", html.escape(camera_admin_note))


def _build_user_admin_replacements(request: web.Request) -> dict[str, str]:
    if _has_developer_access(request):
        return {
            "__USER_ADMIN_MODE_LABEL__": "Modo Desarrollador",
            "__USER_ADMIN_SCOPE_LABEL__": "Desarrolladores",
            "__USER_ADMIN_SCOPE_ROLE__": "desarrollador",
            "__ROLE_ADMIN_HERO_CARD__": _read_template_source("partials/user_admin_role_hero_card.html"),
            "__ROLE_ADMIN_SECTION__": _read_template_source("partials/user_admin_role_section.html"),
            "__USER_ADMIN_ACCESS_NOTE__": "Tu rol desarrollador puede gestionar usuarios y roles dentro de esta consola.",
            "__ORGANIZATION_ADMIN_ACCESS_NOTE__": "Tu rol desarrollador puede gestionar organizaciones de cualquier nivel dentro del sistema.",
            "__CAMERA_ADMIN_ACCESS_NOTE__": "Tu rol desarrollador puede gestionar cámaras fijas o móviles de cualquier nivel dentro del sistema.",
        }

    if _has_admin_access(request):
        return {
            "__USER_ADMIN_MODE_LABEL__": "Modo Administrador",
            "__USER_ADMIN_SCOPE_LABEL__": "Administradores",
            "__USER_ADMIN_SCOPE_ROLE__": "admin",
            "__ROLE_ADMIN_HERO_CARD__": "",
            "__ROLE_ADMIN_SECTION__": "",
            "__USER_ADMIN_ACCESS_NOTE__": "Tu rol administrador puede gestionar usuarios.",
            "__ORGANIZATION_ADMIN_ACCESS_NOTE__": "Tu rol administrador puede gestionar organizaciones de administradores, ingenieros y clientes.",
            "__CAMERA_ADMIN_ACCESS_NOTE__": "Tu rol administrador puede gestionar cámaras de administradores, ingenieros y clientes.",
        }

    return {
        "__USER_ADMIN_MODE_LABEL__": "Modo Ingeniero",
        "__USER_ADMIN_SCOPE_LABEL__": "Ingenieros",
        "__USER_ADMIN_SCOPE_ROLE__": "ingeniero",
        "__ROLE_ADMIN_HERO_CARD__": "",
        "__ROLE_ADMIN_SECTION__": "",
        "__USER_ADMIN_ACCESS_NOTE__": "Tu rol ingeniero puede gestionar usuarios de ingeniero para abajo. Los roles administrador y desarrollador quedan fuera de este directorio.",
        "__ORGANIZATION_ADMIN_ACCESS_NOTE__": "Tu rol ingeniero puede gestionar organizaciones de ingenieros y clientes.",
        "__CAMERA_ADMIN_ACCESS_NOTE__": "Tu rol ingeniero puede gestionar cámaras de ingenieros y clientes.",
    }


def _build_profile_replacements(request: web.Request) -> dict[str, str]:
    user = _get_authenticated_user(request) or {}
    username = str(user.get("usuario") or "operador")
    role = _normalize_role_name(user.get("rol")) or "sin rol"
    user_id = int(user.get("id") or 0)
    display_name = _display_name_from_username(username)
    role_label = {
        "admin": "Administrador",
        "desarrollador": "Desarrollador",
        "ingeniero": "Ingeniero",
        "cliente": "Cliente",
        "operador": "Operador",
        "analista": "Analista",
        "supervisor": "Supervisor",
    }.get(role.casefold(), role.replace("_", " ").strip().title() or "Sin rol")
    role_notes = {
        "admin": "Cuenta con control total sobre accesos, modulos y supervision general del sistema.",
        "administrador": "Cuenta con control total sobre accesos, modulos y supervision general del sistema.",
        "supervisor": "Perfil orientado a vision global, coordinacion y seguimiento operativo de incidentes.",
        "operador": "Acceso pensado para monitoreo continuo, lectura rapida y respuesta tactica del tablero.",
        "analista": "Enfoque en revision de evidencia, trazas de eventos y contexto tecnico del despliegue.",
        "desarrollador": "Perfil tecnico con foco en soporte, validacion interna y ajuste del comportamiento del sistema.",
    }
    role_note = role_notes.get(
        role.casefold(),
        "Cuenta autenticada para operar la consola y revisar los modulos habilitados dentro del sistema.",
    )

    session_started_at = user.get("session_started_at")
    session_expires_at = user.get("session_expires_at")
    started_at_value = session_started_at if isinstance(session_started_at, int) else None
    expires_at_value = session_expires_at if isinstance(session_expires_at, int) else None
    remaining_seconds = expires_at_value - int(time.time()) if expires_at_value is not None else None
    if remaining_seconds is None:
        session_status = "Activa"
    elif remaining_seconds <= 15 * 60:
        session_status = "Expira pronto"
    elif remaining_seconds <= 60 * 60:
        session_status = "Vigente"
    else:
        session_status = "Estable"

    snapshot = _snapshot_stream_states()
    devices = _filter_visible_device_dicts(request, APP_CONTEXT.device_catalog.as_dicts())
    visible_camera_names = {str(device.get("camera_name") or "").strip() for device in devices}
    snapshot = [item for item in snapshot if item[0] in visible_camera_names]
    viewer_total = sum(
        clients for _, _, _, clients in snapshot
        if isinstance(clients, int) and clients > 0
    )
    camera_total = len(snapshot)
    device_total = len(devices)
    db_status = _database_status_label()

    replacements = {
        "__PROFILE_INITIALS__": _initials_from_label(display_name),
        "__PROFILE_DISPLAY_NAME__": display_name,
        "__PROFILE_USERNAME__": username,
        "__PROFILE_ROLE_LABEL__": role_label,
        "__PROFILE_ROLE_NOTE__": role_note,
        "__PROFILE_USER_ID__": str(user_id),
        "__PROFILE_SESSION_STARTED__": _format_ui_datetime(started_at_value),
        "__PROFILE_SESSION_EXPIRES__": _format_ui_datetime(expires_at_value),
        "__PROFILE_SESSION_STATUS__": session_status,
        "__PROFILE_DB_STATUS__": db_status,
        "__PROFILE_CAMERA_TOTAL__": str(camera_total),
        "__PROFILE_DEVICE_TOTAL__": str(device_total),
        "__PROFILE_VIEWER_TOTAL__": str(viewer_total),
    }
    return {key: html.escape(value) for key, value in replacements.items()}


def _render_template(
    template_name: str = "index.html",
    *,
    request: web.Request | None = None,
    replacements: dict[str, str] | None = None,
) -> bytes:
    APP_CONTEXT.ensure_initialized()
    snapshot = _snapshot_stream_states()
    settings = _get_web_settings()
    devices = _filter_visible_device_dicts(request, APP_CONTEXT.device_catalog.as_dicts())
    visible_camera_names = {str(device.get("camera_name") or "").strip() for device in devices}
    snapshot = [
        item
        for item in snapshot
        if item[0] in visible_camera_names
    ]

    status_label = (
        " | ".join(
            f"{name}: {status.upper()} ({clients})"
            for name, status, _, clients in snapshot
        )
        or "IDLE"
    )

    camera_blocks: list[str] = []
    error_blocks: list[str] = []
    camera_items: list[dict[str, object]] = []

    for idx, (camera_name, status, err, _) in enumerate(snapshot):
        safe_camera_name = html.escape(camera_name)
        safe_camera_label = html.escape(camera_name.upper())
        dom_id = _camera_dom_id(camera_name, idx)
        camera_items.append(_camera_item_payload(camera_name, dom_id))

        camera_blocks.append(
            "".join(
                [
                    (
                        f'<section class="camera-card" id="card-{dom_id}" '
                        f'role="button" tabindex="0" aria-pressed="false" '
                        f'aria-label="Abrir cámara {safe_camera_name}">'
                    ),
                    f'<video class="video" id="video-{dom_id}" autoplay playsinline muted></video>',
                    (
                        f'<button class="camera-card-close" id="card-close-{dom_id}" '
                        f'type="button" hidden aria-label="Cerrar cámara {safe_camera_name}">×</button>'
                    ),
                    '<div class="camera-meta">',
                    '<div class="camera-topline">',
                    f'<div class="camera-name">{safe_camera_label}</div>',
                    f'<div class="camera-state" id="state-{dom_id}">Conectando...</div>',
                    "</div>",
                    f'<div class="camera-badges" id="badges-{dom_id}"></div>',
                    '<div class="camera-footer">',
                    '<div class="camera-hint">Toca para enfocar</div>',
                    (
                        f'<button class="camera-audio-toggle" id="card-audio-{dom_id}" '
                        'type="button" hidden>Activar audio</button>'
                    ),
                    "</div>",
                    "</div>",
                    "</section>",
                ]
            )
        )

        if status == "error" and err:
            error_blocks.append(
                (
                    '<section class="error-card">'
                    f"<h3>Error {safe_camera_name}</h3><pre>{html.escape(err)}</pre>"
                    "</section>"
                )
            )

    camera_items_json = json.dumps(camera_items, ensure_ascii=False).replace("</", "<\\/")
    devices_json = json.dumps(devices, ensure_ascii=False).replace("</", "<\\/")

    template = _read_template_source(template_name)
    static_asset_version = _static_asset_version()
    page = (
        template.replace("__STATUS_LABEL__", html.escape(status_label))
        .replace("__CAMERA_STREAMS__", "\n".join(camera_blocks))
        .replace("__ERROR_BLOCK__", "\n".join(error_blocks))
        .replace("__CAMERA_ITEMS_JSON__", camera_items_json)
        .replace("__DEVICE_CATALOG_JSON__", devices_json)
        .replace("__DEFAULT_CAMERA_JSON__", json.dumps(settings.default_camera, ensure_ascii=False))
        .replace("__STATIC_ASSET_VERSION__", static_asset_version)
        .replace("__TELEMETRY_REFRESH_MS__", str(int(TELEMETRY_REFRESH_SECONDS * 1000)))
    )
    merged_replacements = _default_template_replacements()
    if replacements:
        merged_replacements.update(replacements)
    for token, value in merged_replacements.items():
        page = page.replace(token, value)
    # Evita filtrar placeholders internos si hubo una mezcla temporal
    # entre una plantilla nueva y un proceso viejo sin reiniciar.
    page = page.replace("__ROLE_ADMIN_HERO_CARD__", "").replace("__ROLE_ADMIN_SECTION__", "")
    return page.encode("utf-8")


async def handle_index(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    return _html_response(
        "index.html",
        request=request,
        replacements={"__TELEMETRY_FOCUS_RAIL__": ""},
    )

async def handle_perfil(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    return _html_response("perfil.html", request=request, replacements=_build_profile_replacements(request))


def _connect_crops_ssh_for_camaras():
    config = build_default_crops_ssh_config(
        connect_timeout=3,
        command_timeout=5,
        max_retries=1,
        retry_delay=0,
        log_level=logging.WARNING,
    )
    manifest_path = get_default_crops_remote_manifest_path()
    client = RobustSSHClient(config, logger=LOGGER)

    try:
        result = client.read_remote_text_file(manifest_path, check=False, max_retries=1)
    except SSHError:
        LOGGER.exception(
            "No se pudo leer manifest.jsonl por SSH al cargar /camaras: %s@%s:%s",
            config.user,
            config.host,
            config.port,
        )
        return None

    if result.success:
        plate_values = parse_unique_plate_file_records(result.stdout)
        LOGGER.info(
            "Manifest remoto leido por SSH al cargar /camaras: %s@%s:%s placas=%s",
            config.user,
            config.host,
            config.port,
            len(plate_values),
        )
        return plate_values
    else:
        LOGGER.warning(
            "Fallo la lectura SSH de manifest.jsonl al cargar /camaras: "
            "%s@%s:%s returncode=%s stderr=%s",
            config.user,
            config.host,
            config.port,
            result.returncode,
            result.stderr or "(vacio)",
        )
    return []


def _get_cached_crops_plate_values() -> list[dict[str, str]]:
    with _CROPS_MANIFEST_CACHE_LOCK:
        cached_values = _CROPS_MANIFEST_CACHE.get("plate_values")
        if not isinstance(cached_values, list):
            return []
        return list(cached_values)


def _is_crops_manifest_cache_fresh() -> bool:
    with _CROPS_MANIFEST_CACHE_LOCK:
        updated_at = float(_CROPS_MANIFEST_CACHE.get("updated_at") or 0.0)
    return updated_at > 0 and (time.time() - updated_at) <= CROPS_MANIFEST_CACHE_TTL_SEC


def _refresh_crops_manifest_cache(force: bool = False) -> list[dict[str, str]]:
    with _CROPS_MANIFEST_CACHE_LOCK:
        updated_at = float(_CROPS_MANIFEST_CACHE.get("updated_at") or 0.0)
        is_fresh = updated_at > 0 and (time.time() - updated_at) <= CROPS_MANIFEST_CACHE_TTL_SEC
        if not force and is_fresh:
            cached_values = _CROPS_MANIFEST_CACHE.get("plate_values")
            return list(cached_values) if isinstance(cached_values, list) else []
        if _CROPS_MANIFEST_CACHE.get("refreshing"):
            cached_values = _CROPS_MANIFEST_CACHE.get("plate_values")
            return list(cached_values) if isinstance(cached_values, list) else []
        _CROPS_MANIFEST_CACHE["refreshing"] = True

    try:
        plate_values = _connect_crops_ssh_for_camaras()
        normalized_values = plate_values if isinstance(plate_values, list) else []
        with _CROPS_MANIFEST_CACHE_LOCK:
            _CROPS_MANIFEST_CACHE["plate_values"] = list(normalized_values)
            _CROPS_MANIFEST_CACHE["updated_at"] = time.time()
        return normalized_values
    finally:
        with _CROPS_MANIFEST_CACHE_LOCK:
            _CROPS_MANIFEST_CACHE["refreshing"] = False


def _refresh_crops_manifest_cache_in_background() -> None:
    try:
        _refresh_crops_manifest_cache(force=True)
    except Exception:
        LOGGER.exception("No se pudo refrescar el cache de manifest remoto para /camaras.")


async def handle_camaras(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    if _is_crops_manifest_cache_fresh():
        plate_values = _get_cached_crops_plate_values()
    else:
        plate_values = _get_cached_crops_plate_values()
        threading.Thread(
            target=_refresh_crops_manifest_cache_in_background,
            daemon=True,
            name="crops-manifest-cache-refresh",
        ).start()
    return _html_response(
        "camaras.html",
        request=request,
        replacements=_build_plate_preview_replacements(plate_values),
    )


def _read_remote_plate_file_detail(remote_file_path: str) -> dict[str, object]:
    normalized_path = str(remote_file_path or "").strip()
    if not normalized_path:
        return {
            "ok": False,
            "error": "missing_file",
            "message": "Sin archivo asociado.",
        }

    config = build_default_crops_ssh_config(
        connect_timeout=4,
        command_timeout=8,
        max_retries=1,
        retry_delay=0,
        log_level=logging.CRITICAL,
    )
    manifest_path = get_default_crops_remote_manifest_path()
    client = RobustSSHClient(config, logger=CROPS_SSH_QUIET_LOGGER)
    last_error = ""

    for candidate_path in iter_remote_path_candidates(
        normalized_path,
        remote_manifest_path=manifest_path,
    ):
        try:
            result = client.read_remote_text_file(candidate_path, check=False, max_retries=1)
        except SSHError as exc:
            last_error = str(exc)
            continue

        if not result.success:
            last_error = result.stderr or f"No se pudo leer {candidate_path}."
            continue

        try:
            detail: object = json.loads(result.stdout)
        except json.JSONDecodeError:
            detail = {"contenido": result.stdout}

        return {
            "ok": True,
            "file": candidate_path,
            "detail": detail,
        }

    return {
        "ok": False,
        "error": "remote_file_not_found",
        "message": last_error or "No se pudo leer el archivo remoto.",
    }


def _read_remote_plate_crop_image(remote_image_path: str) -> tuple[bytes | None, str, str]:
    normalized_path = str(remote_image_path or "").strip()
    if not normalized_path:
        return None, "application/octet-stream", "Sin imagen asociada."

    config = build_default_crops_ssh_config(
        connect_timeout=4,
        command_timeout=10,
        max_retries=1,
        retry_delay=0,
        log_level=logging.CRITICAL,
    )
    manifest_path = get_default_crops_remote_manifest_path()
    client = RobustSSHClient(config, logger=CROPS_SSH_QUIET_LOGGER)
    last_error = ""

    for candidate_path in iter_remote_path_candidates(
        normalized_path,
        remote_manifest_path=manifest_path,
    ):
        try:
            result = client.run_command(
                f"base64 {shlex.quote(candidate_path)}",
                check=False,
                max_retries=1,
            )
        except SSHError as exc:
            last_error = str(exc)
            continue

        if not result.success or not result.stdout.strip():
            last_error = result.stderr or f"No se pudo leer {candidate_path}."
            continue

        try:
            image_bytes = base64.b64decode("".join(result.stdout.split()).encode("ascii"))
        except (ValueError, TypeError):
            last_error = "La imagen remota no se pudo decodificar."
            continue

        content_type = "image/jpeg"
        lower_path = candidate_path.casefold()
        if lower_path.endswith(".png"):
            content_type = "image/png"
        elif lower_path.endswith(".webp"):
            content_type = "image/webp"
        elif lower_path.endswith(".bmp"):
            content_type = "image/bmp"
        return image_bytes, content_type, ""

    return None, "application/octet-stream", last_error or "No se pudo leer la imagen remota."


async def handle_plate_file_detail(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError, TypeError):
        return _json_response({"error": "invalid_json"}, status=400)

    remote_file_path = str(payload.get("file") or "").strip() if isinstance(payload, dict) else ""
    if not remote_file_path:
        return _json_response(
            {
                "error": "missing_file",
                "message": "Sin archivo asociado.",
            },
            status=400,
        )

    result = await asyncio.to_thread(_read_remote_plate_file_detail, remote_file_path)
    if result.get("ok"):
        return _json_response(result)

    return _json_response(result, status=404)


async def handle_plate_crop_image(request: web.Request) -> web.Response:
    remote_image_path = request.query.get("path", "").strip()
    if not remote_image_path:
        return _json_response({"error": "missing_path"}, status=400)

    image_bytes, content_type, error_message = await asyncio.to_thread(
        _read_remote_plate_crop_image,
        remote_image_path,
    )
    if image_bytes is None:
        return _json_response(
            {
                "error": "remote_image_not_found",
                "message": error_message,
            },
            status=404,
        )

    return web.Response(
        body=image_bytes,
        content_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


async def handle_mapa(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    return _html_response("mapa.html", request=request)


async def handle_eventos(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    return _html_response("eventos.html", request=request)


async def handle_registro_vehiculos(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    return _html_response("registro_vehiculos.html", request=request)


async def handle_usuarios(request: web.Request) -> web.Response:
    _ensure_user_admin_page_access(request)
    APP_CONTEXT.ensure_initialized()
    return _html_response("usuarios.html", request=request, replacements=_build_user_admin_replacements(request))


async def handle_registros(request: web.Request) -> web.Response:
    _ensure_user_admin_page_access(request)
    APP_CONTEXT.ensure_initialized()
    return _html_response("registros.html", request=request, replacements=_build_user_admin_replacements(request))


async def handle_login(request: web.Request) -> web.Response:
    if _get_authenticated_user(request) is not None:
        raise web.HTTPFound("/")

    APP_CONTEXT.ensure_initialized()
    return _html_response("login.html")


async def handle_login_submit(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        try:
            payload = dict(await request.post())
        except Exception:
            return _json_response(
                {
                    "error": "invalid_login_payload",
                    "message": "No se pudieron leer las credenciales enviadas.",
                },
                status=400,
            )

    if not isinstance(payload, dict):
        return _json_response(
            {
                "error": "invalid_login_payload",
                "message": "El formato del login no es válido.",
            },
            status=400,
        )

    identity = payload.get("identity")
    password = payload.get("password")
    if not isinstance(identity, str) or not identity.strip() or not isinstance(password, str) or not password:
        return _json_response(
            {
                "error": "missing_credentials",
                "message": "Ingresa tu usuario y contraseña.",
            },
            status=400,
        )

    try:
        _ensure_database_ready()
        user = UserRepository().authenticate_user(identity, password)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo validar el login contra PostgreSQL: %s", exc)
        return _json_response(
            {
                "error": "database_unavailable",
                "message": "No se pudo conectar con la base de datos para validar el acceso.",
            },
            status=503,
        )

    if user is None:
        return _json_response(
            {
                "error": "invalid_credentials",
                "message": "Usuario o contraseña incorrectos.",
            },
            status=401,
        )

    normalized_user = _normalize_user_record(user)
    token_payload = _build_access_token_response(normalized_user)
    response = _json_response(
        {
            "ok": True,
            "redirect": "/",
            **token_payload,
        }
    )
    _set_auth_cookie(response, normalized_user)
    return response


async def handle_logout(_: web.Request) -> web.Response:
    response = _json_response({"ok": True, "redirect": "/login"})
    _clear_auth_cookie(response)
    return response


async def handle_auth_session(request: web.Request) -> web.Response:
    user = _get_authenticated_user(request)
    if user is None:
        return _json_response(
            {
                "error": "authentication_required",
                "message": "Debes iniciar sesión para continuar.",
            },
            status=401,
        )
    token_payload = _build_access_token_response(user)
    return _json_response(
        {
            "ok": True,
            "authenticated_via": "bearer" if _get_bearer_token(request) else "cookie",
            "session": {
                "expires_in": JWT_ACCESS_TOKEN_TTL_SEC,
            },
            **token_payload,
        }
    )


async def handle_devices(request: web.Request) -> web.Response:
    return _json_response(_filter_visible_device_dicts(request, APP_CONTEXT.device_catalog.as_dicts()))


async def handle_camera_authorized_viewer(request: web.Request) -> web.Response:
    camera_id_raw = _query_value(request, "camera_id")
    camera_name = _query_value(request, "camera_name")
    muted = _coerce_bool(request.query.get("muted"), default=True)
    controls = _coerce_bool(request.query.get("controls"), default=True)
    camera_id = 0
    if camera_id_raw is not None:
        try:
            camera_id = int(camera_id_raw)
        except (TypeError, ValueError):
            return _json_response({"error": "invalid_camera_id"}, status=400)

    device = _visible_device_by_camera_id_for_request(request, camera_id)
    if device is None and camera_name:
        visible_camera_names = _visible_camera_names_for_request(request)
        if camera_name not in visible_camera_names:
            return _json_response({"error": "camera_not_found"}, status=404)
        device = APP_CONTEXT.device_catalog.by_camera_name(camera_name)

    if device is None:
        if not camera_name and camera_id <= 0:
            return _json_response({"error": "invalid_camera_name"}, status=400)
        return _json_response({"error": "camera_not_found"}, status=404)

    if not (
        _is_likely_managed_viewer_source(getattr(device, "viewer_url", ""))
        or _is_likely_managed_viewer_source(getattr(device, "source", ""))
    ):
        return _json_response({"error": "camera_source_not_supported"}, status=400)

    resolved_camera_name = str(getattr(device, "camera_name", "") or camera_name or "").strip()
    try:
        payload = await asyncio.to_thread(
            _request_authorized_viewer_payload_for_camera,
            resolved_camera_name,
            muted=muted,
            controls=controls,
        )
    except StreamViewerError as exc:
        LOGGER.warning("No se pudo resolver viewer autorizado para %s: %s", resolved_camera_name, exc)
        return _json_response(
            {
                "error": "authorized_viewer_unavailable",
                "detail": str(exc),
            },
            status=502,
        )

    viewer_cookies = payload.pop("viewer_cookies", [])
    if payload.get("viewer_url"):
        payload["viewer_url"] = _rewrite_viewer_url_for_request_host(
            str(payload.get("viewer_url") or ""),
            request,
        )
    response = _json_response(payload)
    if isinstance(viewer_cookies, list):
        for cookie in viewer_cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            path = str(cookie.get("path") or "/").strip() or "/"
            if not name.startswith("stream_session_") or not value:
                continue
            response.set_cookie(
                name,
                value,
                httponly=True,
                max_age=3600,
                path=path,
                samesite="Lax",
            )
    return response


async def handle_camera_form_options(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        users = user_repo.get_user_all()
        organizations = organization_repo.list_organizations()
        vehicles = camera_repo.list_vehicles()
        stream_server = camera_repo.get_active_stream_server()
        if not _has_developer_access(request):
            users = _filter_manageable_users(request, users, roles)
            organizations = _filter_manageable_organizations(request, organizations, roles)
            vehicles = _filter_manageable_vehicles(request, vehicles, roles)
        payload = {
            "owners": [_serialize_user_record(user) for user in users],
            "organizations": [_serialize_organization_record(org) for org in organizations],
            "camera_types": [
                _serialize_camera_type_record(item)
                for item in camera_repo.list_camera_types()
            ],
            "protocols": [
                _serialize_protocol_record(item)
                for item in camera_repo.list_protocols()
            ],
            "vehicles": [_serialize_vehicle_record(item) for item in vehicles],
            "brand_presets": get_rtsp_brand_presets(),
            "stream_server": _serialize_stream_server_record(stream_server),
        }
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron cargar las opciones del CRUD de camaras: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response(payload)


async def handle_camera_rtsp_preview(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_camera_rtsp_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_camera_rtsp_payload"}, status=400)

    brand = str(payload.get("marca") or "").strip()
    normalized_brand = normalize_rtsp_brand(brand)
    ip = str(payload.get("ip") or "").strip()
    if not brand:
        return _json_response({"error": "invalid_camera_rtsp_brand"}, status=400)
    if not ip:
        return _json_response({"error": "invalid_camera_rtsp_ip"}, status=400)

    try:
        port = _parse_optional_int(payload, "puerto", minimum=1)
        channel = _parse_optional_int(payload, "canal", minimum=1)
    except ValueError as exc:
        return _json_response({"error": str(exc) or "invalid_camera_rtsp_payload"}, status=400)

    custom_path = str(payload.get("ruta_personalizada") or "").strip() or None
    if normalized_brand == "custom_path" and not custom_path:
        return _json_response({"error": "invalid_camera_rtsp_path"}, status=400)

    config = CameraRTSPConfig(
        marca=brand,
        ip=ip,
        usuario=str(payload.get("usuario") or "").strip(),
        password=str(payload.get("password") or "").strip(),
        puerto=port or 554,
        canal=channel or 1,
        substream=_coerce_bool(payload.get("substream"), default=False),
        ruta_personalizada=custom_path,
    )

    try:
        url = RTSPGenerator.generar(config)
    except RTSPGeneratorError as exc:
        return _json_response(
            {
                "error": "invalid_camera_rtsp_brand",
                "detail": str(exc),
            },
            status=400,
        )

    return _json_response(
        {
            "url": url,
            "brand": normalized_brand,
        }
    )


async def handle_cameras_registry(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        cameras = camera_repo.list_cameras()
        if not _has_developer_access(request):
            cameras = _filter_manageable_cameras(request, cameras, roles)
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron listar las camaras: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response([_serialize_camera_record(camera) for camera in cameras])


async def handle_camera_create(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_camera_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_camera_payload"}, status=400)

    current_user = _get_authenticated_user(request) or {}
    current_user_id = int(current_user.get("id") or 0)
    if current_user_id <= 0:
        return _json_response({"error": "authentication_required"}, status=401)

    try:
        latitude = _parse_optional_coordinate(payload, "latitud", minimum=-90.0, maximum=90.0)
        longitude = _parse_optional_coordinate(payload, "longitud", minimum=-180.0, maximum=180.0)
        vehicle_id = _parse_optional_int(payload, "vehiculo_id", minimum=1)
    except ValueError as exc:
        return _json_response({"error": str(exc) or "invalid_camera_payload"}, status=400)
    if (latitude is None) != (longitude is None):
        return _json_response({"error": "invalid_camera_location"}, status=400)

    organization_id = _safe_int(payload.get("organizacion_id"), default=0)
    owner_user_id = _safe_int(payload.get("propietario_usuario_id"), default=0)
    if organization_id <= 0:
        return _json_response({"error": "invalid_organization_id"}, status=400)
    if owner_user_id <= 0:
        return _json_response({"error": "invalid_owner_user_id"}, status=400)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        owner_user = user_repo.get_user_by_id(owner_user_id)
        organization = organization_repo.get_organization_by_id(organization_id)
        if owner_user is None:
            return _json_response({"error": "owner_user_not_found"}, status=404)
        if organization is None:
            return _json_response({"error": "organization_not_found"}, status=404)
        if not _has_developer_access(request):
            if not _filter_manageable_users(request, [owner_user], roles):
                return _camera_scope_forbidden_response()
            if not _filter_manageable_organizations(request, [organization], roles):
                return _organization_scope_forbidden_response()
            if vehicle_id is not None:
                vehicles = camera_repo.list_vehicles()
                manageable_vehicles = _filter_manageable_vehicles(request, vehicles, roles)
                if not any(_safe_int(vehicle.get("id")) == vehicle_id for vehicle in manageable_vehicles):
                    return _camera_scope_forbidden_response()

        camera = camera_repo.create_camera(
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            created_by_user_id=current_user_id,
            name=str(payload.get("nombre") or "").strip(),
            description=str(payload.get("descripcion") or "").strip() or None,
            camera_type=str(payload.get("tipo_camara_codigo") or payload.get("tipo_camara") or "").strip(),
            protocol=str(payload.get("protocolo_codigo") or payload.get("protocolo") or "").strip(),
            stream_url=str(payload.get("url_stream") or "").strip(),
            rtsp_url=str(payload.get("url_rtsp") or "").strip(),
            fixed_camera_ip=str(payload.get("ip_camaras_fijas") or "").strip() or None,
            unique_code=str(payload.get("codigo_unico") or "").strip() or None,
            brand=str(payload.get("marca") or "").strip() or None,
            model=str(payload.get("modelo") or "").strip() or None,
            serial_number=str(payload.get("numero_serie") or "").strip() or None,
            stream_username=str(payload.get("usuario_stream") or "").strip() or None,
            stream_password=str(payload.get("password_stream") or "").strip() or None,
            inference_enabled=_coerce_bool(payload.get("hacer_inferencia"), default=False),
            active=_coerce_bool(payload.get("activa"), default=True),
            latitude=latitude,
            longitude=longitude,
            altitude_m=_safe_float(payload.get("altitud_m")),
            address=str(payload.get("direccion") or "").strip() or None,
            reference=str(payload.get("referencia") or "").strip() or None,
            vehicle_id=vehicle_id,
            vehicle_position=str(payload.get("vehiculo_posicion") or "").strip() or None,
        )
        APP_CONTEXT.reload_runtime_state()
    except ValueError as exc:
        error_code = str(exc) or "camera_creation_failed"
        status = 409 if error_code in {"camera_already_exists", "camera_unique_code_already_exists"} else 400
        if error_code in {"owner_user_not_found", "organization_not_found", "vehicle_not_found"}:
            status = 404
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo crear la camara: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    APP_CONTEXT.event_store.record(
        "camera_registered",
        camera_name=str(camera.get("nombre") or "").strip(),
        device_id=str(camera.get("nombre") or "").strip(),
        source="camera_registry_db",
        payload=_serialize_camera_record(camera),
    )
    return _json_response({"camera": _serialize_camera_record(camera)}, status=201)


async def handle_camera_update(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    camera_id = _parse_camera_target_id(request)
    if camera_id is None or camera_id <= 0:
        return _json_response({"error": "invalid_camera_id"}, status=400)

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_camera_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_camera_payload"}, status=400)

    try:
        latitude = _parse_optional_coordinate(payload, "latitud", minimum=-90.0, maximum=90.0)
        longitude = _parse_optional_coordinate(payload, "longitud", minimum=-180.0, maximum=180.0)
        vehicle_id = _parse_optional_int(payload, "vehiculo_id", minimum=1)
    except ValueError as exc:
        return _json_response({"error": str(exc) or "invalid_camera_payload"}, status=400)
    if (latitude is None) != (longitude is None):
        return _json_response({"error": "invalid_camera_location"}, status=400)

    organization_id = _safe_int(payload.get("organizacion_id"), default=0)
    owner_user_id = _safe_int(payload.get("propietario_usuario_id"), default=0)
    if organization_id <= 0:
        return _json_response({"error": "invalid_organization_id"}, status=400)
    if owner_user_id <= 0:
        return _json_response({"error": "invalid_owner_user_id"}, status=400)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        existing = camera_repo.get_camera_by_id(camera_id)
        if existing is None:
            return _json_response({"error": "camera_not_found"}, status=404)
        owner_user = user_repo.get_user_by_id(owner_user_id)
        organization = organization_repo.get_organization_by_id(organization_id)
        if owner_user is None:
            return _json_response({"error": "owner_user_not_found"}, status=404)
        if organization is None:
            return _json_response({"error": "organization_not_found"}, status=404)
        if not _has_developer_access(request):
            if not _filter_manageable_cameras(request, [existing], roles):
                return _camera_scope_forbidden_response()
            if not _filter_manageable_users(request, [owner_user], roles):
                return _camera_scope_forbidden_response()
            if not _filter_manageable_organizations(request, [organization], roles):
                return _organization_scope_forbidden_response()
            if vehicle_id is not None:
                vehicles = camera_repo.list_vehicles()
                manageable_vehicles = _filter_manageable_vehicles(request, vehicles, roles)
                if not any(_safe_int(vehicle.get("id")) == vehicle_id for vehicle in manageable_vehicles):
                    return _camera_scope_forbidden_response()

        camera = camera_repo.update_camera(
            camera_id,
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            name=str(payload.get("nombre") or "").strip(),
            description=str(payload.get("descripcion") or "").strip() or None,
            camera_type=str(payload.get("tipo_camara_codigo") or payload.get("tipo_camara") or "").strip(),
            protocol=str(payload.get("protocolo_codigo") or payload.get("protocolo") or "").strip(),
            stream_url=str(payload.get("url_stream") or "").strip(),
            rtsp_url=str(payload.get("url_rtsp") or "").strip(),
            fixed_camera_ip=str(payload.get("ip_camaras_fijas") or "").strip() or None,
            unique_code=str(payload.get("codigo_unico") or "").strip() or None,
            brand=str(payload.get("marca") or "").strip() or None,
            model=str(payload.get("modelo") or "").strip() or None,
            serial_number=str(payload.get("numero_serie") or "").strip() or None,
            stream_username=str(payload.get("usuario_stream") or "").strip() or None,
            stream_password=payload.get("password_stream"),
            preserve_stream_password=not bool(str(payload.get("password_stream") or "").strip()),
            inference_enabled=_coerce_bool(payload.get("hacer_inferencia"), default=False),
            active=_coerce_bool(payload.get("activa"), default=True),
            latitude=latitude,
            longitude=longitude,
            altitude_m=_safe_float(payload.get("altitud_m")),
            address=str(payload.get("direccion") or "").strip() or None,
            reference=str(payload.get("referencia") or "").strip() or None,
            vehicle_id=vehicle_id,
            vehicle_position=str(payload.get("vehiculo_posicion") or "").strip() or None,
        )
        APP_CONTEXT.reload_runtime_state()
    except ValueError as exc:
        error_code = str(exc) or "camera_update_failed"
        if error_code in {"camera_already_exists", "camera_unique_code_already_exists"}:
            status = 409
        elif error_code in {"camera_not_found", "owner_user_not_found", "organization_not_found", "vehicle_not_found"}:
            status = 404
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo actualizar la camara %s: %s", camera_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"camera": _serialize_camera_record(camera)})


async def handle_camera_inference_update(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    camera_id = _parse_camera_target_id(request)
    if camera_id is None or camera_id <= 0:
        return _json_response({"error": "invalid_camera_id"}, status=400)

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_camera_payload"}, status=400)

    if not isinstance(payload, dict) or "hacer_inferencia" not in payload:
        return _json_response({"error": "invalid_camera_payload"}, status=400)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        existing = camera_repo.get_camera_by_id(camera_id)
        if existing is None:
            return _json_response({"error": "camera_not_found"}, status=404)

        if not _has_developer_access(request):
            if not _filter_manageable_cameras(request, [existing], roles):
                return _camera_scope_forbidden_response()

        camera = camera_repo.set_camera_inference_enabled(
            camera_id,
            inference_enabled=_coerce_bool(payload.get("hacer_inferencia"), default=False),
        )
        APP_CONTEXT.reload_runtime_state()
    except ValueError as exc:
        error_code = str(exc) or "camera_update_failed"
        status = 404 if error_code == "camera_not_found" else 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo actualizar la inferencia de la camara %s: %s", camera_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    APP_CONTEXT.event_store.record(
        "camera_inference_updated",
        camera_name=str(camera.get("nombre") or "").strip(),
        device_id=str(camera.get("nombre") or "").strip(),
        source="camera_registry_db",
        payload=_serialize_camera_record(camera),
    )
    return _json_response({"camera": _serialize_camera_record(camera)})


async def handle_camera_delete(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    camera_id = _parse_camera_target_id(request)
    if camera_id is None or camera_id <= 0:
        return _json_response({"error": "invalid_camera_id"}, status=400)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        existing = camera_repo.get_camera_by_id(camera_id)
        if existing is None:
            return _json_response({"error": "camera_not_found"}, status=404)
        if not _has_developer_access(request):
            if not _filter_manageable_cameras(request, [existing], roles):
                return _camera_scope_forbidden_response()

        deleted_camera = camera_repo.delete_camera(camera_id)
        APP_CONTEXT.reload_runtime_state()
    except ValueError as exc:
        error_code = str(exc) or "camera_delete_failed"
        if error_code == "camera_not_found":
            status = 404
        elif error_code == "camera_in_use":
            status = 409
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo eliminar la camara %s: %s", camera_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"ok": True, "camera": _serialize_camera_record(deleted_camera)})


async def handle_events(request: web.Request) -> web.Response:
    limit = _query_limit(request)
    event_type = _query_value(request, "event_type")
    camera_name = _query_value(request, "camera_name")
    device_id = _query_value(request, "device_id")

    events = APP_CONTEXT.event_store.list_events(
        limit=max(limit * 3, limit),
        event_type=event_type,
        camera_name=camera_name,
    )
    if not _has_developer_access(request):
        visible_camera_names = _visible_camera_names_for_request(request)
        events = [
            event
            for event in events
            if not str(event.get("camera_name") or "").strip()
            or str(event.get("camera_name") or "").strip() in visible_camera_names
        ]
    if device_id is not None:
        events = [event for event in events if event.get("device_id") == device_id]
    return _json_response(events[:limit])


async def handle_evidence(request: web.Request) -> web.Response:
    limit = _query_limit(request)
    camera_name = _query_value(request, "camera_name")
    kind = _query_value(request, "kind")
    device_id = _query_value(request, "device_id")

    evidence = APP_CONTEXT.evidence_store.list_evidence(
        limit=max(limit * 3, limit),
        camera_name=camera_name,
        kind=kind,
    )
    if not _has_developer_access(request):
        visible_camera_names = _visible_camera_names_for_request(request)
        evidence = [
            item
            for item in evidence
            if not str(item.get("camera_name") or "").strip()
            or str(item.get("camera_name") or "").strip() in visible_camera_names
        ]
    if device_id is not None:
        evidence = [item for item in evidence if item.get("device_id") == device_id]
    return _json_response(evidence[:limit])


async def handle_vehicle_form_options(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        vehicle_repo = VehicleRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        users = user_repo.get_user_all()
        organizations = organization_repo.list_organizations()
        cameras = [
            camera
            for camera in camera_repo.list_cameras()
            if str(camera.get("tipo_camara_codigo") or "").strip().lower() in {"vehicle", "drone"}
        ]
        if not _has_developer_access(request):
            users = _filter_manageable_users(request, users, roles)
            organizations = _filter_manageable_organizations(request, organizations, roles)
            cameras = _filter_manageable_cameras(request, cameras, roles)
        payload = {
            "owners": [_serialize_user_record(user) for user in users],
            "organizations": [_serialize_organization_record(org) for org in organizations],
            "vehicle_types": [
                _serialize_vehicle_type_record(item)
                for item in vehicle_repo.list_vehicle_types()
            ],
            "cameras": [_serialize_camera_record(camera) for camera in cameras],
            "api_defaults": {
                "default_drone_device_id": API_TELEMETRY_DEFAULT_DRONE_ID,
            },
        }
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron cargar las opciones del CRUD de vehiculos: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response(payload)


async def handle_vehicle_registry(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    limit = _query_limit(request, default=100)
    vehicle_type = _query_value(request, "vehicle_type")
    try:
        _ensure_database_ready()
        repo = VehicleRepository()
        roles = UserRepository().list_roles()
        vehicles = repo.list_vehicles()
        if not _has_developer_access(request):
            vehicles = _filter_manageable_vehicles(request, vehicles, roles)
        entries = [_serialize_vehicle_record(vehicle) for vehicle in vehicles]
        if vehicle_type:
            normalized_type = str(vehicle_type or "").strip().lower()
            entries = [
                entry
                for entry in entries
                if str(entry.get("vehicle_type") or "").strip().lower() == normalized_type
            ]
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron listar los vehiculos registrados: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)
    return _json_response(entries[:limit])


async def _read_vehicle_registry_payload(request: web.Request) -> tuple[dict[str, object] | None, web.Response | None]:
    try:
        payload = await request.json()
    except Exception:
        return None, _json_response({"error": "invalid_vehicle_payload"}, status=400)

    if not isinstance(payload, dict):
        return None, _json_response({"error": "invalid_vehicle_payload"}, status=400)

    vehicle_type_code = (
        str(payload.get("vehicle_type_code", "")).strip().lower()
        or str(payload.get("vehicle_type", "")).strip().lower()
    )
    label = str(payload.get("label", "")).strip()
    identifier = str(payload.get("identifier", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    telemetry_mode = str(payload.get("telemetry_mode", "manual")).strip().lower() or "manual"
    api_device_id = str(payload.get("api_device_id", "")).strip()
    camera_links = payload.get("camera_links")

    organization_id = _safe_int(payload.get("organizacion_id"), default=0)
    owner_user_id = _safe_int(payload.get("propietario_usuario_id"), default=0)

    if organization_id <= 0:
        return None, _json_response({"error": "invalid_organization_id"}, status=400)
    if owner_user_id <= 0:
        return None, _json_response({"error": "invalid_owner_user_id"}, status=400)
    if not vehicle_type_code:
        return None, _json_response({"error": "invalid_vehicle_type"}, status=400)
    if not label:
        return None, _json_response({"error": "invalid_vehicle_label"}, status=400)
    if not identifier:
        return None, _json_response({"error": "invalid_vehicle_identifier"}, status=400)

    is_drone_vehicle = vehicle_type_code in {"dron", "drone", "drone_robiotec"}
    if telemetry_mode == "api" and not api_device_id:
        api_device_id = API_TELEMETRY_DEFAULT_DRONE_ID if is_drone_vehicle else identifier
    if telemetry_mode != "api":
        api_device_id = ""

    return {
        "organization_id": organization_id,
        "owner_user_id": owner_user_id,
        "vehicle_type_code": vehicle_type_code,
        "label": label,
        "identifier": identifier,
        "notes": notes,
        "telemetry_mode": telemetry_mode,
        "api_base_url": "",
        "api_device_id": api_device_id,
        "active": _coerce_bool(payload.get("activo"), default=True),
        "camera_links": camera_links if isinstance(camera_links, list) else [],
    }, None


async def handle_vehicle_registry_create(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    payload, error_response = await _read_vehicle_registry_payload(request)
    if error_response is not None:
        return error_response

    current_user = _get_authenticated_user(request) or {}
    current_user_id = _safe_int(current_user.get("id"), default=0)
    if current_user_id <= 0:
        return _json_response({"error": "authentication_required"}, status=401)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        owner_user = user_repo.get_user_by_id(int(payload["owner_user_id"]))
        organization = organization_repo.get_organization_by_id(int(payload["organization_id"]))
        if owner_user is None:
            return _json_response({"error": "owner_user_not_found"}, status=404)
        if organization is None:
            return _json_response({"error": "organization_not_found"}, status=404)
        if not _has_developer_access(request):
            if not _filter_manageable_users(request, [owner_user], roles):
                return _role_scope_forbidden_response()
            if not _filter_manageable_organizations(request, [organization], roles):
                return _organization_scope_forbidden_response()
            manageable_cameras = _filter_manageable_cameras(request, camera_repo.list_cameras(), roles)
            manageable_camera_ids = {
                _safe_int(camera.get("id"), default=0)
                for camera in manageable_cameras
            }
            for camera_link in list(payload.get("camera_links") or []):
                camera_id = _safe_int(
                    camera_link.get("camera_id") or camera_link.get("camara_id"),
                    default=0,
                )
                if camera_id <= 0 or camera_id not in manageable_camera_ids:
                    return _vehicle_scope_forbidden_response()

        registered = APP_CONTEXT.register_vehicle(
            created_by_user_id=current_user_id,
            **payload,
        )
    except ValueError as exc:
        error_code = str(exc) or "vehicle_registration_failed"
        status = 409 if error_code == "vehicle_already_exists" else 400
        if error_code in {"owner_user_not_found", "organization_not_found", "camera_not_found"}:
            status = 404
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo crear el vehiculo: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response(registered, status=201)


async def handle_vehicle_registry_update(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    registration_id = str(request.match_info.get("registration_id", "") or "").strip()
    if not registration_id:
        return _json_response({"error": "vehicle_not_found"}, status=404)
    parsed_registration_id = _safe_int(registration_id, default=0)
    if parsed_registration_id <= 0:
        return _json_response({"error": "vehicle_not_found"}, status=404)

    payload, error_response = await _read_vehicle_registry_payload(request)
    if error_response is not None:
        return error_response

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        vehicle_repo = VehicleRepository()
        camera_repo = CameraRepository()
        roles = user_repo.list_roles()
        existing = vehicle_repo.get_vehicle_by_id(parsed_registration_id)
        if existing is None:
            return _json_response({"error": "vehicle_not_found"}, status=404)
        owner_user = user_repo.get_user_by_id(int(payload["owner_user_id"]))
        organization = organization_repo.get_organization_by_id(int(payload["organization_id"]))
        if owner_user is None:
            return _json_response({"error": "owner_user_not_found"}, status=404)
        if organization is None:
            return _json_response({"error": "organization_not_found"}, status=404)
        if not _has_developer_access(request):
            if not _filter_manageable_vehicles(request, [existing], roles):
                return _vehicle_scope_forbidden_response()
            if not _filter_manageable_users(request, [owner_user], roles):
                return _role_scope_forbidden_response()
            if not _filter_manageable_organizations(request, [organization], roles):
                return _organization_scope_forbidden_response()
            manageable_cameras = _filter_manageable_cameras(request, camera_repo.list_cameras(), roles)
            manageable_camera_ids = {
                _safe_int(camera.get("id"), default=0)
                for camera in manageable_cameras
            }
            for camera_link in list(payload.get("camera_links") or []):
                camera_id = _safe_int(
                    camera_link.get("camera_id") or camera_link.get("camara_id"),
                    default=0,
                )
                if camera_id <= 0 or camera_id not in manageable_camera_ids:
                    return _vehicle_scope_forbidden_response()

        registered = APP_CONTEXT.update_registered_vehicle(registration_id, **payload)
    except ValueError as exc:
        error_code = str(exc) or "vehicle_update_failed"
        if error_code == "vehicle_not_found":
            return _json_response({"error": error_code}, status=404)
        status = 409 if error_code == "vehicle_already_exists" else 400
        if error_code in {"owner_user_not_found", "organization_not_found", "camera_not_found"}:
            status = 404
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo actualizar el vehiculo %s: %s", registration_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response(registered)


async def handle_vehicle_registry_delete(request: web.Request) -> web.Response:
    APP_CONTEXT.ensure_initialized()
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    registration_id = str(request.match_info.get("registration_id", "") or "").strip()
    if not registration_id:
        return _json_response({"error": "vehicle_not_found"}, status=404)
    parsed_registration_id = _safe_int(registration_id, default=0)
    if parsed_registration_id <= 0:
        return _json_response({"error": "vehicle_not_found"}, status=404)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        vehicle_repo = VehicleRepository()
        roles = user_repo.list_roles()
        existing = vehicle_repo.get_vehicle_by_id(parsed_registration_id)
        if existing is None:
            return _json_response({"error": "vehicle_not_found"}, status=404)
        if not _has_developer_access(request):
            if not _filter_manageable_vehicles(request, [existing], roles):
                return _vehicle_scope_forbidden_response()
        deleted = APP_CONTEXT.delete_registered_vehicle(registration_id)
    except ValueError as exc:
        error_code = str(exc) or "vehicle_delete_failed"
        if error_code == "vehicle_not_found":
            status = 404
        elif error_code == "vehicle_in_use":
            status = 409
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo eliminar el vehiculo %s: %s", registration_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"ok": True, "vehicle": deleted})


async def handle_user_roles(request: web.Request) -> web.Response:
    forbidden = _developer_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        roles = UserRepository().list_roles()
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron listar los roles: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response([_serialize_role_record(role) for role in roles])


async def handle_user_role_options(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        repo = UserRepository()
        roles = _filter_manageable_roles(request, repo.list_roles())
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron listar las opciones de roles: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response([_serialize_role_record(role) for role in roles])


async def handle_role_create(request: web.Request) -> web.Response:
    forbidden = _developer_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_role_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_role_payload"}, status=400)

    code = str(payload.get("codigo", "")).strip()
    name = str(payload.get("nombre", "")).strip()
    level = payload.get("nivel_orden")
    is_system = _coerce_bool(payload.get("es_sistema"), default=True)

    if not code:
        return _json_response({"error": "invalid_role_code"}, status=400)
    if not name:
        return _json_response({"error": "invalid_role_name"}, status=400)
    if level in (None, ""):
        return _json_response({"error": "invalid_role_level"}, status=400)

    try:
        _ensure_database_ready()
        role = UserRepository().create_role(
            code=code,
            name=name,
            level=level,
            is_system=is_system,
        )
    except ValueError as exc:
        error_code = str(exc) or "role_creation_failed"
        status = 409 if error_code == "role_already_exists" else 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo crear el rol: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"role": _serialize_role_record(role)}, status=201)


async def handle_role_update(request: web.Request) -> web.Response:
    forbidden = _developer_api_guard(request)
    if forbidden is not None:
        return forbidden

    role_id = _parse_role_target_id(request)
    if role_id is None or role_id <= 0:
        return _json_response({"error": "invalid_role_id"}, status=400)

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_role_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_role_payload"}, status=400)

    code = str(payload.get("codigo", "")).strip()
    name = str(payload.get("nombre", "")).strip()
    level = payload.get("nivel_orden")
    is_system = _coerce_bool(payload.get("es_sistema"), default=True)

    if not code:
        return _json_response({"error": "invalid_role_code"}, status=400)
    if not name:
        return _json_response({"error": "invalid_role_name"}, status=400)
    if level in (None, ""):
        return _json_response({"error": "invalid_role_level"}, status=400)

    try:
        _ensure_database_ready()
        role = UserRepository().update_role(
            role_id,
            code=code,
            name=name,
            level=level,
            is_system=is_system,
        )
    except ValueError as exc:
        error_code = str(exc) or "role_update_failed"
        if error_code == "role_already_exists":
            status = 409
        elif error_code == "role_not_found":
            status = 404
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo actualizar el rol %s: %s", role_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"role": _serialize_role_record(role)})


async def handle_role_delete(request: web.Request) -> web.Response:
    forbidden = _developer_api_guard(request)
    if forbidden is not None:
        return forbidden

    role_id = _parse_role_target_id(request)
    if role_id is None or role_id <= 0:
        return _json_response({"error": "invalid_role_id"}, status=400)

    try:
        _ensure_database_ready()
        deleted_role = UserRepository().delete_role(role_id)
    except ValueError as exc:
        error_code = str(exc) or "role_delete_failed"
        if error_code == "role_not_found":
            status = 404
        elif error_code == "role_in_use":
            status = 409
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo eliminar el rol %s: %s", role_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"ok": True, "role": _serialize_role_record(deleted_role)})


async def handle_users(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        repo = UserRepository()
        users = repo.get_user_all()
        if not _has_developer_access(request):
            users = _filter_manageable_users(request, users, repo.list_roles())
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron listar los usuarios: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response([_serialize_user_record(user) for user in users])


async def handle_user_create(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_user_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_user_payload"}, status=400)

    username = str(payload.get("usuario", "")).strip()
    email = str(payload.get("email", "")).strip()
    name = str(payload.get("nombre", "")).strip()
    last_name = str(payload.get("apellido", "")).strip() or None
    phone = str(payload.get("telefono", "")).strip() or None
    role = str(payload.get("rol", "")).strip()
    active = _coerce_bool(payload.get("activo"), default=True)
    password = payload.get("password")
    if not username:
        return _json_response({"error": "invalid_username"}, status=400)
    if not email:
        return _json_response({"error": "invalid_email"}, status=400)
    if not name:
        return _json_response({"error": "invalid_name"}, status=400)
    if not role:
        return _json_response({"error": "invalid_role"}, status=400)
    if not isinstance(password, str) or not password.strip():
        return _json_response({"error": "invalid_password"}, status=400)

    current_user = _get_authenticated_user(request) or {}
    current_user_id = int(current_user.get("id") or 0) or None
    try:
        _ensure_database_ready()
        repo = UserRepository()
        if not _has_developer_access(request):
            role_catalog = repo.list_roles()
            allowed_roles = _filter_manageable_roles(request, role_catalog)
            selected_role = _find_role_record(allowed_roles, role)
            if selected_role is None:
                return _role_scope_forbidden_response()

        user = repo.create_user(
            username=username,
            email=email,
            password=password,
            name=name,
            role=role,
            last_name=last_name,
            phone=phone,
            active=active,
            created_by_user_id=current_user_id,
            parent_user_id=current_user_id,
        )
    except ValueError as exc:
        error_code = str(exc) or "user_creation_failed"
        status = 409 if error_code in {"user_already_exists", "email_already_exists"} else 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo crear el usuario: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"user": _serialize_user_record(user)}, status=201)


async def handle_user_update(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    user_id = _parse_user_target_id(request)
    if user_id is None or user_id <= 0:
        return _json_response({"error": "invalid_user_id"}, status=400)

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_user_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_user_payload"}, status=400)

    username = str(payload.get("usuario", "")).strip()
    email = str(payload.get("email", "")).strip()
    name = str(payload.get("nombre", "")).strip()
    last_name = str(payload.get("apellido", "")).strip() or None
    phone = str(payload.get("telefono", "")).strip() or None
    role = str(payload.get("rol", "")).strip()
    active = _coerce_bool(payload.get("activo"), default=True)
    raw_password = payload.get("password")
    if raw_password is not None and not isinstance(raw_password, str):
        return _json_response({"error": "invalid_password"}, status=400)
    if not username:
        return _json_response({"error": "invalid_username"}, status=400)
    if not email:
        return _json_response({"error": "invalid_email"}, status=400)
    if not name:
        return _json_response({"error": "invalid_name"}, status=400)
    if not role:
        return _json_response({"error": "invalid_role"}, status=400)

    current_user = _get_authenticated_user(request) or {}
    current_user_id = int(current_user.get("id") or 0)
    current_user_role = _normalize_role_name(current_user.get("rol"))
    if current_user_id == user_id and current_user_role and _normalize_role_name(role) != current_user_role:
        return _json_response({"error": "cannot_change_current_user_role"}, status=400)

    try:
        _ensure_database_ready()
        repo = UserRepository()
        if not _has_developer_access(request):
            role_catalog = repo.list_roles()
            allowed_roles = _filter_manageable_roles(request, role_catalog)
            target_user = repo.get_user_by_id(user_id)
            if target_user is None:
                return _json_response({"error": "user_not_found"}, status=404)
            manageable_targets = _filter_manageable_users(request, [target_user], role_catalog)
            if not manageable_targets:
                return _role_scope_forbidden_response()
            selected_role = _find_role_record(allowed_roles, role)
            if selected_role is None:
                return _role_scope_forbidden_response()

        user = repo.update_user(
            user_id,
            username=username,
            email=email,
            name=name,
            password=raw_password,
            role=role,
            last_name=last_name,
            phone=phone,
            active=active,
        )
    except ValueError as exc:
        error_code = str(exc) or "user_update_failed"
        if error_code in {"user_already_exists", "email_already_exists"}:
            status = 409
        elif error_code == "user_not_found":
            status = 404
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo actualizar el usuario %s: %s", user_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"user": _serialize_user_record(user)})


async def handle_user_delete(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    user_id = _parse_user_target_id(request)
    if user_id is None or user_id <= 0:
        return _json_response({"error": "invalid_user_id"}, status=400)

    current_user = _get_authenticated_user(request) or {}
    current_user_id = int(current_user.get("id") or 0)
    if current_user_id == user_id:
        return _json_response({"error": "cannot_delete_current_user"}, status=400)

    try:
        _ensure_database_ready()
        repo = UserRepository()
        if not _has_developer_access(request):
            target_user = repo.get_user_by_id(user_id)
            if target_user is None:
                return _json_response({"error": "user_not_found"}, status=404)
            manageable_targets = _filter_manageable_users(request, [target_user], repo.list_roles())
            if not manageable_targets:
                return _role_scope_forbidden_response()

        deleted_user = repo.delete_user(user_id)
    except ValueError as exc:
        error_code = str(exc) or "user_delete_failed"
        status = 404 if error_code == "user_not_found" else 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo eliminar el usuario %s: %s", user_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"ok": True, "user": _serialize_user_record(deleted_user)})


async def handle_organizations(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        organizations = organization_repo.list_organizations()
        if not _has_developer_access(request):
            organizations = _filter_manageable_organizations(
                request,
                organizations,
                user_repo.list_roles(),
            )
    except DatabaseError as exc:
        LOGGER.exception("No se pudieron listar las organizaciones: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response([_serialize_organization_record(org) for org in organizations])


async def handle_organization_create(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_organization_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_organization_payload"}, status=400)

    name = str(payload.get("nombre", "")).strip()
    description = str(payload.get("descripcion", "")).strip() or None
    owner_user_id = payload.get("propietario_usuario_id")
    parsed_owner_user_id = _safe_int(owner_user_id, default=0)
    active = _coerce_bool(payload.get("activa"), default=True)
    if not name:
        return _json_response({"error": "invalid_organization_name"}, status=400)
    if parsed_owner_user_id <= 0:
        return _json_response({"error": "invalid_owner_user_id"}, status=400)

    current_user = _get_authenticated_user(request) or {}
    current_user_id = int(current_user.get("id") or 0)
    if current_user_id <= 0:
        return _json_response({"error": "authentication_required"}, status=401)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        role_catalog = user_repo.list_roles()
        owner_user = user_repo.get_user_by_id(parsed_owner_user_id)
        if owner_user is None:
            return _json_response({"error": "owner_user_not_found"}, status=404)
        if not _has_developer_access(request):
            manageable_owner = _filter_manageable_users(request, [owner_user], role_catalog)
            if not manageable_owner:
                return _organization_scope_forbidden_response()

        organization = OrganizationRepository().create_organization(
            name=name,
            description=description,
            owner_user_id=parsed_owner_user_id,
            created_by_user_id=current_user_id,
            active=active,
        )
    except ValueError as exc:
        error_code = str(exc) or "organization_creation_failed"
        status = 409 if error_code == "organization_already_exists" else 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo crear la organizacion: %s", exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"organization": _serialize_organization_record(organization)}, status=201)


async def handle_organization_update(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    organization_id = _parse_organization_target_id(request)
    if organization_id is None or organization_id <= 0:
        return _json_response({"error": "invalid_organization_id"}, status=400)

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_organization_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_organization_payload"}, status=400)

    name = str(payload.get("nombre", "")).strip()
    description = str(payload.get("descripcion", "")).strip() or None
    owner_user_id = payload.get("propietario_usuario_id")
    parsed_owner_user_id = _safe_int(owner_user_id, default=0)
    active = _coerce_bool(payload.get("activa"), default=True)
    if not name:
        return _json_response({"error": "invalid_organization_name"}, status=400)
    if parsed_owner_user_id <= 0:
        return _json_response({"error": "invalid_owner_user_id"}, status=400)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        role_catalog = user_repo.list_roles()
        organization_repo = OrganizationRepository()
        existing = organization_repo.get_organization_by_id(organization_id)
        if existing is None:
            return _json_response({"error": "organization_not_found"}, status=404)
        if not _has_developer_access(request):
            manageable_target = _filter_manageable_organizations(request, [existing], role_catalog)
            if not manageable_target:
                return _organization_scope_forbidden_response()

        owner_user = user_repo.get_user_by_id(parsed_owner_user_id)
        if owner_user is None:
            return _json_response({"error": "owner_user_not_found"}, status=404)
        if not _has_developer_access(request):
            manageable_owner = _filter_manageable_users(request, [owner_user], role_catalog)
            if not manageable_owner:
                return _organization_scope_forbidden_response()

        organization = organization_repo.update_organization(
            organization_id,
            name=name,
            description=description,
            owner_user_id=parsed_owner_user_id,
            active=active,
        )
    except ValueError as exc:
        error_code = str(exc) or "organization_update_failed"
        if error_code == "organization_already_exists":
            status = 409
        elif error_code == "organization_not_found":
            status = 404
        else:
            status = 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo actualizar la organizacion %s: %s", organization_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"organization": _serialize_organization_record(organization)})


async def handle_organization_delete(request: web.Request) -> web.Response:
    forbidden = _user_admin_api_guard(request)
    if forbidden is not None:
        return forbidden

    organization_id = _parse_organization_target_id(request)
    if organization_id is None or organization_id <= 0:
        return _json_response({"error": "invalid_organization_id"}, status=400)

    try:
        _ensure_database_ready()
        user_repo = UserRepository()
        organization_repo = OrganizationRepository()
        existing = organization_repo.get_organization_by_id(organization_id)
        if existing is None:
            return _json_response({"error": "organization_not_found"}, status=404)
        if not _has_developer_access(request):
            manageable_target = _filter_manageable_organizations(
                request,
                [existing],
                user_repo.list_roles(),
            )
            if not manageable_target:
                return _organization_scope_forbidden_response()

        deleted_organization = organization_repo.delete_organization(organization_id)
    except ValueError as exc:
        error_code = str(exc) or "organization_delete_failed"
        status = 404 if error_code == "organization_not_found" else 400
        return _json_response({"error": error_code}, status=status)
    except DatabaseError as exc:
        LOGGER.exception("No se pudo eliminar la organizacion %s: %s", organization_id, exc)
        return _json_response({"error": "database_unavailable"}, status=503)

    return _json_response({"ok": True, "organization": _serialize_organization_record(deleted_organization)})


async def handle_telemetry(request: web.Request) -> web.Response:
    snapshot = APP_CONTEXT.telemetry_service.list_snapshot(APP_CONTEXT.device_catalog)
    filtered_snapshot: list[dict[str, object]] = []
    for item in snapshot:
        device_id = str(item.get("device_id") or "").strip()
        camera_name = str(item.get("camera_name") or "").strip()
        device = APP_CONTEXT.device_catalog.get(device_id) or APP_CONTEXT.device_catalog.by_camera_name(camera_name)
        if device is not None and not _device_visible_for_request(request, device):
            continue
        if device is None and not _device_visible_for_request(request, item):
            continue
        filtered_snapshot.append(item)
    return _json_response(filtered_snapshot)


def _request_query_float(request: web.Request, name: str) -> float:
    raw = str(request.query.get(name, "")).strip()
    if not raw:
        raise ValueError(f"missing_{name}")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"invalid_{name}") from exc


async def handle_arcom_concession_lookup(request: web.Request) -> web.Response:
    if not ARCOM_ENABLED:
        return _json_response(
            {
                "ok": True,
                "found": False,
                "concession": None,
                "disabled": True,
            }
        )

    try:
        lat = _request_query_float(request, "lat")
        lon = _request_query_float(request, "lon")
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)

    if lat < -90 or lat > 90 or lon < -180 or lon > 180:
        return _json_response({"error": "invalid_coordinates"}, status=400)

    try:
        concession = await asyncio.to_thread(
            ARCOM_CONCESSION_STORE.get_concession_for_point,
            lat=lat,
            lon=lon,
        )
    except ArcomLookupError as exc:
        LOGGER.warning("Consulta local ARCOM no disponible: %s", exc)
        return _json_response({"error": "arcom_unavailable", "detail": str(exc)}, status=503)

    return _json_response(
        {
            "ok": True,
            "found": concession is not None,
            "concession": concession,
        }
    )


async def handle_arcom_concessions_bbox(request: web.Request) -> web.Response:
    if not ARCOM_ENABLED:
        return _json_response(
            {
                "type": "FeatureCollection",
                "features": [],
                "meta": {
                    "disabled": True,
                },
            }
        )

    raw_bbox = str(request.query.get("bbox", "")).strip()
    if not raw_bbox:
        return _json_response({"error": "missing_bbox"}, status=400)

    parts = [part.strip() for part in raw_bbox.split(",")]
    if len(parts) != 4:
        return _json_response({"error": "invalid_bbox"}, status=400)

    try:
        min_lon, min_lat, max_lon, max_lat = [float(part) for part in parts]
    except ValueError:
        return _json_response({"error": "invalid_bbox"}, status=400)

    if min_lon > max_lon or min_lat > max_lat:
        return _json_response({"error": "invalid_bbox"}, status=400)

    try:
        requested_limit = int(str(request.query.get("limit", ARCOM_MAX_FEATURES_PER_REQUEST)).strip() or ARCOM_MAX_FEATURES_PER_REQUEST)
    except ValueError:
        requested_limit = ARCOM_MAX_FEATURES_PER_REQUEST

    try:
        feature_collection = await asyncio.to_thread(
            ARCOM_CONCESSION_STORE.get_concessions_for_bbox,
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            limit=min(requested_limit, ARCOM_MAX_FEATURES_PER_REQUEST),
        )
    except ArcomLookupError as exc:
        LOGGER.warning("Consulta bbox ARCOM no disponible: %s", exc)
        return _json_response({"error": "arcom_unavailable", "detail": str(exc)}, status=503)

    return _json_response(feature_collection)


async def handle_telemetry_update(request: web.Request) -> web.Response:
    device_id = request.match_info.get("device_id", "").strip()
    device = APP_CONTEXT.device_catalog.get(device_id)
    device_meta = APP_CONTEXT.telemetry_service.get_device_metadata(device_id)
    if device is None and device_meta is None:
        return _json_response({"error": "device_not_found"}, status=404)

    try:
        payload = await request.json()
    except Exception:
        return _json_response({"error": "invalid_telemetry_payload"}, status=400)

    if not isinstance(payload, dict):
        return _json_response({"error": "invalid_telemetry_payload"}, status=400)

    try:
        lat = float(payload["lat"])
        lon = float(payload["lon"])
    except (KeyError, TypeError, ValueError):
        return _json_response({"error": "invalid_coordinates"}, status=400)

    base_keys = {
        "lat",
        "lon",
        "altitude",
        "speed",
        "heading",
        "device_status",
        "source_ts",
    }
    extra = {key: value for key, value in payload.items() if key not in base_keys}

    point = APP_CONTEXT.telemetry_service.update(
        device_id,
        lat=lat,
        lon=lon,
        altitude=_safe_float(payload.get("altitude")),
        speed=_safe_float(payload.get("speed")),
        heading=_safe_float(payload.get("heading")),
        device_status=str(payload.get("device_status", "online")),
        source_ts=_safe_float(payload.get("source_ts")),
        extra=extra,
    )
    serialized = point.to_dict(
        APP_CONTEXT.telemetry_service.stale_after_sec,
        APP_CONTEXT.telemetry_service.lost_after_sec,
    )
    if device is not None:
        serialized["camera_name"] = device.camera_name
        serialized["display_name"] = device.camera_name
        serialized["device_kind"] = "camera"
        serialized["capabilities"] = device.capabilities
    else:
        serialized["camera_name"] = str((device_meta or {}).get("camera_name", device_id))
        serialized["display_name"] = str((device_meta or {}).get("display_name", device_id))
        serialized["device_kind"] = str((device_meta or {}).get("device_kind", "vehicle"))
        serialized["vehicle_type"] = str((device_meta or {}).get("vehicle_type", "")).strip()
        serialized["notes"] = str((device_meta or {}).get("notes", "")).strip()
        serialized["capabilities"] = (device_meta or {}).get("capabilities", {"telemetry": True})

    APP_CONTEXT.event_store.record(
        "telemetry_received",
        camera_name=serialized.get("camera_name", ""),
        device_id=device_id,
        source="telemetry_api",
        payload=serialized,
    )
    return _json_response(serialized)


async def on_shutdown(_: web.Application) -> None:
    APP_CONTEXT.api_bridge_manager.stop()
    db.close()


async def on_startup(app: web.Application) -> None:
    app["db_ready"] = True
    try:
        _ensure_database_ready()
        APP_CONTEXT.reload_runtime_state()
    except DatabaseError as exc:
        app["db_ready"] = False
        app["db_error"] = str(exc)
        LOGGER.exception("No se pudo inicializar el pool PostgreSQL al iniciar la web: %s", exc)


def create_app() -> web.Application:
    APP_CONTEXT.ensure_initialized()
    app = web.Application(middlewares=[auth_middleware])
    app.add_routes(
        [
            web.get("/", handle_index),
            web.get("/perfil", handle_perfil),
            web.get("/camaras", handle_camaras),
            web.get("/mapa", handle_mapa),
            web.get("/eventos", handle_eventos),
            web.get("/registro-vehiculos", handle_registro_vehiculos),
            web.get("/usuarios", handle_usuarios),
            web.get("/registros", handle_registros),
            web.get("/login", handle_login),
            web.post("/api/login", handle_login_submit),
            web.post("/api/logout", handle_logout),
            web.get("/api/auth/session", handle_auth_session),
            web.get("/api/devices", handle_devices),
            web.get("/api/camera-viewer-url", handle_camera_authorized_viewer),
            web.post("/api/plate-file-detail", handle_plate_file_detail),
            web.get("/api/plate-crop-image", handle_plate_crop_image),
            web.get("/api/cameras", handle_cameras_registry),
            web.post("/api/cameras", handle_camera_create),
            web.put("/api/cameras/{camera_id}", handle_camera_update),
            web.patch("/api/cameras/{camera_id}/inference", handle_camera_inference_update),
            web.delete("/api/cameras/{camera_id}", handle_camera_delete),
            web.get("/api/camera-form-options", handle_camera_form_options),
            web.post("/api/camera-rtsp-preview", handle_camera_rtsp_preview),
            web.get("/api/events", handle_events),
            web.get("/api/evidence", handle_evidence),
            web.get("/api/vehicle-form-options", handle_vehicle_form_options),
            web.get("/api/vehicle-registry", handle_vehicle_registry),
            web.post("/api/vehicle-registry", handle_vehicle_registry_create),
            web.put("/api/vehicle-registry/{registration_id}", handle_vehicle_registry_update),
            web.delete("/api/vehicle-registry/{registration_id}", handle_vehicle_registry_delete),
            web.get("/api/user-roles", handle_user_roles),
            web.get("/api/user-role-options", handle_user_role_options),
            web.post("/api/user-roles", handle_role_create),
            web.put("/api/user-roles/{role_id}", handle_role_update),
            web.delete("/api/user-roles/{role_id}", handle_role_delete),
            web.get("/api/users", handle_users),
            web.post("/api/users", handle_user_create),
            web.put("/api/users/{user_id}", handle_user_update),
            web.delete("/api/users/{user_id}", handle_user_delete),
            web.get("/api/organizations", handle_organizations),
            web.post("/api/organizations", handle_organization_create),
            web.put("/api/organizations/{organization_id}", handle_organization_update),
            web.delete("/api/organizations/{organization_id}", handle_organization_delete),
            web.get("/api/arcom/concession-lookup", handle_arcom_concession_lookup),
            web.get("/api/arcom/concessions", handle_arcom_concessions_bbox),
            web.get("/api/telemetry", handle_telemetry),
            web.post("/api/telemetry/{device_id}", handle_telemetry_update),
            web.static("/static", STATIC_DIR),
            web.static("/icons", ICONS_DIR),
            web.static("/assets", ASSETS_DIR),
        ]
    )
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


def _find_available_port(host: str, preferred_port: int, max_attempts: int = 20) -> int:
    bind_host = "0.0.0.0" if host == "0.0.0.0" else host
    for port in range(preferred_port, preferred_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((bind_host, port))
                return port
            except OSError:
                continue
    raise OSError(
        errno.EADDRINUSE,
        f"No hay puertos libres entre {preferred_port} y {preferred_port + max_attempts - 1}",
    )


def main() -> None:
    APP_CONTEXT.ensure_initialized()
    settings = _get_web_settings()

    host = settings.host
    port = settings.port
    try:
        bind_port = _find_available_port(host, port)
    except OSError:
        bind_port = port

    visible_host = "127.0.0.1" if host == "0.0.0.0" else host
    if bind_port != port:
        print(f"Puerto {port} ocupado. Usando puerto alterno {bind_port}.")
    print(f"Visor web disponible en http://{visible_host}:{bind_port}")
    if host == "0.0.0.0":
        print("Acceso en red local habilitado: usa la IP local del equipo desde el celular.")
    web.run_app(create_app(), host=host, port=bind_port, access_log=None)


if __name__ == "__main__":
    main()
