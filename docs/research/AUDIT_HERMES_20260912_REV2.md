# Gesamtaudit Revision 2: AURA Quant Terminal (v1.2.5)

**Revisionsdatum:** 2026-09-12
**Auditor:** Senior Quant Systems Auditor (Hermes Agent)
**Baseline-Commit:** `0b7bc94b5dbb63b63cdbe9e0e81225b80cb839c8`
**Audit-Branch:** `audit/hermes-gesamtaudit-20260912`
**Vorgängerbericht:** `docs/research/AUDIT_HERMES_20260912.md`
**Nachfolgebericht (Revision 3):** `docs/research/AUDIT_HERMES_20260912_REV3.md` (Ursachenaufklärung F-16 in 3 Klassen, Beseitigung der Exit-Testlücken F-17 bis F-20)
**Scope:** ausschließlich die Nachprüfungspunkte N1–N6; keine neue Vollprüfung.

---

## 1. Revisionsurteil

Der ursprüngliche Audit bleibt in seiner Baseline-Disziplin, dem F-01-Repro und der Einordnung des TODO-Rauschens belastbar. Revision 2 korrigiert jedoch einen wesentlichen L3-Urteilsfehler: Das Delta von `4.746425474877469e-12` gehört nur zu `BTCUSDT_1h`. Vier der fünf Golden-Fixtures haben Soft-Mismatches mit maximalen Deltas von 8 bis 20. Sämtliche beobachteten Mismatches liegen nach der vom Harness bereits übersprungenen 1.200-Bar-Konvergenzzone; die pauschale Erklärung als frühe EMA-/RMA-Konvergenzartefakte trägt für diese Daten daher nicht.

Das L3-Urteil lautet in Revision 2 **MÄNGEL**. Die absoluten Toleranzen `SOFT_TOLERANCE = 25` und `SOFT_MISMATCH_RATE = 0.001` wurden nicht geändert. Stattdessen ist die bestehende Drift nun vollständig sichtbar und jede Verschlechterung gegenüber dem eingecheckten Referenzprofil wird fail-closed blockiert.

Der nachgeholte Mutationstest tötete 11 von 15 Mutanten. Vier Mutanten überlebten und sind gemäß Auftrag als getrennte Befunde F-17 bis F-20 ausgewiesen.

---

## 2. Aktualisierte Befundtabelle

Die Befunde F-01 bis F-15 des Originalberichts bleiben bestehen, soweit sie hier nicht ausdrücklich korrigiert werden.

| ID | Schwere | Layer | Revision-2-Befund | Status |
|---|---|---|---|---|
| **F-16** | **HIGH** | L3/L6 | Pine↔JS-Divergenzen außerhalb der Konvergenzzone; ursprüngliches Paritätsurteil verallgemeinerte den BTC-Bestwert auf alle Fixtures | offen; Drift-Regression im Gate überwacht |
| **F-17** | **MEDIUM** | L2/L3 | Mutation M04 der Kelly-Formel überlebt die vollständige Suite | offen |
| **F-18** | **HIGH** | L2/L3 | Mutation M13 der produktiven Time-Stop-Millisekunden-Skalierung überlebt | offen |
| **F-19** | **HIGH** | L2/L3 | Mutation M14 der produktiven Verlustbedingung des Time-Stops überlebt | offen |
| **F-20** | **MEDIUM** | L2/L3 | Mutation M15 des produktiven 12-Bar-Fallbacks überlebt | offen |
| **F-21** | **MEDIUM** | L4 | GitHub Actions waren in Release- und neuem CI-Workflow nur auf bewegliche Major-Tags gepinnt | behoben in `83cf989` |

Warum F-16 HIGH ist: Das beobachtete Core-Delta beträgt bis zu 5 Punkte. Auf `XRPUSDT_4h` bei `ts=1661472000000` wechselt der Core dadurch von Pine `52,437` (neutral) zu JS `57,437` (bullisch) und überschreitet die in Pine und JS implementierte Richtungsgrenze 55 (`Symbiose_Signal_System_v1.pine:101-103`, `Symbiose_Dashboard.html:1225-1226`). Damit ist eine unterschiedliche Signalaussage für dieselbe Kerze konkret nachgewiesen. Keines der zehn beobachteten Core-Paare überschreitet die vom Nachprüfungsauftrag zusätzlich genannten Grenzen 25/50/75; das ändert den realen 55er-Richtungswechsel nicht. Der Befund ist für ein Paritätsversprechen und ein Trading-UI materiell.

