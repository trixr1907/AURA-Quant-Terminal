# AURA Trials & Experiment Ledger

Dieses Dokument dient als unveränderliches, kumulatives Prüfprotokoll aller Hypothesen-, Hyperparameter-, Schwellenwert- und Modelländerungen des AURA Quant Terminals. Es verhindert schleichendes p-Hacking (*Researcher Degrees of Freedom*) über Release- und Versionsgrenzen hinweg.

---

## 1. Definitionen & Klassifikation

Jede Code-, Daten- oder Konfigurationsänderung wird vor ihrer Durchführung strikt klassifiziert:

- **Modellexperiment (`+1`):**
  Jede Modifikation an Signal-Logik, Indikator-Berechnungen, Schwellenwerten (`longTh`, `shortTh`, `minScore`), Hyperparameter-Grids (`paramGrid`), TP/SL-Strukturen, Time-Stop-Regeln, Regime-Gates, Universums-Filtern oder Asset-Gewichtungen — sobald sie gegen Marktdaten (Train oder Test) evaluiert wird.
  - *Zähler-Wirkung:* Erhöht `total_model_experiments` um **`+1`**.
  - *DSR-Auswirkung:* Geht in die Multiple-Testing-Korrektur ($T_{\text{eff}}$) ein.

- **Prozess-Fix (`0`):**
  Reine Software-Integritäts-, Dokumentations-, CI/CD-, UI-Rendering-, Caching-, Relay-Sicherheits- oder Test-Harness-Arbeiten ohne jegliche Signal-, Order- oder Modellwirkung (z. B. Zeitstempel-Normalisierung von Sekunden auf Millisekunden im Harness, Behebung von Race Conditions, Layout-Fixes).
  - *Zähler-Wirkung:* Zählt als **`0`** Modellexperimente (`total_model_experiments` bleibt unverändert).

---

## 2. Die Prä-Registrierungs-Regel (Bremse gegen p-Hacking)

> **Verbindliche Invariante:**
> Ein Modellexperiment (`+1`) MUSS **VOR** dem ersten Backtest-, Trainings- oder Auswertungs-Lauf im Ledger mit seiner konkreten **Hypothese** und dem messbaren **Erfolgskriterium** eingetragen werden.
> Eine nachträgliche Rationalisierung oder ein „Probieren bis es grün wird" ist methodisch verboten. Wenn ein Experiment das vorab definierte Erfolgskriterium verfehlt, gilt es als `FAIL / REJECTED` und erhöht dennoch den kumulativen Zähler.

---

## 3. Out-of-Sample (OOS) Lockbox Cut

Zur Verhinderung von Kontamination und Lookahead-Optimierung gilt für alle Modell- und Strategie-Entwicklungen ein verbindlicher Lockbox-Cut:

- **Lockbox Cutoff-Zeitpunkt:** `2026-09-10T00:00:00Z`
- **Gesperrte OOS-Spanne:** 60 Tage (bzw. alle nachfolgenden Kerzen bis zum finalen Release-Gate)
- **Regel:** Kein Entwicklungs-, Grid- oder Schwellenwert-Lauf darf Daten nach dem Cutoff-Zeitpunkt zur Optimierung verwenden. Die Lockbox-Daten werden exakt **einmal** am Ende des Release-Zyklus blind ausgewertet.
- **Verankerung:** Maschinenlesbar deklariert in `tests/fixtures/golden/provenance.json` (`"lockbox"`).

---

## 4. Kumulatives Experiment-Register

Schema: `ID | Datum | Version | Typ | Hypothese (prä-registriert) | Änderung (Datei:Zeile) | Erfolgskriterium (vorab) | Ergebnis | Δ (+1/0) | Total Exp. | Status`

