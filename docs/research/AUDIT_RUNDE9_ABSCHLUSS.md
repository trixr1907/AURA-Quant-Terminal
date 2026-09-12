# AURA Audit Runde 9 — Abschlussbericht F-05, F-06, F-16

Datum: 2026-09-12
Release: v1.2.9

## 1. Executive Summary

F-05 und F-06 sind technisch geschlossen. Die Phase-D-DSR liest die historische Modellversuchszahl nur aus der erfolgreich verifizierten Ledger-Kette und verwendet als konservative Trial-Zahl `max(45, total_model_experiments)`. Das wahrt die alte Phase-D-Untergrenze und kann die DSR bei wachsendem Ledger nur senken.

F-16 ist ehrlich nur teilweise geschlossen: Klasse 1 ist behoben, Klasse 2 akzeptiert und Klasse 3 dokumentiert. Die geforderte CVD-Langzeitmessung kann mit dem vorhandenen unabhängigen Pine-Beweismaterial nicht ausgeführt werden, weil keine der fünf TradingView-CSV-Dateien CVD- oder EMA-CVD-Zustände enthält. v1.2.9 ergänzt die vier dafür notwendigen Data-Window-Exporte und den entsprechenden JS-Datenzugriff. Bis neue TradingView-Exporte vorliegen, bleibt der Status `MESSUNG BLOCKIERT`; es werden keine Driftwerte erfunden.

Das fachliche Urteil bleibt unverändert:

`SOFTWARE_GO / MODEL_NO_EVIDENCE`

## 2. Reihenfolge und PR-Disziplin

### Docs-only Bootstrap — gate-neutral

Befehl:

    gh pr view 2 --json number,state,mergedAt,mergeCommit,url,commits

Ausgabe (gekürzt auf die prüfrelevanten Felder):

    PR 2; state=MERGED
    mergeCommit=54d10f4360625c489dde8201edab6a649eb20246
    commits=11d46cd8 (Präregistrierung), 93232942 (Ledger-Bootstrap)
    url=https://github.com/trixr1907/AURA-Quant-Terminal/pull/2

Merge-Parent-Beleg:

    git show -s --format='%H %P %s' 54d10f4360625c489dde8201edab6a649eb20246
    54d10f4360625c489dde8201edab6a649eb20246 4a61692a8e35cbe37ba01ce4701fbdfd41fb4c3e 93232942d239cd195eff9160df0d68a5398424b3 Merge pull request #2 ...

Dieser PR änderte ausschließlich Markdown-/Research-Dokumente und die JSONL-Ledgerdaten. Er war damit nach dem pfadbewussten v1.2.8-Gate release-neutral. EXP-026 bis EXP-028 wurden als Prozess-/Mess-Fixes (`delta=0`) klassifiziert: Die Runde evaluiert keine neue Signal-, Schwellen-, Parameter-, Selektions- oder Universumslogik gegen Marktdaten, sondern repariert Evidenz-Provenienz und misst bestehende Parität.

### Produktrelease — release-pflichtig

Befehl:

    gh pr view 3 --json number,state,mergedAt,mergeCommit,url,commits

Ausgabe (gekürzt):

    PR 3; state=MERGED
    mergeCommit=c5d9348616b8cd0c21fdcb567058f565ab4b22ae
    commits=b2d5cbc, aa9798c, 1347719, 3012e8f
    url=https://github.com/trixr1907/AURA-Quant-Terminal/pull/3

Merge-Parent-Beleg:

    git show -s --format='%H %P %s' c5d9348616b8cd0c21fdcb567058f565ab4b22ae
    c5d9348616b8cd0c21fdcb567058f565ab4b22ae 54d10f4360625c489dde8201edab6a649eb20246 3012e8f9739ff715e4b52853c26960bab51d80ab Merge pull request #3 ...

