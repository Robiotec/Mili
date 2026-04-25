from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional, Protocol
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =========================
# Logging
# =========================
logger = logging.getLogger("gps_tracker_menu")

GPS_CONTAINER_KEYS = (
    "data",
    "item",
    "items",
    "result",
    "results",
    "records",
    "history",
    "gps",
    "positions",
    "vehicles",
    "telemetry",
)


def _first_present(data: dict, *keys: str, default: object = None) -> object:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _first_nested_mapping(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        nested = data.get(key)
        if isinstance(nested, dict):
            return nested
    return None


def _looks_like_gps_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    if _first_present(payload, "lat", "latitude", "latitud") is not None:
        return _first_present(payload, "lon", "lng", "longitude", "longitud") is not None

    nested = _first_nested_mapping(payload, "location", "position", "coordinates", "coords", "gps")
    if nested is None:
        return False
    return (
        _first_present(nested, "lat", "latitude", "latitud") is not None
        and _first_present(nested, "lon", "lng", "longitude", "longitud") is not None
    )


def _iter_gps_payload_candidates(payload: Any):
    if isinstance(payload, dict):
        if _looks_like_gps_payload(payload):
            yield payload
        for key in GPS_CONTAINER_KEYS:
            if key in payload:
                yield from _iter_gps_payload_candidates(payload[key])
        return

    if isinstance(payload, list):
        for item in payload:
            yield from _iter_gps_payload_candidates(item)


def _parse_timestamp(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")).timestamp(),
        lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M:%S").timestamp(),
        lambda item: float(item),
    ):
        try:
            return float(parser(raw))
        except Exception:
            continue
    return None


def _select_latest_gps_payload(payload: Any, *, device_id: str = "") -> Optional["GPSData"]:
    normalized_device_id = str(device_id or "").strip().casefold()
    candidates: list[tuple[int, GPSData]] = []

    for index, candidate in enumerate(_iter_gps_payload_candidates(payload)):
        try:
            gps = GPSData.from_dict(candidate)
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append((index, gps))

    if not candidates:
        if isinstance(payload, dict):
            return GPSData.from_dict(payload)
        return None

    if normalized_device_id:
        matching = [
            (index, gps)
            for index, gps in candidates
            if str(gps.id or "").strip().casefold() == normalized_device_id
        ]
        if not matching:
            return None
        candidates = matching

    candidates.sort(
        key=lambda item: (
            _parse_timestamp(item[1].timestamp) is not None,
            _parse_timestamp(item[1].timestamp) or float("-inf"),
            item[0],
        )
    )
    return candidates[-1][1]


# =========================
# Modelo
# =========================
@dataclass
class GPSData:
    id: str
    lat: float
    lon: float
    heading: float
    timestamp: str
    _raw: dict = None  # payload completo para campos extra (altitude, speed, battery, etc.)

    def __post_init__(self):
        if self._raw is None:
            self._raw = {}

    def validate(self) -> None:
        if not self.id:
            raise ValueError("id inválido")
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"lat inválida: {self.lat}")
        if not (-180 <= self.lon <= 180):
            raise ValueError(f"lon inválida: {self.lon}")
        if not (0 <= self.heading <= 360):
            raise ValueError(f"heading inválido: {self.heading}")
        if not isinstance(self.timestamp, str) or not self.timestamp.strip():
            raise ValueError("timestamp inválido")

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GPSData":
        nested = _first_nested_mapping(data, "location", "position", "coordinates", "coords", "gps")
        raw_id = (
            _first_present(
                data,
                "id",
                "device_id",
                "vehiculo_id",
                "vehicle_id",
                "drone_id",
                "identifier",
            )
            or (
                _first_present(
                    nested or {},
                    "id",
                    "device_id",
                    "vehiculo_id",
                    "vehicle_id",
                    "drone_id",
                    "identifier",
                )
                if nested is not None
                else None
            )
        )
        gps_id = str(raw_id).strip() if raw_id is not None else ""
        if not gps_id:
            gps_id = "DRON_001"

        lat_raw = _first_present(data, "lat", "latitude", "latitud")
        lon_raw = _first_present(data, "lon", "lng", "longitude", "longitud")
        heading_raw = _first_present(data, "heading", "course", "bearing", "yaw", default=0.0)
        timestamp_raw = _first_present(
            data,
            "timestamp",
            "ts",
            "updated_at",
            "created_at",
            "time",
            "fecha",
            default=None,
        )
        if nested is not None:
            if lat_raw is None:
                lat_raw = _first_present(nested, "lat", "latitude", "latitud")
            if lon_raw is None:
                lon_raw = _first_present(nested, "lon", "lng", "longitude", "longitud")
            if heading_raw in (None, 0.0):
                heading_raw = _first_present(
                    nested,
                    "heading",
                    "course",
                    "bearing",
                    "yaw",
                    default=heading_raw,
                )
            if not timestamp_raw:
                timestamp_raw = _first_present(
                    nested,
                    "timestamp",
                    "ts",
                    "updated_at",
                    "created_at",
                    "time",
                    "fecha",
                    default=timestamp_raw,
                )
        if not timestamp_raw:
            timestamp_raw = datetime.utcnow().isoformat()
        if lat_raw is None or lon_raw is None:
            raise KeyError("lat/lon")

        return cls(
            id=gps_id,
            lat=float(lat_raw),
            lon=float(lon_raw),
            heading=float(heading_raw),
            timestamp=str(timestamp_raw),
            _raw=data if isinstance(data, dict) else {},
        )


