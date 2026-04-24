# NOTA SOBRE central.db

Si ves un archivo `central.db` en el proyecto, corresponde a una base de datos SQLite usada en versiones antiguas o para pruebas locales. Actualmente **NO se usa**: toda la persistencia está en PostgreSQL remoto (ver `.env`). Puedes eliminar `central.db` si no lo necesitas para pruebas.

# API Central - Tokens WebRTC con Protección de Sesión

Sistema ligero de autenticación y autorización para streaming WebRTC protegido por MediaMTX,
con tokens opacos y cookies de sesión HttpOnly.

---

## Arquitectura General

```
┌────────────────────┐                           ┌───────────────────────┐
│   FastAPI :8003    │                           │     MediaMTX          │
│   (API Central)    │────externalAuth request──►│  RTSP  :8554          │
│                    │                           │  WebRTC:8889          │
│  - POST /auth/login     ←──────────────────────┤  API   :9997 (local)  │
│  - POST /auth/validate  response {ok: true}    │                       │
│  - POST /stream-auth/...                       │  externalAuth:        │
│      → GET /token{camera_id}                   │  - Valida tokens      │
│      → GET /viewer{camera_id}                  │  - Protege read/pub   │
│                    │                           │                       │
└────────────────────┘                           └───────────────────────┘
         ▲
         │ JWT + opaque tokens
         │
    ┌────┴───────────┐
    │   Dashboard    │
    │   (navegador)  │
    └────────────────┘
```

**Flujo simplificado:**
1. Dashboard hace login en `/auth/login` → obtiene JWT
2. Dashboard solicita stream token en `/stream-auth/stream/token/{camera_id}` → obtiene token opaco + URL
3. Dashboard abre URL viewer → se establece cookie SessionID
4. Viewer abre video en WebRTC → MediaMTX valida token contra `/auth/validate`
5. MediaMTX permite conexión si token es válido

### Puertos

| Servicio         | Puerto | Protocolo | Acceso externo | Protección                              |
|------------------|--------|-----------|----------------|-----------------------------------------|
| FastAPI          | 8003   | HTTP      | Sí             | JWT (login), tokens opacos (streams)    |
| MediaMTX RTSP    | 8554   | RTSP      | Sí             | externalAuth (leer=token, escribir=lib)|
| MediaMTX WebRTC  | 8889   | HTTP      | Sí             | externalAuth (token en query param)     |
| MediaMTX API     | 9997   | HTTP      | **Bloqueado**  | iptables DROP + bind 127.0.0.1          |

**IP del servidor**: `136.119.96.176`

---

## Modelo de seguridad

| Concepto              | Implementación                                                    |
|-----------------------|-------------------------------------------------------------------|
| Login API             | JWT HS256, 60 min expiración                                      |
| Tokens de stream      | Opacos (`secrets.token_urlsafe(32)`), 15 min, single-use          |
| Vinculación a sesión  | Cookie HttpOnly `stream_session_{token[:16]}` = session_secret    |
| Anti-compartición     | URL viewer sin cookie válida → página "ROBIOTEC PROTEGE..."      |
| Validación MediaMTX   | Request directo a `/auth/validate` con token en password (RTSP)   |
| DB                    | PostgreSQL 15+, usuarios con bcrypt hash                          |

---

## Variables de entorno (*OBLIGATORIAS*)

```bash
POST http://136.119.96.176:8003/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin123"
}
```

Respuesta:
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

Guardar el `access_token` como JWT para los siguientes requests.

### Paso 2: Listar cámaras activas

```bash
GET http://136.119.96.176:8003/mediamtx/paths
Authorization: Bearer <JWT>
```

Respuesta:
```json
{
  "items": [
    {"name": "CAM1", "online": true, "tracks": ["H264", "Opus"], "readers": 0},
    {"name": "CAM2", "online": true, "tracks": ["H264", "Opus"], "readers": 0},
    {"name": "CAM1_INFERENCE", "online": true, "tracks": ["H264"], "readers": 0}
  ]
}
```

### Paso 3: Obtener token de stream (opaco)

