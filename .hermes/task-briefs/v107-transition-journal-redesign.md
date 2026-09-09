# AURA v1.0.7 — Transition-State-Redesign statt weiterer Flag-Patches

Workspace ausschließlich: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Warum Redesign

Mehrere Reviews fanden dieselbe Fehlerklasse: Zustandsflags werden erst nach potenziell mehrdeutigen Mutationen gesetzt. Bei verlorener/ungültiger QEMU-Antwort oder lokalem Docker-Fehler kann die Mutation bereits erfolgt sein, während der Prozess den alten Zustand annimmt. Weitere einzelne Flag-Fixes reichen nicht.

Zielmodell:

```text
attempt flag BEFORE mutation
        |
        v
mutating command
        |
 error/ambiguous result
        v
idempotent reconciliation based on attempted phase
        |
        v
verify basic old-service contract or fail visibly
```

## Aktuelle unabhängige Blocker

1. `enable_cross_device_sync_v107.sh`: `OLD_STOPPED`/`RENAMED` erst nach `vm_exec`; verlorene Antwort nach erfolgreicher Mutation führt zu falschem Rollbackpfad.
2. `aura_webhook_receiver.py`: gleiche Mutation-vor-Flag-Klasse bei stop/rename/run.
3. Receiver löscht Rollback-Container vor endgültigem, sicherem Statusabschluss; späterer Fehler kann nicht zurückrollen.
4. Receiver zerstört einen vorhandenen `aura-terminal-rollback` ungeprüft mit `check=False`.
5. Sync-Skript behandelt jeden Fehler von `guest_sync_env_correct` als sichere Vertragsabweichung.
6. Recovery-Skript behandelt jeden fehlgeschlagenen Container-Inspect als sichere Abwesenheit.

## Auftrag

Striktes TDD: je vertikaler Fehlerklasse erst Regressionstest, beobachtetes RED, Minimalimplementierung, GREEN. Keine echten Remote-, Docker-, VM-, SSH- oder Git-Aktionen.

Ändere nur nötige Dateien im Desktop-Workspace:

- `enable_cross_device_sync_v107.sh`
- `repair_webhook_deployment_v107.sh`
- `aura_webhook_receiver.py`
- zugehörige `test_*.py`
- BAT nur wenn neue Testdatei/Bundle-Datei nötig wird

## 1. Einmal-Migration: attempt-before-action + idempotente Recovery

- Ersetze Erfolgsflags als alleinige Wahrheit durch Attempt-Phasen, die unmittelbar VOR jeder Mutation gesetzt werden:
  - Stop-Versuch
  - Rename-Versuch
  - Candidate-run-Versuch
- Wenn Stop-Ergebnis mehrdeutig/fehlerhaft: idempotent `aura-terminal` starten und Basic-v1.0.7-Vertrag prüfen.
- Wenn Rename-Ergebnis mehrdeutig/fehlerhaft: beide möglichen Welten sicher zusammenführen:
  - Welt A: alter Container heißt noch `aura-terminal`.
  - Welt B: alter Container heißt bereits `$ROLLBACK_NAME`.
  - Recovery muss in beiden Fällen am Ende genau den alten Container als `aura-terminal` starten und Basic-Vertrag prüfen.
- Nach Candidate-run-Versuch darf Recovery Kandidat entfernen, Rollback zurückbenennen/starten und prüfen. Ein fehlender Kandidat ist erwartbar; ein echter Docker-/Reconcile-Fehler darf nicht als Erfolg gelten.
- Keine blind geschluckten kritischen Fehler. Wenn Reconciliation nicht beweisbar ist: Exit 91.
- Dynamische Bash-Harness-Tests müssen verlorene Antwort NACH simulierter Stop- bzw. Rename-Wirkung abdecken, nicht nur Stringpositionen.

## 2. Tri-State-Prüfungen vor Mutation

### Sync-Skript

`guest_sync_env_correct` braucht drei unterscheidbare Resultate:

- 0 = sicher korrekt
- definierter Code, z. B. 10 = sicher erreichbar/gelesen, aber Vertrag abweichend
- anderer Nichtnullcode = Inspect/JSON/QEMU unentscheidbar

Nur der definierte Abweichungscode darf zur Recreation führen. Unentscheidbar muss vor Stop/Rename abbrechen.

