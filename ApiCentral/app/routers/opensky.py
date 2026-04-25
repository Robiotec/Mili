import time

import requests
from fastapi import APIRouter, HTTPException
from app.core.config import settings

router = APIRouter()

_AIRPLANES_URL = "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}"
_REQUEST_TIMEOUT = 12
_KNOTS_TO_MS = 0.514444
_FEET_TO_M = 0.3048


def _parse_alt_m(alt_baro) -> float | None:
    if alt_baro is None or alt_baro == "ground":
        return 0.0
    try:
        return float(alt_baro) * _FEET_TO_M
    except (TypeError, ValueError):
        return None


def _fetch_point(lat: float, lon: float, radius: int) -> list[dict]:
    url = _AIRPLANES_URL.format(lat=lat, lon=lon, radius=radius)
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("ac") or []
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="airplanes.live no respondió a tiempo")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al consultar airplanes.live: {e}")


@router.get("/states")
def get_states():
    query_points = [
        (settings.AIRPLANES_LAT, settings.AIRPLANES_LON, settings.AIRPLANES_RADIUS_NM),
        (settings.AIRPLANES_LAT2, settings.AIRPLANES_LON2, settings.AIRPLANES_RADIUS_NM2),
    ]

    seen: dict[str, dict] = {}
    for lat, lon, radius in query_points:
        if not radius:
            continue
        for ac in _fetch_point(lat, lon, radius):
            lat_ac = ac.get("lat")
            lon_ac = ac.get("lon")
            if lat_ac is None or lon_ac is None:
                continue
            icao = (ac.get("hex") or "").strip().lower()
            if not icao or icao in seen:
                continue

            alt_baro = ac.get("alt_baro")
            on_ground = alt_baro == "ground"
            gs = ac.get("gs")

            seen[icao] = {
                "icao24":    icao,
                "callsign":  (ac.get("flight") or icao).strip(),
                "lon":       lon_ac,
                "lat":       lat_ac,
                "alt_m":     _parse_alt_m(alt_baro),
                "on_ground": on_ground,
                "vel_ms":    float(gs) * _KNOTS_TO_MS if gs is not None else None,
                "heading":   ac.get("track"),
            }

    return {"ts": int(time.time()), "aircraft": list(seen.values())}
