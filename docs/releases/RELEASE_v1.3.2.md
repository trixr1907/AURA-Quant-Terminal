# AURA v1.3.2 — Confluence Terminal (read-only research)

Datum: 2026-09-13

## Inhalt

- **PF-24 (Chart-Liveness über Bitget-Ticker-Kanal):**
  - Subskription des ~200ms Ticker-Streams (`channel: 'ticker'`) für kontinuierliche Live-Close-Updates laufender Kerzen auch bei illiquiden/ruhigen Symbolen.
  - Entkopplung des Chart-State-Keys: Live-Candle-Close löst sofortigen Redraw aus, statt auf den 4s-Reanalyse-Debounce zu warten.
  - Throttled Canvas-Redraw auf ~4 fps (max. 1 Redraw pro 250ms) via RAF zur Minimierung von Render-Overhead.
- **PF-25 (Adaptive Preisformate in Logs):**
  - Neue Hilfsfunktion `fmtPx(x)` formatiert Preise adaptiv mit 2, 6 oder 8 Dezimalstellen (Sub-Unit-Preise ab 0,01 bewusst mit 6 Stellen gemäß Eigentümerentscheidung).
  - Sub-Cent-Coins (z.B. ALCH bei 0,0428) werden in Autobot-Logs und Trade-Karten präzise dargestellt.
- **PF-26 (Log-Hygiene):**
  - Entfernung redundanter Stundenangaben im Time-Stop-Log (`16 Bars (16h)` statt `16 Bars (16h) (16h)`).
  - Formatierung von Uni-DSR mit `<0.01` bei Rundung auf Null und Tausendertrennung bei Trial-Zahlen (`56.664 Trials`).
  - Extraktion der reinen Log-Formatierungsfunktion `formatAutobotEntryLog`.
- **PF-27 (Tests & Verifikation):**
  - 57/57 Node.js-Test-Suiten PASS (3 neue Suiten: `test_chart_liveness_ticker.js`, `test_price_formatting.js`, `test_autobot_entry_log_hygiene.js`).
  - 224/57 Pytest-Tests PASS.
  - Ledger-Eintrag `EXP-032` registriert.