---

## 3. N1 — Vollständige Pine↔JS-Soft-Mismatch-Analyse

### 3.1 Repro und tatsächliche Ausgabe

**Codebeleg:** `tests/compare_pine_js_golden.js:138-186` (unveränderte Schwellen), `tests/compare_pine_js_golden.js:205-260` (ausführliche bzw. JSON-Ausgabe), `Symbiose_Signal_System_v1.pine:490-491` und `Symbiose_Dashboard.html:1225` (Core-Gewichtung).

**Repro:**

```bash
node tests/compare_pine_js_golden.js tests/fixtures/golden/*.csv --verbose
```

**Gekürzte echte Ausgabe:**

```text
PASS .../BTCUSDT_1h.csv: 13573 rows compared (1200 warmup), max delta 4.746425474877469e-12, soft-mismatches: 0 (0.0000%)
PASS .../DOGEUSDT_4h.csv: 9070 rows compared (1200 warmup), max delta 20, soft-mismatches: 2 (0.0221%)
PASS .../ETHUSDT_1h.csv: 13573 rows compared (1200 warmup), max delta 20, soft-mismatches: 2 (0.0147%)
PASS .../SOLUSDT_1h.csv: 13573 rows compared (1200 warmup), max delta 8, soft-mismatches: 10 (0.0737%)
PASS .../XRPUSDT_4h.csv: 9070 rows compared (1200 warmup), max delta 20, soft-mismatches: 6 (0.0662%)
```

### 3.2 Wahl der Konvergenzzone

Als Konvergenzzone werden **1.200 Bars ab Fixture-Start** angesetzt. Das ist keine neu erfundene Auditgrenze, sondern exakt die Grenze, die das Harness für tiefe Exporte bereits verwendet: `tests/compare_pine_js_golden.js:123-127` setzt `effWarmup = 1200` und vergleicht erst danach. Sie entspricht sechs EMA-200-Zeitkonstanten. Der verbleibende Initialisierungsanteil ist näherungsweise `(199/201)^1200 ≈ e^-12 ≈ 0,000006`; das ist konservativer als „wenige Wochen“. Ein Mismatch mit Barindex `< 1200` wäre mit Initialzustandskonvergenz vereinbar. Keiner der erfassten Mismatches liegt dort.

Barindizes wurden erzeugt mit einem `csv.DictReader`-Skript, das Fixture-Timestamps normalisiert und den Index je Mismatch nachschlägt. Echte Eckausgabe:

```text
ETHUSDT_1h.csv ... index=2448
SOLUSDT_1h.csv ... index=11461, 11462, 11486, 12158, 14772
XRPUSDT_4h.csv ... index=1215, 1422, 1746
DOGEUSDT_4h.csv ... index=1644
```

### 3.3 Vollständige Mismatch-Liste

Die Liste enthält auch das jeweils abhängige `core`-Delta, weil das Harness pro Feld zählt.

