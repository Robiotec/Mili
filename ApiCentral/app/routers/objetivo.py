from datetime import datetime, timezone
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

    return {
        "ok": True,
        "cleared": True,
        "existed": existed,
        "id": objetivo_id,
    }
