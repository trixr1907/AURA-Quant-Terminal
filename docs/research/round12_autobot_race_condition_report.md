# AURA — Abschlussbericht Runde 12: Autobot-Scan Race-Condition & KPI-Klarheit (v1.2.12)

**Datum:** 2026-09-12  
**Auditor:** Hermes Agent (Senior Quant Systems Auditor & Coding Agent)  
**Ausgangsversion:** `1.2.11`  
**Zielversion / Veröffentlichte Version:** `1.2.12`  
**Kanonischer Release-Tag:** `v1.2.12` (Tag-Objekt: `3c204d95b955440aea92390c99960dd3a44d5d2a`, peeled: `45f5f3cd1ab1a04f825b5f0007b08c127fba4db4`)  
**Release-Urteil:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Exit 0)

---

## 1. Executive Summary & Wurzelursachen-Analyse

In Runde 12 wurde ein kritischer Race-Condition-Bug im Paper-Autobot behoben, der dazu führen konnte, dass zwei identische Positionen für dasselbe Symbol geöffnet wurden (z. B. doppelte `ALCHUSDT LONG`-Positionen).

### Wurzelursache im Detail:
1. **Asynchrone Laufzeit des Scans:** `scanAndExecuteOpportunities()` führt für jeden qualifizierten Kandidaten mehrere asynchrone Operationen durch (`await fetchKlines`, `analyze`, `runWalkForwardBacktest`). Bei einem Universum von Dutzenden Coins dauert der Durchlauf mehrere Sekunden.
2. **Unkoordinierte Auslöser:** Der Start-Button im UI rief den Scan direkt asynchron auf, während der reguläre `tick()`-Timer (alle 4s geprüft, Intervall 15s) parallel startete, falls `this.lastScanAt` noch nicht synchronisiert war.
3. **Prüfzeitpunkt des Duplikatschutzes:** Der bestehende Schutz `this.trades.some(x => x.coin === c.symbol)` wurde nur **vor** den `await`-Aufrufen geprüft. Zwei überlappende Scans sahen beide den Zustand vor Trade-Erstellung und öffneten beide dieselbe Position.

---

## 2. Implementierte Produkt-Fixes (PF-8 & PF-9)

### PF-8: Reentrancy-Guard & Belt-and-Suspenders-Deduplikation
- **Instanz-Flag `this._scanInProgress`:** Am Anfang von `scanAndExecuteOpportunities()` wird geprüft: Wenn `this._scanInProgress` aktiv ist, bricht der Scan sofort mit `return null` ab, **ohne** `lastScanFunnel` zu verändern oder zu überschreiben.
- **`try/finally`-Absicherung:** Das Flag wird in einem `finally`-Block garantiert wieder auf `false` zurückgesetzt.
- **Start-Button-Synchronisation:** Beim Klick auf den Start-Button wird `this.lastScanAt = Date.now()` gesetzt, sodass `tick()` nicht unmittelbar nachläuft.
- **Belt-and-Suspenders Deduplikations-Recheck:** Unmittelbar vor der Margin-Deduktion und `this.trades.push(newTrade)` (nach allen `await`-Aufrufen) wird `this.trades.some(x => x.coin === c.symbol)` ein zweites Mal geprüft. Bei einem Treffer wird die Position abgewiesen (`DUPLICATE_OR_INVALID`) und das Kapital geschützt.
- **Pflicht-Test:** `tests/test_autobot_scan_reentrancy.js` verifiziert nebenläufige Aufrufe, sofortiges `return null` des Zweitaufrufs, Unverfälschtheit des Funnels und das Greifen des Rechecks.

### PF-9: KPI-Label-Klarheit (Ehrliche Bezeichnungen)
- Das Autobot-KPI „Realisierter PnL" zeigte technisch `realizedPnl + unrealizedPnl` an. Das sichtbare Label wurde auf **„PnL gesamt (offen + realisiert)"** präzisiert (die korrekte Berechnung blieb unberührt).
- Das KPI „Win-Rate / Trades" wurde auf **„Win-Rate (realisiert) / Trades"** umbenannt, um transparent darzustellen, dass sich die Quote auf abgeschlossene Events bzw. Tranchen bezieht.

---

## 3. GitHub Release- & Verifikations-Evidenz (API-Belege)

