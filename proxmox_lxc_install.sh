#!/usr/bin/env bash
# ==============================================================================
# AURA Quant Terminal - Proxmox VE Automated LXC Installer (Community Helper Style)
# ==============================================================================
# Fuehre diesen Befehl direkt in der Proxmox VE Host Shell (PVE Node) aus:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/.../proxmox_lxc_install.sh)"
# oder lade die Datei hoch und starte:
#   bash proxmox_lxc_install.sh
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
Proxmox VE LXC Container Installer (Click & Go)
======================================================
EOF

# Root Check
if [[ $(id -u) -ne 0 ]]; then
  echo -e "${RD}[FEHLER] Dieses Skript muss direkt als root auf dem Proxmox VE Host ausgefuehrt werden!${CL}"
  exit 1
fi

# Pruefe PVE Umgebung
if ! command -v pveversion >/dev/null 2>&1; then
  echo -e "${RD}[FEHLER] Kein Proxmox VE System erkannt (pveversion fehlt)!${CL}"
  exit 1
fi

echo -e "${BL}[INFO] Proxmox VE erkannt: $(pveversion)${CL}\n"

# Finde naechste freie CT ID
NEXTID=$(pvesh get /cluster/nextid)
read -r -p "Container ID eingeben [Standard: $NEXTID]: " CT_ID
CT_ID=${CT_ID:-$NEXTID}

# Hostname
read -r -p "Hostname eingeben [Standard: aura-terminal]: " CT_NAME
CT_NAME=${CT_NAME:-aura-terminal}

# RAM & Cores
read -r -p "RAM in MB zuweisen [Standard: 512]: " CT_RAM
CT_RAM=${CT_RAM:-512}

read -r -p "CPU Cores zuweisen [Standard: 1]: " CT_CORES
CT_CORES=${CT_CORES:-1}

# Storage Pool ermitteln
DEFAULT_STORAGE=$(pvesm status -content rootdir | awk 'NR>1 {print $1; exit}')
read -r -p "Storage Pool [Standard: $DEFAULT_STORAGE]: " CT_STORAGE
CT_STORAGE=${CT_STORAGE:-$DEFAULT_STORAGE}

# Bridge
read -r -p "Netzwerk Bridge [Standard: vmbr0]: " CT_BRIDGE
CT_BRIDGE=${CT_BRIDGE:-vmbr0}

echo -e "\n${YW}======================================================${CL}"
echo -e "Container ID:   ${GN}$CT_ID${CL}"
echo -e "Hostname:       ${GN}$CT_NAME${CL}"
echo -e "Ressourcen:     ${GN}$CT_CORES Cores / $CT_RAM MB RAM${CL}"
echo -e "Storage:        ${GN}$CT_STORAGE${CL}"
echo -e "Bridge:         ${GN}$CT_BRIDGE (DHCP)${CL}"
echo -e "${YW}======================================================${CL}\n"

read -r -p "Installation jetzt starten? (y/n) [y]: " CONFIRM
CONFIRM=${CONFIRM:-y}
if [[ "$CONFIRM" != [yY]* ]]; then
  echo "Abgebrochen."
  exit 0
fi

# 1. Alpine Linux Template aktualisieren / herunterladen
echo -e "\n${BL}[1/5] Lade leichtgewichtiges Alpine Linux Template herunter...${CL}"
pveam update >/dev/null 2>&1 || true
TEMPLATE=$(pveam available -section system | grep alpine-3 | sort -V | tail -n1 | awk '{print $2}')

if ! pveam list "$CT_STORAGE" | grep -q "$TEMPLATE"; then
  echo -e "Herunterladen von $TEMPLATE auf $CT_STORAGE..."
  pveam download "$CT_STORAGE" "$TEMPLATE"
fi

TEMPLATE_FILE="$CT_STORAGE:vztmpl/$TEMPLATE"

# 2. LXC Container erstellen
echo -e "${BL}[2/5] Erstelle LXC Container (ID: $CT_ID)...${CL}"
pct create "$CT_ID" "$TEMPLATE_FILE" \
  --hostname "$CT_NAME" \
  --cores "$CT_CORES" \
  --memory "$CT_RAM" \
  --swap 256 \
  --ostype alpine \
  --net0 "name=eth0,bridge=$CT_BRIDGE,ip=dhcp,firewall=1" \
  --storage "$CT_STORAGE" \
  --onboot 1 \
  --unprivileged 1 \
  --features nesting=1

