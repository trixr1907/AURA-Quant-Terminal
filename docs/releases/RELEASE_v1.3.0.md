# AURA v1.3.0 — Confluence Terminal (read-only research)

Datum: 2026-09-12

## Inhalt

- **PF-14 (Footer-Wahrheit & Synchronisation):**
  - Footer in `Symbiose_Dashboard.html` auf die korrekte Release-Version `v1.3.0` aktualisiert.
  - `scripts/bump_version.py` so erweitert, dass alle Versionsstellen im Dashboard (Signal Contract, Footer, Modal-Titel, Once-Call) und systemweit konsistent synchronisiert werden.
  - Dedizierte Hygiene-Tests in `tests/test_package_hygiene.py` sichern die Parität zwischen `VERSION`-Datei, Footer, Modal und allen Projektkomponenten ab.
- **PF-15 (Echte, datengetriebene Release-Notes):**
  - Datengetriebenes Release-Notes-Objekt `AURA_RELEASE_NOTES` im Dashboard mit Highlights für v1.3.0, v1.2.13, v1.2.12, v1.2.11 und v1.2.10 integriert.
  - Sicheres Rendering über native DOM-APIs (`replaceChildren`, `createElement`, `textContent`) unter Einhaltung des strikten Budgets von 51 innerHTML-Stellen.
  - `showReleaseNotesOnce(version)` zeigt nun dynamisch die Notizen der aktuellen Version mit optionalem Aufklappbereich für ältere Versionen.
  - Node.js- und Python-Hygiene-Tests verifizieren Datenintegrität und Fallback-Verhalten bei unbekannten Versionen.
- **PF-16 (Versionierungs-Policy):**
  - Semantic-Versioning-Policy in `README.md` verbindlich dokumentiert: MAJOR = Breaking, MINOR = Feature-/Produkt-Runden (wie v1.3.0), PATCH = Bugfixes.
