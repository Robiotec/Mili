#!/usr/bin/env python3
"""
Servicio OpenSky: consulta el tráfico aéreo sobre Ecuador y guarda el resultado
en opensky_data.json para que el dashboard lo consuma localmente.

Intervalo: 10 segundos (límite anónimo OpenSky: 10 req/min).
"""

import json
import logging
import time
from pathlib import Path

import requests

OPENSKY_URL = "https://opensky-network.org/api/states/all"
BBOX = {"lamin": -10.0, "lomin": -82.0, "lamax": 5.0, "lomax": -70.0}
INTERVAL_SEC = 10
OUT_FILE = Path(__file__).parent / "opensky_data.json"
REQUEST_TIMEOUT = 9

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [opensky] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("opensky")


def fetch_states() -> dict | None:
    try:
        resp = requests.get(OPENSKY_URL, params=BBOX, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        log.warning("Timeout al consultar OpenSky")
    except requests.exceptions.HTTPError as e:
        log.warning("HTTP error OpenSky: %s", e)
    except Exception as e:
        log.warning("Error inesperado: %s", e)
    return None


def save(data: dict) -> None:
    states = data.get("states") or []
    aircraft = [
        {
            "icao24":    s[0],
            "callsign":  (s[1] or "").strip(),
            "lon":       s[5],
            "lat":       s[6],
            "alt_m":     s[7],
            "on_ground": s[8],
            "vel_ms":    s[9],
            "heading":   s[10],
        }
        for s in states
        if s[5] is not None and s[6] is not None
    ]
    payload = {"ts": data.get("time"), "aircraft": aircraft}
    tmp = OUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(OUT_FILE)
    log.info("Actualizado: %d aeronaves", len(aircraft))


def main() -> None:
    log.info("Iniciando servicio OpenSky (intervalo %ds)", INTERVAL_SEC)
    while True:
        data = fetch_states()
        if data is not None:
            save(data)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