```bash
POST http://136.119.96.176:8003/stream-auth/stream/token/CAM1
Authorization: Bearer <JWT>
```

Respuesta:
```json
{
  "token": "aB3x_kL9m...",
  "token_id": "tok_abc123",
  "stream_url": "http://136.119.96.176:8003/stream-auth/viewer/CAM1?token=aB3x_kL9m...",
  "expires_in": 900
}
```

> **Importante**: La respuesta también establece una cookie HttpOnly
> `stream_session_{token[:16]}` que vincula el token a este navegador.

### Paso 4: Mostrar el video

#### Opción A: Viewer integrado (recomendado para pruebas)

Abrir `stream_url` en el navegador. FastAPI sirve un reproductor WebRTC
que se conecta a `http://136.119.96.176:8889/CAM1/whep?token=xxx`.

Si se abre desde otro navegador sin la cookie → se muestra:
**"ROBIOTEC PROTEGE A SUS CLIENTES"**

#### Opción B: Embeber en iframe

```html
<iframe
  src="http://136.119.96.176:8003/stream-auth/viewer/CAM1?token=TOKEN"
  width="640"
  height="480"
  allow="autoplay"
></iframe>
```

#### Opción C: WebRTC directo con JavaScript (recomendado para producción)

```javascript
const API = 'http://136.119.96.176:8003';
const MEDIAMTX = 'http://136.119.96.176:8889';

// 1. Obtener token opaco (requiere JWT en Authorization)
const res = await fetch(`${API}/stream-auth/stream/token/CAM1`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${jwt}` }
});
const { token } = await res.json();

// 2. Conectar por WebRTC WHEP directo a MediaMTX
const pc = new RTCPeerConnection({
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
});

pc.ontrack = (event) => {
  document.getElementById('video').srcObject = event.streams[0];
};

pc.addTransceiver('video', { direction: 'recvonly' });
pc.addTransceiver('audio', { direction: 'recvonly' });

const offer = await pc.createOffer();
await pc.setLocalDescription(offer);

