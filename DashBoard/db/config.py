from dataclasses import dataclass
from surveillance import settings


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
