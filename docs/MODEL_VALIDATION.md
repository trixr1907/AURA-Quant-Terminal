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

- $K$: Effektive Anzahl getesteter Parameter-Kombinationen / Trials (Standard: 18 Trials).
- $\gamma \approx 0.5772156649$: Euler-Mascheroni-Konstante.
- $DSR \ge 0.95$ (95% Konfidenzniveau) ist Mindestvoraussetzung fuer signifikanten Edge ueber dem Noise-Level.

---

## 3. Realistisches Kostenmodell & Intrabar-Policy

Simulierte Trades muessen realistische Marktfriktionen abbilden:

| Parameter | Bitget USDT-Futures Standard | Begruendung |
|---|---|---|
| **Maker-Gebuehr** | $0.02\%$ (2 bps) | Limit-Ausfuehrungen (z.B. TP1, TP2) |
| **Taker-Gebuehr** | $0.06\%$ (6 bps) | Market-Ausfuehrungen (Einstieg, SL, Timestop) |
| **Slippage** | $1.5 \text{ bps}$ ($0.015\%$) | Ausfuehrungsverzoegerung und Spread |
| **Funding-Rate** | Reale historische 8h-Rates | Finanzierungskosten offener Positionen |

### Intrabar-Kollisionsregel:
Treffen Stop-Loss (SL) und Take-Profit (TP) innerhalb derselben OHLC-Kerze ein, gilt ohne Vorliegen von Sub-Sekunden-Orderbook-Ticks die **konservative Policy: SL wird ausgeloest**. Die Annahme des profitabelsten Pfads ist streng verboten.

---

## 4. Modellstatus-Definitionen

| Status | Kriterien / Bedeutung |
|---|---|
| `MODEL_NO_EVIDENCE` | **Standardstatus.** Vollstaendige Softwaretests sind bestanden, aber es liegt noch kein statistisch ausreichender OOS-Live-Nachweis vor ($N < 30$ oder $DSR < 0.95$). **Kein Echtgeld-Handel erlaubt.** |
| `EVIDENCE_SUPPORTED` | Gilt nur, wenn Walk-Forward-OOS $N \ge 30$, Expectancy $\ge 0.15R$, Profit Factor $\ge 1.25$ und $DSR \ge 0.95$ auf verifizierten OOS-Daten nachgewiesen sind. |
| `MODEL_INVALID` | Backtest oder Replay weisen schwere statistische Fehler, Leaks oder gebrochene Invarianten auf. |
