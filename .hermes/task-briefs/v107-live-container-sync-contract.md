# AURA v1.0.7 — Container-Vertrag für LAN-State-Sync migrieren

Workspace Betriebsdateien: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Belegte Live-Lage

- v1.0.7 ist nach Webhook-Redelivery live: `/serving` HTTP 200, Version 1.0.7.
- `/api/state` mit realem LAN-Host `192.168.8.115:8787` liefert weiterhin HTTP 403 `ERR_FORBIDDEN_HOST`.
- Derselbe Endpunkt mit Host `localhost:8787` oder `127.0.0.1:8787` liefert HTTP 200.
- Root Cause: Der Webhook-Receiver reproduziert beim Update die alte v1.0.6-Container-Env. Diese enthielt nur `SYM_HOST`/`SYM_PORT`, aber nicht:
  - `AURA_ALLOWED_HOSTS=192.168.8.115`
  - `AURA_STATE_DIR=/var/lib/aura`
- Volume `aura-state:/var/lib/aura` ist vorhanden, wird ohne `AURA_STATE_DIR` aber nicht als serverseitiger State-Pfad genutzt.

## Auftrag

Striktes TDD. Ändere nur Desktop-Betriebsdateien. Keine echten Docker-/VM-/Remote-Aktionen. Keine Repo-Commits/Tags/Pushes/Releases. Keine Secrets lesen/ausgeben.

### 1. Receiver-Vertrag migrieren

Datei `aura_webhook_receiver.py`:

- Neue konfigurierbare Deployment-Werte, getrennt von Receiver-Netzwerk:
  - `AURA_DEPLOY_ALLOWED_HOSTS`, Default `192.168.8.115`
  - `AURA_DEPLOY_STATE_DIR`, Default `/var/lib/aura`
- `recreate_arguments()` muss aus geerbter Env alte Einträge für `AURA_ALLOWED_HOSTS` und `AURA_STATE_DIR` entfernen und exakt je einen aktuellen Eintrag anhängen.
- Unabhängig davon, ob Altcontainer diese Werte nicht, falsch oder mehrfach hatte.
- Andere Env-Werte erhalten.
- Volume/Port/Restart-Vertrag weiter erhalten.

Tests in `test_aura_webhook_receiver.py` zuerst rot:

- fehlende Sync-Env wird ergänzt;
- stale/duplizierte Sync-Env wird auf exakt je einen aktuellen Wert normalisiert;
- unrelated Env bleibt erhalten.

### 2. Einmalige Live-Migration als fail-closed BAT/SH

Erstelle:

- `enable_cross_device_sync_v107.sh`
- `ENABLE_CROSS_DEVICE_SYNC_V107.bat`
- `test_enable_cross_device_sync_static.py`

BAT-Muster wie bestehende Dateien:

- Proxmox-IP/User abfragen;
- SH, Receiver und beide Receiver-/Migrations-Tests übertragen;
- Recovery auf VM 201 starten;
- kritische Fehler sichtbar, kein `|| true`, kein `2>/dev/null`.

SH auf Proxmox/VM 201:

1. VMID exakt 201, QEMU-Agent prüfen.
2. Lokale Tests + py_compile + bash syntax vor Remote-Mutation.
3. Gefixten Receiver per bewährtem Base64-Chunk-Transfer temporär in VM übertragen, py_compile, atomar nach `/opt/aura_webhook_receiver.py` installieren, Rechte 0755, Receiver neu starten und GET-Health prüfen.
4. Vor Containeränderung fail-closed prüfen:
   - `docker container inspect aura-terminal` existiert;
   - aktuelle lokale `/serving` meldet exakt v1.0.7;
   - `docker image inspect aura-quant-terminal:1.0.7` existiert;
   - `docker volume inspect aura-state` existiert;
   - aktueller Container ist running + healthy;
   - Portvertrag enthält HostPort 8787;
   - Mountvertrag enthält `aura-state` nach `/var/lib/aura`, RW.
5. Bereits korrekter Containervertrag: keine Recreation, nur Prüfungen.
6. Bei falscher/fehlender Sync-Env:
   - sicherstellen, dass kein `aura-terminal-sync-rollback` existiert; sonst hart abbrechen;
   - `aura-terminal` stoppen;
   - in `aura-terminal-sync-rollback` umbenennen;
   - neuen `aura-terminal` starten mit exakt:
     - `--restart unless-stopped`
     - `-e SYM_HOST=0.0.0.0`
     - `-e SYM_PORT=8787`
     - `-e AURA_ALLOWED_HOSTS=192.168.8.115`
     - `-e AURA_STATE_DIR=/var/lib/aura`
     - `-p 8787:8787`
     - `-v aura-state:/var/lib/aura`
     - Image `aura-quant-terminal:1.0.7`
7. Bis 90 Sekunden prüfen:
   - Docker `running` + `healthy`;
   - `/serving` ok + v1.0.7;
   - `GET /api/state` mit `Host: 192.168.8.115:8787` HTTP 200 und JSON `{ok:true,data:object}`; State-Inhalte nie ausgeben.
8. Erfolg: Rollback-Container entfernen, aber niemals Volume/Image; kompakten Vertrag ausgeben, keine State-Inhalte.
9. Fehler nach Rename: Candidate entfernen, Rollback zurückbenennen/starten, dessen v1.0.7-Health prüfen; Exit ungleich 0.
10. Fehler vor Rename: Altcontainer unverändert lassen.

### 3. Statische Tests

Mindestens:

- nur `docker container inspect` für Container;
- Vorbedingungen kommen vor Stop/Rename;
- Image+Volume+Port+RW-Mount geprüft;
- neue Run-Args exakt vorhanden;
- API-State-LAN-Host wird geprüft;
- Rollback-Aktionen vorhanden und zustandsbasiert;
- kein State-Inhalt ausgegeben;
- kein `docker volume rm`, kein `docker image rm`, kein generisches `docker inspect`, kein `|| true`, kein `2>/dev/null`.

## Verifikation

- alle Desktop-Tests
- py_compile
- bash -n für Recovery und neues SH
- BAT statisch vollständig
- Bericht mit summary/files_changed/red_tests/green_tests/unverified.
