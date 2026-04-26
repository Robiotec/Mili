import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/objetivo",
    tags=["Objetivo"],
)


class ObjetivoPayload(BaseModel):
    latitud: float = Field(...)
    longitud: float = Field(...)


class ObjetivoResponse(BaseModel):
    id: str
    latitud: float
    longitud: float
    updated_at: str


# Almacenamiento en memoria.
# Ojo: si reinicias la API, se pierde.
OBJETIVOS: Dict[str, ObjetivoResponse] = {}
OBJETIVOS_DIR = Path(os.getenv("OBJETIVOS_DIR", "/home/robiotec/SVI/objetivos")).expanduser()
OBJETIVOS_LATEST_DIR = OBJETIVOS_DIR / "latest"


def _normalized_objetivo_id(objetivo_id: str) -> str:
    normalized_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(objetivo_id or "").strip())
    if not normalized_id:
        raise ValueError("invalid_objetivo_id")
    return normalized_id


def _latest_snapshot_path(objetivo_id: str) -> Path:
    return OBJETIVOS_LATEST_DIR / f"{_normalized_objetivo_id(objetivo_id)}.json"


def _objetivo_data(objetivo: ObjetivoResponse) -> dict:
    return {
        "id": objetivo.id,
        "latitud": objetivo.latitud,
        "longitud": objetivo.longitud,
        "updated_at": objetivo.updated_at,
    }


def _point_key(data: dict) -> str:
    return "|".join(
        [
            str(data.get("id") or "").strip(),
            str(data.get("latitud") or "").strip(),
            str(data.get("longitud") or "").strip(),
            str(data.get("updated_at") or "").strip(),
        ]
    )


def _extract_points(payload: dict) -> list[dict]:
    raw_points = payload.get("points") if isinstance(payload.get("points"), list) else []
    points = []
    for point in raw_points:
        if not isinstance(point, dict):
            continue
        data = point.get("data") if isinstance(point.get("data"), dict) else point
        if isinstance(data, dict):
            points.append(dict(data))

    if points:
        return points

    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    return [dict(data)] if data else []


def _load_latest_snapshot(objetivo_id: str) -> dict:
    path = _latest_snapshot_path(objetivo_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_latest_objetivo(objetivo_id: str) -> ObjetivoResponse | None:
    payload = _load_latest_snapshot(objetivo_id)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    try:
        return ObjetivoResponse(
            id=str(data.get("id") or objetivo_id).strip() or objetivo_id,
            latitud=float(data.get("latitud")),
            longitud=float(data.get("longitud")),
            updated_at=str(data.get("updated_at") or "").strip(),
        )
    except (TypeError, ValueError):
        return None


def _persist_latest_snapshot(objetivo: ObjetivoResponse) -> None:
    data = _objetivo_data(objetivo)
    previous = _load_latest_snapshot(objetivo.id)
    points = _extract_points(previous)
    current_key = _point_key(data)
    existing_keys = {_point_key(point) for point in points}
    if current_key and current_key not in existing_keys:
        points.append(data)

    OBJETIVOS_LATEST_DIR.mkdir(parents=True, exist_ok=True)
    _latest_snapshot_path(objetivo.id).write_text(
        json.dumps(
            {
                "ok": True,
                "data": data,
                "points": points,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_url": "ApiCentral",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _clear_latest_snapshot(objetivo_id: str) -> bool:
    path = _latest_snapshot_path(objetivo_id)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


@router.post("/{objetivo_id}/update")
def update_objetivo(objetivo_id: str, payload: ObjetivoPayload):
    """
    Recibe la última posición de un objetivo/dron/vehículo.
    Endpoint:
        POST /objetivo/{id}/update
    """

    objetivo = ObjetivoResponse(
        id=objetivo_id,
        latitud=payload.latitud,
        longitud=payload.longitud,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    OBJETIVOS[objetivo_id] = objetivo
    _persist_latest_snapshot(objetivo)

    return {
        "ok": True,
        "message": "Objetivo actualizado correctamente.",
        "data": objetivo,
    }


@router.get("/{objetivo_id}/")
def get_objetivo(objetivo_id: str):
    """
    Devuelve la última posición registrada de un objetivo.
    Endpoint:
        GET /objetivo/{id}/
    """

    objetivo = OBJETIVOS.get(objetivo_id)
    if objetivo is None:
        objetivo = _load_latest_objetivo(objetivo_id)
        if objetivo is not None:
            OBJETIVOS[objetivo_id] = objetivo

    if objetivo is None:
        raise HTTPException(
            status_code=404,
            detail="Objetivo no encontrado.",
        )

    return {
        "ok": True,
        "data": objetivo,
    }


@router.get("/")
def list_objetivos():
    """
    Lista todos los objetivos registrados en memoria.
    Endpoint:
        GET /objetivo/
    """

    return {
        "ok": True,
        "count": len(OBJETIVOS),
        "data": list(OBJETIVOS.values()),
    }


@router.delete("/{objetivo_id}")
def clear_objetivo(objetivo_id: str):
    """
    Elimina la última posición registrada de un objetivo.
    Endpoint:
        DELETE /objetivo/{id}
    """

    existed = objetivo_id in OBJETIVOS
    OBJETIVOS.pop(objetivo_id, None)
    cache_existed = _clear_latest_snapshot(objetivo_id)

    return {
        "ok": True,
        "cleared": True,
        "existed": existed or cache_existed,
        "id": objetivo_id,
    }