# =========================
# Contrato fuente de datos
# =========================
class TelemetrySource(Protocol):
    def connect(self) -> None:
        ...

    def read_gps(self) -> Optional[GPSData]:
        ...


# =========================
# Fuente dummy
# =========================
class DummyDroneSource:
    def __init__(
        self,
        *,
        device_id: str = "ROBIOCAR-001",
        start_lat: float = -2.1894,
        start_lon: float = -79.8891,
        step: float = 0.01,
    ) -> None:
        self.device_id = str(device_id or "ROBIOCAR-001").strip() or "ROBIOCAR-001"
        self.lat = float(start_lat)
        self.lon = float(start_lon)
        self.heading = 90.0
        self.step = abs(float(step))
        self.connected = False

    def connect(self) -> None:
        self.connected = True
        logger.info("DummyDroneSource conectado")

    def read_gps(self) -> Optional[GPSData]:
        if not self.connected:
            self.connect()

        self.lat += self.step
        self.lon += self.step
        self.heading = (self.heading + 1.0) % 360

        return GPSData(
            id=self.device_id,
            lat=self.lat,
            lon=self.lon,
            heading=self.heading,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )


# =========================
# Cliente API
# =========================
class GPSApiClient:
    def __init__(
        self,
        base_url: str = "",
        timeout: float = 5.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = self._build_session(max_retries, backoff_factor)

    def _build_session(self, max_retries: int, backoff_factor: float) -> requests.Session:
        session = requests.Session()

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Robiotec-GPS-Tracker-Menu/1.0",
        })
        return session

    def get_status(self) -> dict:
        url = f"{self.base_url}/"
        response = self.session.get(url, timeout=self.timeout)

        if response.status_code != 200:
            raise RuntimeError(f"Error consultando / : HTTP {response.status_code} - {response.text}")

        return response.json()

    def send_gps(self, gps: GPSData) -> dict:
        url = f"{self.base_url}/update-gps"
        response = self.session.post(url, json=gps.to_dict(), timeout=self.timeout)

        if response.status_code != 200:
            raise RuntimeError(f"Error enviando GPS: HTTP {response.status_code} - {response.text}")

        return response.json()

    def get_latest_gps(
        self,
        device_id: str | None = None,
        *,
        prefer_vehicle_path: bool = False,
    ) -> Optional[GPSData]:
        parsed = urlparse(self.base_url)
        normalized_path = str(parsed.path or "").rstrip("/").lower()
        normalized_device_id = str(device_id or "").strip()

        query_url = self.base_url if normalized_path.endswith("/gps") else f"{self.base_url}/gps"
        per_vehicle_url = ""
        if normalized_device_id and prefer_vehicle_path and not normalized_path.endswith("/gps"):
            if normalized_path.endswith("/telemetry"):
                per_vehicle_url = f"{self.base_url}/{normalized_device_id}/gps"
            elif "/telemetry/" in normalized_path:
                per_vehicle_url = f"{self.base_url}/gps"
            else:
                per_vehicle_url = f"{self.base_url}/telemetry/{normalized_device_id}/gps"

        params: dict[str, str] = {
            "_ts": f"{time.time():.6f}",
        }
        if normalized_device_id:
            params.update(
                {
                    "device_id": normalized_device_id,
                    "id": normalized_device_id,
                    "identifier": normalized_device_id,
                }
            )

        headers = {
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        }

        if per_vehicle_url:
            response = self.session.get(
                per_vehicle_url,
                params={"_ts": params["_ts"]},
                timeout=self.timeout,
                headers=headers,
            )
            if response.status_code == 200:
                payload = response.json()
                return _select_latest_gps_payload(payload, device_id=normalized_device_id)
            if response.status_code != 404:
                raise RuntimeError(
                    f"Error consultando telemetría por ID: HTTP {response.status_code} - {response.text}"
                )

        response = self.session.get(
            query_url,
            params=params,
            timeout=self.timeout,
            headers=headers,
        )

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise RuntimeError(f"Error consultando /gps: HTTP {response.status_code} - {response.text}")

        payload = response.json()
        return _select_latest_gps_payload(payload, device_id=normalized_device_id)

    def close(self) -> None:
        self.session.close()


