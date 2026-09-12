# AURA v1.2.8 — Path-aware Version Progression

## Überblick

AURA v1.2.8 repariert das SemVer-Progressions-Gate: Dokumentations- und Infrastrukturänderungen können nach einem Release wieder ohne erzwungenen Produkt-Release auf `main` gelangen. Änderungen an Produktcode, Tests, Abhängigkeiten und Build-Artefakten verlangen weiterhin einen Versionsbump.

## Änderungen

### Pfadbewusstes Versions-Gate

- `scripts/release_check.py` verwendet `git diff --name-only <tag>..HEAD` statt der reinen Commit-Anzahl.
- `.github/**`, `docs/**`, Markdown-Dateien und `LICENSE` sind release-neutral.
- Alle übrigen Pfade bleiben fail-closed und erzwingen bei unveränderter Version einen Bump.
- Die Remote-Tag-Auflösung über `git ls-remote` bleibt unverändert erhalten.

### Dokumentationskorrekturen

- Die drei CI-Reparatur-Commits `e4db4ec`, `fc2f683` und `69873e0` sind im Changelog von v1.2.7 nachgetragen.
- Die F-09-Zählung für `innerHTML` ist im Changelog von 49 auf den verifizierten Wert 51 korrigiert.

## Verifikation

- Regressionstests decken Docs-/Infrastruktur-Änderungen sowie blockierende Produktänderungen in beide Richtungen ab.
- Ein frischer Klon bestätigt: Docs-only bleibt grün; eine Änderung an `scripts/release_check.py` ohne Bump schlägt mit `version bump required for update` und Exit 2 fehl.
- Das vollständige Release-Gate wird vor Veröffentlichung ausgeführt.
