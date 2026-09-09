#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal - Linux / Homelab / Unraid / Proxmox Starter Script
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")"

PORT="${AURA_PORT:-8787}"

echo "======================================================="
echo "  AURA QUANT TERMINAL - DOCKER LAUNCHER (Homelab/Linux)"
echo "======================================================="
echo ""

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker is not installed or not in PATH."
    exit 1
fi

echo "[1/3] Building AURA Docker Image..."
docker build -t aura-quant-terminal:latest .

echo "[2/3] Stopping previous container if exists..."
docker stop aura-terminal >/dev/null 2>&1 || true
docker rm aura-terminal >/dev/null 2>&1 || true

echo "[3/3] Starting AURA Container on port ${PORT}..."
docker run -d \
--name aura-terminal \
--restart unless-stopped \
-p "${PORT}:8787" \
-e "AURA_ALLOWED_HOSTS=${AURA_ALLOWED_HOSTS:-127.0.0.1}" \
-e AURA_STATE_DIR=/var/lib/aura \
-v aura-state:/var/lib/aura \
aura-quant-terminal:latest

echo ""
echo "======================================================="
echo "  AURA Quant Terminal running successfully!"
echo "  Dashboard URL: http://localhost:${PORT}/"
echo "  Serving Status: http://localhost:${PORT}/serving"
echo "======================================================="
