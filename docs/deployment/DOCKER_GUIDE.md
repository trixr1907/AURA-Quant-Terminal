# 🐳 AURA Quant Terminal - Docker & Homelab Setup Guide

Das AURA Quant Terminal lässt sich lokal oder im Homelab als isolierter Docker-Container starten. Für den vollständigen Funktionsumfang werden **keine Bitget-API-Schlüssel** benötigt: Der Relay greift ausschließlich auf öffentliche, unauthentifizierte Marktdaten-Endpunkte zu. Ein Read-only-Key ist derzeit nicht erforderlich und bringt lediglich für künftige private Kontoansichten potenziellen Nutzen.

> **Proxmox + VM 201 (`docker-core`):** Verwende `PROXMOX_DEPLOY.bat`, wähle VM 201 und öffne anschließend `http://192.168.8.115:8787/`. Der Deployer übergibt die VM-IP als erlaubten Host, bindet persistenten Zustand an das Docker-Volume `aura-state` und meldet Erfolg erst nach interner und externer Health-Verifikation.

---

## ⚡ Schnellstart: Click & Go (Windows)

1. Doppelklicke auf **`DOCKER_START.bat`**.
2. Das Skript prüft Docker, baut das schlanke Alpine-Image, startet das Terminal automatisch im Hintergrund auf **Port 8787** und führt eine Bounded-Readiness-Prüfung (`/serving`, `/ready`, `/api/public`, `/api/state`) durch.
3. Nach erfolgreicher Verifikation öffnet sich dein Standard-Browser direkt auf `http://localhost:8787/`.
4. **Beenden:** Mit **`DOCKER_STOP.bat`** lässt sich der Container jederzeit sauber stoppen.

---

## 🏠 Homelab, Linux Server & VPS

### Option A: Via Shell-Skript (Linux / macOS)
```bash
chmod +x docker_start.sh
./docker_start.sh
```
Das Skript führt nach dem Start eine automatische Bounded-Readiness-Probe durch (Liveness `/serving`, Marktdaten-Readiness `/ready`, Public-Ticker `/api/public` und State `/api/state`) und gibt bei Fehlern automatisch die Container-Logs aus.

### Option B: Docker Compose (Portainer, Dockge, CasaOS, CLI)
Lege vorher eine `.env` neben `docker-compose.yml`:
```env
AURA_PORT=8787
AURA_ALLOWED_HOSTS=192.168.8.115
```
Passe `AURA_ALLOWED_HOSTS` an die LAN-IP oder den DNS-Namen an, den du im Browser verwendest. Mehrere Werte sind komma-getrennt möglich. Loopback (`127.0.0.1` und `localhost`) bleibt intern immer erlaubt.

```bash
# Konfiguration prüfen
docker compose config

# Starten und neu bauen
docker compose up -d --build

# Gesundheitszustand prüfen
docker inspect aura-terminal --format '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}'
curl -fsS http://192.168.8.115:8787/serving
curl -fsS http://192.168.8.115:8787/ready

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
      - SYM_HOST=0.0.0.0
      - AURA_ALLOWED_HOSTS=192.168.8.115
      - AURA_STATE_DIR=/var/lib/aura
    volumes:
      - aura-state:/var/lib/aura

volumes:
  aura-state:
    name: aura-state
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
  docker run -d --name aura-terminal --restart unless-stopped \
    -p 9090:8787 \
    -e AURA_ALLOWED_HOSTS=<HOST-IP-ODER-DNS> \
    -e AURA_STATE_DIR=/var/lib/aura \
    -v aura-state:/var/lib/aura \
    aura-quant-terminal:latest
  ```
  Ersetze `<HOST-IP-ODER-DNS>` durch die IP-Adresse oder den DNS-Namen,
  unter dem du das Dashboard im Browser öffnest, zum Beispiel
  `192.168.8.115` oder `aura.example`. Der externe Host-Port `9090` darf
  vom internen Relay-Port `8787` abweichen; öffne danach
  `http://<HOST-IP-ODER-DNS>:9090/`.

---

## 🛡️ Sicherheit & Architektur
- **Base Image:** `python:3.12-alpine` (Minimaler Footprint, ~65MB Image-Größe).
- **Non-Root Execution:** Läuft unter dem isolierten Benutzer `aura` (keine Root-Rechte im Container).
- **Liveness & Readiness Endpunkte:**
  - `GET /serving`: Liveness-Probe — meldet HTTP 200, sobald der Webserver und der CORS-Proxy lauschen.
  - `GET /ready`: Marktdaten-Readiness-Probe — liefert HTTP 200 erst nach mindestens einem erfolgreichen, frischen Public-Uplink zu Bitget (vorher/bei Ausfall HTTP 503).
- **Healthcheck:** Automatischer Docker-Healthcheck prüft `/ready`.
- **Persistenz:** Autobot-, Trade- und History-State liegt im Docker-Volume `aura-state` und überlebt Container-Neuerstellungen.
- **Host-Allowlist (`AURA_ALLOWED_HOSTS`):** `/api/state` akzeptiert nur Loopback (`127.0.0.1`, `localhost`) und explizit in `AURA_ALLOWED_HOSTS` konfigurierte LAN-IP-/DNS-Hostnamen.
- **Read-only Marktdaten:** Öffentliche Bitget Marktdaten benötigen **keinen API-Key**. Es werden keine sensiblen Zugangsdaten im Container gespeichert oder übertragen.
