from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, stream_auth, health, ptz, telemetry, opensky
from app.db.connection import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open()
    yield
    db.close()


app = FastAPI(
    title="API Central  - Robiotec",
    description="API para sistema de gestión.",
    version="1.0.0",
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)

# CORS: permitir acceso desde la IP pública y localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{settings.PUBLIC_HOST}:{settings.API_PORT}",
        f"http://{settings.PUBLIC_HOST}",
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Incluir routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(stream_auth.router, prefix="/stream-auth", tags=["stream-auth"])
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(ptz.router, prefix="/ptz", tags=["ptz"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(opensky.router, prefix="/opensky", tags=["opensky"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8004, reload=True)