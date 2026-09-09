# Finaler Korrektur-Task-Brief: AURA v1.0.7 Sync

Workspace: `/home/ivo/projects/AURA_Quant_Terminal`

## Status

Die zweite Umsetzung behebt viele Findings, ist aber noch nicht freigabefähig. Keine bestehenden v1.0.7-Änderungen pauschal zurücksetzen. Keine Git-Side-Effects.

## Verifizierte Restfehler

### 1. Listen-Löschung funktioniert außerhalb atomarer Close-Pfade nicht

`SyncEngine.enqueueList()` vergleicht gegen `this.shadow[key]`, aber `applyServerState()` befüllt/aktualisiert `shadow` nicht. Dadurch ist `previous` oft `[]`. Beispiel: History-Einzellöschung ruft `saveTradeHistory(nextHist)` auf; der Client sendet nur Upserts der verbleibenden Einträge und kein Delete der entfernten ID. Der Server behält den gelöschten Eintrag.

Fix:
- Server-Shadow für Trade-/History-Listen beim Pull und nach bestätigten Serverantworten korrekt aktualisieren.
- Pending-lokalen Zustand nicht überschreiben.
- Optimistisches Shadow-Update und bestätigter Shadow müssen sauber getrennt sein oder anderweitig so implementiert werden, dass mehrere lokale Änderungen vor Bestätigung korrekt diffbar bleiben.
- Einzellöschung aus Historie explizit als ID-Delete senden, wenn das einfacher/sicherer ist.

Pflichttest: Remote History enthält IDs A+B; lokales Löschen von B über den echten UI-/`saveTradeHistory`-Pfad erzeugt Delete(B); nach Serverantwort und Pull bleibt nur A.

### 2. Sync-Status meldet fälschlich „synchronisiert“ bei Pending-Queue

`pull()` setzt immer `synced`, auch wenn `pending.length > 0` oder `queueRunning` aktiv ist.

Fix:
- Status `synchronisiere`/mid solange Pending oder Queue aktiv.
- Erst nach bestätigter leerer Queue `synchronisiert`.
- Pull darf Pending-Status nicht überschreiben.

Pflichttest: Pending-Mutation + erfolgreicher Pull => Status nicht `synced`; nach bestätigter Mutation und leerer Queue => `synced`.

### 3. 409 kann Endlosschleife erzeugen

`sendBatch()` dekrementiert bei 409 `item.attempts`. Bei dauerhaft konkurrierenden Revisionen erreicht der Eintrag niemals `maxRetries`.

Fix:
- Konflikte begrenzt behandeln; kein Zurücksetzen/Dekrementieren des Retry-Zählers.
- Nach Retry-Limit Mutation nicht still löschen. Queue muss sichtbar pausieren/blocked bleiben und `nicht synchronisiert` anzeigen. Lokale Pending-Mutation bleibt erhalten für einen späteren manuellen/automatischen erneuten Versuch; kein anschließender Pull darf sie überschreiben.
- Netzwerkfehler ebenfalls nicht still verwerfen.
- Kein Busy-Loop.

Pflichttests:
- Dauerhafte 409 endet nach exakt begrenzter Zahl Versuche, kein Endlosloop.
- Fehlgeschlagener Eintrag bleibt pending/blocked und Status zeigt unsynchronisiert.

### 4. Homelab-Starter erlauben weiterhin nur Loopback

Mehrere Pfade starten mit `AURA_ALLOWED_HOSTS=127.0.0.1`, zeigen anschließend aber eine LAN-IP als Dashboard-URL:

- `smart_homelab_installer.sh:56-66` ermittelt Host-IP erst nach `docker run`.
- `smart_homelab_installer.sh` LXC-Zweig startet vor IP-Ermittlung mit Loopback.
- `deep_infrastructure_scanner.sh` Host- und LXC-Zweige ebenso.

Fix:
- LAN-IP vor `docker run` ermitteln und exakt als `AURA_ALLOWED_HOSTS` übergeben.
- LXC-IP vor Start aus dem Container ermitteln.
- Lokale Starter `DOCKER_START.bat` und `docker_start.sh` dürfen bewusst nur Loopback erlauben, sofern sie ausschließlich localhost ausgeben.
- Kein `0.0.0.0` als erlaubter Host und keine Wildcard.

Pflichttests müssen die jeweilige Datenfluss-Reihenfolge prüfen, nicht nur ob irgendwo im Skript die Strings `AURA_ALLOWED_HOSTS` und `aura-state` vorkommen.

### 5. History-Reihenfolge auf Server

Neue History-Einträge werden serverseitig in `_apply_mutations_locked()` angehängt, während UI lokal `unshift()` verwendet und Neueste-zuerst erwartet. Dadurch ändert anderes Gerät die Reihenfolge.

Fix:
- Neue History-ID vorne einfügen; Update bestehender ID an bestehender Position.
- History auf die neuesten 200 Einträge gemäß Neueste-zuerst begrenzen (`[:200]`, nicht Tail).
- Active-Trades dürfen bestehende Reihenfolge erhalten und neue IDs anhängen.

Pflichttests für Einfüge- und Trim-Reihenfolge.

### 6. Bootstrap-/Legacy-Konflikt robust machen

`pushDirect()` ruft bei 409 `pull()` auf. Während initialem `pull()` ist `isPulling=true`, daher kehrt dieser Aufruf sofort zurück und übernimmt den Konflikt-State nicht. Außerdem soll Autobot-Queue eine begrenzte, nicht verlierende Konfliktbehandlung nutzen.

Fix:
- Konfliktantwort direkt sicher anwenden, ohne rekursiven blockierten Pull.
- Bootstrap mehrerer Keys nutzt jeweils bestätigte Revision.
- Autobot-Pending bleibt bei erschöpftem Retry sichtbar erhalten.

Pflichttest für Bootstrap/Legacy-409 innerhalb laufendem Pull.

## Nicht verschlechtern

- Atomare Multi-Key Close-/Partial-Close-Batches beibehalten.
- ID-basierte Upsert/Delete-Servermutationen beibehalten.
- HTTP/HTTPS-Same-Origin-Allowlist beibehalten.
- State-Volume in allen Docker-Recreate-Pfaden beibehalten.
- Zonenweisen Pine-FVG-Lebenszyklus beibehalten.
- Version bleibt `1.0.7`.

## TDD und Verifikation

Jeden Pflichttest zuerst RED laufen lassen, dann minimal fixen. Danach:

- `pytest -q`
- `node tests/test_engine_full.js`
- `node tests/test_cross_device_sync.js`
- `node tests/test_release_notes_overlay.js`
- `python3 tests/pine_static_check.py`
- `python3 scripts/release_check.py`
- `python3 scripts/build_package.py --force`
- `bash -n docker_start.sh smart_homelab_installer.sh deep_infrastructure_scanner.sh`
- `git diff --check`

Keine Commits, Tags, Pushes, Releases oder Deployments.