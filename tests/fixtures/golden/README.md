# Pine ↔ JS Golden-Master Export

Diese Prüfung vergleicht das Pine-Script-Modell und die Dashboard-JavaScript-Engine auf denselben geschlossenen OHLCV-Kerzen. Sie ist strenger als ein Quelltextvergleich, weil sie die tatsächlich berechneten Zwischenwerte pro Bar prüft.

**Wichtige Authentizitätsregel:**
Für diese Prüfung zählen ausschließlich echte, unabhängige TradingView/Pine-Exporte oder separat implementierte Referenzquellen mit maschinenlesbarer Provenance (`provenance.json`). Das Erzeugen erwarteter `GM ... Score`-Werte mit der JavaScript-Engine des Dashboards und der anschließende Vergleich gegen denselben JS-Code („JS erzeugt expected und JS vergleicht actual“) ist strikt verboten und wird von der Release-Authentizitätsprüfung als `GOLDEN_MASTER_UNVERIFIED` abgewiesen. Parität ist erst bei vollständiger, unabhängiger Provenance und bestandener Authentizitätsprüfung nachgewiesen.

## Verbindliche Einstellungen

- Pine-Script: `Symbiose_Signal_System_v1.pine` aus diesem Workspace
- Chart-Feed: Bitget Perpetual, z. B. `BITGET:BTCUSDT`
- Nur vollständig geschlossene Bars exportieren
- Standard-Indikatorparameter unverändert lassen:
  - EMA 20/50/200
  - RSI/ADX/ATR 14
  - SuperTrend 10/3
  - Pivot 5
- Für die harten Core-Felder sind Makro-Inputs unerheblich. Für spätere Total-Score-Prüfungen müssen sie in Pine und JS identisch gesetzt werden.

## Fünf Pflicht-Exporte

Je mindestens 500 geschlossene Bars exportieren:

1. `BITGET:BTCUSDT`, 1h
2. `BITGET:ETHUSDT`, 1h
3. `BITGET:SOLUSDT`, 1h
4. `BITGET:XRPUSDT`, 4h
5. `BITGET:DOGEUSDT`, 4h

## TradingView-Export

1. Das aktuelle Pine-Script zum Chart hinzufügen und auf Compile-Fehler prüfen.
2. Symbol und Timeframe gemäß Liste wählen.
3. Genügend Historie laden; mindestens 500 geschlossene Bars plus 235 Warmup-Bars.
4. Chartdaten exportieren.
5. Sicherstellen, dass die CSV diese Spalten enthält:
   - Time/Date/Timestamp
   - Open, High, Low, Close, Volume
   - `GM Trend Score`
   - `GM Momentum Score`
   - `GM Volume Score`
   - `GM Structure Score`
   - `GM Core Score`
6. Die Dateien hier ablegen, zum Beispiel:
   - `tests/fixtures/golden/BTCUSDT_1h.csv`
   - `tests/fixtures/golden/ETHUSDT_1h.csv`
   - `tests/fixtures/golden/SOLUSDT_1h.csv`
   - `tests/fixtures/golden/XRPUSDT_4h.csv`
   - `tests/fixtures/golden/DOGEUSDT_4h.csv`

## Vergleich ausführen

```text
node tests/compare_pine_js_golden.js \
  tests/fixtures/golden/BTCUSDT_1h.csv \
  tests/fixtures/golden/ETHUSDT_1h.csv \
  tests/fixtures/golden/SOLUSDT_1h.csv \
  tests/fixtures/golden/XRPUSDT_4h.csv \
  tests/fixtures/golden/DOGEUSDT_4h.csv
```

Standardtoleranz: absolute Abweichung `<= 0.1` pro hartem Feld und Bar.

Bei einer Abweichung meldet das Tool den ersten Timestamp, Feldnamen, Pine-Wert, JS-Wert und Delta. Der Vergleich darf dann nicht durch Erhöhen der Toleranz „grün gerechnet“ werden; zuerst sind Datenfeed, geschlossene Bars, Warmup und Formelursache zu prüfen.

**Der Harness erzwingt jetzt zwei Mindestgrenzen** (statt still zu „grün“ zu melden):

- `MIN_TOTAL_ROWS = 735` — ein Export mit weniger als 500 geschlossenen + 235 Warmup-Bars
  schlägt sofort mit `export too short` fehl.
- `MIN_COMPARED_ROWS = 500` — werden nach dem Warmup-Skip weniger als 500 Bars tatsächlich
  verglichen, schlägt der Lauf mit `only N comparable rows` fehl.

Warmup-Bars werden auf beiden Seiten übersprungen: Pine liefert während seines eigenen
EMA200-Warmups `na`, und die JS-Seite hält die ersten `effWarmup = min(235, max(14, n-60))`
Bars auf dem neutralen Wert 50 — beide werden als „nicht vergleichbar“ markiert und nicht
als Abweichung gewertet. Leere/`na`/`NaN`-Zellen in den Score-Spalten werden beim Parsen als
NaN akzeptiert (nicht als 0 interpretiert).

## Was hart verglichen wird

- Trend Score
- Momentum Score
- Volume Score
- Structure Score
- Core Score

MTF, VWAP und kumulative Reihen werden separat bewertet, weil Pine `request.security`/`ta.vwap` und der JS-Daily-Anchor beziehungsweise deren Startzustände unterschiedlich sein können. Diese bekannten Architekturunterschiede dürfen nicht als Beweis für Core-Parität ausgegeben werden.

## Lokaler Selbsttest des Parsers

```text
node tests/test_compare_pine_js_golden.js
```

Die enthaltene `sample_valid.csv` prüft nur Parser, Timestamp-Normalisierung und Toleranzlogik. Sie ist ausdrücklich kein TradingView-Paritätsbeleg.