### Recovery-Skript

Container-Existenz ebenfalls tri-state:

- vorhanden
- sicher abwesend
- unentscheidbar/Inspect-/Docker-/QEMU-Fehler

Nur sicher abwesend darf zum Notfall-`docker run` führen. Unentscheidbar: keine Mutation, sichtbarer Fehler.

Keine fragilen stderr-Textmatches. Erzeuge im Gast einen kontrollierten, validierten Status oder nutze explizite Returncodes, ohne Infrastrukturfehler als `not found` zu klassifizieren.

## 3. Receiver: attempted phases + sichere Commit-Grenze

- Vorhandener `rollback_name` darf nie automatisch gelöscht werden. Prüfe explizit in Container-Namespace und brich ab, falls vorhanden. Unerwarteter Inspect-Fehler ebenfalls Abbruch. Test beweist: kein `docker rm -f rollback_name` vor Deployment.
- Setze `old_stop_attempted`, `old_rename_attempted`, `candidate_start_attempted` jeweils VOR lokalem mutierendem `run()`.
- Exception-Reconciliation muss beide möglichen Wirkungen eines fehlgeschlagenen Befehls abdecken:
  - Stop versucht: Original idempotent starten.
  - Rename versucht: falls Rollbackname entstanden, zurückbenennen; andernfalls Original starten.
  - Candidate-run versucht: möglicher Kandidat entfernen, alten Rollback wieder als Original herstellen.
- Verwende einen kleinen getesteten Helper für Container-Existenz/Tri-State oder einen getesteten Reconcile-Helper; keine verstreuten `check=False`-Ketten, deren Ergebnis ignoriert wird.
- Rollback muss verifiziert werden; `start`/`rename` mit `check=False` ohne nachfolgende beweiskräftige Prüfung reicht nicht.
- Finalisierung:
  1. Kandidat gesund, Source-Swap vollständig und rückrollbar.
  2. `write_status("success", ...)` muss gelingen, solange alter Rollback-Container noch existiert.
  3. Erst danach alter Rollback-Container entfernen.
  4. Cleanup-Fehler NACH persistiertem Erfolg dürfen nicht in einen unmöglichen Rollbackpfad springen. Sie müssen sichtbar geloggt werden und dürfen den gesunden Kandidaten nicht entfernen. Alternativ Status mit `cleanup_warning`, sofern atomar und getestet.
  5. Nach Entfernen des Rollbacks darf keine fallible Operation mehr zur normalen Deployment-Exception mit Rollbackversuch führen.
- Source-Backup-Logik aus letztem Fix beibehalten.

## 4. Tests

Mindestens dynamisch beweisen:

- QEMU-Result verlorengegangen, Stop wurde simuliert: alter Container wird gestartet + Basic geprüft; Exit bleibt ursprünglicher Fehler oder 91 bei Recoveryfehler.
- QEMU-Result verlorengegangen, Rename wurde simuliert: alter Container endet unter Originalname laufend.
- Unentscheidbarer Sync-Env-Inspect: kein stop/rename/run.
- Sicher festgestellte Env-Abweichung: Recreation wird erreicht.
- Recovery-Inspect unentscheidbar: kein `docker run`.
- Recovery sicher abwesend: Notfallpfad darf starten.
- Receiver: bestehender Rollback-Container => Abbruch ohne Löschen/Stop.
- Receiver: stop/rename/run hat Wirkung, wirft aber danach Fehler => alter Container wird reconciled.
- Receiver: `write_status("success")` scheitert => alter Rollback existiert noch und wird wiederhergestellt.
- Receiver: Rollback-Entfernung nach persistiertem Erfolg scheitert => Kandidat bleibt gesund, kein Rückrollversuch/keine Entfernung des Kandidaten; Warnung sichtbar.
- Bestehende Source-Swap-, Parser- und Vertrags-Tests bleiben grün.

## Verifikation

- vollständige Desktop-Test-Suite
- `python3 -m py_compile *.py`
- `bash -n *.sh`
- kein `|| true`, kein `2>/dev/null`, kein generisches `docker inspect`
- keine Volume-/Image-/State-Löschung
- Bericht mit RED/GREEN und exakten geänderten Dateien
