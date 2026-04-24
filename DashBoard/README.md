# Dashboard Robiotec

Dashboard web de videovigilancia, telemetria GPS y mapa operativo para Robiotec.

## Stack actual

- Backend: `aiohttp`
- Base de datos: PostgreSQL con `psycopg3`
- Frontend: HTML server-side + `static/web_app.js`
- Video: MediaMTX + integracion con API de proteccion de streams
- Telemetria: `localhost:8004/{unique_id}/gps`
- Geografia minera: GeoPackage local ARCOM + endpoints REST locales

## Modulos existentes

- `web_app.py`: app principal HTTP, vistas HTML y endpoints REST
- `repositories/`: acceso a PostgreSQL por dominio
- `surveillance/app_context.py`: runtime de camaras, telemetria y proyeccion operativa
- `surveillance/telemetry/`: servicio de telemetria y puente API
- `surveillance/arcom.py`: lookup espacial local de concesiones
- `controllers/register_cameras/register_camera.py`: generador RTSP por fabricante
- `controllers/api_protect_stream/protect_stream.py`: integracion con viewer protegido
- `db/bootstrap.py`: bootstrap idempotente de seed inicial

## Estado de la refactorizacion

Lo que ya existe:

- CRUD de usuarios, organizaciones, vehiculos y camaras
- mapa operativo con telemetria
- capa ARCOM local
- integracion base con MediaMTX
- control de acceso por rol/nivel

Lo que estaba debil y ya empezo a corregirse:

- contraseñas en texto plano
- seed inicial inconsistente
- roles heredados (`developer/admin/engineer/client`) mezclados con roles operativos
- README vacio

## Mejoras aplicadas en esta fase

- hashing de contraseñas con `PBKDF2-SHA256`
- compatibilidad hacia atras con contraseñas historicas en texto plano
- rehash automatico al iniciar sesion si el usuario aun tenia password legado
- bootstrap idempotente en `db/bootstrap.py`
- seed inicial de:
  - `superadmin` por defecto (`admin`)
  - organizacion demo
  - vehiculo demo con telemetria API
  - camara demo asociada
- alias de roles para aceptar `superadmin`, `administrador` y `operador`

## Variables de entorno importantes

- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_BOOTSTRAP_ON_STARTUP=true`
- `DEFAULT_SUPERADMIN_USERNAME=admin`
- `DEFAULT_SUPERADMIN_PASSWORD=Robiotec@2026`
- `DEFAULT_SUPERADMIN_EMAIL=admin@robiotec.local`
- `DEFAULT_DEMO_ORG_NAME=ROBIOTEC DEMO`
- `DEFAULT_DEMO_VEHICLE_UNIQUE_ID=DEMO-CAR-001`
- `DEFAULT_DEMO_CAMERA_UNIQUE_ID=DEMO-CAM-001`
- `PASSWORD_HASH_ITERATIONS=390000`
- `JWT_SECRET`
- `JWT_ACCESS_TOKEN_TTL_SECONDS=3600`
- `TELEMETRY_REFRESH_SECONDS=1`
- `ARCOM_GPKG_PATH=/home/robiotec/ARCOM/arcom_catastro.gpkg`

## Como correr

### 1. App web

```bash
cd /home/robiotec/DashBoard
uv run web_app.py
```

### 2. Bootstrap manual de seed

```bash
cd /home/robiotec/DashBoard
uv run python -m db.bootstrap
```

### 3. ARCOM sync

```bash
cd /home/robiotec/ARCOM
python3 sync_arcom.py --watch
```

## Endpoints clave

- `POST /api/login`
- `POST /api/logout`
- `GET /api/auth/session`
- `GET /api/users`
- `GET /api/organizations`
- `GET /api/vehicle-registry`
- `GET /api/cameras`
- `GET /api/devices`
- `GET /api/arcom/concession-lookup`
- `GET /api/arcom/concessions`
- `POST /api/camera-rtsp-preview`

## Auth actual

1. `POST /api/login` valida usuario/password.
2. El backend devuelve:
   - cookie de sesion para la web
   - `access_token` Bearer para la API
3. La API ahora acepta autenticacion por:
   - cookie firmada
   - `Authorization: Bearer <token>`

## Flujo de video actual

1. Usuario inicia sesion en el dashboard.
2. Backend resuelve sesion autenticada.
3. Para video protegido, el backend usa `ProtectedStreamViewerClient`.
4. La API de streams entrega un token de acceso del viewer.
5. El frontend recibe una URL segura del visor, no la credencial RTSP cruda.

Nota:
El siguiente paso grande de refactor debe mover esto a tokens opacos propios en BD (`opaque_video_tokens`) con expiracion corta y scope por stream/path.

## Flujo de telemetria actual

1. El vehiculo tiene `telemetry_mode=api`.
2. El backend consulta `http://localhost:8004/{unique_id}/gps`
3. `surveillance.telemetry.service` mantiene el ultimo estado.
4. El mapa refresca segun `TELEMETRY_REFRESH_SECONDS`.

## Roles objetivo

- `superadmin`: control total del sistema
- `administrador`: gestion operativa
- `operador`: solo visualizacion

Compatibilidad actual:

- `superadmin` se trata como capacidad de desarrollador total
- `administrador` se trata como admin
- `operador` ya existe en capa de permisos del dashboard

## Proximo plan recomendado

1. Unificar modelo de roles y permisos en BD y frontend.
2. Sustituir sesion cookie firmada por JWT real + refresh strategy.
3. Crear tabla `opaque_video_tokens` y emitir tokens propios.
4. Normalizar entidades:
   - `vehicles.unique_id`
   - `cameras.unique_id`
   - `telemetry_latest`
   - `telemetry_history`
   - `mining_concessions`
   - `geofence_events`
   - `audit_logs`
5. Separar `web_app.py` en routers por dominio.
6. Completar tipos de camara faltantes:
   - `ptz`
   - `externa_manual`
7. Agregar runner formal de migraciones.
