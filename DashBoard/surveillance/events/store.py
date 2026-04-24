from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from surveillance.json_utils import to_jsonable


@dataclass(frozen=True)
class SurveillanceEvent:
    event_id: str
    event_type: str
    camera_name: str
    device_id: str
    severity: str
    ts: float
    source: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(asdict(self))


class EventStore:
    def __init__(self, max_events: int = 2000):
        self._max_events = max(100, max_events)
        self._events: deque[SurveillanceEvent] = deque(maxlen=self._max_events)
        self._lock = threading.Lock()

    def record(
        self,
        event_type: str,
        *,
        camera_name: str = "",
        device_id: str = "",
        severity: str = "info",
        source: str = "system",
        payload: dict[str, Any] | None = None,
    ) -> SurveillanceEvent:
        event = SurveillanceEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            camera_name=camera_name,
            device_id=device_id or camera_name,
            severity=severity,
            ts=time.time(),
            source=source,
            payload=to_jsonable(payload or {}),
        )
        with self._lock:
            self._events.appendleft(event)
        return event

    def list_events(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        camera_name: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._lock:
            events = list(self._events)

        filtered = []
        for event in events:
            if event_type and event.event_type != event_type:
                continue
            if camera_name and event.camera_name != camera_name:
                continue
            filtered.append(event.to_dict())
            if len(filtered) >= limit:
                break
        return filtered
