from __future__ import annotations

import base64
import hashlib
import hmac
import os


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "390000"))
PASSWORD_SALT_BYTES = int(os.getenv("PASSWORD_SALT_BYTES", "16"))


def hash_password(password: str) -> str:
    raw_password = str(password or "")
    if not raw_password:
        raise ValueError("invalid_password")

    salt = os.urandom(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${encoded_salt}${encoded_digest}"


def verify_password(password: str, stored_value: str) -> bool:
    raw_password = str(password or "")
    stored = str(stored_value or "")
    if not raw_password or not stored:
        return False

    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_SCHEME:
        # Compatibilidad hacia atras con contraseñas historicas en texto plano.
        return hmac.compare_digest(stored, raw_password)

    _, raw_iterations, encoded_salt, encoded_digest = parts
    try:
        iterations = int(raw_iterations)
    except ValueError:
        return False

    salt = _decode_base64url(encoded_salt)
    expected_digest = _decode_base64url(encoded_digest)
    derived_digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(derived_digest, expected_digest)


def password_needs_rehash(stored_value: str) -> bool:
    stored = str(stored_value or "")
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_SCHEME:
        return True
    try:
        iterations = int(parts[1])
    except ValueError:
        return True
    return iterations < PASSWORD_ITERATIONS


def _decode_base64url(value: str) -> bytes:
    normalized = str(value or "")
    padding = "=" * (-len(normalized) % 4)
    return base64.urlsafe_b64decode(f"{normalized}{padding}".encode("ascii"))
