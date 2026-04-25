import os
import sys
import time
import requests
from pymavlink import mavutil
from datetime import datetime, timezone

API_URL      = os.getenv("TELEMETRY_API_URL", "http://127.0.0.1:8004/telemetry/DRONE/update-gps")
MAV_CONNECTION      = os.getenv("MAV_CONNECTION", "udp:127.0.0.1:14560")
SEND_INTERVAL_SEC   = float(os.getenv("SEND_INTERVAL_SEC", "1.0"))
RECONNECT_DELAY_SEC = float(os.getenv("RECONNECT_DELAY_SEC", "5.0"))
DRONE_TIMEOUT_SEC   = float(os.getenv("DRONE_TIMEOUT_SEC", "10.0"))

SYSTEM_STATUS_MAP = {
    0: "UNINIT", 1: "BOOT", 2: "CALIBRATING", 3: "STANDBY",
    4: "ACTIVE", 5: "CRITICAL", 6: "EMERGENCY", 7: "POWEROFF", 8: "FLIGHT_TERMINATION",
}

FLIGHT_MODES_COPTER = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED",
    5: "LOITER", 6: "RTL", 7: "CIRCLE", 9: "LAND", 11: "DRIFT",
    13: "SPORT", 14: "FLIP", 15: "AUTOTUNE", 16: "POSHOLD", 17: "BRAKE",
    18: "THROW", 19: "AVOID_ADSB", 20: "GUIDED_NOGPS", 21: "SMART_RTL",
    22: "FLOWHOLD", 23: "FOLLOW", 24: "ZIGZAG",
}

FLIGHT_MODES_PLANE = {
    0: "MANUAL", 1: "CIRCLE", 2: "STABILIZE", 3: "TRAINING", 4: "ACRO",
    5: "FLY_BY_WIRE_A", 6: "FLY_BY_WIRE_B", 7: "CRUISE", 8: "AUTOTUNE",
    10: "AUTO", 11: "RTL", 12: "LOITER", 14: "LAND", 15: "GUIDED",
    16: "INITIALISING", 17: "QSTABILIZE", 18: "QHOVER", 19: "QLOITER",
    20: "QLAND", 21: "QRTL",
}


def resolve_mode(custom_mode: int, autopilot: int, vehicle_type: int) -> str:
    if vehicle_type in (2, 13):
        return FLIGHT_MODES_COPTER.get(custom_mode, f"MODE_{custom_mode}")
    if vehicle_type == 1:
        return FLIGHT_MODES_PLANE.get(custom_mode, f"MODE_{custom_mode}")
    return f"MODE_{custom_mode}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def build_state() -> dict:
    return {
        "lat": None,
        "lon": None,
        "altitude": None,
        "speed": None,
        "heading": None,
        "timestamp": None,
        "battery_remaining_pct": None,
        "battery_voltage_v": None,
        "current_battery_a": None,
        "armed": None,
        "mode": None,
        "system_status_text": None,
        "gps_fix_type": None,
        "satellites_visible": None,
    }


def build_payload(state: dict, drone_online: bool) -> dict:
    if drone_online:
        payload = {k: v for k, v in state.items() if v is not None}
        payload["sistema"] = state.get("system_status_text") or "UNKNOWN"
        payload["estado"]  = "ARMADO" if state.get("armed") else "DESARMADO"
        return payload

    payload = {
        "armed": False,
        "mode": "OFFLINE",
        "system_status_text": "OFFLINE",
        "sistema": "OFFLINE",
        "estado": "DESARMADO",
        "timestamp": utc_now_iso(),
    }
    if state["lat"] is not None:
        payload["lat"] = state["lat"]
        payload["lon"] = state["lon"]
    return payload


