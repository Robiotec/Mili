"""Configuración de base de datos. Usa la fuente única de verdad: core/config.py → settings."""
from __future__ import annotations

from dataclasses import dataclass
from app.core.config import settings


@dataclass(frozen=True)
class DBConfig:
    host: str = settings.db_host
    port: int = settings.db_port
    name: str = settings.db_name
    user: str = settings.db_user
    password: str = settings.db_password
    min_size: int = settings.db_min_size
    max_size: int = settings.db_max_size
    timeout: int = settings.db_timeout
    connect_timeout: int = settings.db_connect_timeout

    @property
    def dsn(self) -> str:
        return settings.db_dsn


db_config = DBConfig()

if __name__ == "__main__":
    print(db_config.dsn)