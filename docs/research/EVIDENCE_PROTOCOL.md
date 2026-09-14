# AURA Evidenz-Protokoll & Forschungs-Governance (S1–S6)

**Stand:** 2026-09-14 / Version 1.9.0  
**Geltungsbereich:** Quantitative Forschung, Hypothesen-Präregistrierung, Evidenz-Status, Lockbox-Governance & Handelsfreigabe  

---

## 1. Das 6-Stufen-Modell (S1 bis S6)

Um Data-Mining-Artefakte, Overfitting, Look-Ahead-Bias und P-Hacking mathematisch auszuschließen, durchläuft jede Handelsidee in AURA einen strikten, sequenziellen 6-Stufen-Prozess.

```
+-----------------------------------------------------------------------------------+
| S1: Hypothesen-Formulierung (Präregistrierung, Acceptance Criteria, Params-SHA)  |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| S2: In-Sample (IS) Discovery & Parameter-Fixierung                               |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| S3: Walk-Forward Out-of-Sample (OOS) Verifikation (K>=4 Folds, DSR, Netto-R)     |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| S4: Single-Shot Lockbox Holdout Prüfung (Unberührte, gesperrte Testdaten)        |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| S5: Forward Shadow Testing (Ungefilterte Echtzeit-Entscheidungen, 24-Bar Outcome) |
+----------------------------------------+------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| S6: Produktions-Freigabe / Live-Handelsberechtigung (Streng konditional)         |
+-----------------------------------------------------------------------------------+
```

### Stufe S1: Präregistrierung (`Hypothesis-PreReg`)
- Bevor Tests oder Optimierungen laufen, muss die Hypothese im Trials-Ledger mit kryptographischem Hash (`params_sha256`), Akzeptanzkriterien (`acceptance={n_min, edge_min, dsr_min}`), Ziel-Symbol, Timeframe, Regime-Kontext und Zeithorizont (`bars` oder `until_date`) registriert werden.
- Status: `PREREGISTERED`, Zeitstempel: `frozen_at` (ISO-8601 UTC).

### Stufe S2: In-Sample (IS) Discovery
- Quantitative Modellbildung auf dedizierten Trainings-Perioden.
- Parameter werden vor jeglicher Out-of-Sample-Prüfung final fixiert.

### Stufe S3: Walk-Forward Out-of-Sample (OOS)
- Walk-Forward Backtesting mit $K \ge 4$ nicht-überlappenden Test-Folds.
- Statistische Absicherung gegen multiples Testen via Deflated Sharpe Ratio (DSR), berechnet über die Gesamtzahl aller historischen Modell-Trials im Ledger ($N_{trials}$).

### Stufe S4: Single-Shot Lockbox Holdout
- Prüfung auf einem vorab kryptographisch und zeitlich gesperrten Forward-Holdout-Datensatz (`LOCKED`).
- **Single-Shot-Regel:** Der Datensatz darf genau einmal evaluiert werden. Eine wiederholte Nutzung zerstört den Holdout-Charakter und führt zur sofortigen Entwertung.

### Stufe S5: Forward Shadow Testing
- Der Node/Relay `Shadow Collector` zeichnet jede Funnel-Entscheidung (akzeptiert und verworfen) mit Begründung in Echtzeit auf.
- Deterministische Auswertung nach 24 Kerzen (`hit_sl`, `hit_tp1`, `hit_tp2`, `time_stop`, Netto-R unter Berücksichtigung von Maker-/Taker-Fees und Slippage).

### Stufe S6: Produktions-Freigabe (Live Trading)
- Nur erreichbar, wenn **sowohl** Stufe S4 (Lockbox-Pass) **als auch** Stufe S5 (registrierte Forward-Kriterien) über ein 90-Tage-Rollfenster erfüllt sind.

---

## 2. Kriterien zur Hebung des Evidenz-Status (Elevation Gate)

Ein Setup oder Modell darf seinen Status von `NO_EVIDENCE` bzw. `PAPER_CANDIDATE` auf `EVIDENCE_CONFIRMED` **ausschließlich** dann heben, wenn **alle** folgenden Kriterien kumulativ erfüllt sind:

1. **Exakter Präregistrierungs-Match:** Die getestete Strategie stimmt bezüglich `params_sha256`, Symbol, Timeframe und Acceptance-Schwellen exakt mit einem vorab im Ledger registrierten `Hypothesis-PreReg`-Eintrag überein.
2. **Erfolgreicher Lockbox-Pass (S4):** Positiver statistischer Nachweis auf echten, zuvor ungesehenen Holdout-Daten.
3. **Erfolgreiche Forward-Kriterien (S5):** Live Shadow Tracking über mindestens 90 Tage mit mindestens $N \ge n_{min}$ Trades, einer Netto-Expectancy $\ge edge_{min}$ und $DSR \ge dsr_{min}$.
4. **Ununterbrochene Ledger-Kette:** Alle Schritte sind lückenlos in `docs/research/trials_ledger_chain.jsonl` dokumentiert und kryptographisch verifiziert.

