from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Dict, Any
import time
import uuid
import threading

router = APIRouter()

commands: Dict[str, Dict[str, Any]] = {}
commands_lock = threading.Lock()

PTZCommandType = Literal[
    "up", "down", "left", "right",
    "upleft", "upright", "downleft", "downright",
    "zoomin", "zoomout", "stop"
]

PTZStatusType = Literal["pending", "taken", "done", "error"]

TAKEN_TIMEOUT_SECONDS = 5.0


class PTZCommand(BaseModel):
    camera_id: str = Field(..., example="cam_ptz_1", description="ID único de la cámara")
    command: PTZCommandType = Field(..., example="left", description="Comando PTZ")
    speed: Optional[int] = Field(20, example=20, description="Velocidad del movimiento")
    duration: Optional[float] = Field(0.3, example=0.5, description="Tiempo en segundos")

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, v):
        if v is None:
            return 20
        if v < 1 or v > 100:
            raise ValueError("speed debe estar entre 1 y 100")
        return v

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v):
        if v is None:
            return 0.3
        if v < 0 or v > 10:
            raise ValueError("duration debe estar entre 0 y 10 segundos")
        return v


class AckBody(BaseModel):
    camera_id: str = Field(..., example="cam_ptz_1", description="ID de la cámara ejecutada")
    command_id: str = Field(..., example="f3f7d8c4-b1d0-4f89-a81f-6f4d4c8b1f8c", description="ID único del comando")
    status: PTZStatusType = Field("done", example="done", description="Estado final del comando")
    detail: Optional[Any] = Field(None, description="Información adicional o mensaje de error")


def now_ts() -> float:
    return time.time()


def build_command_record(cmd: PTZCommand) -> Dict[str, Any]:
    command_id = str(uuid.uuid4())
    return {
        "command_id": command_id,
        "camera_id": cmd.camera_id,
        "command": cmd.command,
        "speed": cmd.speed if cmd.speed is not None else 20,
        "duration": cmd.duration if cmd.duration is not None else 0.3,
        "ts": now_ts(),
        "taken_at": None,
        "done_at": None,
        "status": "pending",
        "detail": None,
    }


def is_taken_expired(cmd: Dict[str, Any]) -> bool:
    if cmd["status"] != "taken":
        return False
    taken_at = cmd.get("taken_at")
    if taken_at is None:
        return False
    return (now_ts() - taken_at) > TAKEN_TIMEOUT_SECONDS


@router.post("/command", summary="Enviar comando PTZ", tags=["ptz"])
def post_command(cmd: PTZCommand):
    record = build_command_record(cmd)

    with commands_lock:
        previous = commands.get(cmd.camera_id)
        commands[cmd.camera_id] = record

    return {
        "ok": True,
        "msg": "comando registrado",
        "replaced_previous": (
            previous is not None and previous["status"] in ["pending", "taken"]
            if previous else False
        ),
        "data": record
    }


@router.get("/command/{camera_id}", summary="Obtener comando PTZ pendiente", tags=["ptz"])
def get_command(camera_id: str):
    with commands_lock:
        cmd = commands.get(camera_id)

        if not cmd:
            return {"pending": False}

        if is_taken_expired(cmd):
            cmd["status"] = "pending"
            cmd["taken_at"] = None

        if cmd["status"] != "pending":
            return {"pending": False}

        cmd["status"] = "taken"
        cmd["taken_at"] = now_ts()

        return {"pending": True, "data": cmd}


@router.post("/ack", summary="Confirmar ejecución del comando", tags=["ptz"])
def ack_command(body: AckBody):
    with commands_lock:
        cmd = commands.get(body.camera_id)

        if not cmd:
            raise HTTPException(status_code=404, detail="camera_id no encontrado")

        if cmd["command_id"] != body.command_id:
            raise HTTPException(
                status_code=409,
                detail="command_id no coincide con el comando activo de la cámara"
            )

        cmd["status"] = body.status
        cmd["done_at"] = now_ts()
        cmd["detail"] = body.detail

        return {"ok": True, "msg": "ack registrado", "data": cmd}


@router.get("/status/{camera_id}", summary="Consultar estado de la cámara", tags=["ptz"])
def get_camera_status(camera_id: str):
    with commands_lock:
        cmd = commands.get(camera_id)
        if not cmd:
            return {"ok": False, "msg": "sin comandos para esta cámara"}
        return {"ok": True, "data": cmd}


@router.get("/commands", summary="Listar comandos actuales", tags=["ptz"])
def list_commands():
    with commands_lock:
        return {"ok": True, "count": len(commands), "data": list(commands.values())}


@router.delete("/command/{camera_id}", summary="Eliminar comando de una cámara", tags=["ptz"])
def delete_command(camera_id: str):
    with commands_lock:
        cmd = commands.pop(camera_id, None)
        if not cmd:
            raise HTTPException(status_code=404, detail="camera_id no encontrado")
        return {"ok": True, "msg": "comando eliminado", "data": cmd}