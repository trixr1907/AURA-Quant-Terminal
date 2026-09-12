# AURA v1.2.13 — Confluence Terminal (read-only research)

Datum: 2026-09-12

## Inhalt

- **PF-11 (Dockerfile: VERSION ins Image):**
  - `COPY --chown=aura:aura VERSION .` im Copy-Block von `Dockerfile` fest verankert, damit `/app/VERSION` in jedem gebauten Docker-Image existiert.
- **PF-12 (Relay Fail-Fast & Dynamic Versioning):**
  - `bitget_relay.py` lädt die Version strikt dynamisch aus `VERSION` und beendet den Prozess mit `RuntimeError` (Fail-Closed), falls `VERSION` im Deployment fehlt.
  - Veraltete, hartcodierte Fallback-Versionsnummern (`else "1.2.10"`) wurden restlos entfernt.
- **PF-13 (Regressionsschutz & Runbook-Erweiterung):**
  - Automatisierte Hygiene- und Konsistenztests in `tests/test_package_hygiene.py` verhindern künftige Regressionen (Dockerfile-Copy-Prüfung, Regex-Prüfung auf harte Fallbacks, Version-Match-Assertion und Fail-Fast-Test).
  - Deployment-Runbook um Post-Start-Verifikation von `/serving` gegen den Ziel-Tag erweitert.
