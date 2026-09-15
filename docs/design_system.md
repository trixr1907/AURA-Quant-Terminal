# AURA Design System Gen 2 (v2.1.0)

AURA v2.1.0 finalisiert das visuelle Design-System des vollständig self-contained Quant-Terminals (`Symbiose_Dashboard.html`). Das System vereinheitlicht Farbkontraste, Typografie, Spacing-Raster, Komponentenklassen und Mobil-Viewports ohne jegliche Änderung an der Datenhaltung (Schema v2), der Signalberechnung oder der Trading-Logik.

---

## 1. Design-Prinzipien

1. **Self-Contained & Offline-First:** Keine externen CDNs, Google Fonts, Remote-Stylesheets oder externen Bilder. Alle Schriftarten und Icons basieren auf nativen System-Font-Stacks und Inline-SVGs bzw. Data-URIs.
2. **Funktionale Farbkodierung:** Zustands- und Signal-Farben (Cyan, Teal, Amber, Rose/Coral, Violett) transportieren quantitative Information konsistent und sind textlich redundanzgesichert.
3. **Striktes 4-px-Raster:** Alle Abstände, Polsterungen und Layout-Margen leiten sich aus `--space-1` (4 px) bis `--space-8` (32 px) ab.
4. **Mobile First & Touch-Friendly:** Vollständige Bedienbarkeit ab Viewports <= 420 px (Android) und 390 px (iPhone 12/13/14/15/16). Alle interaktiven Touch-Ziele besitzen eine Mindesthöhe von mindestens 44 px (`--touch-target: 44px`).
5. **Barrierefreiheit (WCAG AA):** Kontraste >= 4.5:1 für Text und >= 3:1 für grafische UI-Komponenten auf allen Hintergründen, globale `:focus-visible`-Tastaturfokusringe, `prefers-reduced-motion`-Unterstützung und `tabular-nums` für numerische Präzision.
6. **innerHTML-Kanon:** Fester Grenzwert von **63** innerHTML-Senken im Dashboard zur Sicherung der XSS-Angriffsfläche und DOM-Stabilität.

---

## 2. Token-Katalog (`:root`)

### 2.1 Farb-Tokens

| Token | Wert | Verwendungszweck | Kontrast zu `--color-base` | Kontrast zu `--color-surface` |
|---|---|---|---|---|
| `--color-base` | `#06090f` | Globaler Terminal-Hintergrund | — | — |
| `--color-surface` | `#0b111b` | Standard Panel-Fläche | — | — |
| `--color-surface-raised` | `#101826` | Erhöhte Karten, Headers, Toolbars | — | — |
| `--color-surface-overlay` | `#141f30` | Modals, Drawers, Dropdowns | — | — |
| `--color-accent` | `#38bdf8` | Primärer Aktions- & Fokus-Farbton (Sky/Cyan) | 8.9:1 (AAA) | 8.2:1 (AAA) |
| `--color-accent-hover` | `#7dd3fc` | Hover-Status für Akzente | 11.8:1 (AAA) | 10.9:1 (AAA) |
| `--color-accent-muted` | `rgba(56,189,248,.15)` | Sanfter Hintergrund für Akzent-Chips | — | — |
| `--color-success` | `#2dd4bf` | Gewinn, Long, Signal GO, WebSocket live | 10.2:1 (AAA) | 9.4:1 (AAA) |
| `--color-success-hover` | `#5eead4` | Hover & Highlights für positive Zustände | 13.5:1 (AAA) | 12.5:1 (AAA) |
| `--color-warning` | `#fbbf24` | Warte-Status, Time-Stop, Fallback-Feed | 11.9:1 (AAA) | 10.9:1 (AAA) |
| `--color-danger` | `#fb7185` | Verlust, Short, Veto, Fehler, Disconnect | 7.1:1 (AAA) | 6.5:1 (AAA) |
| `--color-danger-hover` | `#fda4af` | Hover für Risiko-Aktionen | 10.4:1 (AAA) | 9.6:1 (AAA) |
| `--color-text` | `#f1f5f9` | Primärer Lesetext & Zahlen | 17.8:1 (AAA) | 16.5:1 (AAA) |
| `--color-text-muted` | `#cbd5e1` | Sekundärer Text & Tabellen-Headers | 12.7:1 (AAA) | 11.7:1 (AAA) |
| `--color-text-dim` | `#94a3b8` | Labels, Metadaten, Einheiten, Zeitstempel | 7.4:1 (AAA) | 6.8:1 (AAA) |
| `--color-border` | `rgba(148,163,184,.14)` | Subtile Panel- und Tabellengrenzen | — | — |
| `--color-border-strong` | `rgba(148,163,184,.24)` | Aktive Trennlinien und Kontroll-Borders | — | — |

### 2.2 Typografie-Tokens

