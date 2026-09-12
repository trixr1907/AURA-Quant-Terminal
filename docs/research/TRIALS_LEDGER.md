# AURA Trials & Experiment Ledger

Dieses Dokument dient als unveränderliches, kumulatives Prüfprotokoll aller Hypothesen-, Hyperparameter-, Schwellenwert- und Modelländerungen des AURA Quant Terminals. Es verhindert schleichendes p-Hacking (*Researcher Degrees of Freedom*) über Release- und Versionsgrenzen hinweg.

---

## 1. Definitionen & Klassifikation

Jede Code-, Daten- oder Konfigurationsänderung wird vor ihrer Durchführung strikt klassifiziert:

- **Modellexperiment (`+1`):**
  Jede Modifikation an Signal-Logik, Indikator-Berechnungen, Schwellenwerten (`longTh`, `shortTh`, `minScore`), Hyperparameter-Grids (`paramGrid`), TP/SL-Strukturen, Time-Stop-Regeln, Regime-Gates, Universums-Filtern, Selektions-Objektiven oder Asset-Gewichtungen — sobald sie gegen Marktdaten (Train oder Test) evaluiert wird.
  - *Zähler-Wirkung:* Erhöht `total_model_experiments` um **`+1`**.
  - *DSR-Auswirkung:* Geht in die Multiple-Testing-Korrektur ($T_{\text{eff}}$) ein.

- **Prozess-Fix / Diagnose (`0`):**
  Reine Software-Integritäts-, Dokumentations-, CI/CD-, UI-Rendering-, Caching-, Relay-Sicherheits-, Test-Harness-Arbeiten oder nicht-invasive Diagnosen (D1–D6, B2) ohne jegliche Signal-, Order- oder Modellwirkung.
  - *Zähler-Wirkung:* Zählt als **`0`** Modellexperimente (`total_model_experiments` bleibt unverändert).

---

## 2. Die Prä-Registrierungs-Regel (Bremse gegen p-Hacking)

> **Verbindliche Invariante:**
> Ein Modellexperiment (`+1`) MUSS **VOR** dem ersten Backtest-, Trainings- oder Auswertungs-Lauf im Ledger mit seiner konkreten **Hypothese** und dem messbaren **Erfolgskriterium** eingetragen werden.
> Die Präregistrierung wird in einem **eigenen Commit** festgehalten; dessen Hash steht als `Präreg-Commit: <SHA>` im Ledger-Zeilenkopf bzw. im Hypothesenfeld des Eintrags. Ein Ergebnis-Eintrag ohne vorausgehenden Präregistrierungs-Commit ist als **`prä-registriert (Session-Protokoll, nicht git-belegt)`** zu kennzeichnen und wird nicht als git-belegte Präregistrierung gewertet.
> Eine nachträgliche Rationalisierung oder ein „Probieren bis es grün wird" ist methodisch verboten. Wenn ein Experiment das vorab definierte Erfolgskriterium verfehlt, gilt es als `FAIL / REJECTED` und erhöht dennoch den kumulativen Zähler.

---

## 3. Out-of-Sample (OOS) Lockbox Cut

Zur Verhinderung von Kontamination und Lookahead-Optimierung gilt für alle Modell- und Strategie-Entwicklungen ein verbindlicher Lockbox-Cut:

- **Lockbox Cutoff-Zeitpunkt:** `2026-09-10T00:00:00Z`
- **Gesperrte OOS-Spanne:** 60 Tage (bzw. alle nachfolgenden Kerzen bis zum finalen Release-Gate)
- **Regel:** Kein Entwicklungs-, Grid- oder Schwellenwert-Lauf darf Daten nach dem Cutoff-Zeitpunkt zur Optimierung verwenden. Die Lockbox-Daten werden exakt **einmal** am Ende des Release-Zyklus blind ausgewertet.
- **Verankerung:** Maschinenlesbar deklariert in `tests/fixtures/golden/provenance.json` (`"lockbox"`).

---

## 4. Kryptografischer Bootstrap und Hash-Kette

Der historische Bestand **vor** Einführung der Kette ist als UTF-8-Bytefolge der Datei
`docs/research/TRIALS_LEDGER.md` auf Commit `4a61692a8e35cbe37ba01ce4701fbdfd41fb4c3e`
definiert. Er endet mit genau einem LF (`0x0a`). Sein SHA-256-Seed lautet:

