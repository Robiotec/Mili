#!/usr/bin/env python3
"""
Servicio de tráfico aéreo: consulta airplanes.live (cobertura global con ADS-B)
sobre Ecuador y guarda el resultado en opensky_data.json para que el dashboard
lo consuma localmente.

API: https://airplanes.live/api-guide/
  GET /v2/point/{lat}/{lon}/{radius_nm}  (max 250 nm, sin autenticación)

Intervalo: 15 s (rate limit: 1 req/s, sin clave).
"""

import json
import logging
import os
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
AIRPLANES_URL = os.getenv(
    "AIRPLANES_URL",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
).strip()
QUERY_POINTS = [
    {
        "lat": float(os.getenv("AIRPLANES_LAT", "-1.8")),
        "lon": float(os.getenv("AIRPLANES_LON", "-78.2")),
        "radius": max(0, int(os.getenv("AIRPLANES_RADIUS_NM", "250"))),
    },
    {
        "lat": float(os.getenv("AIRPLANES_LAT2", "-5.5")),
        "lon": float(os.getenv("AIRPLANES_LON2", "-78.5")),
        "radius": max(0, int(os.getenv("AIRPLANES_RADIUS_NM2", "200"))),
    },
]

INTERVAL_SEC = max(int(os.getenv("OPENSKY_INTERVAL_SEC", "15")), 1)
OUT_FILE = Path(os.getenv("OPENSKY_DATA_FILE", str(BASE_DIR / "opensky_data.json"))).expanduser()
REQUEST_TIMEOUT = max(float(os.getenv("OPENSKY_REQUEST_TIMEOUT_SEC", "12")), 1.0)

KNOTS_TO_MS = 0.514444
FEET_TO_M = 0.3048

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [airplanes] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("airplanes")


def _parse_alt_m(alt_baro) -> float | None:
    if alt_baro is None or alt_baro == "ground":
        return 0.0
    try:
        return float(alt_baro) * FEET_TO_M
    except (TypeError, ValueError):
        return None


def fetch_states() -> list[dict]:
    seen: dict[str, dict] = {}
    for qp in QUERY_POINTS:
        url = AIRPLANES_URL.format(**qp)
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            log.warning("Timeout consultando %s", url)
            continue
        except requests.exceptions.HTTPError as e:
            log.warning("HTTP error airplanes.live: %s", e)
            continue
        except Exception as e:
            log.warning("Error inesperado: %s", e)
            continue

        for ac in data.get("ac") or []:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue
            icao = (ac.get("hex") or "").strip().lower()
            if not icao or icao in seen:
                continue

            alt_baro = ac.get("alt_baro")
            on_ground = alt_baro == "ground"
            alt_m = _parse_alt_m(alt_baro)

            gs = ac.get("gs")
            vel_ms = float(gs) * KNOTS_TO_MS if gs is not None else None

            seen[icao] = {
                "icao24":    icao,
                "callsign":  (ac.get("flight") or icao).strip(),
                "lon":       lon,
                "lat":       lat,
                "alt_m":     alt_m,
                "on_ground": on_ground,
                "vel_ms":    vel_ms,
                "heading":   ac.get("track"),
            }

        # Respetar rate limit: 1 req/s
        time.sleep(1)

    return list(seen.values())


def save(aircraft: list[dict]) -> None:
    payload = {"ts": int(time.time()), "aircraft": aircraft}
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(OUT_FILE)
    log.info("Actualizado: %d aeronaves", len(aircraft))


def main() -> None:
    log.info("Iniciando servicio airplanes.live (intervalo %ds)", INTERVAL_SEC)
    while True:
        aircraft = fetch_states()
        save(aircraft)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
