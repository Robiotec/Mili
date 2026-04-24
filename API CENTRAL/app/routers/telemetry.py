from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# Memoria volátil: último estado GPS por vehículo
gps_data_store: dict[str, dict] = {}

class GPSPayload(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    heading: Optional[float] = None
    timestamp: Optional[str] = None

@router.get("/")
def home():
    return {"status": "online", "vehicles": list(gps_data_store.keys())}

# Endpoint para la Raspberry Pi
@router.post("/{vehicle_id}/update-gps")
async def update_gps(vehicle_id: str, data: GPSPayload):
    gps_data_store[vehicle_id] = {"vehicle_id": vehicle_id, **data.model_dump()}
    print(f"Recibido [{vehicle_id}]: {gps_data_store[vehicle_id]}")
    return {"message": "Data received", "vehicle_id": vehicle_id}

# Endpoint para consultar ubicación de un vehículo
@router.get("/{vehicle_id}/gps")
async def get_gps(vehicle_id: str):
    if vehicle_id not in gps_data_store:
        raise HTTPException(status_code=404, detail=f"No GPS data for vehicle '{vehicle_id}'")
    return gps_data_store[vehicle_id]
