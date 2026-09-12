# AURA v1.2.12 — Confluence Terminal (read-only research)

Datum: 2026-09-12

## Inhalt

- **PF-8 (Autobot Scan Reentrancy-Guard & Deduplikation):**
  - Instanz-Flag `_scanInProgress` verhindert überlappende, unkoordinierte Scans aus Start-Button und `tick()`-Intervall (Zweitaufruf gibt sofort `null` zurück, ohne Funnel-Status zu überschreiben).
  - Synchronisierung des Start-Button-Triggers (`lastScanAt = Date.now()`).
  - Zweiter Deduplikations-Recheck unmittelbar vor Trade-Push nach Abschluss aller asynchronen Analysen (`await fetchKlines`, `analyze`, `runWalkForwardBacktest`).
- **PF-9 (Ehrliche KPI-Labels):**
  - Umbenennung des Autobot-KPIs „Realisierter PnL" zu „PnL gesamt (offen + realisiert)".
  - Ergänzung der Win-Rate-Bezeichnung zu „Win-Rate (realisiert) / Trades".
- **PF-10 (Verifikation & Release-Gates):**
  - 51 Node.js-Testsuiten (inkl. `tests/test_autobot_scan_reentrancy.js`) und vollständige pytest-Suite (216/57) grün.
  - `innerHTML`-Budget exakt bei 51 Vorkommen gehalten.
  - Release-Gate: `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Exit 0).
