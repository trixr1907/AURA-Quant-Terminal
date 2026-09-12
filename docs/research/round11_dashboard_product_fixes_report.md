# AURA — Forschungs- und Qualitätsbericht Runde 11: Dashboard-Produkt-Fixes (UX & Feed-Verlässlichkeit)

**Datum:** 2026-09-12  
**Autor:** Hermes Agent (Senior Quant Systems Auditor & Engineer)  
**Ausgangsversion:** `1.2.10`  
**Zielversion / Veröffentlichte Version:** `1.2.11`  
**Kanonischer Release-Branch:** `fix/round11-dashboard-product-quality`  
**Release-Urteil:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Exit 0)  

---

## 1. Executive Summary & Zielsetzung

Runde 11 ist eine dedizierte **Produktqualitäts- und Zuverlässigkeitsrunde** für das im täglichen Praxiseinsatz betriebene AURA Quant Terminal. Nach dem formalen Abschluss des 21-Punkte-Gesamtaudits (F-01 bis F-21) mit v1.2.10 wurden sieben konkrete UX-, Feed- und Auswerte-Schwachstellen (PF-1 bis PF-7) isoliert und testgetrieben behoben:

1. **PF-1 (Bitget WebSocket Live-Feed primär):** Umstellung des Dashboard-Live-Candle-Streams von Binance auf Bitget Public WebSocket v2 (`wss://ws.bitget.com/v2/ws/public`) mit deterministischer Binance-Fallback-Kette und automatischem Reconnect innerhalb von 15 s.
2. **PF-2 (Datenalter & Visibility-Resume):** Implementierung eines kontinuierlichen Header-Status-Pills (`LIVE · <Quelle> · vor <N>s` bzw. rot `WS offline seit Xs`) und `visibilitychange`/`focus`-Ereignishandlern zur verzögerungsfreien Aufholjagd nach Tab-Throttling.
3. **PF-3 (Radar-Volumenfilter):** Anzeige-Umschalter für das Action-Radar (`Alle`, `≥ 500k`, `≥ 1M`, `≥ 5M`) mit dynamischen Echtzeit-Zählern und `localStorage`-Persistenz ohne Beeinflussung quantitativer Scan-Gates.
4. **PF-4 (Win-Rate-Semantik & Partial-Close):** Vollständige Tranchen-Gewichtung in `calculateHistoryStats` (`realizedWinRatePct` neben Event-`winRatePct`), Erfassung von `PARTIAL_CLOSE`-Ereignissen bei TP1/TP2 und fehlerfreie Abwärtskompatibilität zu Legacy-Trades.
5. **PF-5 (Aktueller Preis in aktiven Trades):** Explizite „Aktuell"-Spalte mit Marktpreis, farbcodiertem Entry-Delta (%) und visuellem Alter-Indikator bei Daten älter als 30 s.
6. **PF-6 (Autobot-Zyklusstatus & Event-Log):** Transparenter Scan-Status (`Letzter Scan: vor <N>s`, geprüfte/qualifizierte Kandidaten, Abweisungsgründe) und direkt in der Autobot-Card integriertes Decision-Log.
7. **PF-7 (TradingView-URL & schneller Relay-Fallback):** Korrekte Link-Generierung auf das Bitget-Perpetual-Format (`BITGET:<SYMBOL>.P`), 400 ms Abort-Timeout für Offline-Relays und klare visuelle Rückmeldung.

**Regelkonformität & Hygiene:**
- Keine Änderung an Signal-Scores, Indikator-Parametern oder statistischen Modellen.
- Strikte XSS-/DOM-Hygiene: Alle neuen Werte nutzen `textContent` oder `esc()`; `grep -c innerHTML Symbiose_Dashboard.html` bleibt exakt bei **51**.
- Ledger-Einordnung: Reine UX-/Feed-Optimierung ohne Signal-Logik-Anteil; der Pine-paritätsgeprüfte CVD-Range-Approximationspfad (`v*(2c-h-l)/(h-l)`) bleibt unverändert aktiv.

---

## 2. Detailanalyse der 7 Produkt-Fixes (PF-1 bis PF-7)

### 2.1 PF-1: Bitget-Public-WebSocket als primärer Candle-Feed

- **Problem:** Die Live-Kerzen im Terminal bezogen ihre Daten primär von `wss://stream.binance.com:9443` (bzw. Fallback `data-stream.binance.vision`). In Regionen mit Binance-Restriktionen oder WebSocket-Verbindungsabbrüchen fror der Chart ein, während REST-Abfragen an Bitget weiterliefen.
- **Lösung:**
  - Konfiguration der prioritären Feed-Kette `WS_FEEDS`:
    1. Bitget v2 Public WebSocket (`wss://ws.bitget.com/v2/ws/public`, Topic `candle<TF>`)
    2. Binance Primary (`wss://stream.binance.com:9443/ws/<sym>@kline_<tf>`)
    3. Binance Public Vision Mirror (`wss://data-stream.binance.vision/ws/<sym>@kline_<tf>`)
  - **CVD-Mathematik & Parität:** Bitget-Public-Candles liefern kein Taker-Buy-Volumen (`tbv`). In `Symbiose_Dashboard.html` wird `tbv` beim Bitget-Empfang bewusst weggelassen, wodurch der deterministische Bar-Range-Pfad greift:
    $$\Delta V = \text{volume} \cdot \frac{2 \cdot \text{close} - \text{high} - \text{low}}{\text{high} - \text{low}}$$
    Dies ist exakt die in Runde 10 Pine-paritätsgeprüfte Variante (0 Flips über 64.859 Bars).
