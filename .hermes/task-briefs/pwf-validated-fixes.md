# OpenHands Task-Brief: validierte PWF-Korrekturen

## Rolle

Du arbeitest als Senior Quant-Developer testgetrieben im aktiven AURA-Repo. Ändere nur den unten freigegebenen Scope. Lies zuerst die vollständigen Funktionen und Tests. Keine Commits, kein Push, kein Versionsbump.

## Projekt

- Repo im Agent-Workspace: `/workspace` (vor Änderungen mit `pwd`, `VERSION=1.0.7` und SHA-256 von `Symbiose_Dashboard.html` gegen den Host prüfen)
- Hauptengine: `Symbiose_Dashboard.html`, Block `//  ==ENGINE_BEGIN==` bis `// ==ENGINE_END==`
- Oracle: `tests/reference_backtest.py`, `tests/engine_oracle_export.js`
- Kern-Suites: `tests/test_engine_full.js`, `tests/test_lookahead_metamorphic.js`, `tests/test_autobot_statistical_edge.js`, `scripts/release_check.py`

## Audit-Urteil — Source of Truth

Das externe Audit wurde unabhängig geprüft. Nicht alle Vorschläge werden übernommen:

- M1 bestätigt: `purgeBars=max(20, atrLen)` ist kein Label-Horizont. Fix aber NICHT über instabiles globales p95-Pilotquantil. Der Default-Pilot erzeugte auf den fünf 1500-Bar-Fixtures nur 1–4 geschlossene Trades. Stattdessen exakter fold-/parameterbezogener t1-Schutz.
- M2 teilweise: die 1%-`embargoBars`-Regel ist unbegründet und wächst mit Historie. Ein klassisches Post-Test-Embargo ist bei strikt vergangenheitsbasiertem Forward-Walk leer und wird NICHT ergänzt.
- M3 teilweise: Anchored ist real, Rolling aber keine universell richtige Lösung. Anchored bleibt Default. `minTrainBars` wird von 150 auf 300 erhöht; Mindestzahl geschlossener Train-Trades von 3 auf 5.
- M4 bestätigt: harte Grenze am alten `trainEnd` zensiert lange grenznahe Trades zu früh. Training soll bis direkt vor den Test reichen und nur vollständig vor `testStart` geschlossene Events verwenden.
- M5 bestätigt für TimeStop-Selektion und Autobot-Evidenz; pauschales `×50 Coins×4 TFs` ist verworfen. Effektive Trials sind tatsächliche Auswahlfamilie, nicht das theoretische Universum.
- M6 teilweise: Indikator-Warmup/Perioden werden NICHT blind auf Stunden skaliert. TF wird für transparentes Stundenreporting durchgereicht. Der klare `stagnationHours`→`fallbackBars`-Einheitenfehler wird korrigiert.
- M7 ist Modellwahl, kein bewiesener Bug. K=4 bleibt. Keine adaptive K-Formel.

## Leitplanken

- Keine Order-Relay-, echte Order-, Positionsgrößen-, Margin-, Gebühren- oder P&L-Logik ändern.
- Kein Rolling-Default, kein ACF-Embargo, kein p95-Pilot-Purge, kein CPCV, keine neuen Dependencies.
- `NO_EVIDENCE`, DSR-Neutralwert 0.5 und `INSUFFICIENT_DATA` bleiben fail-closed.
- Tests müssen Verhalten prüfen, nicht nur Source-Strings.
- Produktionscode erst nach beobachtet rotem fokussiertem Test.
- JS↔Python-Fold-Oracle synchron halten.
- Neue eigenständige Tests in `scripts/release_check.py` registrieren.

## Slice 1 — Exakter t1-Trainvertrag und transparentes Fold-Reporting

### RED zuerst

Erweitere `tests/test_engine_full.js` oder erstelle einen fokussierten DOM-freien Test mit folgenden Verhaltensfällen:

