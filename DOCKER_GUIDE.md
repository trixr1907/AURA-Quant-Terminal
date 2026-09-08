# 🐳 AURA Quant Terminal - Docker & Homelab Setup Guide

Das AURA Quant Terminal lässt sich mit einem einzigen Befehl lokal oder auf jedem beliebigen Homelab-Server (Unraid, Proxmox, TrueNAS, Synology, Raspberry Pi / VPS) als isolierter, performanter Docker-Container starten.

---

## ⚡ Schnellstart: Click & Go (Windows)

1. Doppelklicke auf **`DOCKER_START.bat`**.
2. Das Skript prüft Docker, baut das schlanke Alpine-Image und startet das Terminal automatisch im Hintergrund auf **Port 8787**.
3. Dein Standard-Browser öffnet sich direkt auf `http://localhost:8787/`.
4. **Beenden:** Mit **`DOCKER_STOP.bat`** lässt sich der Container jederzeit sauber stoppen.

---

## 🏠 Homelab, Linux Server & VPS

### Option A: Via Shell-Skript (Linux / macOS)
```bash
chmod +x docker_start.sh
./docker_start.sh
```

### Option B: Docker Compose (Portainer, Dockge, CasaOS, CLI)
```bash
# Starten im Hintergrund
docker compose up -d

# Logs ansehen
docker compose logs -f

# Stoppen
docker compose down
```

### Option C: Portainer Stacks / Unraid Template
Kopiere einfach den Inhalt von `docker-compose.yml` in deinen Stack-Editor:
```yaml
services:
  aura-terminal:
    build:
      context: .
      dockerfile: Dockerfile
    image: aura-quant-terminal:latest
    container_name: aura-terminal
    restart: unless-stopped
    ports:
      - "8787:8787"
    environment:
      - SYM_PORT=8787
```

---

## 🔧 Port anpassen
Falls Port 8787 auf deinem Host bereits belegt ist:
- Erstelle eine `.env`-Datei (Vorlage `.env.example`):
  ```env
  AURA_PORT=9090
  ```
- Oder starte direkt via Docker CLI:
  ```bash
  docker run -d --name aura-terminal --restart unless-stopped -p 9090:8787 aura-quant-terminal:latest
  ```

---

## 🛡️ Sicherheit & Architektur
- **Base Image:** `python:3.12-alpine` (Minimaler Footprint, ~65MB Image-Größe).
- **Non-Root Execution:** Läuft unter dem isolierten Benutzer `aura` (keine Root-Rechte im Container).
- **Healthcheck:** Automatischer interner Healthcheck auf `/serving`.
- **Stateless & Read-Only:** Keine API-Keys oder Zugangsdaten nötig.
