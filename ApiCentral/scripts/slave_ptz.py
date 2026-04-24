import time
import threading
import logging
from typing import Optional, Dict, Any

import requests
from requests.auth import HTTPDigestAuth
from requests.packages.urllib3.exceptions import InsecureRequestWarning


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

API_BASE = "http://136.119.96.176:8003"
POLL_INTERVAL = 0.25
DEFAULT_SPEED = 20
DEFAULT_DURATION = 0.30
REQUEST_TIMEOUT = 5
API_RETRY_DELAY = 1.0

# =========================================================
# CONFIGURACIÓN DE LOGS
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
)
logger = logging.getLogger("ptz_client")

# =========================================================
# CONFIGURACIÓN DE CÁMARAS
# =========================================================
CAMERAS = [
    {
        "camera_id": "cam_ptz_1",
        "ip": "192.168.1.215",
        "user": "admin",
        "password": "Robiotec@2025",
        "channel": 1,
        "use_https": False,
    },
    {
        "camera_id": "cam_ptz_2",
        "ip": "192.168.1.64",
        "user": "admin",
        "password": "Robiotec@2025",
        "channel": 1,
        "use_https": False,
    },
]


# =========================================================
# CLIENTE ISAPI HIKVISION
# =========================================================
class HikvisionISAPI:
    def __init__(self, ip: str, user: str, password: str, use_https: bool = False, timeout: int = 5):
        proto = "https" if use_https else "http"
        self.base_url = f"{proto}://{ip}"
        self.auth = HTTPDigestAuth(user, password)
        self.timeout = timeout
        self.session = requests.Session()

    def ptz_continuous(self, channel: int = 1, pan: int = 0, tilt: int = 0, zoom: int = 0) -> str:
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData>
    <pan>{pan}</pan>
    <tilt>{tilt}</tilt>
    <zoom>{zoom}</zoom>
