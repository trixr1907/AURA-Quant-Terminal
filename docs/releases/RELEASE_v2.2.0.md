# AURA v2.2.0 — Evidence Infrastructure Hardening

## Zusammenfassung

AURA v2.2.0 (MINOR) schließt drei extern bestätigte Abweichungen in der Evidenz-Infrastruktur: fehlende Dashboard-Slippage, maskierbare NO-GO-Verdicts und eine nicht an den Forschungs-Ledger gebundene DSR-Trial-Zahl. Signal-, Entry-, Exit-, Gate-, Scoring- und Sizing-Logik bleiben unverändert; einzige Rechenänderung ist die Korrektur der zuvor fehlenden Slippage-Kosten.

## F4 — Slippage-Korrektur

- `App.slippage` startet bei `0.0005` statt `0`.
- Contract-Specs werden vor der kostenabhängigen Walk-Forward-Auswertung geladen.
- Positive `spec.slippage` wird übernommen; fehlende, ungültige oder null Slippage fällt auf `0.0005` zurück.
- Alle produktiven Walk-Forward-Pfade normalisieren Slippage über denselben Resolver.
- Regressionstest belegt: Netto-R mit Gebühren und Slippage ist kleiner als Brutto-R ohne Kosten.

Warum: Der alte Nullwert wurde durch Nullish-Coalescing als gültig behandelt. Dadurch rechnete das Dashboard trotz dokumentierter Kostenannahme ohne Slippage.

## F5 — Verdict-Aggregation

- Priorität: `FAIL` vor `NO-GO` vor `MODEL_NO_EVIDENCE`.
- Derselbe Blocker-Status wird in JSON, Exit-Code und menschenlesbarer Summary verwendet.
- Injiziertes `NO-GO` plus `model_no_evidence=True` bleibt `NO-GO`.
- Ohne echten Blocker bleibt der aktuelle Zustand `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

Warum: Fehlende Modell-Evidenz ist kein Ersatz für einen härteren Software- oder Gate-Blocker.

## F1 — Ledger-N im DSR-Gate

- Relay verifiziert den Ledger und bettet `total_model_experiments` beim Ausliefern in das Dashboard ein.
- Produkt-Floor: `DSR_TRIALS = max(45, total_model_experiments)`.
- Universe-/Search-DSR: `totalTrials = max(currentSearchTrials, DSR_TRIALS)`.
- `tests/model_evidence_real.js` und `tests/reference_backtest.py` verwenden dieselbe konservative Trial-Familie.
- Ungültiger Ledger blockiert Dashboard-Auslieferung und Evidence-Harness fail-closed.
- Monotonie-Test belegt: Mehr Trials verbessern den DSR nicht.

Warum: Historische Modellversuche müssen in die Multiple-Testing-Korrektur eingehen, dürfen aber einen bereits größeren aktuellen Suchraum nie verkleinern.

## Kostenmodell und bewusste Nicht-Ziele

| Evidenzpfad | Maker | Taker | Slippage |
|---|---:|---:|---:|
| Dashboard / S3 | 0,02 % | 0,06 % | 0,05 % |
| Shadow / Headless Runner | 0,10 % | 0,10 % | 0,10 % |

R36 korrigiert ausschließlich den 0-%-Slippage-Bug im Dashboard. Eine vollständige Vereinheitlichung der S3-/S5-Kosten würde Fixtures und Modellbewertung verändern und bleibt R37 vorbehalten. Ebenfalls deferred: 90-Tage-Evidence-Decay/S6, Lockbox-Erweiterungen, Claims-Zeiger und DSR-Neutralwert.

## Integritätsinvarianten

- Ledger: `EXP-032`
- Chain-Head: `ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b`
- `total_model_experiments`: `10`
- Lockbox: `UNUSED`
- Erwartetes Release-Verdict: `SOFTWARE_GO / MODEL_NO_EVIDENCE`
- `innerHTML`: `63 -> 63`
- Keine neue Runtime-Datei; neue Dateien sind Tests und Release-Dokumentation.

## Verifikation

Die finale Beweiskette wird nach dem Merge aus den realen Gate-Ausgaben ergänzt bzw. über GitHub CI, Release-Asset und Deploy-Nachweis referenziert. Pflicht-Gates:

- `python3 -m pytest -q`
- alle selbstlaufenden `tests/test_*.js`
- `node --check` auf dem extrahierten Dashboard-Script
- `python3 scripts/verify_ledger.py`
- `python3 scripts/release_check.py`
- Packaging-/Asset-Hashprüfung nach Download vom GitHub Release
