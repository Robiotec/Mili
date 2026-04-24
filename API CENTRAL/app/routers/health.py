"""Router de salud del sistema. Verifica disponibilidad de dependencias críticas."""

from fastapi import APIRouter, HTTPException, status
from app.db.connection import db

router = APIRouter()


@router.get("/")
async def health_check():
    """
    Health check completo.
    - Verifica conexión a PostgreSQL
    - Retorna 200 si DB es alcanzable, 503 si no
    """
    try:
        # Test conexión a DB
        result = db.fetch_one("SELECT 1 as alive")
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed"
            )
        
        return {
            "status": "ok",
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}"
        )