# =========================
# Servicios
# =========================
class GPSSenderService:
    def __init__(self, source: TelemetrySource, api_client: GPSApiClient, send_interval: float = 1.0) -> None:
        self.source = source
        self.api_client = api_client
        self.send_interval = send_interval

    def run_forever(self) -> None:
        logger.info("Modo ENVÍO iniciado")
        self.source.connect()

        while True:
            start = time.monotonic()

            try:
                gps = self.source.read_gps()

                if gps is None:
                    logger.warning("No se recibió GPS del dron")
                else:
                    response = self.api_client.send_gps(gps)
                    logger.info(
                        "ENVIADO | id=%s | lat=%s | lon=%s | heading=%s | ts=%s | resp=%s",
                        gps.id, gps.lat, gps.lon, gps.heading, gps.timestamp, response
                    )

            except Exception as exc:
                logger.exception("Error en envío GPS: %s", exc)

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, self.send_interval - elapsed))


class GPSReceiverService:
    def __init__(self, api_client: GPSApiClient, poll_interval: float = 1.0, print_repeated: bool = False) -> None:
        self.api_client = api_client
        self.poll_interval = poll_interval
        self.print_repeated = print_repeated
        self._last_seen: Optional[GPSData] = None

    def run_forever(self) -> None:
        logger.info("Modo RECEPCIÓN iniciado")

        while True:
            start = time.monotonic()

            try:
                gps = self.api_client.get_latest_gps()

                if gps is None:
                    logger.warning("La API aún no tiene datos GPS")
                else:
                    changed = gps != self._last_seen
                    if changed or self.print_repeated:
                        print(
                            f"[RECIBIDO] id={gps.id} | lat={gps.lat} | lon={gps.lon} | "
                            f"heading={gps.heading} | timestamp={gps.timestamp}"
                        )
                        self._last_seen = gps

            except Exception as exc:
                logger.exception("Error en recepción GPS: %s", exc)

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, self.poll_interval - elapsed))


class GPSSendAndVerifyService:
    def __init__(self, source: TelemetrySource, api_client: GPSApiClient, send_interval: float = 1.0) -> None:
        self.source = source
        self.api_client = api_client
        self.send_interval = send_interval

    def run_forever(self) -> None:
        logger.info("Modo ENVÍO + VERIFICACIÓN iniciado")
        self.source.connect()

        while True:
            start = time.monotonic()

            try:
                gps = self.source.read_gps()

                if gps is None:
                    logger.warning("No se recibió GPS del dron")
                else:
                    send_response = self.api_client.send_gps(gps)
                    latest = self.api_client.get_latest_gps()

                    logger.info(
                        "ENVIADO | id=%s | lat=%s | lon=%s | heading=%s | ts=%s | resp=%s",
                        gps.id, gps.lat, gps.lon, gps.heading, gps.timestamp, send_response
                    )

                    if latest:
                        print(
                            f"[VERIFICADO API] id={latest.id} | lat={latest.lat} | lon={latest.lon} | "
                            f"heading={latest.heading} | timestamp={latest.timestamp}"
                        )

            except Exception as exc:
                logger.exception("Error en envío/verificación GPS: %s", exc)

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, self.send_interval - elapsed))


