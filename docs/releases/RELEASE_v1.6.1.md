# AURA v1.6.1 — Infra-Patch: Universum-Sync-Isolation & CI-Stabilität

Version: 1.6.1  
Release-Typ: PATCH (Infra-Härtung)  
Datum: 2026-09-14

---

## Kontext

v1.6.0 (Runde 24, Signal-Center) audit-verifiziert. CI-Run 34788297140 schlug auf
Merge-Commit `f1c013d` im Quality-Gate "version progression" fehl. Root-Cause:
`test_launcher.py` rief den Launcher-Hauptpfad ungemockt auf, was Auto-Sync triggerte
und `data/bitget_usdt_futures_universe.json` (getracktes Produktfile) überschrieb.
Post-release Gate (`VERSION == Tag`) bewertet jede Tracked-File-Änderung als
Progressionsverletzung — korrekt und gewollt.

## Massnahmen

- `AURA_UNIVERSE_PATH` / `AURA_DATA_DIR` / `AURA_DISABLE_AUTO_SYNC=1` in start.py,
  sync_market_data.py, bitget_relay.py und release_check.py (subproc-env).
- `test_launcher.py`: `run_command` gemockt; 3 neue Regressions-Tests.
- `test_release_sync.py`: Sync-Safety-Tests mit isoliertem Temp-Universum.

## Verifikation

pytest: 253 passed, 57 subtests — Baseline +3 vs v1.6.0 (250 passed).
JS-Suite: 82/82 Suiten PASS.
innerHTML: 66 (unveraendert).
release_check.py flaglos: EXIT=0, VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE.
LEDGER.md / VERDICT.md: 0 Zeilen geaendert (git diff --numstat = leer).
universe.json: nach pytest unveraendert (git status --porcelain = leer).

## Endpoint-Hygiene

Produktiver Endpoint ausschliesslich: http://192.168.8.115:8787 (VM 201).
Lokaler Dev-Container `aura-terminal` entfernt. Nur ein aktiver Endpoint.

## Scope

PATCH (Infra). Kein veraendertes Scoring/Modell. Ledger EXP-032. Verdict unveraendert.
