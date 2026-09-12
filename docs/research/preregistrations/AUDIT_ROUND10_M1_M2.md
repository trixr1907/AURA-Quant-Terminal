# Präregistrierung — Audit Runde 10: Ledger-Checkpoint und CVD-Referenz

Datum: 2026-09-12
Ausgangscommit: `8a8c691a647553ca1ca1e8b222f0876c00d18dee`
Ausgangsversion: `1.2.9`

## Eingefrorene Baseline

Ausgeführt vor jeder Produktänderung:

    git status --short --branch
    ## main...origin/main

    git fetch origin --tags
    git rev-parse HEAD
    8a8c691a647553ca1ca1e8b222f0876c00d18dee

    git rev-parse origin/main
    8a8c691a647553ca1ca1e8b222f0876c00d18dee

    python3 --version
    Python 3.12.3

    node --version
    v26.5.1

    python3 -m pytest -q
    204 passed, 57 subtests passed in 2.85s
    PYTEST_EXIT=0

## M-1 — Tail-Truncation durch separaten Checkpoint schließen

Klassifikation: Prozess-Fix (`delta = 0`)

Hypothese: Ein produktpflichtiger Checkpoint außerhalb `docs/**`, der `last_entry_id`, `entry_count` und `chain_head` bindet, macht auch das Entfernen des letzten intern gültigen JSONL-Eintrags für den ausführbaren Verifier sichtbar.

Geplante Änderung:

- produktpflichtige Checkpoint-Datei außerhalb `docs/**`;
- fail-closed Vergleich aller drei Checkpoint-Felder in `scripts/verify_ledger.py`;
- `scripts/append_ledger.py` als einziger dokumentierter Append-Pfad mit validiertem Append und atomarem Checkpoint-Update per temporärer Datei plus `os.replace`;
- echte Dateisystemtests für gültigen Zustand, Tail-Löschung, korrekten Skript-Append, direkten JSONL-Append und Checkpoint-Manipulation.

Vorab festgelegtes Erfolgskriterium:

1. Gültige Kette und gültiger Checkpoint ergeben PASS.
2. Entfernen des letzten Eintrags bei unverändertem Checkpoint ergibt FAIL.
3. Korrekter Append über `append_ledger.py` ergibt PASS.
4. Direkter JSONL-Append ohne Checkpoint-Update sowie jede Manipulation eines gebundenen Checkpoint-Felds ergeben FAIL.
5. Fehlender oder unparsbarer Checkpoint ergibt FAIL.

Grenze: Der Checkpoint liefert Tamper-Evidenz, keine Tamper-Prävention. Eine gemeinsame Änderung von Kette und Checkpoint bleibt technisch möglich, wird aber als Produktänderung durch Versions-Gate, Git-Historie, Pull-Request-Review und annotierten Release-Tag verankert.

## M-2 — CVD-Langzeitmessung mit unabhängiger Python-Referenz

Klassifikation: Diagnose (`delta = 0`)

Hypothese: Eine eigenständige Python-Implementierung der in `Symbiose_Signal_System_v1.pine` spezifizierten CVD-/EMA-CVD-Formeln stimmt auf den fünf vorhandenen Golden-Master-OHLCV-Fixtures hinreichend genau mit dem realen Dashboard-Analyzer-Pfad überein, ohne entscheidungsrelevante Kipper zu erzeugen.

Geplante Änderung und Messung:

- `scripts/cvd_reference.py` implementiert CVD und EMA-CVD unabhängig in Python;
- ein Node-Harness führt dieselben CSV-Zeilen durch den vorhandenen Dashboard-Analyzer und serialisiert `cvd`, `emaCvd` und `cvdDelta` je Bar;
- ein reproduzierbarer Vergleich misst BTCUSDT/ETHUSDT/SOLUSDT 1h sowie XRPUSDT/DOGEUSDT 4h;
- je Symbol werden Bars, maximale absolute Drift, maximale relative Drift und die Anzahl unterschiedlicher `cvd > emaCvd`-Prädikate ausgegeben.

Die in v1.2.9 präregistrierten Entscheidungsschwellen bleiben unverändert:

- jeder echte `cvd > emaCvd`-Kipp erzwingt einen Fix;
- maximale relative Drift größer `1e-10` erzwingt einen Fix;
- null Kipper und maximale relative Drift kleiner oder gleich `1e-10` erlauben den Status `AKZEPTIERT` mit symbolweisen Messzahlen.

Die Diagnose verändert weder Signalformel noch Schwellenwert, Gewichtung, Universum oder Auswahlverhalten. Daher erhöht sie `total_model_experiments` nicht. Falls die Messung einen Fix der Modellimplementierung verlangt, wird vor diesem Fix ein neuer Eintrag mit begründeter Klassifikation angelegt.

## Release-Disziplin

Diese Präregistrierung und ihre Ledger-Einträge sind docs-only und release-neutral. Verifier, Append-Skript, Checkpoint und CVD-Harness sind Produktänderungen und erzwingen anschließend Version `1.2.10` über Branch, Pull Request und annotierten Tag im Format:

    AURA v1.2.10 — Confluence Terminal (read-only research)