| Fixture | UTC-Zeit | Barindex | Feld | Pine | JS | Delta | Core-Auswirkung | 25/50/75 im beobachteten Wert überschritten? | Warmup-Urteil |
|---|---:|---:|---|---:|---:|---:|---:|---|---|
| ETHUSDT_1h | 2025-04-13 00:00 | 2448 | volumeScore | 75 | 95 | 20 | +5,0 | nein: Core 62,924 → 67,924 | nicht erklärbar |
| ETHUSDT_1h | 2025-04-13 00:00 | 2448 | core | 62,924 | 67,924 | 5,0 | bereits Core | nein | nicht erklärbar |
| SOLUSDT_1h | 2026-04-23 13:00 | 11461 | trend | 21 | 29 | 8 | +2,4 | nein: 29,675 → 32,075 | nicht erklärbar |
| SOLUSDT_1h | 2026-04-23 13:00 | 11461 | core | 29,675 | 32,075 | 2,4 | bereits Core | nein | nicht erklärbar |
| SOLUSDT_1h | 2026-04-23 14:00 | 11462 | trend | 21 | 29 | 8 | +2,4 | nein: 37,191 → 39,591 | nicht erklärbar |
| SOLUSDT_1h | 2026-04-23 14:00 | 11462 | core | 37,191 | 39,591 | 2,4 | bereits Core | nein | nicht erklärbar |
| SOLUSDT_1h | 2026-04-24 14:00 | 11486 | trend | 45 | 42 | 3 | −0,9 | nein: 67,753 → 66,853 | nicht erklärbar |
| SOLUSDT_1h | 2026-04-24 14:00 | 11486 | core | 67,753 | 66,853 | 0,9 | bereits Core | nein | nicht erklärbar |
| SOLUSDT_1h | 2026-05-22 14:00 | 12158 | trend | 52 | 55 | 3 | +0,9 | nein: 41,019 → 41,919 | nicht erklärbar |
| SOLUSDT_1h | 2026-05-22 14:00 | 12158 | core | 41,019 | 41,919 | 0,9 | bereits Core | nein | nicht erklärbar |
| SOLUSDT_1h | 2026-09-08 12:00 | 14772 | momentum | 10,752615 | 10,303913 | 0,448701 | −0,112175 | nein: 22,438 → 22,326 | nicht erklärbar |
| SOLUSDT_1h | 2026-09-08 12:00 | 14772 | core | 22,438154 | 22,325978 | 0,112175 | bereits Core | nein | nicht erklärbar |
| XRPUSDT_4h | 2022-07-22 12:00 | 1215 | trend | 69 | 66 | 3 | −0,9 | nein: 42,059 → 41,159 | nicht erklärbar |
| XRPUSDT_4h | 2022-07-22 12:00 | 1215 | core | 42,059 | 41,159 | 0,9 | bereits Core | nein | nicht erklärbar |
| XRPUSDT_4h | 2022-08-26 00:00 | 1422 | volumeScore | 18,487846 | 38,487846 | 20 | +5,0 | nein: 52,437 → 57,437 | nicht erklärbar |
| XRPUSDT_4h | 2022-08-26 00:00 | 1422 | core | 52,437 | 57,437 | 5,0 | bereits Core | nein | nicht erklärbar |
| XRPUSDT_4h | 2022-10-19 00:00 | 1746 | volumeScore | 29,032044 | 49,032044 | 20 | +5,0 | nein: 27,058 → 32,058 | nicht erklärbar |
| XRPUSDT_4h | 2022-10-19 00:00 | 1746 | core | 27,058 | 32,058 | 5,0 | bereits Core | nein | nicht erklärbar |
| DOGEUSDT_4h | 2022-10-02 00:00 | 1644 | volumeScore | 5 | 25 | 20 | +5,0 | nein: 31,457 → 36,457 | nicht erklärbar |
| DOGEUSDT_4h | 2022-10-02 00:00 | 1644 | core | 31,457 | 36,457 | 5,0 | bereits Core | nein | nicht erklärbar |

**Konsistent mit EMA/RMA-Konvergenz:** keine.
**Nicht durch die dokumentierte Konvergenzhypothese erklärbar:** alle 20 Feld-Mismatches auf 10 Kerzen.

> **KORREKTUR & URSACHENAUFKLÄRUNG (Revision 3, 2026-09-12):**
> Die pauschale Bewertung *„alle 20 Mismatches nicht erklärbar / exakter Ursprung NICHT GEPRÜFT"* wurde in **Revision 3 (`docs/research/AUDIT_HERMES_20260912_REV3.md`)** vollständig auf Ursachenebene aufgeklärt und in drei Klassen zerlegt:
> 1. **Klasse 1 (4 Fälle volumeScore +20):** Floating-Point-Gleichheitsunterlauf am 00:00 UTC Reset (`close == hlc3 == vwapD`). Pine wertet `close > vwapD` als `false` (-10), JS leidet unter 64-Bit-Float-Unterlauf bei `(h+l+c)/3` und wertet als `true` (+10).
> 2. **Klasse 2 (5 Fälle trend ±3 / +8):** Inhärente Messerschneiden-Diskretisierung an den harten ADX-Schwellen 18.0 und 25.0 durch unvermeidbare kontinuierliche RMA-Restdifferenzen (0.01 bis 0.8) über endliche Historie.
> 3. **Klasse 3 (1 Fall momentum 0.4487):** Kontinuierliches RMA-Restkonvergenzrauschen in RSI/Stoch-RSI.

Wichtig zur Schwellenwirkung: Keiner der konkret beobachteten Core-Paare überquert 25, 50 oder 75. Ein `volumeScore`-Delta 20 verändert den Core aber um 5 Punkte, ein `trend`-Delta 8 um 2,4 Punkte. Deshalb **kann** dieselbe Komponentenabweichung bei einer Kerze nahe einer Gate-Grenze eine Schwelle überqueren; nur in diesen zehn beobachteten Kerzen geschieht es nicht.

