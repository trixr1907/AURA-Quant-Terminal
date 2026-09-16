# UX-Engineering-Audit: AURA v2.5.0 (Symbiose Dashboard & Tutorial)

**Auditor:** UX-Engineering-Auditor (AURA-Audit, Runde 40)  
**Zielsystem:** `Symbiose_Dashboard.html` (599 KB Single-File) & `SYMBIOSE_Tutorial.html` (39 KB)  
**Repository-Pfad:** `/home/ivo/projects/AURA_v2` (Commit `de25830`, v2.5.0)  
**Fokus:** Responsive Weboberfläche (Desktop & Smartphone), WCAG 2.2 AA Barrierefreiheit, klare Datensemantik (Echt vs. Simulation vs. Ausfall), Robustheit bei Verbindungsverlust.

---

## 1. Vollständige Liste der vorhandenen Ansichten & Panels

| # | Panel / Ansicht | DOM-Selektor / ID | Primäre Funktion & UI-Komponenten |
|---|---|---|---|
| 1 | **Global Header & Statusbar** | `header`, `.statusbar`, `.ctl` | Globales Asset-Routing (`#symsel`, `#symcustom`), Timeframe-Wahl (15m, 1h, 4h, 1d), globale Risiko- & Equity-Parameter (`#equity`, `#risk`, `#timestop`), Feed-Status-Pille (`#feed-status-pill`), Live-Refresh-Trigger (`#refresh`), Audio-Toggle (`#sound-toggle`), Release-Notes-Trigger (`#btn-release-notes`), Datenquellen-Status-Dots (Marktdaten, F&G, CoinGecko, Sync, WS Live). |
| 2 | **Makro-Wetterleiste** | `.macrobar`, `#macro-btc-cell` | Übergeordnetes BTC-Regime (Bullish/Bearish/Neutral), EMA50/EMA200-Spreizung, BTC-ADX, globales Funding-Rate-Klima, Fear & Greed Index, visualisierte BTC-Bias-Leiste (`.btc-bias-bar`). |
| 3 | **Hero / Fokus-Setup Panel** | `section#hero` | Zentrales Entscheidungszentrum ("Single Source of Truth"): Research Gate Verdict (`#hero-go-badge`, GO / NO-GO), ausgewählter Coin (`#hero-coin`), Trendrichtung (`#hero-dir-badge`), Confluence-Score-Chip (`#hero-score-chip`), Timing-Chip (`#hero-when-chip`), quantitative Kernlevel (Entry, SL, TP1, TP2), Aktions-Buttons (⚡ Paper-Trade starten, 📋 Setup kopieren, 📊 TV öffnen, ⌁ Action Radar), Setup-Begründung (`#hero-why`), Research-Exposure-Kalkulator (Kontrakte, USDT Notional, Modellrisiko %, Kelly-Chip, Quellen-Badge). |
| 4 | **TradingView Bridge & Presets** | `section#tv-basic-panel` | TradingView Deep-Link- & Preset-Panel mit 1-Klick-Listenexporten (Top-30 Symbole, Long-Liste, Short-Liste, 3 Preisalarme, Setup-Notiz) und automatischer Bitget-USDT-M-URL-Generierung. |
| 5 | **Setup-Metriken / Price Strip** | `section#pricestrip` | Horizontale Metrikenleiste: Spot-Preis, 24h-Veränderung %, 24h-Volumen, ATR (14), RSI (14), ADX-Trendstärke, Spread/Slippage-Schätzung. |
| 6 | **Chart & Technische Validierung** | `article.panel.chartcard` | Interaktiver HTML5-Canvas-Candlestick-Chart mit Overlays (EMA 20/50/200, SuperTrend, VWAP, FVG-/Imbalance-Zonen, Liquidity-Zonen), Zeichenwerkzeugen (Linie, Trendlinie, Löschen), Zeitrahmen-Zoom und Pine-Script-Export. |
| 7 | **Signal Breakdown & Confluence Card** | `article#sigcard` | Detaillierte Confluence-Zerlegung in 5 Kernfaktoren (Trend, Momentum, Volatilität, Volumen, Marktstruktur), Gate-Status-Matrix (Regime, Squeeze, MTF, Kelly) und Time-Stop-Optimierungs-Widget (`#time-stop-optimizer`). |
| 8 | **Liquidity & Structure Panel** | `div#liqlist` | Orderbuch-Tiefe, Key Support/Resistance-Levels, Equal Highs / Lows (EQH/EQL), Fair Value Gaps (FVG) und dynamische Zonen mit prozentualem Abstand zum Spot-Preis. |
| 9 | **Multi-Timeframe Matrix** | `article#mtfcard` | 4-Zeitebenen-Matrix (15m, 1h, 4h, 1d) mit Trendrichtung, Indikator-Zustand, Alignment-Score und visueller Confluence-Ampel. |
| 10 | **Derivatives Context Panel** | `article#derivatives-card` | Open Interest (OI) mit 4h-Delta, Funding Rate mit Z-Score, Long/Short-Ratio und geschätzte Liquidationsbänder. |
| 11 | **Market Pulse Panel** | `section#pulsecard` | Marktbreite, Volatilitätsregime, Top-Gewinner/Verlierer, Funding-Verteilung und Korrelationsmatrix zu Bitcoin. |
| 12 | **Server Autobot Panel** | `section#autobot-section` | Docker-Server-Bot-Steuerung & Viewer: Server-Paper-Equity-KPIs (Startkapital, ROI %, Brutto-PnL, Win-Rate, Profit-Faktor, Offene Slots), Live-Entscheidungsprotokoll (Decision Log), Bot-Funnel (24h) (`#bot-funnel-section`) und Konfigurations-Editor (`#btn-config-autobot`, `#btn-save-ab-config`) für Scan-Profile, Risikosteuerung, Filter, OOS-Mindesttrades und Time-Stops. |
| 13 | **Benachrichtigungen Panel** | `section#ntfy-settings-panel` | Konfiguration von ntfy-Push-Benachrichtigungen mit Topic-URL, Test-Push-Trigger und granularen Checkboxen (Ordereröffnung, TP1, TP2, TP3, Stop-Loss, sonstiger Schluss). |
| 14 | **Live Paper Tracker & Position Manager** | `section#live-tracker-panel` | Verwaltung offener & historischer Paper-Positionen: Portfolio-KPIs (Gesamt-Margin, Notional, Live-PnL, Gewichteter ROI, Initialrisiko), manuelles Trade-Erstellungsformular (`.trade-form-grid`), aktive Positionstracker mit TP/SL-Fortschrittsbalken und Schließen-Aktionen sowie geschlossene Trade-Historie (`#trade-history-section`) mit Filtern und CSV/JSON-Export. |
| 15 | **OOS Backtest Validation Panel** | `section.panel.backtest-panel` | Statistische Validierung historischer Signale via 4-Fold Anchored Walk-Forward Out-of-Sample Backtests (Anzahl Setups, Win-Rate, Ø Gewinn R, Profit-Faktor, Erwartungswert R, Deflated Sharpe Ratio (DSR), Max Drawdown) inklusive vollständiger Fold-Trade-Tabelle. |
| 16 | **Methodik & Begriffe Accordion** | `details.panel.details-panel` | Ausklappbares Bildungs-Panel mit Erläuterungen zu Score-Berechnung, Gating-Logik, Deflated Sharpe Ratio nach López de Prado und Out-of-Sample-Validierung. |
| 17 | **Action Radar Drawer** | `aside#radarcard` | Slide-over Universums-Scanner mit Filtern für Zeiteinheiten (Alle, 15m, 1h, 4h, 1d), Mindestvolumen (500k, 1M, 5M), Sortier- und Filter-Presets (Top Edge, Score auf-/absteigend, Longs/Shorts, Squeeze-Alarm, 4/4 MTF, A-Z) und Fortschrittsanzeige des Hintergrund-Scanners. |
| 18 | **Release Notes Modal** | `div#release-notes-modal` | Modaler Dialog zur Anzeige der Versionshinweise (v2.5.0 Changelog, behobene Fehler, Tutorial-Link). |
| 19 | **TradingView Drawing Tool Precision Modal** | `div#tv-drawing-tool-modal` | Modaler Leitfaden zum 1-Klick-Kopieren von Einstiegspreis, Stop-Loss, Take-Profits, Positionsgröße und Pine Script für das native TradingView Long/Short-Zeichentool (Hinweis: Aktuell ungebunden im JS). |

