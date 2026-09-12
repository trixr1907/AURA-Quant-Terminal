# Präregistrierung — AURA Audit Runde 9 (M-1 und M-3)

Datum: 2026-09-12
Zielversion: v1.2.9
Baseline: v1.2.8 (`4a61692a8e35cbe37ba01ce4701fbdfd41fb4c3e`)

## M-1 — DSR-Suchraum aus dem Trials-Ledger

Klassifikation: Prozess-Fix (`Δ = 0`)

Begründung: Die Maßnahme verändert weder Signalregeln noch Indikatoren, Schwellenwerte, Parameter-Grids, Selektion oder Handelslogik. Sie korrigiert ausschließlich die bereits vorhandene Multiple-Testing-Bilanzierung, indem die DSR-Deflation den kumulativen, verifizierten Ledger-Zähler statt eines aktuellen Radar-Multiplikators verwendet. Es wird keine neue Modellvariante gegen Marktdaten erprobt.

Vorab festgelegte Erfolgskriterien:

1. Ein gültiges Ledger liefert seinen verifizierten Wert `total_model_experiments` als autoritative Untergrenze für die DSR-Trial-Zahl.
2. Fehlendes, unparsbares oder kryptografisch ungültiges Ledger führt fail-closed zu keiner DSR-Freigabe.
3. Für `ledger_trials >= legacy_trials` gilt auf identischen Returns `DSR_neu <= DSR_alt`.
4. Tests decken gültiges, fehlendes und manipuliertes Ledger ab.

## M-3 — CVD-Akkumulationspräzision messen

Klassifikation: Diagnose (`Δ = 0`)

Begründung: Die vorregistrierte Messung beobachtet ausschließlich Pine-/JS-Arithmetik auf bestehenden Golden-Master-Daten. Sie ändert zunächst keine Modell-, Signal- oder Schwellenlogik. Falls die Messung Vergleichskipps oder unbeschränkte Drift belegt, wird vor jeder Modelländerung ein separater Eintrag als Modellexperiment (`+1`) präregistriert.

Vorab festgelegte Messung und Entscheidung:

1. Für BTC/ETH/SOL 1h sowie XRP/DOGE 4h werden jeweils mindestens 5.000 Bars ausgewertet.
2. Ausgegeben werden absolute Enddrift, maximale absolute Drift, relative Drift und die Anzahl abweichender `cvd > emaCvd`-Vergleiche je Fixture.
3. Bei mindestens einem Vergleichskipp oder nachweislich unbeschränkt wachsender Drift wird keine Akzeptanz dokumentiert; ein Fix erfordert eine neue `+1`-Präregistrierung.
4. Bei null Vergleichskipps und beschränkter Drift wird F-16 mit dem gemessenen Maximalwert und Messfenster als akzeptiertes numerisches Verhalten dokumentiert.

Diese Datei ist die unveränderliche Vorab-Festlegung. Der nachfolgende Ledger-Eintrag verweist auf den Commit, der diese Präregistrierung erstmals enthält.