</PTZData>"""

        url = f"{self.base_url}/ISAPI/PTZCtrl/channels/{channel}/continuous"

        response = self.session.put(
            url,
            data=body.encode("utf-8"),
            auth=self.auth,
            headers={"Content-Type": "application/xml"},
            timeout=self.timeout,
            verify=False,
        )
        response.raise_for_status()
        return response.text

    def ptz_stop(self, channel: int = 1) -> str:
        return self.ptz_continuous(channel=channel, pan=0, tilt=0, zoom=0)


# =========================================================
# MAPEO DE COMANDOS
# =========================================================
def get_ptz_values(command: str, speed: int):
    speed = int(speed)

    mapping = {
        "up":        (0, speed, 0),
        "down":      (0, -speed, 0),
        "left":      (-speed, 0, 0),
        "right":     (speed, 0, 0),
        "upleft":    (-speed, speed, 0),
        "upright":   (speed, speed, 0),
        "downleft":  (-speed, -speed, 0),
        "downright": (speed, -speed, 0),
        "zoomin":    (0, 0, speed),
        "zoomout":   (0, 0, -speed),
        "stop":      (0, 0, 0),
    }

    return mapping.get(command)


def execute_command(cam: HikvisionISAPI, channel: int, command: str, speed: int, duration: float):
    speed = int(speed or DEFAULT_SPEED)
    duration = float(duration or DEFAULT_DURATION)

    values = get_ptz_values(command, speed)
    if values is None:
        raise ValueError(f"Comando desconocido: {command}")

    pan, tilt, zoom = values

    if command == "stop":
        cam.ptz_stop(channel)
        return

    cam.ptz_continuous(channel=channel, pan=pan, tilt=tilt, zoom=zoom)

    if duration > 0:
        time.sleep(duration)

    cam.ptz_stop(channel)


# =========================================================
# API CLIENT
# =========================================================
class APIClient:
    def __init__(self, base_url: str, timeout: int = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_command(self, camera_id: str) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/ptz/command/{camera_id}",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def send_ack(
        self,
        camera_id: str,
        command_id: str,
        status: str = "done",
        detail: Optional[Any] = None
    ) -> Dict[str, Any]:
        payload = {
            "camera_id": camera_id,
            "command_id": command_id,
            "status": status,
        }

        if detail is not None:
            payload["detail"] = detail

        response = self.session.post(
            f"{self.base_url}/ptz/ack",
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json() if response.content else {"ok": True}


# =========================================================
# VALIDACIÓN DE RESPUESTA
# =========================================================
def parse_pending_command(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError("La respuesta de la API no es un objeto JSON válido.")

    pending = data.get("pending", False)
    if not pending:
        return None

    cmd = data.get("data")
    if not isinstance(cmd, dict):
        raise ValueError("La API indicó pending=True pero no devolvió data válida.")

    required_fields = ["command_id", "camera_id", "command"]
    for field in required_fields:
        if field not in cmd or cmd[field] in [None, ""]:
            raise ValueError(f"Falta campo requerido en comando: {field}")

    if "speed" not in cmd or cmd["speed"] is None:
        cmd["speed"] = DEFAULT_SPEED

    if "duration" not in cmd or cmd["duration"] is None:
        cmd["duration"] = DEFAULT_DURATION

    return cmd


# =========================================================
# WORKER POR CÁMARA
# =========================================================
def camera_worker(camera_cfg: Dict[str, Any]):
    camera_id = camera_cfg["camera_id"]
    channel = camera_cfg.get("channel", 1)

    cam = HikvisionISAPI(
        ip=camera_cfg["ip"],
        user=camera_cfg["user"],
        password=camera_cfg["password"],
        use_https=camera_cfg.get("use_https", False),
        timeout=REQUEST_TIMEOUT,
    )

    api = APIClient(API_BASE, timeout=REQUEST_TIMEOUT)

    logger.info(f"[{camera_id}] Worker iniciado para IP {camera_cfg['ip']}")

    while True:
        current_command_id = None

        try:
            data = api.fetch_command(camera_id)
            cmd = parse_pending_command(data)

            if cmd is None:
                time.sleep(POLL_INTERVAL)
                continue

            current_command_id = cmd["command_id"]
            command = cmd["command"]
            speed = cmd.get("speed", DEFAULT_SPEED)
            duration = cmd.get("duration", DEFAULT_DURATION)

            logger.info(
                f"[{camera_id}] Ejecutando command_id={current_command_id} "
                f"command={command} speed={speed} duration={duration}"
            )

            execute_command(
                cam=cam,
                channel=channel,
                command=command,
                speed=speed,
                duration=duration
            )

            ack_response = api.send_ack(
                camera_id=camera_id,
                command_id=current_command_id,
                status="done",
                detail={
                    "command": command,
                    "speed": speed,
                    "duration": duration,
                }
            )

            logger.info(f"[{camera_id}] ACK enviado correctamente: {ack_response}")

            time.sleep(POLL_INTERVAL)

        except requests.exceptions.RequestException as e:
            logger.error(f"[{camera_id}] ERROR API/HTTP: {e}")
            time.sleep(API_RETRY_DELAY)

        except Exception as e:
            logger.error(f"[{camera_id}] ERROR GENERAL: {e}")

            if current_command_id:
                try:
                    api.send_ack(
                        camera_id=camera_id,
                        command_id=current_command_id,
                        status="error",
                        detail=str(e)
                    )
                    logger.info(f"[{camera_id}] ACK de error enviado")
                except Exception as ack_err:
                    logger.error(f"[{camera_id}] ERROR enviando ACK de error: {ack_err}")

            time.sleep(API_RETRY_DELAY)


# =========================================================
# MAIN
# =========================================================
def main():
    logger.info("Iniciando agente PTZ multi-cámara...")

    threads = []

    for camera_cfg in CAMERAS:
        thread_name = f"worker-{camera_cfg['camera_id']}"
        t = threading.Thread(
            target=camera_worker,
            args=(camera_cfg,),
            daemon=True,
            name=thread_name,
        )
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Cierre solicitado por usuario. Finalizando agente PTZ...")


if __name__ == "__main__":
    main()