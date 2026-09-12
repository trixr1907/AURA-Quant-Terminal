# Research Integrity & Model Risk Management — Glossar für das AURA Quant Terminal

> Zweck: einheitliche, präzise Begriffe für Herleitung, Implementierung, Darstellung
> und statistische Validierung der Quant-Pipeline. Für Doku, Briefings an Agents
> (Hermes/OpenHands) und unabhängige Reviewer.
>
> Kernunterscheidung vorab:
> **MRM garantiert keine Gewinne.** Es garantiert nur, dass die Pipeline einen echten
> Edge korrekt misst — und einen fehlenden Edge ehrlich als solchen ausweist.

---

## 1. Die vier Ebenen (immer in dieser Reihenfolge prüfen)

| # | Ebene | Leitfrage | AURA-Beispiel |
|---|---|---|---|
| 1 | **Herleitung (Derivation)** | Folgt die Formel *beweisbar* aus Annahmen? | Purge/Embargo nach López de Prado, DSR-Formel nach Bailey/LdP |
| 2 | **Implementierung (Correctness)** | Rechnet der Code exakt das? | JS-Engine ↔ `reference_backtest.py` (Oracle) ↔ Pine Golden Master |
| 3 | **Darstellung (Provenance)** | Zeigt das UI genau die berechneten Werte? | Kein Zahlendreher, kein Hardcode im Dashboard (Demo-Fehler war genau das) |
| 4 | **Statistische Validität** | Ist der Edge echt — oder Overfitting/Leak? | Walk-Forward, Purge, DSR-Trial-Accounting, Evidence-Gates |

Ein Fehler auf **einer** Ebene macht alles Darüberliegende ungültig.
Umgekehrt gilt: Ebene 1–3 können perfekt sein, und Ebene 4 sagt trotzdem ehrlich
„kein Edge" (NO_EVIDENCE). Das ist kein Fehler, das ist der Zweck.

---

## 2. Begriffstabelle

| Umgangssprachlich | Präziser Begriff | Bedeutung | Gegenbegriff / Fehler |
|---|---|---|---|
| „richtig hergeleitet" | Finanzmathematik / Statistische Inferenz | Formel folgt logisch aus Annahmen | „Hat sich bewährt" (Empirie statt Beweis) |
| „richtig gerechnet" | Correctness / Implementierungs-Treue | Code = Mathematik, exakt | Rundungs-/Indexfehler, Off-by-one |
| „zwei Rechnungen müssen gleich sein" | **Oracle-Parität** | unabhängige Referenzimplementierung liefert identische Werte | ein Wert „auswendig" in den zweiten Pfad geschrieben |
| „Anzeige stimmt" | **Data Lineage / Provenance / Single Source of Truth** | jede UI-Zahl rückverfolgbar auf die eine Engine | Hardcode, Duplikat-Logik, manuell gepflegte Kopie |
| „Tipp ist echt" | **Statistische Validität / Out-of-Sample-Generalisation** | Signal gilt auf Daten, die es nie gesehen hat | In-Sample-Optimismus, Look-ahead |
| „zu viel getestet" | **Backtest-Overfitting** (BkOverfit) | zu viele Versuche → irgendetwas „funktioniert" immer | p-Hacking, unkorrigierte Multiplicity |
| „wie viel Overfitting war drin?" | **Deflated Sharpe Ratio (DSR)** | Sharpe nach Korrektur um effektive Trial-Zahl | roher Sharpe (unkorrigiert) |
| „Tests dürfen nichts verraten" | **Leakage-Resistenz / Metamorphic Testing** | Ergebnis unverändert bei erlaubter Datenvertauschung | Look-ahead, Purge-Lücke |
| „Signal erst nach Kerzenschluss" | **Kausalität / point-in-time** | Feature kennt nur Vergangenheit + aktuelle Bar | Future-Peeking (Close-zu-Close-Bug) |
| „Trade-Label sauber trennen" | **Purged Cross-Validation / Embargo** | Train/Test durch Label-Horizont getrennt | Überlappung = Selbstkorrelation = Schein-Edge |
| „darf der Bot traden?" | **Evidence-Gating / fail-closed** | ohne ausreichende statistische Evidenz: kein Trade | Punktschätzer-Gate (nur exp>0) |
| „Master der Strategie" | **Golden Master** | Pine-Datei als Referenzwahrheit der Logik | divergente Implementierungen |
| „unabhängige Kontrollrechnung" | **Test-Oracle** | `reference_backtest.py` als zweite Implementierung | self-fulfilling tests (Test kopiert Code) |