// Token va como query param — MediaMTX lo envía a externalAuth para validar
const whepRes = await fetch(`${MEDIAMTX}/CAM1/whep?token=${token}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/sdp' },
  body: pc.localDescription.sdp
});

const answer = await whepRes.text();
await pc.setRemoteDescription({ type: 'answer', sdp: answer });
```

```html
<video id="video" autoplay muted playsinline></video>
```

### Gestión de tokens

```bash
# Ver tokens activos (requiere JWT admin)
GET http://136.119.96.176:8003/auth/tokens/active
Authorization: Bearer <JWT>

# Revocar un token por ID
POST http://136.119.96.176:8003/auth/tokens/revoke/{token_id}
Authorization: Bearer <JWT>
```

### Seguridad de los tokens de stream

- Cada token `stream_read` es **de un solo uso** vinculado por cookie al navegador que lo solicitó
- Si alguien copia la URL, el otro navegador ve **"ROBIOTEC PROTEGE A SUS CLIENTES"**
- El token expira en **15 minutos**
- MediaMTX valida cada conexión WebRTC/RTSP llamando a `/auth/validate`

---

## Flujo de Inferencia (Video + Audio)

El servidor de inferencia consume el video original via RTSP, aplica
procesamiento (detección, tracking, etc.) y lo republica como un nuevo stream
**conservando el audio original**.

```
R-Box ──RTSP publish (video+audio)──► MediaMTX (CAM1)
                                           │
                                           ▼ RTSP read (con service-token)
                                   Servidor Inferencia
                                     │ video → OpenCV → inferencia
                                     │ audio → passthrough
                                     ▼ RTSP publish libre (video+audio)
                                  MediaMTX (CAM1_INFERENCE)
                                           │
                                           ▼ WebRTC :8889 (con stream_read token)
                                      Dashboard (video+audio)
```

### Paso 1: Obtener service-token

El servidor de inferencia necesita un `service` token para leer streams RTSP.
Publicar es libre (no necesita token).

```bash
POST http://136.119.96.176:8003/auth/service-token
Authorization: Bearer <JWT_ADMIN>
Content-Type: application/json

{
  "read_paths": ["CAM1", "CAM2"],
  "publish_paths": ["CAM1_INFERENCE", "CAM2_INFERENCE"],
  "expires_hours": 24
}
```

> Si no se envía `publish_paths`, se generan automáticamente con sufijo `_INFERENCE`.

Respuesta:
```json
{
  "token": "svc_xYz...",
  "token_id": "tok_svc_123",
  "type": "service",
  "expires_in": 86400,
  "read_paths": ["CAM1", "CAM2"],
  "publish_paths": ["CAM1_INFERENCE", "CAM2_INFERENCE"],
  "rtsp_examples": {
    "CAM1": { "read": "rtsp://inference:svc_xYz...@136.119.96.176:8554/CAM1" },
    "CAM1_INFERENCE": { "publish": "rtsp://inference:svc_xYz...@136.119.96.176:8554/CAM1_INFERENCE" }
  }
}
```

### Paso 2: Leer el video original con token

El token se pasa como **password** en la URL RTSP (MediaMTX lo envía a
externalAuth en el campo `password`):

```bash
# FFmpeg — leer CAM1 con service-token
ffmpeg -rtsp_transport tcp \
  -i "rtsp://inference:svc_xYz...@136.119.96.176:8554/CAM1" \
  -f rawvideo -pix_fmt bgr24 pipe:1
```

```python
import cv2

# OpenCV — el token va como password
cap = cv2.VideoCapture('rtsp://inference:svc_xYz...@136.119.96.176:8554/CAM1')

while True:
    ret, frame = cap.read()
    if not ret:
        break
    # Aplicar inferencia al frame...
```

### Paso 3: Publicar video con inferencia + audio

Publicar a MediaMTX es libre (no requiere token). Se usa un nombre diferente
como `CAM1_INFERENCE`. Para **conservar el audio**, se usa FFmpeg con dos inputs:

```python
import cv2
import subprocess
import numpy as np

SERVICE_TOKEN = "svc_xYz..."
SERVER = "136.119.96.176"
CAMERA = "CAM1"

rtsp_source = f"rtsp://inference:{SERVICE_TOKEN}@{SERVER}:8554/{CAMERA}"
rtsp_dest = f"rtsp://{SERVER}:8554/{CAMERA}_INFERENCE"

cap = cv2.VideoCapture(rtsp_source)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25

# FFmpeg: video procesado por pipe + audio del stream original
ffmpeg_cmd = [
    'ffmpeg', '-loglevel', 'warning',
    # Input 0: video raw procesado
    '-f', 'rawvideo', '-pix_fmt', 'bgr24',
    '-s', f'{width}x{height}', '-r', str(fps),
    '-i', 'pipe:0',
    # Input 1: audio del stream original
    '-rtsp_transport', 'tcp',
    '-i', rtsp_source,
    # Mapear: video de input 0, audio de input 1
    '-map', '0:v:0', '-map', '1:a:0',
    # Video encoding
    '-c:v', 'libx264', '-preset', 'ultrafast',
    '-tune', 'zerolatency', '-b:v', '2M',
    # Audio passthrough
    '-c:a', 'aac', '-b:a', '128k',
    # Output RTSP
    '-f', 'rtsp', '-rtsp_transport', 'tcp',
    rtsp_dest,
]

proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # === INFERENCIA ===
    # frame = modelo.predict(frame)
    # cv2.rectangle(frame, ...)
    # cv2.putText(frame, "Persona detectada", ...)

    proc.stdin.write(frame.tobytes())

cap.release()
proc.stdin.close()
proc.wait()
```

### Paso 4: Ver el video con inferencia desde el dashboard

El stream `CAM1_INFERENCE` aparece como cualquier otro en MediaMTX:

```bash
POST http://136.119.96.176:8003/stream-auth/stream/token/CAM1_INFERENCE
Authorization: Bearer <JWT>
```

### Usar el script de inferencia incluido

```bash
cd /home/yandriuchuari/api_central

# Automático: obtiene token, lee, aplica inferencia demo, republica con audio
python scripts/inference_client.py --server 136.119.96.176 --camera CAM1 --auto-token

# Con token manual
python scripts/inference_client.py --server 136.119.96.176 --camera CAM1 --token "svc_xYz..."

# Con preview local
python scripts/inference_client.py --server 136.119.96.176 --camera CAM1 --auto-token --preview
```

### Resumen de streams por cámara

| Stream            | Descripción                          | Quién publica       | Audio |
|-------------------|--------------------------------------|---------------------|-------|
| `CAM1`            | Video original de la cámara          | R-Box               | Sí    |
| `CAM1_INFERENCE`  | Video con detección/tracking         | Servidor inferencia  | Sí    |
| `CAM2`            | Video original de la cámara          | R-Box               | Sí    |
| `CAM2_INFERENCE`  | Video con detección/tracking         | Servidor inferencia  | Sí    |

---

## Flujo R-Box (Dispositivo)

La R-Box es un dispositivo que publica video de cámaras IP locales al servidor
MediaMTX. La R-Box consulta la API para saber qué cámaras tiene asignadas.

```
R-Box encendida
    │
    ▼ POST /rboxes/device/init {serial, secret}
    │
    ├─── Heartbeat (status=online)
    ├─── Lista de cámaras con URLs RTSP source
    └─── Token de publish para MediaMTX
    │
    ▼ Por cada cámara:
    ffmpeg -i rtsp://cam_local:554/ch1 -c:v copy -c:a aac \
           -f rtsp rtsp://rbox:TOKEN@136.119.96.176:8554/CAM1
```

### Endpoint R-Box Init (endpoint único para inicialización)

```bash
POST http://136.119.96.176:8003/rboxes/device/init
Content-Type: application/json

{
  "serial": "RBOX_001",
  "secret": "mi_secreto_rbox",
  "ip_publica": "1.2.3.4",
  "ip_local": "192.168.1.10"
}
```

Respuesta:
```json
{
  "rbox": {
    "id": 1,
    "serial": "RBOX_001",
    "nombre": "R-Box Oficina Central",
    "organizacion_id": 1,
    "status": "online"
  },
  "cameras": [
    {
      "stream_name": "CAM1",
      "rtsp_source": "rtsp://admin:pass@192.168.1.100:554/ch1",
      "publish_url": "rtsp://rbox:TOKEN@136.119.96.176:8554/CAM1",
      "es_ptz": false,
      "marca": "Hikvision",
      "modelo": "DS-2CD2143",
      "hacer_inferencia": true
    }
  ],
  "publish_token": {
    "token": "pub_aB3x...",
    "token_id": "tok_pub_456",
    "expires_in": 86400
  },
  "count": 1
}
```

### Otros endpoints R-Box

```bash
# Heartbeat periódico (cada 60s)
POST http://136.119.96.176:8003/rboxes/device/heartbeat?serial=RBOX_001

# Consultar cámaras sin token (solo con serial)
GET http://136.119.96.176:8003/rboxes/device/my-cameras?serial=RBOX_001
```

### Usar el script R-Box incluido

```bash
cd /home/yandriuchuari/api_central

# Iniciar R-Box client
python scripts/rbox_client.py --serial RBOX_001 --secret mi_secreto --server 136.119.96.176

# Con IPs
python scripts/rbox_client.py --serial RBOX_001 --secret mi_secreto \
  --server 136.119.96.176 --ip-publica 1.2.3.4 --ip-local 192.168.1.10
```

---

## Dashboard - Embeber Video WebRTC

### Opción A: HTML de prueba incluido

Abrir `scripts/dashboard_webrtc.html` en el navegador. Permite:
- Conectar a la API con credenciales
- Ver todas las cámaras activas
- Conectar/desconectar streams individuales o todos a la vez
- Video + audio por WebRTC

### Opción B: Embeber en tu propia app

```javascript
const API = 'http://136.119.96.176:8003';
const MEDIAMTX = 'http://136.119.96.176:8889';

async function connectCamera(jwt, cameraId, videoElement) {
    // 1. Obtener token opaco
    const tokenRes = await fetch(`${API}/stream-auth/stream/token/${cameraId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${jwt}` },
        credentials: 'include',
    });
    const { token } = await tokenRes.json();

    // 2. Crear RTCPeerConnection
    const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    });

    pc.ontrack = (evt) => {
        videoElement.srcObject = evt.streams[0];
        videoElement.play().catch(() => {
            videoElement.muted = true;
            videoElement.play();
        });
    };

    // Video + Audio
    pc.addTransceiver('video', { direction: 'recvonly' });
    pc.addTransceiver('audio', { direction: 'recvonly' });

    // 3. WHEP handshake con MediaMTX
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const whepRes = await fetch(`${MEDIAMTX}/${cameraId}/whep?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: pc.localDescription.sdp,
    });

    const answer = await whepRes.text();
    await pc.setRemoteDescription({ type: 'answer', sdp: answer });

    return pc;  // Guardar referencia para cerrar después: pc.close()
}
```

```html
<video id="cam1" autoplay playsinline></video>
<video id="cam1-inference" autoplay playsinline></video>

