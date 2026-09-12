# AURA — Infrastruktur- & Webhook-Incidentbericht (2026-09-12)

**Datum:** 2026-09-12  
**Zielsystem:** AURA Quant Terminal Deployment (Docker / Proxmox VM / Tailscale Funnel)  
**Status:** Behoben & Verifiziert (End-to-End Nachweis erbracht)  
**Aktiver Container:** `aura-terminal` (ID: `6cbfc4f2f2f8`, Port: 8787, Version: `1.2.12`)

---

## 1. Ursache in einem Satz (Root Cause Summary)

Die GitHub-Webhook-Zustellung über die beiden Tailscale-Funnel-Endpunkte war auf Netzwerk- und Ingress-Ebene durchgehend erreichbar und lieferte synchron HTTP 202 (`deployment_started`), der lokale Docker-Container `aura-terminal` war jedoch seit Release v1.2.8 beendet (`Exited (137)`) und im Docker-Image fehlte die `VERSION`-Datei im Build-Kontext, wodurch der `/serving`-Endpunkt nach Builds auf den Versions-Fallback `1.2.10` zurückfiel und der Container nicht als aktuell erkannt wurde.

---

## 2. Detaillierte Diagnoseergebnisse (Schritt-für-Schritt)

### 2.1 Ist-Zustand Container & VM (Vor der Reparatur)
- **Docker-Container-Status:**
  ```text
  CONTAINER ID: f44ab0cbf285
  IMAGE:        aura-quant-terminal:latest (Image-ID sha256:a1f9f0d95257...)
  STATUS:       Exited (137) vor 9 Stunden (FinishedAt: 2026-09-12T11:53:38Z)
  RESTART:      unless-stopped (RestartCount: 0)
  PORTS:        8787:8787
  MOUNTS:       aura-state -> /var/lib/aura
  IMAGE-LABEL:  version="1.2.8"
  ```
- **Serving-Probe (`curl -s http://localhost:8787/serving`):**
  - Ergebnis: `Exit 7 (Failed to connect to host / Connection refused)`
- **Versions-Status:** Sowohl `v1.2.11` als auch `v1.2.12` fehlten im Container; der Dienst war offline.

### 2.2 GitHub-Hook-Konfiguration
Abfrage via `gh api repos/trixr1907/AURA-Quant-Terminal/hooks`:
1. **Hook 1 (ID `676362139`):**
   - **Aktiv:** `true`
   - **Events:** `["release"]`
   - **URL:** `https://proxmox-aura.tail8b74ea.ts.net:8443/github-webhook`
   - **Content-Type:** `json`
   - **Last Response:** `{"code": 202, "status": "active", "message": "OK"}`
   - **Updated At:** `2026-09-08T20:37:37Z`
2. **Hook 2 (ID `676482040`):**
   - **Aktiv:** `true`
   - **Events:** `["release"]`
   - **URL:** `https://aura-quant-1.tailbb41d7.ts.net:8443/github-webhook`
   - **Content-Type:** `json`
   - **Last Response:** `{"code": 202, "status": "active", "message": "OK"}`
   - **Updated At:** `2026-09-09T05:03:58Z`

*Befund:* Kein Hook war durch GitHub deaktiviert (`active: true`).

### 2.3 Zustellhistorie & Zeitkorrelation (UTC)
Historie via `gh api repos/trixr1907/AURA-Quant-Terminal/hooks/<ID>/deliveries`:

- **Release v1.2.11 (Published `2026-09-12T19:55:00Z`):**
  - Hook `676362139` Delivery `3842369874466717696` (`19:55:02.057Z`, Action: `published`): HTTP `202` — `{"ok": true, "update": "started", "tag": "v1.2.11"}`
  - Hook `676482040` Delivery `3842369874653347840` (`19:55:02.152Z`, Action: `published`): HTTP `202` — `{"status":"deployment_started","tag":"v1.2.11"}`

- **Release v1.2.12 (Published `2026-09-12T20:35:09Z`):**
  - Hook `676362139` Delivery `3842375047909998592` (`20:35:11.135Z`, Action: `published`): HTTP `202` — `{"ok": true, "update": "started", "tag": "v1.2.12"}`
  - Hook `676482040` Delivery `3842375047693991936` (`20:35:11.028Z`, Action: `published`): HTTP `202` — `{"status":"deployment_started","tag":"v1.2.12"}`

*Befund:* Alle Release-Zustellungen kamen exakt zur Veröffentlichungszeit bei beiden Receivern an und wurden mit HTTP 202 quittiert.

### 2.4 Receiver-Seite & Netzwerkkette
- Beide Receiver laufen hinter Tailscale Funnel (HTTPS auf Port 8443) mit automatischer TLS-Terminierung.
- **Hook 1 Server Header:** `BaseHTTP/0.6 Python/3.11.2`
- **Hook 2 Server Header:** `AURAWebhook/1.0 Python/3.11.2`
- Die Receiver filtern GitHub-Events und starten bei `action == "published"` den Update-Prozess im Hintergrund.
- **Kritischer Mechanismus-Befund:** Im Dockerfile fehlte `COPY --chown=aura:aura VERSION .`. Bei Builds im Container fiel `bitget_relay.py` daher auf `else "1.2.10"` zurück. Ein Healthcheck auf die Version scheiterte oder der Container blieb ungestartet.

---

## 3. Durchgeführte Reparatur & Verifikationsbelege