Ohne die gleichzeitige Erfüllung von Lockbox-Pass **UND** registrierten Forward-Kriterien ist jede Hebung strikt verboten.

---

## 3. 90-Tage-Rollfenster & Verfallsregeln (`Evidence Decay`)

Statistische Evidenz an Finanzmärkten ist nicht permanent. Marktregime, Liquiditätsstrukturen und Volatilitätsmuster verändern sich kontinuierlich.

- **90-Tage-Rollfenster:** Die Gültigkeit eines Evidenznachweises wird über ein rollierendes 90-Tage-Zeitfenster kontinuierlich neu bewertet.
- **Evidence Decay (Evidenz-Verfall):** Liefert ein Modell über die letzten 90 Tage keine statistisch signifikante positive Netto-Expectancy mehr oder fällt die Trade-Anzahl unter das Mindestvolumen, verfällt der Evidenzstatus automatisch.
- **Sofortige Degradierung:** Bei Evidenzverfall wird das Modell unmittelbar von Stufe S6 auf Stufe S5 (Shadow-Modus) oder Stufe S1 zurückgestuft. Der Bot schaltet fail-closed ab.

---

## 4. Fail-Close-Regeln & Nicht-Evidenz (`NO_EVIDENCE`)

AURA folgt dem wissenschaftlichen Nullhypothesen-Prinzip: **Ein Modell besitzt standardmäßig keinen Edge, bis das Gegenteil unter strikt kontrollierten Bedingungen bewiesen wurde.**

1. **Nicht-Evidenz ist der Normalzustand:** Das Fehlen von Evidenz (`NO_EVIDENCE`) ist kein Systemfehler, sondern der wissenschaftlich ehrliche Ausgangszustand.
2. **Fail-Closed bei Unvollständigkeit:** Fehlende PreReg-Einträge, unvollständige Marktdaten, Datenlücken, nicht-positive OOS-Ergebnisse oder ungültige Hashes führen zum sofortigen Abbruch (`Exit != 0` bzw. `REJECTED`).
3. **Keine Aushebelung:** Weder hohe In-Sample-Gewinne noch historische Backtest-Kurven können ein negatives OOS-, Lockbox- oder Shadow-Urteil überschreiben.

---

## 5. Warum heute `NO_EVIDENCE` gilt (Transparente Erklärung)

Im aktuellen Entwicklungsstand (v1.9.0) liefert das Release-Gate folgendes ehrliches Ergebnis:
`verdict: "SOFTWARE_GO / MODEL_NO_EVIDENCE"`

### Wissenschaftliche Gründe:
1. **Walk-Forward OOS-Baseline auf realen Daten:** Die 5 Golden-Fixtures auf realen Marktdaten (BTC 1h, ETH 1h, SOL 1h, XRP 4h, DOGE 4h) zeigen nach Abzug realistischer Handelsgebühren (Maker 0.1%, Taker 0.1%, Slippage 0.1%) und unter Berücksichtigung der Deflated Sharpe Ratio (über alle historischen Versuche) keinen statistisch signifikanten positiven Edge über alle Regime hinweg.
2. **Lockbox-Holdout ungenutzt (`UNUSED`):** Die Lockbox wurde für die Modelle ehrlich als unberührtes Holdout deklariert und noch nicht verbraucht.
3. **Shadow Collector neu etabliert:** Die systematische Vorwärts-Erfassung ungefilterter Funnel-Entscheidungen (Slice C) wurde frisch integriert und sammelt nun die notwendigen 90 Tage an Live-Echtzeit-Outcomes.
4. **Software ist fehlerfrei (`SOFTWARE_GO`):** Alle Komponenten, Daten-Audits, K-Fold-Pipelines, mathematischen Orakel und Schattensammler arbeiten mit 100% deterministischer Präzision.

Das System arbeitet somit als Software-Terminal auf Enterprise-Niveau, täuscht dem Nutzer jedoch keine Scheingewinne vor.

---

## 6. PreReg- & Lockbox-Dokumentation

### Präregistrierung (`scripts/append_ledger.py --prereg`)
- Jeder neue Modellversuch muss vor der Ausführung in `docs/research/trials_ledger_chain.jsonl` mit Typ `Hypothesis-PreReg` hinterlegt werden.
- `scripts/hypothesis_check.py` validiert experimentelle Ergebnisse deterministisch gegen diese Registrierung.

### Lockbox Governance (`scripts/lockbox_register.py`)
- Die Sperrung von Holdout-Daten erfordert eine explizite Bestätigung auf den Prompt:
  `Lockbox-Spanne ab heute für N Tage sperren? Das kann nicht rückgängig gemacht werden.`
- Nach Bestätigung (`ja`/`yes`) wird der Holdout mit Status `LOCKED` versehen.
- Jede Auswertung eines Lockbox-Datensatzes wird unveränderlich im Ledger als konsumierter Single-Shot-Versuch protokolliert.
