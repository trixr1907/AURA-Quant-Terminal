# OpenHands Task Brief — Runde 36 / AURA v2.2.0

## Ziel

Drei belegte Evidence-Infrastrukturfehler minimal und ohne Trading-Strategie-Änderung schließen:

1. F4: Dashboard-Walk-Forward darf Slippage nicht stillschweigend als 0 berechnen.
2. F5: Ein echter `NO-GO` darf nicht durch `MODEL_NO_EVIDENCE` maskiert werden.
3. F1: DSR-Trial-Zahl muss konservativ mit dem verifizierten kumulativen Ledger-N wachsen.

Arbeite strikt in vertikalen RED→GREEN-Slices. Pro Slice zuerst Regressionstest schreiben und mit dem erwarteten Fehler ausführen, dann minimalen Produktfix, dann gezielten Test erneut ausführen. Keine unabhängigen Slices parallel bearbeiten.

## Workspace und Schutzregeln

- Host-Repo: `/home/ivo/projects/AURA_Quant_Terminal`
- Sandbox-Repo: vor Edit selbst per `pwd`, Branch, `git rev-parse HEAD` und SHA-256 von `VERSION` verifizieren.
- Branch: `feat/round36-v2.2.0-evidence-infra`
- Start-Commit: `d62543fdf8bc49a1aa5a8ae8ac946c8304a01cf1` (`v2.1.0`)
- Vorhandene uncommittete Datei dieses Briefs erhalten: `docs/research/OPENHANDS_TASK_BRIEF_ROUND36.md`.
- Verboten: `git checkout`, `git restore`, `git reset`, `git clean`, pauschales `rm`, Reformatierung ganzer Dateien, Commit, Push, Tag, Release oder Deploy.
- `docs/research/trials_ledger_chain.jsonl` und `ledger_checkpoint.json` nicht ändern.
- Keine Lockbox auswerten. Keine Entry-/Exit-/Gate-/Score-/Sizing-Logik ändern. Nur Slippage-Kostenbug, Verdict-Priorität und DSR-Trial-Accounting.
- `innerHTML`-Vorkommen im Dashboard müssen 63 bleiben.
- Code-Kommentare Englisch; bestehender Projektstil.

## Verifizierter Ausgangszustand

- `VERSION`: `2.1.0`
- `python3 -m pytest -q`: `472 passed, 69 subtests passed`
- dynamische JS-Discovery: `92/92` Dateien grün
- `python3 scripts/release_check.py`: Exit 0, `SOFTWARE_GO / MODEL_NO_EVIDENCE`
- `python3 scripts/verify_ledger.py`: EXP-032, Chain-Head `ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b`, `total_model_experiments=10`
- Dashboard: 63 Literalvorkommen `innerHTML`

## Slice F4 — Slippage P0

### RED

Neue Tests:

- `tests/test_slippage_not_zero.js`: echten Dashboard-Engine-Slice aus dem eingecheckten `Symbiose_Dashboard.html` in isoliertem Node-VM-Kontext ausführen. Belegen, dass eine Walk-Forward-/Simulationsberechnung mit Default-Kosten Slippage >0 nutzt und dass Netto-R mit Gebühren/Slippage kleiner als die identische Brutto-/Nullkostenberechnung ist. Keine reine String-Prüfung als einziger Verhaltensbeleg.
- `tests/test_slippage_assigned.py`: Dashboard-Quelle prüfen: App-Default exakt `0.0005`, mindestens eine `App.slippage = ...`-Zuweisung beim Spec-Laden, Null/fehlende Spec-Slippage fällt auf `0.0005` zurück; alle bekannten WF-Aufrufe reichen eine gültige Slippage weiter.

Beide neuen Tests vor Produktfix einzeln ausführen und erwartetes Rot dokumentieren.

### GREEN

Minimal in `Symbiose_Dashboard.html`:

- `App.slippage` initial `0.0005` statt `0`.
- Beim Laden von Contract-Specs: `App.slippage = spec.slippage ?? 0.0005` beziehungsweise semantisch gleichwertig, wobei 0 als ungültig behandelt wird.
- Der Spec-Parser darf optional `slippage` liefern, muss aber ohne Feld bei `0.0005` bleiben.
- `evaluateTimeStopOptions` und alle WF-Pfade müssen 0/undefined/null fail-safe auf `0.0005` normalisieren. Keine Änderung der Gebührenwerte.

Gezielte Tests danach grün; `node --check` auf extrahiertem Dashboard-Script.

## Slice F5 — Verdict-Priorität P1

### RED

Neue Datei `tests/test_verdict_aggregation_masks_no_go.py`:

