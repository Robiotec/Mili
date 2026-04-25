from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, stream_auth, health, ptz, telemetry, opensky, objetivo
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
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

_extra_origins = [o.strip() for o in settings.CORS_EXTRA_ORIGINS.split(",") if o.strip()]
_cors_origins = [
    f"http://{settings.PUBLIC_HOST}:{settings.API_PORT}",
    f"http://{settings.PUBLIC_HOST}",
    *_extra_origins,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
app.include_router(objetivo.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8004, reload=True)