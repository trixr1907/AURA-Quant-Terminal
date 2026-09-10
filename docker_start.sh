#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal - Linux / Homelab / Unraid / Proxmox Starter Script
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")"

PORT="${AURA_PORT:-8787}"
ALLOWED_HOSTS="${AURA_ALLOWED_HOSTS:-127.0.0.1}"

echo "======================================================="
echo "  AURA QUANT TERMINAL - DOCKER LAUNCHER (Homelab/Linux)"
echo "======================================================="
echo ""
echo "LAN-Konfiguration:"
echo "  AURA_ALLOWED_HOSTS='${ALLOWED_HOSTS}'"
echo "  (Fuer LAN-Zugriff weitere Hostnamen/IPs komma-getrennt uebergeben;"
echo "   Loopback 127.0.0.1 und localhost bleiben immer erlaubt)."
echo ""

if ! command -v docker >/dev/null 2>&1; then
    echo "[FEHLER] Docker ist nicht installiert oder nicht im PATH." >&2
    exit 1
fi

echo "[1/4] Building AURA Docker Image..."
docker build -t aura-quant-terminal:latest .

echo "[2/4] Stopping previous container if exists..."
docker stop aura-terminal >/dev/null 2>&1 || true
docker rm aura-terminal >/dev/null 2>&1 || true

echo "[3/4] Starting AURA Container on port ${PORT}..."
docker run -d \
--name aura-terminal \
--restart unless-stopped \
-p "${PORT}:8787" \
-e "AURA_ALLOWED_HOSTS=${ALLOWED_HOSTS}" \
-e AURA_STATE_DIR=/var/lib/aura \
-v aura-state:/var/lib/aura \
aura-quant-terminal:latest

echo "[4/4] Verifiziere Bereitschaft und Endpunkte (Bounded Readiness Poll)..."
MAX_WAIT=45
START_TIME=$(date +%s)
READY=0

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))

    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        break
    fi

    # a) Pruefe ob Container laeuft
    RUNNING=$(docker inspect aura-terminal --format '{{.State.Running}}' 2>/dev/null || echo "false")
    if [ "$RUNNING" != "true" ]; then
        sleep 1
        continue
    fi

    # c) /serving (Liveness)
    if ! curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/serving" >/dev/null 2>&1; then
        sleep 1
        continue
    fi

    # d) Repraesentativer /api/public Ticker-Aufruf (BTCUSDT)
    if ! curl -fsS --max-time 5 -H "Content-Type: application/json" \
         -d '{"path":"/api/v2/mix/market/ticker","params":{"symbol":"BTCUSDT","productType":"USDT-FUTURES"}}' \
         "http://127.0.0.1:${PORT}/api/public" >/dev/null 2>&1; then
        sleep 1
        continue
    fi

    # b) /ready (Marktdaten-Readiness nach Uplink)
    if ! curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/ready" >/dev/null 2>&1; then
        sleep 1
        continue
    fi

    # e) /api/state (State mit erlaubtem Host)
    if ! curl -fsS --max-time 3 -H "Host: 127.0.0.1:${PORT}" "http://127.0.0.1:${PORT}/api/state" >/dev/null 2>&1; then
        sleep 1
        continue
    fi

    READY=1
    break
done

if [ "$READY" -ne 1 ]; then
    echo "" >&2
    echo "[FEHLER] Bereitschafts-Prüfung (Readiness Probe) nach ${MAX_WAIT}s fehlgeschlagen!" >&2
    echo "[LOGS] Letzte Container-Logs von aura-terminal:" >&2
    docker logs --tail 50 aura-terminal >&2 || true
    exit 1
fi

echo ""
echo "======================================================="
echo "  AURA Quant Terminal running successfully!"
echo "  Dashboard URL:  http://localhost:${PORT}/"
echo "  Tutorial URL:   http://localhost:${PORT}/tutorial"
echo "  Serving Status: http://localhost:${PORT}/serving"
echo "  Readiness:      http://localhost:${PORT}/ready"
echo "  Shared State:   http://localhost:${PORT}/api/state"
echo "======================================================="