def main():
    log(f"Iniciando robiotecTelemetry. Conexión: {MAV_CONNECTION}  →  API: {API_URL}")
    session = requests.Session()
    state = build_state()
    last_send = time.monotonic()
    last_heartbeat_mono: float | None = None

    while True:
        log(f"Abriendo conexión MAVLink en {MAV_CONNECTION}...")
        try:
            mav = mavutil.mavlink_connection(MAV_CONNECTION)
        except Exception as exc:
            log(f"[ERROR] No se pudo abrir conexión MAVLink: {exc}. Reintentando en {RECONNECT_DELAY_SEC}s...")
            time.sleep(RECONNECT_DELAY_SEC)
            continue

        log("Conexión MAVLink abierta. Esperando mensajes del dron...")

        try:
            while True:
                try:
                    msg = mav.recv_match(blocking=True, timeout=0.1)
                except Exception as exc:
                    log(f"[WARN] Error recibiendo mensaje MAVLink: {exc}")
                    msg = None

                if msg:
                    t = msg.get_type()

                    if t == "GLOBAL_POSITION_INT":
                        state["lat"] = msg.lat / 1e7
                        state["lon"] = msg.lon / 1e7
                        state["altitude"] = round(msg.alt / 1000, 2)
                        state["speed"] = round(
                            ((msg.vx ** 2 + msg.vy ** 2 + msg.vz ** 2) ** 0.5) / 100 * 3.6, 2
                        )
                        state["heading"] = round(msg.hdg / 100, 2) if msg.hdg != 65535 else None
                        state["timestamp"] = utc_now_iso()

                    elif t == "BATTERY_STATUS":
                        pct = msg.battery_remaining
                        state["battery_remaining_pct"] = pct if pct != -1 else None
                        v = msg.voltages[0] if msg.voltages and msg.voltages[0] != 65535 else None
                        state["battery_voltage_v"] = round(v / 1000, 3) if v else None
                        i = msg.current_battery
                        state["current_battery_a"] = round(i / 100, 2) if i != -1 else None

                    elif t == "HEARTBEAT":
                        base_mode = msg.base_mode
                        state["armed"] = bool(base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        state["mode"] = resolve_mode(msg.custom_mode, msg.autopilot, msg.type)
                        state["system_status_text"] = SYSTEM_STATUS_MAP.get(
                            msg.system_status, str(msg.system_status)
                        )
                        last_heartbeat_mono = time.monotonic()

                    elif t == "GPS_RAW_INT":
                        state["gps_fix_type"] = msg.fix_type
                        state["satellites_visible"] = (
                            msg.satellites_visible if msg.satellites_visible != 255 else None
                        )

                now = time.monotonic()
                if now - last_send >= SEND_INTERVAL_SEC:
                    drone_online = (
                        last_heartbeat_mono is not None
                        and now - last_heartbeat_mono < DRONE_TIMEOUT_SEC
                    )
                    payload = build_payload(state, drone_online)
                    try:
                        resp = session.post(API_URL, json=payload, timeout=3)
                        if drone_online:
                            estado  = "ARMADO" if state["armed"] else "DESARMADO"
                            sistema = state.get("system_status_text") or "UNKNOWN"
                            log(
                                f"[OK {resp.status_code}] lat={state['lat']} lon={state['lon']} "
                                f"alt={state['altitude']}m spd={state['speed']}km/h "
                                f"bat={state['battery_remaining_pct']}% "
                                f"sistema={sistema} estado={estado} mode={state['mode']}"
                            )
                        else:
                            log(f"[OK {resp.status_code}] dron OFFLINE — enviando ceros")
                    except Exception as exc:
                        log(f"[ERROR] No se pudo enviar a API: {exc}")
                    last_send = now

        except KeyboardInterrupt:
            log("Detenido por usuario.")
            sys.exit(0)
        except Exception as exc:
            log(f"[ERROR] Fallo en bucle MAVLink: {exc}. Reconectando en {RECONNECT_DELAY_SEC}s...")
            try:
                mav.close()
            except Exception:
                pass
            state = build_state()
            last_heartbeat_mono = None
            time.sleep(RECONNECT_DELAY_SEC)


if __name__ == "__main__":
    main()
