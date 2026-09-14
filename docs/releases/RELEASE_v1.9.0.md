# AURA v1.9.0 — Evidenz-Programm, PreReg & Shadow Collector

**Release-Typ:** MINOR (`1.9.0`, Evidenz-Programm, Daten-Audit, PreReg, Shadow Collector & Lockbox Governance)  
**Datum:** 2026-09-14  
**Research-Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`  
**Trials-Ledger:** unverändert `EXP-032` (Entry-Count 7, Total 10)  

---

## Überblick

AURA v1.9.0 führt das vollständige Evidenz-Programm (Slices A–E) ein. Ziel ist die lückenlose methodische und kryptographische Absicherung von quantitativen Hypothesen von der ersten Idee bis zum Live-Betrieb, ohne Scheingewinne oder Overfitting vorzutäuschen.

---

## Wichtigste Neuerungen

### Slice A — Daten-Fundament
- Neues Audit-Werkzeug `scripts/data_foundation_audit.py` zur deterministischen Prüfung aller Kerzen-Fixtures (geschlossene Kerzen, Zeitspannen, Lückenfreiheit, Duplikate, Null-/Outlier-Werte und Provenienz).
- Klare Trennung: Daten werden strikt als `REAL`, `SYNTHETIC` oder `UNKNOWN` klassifiziert.
- Schwellenwert $N = 1000$ Kerzen für Walk-Forward-Tauglichkeit.
- Dokumentation in `docs/research/DATA_FOUNDATION.md`.

### Slice B — PreReg & Check
- Erweiterung von `scripts/append_ledger.py` um den `--prereg`-Modus für unveränderliche `Hypothesis-PreReg`-Einträge im Ledger.
- `scripts/hypothesis_check.py` prüft Modellergebnisse deterministisch gegen die Vorab-Registrierung (exakte Übereinstimmung von `params_sha256`, Symbol, Timeframe und Acceptance-Kriterien).

### Slice C — Shadow Collector
- Neues Node-Modul `shadow_collector.js` im Server-Runner für die lückenlose Vorwärts-Erfassung jeder Funnel-Kandidaten-Entscheidung (`ACCEPTED` / `REJECTED` mit exaktem Ablehnungsgrund).
- Deterministische 24-Bar-Outcome-Auswertung (`hit_sl`, `hit_tp1`, `hit_tp2`, `time_stop`, Netto-R) mit Berücksichtigung von Gebühren (Maker 0.1%, Taker 0.1%, Slippage 0.1%).
- Automatische Retention (180 Tage) und Cap-Begrenzung (20 MB) mit atomarem Rewrite.
- Telemetrie in `/ready` (`shadow:{enabled,entries,pending_outcomes,evaluated}`) und Erweiterung des Daily-Digest.

### Slice D — Lockbox Registrar
- `scripts/lockbox_register.py` zur explizit bestätigten Sperrung von Holdout-Daten für $N$ Tage (`LOCKED`).
- Single-Shot-Regel: Verhindert Mehrfach-Auswertungen desselben Holdouts.

### Slice E — Evidenz-Protokoll & Governance
- Umfassende Governance-Spezifikation in `docs/research/EVIDENCE_PROTOCOL.md`.
- 6-Stufen-Modell (S1 bis S6), Kriterien für Statushebung (nur Lockbox-Pass UND registrierte Forward-Kriterien), 90-Tage-Rollfenster und Evidence-Decay.
- Transparente Begründung des heutigen `NO_EVIDENCE`-Status auf Basis realer OOS-Metriken.

---

## Scope und Grenzen

- Keine Änderungen an Signalrichtung, Score-, Regime-, ADX-, Squeeze-, OOS-/DSR- oder Universe-Gates.
- Keine Lockbox-Auswertung/Nutzung in dieser Runde.
- Echte Ledger-Kette unverändert auf `EXP-032`; `ledger_checkpoint.json` unverändert.
- Urteil bleibt ehrlich `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
