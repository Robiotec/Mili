from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


OBJETIVO_ID = os.getenv("OBJETIVO_ID", "DRONE").strip() or "DRONE"
OBJETIVO_API_URL = os.getenv("OBJETIVO_API_URL", f"http://45.32.167.86:8004/objetivo/{OBJETIVO_ID}/").strip()
OBJETIVOS_DIR = Path(os.getenv("OBJETIVOS_DIR", str(Path(__file__).resolve().parent))).expanduser()
LATEST_DIR = OBJETIVOS_DIR / "latest"
HISTORY_DIR = OBJETIVOS_DIR / "history"
LOG_FILE = OBJETIVOS_DIR / "objetivos.log"
POLL_INTERVAL_SEC = max(float(os.getenv("OBJETIVO_POLL_INTERVAL_SEC", "1.0")), 0.25)
HTTP_TIMEOUT_SEC = max(float(os.getenv("OBJETIVO_HTTP_TIMEOUT_SEC", "5.0")), 1.0)


def configure_logging() -> logging.Logger:
    OBJETIVOS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("objetivos")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def read_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=HTTP_TIMEOUT_SEC) as response:
        body = response.read().decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("invalid_response_payload")
    return payload


def normalize_snapshot(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    latitud = data.get("latitud")
    longitud = data.get("longitud")
    try:
        latitud = float(latitud)
        longitud = float(longitud)
    except (TypeError, ValueError):
        return None

    return {
        "ok": bool(payload.get("ok", True)),
        "data": {
            "id": str(data.get("id") or OBJETIVO_ID).strip() or OBJETIVO_ID,
            "latitud": latitud,
            "longitud": longitud,
            "updated_at": str(data.get("updated_at") or "").strip(),
        },
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_url": OBJETIVO_API_URL,
    }


def latest_snapshot_path(objetivo_id: str) -> Path:
    return LATEST_DIR / f"{objetivo_id}.json"


def history_snapshot_path(objetivo_id: str) -> Path:
    return HISTORY_DIR / f"{objetivo_id}.ndjson"


def clear_latest_snapshot(objetivo_id: str) -> bool:
    path = latest_snapshot_path(objetivo_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def load_previous_snapshot(objetivo_id: str) -> dict[str, Any] | None:
    path = latest_snapshot_path(objetivo_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def snapshot_point_key(snapshot: dict[str, Any]) -> str:
    data = snapshot.get("data") if isinstance(snapshot, dict) else None
    if not isinstance(data, dict):
        return ""
    return "|".join(
        [
            str(data.get("id") or "").strip(),
            str(data.get("latitud") or "").strip(),
            str(data.get("longitud") or "").strip(),
            str(data.get("updated_at") or "").strip(),
        ]
    )


def snapshot_points(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return []

    points = snapshot.get("points")
    if isinstance(points, list):
        normalized_points = []
        for point in points:
            if not isinstance(point, dict):
                continue
            data = point.get("data") if isinstance(point.get("data"), dict) else point
            if isinstance(data, dict):
                normalized_points.append(dict(data))
        if normalized_points:
            return normalized_points

    data = snapshot.get("data")
    return [dict(data)] if isinstance(data, dict) else []


def history_points(objetivo_id: str) -> list[dict[str, Any]]:
    path = history_snapshot_path(objetivo_id)
    points: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return points
    except Exception:
        return points

    seen_keys = set()
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        data = payload.get("data")
        if not isinstance(data, dict):
            continue
        if str(data.get("id") or "").strip() != objetivo_id:
            continue
        point_key = snapshot_point_key({"data": data})
        if not point_key or point_key in seen_keys:
            continue
        points.append(dict(data))
        seen_keys.add(point_key)
    return points


def snapshot_changed(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    previous_data = previous.get("data") if isinstance(previous, dict) else None
    current_data = current.get("data") if isinstance(current, dict) else None
    if not isinstance(previous_data, dict) or not isinstance(current_data, dict):
        return True
    if not isinstance(previous.get("points"), list):
        return True
    return (
        previous_data.get("updated_at") != current_data.get("updated_at")
        or previous_data.get("latitud") != current_data.get("latitud")
        or previous_data.get("longitud") != current_data.get("longitud")
    )


def persist_snapshot(snapshot: dict[str, Any]) -> None:
    data = snapshot["data"]
    objetivo_id = str(data["id"]).strip() or OBJETIVO_ID
    path = latest_snapshot_path(objetivo_id)
    previous = load_previous_snapshot(objetivo_id)
    active_points = snapshot_points(previous)
    if previous and not isinstance(previous.get("points"), list):
        migrated_points = history_points(objetivo_id)
        if migrated_points:
            active_points = migrated_points
    current_key = snapshot_point_key(snapshot)
    existing_keys = {
        snapshot_point_key({"data": point})
        for point in active_points
    }
    if current_key and current_key not in existing_keys:
        active_points.append(dict(data))

    snapshot_with_points = dict(snapshot)
    snapshot_with_points["points"] = active_points

    path.write_text(
        json.dumps(snapshot_with_points, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with history_snapshot_path(objetivo_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False))
        handle.write("\n")


def main() -> int:
    logger = configure_logging()
    logger.info("Iniciando servicio de objetivos. URL=%s", OBJETIVO_API_URL)

    previous = load_previous_snapshot(OBJETIVO_ID)
    while True:
        try:
            payload = read_json(OBJETIVO_API_URL)
            snapshot = normalize_snapshot(payload)
            if snapshot is None:
                logger.warning("Respuesta sin coordenadas validas para %s", OBJETIVO_ID)
            else:
                data = snapshot["data"]
                logger.info(
                    "Lectura objetivo %s lat=%.6f lon=%.6f updated_at=%s",
                    data["id"],
                    data["latitud"],
                    data["longitud"],
                    data["updated_at"] or "--",
                )
                if snapshot_changed(previous, snapshot):
                    persist_snapshot(snapshot)
                    previous = snapshot
                    logger.info(
                        "Objetivo %s actualizado lat=%.6f lon=%.6f updated_at=%s",
                        data["id"],
                        data["latitud"],
                        data["longitud"],
                        data["updated_at"] or "--",
                    )
        except HTTPError as exc:
            if exc.code == 404:
                previous = None
                logger.info("Objetivo %s no encontrado en API; latest local se conserva hasta Clear", OBJETIVO_ID)
            logger.warning("HTTP %s consultando objetivo %s", exc.code, OBJETIVO_ID)
        except URLError as exc:
            logger.warning("No se pudo consultar objetivo %s: %s", OBJETIVO_ID, exc)
        except Exception as exc:
            logger.exception("Fallo inesperado consultando objetivo %s: %s", OBJETIVO_ID, exc)

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
