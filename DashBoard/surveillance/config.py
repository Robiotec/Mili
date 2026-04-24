from __future__ import annotations

import json
import os
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
SUPPORTED_CAMERA_SOURCE_SCHEMES = ("rtsp://", "rtmp://", "http://", "https://", "udp://", "srt://")
SUPPORTED_VIEWER_SOURCE_SCHEMES = ("http://", "https://")
UNSUPPORTED_SIGNALING_SOURCE_SCHEMES = ("webrtc://", "whip://", "whep://")
NETWORK_PATH_SCHEMES = SUPPORTED_CAMERA_SOURCE_SCHEMES
CAMERA_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
TOP_LEVEL_YAML_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*:")
EMBEDDED_M3U8_PATTERN = re.compile(r"""['"](?P<path>[^'"]+\.m3u8(?:\?[^'"]*)?)['"]""", re.IGNORECASE)
HTTP_SOURCE_SNIFF_TIMEOUT_SEC = 4.0
HTTP_SOURCE_SNIFF_BYTES = 65536
MEDIAMTX_WEBRTC_PORT = os.getenv("MEDIAMTX_WEBRTC_PORT", "8989")
MEDIAMTX_RTSP_PORT = os.getenv("MEDIAMTX_RTSP_PORT", "8654")


def read_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"El archivo de configuracion debe ser un objeto YAML: {path}")
    return data


def is_valid_camera_name(camera_name: str) -> bool:
    return bool(CAMERA_NAME_PATTERN.fullmatch(camera_name.strip()))


def _find_top_level_section_bounds(
    lines: list[str],
    *,
    section_name: str,
) -> tuple[int | None, int]:
    section_header_pattern = re.compile(
        rf"^{re.escape(section_name)}:\s*(?:#.*)?$"
    )
    section_start_idx: int | None = None
    section_end_idx = len(lines)

    for idx, raw_line in enumerate(lines):
        if section_header_pattern.match(raw_line.rstrip("\r\n")):
            section_start_idx = idx
            for probe_idx in range(idx + 1, len(lines)):
                probe_line = lines[probe_idx]
                probe_stripped = probe_line.strip()
                if not probe_stripped:
                    continue
                if probe_line[:1].isspace():
                    continue
                if probe_line.lstrip().startswith("#"):
                    continue
                if TOP_LEVEL_YAML_KEY_PATTERN.match(probe_line):
                    section_end_idx = probe_idx
                    break
            break

    return section_start_idx, section_end_idx


def _section_insert_idx(lines: list[str], start_idx: int, end_idx: int) -> int:
    insert_idx = end_idx
    while insert_idx > start_idx + 1 and not lines[insert_idx - 1].strip():
        insert_idx -= 1
    return insert_idx


def _append_mapping_entry_to_section_text(
    yaml_text: str,
    *,
    section_name: str,
    key: str,
    value: str,
) -> str:
    lines = yaml_text.splitlines(keepends=True)
    section_start_idx, section_end_idx = _find_top_level_section_bounds(
        lines,
        section_name=section_name,
    )

    entry_line = f"  {key}: {json.dumps(value, ensure_ascii=False)}\n"
    if section_start_idx is None:
        base = yaml_text.rstrip()
        if base:
            return f"{base}\n\n{section_name}:\n{entry_line}"
        return f"{section_name}:\n{entry_line}"

    existing_entry_pattern = re.compile(rf"^\s{{2}}{re.escape(key)}\s*:")
    for idx in range(section_start_idx + 1, section_end_idx):
        if existing_entry_pattern.match(lines[idx]):
            raise ValueError("camera_already_exists")

    insert_idx = _section_insert_idx(lines, section_start_idx, section_end_idx)
    lines.insert(insert_idx, entry_line)
    return "".join(lines)