### 3.1 Produkt Pull Request & Merge Commit
- **Pull Request:** [#10 (fix(autobot): resolve scan reentrancy race condition and duplicate positions (v1.2.12))](https://github.com/trixr1907/AURA-Quant-Terminal/pull/10)
- **Merge-Methode:** Normaler Merge-Commit (`--merge`, kein Squash)
- **Merge Commit SHA:** `45f5f3cd1ab1a04f825b5f0007b08c127fba4db4`
- **Merge-Parents (2 Parents nachgewiesen):**
  - Parent 1 (`main` vor PR #10): `5c7cdb231c6226f43614206bc933477c46f1c141`
  - Parent 2 (`fix/round12-autobot-race-condition` HEAD): `c62d84eda3f9e102aebaec251435399cf1feb9e6`

### 3.2 Annotierter Release-Tag
- **Tag:** `v1.2.12`
- **Tag-Objekt SHA:** `3c204d95b955440aea92390c99960dd3a44d5d2a`
- **Tag-Peel SHA (`v1.2.12^{commit}`):** `45f5f3cd1ab1a04f825b5f0007b08c127fba4db4`
- **Tag-Message:** `AURA v1.2.12 — Confluence Terminal (read-only research)`

### 3.3 GitHub Actions Check-Run Conclusions auf Merge Commit `45f5f3cd`
- `SonarCloud Code Analysis`: status=`completed`, conclusion=`neutral`
- `Socket Security: Project Report`: status=`completed`, conclusion=`success`
- `Test Suite & Quality Gates`: status=`completed`, conclusion=`success`
- `publish`: status=`completed`, conclusion=`success`

### 3.4 GitHub Release Asset (`symbiose.zip`)
Das Asset wurde nach dem Upload via GitHub API heruntergeladen und unabhängig gehasht:
- **Download-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.2.12/symbiose.zip`
- **Asset-Dateigröße:** `226.181 Bytes`
- **SHA-256 (nach Download verifiziert):**  
  `c759fe7a1c340f6cdfc83079365fdd98be5ff7e2439ea8173fa86cd94baecf54`
- **Dateianzahl im ZIP-Archiv:** `26`
- **VERSION im ZIP-Archiv:** `1.2.12`
- **Enthaltene Pflichtdateien:** `LICENSE` (vorhanden), `RELEASE_v1.2.12.md` (vorhanden), `README.md` (vorhanden), `VERSION` (vorhanden).

---

## 4. Test-Suiten & Hygiene-Bestätigungen (PF-10)

### 4.1 Reproduzierbare Test-Zählbefehle
- **Node.js Unit-Test-Dateien (`test_*.js`):**
  ```bash
  for f in tests/test_*.js; do node "$f" >/dev/null && echo "$f: PASS"; done | wc -l
  # Ausgabe: 51 (51 von 51 Suiten PASS)
  ```
- **Gesamte selbstausführende JS-Module in `tests/`:**
  ```bash
  for f in tests/*.js; do node "$f" >/dev/null 2>&1 && echo "$f: PASS"; done | wc -l
  # Ausgabe: 54 (51 test_*.js + 3 Runner-Module engine_oracle_export, model_evidence_real, sensitivity_release_gates)
  ```
- **Python Pytest Suite:**
  ```bash
  pytest -q
  # Ausgabe: 216 passed, 57 subtests passed in 9.21s
  ```
- **XSS & DOM-Sicherheits-Budget:**
  ```bash
  grep -c 'innerHTML' Symbiose_Dashboard.html
  # Ausgabe: 51 (exakt 51 Vorkommen, Budget eingehalten)
  ```
- **Release-Gate:**
  ```bash
  python3 scripts/release_check.py
  # Ausgabe: EXIT=0, Verdict: SOFTWARE_GO / MODEL_NO_EVIDENCE
  ```

---

## 5. Ledger-Klassifikation

- **Kategorie:** `PROCESS_FIX / DIAGNOSTICS`
- **Begründung:** Runde 12 implementiert einen reinen Concurrency- und UI-Labels-Fix. Es wurden keinerlei Berechnungsformeln für Scores, Indikatoren, DSR, Walk-Forward-Gates oder Sizing-Formeln verändert. Der Hash-Chain-Head bleibt unverändert bei `EXP-030` (`7a00e09a535da4327ab92ab1f69bb13814910d8128601812ab7f39d265f6a209`) mit 10 Modell-Experimenten verankert.
