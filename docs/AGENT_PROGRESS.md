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
| 1 | Subaudits (Quant / Integrity / Dataflow / UX), Befundliste, Funktionsinventar, Datenflusskarte | ✅ DONE (2026-09-17) → `docs/AUDIT.md` + `docs/research/audit_r40/` |
| 2 | Zielarchitektur + ADRs + Migrationsfolge + priorisierter Plan | ✅ DONE (2026-09-17) → `docs/ARCHITECTURE.md` + `docs/adr/ADR-0001..0005` |
| 3 | Vertikale Implementierung (serverseitiger Kern zuerst) | ⬜ |
| 4 | Formelregister + Golden-Fixtures + Parität | ⬜ |
| 5 | Web-UI (responsive) + Control Plane + Auth | ⬜ |
| 6 | Docker/Compose-Härtung, Backup/Restore, Runbook | ⬜ |
| 7 | Evidenz: Acceptance-Matrix, Release-Evidence, Soak (oder NOT_RUN) | ⬜ |

## Entscheidungen (laufend)

- 2026-09-17: Arbeit erfolgt im frischen Clone `AURA_v2`; Alt-Checkout bleibt unangetastet (Nutzer-WIP `test_bot_config_security.py` → wird als Requirement übernommen: serverseitige Config-Validierung + Relay-Token).
- 2026-09-17: Subaudit-Kritikalitäten vom Lead verifiziert: Q-01 (Equity ohne PnL, `headless_autobot.js:644/981/1075`), Q-02 (kein TP-Exit, `:624-632`), Q-03 (Time-Stop als sl_close, `:642`) bestätigt; Q-04 (SL-Maske `:332`) bestätigt, aber HIGH→MEDIUM herabgestuft (aktuelle Auswirkung begrenzt, da `currentSl=entry<tp1`; bricht bei künftigem Trailing über TP1).
- 2026-09-17: Zielarchitektur festgelegt (ADRs): Python 3.12 + FastAPI, SQLite WAL, 2 Container (worker/app) aus einem Image, Session+CSRF+Bearer (Argon2id), SemVer-Images ohne `latest`. Bestands-State-Migration ist Pflichtbestandteil (M-0..M-4).
- 2026-09-17: Runner-Fixes Q-01..Q-04 werden NICHT im Alt-Code geflickt, sondern in `aura.runner` neu implementiert (Ledger-Klassifikation: Prozess-Fix, kein Modellexperiment — Ausführungskorrektheit, keine Signaländerung).

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
- Backup-Ziel: Vorschlag offen (in `docs/DEPLOYMENT_PROXMOX.md`, Phase P7).
- Alt-State der Produktiv-VM muss für M-0/M-1 gesichert werden (Zugriff auf VM nötig; bis dahin Entwicklung gegen synthetische Alt-State-Fixtures).

## Nächste Schritte

1. Accounting- und Restart-Failures red-first beheben; danach v3- und vollständige Python-Suite erneut ausführen.
2. Bestehende JS-Suiten dynamisch vollständig ausführen und Funktionsdrift inventarisieren.
3. Worker/Risk-Gates/Persistenz/API/UI als einen deterministischen Replay-Durchstich integrieren.
4. Browser-E2E, Container/Restore/Störungstests und anschließend Abnahmebericht durchführen.

## Verifikation 2026-09-17 — aktueller Stand

- Tatsächlicher HEAD und vorhandener Dirty Worktree wurden erfasst; keine Nutzeränderung wurde verworfen.
- `python3 -m pytest tests/test_v3_*.py -ra`: **85 passed, 2 failed, Exit 1**.
- `python3 -m pytest -ra` vor Fix: **593 passed, 2 failed, Exit 1**; Rohlog `docs/evidence/v3_acceptance_20260917/pytest_full.log`.
- Accounting/Restart red-first behoben; gezielte Suite **13/13 PASS** und vollständige Python-Suite danach **595/595 PASS, Exit 0** (`accounting_fix.log`, `pytest_full_after_accounting_fix.log`).
- Dynamische JS-Regression: **98/98 PASS, Exit 0**; Artefakte `docs/evidence/v3_acceptance_20260917/js_full.log` und `js_results.json`.
- Vertikale Integration nach Ergänzung von Closed-Bar-Persistenz, Same-Bar-Dedupe, fail-closed Liquiditätsgate und DB-Refresh der API: **7/7 PASS**; vollständige Python-Suite danach **600/600 PASS** (`vertical_integration.log`, `pytest_full_after_vertical_fix.log`).
- Der öffentliche Bitget-Test hat in dieser Runde real Daten empfangen und validiert; Nichterreichbarkeit wird nun als `NOT_RUN`/Skip statt als PASS ausgewiesen.
- Verbleibende Blocking-Befunde: Dashboard ist nicht an die mutierende v3-Control-Plane angebunden; Compose bleibt lokal NOT_RUN.
- Der zuvor nur prozesslokale Not-Halt wurde über die SQLite-Command-Tabelle an den separaten Worker gekoppelt; Cross-Process Halt+Resume ist mit getrennten DB-Verbindungen grün getestet.
- Unabhängige Read-only-Reviews bestätigten weitere Blocker: fehlendes Funding/TP3, falsches R-Multiple nach TP1, Backtest-Entry-Fee, fehlender Holdout-Gate, unsicherer Default-Token und unkoordinierter Restore; der ebenfalls gefundene Same-Bar-Dedupe-Fehler ist inzwischen red-first behoben.
- Daher derzeit ausdrücklich: **kein SOFTWARE GO, kein Deployment GO, MODEL_NO_EVIDENCE**.
