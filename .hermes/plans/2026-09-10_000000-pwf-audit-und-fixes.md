# AURA Purged-Walk-Forward Audit- und Umsetzungsplan

> **For Hermes:** Implementiere den Plan phasenweise. Größere Codeänderungen gehen als enger Task-Brief an OpenHands; Hermes prüft jede Behauptung und jeden Diff unabhängig.

**Goal:** Die Expertenaussagen M1–M7 unabhängig gegen den aktuellen AURA-Code und reproduzierbare Daten prüfen, nur bestätigte Fehler testgetrieben beheben und das ehrliche Release-Verdict erhalten.

**Architecture:** Zuerst unveränderte Baseline und Ist-Datenfluss erfassen. Danach M1–M7 einzeln mit Codebeleg, Gegenprobe und fachlicher Einordnung bewerten. Bestätigte Korrekturen werden als vertikale TDD-Slices in der JavaScript-Engine umgesetzt und im Python-Oracle gespiegelt; Optimizer-/Autobot-Konsumenten und Dokumentation werden nur angepasst, soweit die Evidenz es verlangt.

**Tech Stack:** Single-File HTML/JavaScript Engine, Node.js VM-Tests, Python-stdlib Oracle, pytest, Release-Checker.

---

## Nicht verhandelbare Leitplanken

- Keine Änderungen an echter Order-, Positions- oder Geldlogik.
- Kein Commit, Push oder Release ohne separaten Nutzerauftrag.
- Bestehendes `NO_EVIDENCE`, `MODEL_NO_EVIDENCE`, DSR-Neutralverhalten und `INSUFFICIENT_DATA` bleiben fail-closed.
- Tests zuerst: Jeder Verhaltensfix beginnt mit einem reproduzierbar roten Test.
- JavaScript-Foldarithmetik und Python-Oracle bleiben synchron.
- Expertenzahlen und die mitgelieferte Referenzimplementierung sind Hypothesen, keine Wahrheit.
- Rolling Window, ACF-Embargo, Trial-Multiplikation und timeframe-skalierte Barwerte werden nur übernommen, wenn Definition, Datenfluss und Gegenproben tragen.
- OpenHands-Resultate zählen nicht als Beweis; Hermes liest Diff und führt Tests selbst aus.

## Phase 1: Unveränderte Baseline

**Objective:** Belegen, wie der aktuelle Stand wirklich arbeitet und ob das Repo vor Änderungen grün ist.

**Dateien lesen:**
- `Symbiose_Dashboard.html`
- `tests/reference_backtest.py`
- `tests/engine_oracle_export.js`
- `tests/test_engine_full.js`
- `tests/test_lookahead_metamorphic.js`
- `tests/sensitivity_release_gates.js`
- `tests/test_autobot_statistical_edge.js`
- `tests/test_timestop_timeframe_scaling.js`
- `scripts/release_check.py`
- `SYMBIOSE_Model_Validation.md`
- `README.md`

**Schritte:**
1. Definitionen und sämtliche Konsumenten von `runWalkForwardBacktest`, `simulateRange`, `calcDSR`, `autoOptimizeTimeStop`, `optimizeTimeStopForAsset` und `evaluateAutobotEdge` verfolgen.
2. Baseline-Kommandos unverändert ausführen und Ausgaben sichern:
   - `python3 tests/reference_backtest.py`
   - `node tests/test_lookahead_metamorphic.js`
   - `node tests/test_engine_full.js`
   - `node tests/sensitivity_release_gates.js`
   - `pytest`
   - `python3 scripts/release_check.py`
3. Aktuellen Git-Status dokumentieren; vorhandene Nutzerdateien nicht überschreiben.

## Phase 2: Behauptungen M1–M7 unabhängig validieren

**Objective:** Pro Punkt ein Urteil `bestätigt`, `teilweise bestätigt`, `nicht bestätigt` oder `methodisch ungeklärt` erzeugen.

