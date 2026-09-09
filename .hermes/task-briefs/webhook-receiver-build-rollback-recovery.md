# AURA Webhook-Receiver — Docker-Config und Rollback-Recovery

Workspace: `/home/ivo/projects/AURA_Quant_Terminal`
Externe Betriebsdateien: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Belegte Produktionsfehler

Webhook `published` für v1.0.7 wurde angenommen und startete Deployment. VM-Status:

- `docker build -t aura-quant-terminal:1.0.7 /opt/aura.next` schlug fehl.
- Exakte Docker-Ausgabe: `ERROR: mkdir /root/.docker: read-only file system`.
- systemd-Service nutzt `ProtectHome=true`, `ProtectSystem=full`; `/var/lib/aura-webhook` ist per `StateDirectory` und `ReadWritePaths` beschreibbar.
- Receiver-Exception-Handler führte danach unconditional `docker rm -f aura-terminal` aus, obwohl der Fehler VOR `docker stop`/`docker rename` passierte.
- Dadurch wurde der gesunde v1.0.6-Container gelöscht. Kein `aura-terminal`, kein Rollback-Container, Port 8787 ist down.
- Alte Image-/Runtime-Fakten aus Diagnose:
  - Originalcontainer-Image: `aura-terminal:latest`
  - Port: `8787:8787`
  - Volume: `aura-state:/var/lib/aura`
  - Restart: `unless-stopped`
  - Env: `SYM_HOST=0.0.0.0`, `SYM_PORT=8787`
  - Original war healthy v1.0.6.
- `/opt/aura` ist v1.0.6, `/opt/aura.next` ist v1.0.7.

## Auftrag

Striktes TDD: Regressionstests zuerst schreiben und rot ausführen. Danach minimal fixen.

### 1. Receiver gegen schreibgeschütztes HOME absichern

Datei: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/aura_webhook_receiver.py`

- Docker CLI muss einen expliziten beschreibbaren `DOCKER_CONFIG` unterhalb von `STATUS_DIR` verwenden, z. B. `/var/lib/aura-webhook/docker-config`.
- Verzeichnis mit restriktiven Rechten erstellen, bevor Docker-Befehle laufen.
- Nicht `/root/.docker` verwenden.
- Lösung muss auch nach Service-Neustart wirken.

### 2. Rollback-Logik korrekt zustandsbasiert machen

- Ein Fehler vor Stop/Rename des Altcontainers darf `aura-terminal` niemals entfernen, stoppen oder umbenennen.
- Nur wenn der Altcontainer erfolgreich nach `aura-terminal-rollback` umbenannt wurde, darf ein möglicher neuer `aura-terminal` entfernt und der Rollback-Container zurückbenannt/gestartet werden.
- Flags sollen tatsächliche Zustandsübergänge abbilden (`old_renamed`, ggf. `candidate_started`), nicht nur Absichten.
- Fehlerstatus bleibt fail-closed.
- Bestehende State-Volume-Konfiguration bleibt erhalten.

### 3. Automatisierte Regressionstests

Neue lokale Testdatei unter `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`, z. B. `test_aura_webhook_receiver.py`.

Mindestens:

- importierter Receiver setzt `DOCKER_CONFIG` unter `STATUS_DIR`, Verzeichnis wird erstellt.
- simuliertes `docker build` scheitert vor Stop/Rename: Befehlsprotokoll enthält KEIN `docker rm -f aura-terminal`, KEIN `docker stop aura-terminal`, KEIN Rename.
- Fehler nach erfolgreichem Rename: Candidate wird entfernt, Rollback zurückbenannt und gestartet.
- `write_status("failed", ...)` bleibt erhalten.
- Tests dürfen keine echten Docker-/VM-Aktionen ausführen.

### 4. Recovery-Skriptpaar erstellen

Erstelle:

- `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/repair_webhook_deployment_v107.sh`
- `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/REPAIR_WEBHOOK_DEPLOYMENT_V107.bat`

BAT:

- fragt Proxmox-IP/User wie bestehende BATs ab.
- überträgt Shell-Skript, gefixten Receiver und Tests nach `/root/aura_webhook/`.
- führt Shell-Skript für VM 201 aus.
- jeder kritische Schritt fail-closed; kein `|| true`, keine Fehlerunterdrückung.

Shell-Skript auf Proxmox:

1. QEMU-Agent prüfen.
2. Lokale Receiver-Tests ausführen, bevor etwas installiert wird.
3. Gefixten Receiver per bewährtem Base64-Chunk-Verfahren in VM nach temporärem Pfad übertragen.
4. In VM `python3 -m py_compile` auf temporärer Datei.
5. Temporäre Datei atomar nach `/opt/aura_webhook_receiver.py` verschieben, Rechte 0755.
6. `/var/lib/aura-webhook/docker-config` mit sicheren Rechten erstellen.
7. `systemctl restart aura-webhook.service`, active + lokaler GET-Healthcheck prüfen.
8. Falls `aura-terminal` fehlt, v1.0.6 aus `aura-terminal:latest` mit exakt folgendem Vertrag wiederherstellen:
   - `--restart unless-stopped`
   - `-e SYM_HOST=0.0.0.0`
   - `-e SYM_PORT=8787`
   - `-p 8787:8787`
   - `-v aura-state:/var/lib/aura`
   - Image `aura-terminal:latest`
9. Falls Container bereits existiert, nicht verändern.
10. Bis zu 90 Sekunden `/serving` abfragen; `ok=true`, Version `1.0.6` oder `1.0.7`, Docker health healthy verlangen.
11. Abschließend Status, Version, Port und Volume-Namen ohne State-Inhalte ausgeben.
12. Keine Webhook-Redelivery auslösen; das erledigt Parent nach erfolgreicher Recovery.

Wichtig:

- Keine Secrets lesen oder ausgeben.
- State-Datei/Volume nie löschen oder deren Inhalte ausgeben.
- Keine Repo-Commits/Tags/Pushes/Releases.
- Änderungen nur in den genannten Desktop-Betriebsdateien und Testdatei.

## Verifikation

- `python3 -m unittest .../test_aura_webhook_receiver.py -v`
- `python3 -m py_compile .../aura_webhook_receiver.py .../test_aura_webhook_receiver.py`
- `bash -n .../repair_webhook_deployment_v107.sh`
- statische Prüfung des BAT/Shell-Vertrags
- Bericht mit `summary`, `files_changed`, `red_tests`, `green_tests`, `unverified`.
