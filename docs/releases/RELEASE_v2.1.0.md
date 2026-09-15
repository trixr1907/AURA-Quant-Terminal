# AURA v2.1.0 — UI Generation 2: Design System Final

## Zusammenfassung

AURA **v2.1.0 (MINOR)** finalisiert das in Runde 35a vorbereitete Design-System der zweiten Generation. Die visuelle Präsentation des Dashboards (`Symbiose_Dashboard.html`) wurde standardisiert, ohne auch nur ein Bit an der Datenhaltung (Schema v2), der Signalberechnung oder der Trading-Logik zu verändern.

---

## Kerninhalte

### 1. Zentraler CSS-Token-Katalog (`:root`)
- **Farben:** Basistöne, Panels (`--color-surface`, `--color-surface-raised`, `--color-surface-overlay`), Semantik (`--color-accent`, `--color-success`, `--color-warning`, `--color-danger`) und Text-Hierarchie (`--color-text`, `--color-text-muted`, `--color-text-dim`).
- **Typografie:** Nativer System-Font-Stack (`--font-sans`, `--font-mono`), modulare Schriftgrößenskala (`--text-xs` bis `--text-2xl`), definierte Zeilenabstände (`--leading-tight`, `--leading-normal`, `--leading-relaxed`).
- **4-px-Raster:** Konsistente Abstände über `--space-1` (4 px) bis `--space-8` (32 px).
- **Radien & Schatten:** Modulare Grenzradien (`--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-pill`) und Tiefenschatten (`--shadow-sm`, `--shadow-md`, `--shadow-lg`).
- **Z-Layering:** Feste Schichten von Content (`--z-content: 1`) über Sticky (`20`), Drawer (`60`), Banner (`9999`) bis zu kritischen Alerts (`99999`).

### 2. Komponentenverträge
- Einheitliche Klassen für Panel-Container (`.ui-card`, `.ui-panel`, `.panel`), Buttons (`.ui-button`, `.cbtn`, `button.act`), Badges (`.ui-badge`, `.badge`) und Tabellen (`.ui-table`, `table`).
- Tabellen-Layouts adaptieren bei <= 420 px automatisch in kompakte Zeilenkarten.

### 3. Mobile Viewports & Barrierefreiheit (WCAG AA)
- Durchgängige Touch-Ziele von mindestens 44 px (`--touch-target: 44px`) für alle interaktiven Kontrollen auf mobilen Viewports (390 px / 420 px).
- Text-Kontraste auf allen Oberflächen übertreffen WCAG AA (Text >= 6.8:1, Primärtext 17.8:1).
- Globale `:focus-visible`-Tastaturfokusringe (2-px-Ring in Akzentfarbe mit Sanftschatten).
- Respektierung von `prefers-reduced-motion: reduce`.
- Tabellarische Ziffern (`tabular-nums`) auf allen Finanzdaten.

### 4. Self-Contained Garantie & XSS-Kanon
- **Keine externen Ressourcen:** 0 externe Stylesheets, Google Fonts, CDNs oder Bild-URLs.
- **`innerHTML`-Kanon:** Exakt **63 -> 63** Stellen im Dashboard.

---

## Evidenzkette & Quant-Schutz

| Prüffeld | Status v2.0.0 | Status v2.1.0 | Befund |
|---|---|---|---|
| Trials Ledger | EXP-032 / Chain-Head `ac613227...` | EXP-032 / Chain-Head `ac613227...` | Bytegenau identisch |
| Lockbox Registry | UNUSED | UNUSED | Unberührt |
| Release Verdict | `SOFTWARE_GO / MODEL_NO_EVIDENCE` | `SOFTWARE_GO / MODEL_NO_EVIDENCE` | Unverändert |
| Schema Version | `schema_version: 2` | `schema_version: 2` | Unverändert |
| innerHTML Sinks | 63 | 63 | 0 neue Senken |
| Trading Gates / Sizing | Bit-identisch | Bit-identisch | Zero Drift |
| Packaging Closure | 100% Manifest / Docker | 100% Manifest / Docker | Grün |
