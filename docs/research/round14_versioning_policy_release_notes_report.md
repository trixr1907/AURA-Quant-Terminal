# AURA — Abschlussbericht Runde 14: Footer-Wahrheit, Release-Notes & Versionierungs-Policy (v1.3.0)

**Datum:** 2026-09-12  
**Auditor:** Hermes Agent (Senior Quant Systems Auditor & Coding Agent)  
**Ausgangsversion:** v1.2.13  
**Zielversion:** v1.3.0 (MINOR Release gem. neuer SemVer-Policy)  
**Ledger-Status:** `EXP-030` (5 Einträge, Chain-Head `7a00e09a535da4327ab92ab1f69bb13814910d8128601812ab7f39d265f6a209`, 10 Modell-Experimente unverändert)  
**Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) · `synthetic-gate: PAPER_CANDIDATE` · `lockbox-eval: UNUSED`  

---

## 1. Übersicht & Zielerreichung

In dieser Runde wurden drei vom Eigentümer identifizierte Qualitätsmängel und eine strategische Policy-Anpassung umgesetzt:

1. **PF-14 (Footer-Wahrheit & Synchronisation):**
   - Die veraltete Footer-Versionsangabe (`AURA Confluence Terminal v1.2.10`) wurde auf `v1.3.0` aktualisiert.
   - `scripts/bump_version.py` wurde so erweitert, dass alle Versionsstellen im Dashboard (Signal Contract, Footer, Modal-Titel, Once-Call) und systemweit konsistent synchronisiert werden.
   - `scripts/release_check.py` prüft nun explizit den Footer-Tag (`<footer>...vX.Y.Z`).
   - Zusätzliche Hygiene-Tests in `tests/test_package_hygiene.py` verhindern künftige Desynchronisationen.

2. **PF-15 (Echte, datengetriebene Release-Notes):**
   - Datengetriebenes Release-Notes-Objekt `AURA_RELEASE_NOTES` im Dashboard mit Retrofüllung für v1.2.10, v1.2.11, v1.2.12, v1.2.13 und v1.3.0 eingeführt.
   - Sicheres DOM-Rendering via `replaceChildren()`, `createElement()` und `textContent` — der `innerHTML`-Zähler bleibt strikt bei **51**.
   - `showReleaseNotesOnce(version)` zeigt dynamisch die Highlights der aktuellen Version an und bietet einen interaktiven Aufklappbereich für frühere Versionen.
   - Bei unbekannten Versionen wird ein klarer Platzhalter angezeigt statt des alten statischen Marketing-Texts.
   - Vollständige Akzeptanz- und Lifecycle-Tests in `tests/test_release_notes_overlay.js` und `tests/test_package_hygiene.py`.

3. **PF-16 (Verbindliche Versionierungs-Policy):**
   - Semantic Versioning (`MAJOR.MINOR.PATCH`) in `README.md` fest verankert:
     - **MAJOR (x.0.0):** Breaking Changes, Architekturwechsel oder inkompatible Signal-Contracts.
     - **MINOR (1.x.0):** Feature- und Produkt-Runden (wie v1.2.11 rückblickend und v1.3.0 jetzt).
     - **PATCH (1.x.y):** Reine Bugfix- und Hygiene-Releases.

4. **PF-17 (Verifikation & Release v1.3.0):**
   - Vollständiger PR-, CI-, Merge- und Release-Zyklus autonom durchgeführt.

---

## 2. GitHub-API-Belege (Verifikationsnachweis)

### 2.1 Produkt Pull Request & Merge Commit
- **PR:** [#15 (fix(dashboard): synchronize footer version, introduce data-driven release notes, and document SemVer policy (v1.3.0))](https://github.com/trixr1907/AURA-Quant-Terminal/pull/15)
- **Merge-Methode:** Normaler Merge-Commit (`--merge`, kein Squash — exakt 2 Parents)
- **Produkt-Merge-Commit SHA:** `0aad4f449f7e2771d2cdfb9189f0b9f393e80776`
- **Merge-Parents (2 Parents nachgewiesen):**
  - Parent 1 (`main` vor PR #15): `492fa04963e0ccbab7c3e2c7080cdb197b048ea2`
  - Parent 2 (`fix/round14-versioning-policy-and-release-notes` HEAD): `f3a8afd95ef322e4a839713745fd9fc59272c2cd`

### 2.2 Annotierter Release-Tag
- **Tag:** `v1.3.0`
- **Tag-Objekt SHA:** `da6cdb69d6f02fe45fa38f16b11b15d0639f520c`
- **Tag-Peel SHA (`v1.3.0^{commit}`):** `0aad4f449f7e2771d2cdfb9189f0b9f393e80776`
- **Tag-Message:** `AURA v1.3.0 — Confluence Terminal (read-only research)`

### 2.3 GitHub Actions Check-Run Conclusions auf Merge Commit `0aad4f44`
- `SonarCloud Code Analysis`: status=`completed`, conclusion=`neutral`
- `Socket Security: Project Report`: status=`completed`, conclusion=`success`
- `publish`: status=`completed`, conclusion=`success`
- `Test Suite & Quality Gates`: status=`completed`, conclusion=`success`

### 2.4 GitHub Release Asset (`symbiose.zip`)
Das Asset wurde nach dem Upload via GitHub API heruntergeladen und unabhängig gehasht:
- **Download-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.3.0/symbiose.zip`
- **Asset-Dateigröße:** `228.346 Bytes`
- **SHA-256 (nach Upload heruntergeladen):**  
  `b9658440c17b577ecfeab72af7f6a16facf1bbc2c58f98a49ca8be17b77a5df4`
- **Dateianzahl im ZIP-Archiv:** `26 Dateien`
- **VERSION im ZIP-Archiv:** `1.3.0`
- **Enthaltene Pflichtdateien:** `LICENSE`, `RELEASE_v1.3.0.md`, `README.md`, `VERSION`, `Dockerfile`, `Symbiose_Dashboard.html`, `bitget_relay.py`.

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
   - **224 passed, 57 subtests passed** in 8.86s (Basis 220/57 + 4 neue Hygiene-Tests).

4. **Finale Release-Gate-Ausgabe (`scripts/release_check.py`):**
   - **EXIT=0**
   - **Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) · `synthetic-gate: PAPER_CANDIDATE` · `lockbox-eval: UNUSED`

5. **Ledger-Klassifikation:**
   - **Kategorie:** `PROCESS_FIX / UI_HYGIENE_POLICY` (UI-Konsistenz, datengetriebene Release-Notes und SemVer-Dokumentation; keine Berührung von Modell-, Sizing- oder Signal-Logik. Kette bleibt stabil bei `EXP-030` mit 10 Modell-Experimenten).
