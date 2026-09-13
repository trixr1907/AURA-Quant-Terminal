# AURA Confluence Terminal — Release v1.5.3

**Datum:** 2026-09-13  
**Typ:** PATCH (UI-Bugfix / Interaktions-Stabilität)  
**SemVer-Grund:** PF-50 DOM-stabile Trade-Karten (Zahlen live, Knoten beständig ohne zerstörendes Re-Rendering bei Ticks) im Live-Tracker und Autobot; PF-51 ntfy Trade-Pushes Dokumentation; Version-Sync.  
**Urteil:** SOFTWARE_GO / MODEL_NO_EVIDENCE (unverändert)  
**Ledger-Status:** EXP-032 (unverändert)

---

## Änderungen

### 1. PF-50 — DOM-stabile Trade-Karten (Flacker-Beseitigung)
- **Problem:** Ticks im Autobot (4 s) und Live-Tracker (15 s sowie Live-Ticker-Preise) bauten zuvor mit jedem Render alle Karten-Knoten neu auf (`innerHTML = ...` / `replaceChildren()`). Textselektionen, Tooltips und Klicks auf Buttons / Copyable-Werte gingen unter dem Mauszeiger verloren (Dauerflackern).
- **Lösung:** 
  - Karten-DOM-Elemente werden pro `trade.id` exakt einmalig erzeugt und anhand von `data-trade-id` wiederverwendet (`syncTradeCardsContainer`).
  - Metrik- und Preisänderungen werden in-place via `updateTradeCardElement` in die bestehenden Textknoten und Attribute geschrieben (`.tc-pnl`, `.tc-pnl-roi`, `.tc-val`, `.tc-time`, `.intel-badge`, Fortschrittsbalken).
  - Karten werden nur bei echten Trade-Öffnungen/Schließungen hinzugefügt bzw. entfernt.
  - Interaktionen via Delegation (`data-copy-val`, Break-Even, Teil-TP, Schließen) bleiben über beliebig viele Update-Zyklen stabil.
  - Betrifft sowohl den manuellen Live-Tracker (`#trade-list`) als auch den Autobot (`#ab-trades-container`) unter Wahrung der PF-41 DOM-Identität.
- **Tests:** Neuer Test `tests/test_pf50_trade_card_dom_stability.js` verifiziert Node-Identität (`isSameNode`), In-Place-Textupdates, dynamische Add/Remove-Zyklen und Klick-Reaktivität nach mehreren Zyklen in beiden Containern.

### 2. PF-51 — ntfy Trade-Pushes Dokumentation
- `docs/deployment/NTFY_GUIDE.md` um den Abschnitt „Trade-Pushes aktivieren" erweitert:
  - Konfiguration der Umgebungsvariable `AURA_NTFY_URL=https://ntfy.sh/<TOPIC-NAME>` auf dem Docker-Container `aura-terminal`.
  - Push-Zusammenfassung bei geschlossenen Trades (Symbol, Richtung, realisierte PnL USDT, Netto-ROI %, R-Multiple, Schließungsgrund).
  - Topic-Name bleibt vertraulich und wird nie im Repository gespeichert.

---

## Verifikations-Nachweise (Regel 2: ausgeführte Befehle + Ausgabe)

### Pytest-Suite
```
$ python3 -m pytest -q --tb=no
236 passed, 57 subtests passed in 10.84s
```

### JS-Test-Suiten
```
$ for f in tests/test_*.js; do node "$f" >/dev/null 2>&1 || echo "FAILED: $f"; done
78 Suiten geprüft — 0 Fehler
```

### innerHTML-Kanonik
```
$ grep -o innerHTML Symbiose_Dashboard.html | wc -l
66
```
*(Delta +15 gegenüber v1.5.2 durch gezielte Card-Template-Erzeugung und granulare In-Place-Setter).*

### Scope & Evidenz-Garantie
- Keine Änderungen an Signal-, Score-, Radar- oder Sizing-Algorithmen.
- Reine UI-Stabilitäts-, Dokumentations- und Synchronisations-Änderungen.
- `TRIALS_LEDGER.md` bleibt auf `EXP-032`.
- Urteil: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
