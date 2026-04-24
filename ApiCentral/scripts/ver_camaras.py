"""
Script para ver múltiples cámaras RTSP desde MediaMTX en cuadrícula con OpenCV.

Uso:
    python ver_camaras.py

Dependencias:
    pip install opencv-python numpy screeninfo

Nota: La autenticación RTSP está desactivada, cualquier persona puede ver los streams.
"""


import sys
import cv2
import numpy as np
import math
import threading
import time
from screeninfo import get_monitors

# ─── Configuración ───────────────────────────────────────────────────────────

# MediaMTX RTSP Server
MEDIAMTX_HOST = "136.119.96.176"
RTSP_PORT = 8554

# Lista de cámaras a visualizar — agregar o quitar según se necesite
CAMARAS = [
    "CAM1",
    "CAM2",
    "CAM3",
]


# ─── Funciones ───────────────────────────────────────────────────────────────

def mostrar_videos_rtsp(rtsp_urls, camera_names):
    """
    Abre múltiples streams RTSP y los muestra en una ventana en cuadrícula.
    Se adapta al número de cámaras y al tamaño del monitor principal.
    """
    # Obtener tamaño del monitor principal
    monitor = get_monitors()[0]
    screen_w, screen_h = monitor.width, monitor.height

    n = len(rtsp_urls)
    if n == 0:
        print("No hay cámaras para mostrar.")
        return

    # Calcular filas y columnas óptimas para la cuadrícula
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)

    # Tamaño de cada video
    cell_w = screen_w // cols
    cell_h = screen_h // rows

    # Inicializar capturas con timeout y propiedades
    caps = []
    for url in rtsp_urls:
        cap = cv2.VideoCapture(url)
        # Configurar timeout de 5 segundos para OpenCV
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 30)
        caps.append(cap)

    def leer_frame(cap, idx, frames, locks, estado):
        """Lee frames de forma continua con manejo de errores."""
        reintentos = 0
        max_reintentos = 3
        
        while reintentos < max_reintentos:
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (cell_w, cell_h))
                reintentos = 0  # Reset reintentos si es exitoso
                with locks[idx]:
                    frames[idx] = frame
                    estado[idx] = "OK"
            else:
                reintentos += 1
                with locks[idx]:
                    estado[idx] = f"Reconectando ({reintentos}/{max_reintentos})"
                time.sleep(1)

        # Si fallan todos los reintentos, mostrar error
        with locks[idx]:
            estado[idx] = "DESCONECTADO"
            frames[idx] = crear_frame_error(cell_w, cell_h, f"Error en cámara {camera_names[idx]}")

    def crear_frame_error(w, h, mensaje):
        """Crea un frame con mensaje de error."""
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        cv2.putText(frame, mensaje, (10, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.6, (0, 0, 255), 2)
        return frame

    # Compartir frames entre hilos
    frames = [np.zeros((cell_h, cell_w, 3), dtype=np.uint8) for _ in range(n)]
    estado = ["Conectando..." for _ in range(n)]
    locks = [threading.Lock() for _ in range(n)]
    threads = []
    for i, cap in enumerate(caps):
        t = threading.Thread(target=leer_frame, args=(cap, i, frames, locks, estado), daemon=True)
        t.start()
        threads.append(t)

    print("[*] Mostrando videos en cuadrícula. Presiona 'q' para salir.")
    time.sleep(2)  # Dar tiempo para conectar

    while True:
        grid = []
        for r in range(rows):
            fila = []
            for c in range(cols):
                idx = r * cols + c
                if idx < n:
                    with locks[idx]:
                        f = frames[idx].copy()
                        est = estado[idx]
                    # Agregar nombre y estado de la cámara
                    frame_con_label = f.copy()
                    label = f"{camera_names[idx]} - {est}"
                    cv2.putText(frame_con_label, label, (5, 25), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    fila.append(frame_con_label)
                else:
                    fila.append(np.zeros((cell_h, cell_w, 3), dtype=np.uint8))
            grid.append(np.hstack(fila))
        grid_img = np.vstack(grid)
        cv2.imshow('Cámaras RTSP - Presiona Q para salir', grid_img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("[*] Cerrando visor...")
            break

    for cap in caps:
        cap.release()
    cv2.destroyAllWindows()

def construir_rtsp_url(host: str, port: int, camera_id: str) -> str:
    """Construye la URL RTSP sin autenticación."""
    return f"rtsp://{host}:{port}/{camera_id}"


def login(base_url: str, username: str, password: str) -> str:
    """Autentica contra la API y retorna el JWT."""
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Login fallido ({resp.status_code}): {resp.text}")
        sys.exit(1)

    data = resp.json()
    token = data["access_token"]
    print(f"[OK] Login exitoso. JWT obtenido.")
    return token


def obtener_token_playback(base_url: str, jwt: str, camera_id: str) -> dict:
    """Solicita un token opaco de playback para una cámara específica."""
    resp = requests.post(
        f"{base_url}/stream-auth/stream/token/{camera_id}",
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[ERROR] No se pudo obtener token para {camera_id} ({resp.status_code}): {resp.text}")
        return None

    data = resp.json()
    print(f"[OK] Token obtenido para {camera_id} (expira en {data['expires_in']}s)")
    return data


def construir_rtsp_url(host: str, port: int, camera_id: str, token: str) -> str:
    """Construye la URL RTSP con el token embebido como password."""
    return f"rtsp://user:{token}@{host}:{port}/{camera_id}"


def main():
    print("=" * 70)
    print("  Visor de Cámaras RTSP - MediaMTX")
    print("=" * 70)
    print()

    # Construir URLs RTSP para cada cámara
    print(f"[1] Construyendo URLs RTSP para {len(CAMARAS)} cámara(s)...")
    resultados = []
    for cam in CAMARAS:
        rtsp_url = construir_rtsp_url(MEDIAMTX_HOST, RTSP_PORT, cam)
        resultados.append({
            "camera": cam,
            "rtsp_url": rtsp_url,
        })
    print()

    # Mostrar resultados
    if not resultados:
        print("[!] No hay cámaras configuradas.")
        sys.exit(1)

    print("=" * 70)
    print("  URLs RTSP de Reproducción")
    print("=" * 70)
    for r in resultados:
        print(f"\n  Cámara: {r['camera']}")
        print(f"  RTSP:   {r['rtsp_url']}")

    print("\n" + "-" * 70)
    print("  Comandos rápidos para VLC:")
    print("-" * 70)
    for r in resultados:
        print(f"  vlc '{r['rtsp_url']}'")

    print("\n" + "-" * 70)
    print("  Comandos rápidos para ffplay:")
    print("-" * 70)
    for r in resultados:
        print(f"  ffplay -rtsp_transport tcp '{r['rtsp_url']}'")

    print()

    # Mostrar videos en cuadrícula con OpenCV
    print("[2] Iniciando reproducción de videos en cuadrícula (presiona 'q' para salir)...")
    rtsp_urls = [r['rtsp_url'] for r in resultados]
    camera_names = [r['camera'] for r in resultados]
    mostrar_videos_rtsp(rtsp_urls, camera_names)


if __name__ == "__main__":
    main()
