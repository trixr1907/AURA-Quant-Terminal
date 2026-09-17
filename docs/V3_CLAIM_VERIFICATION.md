# AURA v3 — Claim-Verifikation (V3_CLAIM_VERIFICATION.md)

**Status:** IN ARBEIT — keine Produktfreigabe · **Datum:** 2026-09-17 · **Prüf-Scope:** Überprüfung der Behauptungen aus dem vorherigen Abschlussbericht gegen die tatsächliche Codebasis, Tests und Artefakte im Branch `audit/r40-baseline` (HEAD `958d7ad3fe0846732cf3185277ca5c89c6434675`).

## 0. Eingefrorener tatsächlicher Ausgangsstand

| Merkmal | Beobachtung | Ergebnis |
|---|---|:---:|
| Workspace | `/home/ivo/projects/AURA_v2` vorhanden | PASS |
| Branch / HEAD | `audit/r40-baseline` / `958d7ad3fe0846732cf3185277ca5c89c6434675` | PASS |
| Historie | P1–P8-Commits `231df73` bis `958d7ad` vorhanden | PASS |
| Arbeitsbaum | Bereits vor dieser Verifikationsrunde modifizierte Dateien und untracked Verifikationsartefakte vorhanden; Details unten | UNVERIFIED |
| Runtime | Python 3.12.3, Node v26.5.1, Docker 29.1.3 | PASS |
| Compose-Plugin | `docker compose` nicht installiert (`docker: unknown command: docker compose`) | FAIL |

Vorhandene Änderungen beim Start dieser Runde wurden geschützt und nicht verworfen:

- modifiziert: `Dockerfile`, `aura/api/app.py`, `aura/api/routes.py`, `aura/runner/paper_engine.py`, `aura/runner/worker.py`, `docker-compose.yml`, `docs/research/audit_r40/ux.md`
- untracked: `docs/V3_CLAIM_VERIFICATION.md`, `tests/test_v3_quant_accounting_independent.py`, `tests/test_v3_vertical_integration.py`

Diese Änderungen stammen aus einer vorangegangenen, abgebrochenen Verifikationsarbeit und sind deshalb nicht als geprüfter Stand zu behandeln. Die ersten real ausgeführten Baselines zeigen bereits zwei Accounting-/Restart-Fehler. Vollständiges Pytest-Log: `docs/evidence/v3_acceptance_20260917/pytest_full.log`.

---

## 1. Verifikationsmatrix aller v3-Kernclaims

