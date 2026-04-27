"""
Router para generar tokens opacos de acceso a streams de MediaMTX.
MediaMTX valida los tokens directamente via externalAuthenticationURL.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, Response
from app.core.security import get_current_user
from app.core.token_store import token_store
from app.core.config import settings
import asyncio
import re
import html
import requests as http_client

VALID_PATH_RE = re.compile(r"^[A-Za-z0-9_\-/]{1,100}$")

router = APIRouter()


@router.post("/stream/token/{camera_id:path}")
async def get_stream_token(camera_id: str, request: Request, user: dict = Depends(get_current_user)):
    """
    Genera un token opaco para ver un stream por WebRTC/HLS.
    Requiere JWT de sesión válido.
    El token se vincula al navegador mediante cookie.
    """
    if not VALID_PATH_RE.match(camera_id):
        raise HTTPException(status_code=400, detail="camera_id inválido")

    host = settings.PUBLIC_HOST
    api_port = settings.API_PORT

    token_value, token_id, session_secret = token_store.create_token(
        token_type="stream_read",
        company_id=user.get("company_id", "1"),
        paths=[camera_id],
        actions=["read"],
        expires_in=settings.PLAYBACK_TOKEN_EXPIRE_MINUTES * 60,
        single_use=True,
        user_id=user.get("sub"),
    )

    viewer_url = f"http://{host}:{api_port}/stream-auth/viewer/{camera_id}?token={token_value}"

    response_data = {
        "token": token_value,
        "token_id": token_id,
        "expires_in": settings.PLAYBACK_TOKEN_EXPIRE_MINUTES * 60,
        "stream_url": viewer_url,
        "instruction": "Abre stream_url en el navegador. El token queda vinculado a este navegador mediante cookie.",
    }

    response = Response(
        content=__import__("json").dumps(response_data),
        media_type="application/json",
    )
    response.set_cookie(
        key=f"stream_session_{token_value[:16]}",
        value=session_secret,
        max_age=settings.PLAYBACK_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/viewer/{camera_id:path}", response_class=HTMLResponse)
async def stream_viewer(camera_id: str, request: Request, token: str = ""):
    """
    Página viewer que verifica la cookie de sesión antes de mostrar el stream.
    Si la cookie no coincide, muestra mensaje de protección.
    """
    if not token or not VALID_PATH_RE.match(camera_id):
        return HTMLResponse(content=_protection_page(), status_code=403)

    # Buscar la cookie correspondiente a este token
    cookie_key = f"stream_session_{token[:16]}"
    session_secret = request.cookies.get(cookie_key, "")

    if not session_secret:
        return HTMLResponse(content=_protection_page(), status_code=403)

    allowed, reason = token_store.validate_session(token, session_secret)
    if not allowed:
        return HTMLResponse(content=_protection_page(), status_code=403)

    host = settings.PUBLIC_HOST
    safe_camera_id = html.escape(camera_id)
    safe_token = html.escape(token)

    return HTMLResponse(content=_viewer_page(safe_camera_id, safe_token, host))


@router.get("/streams")
async def list_streams(user: dict = Depends(get_current_user)):
    """Lista streams activos desde MediaMTX. Requiere JWT."""
    def _fetch_streams():
        auth = None
        if settings.MEDIAMTX_API_USERNAME and settings.MEDIAMTX_API_PASSWORD:
            auth = (settings.MEDIAMTX_API_USERNAME, settings.MEDIAMTX_API_PASSWORD)
        r = http_client.get(f"{settings.MEDIAMTX_API_URL}/v3/paths/list", auth=auth, timeout=2)
        r.raise_for_status()
        return r.json()

    try:
        data = await asyncio.to_thread(_fetch_streams)
        items = data.get("items") or []
        streams = []
        for p in items:
            streams.append({
                "name": p.get("name", ""),
                "ready": p.get("ready", False),
                "tracks": p.get("tracks", []),
                "source_type": p.get("source", {}).get("type", "unknown") if isinstance(p.get("source"), dict) else "unknown",
                "readers": len(p.get("readers") or []),
                "bytes_received": p.get("bytesReceived", 0),
                "bytes_sent": p.get("bytesSent", 0),
                "ready_time": p.get("readyTime", ""),
            })
        return {"streams": streams, "total": len(streams)}
    except http_client.ConnectionError:
        raise HTTPException(status_code=502, detail="MediaMTX no responde")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error consultando MediaMTX: {str(e)}")


@router.get("/panel", response_class=HTMLResponse)
async def stream_panel(request: Request):
    """Panel de prueba para generar tokens y ver streams desde el navegador."""
    base = str(request.base_url).rstrip("/")
    return HTMLResponse(content=_panel_page(base))


def _panel_page(base: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stream Panel</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 30px; }}
        h1 {{ color: #4CAF50; margin-bottom: 20px; font-size: 22px; }}
        .card {{ background: #1a1a2e; border-radius: 10px; padding: 20px; margin: 12px 0; border: 1px solid #333; }}
        input {{ background: #111; color: #fff; border: 1px solid #444; padding: 10px 14px; border-radius: 6px;
                font-size: 14px; width: 200px; }}
        button {{ background: #4CAF50; color: #fff; border: none; padding: 10px 20px; border-radius: 6px;
                 cursor: pointer; font-size: 14px; margin: 4px; }}
        button:hover {{ background: #45a049; }}
        button:disabled {{ background: #333; cursor: not-allowed; }}
        .cam-btn {{ background: #2196F3; }}
        .cam-btn:hover {{ background: #1976D2; }}
        #log {{ background: #111; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 13px;
                max-height: 200px; overflow-y: auto; white-space: pre-wrap; margin-top: 10px; }}
        .ok {{ color: #4CAF50; }} .err {{ color: #ff4444; }} .info {{ color: #2196F3; }}
        #cameras {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    </style>
</head>
<body>
    <h1>Stream Panel</h1>

    <div class="card" id="login-card">
        <h3>1. Login</h3>
        <div style="margin-top:10px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <input id="user" placeholder="Usuario" value="">
            <input id="pass" type="password" placeholder="Contrase&ntilde;a" value="">
            <button onclick="doLogin()">Iniciar sesi&oacute;n</button>
        </div>
    </div>

    <div class="card" id="cam-card" style="display:none">
        <h3>2. Streams activos <button onclick="loadStreams()" style="font-size:12px;padding:4px 10px;background:#555;">&#x21bb; Recargar</button></h3>
        <div id="cameras" style="margin-top:10px;"></div>
        <div id="no-streams" style="display:none; margin-top:10px; color:#888;">No hay streams activos en MediaMTX</div>
        <div style="margin-top:12px; border-top:1px solid #333; padding-top:10px;">
            <span style="color:#888; font-size:12px;">Manual:</span>
            <input id="cam-input" placeholder="Nombre de c&aacute;mara" style="width:140px;">
            <button class="cam-btn" onclick="getToken(document.getElementById('cam-input').value)" style="font-size:12px;padding:6px 12px;">Ver</button>
        </div>
    </div>

    <div class="card">
        <h3>Log</h3>
        <div id="log"></div>
    </div>

    <script>
        const BASE = '{base}';
        const logEl = document.getElementById('log');
        let jwt = '';
        let prevStats = {{}};
        let prevTime = 0;

        function log(msg, cls) {{
            const d = document.createElement('div');
            d.className = cls || '';
            d.textContent = msg;
            logEl.appendChild(d);
            logEl.scrollTop = logEl.scrollHeight;
        }}

        function formatRate(bytesPerSec) {{
            if (bytesPerSec <= 0) return '0 b/s';
            const bps = bytesPerSec * 8;
            if (bps >= 1000000) return (bps / 1000000).toFixed(1) + ' Mbps';
            if (bps >= 1000) return (bps / 1000).toFixed(0) + ' Kbps';
            return bps.toFixed(0) + ' bps';
        }}

        function formatBytes(bytes) {{
            if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB';
            if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
            if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
            return bytes + ' B';
        }}

        async function doLogin() {{
            const user = document.getElementById('user').value.trim();
            const pass = document.getElementById('pass').value;
            if (!user || !pass) {{ log('Ingresa usuario y contrase\u00f1a', 'err'); return; }}

            log('Haciendo login...', 'info');
            try {{
                const r = await fetch(BASE + '/auth/login', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ username: user, password: pass }})
                }});
                if (!r.ok) {{ const e = await r.json(); log('Login fallido: ' + e.detail, 'err'); return; }}
                const data = await r.json();
                jwt = data.access_token;
                log('Login OK', 'ok');
                document.getElementById('login-card').style.opacity = '0.5';
                document.getElementById('cam-card').style.display = 'block';
                loadStreams();
                setInterval(loadStreams, 5000);
            }} catch(e) {{ log('Error: ' + e, 'err'); }}
        }}

        async function loadStreams() {{
            try {{
                const r = await fetch(BASE + '/stream-auth/streams', {{
                    headers: {{ 'Authorization': 'Bearer ' + jwt }}
                }});
                if (!r.ok) {{ log('Error cargando streams', 'err'); return; }}
                const data = await r.json();
                const now = Date.now() / 1000;
                const elapsed = prevTime > 0 ? now - prevTime : 0;
                const container = document.getElementById('cameras');
                const noStreams = document.getElementById('no-streams');
                container.innerHTML = '';
                if (data.streams.length === 0) {{
                    noStreams.style.display = 'block';
                    prevTime = now;
                    return;
                }}
                noStreams.style.display = 'none';
                data.streams.forEach(s => {{
                    let rateIn = 0, rateOut = 0;
                    if (elapsed > 0 && prevStats[s.name]) {{
                        rateIn = Math.max(0, (s.bytes_received - prevStats[s.name].rx) / elapsed);
                        rateOut = Math.max(0, (s.bytes_sent - prevStats[s.name].tx) / elapsed);
                    }}
                    prevStats[s.name] = {{ rx: s.bytes_received, tx: s.bytes_sent }};

                    const div = document.createElement('div');
                    div.style.cssText = 'background:#16213e;border:1px solid #0f3460;border-radius:8px;padding:12px;margin-bottom:8px;cursor:pointer;';
                    div.onmouseover = () => div.style.borderColor = '#4CAF50';
                    div.onmouseout = () => div.style.borderColor = '#0f3460';
                    const ready = s.ready ? '<span style="color:#4CAF50;">&#9679;</span>' : '<span style="color:#ff4444;">&#9679;</span>';
                    const tracks = s.tracks ? s.tracks.map(t => t.codec || t.type).join(', ') : '-';
                    const readers = s.readers || 0;
                    const src = s.source_type || '-';
                    const rateInStr = elapsed > 0 ? formatRate(rateIn) : '...';
                    const rateOutStr = elapsed > 0 ? formatRate(rateOut) : '...';
                    div.innerHTML = `
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:16px;font-weight:bold;">${{ready}} ${{s.name}}</span>
                            <button class="cam-btn" onclick="event.stopPropagation();getToken('${{s.name}}')" style="font-size:12px;padding:5px 14px;">&#9654; Ver</button>
                        </div>
                        <div style="font-size:12px;color:#888;margin-top:6px;">
                            Fuente: ${{src}} &nbsp;|&nbsp; Tracks: ${{tracks}} &nbsp;|&nbsp;
                            Viewers: <b style="color:#2196F3;">${{readers}}</b>
                        </div>
                        <div style="font-size:12px;margin-top:4px;">
                            <span style="color:#4CAF50;">&#8595; ${{rateInStr}}</span>
                            <span style="color:#888;">&nbsp;(${{formatBytes(s.bytes_received)}})</span>
                            &nbsp;&nbsp;
                            <span style="color:#2196F3;">&#8593; ${{rateOutStr}}</span>
                            <span style="color:#888;">&nbsp;(${{formatBytes(s.bytes_sent)}})</span>
                        </div>`;
                    div.onclick = () => getToken(s.name);
                    container.appendChild(div);
                }});
                prevTime = now;
                log('Streams cargados: ' + data.total, 'info');
            }} catch(e) {{ log('Error cargando streams: ' + e, 'err'); }}
        }}

        async function getToken(camId) {{
            if (!camId) {{ log('Ingresa nombre de c\u00e1mara', 'err'); return; }}
            if (!jwt) {{ log('Primero haz login', 'err'); return; }}

            log('Solicitando token para ' + camId + '...', 'info');
            try {{
                const r = await fetch(BASE + '/stream-auth/stream/token/' + camId, {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + jwt }},
                    credentials: 'include'
                }});
                if (!r.ok) {{ const e = await r.json(); log('Error: ' + e.detail, 'err'); return; }}
                const data = await r.json();
                log('Token generado: ' + data.token_id, 'ok');
                log('Cookie seteada en este navegador', 'ok');
                log('Abriendo viewer...', 'info');
                window.open(data.stream_url, '_blank');
            }} catch(e) {{ log('Error: ' + e, 'err'); }}
        }}

        // Enter en password hace login
        document.getElementById('pass').addEventListener('keydown', e => {{ if (e.key === 'Enter') doLogin(); }});
        document.getElementById('cam-input').addEventListener('keydown', e => {{
            if (e.key === 'Enter') getToken(document.getElementById('cam-input').value);
        }});
    </script>
</body>
</html>"""


