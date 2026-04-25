from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class DBConfig:
    host: str = os.getenv("DB_HOST", "127.0.0.1")
    port: int = int(os.getenv("DB_PORT", "5432"))
    name: str = os.getenv("DB_NAME", "dashboard")
    user: str = os.getenv("DB_USER", "dashboarduser")
    password: str = os.getenv("DB_PASSWORD", "")
    min_size: int = int(os.getenv("DB_MIN_SIZE", "1"))
    max_size: int = int(os.getenv("DB_MAX_SIZE", "10"))
    timeout: int = int(os.getenv("DB_TIMEOUT", "10"))
    connect_timeout: int = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.name} "
            f"user={self.user} "
            f"password={self.password} "
            f"connect_timeout={self.connect_timeout}"
        )

db_config = DBConfig()

if __name__ == "__main__":
    print(db_config.dsn)