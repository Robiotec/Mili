from __future__ import annotations

import base64
import binascii
import logging
import mimetypes
import shlex
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from controllers.cropts_embeding.crops_reading import (
    RemoteManifestWatcher,
    RobustSSHClient,
    SSHConfig,
    build_manifest_snapshot,
    iter_remote_path_candidates,
    normalize_plate_key,
)
from surveillance.evidence.store import EvidenceStore


LOGGER = logging.getLogger(__name__)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
IMAGE_KEY_PRIORITY = (
    "vehicle_crop",
    "vehicle_crop_path",
    "vehicle_image",
    "vehicle_image_path",
    "car_crop",
    "car_crop_path",
    "crop_vehicle",
    "crop_car",
    "frame_crop",
    "snapshot_path",
    "snapshot",
    "image_path",
    "image_file",
    "image",
    "img",
    "plate_crop",
    "plate_crop_path",
    "plate_image",
    "plate_image_path",
)


@dataclass(frozen=True)
class RemoteEvidenceBridgeConfig:
    enabled: bool = False
    host: str = ""
    user: str = ""
    port: int = 22
    key_path: str = ""
    connect_timeout: int = 10
    command_timeout: int = 20
    max_retries: int = 1
    retry_delay: int = 2
    strict_host_key_checking: str = "accept-new"
    remote_manifest_path: str = ""
    poll_interval_sec: float = 1.0
    camera_name_map: dict[str, str] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return bool(
            self.enabled
            and self.host.strip()
            and self.user.strip()
            and self.remote_manifest_path.strip()
        )


def load_remote_evidence_bridge_config(cfg_data: dict[str, Any]) -> RemoteEvidenceBridgeConfig:
    raw_cfg = cfg_data.get("remote_evidence")
    if not isinstance(raw_cfg, dict):
        return RemoteEvidenceBridgeConfig()

    raw_camera_map = raw_cfg.get("camera_name_map")
    camera_name_map: dict[str, str] = {}
    if isinstance(raw_camera_map, dict):
        for raw_key, raw_value in raw_camera_map.items():
            key = str(raw_key or "").strip()
            value = str(raw_value or "").strip()
            if key and value:
                camera_name_map[key] = value

    key_path = str(raw_cfg.get("key_path") or "").strip()
    if key_path:
        key_path = str(Path(key_path).expanduser())

    return RemoteEvidenceBridgeConfig(
        enabled=bool(raw_cfg.get("enabled")),
        host=str(raw_cfg.get("host") or "").strip(),
        user=str(raw_cfg.get("user") or "").strip(),
        port=_safe_int(raw_cfg.get("port"), default=22),
        key_path=key_path,
        connect_timeout=_safe_int(raw_cfg.get("connect_timeout"), default=10),
        command_timeout=_safe_int(raw_cfg.get("command_timeout"), default=20),
        max_retries=max(1, _safe_int(raw_cfg.get("max_retries"), default=1)),
        retry_delay=max(0, _safe_int(raw_cfg.get("retry_delay"), default=2)),
        strict_host_key_checking=str(raw_cfg.get("strict_host_key_checking") or "accept-new").strip() or "accept-new",
        remote_manifest_path=str(raw_cfg.get("manifest_path") or "").strip(),
        poll_interval_sec=max(0.5, _safe_float(raw_cfg.get("poll_interval_sec"), default=1.0)),
        camera_name_map=camera_name_map,
    )


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_camera_alias(value: object) -> str:
    return "".join(ch for ch in str(value or "").strip().casefold() if ch.isalnum())


def _is_image_path(value: object) -> bool:
    path = str(value or "").strip()
    if not path:
        return False
    lower = path.casefold()
    return any(lower.endswith(suffix) for suffix in IMAGE_SUFFIXES)


def _iter_string_values(payload: Any):
    if isinstance(payload, dict):
        for value in payload.values():
            yield from _iter_string_values(value)
        return

    if isinstance(payload, (list, tuple, set)):
        for value in payload:
            yield from _iter_string_values(value)
        return

    if isinstance(payload, str):
        normalized = payload.strip()
        if normalized:
            yield normalized


