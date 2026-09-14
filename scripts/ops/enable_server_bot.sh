#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal — Generic Server-Bot Activation Tool
# ==============================================================================
# Persistently configures and activates the 24/7 headless paper autobot.
# Writes /var/lib/aura/aura_bot.env so configuration survives release recreations.
#
# Usage:
#   sudo ./scripts/ops/enable_server_bot.sh [OPTIONS]
#
# Options / Environment:
#   --ntfy-url <url>      ntfy target URL (e.g. https://ntfy.sh/<topic>)
#   --scan-sec <seconds>  Scan cycle interval in seconds (default: 60)
#   --equity <amount>     Paper equity in USDT (default: 10000)
#   --state-dir <dir>     Persistent state directory (default: /var/lib/aura)
#   --container <name>    Docker container name (default: aura-terminal)
#   --non-interactive     Do not prompt; fail if required arguments are missing
#   -h, --help            Show this help message
# ==============================================================================

set -euo pipefail

# ANSI color codes
YW="\033[33m"
BL="\033[36m"
RD="\033[01;31m"
GN="\033[1;92m"
CL="\033[m"

# Default configuration values
NTFY_URL="${AURA_NTFY_URL:-}"
SCAN_SEC="${AURA_BOT_SCAN_SEC:-60}"
EQUITY="${AURA_BOT_EQUITY:-10000}"
STATE_DIR="${AURA_STATE_DIR:-/var/lib/aura}"
CONTAINER_NAME="${AURA_CONTAINER_NAME:-aura-terminal}"
NON_INTERACTIVE=false

usage() {
  cat << EOF
AURA Server-Bot Activation Tool

Usage:
  sudo $0 [OPTIONS]

Options:
  --ntfy-url <url>      ntfy target URL (e.g. https://ntfy.sh/<topic>)
  --scan-sec <seconds>  Scan cycle interval in seconds (default: 60)
  --equity <amount>     Paper starting equity in USDT (default: 10000)
  --state-dir <dir>     Host state dir / mount (default: /var/lib/aura)
  --container <name>    Container name (default: aura-terminal)
  --non-interactive     Run without interactive prompts
  -h, --help            Show this help message
EOF
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ntfy-url)
      NTFY_URL="$2"
      shift 2
      ;;
    --scan-sec)
      SCAN_SEC="$2"
      shift 2
      ;;
    --equity)
      EQUITY="$2"
      shift 2
      ;;
    --state-dir)
      STATE_DIR="$2"
      shift 2
      ;;
    --container)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --non-interactive)
      NON_INTERACTIVE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo -e "${RD}[FEHLER] Unbekanntes Argument: $1${CL}" >&2
      usage
      exit 1
      ;;
  esac
done

echo -e "${BL}============================================================${CL}"
echo -e "${BL}  AURA Quant Terminal — Server-Bot 24/7 Aktivierung        ${CL}"
echo -e "${BL}============================================================${CL}"

# Interactive prompt if NTFY_URL is not set
if [[ -z "$NTFY_URL" ]]; then
  if [[ "$NON_INTERACTIVE" = true ]]; then
    echo -e "${RD}[FEHLER] AURA_NTFY_URL ist erforderlich (--ntfy-url oder Env-Variable).${CL}" >&2
    exit 1
  fi

  echo -e "\n${YW}Bitte ntfy-Push-URL eingeben (z. B. https://ntfy.sh/mein-geheimer-topic):${CL}"
  read -r -p "ntfy URL: " NTFY_URL
fi

# Validation: URL format
if ! echo "$NTFY_URL" | grep -Eq '^https?://[a-zA-Z0-9.-]+(:[0-9]+)?/[a-zA-Z0-9_.-]+$'; then
  echo -e "${RD}[FEHLER] Ungültiges URL-Format für ntfy: '$NTFY_URL'${CL}" >&2
  echo -e "Erwartetes Format: https://ntfy.sh/<dein-topic>" >&2
  exit 1
fi

# Validation: Scan interval numeric
if ! echo "$SCAN_SEC" | grep -Eq '^[0-9]+$' || [[ "$SCAN_SEC" -lt 10 ]] || [[ "$SCAN_SEC" -gt 3600 ]]; then
  echo -e "${RD}[FEHLER] Ungültiger Scan-Intervall: '$SCAN_SEC' (Erlaubt: 10 bis 3600 Sekunden).${CL}" >&2
  exit 1
fi

