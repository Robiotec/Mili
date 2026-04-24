#!/usr/bin/env python3
"""Seed/upsert de usuarios en PostgreSQL para API Central."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

# Permite ejecutar este script directamente desde scripts/
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.security import get_password_hash
from app.db.config import db_config

# Parametros editables en el script
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Robiotec@2025"
DEFAULT_ROLE = "admin"


def upsert_user(username: str, password: str, role: str) -> None:
    password_hash = get_password_hash(password)

    with psycopg.connect(db_config.dsn) as conn:
        with conn.cursor() as cur:
            # Asegura que el rol exista
            cur.execute("SELECT id FROM roles WHERE rol = %s", (role,))
            role_row = cur.fetchone()
            if role_row:
                role_id = role_row[0]
            else:
                cur.execute("INSERT INTO roles (rol) VALUES (%s) RETURNING id", (role,))
                role_id = cur.fetchone()[0]

            # Upsert por usuario
            cur.execute("SELECT id FROM usuarios WHERE usuario = %s", (username,))
            user_row = cur.fetchone()

            if user_row:
                cur.execute(
                    "UPDATE usuarios SET password = %s, rol_id = %s WHERE id = %s",
                    (password_hash, role_id, user_row[0]),
                )
                action = "actualizado"
            else:
                cur.execute(
                    "INSERT INTO usuarios (usuario, password, rol_id) VALUES (%s, %s, %s)",
                    (username, password_hash, role_id),
                )
                action = "insertado"

        conn.commit()

    print(f"Usuario '{username}' {action} con rol '{role}'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inserta o actualiza un usuario en la DB")
    parser.add_argument("--username", help="Nombre de usuario (override de DEFAULT_USERNAME)")
    parser.add_argument("--password", help="Password en texto plano (override de DEFAULT_PASSWORD)")
    parser.add_argument("--role", help="Rol (override de DEFAULT_ROLE)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    username = (args.username or DEFAULT_USERNAME).strip()
    password = args.password if args.password is not None else DEFAULT_PASSWORD
    role = (args.role or DEFAULT_ROLE).strip()

    if not username:
        print("ERROR: username no puede estar vacio")
        return 1

    if not password:
        print("ERROR: password no puede estar vacio")
        return 1

    if not role:
        print("ERROR: role no puede estar vacio")
        return 1

    try:
        upsert_user(username, password, role)
        return 0
    except Exception as exc:
        print(f"ERROR: no se pudo insertar/actualizar usuario: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
