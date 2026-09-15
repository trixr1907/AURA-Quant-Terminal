# AURA Design System Gen 2

AURA v2.0.0 konsolidiert die visuelle Sprache des vollständig self-contained Dashboards. Die Darstellung wurde vereinheitlicht, ohne Daten, Panel-Funktionen oder Trading-Logik zu verändern.

## Prinzipien

- Self-contained: keine Webfonts, CDNs oder externen Bild-/CSS-Ressourcen.
- Funktion vor Dekoration: Zustandsfarben sind konsistent und textlich ergänzt.
- 4-px-Raster: Abstände werden über `--space-1` bis `--space-6` skaliert.
- Mobil ab 420 px: Touch-Ziele mindestens 44 px; Tabellen werden zu lesbaren Zeilenkarten.
- Barrierearm: WCAG-AA-fähige Textfarben, globale `:focus-visible`-Ringe und `prefers-reduced-motion`.

## Token-Katalog

### Farben

| Token | Zweck |
|---|---|
| `--color-base` | Seitenhintergrund |
| `--color-surface`, `--color-surface-raised`, `--color-surface-overlay` | Panel-Ebenen |
| `--color-accent` | Interaktion und Fokus |
| `--color-success` | positiver/gesunder Zustand |
| `--color-warning` | Warnung/abwarten |
| `--color-danger` | Fehler/Risiko |
| `--color-text`, `--color-text-muted`, `--color-text-dim` | Text-Hierarchie |

### Typografie

- `--font-sans`, `--font-mono`: lokale System-Font-Stacks.
- `--text-xs` bis `--text-2xl`: abgestufte Textgrößen.

### Layout

- `--space-1` bis `--space-6`: 4, 8, 12, 16, 20 und 24 px.
- `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-pill`.
- `--shadow-sm`, `--shadow-md`.
- `--z-content`, `--z-sticky`, `--z-drawer`, `--z-toast`, `--z-critical`.
- `--breakpoint-mobile: 420px`, `--breakpoint-tablet: 960px` (Dokumentations-Tokens; CSS-Media-Queries verwenden die entsprechenden statischen Werte).
- `--touch-target: 44px`.

## Komponentenverträge

- `.ui-card` / `.panel`: gemeinsame Fläche, Radius und Schatten.
- `.ui-button` / `.cbtn` / `button.act`: gemeinsame Mindesthöhe und Radius.
- `.ui-badge` / `.badge`: pill-förmiger Statusindikator.
- `.trade-card`, `.history-card`: responsive Trade-/Historienzeilen.

Die bestehenden Klassen bleiben absichtlich erhalten, damit DOM-Verträge und die vollständige JS-Testsuite unverändert weiterarbeiten.
