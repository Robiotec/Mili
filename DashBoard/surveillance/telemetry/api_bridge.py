from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any

from gps_api_client import GPSApiClient
from surveillance.telemetry.service import TelemetryService
from surveillance.vehicle_registry import VehicleRegistryEntry


API_POLL_INTERVAL_SEC = max(float(os.getenv("TELEMETRY_REFRESH_SECONDS", "1")), 0.25)
DEFAULT_GPS_API_BASE_URL = (
    os.getenv("GPS_API_BASE_URL", "").strip()
    or os.getenv("STREAM_API_BASE_URL", "").strip()
)
LOGGER = logging.getLogger(__name__)


class ApiTelemetryBridgeManager:
    def __init__(self, telemetry_service: TelemetryService, event_store: Any):
        self.telemetry_service = telemetry_service
        self.event_store = event_store
        self._workers: dict[str, _ApiTelemetryBridgeWorker] = {}
        self._lock = threading.Lock()

    def reload_entries(self, entries: list[VehicleRegistryEntry]) -> None:
        managed = {
            entry.registration_id: entry
            for entry in entries
            if str(entry.telemetry_mode or "").strip().lower() == "api"
        }

        with self._lock:
            active_keys = set(managed)
            for key, worker in list(self._workers.items()):
                if key in active_keys:
                    continue
                worker.stop()
                del self._workers[key]

            for key, entry in managed.items():
                worker = self._workers.get(key)
                if worker is None:
                    worker = _ApiTelemetryBridgeWorker(
                        entry=entry,
                        telemetry_service=self.telemetry_service,
                        event_store=self.event_store,
                    )
                    self._workers[key] = worker
                    worker.start()
                    continue
                worker.update_entry(entry)

    def stop(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()


class _ApiTelemetryBridgeWorker:
    def __init__(
        self,
        *,
        entry: VehicleRegistryEntry,
        telemetry_service: TelemetryService,
        event_store: Any,
    ) -> None:
        self.telemetry_service = telemetry_service
        self.event_store = event_store
        self._entry = entry
        self._entry_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._reported_link = False

    def update_entry(self, entry: VehicleRegistryEntry) -> None:
        with self._entry_lock:
            self._entry = entry

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def _run(self) -> None:
        client: GPSApiClient | None = None
        current_base_url = ""

        try:
            while not self._stop_event.is_set():
                with self._entry_lock:
                    entry = self._entry

                base_url = str(entry.api_base_url or "").strip() or DEFAULT_GPS_API_BASE_URL
                if not base_url:
                    self._stop_event.wait(API_POLL_INTERVAL_SEC)
                    continue

                if client is None or current_base_url != base_url:
                    if client is not None:
                        client.close()
                    client = GPSApiClient(base_url=base_url)
                    current_base_url = base_url

                try:
                    gps = self._read_gps(client, entry)
                    if gps is not None:
                        self._forward_gps(entry, gps)
                except Exception as exc:  # pragma: no cover - dependiente de red externa
                    LOGGER.debug("No se pudo consultar telemetria API para %s: %s", entry.identifier, exc)

                self._stop_event.wait(API_POLL_INTERVAL_SEC)
        finally:
            if client is not None:
                client.close()

    def _read_gps(self, client: GPSApiClient, entry: VehicleRegistryEntry):
        expected_id = str(entry.api_device_id or entry.identifier or "").strip() or None
        return client.get_latest_gps(device_id=expected_id, prefer_vehicle_path=True)

    def _forward_gps(self, entry: VehicleRegistryEntry, gps: Any) -> None:
        expected_id = str(entry.api_device_id or entry.identifier or "").strip()
        received_id = str(getattr(gps, "id", "") or "").strip()
        if expected_id and received_id and expected_id.casefold() != received_id.casefold():
            return

        self.telemetry_service.update(
            entry.identifier,
            lat=float(gps.lat),
            lon=float(gps.lon),
            heading=_safe_float(getattr(gps, "heading", None)),
            device_status="online",
            source_ts=_parse_source_timestamp(getattr(gps, "timestamp", "")),
            extra={
                "telemetry_mode": "api",
                "vehicle_id": received_id or expected_id or entry.identifier,
                "gps_api_id": received_id or expected_id,
                "gps_api_timestamp": str(getattr(gps, "timestamp", "") or "").strip(),
                "gps_api_base_url": str(entry.api_base_url or "").strip(),
                "api_device_id": expected_id,
                "telemetry_notes": str(entry.notes or "").strip(),
            },
        )

        if self._reported_link:
            return
        try:
            self.event_store.record(
                "gps_api_vehicle_linked",
                camera_name=entry.identifier,
                device_id=entry.identifier,
                source="gps_api_bridge",
                payload={
                    "identifier": entry.identifier,
                    "label": entry.label,
                    "base_url": str(entry.api_base_url or "").strip(),
                    "expected_id": expected_id,
                    "received_id": received_id or expected_id,
                },
            )
        except Exception:  # pragma: no cover - defensivo
            return
        self._reported_link = True


def _parse_source_timestamp(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(raw).timestamp()
        except Exception:
            continue
    return None


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
