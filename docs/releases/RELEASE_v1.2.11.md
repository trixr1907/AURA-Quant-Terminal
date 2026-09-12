# AURA v1.2.11 — Confluence Terminal (read-only research)

Datum: 2026-09-12

## Inhalt

- **PF-1 (Bitget WebSocket Live-Feed primär):** Umstellung des Dashboard-Live-Candle-Streams von Binance auf Bitget Public WebSocket v2 (`wss://ws.bitget.com/v2/ws/public`, Topic `candle<TF>`) mit deterministischer Binance-Fallback-Kette und automatischem Reconnect.
- **PF-1 (CVD-Mathematik):** Bitget liefert kein Taker-Buy-Volumen; der deterministische Range-Approximationspfad (`v*(2c-h-l)/(h-l)`) sichert exakte Pine-Parität (0 Flips / 64.859 Bars).
- **PF-2 (Datenalter & Visibility-Resume):** Status-Pill `#feed-status-pill` (`LIVE · <Quelle> · vor <N>s`) und `visibilitychange`/`focus`-Handler zur verzögerungsfreien Aufholjagd nach Hintergrund-Drosselung.
- **PF-3 (Radar-Volumenfilter):** Display-Filter am Action-Radar (`Alle`, `≥ 500k`, `≥ 1M`, `≥ 5M`) mit dynamischen Live-Zählern und `localStorage`-Persistenz ohne Einfluss auf Scan-Gates.
- **PF-4 (Win-Rate-Semantik):** Erfassung von `PARTIAL_CLOSE`-Events bei TP1/TP2, tranchen-gewichtete realisierte Win-Rate (`realizedWinRatePct`) in `calculateHistoryStats` und fehlertolerante Legacy-Normalisierung.
- **PF-5 (Live-Tradepreis):** Explizite „Aktuell"-Spalte mit Marktpreis, farbcodiertem Entry-Delta (%) und visuellem Alter-Indikator bei Daten älter als 30 s.
- **PF-6 (Autobot-Zyklusstatus & Event-Log):** Transparenter Scan-Status (`Letzter Scan: vor <N>s`, geprüfte/qualifizierte Kandidaten, Abweisungsgründe) und integriertes In-Card Decision-Log.
- **PF-7 (TradingView-URL & schneller Relay-Fallback):** Bitget-Perpetual-URLs (`BITGET:<SYMBOL>.P`), 400 ms Abort-Timeout für Offline-Relays und visuelle Rückmeldung im UI.
- Versionierung, Build-Manifeste und Release-Prüfungen auf `1.2.11` synchronisiert.

## Integritätsurteil

`SOFTWARE_GO / MODEL_NO_EVIDENCE`

Die Änderungen verbessern die Produktqualität, UX und Feed-Zuverlässigkeit im täglichen Betrieb. Sie verändern weder Signallogik noch statistische Modelle.