def _append_nested_mapping_entry_to_section_text(
    yaml_text: str,
    *,
    section_name: str,
    nested_section_name: str,
    key: str,
    values: dict[str, float],
) -> str:
    lines = yaml_text.splitlines(keepends=True)
    section_start_idx, section_end_idx = _find_top_level_section_bounds(
        lines,
        section_name=section_name,
    )

    nested_block_lines = [f"    {key}:\n"]
    nested_block_lines.extend(
        f"      {subkey}: {json.dumps(subvalue, ensure_ascii=False)}\n"
        for subkey, subvalue in values.items()
    )

    if section_start_idx is None:
        base = yaml_text.rstrip()
        block = "".join(
            [
                f"{section_name}:\n",
                f"  {nested_section_name}:\n",
                *nested_block_lines,
            ]
        )
        if base:
            return f"{base}\n\n{block}"
        return block

    nested_section_pattern = re.compile(
        rf"^(\s{{2}}{re.escape(nested_section_name)}:)\s*(.*)$"
    )
    existing_entry_pattern = re.compile(rf"^\s{{4}}{re.escape(key)}\s*:")
    nested_section_idx: int | None = None
    nested_section_end_idx = section_end_idx

    for idx in range(section_start_idx + 1, section_end_idx):
        raw_line = lines[idx]
        match = nested_section_pattern.match(raw_line.rstrip("\r\n"))
        if not match:
            continue
        nested_section_idx = idx
        nested_section_end_idx = section_end_idx
        for probe_idx in range(idx + 1, section_end_idx):
            probe_line = lines[probe_idx]
            probe_stripped = probe_line.strip()
            if not probe_stripped:
                continue
            if probe_line.lstrip().startswith("#"):
                continue
            indent = len(probe_line) - len(probe_line.lstrip(" "))
            if indent <= 2:
                nested_section_end_idx = probe_idx
                break
        inline_value = match.group(2).strip()
        if inline_value == "{}":
            lines[idx] = f"  {nested_section_name}:\n"
            nested_section_end_idx = idx + 1
        break

    if nested_section_idx is None:
        insert_idx = _section_insert_idx(lines, section_start_idx, section_end_idx)
        lines[insert_idx:insert_idx] = [
            f"  {nested_section_name}:\n",
            *nested_block_lines,
        ]
        return "".join(lines)

    for idx in range(nested_section_idx + 1, nested_section_end_idx):
        if existing_entry_pattern.match(lines[idx]):
            raise ValueError("camera_already_exists")

    insert_idx = nested_section_end_idx
    while insert_idx > nested_section_idx + 1 and not lines[insert_idx - 1].strip():
        insert_idx -= 1

    lines[insert_idx:insert_idx] = nested_block_lines
    return "".join(lines)


def _append_nested_scalar_entry_to_section_text(
    yaml_text: str,
    *,
    section_name: str,
    nested_section_name: str,
    key: str,
    value: str,
) -> str:
    lines = yaml_text.splitlines(keepends=True)
    section_start_idx, section_end_idx = _find_top_level_section_bounds(
        lines,
        section_name=section_name,
    )

    nested_entry_line = f"    {key}: {json.dumps(value, ensure_ascii=False)}\n"
    if section_start_idx is None:
        base = yaml_text.rstrip()
        block = "".join(
            [
                f"{section_name}:\n",
                f"  {nested_section_name}:\n",
                nested_entry_line,
            ]
        )
        if base:
            return f"{base}\n\n{block}"
        return block

    nested_section_pattern = re.compile(
        rf"^(\s{{2}}{re.escape(nested_section_name)}:)\s*(.*)$"
    )
    existing_entry_pattern = re.compile(rf"^\s{{4}}{re.escape(key)}\s*:")
    nested_section_idx: int | None = None
    nested_section_end_idx = section_end_idx

    for idx in range(section_start_idx + 1, section_end_idx):
        raw_line = lines[idx]
        match = nested_section_pattern.match(raw_line.rstrip("\r\n"))
        if not match:
            continue
        nested_section_idx = idx
        nested_section_end_idx = section_end_idx
        for probe_idx in range(idx + 1, section_end_idx):
            probe_line = lines[probe_idx]
            probe_stripped = probe_line.strip()
            if not probe_stripped:
                continue
            if probe_line.lstrip().startswith("#"):
                continue
            indent = len(probe_line) - len(probe_line.lstrip(" "))
            if indent <= 2:
                nested_section_end_idx = probe_idx
                break
        inline_value = match.group(2).strip()
        if inline_value == "{}":
            lines[idx] = f"  {nested_section_name}:\n"
            nested_section_end_idx = idx + 1
        break

    if nested_section_idx is None:
        insert_idx = _section_insert_idx(lines, section_start_idx, section_end_idx)
        lines[insert_idx:insert_idx] = [
            f"  {nested_section_name}:\n",
            nested_entry_line,
        ]
        return "".join(lines)

    for idx in range(nested_section_idx + 1, nested_section_end_idx):
        if existing_entry_pattern.match(lines[idx]):
            raise ValueError("camera_already_exists")

    insert_idx = nested_section_end_idx
    while insert_idx > nested_section_idx + 1 and not lines[insert_idx - 1].strip():
        insert_idx -= 1

    lines[insert_idx:insert_idx] = [nested_entry_line]
    return "".join(lines)


