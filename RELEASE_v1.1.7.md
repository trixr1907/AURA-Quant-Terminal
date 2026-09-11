# AURA v1.1.7 — Setup Discovery, Edge-Auswahl & Radar-Ranking

**Release-Version:** `v1.1.7`  
**Datum:** 2026-09-11  
**Typ:** Feature & Usability Release (Setup Discovery & Edge Cockpit)  
**Status:** Verifiziert & Bereit  

---

## 1. Release-Zusammenfassung & Modell-Status

- **Modell-Status:** `MODEL_NO_EVIDENCE (real)` — Reale Golden-Master-Fixtures (BTC, ETH, SOL, XRP, DOGE) weisen DSR < 0.5 auf; die Software ist deterministisch abgesichert und blockiert unbewiesene Signale fail-closed.
- **Wesentliche Neuerungen in v1.1.7:**
  1. **Hero Top-Setups Quick-Picks:** Interaktive 1-Klick-Chips für die bis zu 4 stärksten Radar-Kandidaten direkt in der Hero-Fußzeile (`#hero-source`). Ein Klick lädt sofort den stärksten Timeframe und startet die 1.500-Kerzen Walk-Forward-Backtest- und Kelly-Edge-Berechnung.
  2. **Smarte 3-Stufen Radar-Gruppierung:** Klare und transparente Trennung im 🎯 Top-Edge-Modus in:
     - `🔥 Hot Setups (Ausführbar)`: Alle technischen Gates grün (MTF $\ge 3/4$, ADX $\ge 20$, kein Squeeze, passendes Regime, kein BTC-Block).
     - `🎯 Top Setup-Kandidaten`: Starkes Signal & hohes MTF-Alignment, wartet auf finale Bestätigung/Ausbruch.
     - `👀 Watchlist & Universum`: Der übrige Markt.
  3. **Aussagekräftiger Signal-Score im Radar:** In der Gesamtansicht (`all`) zeigt die Score-Spalte den tatsächlichen Score des stärksten Timeframes inklusive Timeframe-Tag (z. B. `86.0 (4h)`) statt des verwässerten 4-TF-Durchschnitts.
  4. **Strikte TDD-Testabdeckung:** Neuer Test `tests/test_radar_top_candidates.js` in `scripts/release_check.py` integriert; vollständige Suite mit 121 Engine-Tests, 165 Pytest-Tests und Browser-E2E-Checks verifiziert (`PASS`).

---

## 2. Artefakte & Versionierung

- **Release-Version:** `v1.1.7`
- **Synchronisierte Komponenten:** `VERSION`, `bitget_relay.py`, `Symbiose_Dashboard.html`, `SYMBIOSE_Tutorial.html`, `Symbiose_Signal_System_v1.pine`, `README.md`, `START.bat`, `START_OHNE_GUI.bat`, `docs/architecture.md`, `claims.csv`
