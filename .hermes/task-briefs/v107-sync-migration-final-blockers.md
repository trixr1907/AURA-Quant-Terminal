# AURA v1.0.7 Sync-Migration — drei Finalreview-Blocker

Workspace ausschließlich: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Befunde des unabhängigen Reviews

1. `enable_cross_device_sync_v107.sh`: Stop erfolgreich, Rename fehlgeschlagen. `RENAMED=0`, daher Trap startet gestoppten Altcontainer nicht neu.
2. `enable_cross_device_sync_v107.sh` und `repair_webhook_deployment_v107.sh`: `parse_guest_result` akzeptiert fehlendes `exitcode` als 0. `qm guest exec` ist ohne explizit sicheres synchrones Verhalten aufgerufen. PID-only JSON darf niemals als Erfolg gelten.
3. `aura_webhook_receiver.py`: `APP_DIR.replace(backup_dir)` kann gelingen und `next_dir.replace(APP_DIR)` scheitern. `source_swapped` bleibt False und Catch stellt APP_DIR nicht wieder her.

## Auftrag

Striktes TDD. Erst je Bug Regressionstest schreiben und RED ausführen, dann Minimalfix und GREEN. Ändere nur nötige Dateien im Desktop-Workspace:

- `enable_cross_device_sync_v107.sh`
- `repair_webhook_deployment_v107.sh`
- `aura_webhook_receiver.py`
- zugehörige `test_*.py`

Keine echten Remote-, Docker-, VM-, SSH- oder Git-Aktionen.

## Anforderungen

### A. Stop/Rename-Zustandsautomat

- Tracke erfolgreichen Stop separat, z. B. `OLD_STOPPED=0/1`.
- Flag unmittelbar nach erfolgreich bestätigtem `docker stop aura-terminal` setzen, vor Rename.
- Scheitert Rename, muss Fehlerhandler den originalen `aura-terminal` wieder starten und mindestens Basisvertrag v1.0.7 prüfen.
- Scheitert der Neustart oder seine Prüfung, eindeutiger eigener Rollback-Fehlercode (z. B. 91), nie Erfolg.
- Nach erfolgreichem Rename darf nicht versucht werden, den alten Namen vor Rückbenennung zu starten.
- Kandidatenfehler nach Rename: Kandidat entfernen, Rollback zurückbenennen/starten, Basic-v1.0.7 prüfen.
- Kein State-/Volume-/Image-Löschen.

### B. QEMU Guest Exec strikt synchron/fail-closed

Für beide SH-Skripte:

- `parse_guest_result` muss JSON-Objekt voraussetzen.
- `exitcode` muss vorhanden, ganzzahlig und kein Bool sein. Fehlend/ungültig/PID-only => Nichtnull.
- `out-data` und `err-data` müssen Strings sein (fehlend darf leer sein, falscher Typ => Nichtnull).
- `qm guest exec` muss nach verifizierter Proxmox-CLI-Semantik explizit synchron bis Abschluss laufen. Bevorzugt vorhandenes Proxmox-Vertragsmuster mit `--timeout 0`, sofern dokumentiert/verträglich. Keine erfundene Option. Falls `--timeout 0` nicht belastbar ist, implementiere korrektes PID/`guest exec-status`-Polling mit Timeout und finalem Exitcode.
- Ein Zwischen-/PID-Ergebnis darf nie als erfolgreicher Gastbefehl gelten.
- Parserfehler sichtbar auf stderr; kein `|| true`, kein `2>/dev/null`.
- Statische/dynamische Tests für: valides Exit 0, valides Exit !=0, fehlendes exitcode, PID-only, falsche Typen, ungültiges JSON.

### C. Receiver Source-Swap-Rollback

- Tracke getrennt, sobald `APP_DIR` erfolgreich nach `backup_dir` verschoben wurde.
- Scheitert unmittelbar danach `next_dir.replace(APP_DIR)`, muss Catch den bisherigen Source-Baum aus `backup_dir` atomar/bestmöglich auf `APP_DIR` zurückstellen.
- Auch Fehler nach komplettem Source-Swap müssen bisherigen Source-Baum wiederherstellen, wie bisher beabsichtigt.
- Restore-Fehler dürfen nicht still als erfolgreicher Rollback erscheinen; Deploymentstatus bleibt `failed`, Logs enthalten Fehler. Keine Ausnahme darf ursprüngliche Fehlerbehandlung umgehen.
- Regressionstest muss real mit temporären Verzeichnissen bzw. gezieltem Path.replace-Fehler beweisen: nach Fehler existiert APP_DIR mit alten Daten, `.previous` ist nicht der einzige verbliebene alte Baum.
- Bestehende Container-Rollbacktests bleiben grün.

## Zusätzliche Prüfung

- BAT-Bundle enthält weiterhin alle durch Scripts referenzierten Tests/Dateien.
- `python3 -m pytest -q` bzw. vollständige lokale Desktop-Test-Suite.
- `python3 -m py_compile` aller Python-Dateien.
- `bash -n` beider SH-Dateien.
- Sicherheits-Scan: kein `|| true`, kein `2>/dev/null`, kein generisches `docker inspect`, keine Volume-/Image-/State-Löschung.
- Bericht mit konkretem RED- und GREEN-Nachweis sowie geänderten Dateien.
