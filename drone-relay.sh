#!/bin/bash
# Relay: mediamtx remoto (8654) -> mediamtx-api local (8654)
# Path monitoreado: /DRONE

MEDIAMTX_API="http://127.0.0.1:9997"
SRC_PATH="DRONE"
SRC_RTSP="rtsp://100.125.116.89:8654/${SRC_PATH}"
DST_RTSP="rtsp://localhost:8654/${SRC_PATH}"

while true; do
    until curl -sf "${MEDIAMTX_API}/v3/paths/list" >/dev/null 2>&1; do
        echo "Esperando que mediamtx este listo..."
        sleep 3
    done

    READY=$(curl -sf "${MEDIAMTX_API}/v3/paths/get/${SRC_PATH}" 2>/dev/null | grep -c 'ready.*true')

    if [ "${READY}" -gt 0 ] 2>/dev/null; then
        echo "Stream ${SRC_PATH} disponible, iniciando relay..."
        ffmpeg -loglevel warning -rtsp_transport tcp \
            -i "${SRC_RTSP}" \
            -c copy -f rtsp -rtsp_transport tcp \
            "${DST_RTSP}"
        echo "ffmpeg finalizo, esperando nuevo stream..."
    else
        echo "Sin stream en /${SRC_PATH}, reintentando en 3s..."
    fi

    sleep 3
done
