"""Configuración de base de datos. Usa la fuente única de verdad: core/config.py → settings."""
from __future__ import annotations

from dataclasses import dataclass
from app.core.config import settings


@dataclass(frozen=True)
class DBConfig:
    host: str = settings.DB_HOST
    port: int = settings.DB_PORT
    name: str = settings.DB_NAME
    user: str = settings.DB_USER
    password: str = settings.DB_PASSWORD
    min_size: int = settings.DB_MIN_SIZE
    max_size: int = settings.DB_MAX_SIZE
    timeout: int = settings.DB_TIMEOUT
    connect_timeout: int = settings.DB_CONNECT_TIMEOUT

    @property
    def dsn(self) -> str:
        return settings.db_dsn


db_config = DBConfig()

if __name__ == "__main__":
    print(db_config.dsn)