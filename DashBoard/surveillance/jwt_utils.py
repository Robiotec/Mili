from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from surveillance import settings

JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_TTL_SEC = settings.JWT_ACCESS_TOKEN_TTL_SECONDS


def encode_jwt(payload: dict[str, Any], *, secret: str | None = None) -> str:
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    encoded_header = _b64url_json(header)
    encoded_payload = _b64url_json(payload)
    signature = _sign(f"{encoded_header}.{encoded_payload}", secret=secret)
    return f"{encoded_header}.{encoded_payload}.{signature}"


def decode_jwt(token: str, *, secret: str | None = None) -> dict[str, Any] | None:
    raw_token = str(token or "").strip()
    if raw_token.count(".") != 2:
        return None
    encoded_header, encoded_payload, encoded_signature = raw_token.split(".", 2)
    expected_signature = _sign(f"{encoded_header}.{encoded_payload}", secret=secret)
    if not hmac.compare_digest(encoded_signature, expected_signature):
        return None
    try:
        header = _json_from_b64url(encoded_header)
        payload = _json_from_b64url(encoded_payload)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None
    if header.get("alg") != JWT_ALGORITHM:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        return None
    return payload


def issue_access_token(
    *,
    user_id: int,
    username: str,
    role: str,
    role_level: int | None = None,
    expires_in: int | None = None,
) -> tuple[str, int]:
    issued_at = int(time.time())
    ttl = expires_in if isinstance(expires_in, int) and expires_in > 0 else JWT_ACCESS_TOKEN_TTL_SEC
    expires_at = issued_at + ttl
    payload = {
        "sub": str(user_id),
        "usuario": username,
        "rol": role,
        "nivel_orden": role_level if isinstance(role_level, int) and role_level > 0 else None,
        "iat": issued_at,
        "exp": expires_at,
    }
    return encode_jwt(payload), ttl


def _sign(value: str, *, secret: str | None = None) -> str:
    signing_secret = (secret or JWT_SECRET).encode("utf-8")
    digest = hmac.new(signing_secret, value.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_bytes(digest)


def _b64url_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64url_bytes(raw)


def _b64url_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _json_from_b64url(value: str) -> Any:
    padding = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    return json.loads(raw.decode("utf-8"))
