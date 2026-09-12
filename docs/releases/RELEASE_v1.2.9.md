# AURA v1.2.9 — Confluence Terminal (read-only research)

Datum: 2026-09-12

## Inhalt

- F-05: Phase-D-DSR verwendet eine durch die Ledger-Hashkette verifizierte historische Trial-Zahl. Der effektive Wert ist `max(45, total_model_experiments)`, damit die neue Rechnung niemals weniger konservativ als der alte Phase-D-Gesamtsuchraum ist.
- F-06: SHA-256-Kette über kanonische JSONL-Einträge, gebunden an den unveränderlichen v1.2.8-Ledger-Snapshot. `scripts/verify_ledger.py` ist fail-closed in `scripts/release_check.py` integriert.
- F-16: Pine exportiert künftig CVD, EMA-CVD, den booleschen Vergleich und Volumendelta im Data Window. Die bestehenden Golden-Master-Dateien enthalten diese Pine-Zustände nicht; deshalb wird ohne neuen TradingView-Export kein erfundener Driftwert berichtet.
- Versionierung und Paketmetadaten auf 1.2.9 synchronisiert.

## Integritätsurteil

`SOFTWARE_GO / MODEL_NO_EVIDENCE`

Die Änderungen härten die Modellintegrität. Sie belegen keinen statistischen Edge und ersetzen keinen echten OOS-Nachweis.
