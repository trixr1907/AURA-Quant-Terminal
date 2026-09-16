# ADR-0002: Datenbank und Persistenz

**Status:** Akzeptiert (2026-09-17) · **Kontext:** R40-Neuentwicklung; Befund D-03 (JSON-Flatfiles), Stakeholder-Pflicht: Alt-State migrieren

## Entscheidung

- **SQLite im WAL-Modus** als einzige Systemdatenbank, Datei auf Named Volume `aura-data`.
- Schema-Versionierung über nummerierte SQL-Migrationsdateien + `schema_migrations`-Tabelle (eigener schlanker Runner, fail-closed bei unbekannter Version). Kein Alembic (YAGNI bei überschaubarem Schema).
- **Single-Writer-Regeln je Tabelle** (dokumentiert in `docs/DATA_CONTRACTS.md`): Runner/Worker schreibt Marktdaten, Trades, Funnel; App schreibt Config/Commands; beide lesen. `busy_timeout` gesetzt, kurze Transaktionen.
- Geldbeträge/Mengen als INTEGER-Fixed-Point oder TEXT (Decimal), niemals REAL, wo Rundung fachlich gefährlich ist.
- Backups über die SQLite-Online-Backup-API (konsistent bei laufendem Betrieb) auf externes Ziel (ADR-0005, Backup-Vorschlag in `docs/DEPLOYMENT_PROXMOX.md`).

## Begründung

- Single-User, Single-VM: PostgreSQL wäre ein zusätzlicher Dienst, SPOF und Betriebsaufwand (Upgrades, PITR) ohne nachgewiesenen Bedarf. SQLite WAL deckt ACID, parallele Leser und Crash-Safety ab.
- Gegenüber JSON-Flatfiles (Ist-Zustand): echte Transaktionen, Indizes für Historie/Abfragen, kein OCC-via-Datei mehr nötig (DB-Transaktionen + Revisionsspalten ersetzen `_rev`/HTTP-409-Mechanik serverseitig; API liefert weiterhin Revisionen für Clients).
- Alternative verworfen: PostgreSQL (Overhead), reine Flatfiles (Befund D-03), Parquet-only (kein Transaktionsmodell für Runner-State).

## Konsequenzen

- Legacy-Importer (`aura.store.legacy_import`) wird Pflichtbestandteil mit Dry-Run, Vollständigkeitsreport und Idempotenz.
- Shadow-Log bleibt konzeptionell append-only (DB-Tabelle, nur INSERT) — kein UPDATE/DELETE auf Evidenztabellen per Policy + Trigger.
- Wachstumsgrenzen und Retention werden im Runbook überwacht (DB-Größe, Vakuum-Strategie).
