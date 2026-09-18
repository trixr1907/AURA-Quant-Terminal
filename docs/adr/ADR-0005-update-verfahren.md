# ADR-0005: Versionierung, Update- und Rollback-Verfahren

**Status:** Akzeptiert (2026-09-17) · **Kontext:** Befund S-08 (`latest`-Tag), Mandat: reproduzierbare Builds, keine `latest`-Abhängigkeiten

## Entscheidung

- **SemVer** unverändert (Policy aus README bleibt). Produktversion in `VERSION`, einzige Quelle; Container und API melden sie.
- **Images werden mit exakter Version getaggt** (`aura-quant-terminal:3.0.0`), Basis-Images per Digest gepinnt; kein `latest` in Compose.
- **Update:** neues Image bauen (oder aus Registry ziehen) → `docker compose up -d` mit neuem Tag → DB-Migrationen laufen beim Start idempotent und fail-closed (Backup vor Migration) → Healthcheck/Readiness prüfen.
- **Rollback:** Compose auf vorheriges Tag zurücksetzen; DB-Zustand vor Migration liegt als automatisches Pre-Migration-Backup vor (auf externem Ziel, sobald Backup eingerichtet). Rollback-Schritte in `docs/OPERATIONS_RUNBOOK.md`.
- **Lockfiles:** Python-Abhängigkeiten mit exakten Versionen (+ Hashes); Docker-Basis per Digest; Node nur für Tests (CI pinnen).
- Kein Auto-Deploy ohne ausdrückliche Zustimmung; Updates werden manuell bzw. über dokumentiertes Skript ausgelöst.

## Begründung

- Reproduzierbare Builds und ein geregelter Update-Prozess sind Mandats-Kern; das bisherige `latest`-Tag macht Rollbacks und Schema-Kompatibilität unbestimmt (S-08).
- Pre-Migration-Backup + fail-closed Migration verhindert den klassischen „halbe Migration nach Update"-Zustand.

## Konsequenzen

- CI baut das Image und prüft, dass `VERSION`, Compose-Tag und Release-Doku übereinstimmen.
- `docs/DEPLOYMENT_PROXMOX.md` enthält die exakten Update-/Rollback-Befehle inkl. Verifikation.
