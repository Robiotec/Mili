from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field

# Siempre buscar .env desde la raíz del proyecto, sin importar desde dónde se ejecute
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Configuración centralizada. TODOS los valores vienen de .env o variables de entorno."""

    # ── General ──
    PUBLIC_HOST: str
    API_PORT: int

    # ── JWT ──
    SECRET_KEY: str = Field(..., description="Clave secreta para JWT. Mínimo 32 caracteres.")
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    PLAYBACK_TOKEN_EXPIRE_MINUTES: int

    # ── MediaMTX ──
    MEDIAMTX_API_URL: str
    MEDIAMTX_API_USERNAME: Optional[str] = None
    MEDIAMTX_API_PASSWORD: Optional[str] = None

    # ── PostgreSQL ──
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_MIN_SIZE: int = 1
    DB_MAX_SIZE: int = 10
    DB_TIMEOUT: int = 10
    DB_CONNECT_TIMEOUT: int = 5

    class Config:
        env_file = str(_ENV_FILE)
        extra = "ignore"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY es obligatorio")
        if len(self.SECRET_KEY) < 32:
            raise ValueError(f"SECRET_KEY debe tener mínimo 32 caracteres (actual: {len(self.SECRET_KEY)})")

    @property
    def db_dsn(self) -> str:
        return (
            f"host={self.DB_HOST} "
            f"port={self.DB_PORT} "
            f"dbname={self.DB_NAME} "
            f"user={self.DB_USER} "
            f"password={self.DB_PASSWORD} "
            f"connect_timeout={self.DB_CONNECT_TIMEOUT}"
        )


settings = Settings()