# Validation: Equity numeric
if ! echo "$EQUITY" | grep -Eq '^[0-9]+(\.[0-9]+)?$' || (( $(echo "$EQUITY <= 0" | awk '{print ($1 <= 0)}') )); then
  echo -e "${RD}[FEHLER] Ungültiges Startkapital (Equity): '$EQUITY' (Muss positiv numerisch sein).${CL}" >&2
  exit 1
fi

# Determine persistent state directory on host
if [[ ! -d "$STATE_DIR" ]]; then
  # Check if docker volume aura-state exists
  DOCKER_VOL_PATH="/var/lib/docker/volumes/aura-state/_data"
  if [[ -d "$DOCKER_VOL_PATH" ]]; then
    echo -e "${BL}[INFO] Erstelle Symlink $STATE_DIR -> $DOCKER_VOL_PATH${CL}"
    mkdir -p "$(dirname "$STATE_DIR")"
    ln -sfn "$DOCKER_VOL_PATH" "$STATE_DIR"
  else
    echo -e "${BL}[INFO] Erstelle Verzeichnis $STATE_DIR${CL}"
    mkdir -p "$STATE_DIR"
  fi
fi

ENV_FILE="${STATE_DIR}/aura_bot.env"

echo -e "\n${BL}[1/3] Schreibe persistente Konfigurationsdatei: $ENV_FILE${CL}"
cat << EOF > "$ENV_FILE"
# AURA Quant Terminal — Persistent Server-Bot Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
AURA_BOT_MODE=server
AURA_BOT_SCAN_SEC=${SCAN_SEC}
AURA_BOT_EQUITY=${EQUITY}
AURA_NTFY_URL=${NTFY_URL}
EOF

chmod 644 "$ENV_FILE"
echo -e "${GN}[OK] Konfigurationsdatei erfolgreich geschrieben.${CL}"

# Check Docker Container presence
echo -e "\n${BL}[2/3] Prüfe Docker Container '$CONTAINER_NAME'...${CL}"
if ! command -v docker >/dev/null 2>&1; then
  echo -e "${YW}[WARNUNG] Docker CLI nicht gefunden. Bitte Container manuell mit /var/lib/aura/aura_bot.env neu starten.${CL}"
  exit 0
fi

if ! docker ps -a --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}$"; then
  echo -e "${YW}[WARNUNG] Container '$CONTAINER_NAME' nicht gefunden. Bitte Image starten und -v ${STATE_DIR}:/var/lib/aura einbinden.${CL}"
  exit 0
fi

# Recreate container with persistent environment applied
echo -e "${BL}[3/3] Wende neue Konfiguration auf Container '$CONTAINER_NAME' an...${CL}"

# Extract image & network parameters from existing container
CURRENT_IMAGE=$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}')
echo -e "${BL}[INFO] Aktuelles Image: ${CURRENT_IMAGE}${CL}"

# Stop and recreate cleanly
docker stop "$CONTAINER_NAME" >/dev/null
docker rm "$CONTAINER_NAME" >/dev/null

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -e PYTHONUNBUFFERED=1 \
  -e SYM_PORT=8787 \
  -e SYM_HOST=0.0.0.0 \
  -e AURA_BOT_MODE=server \
  -e "AURA_BOT_SCAN_SEC=${SCAN_SEC}" \
  -e "AURA_BOT_EQUITY=${EQUITY}" \
  -e "AURA_NTFY_URL=${NTFY_URL}" \
  -e "AURA_STATE_DIR=${STATE_DIR}" \
  -v "aura-state:/var/lib/aura" \
  -p 8787:8787 \
  "$CURRENT_IMAGE" >/dev/null

echo -e "${GN}[OK] Container '$CONTAINER_NAME' neu gestartet.${CL}"

# Verification display
echo -e "\n${GN}============================================================${CL}"
echo -e "${GN}  Server-Bot erfolgreich aktiviert!                         ${CL}"
echo -e "${GN}============================================================${CL}"
echo -e "\n${BL}Verifikationsbefehle:${CL}"
echo -e "  1. Status & Runner prüfen:"
echo -e "     curl -s http://localhost:8787/ready | jq .runner"
echo -e "  2. Container-Logs einsehen:"
echo -e "     docker logs --tail 20 -f $CONTAINER_NAME"
echo -e "  3. Test-Signal senden:"
echo -e "     curl -s -X POST http://localhost:8787/api/signals \\"
echo -e "       -H 'Content-Type: application/json' \\"
echo -e "       -d '{\"title\":\"AURA Server-Bot Test\",\"body\":\"Signal-Pfad verifiziert\",\"priority\":3}'"
echo -e ""
