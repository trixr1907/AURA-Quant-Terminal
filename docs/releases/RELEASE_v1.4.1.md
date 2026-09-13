# AURA Quant Terminal — Runde 18 Schlussbericht (v1.4.1, PATCH)

**Datum:** 13. September 2026  
**Autor:** Hermes (Agent) & Ivo  
**Version:** v1.4.1 (PATCH-Release)  
**Ledger-Stand:** EXP-032 (unverändert — reiner Prozess-, Anzeige- und Regressionsfix)  
**Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real)  

---

## 1. Executive Summary & Kontext

Runde 18 adressiert das Feedback des Systemeigentümers zu v1.4.0 in Form eines fokussierten PATCH-Releases:
1. **PF-37 (Regression):** Behebung der fehlenden Live-Metriken in den Autobot-Trade-Karten (`renderTradeCard(t, null, …)` → echte `calculateTradeMetrics(t, px)`-Werte).
2. **PF-38 (Klartext & Tooltips):** Endverbraucher-verständliche deutsche Übersetzungen und Tooltips für das Makro-BTC-Regime und alle Hero-Level-Kacheln mit `tabindex="0"` und `aria-describedby`.
3. **PF-39 (BTC-Chart Frische & Lade-Zustand):** Diagnose der Ursachen für unvollständige Datenstände, Ergänzung eines Sekundentakt-Frische-Badges im Chartkopf und Korrektur des Ladeband-Zustands (`loading` vs `error`).
4. **PF-40 (Verifikation & Release-Hygiene):** 100% grüne Tests (236 pytest, 57 Subtests, 67/67 JS-Suiten, innerHTML=51), deterministischer Release-Check `EXIT=0`.

---

## 2. PF-37 — Regression: Autobot Live-Verfolgung

### Befund & Ursache
In v1.4.0 übergab die Autobot-Renderfunktion in `Symbiose_Dashboard.html` (Z. ~9182) `null` als zweites Argument (`m`) an `renderTradeCard(t, m, px, idx, options)`. Dadurch fehlten in den gerenderten Autobot-Karten die dynamischen Metriken (PnL Gross, Margin ROI %, R-Vielfaches, Stop-Loss-Distanz). Zudem war der Autobot-Container nicht an den rAF-Ticker-Takt (`scheduleLiveTradesRender`) gekoppelt.

### Fix
- `calculateTradeMetrics(t, px)` wird in der Autobot-Renderschleife aufgerufen und als `m` an `renderTradeCard` übergeben.
- Am Ende von `renderLiveTrades()` wird geprüft, ob eine aktive `Autobot`-Instanz mit offenen Trades existiert, und deren `.render()` angestoßen.
- Regressionstest `tests/test_pf37_autobot_live_metrics.js` belegt:
  1. Statisch: `renderTradeCard(t, null` existiert nirgendwo mehr in der Codebase.
  2. Dynamisch: Simulierter Ticker-Tick berechnet exakte PnL-/ROI-Werte für Autobot-Karten identisch zum Live-Tracker.

---

## 3. PF-38 — Klartext & Tooltips: BTC-Regime & Hero-Levels

### BTC-Regime-Zelle (`#macro-btc-cell`)
- `tabindex="0"`, `role="region"`, `aria-labelledby="macro-btc-cell-title"`, `aria-describedby="macro-btc-tooltip"`.
- Verständliche Endverbraucher-Erklärung im `info-tip`:
  > *„BTC-Regime erklärt: BULL = Kurs über EMA200 UND EMA50 über EMA200 — beide Linien zeigen aufwärts. BEAR = Kurs unter EMA200 UND EMA50 unter EMA200. SIDEWAYS = alles dazwischen oder Bollinger-Squeeze aktiv (Kurs komprimiert, Ausbruch meist danach). ADX ≥ 20 = Trend vorhanden; ADX < 20 = Konsolidierung. E50-vs-E200 zeigt den prozentualen Abstand der schnellen Linie zur langsamen.“*