# 3. Container starten
echo -e "${BL}[3/5] Starte Container...${CL}"
pct start "$CT_ID"
sleep 4

# 4. Abhängigkeiten im Container installieren
echo -e "${BL}[4/5] Richte Python & AURA Service ein...${CL}"
pct exec "$CT_ID" -- apk update
pct exec "$CT_ID" -- apk add --no-cache python3 curl bash

# Anwendungsverzeichnis vorbereiten
pct exec "$CT_ID" -- mkdir -p /opt/aura/data

# Lokale Dateien kopieren falls aus Workspace ausgefuehrt, sonst minimales Setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
if [[ -f "$SCRIPT_DIR/bitget_relay.py" ]]; then
  pct push "$CT_ID" "$SCRIPT_DIR/bitget_relay.py" /opt/aura/bitget_relay.py
  if [[ -f "$SCRIPT_DIR/VERSION" ]]; then
    pct push "$CT_ID" "$SCRIPT_DIR/VERSION" /opt/aura/VERSION
  fi
  pct push "$CT_ID" "$SCRIPT_DIR/Symbiose_Dashboard.html" /opt/aura/Symbiose_Dashboard.html
  pct push "$CT_ID" "$SCRIPT_DIR/SYMBIOSE_Tutorial.html" /opt/aura/SYMBIOSE_Tutorial.html
  if [[ -f "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" ]]; then
    pct push "$CT_ID" "$SCRIPT_DIR/data/bitget_usdt_futures_universe.json" /opt/aura/data/bitget_usdt_futures_universe.json
  fi
fi

# 5. LXC LAN-IP muss vor Service-Erstellung/-Start fail-closed ermittelt werden
# (der Service verwendet die ermittelte IP als Allowlist und persistiert State).
echo -e "${BL}[5/5] Ermittle LXC-LAN-IP...${CL}"
sleep 3
IP=""
for i in {1..10}; do
  IP=$(pct exec "$CT_ID" -- sh -c "ip -4 -o addr show scope global dev eth0 | awk 'NR==1 {split(\$4,a,\"/\"); print a[1]}'" || true)
  if [[ "$IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then break; fi
  IP=""
  sleep 1
done
if [[ -z "$IP" ]]; then
  echo -e "${RD}[FEHLER] Keine gültige LAN-IPv4 auf eth0 gefunden; Service wird nicht gestartet.${CL}"
  exit 1
fi

pct exec "$CT_ID" -- env AURA_ALLOWED_HOSTS="$IP" AURA_STATE_DIR=/var/lib/aura sh -c 'mkdir -p /var/lib/aura'
pct exec "$CT_ID" -- env AURA_ALLOWED_HOSTS="$IP" AURA_STATE_DIR=/var/lib/aura sh -c 'cat << "SVC" > /etc/init.d/aura-terminal
#!/sbin/openrc-run

name="AURA Quant Terminal"
description="AURA Quant Terminal & Relay Service"
command="/usr/bin/python3"
command_args="/opt/aura/bitget_relay.py"
command_background="yes"
pidfile="/run/aura-terminal.pid"
directory="/opt/aura"
export SYM_HOST="0.0.0.0"
export SYM_PORT="8787"
export AURA_ALLOWED_HOSTS="'"$IP"'"
export AURA_STATE_DIR="/var/lib/aura"

depend() {
    need net
    after firewall
}
SVC
chmod +x /etc/init.d/aura-terminal
rc-update add aura-terminal default
rc-service aura-terminal start
'


echo -e "\n${GN}======================================================${CL}"
echo -e "${GN}  AURA QUANT TERMINAL ERFOLGREICH INSTALLIERT!${CL}"
echo -e "${GN}======================================================${CL}"
if [[ -n "$IP" ]]; then
  echo -e "Web-Dashboard:  ${BL}http://${IP}:8787/${CL}"
  echo -e "Tutorial:       ${BL}http://${IP}:8787/tutorial${CL}"
else
  echo -e "Web-Dashboard:  ${BL}http://<CONTAINER-IP>:8787/${CL} (Pruefe IP in Proxmox Web-UI)"
fi
echo -e "Status:         ${YW}LXC Container $CT_ID laeuft im Hintergrund & startet bei Boot.${CL}"
echo -e "Verwaltung:     ${YW}pct enter $CT_ID${CL} oder ueber Proxmox Web-UI."
echo -e "======================================================\n"
