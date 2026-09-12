# AURA Edge-Forschung — Abschluss A bis D

**Datum:** 2026-09-10  
**Fixtures:** BTC 1h, ETH 1h, SOL 1h, XRP 4h, DOGE 4h  
**Lockbox-Cutoff:** `2026-09-10T00:00:00Z`  
**Modell-Verdikt:** `MODEL_NO_EVIDENCE`

## 1. Ausgangsfrage

Die Ausgangsfrage war, ob AURA nach Herstellung einer ehrlichen, kausalen und reproduzierbaren Messkette einen zertifizierbaren Out-of-Sample-Edge auf den fünf realen Golden-Master-Fixtures besitzt. Sie wurde gestellt, weil ein technisch korrekt arbeitendes Dashboard, synthetisch grüne Tests oder positives Brutto-Alpha keine statistische Evidenz für reale Profitabilität darstellen. Deshalb wurden Kosten, Regime, Stichprobentiefe, Walk-Forward-Selektion und Fold-Geometrie getrennt untersucht, bevor weitere Strategieparameter hätten verändert werden dürfen.

## 2. Chronologie und Kernaussagen

### Phase A — Diagnose

Phase A zerlegte die bestehende Strategie in Kosten-, Payoff-, Exit-, Regime-, Sample-Size- und Cross-Asset-Komponenten. Der zentrale Befund war, dass das damalige Selektionsobjektiv den vorgesehenen Regime-Filter in kurzen Trainingsfenstern wegen zu weniger Trades auf `-Infinity` setzte und damit systematisch wegselektierte. D4 lokalisierte die besseren Ergebnisse im ADX-Regime 20–30 und Verluste im Chop; D5 zeigte zugleich, dass die beobachteten Stichproben und Sharpe-Werte weit von einer DSR-Zertifizierung entfernt waren.

### Phase B — Gated-Variante und volle Historie

Die erzwungen gated Variante reduzierte auf den drei 1h-Assets die Verluste deutlich und drehte die mittlere Net-Expectancy ungefähr auf flat bis leicht positiv. Die beiden 4h-Assets bestätigten diese Richtung jedoch nicht; damit scheiterte die Cross-Asset-Bestätigung. Auf voller Fixture-Tiefe wuchs die Stichprobe, doch die gated Variante blieb mit 21–65 Trades je Fixture unter dem vorab geforderten Wert von 100 und war weiterhin nicht zertifizierbar.

### Phase C — Selektionsobjektiv-Reform EXP-024

EXP-024 ersetzte den harten Ausschluss ab weniger als fünf Trades durch das vorab festgelegte regularisierte Objektiv mit `minTrainTrades=2`. Der Fix ist fachlich korrekt und minimal, wirkte in der OOS-Tabelle aber nur auf SOL und XRP; BTC, ETH und DOGE blieben bit-identisch. Er erzeugte gegenüber der alten Selektion genau einen zusätzlichen Gate-Flip (XRP Fold 2); die dortige Expectancy-Verbesserung entstand durch geringere Exposition, obwohl die Qualität pro verbleibendem Trade schlechter wurde. Das präregistrierte 1h-Kriterium war je Asset nur auf SOL positiv und daher lediglich teilweise erfüllt.

### Phase D — Fairer Harness und bindende Stopp-Regel

EXP-025 vergrößerte ausschließlich im Mess-Harness das erste Trainingsfenster auf 2.000 Bars für 1h beziehungsweise 500 Bars für 4h; Produktionsindikatoren, Gates, Schwellen und Objektiv blieben unverändert. Der mittlere Fold-1-Trade-Anteil sank auf 26,5 %, aber SOL lag einzeln bei 42,3 %, und auf 4h reichten 500 Bars weiterhin nicht für mindestens fünf gated Train-Trades in jedem Fold. Der konservativ gepoolte Gated-DSR betrug bei 205 OOS-Trades und $T=45$ nur 0,038. Damit griff die vorab festgelegte D2-Stopp-Regel und beendete die Edge-Forschung vor B3.

## 3. Abschlussverdikt

**„Keine zertifizierbare Out-of-Sample-Evidenz auf den 5 Fixtures; aggregierter OOS-DSR 0.038 (T=45) < 0.50; B3 nicht durchgeführt."**

## 4. Was das Framework geleistet hat

Das Framework hat ein wahrheitsgemäßes Negativergebnis produziert, statt eine weitere Parameteriteration bis zu einem grünen Ergebnis zuzulassen. Es hat einen realen Selektionsfehler und einen Fold-Geometrie-Bias sichtbar gemacht, beide reproduzierbar gemessen und die Objektiv- sowie Geometrie-Parität durch unabhängige Python-Spiegel abgesichert. Vor allem hat die bindende Stopp-Regel verhindert, dass TP1-/R:R-Tuning auf denselben historischen Fixtures eine p-Hacking-Spirale eröffnet.

## 5. Was ausdrücklich nicht behauptet wird

- Es wird kein realer oder zertifizierter Trading-Edge behauptet.
- Das Modell ist kein „vielversprechender Kandidat" und erhält kein Live-Trading-GO.
- Positive Einzelwerte auf ETH oder SOL ersetzen weder Cross-Asset-Konsistenz noch die DSR-Schwelle.
- Das synthetische Gate `PAPER_CANDIDATE` belegt nur Software- und Fixture-Integrität, keine Modell-Evidenz.
- Die Objektiv-Reform behebt einen Selektionsdefekt; sie beweist keine Profitabilität.

## 6. Offene Punkte

### Lockbox-Holdout

Die Forward-Lockbox ist unbewertet. Ihr Cutoff bleibt `2026-09-10T00:00:00Z`; in den aktuellen Fixtures liegen keine gesperrten Bars, daher lautet der Status `UNUSED`. Eine spätere Lockbox-Auswertung darf nur auf neu hinzugekommenen, bis dahin unangetasteten Bars erfolgen und ändert nichts rückwirkend an diesem Forschungsabschluss.

### Versionsentscheidung

Der dokumentierte EXP-024-Objektiv-Fix und die Research-Dokumentation werden als Patch-Release v1.1.2 veröffentlicht. Das Software-Verdikt darf dabei grün sein, während das Modell-Verdikt unverändert ehrlich `MODEL_NO_EVIDENCE (real)` bleibt.

## 7. Präregistrierungs-Transparenz

EXP-022, EXP-024 und EXP-025 wurden laut Session-Protokoll vor ihren Messläufen eingetragen, besitzen jedoch keinen jeweils vorausgehenden, separaten Präregistrierungs-Commit. Sie sind deshalb als `prä-registriert (Session-Protokoll, nicht git-belegt)` gekennzeichnet und werden nicht als git-belegte Präregistrierungen gewertet. Ab dem nächsten Experiment sind Hypothese und Erfolgskriterium zwingend in einem eigenen Commit festzuhalten, dessen Hash vor dem Lauf im Ledger steht.
