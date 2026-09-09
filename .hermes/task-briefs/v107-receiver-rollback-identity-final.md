# AURA v1.0.7 — Receiver-Rollback über Containeridentität beweisen

Workspace ausschließlich: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Scope-Entscheidung

Der aktive Live-Pfad ist ausschließlich:

- `ENABLE_CROSS_DEVICE_SYNC_V107.bat`
- `enable_cross_device_sync_v107.sh`
- `aura_webhook_receiver.py`
- deren direkt übertragene Tests

`setup_webhook.sh`, `FIX_AND_ENABLE_WEBHOOK.bat`, `rebuild_tailscale.sh` und `REBUILD_TAILSCALE.bat` werden vom Migrations-BAT weder übertragen noch aufgerufen. Sie sind Alt-/Installationswerkzeuge und kein Blocker für diese einmalige Live-Migration. Nicht ändern.

## Relevante Review-Blocker

1. `aura_webhook_receiver.py`: Reconciliation beweist nur `Running`, nicht dass wirklich der ursprüngliche Container zurückkam.
2. Verlorene Antwort beim Rück-Rename kann die Funktion vor `docker start` abbrechen, obwohl Rename bereits wirkte.

## Auftrag

Striktes TDD. Ändere ausschließlich:

- `aura_webhook_receiver.py`
- `test_aura_webhook_receiver.py`

Keine echten Remote-, Docker-, VM-, SSH- oder Git-Aktionen.

## Zielarchitektur

Nutze die vor Deployment erfasste `old_config` als unveränderlichen Identitäts-/Vertragsbeleg für Rollback.

### A. Expected-old-config an Reconciliation übergeben

- `reconcile_container_state(..., expected_old_config=old_config)`.
- Der erwartete alte Container braucht eine nichtleere eindeutige Docker-`Id`. Fehlt sie, vor jeder Deployment-Mutation fail-closed abbrechen oder Reconciliation als nicht beweisbar ablehnen.
- Nach Wiederherstellung und Start: aktuelles `docker container inspect aura-terminal` lesen und mindestens beweisen:
  - `Id` exakt gleich erwarteter alter `Id`
  - `State.Running is True`
  - `State.OOMKilled` nicht True
  - `State.Error` leer
  - `Config.Image` gleich alt
  - `HostConfig.PortBindings` gleich alt
  - Mount-Vertrag gleich alt für Typ, Source/Name, Destination und RW
  - relevante Config-Env des alten Containers unverändert (normalisierte Liste/Multiset)
  - RestartPolicy gleich alt
- Warum: identische ID beweist bereits denselben Container; Vertragsvergleich liefert klare Diagnose und schützt Tests/Mocks vor falschen Positiven.

### B. Rück-Rename mit verlorener Antwort reconciliieren

Wenn Rollbackname vorhanden:

1. Versuch `docker rename rollback_name aura-terminal`.
2. Falls Befehl wirft/unklar ist, danach tri-state beide Namen prüfen.
3. Nur wenn `rollback_name` sicher absent UND `aura-terminal` sicher present, darf als bereits wirksam fortgefahren werden.
4. Sonst Reconciliation fail-closed abbrechen.
5. Danach `docker start aura-terminal` versuchen. Falls Start wirft/Antwort verloren, trotzdem finalen Inspect durchführen; nur exakte alte ID + laufender Vertrag darf Erfolg ergeben.

Auch bei normalem Rename/Start immer finale Identitäts-/Vertragsprüfung.

### C. Candidate-Removal beibehalten

Bestehende Logik für sicher absent/present/unknown behalten. Danach alten Container wiederherstellen. Keine blinden `check=False`-Ketten.

## RED-Tests

Mindestens:

1. Laufender Container mit anderer ID wird abgelehnt.
2. Gleiche ID, aber falsches Image/Port/Mount/Env/RestartPolicy wird jeweils oder parametrisiert abgelehnt.
3. Rück-Rename wirkt, wirft danach; Re-Probe zeigt Rollback absent/original present; Start wird erreicht und exakte alte ID bestätigt → Erfolg.
4. Rück-Rename wirft und beide Namen unentscheidbar/unerwartet → kein Erfolg.
5. Start wirkt, wirft danach; finaler Inspect zeigt exakte alte ID laufend → Erfolg.
6. Deployment übergibt `old_config` an Reconciliation.
7. Vorhandene Tests bleiben grün.

## Verifikation

- vollständige Desktop-Test-Suite
- `python3 -m py_compile *.py`
- `bash -n enable_cross_device_sync_v107.sh repair_webhook_deployment_v107.sh`
- keine Änderungen an Alt-Setup-/Tailscale-Skripten
- Bericht mit beobachtetem RED/GREEN und geänderten Dateien
