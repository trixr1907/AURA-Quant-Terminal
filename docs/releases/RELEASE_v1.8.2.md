# AURA v1.8.2 — Ehrliches Ready & Live-Ausführungspreis

**Release-Typ:** PATCH (`1.8.2`, Betriebswahrheit und Paper-Ausführungskorrektur)
**Datum:** 2026-09-14
**Research-Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`
**Trials-Ledger:** unverändert `EXP-032`

## Überblick

AURA v1.8.2 beseitigt zwei produktionsrelevante Täuschungen: Ohne `AURA_BOT_MODE` kann `/ready` keinen alten Runner mehr als lebendig darstellen, und neue Paper-Trades verwenden nicht länger den bis zu eine Kerze alten Signal-Schlusskurs als simulierten Ausführungspreis.

## Behoben

- `/ready.runner` folgt ausschließlich der aktuellen Container-ENV. Ohne Server-Modus: `mode: "none"`, `bot_enabled: false`, `running: false`, `state: "not_configured"`; keine historischen Staleness-, Zyklus-, Trade- oder Equity-Werte.
- Persistente Bot-Historie ohne `AURA_BOT_MODE` erzeugt beim Relay-Start einen lauten ERROR. Ist `AURA_NTFY_URL` konfiguriert, erfolgt ein einmaliger P3-Warnversuch; andernfalls folgt ein zweiter ERROR mit Guide-Hinweis.
- Browser- und Headless-Paper-Autobot trennen Signal und Ausführung: Modell/Gates bleiben auf geschlossenen Kerzen, Entry/Mark/SL/TP/Risiko verwenden den unmittelbar zuvor abgerufenen Live-Ticker.
- Logs und Open-Pushes zeigen Entry, Signalpreis und prozentuale Differenz.
- Tickerfehler fallen mit WARN auf den Signal-Kerzenschluss zurück.
- Überalterte Signalfeeds werden vor dem Entry bei mehr als `1,5 × Kerzendauer` als `STALE_CANDLE` abgelehnt.

## Betrieb

Der Server-Bot-Guide enthält eine Pflicht-Checkliste für manuelle Container-Ersetzungen: kanonische gehärtete Container-Spec inklusive `--env-file /var/lib/aura/aura_bot.env`, bevorzugter Receiver-/Redeliver- beziehungsweise `scripts/ops/enable_server_bot.sh`-Pfad sowie ein direkter `/ready`- und `cycle_count`-Check.

## Scope und Grenzen

- Keine Änderung an Richtung, Score, Regime, ADX, Squeeze, OOS/DSR oder Universe-Gates.
- Weiterhin reine Paper-Simulation ohne private Order-Bridge.
- Ein erfolgreiches Software-/CI-Gate ist kein Nachweis eines profitablen Modells.
- Produktiv-Deploy und Push-Zustellung gelten nur mit separatem VM-Beleg und echter ntfy-Nachrichten-ID als verifiziert.