<script>
// Login primero
const loginRes = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
});
const { access_token: jwt } = await loginRes.json();

// Conectar cámaras (original + inferencia, ambos con audio)
connectCamera(jwt, 'CAM1', document.getElementById('cam1'));
connectCamera(jwt, 'CAM1_INFERENCE', document.getElementById('cam1-inference'));
</script>
```

### Opción C: iframe (viewer integrado)

```html
<iframe
  src="http://136.119.96.176:8003/stream-auth/viewer/CAM1?token=TOKEN"
  width="640" height="480" allow="autoplay"
></iframe>
```

> **Nota**: El token debe obtenerse previamente via POST y la cookie
> debe estar seteada en el mismo navegador.

---

## Cómo funciona externalAuth

MediaMTX llama a `http://127.0.0.1:8003/auth/validate` para cada conexión:

| Protocolo | Método HTTP | Token viene en         |
|-----------|-------------|------------------------|
| RTSP      | POST        | Campo `password` del body JSON |
| WebRTC    | GET         | Query param `token` (dentro del campo `query`) |
| HLS       | GET         | Query param `token` (dentro del campo `query`) |

El endpoint `/auth/validate` responde:

- **200 OK** → acceso permitido
- **401 Unauthorized** → acceso denegado

Acciones que se permiten sin token: `api`, `metrics`, `pprof`, `publish` (temporal).

