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

Gemäß Regel 2 der `RELEASE_CHECKLIST.md` stammen alle folgenden Hashes aus den jeweils zitierten, tatsächlich ausgeführten Befehlen.

### Merge-Commit und Parents (PR #28)

```bash
git show -s --format='%H%n%P%n%s' e51f0f0a45b0758c9a0def4a054ba2a18abd8da0
# -> e51f0f0a45b0758c9a0def4a054ba2a18abd8da0
# -> 2235f371c784a753f44b5b1036182ce6f91deb1f 52dbabba8be19ad8cac89f7bbccda087cb509458
# -> Merge pull request #28 from trixr1907/fix/round20-v1.5.1
```

Die zwei Parents belegen den geforderten Merge-Commit; es wurde nicht gesquasht.

### Tag-Peel und kanonische Botschaft

```bash
git cat-file -p refs/tags/v1.5.1
# -> object e51f0f0a45b0758c9a0def4a054ba2a18abd8da0
# -> type commit
# -> tag v1.5.1
# -> tagger ivo <trixr@hotmail.de> 1789319969 +0200
# ->
# -> AURA v1.5.1 — Confluence Terminal (read-only research)

git rev-parse refs/tags/v1.5.1^{}
# -> e51f0f0a45b0758c9a0def4a054ba2a18abd8da0

git ls-remote origin refs/tags/v1.5.1 refs/tags/v1.5.1^{}
# -> c1edab76cd3c36aff8d835609ac197bb9df176c3 refs/tags/v1.5.1
# -> e51f0f0a45b0758c9a0def4a054ba2a18abd8da0 refs/tags/v1.5.1^{}
```

### GitHub Check-Runs des PR-Head-Commits

```bash
gh api repos/trixr1907/AURA-Quant-Terminal/commits/52dbabba8be19ad8cac89f7bbccda087cb509458/check-runs --jq '.check_runs[] | [.name,.conclusion,.details_url] | @tsv'
# -> SonarCloud Code Analysis failure https://sonarcloud.io/dashboard?id=trixr1907_AURA-Quant-Terminal2&pullRequest=28
# -> Socket Security: Pull Request Alerts success https://socket.dev
# -> Socket Security: Project Report success https://socket.dev/dashboard/org/ivo-to3gm/sbom/08251702-8660-425e-8b45-b257114a3a29
# -> Sourcery review skipped https://sourcery.ai
# -> Test Suite & Quality Gates success https://github.com/trixr1907/AURA-Quant-Terminal/actions/runs/34771108759/job/103760749974
# -> Test Suite & Quality Gates success https://github.com/trixr1907/AURA-Quant-Terminal/actions/runs/34771099007/job/103760725287
```

Der von `main` verlangte Check `Test Suite & Quality Gates` war erfolgreich. SonarCloud blieb ein nicht verpflichtender externer Check mit Fehlerstatus; dieser Status wird hier ungeschönt ausgewiesen.

### Veröffentlichungsworkflow und GitHub Release

```bash
gh run view 34771244469 --json status,conclusion,url,headSha,headBranch
# -> {"conclusion":"success","headBranch":"v1.5.1","headSha":"e51f0f0a45b0758c9a0def4a054ba2a18abd8da0","status":"completed","url":"https://github.com/trixr1907/AURA-Quant-Terminal/actions/runs/34771244469"}

gh release view v1.5.1 --json url,isDraft,isPrerelease,targetCommitish,tagName,assets --jq '[.isDraft,.isPrerelease,.tagName,.targetCommitish,.url,.assets[0].name,.assets[0].state,.assets[0].size,.assets[0].url] | @tsv'
# -> false false v1.5.1 main https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.5.1 symbiose.zip uploaded 240791 https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.5.1/symbiose.zip
```

### Release-Asset SHA-256 nach Download

```bash
rm -rf /tmp/aura-v151-release-download
mkdir -p /tmp/aura-v151-release-download
gh release download v1.5.1 -p 'symbiose.zip' -D /tmp/aura-v151-release-download
sha256sum /tmp/aura-v151-release-download/symbiose.zip
# -> 9d1b23c7c34af178c71bbd9c8fa89663a52a8289b3e0856537c4c501d059268a  /tmp/aura-v151-release-download/symbiose.zip
```

Der Asset-Hash unterscheidet sich vom lokalen Vorab-Build in Abschnitt 4, weil der Veröffentlichungsworkflow das Archiv aus dem getaggten Merge-Commit neu gebaut hat; ZIP-Metadaten können dabei den Container-Hash verändern. Die Prüfung aller 26 Nutzdaten-Mitglieder gegen den Tag ergab jedoch keine Abweichung:

```bash
python3 -c "import hashlib,subprocess,zipfile; p='/tmp/aura-v151-release-download/symbiose.zip'; z=zipfile.ZipFile(p); names=z.namelist(); forbidden=[]; [forbidden.append(n) for n in names if n.endswith('/') or n.startswith('/') or '..' in n.split('/') or '.hermes' in n.split('/') or '__pycache__' in n.split('/') or '.git' in n.split('/') or (n.split('/')[-1].lower().startswith('.env') and n.split('/')[-1].lower() != '.env.example')]; missing=[]; mism=[]; [(missing.append(n) if (r:=subprocess.run(['git','show','v1.5.1:'+n],capture_output=True)).returncode else mism.append(n) if hashlib.sha256(z.read(n)).digest()!=hashlib.sha256(r.stdout).digest() else None) for n in names]; print(f'members={len(names)} unique={len(set(names))} forbidden={len(forbidden)} missing_from_tag={len(missing)} hash_mismatches={len(mism)}'); print('RESULT: PASS' if not forbidden and not missing and not mism and len(names)==len(set(names)) else 'RESULT: FAIL')"
# -> members=26 unique=26 forbidden=0 missing_from_tag=0 hash_mismatches=0
# -> RESULT: PASS
```

### Docs-Hash aus dem getaggten Git-Objekt

Dieser Hash belegt den beim Release getaggten Bericht einschließlich der damals bewusst gesetzten Post-Release-Platzhalter. Der vorliegende Abschluss-Commit ergänzt anschließend ausschließlich die real ausgeführten Veröffentlichungsnachweise.

```bash
git show e51f0f0a45b0758c9a0def4a054ba2a18abd8da0:docs/releases/RELEASE_v1.5.1.md | sha256sum
# -> 3ed934d379438da2834c153469c72be90d781f00044ae5f5de687e3ac117d708  -
```

## 7. Schlussurteil

v1.5.1 macht die MTF-Konfiguration im Autobot-Pfad wirksam und erklärt null Signale verbrauchergerecht. Der Evidenz-Gate bleibt fail-closed. Ein technisch grüner Release bedeutet weiterhin keinen nachgewiesenen Trading-Edge: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