1. Ein Train-Signal, dessen Entry/Exit vollständig vor `testStart` liegt, bleibt in der Parameterauswahl.
2. Ein Train-Signal, dessen Position bei `testStart` noch offen wäre, fließt nicht in das Objective ein.
3. Keine zur Parameterauswahl verwendete Position hat `exitBar >= testStart`.
4. Kein Train-Signal liest den Entry-Open bei oder nach `testStart`; letzter zulässiger Signalindex ist `testStart - 2`.
5. Fold-Report enthält mindestens:
   - `trainRange`
   - `testRange`
   - `trainBars`
   - `trainHours`
   - `testHours`
   - `trainTrades`
   - `purgedByT1`
   - `censoredTest`
   - `selectionObjective`
6. `purgedByT1` ist im konstruierten Overlap-Fall > 0.

Test ausführen und das erwartete Rot dokumentieren.

### GREEN

In `runWalkForwardBacktest`:

- `minTrainBars = 300`.
- `minTrainTrades = 5`.
- Entferne den fixen ATR-Purge und das 1%-Embargo aus der Train-Grenzberechnung.
- Für Fold `testStart` gilt:
  - Kandidaten-Train beginnt weiterhin bei `warmup` (anchored).
  - letzter Train-Signalindex `testStart - 2`, weil Entry `i+1` nutzt.
  - Exit-Grenze `testStart - 1`; so liest Training keine Testkerze.
- Pro Parameter simuliere mit genau dieser Grenze.
- Objective nutzt ausschließlich geschlossene Trades; offene Grenzereignisse werden als `purgedByT1` gezählt.
- Parameter mit weniger als fünf geschlossenen Train-Trades erhalten kein valides Auswahlobjective.
- Bewahre deterministischen Fallback auf Grid[0], aber reporte fehlende Train-Evidenz ehrlich; erfinde keine Trades.
- OOS bleibt auf `testEnd` begrenzt. Reporte offene OOS-Events als `censoredTest`.
- `options.tfMinutes` akzeptieren, nur als positive endliche Minuten validieren, Default 60. Daraus `trainHours` und `testHours` berechnen. Keine Indikator-/Warmup-Skalierung.
- Rückgabe darf optional `method`/`geometry` tragen, damit UI/Doku nicht mehr von „Embargo“ spricht.

Wichtig: Nutze keinen unbeschränkten Train-Lauf, der Bars aus dem Test liest. Das externe Beispiel `maxExitIdx=null` wird ausdrücklich NICHT übernommen.

### Oracle

Spiegle die neue Fold-Geometrie in `tests/reference_backtest.py::fold_boundaries` und Export. Oracle soll mindestens `trainRange`, `testRange`, `trainBars`, `trainHours`, `testHours` und `totalTrials` vergleichen. Für neutrales A ohne Trades ist `trainRange=[warmup,testStart-2]`; `purgedByT1=0`.

## Slice 2 — Trial-Accounting ohne pauschale Doppelzählung

### RED zuerst

Tests:

1. Identische nicht-degenerierte Returns: `calcDSR(..., 468).dsr <= calcDSR(..., 18).dsr` und `srStar` monoton nicht fallend.
2. `runWalkForwardBacktest(...,{trialMultiplier:26})` liefert `totalTrials=18*26`; ungültige/kleiner-1 Multiplier fail-closed auf 1.
3. Auto-TimeStop 5..30 übergibt 26 als tatsächliche Kandidatenzahl und der gewählte DSR stammt aus einem Lauf mit `totalTrials=468`.
4. Asset-TimeStop nutzt exakt `maxBars-minBars+1`, nicht hardcoded 21.
5. Autobot-WF nutzt als konservative aktuelle Auswahlfamilie die tatsächlich vorhandene Kandidatenanzahl, nicht hardcoded 50×4.

### GREEN

- `runWalkForwardBacktest` normalisiert `options.trialMultiplier` auf eine endliche Ganzzahl >=1.
- `totalTrials = paramGrid.length * trialMultiplier`.
- `calcDSR` nutzt `totalTrials`.
- Jeder TimeStop-Sweep berechnet vor dem Loop seine echte Kandidatenanzahl und reicht sie in jeden WF-Lauf.
- Auto-Optimizer speichert/zeigt beim Gewinner neben Bars auch effektive Trials; keine falsche Unabhängigkeitsbehauptung.
- Autobot reicht `Math.max(1, candidates.length)` als `trialMultiplier` in den frischen WF-Lauf. Nicht zusätzlich ×4, weil nur der ausgewählte TF per WF geprüft wird.