class RemoteEvidenceBridge:
    def __init__(
        self,
        *,
        config: RemoteEvidenceBridgeConfig,
        evidence_store: EvidenceStore,
        local_camera_names_provider: Callable[[], list[str]],
    ) -> None:
        self.config = config
        self.evidence_store = evidence_store
        self.local_camera_names_provider = local_camera_names_provider
        self._watcher: RemoteManifestWatcher | None = None
        self._client: RobustSSHClient | None = None
        self._lock = threading.Lock()
        self._seen_keys: set[str] = set()

    def start(self) -> None:
        if not self.config.is_ready:
            return

        with self._lock:
            if self._watcher is not None and self._watcher.is_alive():
                return

            self._client = RobustSSHClient(
                SSHConfig(
                    host=self.config.host,
                    user=self.config.user,
                    port=self.config.port,
                    key_path=self.config.key_path or None,
                    connect_timeout=self.config.connect_timeout,
                    command_timeout=self.config.command_timeout,
                    max_retries=self.config.max_retries,
                    retry_delay=self.config.retry_delay,
                    strict_host_key_checking=self.config.strict_host_key_checking,
                    log_level=30,
                )
            )

            try:
                initial_snapshot = build_manifest_snapshot(
                    client=self._client,
                    remote_manifest_path=self.config.remote_manifest_path,
                    signature=None,
                    previous_snapshot=None,
                    fetch_details=True,
                    max_retries=1,
                )
            except Exception:
                LOGGER.exception(
                    "No se pudo inicializar la lectura remota de evidencias desde %s@%s:%s",
                    self.config.user,
                    self.config.host,
                    self.config.remote_manifest_path,
                )
                self._client = None
                self._seen_keys.clear()
                return

            for plate in initial_snapshot.order:
                item = initial_snapshot.merged_by_plate.get(plate) or initial_snapshot.manifest_by_plate.get(plate)
                if item:
                    self._record_plate_item(item)

            watcher = RemoteManifestWatcher(
                client=self._client,
                remote_manifest_path=self.config.remote_manifest_path,
                resync_interval=self.config.poll_interval_sec,
                on_item_event=self._on_item_event,
            )
            try:
                watcher.start()
            except Exception:
                LOGGER.exception(
                    "No se pudo iniciar el observador remoto de evidencias desde %s@%s:%s",
                    self.config.user,
                    self.config.host,
                    self.config.remote_manifest_path,
                )
                self._client = None
                self._seen_keys.clear()
                return

            self._watcher = watcher

    def stop(self) -> None:
        with self._lock:
            watcher = self._watcher
            self._watcher = None
            self._client = None
            self._seen_keys.clear()

        if watcher is not None:
            watcher.stop()
            watcher.join(timeout=3)

    def fetch_remote_file_bytes(self, remote_path: str) -> bytes | None:
        client = self._client
        if client is None:
            return None

        for candidate_path in iter_remote_path_candidates(
            remote_path,
            remote_manifest_path=self.config.remote_manifest_path,
        ):
            result = client.run_command(
                f"base64 {shlex.quote(candidate_path)}",
                check=False,
                max_retries=1,
            )
            if not result.success or not result.stdout.strip():
                continue

            try:
                return base64.b64decode("".join(result.stdout.split()).encode("ascii"))
            except (binascii.Error, ValueError):
                continue

        return None

    def guess_content_type(self, remote_path: str) -> str:
        guessed_type, _ = mimetypes.guess_type(str(remote_path or "").strip())
        return guessed_type or "application/octet-stream"

    def _on_item_event(self, event_name: str, item: dict) -> None:
        if event_name not in {"AGREGADO", "ACTUALIZADO"}:
            return
        self._record_plate_item(item)

    def _record_plate_item(self, item: dict) -> None:
        normalized_item = dict(item)
        plate = normalize_plate_key(normalized_item.get("plate"))
        if not plate:
            return

        remote_camera_name = str(
            normalized_item.get("cam_id")
            or normalized_item.get("camera_name")
            or normalized_item.get("camera")
            or ""
        ).strip()
        normalized_item["plate"] = plate
        image_path = self._resolve_remote_image_path(normalized_item)
        if image_path:
            normalized_item["remote_image_path"] = image_path

        evidence_key = "|".join(
            [
                remote_camera_name,
                plate,
                str(normalized_item.get("ts") or ""),
                str(normalized_item.get("detail_file") or normalized_item.get("file") or ""),
                image_path,
            ]
        )
        if evidence_key in self._seen_keys:
            return
        self._seen_keys.add(evidence_key)

        resolved_camera_name = self._resolve_camera_name(remote_camera_name)
        evidence_ts = _safe_float(normalized_item.get("ts"), default=0.0) or None
        self.evidence_store.record(
            kind="plate_snapshot",
            camera_name=resolved_camera_name or remote_camera_name,
            device_id=":".join(part for part in (resolved_camera_name or remote_camera_name, plate) if part) or plate,
            file_path=image_path,
            metadata=normalized_item,
            ts=evidence_ts,
        )

    def _resolve_camera_name(self, remote_camera_name: str) -> str:
        normalized_remote_name = str(remote_camera_name or "").strip()
        if not normalized_remote_name:
            return ""

        explicit = self.config.camera_name_map.get(normalized_remote_name)
        if explicit:
            return explicit

        local_camera_names = [str(item or "").strip() for item in self.local_camera_names_provider() if str(item or "").strip()]
        if normalized_remote_name in local_camera_names:
            return normalized_remote_name

        folded_remote_name = normalized_remote_name.casefold()
        for local_name in local_camera_names:
            if local_name.casefold() == folded_remote_name:
                return local_name

        normalized_alias = _normalize_camera_alias(normalized_remote_name)
        for local_name in local_camera_names:
            if _normalize_camera_alias(local_name) == normalized_alias:
                return local_name

        return normalized_remote_name

    def _resolve_remote_image_path(self, item: dict) -> str:
        for key in IMAGE_KEY_PRIORITY:
            candidate = item.get(key)
            if _is_image_path(candidate):
                resolved = self._resolve_remote_path(str(candidate))
                if resolved:
                    return resolved

        for value in _iter_string_values(item):
            if not _is_image_path(value):
                continue
            resolved = self._resolve_remote_path(value)
            if resolved:
                return resolved

        return ""

    def _resolve_remote_path(self, remote_path: str) -> str:
        client = self._client
        if client is None:
            return ""

        for candidate_path in iter_remote_path_candidates(
            remote_path,
            remote_manifest_path=self.config.remote_manifest_path,
        ):
            result = client.run_command(
                f"if [ -f {shlex.quote(candidate_path)} ]; then printf 'OK'; fi",
                check=False,
                max_retries=1,
            )
            if result.success and result.stdout.strip() == "OK":
                return candidate_path
        return ""