Der PR änderte Produktcode (`scripts/`, `tools/`, Dashboard, Pine und Tests) und war daher release-pflichtig. Es gab keinen direkten Produkt-Push auf `main`; beide Merge-Commits haben je zwei Parents.

## 3. F-06 — Ledger-Hashkette

Der historische Bestand wurde bytegenau als `docs/research/TRIALS_LEDGER_LEGACY_v1.2.8.md` eingefroren. Die kanonische Serialisierung ist im Ledger dokumentiert: UTF-8, feste Feldreihenfolge, kompaktes JSON ohne ASCII-Escaping und genau ein LF. Jeder neue Eintrag enthält `prev_hash` und `entry_hash`.

Verifier-Beleg:

    python3 scripts/verify_ledger.py
    {"ok":true,"entry_count":3,"total_model_experiments":10,"legacy_sha256":"23f59ef8df9f348609280d8f57583e32c2d7afc1e9b428f9d50ae75051eeeb0c","chain_head":"da5723592ca1cd6c0467e9964ac407af884e622480812fedf7d0491cb74ae1dc"}

Regressionstest:

    python3 -m pytest tests/test_trials_ledger.py -q
    7 passed in 0.02s

Die Fälle umfassen gültige Kette, manipulierten Eintrag, korrektes Append, fehlende Dateien, gelöschten Eintrag, umsortierte Einträge und ungültiges JSON. `scripts/release_check.py` ruft den Verifier als Pflichtcheck auf; jede Ausnahme oder Exitcode ungleich null ergibt `FAIL`.

## 4. F-05 — autoritative DSR-Trial-Zahl

`tools/edge_diagnostic_phase_d.js` ruft `scripts/verify_ledger.py` auf. Fehlende, unparsbare oder ungültige Evidenz wird als `TRIALS_LEDGER_INVALID` abgebrochen. Es gibt keinen stillen Rückfall auf Radar- oder Defaultzahlen.

Die effektive Phase-D-Trial-Zahl lautet:

    DSR_TRIALS = max(45, total_model_experiments)

Warum `max`: Für feste Returns steigt `srStar` mit N und die DSR sinkt. Das größere N ist deshalb mathematisch strenger. Die 45 sind der vorherige gepoolte Phase-D-Suchraum; ein derzeit kleinerer Ledger-Zähler darf die alte Deflation nicht abschwächen.

Monotoniebeleg:

    node tests/test_dsr_ledger.js
    DSR_LEDGER_MONOTONIC PASS old_N=45 ledger_N=120 old_DSR=0.2692495647769471 new_DSR=0.17292439364937728

Damit gilt im Test bei `ledger_N >= old_N`: `DSR_neu <= DSR_alt`.

## 5. F-16 — CVD-Messstatus