### M1 — Purge
1. Prüfen, welchen Zweck das bestehende Pre-Test-Gap tatsächlich erfüllt.
2. Reale geschlossene Trade-Haltedauern aus den Golden-Fixtures mit aktueller Engine messen.
3. Quantilberechnung, kleine Stichproben, Symbol-/TF-Streuung und Pilot-Parameter-Sensitivität prüfen.
4. Sample-Level-Overlap gegen statischen Quantil-Purge abgrenzen.

### M2 — Embargo
1. AFML-Definition gegen den konkreten sequentiellen Walk-Forward-Datenfluss prüfen.
2. Klären, ob Post-Test-Embargo bei rein vergangenheitsbasiertem Expanding/Rolling Training überhaupt relevant oder doppelt gezählt wäre.
3. ACF-Heuristik auf Stationarität, negative Korrelation, hohe `rho1`, kleine Stichproben und Einheiten prüfen.
4. Keine Behauptung „AFML-konform“ ohne präzise Event-/Informationsmengen-Definition übernehmen.

### M3 — Anchored vs. Rolling
1. Aktuelle Fold-Geometrie und effektive Trainlängen messen.
2. Rolling nicht als universell „korrekt“ voraussetzen; Bias/Varianz, Regimewechsel und Datenmenge vergleichen.
3. Default nur ändern, wenn robuste Tests und dokumentierter Trade-off vorliegen.

### M4 — Trunkierung/Zensur
1. Verifizieren, welche grenznahen Train-Trades `open` werden und aus dem Objektiv fallen.
2. Test konstruieren, der Parameterauswahl durch Grenztrunkierung sichtbar macht.
3. Korrekte Alternative definieren: Simulation darf keine Testpreise zur Train-Auswahl lesen; Trades mit überlappendem `t1` werden explizit ausgeschlossen.

### M5 — DSR-Trials
1. Jede tatsächliche Auswahlstufe und ihren Datenbezug verfolgen.
2. Verhindern, dass Trials doppelt gezählt werden: Grid, TimeStop, Asset und TF nur dann multiplizieren, wenn auf derselben Evidenz ausgewählt und derselbe DSR als Gütesiegel konsumiert wird.
3. Autobot-Gate separat bewerten: DSR/CI/Evidenzstatus statt nur positiver Punktschätzer und fünf Trades.
4. DSR-Monotonie mit identischen Returns testen.

### M6 — Timeframe-Skalierung
1. Alle Barparameter nach fachlicher Bedeutung klassifizieren: Indikatorlookback, Holding-Horizont, Cooldown, Mindest-Train/Test und UI-TimeStop.
2. Nur ökonomisch zeitabhängige Parameter skalieren; Indikatorperioden nicht blind umrechnen.
3. Call-Sites müssen `tfMinutes`/Timeframe explizit liefern; unbekannter TF fail-closed oder sauberer Legacy-Default.

### M7 — Adaptive Geometrie
1. K=4 bei mehreren Datenlängen und TFs messen.
2. Prüfen, ob `K=floor(testable/minTest)` fachlich genügend Train-/Test-Evidenz garantiert.
3. Adaptive K-Regel nur mit stabilen Grenzen, Oracle-Parität und Look-ahead-Invarianz übernehmen.

## Phase 3: Auditbericht und Fix-Scope einfrieren

**Objective:** Vor Codeänderungen präzise festlegen, welche Punkte wirklich geändert werden.

**Create:** `.hermes/task-briefs/pwf-validated-fixes.md`

Der Brief enthält:
- Urteil und Beleg pro M1–M7.
- Exakte Funktionen/Dateien.
- Verhaltensinvarianten.
- Rote Tests je bestätigtem Defekt.
- Explizite Nicht-Ziele.
- Testkommandos und erwartetes ehrliches Release-Verdict.

## Phase 4: TDD-Umsetzung in vertikalen Slices

**Voraussichtliche Dateien:**
- Modify: `Symbiose_Dashboard.html`
- Modify: `tests/test_engine_full.js`
- Modify: `tests/test_lookahead_metamorphic.js`
- Modify: `tests/engine_oracle_export.js`
- Modify: `tests/reference_backtest.py`
- Modify/Create: fokussierte PWF-/Optimizer-/Autobot-Tests unter `tests/`
- Modify: `scripts/release_check.py` falls neue Tests sonst nicht im Gate laufen
- Modify: `SYMBIOSE_Model_Validation.md`
- Modify: `README.md` nur für nachweislich geändertes Verhalten
- Create: `PWF_FIX_REPORT.md`