### 3.4 Produktfrage

**Ja, Pine-Overlay und Dashboard erzeugen für mindestens eine exportierte Kerze unterschiedliche Signalaussagen.** Konkreter Beleg: Auf `XRPUSDT_4h` bei `ts=1661472000000` ergibt Pine `core=52,437` und damit neutral, während JS `core=57,437` und damit bullisch ergibt. Beide Implementierungen klassifizieren oberhalb 55 bullisch und unterhalb 45 bärisch (`Symbiose_Signal_System_v1.pine:101-103`, `Symbiose_Dashboard.html:1225-1226`). Die zehn beobachteten Kerzen überschreiten keine der zusätzlich geprüften Grenzen 25/50/75; der reale Wechsel über die operative Richtungsgrenze 55 beantwortet die Produktfrage dennoch eindeutig mit Ja. Der exakte Ursprung der diskreten Trend-/Volumensprünge ist **NICHT GEPRÜFT**; Revision 2 belegt, dass die bisherige Warmup-Erklärung nicht genügt, lokalisiert aber noch nicht die Pine-vs.-JS-Zweigentscheidung.

---

## 4. N2 — Mutationstest der fünf Kernfunktionen

### 4.1 Methode und Repro

**Codebeleg:** `scripts/audit_rev2_mutations.py:1-242`; mutierte Produktstellen: Score `Symbiose_Dashboard.html:1225`, Kelly `:1399-1413`, Regime-Gate `:1784-1788`, Liquidität `:8456-8460`, Time-Stop `:8340-8344`.

Jede der 15 Mutationen wurde einzeln eingespielt. Danach liefen alle 40 selbstlaufenden `tests/test_*.js` und `python3 -m pytest -q`. Im `finally`-Block wurden die ursprünglichen Bytes zurückgeschrieben. Repro:

```bash
python3 scripts/audit_rev2_mutations.py --output /tmp/aura_rev2_mutation_results.json
```

Echte Zusammenfassung:

```text
SUMMARY killed=11 survived=4 total=15
{"git_diff_empty": true, "git_diff_exit": 0, "source_bytes_restored": true,
 "source_sha256_after": "a993f1b15db0e1180b225b5ca35f03e2e43a45886a9e8764baa5d9a0e2dd778e",
 "source_sha256_before": "a993f1b15db0e1180b225b5ca35f03e2e43a45886a9e8764baa5d9a0e2dd778e"}
```

### 4.2 Mutationsmatrix

| Funktion | ID / Mutation | Erwartete Wirkung | Rot werdender Test | Reaktion? |
|---|---|---|---|---|
| Score | M01 Trendbeitrag Vorzeichenflip | Scores/Golden-Parität ändern | `test_audit_integrity.js`, `test_model_evidence_real.js`, Pytest | ja |
| Score | M02 Volumeninput +1 | Scores ändern | `test_audit_integrity.js`, `test_model_evidence_real.js` | ja |
| Score | M03 Momentum `+`→`-` | Scores/Trades ändern | `test_audit_integrity.js`, `test_model_evidence_real.js`, Pytest | ja |
| calcKelly | M04 Formelzähler `-1`→`+1` | falsches Kelly trotz positiver Inputs | keiner | **nein — F-17** |
| calcKelly | M05 Half-Kelly `0.5`→`-0.5` | Risiko/Edge null/negativ | `test_engine_full.js`, `test_live_trade_tracker.js` | ja |
| calcKelly | M06 `hasEdge > 0`→`< 0` | Edge-Flag invertiert | `test_engine_full.js`, `test_live_trade_tracker.js` | ja |
| Regime | M07 Gate-Aktivierung invertiert | Regime-Gate bei falschem Modus aktiv | `test_engine_full.js` | ja |
| Regime | M08 Long-Regimevergleich invertiert | gültige Longs blockiert/falsche erlaubt | `test_engine_full.js`, `test_model_evidence_real.js` | ja |
| Regime | M09 Squeeze-Veto invertiert | falsche Bars blockiert/erlaubt | `test_engine_full.js`, `test_model_evidence_real.js` | ja |
| Liquidität | M10 Verified-Vergleich invertiert | verifizierte Liquidität blockiert | vier Autobot-/Liquidity-Tests | ja |
| Liquidität | M11 Volumengrenze `<`→`>=` | liquide Assets blockiert, illiquide möglich | drei Autobot-Tests | ja |
| Liquidität | M12 `unverified || invalid`→`&&` | einzelne fehlende Evidenz kann durchrutschen | `test_autobot_scan_diagnostics.js` | ja |
| Time-Stop | M13 `*60000`→`/60000` | produktiver Hold-Zeitraum kollabiert | keiner | **nein — F-18** |
| Time-Stop | M14 `curRoi < -3`→`> -3` | Gewinner statt Verlierer geschlossen | keiner | **nein — F-19** |
| Time-Stop | M15 Fallback 12→13 Bars | produktiver Default verschoben | keiner | **nein — F-20** |

