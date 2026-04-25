# SVI — Sistema de Vigilancia Inteligente

Plataforma de monitoreo en tiempo real para vehículos, drones y cámaras IP desarrollada por **Robiotec / Grupo Minero Bonanza** en Ecuador. Integra telemetría MAVLink, video en streaming, catastro geoespacial y tráfico aéreo sobre un dashboard web interactivo.

---

## Arquitectura general

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERNET / LAN                           │
└──────────┬─────────────────────┬───────────────────────────────┘
           │                     │
    ┌──────▼──────┐       ┌──────▼──────┐
    │  DashBoard  │       │ ApiCentral  │
    │  aiohttp    │◄─────►│  FastAPI    │
    │  :8001      │       │  :8004      │
    └──────┬──────┘       └──────┬──────┘
           │                     │
    ┌──────▼──────┐       ┌──────▼──────┐
    │ PostgreSQL  │       │ PostgreSQL  │
    │ (dashboard) │       │(apicentral) │
    └─────────────┘       └──────┬──────┘
                                 │
                    ┌────────────▼────────────┐
                    │      MediaMTX           │
                    │  Streaming Server :8989 │
                    │  (WebRTC / HLS / RTSP)  │
                    └────────────▲────────────┘
                                 │
           ┌─────────────────────┤
           │                     │
    ┌──────▼──────┐       ┌──────▼──────┐
    │ robiotec    │       │   OpenSky   │
    │ Telemetry   │       │   Fetch     │
    │ MAVLink→API │       │ (cada 10s)  │
    └──────▲──────┘       └─────────────┘
           │
    ┌──────▼──────┐
    │ mavlink-    │
    │ router      │
    │ (UDP relay) │
    └──────▲──────┘
           │
    ┌──────▼──────┐
    │   Dron /    │
    │ Autopiloto  │
    │ (ArduPilot) │
    └─────────────┘
```

---

## Componentes

### 1. DashBoard (`/DashBoard`)
Aplicación web principal. Servidor **aiohttp** en el puerto **8001**.

- Mapa interactivo Leaflet con capas:
  - Posición en tiempo real de drones y vehículos
  - Tracks de vuelo (polylines) con estado `ground → flying → landed`
  - Tráfico aéreo (OpenSky Network) con icono SVG rotado según heading
  - Catastro ARCOM (GeoPackage)
- Panel de telemetría: posición GPS, altitud (MSL y AGL), velocidad (m/s), batería, modo de vuelo, estado del sistema
- Gestión de cámaras IP con streaming WebRTC/HLS via MediaMTX
- Autenticación JWT con roles
- Exportación de tracks de ruta en JSON

**Stack:** Python 3.11, aiohttp, psycopg3, Leaflet.js, Video.js

**Inicio manual:**
```bash
cd /home/robiotec/SVI/DashBoard
uv run web_app.py
```

---

### 2. ApiCentral (`/ApiCentral`)
API REST backend. **FastAPI + uvicorn** en el puerto **8004** como servicio systemd.

**Endpoints principales:**

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/telemetry/{vehicle_id}/update-gps` | Recibe datos MAVLink del dron |
| `GET`  | `/telemetry/{vehicle_id}/gps` | Devuelve última posición del vehículo |
| `GET`  | `/telemetry/` | Lista vehículos con datos activos |
| `POST` | `/auth/login` | Autenticación, devuelve JWT |
| `GET`  | `/stream-auth/verify` | Valida token para acceso a streams |
| `POST` | `/ptz/{camera_id}/move` | Control PTZ de cámaras |
| `GET`  | `/health/` | Health check |

**Servicio systemd:**
```bash
systemctl status apicentral.service
systemctl restart apicentral.service
```

---

### 3. robiotecTelemetry (`/robiotecTelemetry`)
Puente MAVLink → ApiCentral. Lee mensajes del autopiloto y los publica en la API central cada segundo.

**Mensajes MAVLink procesados:**
- `GLOBAL_POSITION_INT` → lat, lon, altitud MSL, altitud AGL (`relative_alt`), velocidad
- `HEARTBEAT` → modo de vuelo, estado del sistema, armado
- `BATTERY_STATUS` → voltaje, corriente, porcentaje de batería
- `GPS_RAW_INT` → tipo de fix GPS, satélites visibles

**Flujo de datos:**
```
Autopiloto → mavlink-router (UDP :14560) → robiotecTelemetry.py → ApiCentral → DashBoard
```

**Servicio systemd:**
```bash
systemctl status robiotec-telemetry.service
systemctl restart robiotec-telemetry.service
```

**Logs:**
```bash
tail -f /home/robiotec/SVI/robiotecTelemetry/robiotecTelemetry.log
```

---