- `compute_verdict([{status: "NO-GO"}, ...], model_no_evidence=True)` ergibt `NO-GO`.
- Nur PASS-Status plus `model_no_evidence=True` ergibt weiterhin `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
- FAIL bleibt höchste Priorität.

Vor Fix gezielt ausführen und erwartetes Rot belegen.

### GREEN

In `scripts/release_check.py` nur Priorität korrigieren:

1. `FAIL`
2. `NO-GO`
3. `SOFTWARE_GO / MODEL_NO_EVIDENCE`
4. übrige bestehende Zustände

Gezielten Test grün ausführen. Zusätzlich einen echten Funktionsaufruf mit injiziertem `NO-GO` ausgeben.

## Slice F1 — Ledger-N im DSR P2

### Wichtiger Ist-Befund

Der kanonische Checkpoint liegt im Repo-Root (`ledger_checkpoint.json`), nicht unter `docs/research/`, und enthält aktuell nur `schema_version`, `last_entry_id`, `entry_count`, `chain_head`. Der verifizierte Zähler `total_model_experiments=10` kommt aus `scripts/verify_ledger.py`. Deshalb weder einen nicht existierenden Pfad voraussetzen noch den Checkpoint/die Kette für diesen Release mutieren. Nutze den bereits verifizierten Ledger-Pfad oder einen klar benannten eingebetteten, testgekoppelten Wert für den self-contained Browser; fail-safe Untergrenze 10, produktive Untergrenze 18.

### RED

`tests/test_dsr_ledger.js` erweitern:

- bisherige Archiv-Assertions behalten;
- Dashboard enthält `loadVerifiedLedgerTrials`, `LEDGER_TRIALS`, `DSR_TRIALS` und `Math.max(currentSearchTrials, DSR_TRIALS)`;
- Dashboard-Verhalten: bei festem Returns-Vektor und höherem Ledger-N darf DSR nie steigen;
- `tests/model_evidence_real.js` nutzt `Math.max(wf?.totalTrials || 18, DSR_TRIALS)` oder semantisch exakt gleichwertig.

Python-Test ergänzen oder bestehendes Orakel so erweitern, dass `load_ledger_trials()` den verifizierten Ledger-Zähler 10 liefert und `max(18, ledger_trials)` gilt. Vor Produktfix gezielt Rot belegen.

### GREEN

- `tests/reference_backtest.py`: `load_ledger_trials()` auf dem echten verifizierten Ledger-Zustand; DSR-Aufrufe konservativ mit `max(18, ledger_trials)` statt fixem 18. Kein stilles Akzeptieren manipulierter Ledger-Evidenz.
- Dashboard: self-contained/browserfähiger Loader mit `LEGACY_DSR_TRIALS = 18`, Ledger-N und `DSR_TRIALS = Math.max(LEGACY_DSR_TRIALS, LEDGER_TRIALS)`; im WF `currentSearchTrials` berechnen und `totalTrials = Math.max(currentSearchTrials, DSR_TRIALS)`.
- `tests/model_evidence_real.js`: denselben DSR-Trial-Floor anwenden. Keine Änderung von Acceptance-Schwellen.

## Release- und Doku-Slice

Nach den drei funktionalen Slices:

- `VERSION` und alle kanonisch geprüften Versionsflächen auf `2.2.0` synchronisieren.
- `CHANGELOG.md` mit R36/F4/F5/F1 aktualisieren.
- `docs/architecture.md`: Dashboard Default `maker 0.0002`, `taker 0.0006`, `slippage 0.0005`; Shadow/Runner bewusst weiterhin `0.001/0.001/0.001`, daher nicht direkt mit S3 vergleichbar.
- `docs/research/EVIDENCE_PROTOCOL.md`: S3 nutzt mindestens `max(18, total_model_experiments)` und produktiv `max(currentSearchTrials, DSR_TRIALS)`.
- `docs/releases/RELEASE_v2.2.0.md`: Grund, Scope, Non-Goals, Tests und unveränderte Evidence-Identität. Keine erfundenen finalen SHAs, CI-, Asset- oder Deploy-Belege eintragen; unbekannte Live-Belege als offen markieren.
- Packaging-Manifest (`scripts/build_package.py`) auf Release-Report v2.2.0 aktualisieren, wenn dies die bestehende Versionskonvention verlangt.
- Dashboard Release Notes für 2.2.0 minimal aktualisieren.

## Pflichtverifikation vor Übergabe

- neue F4/F5/F1-Tests grün
- `python3 -m pytest -q`
- alle dynamisch entdeckten `tests/test_*.js` einzeln; Failures pro Datei erfassen
- Dashboard-Script extrahieren und `node --check`
- `python3 scripts/verify_ledger.py`
- `python3 scripts/release_check.py` Exit 0 und Verdict `SOFTWARE_GO / MODEL_NO_EVIDENCE`
- `python3 scripts/build_package.py`
- `grep -o 'innerHTML' Symbiose_Dashboard.html | wc -l` ergibt 63
- `git diff -- docs/research/trials_ledger_chain.jsonl ledger_checkpoint.json` leer

Am Ende nur geänderte Dateien, RED-/GREEN-Befehle mit echten Ergebnissen, Rest-Risiken und Blocker melden. Nicht committen.
