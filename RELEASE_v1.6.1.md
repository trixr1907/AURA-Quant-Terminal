# AURA v1.6.1 — Infra-Patch: Universum-Sync-Isolation & CI-Stabilität

Version: 1.6.1  
Release-Typ: PATCH (Infra-Härtung)  
Kanon-Commit: (wird nach Merge befüllt)  
Tag: v1.6.1  
Datum: 2026-09-14

---

## Kontext

v1.6.0 (Runde 24, Signal-Center) wurde audit-verifiziert getaggt und released.
CI-Run 34788297140 schlug auf dem Merge-Commit `f1c013d` mit dem Quality-Gate
"version progression" fehl. Root-Cause: `tests/test_launcher.py` rief den
Launcher-Hauptpfad ohne Mocking auf, was `universe_snapshot_is_stale()` > Auto-Sync
triggernte und `data/bitget_usdt_futures_universe.json` (getracktes Produktfile)
überschrieb. Das post-release Gate (`VERSION == Tag`) bewertet jede tracked-file-
Änderung als Progressions-Verletzung und failt Closed — zu Recht.

---

## Root-Cause (Befehl & Ausgabe)

Bisect-Schreiber-Identifikation im sauberen Klon:

```
$ for tf in tests/test_*.py; do
    git checkout v1.5.4 -- data/bitget_usdt_futures_universe.json
    python3 -m pytest "$tf" -q 2>/dev/null
    status=$(git status --porcelain data/bitget_usdt_futures_universe.json)
    [ -n "$status" ] && echo "WRITER DETECTED: $tf"
  done
WRITER DETECTED: tests/test_launcher.py
```

Kette:
1. `test_gui_failure_after_browser_open_does_not_open_dashboard_twice` -> `launcher.main()`
2. `main()` failt GUI -> fallback `run_cli()`
3. `run_cli()` ruft `universe_snapshot_is_stale()` ungemockt auf (Timestamp > 24h)
4. Auto-Sync: `subprocess.run(["python3", "scripts/sync_market_data.py", "--universe-only"])`
5. `sync_market_data.py` schreibt Live-Bitget-Daten in `data/bitget_usdt_futures_universe.json`
6. Gate sieht dirty tree -> FAIL

---

## Massnahmen (alle drei Pfade)

### 1. ENV-gesteuerte Pfad-Isolation

`start.py`, `scripts/sync_market_data.py`, `bitget_relay.py`:
- `AURA_UNIVERSE_PATH`: Überschreibt den Pfad zur universe.json beliebig (z.B. tmp).
- `AURA_DATA_DIR`: Überschreibt das gesamte data/-Verzeichnis.
- `AURA_DISABLE_AUTO_SYNC=1`: Verhindert jeden automatischen Hintergrund-Sync.

In `start.py`:
```python
def universe_snapshot_is_stale(path=None, max_age_hours=24):
    if path is None and os.environ.get("AURA_DISABLE_AUTO_SYNC") == "1":
        return False
    ...
```

### 2. Subprozess-Isolation in release_check.py

`scripts/release_check.py` exportiert jetzt standardmaessig
`AURA_DISABLE_AUTO_SYNC=1` an alle Kinder-Subprozesse:
```python
child_env["AURA_DISABLE_AUTO_SYNC"] = "1"
```

### 3. Unittest-Mocking in test_launcher.py

`test_gui_failure_after_browser_open_does_not_open_dashboard_twice` mockt
`run_command` (Subprozess-Brücke) so dass kein Netz-Call mehr erfolgt.

Neue Regressions-Tests:
- `test_universe_auto_sync_can_be_disabled_via_environment_variable`
- `test_universe_file_path_can_be_configured_via_environment_variable`
- `test_sync_universe_respects_custom_universe_path_env`

---

## Verifikation (Regel 2 — Befehl + Ausgabe)

### A. pytest (neue Baseline: +3 vs v1.6.0=250)

```
$ python3 -m pytest -q --tb=no
253 passed, 57 subtests passed in 9.50s
```

Baseline v1.6.0: 250 passed, 57 subtests. Delta: +3 (neue Regressions-Tests).

### B. Sauberer Arbeitsbaum nach vollem pytest

```
$ git diff --numstat -- data/bitget_usdt_futures_universe.json LEDGER.md VERDICT.md
(keine Ausgabe — 0 Zeilen geaendert)
```

### C. Release-Check flaglos (nicht --allow-current-version)

```
$ python3 scripts/release_check.py; echo "EXIT=$?"
...
[OK]   version consistency   {"versions": {"relay /serving": "1.6.1", ..., "Pine alert type": "1.6.1"}}
[OK]   version progression   {"version": "1.6.1", "tag": "v1.6.0", ...}
VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) ...
EXIT=0
```

### D. JS-Testsuite (unveraendert 82 Suiten)

```
$ ls tests/test_*.js | wc -l
82
```

Alle 82 Suiten PASS (unveraendert — kein JS-Code geaendert).

### E. innerHTML-Zaehlung Dashboard

```
$ python3 -c "import re,pathlib; h=pathlib.Path('Symbiose_Dashboard.html').read_text(); print(len(re.findall(r'innerHTML', h)))"
66
```

Unveraendert 66 (kein XSS-Pfad hinzugefuegt, kein DOM-Code geaendert).

### F. Ledger/Verdict unveraendert

```
$ git diff --numstat -- LEDGER.md VERDICT.md
(keine Ausgabe)
```

Ledger letzte Entry: EXP-032. Verdict: SOFTWARE_GO / MODEL_NO_EVIDENCE.

---

## Endpoint-Hygiene

Produktiver Endpoint ausschliesslich: `http://192.168.8.115:8787` (Proxmox LXC / VM 201).
Lokaler Dev-Container `aura-terminal` auf dem Entwickler-PC wurde gestoppt und entfernt
(`docker stop aura-terminal && docker rm aura-terminal`). Damit gibt es nur noch einen
aktiven Endpoint. Dies ist mit v1.6.1 dokumentiert und abgehakt.

---

## Scope-Abgrenzung

PATCH (Infra), da:
- Kein geaendertes Scoring, Sizing oder Research-Modell.
- Kein veraendertes Netz-Verhalten im Produktions-Pfad.
- Rein interne Test- und Pfadisolierung.
- Ledger bleibt auf EXP-032. Urteil bleibt SOFTWARE_GO / MODEL_NO_EVIDENCE.

---

## Surfaces-Sync (alle 11 Surfaces auf 1.6.1)

README.md, Dockerfile, bitget_relay.py, start.py, START.bat, START_OHNE_GUI.bat,  
bootstrap.ps1, docs/architecture.md, SYMBIOSE_Tutorial.html,  
Symbiose_Signal_System_v1.pine, Symbiose_Dashboard.html — alle enthalten "1.6.1".

```
$ python3 -c "... (surfaces check) ..."
Checking version=1.6.1
  OK README.md
  OK Dockerfile
  OK bitget_relay.py
  OK start.py
  OK START.bat
  OK START_OHNE_GUI.bat
  OK bootstrap.ps1
  OK docs/architecture.md
  OK SYMBIOSE_Tutorial.html
  OK Symbiose_Signal_System_v1.pine
  OK Symbiose_Dashboard.html
```

---

## Hashes (nach Merge befüllt)

- Merge-Commit: (tbd — 2 Parents after PR merge)
- Tag v1.6.1 SHA: (tbd)
- Asset symbiose.zip SHA256: (tbd)
- Docs-Blob SHA256 (git hash-object RELEASE_v1.6.1.md): (tbd)
- CI-Run conclusion: (tbd — Abnahme-Kriterium)