---

## 3. Die Disziplinen im Überblick

### 3.1 Model Risk Management (MRM)
Institutioneller Überbegriff (Banken, reguliert in den USA als **SR 11-7**).
Umfasst: Dokumentation der Annahmen, unabhängige Validierung, Limits,
Monitoring — exakt die vier Ebenen aus Abschnitt 1.

### 3.2 Research Integrity / Methodische Validierung
Der akademisch-neutralere Begriff für dasselbe in einer Research-Pipeline.
Kernfrage: „Ist diese Schlussfolgerung aus diesen Daten methodisch zulässig?"

### 3.3 Quantitäts-Accounting („Quant-Audit")
Die Disziplin, die bei AURA gelaufen ist: jede Zahl auf Herkunft und
Korrektheit prüfen (Wer hat gerechnet? Mit welchen Parametern? Auf welchen Daten?).

### 3.4 Edge-Forschung / Alpha Research
**Getrennt von 3.1–3.3.** Hier geht es darum, eine Strategie zu *finden/verbessern*,
nicht um die Korrektheit der Messung. AURA hat beides — sie dürfen nicht vermischt
werden: ein Mess-Fix ist kein Strategie-Fix.

---

## 4. AURA-Komponenten → Disziplin (Zuordnung)

| Datei / Mechanismus | Rolle im Rahmen |
|---|---|
| `Symbiose_Signal_System_v1.pine` | **Golden Master** — Referenzwahrheit der Strategie-Logik |
| `Symbiose_Dashboard.html` (Engine-Block) | **Produktions-Implementierung** (Ebene 2) |
| `tests/reference_backtest.py` | **Test-Oracle** — unabhängige Kontrollrechnung (Parität) |
| `tests/test_engine_full.js` | Implementierungs- + Grenzvertragstests |
| `tests/test_lookahead_metamorphic.js` | **Leakage-Resistenz** (metamorphic, kausal) |
| `tests/sensitivity_release_gates.js` | **Release-Gates** — berechnet, nie von Hand behauptet |
| `runWalkForwardBacktest` + Purge/t1 | **Purged Walk-Forward** — Out-of-Sample-Validierung |
| `calcDSR` + `totalTrials` | **Overfitting-Korrektur** (DSR) |
| `evidenceStatus` (NO_EVIDENCE/PAPER_CANDIDATE) | **Evidence-Gating** (fail-closed) |
| Golden-Fixtures + `provenance.json` | **Data Lineage** — nachvollziehbare Datenherkunft |

---

## 5. Formulierungshilfen für Briefings

**Kurzfassung (1 Satz):**
> „Wir betreiben Research Integrity über vier Ebenen — Herleitung, Implementierung,
> Darstellung, statistische Validierung — mit Oracle-Parität (JS↔Python↔Pine),
> Evidence-Gating und DSR-Trial-Accounting."

**Für Hermes / Agents (Auftragssprache):**
> „Fix ist nur erlaubt, wenn er Ebene 1–4 konsistent lässt: Herleitung dokumentiert,
> Engine- und Oracle-Ergebnis paritätsgleich, UI-Wert = Engine-Wert (Lineage),
> und die statistische Aussage (DSR, evidenceStatus) aus den *effektiven* Trials."

**Für Reviewer (Prüfauftrag):**
> „Prüfe die vier Ebenen einzeln und berichte separat: (1) Derivation, (2) Correctness,
> (3) Provenance, (4) statistische Validität. Ein Fehler auf einer Ebene invalidiert
> die Aussagen aller darüberliegenden Ebenen."

**Für die Doku (Abschlussbericht):**
> „Die Vorher/Nachher-Werte dokumentieren geänderte Messlogik, keine Performance.
> Research Integrity ist erfüllt, wenn die Messung ehrlich ist — nicht wenn sie
> besser aussieht."

---

## 6. Die drei Sätze, die das ganze Projekt zusammenfassen

1. **Wahrheit der Rechnung** (Ebene 1–3): Die Zahlen müssen stimmen — hergeleitet,
   korrekt implementiert, rückverfolgbar dargestellt.
2. **Wahrheit der Aussage** (Ebene 4): Die Zahl muss bedeuten, was sie behauptet —
   kein Leak, kein Overfitting, ehrliche Trials.
3. **Erfolg ist keine Messfrage:** MRM sagt dir, *ob* ein Edge existiert — nie, *dass*
   einer existiert. Erfolgreiche Trades sind das Produkt der Edge-Forschung, nicht
   des Messrahmens.
