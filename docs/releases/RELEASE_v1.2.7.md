# AURA v1.2.7 — CI Reproducibility & Dependency Pinning

## Überblick

AURA v1.2.7 liefert die deterministische Absicherung der Continuous-Integration- und Release-Pipelines durch striktes Pinning aller Test- und Laufzeitabhängigkeiten sowie Bereinigung der GitHub Actions Workflows.

---

## Highlights in v1.2.7

### 1. 📦 Deterministisches Pytest-Pinning (K7)
* **Explizites Pinning in `requirements.txt`:** `pytest==9.1.1` wurde direkt in das Release-Manifest aufgenommen.
* **Beseitigung von Ad-hoc-Installationen:** Entfernung unversionierter `pip install ... pytest`-Aufrufe aus `.github/workflows/ci.yml` und `.github/workflows/publish-release.yml`.
* **Reproduzierbare CI:** Build- und Testläufe sind vollständig immun gegen Breaking Changes künftiger PyPI-Releases.

### 2. ⚙️ CI- & Release-Workflow-Harmonisierung
* **Python 3.12 Laufzeit-Standardisierung:** `publish-release.yml` verwendet konsistent die gepinnte Python 3.12-Runtime analog zu `ci.yml`.
* **SemVer-Progression & Release-Gating:** Konsistente Überprüfung der Versionsprogression über Branch- und Tag-Workflows.

---

## Verifikationsstatus
- `pytest` Suite: **193 Tests bestanden, 57 Subtests bestanden**.
- Standalone JS Suites: **42/42 Testsuiten bestanden**.
- `scripts/release_check.py`: **SOFTWARE_GO / MODEL_NO_EVIDENCE** (Exit 0).