def _protection_page() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acceso Denegado</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #fff;
            overflow: hidden;
        }
        .container {
            text-align: center;
            padding: 60px 40px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 0, 0, 0.3);
            border-radius: 20px;
            backdrop-filter: blur(10px);
            max-width: 600px;
            animation: fadeIn 1s ease-out;
        }
        .shield {
            font-size: 80px;
            margin-bottom: 20px;
            animation: pulse 2s infinite;
        }
        h1 {
            font-size: 28px;
            font-weight: 700;
            color: #ff4444;
            letter-spacing: 3px;
            margin-bottom: 15px;
            text-transform: uppercase;
        }
        .subtitle {
            font-size: 16px;
            color: rgba(255, 255, 255, 0.6);
            margin-top: 10px;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="shield">🛡️</div>
        <h1>ROBIOTEC PROTEGE A SUS CLIENTES</h1>
        <p class="subtitle">Este enlace de stream no es válido para este navegador.</p>
    </div>
</body>
</html>"""


def _viewer_page(camera_id: str, token: str, host: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stream - {camera_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #0a0a0a;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #fff;
        }}
        .header {{
            padding: 15px 30px;
            background: rgba(255, 255, 255, 0.05);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            width: 100%;
            text-align: center;
        }}
        .header h1 {{ font-size: 18px; font-weight: 500; color: #4CAF50; }}
        .video-container {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 20px;
        }}
        #video {{
            max-width: 100%;
            max-height: 80vh;
            background: #111;
            border-radius: 8px;
        }}
        .status {{
            padding: 10px;
            font-size: 14px;
            color: rgba(255, 255, 255, 0.5);
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{camera_id}</h1>
    </div>
    <div class="video-container">
        <video id="video" autoplay muted playsinline controls></video>
    </div>
    <div class="status" id="status">Conectando...</div>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script>
        const video = document.getElementById('video');
        const status = document.getElementById('status');
        const whepUrl = 'http://{host}:{settings.MEDIAMTX_WEBRTC_PORT}/{camera_id}/whep';
        const hlsUrl = 'http://{host}:{settings.MEDIAMTX_HLS_PORT}/{camera_id}/index.m3u8?token={token}';

        async function startWebRTC() {{
            try {{
                const pc = new RTCPeerConnection({{
                    iceServers: [{{ urls: 'stun:stun.l.google.com:19302' }}]
                }});

                let gotTrack = false;
                pc.ontrack = (evt) => {{
                    gotTrack = true;
                    video.srcObject = evt.streams[0];
                    status.textContent = 'Stream activo (WebRTC)';
                    status.style.color = '#4CAF50';
                }};

                pc.oniceconnectionstatechange = () => {{
                    if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'disconnected') {{
                        if (!gotTrack) {{
                            status.textContent = 'WebRTC falló, probando HLS...';
                            status.style.color = '#FFA500';
                            startHLS();
                        }} else {{
                            status.textContent = 'Conexión perdida. Recargue la página.';
                            status.style.color = '#ff4444';
                        }}
                    }}
                }};

                pc.addTransceiver('video', {{ direction: 'recvonly' }});
                pc.addTransceiver('audio', {{ direction: 'recvonly' }});

                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                const resp = await fetch(whepUrl + '?token={token}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/sdp' }},
                    body: pc.localDescription.sdp,
                }});

                if (!resp.ok) {{
                    throw new Error('WebRTC no disponible: ' + resp.status);
                }}

                const answer = await resp.text();
                await pc.setRemoteDescription({{ type: 'answer', sdp: answer }});

                // Si en 5s no llega video, caer a HLS
                setTimeout(() => {{
                    if (!gotTrack) {{
                        pc.close();
                        status.textContent = 'WebRTC sin video, probando HLS...';
                        status.style.color = '#FFA500';
                        startHLS();
                    }}
                }}, 5000);
            }} catch (err) {{
                status.textContent = 'WebRTC falló, probando HLS...';
                status.style.color = '#FFA500';
                startHLS();
            }}
        }}

        function startHLS() {{
            if (typeof Hls === 'undefined') {{
                status.textContent = 'Error: no se pudo cargar hls.js';
                status.style.color = '#ff4444';
                return;
            }}
            if (Hls.isSupported()) {{
                const hls = new Hls({{ enableWorker: true, lowLatencyMode: true }});
                hls.loadSource(hlsUrl);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, () => {{
                    video.play();
                    status.textContent = 'Stream activo (HLS)';
                    status.style.color = '#4CAF50';
                }});
                hls.on(Hls.Events.ERROR, (event, data) => {{
                    if (data.fatal) {{
                        status.textContent = 'Error HLS: codec no soportado por este navegador (posible H265). Pruebe con Safari o Edge.';
                        status.style.color = '#ff4444';
                    }}
                }});
            }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                // Safari soporta HLS nativo (incluyendo H265)
                video.src = hlsUrl;
                video.addEventListener('loadedmetadata', () => {{
                    video.play();
                    status.textContent = 'Stream activo (HLS nativo)';
                    status.style.color = '#4CAF50';
                }});
                video.addEventListener('error', () => {{
                    status.textContent = 'Error reproduciendo stream';
                    status.style.color = '#ff4444';
                }});
            }} else {{
                status.textContent = 'Este navegador no soporta HLS ni WebRTC para este stream';
                status.style.color = '#ff4444';
            }}
        }}

        startWebRTC();
    </script>
</body>
</html>"""