- **Testnachweis:** `tests/test_bitget_websocket_reconnect.js` belegt Stream-Parsing, Topic-Subscription und automatisches Failover/Reconnect bei Verbindungsabbruch.

### 2.2 PF-2: Datenalter-Pill & Tab-Rückkehr-Aufholjagd

- **Problem:** Hintergrund-Tabs wurden von modernen Browsern nach wenigen Minuten gedrosselt; bei Rückkehr zeigte das Dashboard veraltete Stände, ohne dass der Nutzer das Alter der Daten erkennen konnte.
- **Lösung:**
  - Im Header wurde ein permanenter Status-Pill integriert: `#feed-status-pill`. Er aktualisiert sich sekündlich und zeigt bei aktivem Feed `LIVE · bitget-ws · vor 1s` bzw. bei getrenntem WebSocket auffällig rot `WS offline seit 45s`.
  - Es wurden Event-Listener für `visibilitychange` (`document.visibilityState === 'visible'`) und `window.focus` registriert (`bindResumeRefresh`). Ist der letzte vollständige Datenabruf älter als 60 s, wird sofort `loadAll()` ausgeführt.
- **Testnachweis:** `tests/test_data_freshness_resume.js` prüft die Event-Listener-Registrierung, Auslösung bei Tab-Fokus und die sekundengenaue Alter-Formatierung.

### 2.3 PF-3: Radar-Volumenfilter (Display-Filter)

- **Problem:** Das Bitget-Perpetual-Universum umfasst über 780 aktive Märkte. Im Action-Radar fehlte eine schnelle optische Filterung nach Mindestliquidität.
- **Lösung:**
  - Im Radar-Steuerungsbereich wurde ein Select-Filter `#radar-volume-filter` mit den Stufen `Alle`, `≥ 500k`, `≥ 1M`, `≥ 5M` implementiert.
  - Die Filterstufen zeigen live die exakte Anzahl passender Symbole (z. B. `Alle (787)`, `≥ 500k (188)`, `≥ 1M (126)`, `≥ 5M (52)`).
  - Der Filter wirkt ausschließlich auf die visuelle Darstellung (`filterRadarByVolume`), manipuliert keine quantitativen Scan-Kriterien und persistiert die Nutzerauswahl in `localStorage`.
- **Testnachweis:** `tests/test_radar_volume_filter.js` validiert Filterlogik, Symbol-Zähler und Schwellenwertprüfung.

### 2.4 PF-4: Partial-Close-Historie & Tranchen-gewichtete Win-Rate

- **Problem:** Teilgewinnmitnahmen (z. B. 50% TP2 im Autobot oder manuelle Scale-Outs) schrieben bisher kein Historien-Event, solange der Rest-Trade (Runner) aktiv war. Dies führte zu einer verzerrten Win-Rate von 0%, obwohl erhebliche Gewinne realisiert worden waren.
- **Lösung:**
  - Teilverkäufe erzeugen sofort ein `PARTIAL_CLOSE`-Event mit `fractionClosed: 0.5`, `realizedPnlGross` und Grund (`PARTIAL_TAKE_PROFIT_TP2`).
  - `calculateHistoryStats` berechnet sowohl die Event-basierte Win-Rate (`winRatePct`) als auch die **tranchen-gewichtete realisierte Win-Rate** (`realizedWinRatePct`):
    $$\text{Realized WR} = \frac{\sum_{\text{Wins}} \text{fractionClosed}}{\sum_{\text{All}} \text{fractionClosed}} \times 100$$
  - Vollständige Rückwärtskompatibilität: Legacy-Einträge ohne `fractionClosed` werden automatisch mit `1.0` (bzw. `0.5` bei historischen Partials) normalisiert.
- **Testnachweis:** `tests/test_partial_close_winrate_stats.js` belegt exakte Tranchen-Gewichtung, Win-Rate-Berechnung bei Teiltreffern und Toleranz historischer Daten.

### 2.5 PF-5: Live-Tradepreis und Alter-Indikator

- **Problem:** In der Übersicht aktiver Trades wurde der Markpreis zwar für PnL-Berechnungen herangezogen, aber nicht übersichtlich als eigene Spalte mit Entry-Delta und Alter dargestellt.
- **Lösung:**
  - Jede Trade-Karte enthält nun ein dezidiertes `tc-item` „Aktuell" mit aktuellem Preis, farbcodiertem Abstand zum Einstieg (`+8.00%`) und einem optischen Indikator (`stale-price-dot`), wenn der Markpreis älter als 30 s ist.
