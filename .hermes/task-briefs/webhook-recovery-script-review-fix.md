# AURA Recovery-Skript — letzter fail-closed Review-Fix

Workspace für Betriebsdateien: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Kontext

Das neu erstellte `repair_webhook_deployment_v107.sh` ist noch nicht freigegeben. Parent-Review fand:

- Zeile mit `docker inspect aura-terminal >/dev/null 2>&1` unterdrückt einen kritischen Diagnosefehler. Nutzerregel verbietet `2>/dev/null` an kritischen Schritten.
- Vor Wiederherstellung des gelöschten Containers muss fail-closed bewiesen sein, dass das bekannte Image `aura-terminal:latest` und das bestehende State-Volume `aura-state` vorhanden sind. Das Volume darf nie neu angelegt/gelöscht oder inhaltlich gelesen werden.

## Auftrag

Ändere ausschließlich:

- `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/repair_webhook_deployment_v107.sh`
- falls für statische Regression nötig eine Testdatei im selben Ordner

Striktes TDD: statischen Regressionstest zuerst rot, dann minimaler Fix.

1. Ersetze den unterdrückten Existenzcheck durch einen sichtbaren, maschinenlesbaren Docker-Inspect ohne stderr-Unterdrückung, z. B. `docker inspect --format '{{.Id}}' aura-terminal`.
2. Wenn `aura-terminal` fehlt, prüfe vor `docker run` explizit und sichtbar:
   - `docker image inspect --format '{{.Id}}' aura-terminal:latest`
   - `docker volume inspect --format '{{.Name}}' aura-state`
   Beide müssen erfolgreich sein; andernfalls Recovery hart abbrechen.
3. Erst danach darf der bekannte v1.0.6-Vertrag gestartet werden.
4. Keine Verwendung von `|| true`, `2>/dev/null`, blindem Fehler-Verschlucken oder State-Inhaltsausgabe.
5. Keine echten Docker-/VM-/Remote-Aktionen, keine Secrets, keine Commits/Tags/Pushes/Releases.

## Verifikation

- `bash -n repair_webhook_deployment_v107.sh`
- statischer Test: kein `|| true`, kein `2>/dev/null`; Image- und Volume-Inspect kommen vor Docker-Run; Container-Existenzcheck sichtbar.
- vorhandene Receiver-Unit-Tests weiterhin grün.
- Bericht: summary, files_changed, red_tests, green_tests, unverified.
