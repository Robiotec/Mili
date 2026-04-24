from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field

# Siempre buscar .env desde la raíz del proyecto, sin importar desde dónde se ejecute
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Configuración centralizada. TODOS los valores vienen de .env o variables de entorno."""

    # ── General ──
    public_host: str = "136.119.96.176"
    api_port: int = 8003

    # ── JWT ──
    secret_key: str = Field(..., description="Clave secreta para JWT. Mínimo 32 caracteres.")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    playback_token_expire_minutes: int = 15

    # ── MediaMTX ──
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    mediamtx_api_username: Optional[str] = None
    mediamtx_api_password: Optional[str] = None

    # ── PostgreSQL ──
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "vigilancia"
    db_user: str = "postgres"
    db_password: str = ""
    db_min_size: int = 1
    db_max_size: int = 10
    db_timeout: int = 10
    db_connect_timeout: int = 5

    class Config:
        env_file = str(_ENV_FILE)
        extra = "ignore"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.secret_key:
            raise ValueError("SECRET_KEY es obligatorio")
        if len(self.secret_key) < 32:
            raise ValueError(f"SECRET_KEY debe tener mínimo 32 caracteres (actual: {len(self.secret_key)})")

    @property
    def db_dsn(self) -> str:
        return (
            f"host={self.db_host} "
            f"port={self.db_port} "
            f"dbname={self.db_name} "
            f"user={self.db_user} "
            f"password={self.db_password} "
            f"connect_timeout={self.db_connect_timeout}"
        )


settings = Settings()