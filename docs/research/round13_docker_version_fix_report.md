# AURA — Abschlussbericht Runde 13: Docker-VERSION-Hygiene & Fail-Fast (v1.2.13)

**Datum:** 2026-09-12  
**Auditor:** Hermes Agent (Senior Quant Systems Auditor & Coding Agent)  
**Ausgangsversion:** `v1.2.12`  
**Zielversion:** `v1.2.13`  
**Themenbereich:** Infrastruktur-Hygiene, Container-Packaging & Fail-Closed Versioning

---

## 1. Executive Summary & Root Cause Audit

In Runde 13 wurde die verbleibende Lücke im Docker-Packaging und Versions-Management dauerhaft und strukturell geschlossen:

1. **PF-11 (Dockerfile VERSION Copy):** `COPY --chown=aura:aura VERSION .` wurde fest in `Dockerfile` integriert.
2. **PF-12 (Relay Dynamic Fail-Fast):** `bitget_relay.py` lädt die Versionsinformation strikt dynamisch aus `VERSION` und beendet den Prozess mit `RuntimeError` (Fail-Closed), falls `VERSION` im Deployment fehlt. Veraltete, hartcodierte Versions-Fallbacks (`else "1.2.10"`) wurden restlos entfernt.
3. **PF-13 (Regressionsschutz & Runbook):** Automatisierte Tests in `tests/test_package_hygiene.py` prüfen das `Dockerfile` auf `COPY ... VERSION ...`, verifizieren das Fehlen von `1.2.x`-Fallbacks, erzwingen Versions-Parität und testen das Fail-Fast-Verhalten. Das Deployment-Runbook wurde um eine zwingende Post-Start-Verifikation (`GET /serving` vs. Ziel-Tag) ergänzt.

### Frage: Baut der Receiver auf der VM aus dem Release-ZIP oder aus einem Git-Checkout?
**Antwort:** Der Receiver auf der VM baut direkt aus dem **Release-ZIP (`symbiose.zip`)**.
- **Beweiskette:** Der Receiver lädt bei `release.published` das Release-Asset `symbiose.zip` via GitHub API herunter und entpackt alle Dateien nach `/opt/aura-terminal/`.
- Da `symbiose.zip` die `VERSION`-Datei stets enthielt, lag `VERSION` im lokalen Build-Verzeichnis `/opt/aura-terminal/VERSION` vor. Weil das `Dockerfile` jedoch vor Runde 13 nur `bitget_relay.py`, `Symbiose_Dashboard.html`, `SYMBIOSE_Tutorial.html` und `data/` kopierte, landete `VERSION` nie im Container-Dateisystem `/app/`.
- Durch PF-11 wird `VERSION` nun explizit in das Image kopiert, sodass Container-Builds aus `symbiose.zip` und Git-Checkouts identisch und vollständig sind.

---

## 2. GitHub-API-Belege (Verifikationsnachweis)

### 2.1 Produkt Pull Request & Merge Commit
- **PR:** [#13 (fix(docker): ensure VERSION file is copied to Docker image and enforce relay fail-fast (v1.2.13))](https://github.com/trixr1907/AURA-Quant-Terminal/pull/13)
- **Merge-Methode:** Normaler Merge-Commit (`--merge`, kein Squash — exakt 2 Parents)
- **Produkt-Merge-Commit SHA:** `9f92028300ecd0ef2401615a1a1219ee76ef0aa8`
- **Merge-Parents:**
  - Parent 1 (`main` vor PR #13): `718d9522293fc493699bfb572d3a0259cd0f7c61`
  - Parent 2 (`fix/round13-docker-version-hygiene` HEAD): `79cd8bac81930325da4d04e13f9e2d33dad2242e`

### 2.2 Annotierter Release-Tag
- **Tag:** `v1.2.13`
- **Tag-Objekt SHA:** `c1024e2cda50bff516823f11a28ec1f85c58fcdc`
- **Tag-Peel SHA (`v1.2.13^{commit}`):** `9f92028300ecd0ef2401615a1a1219ee76ef0aa8`
- **Tag-Message:** `AURA v1.2.13 — Confluence Terminal (read-only research)`

### 2.3 GitHub Actions Check-Run Conclusions auf Merge Commit `9f920283`
- `SonarCloud Code Analysis`: status=`completed`, conclusion=`neutral`
- `Socket Security: Project Report`: status=`completed`, conclusion=`success`
- `publish`: status=`completed`, conclusion=`success`
- `Test Suite & Quality Gates`: status=`completed`, conclusion=`success`

### 2.4 GitHub Release Asset (`symbiose.zip`)
Das Asset wurde nach dem Upload via GitHub API heruntergeladen und unabhängig gehasht:
- **Download-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.2.13/symbiose.zip`
- **Asset-Dateigröße:** `226.281 Bytes`
- **SHA-256 (nach Upload heruntergeladen):**  
  `4e66c9d79ce9863a64aa5b354559fc4e5e14e813d1db550555a4beef36bf2372`
- **Dateianzahl im ZIP-Archiv:** `26 Dateien`
- **VERSION im ZIP-Archiv:** `1.2.13`
- **Enthaltene Pflichtdateien:** `LICENSE` (vorhanden), `RELEASE_v1.2.13.md` (vorhanden), `README.md` (vorhanden), `VERSION` (vorhanden), `Dockerfile` (vorhanden).

---

## 3. Bestätigung der Prüf- und Hygiene-Kriterien

1. **Reproduzierbare Test-Zählbefehle & Suiten-Anzahl:**
   - **Node.js Unit-Test-Dateien (`tests/test_*.js`):**
     ```bash
     for f in tests/test_*.js; do node "$f" >/dev/null && echo "$f: PASS"; done | wc -l
     ```
     **Ergebnis:** Exakt **51** (51/51 Suiten PASS).
   - **Gesamte selbstausführende JS-Module in `tests/`:**
     ```bash
     for f in tests/*.js; do node "$f" >/dev/null 2>&1 && echo "$f: PASS"; done | wc -l
     ```
     **Ergebnis:** Exakt **54** (51 `test_*.js` + 3 Runner-Module).

2. **DOM-Sicherheit / innerHTML-Budget:**
   - `grep -c 'innerHTML' Symbiose_Dashboard.html` liefert exakt **51**.

3. **Pytest Test-Suite:**
   - **220 passed, 57 subtests passed** in 8.39s (inklusive der 4 neuen Hygiene- & Fail-Fast-Tests).

4. **Finale Release-Gate-Ausgabe (`scripts/release_check.py`):**
   - **EXIT=0**
   - **Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) · `synthetic-gate: PAPER_CANDIDATE` · `lockbox-eval: UNUSED`

5. **Ledger-Klassifikation:**
   - **Kategorie:** `PROCESS_FIX / INFRASTRUCTURE_HYGIENE` (Dockerfile Packaging, Relay Fail-Fast & Hygiene-Gates; keine Berührung von Signal-Scores, Sizing oder Indikator-Logik. Kette bleibt stabil bei `EXP-030` mit 10 Modell-Experimenten).
