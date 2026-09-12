# AURA v1.2.10 — Confluence Terminal (read-only research)

Datum: 2026-09-12

## Inhalt

- F-06: Separater produktpflichtiger Checkpoint (`ledger_checkpoint.json`) verankert `last_entry_id`, `entry_count` und `chain_head`. Tail-Truncation (Entfernen des letzten Ketteneintrags) erzeugt im fail-closed Verifier `scripts/verify_ledger.py` zwingend einen Fehler.
- F-06: `scripts/append_ledger.py` implementiert den validierten Append-Prozess und aktualisiert den Checkpoint atomar über eine temporäre Datei mit `os.replace`.
- F-16: Unabhängige Python-Referenz `scripts/cvd_reference.py` verifiziert die Pine-Spezifikation gegen die reale JavaScript-Dashboard-Engine über alle 5 Golden-Master-Fixtures (64.859 Bars).
- F-16: Messung belegt 0 Vergleichskipps (`flip_count = 0`) und eine maximale relative Drift von $2,54 \times 10^{-11} \le 1 \times 10^{-10}$. F-16 ist als akzeptiertes numerisches Verhalten abgeschlossen.
- Versionierung und Paketmetadaten auf 1.2.10 synchronisiert.

## Integritätsurteil

`SOFTWARE_GO / MODEL_NO_EVIDENCE`

Die Änderungen schließen die Tamper-Evidenz des Ledgers und belegen die numerische CVD-Implementierungspräzision. Sie beweisen keinen statistischen Edge und verändern die Signallogik nicht.