| ID | Datum | Version | Typ | Hypothese (prä-registriert) | Änderung (Datei:Zeile) | Erfolgskriterium (vorab) | Ergebnis | Δ | Total Exp. | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **EXP-001** | 2026-09-08 | v1.0.8 | Modellexperiment | t1-sicherer Purge eliminiert Forward-Lookahead über Testfold-Grenzen. | `Symbiose_Dashboard.html:1769` | Null überlappende OOS-Trades an Fold-Grenzen | Metamorphisch & deterministisch verifiziert | +1 | 1 | ACCEPTED |
| **EXP-002** | 2026-09-08 | v1.0.8 | Modellexperiment | Entfernung des ATR-Embargos vereinfacht Geometrie ohne Leakage, da t1-Purge hinreichend schützt. | `Symbiose_Dashboard.html:1769` | Identische OOS-Trade-Isolation bei kürzerer Totzeit | Keine Informationslecks nachgewiesen | +1 | 2 | ACCEPTED |
| **EXP-003** | 2026-09-08 | v1.0.8 | Modellexperiment | Mindesttrainingsgröße `minTrainBars = 300` stabilisiert In-Sample-Schätzungen. | `Symbiose_Dashboard.html:1731` | Keine Folds mit unterbestimmter Varianz ($n < 300$) | Fold-Degenerierung behoben | +1 | 3 | ACCEPTED |
| **EXP-004** | 2026-09-08 | v1.0.8 | Modellexperiment | Walk-Forward DSR muss internes Parameter-Grid (18) explizit im Nenner bilanzieren. | `Symbiose_Dashboard.html:1813` | DSR berechnet $T_{\text{eff}} \ge 18$ | Korrekte DSR-Deflation implementiert | +1 | 4 | ACCEPTED |
| **EXP-005** | 2026-09-08 | v1.0.8 | Modellexperiment | Vereinheitlichung des TimeStop-Caps auf 30 Bars harmonisiert Haltedauer über Timeframes. | `Symbiose_Dashboard.html:6089` | Keine Haltedauer-Verzerrungen bei TF-Wechsel | Cap über alle TFs konsistent auf 30 limitiert | +1 | 5 | ACCEPTED |
| **EXP-006** | 2026-09-08 | v1.0.8 | Modellexperiment | Autobot Entry Gate blockiert Trades bei ungenügender OOS-Stichprobe ($N < 15$), negativem Edge oder DSR $< 0.5$. | `Symbiose_Dashboard.html:6731` | 0 autonome Orders ohne statistische OOS-Evidenz | Fail-closed Gate aktiv und verifiziert | +1 | 6 | ACCEPTED |
| **EXP-007** | 2026-09-09 | v1.0.9 | Prozess-Fix | Unabhängige Golden-Master-Provenienz und Doku sichern Reproduzierbarkeit ohne Modelländerung. | `tests/fixtures/golden/provenance.json` | 100% Provenienz-Abdeckung aller Fixtures | Provenienz-Manifest verifiziert | 0 | 6 | ACCEPTED |
| **EXP-008** | 2026-09-10 | v1.1.0 | Modellexperiment | Autobot Scan übermittelt `trialMultiplier = wfEvaluated` ($N_{\text{Sym}} \times 4$), um Survivor-Bias über das gescannte Universum zu eliminieren. | `Symbiose_Dashboard.html:7139` | Korrekte Deflation über $T_{\text{eff}} = 18 \times \text{Universe}$ | Universe-DSR ausgewiesen | +1 | 7 | ACCEPTED |
| **EXP-009** | 2026-09-10 | v1.1.0 | Modellexperiment | Option B Dual-DSR trennt lokales Setup-Gate von striktem Universe-Gate (`strictUniverseGate`). | `Symbiose_Dashboard.html:6731` | Transparente Koexistenz beider Metriken im UI | Umschaltbares Gate implementiert & getestet | +1 | 8 | ACCEPTED |
| **EXP-010** | 2026-09-10 | v1.1.0 | Prozess-Fix | In-Memory TTL-Cache und Token-Bucket im Relay schützen Public Endpoints vor Rate-Limits. | `bitget_relay.py:240` | 0 Exchange 429-Fehler unter Last | Schutz aktiv, 0 Modellwirkung | 0 | 8 | ACCEPTED |
| **EXP-011** | 2026-09-10 | v1.1.0 | Prozess-Fix | RenderCache Dirty-Flag Rendering verhindert unnötige DOM-Neubauten bei WebSocket-Ticks. | `Symbiose_Dashboard.html:3620` | Signifikante CPU-Entlastung bei Ticks | UI stabil, 0 Modellwirkung | 0 | 8 | ACCEPTED |
| **EXP-012** | 2026-09-10 | v1.1.0 | Prozess-Fix | Lockbox OOS-Quarantäne-Guard sperrt Bars $\ge \text{Cutoff}$ automatisiert. | `scripts/lockbox_guard.py:1` | Fail-closed Abbruch bei unbefugtem Holdout-Zugriff | Guard aktiv, 0 Modellwirkung | 0 | 8 | ACCEPTED |
| **EXP-013** | 2026-09-10 | v1.1.1 | Prozess-Fix | B1: Wiederherstellung des fail-closed CI-Release-Gates & Software-GO Packaging ohne Bypasses. | `scripts/release_check.py:150` | CI blockt bei Fehler (Exit 2), akzeptiert Software-GO (Exit 0) | Fail-closed Verhalten verifiziert | 0 | 8 | ACCEPTED |
| **EXP-014** | 2026-09-10 | v1.1.1 | Prozess-Fix | B2: Millisekunden-Zeitstempel-Normalisierung im Model Evidence Gate (`normalizeTimestamp`). | `tests/model_evidence_real.js:45` | Konsistente ms-Zeitbasis über alle 5 Fixtures | Tages-VWAP & Session-Bounds konsistent | 0 | 8 | ACCEPTED |
| **EXP-015** | 2026-09-10 | v1.1.1 | Prozess-Fix | B3: Dokumentation der Millisekunden-Zeitstempel-Konvention und Provenienz-Synchronisation. | `docs/architecture.md:50` | Vollständige Doku der Zeitbasis | Dokumentiert & synchronisiert | 0 | 8 | ACCEPTED |

