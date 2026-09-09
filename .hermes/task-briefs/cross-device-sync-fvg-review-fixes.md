# Korrektur-Task-Brief: Cross-Device Sync + FVG v1.0.7

Workspace: `/home/ivo/projects/AURA_Quant_Terminal`

## Ausgangslage

Die erste v1.0.7-Implementierung ist noch uncommittet. Ein unabhängiger Review blockiert die Freigabe. Bestehende Änderungen nicht pauschal zurücksetzen, sondern gezielt korrigieren. Keine Git-Side-Effects.

## Blockierende Findings

1. `saveTrades()` und `saveTradeHistory()` senden unabhängige Full-Array-Writes mit derselben Revision. `closeTrade()`/`takePartialProfit()` können dadurch nur halb persistiert werden.
2. Bei HTTP 409 wird lokaler Pending-State verworfen. Gleichzeitige Änderungen verschiedener Geräte können verloren gehen.
3. Host-/Origin-Prüfung ist für direkten LAN-Zugriff nur bei korrektem `AURA_ALLOWED_HOSTS` nutzbar und lehnt sichere Same-Origin-HTTPS-Reverse-Proxies grundsätzlich ab.
4. Einige Docker-Startpfade mounten kein persistentes `aura-state`-Volume und reichen keine Host-Allowlist durch.
5. Pine verwaltet FVG-Boxen nicht zonenweise: nur neueste Box wird verlängert/mitigiert, ältere aktive Zonen bleiben falsch stehen.

## Zielverhalten

### A. Verlustfreie Listen-Mutationen

Paper-Trades und Historie müssen als ID-basierte Mutationen synchronisiert werden, nicht als ungeschützte Full-Array-Überschreibungen.

- Server unterstützt atomare Batch-Mutationen unter `STATE_LOCK`.
- Ein Request kann mehrere Änderungen über mehrere Keys atomar anwenden, insbesondere:
  - aktiven Trade entfernen + History-Record hinzufügen;
  - aktiven Trade aktualisieren + History-Record hinzufügen bei Teilverkauf.
- Listenoperationen mindestens: `upsert` anhand stabiler `id`, `delete` anhand `id`.
- Serverseitige Validierung: nur erlaubte State-Keys; Listenmutation nur für Trade-/History-Keys; Größenlimits; ungültige Payloads ohne Teilmutation ablehnen.
- Atomarer Dateischreibvorgang; `_rev` steigt genau einmal pro erfolgreiches Batch.
- Unterschiedliche IDs von mehreren Geräten dürfen sich nicht gegenseitig löschen.
- Eine explizite Löschung muss auf anderem Gerät erscheinen und darf nicht durch dessen unveränderten Altzustand wiederbelebt werden.
- Reihenfolge in Arrays deterministisch halten, sinnvollerweise bestehende Position ersetzen und neue IDs entsprechend UI-Semantik einfügen.
- Existierende Single-Key-API nur beibehalten, wenn weiterhin sicher benötigt; UI-Paper-Trades/History sollen den neuen mutationsbasierten Pfad nutzen.

### B. Client-Queue und Reconcile

- Mutationen eines Clients strikt sequenziell senden; keine parallelen Requests mit derselben Revision.
- Pending-Mutationen dürfen bei 409 oder temporärem Netzwerkfehler nicht still verloren gehen.
- Bei 409: aktuellen Serverstand/Revision übernehmen und dieselbe semantische Mutation erneut versuchen (begrenzte/saubere Retry-Logik; keine Endlosschleife).
- Nach erfolgreichem Mutations-Batch lokalen Server-Shadow aktualisieren.
- Polling darf keine lokal noch ausstehende Mutation überschreiben.
- `closeTrade()` und `takePartialProfit()` müssen jeweils genau ein atomisches Sync-Batch erzeugen.
- Start, Update, Full-Close, Partial-Close und History-Einzellöschung abdecken.
- UI-Status darf erst „synchronisiert“ zeigen, wenn Queue leer und letzter Request bestätigt ist; sonst „synchronisiere“, „Konflikt“ oder „offline“.
- Autobot-Singleton ebenfalls sequenzieren; ein 409 darf lokalen Pending-Write nicht still verwerfen.

### C. Host/Origin

