# AURA v3 — Modell-Validierung & Statistische Evidenz (MODEL_VALIDATION.md)

**Status:** Kanonisch v3.0 · **Datum:** 2026-09-17 · **Geltung:** Verbindlich fuer alle Backtests, Optimierungen und Modellstatus-Deklarationen

---

## 1. Validierungsprotokoll & Trennungsprinzip

Zur Vermeidung von Overfitting, Selection Bias und Multiple-Testing-Illusionen gilt fuer alle Quant-Modelle in AURA:

1. **Strikte Daten-Splits:**
   - **In-Sample (Train):** Historische Daten zur Parameter-Findung.
   - **Out-of-Sample (Validation / Walk-Forward):** Folds zur Pruefung von Generalisierung und PAVA-Kalibrierung.
   - **Holdout Lockbox:** Unangetasteter Datensatz fuer die finale Abnahme. Nach Einsicht verliert die Lockbox ihren unberuehrten Status.
2. **t1-Safe Walk-Forward:**
   - Keine Zukunftsdaten im Trainingssatz.
   - Zwischen Trainingsende und Teststart liegt ein Sicherheitsabstand ($\ge 1$ Bar), um ueberlappende Trade-Labels auszuschliessen.
3. **Kein Zuruecksetzen des Ledgers:**
   - Alle registrierten Hypothesen und Experimente (EXP-001 bis EXP-032) bleiben unveraendert erhalten.
   - Fehlversuche werden vollstaendig mitgezaehlt.

---

## 2. Deflated Sharpe Ratio (DSR) & Trial-Zaehlung

Nach Bailey & López de Prado (2014) sinkt die statistische Signifikanz einer Strategie mit der Anzahl der durchgefuehrten Versuche (Multiple Testing):

$$SR^* = \sqrt{\frac{\mathbb{V}[\widehat{SR}]}{N-1}} \left( (1-\gamma) \Phi^{-1}\left(1 - \frac{1}{K}\right) + \gamma \Phi^{-1}\left(1 - \frac{1}{K \cdot e}\right) \right)$$

$$DSR = \Phi\left( \frac{\widehat{SR} - SR^*}{\sqrt{\mathbb{V}[\widehat{SR}]}} \right)$$

- $K$: Effektive Anzahl getesteter Parameter-Kombinationen / Trials. `18` ist derzeit lediglich der Kompatibilitaets-Default der API; fuer eine Evidenzpruefung muss $K$ die konkrete Suchfamilie und das unveraenderte Experiment-Ledger konservativ abdecken.
- $\gamma \approx 0.5772156649$: Euler-Mascheroni-Konstante.
- Ein hoher DSR-Wert ist nur eine notwendige Diagnose, kein hinreichender Modellbeweis.

### Aktueller Implementierungsstatus

Die aktuelle `WalkForwardOptimizer`-Komponente simuliert eine feste Konfiguration auf OOS-Folds. Sie fuehrt weder eine train-only Parametersuche noch einen versiegelten finalen Lockbox-Test aus. Deshalb gibt sie unabhaengig von Kennzahlen ausschliesslich `MODEL_NO_EVIDENCE` zurueck. Die PAVA-Funktion ist separat implementiert, wird in dieser Pipeline aber noch nicht train-only/OOS-sicher angewendet.

---

## 3. Realistisches Kostenmodell & Intrabar-Policy

Simulierte Trades muessen realistische Marktfriktionen abbilden:

| Parameter | Bitget USDT-Futures Standard | Begruendung |
|---|---|---|
| **Maker-Gebuehr** | $0.02\%$ (2 bps) | Konfigurationsannahme fuer simulierte Limit-Ausfuehrungen; kein garantierter individueller Kontotarif |
| **Taker-Gebuehr** | $0.06\%$ (6 bps) | Konfigurationsannahme fuer simulierte Market-Ausfuehrungen; kein garantierter individueller Kontotarif |
| **Slippage** | $1.5 \text{ bps}$ ($0.015\%$) | Eigene konservative Simulationsheuristik, keine von Bitget veroeffentlichte feste Gebuehr |
| **Funding-Rate** | NICHT IMPLEMENTIERT | Dokumentierter Pflichtpunkt; Runner und Backtester buchen derzeit kein Funding |

**Zeitliche Gueltigkeit und Quelle:** Die 2/6-bps-Werte sind als beobachtete Bitget-Basistarif-Annahme fuer USDT-Futures dokumentiert, aber in dieser Abnahme nicht belastbar aus einer versionierten, maschinenlesbaren Tarifquelle mit Gueltigkeitszeitraum verifiziert. Die oeffentliche Bitget-Gebuehrenseite wurde am 2026-09-17 abgerufen, lieferte im Extrakt jedoch keine belastbare Tariftabelle. Vor einer Modellabnahme muessen Tarif, VIP-Stufe und Vertrag pro Lauf als Provenienz gespeichert werden.

Das Altmodell `0.10% / 0.10% / 0.10%` stammt aus `headless_autobot.js` (`makerFee`, `takerFee`, `slippage` jeweils `0.001`) und war eine konservative Produktannahme, kein nachgewiesener Bitget-Tarif. Die Umstellung auf `0.02% / 0.06% / 0.015%` ist deshalb eine Aenderung der Simulationsannahmen und darf nicht als reine Fehlerkorrektur oder als Edge-Beweis behandelt werden.

### Intrabar-Kollisionsregel:
Treffen Stop-Loss (SL) und Take-Profit (TP) innerhalb derselben OHLC-Kerze ein, gilt ohne Vorliegen von Sub-Sekunden-Orderbook-Ticks die **konservative Policy: SL wird ausgeloest**. Die Annahme des profitabelsten Pfads ist streng verboten.

---

## 4. Modellstatus-Definitionen

| Status | Kriterien / Bedeutung |
|---|---|
| `MODEL_NO_EVIDENCE` | **Standardstatus.** Softwaretests koennen bestanden sein, ohne dass eine vorab registrierte, versiegelte und unabhaengige Modellabnahme vorliegt. Eine universelle Mindestzahl von 30 Trades wird nicht behauptet. **Kein Echtgeld-Handel erlaubt.** |
| `EVIDENCE_SUPPORTED` | Darf erst nach einem separat vorab registrierten Protokoll, begruendeter Power-/Sample-Planung, vollstaendiger Trial-Provenienz, train-only Auswahl, OOS-Auswertung und unangetasteter finaler Lockbox vergeben werden. Die aktuelle WFO-Komponente kann diesen Status nicht erzeugen. |
| `MODEL_INVALID` | Backtest oder Replay weisen schwere statistische Fehler, Leaks oder gebrochene Invarianten auf. |
