#!/usr/bin/env python3
"""
Script de prueba para generar y validar tokens opacos.
Prueba el flujo completo: login → stream token → validate MediaMTX → revoke.

Uso:
    python3 scripts/test_tokens.py
    python3 scripts/test_tokens.py --host 136.119.96.176
    python3 scripts/test_tokens.py --camera CAM2
"""

import argparse
import sys
import json
import base64
import requests

# ─── Configuración por defecto ───
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8003
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin123"
DEFAULT_CAMERA = "CAM1"


class Colors:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def log_ok(msg):
    print(f"  {Colors.OK}✓{Colors.END} {msg}")


def log_fail(msg):
    print(f"  {Colors.FAIL}✗{Colors.END} {msg}")


def log_info(msg):
    print(f"  {Colors.INFO}→{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.BOLD}{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}{Colors.END}")


def main():
    parser = argparse.ArgumentParser(description="Test de tokens opacos API Central")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host de la API (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Puerto (default: {DEFAULT_PORT})")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"Usuario (default: {DEFAULT_USER})")
    parser.add_argument("--password", default=DEFAULT_PASS, help=f"Password (default: {DEFAULT_PASS})")
    parser.add_argument("--camera", default=DEFAULT_CAMERA, help=f"ID de cámara (default: {DEFAULT_CAMERA})")
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}"
    session = requests.Session()
    passed = 0
    failed = 0
    jwt = None
    token = None
    token_id = None

    # ═══════════════════════════════════════════════
    # 1. Health Check
    # ═══════════════════════════════════════════════
    section("1. Health Check")
    try:
        r = session.get(f"{base}/health/", timeout=5)
        data = r.json()
        if r.status_code == 200 and data.get("status") == "ok":
            log_ok(f"API saludable — DB: {data.get('database')}")
            passed += 1
        else:
            log_fail(f"Status inesperado: {r.status_code} → {data}")
            failed += 1
    except requests.ConnectionError:
        log_fail(f"No se puede conectar a {base}")
        print(f"\n{Colors.FAIL}Verifica que la API esté corriendo.{Colors.END}")
        sys.exit(1)

    # ═══════════════════════════════════════════════
    # 2. Login
    # ═══════════════════════════════════════════════
    section("2. Login")
    r = session.post(f"{base}/auth/login", json={"username": args.user, "password": args.password})
    if r.status_code == 200:
        jwt = r.json()["access_token"]
        # Decodificar payload del JWT para saber el rol
        payload_b64 = jwt.split(".")[1] + "=="
        jwt_payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        user_role = jwt_payload.get("role", "unknown")
        is_admin = user_role == "admin"
        log_ok(f"JWT obtenido: {jwt[:40]}...")
        log_info(f"Rol: {user_role}")
        passed += 1
    else:
        log_fail(f"Login falló: {r.status_code} → {r.text}")
        failed += 1
        print(f"\n{Colors.FAIL}Sin JWT no se puede continuar.{Colors.END}")
        sys.exit(1)

    # ═══════════════════════════════════════════════
    # 3. Login con credenciales incorrectas (debe fallar)
    # ═══════════════════════════════════════════════
    section("3. Login incorrecto (debe dar 401)")
    r = session.post(f"{base}/auth/login", json={"username": args.user, "password": "wrong_password"})
    if r.status_code == 401:
        log_ok(f"Rechazado correctamente: {r.json()['detail']}")
        passed += 1
    else:
        log_fail(f"Esperaba 401, recibí {r.status_code}")
        failed += 1

    # ═══════════════════════════════════════════════
    # 4. Generar stream token
    # ═══════════════════════════════════════════════
    section(f"4. Generar token opaco para '{args.camera}'")
    headers = {"Authorization": f"Bearer {jwt}"}
    r = session.post(f"{base}/stream-auth/stream/token/{args.camera}", headers=headers)
    if r.status_code == 200:
        data = r.json()
        token = data["token"]
        token_id = data["token_id"]
        log_ok(f"Token: {token[:30]}...")
        log_ok(f"Token ID: {token_id}")
        log_ok(f"Expira en: {data['expires_in']}s")
        log_info(f"Viewer URL: {data['stream_url']}")
        passed += 1
    else:
        log_fail(f"Error generando token: {r.status_code} → {r.text}")
        failed += 1

    # ═══════════════════════════════════════════════
    # 5. Validate MediaMTX — RTSP read con token
    # ═══════════════════════════════════════════════
    section("5. Validate MediaMTX (simula RTSP read)")
    if token:
        r = session.post(f"{base}/auth/validate", json={
            "user": "",
            "password": token,
            "ip": "192.168.1.100",
            "action": "read",
            "path": args.camera,
            "protocol": "rtsp",
            "query": "",
        })
        if r.status_code == 200 and r.json().get("ok"):
            log_ok("MediaMTX permitiría esta conexión RTSP")
            passed += 1
        else:
            log_fail(f"Validate falló: {r.status_code} → {r.text}")
            failed += 1
    else:
        log_fail("Sin token, no se puede probar")
        failed += 1

    # ═══════════════════════════════════════════════
    # 6. Validate MediaMTX — WebRTC read con query param
    # ═══════════════════════════════════════════════
    section("6. Validate MediaMTX (simula WebRTC read)")
    if token:
        # Generar un segundo token para WebRTC
        r2 = session.post(f"{base}/stream-auth/stream/token/{args.camera}", headers=headers)
        if r2.status_code == 200:
            token_webrtc = r2.json()["token"]
            r = session.post(f"{base}/auth/validate", json={
                "user": "",
                "password": "",
                "ip": "192.168.1.100",
                "action": "read",
                "path": args.camera,
                "protocol": "webrtc",
                "query": f"token={token_webrtc}",
            })
            if r.status_code == 200 and r.json().get("ok"):
                log_ok("MediaMTX permitiría esta conexión WebRTC")
                passed += 1
            else:
                log_fail(f"Validate WebRTC falló: {r.status_code} → {r.text}")
                failed += 1
        else:
            log_fail("No se pudo generar segundo token")
            failed += 1
    else:
        log_fail("Sin token, no se puede probar")
        failed += 1

    # ═══════════════════════════════════════════════
    # 7. Validate sin token (debe dar 401)
    # ═══════════════════════════════════════════════
    section("7. Validate sin token (debe dar 401)")
    r = session.post(f"{base}/auth/validate", json={
        "user": "",
        "password": "",
        "ip": "192.168.1.100",
        "action": "read",
        "path": args.camera,
        "protocol": "rtsp",
        "query": "",
    })
    if r.status_code == 401:
        log_ok(f"Rechazado correctamente: {r.json()['detail']}")
        passed += 1
    else:
        log_fail(f"Esperaba 401, recibí {r.status_code}")
        failed += 1

    # ═══════════════════════════════════════════════
    # 8. Validate con token inventado (debe dar 401)
    # ═══════════════════════════════════════════════
    section("8. Validate con token falso (debe dar 401)")
    r = session.post(f"{base}/auth/validate", json={
        "user": "",
        "password": "token_falso_inventado_12345",
        "ip": "192.168.1.100",
        "action": "read",
        "path": args.camera,
        "protocol": "rtsp",
        "query": "",
    })
    if r.status_code == 401:
        log_ok(f"Rechazado correctamente: {r.json()['detail']}")
        passed += 1
    else:
        log_fail(f"Esperaba 401, recibí {r.status_code}")
        failed += 1

    # ═══════════════════════════════════════════════
    # 9. Validate path incorrecto (token válido, path diferente)
    # ═══════════════════════════════════════════════
    section("9. Token válido pero path incorrecto (debe dar 401)")
    # Generar nuevo token para CAM específica
    r3 = session.post(f"{base}/stream-auth/stream/token/{args.camera}", headers=headers)
    if r3.status_code == 200:
        token_path_test = r3.json()["token"]
        r = session.post(f"{base}/auth/validate", json={
            "user": "",
            "password": token_path_test,
            "ip": "192.168.1.100",
            "action": "read",
            "path": "OTRA_CAMARA_INEXISTENTE",
            "protocol": "rtsp",
            "query": "",
        })
        if r.status_code == 401:
            log_ok(f"Rechazado correctamente: {r.json()['detail']}")
            passed += 1
        else:
            log_fail(f"Esperaba 401, recibí {r.status_code} → {r.text}")
            failed += 1
    else:
        log_fail("No se pudo generar token para test de path")
        failed += 1

    # ═══════════════════════════════════════════════
    # 10. Revocar token
    # ═══════════════════════════════════════════════
    section("10. Revocar token")
    if not is_admin:
        log_info(f"Usuario '{args.user}' tiene rol '{user_role}' → revoke requiere admin, verificando 403")
        if token_id:
            r = session.post(f"{base}/auth/tokens/revoke/{token_id}", headers=headers)
            if r.status_code == 403:
                log_ok("Rechazado correctamente (no es admin)")
                passed += 1
            else:
                log_fail(f"Esperaba 403, recibí {r.status_code} → {r.text}")
                failed += 1
        else:
            log_fail("Sin token_id")
            failed += 1
    elif token_id:
        r = session.post(f"{base}/auth/tokens/revoke/{token_id}", headers=headers)
        if r.status_code == 200:
            log_ok(f"Token {token_id} revocado")
            passed += 1
        else:
            log_fail(f"Revoke falló: {r.status_code} → {r.text}")
            failed += 1

        # Verificar que el token revocado ya no funciona
        r = session.post(f"{base}/auth/validate", json={
            "user": "",
            "password": token,
            "ip": "192.168.1.100",
            "action": "read",
            "path": args.camera,
            "protocol": "rtsp",
            "query": "",
        })
        if r.status_code == 401:
            log_ok("Token revocado correctamente rechazado")
            passed += 1
        else:
            log_fail(f"Token revocado aún funciona: {r.status_code}")
            failed += 1
    else:
        log_fail("Sin token_id para revocar")
        failed += 1

    # ═══════════════════════════════════════════════
    # 11. Acciones internas (api/metrics) permitidas sin token
    # ═══════════════════════════════════════════════
    section("11. Acciones internas (api, metrics)")
    for action in ("api", "metrics"):
        r = session.post(f"{base}/auth/validate", json={
            "user": "", "password": "", "ip": "127.0.0.1",
            "action": action, "path": "", "protocol": "", "query": "",
        })
        if r.status_code == 200:
            log_ok(f"Acción '{action}' permitida sin token")
            passed += 1
        else:
            log_fail(f"Acción '{action}' bloqueada: {r.status_code}")
            failed += 1

    # ═══════════════════════════════════════════════
    # Resumen
    # ═══════════════════════════════════════════════
    total = passed + failed
    print(f"\n{'═' * 50}")
    print(f"  RESULTADO: {Colors.OK}{passed}{Colors.END}/{total} pasaron", end="")
    if failed:
        print(f" — {Colors.FAIL}{failed} fallaron{Colors.END}")
    else:
        print(f" — {Colors.OK}TODO OK{Colors.END}")
    print(f"{'═' * 50}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