Fixture-Inventur:

    python3 <CSV-Inventur über tests/fixtures/golden/*USDT_*.csv>
    BTCUSDT_1h.csv: bars=14773; columns=31; cvd_columns=[]
    DOGEUSDT_4h.csv: bars=10270; columns=31; cvd_columns=[]
    ETHUSDT_1h.csv: bars=14773; columns=31; cvd_columns=[]
    SOLUSDT_1h.csv: bars=14773; columns=31; cvd_columns=[]
    XRPUSDT_4h.csv: bars=10270; columns=31; cvd_columns=[]

Alle Fenster erfüllen die geforderten mindestens 5.000 Bars. Keine Datei enthält jedoch die unabhängigen Pine-Reihen `cvd`, `emaCvd`, `cvd > emaCvd` oder `volDelta`. Deshalb sind absolute Drift, relative Drift und Flipzahl mit dem existierenden Datenbestand mathematisch nicht identifizierbar: Eine ausschließlich aus OHLCV erneut berechnete „Pine“-Reihe wäre dieselbe Implementierungsannahme, kein unabhängiger Pine↔JS-Beleg.

Versuch, TradingView Desktop automatisiert zu nutzen:

    computer_use(action="list_apps")
    ERROR: computer_use backend unavailable ... create named pipe ... os error 123

Daher wurde nicht behauptet, die Desktop-Messung sei erfolgt. Stattdessen exportiert Pine v1.2.9 künftig:

    GM CVD
    GM EMA CVD 20
    GM CVD Above EMA
    GM CVD Delta

Das Dashboard liefert dazu `cvd`, `emaCvd` und `cvdDelta`. Vorab definierte Entscheidungsschwelle für den erneuten Exportlauf: jeder echte boolesche Kipp oder relative Drift größer `1e-10` erzwingt einen Fix; null Kipper und Drift höchstens `1e-10` erlauben den Status `AKZEPTIERT` mit symbolweisen Zahlen.

Der F-16-Status in `docs/research/AUDIT_ABSCHLUSS.md` wurde deshalb von einer zu breiten Akzeptanz auf `TEILS AKZEPTIERT / MESSUNG BLOCKIERT` korrigiert. Das ist bewusst kein falscher Abschluss des nicht messbaren Teilbefunds.

## 6. Tests vor und nach der Runde

Baseline in isoliertem v1.2.8-Worktree:

    python3 -m pytest -q
    197 passed, 57 subtests passed in 2.74s

Final auf v1.2.9:

    python3 -m pytest -q
    204 passed, 57 subtests passed in 2.77s

Netto kamen sieben pytest-Tests hinzu. Zusätzlich:

    node tests/test_engine_full.js
    ERGEBNIS: 121 PASSED | 0 FAILED | 121 TOTAL

## 7. Veröffentlichung und GitHub-API-Belege

Main und Tag:

    git ls-remote origin refs/heads/main
    c5d9348616b8cd0c21fdcb567058f565ab4b22ae

    git ls-remote origin refs/tags/v1.2.9
    c88c6d0eeb4e970b790850d715285d6e82417efe

    git ls-remote origin 'refs/tags/v1.2.9^{}'
    c5d9348616b8cd0c21fdcb567058f565ab4b22ae

Tag-Botschaft:

    git tag -n99 v1.2.9 | head -1
    v1.2.9  AURA v1.2.9 — Confluence Terminal (read-only research)

Check-Runs auf dem Merge-Commit:

    gh api repos/:owner/:repo/commits/c5d9348616b8cd0c21fdcb567058f565ab4b22ae/check-runs --jq ...
    publish  completed  success
    SonarCloud Code Analysis  completed  neutral
    Socket Security: Project Report  completed  success
    Test Suite & Quality Gates  completed  success

Release:

    gh release view v1.2.9 --json tagName,isDraft,isPrerelease,publishedAt,assets,url
    tagName=v1.2.9; isDraft=false; isPrerelease=false
    asset=symbiose.zip; size=222916
    url=https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.2.9

Heruntergeladenes Asset:

    asset_bytes=222916
    file_count=26
    LICENSE=True
    RELEASE=True
    VERSION=1.2.9

XSS-Inventar unverändert:

    grep -c innerHTML Symbiose_Dashboard.html
    51

## 8. Finaler Gate-Lauf

Befehl:

    python3 scripts/release_check.py; echo EXIT=$?

Prüfrelevante Ausgabe:

    [OK] trials ledger hash chain
    [OK] pytest full suite
    [OK] browser E2E (deterministic)
    [OK] version consistency ... 1.2.9
    [OK] version progression ... tag v1.2.9
    VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) · synthetic-gate: PAPER_CANDIDATE · lockbox-eval: UNUSED
    EXIT=0

## 9. Schlussurteil

v1.2.9 beweist Integrität der DSR-Eingabe und Tamper-Evidenz des Trials-Ledgers. Es schafft außerdem die notwendige Instrumentierung für die noch ausstehende unabhängige CVD-Messung. Es beweist keinen Edge. `MODEL_NO_EVIDENCE` bleibt bis zu einem echten OOS-Nachweis bestehen.