| Claim | Codepfad | Ausgeführter Test | Artefakt | Ergebnis | Verbleibende Lücke |
|---|---|---|---|:---:|---|
| **C-01:** SQLite WAL Store & Schema v2 | `aura/store/db.py`, `migrations/0001_init.sql`, `0002_processed_bars.sql` | `python3 -m pytest tests/test_v3_store.py -v` | `tests/test_v3_store.py` | **PASS** | Schema v2 ergänzt genau-einmal-Claim für geschlossene Bars. |
| **C-02:** Append-Only Trigger für Audit & Shadow | `aura/store/migrations/0001_init.sql` | `tests/test_v3_store.py::test_append_only_triggers` | SQLite Trigger in Schema | **PASS** | Keine. Verhindert unberechtigte Updates auf Logs. |
| **C-03:** Idempotenter Legacy-Import aus JSON | `aura/store/legacy_import.py` | `tests/test_v3_store.py::test_real_import_maps_fields` | `tests/test_v3_store.py` | **PASS** | Reale Produktiv-DB auf VM muss bei Deployment migriert werden. |
| **C-04:** Kanonische Indikatoren (EMA, ATR, VWAP, CVD-Proxy) | `aura/core/indicators.py` | `python3 -m pytest tests/test_v3_core_indicators.py -v` | `docs/FORMULA_SPEC.md` (F01–F25) | **PASS** | Keine. 16 Handberechnungen & UTC-Resets verifiziert. |
| **C-05:** Fractional Kelly mit Sample-Shrinkage | `aura/core/risk.py` | `tests/test_v3_core_risk.py::test_kelly_sample_shrinkage` | `docs/FORMULA_SPEC.md` (F45) | **PASS** | Keine. Formel nach Thorpe/López de Prado verifiziert. |
| **C-06:** Lot-Sizing mit ULP-Schutz & Budget-Cap | `aura/core/risk.py` | `tests/test_v3_core_risk.py::test_size_position_never_exceeds_risk_budget` | `docs/FORMULA_SPEC.md` (F46) | **PASS** | Keine. Truncation auf Bitget Lot-Steps ohne Overshoot. |
| **C-07:** Hebelempfehlung als Margin-Regler | `aura/core/risk.py` | `tests/test_v3_core_risk.py::test_leverage_does_not_change_stop_loss_distance` | `docs/FORMULA_SPEC.md` (F47) | **PASS** | Keine. SL-Distanz bleibt unberührt. |
| **C-08:** Confluence-Scoring & Makro-Cap ($\pm 15$) | `aura/core/scoring.py` | `python3 -m pytest tests/test_v3_core_scoring.py -v` | `docs/FORMULA_SPEC.md` (F35–F44) | **PASS** | Keine. Gewichte summieren exakt zu 100%. |
| **C-09:** Deflated Sharpe Ratio (DSR) & PAVA | `aura/core/stats.py` | `python3 -m pytest tests/test_v3_core_stats.py -v` | `docs/FORMULA_SPEC.md` (F50–F58) | **PASS** | Keine. Acklam-Approximation & Monotonie belegt. |
| **C-10:** Accounting-Erhaltungsgleichung | `aura/core/stats.py`, `aura/runner/paper_engine.py` | Vorher: vollständige Suite rot; nach Fix: `python3 -m pytest -ra` | `docs/evidence/v3_acceptance_20260917/{pytest_full,accounting_fix,pytest_full_after_accounting_fix}.log` | **PASS** | Entry-Fee wird jetzt beim Öffnen von Equity abgezogen; vollständige Python-Suite nach Fix 595/595 grün. Funding und freie-Mittel-/Margin-Ledger bleiben separat UNVERIFIED. |
| **C-11:** Parität mit Golden-Fixtures & JS-Orakeln | `aura/core/` vs Reference | `python3 -m pytest tests/test_v3_core_parity.py -v` | `tests/test_v3_core_parity.py` | **PASS** | Keine. 5 Paritätsprüfungen grün. |
| **C-12:** Fix Q-01 (Equity-Update mit Realized PnL) | `aura/runner/paper_engine.py` | Red-first Handrechnung, danach 13 gezielte Tests und vollständige Python-Suite | `docs/evidence/v3_acceptance_20260917/accounting_fix.log` | **PASS** | Entry-Fee und Exit-Netto-PnL fließen jetzt in die Equity. Freie Mittel/Margin sind noch kein separates persistentes Ledger. |
| **C-13:** Fix Q-02 (50% TP1-Exit & Breakeven-SL-Shift) | `aura/runner/paper_engine.py` | Restart während TP1-Teil-Exit, anschließend BE-SL | `docs/evidence/v3_acceptance_20260917/accounting_fix.log` | **PASS** | Initial-Notional bleibt bei Updates erhalten und stellt Initial-/Restmenge exakt wieder her; gezielte Suite 13/13 grün. TP3 ist weiterhin nicht implementiert. |
| **C-14:** Fix Q-03 (Konservative Intrabar-SL-Priorisierung) | `aura/runner/paper_engine.py` | `tests/test_v3_runner.py::test_intrabar_collision_conservative_policy` | `tests/test_v3_runner.py` | **PASS** | Keine. Bei SL+TP-Hit im selben Bar greift SL. |
| **C-15:** Fix Q-04 (Saubere Exit-Labels für Timestop) | `aura/runner/paper_engine.py` | `tests/test_v3_runner.py::test_timestop_labeled_correctly` | `tests/test_v3_runner.py` | **PASS** | Keine. `TIMESTOP` als eigener Exit-Reason geführt. |
| **C-16:** Not-Halt Zustandsmaschine (FSM) | `aura/api/routes.py`, `aura/runner/worker.py`, `aura/runner/state_machine.py` | API und Worker mit getrennten SQLite-Verbindungen; Halt und Resume über persistierte Commands | gezielter Test `TestCrossProcessControlPlane` | **PASS** | API-Commands erreichen jetzt den separaten Worker-Prozess idempotent über SQLite. UI-Bedienung und Restart-/Race-Störungstests bleiben UNVERIFIED. |
| **C-17:** Bitget REST Adapter v2 mit Rate-Limiter | `aura/data/bitget_adapter.py` | `python3 -m pytest tests/test_v3_vertical_integration.py::TestBitgetOnlineIntegration::test_live_bitget_public_feed_and_validation -ra` | `docs/evidence/v3_acceptance_20260917/vertical_integration.log` | **PASS** | In dieser Runde realer öffentlicher Abruf, Normalisierung und Invariantenprüfung erfolgreich. Künftige Nichterreichbarkeit wird explizit als `NOT_RUN`/Skip statt PASS klassifiziert. |
| **C-18:** Physikalische Kerzen-Invarianten & Gaps | `aura/data/validation.py`, `gap_detector.py` | `tests/test_v3_data.py::test_detect_gaps_in_series` | `docs/DATA_CONTRACTS.md` | **PASS** | Keine. Validierung filtert korrupte Kerzen. |
| **C-19:** Event-basierte Backtest-Engine & Walk-Forward | `aura/backtest/engine.py`, `walk_forward.py` | `python3 -m pytest tests/test_v3_backtest.py -v` | `docs/MODEL_VALIDATION.md` | **PASS** | Isolierte Tests grün; Funding-Carry, Holdout-Prozess und Produktionsparität bleiben UNVERIFIED. |
| **C-20:** Kostenmodell (0.02% Maker, 0.06% Taker, 0.015% Slip) | `aura/backtest/engine.py`, `aura/runner/paper_engine.py` | unabhängige Runner-Handrechnung plus Backtest-Kostensensitivität | `docs/evidence/v3_acceptance_20260917/accounting_fix.log` | **FAIL** | Runner-Entry-Fee ist korrigiert. Backtester belastet Entry-Fees noch nicht gegen Equity; Funding fehlt. Quellen und zeitliche Gültigkeit gegenüber Altmodell 0,10%/0,10%/0,10% bleiben UNVERIFIED. |
| **C-21:** FastAPI Control Plane & Constant-Time Token Auth | `aura/api/auth.py`, `aura/api/routes.py`, `aura/api/app.py` | `python3 -m pytest tests/test_v3_api_security.py -v` | `docs/SECURITY.md` | **FAIL** | API-Token-Unit-Tests bestehen, aber ausgeliefertes Dashboard ruft Legacy-`/api/state` und `/api/bot-config` auf; v3 bietet für POST `/api/state`/`/api/bot-config` keine kompatiblen Routen. Browser-Login/Session/CSRF fehlen; CORS ist `*` mit Credentials. |
| **C-22:** Docker Compose Multi-Container & Security Hardening | `Dockerfile`, `docker-compose.yml` | `docker compose version` | Baseline-Kommandoausgabe vom 2026-09-17 | **NOT_RUN** | Compose-Plugin fehlt lokal. Dockerfile enthält aktuell widersprüchliche Versionen und versucht `chown aura:aura`, bevor der Benutzer angelegt wird; sauberer Build ist noch nicht bewiesen. |
| **C-23:** Online SQLite Backup & Verified Restore | `scripts/backup.py`, `scripts/restore.py` | `python3 -m pytest tests/test_v3_backup_restore.py -v` | `docs/OPERATIONS_RUNBOOK.md` | **PASS** | Dateibackup, Checksum und Integrity-Check isoliert bestanden; Start aus Restore und duplikatfreie Fortsetzung bleiben UNVERIFIED. |
| **C-24:** 24h Soak-Test | nicht vorhanden | nicht ausgeführt | kein Soak-Artefakt vorhanden | **NOT_RUN** | Es existiert derzeit weder `scripts/soak_test.py` noch `docs/RELEASE_EVIDENCE.md`; dauerhafte Ausführungsumgebung und Harness fehlen. |
| **C-25:** Statistischer Edge-Beweis (Model Evidence) | `aura/backtest/`, `aura/runner/` | keine vorab registrierte neue Modellabnahme ausgeführt | `docs/MODEL_VALIDATION.md` | **UNVERIFIED** | Modellstatus bleibt `MODEL_NO_EVIDENCE`. Die Dokumentation formuliert eine universelle N≥30-Schwelle; das ist keine belegte allgemeine Evidenzregel und muss korrigiert werden. |
| **C-26:** Vertikaler Signalerzeugungs-Worker | `aura/runner/worker.py`, `aura/store/migrations/0002_processed_bars.sql` | deterministischer Replay plus getrennte API-/Worker-Verbindungen | `docs/evidence/v3_acceptance_20260917/vertical_integration.log` | **PASS** | Worker erzeugt nach fail-closed Liquiditätsgate neue Paper-Entries, persistiert rohe Kerzen, verarbeitet nur geschlossene Bars genau einmal, verwaltet TP1/TP2 und API lädt Worker-Schreibstände nach. UI, Funding/TP3 und vollständige Regime-/MTF-Gates bleiben separate Lücken. |

