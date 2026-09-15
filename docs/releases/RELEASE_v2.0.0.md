# AURA v2.0.0 — Schema Generation 2 & UI Generation 2

**Release-Typ:** MAJOR (`2.0.0`)  
**Tag-Botschaft:** `AURA v2.0.0 — Confluence Terminal (read-only research)`  
**Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`

## Warum MAJOR?

v2.0.0 führt ein versioniertes, migrationsfähiges Format für Laufzeit-/Portfolio-State sowie die zweite Generation des Dashboard-Design-Systems ein. Das ist eine absichtlich inkompatible Datenform-Grenze. Signalberechnung, Entries, Exits, Gates, Scoring, Sizing und Engine-Mathematik bleiben unverändert.

## Schema Generation 2

- `aura_shared_state.json` und `aura_signal_center_state.json` verwenden `schema_version: 2`.
- Trades und Historieneinträge erhalten `record_schema: 2`; deterministische IDs und `parentId` bleiben unverändert.
- Startmigration läuft vor Runner-Freigabe, legt zeitgestempelte, bytegetreue v1-Backups an und schreibt atomar.
- Idempotente Migration, Dry-Run und bestätigungspflichtiger Rollback über `scripts/ops/aura_state_migrate.py`.
- Schema >2 ist fail-closed: kein State-Schreiben und kein Runner-Start.
- Disk-Space-Guard schützt das Original bei unzureichendem freien Speicher.
- `/ready` und `/status` zeigen die aktive Laufzeit-Schema-Version rein lesend.
- `shadow_log.jsonl` und `shadow_stats.json` werden weder migriert noch umgeschrieben.

## UI Generation 2

- Zentraler CSS-Token-Katalog für Farben, Typografie, 4-px-Abstände, Radien, Schatten und Z-Layer.
- Gemeinsame Verträge für Panels, Karten, Buttons und Badges bei unveränderter DOM-/JS-Funktion.
- 420-px-Mobile-Layer mit 44-px-Touchzielen und zeilenbasierter Tabellendarstellung.
- Globale `:focus-visible`-Ringe und `prefers-reduced-motion`.
- Weiterhin vollständig self-contained, ohne externe Runtime-Ressourcen.

## Deprecated-Cleanup

Der Single-Key-State-Schreibpfad bleibt erhalten, weil Browser/Autobot ihn noch konsumieren. Erfolgreiche Nutzung liefert `X-Aura-Deprecation: single-key-writes; removal >= v2.1` und einen gezählten Warn-Logeintrag. Es wurde kein vermeintlich toter Runtime-Code entfernt: Der erforderliche doppelte Null-Consumer-Nachweis lag für keinen Kandidaten vor.

Ausdrücklich unberührt:

- `LEGACY_LEDGER` / `LEGACY_SHA256`, Ledger-Verifikation und Checkpoint-Schema v1.
- Lockbox-Register/Guard und Präregistrierung.
- Shadow-Log-Format.
- Trading-Gates und Modellparameter.

## Migration und Rollback

Dry-Run:

```bash
python3 scripts/ops/aura_state_migrate.py --state-dir /var/lib/aura --dry-run
```

Rollback:

```bash
python3 scripts/ops/aura_state_migrate.py --state-dir /var/lib/aura --rollback
python3 scripts/ops/aura_state_migrate.py --state-dir /var/lib/aura --rollback --yes
```

Beim Downgrade muss zuerst das v1-Backup wiederhergestellt und danach das vorgehaltene letzte v1.x-Image gestartet werden.

## Prüfprotokoll

Die finalen, auf Merge-Commit und Release-Asset bezogenen Zahlen werden nach Merge und Publish in diesem Bericht ergänzt bzw. im Abschlussbericht mit Befehl und Roh-Ausgabe zitiert. Verbindliche Gates: vollständiges pytest, dynamische JS-Suite, `node --check`, Ledger-Verifikation, `release_check.py`, innerHTML-Kanon 63, Package-Closure und SHA-256 des von GitHub heruntergeladenen Assets.

## Betriebsbeobachtungen

Live-VM-/ntfy-Belege sind keine lokal ableitbaren Erwartungen. Migrationslog, `/ready`, `/status`, Backup-Pfad, Runner-Crash-Zähler, Digest und ntfy-ID werden erst nach realem Auto-Deploy als verifiziert berichtet. Ohne erreichbaren VM-Zugang bleiben diese Punkte ausdrücklich `NICHT GEPRÜFT`.
