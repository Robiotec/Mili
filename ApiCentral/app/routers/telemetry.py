import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

gps_data_store: dict[str, dict] = {}
LOGGER = logging.getLogger(__name__)


class GPSPayload(BaseModel):
    # Posición
    lat: Optional[float] = None
    lon: Optional[float] = None
    heading: Optional[float] = None
    timestamp: Optional[str] = None
    altitude: Optional[float] = None
    speed: Optional[float] = None
    # Batería
    battery_remaining_pct: Optional[float] = None
    battery_voltage_v: Optional[float] = None
    current_battery_a: Optional[float] = None
    # Estado del vehículo
    armed: Optional[bool] = None
    mode: Optional[str] = None
    system_status_text: Optional[str] = None
    # GPS
    gps_fix_type: Optional[int] = None
    satellites_visible: Optional[int] = None


@router.get("/")
def home():
    return {"status": "online", "vehicles": list(gps_data_store.keys())}


@router.post("/{vehicle_id}/update-gps")
async def update_gps(vehicle_id: str, data: GPSPayload):
    gps_data_store[vehicle_id] = {
        "vehicle_id": vehicle_id,
        **data.model_dump(exclude_none=False),
    }
    LOGGER.info(
        "[%s] lat=%s lon=%s alt=%sm spd=%skm/h hdg=%s° bat=%s%% armed=%s mode=%s sats=%s",
        vehicle_id,
        data.lat,
        data.lon,
        data.altitude,
        data.speed,
        data.heading,
        data.battery_remaining_pct,
        data.armed,
        data.mode,
        data.satellites_visible,
    )
    return {"message": "Data received", "vehicle_id": vehicle_id}


@router.get("/{vehicle_id}/gps")
async def get_gps(vehicle_id: str):
    if vehicle_id not in gps_data_store:
        raise HTTPException(status_code=404, detail=f"No GPS data for vehicle '{vehicle_id}'")
    return gps_data_store[vehicle_id]
