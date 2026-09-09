#!/bin/bash
# setup_auto_update_service.sh — Installs AURA Auto-Updater Service on VM 201
set -e

APP_DIR="/opt/aura-terminal"
SERVICE_NAME="aura-updater"

echo "=== AURA AUTO-UPDATER SERVICE INSTALLATION ==="
mkdir -p "$APP_DIR/scripts"

# Copy updater script
cp "$(dirname "$0")/aura_auto_updater.py" "$APP_DIR/scripts/aura_auto_updater.py" 2>/dev/null || true
chmod +x "$APP_DIR/scripts/aura_auto_updater.py"

# Create systemd service
cat << 'EOF' > /etc/systemd/system/aura-updater.service
[Unit]
Description=AURA Quant Terminal Auto-Updater Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aura-terminal
ExecStart=/usr/bin/python3 /opt/aura-terminal/scripts/aura_auto_updater.py
Restart=always
RestartSec=10
Environment="AURA_REPO=trixr1907/AURA-Quant-Terminal"
Environment="AURA_UPDATE_INTERVAL=60"
Environment="AURA_APP_DIR=/opt/aura-terminal"
Environment="AURA_CONTAINER_NAME=aura-terminal"
Environment="AURA_PORT=8787"
Environment="AURA_STATE_VOLUME=aura-state"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "✅ AURA Auto-Updater erfolgreich als systemd-Service installiert und gestartet!"
echo "Status anzeigen mit: systemctl status $SERVICE_NAME"
echo "Logs ansehen mit:     journalctl -u $SERVICE_NAME -f"
