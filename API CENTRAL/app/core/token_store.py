"""
Token store - Tokens opacos para acceso a MediaMTX.

Tipos de token:
  - stream_read:  Dashboard ve un stream (single-use por IP)
  - publish:      R-Box publica RTSP
  - service:      Servidor de inferencia lee + publica

MediaMTX llama a /auth/validate (POST) con {user, password, path, action, protocol, ip, query}.
El token viaja como:
  - RTSP: campo password (rtsp://user:TOKEN@host/path)
  - WebRTC/HLS: query param (?token=TOKEN)
"""
import secrets
import threading
import time
import uuid
from typing import Optional


class OpaqueTokenStore:
    CLEANUP_INTERVAL = 120  # segundos entre limpiezas automáticas

    def __init__(self):
        self._tokens: dict[str, dict] = {}   # token_value -> metadata
        self._id_map: dict[str, str] = {}     # token_id -> token_value
        self._lock = threading.Lock()
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """Hilo daemon que limpia tokens expirados periódicamente."""
        t = threading.Thread(target=self._periodic_cleanup, daemon=True)
        t.start()

    def _periodic_cleanup(self):
        while True:
            time.sleep(self.CLEANUP_INTERVAL)
            self._cleanup()

    def create_token(
        self,
        token_type: str,
        company_id: str,
        paths: list[str],
        actions: list[str],
        expires_in: int = 900,
        single_use: bool = False,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> tuple[str, str, str]:
        """Crea un token opaco. Retorna (token_value, token_id, session_secret)."""
        self._cleanup()
        token_value = secrets.token_urlsafe(32)
        token_id = str(uuid.uuid4())[:8]
        session_secret = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens[token_value] = {
                "token_id": token_id,
                "type": token_type,
                "company_id": company_id,
                "user_id": user_id,
                "device_id": device_id,
                "paths": paths,
                "actions": actions,
                "created_at": time.time(),
                "expires_at": time.time() + expires_in,
                "single_use": single_use,
                "claimed_by_ip": None,
                "session_secret": session_secret,
                "session_claimed": False,
                "revoked": False,
            }
            self._id_map[token_id] = token_value
        return token_value, token_id, session_secret

    def validate(self, token: str, path: str, action: str, ip: str = "") -> tuple[bool, str]:
        """Valida un token opaco contra path y action. Retorna (allowed, reason)."""
        self._cleanup()
        with self._lock:
            entry = self._tokens.get(token)
            if not entry:
                return False, "Token no encontrado"
            if entry["revoked"]:
                return False, "Token revocado"
            if entry["expires_at"] < time.time():
                return False, "Token expirado"
            if action not in entry["actions"]:
                return False, f"Acción '{action}' no permitida"
            if path not in entry["paths"] and "*" not in entry["paths"]:
                return False, f"Path '{path}' no autorizado"
            if entry["single_use"]:
                if entry["claimed_by_ip"] is None:
                    entry["claimed_by_ip"] = ip
                elif entry["claimed_by_ip"] != ip:
                    return False, "Token ya usado por otra IP"
            return True, "OK"

    def validate_session(self, token: str, session_secret: str) -> tuple[bool, str]:
        """Valida que el session_secret coincida con el token. Retorna (allowed, reason)."""
        with self._lock:
            entry = self._tokens.get(token)
            if not entry:
                return False, "Token no encontrado"
            if entry["revoked"]:
                return False, "Token revocado"
            if entry["expires_at"] < time.time():
                return False, "Token expirado"
            if entry.get("session_secret") != session_secret:
                return False, "ROBIOTEC PROTEGE A SUS CLIENTES"
            if entry.get("session_claimed"):
                # Ya fue reclamado, solo permitir si el secret coincide (ya verificado arriba)
                return True, "OK"
            # Marcar como reclamado
            entry["session_claimed"] = True
            return True, "OK"

    def revoke_by_id(self, token_id: str) -> bool:
        """Revoca un token por su token_id."""
        with self._lock:
            token_value = self._id_map.get(token_id)
            if token_value and token_value in self._tokens:
                self._tokens[token_value]["revoked"] = True
                return True
            return False

    def get_active(self, company_id: str = None) -> list[dict]:
        """Lista tokens activos, opcionalmente filtrados por company_id."""
        self._cleanup()
        with self._lock:
            result = []
            for entry in self._tokens.values():
                if entry["revoked"]:
                    continue
                if company_id and entry["company_id"] != company_id:
                    continue
                result.append({
                    "token_id": entry["token_id"],
                    "type": entry["type"],
                    "paths": entry["paths"],
                    "actions": entry["actions"],
                    "company_id": entry["company_id"],
                    "user_id": entry["user_id"],
                    "device_id": entry["device_id"],
                    "created_at": entry["created_at"],
                    "expires_at": entry["expires_at"],
                    "single_use": entry["single_use"],
                    "claimed_by_ip": entry["claimed_by_ip"],
                })
            return result

    def _cleanup(self):
        now = time.time()
        with self._lock:
            expired = [t for t, e in self._tokens.items() if e["expires_at"] < now]
            for t in expired:
                tid = self._tokens[t].get("token_id")
                del self._tokens[t]
                if tid and tid in self._id_map:
                    del self._id_map[tid]


token_store = OpaqueTokenStore()
