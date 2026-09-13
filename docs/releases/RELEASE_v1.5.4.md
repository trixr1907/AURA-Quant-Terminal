# AURA Confluence Terminal — Release v1.5.4

**Datum:** 2026-09-13  
**Typ:** PATCH (UI/UX-Parität, Setup-Fallbacks, Timeframe-Links & Layout-Stabilität)  
**SemVer-Grund:** PF-53 Manuelle Trade-Karte auf Autobot-Niveau (fmtP, Multi-TP, 5s REST-Intervall), PF-54 Setup-Validation ohne stille Fallbacks, PF-55 TradingView-Links mit Timeframe, PF-56 Autobot Layout-Stabilität, PF-57 Autobot Intel-Block; Version-Sync auf v1.5.4.  
**Urteil:** SOFTWARE_GO / MODEL_NO_EVIDENCE (unverändert)  
**Ledger-Status:** EXP-032 (unverändert)

---

## Änderungen

### 1. PF-53 — Manuelle Trade-Karte auf Autobot-Niveau
- **Adaptive Preisformatierung:** Alle Preis-Level-Felder im manuellen Pfad (`entryDisplay`, `priceDisplay`, `slDisplay`, `tpDisplay`, `tp1Display`, `tp2Display`, `tp3Display`, `mfeDisplay`, `maeDisplay`) nutzen nun `fmtP`/`fmtPx` (identisch zum Autobot-Pfad). USDT-Werte (Margin, Notional, Risk) bleiben standardisiert 2-stellig.
- **Multi-TP-Unterstützung:** `tp2Display` und `tp3Display` werden im Manual-Aufruf übergeben und in der Karte sauber gerendert.
- **In-Place Updates:** `updateTradeCardElement` aktualisiert alle dynamischen Grid-Werte, Range-Labels und Mark-Alter direkt im DOM ohne Karten-Rebuild.
- **Preisfrische:** Das REST-Refresh-Intervall für offene Nicht-Fokus-Positionen wurde von 15 s auf **5 s** verkürzt.

### 2. PF-54 — Paper-Trade-Übernahme aus Setup-Validation ohne stille Fallbacks
- `startPaperTradeFromCockpit` übernimmt Entry, SL, TP1, TP2, TP3, Hebel und Time-Stop exakt aus dem validierten Setup (`App.data.live`).
- Greifen Heuristik-Fallbacks (z.B. fehlende Setup-Level), wird das Trade-Objekt mit `fallbackSl: true` und der Begründung `"Fallback-SL (ATR), Setup-Level fehlten"` markiert und in der Karte/Intel-Zeile transparent ausgewiesen — keine stillen Ersatzwerte.

### 3. PF-55 — TradingView-Links überall MIT Timeframe
- `buildTradingViewChartUrl(symbol, tf)` delegiert an `buildTradingViewUrl(symbol, tf)` unter Nutzung von `mapTradingViewInterval` (15m → 15, 1h → 60, 4h → 240, 1d → D).
- Alle Einstiegspunkte (Trade-Karten, Hero-Buttons, Chart-Panel) übergeben den aktiven Timeframe (`App.chartTF` bei manuellen Trades, `t.signalTf` bei Autobot-Trades).

### 4. PF-56 — Layout-Stabilität im Autobot-Panel
- `font-variant-numeric: tabular-nums` auf `.trade-card`, `.tc-pnl`, `.tc-grid`, `.tc-item b` und `.tc-track-labels` angewendet, um Ziffernbreiten-Jitter zu eliminieren.
- Feste/reservierte Breiten und `box-sizing: border-box` mit `max-width: 100%` verhindern Overflow im mobilen Viewport (390 px Viewport im Browser-Harness verifiziert).
- `@media(prefers-reduced-motion: reduce)` wird für alle Kartenanimationen respektiert.

### 5. PF-57 — Intel-Block (Phase/SMC/BTC-Trend) für Autobot-Karten
- Die Intel-Logik wurde in `buildTradeIntelAssessment(t, m, px, side, isAutobot)` vereinheitlicht.
- Autobot-Karten rendern dieselbe taktische Intel-Zeile (Taktische Phase, SMC UTC-Session, BTC-Trend-Confluence, Ziel-TPs).

---

## Verifikations-Nachweise (Regel 2: ausgeführte Befehle + Ausgabe)

### Pytest-Suite
```
$ python3 -m pytest -q --tb=no
236 passed, 57 subtests passed in 11.07s
```

### JS-Test-Suiten (Kanonischer Loop)
```
$ for f in tests/test_*.js; do node "$f" >/dev/null 2>&1 || echo "FAILED: $f"; done
79 Suiten ausgeführt — 0 Fehler
```

### Neue Test-Suite
```
$ node tests/test_pf53_pf57_card_and_link_improvements.js
=== TEST: PF-53 .. PF-57 CARDS, FALLBACKS, TV LINKS & AUTOBOT INTEL ===
  PASS PF-55: TradingView URLs contain expected interval parameters
  PASS PF-54: Setup validation records explicit fallback reason without silent replacement
  PASS PF-53/PF-57: Full Intel assessment (SMC/BTC/Phases) and Multi-TP support in cards
  PASS PF-56: Layout stability CSS and prefers-reduced-motion verified

============================================================
ERGEBNIS: PF-53..PF-57 VERIFICATION ALL CHECKS PASSED
============================================================
```

### innerHTML-Kanonik
```
$ grep -o innerHTML Symbiose_Dashboard.html | wc -l
66
```

### Scope & Evidenz-Garantie
- Keine Änderungen an Signal-, Score-, Radar- oder Sizing-Algorithmen.
- Reine UI/UX-Paritäts-, Fallback-Transparenz- und Layout-Stabilitäts-Änderungen.
- `TRIALS_LEDGER.md` bleibt auf `EXP-032`.
- Urteil: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
