# AURA Data Foundation — Audit & Provenance Report

**Stand:** 2026-09-14T23:15:04Z  
**Audit-Tool:** `scripts/data_foundation_audit.py`  
**Schwellenwert WF-Tauglichkeit:** $N = 1000$ abgeschlossene Kerzen ($n \ge N$)  

---

## 1. Überblick & Zusammenfassung

Das Daten-Fundament von AURA wurde einem vollautomatisierten, deterministischen Audit unterzogen. Jede Datenquelle wird strikt nach expliziter Provenienz (CSV-Spalte oder bekannte Fixture-Metadaten) klassifiziert. Es werden keine Vermutungen über die Herkunft angestellt.

| Metrik | Wert |
|---|---|
| **Geprüfte Dateien gesamt** | 6 |
| **Kerzen gesamt** | 64.860 |
| **Reale Datensätze (REAL)** | 5 |
| **Synthetische Datensätze (SYNTHETIC)** | 0 |
| **Unbekannte Datensätze (UNKNOWN)** | 1 |
| **Walk-Forward tauglich ($n \ge 1000$)** | 5 |

---

## 2. Detaillierte Audit-Tabelle der Standard-Fixtures

Die folgenden Zahlen stammen direkt aus der Ausführung von `python3 scripts/data_foundation_audit.py`:

| Symbol | TF | Kerzen gesamt | Kerzen geschl. | Start (UTC) | Ende (UTC) | Lücken | Duplikate | Null/0 | Outlier | Provenienz | WF ($n \ge 1000$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **BTCUSDT** | 1h | 14.773 | 14.773 | 2025-01-01T00:00:00Z | 2026-09-08T12:00:00Z | 0 | 0 | 0 | 0 | **REAL** | **JA** |
| **DOGEUSDT** | 4h | 10.270 | 10.270 | 2022-01-01T00:00:00Z | 2026-09-08T12:00:00Z | 0 | 0 | 0 | 0 | **REAL** | **JA** |
| **ETHUSDT** | 1h | 14.773 | 14.773 | 2025-01-01T00:00:00Z | 2026-09-08T12:00:00Z | 0 | 0 | 0 | 0 | **REAL** | **JA** |
| **SOLUSDT** | 1h | 14.773 | 14.773 | 2025-01-01T00:00:00Z | 2026-09-08T12:00:00Z | 0 | 0 | 0 | 0 | **REAL** | **JA** |
| **XRPUSDT** | 4h | 10.270 | 10.270 | 2022-01-01T00:00:00Z | 2026-09-08T12:00:00Z | 0 | 0 | 0 | 0 | **REAL** | **JA** |
| **sample_valid** | unk | 1 | 1 | 2024-01-01T00:00:00Z | 2024-01-01T00:00:00Z | 0 | 0 | 0 | 0 | **UNKNOWN** | **NEIN** |

---

## 3. SHA-256 Integritäts-Hashes der Golden Fixtures

Jede Fixture wird kryptographisch über ihren SHA-256-Prüfsummenwert verifiziert:

- `BTCUSDT_1h.csv`: `460a1aee5a7e7939b74e12082726870adcf1d5731801a1f9b3123d29f72fee14` (Spanne: 615,5 Tage)
- `DOGEUSDT_4h.csv`: `e18145b07db79bd8d476965e79a8af62b0436fccbf6dd9add7e223366d791721` (Spanne: 1711,5 Tage)
- `ETHUSDT_1h.csv`: `298c417d267e2e49759a3f34ee5af14911d6a07545e15004b007b71d77dd6f46` (Spanne: 615,5 Tage)
- `SOLUSDT_1h.csv`: `05c8b33d148b1ed2a4f0d0e2f33aaecb8b9262cc2959f7f6a6a5f1db14e5bb9a` (Spanne: 615,5 Tage)
- `XRPUSDT_4h.csv`: `6f2141598ea64cf762148877d92b72c18348bf9fda49b23e4a8c16da942fa465` (Spanne: 1711,5 Tage)
- `sample_valid.csv`: `5358e14dcf3d5faa02d433be88917575ba799bc8dbe0be3546db7bd77be35289` (Spanne: 0,0 Tage)

---

## 4. Audit-Methodik & Validierungsregeln

1. **Keine synthetische Verwechslung:** Daten ohne explizite Realkennzeichnung oder aus Test-Generatoren werden niemals als `REAL` eingestuft.
2. **Lückenfreiheit & Zeitachsen-Monotonie:** Die Zeitstempel müssen monoton steigend sein und der deklarierten Timeframe-Schrittweite entsprechen. Keine Lücken ($0$), keine Duplikate ($0$).
3. **Plausibilität & Outlier-Schutz:** Jede Kerze muss $H \ge \max(O, C)$, $L \le \min(O, C)$, $V \ge 0$ und positive Preise erfüllen. Extreme Ausreißer (> 500% Sprung ohne Marktkontext) werden geflaggt.
4. **Walk-Forward Mindestgröße:** $N = 1000$ abgeschlossene Kerzen sind zwingend erforderlich, um statistisch signifikante $K \ge 4$ Fold-Splits ohne Look-Ahead-Bias durchzuführen.