---

## API - Referencia completa

### Autenticación (`/auth`)

| Método    | Endpoint                         | Auth requerida | Descripción                                  |
|-----------|----------------------------------|----------------|----------------------------------------------|
| POST      | `/auth/login`                    | Ninguna        | Login usuario → JWT                          |
| POST      | `/auth/rbox-token`               | Ninguna (TODO) | Token opaco para R-Box publish               |
| POST      | `/auth/service-token`            | JWT admin      | Token opaco para inferencia (read + publish) |
| GET/POST  | `/auth/validate`                 | Token opaco    | Validación MediaMTX externalAuth             |
| GET       | `/auth/tokens/active`            | JWT admin      | Lista tokens opacos activos                  |
| POST      | `/auth/tokens/revoke/{token_id}` | JWT admin      | Revoca un token por ID                       |

### Streams (`/stream-auth`)

| Método | Endpoint                                 | Auth requerida | Descripción                          |
|--------|------------------------------------------|----------------|--------------------------------------|
| POST   | `/stream-auth/stream/token/{camera_id}`  | JWT            | Genera token opaco + cookie sesión   |
| GET    | `/stream-auth/viewer/{camera_id}`        | Token + cookie | Viewer HTML WebRTC (video + audio)   |
| GET    | `/stream-auth/test`                      | Ninguna        | Página de prueba (login + cámaras)   |

### R-Boxes (`/rboxes`)