# =========================
# Menú
# =========================
def clear_screen() -> None:
    print("\n" * 2)


def choose_source() -> TelemetrySource:
    while True:
        print("\n=== Seleccionar fuente de telemetría ===")
        print("1. Dummy (prueba)")
        option = input("Elige una opción: ").strip()

        if option == "1":
            device_id = input("ID del dispositivo dummy [ROBIOCAR-001]: ").strip() or "ROBIOCAR-001"
            start_lat = ask_float("Latitud inicial", -2.1894)
            start_lon = ask_float("Longitud inicial", -79.8891)
            step = ask_float("Desplazamiento por lectura (grados)", 0.01)
            return DummyDroneSource(
                device_id=device_id,
                start_lat=start_lat,
                start_lon=start_lon,
                step=step,
            )

        print("Opción inválida. Intenta de nuevo.\n")


def ask_float(prompt: str, default: float) -> float:
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print("Valor inválido, se usará el valor por defecto.")
        return default


def print_menu() -> None:
    print("\n==============================")
    print("   GPS TRACKER API - MENÚ")
    print("==============================")
    print("1. Enviar datos del dron a la API")
    print("2. Recibir datos de la API en tiempo real")
    print("3. Enviar y verificar lo publicado en la API")
    print("4. Ver estado de la API")
    print("5. Obtener una sola lectura desde /gps")
    print("6. Salir")
    print("==============================")


def run_menu() -> None:
    base_url = input("Base URL de la API: ").strip()

    api_client = GPSApiClient(base_url=base_url)

    try:
        while True:
            print_menu()
            choice = input("Selecciona una opción: ").strip()

            if choice == "1":
                source = choose_source()
                send_interval = ask_float("Intervalo de envío en segundos", 1.0)

                service = GPSSenderService(
                    source=source,
                    api_client=api_client,
                    send_interval=send_interval,
                )

                print("\nIniciando modo envío. Presiona CTRL+C para volver al menú.\n")
                try:
                    service.run_forever()
                except KeyboardInterrupt:
                    logger.info("Regresando al menú principal...")

            elif choice == "2":
                poll_interval = ask_float("Intervalo de consulta en segundos", 1.0)
                repeated = input("¿Imprimir aunque no cambie? (s/n) [n]: ").strip().lower()
                print_repeated = repeated == "s"

                service = GPSReceiverService(
                    api_client=api_client,
                    poll_interval=poll_interval,
                    print_repeated=print_repeated,
                )

                print("\nIniciando modo recepción. Presiona CTRL+C para volver al menú.\n")
                try:
                    service.run_forever()
                except KeyboardInterrupt:
                    logger.info("Regresando al menú principal...")

            elif choice == "3":
                source = choose_source()
                send_interval = ask_float("Intervalo de envío en segundos", 1.0)

                service = GPSSendAndVerifyService(
                    source=source,
                    api_client=api_client,
                    send_interval=send_interval,
                )

                print("\nIniciando modo envío + verificación. Presiona CTRL+C para volver al menú.\n")
                try:
                    service.run_forever()
                except KeyboardInterrupt:
                    logger.info("Regresando al menú principal...")

            elif choice == "4":
                try:
                    status = api_client.get_status()
                    print("\nEstado API:")
                    print(status)
                except Exception as exc:
                    print(f"\nError consultando estado de la API: {exc}")

            elif choice == "5":
                try:
                    device_id = input("ID a consultar [vacío=último disponible]: ").strip() or None
                    gps = api_client.get_latest_gps(device_id=device_id)
                    if gps is None:
                        print("\nLa API no tiene datos GPS todavía.")
                    else:
                        print("\nÚltima lectura GPS:")
                        print(gps)
                except Exception as exc:
                    print(f"\nError consultando /gps: {exc}")

            elif choice == "6":
                print("\nSaliendo...")
                break

            else:
                print("\nOpción inválida. Intenta de nuevo.")

    finally:
        api_client.close()


if __name__ == "__main__":
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    run_menu()
