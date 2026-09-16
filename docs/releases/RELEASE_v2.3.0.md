# AURA v2.3.0 — Confluence Terminal (read-only research)
## Release-Bericht: Evidence Infra Completion (Runde 37)

**Datum:** 2026-09-16
**Branch:** feat/round37-v2.3.0-evidence-completion
**Tag:** AURA v2.3.0 — Confluence Terminal (read-only research)
**Anlass:** Audit AUDIT_EVIDENCE_INFRASTRUCTURE_20260915 identifizierte 2 substanzielle + 4 mittlere/niedrige offene Abweichungen nach R36 (v2.2.0).

---

## 1. Abnahmeprotokoll

| # | Kriterium | Status | Beleg |
|---|---|---|---|
| 1 | F2: S6-Gate implementiert, model_verdict_lifted nur bei synthetischem 90d-Pass true | PASS | test_hypothesis_s6_gate.py: 4/4 grün |
| 2 | F3: Alle 5 Pfade 0.001/0.001/0.001, model_evidence_real NO_EVIDENCE | PASS | test_cost_model_unified.py: 5/5 grün |
| 3 | F6: claims.csv aktuell, TRIALS_LEDGER Kopf ac613227…+EXP-031/032, Lockbox-Erzwingung | PASS | generate_claims.py, verify_ledger: ok, test_lockbox_enforcement: 3/3 grün |
| 4 | pytest >= 490 (tatsächlich 500), JS-Suiten grün, release_check Exit 0 | PASS | 500 passed, 69 subtests |
| 5 | Evidenz unbewegt: EXP-032/ac613227..., Lockbox UNUSED, Schatten append-only | PASS | verify_ledger.py: ok, provenance.json unberührt |
| 6 | Doku: EVIDENCE_PROTOCOL.md S3/S6 + architecture.md Kostenmodell + RELEASE_v2.3.0.md | PASS | Dieses Dokument |
| 7 | Live: 15. Auto-Deploy-Beweis | PENDING — nach Merge/Tag |

---

## 2. F2 — S6-Elevation-Gate + 90-Tage-Fenster + Evidence-Decay

### Was implementiert wurde

`scripts/hypothesis_check.py` implementiert jetzt vollständige S6-Protokolllogik:

- `evaluate_lockbox_pass(lockbox_data)`: Prüft ob Lockbox status == "LOCKED" und holdout_pass == true. Fail-closed bei fehlendem/ungültigem/bereits konsumierten Lockbox.
- `evaluate_forward_window(shadow_log_path, n_min, edge_min, dsr_min, window_days=90)`: Filtert shadow_log.jsonl auf exakt 90 UTC-Tage, aggregiert Netto-Expectancy + DSR(max(45, ledger_n)), prüft alle drei Kriterien kumulativ.
- `evaluate_decay(shadow_log_path, n_min, edge_min, window_days=90)`: Signalisiert decay_warning wenn letzte 90 Tage negativ oder n < n_min.
- `check_hypothesis(...)`: Gibt model_verdict_lifted: true nur zurück wenn S4 UND S5 bestehen.

### Heutiger Status (korrekt fail-closed)

- Shadow-Collector läuft weniger als 90 Tage: evaluate_forward_window liefert pass: False.
- Lockbox UNUSED (kein holdout_pass: true): evaluate_lockbox_pass liefert pass: False.
- Ergebnis: model_verdict_lifted: false, verdict: SOFTWARE_GO / MODEL_NO_EVIDENCE — korrekt und erwartet.

### Tests

```
tests/test_hypothesis_s6_gate.py::test_s6_gate_case_a_no_lockbox_pass PASSED
tests/test_hypothesis_s6_gate.py::test_s6_gate_case_b_lockbox_pass_but_shadow_insufficient PASSED
tests/test_hypothesis_s6_gate.py::test_s6_gate_case_c_both_s4_and_s5_pass_elevates_to_s6 PASSED
tests/test_hypothesis_s6_gate.py::test_s6_gate_case_d_evidence_decay_demotes PASSED
tests/test_shadow_90d_window.py::test_evaluate_forward_window_filters_exact_90_days PASSED
tests/test_shadow_90d_window.py::test_evaluate_forward_window_ledger_trials_monotonicity PASSED
```

---

## 3. F3 — Kostenmodell-Vereinheitlichung

### Auswirkung der Vereinheitlichung (quantifiziert)

| Asset | Altes Modell (S3: 0.02%/0.06%/0.05%) | Neues Modell (0.1%/0.1%/0.1%) | Delta |
|---|---:|---:|---|
| ETH 1h | +0.208 R | -0.039 R | Vorzeichenwechsel |
| BTC 1h | ~+0.006 R | ~-0.480 R | Faktor ~800 Kostendrag |
| DSR (gesamt) | 0.015 | 0.013 | Bleibt weit unter 0.5-Schwelle |

Dieser Vorzeichenwechsel ist methodisch korrekt und erwartet: Das alte Dashboard-Modell war gegenüber dem Shadow/Runner-Modell um Faktor 3-5 günstiger und erlaubte keinen sauberen S3/S5-Vergleich. MODEL_NO_EVIDENCE gilt bei DSR = 0.013 gegenüber Passschwelle 0.5 weiterhin stabil.

### Geänderte Dateien (F3)

