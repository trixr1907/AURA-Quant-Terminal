# AURA Trials & Experiment Ledger

Dieses Dokument dient als unveränderliches, kumulatives Prüfprotokoll aller Hypothesen-, Hyperparameter-, Schwellenwert- und Modelländerungen des AURA Quant Terminals. Es verhindert schleichendes p-Hacking (Researcher Degrees of Freedom) über Release- und Versionsgrenzen hinweg.

---

## 1. Out-of-Sample (OOS) Lockbox Cut

Zur Verhinderung von Kontamination und Lookahead-Optimierung gilt für alle Modell- und Strategie-Entwicklungen ein verbindlicher Lockbox-Cut:

- **Lockbox Cutoff-Zeitpunkt:** `2026-09-10T00:00:00Z`
- **Gesperrte OOS-Spanne:** 60 Tage (bzw. alle nachfolgenden Kerzen bis zum finalen Release-Gate)
- **Regel:** Kein Entwicklungs-, Grid- oder Schwellenwert-Lauf darf Daten nach dem Cutoff-Zeitpunkt zur Optimierung verwenden. Die Lockbox-Daten werden exakt **einmal** am Ende des Release-Zyklus blind ausgewertet.
- **Verankerung:** Maschinenlesbar deklariert in `tests/fixtures/golden/provenance.json` (`"lockbox"`).

---

## 2. Kumulatives Experiment-Register

Jede Änderung an Indikator-Schwellen, Parametern, Walk-Forward-Architektur oder Filtern wird als eigenständiges Experiment geführt.

| ID | Version | Datum | Datei : Zeile | Typ | Beschreibung & Begründung |
|---|---|---|---|---|---|
| **EXP-001** | v1.0.8 | 2026-09-08 | `Symbiose_Dashboard.html:1769` | Walk-Forward | **t1-sicherer Purge:** `trainEnd = testStart - 2`, `trainExitBoundary = testStart - 1`. Trades mit `exitBar >= testStart` werden strikt aus dem Training entfernt. |
| **EXP-002** | v1.0.8 | 2026-09-08 | `Symbiose_Dashboard.html:1769` | Walk-Forward | **Embargo-Entfernung:** Unnötige ATR-Embargo-Heuristik entfernt, da t1-Purge Überschneidungen mathematisch exakt ausschließt. |
| **EXP-003** | v1.0.8 | 2026-09-08 | `Symbiose_Dashboard.html:1731` | Validierung | **minTrainBars = 300:** Verhindert statistisch unterbestimmte OOS-Folds (früheres 126-Bar-Problem behoben). |
| **EXP-004** | v1.0.8 | 2026-09-08 | `Symbiose_Dashboard.html:1813` | Statistik / DSR | **DSR Trial Accounting:** Walk-Forward DSR bilanziert `totalTrials = paramGrid.length * trialMultiplier` (Grid = 18). |
| **EXP-005** | v1.0.8 | 2026-09-08 | `Symbiose_Dashboard.html:6089` | Optimierung | **TimeStop-Cap Harmonisierung:** `maxBars = 30` einheitlich für alle Timeframe-Sweeps. |
| **EXP-006** | v1.0.8 | 2026-09-08 | `Symbiose_Dashboard.html:6731` | Execution Gate | **Autobot Entry Gate:** Fail-closed Validierung auf `total >= 15`, `edge > 0`, `DSR >= 0.5`. |
| **EXP-007** | v1.0.9 | 2026-09-09 | `—` | Hygiene | *(Keine Modelländerung — reine Dokumentations- & Provenienz-Validierung, 0 Experimente)* |
| **EXP-008** | v1.1.0 | 2026-09-10 | `Symbiose_Dashboard.html:7139` | Multi-Testing | **Universe-Adjustierter DSR:** Autobot übermittelt `trialMultiplier = wfEvaluated` (gesamte Scan-Hypothesen-Familie `Symbole × 4 TFs`), um Survivor-Bias über das gescannte Universum zu eliminieren. |
| **EXP-009** | v1.1.0 | 2026-09-10 | `Symbiose_Dashboard.html:6731` | Execution Gate | **Option B Dual-DSR & strictUniverseGate:** Anzeige von Setup-DSR und Universums-DSR im UI; Schalter `strictUniverseGate` (Default: false) für optionales striktes Universe-Gate. |
| **EXP-010** | v1.1.0 | 2026-09-10 | `bitget_relay.py:240` | Infrastruktur | *(Keine Modelländerung — Relay In-Memory TTL-Cache & Token-Bucket Rate Limiter, 0 Experimente)* |
| **EXP-011** | v1.1.0 | 2026-09-10 | `Symbiose_Dashboard.html:3620` | UI-Performance | *(Keine Modelländerung — RenderCache Dirty-Flag Panel Rendering, 0 Experimente)* |
| **EXP-012** | v1.1.0 | 2026-09-10 | `scripts/lockbox_guard.py:1` | Holdout-Quarantäne | *(Keine Modelländerung — Lockbox OOS-Evaluationsmechanik & Quarantäne-Guard, 0 Experimente)* |
| **EXP-013** | v1.1.1 | 2026-09-10 | `scripts/release_check.py:150` | CI / Release-Gate | *(Keine Modelländerung — B1: Wiederherstellung fail-closed Release-Gate & Software-GO Packaging, 0 Experimente)* |
| **EXP-014** | v1.1.1 | 2026-09-10 | `tests/model_evidence_real.js:45` | Mess-Integrität | *(Keine Modelländerung — B2: Millisekunden-Zeitstempel-Normalisierung im Model Evidence Gate, 0 Experimente)* |
| **EXP-015** | v1.1.1 | 2026-09-10 | `docs/architecture.md:50` | Dokumentation | *(Keine Modelländerung — B3: Dokumentation der Zeitstempel-Konvention & Provenienz-Update, 0 Experimente)* |

---

## 3. Bilanzierte Kennzahlen

- **Kumulative Modell-Experimente (Gesamt):** 8 (EXP-001 bis EXP-006, EXP-008, EXP-009)
- **Infrastruktur/Hygiene/Mess-Releases:** 7 (EXP-007, EXP-010, EXP-011, EXP-012, EXP-013, EXP-014, EXP-015)
- **Modell-Trials im Autobot-Scan (Default Universe 120 Symbole × 4 TFs):**
  - Universums-Hypothesen: `480`
  - Internes Parameter-Grid: `18`
  - Effektive Hypothesen-Familie ($T_{\text{eff}}$): $18 \times 480 = \mathbf{8.640}$
- **Formel:**
  $$T_{\text{eff}} = 18 \times \text{UniverseHypothesen}$$

---

## 4. Konvention für künftige Änderungen

1. Jede Änderung an `paramGrid`, Indikator-Gewichten, `minScore`, `minSamples`, DSR-Schwellen oder Time-Stop-Bereichen erfordert einen neuen Eintrag in Tabelle 2.
2. Der Eintrag muss vor dem Merge vorgenommen werden und den Commit mit Begründung referenzieren.
3. Tests müssen belegen, dass veränderte Parameter keine unausgewiesenen Trials einführen.
