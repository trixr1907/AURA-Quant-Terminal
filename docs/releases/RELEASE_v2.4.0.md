# AURA v2.4.0 — Confluence Terminal (read-only research)
## Release-Bericht: Triple-Forensik Fix (Runde 38)

**Datum:** 2026-09-16

**Branch:** `feat/round38-v2.4.0-triple-forensik-fix`

**Tag-Botschaft:** `AURA v2.4.0 — Confluence Terminal (read-only research)`

**Ausgangsbasis:** `c999a0346d6700b6e0e5f4aaf6d421fc6f6c0cb1`

## 1. Zweck

R38 behebt die Warnungen des Triple-Persona-Audits, ohne die globale Modellwahrheit zu verändern. Der Release ist MINOR, weil `classifyRadarTf` neue, rückwärtskompatible Schwellenparameter besitzt und die Autobot-Profile 58/65/75 im Fresh-Gate tatsächlich wirksam werden. AURA bleibt ein Read-only-Research- und Paper-Simulationssystem ohne Live-Orderpfad.

## 2. Implementierte Korrekturen

- `evaluateAutobotEdge` verlangt endliche, vorhandene und nicht-konstante OOS-Returns. DSR=0.5 aus Nullvarianz kann kein Entry-Gate mehr passieren.
- `regimeOf` nutzt ein preisrelatives Epsilon `max(1e-12, |EMA200| × 1e-12)`; flache Reihen bleiben über Preisgrößen hinweg `SIDEWAYS`.
- `classifyRadarTf` akzeptiert `longTh`/`shortTh`. Nur das Autobot-Fresh-Gate übergibt die Profilwerte; der Discovery-Radar bleibt unverändert bei 75/25.
- Headless-Runner und Dashboard nutzen dieselbe profilabhängige Fresh-Gate-Logik.
- DSR-Ampel nutzt das operative Profil-Gate: ≥0.80 grün, ≥Gate amber, darunter rot.
- Score wird als Index statt Gewinnwahrscheinlichkeit, Kelly als Stichproben-Edge statt Einzeltrade-Gewinn und DSR als Skala 0–1 erklärt.
- Tutorial enthält sichtbare Research-only-Disclaimer in Header und Footer sowie korrigierte Version und R-Multiple.
- DSR-Default T=18 und Score-Clamp [0,100] sind durch neue Verhaltens-Tests mutationsempfindlich abgesichert.

## 3. Bekannte Test-Qualitätslücke (R39-Backlog)

Das Audit fand in einzelnen älteren Suites einen hohen Anteil statischer `source.includes()`-/`indexOf()`-Assertions. Außerdem deckt `scripts/audit_rev2_mutations.py` DSR, `headless_autobot.js` und Python-Module noch nicht ab. Diese Arbeit bleibt bewusst R39-Backlog: R38 schließt die konkret überlebenden DSR-Default- und Score-Clamp-Mutationen mit verhaltensbasierten Tests, führt aber keinen breiten Harness-Umbau durch.

## 4. Evidenzstatus und Invarianten

- Globale Release-Wahrheit: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
- Ledger: EXP-032 und Chain-Head bleiben unverändert.
- Lockbox: `UNUSED`; kein Holdout-Lauf wurde ausgelöst.
- Kostenmodell: 0.1% Maker / 0.1% Taker / 0.1% Slippage unverändert.
- Kelly, DSR-Formel, PAVA, Score-Gewichte, SL/TP und Walk-Forward-Geometrie unverändert.
- `innerHTML`-Kanon: 63; R38 fügt keine neuen `innerHTML`-Sinks hinzu.

## 5. Abnahmeprotokoll

| Kriterium | Status | Beleg |
|---|---|---|
| Nullvarianz 6/12 identische +1R reject | PASS | `tests/test_r38_quant_guards.js` |
| Flache Reihe → SIDEWAYS | PASS | `tests/test_r38_quant_guards.js` |
| Profil 58 erlaubt Score 60, Profil 75 blockiert | PASS | `tests/test_r38_quant_guards.js` |
| DSR-Default T=18 mutationsempfindlich | PASS | `tests/test_dsr_default_trials.js` |
| Score-Clamp negative Inputs → 0 | PASS | `tests/test_score_clamp_negative.js` |
| Vollständige Suites / Release-Gate / Ledger | PASS | pytest: 504 passed + 69 subtests; 97 JS-Suites; release_check: 120/120 PASS, Exit 0, SOFTWARE_GO / MODEL_NO_EVIDENCE; verify_ledger Exit 0 |
| PR/CI/Merge/Tag/Release/Asset/Deploy | PENDING | Wird nach Veröffentlichung ergänzt |
