#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal - Smart Auto-Detect Proxmox VE & Homelab Installer
# ==============================================================================
# Automatische Erkennung:
# 1. Prüft, ob Docker auf dem System/Host vorhanden ist -> richtet Container ein.
# 2. Wenn kein Docker:
#    - Auf Proxmox VE: Bietet automatischen Docker-LXC oder nativen LXC an & installiert.
#    - Auf Linux/Debian/Ubuntu: Installiert Docker automatisiert & startet Container.
# ==============================================================================

set -euo pipefail

# ANSI Farbcodes
YW=$(echo "\033[33m")
BL=$(echo "\033[36m")
RD=$(echo "\033[01;31m")
GN=$(echo "\033[1;92m")
CL=$(echo "\033[m")

clear
cat << "EOF"
    ___   __  ______  ___       ____                    
   /   | / / / / __ \/   |     / __ \__  ______ _____  / /_
  / /| |/ / / / /_/ / /| |    / / / / / / / __ `/ __ \/ __/
 / ___ / /_/ / _, _/ ___ |   / /_/ / /_/ / /_/ / / / / /_  
/_/  |_\____/_/ |_/_/  |_|   \___\_\__,_/\__,_/_/ /_/\__/  
Smart Homelab & Proxmox Auto-Detect Installer (Click & Go)
==========================================================
EOF

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PORT="${AURA_PORT:-8787}"

# ------------------------------------------------------------------------------
# 1. Funktion: AURA per Docker bereitstellen
# ------------------------------------------------------------------------------
deploy_docker() {
  echo -e "\n${BL}[DOCKER] Starte Bereitstellung von AURA Quant Terminal via Docker...${CL}"
  cd "$SCRIPT_DIR"
  
  if ! docker info >/dev/null 2>&1; then
    echo -e "${YW}[INFO] Docker Daemon antwortet nicht, versuche Service-Start...${CL}"
    systemctl start docker || service docker start || true
    sleep 2
  fi

  echo -e "${BL}[1/3] Baue Docker Image (aura-quant-terminal:latest)...${CL}"
  docker build -t aura-quant-terminal:latest "$SCRIPT_DIR"

  echo -e "${BL}[2/3] Bereinige alte Container falls vorhanden...${CL}"
  docker stop aura-terminal >/dev/null 2>&1 || true
  docker rm aura-terminal >/dev/null 2>&1 || true

  echo -e "${BL}[3/3] Starte Container im Hintergrund auf Port ${PORT}...${CL}"
  docker run -d \
    --name aura-terminal \
    --restart unless-stopped \
    -p "${PORT}:8787" \
    aura-quant-terminal:latest

  # Host-IP ermitteln
  HOST_IP=$(hostname -I | awk '{print $1}' || echo "localhost")

  echo -e "\n${GN}======================================================${CL}"
  echo -e "${GN}  AURA QUANT TERMINAL ERFOLGREICH VIA DOCKER GESTARTET!${CL}"
  echo -e "${GN}======================================================${CL}"
  echo -e "Web-Dashboard:  ${BL}http://${HOST_IP}:${PORT}/${CL}"
  echo -e "Tutorial:       ${BL}http://${HOST_IP}:${PORT}/tutorial${CL}"
  echo -e "Healthcheck:    ${BL}http://${HOST_IP}:${PORT}/serving${CL}"
  echo -e "Status:         ${YW}Container 'aura-terminal' laeuft & startet automatisch bei Boot.${CL}"
  echo -e "======================================================\n"
  exit 0
}

# ------------------------------------------------------------------------------
# 2. Funktion: Docker auf Standard-Linux (Debian/Ubuntu/Alpine) installieren
# ------------------------------------------------------------------------------
install_docker_and_deploy() {
  echo -e "\n${YW}[AUTONOM] Kein Docker gefunden. Starte automatische Docker-Installation...${CL}"
  if [[ $(id -u) -ne 0 ]]; then
    echo -e "${RD}[FEHLER] Root-Rechte (sudo) erforderlich, um Docker zu installieren!${CL}"
    exit 1
  fi

  echo -e "${BL}Installiere offizielle Docker Engine via get.docker.com...${CL}"
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
  echo -e "${GN}[OK] Docker wurde erfolgreich installiert!${CL}"
  deploy_docker
}

# ------------------------------------------------------------------------------
# 3. Funktion: Proxmox VE LXC Container mit Docker einrichten
# ------------------------------------------------------------------------------
deploy_proxmox_docker_lxc() {
  echo -e "\n${BL}[PROXMOX] Erstelle dedizierten Docker-LXC Container auf Proxmox VE...${CL}"
  
  NEXTID=$(pvesh get /cluster/nextid)
  read -r -p "Container ID eingeben [Standard: $NEXTID]: " CT_ID
  CT_ID=${CT_ID:-$NEXTID}

  read -r -p "Hostname eingeben [Standard: aura-docker]: " CT_NAME
  CT_NAME=${CT_NAME:-aura-docker}

  read -r -p "RAM in MB [Standard: 1024]: " CT_RAM
  CT_RAM=${CT_RAM:-1024}

  read -r -p "Disk-Groesse in GB [Standard: 8]: " CT_DISK
  CT_DISK=${CT_DISK:-8}

  DEFAULT_STORAGE=$(pvesm status -content rootdir | awk 'NR>1 {print $1; exit}')
  read -r -p "Storage Pool [Standard: $DEFAULT_STORAGE]: " CT_STORAGE
  CT_STORAGE=${CT_STORAGE:-$DEFAULT_STORAGE}

  read -r -p "Netzwerk Bridge [Standard: vmbr0]: " CT_BRIDGE
  CT_BRIDGE=${CT_BRIDGE:-vmbr0}

  echo -e "\n${BL}[1/6] Lade Debian Template fuer Docker herunter...${CL}"
  pveam update >/dev/null 2>&1 || true
  TEMPLATE=$(pveam available -section system | grep debian-12-standard | sort -V | tail -n1 | awk '{print $2}')
  if ! pveam list "$CT_STORAGE" | grep -q "$TEMPLATE"; then
    pveam download "$CT_STORAGE" "$TEMPLATE"
  fi
  TEMPLATE_FILE="$CT_STORAGE:vztmpl/$TEMPLATE"

  echo -e "${BL}[2/6] Erstelle LXC Container (mit Docker/Nesting-Support)...${CL}"
  pct create "$CT_ID" "$TEMPLATE_FILE" \
    --hostname "$CT_NAME" \
    --cores 2 \
    --memory "$CT_RAM" \
    --swap 512 \
    --rootfs "$CT_STORAGE:${CT_DISK}" \
    --ostype debian \
    --net0 "name=eth0,bridge=$CT_BRIDGE,ip=dhcp,firewall=1" \
    --storage "$CT_STORAGE" \
    --onboot 1 \
    --unprivileged 1 \
    --features "nesting=1,keyctl=1"

  echo -e "${BL}[3/6] Starte Container ID $CT_ID...${CL}"
  pct start "$CT_ID"
  sleep 5

  echo -e "${BL}[4/6] Installiere Docker im LXC Container...${CL}"
  pct exec "$CT_ID" -- apt-get update -y
  pct exec "$CT_ID" -- apt-get install -y curl ca-certificates
  pct exec "$CT_ID" -- bash -c "curl -fsSL https://get.docker.com | sh"
  pct exec "$CT_ID" -- systemctl enable --now docker

  echo -e "${BL}[5/6] Kopiere AURA Projektdateien in den Container...${CL}"
  pct exec "$CT_ID" -- mkdir -p /opt/aura/data
  pct push "$CT_ID" "$SCRIPT_DIR/Dockerfile" /opt/aura/Dockerfile
  pct push "$CT_ID" "$SCRIPT_DIR/bitget_relay.py" /opt/aura/bitget_relay.py
  pct push "$CT_ID" "$SCRIPT_DIR/Symbiose_Dashboard.html" /opt/aura/Symbiose_Dashboard.html
  pct push "$CT_ID" "$SCRIPT_DIR/SYMBIOSE_Tutorial.html" /opt/aura/SYMBIOSE_Tutorial.html
  if [[ -f "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" ]]; then
    pct push "$CT_ID" "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" /opt/aura/data/bitget_usdt_futures_universe.json
  fi

  echo -e "${BL}[6/6] Baue und starte AURA Docker Container im LXC...${CL}"
  pct exec "$CT_ID" -- bash -c "cd /opt/aura && docker build -t aura-quant-terminal:latest . && docker run -d --name aura-terminal --restart unless-stopped -p 8787:8787 aura-quant-terminal:latest"

  sleep 3
  IP=""
  for i in {1..10}; do
    IP=$(pct exec "$CT_ID" -- ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || true)
    if [[ -n "$IP" ]]; then break; fi
    sleep 1
  done

  echo -e "\n${GN}======================================================${CL}"
  echo -e "${GN}  PROXMOX DOCKER LXC ERFOLGREICH EINGERICHTET!${CL}"
  echo -e "${GN}======================================================${CL}"
  if [[ -n "$IP" ]]; then
    echo -e "Web-Dashboard:  ${BL}http://${IP}:8787/${CL}"
    echo -e "Tutorial:       ${BL}http://${IP}:8787/tutorial${CL}"
  else
    echo -e "Web-Dashboard:  ${BL}http://<CONTAINER-IP>:8787/${CL}"
  fi
  echo -e "Status:         ${YW}LXC Container $CT_ID mit isoliertem Docker laeuft.${CL}"
  echo -e "======================================================\n"
  exit 0
}

# ------------------------------------------------------------------------------
# 4. Hauptlogik: Scannen & Entscheiden
# ------------------------------------------------------------------------------
echo -e "${BL}[SCAN] Scanne Umgebung nach Docker und Proxmox VE...${CL}"

# Fall 1: Docker ist bereits lokal installiert und nutzbar
if command -v docker >/dev/null 2>&1; then
  echo -e "${GN}[GEFUNDEN] Docker ist bereits auf diesem Host installiert!${CL}"
  deploy_docker
fi

# Fall 2: Kein Docker, aber System ist ein Proxmox VE Host (pveversion vorhanden)
if command -v pveversion >/dev/null 2>&1; then
  echo -e "${YW}[PROXMOX VE HOST ERKANNT] Kein Docker direkt auf dem Host.${CL}"
  echo -e "Waehle Installationsmodus:"
  echo -e "  1) ${GN}Dedizierten Docker-LXC Container erstellen (Empfohlen & Isoliert)${CL}"
  echo -e "  2) ${BL}Ultra-schlanken nativen Alpine LXC Container erstellen (~35 MB RAM)${CL}"
  read -r -p "Auswahl [1-2, Standard: 1]: " PVE_CHOICE
  PVE_CHOICE=${PVE_CHOICE:-1}

  if [[ "$PVE_CHOICE" == "2" ]]; then
    bash "$SCRIPT_DIR/proxmox_lxc_install.sh"
    exit 0
  else
    deploy_proxmox_docker_lxc
  fi
fi

# Fall 3: Standard Linux Server / Homelab ohne Docker
install_docker_and_deploy