---

## 5. Bilanzierte Kennzahlen

- **Kumulative Modell-Experimente (`total_model_experiments`):** **`8`** (EXP-001 bis EXP-006, EXP-008, EXP-009)
- **Prozess- / Infrastruktur- / Mess-Fixes:** **`7`** (EXP-007, EXP-010, EXP-011, EXP-012, EXP-013, EXP-014, EXP-015)
- **Modell-Trials im Autobot-Scan (Default Universe: 120 Symbole × 4 TFs):**
  - Universums-Hypothesen: `480`
  - Internes Parameter-Grid: `18`
  - Effektive Hypothesen-Familie ($T_{\text{eff}}$): $18 \times 480 = \mathbf{8.640}$
- **Formel:**
  $$T_{\text{eff}} = \text{Grid}_{\text{intern}} \times \text{UniverseHypothesen} = 18 \times (N_{\text{Symbole}} \times N_{\text{Timeframes}})$$

---

## 6. Protokoll-Regeln für künftige Modellexperimente

1. Vor jeder Anpassung an Indikatoren, Schwellenwerten oder Optimierungs-Grids wird eine neue Zeile (`EXP-016`, etc.) mit `Typ = Modellexperiment`, prä-registrierter Hypothese und messbarem Zielkriterium eingetragen.
2. Nach Abschluss der Untersuchung wird das reale Messergebnis eingetragen und der Status auf `ACCEPTED` (Kriterium erreicht) oder `REJECTED` (Kriterium verfehlt) gesetzt.
3. Der Zähler `total_model_experiments` wird bei jedem Modellexperiment inkrementiert und fließt transparent in die statistische Bewertung ein.
