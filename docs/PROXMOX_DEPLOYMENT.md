# Proxmox / Homelab Inbetriebnahme (Runbook)

Dieses minimale Runbook beschreibt die Erstinbetriebnahme des AURA v3 Terminals in einer Linux-basierten Proxmox-VM (z.B. Debian/Ubuntu) oder einem Homelab Server mit Docker in 24/7 Betrieb.

## Systemvoraussetzungen
1. Eine laufende Linux-VM (z.B. Debian 12) auf Proxmox.
2. Installiertes **Docker** und das **Docker Compose**-Plugin (`docker compose`).
3. Port `8000` darf auf dem Host nicht von anderen Diensten belegt sein.

## 3 Schritte zur Inbetriebnahme

**1. Repository klonen / Projekt bereitstellen**
Laden Sie den Quellcode auf die Proxmox VM:
```bash
git clone https://github.com/trixr1907/AURA-Quant-Terminal.git /opt/aura
cd /opt/aura
```

**2. Umgebungsvariablen `.env` anlegen**
Eine Vorlage liegt als `.env.example` bei. Für die Inbetriebnahme diese umbenennen und den Token sicher setzen:
```bash
cp .env.example .env
nano .env  # -> AURA_RELAY_TOKEN anpassen!
```

**3. Container-Stack starten**
Build durchführen und Container im Hintergrund (detached) hochfahren.
```bash
docker compose up -d --build
```

## Verifikation nach dem Start
Überprüfen Sie den reibungslosen Container-Status:
```bash
docker compose ps
```
Beide Services (`aura-api` und `aura-worker`) sollten nach ein paar Minuten den Status `(healthy)` anzeigen.

Die Start-Logbücher lassen sich einsehen über:
```bash
docker compose logs -f
```

## Aufruf im Browser
Sobald der Container läuft, erreichen Sie das moderne, mobile-optimierte Terminal einfach über das Heimnetzwerk auf Ihrem **PC oder Smartphone**.
Nutzen Sie dazu die IP-Adresse der Proxmox VM:

`http://<SERVER-IP>:8000/`

(Bspw: `http://192.168.178.50:8000/`)

Eine dedizierte mobile Nutzung ist hierüber von jedem Smartphone im WLAN reibungslos möglich.