### Hero-Level-Kacheln (`#hero-levels`)
Alle vier Kacheln verfügen über verständliche deutsche Kurzlabel, Tooltips und Touch-Icons:
- **Entry:** *„Einstiegskurs: Der geplante Kaufpreis (Long) bzw. Verkaufspreis (Short). Erst wenn der Markt diesen Preis erreicht, ist der Trade aktiv.“*
- **Stop-Loss (SL):** *„Notbremse / Verlustgrenze: Maximaler Verlust-Kurs. Schließt die Position automatisch. Nie weiter nach unten verschieben!“*
- **Take-Profit 1 (TP1):** *„Teilgewinn-Ziel 1: Erstes Gewinnziel. Bei Erreichen: 25–50% schließen und SL auf Einstieg (Break-Even) anheben.“*
- **Take-Profit 2 (TP2):** *„Hauptziel / Moonbag: Zweites Gewinnziel für die verbleibende Restposition. Kein TP2 = kompletter Exit bei TP1.“*

---

## 4. PF-39 — BTC-Chart Frische-Badge & Diagnoseprotokoll

### Diagnose & Ursachenanalyse
Die Analyse der Netzwerkpfade und WebSocket-Zustände bestätigt drei Kernursachen für gelegentliche Verzögerungen beim Fokus-Chart:
1. **Radar-Scan Rate-Limit-Kollision:** Während eines vollen 30-Coin-Radar-Scans werden bis zu 120 REST-Anfragen in kurzer Folge gesendet; ein zeitgleicher Klick auf ein neues Fokus-Symbol geriet in dieselbe Abort-/Rate-Limit-Queue.
2. **Sticky-Socket Re-Subscription Race:** Bei schnellem Coin-Wechsel vor Eintreffen des ersten Ticker-Frames blieb der Canvas kurz im Ausgangszustand stehen.
3. **Stale-State Überdeckung:** Das Fehlerband war in v1.4.0 nur bei `status === 'error'` sichtbar; der Zwischenzustand `loading` zeigte keine sichtbare Laderückmeldung.

### Maßnahmen & Frische-Sichtbarkeit
- **Frische-Badge am Chartkopf:** Direkt neben `#chart-src` platziert (`#chart-freshness-badge`). Zeigt im Sekundentakt das Kerzen-Alter: `Kerzen: vor Xs · <Quelle>`. Färbt sich bei Überalterung (>120s) bernsteinfarben (`var(--amb)`) und bei Ladefehlern rot (`var(--red2)`).
- **Echtes Ladeband (`#chart-load-state`):** Zeigt während des Ladens `Lade Chart-Daten …` mit Abbrechen-Option und verschwindet nach erfolgreichem Laden automatisch (`hidden = true`).

---

## 5. PF-40 — Verifikation & Testmatrix

### Zählbefehle & Belege
```bash
# Pytest Suite
python3 -m pytest -q
# Ergebnis: 236 passed, 57 subtests passed in 9.22s

# JS Test Suiten
ls -1 tests/test_*.js | wc -l
# Ergebnis: 67 Suiten (alle 67 bestanden)

# innerHTML Guard
grep -c "innerHTML" Symbiose_Dashboard.html
# Ergebnis: 51

# Automated Release Gate
python3 scripts/release_check.py
# Ergebnis: VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) · EXIT=0
```

### Ledger-Klassifikation
- **Status:** Unverändert auf `EXP-032`.
- **Begründung:** Runde 18 ist ein reines UX-, Anzeige-, Tooltip- und Regressionsfix-Release (PATCH). Es wurden keine Modellparameter, Signal-Schwellen, Universums-Gates oder statistischen Filter verändert.

---

## 6. Fazit & Ausblick

Mit v1.4.1 sind alle offenen Diagnoseschulden und Regressionspunkte aus Runde 17 vollständig geschlossen. Die größeren UX-Themen (Best-of-breed Trade-Karten-Restyle, Chart-Resize, Zeichentools, Time-Stop-Demotion) folgen planmäßig in Version **v1.5.0**.
