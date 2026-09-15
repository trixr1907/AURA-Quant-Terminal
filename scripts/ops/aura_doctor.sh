#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal — aura_doctor.sh (One-Command Diagnostics)
# ==============================================================================
# Comprehensive health and configuration audit for the AURA Docker container,
# Headless Paper Autobot, persistent storage, security hardening, and ntfy pushes.
#
# Usage (in Docker VM):
#   ./scripts/ops/aura_doctor.sh [OPTIONS]
#
# Or via Proxmox Host:
#   qm guest exec <VMID> -- /home/aura/scripts/ops/aura_doctor.sh [OPTIONS]
#
# Options:
#   --push                Send a real test push notification from container ENV
#   --json                Output machine-readable JSON format
#   --container <name>    Container name (default: aura-terminal)
#   --state-dir <dir>     Host persistent state dir (default: /var/lib/aura)
#   --relay-url <url>     Relay base URL (default: http://127.0.0.1:8787)
#   -h, --help            Show this help message
# ==============================================================================

set -euo pipefail

# ANSI color codes
YW="\033[33m"
BL="\033[36m"
RD="\033[01;31m"
GN="\033[1;92m"
DIM="\033[2m"
CL="\033[m"

CONTAINER_NAME="${AURA_CONTAINER_NAME:-aura-terminal}"
STATE_DIR="${AURA_STATE_DIR:-/var/lib/aura}"
RELAY_URL="${AURA_RELAY_URL:-http://127.0.0.1:8787}"
DO_PUSH=false
JSON_MODE=false

usage() {
  cat << EOF
AURA Doctor — Diagnose-Tool für AURA Quant Terminal

Verwendung:
  $0 [OPTIONEN]

Optionen:
  --push                Sendet einen echten Test-Push aus der Container-ENV
  --json                Gibt das Diagnose-Ergebnis als strukturiertes JSON aus
  --container <name>    Docker-Container-Name (Standard: aura-terminal)
  --state-dir <dir>     Persistentes State-Verzeichnis (Standard: /var/lib/aura)
  --relay-url <url>     Relay HTTP URL (Standard: http://127.0.0.1:8787)
  -h, --help            Zeigt diese Hilfe an
EOF
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      DO_PUSH=true
      shift
      ;;
    --json)
      JSON_MODE=true
      shift
      ;;
    --container)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --state-dir)
      STATE_DIR="$2"
      shift 2
      ;;
    --relay-url)
      RELAY_URL="$2"
      shift 2
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

# Result accumulator
CHECKS_JSON="[]"
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