## Slice 3 — Autobot-Evidenz fail-closed

### RED zuerst

Ändere `tests/test_autobot_statistical_edge.js` verhaltensbasiert:

- `evaluateAutobotEdge` erhält das vollständige WF-Objekt, nicht nur `stats`.
- Ablehnen bei:
  - `evidenceStatus !== 'OOS'`
  - weniger als 15 geschlossenen OOS-Trades
  - nicht-endlichen Werten
  - Expectancy/Edge <= 0
  - fehlendem DSR
  - `dsr.dsr < 0.5`
- Akzeptieren nur bei OOS, >=15 Trades, positivem Edge und DSR >=0.5.
- Rückgabe enthält `dsr` und `effectiveTrials` zusätzlich zu `edge`/`sampleSize`.
- Scan-Integration übergibt `freshWalkForward`, nicht `.stats`.

### GREEN

Minimaler Fix in `evaluateAutobotEdge` und Call-Site. Kein Sizing oder Trade-Management ändern.

## Slice 4 — Timeframe-Vertrag und klarer Stunden-/Bars-Fix

### RED zuerst

- Dashboard-WF-Aufruf übergibt `tfMinutes=tfToMinutes(App.chartTF)`.
- Autobot-WF-Aufruf übergibt `tfMinutes=tfToMinutes(freshCandidate.tf)`.
- Bei `stagnationHours=12`, TF 4h ist der Fallback `ceil(12/4)=3 Bars`, Ergebnisstunden 12 — nicht 12 Bars/48h.
- Bei 15m sind 12h entsprechend 48 Bars, soweit durch validierte Caps zulässig.

### GREEN

- Korrigiere an der Autobot-Call-Site die Einheit:
  - `fallbackHours = stagnationHours`
  - `fallbackBars = max(1, ceil(fallbackHours / tfHours))`
- Passe notwendige Caps so an, dass der ausdrücklich als Stunden konfigurierte Fallback nicht still auf eine andere Zeit springt.
- Keine pauschale Skalierung von EMA/ATR/warmup/cooldown/maxHold.

## Slice 5 — UI, Release-Gate, Doku

- `renderBacktest` darf nicht mehr hart „K=4 · Embargo“ behaupten, wenn das Objekt die Methode beschreibt. Zeige tatsächliche Foldzahl, `t1-purged`, Train-/Teststunden und effektive Trials kompakt.
- `tests/engine_oracle_export.js` und `tests/reference_backtest.py` synchron.
- Falls neuer Test: in `scripts/release_check.py` registrieren.
- `SYMBIOSE_Model_Validation.md` aktualisieren: exakter t1-Schutz, anchored K=4 als bewusster Default, minTrain 300/minTrainTrades 5, Trialfamilien, keine Behauptung eines Post-Test-Embargos.
- README nur dort anpassen, wo das sichtbare Verhalten beschrieben ist.
- `PWF_FIX_REPORT.md` erstellen: M1–M7 Urteil, übernommene/verworfene Vorschläge, reale Baseline-Werte. Keine erfundenen Vorher/Nachher-Zahlen. Markiere Messungen, die Hermes nach Merge noch neu ausführen muss.

## Verifikation

Nach jedem Slice fokussierte Tests. Abschließend:

```bash
python3 tests/reference_backtest.py
node tests/test_lookahead_metamorphic.js
node tests/test_engine_full.js
node tests/test_autobot_statistical_edge.js
node tests/test_timestop_timeframe_scaling.js
node tests/sensitivity_release_gates.js
pytest -q
python3 scripts/release_check.py
```

Beim letzten Command ist ein alleiniger `version progression`-FAIL erwartbar, weil `VERSION=1.0.7` bereits getaggt ist und kein Versionsbump Teil dieses Tasks ist. Alle funktionalen Gates müssen PASS sein. Berichte exakte Commands, Ergebnisse und geänderte Dateien.