| Método | Endpoint                          | Auth requerida | Descripción                              |
|--------|-----------------------------------|----------------|------------------------------------------|
| POST   | `/rboxes/`                        | JWT            | Registrar nueva R-Box                    |
| GET    | `/rboxes/`                        | JWT            | Listar R-Boxes                           |
| GET    | `/rboxes/{rbox_id}`               | JWT            | Detalle de una R-Box                     |
| PUT    | `/rboxes/{rbox_id}`               | JWT            | Actualizar R-Box                         |
| POST   | `/rboxes/{rbox_id}/camaras`       | JWT            | Asignar cámara a R-Box                   |
| DELETE | `/rboxes/{rbox_id}/camaras/{id}`  | JWT            | Desasignar cámara                        |
| GET    | `/rboxes/{rbox_id}/camaras`       | JWT            | Listar cámaras de R-Box (dashboard)      |
| POST   | `/rboxes/device/init`             | Ninguna*       | **Init R-Box: heartbeat+cámaras+token**  |
| POST   | `/rboxes/device/heartbeat`        | Ninguna        | Heartbeat periódico                      |
| GET    | `/rboxes/device/my-cameras`       | Ninguna        | Cámaras por serial (alternativa a init)  |

> *`/rboxes/device/init` requiere `serial` + `secret` en el body.

### MediaMTX (`/mediamtx`)

| Método | Endpoint                  | Auth requerida | Descripción                      |
|--------|---------------------------|----------------|----------------------------------|
| GET    | `/mediamtx/paths`         | JWT            | Lista streams activos            |
| POST   | `/mediamtx/paths/{path}`  | JWT admin      | Crea configuración para un path  |

### Cámaras (`/cameras`)

| Método | Endpoint           | Auth requerida | Descripción            |
|--------|--------------------|----------------|------------------------|
| POST   | `/cameras/`        | JWT            | Registrar nueva cámara |
| GET    | `/cameras/`        | JWT            | Listar cámaras         |
| GET    | `/cameras/{id}`    | JWT            | Detalle de cámara      |
| PUT    | `/cameras/{id}`    | JWT            | Actualizar cámara      |

### PTZ (`/ptz`)

| Método | Endpoint                  | Auth requerida | Descripción              |
|--------|---------------------------|----------------|--------------------------|
| POST   | `/ptz/command`            | Ninguna        | Enviar comando PTZ       |
| GET    | `/ptz/command/{camera_id}`| Ninguna        | R-Box obtiene comando    |
| POST   | `/ptz/ack`                | Ninguna        | R-Box confirma ejecución |

### Health (`/health`)

| Método | Endpoint    | Auth requerida | Descripción                   |
|--------|-------------|----------------|-------------------------------|
| GET    | `/health/`  | Ninguna        | Estado del API, DB y MediaMTX |

---

## Configuración

### Variables de entorno (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/api_central
SECRET_KEY=supersecretkey123456789
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
RBOX_TOKEN_EXPIRE_HOURS=24
PLAYBACK_TOKEN_EXPIRE_MINUTES=15
MEDIAMTX_API_URL=http://localhost:9997
```

### MediaMTX (`/opt/mediamtx.yml`)

```yaml
api: yes
apiAddress: 127.0.0.1:9997                                    # Solo accesible localmente
externalAuthenticationURL: http://127.0.0.1:8003/auth/validate # FastAPI valida todo

webrtcICEServers2:
  - url: stun:stun.l.google.com:19302

webrtcAdditionalHosts:
  - 136.119.96.176

webrtcICEUDPMuxAddress: :8189
webrtcICETCPMuxAddress: :8189

paths:
  "~^.*$":
    disablePublisherOverride: no
```

### iptables (reglas activas)

```bash
# HLS bloqueado externamente
iptables -A INPUT -p tcp --dport 8888 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8888 -j DROP

# API MediaMTX bloqueada externamente
iptables -A INPUT -p tcp --dport 9997 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 9997 -j DROP

# WebRTC :8889 ABIERTO (protegido por externalAuth)
# RTSP :8554 ABIERTO (protegido por externalAuth)
# FastAPI :8003 ABIERTO
# ICE mux :8189 ABIERTO
```

> **Nota**: La protección de streams la hace MediaMTX externalAuth + FastAPI.

---

## Iniciar servicios

```bash
# MediaMTX (servicio systemd)
sudo systemctl start mediamtx

