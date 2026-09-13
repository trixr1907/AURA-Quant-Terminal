# AURA Quant Terminal — Runde 20 Schlussbericht (v1.5.1, PATCH)

## 1. Executive Summary

Runde 20 behebt zwei Ehrlichkeitsmängel im Paper-Autobot, ohne den quantitativen Evidenzschutz oder die Radar-Klassifikation zu lockern.

- PF-47: `evaluateAutobotCandidate` leitet die MTF-Freigabe aus dem übergebenen `mtfNeed` ab. Die Radar-Anzeige und ihr `SYM.mtfNeed`-Ranking bleiben getrennt und unverändert.
- PF-48: Der Funnel erklärt bei `selected === 0` den dominanten Ablehnungsgrund in Klartext. Reject-Labels besitzen Tooltips; MinScore-, MTF- und TimeStop-Hinweise benennen ihre tatsächliche Reichweite.
- Das Fresh-Gate revalidiert weiterhin direkt vor dem Einstieg.
- `evaluateAutobotEdge` lehnt weiterhin bei nichtpositivem Edge oder zu kleiner DSR ab.
- Urteil: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

## 2. Unveränderte harte Grenzen

Die Runde ändert weder `classifyRadarTf` noch seine festen Schwellen `SYM.longTh = 75`, `SYM.shortTh = 25`, Regime-Match, `ADX >= 20` und Squeeze-Block. Ebenso bleibt in `evaluateAutobotEdge` die Ablehnung für `edge <= 0 || testDsr < minDsr` inhaltlich unverändert.

Damit macht PF-47 ausschließlich einen bereits dokumentierten Konfigurationsvertrag wirksam: Ein Autobot-Wert von 1/4 kann eine technisch tradeable Radar-Zeile mit `aligned = 1` konsumieren, ohne die feste technische Qualifikation oder die spätere OOS-Evidenzprüfung zu umgehen.

## 3. Implementierung und Regressionstests

- `tests/test_pf47_mtf_knob_honored.js` prüft 1/4 akzeptiert, 3/4 abgelehnt, BTC-Block, nicht tradeable Best-TF und die konfigurationsabhängige `radarFiltered`-Zahl.
- `tests/test_pf48_funnel_explanation.js` prüft OOS- und Radar-Klartext, Unterdrückung bei ausgewähltem Setup, Reject-Tooltips, Settings-Hinweise und `textContent`-Rendering.
- Bestehende Entry-, Scan-, Fresh-Gate- und Diagnose-Suiten bleiben grün.
- Das `innerHTML`-Budget bleibt ohne Delta bei 51; neue dynamische Texte werden über DOM-Knoten und `textContent` angefügt.

## 4. Lokale Verifikation (Befehl + Ausgabe)

### Python-Suite

```bash
python3 -m pytest -q
# -> 236 passed, 57 subtests passed in 9.72s
```

### JavaScript-Suiten

```bash
count=0; for f in tests/test_*.js; do node "$f" >/dev/null || { echo "FAILED:$f"; exit 1; }; count=$((count+1)); done; echo "JS suites: $count/$count"
# -> JS suites: 77/77
```

Die Basis 75/75 wächst ausschließlich um die beiden geforderten Suiten `pf47_mtf_knob_honored` und `pf48_funnel_explanation` auf 77/77.

### innerHTML-Budget

```bash
printf 'innerHTML: '; grep -o innerHTML Symbiose_Dashboard.html | wc -l
# -> innerHTML: 51
```

### CVD-Gate

```bash
python3 scripts/cvd_reference.py
# -> "ok": true
# -> "max_flip_count": 0
# -> alle fünf Fixtures: "passed": true
```

### Release-Gate

```bash
python3 scripts/release_check.py
# -> [OK] js: pf47 mtf knob honored
# -> [OK] js: pf48 funnel explanation
# -> [OK] cvd independent reference parity
# -> [OK] pytest full suite  236 passed, 57 subtests passed
# -> VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) · synthetic-gate: PAPER_CANDIDATE · lockbox-eval: UNUSED
# -> EXIT=0
```

### Paket-Build vor Veröffentlichung

```bash
python3 scripts/build_package.py
# -> Built symbiose.zip: 26 files
# -> SHA-256: 51f13a03e51778f5b541305a1b994521f5e481d47ef17b8a5f65f8ec25c860c1
# -> SMOKE TEST: all non-browser checks passed from clean extraction
```

Dieser lokale Build-Hash ist kein Ersatz für den verbindlichen Asset-Nachweis nach Download des veröffentlichten GitHub-Release-Assets; dieser folgt in Abschnitt 6.

## 5. Ledger-Klassifikation

Kategorie: `PROCESS_FIX / UI_HYGIENE / CONFIG_PLUMBING`.

Begründung: PF-47 korrigiert die Verdrahtung eines vorhandenen MTF-Bedienelements im Autobot-Konsumpfad. PF-48 ergänzt ausschließlich verständliche Diagnostik und Bedienhinweise. Es wurden keine Score-, Sizing-, Evidenz-, DSR- oder Radar-Klassifikationsformeln geändert und keine neue Hypothese gegen Marktdaten ausgewertet. Daher entsteht kein neues Modell-Experiment.

```bash
python3 scripts/verify_ledger.py
# -> {"ok":true,"last_entry_id":"EXP-032","entry_count":7,"chain_head":"ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b","total_model_experiments":10,"legacy_sha256":"23f59ef8df9f348609280d8f57583e32c2d7afc1e9b428f9d50ae75051eeeb0c"}
```

## 6. Veröffentlichungsnachweise

Die folgenden Felder werden erst nach Merge, Tag und GitHub-Release mit tatsächlich ausgeführten Befehlen und deren Ausgaben ergänzt. Platzhalter sind bewusst keine Hash-Angaben.

### Merge-Commit und Parents

PENDING_POST_MERGE

### Tag-Peel und kanonische Botschaft

PENDING_POST_TAG

### GitHub Check-Runs

PENDING_POST_CI

### Release-Asset SHA-256 nach Download

PENDING_POST_RELEASE_DOWNLOAD

### Docs-Hash aus Git gelesen

PENDING_POST_DOCS_HASH

## 7. Schlussurteil

v1.5.1 macht die MTF-Konfiguration im Autobot-Pfad wirksam und erklärt null Signale verbrauchergerecht. Der Evidenz-Gate bleibt fail-closed. Ein technisch grüner Release bedeutet weiterhin keinen nachgewiesenen Trading-Edge: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