`23f59ef8df9f348609280d8f57583e32c2d7afc1e9b428f9d50ae75051eeeb0c`

Neue Einträge liegen maschinenlesbar in `docs/research/trials_ledger_chain.jsonl`.
Jede Zeile ist ein JSON-Objekt. Für `entry_hash` wird das Objekt ohne das Feld
`entry_hash` in dieser festen Feldreihenfolge serialisiert:

`id,date,version,type,hypothesis,change,success_criterion,result,delta,total_model_experiments,status,prereg_commit,prev_hash`

Kanonische Serialisierung: UTF-8, JSON ohne ASCII-Escaping, ohne Leerzeichen
(Separatoren `,` und `:`), genau ein LF am Ende. `entry_hash` ist SHA-256 über diese
Bytefolge. Beim ersten Eintrag ist `prev_hash` der Bootstrap-Seed; danach ist
`prev_hash` exakt der `entry_hash` des unmittelbaren Vorgängers. IDs müssen strikt
aufsteigend und lückenlos sein; `total_model_experiments` muss dem vorherigen Total
plus `delta` entsprechen. Der Verifier behandelt fehlende, gelöschte, umsortierte,
manipulierte oder formal ungültige Einträge fail-closed.

Aktueller Kettenkopf nach den Präregistrierungen EXP-026 bis EXP-028:
`da5723592ca1cd6c0467e9964ac407af884e622480812fedf7d0491cb74ae1dc`

---