# FastAPI
cd /home/yandriuchuari/api_central
uv run python -m app.main

# Verificar
curl http://localhost:8003/health/
curl http://localhost:9997/v3/paths/list
```

### Página de prueba

Abrir en el navegador: `http://136.119.96.176:8003/stream-auth/test`

Permite hacer login, ver cámaras activas y abrir viewers con un click.

### Ver streams activos desde CLI

```bash
cd /home/yandriuchuari/api_central
uv run camera_viewer.py
```

---

## Estructura del proyecto

```
api_central/
├── app/
│   ├── main.py              # FastAPI, routers, CORS
│   ├── core/
│   │   ├── config.py        # Settings desde .env
│   │   ├── database.py      # PostgreSQL async (SQLAlchemy)
│   │   ├── security.py      # JWT login + get_current_user + require_admin
│   │   └── token_store.py   # OpaqueTokenStore (create, validate, revoke)
│   ├── db/
│   │   ├── config.py        # Configuración DB (psycopg pool)
│   │   └── connection.py    # DatabasePool con reintentos
│   ├── models/              # SQLAlchemy ORM
│   │   ├── camera.py
│   │   ├── company.py
│   │   ├── rbox.py
│   │   └── user.py
│   ├── routers/
│   │   ├── auth.py          # Login, rbox-token, service-token, validate, tokens
│   │   ├── stream_auth.py   # Token de stream, viewer HTML, test page
│   │   ├── cameras.py       # CRUD cámaras
│   │   ├── mediamtx.py      # Consultar MediaMTX API
│   │   ├── rboxes.py        # Gestión R-Boxes + device/init + device/my-cameras
│   │   ├── ptz.py           # Control PTZ remoto por polling
│   │   ├── streams.py       # (stub)
│   │   ├── playback.py      # (stub)
│   │   ├── companies.py     # Gestión empresas (TODO)
│   │   └── health.py        # Health check
│   ├── schemas/             # Pydantic (request/response)
│   ├── repositories/        # Acceso a DB
│   ├── services/            # Lógica de negocio
│   └── utils/               # Utilidades
├── scripts/
│   ├── inference_client.py  # Cliente inferencia: lee RTSP, infiere, republica con audio
│   ├── rbox_client.py       # Cliente R-Box: init + publicar cámaras
│   ├── dashboard_webrtc.html # Dashboard WebRTC de prueba (video + audio)
│   └── test_flow.py         # Test completo del flujo API
├── camera_viewer.py         # CLI: streams activos + links con token opaco
├── requirements.txt
├── .env
└── README.md
```

---

## Scripts de prueba

### Test completo del flujo

```bash
cd /home/yandriuchuari/api_central

# Test básico
python scripts/test_flow.py --server 136.119.96.176

# Test con R-Box
python scripts/test_flow.py --server 136.119.96.176 --rbox-serial RBOX_001

# Test con cámara específica
python scripts/test_flow.py --server 136.119.96.176 --camera CAM1 --rbox-serial RBOX_001
```

### Cliente de inferencia

```bash
# Automático: obtiene token, lee video+audio, aplica inferencia, republica
python scripts/inference_client.py --server 136.119.96.176 --camera CAM1 --auto-token

# Con token existente
python scripts/inference_client.py --server 136.119.96.176 --camera CAM1 --token "TOKEN"

# Especificar nombre de salida diferente
python scripts/inference_client.py --server 136.119.96.176 --camera CAM1 \
  --auto-token --output-suffix "_YOLO"
```

### Cliente R-Box

```bash
# La R-Box se inicializa, obtiene cámaras y publica streams
python scripts/rbox_client.py --serial RBOX_001 --secret mi_secreto --server 136.119.96.176
```

### Dashboard WebRTC

Abrir `scripts/dashboard_webrtc.html` en un navegador web.
Configurar IP del servidor, credenciales, y conectar streams.

---

**Última actualización**: 31 de marzo de 2026
