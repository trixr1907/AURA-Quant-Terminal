# AURA v1.0.7 — Reconciliation- und Commit-Korrektheit

Workspace ausschließlich: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Parent-Review nach Zustandsautomaten-Redesign

36 Tests sind grün, aber konkrete P1-Lücken bleiben. Das ist eine Korrektur des neuen Reconciliation Leahs, kein weiterer Feature-Scope.

### 1. Doppelte Funktion

`enable_cross_device_sync_v107.sh` definiert `guest_container_presence()` zweimal. Nur eine Definition behalten; Tests dürfen nicht durch versehentliches Überschreiben einer früheren Implementierung grün sein.

### 2. Recovery erkennt sichere Abwesenheit nicht

`repair_webhook_deployment_v107.sh:68-80` ruft direkt `docker container inspect` auf und erwartet Gast-Exitcode 10 für „sicher abwesend“. Docker liefert bei fehlendem Container aber regulär Exit 1. Es gibt keine Übersetzung auf 10. Ergebnis: echte Abwesenheit wird immer als unentscheidbar klassifiziert; Notfall-Recovery ist unerreichbar.

Implementiere einen Gastbefehl, der Docker-Infrastrukturfehler von sicherer Abwesenheit unterscheidet, bevorzugt über erfolgreiches `docker container ls -a --format '{{.Names}}' --filter exact-name` und kontrollierte Exitcodes 0/10. Exakte Namensprüfung. Docker-Befehlsfehler bleiben original Nicht-0/10 und damit unentscheidbar.

### 3. Migration: mehrdeutiges finales Rollback-Cleanup kann Kandidat zerstören

`enable_cross_device_sync_v107.sh` entfernt nach verifiziertem Kandidaten den Rollback noch mit aktiven Attempt-Flags. Wenn `docker rm '$ROLLBACK_NAME'` real gelingt, aber QEMU-Antwort verloren geht, feuert ERR-Reconciliation:

- möglicher Kandidat `aura-terminal` wird entfernt,
- Rollback ist real schon weg,
- alter Dienst kann nicht wiederhergestellt werden,
- Outage.

Korrigiere Commit-Grenze:

- Nach vollständig bestandenem `verify_live_sync_contract` ist der Kandidat committed.
- Setze Rollback-Attemptflags vor Cleanup so, dass ein Cleanup-Fehler niemals Kandidaten-Reconciliation auslöst.
- Rollback-Container-Cleanup ist danach best effort im Sinne „Fehler sichtbar, Kandidat bleibt“; kein `|| true` und keine Unterdrückung. Bei Fehler: eindeutige Warnung/Nichtnull oder sauberer Cleanup-Warning-Pfad, aber Kandidat nie stoppen/löschen.
- Eine verlorene Antwort nach tatsächlich erfolgreichem Rollback-RM muss Kandidat laufend lassen.
- Eine verlorene Antwort ohne tatsächliches RM darf Kandidat ebenfalls laufend lassen und alten gestoppten Rollback behalten.
- Dynamischer Harness-Test für beide Welten.

### 4. Receiver-Reconcile bricht bei fehlendem Kandidaten zu früh ab

`aura_webhook_receiver.py:140-151` macht bei `candidate_start_attempted` blind `docker rm -f aura-terminal` mit `check=True`. Falls Candidate-run vor Erstellung scheiterte, bricht Reconcile hier ab und erreicht Rückbenennung des alten Rollbacks nicht.

- Prüfe Kandidaten-Präsenz tri-state.
- present: entfernen und Entfernung/Abwesenheit beweisen.
- absent: normal weiter zum alten Rollback.
- unknown: Reconciliation fehlschlagen.
- Danach alten Container idempotent unter Originalnamen herstellen, starten und seine laufende Existenz beweisen.
- Tests für Candidate-run-attempted aber Kandidat sicher absent; Rollback muss dennoch zurückkehren.
- Tests für Candidate-RM wirksam, Antwort/Resultat problematisch; reconcile darf nur dann Erfolg melden, wenn Endzustand bewiesen ist.

### 5. Receiver: Cleanup-Warning darf nie Outer-Rollback auslösen

Nach `write_status("success")` ist Deployment committed. Aktuell können Fehler beim Rollback-RM, Backup-Cleanup oder beim Schreiben von `cleanup_warning` aus dem inneren Block heraus in den äußeren `except` laufen. Besonders nach real entferntem Rollback kann der Outer-Rollback den gesunden Kandidaten entfernen.

- Tracke explizit `deployment_committed=True` direkt nach erfolgreichem Success-Status.
- Der äußere Exception-Pfad darf Container-/Source-Rollback nur vor Commit versuchen.
- Cleanup nach Commit vollständig separieren: Fehler loggen; optional `cleanup_warning` schreiben. Falls dieses Schreiben selbst scheitert, nur loggen, nie äußeren Rollback starten.
- Nach Rollback-RM dürfen keine Fehler mehr einen Candidate-Rollback auslösen.
- Tests:
  - success status gelingt; Rollback-RM real wirkt und wirft/Antwort verloren → Kandidat bleibt.
  - cleanup_warning-Statuswrite scheitert → Kandidat bleibt, kein `docker rm -f aura-terminal`.
  - Backup-Cleanup scheitert → Kandidat bleibt.

## TDD-Regeln

- Je Fehlerklasse Regressionstest zuerst und beobachtetes RED.
- Dann minimaler Fix und GREEN.
- Keine echten Remote-, Docker-, VM-, SSH- oder Git-Aktionen.
- Nur Desktop-Workspace ändern.

## Verifikation

- vollständige Desktop-Test-Suite
- `python3 -m py_compile *.py`
- `bash -n *.sh`
- keine doppelte Shell-Funktion
- kein `|| true`, kein `2>/dev/null`, kein generisches `docker inspect`
- keine Volume-/Image-/State-Löschung
- Bericht mit RED/GREEN und geänderten Dateien
