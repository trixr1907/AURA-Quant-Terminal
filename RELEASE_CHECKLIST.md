# AURA — Release Checklist

Ein Befehl prüft alle automatisierbaren Qualitäts-Gates:

```text
python3 scripts/release_check.py
```

Exit `0` bedeutet: kein erforderlicher Software-Check fehlgeschlagen. Das finale JSON enthält zusätzlich das ehrliche Modell-Verdict. Fehlende oder negative Edge-Evidenz darf niemals als Profitabilitätsnachweis erscheinen.

## Automatisierte Gates

| Gate | Prüfpfad | Pass-Kriterium |
|---|---|---|
| Engine | `node tests/test_engine_full.js` | keine Fehlschläge |
| Radar Progressive Rendering | `node tests/test_radar_progressive.js` | Batch-Updates und Volumen-Early-Skip bestanden |
| Live Trade Tracker | `node tests/test_live_trade_tracker.js` | Tracker-Logik, State-Transitions und Invarianten bestanden |
| SMC Sessions (UTC) | `node tests/test_smc_sessions.js` | 10 Grenztests, Killzone-Semantik, Shading-Konsistenz und Tooltip bestanden |
| Statistik | Python-Orakel, Metamorphik, Sensitivität | deterministisch; Verdict korrekt klassifiziert |
| Public Relay | `python3 -m unittest tests/test_relay_full.py` | Serving, CORS, Public Proxy und Fail-closed-Routing bestanden |
| Release & Sync Suite | `python3 -m unittest tests/test_release_sync.py` | Fail-closed Versionsprüfung, Golden-Master-Authentizität und Sync-Safety bestanden |
| Launcher | `python3 -m unittest tests/test_launcher.py` | GUI-/CLI-Fallback und Abhängigkeiten bestanden |
| Research Cleanup | `python3 -m unittest tests/test_research_cleanup.py` | keine Execution-Artefakte im Produktpfad |
| JavaScript-Syntax | extrahierter `<script>`-Block via `node --check` | Exit 0 |
| Pine-Statik | `python3 tests/pine_static_check.py` | Regeln und Pflichtplots bestanden |
| Golden-Master-Authentizität | `verify_golden_authenticity` | Ausschließlich echte TradingView-CSV-Exporte mit unabhängiger Provenance (fail-closed, keine Heuristik-Freigabe) |
| Golden Master Parität | fünf echte TradingView-CSV-Dateien | Pine↔JavaScript-Vergleich (erfordert verifizierte unabhängige Provenance) |
| Browser E2E | `python3 tests/browser_research_harness.py` | TOD-Layout, Read-only-Invarianten, deterministisches Rendering |
| Versionskonsistenz | Relay, README, Dashboard | alle drei Versionen vorhanden und identisch (fail-closed) |
| Secret Scan | Source-/Dokumentationsbaum | keine Credential-Werte |

Der Browser-Test respektiert `SYM_BROWSER_RUNS`. Schneller Smoke-Test:

```text
SYM_BROWSER_RUNS=1 python3 scripts/release_check.py
```

## Externe Grenzen

- Pine-v6-Kompilierung erfolgt in TradingView; die lokale Statikprüfung ist kein Compiler-Ersatz.
- Golden-Master-Dateien müssen echte, unabhängige TradingView/Pine-Exporte mit maschinenlesbarer Provenance (`provenance.json`) sein. Ein Generieren von `GM ... Score`-Werten mit der Dashboard-JavaScript-Engine und anschließender JS-Vergleich ist unzulässig. Parität ist erst bei unabhängig nachgewiesener Provenance belegt; ohne Provenance bleibt der Status `GOLDEN_MASTER_UNVERIFIED`.
- Historische Golden-Master-Parität beweist Rechengleichheit, nicht Markt-Edge.
- `MODEL_NO_EVIDENCE` blockiert jede Behauptung eines profitablen Modells.

## Paket

Nach einem Lauf ohne `FAIL`:

```text
python3 scripts/build_package.py --force
```

Der Builder nutzt eine Allowlist, erzeugt SHA-256 und führt Smoke-Tests in einer frischen Entpackung aus. `--force` überschreibt ausschließlich den Packaging-Guard bei `MODEL_NO_EVIDENCE`; es ändert weder Tests noch Verdict.