---

## 2. Zielprodukt-Bedarf vs. Existierender Ist-Zustand

| Anforderung Zielprodukt | Ist-Zustand (v2.5.0) | Gap / Bewertung |
|---|---|---|
| **Mobile-First Responsive Usability (320px–390px)** | Gute Grundstruktur mit 5 Media Queries (`1280px`, `960px`, `620px`, `420px`, `390px`). | **Teilweise erfüllt**: Zentrale Steuerelemente im Header und Tracker passen sich an; einige Bot- und Chart-Buttons verletzen jedoch 44px-Touch-Targets. |
| **Not-Halt / Panic-Button** | Nicht vorhanden. Trades müssen einzeln pro Karte geschlossen werden. | **Kritischer Gap**: Bei Marktstress oder Fehlfunktion fehlt ein 1-Klick-Sicherheitsventil zum Schließen aller Positionen bzw. Pausieren des Bots. |
| **Klare Unterscheidung Paper/Simulation vs. Echt** | Durchgängige textuelle Hinweise ("Paper-Simulation", "Research Station", "Brutto-PnL"). | **Leichter Gap**: Das grüne `● SERVER LIVE`-Badge im Autobot suggeriert echten Börsenhandel statt reiner Docker-Simulation. |
| **Ehrliche Anzeige fehlender Daten (Keine Pseudo-Nullen)** | Teils `—` (z.B. Hero, MTF), aber statische HTML-Initialwerte im Autobot (`10,000 USDT`, `0.0%`). | **Mittlerer Gap**: Uninitialisierte Serverdaten sehen aus wie ein intaktes Konto mit 0 Verlusten. |
| **WCAG 2.2 AA Barrierefreiheit** | Hohe Kontraste (7:1 bis 18:1), solides `:focus-visible`, semantische ARIA-Labels vorhanden. | **Mittlerer Gap**: Micro-Typography (9px/10px) ist mobil zu klein; einige Toolbar-Buttons haben keine Labels. |
| **Verbindungsüberwachung & Stale-State** | Feed-Status-Pille trackt Disconnect-Alter dynamisch (`WS offline seit Xs`). | **Mittlerer Gap**: Offene Trades frieren bei WS-Ausfall stillstehend ein, ohne optische Warnung ("Preise veraltet") auf den Trade-Karten. |
| **TradingView-Integration & Drawing-Tools** | Schnelle Deep-Links funktionieren; Clipboard-Fallback ist extrem robust. | **Mittlerer Gap**: Das Drawing-Tool-Modal (`#tv-drawing-tool-modal`) ist toter HTML-Code ohne JS-Anbindung. |
| **Tutorial-Synchronität** | 10 ausführliche Kapitel mit präzisen Formelerklärungen und Diagrammen. | **Geringer Gap**: Kapitel 7 fehlt in der Nummerierung (Sprung von 6 auf 8). |

