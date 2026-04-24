from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from app.core.security import create_access_token, verify_password, get_current_user
from app.core.token_store import token_store
from app.db.connection import db
from datetime import timedelta
from app.core.config import settings
from urllib.parse import parse_qs


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """Login de usuario (dashboard). Retorna JWT para la API REST."""
    row = db.fetch_one(
        "SELECT u.id, u.usuario, u.password, r.rol "
        "FROM usuarios u JOIN roles r ON u.rol_id = r.id "
        "WHERE u.usuario = %s",
        (request.username,),
    )
    if not row or not verify_password(request.password, row["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(row["id"]), "company_id": "1", "role": row["rol"]},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.api_route("/validate", methods=["GET", "POST"])
async def validate_mediamtx(request: Request):
    """
    MediaMTX externalAuthenticationURL handler.
    Valida tokens opacos para acceso a streams RTSP/WebRTC.
    
    MediaMTX v1.16.3 envía:
      - POST con JSON body para RTSP: {user, password, ip, action, path, protocol, id, query}
      - GET con query params para WebRTC/HLS: ?user=&password=&ip=&action=&path=&protocol=&query=
    
    Token viaja en:
      - RTSP: campo password (rtsp://user:TOKEN@host/path)
      - WebRTC/HLS: query param original ?token=xxx (viene en campo "query")
    
    Retorna 200 para permitir, 401 para denegar.
    """
    if request.method == "POST":
        body = await request.json()
    else:
        # GET: parámetros en query string
        body = dict(request.query_params)

    user = body.get("user", "")
    password = body.get("password", "")
    action = body.get("action", "")
    path = body.get("path", "")
    protocol = body.get("protocol", "")
    ip = body.get("ip", "")
    query = body.get("query", "")

    # Permitir acciones internas (api, metrics)
    if action in ("api", "metrics", "pprof"):
        return {"ok": True}

    # Permitir publish (cámaras RTSP no pueden portar tokens opacos)
    #Eliminar si desean tener publicación autenticada en MediaMTX, pero implica que cada cámara debe portar 
    #un token opaco único en su URL RTSP
    if action == "publish":
        return {"ok": True}
    
    
    # Permitir lectura (playback) sin requerir token
    # Desactiva autenticación para RTSP playback
    """
    if action == "read":
        return {"ok": True}
    """

    # Extraer token según protocolo
    token = ""
    if protocol in ("rtsp", "rtsps", "rtmp", "rtmps"):
        token = password
    elif query:
        params = parse_qs(query)
        token_list = params.get("token", [])
        token = token_list[0] if token_list else ""

    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")

    # Validar token contra el token store
    allowed, reason = token_store.validate(token, path, action, ip)
    if not allowed:
        raise HTTPException(status_code=401, detail=reason)

    return {"ok": True}


@router.post("/tokens/revoke/{token_id}")
async def revoke_token_endpoint(token_id: str, user: dict = Depends(get_current_user)):
    """Revoca un token opaco por su token_id. Requiere JWT admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    revoked = token_store.revoke_by_id(token_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Token no encontrado")
    return {"message": f"Token {token_id} revocado"}