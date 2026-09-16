# AURA — Forschungsbericht: R38 v2.4.0 Triple-Forensik Fix & Transparenz-Audit

**Datum:** 2026-09-16  
**Zielversion:** `2.4.0` (MINOR)  
**Baseline-Commit:** `c999a0346d6700b6e0e5f4aaf6d421fc6f6c0cb1`  
**Merge-Commit:** `a4d5da0f764287c766ddb4ad8bcd3e1c6cf3d456`  
**Peeled Release Tag:** `v2.4.0` -> `a4d5da0f764287c766ddb4ad8bcd3e1c6cf3d456`  
**Release Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`

---

## 1. Ausgangslage: Forensik-Audit-Befunde (c999a03)

Das vorangegangene Triple-Persona-Forensik-Audit (Quant, Endnutzer, DevSecOps) ergab 0 Blocker, 12 Warnungen und 3 Auflagen:
1. **Divergenz Doku vs. Code (Q-1):** `PHASE1_REPORT.md` dokumentierte Setup-DSR >= 0.5, während operative Profile 0.10/0.05/0.30 nutzen.
2. **Nullvarianz-DSR Pass-Through (Q-2):** `calcDSR` liefert bei identischen Returns neutral 0.5; dieser Wert passierte Profile mit Hürden <= 0.5 ohne Streuungsinformation.
3. **Epsilon bei flachen Reihen (Q-3):** Flache EMA-Reihen konnten durch ULP-Drift von SIDEWAYS zu schwachem BEAR kippen.
4. **Wirkungsloses Profil "Aktiv (Score 58)" (UX-01):** `classifyRadarTf` filterte hart ab 75; das Fresh-Gate blockierte Signale unter 75 trotz aktivem Profil.
5. **UX-Misreads (UX-02 bis UX-04 & Farbcode):** DSR-Signifikanz vs. Sharpe Ratio unklar, Kelly-Edge als Trade-Gewinn missverstehbar, DSR < 0.5 rot markiert trotz vom Bot akzeptierter Trades.
6. **Tutorial-Hygiene & Disclaimer (VER-01, DOC-01, DISC-01):** Versionssprung v2.2.0, Tippfehler 1.0.0R, fehlende Research-Only-Disclaimer.
7. **Mutationslücken (F-MUT-01, F-MUT-02):** Ungetesteter DSR-Default N=18 und ungetestete negative Score-Clamp-Grenze.

---

## 2. Implementierte Korrekturen

- **Parametrisierbares Fresh-Gate:** `classifyRadarTf` akzeptiert `longTh` und `shortTh`. Dashboard und `headless_autobot.js` übergeben `minScore` und `100 - minScore` im Fresh-Gate; der Discovery-Radar verbleibt unverändert bei 75/25.
- **Fail-Closed Nullvarianz-Guard:** `evaluateAutobotEdge` berechnet vor Edge- und DSR-Freigabe die Return-Varianz (`sampleVariance < 1e-12` -> Reject).
- **Skaleninvariantes Epsilon:** `regimeOf` nutzt `max(1e-12, |EMA200| * 1e-12)`; flache Reihen bleiben universell `SIDEWAYS`.
- **Operative DSR-Ampel:** `renderBacktest` synchronisiert Anzeige und Farbcodierung mit dem tatsächlich aktiven Profil (Standard: Setup-DSR gegen 0.10/0.05/0.30; Strikt: Uni-DSR gegen 0.50).
- **Begriffsklarheit:** Score als 0–100-Index deklariert, Kelly-Edge als Erwartungswert über die Stichprobe, Tutorial mit Research-Only-Banner in Header und Footer.
- **Test-Absicherung:** Neue Verhaltens-Suites `tests/test_r38_quant_guards.js`, `tests/test_r38_dsr_display.js`, `tests/test_dsr_default_trials.js` und `tests/test_score_clamp_negative.js` decken Mutationen ab.

---

## 3. Verifikations- und Release-Evidenz

- **Pytest:** 504 passed, 69 subtests passed (Exit 0)
- **Discovered JS Suites:** 97/97 Suites PASS (Exit 0)
- **Release-Check:** 120 Checks PASS, Exit 0, Verdict: `SOFTWARE_GO / MODEL_NO_EVIDENCE`
- **Ledger-Integrität:** EXP-032 unverändert, Chain-Head `ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b`
- **DOM-Sicherheit:** `innerHTML`-Kanon 63 unverändert (Delta 0)
- **GitHub Release & Asset:** Tag `v2.4.0` gepusht, GitHub Release publiziert, Asset `symbiose.zip` verifiziert (SHA-256: `67b6ca32d9ca792dfb033106072825d6438e5edca6869c4d923ab9bf497ad25d`)
- **Deploy Webhook:** Delivery `0151d200-b177-11f1-8cd7-633d4c50e357` synchron mit HTTP 202 (`{"ok": true, "update": "started", "tag": "v2.4.0"}`) quittiert.
