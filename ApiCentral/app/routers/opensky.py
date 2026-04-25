import requests
from fastapi import APIRouter, HTTPException
from app.core.config import settings

router = APIRouter()

OPENSKY_URL = "https://opensky-network.org/api/states/all"
REQUEST_TIMEOUT = 10


@router.get("/states")
def get_states():
    params = {
        "lamin": settings.OPENSKY_LAMIN,
        "lomin": settings.OPENSKY_LOMIN,
        "lamax": settings.OPENSKY_LAMAX,
        "lomax": settings.OPENSKY_LOMAX,
    }
    try:
        resp = requests.get(OPENSKY_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="OpenSky no respondió a tiempo")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al consultar OpenSky: {e}")
