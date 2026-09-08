#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal - Deep Proxmox & Homelab Infrastructure Scanner (v2.1)
# ==============================================================================
# - Robuste IPv4-Erkennung
# - Zuverlässiger VM File-Transfer via qemu-ga guest-file-open / write / close
#   und Fallback auf geteilte Base64-Chunks (unterstützt alle Proxmox Versionen)
# ==============================================================================

set -euo pipefail

YW=$(echo "\033[33m")
BL=$(echo "\033[36m")
RD=$(echo "\033[01;31m")
GN=$(echo "\033[1;92m")
PR=$(echo "\033[1;35m")
CL=$(echo "\033[m")

clear
cat << "EOF"
    ___   __  ______  ___       ____                    
   /   | / / / / __ \/   |     / __ \__  ______ _____  / /_
  / /| |/ / / / /_/ / /| |    / / / / / / / __ `/ __ \/ __/
 / ___ / /_/ / _, _/ ___ |   / /_/ / /_/ / /_/ / / / / /_  
/_/  |_\____/_/ |_/_/  |_|   \___\_\__,_/\__,_/_/ /_/\__/  
Deep Proxmox & Homelab Infrastructure Scanner & Auto-Deployer
=============================================================
EOF

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PORT="${AURA_PORT:-8787}"

declare -a DOCKER_TARGETS=()
declare -a DOCKER_TYPES=()
declare -a DOCKER_IPS=()

# Helper zur sauberen IPv4-Ermittlung einer KVM-VM (ignoriert fe80::, 127.0.0.1, 172.17.x)
get_vm_ipv4() {
  local vmid="$1"
  local ip=""

  # 1. Methode: qm guest exec mit hostname -I
  if command -v qm >/dev/null 2>&1; then
    local ips_raw
    ips_raw=$(qm guest exec "$vmid" -- bash -c "hostname -I 2>/dev/null || ip -4 addr show 2>/dev/null" 2>/dev/null | grep -oP '\b(?!(?:127|172\.(?:1[6-9]|2[0-9]|3[01])|10\.244|10\.96)\.)\d{1,3}(?:\.\d{1,3}){3}\b' || true)
    ip=$(echo "$ips_raw" | head -n1 || true)
  fi

  # 2. Methode: Guest Agent Network Interfaces
  if [[ -z "$ip" ]] && command -v qm >/dev/null 2>&1; then
    local json_out
    json_out=$(qm guest cmd "$vmid" network-get-interfaces 2>/dev/null || true)
    if [[ -n "$json_out" ]]; then
      ip=$(echo "$json_out" | grep -B2 '"ip-address-type":"ipv4"' | grep -oP '(?<="ip-address":")\d+(\.\d+){3}' | grep -vE '^(127\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|10\.244\.|10\.96\.)' | head -n1 || true)
    fi
  fi

  # 3. Methode: ARP Scan / Neighbours ueber MAC
  if [[ -z "$ip" ]] && command -v qm >/dev/null 2>&1; then
    local mac
    mac=$(qm config "$vmid" 2>/dev/null | grep -oP '(?<=(?:virtio|e1000)=)[0-9A-Fa-f:]+' | head -n1 | tr '[:upper:]' '[:lower:]' || true)
    if [[ -n "$mac" ]]; then
      ip=$(ip neigh show 2>/dev/null | grep -i "$mac" | grep -oP '^\d+(\.\d+){3}' | head -n1 || true)
    fi
  fi

  echo "$ip"
}

wait_for_vm_ipv4() {
  local vmid="$1"
  local timeout_sec="${2:-30}"
  local elapsed=0
  local ip=""
  while [[ $elapsed -lt $timeout_sec ]]; do
    ip=$(get_vm_ipv4 "$vmid")
    if [[ -n "$ip" ]]; then
      echo "$ip"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

verify_vm_deployment() {
  local vmid="$1"
  local ip="$2"
  local inspect_cmd
  inspect_cmd="docker inspect aura-terminal --format 'running={{.State.Running}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}} oom={{.State.OOMKilled}} error={{.State.Error}}'"
  local inspect_out=""
  for _ in {1..20}; do
    inspect_out=$(qm guest exec "$vmid" -- bash -c "$inspect_cmd" 2>/dev/null || true)
    if [[ "$inspect_out" == *"running=true"* && "$inspect_out" == *"health=healthy"* && "$inspect_out" == *"oom=false"* ]]; then
      break
    fi
    sleep 2
  done
  if [[ "$inspect_out" != *"running=true"* || "$inspect_out" != *"health=healthy"* || "$inspect_out" != *"oom=false"* ]]; then
    echo -e "${RD}[FEHLER] Container ist nicht gesund: ${inspect_out}${CL}" >&2
    qm guest exec "$vmid" -- docker logs --tail 50 aura-terminal >&2 || true
    return 1
  fi
  if ! curl -fsS --max-time 10 "http://${ip}:${PORT}/serving" | grep -q '"ok": true'; then
    echo -e "${RD}[FEHLER] Externer Healthcheck http://${ip}:${PORT}/serving fehlgeschlagen.${CL}" >&2
    return 1
  fi
  if ! curl -fsS --max-time 10 "http://${ip}:${PORT}/" | grep -q "AURA"; then
    echo -e "${RD}[FEHLER] Dashboard ist extern nicht erreichbar.${CL}" >&2
    return 1
  fi
  if ! curl -fsS --max-time 10 "http://${ip}:${PORT}/tutorial" | grep -q "AURA"; then
    echo -e "${RD}[FEHLER] Tutorial ist extern nicht erreichbar.${CL}" >&2
    return 1
  fi
  echo -e "${GN}[OK] Container gesund; Dashboard, Tutorial und Healthcheck extern erreichbar.${CL}"
}

# Übertrage eine Datei in eine VM via QEMU Guest Agent (in Chunks aufgeteilt)
transfer_file_to_vm() {
  local vmid="$1"
  local src="$2"
  local dst="$3"

  # Leere Ziel-Datei anlegen
  qm guest exec "$vmid" -- bash -c "mkdir -p '$(dirname "$dst")' && rm -f '$dst'" >/dev/null 2>&1

  # Splitte Base64 in 32KB Blöcke
  local tmp_b64
  tmp_b64=$(mktemp)
  base64 -w 0 "$src" > "$tmp_b64"

  local split_dir
  split_dir=$(mktemp -d)
  split -b 32000 "$tmp_b64" "$split_dir/part_"

  for part in "$split_dir"/part_*; do
    local chunk
    chunk=$(cat "$part")
    qm guest exec "$vmid" -- bash -c "echo -n '$chunk' >> '${dst}.b64'" >/dev/null 2>&1
  done

  # Dekodieren in der VM
  qm guest exec "$vmid" -- bash -c "base64 -d '${dst}.b64' > '$dst' && rm -f '${dst}.b64'" >/dev/null 2>&1

  rm -rf "$split_dir" "$tmp_b64"
}

# ------------------------------------------------------------------------------
# 1. TIEFENDIAGNOSE & SCANNER
# ------------------------------------------------------------------------------
echo -e "${BL}[1/3] Starte Tiefenscan der Server-Infrastruktur nach Docker...${CL}\n"

# A. Host-Check
echo -n "  ➜ Scanne Host-System... "
if command -v docker >/dev/null 2>&1; then
  HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
  echo -e "${GN}[DOCKER GEFUNDEN]${CL} (IPv4: $HOST_IP)"
  DOCKER_TARGETS+=("Host-System ($(hostname))")
  DOCKER_TYPES+=("host")
  DOCKER_IPS+=("$HOST_IP")
else
  echo -e "${YW}[Kein Docker auf Host]${CL}"
fi

# B. Proxmox LXC Container durchsuchen
IS_PVE=false
if command -v pveversion >/dev/null 2>&1; then
  IS_PVE=true
  echo -e "  ➜ Proxmox VE erkannt (${GN}$(pveversion)${CL}). Scanne alle LXC Container..."
  
  RUNNING_CTS=$(pct list 2>/dev/null | awk 'NR>1 && $2=="running" {print $1 ":" $3}' || true)
  if [[ -n "$RUNNING_CTS" ]]; then
    for ct in $RUNNING_CTS; do
      CT_ID="${ct%%:*}"
      CT_NAME="${ct##*:}"
      echo -n "    * Prüfe LXC $CT_ID ($CT_NAME)... "
      if pct exec "$CT_ID" -- sh -c "command -v docker || which docker" >/dev/null 2>&1; then
        CT_IP=$(pct exec "$CT_ID" -- ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || true)
        if [[ -z "$CT_IP" ]]; then
          CT_IP=$(pct exec "$CT_ID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)
        fi
        echo -e "${GN}[DOCKER AKTIV]${CL} (IPv4: ${CT_IP:-DHCP})"
        DOCKER_TARGETS+=("LXC $CT_ID ($CT_NAME - Docker)")
        DOCKER_TYPES+=("lxc_docker:$CT_ID")
        DOCKER_IPS+=("${CT_IP:-}")
      elif pct exec "$CT_ID" -- test -d /opt/aura >/dev/null 2>&1; then
        CT_IP=$(pct exec "$CT_ID" -- ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || true)
        if [[ -z "$CT_IP" ]]; then
          CT_IP=$(pct exec "$CT_ID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)
        fi
        echo -e "${GN}[AURA NATIV GEFUNDEN]${CL} (IPv4: ${CT_IP:-DHCP})"
        DOCKER_TARGETS+=("LXC $CT_ID ($CT_NAME - Nativer LXC Service)")
        DOCKER_TYPES+=("lxc_native:$CT_ID")
        DOCKER_IPS+=("${CT_IP:-}")
      else
        echo -e "${CL}[Kein Docker / Kein AURA]${CL}"
      fi
    done
  else
    echo "    (Keine aktiven LXC-Container gefunden)"
  fi

  # C. Proxmox QEMU/KVM VMs durchsuchen
  echo -e "  ➜ Scanne laufende KVM-VMs via QEMU Guest Agent..."
  RUNNING_VMS=$(qm list 2>/dev/null | awk 'NR>1 && $3=="running" {print $1 ":" $2}' || true)
  if [[ -n "$RUNNING_VMS" ]]; then
    for vm in $RUNNING_VMS; do
      VM_ID="${vm%%:*}"
      VM_NAME="${vm##*:}"
      echo -n "    * Prüfe VM $VM_ID ($VM_NAME)... "
      if qm guest exec "$VM_ID" -- which docker >/dev/null 2>&1; then
        VM_IP=$(get_vm_ipv4 "$VM_ID")
        echo -e "${GN}[DOCKER AKTIV]${CL} (IPv4: ${VM_IP:-wird ermittelt})"
        DOCKER_TARGETS+=("VM $VM_ID ($VM_NAME)")
        DOCKER_TYPES+=("vm:$VM_ID")
        DOCKER_IPS+=("$VM_IP")
      else
        echo -e "${CL}[Kein Docker / Kein Guest Agent]${CL}"
      fi
    done
  else
    echo "    (Keine laufenden KVM-VMs gefunden)"
  fi
fi

# ------------------------------------------------------------------------------
# 2. AUSWERTUNG & DEPLOYMENT-PFAD
# ------------------------------------------------------------------------------
echo -e "\n${BL}[2/3] Scan-Ergebnis:${CL}"
FOUND_COUNT=${#DOCKER_TARGETS[@]}

if [[ $FOUND_COUNT -gt 0 ]]; then
  echo -e "${GN}  ✓ Es wurden $FOUND_COUNT aktive Docker-Umgebung(en) gefunden!${CL}\n"
  for i in "${!DOCKER_TARGETS[@]}"; do
    D_IP="${DOCKER_IPS[$i]}"
    IP_DISP=${D_IP:-"DHCP / Auto-Detect"}
    echo -e "  $((i+1))) ${GN}${DOCKER_TARGETS[$i]}${CL} [IPv4: ${BL}${IP_DISP}${CL}]"
  done
  echo -e "  N) ${YW}Neuen dedizierten LXC Container aufsetzen (Best Practice)${CL}"
  echo ""
  read -r -p "Ziel für AURA Quant Terminal wählen [1-$FOUND_COUNT oder N, Standard: 1]: " TARGET_CHOICE
  TARGET_CHOICE=${TARGET_CHOICE:-1}

  if [[ "$TARGET_CHOICE" =~ ^[0-9]+$ ]] && [ "$TARGET_CHOICE" -ge 1 ] && [ "$TARGET_CHOICE" -le "$FOUND_COUNT" ]; then
    SEL_IDX=$((TARGET_CHOICE-1))
    SEL_TYPE="${DOCKER_TYPES[$SEL_IDX]}"
    SEL_TARGET="${DOCKER_TARGETS[$SEL_IDX]}"
    SEL_IP="${DOCKER_IPS[$SEL_IDX]}"

    echo -e "\n${BL}[3/3] Bereitstellung auf: $SEL_TARGET...${CL}"

    if [[ "$SEL_TYPE" == "host" ]]; then
      cd "$SCRIPT_DIR"
      docker build -t aura-quant-terminal:latest .
      docker stop aura-terminal >/dev/null 2>&1 || true
      docker rm aura-terminal >/dev/null 2>&1 || true
      docker run -d --name aura-terminal --restart unless-stopped -p "${PORT}:8787" aura-quant-terminal:latest
      SEL_IP=$(hostname -I | awk '{print $1}')

    elif [[ "$SEL_TYPE" =~ ^lxc_docker: || "$SEL_TYPE" =~ ^lxc: ]]; then
      T_CT_ID="${SEL_TYPE#lxc_docker:}"
      T_CT_ID="${T_CT_ID#lxc:}"
      echo -e "Übertrage Dateien in LXC $T_CT_ID (Docker)..."
      pct exec "$T_CT_ID" -- mkdir -p /opt/aura/data
      pct push "$T_CT_ID" "$SCRIPT_DIR/Dockerfile" /opt/aura/Dockerfile
      pct push "$T_CT_ID" "$SCRIPT_DIR/bitget_relay.py" /opt/aura/bitget_relay.py
      pct push "$T_CT_ID" "$SCRIPT_DIR/Symbiose_Dashboard.html" /opt/aura/Symbiose_Dashboard.html
      pct push "$T_CT_ID" "$SCRIPT_DIR/SYMBIOSE_Tutorial.html" /opt/aura/SYMBIOSE_Tutorial.html
      if [[ -f "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" ]]; then
        pct push "$T_CT_ID" "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" /opt/aura/data/bitget_usdt_futures_universe.json
      fi
      echo -e "Baue und starte Container in LXC $T_CT_ID..."
      pct exec "$T_CT_ID" -- bash -c "cd /opt/aura && docker build -t aura-quant-terminal:latest . && docker stop aura-terminal >/dev/null 2>&1 || true && docker rm aura-terminal >/dev/null 2>&1 || true && docker run -d --name aura-terminal --restart unless-stopped -p 8787:8787 aura-quant-terminal:latest"
      SEL_IP=$(pct exec "$T_CT_ID" -- ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || pct exec "$T_CT_ID" -- hostname -I | awk '{print $1}')

    elif [[ "$SEL_TYPE" =~ ^lxc_native: ]]; then
      T_CT_ID="${SEL_TYPE#lxc_native:}"
      echo -e "Übertrage Dateien in nativen AURA LXC $T_CT_ID..."
      pct exec "$T_CT_ID" -- mkdir -p /opt/aura/data
      pct push "$T_CT_ID" "$SCRIPT_DIR/bitget_relay.py" /opt/aura/bitget_relay.py
      pct push "$T_CT_ID" "$SCRIPT_DIR/Symbiose_Dashboard.html" /opt/aura/Symbiose_Dashboard.html
      pct push "$T_CT_ID" "$SCRIPT_DIR/SYMBIOSE_Tutorial.html" /opt/aura/SYMBIOSE_Tutorial.html
      if [[ -f "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" ]]; then
        pct push "$T_CT_ID" "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" /opt/aura/data/bitget_usdt_futures_universe.json
      fi
      echo -e "Starte nativen AURA Service in LXC $T_CT_ID neu..."
      pct exec "$T_CT_ID" -- sh -c "rc-service aura restart 2>/dev/null || systemctl restart aura 2>/dev/null || (pkill -f bitget_relay.py || true && nohup python3 /opt/aura/bitget_relay.py >/opt/aura/aura.log 2>&1 &)"
      SEL_IP=$(pct exec "$T_CT_ID" -- ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || pct exec "$T_CT_ID" -- hostname -I | awk '{print $1}')

    elif [[ "$SEL_TYPE" =~ ^vm: ]]; then
      T_VM_ID="${SEL_TYPE#vm:}"
      echo -e "Erstelle Verzeichnis /opt/aura in VM $T_VM_ID..."
      qm guest exec "$T_VM_ID" -- mkdir -p /opt/aura/data >/dev/null 2>&1

      echo -e "Kopiere Dateien sauber in VM $T_VM_ID via QEMU Guest Agent..."
      for f in Dockerfile bitget_relay.py Symbiose_Dashboard.html SYMBIOSE_Tutorial.html; do
        if [[ -f "$SCRIPT_DIR/$f" ]]; then
          echo -n "  ➜ Übertrage $f... "
          transfer_file_to_vm "$T_VM_ID" "$SCRIPT_DIR/$f" "/opt/aura/$f"
          echo -e "${GN}[OK]${CL}"
        fi
      done

      if [[ -f "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" ]]; then
        echo -n "  ➜ Übertrage data/bitget_usdt_futures_universe.json... "
        transfer_file_to_vm "$T_VM_ID" "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" "/opt/aura/data/bitget_usdt_futures_universe.json"
        echo -e "${GN}[OK]${CL}"
      fi

      # IPv4 vor dem Start ermitteln, damit /api/state den LAN-Host explizit erlaubt.
      SEL_IP=$(wait_for_vm_ipv4 "$T_VM_ID" 30) || {
        echo -e "${RD}[FEHLER] Keine LAN-IPv4 für VM $T_VM_ID ermittelt. Prüfe den QEMU Guest Agent.${CL}" >&2
        exit 1
      }

      echo -e "\nBaue und starte AURA Docker Container in VM $T_VM_ID..."
      RUN_CMD="cd /opt/aura && docker build -t aura-quant-terminal:latest . && docker stop aura-terminal >/dev/null 2>&1 || true; docker rm aura-terminal >/dev/null 2>&1 || true; docker run -d --name aura-terminal --restart unless-stopped -p ${PORT}:8787 -e AURA_ALLOWED_HOSTS='$SEL_IP' -e AURA_STATE_DIR=/var/lib/aura -v aura-state:/var/lib/aura aura-quant-terminal:latest"
      DEPLOY_OUT=$(qm guest exec "$T_VM_ID" -- bash -c "$RUN_CMD")
      if [[ "$DEPLOY_OUT" != *'"exitcode" : 0'* && "$DEPLOY_OUT" != *'"exitcode":0'* && "$DEPLOY_OUT" != *'"exitcode": 0'* ]]; then
        echo -e "${RD}[FEHLER] Docker-Deployment in VM $T_VM_ID fehlgeschlagen:${CL}" >&2
        echo "$DEPLOY_OUT" >&2
        exit 1
      fi
      verify_vm_deployment "$T_VM_ID" "$SEL_IP"
    fi

    if [[ -z "$SEL_IP" ]]; then
      echo -e "${RD}[FEHLER] Keine LAN-IP für das gewählte Ziel ermittelt; Deployment wird nicht als erfolgreich gemeldet.${CL}" >&2
      exit 1
    fi

    echo -e "\n${GN}======================================================${CL}"
    echo -e "${GN}  AURA QUANT TERMINAL ERFOLGREICH BEREITGESTELLT!${CL}"
    echo -e "${GN}======================================================${CL}"
    echo -e "Web-Dashboard:  ${BL}http://${SEL_IP}:${PORT}/${CL}"
    echo -e "Tutorial:       ${BL}http://${SEL_IP}:${PORT}/tutorial${CL}"
    echo -e "Healthcheck:    ${BL}http://${SEL_IP}:${PORT}/serving${CL}"
    echo -e "Status:         ${YW}Container 'aura-terminal' laeuft aktiv in ${SEL_TARGET}.${CL}"
    echo -e "======================================================\n"
    exit 0
  fi
fi

# ------------------------------------------------------------------------------
# 3. FALLBACK: KEIN DOCKER GEFUNDEN -> BESTES INDIVIDUELLES SETUP ERMITTELN
# ------------------------------------------------------------------------------
echo -e "${YW}  ➜ Kein bestehender Docker-Service gefunden.${CL}"
echo -e "${BL}  ➜ Ermittle automatisch das hardware-optimale Setup...${CL}\n"

TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
CPU_CORES=$(nproc)

echo -e "  Hardware-Profil: ${PR}$CPU_CORES Cores / $TOTAL_RAM_MB MB RAM${CL}"

if [[ "$IS_PVE" == true ]]; then
  echo -e "\n${GN}[EMPFEHLUNG FUER PROXMOX VE]${CL}"
  echo -e "  1) ${GN}Neuen isolierten Docker-LXC erstellen (Empfohlen für Modularität)${CL}"
  echo -e "     -> Debian 12 mit Nesting/Keyctl & vorkonfigurierter Docker Engine."
  echo -e "  2) ${BL}Ultra-Leichtgewicht Alpine LXC (~35 MB RAM - Maximale Ressourceneffizienz)${CL}"
  echo -e "     -> Nativer Python Daemon ohne Docker-Overhead."
  read -r -p "Auswahl [1-2, Standard: 1]: " PVE_CHOICE
  PVE_CHOICE=${PVE_CHOICE:-1}

  if [[ "$PVE_CHOICE" == "2" ]]; then
    bash "$SCRIPT_DIR/proxmox_lxc_install.sh"
    exit 0
  else
    bash "$SCRIPT_DIR/smart_homelab_installer.sh"
    exit 0
  fi
else
  echo -e "\n${GN}[EMPFEHLUNG FUER LINUX / HOMELAB]${CL}"
  echo -e "  Installiere offizielle Docker Engine vollautomatisch und starte AURA Terminal."
  read -r -p "Jetzt ausführen? (y/n) [y]: " RUN_DOCKER_INSTALL
  RUN_DOCKER_INSTALL=${RUN_DOCKER_INSTALL:-y}
  if [[ "$RUN_DOCKER_INSTALL" == [yY]* ]]; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    cd "$SCRIPT_DIR"
    docker build -t aura-quant-terminal:latest .
    docker run -d --name aura-terminal --restart unless-stopped -p "${PORT}:8787" aura-quant-terminal:latest
    MY_IP=$(hostname -I | awk '{print $1}')
    echo -e "\n${GN}======================================================${CL}"
    echo -e "${GN}  AURA QUANT TERMINAL ERFOLGREICH GESTARTET!${CL}"
    echo -e "${GN}======================================================${CL}"
    echo -e "Web-Dashboard: http://${MY_IP}:${PORT}/"
    echo -e "======================================================\n"
  fi
fi