F-17 ist MEDIUM, weil Boundary-/Property-Tests Caps und Edge-Flags prüfen, aber nicht den exakten positiven `fStar`-Wert. F-18 und F-19 sind HIGH: Sie betreffen den produktiven Autobot-Exitpfad und könnten Trades um Größenordnungen zu früh beziehungsweise auf der falschen PnL-Seite schließen. F-20 ist MEDIUM: explizit konfigurierte `timeStopBars` bleiben unberührt, aber der Fallback ist ungeschützt.

---

## 5. N3 — F-03-Beleglage und ehrliche Testsemantik

### 5.1 Absicht

Die Absicht ist über die Commit-Message hinaus belegt:

- `docs/releases/RELEASE_v1.2.4.md:18-20`: „Paper Trading Vollständig Freigeschaltet“, künstliche Cockpit-Sperre entfernt, jederzeitiger manueller Start mit ATR-Fallback.
- `docs/CHANGELOG.md:17-18`: Hero-Candidate-Locks auf `btn-paper-trade`/`startPaperTradeFromCockpit` entfernt.
- Commit-Diff `git show 4e4a726 -- Symbiose_Dashboard.html` entfernt `btnPaper.disabled = !paperAllowed` und den `canStartHeroPaperTrade(L)`-Guard aus dem Cockpit-Handler.

Die ursprüngliche Aussage „bewusst“ war inhaltlich richtig, aber im Bericht unzureichend belegt.

### 5.2 Korrigierte Testaussage und Autobot-Negativprobe

**Repro:**

```bash
grep -c canStartHeroPaperTrade Symbiose_Dashboard.html
node tests/test_hero_paper_gate.js
node tests/test_autobot_entry_gate.js
```

**Echte Ausgabe:**

```text
1
PASS cockpit paper trade is intentionally ungated; autobot gates remain fail-closed
PASS Autobot only enters freshly revalidated Action Radar Hot Setups
```

`canStartHeroPaperTrade` kommt genau einmal vor: in seiner Definition (`Symbiose_Dashboard.html:5002`), nicht im Cockpit-Handler. `tests/test_hero_paper_gate.js:72-75` prüft nun explizit, dass der Cockpit-Handler das Gate nicht aufruft.

Wirksamkeitsprobe: `candidate.executable !== true` wurde temporär zu `=== true` invertiert und `node tests/test_autobot_entry_gate.js` ausgeführt. Echte Ausgabe, danach vollständige Wiederherstellung:

```text
broken Autobot gate exit: 1
AssertionError [ERR_ASSERTION]: an actual radar Hot Setup must be accepted
```

Produktsemantik: **Autobot-Pfad fail-closed; manueller Cockpit-Paper-Button absichtlich ungekoppelt und daher nicht fail-closed im selben Sinn.**

---

## 6. N4 — Ledger-Roadmap und Supply Chain

### 6.1 F-06 wird Welle W3 zugeordnet

- **Aufwand:** etwa 1–2 Tage.
- **Risiko:** mittel; Migration darf historische Einträge nicht neu schreiben oder still neu hashen.
- **Konkrete Maßnahme:** kanonisches strukturiertes Ledger mit `previous_hash`/`entry_hash` pro Eintrag; CI rekonstruiert die SHA-256-Kette und vergleicht historische Prefix-Hashes gegen einen signierten Checkpoint. Alternativ oder ergänzend signierte Git-Tags/Commits für Checkpoints. Nur ein normaler Git-Diff-Test reicht nicht als Kryptografie.
- **Abnahmekriterium:** Mutation einer historischen Zeile macht die CI rot; Append eines korrekt verketteten Eintrags bleibt grün.

### 6.2 F-21 — bewegliche Action-Tags

