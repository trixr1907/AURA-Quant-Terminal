# AURA Recovery — Health-Retry und präziser Build-Fehlertest

Workspace: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Offene Review-Punkte

1. `repair_webhook_deployment_v107.sh:58-65` prüft Health nur einmal. Der vereinbarte Vertrag verlangt bis zu 90 Sekunden Startzeit.
2. `test_build_failure_before_stop_never_removes_or_changes_old_container` scheitert aktuell bereits in `current_container_config()` (`Unexpected docker inspect response`) und erreicht den simulierten Docker-Build nicht. Der Testname beweist daher nicht exakt den Build-Fehlerpfad.

## Auftrag

Striktes TDD. Ändere nur:

- `repair_webhook_deployment_v107.sh`
- `test_aura_webhook_receiver.py`
- `test_repair_webhook_deployment_static.py` falls nötig

### Health

- Poll bis maximal 90 Sekunden.
- Pro Versuch Docker-State/Health und `/serving` prüfen.
- Erfolg nur wenn Container läuft, Docker health `healthy`, `/serving.ok == true`, Version `1.0.6` oder `1.0.7`.
- 3 Sekunden Intervall.
- Letzten Fehler sichtbar ausgeben; nach Timeout Exit ungleich 0.
- Keine Fehlerunterdrückung via `2>/dev/null` oder `|| true`.
- Erwartbare Poll-Fehler dürfen kontrolliert in einer `if`-Bedingung abgefangen und sichtbar protokolliert werden.

### Build-Regressionstest

- `current_container_config()` mit realistisch gültigem Altcontainer-Config mocken.
- Sicherstellen, dass `fake_run()` wirklich den `docker build`-Befehl sieht und dort den simulierten Fehler wirft.
- Explizit assertieren, dass genau ein Docker-Build versucht wurde.
- Weiterhin beweisen: kein Stop/Rename/Remove des Altcontainers; Status failed.

Keine echten Docker-/VM-/Remote-Aktionen, keine Secrets, keine Git-Side-Effects.

## Verifikation

- alle 7+ lokalen Tests grün
- `bash -n`
- `py_compile`
- statisch kein `2>/dev/null`, kein `|| true`
- Bericht mit RED/GREEN.