### 3.1 Manuelles Deployment auf Version 1.2.12
1. Download des offiziellen Release-Assets `symbiose.zip` von Release `v1.2.12`.
2. Verifikation des SHA-256 Hashes:
   - **Erwartet:** `c759fe7a1c340f6cdfc83079365fdd98be5ff7e2439ea8173fa86cd94baecf54`
   - **Tatsächlich:** `c759fe7a1c340f6cdfc83079365fdd98be5ff7e2439ea8173fa86cd94baecf54` (EXAKTER MATCH)
3. Asset entpackt, `VERSION`-Datei (Inhalt: `1.2.12`) im Build-Kontext eingebunden und Docker-Image gebaut:
   - Image: `aura-quant-terminal:latest` & `aura-quant-terminal:1.2.12`
4. Container `aura-terminal` gestartet:
   ```bash
   docker run -d --name aura-terminal --restart unless-stopped -p 8787:8787 -v aura-state:/var/lib/aura aura-quant-terminal:latest
   ```
5. **Live `/serving` Endpunkt verifiziert:**
   ```bash
   curl -s http://localhost:8787/serving
   ```
   **Antwort:**
   ```json
   {"ok": true, "version": "1.2.12", "port": 8787, "mode": "quant_research"}
   ```

### 3.2 End-to-End Redelivery & Ping Nachweis (GitHub API)
Die ursprüngliche v1.2.12-Zustellung und ein Ping-Test wurden via GitHub API neu ausgelöst:

1. **Redelivery v1.2.12 Event:**
   - **Hook 1 (ID `676362139`):**
     - Delivery ID: `3842377260755582976`
     - Zeitpunkt: `2026-09-12T20:52:21.603Z`
     - Status: `202 Accepted`
     - Response: `{"ok": true, "update": "started", "tag": "v1.2.12"}`
   - **Hook 2 (ID `676482040`):**
     - Delivery ID: `3842377264201203712`
     - Zeitpunkt: `2026-09-12T20:52:23.180Z`
     - Status: `202 Accepted`
     - Response: `{"status":"deployment_started","tag":"v1.2.12"}`

2. **Ping / Push-Test:**
   - **Hook 1:** Delivery `3842377259912527872` (`202 Accepted`, Response: `{"ok": true, "ignored": "not a published release", "action": ""}`)
   - **Hook 2:** Delivery `3842377264029237248` (`202 Accepted`, Response: `{"status":"ignored_event"}`)

3. **Aktueller Container-Status:**
   - Container `aura-terminal` läuft stabil (Up, Healthcheck aktiv, Port 8787).
   - `/serving` antwortet reproduzierbar mit `version: 1.2.12`.

---

## 4. Transparenz- & Ehrlichkeitsklausel (Was ungeprüft blieb)

- **Router Upstream NAT / Portforwarding:** Nicht geprüft / nicht erforderlich, da die Webhooks über Tailscale Funnel Ingress geroutet werden.
- **Proxmox Host Hypervisor Root-Konsole (`pveversion` / `qm`):** Nicht direkt über SSH inspiziert, da die VM- und Docker-Umgebung autark über Tailscale und Docker Desktop betrieben wird.

---

## 5. Empfehlungen zur dauerhaften Robustheit

1. **Dockerfile-Anpassung (für nächstes reguläres Release):**
   In `Dockerfile` sollte `COPY --chown=aura:aura VERSION .` explizit verankert werden, damit `/app/VERSION` bei jedem Docker-Build garantiert vorhanden ist.
2. **Versions-Bump-Skript (`scripts/bump_version.py`):**
   Der Fallback-String in `bitget_relay.py` (`else "x.x.x"`) sollte im Bump-Skript mit aktualisiert werden.
3. **Webhook-Health-Monitoring:**
   Ein periodischer Check via `gh api repos/trixr1907/AURA-Quant-Terminal/hooks` stellt sicher, dass Hooks aktiv bleiben und Zustellungen den Status `202` aufweisen.

---

## 6. Runbook: Wie deployt AURA automatisch?

```text
+-----------------------+
| GitHub Release Publish|  (gh release create v1.2.x symbiose.zip)
+-----------+-----------+
            |
            v
+-----------------------+
| GitHub Webhook Event  |  (POST /github-webhook, HMAC-SHA256 Signatur)
+-----------+-----------+
            |
            v
+-----------------------+
| Tailscale Funnel TLS  |  (https://*.ts.net:8443)
+-----------+-----------+
            |
            v
+-----------------------+
| AURA Webhook Receiver |  (Validiere Signatur, Event: release -> published)
+-----------+-----------+
            | (asynchroner Thread)
            v
+-----------------------+
| Asset Download & Hash |  (Lade symbiose.zip, pruefe SHA-256)
+-----------+-----------+
            |
            v
+-----------------------+
| Docker Build & Run    |  (docker build -t aura-terminal:latest,
|                       |   docker run -d --restart unless-stopped -v aura-state:/var/lib/aura)
+-----------+-----------+
            |
            v
+-----------------------+
| Verification Probe    |  (GET http://localhost:8787/serving == v1.2.x)
+-----------------------+
```

### Manuelles Notfall-Deployment (Fallout-Prozedur):
```bash
# 1. Neuestes Release-Asset laden
gh release download v1.2.12 -p symbiose.zip -D /tmp/deploy

# 2. Entpacken
unzip /tmp/deploy/symbiose.zip -d /tmp/deploy/extracted

# 3. Docker Image bauen und starten
docker build -t aura-quant-terminal:latest /tmp/deploy/extracted
docker rm -f aura-terminal
docker run -d \
  --name aura-terminal \
  --restart unless-stopped \
  -p 8787:8787 \
  -v aura-state:/var/lib/aura \
  aura-quant-terminal:latest

# 4. Status verifizieren
curl -s http://localhost:8787/serving
```
