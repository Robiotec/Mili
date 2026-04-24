from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from surveillance.json_utils import to_jsonable


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    camera_name: str
    device_id: str
    ts: float
    file_path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(asdict(self))


class EvidenceStore:
    def __init__(self, max_items: int = 2000):
        self._items: deque[EvidenceRecord] = deque(maxlen=max(100, max_items))
        self._lock = threading.Lock()

    def record(
        self,
        *,
        kind: str,
        camera_name: str,
        device_id: str,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        item = EvidenceRecord(
            evidence_id=str(uuid.uuid4()),
            kind=kind,
            camera_name=camera_name,
            device_id=device_id or camera_name,
            ts=time.time(),
            file_path=file_path,
            metadata=to_jsonable(metadata or {}),
        )
        with self._lock:
            self._items.appendleft(item)
        return item

    def list_evidence(
        self,
        *,
        limit: int = 100,
        camera_name: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._lock:
            items = list(self._items)

        filtered = []
        for item in items:
            if camera_name and item.camera_name != camera_name:
                continue
            if kind and item.kind != kind:
                continue
            filtered.append(item.to_dict())
            if len(filtered) >= limit:
                break
        return filtered