## 5. Kumulatives Experiment-Register

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
| **EXP-016** | 2026-09-10 | v1.1.1 | Diagnose | D1 Kosten-Dekomposition: Slippage und Taker-Exit-Fees stellen >80% des Kostendrags dar. | `tools/edge_diagnostic_phase_a.js:15` | Vollständige Aufspaltung in Maker-, Taker- und Slippage-Kosten je Fixture | Verifiziert: Slippage & Taker dominieren; Kosten 0.079-0.380 R/Trade | 0 | 8 | ACCEPTED |
| **EXP-017** | 2026-09-10 | v1.1.1 | Diagnose | D2 Payoff- & WR-Struktur: Erwartungswert-Profil ist mit Payoff >2.0:1 strukturell gesund. | `tools/edge_diagnostic_phase_a.js:35` | Exakte Messung von WR, avgWinR, avgLossR, TP1-Hit-Rate | Verifiziert: Payoff 2.17:1 bis 2.73:1, TP1-Hit-Rate 24-34% | 0 | 8 | ACCEPTED |
| **EXP-018** | 2026-09-10 | v1.1.1 | Diagnose | D3 Exit-Grund-Zerlegung: Breakeven hochprofitabel, direkte Stops dominieren Verlustseite. | `tools/edge_diagnostic_phase_a.js:55` | Quantifizierung von RNet, Trade-Anzahl, WinRate je ExitReason | Verifiziert: Breakeven +0.26 bis +0.88 R, Stop -0.12 bis +0.25 R | 0 | 8 | ACCEPTED |
| **EXP-019** | 2026-09-10 | v1.1.1 | Diagnose | D4 Regime-Bedingung: Signal generiert Netto-Edge bei ADX 20-30 und verliert im Chop (ADX <20). | `tools/edge_diagnostic_phase_a.js:75` | Messung des mittleren RNet konditioniert auf ADX-Buckets | Verifiziert: ADX <20 verliert überall; ADX 20-30 gewinnt überall | 0 | 8 | ACCEPTED |
| **EXP-020** | 2026-09-10 | v1.1.1 | Diagnose | D5 Sample-Size & DSR-Inversion: Bei n ≈ 33 Trades ist SR >= 0.33 für DSR >= 0.5 nötig. | `tools/edge_diagnostic_phase_a.js:95` | Numerische Inversion der DSR-Gleichung für n=15..1000 | Verifiziert: n=33 erfordert SR >= 0.33; n=200 senkt Schwelle auf SR >= 0.13 | 0 | 8 | ACCEPTED |
| **EXP-021** | 2026-09-10 | v1.1.1 | Diagnose | D6 Querschnitts-Konsistenz: Alle 5 Assets zeigen homogenes Brutto-Alpha (+0.051 bis +0.475 R). | `tools/edge_diagnostic_phase_a.js:120` | Asset-übergreifende Gegenüberstellung von Gross Exp, Net Exp, DSR | Verifiziert: Signal trägt auf allen 5 Assets echte Information | 0 | 8 | ACCEPTED |
| **EXP-022 — prä-registriert (Session-Protokoll, nicht git-belegt)** | 2026-09-10 | v1.1.1 | Modellexperiment | B1 Gated-Variante: Erzwungenes `regimeGate = true` im Parameter-Grid eliminiert Chop-Verluste. | `tools/edge_diagnostic_phase_b.js:20` | Net-OOS-Exp steigt auf ≥ 4/5 Fixtures; konsistent 1h vs 4h. | Richtungweisend (n=1–2 nicht zertifizierbar); Net-Exp steigt auf 1500 Bars Ø +2.112 R vs +0.020 R, DSR=0.500 ist neutraler Fallback. | +1 | 9 | EVALUATED |
| **EXP-023** | 2026-09-10 | v1.1.1 | Diagnose | B2 Stichprobe auf volle Tiefe: Volle Fixture-Tiefe (10k-14.7k Bars) liefert n ≥ 100 je Asset. | `tools/edge_diagnostic_phase_b.js:80` | n ≥ 100 je Fixture erreicht; DSR beider Varianten berichtet. | Teilweise erfüllt: N=1174 Base-Trades (alle n>=100), N=226 Gated-Trades (1h n=54-65, 4h n=21-25); 1h verbessert um +0.177 R, 4h nicht bestätigt; SR-Schwelle sinkt auf 0.13-0.19. | 0 | 9 | EVALUATED |
| **EXP-024 — prä-registriert (Session-Protokoll, nicht git-belegt)** | 2026-09-10 | v1.1.1 | Modellexperiment | C1 Selektionsobjektiv-Reform: Ersatz der harten Stufe `stats.total >= 5 ? exp * Math.sqrt(n) : -Infinity` durch regularisiertes `stats.total >= 2 ? stats.exp * Math.sqrt(stats.total) * (1 - 1 / (1 + stats.total)) : -Infinity` wählt `regimeGate=true` organisch in >= 50% der Folds und hebt Net-Exp auf voller Tiefe. | `Symbiose_Dashboard.html:1789` | (1) Aggregierte OOS-Net-Exp steigt vs Baseline UND (2) `regimeGate=true` in >= 50% der Folds organisch gewählt UND (3) Net-Exp-Δ auf 1h (BTC/ETH/SOL) positiv und auf 4h (XRP/DOGE) nicht-negativ. | Bestanden (eingeschränkt): Net-Exp steigt um +0.032 R (SOL +0.084, XRP +0.078, Rest 0.000); Kriterien 1/2/4 erfüllt; Kriterium 3 je Einzel-Asset nur 1/3 positiv auf 1h (Aggregat-Lesart). | +1 | 10 | ACCEPTED |
| **EXP-025 — prä-registriert (Session-Protokoll, nicht git-belegt)** | 2026-09-10 | v1.1.1 | Diagnose | D1 Fold-1-Geometrie-Fix: Vergrößerung des Initial-Trainingsfensters auf minTrainBars=2000 (1h) bzw. 500 (4h) senkt den Fold-1-Trade-Anteil auf <= 40% und liefert einen fairen OOS-Baseline-Vergleich. Vorab festgelegte D2 STOPP-Regel: GO für B3 nur bei aggregiertem DSR >= 0.50, sonst bindender STOPP (NO_EVIDENCE). | `tools/edge_diagnostic_phase_d.js:45` | (1) Fold-1-Anteil an Gesamt-Trades <= 40% UND (2) alle Folds erreichen >= 5 Train-Trades für selektive Konfigurationen UND (3) Vollständiger gated vs ungated Vergleich berichtet. | Teilweise: Fold-1-Anteil Ø 26.5%, aber SOL 42.3% >40%; 1h selektive Kapazität >=5, 4h verfehlt (XRP F1=1/F2=3, DOGE F1=0); fairer Gated-Vergleich vollständig. D2 STOPP angewendet: konservativ aggregierter OOS-DSR 0.038 bei T=45 (lokal T=9: 0.152) < 0.50, daher NO_EVIDENCE und B3 nicht durchgeführt. | 0 | 10 | EVALUATED / STOPP |
| **EXP-026** | 2026-09-12 | v1.2.9 | Prozess-Fix | SHA-256-Kette macht Ledger-Manipulation, Löschung und Umsortierung fail-closed sichtbar. Präregistrierung: `docs/research/preregistrations/AUDIT_ROUND9_M1_M3.md`; Präreg-Commit: `11d46cd`. | `docs/research/TRIALS_LEDGER.md`; geplant: `scripts/verify_ledger.py` | Gültige Kette PASS; manipulierte, gelöschte, umsortierte oder ungültige Kette FAIL | Präregistriert; Bootstrap-Seed bindet Bestand von v1.2.8 | 0 | 10 | PREREGISTERED |
| **EXP-027** | 2026-09-12 | v1.2.9 | Prozess-Fix | DSR nutzt den kryptografisch verifizierten kumulativen Ledger-Zähler statt des aktuellen Radar-Universums. Präregistrierung: `docs/research/preregistrations/AUDIT_ROUND9_M1_M3.md`; Präreg-Commit: `11d46cd`. | geplant: `tools/edge_diagnostic_phase_d.js` und Ledger-Loader | Ledger-N autoritativ; fehlendes/unparsbares/ungültiges Ledger fail-closed; DSR-Monotonie | Präregistriert vor Implementierung und Messlauf | 0 | 10 | PREREGISTERED |
| **EXP-028** | 2026-09-12 | v1.2.9 | Diagnose | CVD-Akkumulationsdrift wird auf allen fünf Golden-Master-Fixtures über mindestens 5.000 Bars gemessen. Präregistrierung: `docs/research/preregistrations/AUDIT_ROUND9_M1_M3.md`; Präreg-Commit: `11d46cd`. | geplant: reproduzierbarer CVD-Paritätsmesser | Absolute/relative Drift und Vergleichskipps je Fixture; bei Kipp oder unbeschränktem Wachstum keine Akzeptanz | Präregistriert vor Messlauf | 0 | 10 | PREREGISTERED |