---

## 3. Detaillierte Audit-Befunde [Was][Wo][Warum][Fix]

### Befund 1: Fehlender globaler Not-Halt / Panic-Button
* **[Was]:** Es existiert kein globaler Not-Halt-Schalter ("Alle Positionen sofort schließen" bzw. "Server-Bot notstoppen").
* **[Wo]:** `Symbiose_Dashboard.html`, `#live-tracker-panel` und `#autobot-section`.
* **[Warum]:** Wenn der Markt plötzlich dreht oder der Nutzer eine Fehlkonfiguration feststellt, muss jede Position einzeln über die jeweilige Karte gesucht und geschlossen werden. Auf Mobilgeräten erzeugt dies untragbare Latenzen und Fehlerpotenzial.
* **[Fix]:** Einen prominenten, zweistufigen (Hold-to-Confirm) "Not-Halt / Alle schließen"-Button in der Header- oder Tracker-Leiste einbauen, der via `closeTrade()` iterativ alle offenen Positionen liquidiert und den Bot deaktiviert.
* **Schweregrad:** **HOCH**

---

### Befund 2: Verwaistes TradingView-Modal ohne JavaScript-Event-Binding (Dead UI)
* **[Was]:** Das HTML-Element `#tv-drawing-tool-modal` (Zeilen 675–753) inklusive der Aktions-Buttons `#tv-draw-close`, `#tv-draw-done`, `#btn-copy-tv-order` und `#btn-copy-tv-pine-standalone` ist im DOM vorhanden, besitzt aber keinerlei Event-Listener oder Aufruf-Funktion in `<script>`.
* **[Wo]:** `Symbiose_Dashboard.html`, Zeilen 675–753 und Script-Block ab Zeile 756.
* **[Warum]:** Nutzer, die geführte TradingView-Zeichentool-Level oder Pine-Snippets über diesen Dialog erwarten, erhalten keinerlei Reaktion; wertvoller Code liegt brach.
* **[Fix]:** Funktionen `openTvDrawModal(symbol, levels)` und `closeTvDrawModal()` im JS implementieren, an `#btn-hero-tv` / `#btn-chart-tv` anbinden und Modal-Events verdrahten.
* **Schweregrad:** **HOCH**