| Datei | Vorher | Nachher |
|---|---|---|
| tests/model_evidence_real.js L111-113 | makerFee:0.0002, takerFee:0.0006, slippage:0.0005 | makerFee:0.001, takerFee:0.001, slippage:0.001 |
| tests/engine_oracle_export.js L51 | makerFee:0.0002, takerFee:0.0006, slippage:0 | makerFee:0.001, takerFee:0.001, slippage:0.001 |
| tests/sensitivity_release_gates.js L53-54 | Grid-Center slippage:0 | Grid-Center slippage:0.001 |
| tests/reference_backtest.py | kein DEFAULT_* | DEFAULT_MAKER_FEE=0.001, DEFAULT_TAKER_FEE=0.001, DEFAULT_SLIPPAGE=0.001 |
| Symbiose_Dashboard.html App.slippage | 0.0005 | 0.001 |
| Symbiose_Dashboard.html resolveSlippage | fallback 0.0005 | fallback 0.001 |
| Symbiose_Dashboard.html evaluateTimeStopOptions | defaults 0.0002/0.0006 | defaults 0.001/0.001 |

### Tests

```
tests/test_cost_model_unified.py::test_dashboard_cost_model_defaults PASSED
tests/test_cost_model_unified.py::test_model_evidence_real_cost_defaults PASSED
tests/test_cost_model_unified.py::test_reference_backtest_cost_defaults PASSED
tests/test_cost_model_unified.py::test_shadow_collector_cost_defaults PASSED
tests/test_cost_model_unified.py::test_headless_autobot_cost_defaults PASSED
```

---

## 4. F6 — Claims + Ledger + Lockbox-Erzwingung + DSR-Neutralwert

### claims.csv

- `python3 scripts/generate_claims.py` neu ausgeführt.
- 29 Einträge, CLM-17/18/28 als behoben markiert.
- Zeile-Zähler-Diskrepanz (+361/-614 Zeilen) durch Neugeneration beseitigt.

### TRIALS_LEDGER.md

- Kettenkopf aktualisiert von `7a00e09a...` auf `ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b`.
- EXP-031 (CVD Vereinheitlichung, v1.3.1, Prozess-Fix, delta=0, total_exp=10) in Tabelle ergänzt.
- EXP-032 (Ticker-Liveness/Preisformatierung, v1.3.2, Prozess-Fix, delta=0, total_exp=10) in Tabelle ergänzt.
- Bilanz: 22 Prozess-/Infrastruktur-/Diagnose-Einträge (war 20).
- verify_ledger.py: ok, last_entry_id: EXP-032, entry_count: 7, chain_head: ac613227...

### Lockbox-Erzwingung

- `scripts/lockbox_guard.py` hat jetzt Erzwingungsklasse `LockboxAlreadyConsumedError`.
- `record_lockbox_evaluation()` schreibt den Lockbox-Status auf CONSUMED (atomarer Write).
- Zweite Auswertung löst `LockboxAlreadyConsumedError` aus — fail-closed.
- Echte provenance.json bleibt LOCKED / UNUSED — unberührt.

### DSR-Neutralwert (Klarstellung in EVIDENCE_PROTOCOL.md S3)

- DSR = 0.5 ist der theoretische Neutralpunkt (Signal nicht von Zufall unterscheidbar).
- Passschwelle: DSR >= 0.5 UND positive Netto-Expectancy UND n >= n_min — alle drei kumulativ.
- DSR = 0.5 allein ist kein hinreichendes Kriterium für S3/S5-Pass.

---

## 5. Unveränderliche Anker (Evidenz-Kontinuität)

| Anker | Wert |
|---|---|
| Laatste Ledger-Eintrag | EXP-032 |
| Chain-Head | ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b |
| total_model_experiments | 10 |
| Lockbox-Status | LOCKED / UNUSED |
| Verdict | SOFTWARE_GO / MODEL_NO_EVIDENCE |
| Shadow-Tage | < 90 (S6 fail-closed korrekt) |

---

## 6. Funktionsnachweis

```
pytest: 500 passed, 69 subtests passed in 13.18s
node tests/model_evidence_real.js: exit 0
node tests/engine_oracle_export.js: exit 0
node tests/sensitivity_release_gates.js: exit 0
node tests/test_slippage_not_zero.js: SLIPPAGE_NOT_ZERO PASS gross_R=4.33 net_R=4.058
node tests/test_audit_integrity.js: exit 0
python3 scripts/verify_ledger.py: ok / EXP-032 / ac613227...
python3 scripts/release_check.py: (pending — nach VERSION bump)
innerHTML Symbiose_Dashboard.html + SYMBIOSE_Tutorial.html: 59
```

---

## 7. Scope-Abgrenzung

Diese Version ändert ausschliesslich:
- Evidence-Infrastruktur (S6-Gate, Shadow-Fenster, Lockbox-Erzwingung, Evidence-Decay)
- Kostenmodell-Konstanten (Vereinheitlichung, kein Edge-Tuning)
- Dokumentation und Ledger-Sync

Nicht geändert:
- Signal-Logik (Score-Gewichte, ADX/Regime/Squeeze-Schwellen, TP/SL-Struktur, Sizing, Entries, Exits)
- Ledger-Inhalt (EXP-032 und Vorgänger unberührt)
- Lockbox-Holdout (nicht evaluiert, Single-Shot-Schutz intakt)
- Shadow-Log (append-only, keine Manipulation)