**Beleg vor Fix:** `.github/workflows/publish-release.yml:45,59` nutzte `actions/checkout@v4` und `actions/setup-python@v5`; das neu erstellte `.github/workflows/ci.yml:27,32,37` ebenso plus `actions/setup-node@v4`.

Die GitHub-API löste am 2026-09-12 auf:

```text
checkout-v4    11d5960a326750d5838078e36cf38b85af677262
setup-python-v5 a26af69be951a213d495a4c3e4e4022e16d87065
setup-node-v4   49933ea5288caeca8642d1e84afbd3f7d6820020
```

Commit `83cf989` pinnt diese 40-stelligen SHAs. Die maschinelle Prüfung meldete `0 []` bewegliche Action-Refs.

`contents: write` ist für `gh release create ... --generate-notes` nötig, weil damit ein GitHub Release und Asset geschrieben werden. Es kann nicht auf eine einzelne Step-Permission begrenzt werden; GitHub Actions unterstützt Permissions auf Workflow- oder Job-Ebene. Deshalb ist der Workflow-Default jetzt `contents: read`, der einzige Publish-Job erhält `contents: write` (`.github/workflows/publish-release.yml:14-25`). Die Berechtigung ist auf Job-Ebene minimal, aber wegen der Ein-Job-Struktur weiterhin während Build/Test dieses Jobs vorhanden. Eine noch engere zeitliche Trennung erfordert zwei Jobs plus Artefaktübergabe und war außerhalb des engen Scope.

---

## 7. N5 — Zahlenkonsistenz und Tags

Alle Werte wurden neu erzeugt:

```bash
find tests -maxdepth 1 -type f -name 'test_*.js' -printf '.' | wc -c   # 40
find tests -maxdepth 1 -type f -name '*.js' -printf '.' | wc -c         # 44
find tests -maxdepth 1 -type f -name '*.js' ! -name 'test_*.js' -printf '%f\n' | sort
python3 -m pytest -q
wc -l Symbiose_Dashboard.html && wc -c Symbiose_Dashboard.html
```

Echte Werte am Dokumentationszeitpunkt:

- 40 selbstlaufende JS-Testdateien im Discovery-Muster `test_*.js`.
- 44 `.js`-Dateien insgesamt.
- Vier Nicht-Selbstläufer:
  - `compare_pine_js_golden.js`: Harness/CLI und importiertes Modul; der Selbsttest ist `test_compare_pine_js_golden.js`.
  - `engine_oracle_export.js`: Oracle-Datenexport, von `tests/reference_backtest.py` aufgerufen.
  - `model_evidence_real.js`: Berichtsgenerator/Gate, von `release_check.py` und `test_model_evidence_real.js` aufgerufen.
  - `sensitivity_release_gates.js`: Berichtsgenerator, von `release_check.py` aufgerufen; dokumentiert selbst „not a gate“.
- Baseline-Pytest laut `BASELINE_20260912.md`: **178 passed, 57 subtests passed**. Die Originalangabe „180 Pytest-Units“ war falsch.
- Aktueller Rev2-Stand nach neuen Regressionstests: **193 passed, 57 subtests passed**.
- Dashboard: **8.971 Zeilen, 471.140 Bytes**.

### Veralteter lokaler Tag-Stand

**Repro:** `git tag --list 'v*' --sort=-v:refname` zeigte lokal als höchsten Tag `v1.2.2`; `git ls-remote --tags origin` zeigte zusätzlich `v1.2.3`, `v1.2.4`, `v1.2.5`.

Bewertung: Härten war erforderlich. Ein Versionsgate darf lokal nicht still gegen veraltete Metadaten bestehen. Commit `795aa47` liest nun den höchsten strikten SemVer-Tag sowohl lokal als auch per `git ls-remote --tags origin`, verändert lokale Refs nicht und scheitert fail-closed, wenn der Origin-Stand nicht verifiziert werden kann. Der normale CI-Pfad ruft `python3 scripts/release_check.py` ohne `--allow-current-version` auf. Das Gate löst den Remote-Tag auf, zählt Commits in `<Tag>..HEAD` und kombiniert diese mit Worktree-Änderungen; dadurch blockiert es sowohl bereits committete als auch uncommittierte Änderungen ohne Versionsbump. Das Ausnahme-Flag bleibt ausschließlich für explizite Audit-/Reproduktionsläufe. Direkter CI-äquivalenter Repro ohne Flag:

```text
[FAIL] version progression {"version":"1.2.5","tag":"v1.2.5","error":"version bump required for update",...}
VERDICT: FAIL
EXIT=2
```