---

### Befund 3: Irreführende statische Default-Werte statt N/A bei uninitialisierten Server-Bot KPIs
* **[Was]:** Im Autobot-Panel stehen im statischen HTML feste Zahlenwerte: `10,000.00 USDT` Server-Paper-Equity, `+0.00%` ROI, `0.00 USDT` PnL, `0.0% (0)` Win-Rate.
* **[Wo]:** `Symbiose_Dashboard.html`, `#autobot-section` (`.ab-kpis`).
* **[Warum]:** Solange der Docker-Server noch lädt oder wenn der Server nicht erreichbar ist, wird dem Nutzer ein fehlerfreier Null-Verlust-Zustand vorgegaukelt, anstatt den Lade-/Ausfallzustand transparent zu machen.
* **[Fix]:** Statische HTML-Werte auf `—` setzen und erst bei verifiziertem Server-Handshake mit echten Daten befüllen; bei Disconnect Skeleton-Loader oder Warnhinweis anzeigen.
* **Schweregrad:** **HOCH**

---

### Befund 4: Touch-Target-Verletzungen (< 44px) bei kritischen Bot- und Chart-Aktionen
* **[Was]:** Mehrere interaktive Bedienelemente unterschreiten die Mindestgröße von 44×44px (WCAG 2.2 Target Size):
  - `.ab-toggle-btn`: Feste Höhe `28px` (Zeile 232 / CSS).
  - `#btn-config-autobot` ("⚙ Parameter"): `padding: 4px 9px; font-size: 9.5px` (~24px Höhe).
  - `#btn-reset-autobot` ("↺ Archiv"): `padding: 4px 8px; font-size: 9.5px` (~24px Höhe).
  - Chart-Toolbar-Buttons (`#tool-select`, `#tool-hline`, `#tool-trend`, Zoom-Buttons): ~26px Höhe.
* **[Wo]:** `Symbiose_Dashboard.html`, CSS `.ab-toggle-btn`, `.chart-draw-toolbar button`, Inline-Styles an Buttons.
* **[Warum]:** Auf Smartphones führen zu kleine Touch-Ziele zu häufigen Fehlbedienungen und Frustration bei der Parameter-Einstellung.
* **[Fix]:** In `@media(max-width:620px)` für alle Schaltflächen `.ab-toggle-btn, .chart-draw-toolbar button, .tc-btn` ein `min-height: 44px; min-width: 44px;` und touch-optimierte Abstände definieren.
* **Schweregrad:** **MITTEL**

---

### Befund 5: Unzureichende Schriftgrößen (Micro-Typography 9px/10px) auf Mobilgeräten
* **[Was]:** Zahlreiche Beschriftungen nutzen `font-size: 9px` (`--text-xs`) oder `10px` (`--text-sm`) (z.B. `.ab-kpi span`, `.tv-basic-help`, `.feed-status-pill`, `.macro-btc-sub`).
* **[Wo]:** `Symbiose_Dashboard.html`, CSS-Design-Tokens `--text-xs: 9px;`, `--text-sm: 10px;`.
* **[Warum]:** Auf mobilen Displays (z.B. 360–390px Viewport) mit hoher Pixeldichte ist 9px ohne Zoom kaum lesbar und verstößt gegen ergonomische Standards (empfohlen: Fließtext/Labels ≥ 12–14px).
* **[Fix]:** CSS-Tokens auf `--text-xs: 11px;` und `--text-sm: 12px;` anheben oder responsive Skalierung via `clamp(11px, 2.5vw, 13px)` für mobile Breakpoints erzwingen.
* **Schweregrad:** **MITTEL**

