# AURA v1.0.7 — Shell-Reconciliation an Receiver-Parität bringen

Workspace ausschließlich: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Enger aktiver Scope

- `ENABLE_CROSS_DEVICE_SYNC_V107.bat`
- `enable_cross_device_sync_v107.sh`
- `test_enable_cross_device_sync_static.py`

Andere Dateien nur lesen, nicht ändern. Keine Remote-/Docker-/VM-/SSH-/Git-Aktionen.

## Finalreview-Befunde

1. `reconcile_after_attempts` behandelt verlorene Antworten von Candidate-RM, Rück-Rename und Start nicht anhand des belegten Endzustands. Es setzt `reconcile_rc=1` sofort oder fährt mit unbewiesener Namenswelt fort.
2. `guest_container_contract`/No-op-Pfad beweist nicht, dass `aura-terminal` exakt Image `aura-quant-terminal:1.0.7` nutzt.

## Auftrag

Striktes TDD. Je Fehlerklasse Regressionstest zuerst, beobachtetes RED, dann Minimalfix, GREEN.

### A. Eindeutiger v1.0.7-Basisvertrag

`guest_container_contract(name)` muss zusätzlich fordern:

- `.Config.Image == "aura-quant-terminal:1.0.7"`

Damit müssen sowohl Migrationskandidat als auch No-op-Pfad die Image-Identität beweisen. `/serving == 1.0.7` bleibt zusätzliche Prüfung.

Achtung Rollback: Der alte Container im aktuellen Live-Zustand wurde ebenfalls aus `aura-quant-terminal:1.0.7` gestartet; daher ist dieser Basisvertrag passend. Falls Tests eine andere Annahme zeigen, keinen Vertrag aufweichen, sondern explizite Expected-Image-Verifikation entwerfen.

Tests:

- `/serving` v1.0.7 + falsches `.Config.Image` => Basisvertrag scheitert.
- exaktes Image + bestehende Port/Volume/Health-Bedingungen => Erfolg.
- No-op-Pfad kann mit falschem Image keinen Erfolg melden.

### B. Zustandsbasierte Shell-Reconciliation

Baue `reconcile_after_attempts` analog zur inzwischen gehärteten Python-Receiver-Logik. Jede verlorene Antwort wird durch Präsenz- und Endvertragsprüfung entschieden.

#### Candidate-RM

Wenn `CANDIDATE_RUN_ATTEMPTED=1`:

1. Präsenz von `aura-terminal` tri-state prüfen.
2. present: `docker rm -f aura-terminal` versuchen.
3. Wirft/antwortet unklar: erneut Präsenz prüfen.
4. Nur sicher absent gilt als erfolgreich entfernt.
5. Noch present oder unknown => Reconciliation fehlschlägt; kein blindes Weiterarbeiten mit Namenskollision.
6. Bereits absent => normal fortfahren.

#### Rück-Rename

Wenn `RENAME_ATTEMPTED=1`:

1. Rollbackname und Originalname tri-state prüfen.
2. Sichere Welten:
   - Rollback present, Original absent: Rename versuchen.
   - Rollback absent, Original present: Rename war bereits wirksam; weiter.
3. Nach Rename-Fehler erneut beide Namen prüfen. Nur Rollback absent + Original present erlaubt Fortsetzung.
4. Beide present, beide absent oder unknown => Fail-closed.

#### Start

1. `docker start aura-terminal` versuchen.
2. Verlorene/fehlerhafte Antwort nicht sofort als endgültiger Fehler klassifizieren.
3. Abschließend `verify_basic_v107 aura-terminal` ausführen.
4. Nur vollständig bestandener Basisvertrag darf die Reconciliation als erfolgreich bewerten.
5. Scheitert Basisvertrag => Exit 91.

#### Exitcode

- Erfolgreich bewiesene Wiederherstellung gibt ursprünglichen Fehlercode zurück, nicht 91.
- Nicht beweisbare Wiederherstellung endet 91.
- Keine State-/Volume-/Image-Löschung.

### C. Dynamische Tests

Mindestens folgende realistische Shell-Harnesses:

1. Candidate-RM wirkt, Antwort verloren; Re-Probe absent; Rück-Rename/Start + Basisvertrag erfolgreich → ursprünglicher Fehlercode.
2. Candidate-RM wirkt nicht und Antwort fehlerhaft; Re-Probe present → 91; kein Rename-Versuch.
3. Rück-Rename wirkt, Antwort verloren; Re-Probe rollback absent/original present; Start + Basis erfolgreich → ursprünglicher Fehlercode.
4. Rück-Rename wirkt nicht; Re-Probe rollback present/original absent → 91.
5. Start wirkt, Antwort verloren; Basisvertrag erfolgreich → ursprünglicher Fehlercode.
6. Start wirkt nicht; Basisvertrag scheitert → 91.
7. Unentscheidbare Präsenz an jeder kritischen Stelle → 91.
8. Keine parallelen Kandidat-/Rollback-Welten werden als Erfolg akzeptiert.

## Verifikation

- vollständige Desktop-Pytest-Suite
- `python3 -m py_compile *.py`
- `bash -n enable_cross_device_sync_v107.sh`
- kein `|| true`, kein `2>/dev/null`, kein generisches `docker inspect`
- Bericht mit konkretem RED/GREEN und geänderten Dateien