---

## 2. Tatsächlich ausgeführte Testbaseline

| Scope | Exakter Befehl | Ergebnis | Exit | Artefakt |
|---|---|---|---:|---|
| v3 vollständig, vor Fix | `python3 -m pytest tests/test_v3_*.py -ra` | 87 gesammelt; 85 passed, 2 failed | 1 | Fehler im ursprünglichen Gesamtsuite-Log |
| Python vollständig, vor Fix | `python3 -m pytest -ra` | 595 gesammelt; 593 passed, 2 failed; keine Skips berichtet | 1 | `docs/evidence/v3_acceptance_20260917/pytest_full.log` |
| Accounting/Restart nach Fix | `python3 -m pytest tests/test_v3_quant_accounting_independent.py tests/test_v3_runner.py tests/test_v3_vertical_integration.py -ra` | 13 passed | 0 | `docs/evidence/v3_acceptance_20260917/accounting_fix.log` |
| Python vollständig, nach Fix | `python3 -m pytest -ra` | 595 passed; keine Fehler oder Skips berichtet | 0 | `docs/evidence/v3_acceptance_20260917/pytest_full_after_accounting_fix.log` |
| Vertikale Integration nach Persistenz-/Control-Plane-Fix | `python3 -m pytest tests/test_v3_vertical_integration.py -ra` | 7 passed, echter Bitget-Abruf enthalten | 0 | `docs/evidence/v3_acceptance_20260917/vertical_integration.log` |
| Python vollständig nach vertikaler Integration | `python3 -m pytest -ra` | 600 passed; keine Fehler oder Skips | 0 | `docs/evidence/v3_acceptance_20260917/pytest_full_after_vertical_fix.log` |
| Bestehende JS-Suiten | dynamische Ausführung aller `tests/test_*.js` einzeln mit Node und `AURA_DISABLE_AUTO_SYNC=1` | 98/98 PASS, 0 FAIL, 0 TIMEOUT | 0 | `docs/evidence/v3_acceptance_20260917/js_full.log`, `js_results.json` |
| Release-Gate | noch nicht erneut in disposable Worktree ausgeführt | NOT_RUN | — | — |
| Browser-E2E | noch nicht ausgeführt | NOT_RUN | — | — |
| Compose | Plugin lokal nicht verfügbar | NOT_RUN | — | — |