- **Testnachweis:** `tests/test_live_trade_current_price_render.js` prüft die Rendering-Pipeline unter verschiedenen Preiskonstellationen und Altersstufen.

### 2.6 PF-6: Autobot-Zyklusstatus & In-Card Event-Log

- **Problem:** Nach automatischen Markt-Scans war für den Nutzer unklar, wann der letzte Scan stattfand und aus welchen Gründen Kandidaten abgewiesen wurden.
- **Lösung:**
  - Die Zusammenfassungszeile `#ab-funnel-summary` zeigt sekundengenau den Zyklusstatus an:  
    `Letzter Scan: vor 4s · Funnel: 12 Hypothesen (3 Märkte × 4 TFs) → 1 qualifiziert · [Setup-DSR ≥ 0.10 · OOS ≥ 8] · Abgelehnt: MODEL_NO_EVIDENCE:3`.
  - Das ausklappbare Decision-Log `#ab-live-log` rendert die neuesten Ereignisse direkt in der Karte.
- **Testnachweis:** `tests/test_autobot_cycle_status_log.js` validiert Funnel-Diagnostik, Zeitstempel-Aktualisierung und Log-Ausgabe.

### 2.7 PF-7: TradingView-URL-Generierung & schneller Relay-Fallback

- **Problem:** Die externe Chart-Öffnung erzeugte vereinzelt Binance-Präfixe; war der lokale Desktop-Relay-Server offline, entstand eine störende 2-Sekunden-Verzögerung vor dem Web-Fallback.
- **Lösung:**
  - Generierung von sauberen Bitget-Perpetual-URLs (`BITGET:<SYMBOL>.P`).
  - Einbindung eines `AbortController`-Signals mit 400 ms Timeout für Relay-Anfragen (`/api/open-tradingview`), sodass bei Offline-Relay sofort der direkte Browser-Tab geöffnet wird.
  - Klare Dokumentation der Docker/Host-Relay-Architektur im Quellcode.
- **Testnachweis:** `tests/test_tradingview_url_and_fast_fallback.js` belegt URL-Struktur und Fallback-Ausführung unter 500 ms.

---

## 3. Test- & Verifikationsübersicht

Alle neuen und bestehenden Test-Suites wurden im Rahmen des Release-Gates ausgeführt:

| Test-Suite | Fokus | Status |
|:---|:---|:---:|
| `node tests/test_bitget_websocket_reconnect.js` | PF-1 Bitget WS Feed & Reconnect | **PASS (0)** |
| `node tests/test_data_freshness_resume.js` | PF-2 Visibility & Data Age | **PASS (0)** |
| `node tests/test_radar_volume_filter.js` | PF-3 Radar Volume Filter & Counters | **PASS (0)** |
| `node tests/test_partial_close_winrate_stats.js` | PF-4 Partial-Close & Win-Rate | **PASS (0)** |
| `node tests/test_live_trade_current_price_render.js` | PF-5 Live Trade Price & Stale Dot | **PASS (0)** |
| `node tests/test_autobot_cycle_status_log.js` | PF-6 Autobot Funnel & Event Log | **PASS (0)** |
| `node tests/test_tradingview_url_and_fast_fallback.js` | PF-7 Bitget TV URL & Fast Fallback | **PASS (0)** |
| `node tests/test_live_trade_tracker.js` | Regression Trade Tracker & Cockpit | **PASS (0)** |
| `node tests/test_websocket_generation.js` | Regression WebSocket Stream Handlers | **PASS (0)** |
| `node tests/test_radar_sorting.js` | Regression Action Radar Sort Modes | **PASS (0)** |
| `node tests/test_autobot_scan_diagnostics.js` | Regression Autobot Scan Gates | **PASS (0)** |
| `node tests/test_tradingview_link.js` | Regression TV Link Builder | **PASS (0)** |
| `node tests/test_tradingview_desktop_fallback.js` | Regression TV Desktop Fallback | **PASS (0)** |
| `python3 -m pytest -q` | Pytest Backend & Parity Suites | **PASS (0)** |
| `python3 scripts/verify_ledger.py` | Immutable Hash-Chain Check | **PASS (0)** |
| `python3 scripts/release_check.py` | Full Autonomous Release Gate | **PASS (0)** |

---

## 4. Fazit & Release-Urteil

Mit v1.2.11 erhält das AURA Quant Terminal eine signifikante Aufwertung in Alltagstauglichkeit, visueller Klarheit und Netzwerk-Resilienz, ohne die quantitativ auditierten Modellgrenzen zu verletzen.

- **Gesamtergebnis:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Exit-Code 0)
- **Produktionsreife:** Vollständig für automatisiertes Proxmox/Docker-Deployment via Webhook freigegeben.
