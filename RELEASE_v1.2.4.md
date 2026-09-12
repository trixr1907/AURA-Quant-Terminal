# AURA v1.2.4 — 1:1 Position Tool Precision & Paper Trade Unlock

## Überblick

AURA v1.2.4 trennt das **1:1 TradingView Long/Short Position Tool** sauber als dedizierten, eigenständigen Generator für aktive Trades ab, schaltet die **Paper-Trade-Ausführung vollständig frei** und optimiert den **TradingView Desktop Protocol Dispatch** für einen fehlerfreien Workflow auf Desktop- und Web-Ebene.

---

## Highlights in v1.2.4

### 1. 📐 1:1 TradingView Long/Short Position Tool (Dediziert pro Trade)
* **Keine Überlagerung im Hauptindikator:** Das Pine Script `Symbiose_Signal_System_v1.pine` bleibt schlank und fokussiert auf die Confluence Signal Engine & Alerts.
* **1:1 Position-Tool bei Bedarf:** In der Trade-Liste („Aktive Trades“) generiert der Button **`📐 1:1 TV Position Tool`** ein eigenständiges, perfektes TradingView v6 Script:
  * **Long-Position Tool (Solution 43000517002):** Grüne Gewinnzone (`#089981`), rote Stop-Loss-Zone (`#f23645`), Einstiegslinie, R:R-Badge mit Risiko, Reward, Notional, Margin und Hebel.
  * **Short-Position Tool (Solution 43000516992):** Rote Verlustzone oben, grüne Gewinnzone unten, exakt auf die Trade-Parameter abgestimmt.
* **1-Click-Kopieren & TV-Launch:** Kopiert das eigenständige Position-Tool direkt in die Zwischenablage und startet TradingView Desktop mit dem passenden Markt.

### 2. ⚡ Paper Trading Vollständig Freigeschaltet
* Die künstliche Sperre („⚡ Paper-Simulation gesperrt“) auf dem Cockpit-Button wurde entfernt.
* Nutzer können nun jederzeit sofort einen Paper-Trade starten — entweder aus einem aktiven Setup oder mit dynamischen ATR-gestützten Risikolevels auf Basis des aktuellen Live-Preises.

### 3. 🚀 Zuverlässiger TradingView Desktop Launch
* Direkte protocol-basierte Verknüpfung (`tradingview://`) im Browser für Windows/macOS.
* Gleichzeitige Relay-Benachrichtigung (`/api/open-tradingview`) und Fallback für Web-Tabs.

---

## Verifikationsstatus
- `pytest` Suite: **50/50 Tests bestanden**.
- `node tests/test_tradingview_position_bridge.js`: **PASS**.
- `node tests/test_pine_forecast_generation.js`: **PASS**.
- `python3 tests/pine_static_check.py`: **OK** (0 Fehler, reine Signal-Engine).
- `scripts/release_check.py`: **SOFTWARE_GO**.
