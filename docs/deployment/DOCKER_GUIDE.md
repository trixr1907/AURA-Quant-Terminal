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

---

## 🔔 Push-Benachrichtigungen via ntfy (opt-in, v1.4.0+)

AURA kann dich per [ntfy](https://ntfy.sh) benachrichtigen, wenn ein Trade geschlossen wird.
Die Funktion ist **standardmäßig deaktiviert** — kein Traffic ohne Konfiguration.

### Schnellstart

1. Erstelle einen kostenlosen ntfy-Topic (z.B. auf `ntfy.sh` oder selfhosted):
   ```
   https://ntfy.sh/mein-aura-alerts-xyz
   ```
2. Setze die Umgebungsvariable `AURA_NTFY_URL` auf diese URL.

### Docker CLI
```bash
docker run -d --name aura-terminal \
  -p 8787:8787 \
  -e AURA_ALLOWED_HOSTS=<HOST-IP> \
  -e AURA_STATE_DIR=/var/lib/aura \
  -e AURA_NTFY_URL=http://ntfy.sh/mein-aura-alerts-xyz \
  -v aura-state:/var/lib/aura \
  aura-quant-terminal:latest
```

### Docker Compose `.env`
```env
AURA_PORT=8787
AURA_ALLOWED_HOSTS=192.168.8.115
AURA_NTFY_URL=http://ntfy.sh/mein-aura-alerts-xyz
```

Und in `docker-compose.yml` unter `environment` ergänzen:
```yaml
- AURA_NTFY_URL=${AURA_NTFY_URL:-}
```

### Selfhosted ntfy

```bash
docker run -d --name ntfy -p 8080:80 \
  -v ntfy-data:/var/cache/ntfy \
  binwiederhier/ntfy serve
```

Dann `AURA_NTFY_URL=http://<SERVER-IP>:8080/mein-topic`.

### Sicherheitshinweise

- `AURA_NTFY_URL` wird **nur ausgewertet**, wenn sie auf `http://` oder `https://` beginnt. `file://` und andere Schemas werden stillschweigend ignoriert.
- Die Benachrichtigung läuft auf einem Daemon-Thread (fire-and-forget). HTTP-Fehler oder Verbindungsprobleme blockieren **nie** den Relay-Betrieb.
- Benachrichtigungen enthalten keine API-Keys, keine Passwörter und keine sensitiven Kontodetails — nur Symbol, Trade-ID, Seite (Long/Short) und PnL.
- Nutze einen **zufälligen, unguessable Topic-Namen**, um unbefugten Zugriff auf deine Benachrichtigungen zu vermeiden.

---

## Datenhaltung v2: Upgrade und Downgrade

AURA v2.0.0 migriert den persistenten Laufzeit-State beim Relay-Start automatisch und vor Freigabe des Headless Runners. Der persistente Pfad bleibt `/var/lib/aura`; dadurch bleibt der read-only Rootfs kompatibel.

Vor dem Deploy prüfen:

```bash
python3 scripts/ops/aura_state_migrate.py --state-dir /var/lib/aura --dry-run
```

Nach dem Deploy prüfen:

```bash
curl -fsS http://127.0.0.1:8787/ready
ls -l /var/lib/aura/aura_shared_state.json.v1-backup-*
```

Erwartet werden `schema_version: 2` und genau ein neues, zeitgestempeltes v1-Backup. `shadow_log.jsonl` ist nicht Teil der Migration.

Downgrade auf das letzte v1.x-Image:

1. Container stoppen, damit kein Schreiber aktiv ist.
2. Rollback zunächst ohne Schreibzugriff prüfen:
   `python3 scripts/ops/aura_state_migrate.py --state-dir /var/lib/aura --rollback`
3. Backup wiederherstellen:
   `python3 scripts/ops/aura_state_migrate.py --state-dir /var/lib/aura --rollback --yes`
4. Das weiterhin lokal vorgehaltene letzte v1.x-Image starten.
5. `/ready`, Runner-Zyklen und State-Revision prüfen.

Ohne `--yes` überschreibt der Rollback nichts. Bei Schema >2 beendet sich der v2-Relay fail-closed und empfiehlt Image-Rollback oder Backup-Restore.

---

## 🔄 Frischinstallation: Receiver einrichten (Automatischer GitHub Deploy-Receiver)

Für Server, Proxmox-VMs und VPS-Instanzen steht mit `scripts/ops/aura_webhook_receiver.reference.py` eine kanonische Referenz-Implementierung des Deploy-Receivers bereit.

Der Receiver empfängt GitHub Release-Webhooks, validiert die kryptografische HMAC-SHA256 Signatur, lädt das offizielle `symbiose.zip` Release-Asset herunter, baut das gehärtete Image und startet bzw. aktualisiert den Container automatisch.

### Eigenschaften & Sicherheitsmodell
- **Clean-Slate Bootstrap:** Existiert noch kein `aura-terminal` Container auf dem Zielsystem (Frischinstallation), erzeugt der Receiver den Container vollautomatisch aus der kanonischen Compose-Spezifikation (`--restart unless-stopped`, `--read-only`, `--security-opt no-new-privileges:true`, `--cap-drop ALL`, tmpfs `/tmp`, Port 8787, Volume `aura-state`, `--env-file /var/lib/aura/aura_bot.env` falls vorhanden).
- **Rollback-Schutz:** Bei existierenden Containern wird vor dem Update ein Backup-Container (`aura-terminal-rollback`) vorgehalten. Schlägt Build oder `/serving` Health-Check fehl, wird der vorherige Zustand atomar wiederhergestellt.
- **Push-Benachrichtigungen:** Bei gesetzter `AURA_NTFY_URL` sendet der Receiver Erfolgsmeldungen (P3) und Fehleralarme (P4) direkt aufs Smartphone.
- **Keine Secrets im Code:** Alle Parameter werden über systemd Environment / Drop-ins konfiguriert.

### 1. Referenz-Datei installieren

Auf dem Zielserver (als Root bzw. via `sudo`):

```bash
sudo cp scripts/ops/aura_webhook_receiver.reference.py /opt/aura_webhook_receiver.py
sudo chmod 0755 /opt/aura_webhook_receiver.py
```

### 2. systemd-Service einrichten

Erstelle `/etc/systemd/system/aura-webhook.service`:

```ini
[Unit]
Description=AURA GitHub Webhook Release Deploy Receiver
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt
ExecStart=/usr/bin/python3 /opt/aura_webhook_receiver.py
Restart=always
RestartSec=5
EnvironmentFile=-/etc/default/aura-webhook

# Sicherheitshärtung
LimitNOFILE=65536
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### 3. Konfiguration anlegen

Erstelle `/etc/default/aura-webhook` mit mindestens 32 Zeichen Secret:

```env
AURA_WEBHOOK_PORT=8443
AURA_WEBHOOK_SECRET=HIER_MINDESTENS_32_ZEICHEN_LANGES_GEHEIMES_TOKEN
AURA_WEBHOOK_REPOSITORY=trixr1907/AURA-Quant-Terminal
AURA_APP_DIR=/opt/aura
AURA_CONTAINER_NAME=aura-terminal
AURA_IMAGE_REPOSITORY=aura-quant-terminal
AURA_ALLOWED_HOSTS=127.0.0.1,192.168.8.115
AURA_NTFY_URL=https://ntfy.sh/<DEIN-GEHEIMER-TOPIC>
```

Dienst aktivieren und starten:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aura-webhook.service
```

Status und Liveness prüfen:

```bash
sudo systemctl status aura-webhook.service
curl -s http://127.0.0.1:8443/
# Antwort: {"ok": true, "service": "aura-webhook-receiver"}
```

### 4. GitHub Webhook konfigurieren

Im GitHub Repository unter **Settings → Webhooks → Add webhook**:
- **Payload URL:** `https://<DEINE-DOMAIN-ODER-IP>:8443/github-webhook`
- **Content type:** `application/json`
- **Secret:** Das in `/etc/default/aura-webhook` konfigurierte `AURA_WEBHOOK_SECRET`
- **Which events would you like to trigger this webhook?** `Let me select individual events` → **Releases** auswählen.
- **Active:** ✅

Sobald ein Release veröffentlicht wird, baut der Receiver das Release vollautomatisch und bootet das Terminal schlüsselfertig.