---

### Befund 6: Fehlendes Stale-Data-Overlay auf offenen Positionen bei Verbindungsabbruch
* **[Was]:** Wenn der WebSocket offline geht (`feed-status-pill offline`), stoppt der Ticker. Die PnL- und Distanzanzeigen der offenen Trade-Karten (`.trade-card`) bleiben auf dem letzten Wert eingefroren, ohne dass die Karte selbst als "Daten veraltet" gekennzeichnet wird.
* **[Wo]:** `Symbiose_Dashboard.html`, `calculateTradeMetrics()` und `renderLiveTrades()`.
* **[Warum]:** Der Nutzer sieht statische Gewinne/Verluste und wiegt sich in falscher Sicherheit, während sich der reale Markt weiterbewegt.
* **[Fix]:** Bei `App.status.ws !== 'live'` einen halbtransparenten Overlay-Banner ("⚠️ Preise eingefroren — Live-Feed offline") über `.trade-card` und `#trade-portfolio-kpis` legen.
* **Schweregrad:** **MITTEL**

---

### Befund 7: Ambiguität bei "SERVER LIVE" Badge vs. Paper-Trading-Kennzeichnung
* **[Was]:** Das Badge `#ab-status-badge` im Autobot-Header zeigt ein leuchtend grünes `● SERVER LIVE`, direkt neben "▶ Server-Bot Config aktivieren".
* **[Wo]:** `Symbiose_Dashboard.html`, `#ab-status-badge` (Zeile 231).
* **[Warum]:** Trotz Untertitel "Server-Paper-Equity" sticht das grüne "SERVER LIVE" prominent hervor und kann bei neuen Nutzern die fatale Fehlannahme erzeugen, dass echtes Kapital an einer Börse gehandelt wird.
* **[Fix]:** Badge explizit beschriften: `● SERVER PAPER LIVE` oder `● DOCKER SIMULATION LIVE` mit erklärendem Tooltip.
* **Schweregrad:** **NIEDRIG**

---

### Befund 8: Inkonsistente Kapitelnummerierung im Tutorial (`SYMBIOSE_Tutorial.html`)
* **[Was]:** In `SYMBIOSE_Tutorial.html` springt die Kapitelzählung direkt von `<span class="num">6</span>` (Makro-Kontext) zu `<span class="num">8</span>` (TradingView & Pine Script v6); Kapitel 7 fehlt.
* **[Wo]:** `SYMBIOSE_Tutorial.html`, Zeilen 330–350.
* **[Warum]:** Verwirrt Lernende und erweckt den Eindruck, dass ein relevanter Abschnitt (z.B. Backtesting oder Risikomanagement) versehentlich gelöscht wurde.
* **[Fix]:** Kapitelnummern fortlaufend von 1 bis 10 durchzählen oder das fehlende Kapitel 7 (z.B. "Live Paper Tracker & Positionsmanagement") ergänzen.
* **Schweregrad:** **NIEDRIG**

---

## 4. Fazit & Umsetzungsempfehlungen

1. **Sicherheit & Not-Halt:** Die Implementierung eines globalen 2-Klick/Hold Not-Halts für alle offenen Trades hat höchste Priorität für den mobilen Praxiseinsatz.
2. **Code-Hygiene:** Das ungebundene TradingView-Modal (`#tv-drawing-tool-modal`) muss entweder mit JS-Eventhandlern aktiviert oder bereinigt werden.
3. **Mobile Ergonomie:** Die Erhöhung der Micro-Schriftgrößen von 9px auf 11–12px und die Durchsetzung von 44px-Touch-Targets für alle Schaltflächen im Autobot- und Chart-Bereich stellen die WCAG 2.2 AA Konformität sicher.
4. **Ausfall-Transparenz:** Disconnect-Zustände müssen sich sofort optisch auf alle betroffenen Live-PnL-Bereiche auswirken (Stale-Banner statt stummer Zahlen-Einfrierung).
