# AURA R40 — Agent Progress (evidenzbasierte Neuentwicklung)

> Laufendes Arbeitsprotokoll über Sitzungen hinweg. Jede Phase: implementieren → gezielt testen → Integration prüfen → Befunde beheben → Regression prüfen → Evidenz sichern.

## Ausgangspunkt

- **Ausgangs-SHA:** `de25830de9884a4a6b9019d1ecf0bf2da6f147a9` (main, 2026-09-16, v2.5.0)
- **Arbeits-Branch:** `audit/r40-baseline` (spätere Feature-Branches je Phase)
- **Arbeits-Checkout:** `/home/ivo/projects/AURA_v2` (frischer Clone; Alt-Checkout mit Nutzer-WIP unverändert)
- **Baseline-Dokument:** `docs/research/BASELINE_R40_20260917.md` — pytest 508+69 grün, JS 98/98 grün, Gate `SOFTWARE_GO / MODEL_NO_EVIDENCE`, Ledger EXP-032 valide.

## Stakeholder-Entscheidungen (2026-09-17)

1. Ubuntu/Debian-VM auf Proxmox existiert, ausreichende Ressourcen.
2. Bestandsinstallation läuft; **State-Migration ist Pflicht**.
3. Zugriff: LAN + WireGuard/Tailscale, kein offener Port.
4. Backup-Ziel: keines vorhanden → Vorschlag erarbeiten.
5. ntfy bleibt Benachrichtigungskanal.
6. Annahme (konservativ, dokumentiert): Single-User.

## Phasenplan (Arbeitsstand)

| Phase | Inhalt | Status |
|---|---|---|
| 0 | Baseline einfrieren, Mandatsfragen | ✅ DONE (2026-09-17) |
| 1 | Subaudits (Quant / Integrity / Dataflow / UX), Befundliste, Funktionsinventar, Datenflusskarte | 🔄 RUNNING (4 Read-only-Subaudits) |
| 2 | Zielarchitektur + ADRs + Migrationsfolge + priorisierter Plan | ⬜ |
| 3 | Vertikale Implementierung (serverseitiger Kern zuerst) | ⬜ |
| 4 | Formelregister + Golden-Fixtures + Parität | ⬜ |
| 5 | Web-UI (responsive) + Control Plane + Auth | ⬜ |
| 6 | Docker/Compose-Härtung, Backup/Restore, Runbook | ⬜ |
| 7 | Evidenz: Acceptance-Matrix, Release-Evidence, Soak (oder NOT_RUN) | ⬜ |

## Entscheidungen (laufend)

- 2026-09-17: Arbeit erfolgt im frischen Clone `AURA_v2`; Alt-Checkout bleibt unangetastet (Nutzer-WIP `test_bot_config_security.py` → wird als Requirement übernommen: serverseitige Config-Validierung + Relay-Token).

## Ausgeführte Kernbefehle (Phase 0)

```
git clone https://github.com/trixr1907/AURA-Quant-Terminal.git AURA_v2
git checkout -b audit/r40-baseline
python3 -m pytest -q                      # 508 passed, 69 subtests, exit 0
for f in tests/test_*.js; node $f         # 98/98 PASS
python3 scripts/release_check.py          # SOFTWARE_GO / MODEL_NO_EVIDENCE, exit 0 (Worktree /tmp/aura_gate)
python3 scripts/verify_ledger.py          # ok:true EXP-032, exit 0
python3 tests/reference_backtest.py       # ALL ASSERTIONS PASSED, exit 0
python3 tests/pine_static_check.py        # OK, exit 0
```

## Blocker / Offenes

- Lokales `docker compose`-Plugin fehlt → Compose-Smoke auf Ziel-VM (Deployment bleibt NOT_RUN bis dahin).
- Subaudit-Ergebnisse (Quant/Integrity/Dataflow/UX) ausstehend → Phase-1-Abschluss.

## Nächste Schritte

1. Subaudit-Artefakte konsolidieren → `docs/AUDIT.md` (Befundliste mit Schweregrad, Beleg, Reproduktionsweg).
2. Funktionsinventar (Beibehalten/Ersetzen/Entfernen) + Datenflusskarte finalisieren.
3. Zielarchitektur + ADRs + Migrationsplan (State aus Bestandsinstallation!) + Implementierungsreihenfolge.