Historische, inzwischen behobene Blocking-Failures (Red-Nachweis bleibt erhalten):

1. `test_hand_calculated_long_two_stage_tp`: Entry-Fee fehlte in der laufenden Equity.
2. `test_restart_during_partial_exit_preserves_be_and_pnl`: verbleibende Menge wurde beim Restart nicht exakt wiederhergestellt.

Beide Fehler wurden minimal im Runner/Persistenzpfad behoben und durch `accounting_fix.log` sowie die vollständige grüne Python-Suite gegengeprüft.

## 3. Zusammenfassung der Claim-Klassifikation

Die frühere Zählung „21 PASS“ ist verworfen: Sie beruhte überwiegend auf isolierten Tests und nicht auf der geforderten Produktintegration. Bis zur vollständigen Regression, E2E- und Betriebsprüfung gilt:

- **PASS:** nur eng begrenzte, oben ausdrücklich als isoliert bestandene Komponentenclaims.
- **FAIL:** vollständige Browser/Control-Plane-Integration und dadurch weiterhin das globale SOFTWARE-GO.
- **UNVERIFIED:** Funktionsparität, Kostenquellen, Funding, TP3, Migration-Vollständigkeit, Restore-Fortsetzung sowie mehrere Quant-Definitionen.
- **NOT_RUN:** Release-Gate, Browser-E2E/Screenshots, Compose, Störungstests und 24h-Soak.
- **Modellstatus:** `MODEL_NO_EVIDENCE`; synthetische Trades sind ausschließlich Testdaten.