- Host bleibt explizit allowlisted: Loopback plus `AURA_ALLOWED_HOSTS`.
- Same-Origin `http` und `https` erlauben.
- Vergleiche Origin-Authority gegen Request-Host-Authority sicher:
  - direkter LAN-Fall `Host: 192.168.8.115:8787`, `Origin: http://192.168.8.115:8787` erlaubt;
  - Reverse-Proxy-Fall `Host: erlaubte.domain`, `Origin: https://erlaubte.domain` erlaubt;
  - anderer Host, Port, Userinfo, Query, Fragment oder `null` abweisen.
- Kein Wildcard-Freischalten des privilegierten State-Endpunkts.

### D. Persistenter Docker-Vertrag

Alle im Repo angebotenen Docker-Start-/Homelab-Pfade prüfen und korrigieren:

- `docker-compose.yml`
- `DOCKER_START.bat`
- `docker_start.sh`
- `smart_homelab_installer.sh`
- alle relevanten Zweige in `deep_infrastructure_scanner.sh`
- ggf. Guides/Tests

Jeder Container-Recreate-Pfad muss `AURA_STATE_DIR=/var/lib/aura` und `-v aura-state:/var/lib/aura` verwenden. LAN-Deployer müssen die echte LAN-IP als `AURA_ALLOWED_HOSTS` übergeben. Lokale Starter dürfen sicher auf Loopback beschränkt bleiben. Dockerfile kann den Mountpoint dokumentieren, aber ein `VOLUME` allein ersetzt nicht das explizite benannte Volume im Run-Vertrag.

### E. FVG Pine zonenweise

- 3-Kerzen-Erkennung bleibt:
  - bullish: `low > high[2]`
  - bearish: `high < low[2]`
- Jede erzeugte Pine-Box hat eigene Top/Bot/Dir/Aktiv-Metadaten in parallelen Arrays oder gleichwertiger Pine-Struktur.
- Jede aktive Zone wird auf jeder späteren Bar unabhängig nach rechts verlängert.
- Full mitigation:
  - bullish beendet, wenn `low <= zone.bot`;
  - bearish beendet, wenn `high >= zone.top`.
- Mitigierte Box endet auf exakter Mitigations-Bar und wird danach nicht verlängert.
- Maximalzahl sauber über alle parallelen Arrays synchron beschneiden/löschen.
- Globaler letzter-FVG-Signalzustand und MTF-Output dürfen nicht unbeabsichtigt verändert werden; JS/Pine-Signalparität bewahren.

## TDD-Pflicht

Vor jeder Produktionskorrektur passenden Test hinzufügen und RED belegen. Mindestens:

1. Zwei schnelle Client-Mutationen werden sequenziell mit aktualisierter Revision gesendet.
2. 409 zieht Serverstand und wiederholt Pending-Mutation, statt sie zu verlieren.
3. Poll überschreibt keinen Pending-Write.
4. Gleichzeitiges Upsert verschiedener Trade-IDs erhält beide.
5. Delete einer ID lässt andere IDs unberührt.
6. Atomic Close-Batch entfernt aktiven Trade und ergänzt Historie in einem Revision-Schritt.
7. Ungültiges Batch mutiert gar nichts.
8. HTTPS Same-Origin für allowlisted DNS-Host erlaubt; Host-/Port-Mismatch blockiert.
9. Alle Docker-Startpfade enthalten State-Volume/State-Dir; Homelab-Pfade Host-Allowlist.
10. Pine-Static-/Verhaltenstest belegt mehrere gleichzeitig aktive Boxen und zonenweise Mitigation.

## Verifikation

Mindestens ausführen:

- `pytest -q`
- `node tests/test_engine_full.js`
- `node tests/test_cross_device_sync.js`
- alle neuen Sync-/Pine-Tests
- `node tests/test_release_notes_overlay.js`
- `python3 tests/pine_static_check.py`
- `node tests/compare_pine_js_golden.js` nur mit den vom Repo erwarteten Fixture-Argumenten oder über `scripts/release_check.py`
- `python3 scripts/release_check.py`
- `python3 scripts/build_package.py --force`
- `git diff --check`

## Grenzen

- Version bleibt `1.0.7`.
- Keine echten Brokerorders.
- Keine Secrets lesen oder ausgeben.
- Keine Commits, Tags, Pushes, Releases oder Deployments.
- Nur taskbezogene Änderungen.