# AURA v1.2.0 — USDT-M-Fokus, lesbare Marktstruktur & Autobot-Profile

## Überblick

AURA v1.2.0 fokussiert die gesamte Daten- und Analyse-Pipeline strikt auf aktive Bitget-USDT-M-Perpetual-Futures, verbessert die Lesbarkeit von Marktstrukturen (BOS/CHoCH) im Pine-Script v6, bindet die TradingView Desktop App auf Windows/WSL mit automatischem Web-Fallback ein und macht den Autobot-Scan-Funnel über Aktivitätsprofile transparent konfigurierbar.

## Neu

- **Striktes Bitget-USDT-M-Universum:**
  - Synchronisation und Laufzeit-Validierung filtern ausschließlich Kontrakte mit `productType=USDT-FUTURES`, `quoteCoin=USDT`, `symbolType=perpetual` und Status `normal/online`.
  - Keine fehlerhaften Nicht-Futures-, Coin-M-, USDC- oder Spot-Paare im System.
  - Snapshot `data/bitget_usdt_futures_universe.json` mit 488 aktiven Bitget USDT-M Perpetuals aktualisiert.
  - Relay liefert den kanonischen Offline-Snapshot unter `/data/bitget_usdt_futures_universe.json`.
  - Dashboard-Eingaben für eigene Paare weisen ungültige Nicht-USDT-M-Paare fail-closed ab.

- **Lesbare Marktstruktur in Pine Script v6:**
  - BOS- und CHoCH-Labels mit anpassbarer Labelgröße (`Klein`, `Normal`, `Groß`, Standard `Normal`).
  - Vertikaler ATR- und Mindest-Tick-Abstand (`high + offset`, `low - offset`) verhindert visuelle Überlappungen mit Kerzendochten.
  - Strukturierte Tooltips und kontrastreiche Farbgestaltung für bullische und bearische Strukturbrüche.

- **TradingView Desktop App Deep Linking & Web-Fallback:**
  - Auf Desktop-Systemen versucht AURA zuerst das registrierte Windows-App-Protokoll `tradingview://` über den lokalen Relay bzw. IFrame aufzurufen.
  - Ist die TradingView PC-App nicht vorhanden oder schlägt der Aufruf fehl, öffnet sich verzögerungsfrei die HTTPS-Web-Version als Fallback.
  - Strikte URL-Allowlist begrenzt Aufrufe auf kanonische TradingView-Chart-Pfade.

- **Transparente Autobot-Scan-Profile:**
  - Vordefinierte Presets: *Ausgewogen* (Score ≥ 65, MTF ≥ 2/4, OOS ≥ 10, DSR ≥ 0.35), *Aktiv* (Score ≥ 58, MTF ≥ 1/4), *Defensiv* (Score ≥ 72, MTF ≥ 3/4) und *Benutzerdefiniert*.
  - Dynamische Regler für OOS-Mindestsample-Größe und Mindest-Setup-DSR verhindern Signal-Vollblockaden bei konservativen Filtereinstellungen.
  - Detaillierte Funnel-Diagnostik im Dashboard zeigt exakt an, an welchem Gate (Score, MTF, BTC-Bias, OOS-Edge, Liquidität) Kandidaten gefiltert werden.

## Ehrliche Grenzen

- Auch bei gelockerten Profilen erfordert der Autobot zwingend eine positive OOS-Expectancy im Walk-Forward-Test — es werden keine Scheinsignale generiert.
- Das reale Modellverdikt bleibt bei `MODEL_NO_EVIDENCE`, da bisher kein historisches Universum-Backtest über 18 Grid-Kombinationen statistische Signifikanz nach DSR nachgewiesen hat.
- AURA führt weiterhin keine echten Exchange-Orders aus; das Terminal arbeitet rein als quantitatives Research- und Paper-Simulations-Werkzeug.

## Verifikation

- Pytest-Testsuite: 174 Tests und 57 Subtests bestanden.
- Node.js-Testsuites für Autobot-Profile, TradingView-Desktop-Fallback und Fallback-Liquidität bestanden.
- Pine Static Check: 0 Syntaxfehler, 842 Zeilen validiert.
- Release-Check: Alle 10 Software-Gates bestanden (`SOFTWARE_GO / MODEL_NO_EVIDENCE`).