**Slice-Reihenfolge:**
1. Trial-/Evidenzvertrag und DSR-Monotonie.
2. Purge-/Overlap-Messung und explizites Fold-Reporting.
3. Leakage-freie Train-Sample-Auswahl ohne Grenzzensur.
4. Fenster-/Geometrieänderung, falls validiert.
5. TF-Vertrag und Skalierung, falls validiert.
6. Autobot-Gate gegen unzureichende statistische Evidenz, ohne Execution-Code umzubauen.
7. Oracle, Release-Registrierung und Dokumentation synchronisieren.

Für jeden Slice:
1. Fokussierten Test schreiben.
2. Test ausführen und erwartetes Rot belegen.
3. Minimalen Produktionsfix umsetzen.
4. Fokussierten Test auf Grün bringen.
5. Engine-, Oracle- und Metamorphik-Suite ausführen.
6. Diff prüfen, bevor nächster Slice beginnt.

## Phase 5: Unabhängiger Review

**Objective:** Statistik-, Leakage- und Integrationsfehler finden, bevor „fertig“ gemeldet wird.

Review-Gates:
- Kein Test liest nur Source-Tokens statt Verhalten zu prüfen, sofern Verhalten testbar ist.
- Kein Train-Trade liest Preise aus eigenem oder späterem Testfenster.
- Kein OOS-Trade überschreitet seinen Testfold.
- Keine offene/zensorierte Position wird als geschlossene Evidenz gezählt.
- Effektive Trialzahl entspricht tatsächlichem Auswahlpfad und wird sichtbar berichtet.
- Alle relevanten Dashboard-/Optimizer-/Autobot-Call-Sites liefern denselben TF-/Trial-Vertrag.
- Kleine Datenmengen bleiben fail-closed.
- Append-Future-Metamorphik bleibt stabil.
- Keine Order-/Positions-/Geldlogik wurde unbeabsichtigt verändert.

## Phase 6: Vollständige Verifikation

**Kommandos:**
- `python3 tests/reference_backtest.py`
- `node tests/test_lookahead_metamorphic.js`
- `node tests/test_engine_full.js`
- `node tests/sensitivity_release_gates.js`
- alle neuen fokussierten Node-Tests
- `pytest`
- `python3 scripts/release_check.py`

**Reproduzierbare Messung:**
- Golden-Fixtures BTC/ETH/SOL 1h sowie XRP/DOGE 4h.
- Pro Fixture: Bars, Pilot-Trades, Haltedauer-Quantile, Purge, Embargo, Fold-Grenzen, Train-/Test-Bars und -Stunden, zensierte/gepurgte Samples, OOS-Trades, Expectancy, DSR, effektive Trials.
- Vorher/Nachher nur aus real ausgeführten Versionen; keine rekonstruierten Beispielarrays als Beleg.

## Phase 7: Abschlussbericht

**Create:** `PWF_FIX_REPORT.md`

Enthält:
- M1–M7: ursprüngliche Aussage, Urteil, Code-/Testbeleg, umgesetzter oder verworfener Vorschlag.
- Vorher/Nachher-Zahlen mit Fixture und Command.
- Vollständige Testausgabe in zusammengefasster Form.
- Ehrliches Software-/Modell-Verdict getrennt.
- Offene Restrisiken und nicht verifizierte externe Pfade.

## Stop-Kriterien

Fertig erst wenn:
- M1–M7 einzeln entschieden sind.
- Jeder bestätigte Fix einen zuvor roten Verhaltenstest besitzt.
- JS↔Python-Parität grün ist.
- Vollständige Baseline-/Release-Suite ohne neue Regression läuft.
- `PWF_FIX_REPORT.md` reproduzierbare statt behauptete Zahlen enthält.
- Git-Diff unabhängig geprüft wurde.
