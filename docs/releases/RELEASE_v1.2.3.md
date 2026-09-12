# AURA v1.2.3 — Confluence Terminal Brand Identity & TradingView Visual Precision

## Überblick

AURA v1.2.3 etabliert das vollständige neue Erscheinungsbild als **AURA — Confluence Terminal** (`Quantitative Edge · Visual Precision · Pure Execution`), repariert die Rendering-Geometrie des **1:1 Pine Script Long/Short Position Drawing Tools**, aktualisiert das Repository auf **SOTA GitHub Designer-Niveau** und befreit das Release-Paket von Datenmüll.

---

## Highlights in v1.2.3

### 1. 🎨 Vollständiges Rebranding: AURA — Confluence Terminal
- **Laser-Gradient Vektor-Logo**: SVG-Brand-Asset mit geometrischem Rhombus-Kern (`assets/aura_logo.svg` und `assets/aura_logo_horizontal.svg`).
- **SOTA GitHub Readme**: Modernes Dark-Mode-Layout mit strukturierten Tabellen, Live-Visualisierungsbeispielen und sauberer Architektur-Dokumentation.
- **Konsistente Identität**: Dashboard-Header, SVG-Favicon, Tutorials, CLI-Banner und Start-Skripte sind nahtlos auf den neuen Namen und Claim synchronisiert.

### 2. 📊 TradingView Pine Script v6: 1:1 Long/Short Position Tool Fix
- **Kapazitäts-Upgrade**: `max_boxes_count=500`, `max_labels_count=500`, `max_lines_count=500` verhindern Zeichen-Buffer-Überläufe in TradingView.
- **Präzise Verankerung**: Dynamische `x1`-Berechnung verhindert horizontales Überdehnen über historische Kerzen und hält Preismarker im Sichtfeld.
- **Native Prognosen-Optik**: 1:1 Nachbildung der offiziellen TradingView Prognose-Werkzeuge mit grüner Gewinnzone (`#089981`), roter Verlustzone (`#f23645`), Einstiegslinie (`#787b86`), Ziel-Badges (TP2) und Stop-Loss-Markern.

### 3. 🧹 Lean Release Hygiene
- **Schlankes Endnutzer-Paket**: `symbiose.zip` enthält ausschließlich produktive Laufzeitdateien, Dokumentation und Assets (unter 250 KB).
- **Bereinigte Root-Struktur**: Veraltete Einmalberichte und Testdiagnostika wurden aus dem Root bereinigt.

---

## Verifikation
- Alle 176 `pytest` Tests bestanden.
- Alle Node.js Integrationsprüfungen (`test_tradingview_position_bridge.js`, `test_pine_forecast_generation.js`, `test_dirty_flag_rendering.js`) bestanden.
- Reines und deterministisches `scripts/release_check.py` Ergebnis: `SOFTWARE_PASS`.