### 4. OpenSky (`/opensky`)
Servicio de tráfico aéreo. Consulta la API pública de OpenSky Network cada 10 segundos y guarda el resultado en `opensky_data.json`. El DashBoard consume ese archivo local (sin llamar a OpenSky directamente) para mostrar aeronaves en el mapa.

**Bounding box Ecuador:** `(-10, -82, 5, -70)`

**Formato del JSON guardado:**
```json
{
  "ts": 1714000000,
  "aircraft": [
    {
      "icao24": "abc123",
      "callsign": "AV204",
      "lon": -78.5,
      "lat": -0.2,
      "alt_m": 10500,
      "on_ground": false,
      "vel_ms": 240.5,
      "heading": 180
    }
  ]
}
```

**Servicio systemd:**
```bash
systemctl status opensky.service
tail -f /home/robiotec/SVI/opensky/opensky.log
```

---

### 5. MediaMTX (`/mediamtx`)
Servidor de streaming multimedia. Expone streams de cámara en WebRTC (`:8989`), HLS (`:8988`) y RTSP (`:8654`).

**Servicios systemd:**
```bash
systemctl status mediamtx.service          # Servidor principal (cámaras registradas)
systemctl status mediamtx-api.service      # Instancia API de validación de tokens
systemctl status drone-relay.service       # Relay RTSP dron → MediaMTX API
```

---

### 6. ARCOM (`/arcom`)
Descarga y mantiene actualizado el catastro predial del sistema ARCOM (Ecuador) en formato GeoPackage. Se superpone en el mapa del DashBoard como capa vectorial.

**Timer systemd:** se ejecuta todos los lunes a las 02:00 UTC.
```bash
systemctl status arcom_update.timer
systemctl list-timers arcom_update.timer
```

---

## Requisitos del sistema

| Componente | Versión mínima |
|---|---|
| Python | 3.11 |
| PostgreSQL | 14+ |
| uv (gestor de paquetes) | latest |
| systemd | cualquier versión moderna |

---

## Instalación

### 1. Clonar y configurar entornos

```bash
# ApiCentral
cd /home/robiotec/SVI/ApiCentral
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# DashBoard
cd /home/robiotec/SVI/DashBoard
pip install uv
uv sync
```

### 2. Configurar variables de entorno

Copiar los archivos de ejemplo y completar los valores:

```bash
cp ApiCentral/.env.example    ApiCentral/.env
cp DashBoard/.env.example     DashBoard/.env
cp robiotecTelemetry/.env.example  robiotecTelemetry/.env
```

**Variables críticas que DEBEN configurarse:**

| Variable | Archivo | Descripción |
|---|---|---|
| `SECRET_KEY` | ApiCentral/.env | JWT secret (mín. 32 caracteres) |
| `JWT_SECRET` | DashBoard/.env | JWT secret del DashBoard |
| `WEB_SESSION_SECRET` | DashBoard/.env | Secreto de sesión web |
| `DB_PASSWORD` | ambos .env | Contraseña de PostgreSQL |
| `PUBLIC_HOST` | ApiCentral/.env | IP pública del servidor |
| `MEDIAMTX_HOST` | DashBoard/.env | IP pública para URLs de stream |

### 3. Inicializar bases de datos

```bash
# ApiCentral
psql -U postgres -f /home/robiotec/SVI/ApiCentral/db/init_apicentral.sql

# DashBoard
cd /home/robiotec/SVI/DashBoard && uv run db/bootstrap.py
```

### 4. Habilitar servicios systemd

```bash
systemctl enable --now apicentral.service
systemctl enable --now robiotec-telemetry.service
systemctl enable --now opensky.service
systemctl enable --now mediamtx.service
systemctl enable --now arcom_update.timer
```

---

## Servicios activos

| Servicio | Puerto | Descripción |
|---|---|---|
| `apicentral.service` | 8004 | API REST backend |
| `mediamtx.service` | 8989 / 8988 / 8654 | Streaming de cámaras |
| `mediamtx-api.service` | — | Instancia de validación de streams |
| `drone-relay.service` | — | Relay RTSP del dron |
| `robiotec-telemetry.service` | — | Telemetría MAVLink → API |
| `opensky.service` | — | Tráfico aéreo OpenSky Ecuador |
| `arcom_update.timer` | — | Actualización catastro (lunes 02:00) |

**El DashBoard NO corre como servicio systemd.** Se inicia manualmente:
```bash
cd /home/robiotec/SVI/DashBoard && uv run web_app.py
```

---

## Telemetría del dron

### Detección de vuelo

El sistema usa `relative_alt` (altitud AGL sobre el punto de despegue) para determinar el estado del dron, **no** la altitud MSL. Esto es crítico en zonas de alta montaña como los Andes, donde el GPS puede reportar altitudes absolutas elevadas estando el dron en tierra.