- **`--font-sans`:** `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
- **`--font-mono`:** `"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace`
- **Größen:**
  - `--text-xs`: `9px` (Labels, Micro-Pills)
  - `--text-sm`: `10px` (Headers, Badges, Tabellen-Text)
  - `--text-md`: `13px` (Body-Text, Eingaben)
  - `--text-lg`: `16px` (Subheadings, KPI-Zahlen)
  - `--text-xl`: `24px` (Hero-Badges, Großmetriken)
  - `--text-2xl`: `34px` (Haupt-Coin & Signal-Headline)
- **Zeilenhöhen:**
  - `--leading-tight`: `1.1`
  - `--leading-normal`: `1.45`
  - `--leading-relaxed`: `1.6`

### 2.3 Spacing-Raster (4-px-Basis)

- `--space-1`: `4px`
- `--space-2`: `8px`
- `--space-3`: `12px`
- `--space-4`: `16px`
- `--space-5`: `20px`
- `--space-6`: `24px`
- `--space-7`: `28px`
- `--space-8`: `32px`

### 2.4 Radien & Schatten

- `--radius-sm`: `6px` (Buttons, Inputs, Chips)
- `--radius-md`: `10px` (Subpanels, Toolbars)
- `--radius-lg`: `14px` (Hauptpanels, Karten)
- `--radius-pill`: `999px` (Status-Badges, Tags)
- `--shadow-sm`: `0 4px 20px rgba(0, 0, 0, .18)`
- `--shadow-md`: `0 18px 50px rgba(0, 0, 0, .28)`
- `--shadow-lg`: `0 24px 70px rgba(0, 0, 0, .45)`

### 2.5 Z-Index Layering

- `--z-base`: `0`
- `--z-content`: `1`
- `--z-sticky`: `20` (Sticky Headers & Bars)
- `--z-launcher`: `45` (Radar-Seitenreiter)
- `--z-backdrop`: `50` (Modal- & Drawer-Backdrops)
- `--z-drawer`: `60` (Radar-Drawer)
- `--z-toast`: `100` (Kopier- und Hinweis-Toasts)
- `--z-banner`: `9999` (Globale Version-Reload-Banner)
- `--z-critical`: `99999` (Sicherheits- und Vollbildhinweise)

---

## 3. Komponentenklassen

- **Panels & Karten:** `.panel`, `.ui-card`, `.ui-panel`, `.trade-card`, `.history-card`, `.tv-basic-panel`, `.autobot-panel`
- **Buttons:** `.cbtn`, `.act`, `.tc-btn`, `.ab-toggle-btn`, `.hero-paper-btn`, `.copy-intel-btn`, `.hero-tv-btn`, `.draw-tool-btn`, `.ui-button`
- **Badges & Indikatoren:** `.badge`, `.ui-badge`, `.feed-status-pill`, `.autobot-status-badge`, `.hero-dir-badge`, `.hero-score-chip`, `.hero-when-chip`, `.hero-kelly-chip`, `.tv-basic-badge`
- **Tabellen:** `table`, `.ui-table`, `.btbl` mit automatischer Transformation in Zeilenkarten auf kleinen Viewports
- **Formulare:** `select`, `input[type=text]`, `input[type=number]`, `input[type=range]` mit standardisierten Fokus- und Hover-Zuständen

---

## 4. Responsive & Mobile Viewports

- **<= 960 px (Tablet):** Vertikales Wrapping von Header und Controls; 1-spaltige Anordnung der Signal-Analyse-Flows.
- **<= 620 px (Kompakt):** Reduktion von Sekundär-Status-Badges, 2-spaltige KPI-Karten, mobile Radar-Schaltfläche.
- **<= 420 px (Mobile Standard):**
  - Alle interaktiven Elemente (Buttons, Inputs, Selects, Drawer-Schließer, Filter) halten mindestens `min-height: 44px`.
  - Backtest- und Trade-Tabellen blenden Tabellenköpfe aus und rendern Zeilen als geschachtelte Karten.
- **<= 390 px (iPhone Viewport):**
  - Skalierung der Hero-Coin-Schriftgröße auf 24 px; 1-spaltige Level- und Hero-Inner-Layouts zur Vermeidung jeglichen horizontalen Scrollens.

---

## 5. Barrierefreiheit & Invarianten

- **Fokus-Indikatoren:** `:where(button, a, input, select, summary, [tabindex]):focus-visible` zeichnet einen 2-px-Ring in Akzentfarbe mit 4-px-Sanftschatten.
- **Reduzierte Bewegung:** `@media (prefers-reduced-motion: reduce)` schaltet alle CSS-Transitionen und Animationen ab.
- **Zahlenkonsistenz:** Tabellarische Ziffern (`font-variant-numeric: tabular-nums`) für alle Finanzdaten, PnL-Werte, Stop-Loss-Level und Zeitstempel.
- **Evidenzschutz:** `Symbiose_Dashboard.html` enthält exakt **63** `innerHTML`-Stellen. Es wurden keine neuen dynamischen HTML-Senken hinzugefügt.