def _normalize_coordinate(value: Any, *, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValueError("invalid_camera_location") from None
    if not math.isfinite(numeric) or numeric < minimum or numeric > maximum:
        raise ValueError("invalid_camera_location")
    return numeric


def register_camera_source(
    config_path: Path | str,
    *,
    camera_name: str,
    source: str,
    lat: float | None = None,
    lon: float | None = None,
    audio_source: str | None = None,
) -> None:
    normalized_name = camera_name.strip()
    normalized_source = str(source or "").strip()
    if not is_valid_camera_name(normalized_name):
        raise ValueError("invalid_camera_name")
    source_error = validate_camera_source(normalized_source)
    if source_error is not None:
        raise ValueError(source_error)
    if (lat is None) != (lon is None):
        raise ValueError("invalid_camera_location")
    normalized_audio_source = ""
    if audio_source is not None:
        normalized_audio_source = str(audio_source).strip()
        if normalized_audio_source:
            audio_source_error = validate_camera_source(normalized_audio_source)
            if audio_source_error is not None:
                raise ValueError(audio_source_error)
    normalized_lat = None if lat is None else _normalize_coordinate(lat, minimum=-90.0, maximum=90.0)
    normalized_lon = None if lon is None else _normalize_coordinate(lon, minimum=-180.0, maximum=180.0)

    path = Path(config_path)
    current_text = path.read_text(encoding="utf-8")
    updated_text = _append_mapping_entry_to_section_text(
        current_text,
        section_name="IP_ADDRESS",
        key=normalized_name,
        value=normalized_source,
    )
    if normalized_lat is not None and normalized_lon is not None:
        updated_text = _append_nested_mapping_entry_to_section_text(
            updated_text,
            section_name="telemetry",
            nested_section_name="devices",
            key=normalized_name,
            values={
                "lat": normalized_lat,
                "lon": normalized_lon,
            },
        )
    if normalized_audio_source:
        updated_text = _append_nested_scalar_entry_to_section_text(
            updated_text,
            section_name="audio",
            nested_section_name="sources",
            key=normalized_name,
            value=normalized_audio_source,
        )
    parsed = yaml.safe_load(updated_text) or {}
    if not isinstance(parsed, dict):
        raise ValueError("invalid_config_root")

    ip_address_cfg = parsed.get("IP_ADDRESS")
    if not isinstance(ip_address_cfg, dict):
        raise ValueError("invalid_ip_address_section")
    if str(ip_address_cfg.get(normalized_name, "")).strip() != normalized_source:
        raise ValueError("camera_persistence_failed")
    if normalized_lat is not None and normalized_lon is not None:
        telemetry_cfg = parsed.get("telemetry")
        if not isinstance(telemetry_cfg, dict):
            raise ValueError("invalid_camera_location")
        telemetry_devices_cfg = telemetry_cfg.get("devices")
        if not isinstance(telemetry_devices_cfg, dict):
            raise ValueError("invalid_camera_location")
        location_payload = telemetry_devices_cfg.get(normalized_name)
        if not isinstance(location_payload, dict):
            raise ValueError("camera_persistence_failed")
        try:
            stored_lat = float(location_payload.get("lat"))
            stored_lon = float(location_payload.get("lon"))
        except (TypeError, ValueError):
            raise ValueError("camera_persistence_failed") from None
        if abs(stored_lat - normalized_lat) > 1e-9 or abs(stored_lon - normalized_lon) > 1e-9:
            raise ValueError("camera_persistence_failed")
    if normalized_audio_source:
        audio_cfg = parsed.get("audio")
        if not isinstance(audio_cfg, dict):
            raise ValueError("camera_persistence_failed")
        audio_sources_cfg = audio_cfg.get("sources")
        if not isinstance(audio_sources_cfg, dict):
            raise ValueError("camera_persistence_failed")
        stored_audio_source = str(audio_sources_cfg.get(normalized_name, "")).strip()
        if stored_audio_source != normalized_audio_source:
            raise ValueError("camera_persistence_failed")
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(updated_text, encoding="utf-8")
    temp_path.replace(path)


def validate_camera_source(raw_path: Any) -> str | None:
    if not isinstance(raw_path, str):
        return "invalid_camera_source"

    normalized = raw_path.strip().lower()
    if not normalized:
        return "invalid_camera_source"
    if normalized.startswith(UNSUPPORTED_SIGNALING_SOURCE_SCHEMES):
        return "unsupported_camera_source_protocol"
    if normalized.startswith(SUPPORTED_CAMERA_SOURCE_SCHEMES):
        return None
    return "invalid_camera_source"


def validate_camera_viewer_source(raw_path: Any) -> str | None:
    if not isinstance(raw_path, str):
        return "invalid_camera_source"

    normalized = raw_path.strip().lower()
    if not normalized:
        return "invalid_camera_source"
    if normalized.startswith(UNSUPPORTED_SIGNALING_SOURCE_SCHEMES):
        return "unsupported_camera_source_protocol"
    if normalized.startswith(SUPPORTED_VIEWER_SOURCE_SCHEMES):
        return None
    if normalized.startswith(SUPPORTED_CAMERA_SOURCE_SCHEMES):
        return "unsupported_camera_source_protocol"
    return "invalid_camera_source"


@lru_cache(maxsize=256)
def normalize_camera_source(raw_path: Any) -> str:
    normalized = str(raw_path or "").strip()
    if not normalized:
        return ""

    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in {"http", "https"}:
        return normalized

    path_lower = parsed.path.lower()
    if path_lower.endswith(".m3u8"):
        return normalized

    try:
        content_type, preview = _fetch_http_source_preview(normalized)
    except Exception:
        return normalized
    preview_lower = preview.lower()
    if "html" not in content_type and "<html" not in preview_lower and "<!doctype html" not in preview_lower:
        return normalized

    matches = [match.group("path") for match in EMBEDDED_M3U8_PATTERN.finditer(preview)]
    if not matches:
        rtsp_candidate = _resolve_mediamtx_webrtc_page_to_rtsp(parsed, preview)
        return rtsp_candidate or normalized

    candidate = next((item for item in matches if "index.m3u8" in item.lower()), matches[0])
    resolved = urljoin(_base_url_for_relative_resolution(normalized), candidate)
    resolved_parts = urlparse(resolved)
    if not resolved_parts.query and parsed.query:
        resolved = urlunparse(resolved_parts._replace(query=parsed.query))
    return resolved


@lru_cache(maxsize=256)
def resolve_camera_viewer_url(raw_path: Any) -> str:
    candidate = str(raw_path or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""

    if parsed.path.lower().endswith(".m3u8"):
        return ""

    try:
        content_type, preview = _fetch_http_source_preview(candidate)
    except Exception:
        return ""

    preview_lower = preview.lower()
    if "html" not in content_type and "<html" not in preview_lower and "<!doctype html" not in preview_lower:
        return ""

    return candidate if _is_mediamtx_webrtc_page(preview) else ""


def is_network_path(raw_path: Any) -> bool:
    return validate_camera_source(raw_path) is None


def _base_url_for_relative_resolution(source_url: str) -> str:
    parsed = urlparse(source_url)
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = f"{path}/"
    return urlunparse(parsed._replace(path=path, params="", fragment=""))


def _fetch_http_source_preview(source_url: str) -> tuple[str, str]:
    request = Request(
        source_url,
        headers={
            "User-Agent": "ROBIOTEC/1.0",
            "Range": f"bytes=0-{HTTP_SOURCE_SNIFF_BYTES - 1}",
        },
    )
    with urlopen(request, timeout=HTTP_SOURCE_SNIFF_TIMEOUT_SEC) as response:
        content_type = str(response.headers.get("Content-Type", "")).lower()
        raw_preview = response.read(HTTP_SOURCE_SNIFF_BYTES)
    return content_type, raw_preview.decode("utf-8", errors="ignore")


def _resolve_mediamtx_webrtc_page_to_rtsp(parsed_url, preview: str) -> str | None:
    if not _is_mediamtx_webrtc_page(preview):
        return None
    if str(parsed_url.port or "") != MEDIAMTX_WEBRTC_PORT:
        return None
    path = (parsed_url.path or "").strip("/")
    if not path:
        return None
    return f"rtsp://{parsed_url.hostname}:{MEDIAMTX_RTSP_PORT}/{path}"


def _is_mediamtx_webrtc_page(preview: str) -> bool:
    preview_lower = preview.lower()
    return "mediamtxwebrtcreader" in preview_lower or "new url('whep'" in preview_lower


def as_bool(raw: Any, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        val = raw.strip().lower()
        if val in {"1", "true", "yes", "on", "si", "sí"}:
            return True
        if val in {"0", "false", "no", "off"}:
            return False
    if isinstance(raw, (int, float)):
        return bool(raw)
    return default