Mit `--allow-current-version` für den dokumentierten Audit-Repro lautet derselbe Check `[OK]` und nennt weiterhin `local_tag:"v1.2.2"`, `remote_tag:"v1.2.5"`, `local_tags_stale:true`.

In CI bleibt `fetch-depth: 0` sinnvoll; der Remote-Abgleich schützt zusätzlich lokale Läufe und falsch konfigurierte Checkouts.

---

## 8. N6 — Sichtbares Paritätsprofil und No-Regression-Trendgate

**Codebeleg:** `tests/compare_pine_js_golden.js:205-260`, `tests/fixtures/golden/parity_reference.json:1-31`, `scripts/release_check.py:427-512` und `:623-624`, `tests/test_release_sync.py:526-648`.

Der Harness besitzt nun `--json`. `release_check.py` speichert im Check-Detail für jedes Fixture:

- `max_delta`
- `soft_mismatches`
- `soft_rate`
- die drei eingecheckten Referenzwerte
- konkrete Regressionen

Die Referenz friert den am 2026-09-12 beobachteten Iststand ein. Sie behauptet nicht, die Abweichungen seien korrekt. Jede Erhöhung von maximalem Delta, Soft-Anzahl oder Soft-Rate schlägt fehl, selbst solange die unveränderten absoluten Grenzen 25 und 0,1 % noch eingehalten würden. Das Gate verlangt zudem `ok: true`, exakt die fünf erwarteten eindeutigen Fixtures und endliche numerische Pflichtmetriken; fehlende, doppelte oder unerwartete Einträge scheitern fail-closed.

**Normale Verifikation:**

```bash
python3 scripts/release_check.py --allow-current-version
```

Echte Ausgabe (gekürzt):

```text
[OK] golden 5-symbol comparison & trend {"metrics":[{"fixture":"BTCUSDT_1h.csv","max_delta":4.746425474877469e-12,...
VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) ...
EXIT=0
```

**Künstliche Regression:** Ein In-Memory-Bericht setzte SOL `soft_mismatches` von 10 auf 11, ohne Fixture oder Referenzdatei zu verändern:

```text
ARTIFICIAL_REGRESSION_STATUS=FAIL
{"regressions":[{"fixture":"SOLUSDT_1h.csv","metric":"soft_mismatches","actual":11,"reference":10}]}
```

Damit ist nachgewiesen, dass derselbe Gate-Pfad, den CI über `python3 scripts/release_check.py` ohne Bypass-Flag ausführt, die Verschlechterung rot bewertet. Zusätzliche Negativtests belegen den Fail-closed-Modus bei fehlendem `ok`, nicht endlichen Metriken und doppelten oder unerwarteten Fixtures. `SOFT_TOLERANCE` und `SOFT_MISMATCH_RATE` blieben unverändert.

---

## 9. Korrigierte Schichturteile L1–L6

- **L1 Reproduzierbarkeit & Build: SAUBER (nach Fixes).** Keine N1–N6-Erkenntnis kehrt dieses Urteil um. Zahlen wurden korrigiert.
- **L2 Test-Integrität: MÄNGEL.** Discovery und CI sind verbessert, aber vier von 15 gezielten Kernmutationen überlebten. Besonders der produktive Time-Stop-Pfad ist durch drei überlebende Mutationen nicht ausreichend behavior-basiert abgesichert.
- **L3 Quantitative & Statistische Integrität: MÄNGEL.** Lookahead-Invarianz und ehrliches `MODEL_NO_EVIDENCE` bleiben Stärken. Die behauptete nahezu exakte Gesamtparität ist aber widerlegt; F-16 und der ungeschützte Kelly-/Time-Stop-Rechenpfad verhindern `SAUBER`.
- **L4 Security & Supply Chain: SAUBER (nach Fixes), mit offenen Altbefunden.** N4/F-21 wurde durch SHA-Pinning und Job-Level-Permissions behoben. F-09 aus Runde 1 bleibt als MEDIUM-Roadmap-Befund bestehen.
- **L5 Codequalität & Wartbarkeit: MÄNGEL.** Unverändert: 471.140-Byte-/8.971-Zeilen-Monolith und String-Slicing-Kopplung.
- **L6 Produkt-Ehrlichkeit & Doku-Kohärenz: MÄNGEL.** Die UI bleibt ehrlich paper-only und `MODEL_NO_EVIDENCE` bleibt korrekt. Die pauschale Aussage „Risk Gates schließen fail-closed“ war aber zu breit: Autobot ja; manueller Cockpit-Paper-Button absichtlich nein. Außerdem war das Paritätsversprechen überzogen.