| Estado | Condición |
|---|---|
| `ground` | `relative_alt < DRONE_TAKEOFF_ALT_M` (por defecto 100 m) |
| `flying` | `relative_alt >= DRONE_TAKEOFF_ALT_M` |
| `landed` | Vuelta a `relative_alt < DRONE_TAKEOFF_ALT_M` después de haber volado |

El umbral se configura en `DashBoard/.env`:
```env
DRONE_TAKEOFF_ALT_M=100
```

### Tracks de ruta

- Durante el vuelo se dibuja una polyline cian en el mapa
- Al aterrizar la polyline cambia a gris punteado
- El botón **Exportar rutas** descarga un JSON con todos los tracks y los limpia del mapa

---

## Variables de entorno — referencia rápida

### ApiCentral
```env
PUBLIC_HOST=          # IP pública del servidor
API_PORT=8004
SECRET_KEY=           # JWT secret ≥ 32 caracteres
CORS_EXTRA_ORIGINS=   # orígenes extra separados por coma (dev: http://localhost:3000)
DB_HOST=127.0.0.1
DB_NAME=apicentral
DB_USER=apicentraluser
DB_PASSWORD=
MEDIAMTX_API_URL=http://127.0.0.1:9998
OPENSKY_LAMIN=-5.0    # Bounding box Ecuador
OPENSKY_LOMIN=-81.0
OPENSKY_LAMAX=2.0
OPENSKY_LOMAX=-75.0
```

### DashBoard
```env
JWT_SECRET=           # JWT secret del DashBoard
WEB_SESSION_SECRET=   # Secreto de sesión (cookie)
DB_HOST=127.0.0.1
DB_NAME=dashboard
DB_USER=dashboarduser
DB_PASSWORD=
STREAM_API_BASE_URL=http://127.0.0.1:8004
GPS_API_BASE_URL=http://127.0.0.1:8004
MEDIAMTX_HOST=        # IP pública para URLs de stream WebRTC
MEDIAMTX_WEBRTC_PORT=8989
DRONE_TAKEOFF_ALT_M=100
ARCOM_GPKG_PATH=/ruta/al/arcom_catastro.gpkg
```

### robiotecTelemetry
```env
TELEMETRY_API_URL=http://<IP>:8004/telemetry/DRONE/update-gps
MAV_CONNECTION=udp:127.0.0.1:14560
SEND_INTERVAL_SEC=1.0
RECONNECT_DELAY_SEC=5.0
DRONE_TIMEOUT_SEC=10.0
```

---

## Estructura del repositorio

```
SVI/
├── ApiCentral/              # API REST (FastAPI)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/config.py   # Configuración centralizada con pydantic-settings
│   │   └── routers/         # auth, telemetry, ptz, stream_auth, health, opensky
│   ├── db/init_apicentral.sql
│   ├── mediamtx/mediamtx.yml
│   └── .env.example
├── DashBoard/               # Aplicación web (aiohttp)
│   ├── web_app.py           # Punto de entrada, ~3800 líneas
│   ├── surveillance/        # Módulos de lógica de negocio
│   │   ├── telemetry/       # api_bridge.py, service.py
│   │   ├── jwt_utils.py
│   │   └── config.py
│   ├── repositories/        # Acceso a datos (cámaras, usuarios, vehículos)
│   ├── templates/           # HTML Jinja-like con reemplazo de tokens
│   ├── static/              # web_app.js, web_app.css
│   ├── db/                  # connection.py, config.py, bootstrap.py
│   └── .env.example
├── robiotecTelemetry/       # Puente MAVLink → ApiCentral
│   ├── robiotecTelemetry.py
│   ├── robiotecTelemetry.sh
│   └── .env.example
├── opensky/                 # Tráfico aéreo OpenSky Network
│   ├── opensky_fetch.py
│   ├── opensky.sh
│   └── opensky_data.json    # Caché local (actualizado cada 10s)
├── arcom/                   # Catastro predial Ecuador
│   ├── download_arcom.py
│   └── arcom_update.sh
├── mediamtx/                # Binario y config de MediaMTX
└── mavlink-router/          # Router UDP para mensajes MAVLink
```

---

## Seguridad

- Los archivos `.env` están excluidos del repositorio por `.gitignore` — nunca hacer commit de credenciales
- Usar `.env.example` como plantilla; completar los valores reales en `.env`
- `JWT_SECRET` y `WEB_SESSION_SECRET` deben ser cadenas aleatorias seguras (mín. 32 caracteres)
- La documentación automática de FastAPI (`/docs`, `/redoc`) está deshabilitada en producción
- CORS configurado solo para el host público; orígenes de desarrollo se agregan via `CORS_EXTRA_ORIGINS`

---

## Desarrollado por

**Robiotec — Grupo Minero Bonanza**  
Ecuador · 2025