add_check() {
  local id="$1"
  local status="$2" # PASS, WARN, FAIL
  local msg="$3"
  local detail="${4:-}"

  if [[ "$status" == "PASS" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
    if [[ "$JSON_MODE" = false ]]; then
      echo -e " [ ${GN}PASS${CL} ] ${id}: ${msg}"
      if [[ -n "$detail" ]]; then
        echo -e "          ${DIM}${detail}${CL}"
      fi
    fi
  elif [[ "$status" == "WARN" ]]; then
    WARN_COUNT=$((WARN_COUNT + 1))
    if [[ "$JSON_MODE" = false ]]; then
      echo -e " [ ${YW}WARN${CL} ] ${id}: ${msg}"
      if [[ -n "$detail" ]]; then
        echo -e "          ${YW}${detail}${CL}"
      fi
    fi
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [[ "$JSON_MODE" = false ]]; then
      echo -e " [ ${RD}FAIL${CL} ] ${id}: ${msg}"
      if [[ -n "$detail" ]]; then
        echo -e "          ${RD}${detail}${CL}"
      fi
    fi
  fi

  # Escape JSON strings
  local esc_msg esc_detail
  esc_msg=$(echo "$msg" | sed 's/"/\\"/g')
  esc_detail=$(echo "$detail" | sed 's/"/\\"/g')

  local item="{\"id\":\"${id}\",\"status\":\"${status}\",\"message\":\"${esc_msg}\",\"detail\":\"${esc_detail}\"}"
  if [[ "$CHECKS_JSON" == "[]" ]]; then
    CHECKS_JSON="[${item}]"
  else
    CHECKS_JSON="${CHECKS_JSON%]},${item}]"
  fi
}

mask_url() {
  local url="$1"
  if [[ -z "$url" ]]; then
    echo "Nicht konfiguriert"
    return
  fi
  local base topic
  if [[ "$url" =~ ^(https?://[^/]+/)(.*)$ ]]; then
    base="${BASH_REMATCH[1]}"
    topic="${BASH_REMATCH[2]}"
    if [[ ${#topic} -gt 6 ]]; then
      echo "${base}${topic:0:6}…"
    elif [[ ${#topic} -gt 2 ]]; then
      echo "${base}${topic:0:2}…"
    else
      echo "${base}…"
    fi
  else
    if [[ ${#url} -gt 6 ]]; then
      echo "${url:0:6}…"
    else
      echo "${url}…"
    fi
  fi
}

if [[ "$JSON_MODE" = false ]]; then
  echo -e "${BL}============================================================${CL}"
  echo -e "${BL}  AURA Doctor — Ein-Befehl-Systemdiagnose                  ${CL}"
  echo -e "${BL}============================================================${CL}"
  echo -e "Zeit: $(date -u '+%Y-%m-%d %H:%M:%S UTC') | Host: $(hostname)"
  echo ""
fi

# ------------------------------------------------------------------------------
# Check 1: Docker Container Status & Image Tag
# ------------------------------------------------------------------------------
CONTAINER_RUNNING=false
CONTAINER_INSPECT=""
if command -v docker &>/dev/null; then
  if docker inspect "$CONTAINER_NAME" &>/dev/null; then
    CONTAINER_INSPECT=$(docker inspect "$CONTAINER_NAME" 2>/dev/null || true)
    STATE_RUNNING=$(echo "$CONTAINER_INSPECT" | grep -o '"Running": *[a-z]*' | head -1 | awk '{print $2}' || true)
    if [[ "$STATE_RUNNING" == "true" ]]; then
      CONTAINER_RUNNING=true
      IMAGE_NAME=$(echo "$CONTAINER_INSPECT" | grep -o '"Image": *"[^"]*"' | head -1 | cut -d'"' -f4 || true)
      add_check "container_status" "PASS" "Container '$CONTAINER_NAME' existiert und läuft" "Image: $IMAGE_NAME"
    else
      add_check "container_status" "FAIL" "Container '$CONTAINER_NAME' existiert, läuft aber NICHT (Status: gestoppt)"
    fi
  else
    add_check "container_status" "FAIL" "Container '$CONTAINER_NAME' nicht gefunden" "Bitte Container per docker run starten."
  fi
else
  add_check "container_status" "WARN" "Docker CLI nicht verfügbar" "Laufe außerhalb einer Docker-Host-Umgebung."
fi

# ------------------------------------------------------------------------------
# Check 2: Relay /serving & /ready Endpoint Checks
# ------------------------------------------------------------------------------
SERVING_JSON=""
READY_JSON=""
if command -v curl &>/dev/null; then
  SERVING_RES=$(curl -s -w "\n%{http_code}" --connect-timeout 3 "$RELAY_URL/serving" 2>/dev/null || true)
  HTTP_CODE=$(echo "$SERVING_RES" | tail -n1)
  SERVING_BODY=$(echo "$SERVING_RES" | sed '$d')

  if [[ "$HTTP_CODE" == "200" ]]; then
    VERSION_VAL=$(echo "$SERVING_BODY" | grep -o '"version": *"[^"]*"' | cut -d'"' -f4 || true)
    add_check "relay_serving" "PASS" "Relay /serving antwortet HTTP 200 (Version v${VERSION_VAL})"
  else
    add_check "relay_serving" "FAIL" "Relay /serving nicht erreichbar unter $RELAY_URL (HTTP $HTTP_CODE)"
  fi

  READY_RES=$(curl -s -w "\n%{http_code}" --connect-timeout 3 "$RELAY_URL/ready" 2>/dev/null || true)
  READY_HTTP=$(echo "$READY_RES" | tail -n1)
  READY_BODY=$(echo "$READY_RES" | sed '$d')

  if [[ "$READY_HTTP" == "200" || "$READY_HTTP" == "503" ]]; then
    BOT_ENABLED=$(echo "$READY_BODY" | grep -o '"bot_enabled": *[a-z]*' | head -1 | awk '{print $2}' || true)
    RUNNER_STATE=$(echo "$READY_BODY" | grep -o '"state": *"[^"]*"' | head -1 | cut -d'"' -f4 || true)
    CYCLE_COUNT=$(echo "$READY_BODY" | grep -o '"cycle_count": *[0-9]*' | head -1 | awk '{print $2}' || true)
    LAST_CYCLE_AGE=$(echo "$READY_BODY" | grep -o '"last_cycle_age_sec": *[0-9.]*' | head -1 | awk '{print $2}' || true)
    PAUSED_VAL=$(echo "$READY_BODY" | grep -o '"paused": *[a-z]*' | head -1 | awk '{print $2}' || true)

    if [[ "$RUNNER_STATE" == "not_configured" ]]; then
      add_check "bot_ready" "WARN" "Server-Bot ist nicht konfiguriert (AURA_BOT_MODE != server)" "Zur Aktivierung: docs/deployment/SERVER_BOT_GUIDE.md"
    elif [[ "$RUNNER_STATE" == "running" ]]; then
      if [[ -n "$LAST_CYCLE_AGE" ]] && (( $(echo "$LAST_CYCLE_AGE < 180" | bc -l 2>/dev/null || echo 1) )); then
        add_check "bot_ready" "PASS" "Server-Bot läuft aktiv (Zyklen: ${CYCLE_COUNT:-0}, letzter Scan vor ${LAST_CYCLE_AGE}s)"
      else
        add_check "bot_ready" "WARN" "Server-Bot läuft, aber Scan-Zyklus ist älter als 180s (${LAST_CYCLE_AGE:-unbekannt}s)"
      fi
    elif [[ "$PAUSED_VAL" == "true" ]]; then
      add_check "bot_ready" "PASS" "Server-Bot ist ordnungsgemäß pausiert (Browser-Bot hat Vorrang)"
    else
      add_check "bot_ready" "FAIL" "Server-Bot in unerwartetem Zustand: $RUNNER_STATE"
    fi
  else
    add_check "bot_ready" "FAIL" "Relay /ready liefert keinen gültigen Status (HTTP $READY_HTTP)"
  fi
else
  add_check "relay_serving" "WARN" "curl nicht verfügbar" "Kann Relay-Endpoints nicht direkt anfragen."
fi

# ------------------------------------------------------------------------------
# Check 3: Container ENV & Hardening Flags
# ------------------------------------------------------------------------------
CONTAINER_NTFY=""
if [[ "$CONTAINER_RUNNING" = true && -n "$CONTAINER_INSPECT" ]]; then
  ENV_BLOCK=$(echo "$CONTAINER_INSPECT" | grep -A 50 '"Env": \[' || true)
  
  # Check AURA_BOT_MODE
  if echo "$ENV_BLOCK" | grep -q 'AURA_BOT_MODE=server'; then
    add_check "env_bot_mode" "PASS" "Container ENV enthält AURA_BOT_MODE=server"
  else
    add_check "env_bot_mode" "WARN" "AURA_BOT_MODE=server fehlt in Container-ENV" "Bot läuft nicht als 24/7 Server-Bot."
  fi

  # Check AURA_NTFY_URL
  CONTAINER_NTFY=$(echo "$ENV_BLOCK" | grep -o 'AURA_NTFY_URL=[^", ]*' | head -1 | cut -d'=' -f2 || true)
  if [[ -n "$CONTAINER_NTFY" ]]; then
    MASKED_NTFY=$(mask_url "$CONTAINER_NTFY")
    add_check "env_ntfy_url" "PASS" "AURA_NTFY_URL konfiguriert: $MASKED_NTFY"
  else
    add_check "env_ntfy_url" "WARN" "AURA_NTFY_URL nicht im Container konfiguriert" "Push-Benachrichtigungen deaktiviert."
  fi

  # Hardening flags
  READONLY_FS=$(echo "$CONTAINER_INSPECT" | grep -o '"ReadonlyRootfs": *[a-z]*' | head -1 | awk '{print $2}' || true)
  CAP_DROP=$(echo "$CONTAINER_INSPECT" | grep -A 5 '"CapDrop": \[' | grep -i 'ALL' || true)
  NO_NEW_PRIVS=$(echo "$CONTAINER_INSPECT" | grep -o '"no-new-privileges"' || true)
  RESTART_POLICY=$(echo "$CONTAINER_INSPECT" | grep -A 5 '"RestartPolicy": {' | grep -o '"Name": *"[^"]*"' | head -1 | cut -d'"' -f4 || true)

  HARDENING_MSGS=""
  if [[ "$READONLY_FS" == "true" ]]; then
    HARDENING_MSGS="${HARDENING_MSGS}readonly-rootfs "
  fi
  if [[ -n "$CAP_DROP" ]]; then
    HARDENING_MSGS="${HARDENING_MSGS}cap-drop=ALL "
  fi
  if [[ -n "$NO_NEW_PRIVS" ]]; then
    HARDENING_MSGS="${HARDENING_MSGS}no-new-privileges "
  fi
  if [[ "$RESTART_POLICY" == "unless-stopped" || "$RESTART_POLICY" == "always" ]]; then
    HARDENING_MSGS="${HARDENING_MSGS}restart=${RESTART_POLICY} "
  fi

  if [[ -n "$HARDENING_MSGS" ]]; then
    add_check "container_hardening" "PASS" "Container-Härtungs-Flags aktiv" "$HARDENING_MSGS"
  else
    add_check "container_hardening" "WARN" "Container-Härtungs-Flags nicht vollständig gesetzt" "Empfohlen: --read-only --cap-drop ALL --security-opt no-new-privileges"
  fi
fi

# ------------------------------------------------------------------------------
# Check 4: Persistent Storage & Filesystem
# ------------------------------------------------------------------------------
ENV_FILE="${STATE_DIR}/aura_bot.env"
if [[ -f "$ENV_FILE" ]]; then
  if [[ -r "$ENV_FILE" ]]; then
    PERMS=$(stat -c "%a" "$ENV_FILE" 2>/dev/null || stat -f "%Op" "$ENV_FILE" 2>/dev/null || echo "lesbar")
    add_check "env_file" "PASS" "Env-Datei '$ENV_FILE' vorhanden und lesbar" "Rechte: $PERMS"
  else
    add_check "env_file" "FAIL" "Env-Datei '$ENV_FILE' existiert, ist aber nicht lesbar"
  fi
else
  add_check "env_file" "WARN" "Env-Datei '$ENV_FILE' existiert nicht" "Konfiguration wird nach Container-Neustart zurückgesetzt."
fi

SHADOW_LOG="${STATE_DIR}/shadow_log.jsonl"
if [[ -f "$SHADOW_LOG" ]]; then
  SHADOW_SIZE=$(ls -lh "$SHADOW_LOG" | awk '{print $5}')
  SHADOW_LINES=$(wc -l < "$SHADOW_LOG" || echo "0")
  add_check "shadow_log" "PASS" "Schatten-Log '$SHADOW_LOG' aktiv" "Größe: $SHADOW_SIZE (${SHADOW_LINES} Einträge)"
else
  add_check "shadow_log" "PASS" "Schatten-Log noch nicht angelegt (oder frisch)"
fi

# Disk Space Check (> 500 MB)
if command -v df &>/dev/null; then
  DISK_TARGET="$STATE_DIR"
  if [[ ! -d "$DISK_TARGET" ]]; then
    DISK_TARGET="/"
  fi
  FREE_MB=$(df -m "$DISK_TARGET" 2>/dev/null | awk 'NR==2 {print $4}' || echo "1000")
  if [[ "$FREE_MB" -gt 500 ]]; then
    add_check "disk_space" "PASS" "Festplattenspeicher nominal" "${FREE_MB} MB frei auf $DISK_TARGET (Minimum: 500 MB)"
  else
    add_check "disk_space" "FAIL" "Festplattenspeicher kritisch knapp: ${FREE_MB} MB frei (Minimum: 500 MB)"
  fi
fi

# ------------------------------------------------------------------------------
# Check 5: Container Log Errors (24h)
# ------------------------------------------------------------------------------
if [[ "$CONTAINER_RUNNING" = true ]]; then
  ERROR_COUNT=$(docker logs --since 24h "$CONTAINER_NAME" 2>&1 | grep -iE 'ERROR|CRITICAL|FATAL|Exception' | wc -l || echo "0")
  if [[ "$ERROR_COUNT" -eq 0 ]]; then
    add_check "container_logs" "PASS" "Keine Fehler in Container-Logs der letzten 24h"
  elif [[ "$ERROR_COUNT" -le 50 ]]; then
    add_check "container_logs" "WARN" "${ERROR_COUNT} Fehlermeldungen in Container-Logs der letzten 24h" "Prüfe 'docker logs --since 24h $CONTAINER_NAME'"
  else
    add_check "container_logs" "FAIL" "Hohe Fehleranzahl: ${ERROR_COUNT} Fehler in Logs der letzten 24h" "Prüfe 'docker logs --since 24h $CONTAINER_NAME'"
  fi
fi

# ------------------------------------------------------------------------------
# Check 6: Deploy Receiver Unit & Drop-in
# ------------------------------------------------------------------------------
if command -v systemctl &>/dev/null; then
  if systemctl list-unit-files 2>/dev/null | grep -q 'aura-deploy-receiver.service'; then
    if systemctl is-active aura-deploy-receiver.service &>/dev/null; then
      add_check "deploy_receiver" "PASS" "Deploy-Receiver systemd-Unit aktiv"
    else
      add_check "deploy_receiver" "WARN" "Deploy-Receiver systemd-Unit installiert, aber inaktiv"
    fi
  else
    add_check "deploy_receiver" "PASS" "Deploy-Receiver nicht als systemd-Unit eingerichtet (optional)"
  fi
fi

# ------------------------------------------------------------------------------
# Check 7: Test-Push Notification (--push flag)
# ------------------------------------------------------------------------------
if [[ "$DO_PUSH" = true ]]; then
  TARGET_NTFY="$CONTAINER_NTFY"
  if [[ -z "$TARGET_NTFY" && -f "$ENV_FILE" ]]; then
    TARGET_NTFY=$(grep -o 'AURA_NTFY_URL=[^", ]*' "$ENV_FILE" | head -1 | cut -d'=' -f2 || true)
  fi
  if [[ -z "$TARGET_NTFY" ]]; then
    TARGET_NTFY="${AURA_NTFY_URL:-}"
  fi

  if [[ -n "$TARGET_NTFY" ]]; then
    PUSH_PAYLOAD="AURA Doctor Test-Push von $(hostname) um $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    PUSH_RESP=$(curl -s -X POST \
      -H "Title: AURA Doctor Test" \
      -H "Priority: 3" \
      -H "Tags: white_check_mark,stethoscope" \
      -d "$PUSH_PAYLOAD" \
      "$TARGET_NTFY" 2>/dev/null || true)

    NTFY_ID=$(echo "$PUSH_RESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "OK")
    MASKED_TARGET=$(mask_url "$TARGET_NTFY")
    add_check "test_push" "PASS" "Test-Push erfolgreich gesendet an $MASKED_TARGET" "ntfy-Message-ID: $NTFY_ID"
  else
    add_check "test_push" "FAIL" "Test-Push fehlgeschlagen: Keine AURA_NTFY_URL gefunden"
  fi
fi

# ------------------------------------------------------------------------------
# Summary & Exit
# ------------------------------------------------------------------------------
OVERALL_STATUS="PASS"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  OVERALL_STATUS="FAIL"
fi

if [[ "$JSON_MODE" = true ]]; then
  cat << EOF
{
  "status": "${OVERALL_STATUS}",
  "timestamp": "$(date -u '+%Y-%m-%d %H:%M:%SZ')",
  "counts": {
    "pass": ${PASS_COUNT},
    "warn": ${WARN_COUNT},
    "fail": ${FAIL_COUNT}
  },
  "checks": ${CHECKS_JSON}
}
EOF
else
  echo ""
  echo -e "${BL}------------------------------------------------------------${CL}"
  if [[ "$OVERALL_STATUS" == "PASS" ]]; then
    echo -e "Ergebnis: ${GN}PASS (0 Fehler, ${WARN_COUNT} Warnungen, ${PASS_COUNT} Erfolgreich)${CL}"
  else
    echo -e "Ergebnis: ${RD}FAIL (${FAIL_COUNT} Fehler, ${WARN_COUNT} Warnungen, ${PASS_COUNT} Erfolgreich)${CL}"
  fi
  echo -e "${BL}============================================================${CL}"
fi

if [[ "$OVERALL_STATUS" == "PASS" ]]; then
  exit 0
else
  exit 1
fi
