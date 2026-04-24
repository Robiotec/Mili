from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from surveillance.json_utils import to_jsonable


VALID_VEHICLE_TYPES = {"dron", "automovil"}
VALID_TELEMETRY_MODES = {"manual", "api"}


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class VehicleRegistryEntry:
    registration_id: str
    created_ts: float
    updated_ts: float
    vehicle_type: str
    label: str
    identifier: str
    notes: str = ""
    telemetry_mode: str = "manual"
    api_base_url: str = ""
    api_device_id: str = ""
    camera_name: str = ""
    owner_level: int | None = None
    organization_id: int | None = None
    organization_name: str = ""

    @property
    def has_live_telemetry(self) -> bool:
        if self.telemetry_mode == "api":
            return bool(self.api_device_id or self.identifier)
        return False

    def to_storage_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_dict(self) -> dict[str, Any]:
        payload = to_jsonable(asdict(self))
        payload["ts"] = self.updated_ts
        payload["source"] = "vehicle_registry"
        payload["has_live_telemetry"] = self.has_live_telemetry
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "VehicleRegistryEntry":
        vehicle_type = str(raw.get("vehicle_type", "")).strip().lower()
        if vehicle_type not in VALID_VEHICLE_TYPES:
            raise ValueError("invalid_vehicle_type")

        identifier = str(raw.get("identifier", "")).strip()
        label = str(raw.get("label", "")).strip()
        if not identifier:
            raise ValueError("invalid_vehicle_identifier")
        if not label:
            raise ValueError("invalid_vehicle_label")

        registration_id = str(raw.get("registration_id", "")).strip() or str(uuid.uuid4())
        created_ts = float(raw.get("created_ts", 0.0) or 0.0)
        updated_ts = float(raw.get("updated_ts", 0.0) or 0.0)
        if created_ts <= 0.0:
            created_ts = time.time()
        if updated_ts <= 0.0:
            updated_ts = created_ts

        api_base_url = str(raw.get("api_base_url", "")).strip()
        telemetry_mode = str(raw.get("telemetry_mode", "")).strip().lower()
        if telemetry_mode not in VALID_TELEMETRY_MODES:
            if api_base_url:
                telemetry_mode = "api"
            else:
                telemetry_mode = "manual"

        return cls(
            registration_id=registration_id,
            created_ts=created_ts,
            updated_ts=updated_ts,
            vehicle_type=vehicle_type,
            label=label,
            identifier=identifier,
            notes=str(raw.get("notes", "")).strip(),
            telemetry_mode=telemetry_mode,
            api_base_url=api_base_url,
            api_device_id=str(raw.get("api_device_id", "")).strip(),
            camera_name=str(raw.get("camera_name", "")).strip(),
            owner_level=_safe_int(raw.get("owner_level")),
            organization_id=_safe_int(raw.get("organization_id")),
            organization_name=str(raw.get("organization_name", "")).strip(),
        )


class VehicleRegistryStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()

    def list_entries(self, *, vehicle_type: str | None = None) -> list[VehicleRegistryEntry]:
        normalized_type = str(vehicle_type or "").strip().lower() or None
        with self._lock:
            entries = list(self._load_entries_unlocked().values())

        if normalized_type is not None:
            entries = [entry for entry in entries if entry.vehicle_type == normalized_type]
        entries.sort(key=lambda item: (item.updated_ts, item.created_ts), reverse=True)
        return entries

    def get(self, identifier: str) -> VehicleRegistryEntry | None:
        normalized_key = self._identifier_key(identifier)
        if not normalized_key:
            return None
        with self._lock:
            return self._load_entries_unlocked().get(normalized_key)

    def get_by_registration_id(self, registration_id: str) -> VehicleRegistryEntry | None:
        normalized_registration_id = str(registration_id or "").strip()
        if not normalized_registration_id:
            return None
        with self._lock:
            entries = self._load_entries_unlocked()
            _, entry = self._find_entry_by_registration_id_unlocked(entries, normalized_registration_id)
            return entry

    def register(
        self,
        *,
        vehicle_type: str,
        label: str,
        identifier: str,
        notes: str = "",
        telemetry_mode: str = "manual",
        api_base_url: str = "",
        api_device_id: str = "",
    ) -> VehicleRegistryEntry:
        now = time.time()
        entry = self._build_entry(
            registration_id=str(uuid.uuid4()),
            created_ts=now,
            updated_ts=now,
            vehicle_type=vehicle_type,
            label=label,
            identifier=identifier,
            notes=notes,
            telemetry_mode=telemetry_mode,
            api_base_url=api_base_url,
            api_device_id=api_device_id,
        )

        with self._lock:
            entries = self._load_entries_unlocked()
            key = self._identifier_key(entry.identifier)
            if key in entries:
                raise ValueError("vehicle_already_exists")
            entries[key] = entry
            self._write_entries_unlocked(entries)
        return entry

    def update(
        self,
        registration_id: str,
        *,
        vehicle_type: str,
        label: str,
        identifier: str,
        notes: str = "",
        telemetry_mode: str = "manual",
        api_base_url: str = "",
        api_device_id: str = "",
    ) -> VehicleRegistryEntry:
        normalized_registration_id = str(registration_id or "").strip()
        if not normalized_registration_id:
            raise ValueError("vehicle_not_found")

        with self._lock:
            entries = self._load_entries_unlocked()
            existing_key, existing_entry = self._find_entry_by_registration_id_unlocked(entries, normalized_registration_id)
            if existing_entry is None or existing_key is None:
                raise ValueError("vehicle_not_found")

            updated_entry = self._build_entry(
                registration_id=existing_entry.registration_id,
                created_ts=existing_entry.created_ts,
                vehicle_type=vehicle_type,
                label=label,
                identifier=identifier,
                notes=notes,
                telemetry_mode=telemetry_mode,
                api_base_url=api_base_url,
                api_device_id=api_device_id,
                updated_ts=time.time(),
            )

            next_key = self._identifier_key(updated_entry.identifier)
            duplicate = entries.get(next_key)
            if duplicate is not None and duplicate.registration_id != existing_entry.registration_id:
                raise ValueError("vehicle_already_exists")

            del entries[existing_key]
            entries[next_key] = updated_entry
            self._write_entries_unlocked(entries)
        return updated_entry

    def delete(self, registration_id: str) -> VehicleRegistryEntry:
        normalized_registration_id = str(registration_id or "").strip()
        if not normalized_registration_id:
            raise ValueError("vehicle_not_found")

        with self._lock:
            entries = self._load_entries_unlocked()
            existing_key, existing_entry = self._find_entry_by_registration_id_unlocked(entries, normalized_registration_id)
            if existing_entry is None or existing_key is None:
                raise ValueError("vehicle_not_found")
            del entries[existing_key]
            self._write_entries_unlocked(entries)
        return existing_entry

    def _load_entries_unlocked(self) -> dict[str, VehicleRegistryEntry]:
        if not self.path.exists():
            return {}

        try:
            raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        if isinstance(raw_data, dict):
            if isinstance(raw_data.get("entries"), list):
                raw_entries = raw_data.get("entries", [])
            elif isinstance(raw_data.get("entries"), dict):
                raw_entries = list(raw_data.get("entries", {}).values())
            else:
                raw_entries = []
        elif isinstance(raw_data, list):
            raw_entries = raw_data
        else:
            raw_entries = []

        entries: dict[str, VehicleRegistryEntry] = {}
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            try:
                entry = VehicleRegistryEntry.from_dict(raw_entry)
            except ValueError:
                continue
            entries[self._identifier_key(entry.identifier)] = entry
        return entries

    def _write_entries_unlocked(self, entries: dict[str, VehicleRegistryEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": [
                entry.to_storage_dict()
                for entry in sorted(
                    entries.values(),
                    key=lambda item: (item.updated_ts, item.created_ts),
                    reverse=True,
                )
            ]
        }
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    @staticmethod
    def _identifier_key(identifier: str) -> str:
        return str(identifier or "").strip().casefold()

    @staticmethod
    def _find_entry_by_registration_id_unlocked(
        entries: dict[str, VehicleRegistryEntry],
        registration_id: str,
    ) -> tuple[str | None, VehicleRegistryEntry | None]:
        normalized_registration_id = str(registration_id or "").strip()
        for key, entry in entries.items():
            if str(entry.registration_id or "").strip() == normalized_registration_id:
                return key, entry
        return None, None

    @staticmethod
    def _build_entry(
        *,
        registration_id: str,
        created_ts: float,
        vehicle_type: str,
        label: str,
        identifier: str,
        notes: str = "",
        telemetry_mode: str = "manual",
        api_base_url: str = "",
        api_device_id: str = "",
        updated_ts: float | None = None,
    ) -> VehicleRegistryEntry:
        normalized_type = str(vehicle_type).strip().lower()
        normalized_label = str(label).strip()
        normalized_identifier = str(identifier).strip()
        normalized_notes = str(notes).strip()
        normalized_telemetry_mode = str(telemetry_mode or "").strip().lower() or "manual"
        normalized_api_base_url = str(api_base_url).strip().rstrip("/")
        normalized_api_device_id = str(api_device_id).strip()

        if normalized_type not in VALID_VEHICLE_TYPES:
            raise ValueError("invalid_vehicle_type")
        if not normalized_label:
            raise ValueError("invalid_vehicle_label")
        if not normalized_identifier:
            raise ValueError("invalid_vehicle_identifier")
        if normalized_telemetry_mode not in VALID_TELEMETRY_MODES:
            raise ValueError("invalid_vehicle_telemetry_mode")

        if normalized_telemetry_mode == "api":
            if not normalized_api_device_id:
                normalized_api_device_id = normalized_identifier
        else:
            normalized_api_base_url = ""
            normalized_api_device_id = ""

        normalized_created_ts = float(created_ts or 0.0)
        if normalized_created_ts <= 0.0:
            normalized_created_ts = time.time()
        normalized_updated_ts = float(updated_ts or 0.0)
        if normalized_updated_ts <= 0.0:
            normalized_updated_ts = normalized_created_ts

        return VehicleRegistryEntry(
            registration_id=str(registration_id or "").strip() or str(uuid.uuid4()),
            created_ts=normalized_created_ts,
            updated_ts=normalized_updated_ts,
            vehicle_type=normalized_type,
            label=normalized_label,
            identifier=normalized_identifier,
            notes=normalized_notes,
            telemetry_mode=normalized_telemetry_mode,
            api_base_url=normalized_api_base_url,
            api_device_id=normalized_api_device_id,
        )
