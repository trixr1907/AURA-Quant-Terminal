# AURA v1.2.5 — Native TradingView Drawing Tool Assist & Zero Indicator Slots

## Überblick

AURA v1.2.5 bindet das **native TradingView Zeichentool „Long-Position" & „Short-Position"** (aus der linken Werkzeugleiste unter *Prognosen*) über ein interaktives HUD ein, **ohne einen einzigen Indikator-Platz auf dem Chart zu verbrauchen**.

---

## Highlights in v1.2.5

### 1. 📐 Natives TradingView Zeichentool Assist (0 Indikator-Plätze)
* **Keine Indikator-Verschwendung:** Statt einen kostbaren Indikator-Slot mit einem Pine-Skript zu blockieren, nutzt AURA das native TradingView-Zeichentool (Long-Position / Short-Position).
* **Interaktives Quick-Copy HUD:** Klickt man bei einem aktiven Trade auf **`📐 TV Zeichentool`**, öffnet sich ein kompaktes Overlay mit:
  * **Einstiegspreis (Entry):** 1-Klick-Kopieren.
  * **Gewinnziel (Take Profit):** 1-Klick-Kopieren mit % und Dollar-Ertrag.
  * **Stopp-Loss (SL):** 1-Klick-Kopieren mit % und Risiko.
  * **Positionsgröße & CRV:** Exakte Hebel- und Notional-Angaben.
* **Paper Trading Order-Export:** 1-Klick-Export für das TradingView Paper-Trading Panel, wodurch TradingView die Positionen und Bracket-Linien (SL/TP) vollautomatisch und nativ auf den Chart zeichnet.

---

## Verifikationsstatus
- `pytest` Suite: **50/50 Tests bestanden**.
- `node tests/test_tradingview_position_bridge.js`: **PASS**.
- `python3 tests/pine_static_check.py`: **OK** (0 Fehler, reine Signal-Engine).
- `scripts/release_check.py`: **SOFTWARE_GO**.
