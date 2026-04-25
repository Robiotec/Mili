#!/bin/bash
LOG_FILE="/home/robiotec/SVI/arcom/arcom_update.log"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') - Iniciando actualización ARCOM ===" >> "$LOG_FILE"
/usr/bin/python3 /home/robiotec/SVI/arcom/download_arcom.py >> "$LOG_FILE" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') - Finalizado ===" >> "$LOG_FILE"