---

## 10. Aktualisierte Roadmap

### W1 — in Revision 2 behoben

- N1: vollständige Mismatch-Ausgabe (`55a27a9`).
- N3: wahrheitsgemäße Cockpit-vs.-Autobot-Testsemantik (`a8ee49e`).
- N4/F-21: Action-SHA-Pinning und Job-Level-Release-Permission (`83cf989`).
- N5: Origin-Tag-Abgleich für Version Progression (`795aa47`).
- N6: maschinenlesbares Paritätsprofil plus No-Regression-Gate (`6034fe6`).

### W2 — vor nächstem Release

- **F-17:** Exakten `fStar`-, `halfKelly`- und `riskAmt`-Oracle-Test mit analytisch berechneten Werten ergänzen (Aufwand: 1–2 Stunden, geringes Risiko).
- **F-18/F-19/F-20:** Produktiven `Autobot.monitorTrades()`-Pfad mit kontrollierter Zeit/PnL direkt testen: 15m/1h/4h/1d, vor/nach Deadline, Gewinner/Verlierer, Break-even, explizite und Fallback-Bars (Aufwand: 0,5–1 Tag, geringes Risiko).
- **F-16:** Diskrete Branch-Differenzen bei OBV/EMA und Trendbedingungen anhand der zehn betroffenen Kerzen instrumentieren und Pine-Data-Window-Zwischenwerte neu exportieren (Aufwand: 1–2 Tage plus TradingView-Zugriff; mittleres Risiko). Erst danach absolute Toleranz fachlich neu bewerten.

### W3 — strukturell

- **F-06:** Ledger-Hashkette plus signierter Checkpoint und CI-Prefix-Integritätsprüfung umsetzen (Aufwand: 1–2 Tage; mittleres Migrationsrisiko).
- F-05 an globalen historischen Trials-Zähler koppeln.
- Dashboard-Engine modularisieren und String-Slicing-Tests abbauen.

---

## 11. Erneute Antwort: drei Hinderungsgründe für den täglichen Einsatz

**Die Antwort hat sich gegenüber Runde 1 geändert.** Die behobene Origin-Schwachstelle gehört nicht mehr in die drei aktuellen Hinderungsgründe. Die Paritätsfrage gehört jetzt ausdrücklich hinein.

1. **Ungeklärte Pine↔Dashboard-Parität.**

   Vier von fünf Fixtures divergieren außerhalb der 1.200-Bar-Konvergenzzone; Core-Deltas erreichen 5 Punkte. Auf `XRPUSDT_4h` bei `ts=1661472000000` ist die Folge bereits konkret: Pine bleibt mit Core 52,437 neutral, JS wird mit 57,437 bullisch und überschreitet die operative Richtungsgrenze 55. Der Grund entfällt erst, wenn die zehn betroffenen Kerzen auf Pine-/JS-Zwischenwertniveau erklärt oder korrigiert sind und neue unabhängige Exporte übereinstimmen.

2. **Fehlende Out-of-Sample-Alpha-Evidenz (`MODEL_NO_EVIDENCE`).**

   Das ist weiterhin kein Softwarefehler, aber ein legitimer Grund gegen täglichen Einsatz als Entscheidungssystem. Er entfällt erst mit prospektiver, unabhängiger OOS-Evidenz nach Kosten, Slippage und Multiple-Testing-Korrektur. Bis dahin ist das Produkt Research-/Paper-Werkzeug.

3. **Monolith plus konkret nachgewiesene Testlücken im produktiven Exitpfad.**

   Der 8.971-Zeilen-Monolith bleibt schwer sicher zu ändern; zusätzlich überlebten drei Mutationen an Time-Stop-Skalierung, Verlustbedingung und Fallback. Der Grund entfällt durch direkte behavior-basierte `monitorTrades()`-Tests und anschließend inkrementelle Engine-Modularisierung ohne String-Slicing-Kopplung.

Die Runde-1-Punkte „Monolith“ und „keine OOS-Evidenz“ bleiben. Der frühere dritte Punkt „Origin-Schnittstelle“ ist durch F-01/F-13 behoben und wird durch „ungeklärte Parität“ ersetzt; die Mutationsergebnisse verschärfen den Monolith-/Testpunkt.