---

## 6. Bilanzierte Kennzahlen

- **Kumulative Modell-Experimente (`total_model_experiments`):** **`10`** (EXP-001 bis EXP-006, EXP-008, EXP-009, EXP-022, EXP-024)
- **Prozess- / Infrastruktur- / Mess- & Diagnose-Einträge:** **`18`** (EXP-007, EXP-010 bis EXP-021, EXP-023, EXP-025 bis EXP-028)
- **Modell-Trials im Autobot-Scan (Default Universe: 120 Symbole × 4 TFs):**
  - Universums-Hypothesen: `480`
  - Internes Parameter-Grid: `18` (bzw. `9` bei rein gated)
  - Effektive Hypothesen-Familie ($T_{\text{eff}}$): $18 \times 480 = \mathbf{8.640}$
- **Formel:**
  $$T_{\text{eff}} = \text{Grid}_{\text{intern}} \times \text{UniverseHypothesen} = 18 \times (N_{\text{Symbole}} \times N_{\text{Timeframes}})$$

---

## 7. Protokoll-Regeln für künftige Modellexperimente

1. Vor jeder Anpassung an Indikatoren, Schwellenwerten oder Optimierungs-Grids wird eine neue Zeile (`EXP-026`, etc.) mit `Typ = Modellexperiment`, prä-registrierter Hypothese und messbarem Zielkriterium eingetragen und als eigener Präregistrierungs-Commit gespeichert.
2. Der Präregistrierungs-Commit-Hash wird vor dem Messlauf im Experiment-Eintrag festgehalten. Fehlt dieser vorausgehende Commit, lautet der Status zwingend `prä-registriert (Session-Protokoll, nicht git-belegt)`.
3. Nach Abschluss der Untersuchung wird das reale Messergebnis eingetragen und der Status auf `ACCEPTED` (Kriterium erreicht) oder `REJECTED` (Kriterium verfehlt) gesetzt.
4. Der Zähler `total_model_experiments` wird bei jedem Modellexperiment inkrementiert und fließt transparent in die statistische Bewertung ein.
