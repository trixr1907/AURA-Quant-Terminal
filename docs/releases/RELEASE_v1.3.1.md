# AURA v1.3.1 — Confluence Terminal (read-only research)

Datum: 2026-09-13

## Inhalt

- **PF-18 (Feed-Index zurücksetzen):**
  - In `ws.onopen` wird `wsTry = 0` bei jedem erfolgreich geöffneten Feed zurückgesetzt.
  - Bitget bleibt nach jedem kontrollierten Reconnect die erste Wahl; Binance wird nur noch nach echten Bitget-Fehlern angesteuert.
- **PF-19 (Bitget-Keepalive):**
  - Solange eine Bitget-WS-Verbindung aktiv ist, wird alle 25s ein App-Level-Ping (`ws.send('ping')`) gesendet.
  - Verhindert serverseitige Timeouts nach 30s Inaktivität gemäß Bitget v2 WS-Spezifikation; Keepalive-Timer wird bei `onclose` und `onerror` sauber bereinigt.
- **PF-20 (Sticky-Socket: Symbolwechsel ohne Neuverbindung):**
  - Bei Symbol- und Timeframe-Wechseln mit bestehender, lebender Bitget-Verbindung wird auf derselben Verbindung umgesubscribed (`unsubscribe` alte args, `subscribe` neue) anstatt den Socket zu schließen.
  - Eliminiert Verbindungs-Churn bei der Coin-Auswahl im Dashboard vollständig.
- **PF-21 (Pill-Ehrlichkeit: Fallback-Zustand sichtbar):**
  - Die Feed-Status-Pill unterstützt einen dritten Zustand: Bei Quelle ≠ `bitget-ws` im Live-Modus wird die Pill gelb (`fallback`) mit dem Text `FALLBACK · <quelle> · vor <N>s` dargestellt.
  - Macht eventuelle Abweichungen durch Fallback-Kerzen im Dashboard sofort transparent sichtbar.
- **PF-22 (CVD feed-unabhängig):**
  - `cvdSeries` vereinheitlicht die Berechnung strikt auf die Pine-paritätsgeprüfte Range-Approximation $v \cdot \frac{2c - h - l}{h - l}$.
  - CVD, Delta und EMA(CVD) liefern identische Ergebnisse unabhängig von der Anwesenheit oder dem Wert des `tbv`-Feldes.
  - Golden-Master-Gate und Paritätsprüfungen bleiben unverändert grün; Ledger-Eintrag `EXP-031` (Prozess-Fix).
- **PF-23 (Automatisierte Tests & Verifikation):**
  - Erweiterter Reconnect- und Sticky-Socket-Test in `tests/test_bitget_websocket_reconnect.js`.
  - Neuer Test für den Keepalive-Timer-Lebenszyklus in `tests/test_bitget_keepalive.js`.
  - Neuer Test für die transparente Fallback-Pill-Darstellung in `tests/test_feed_status_fallback_pill.js`.
  - Neuer Test für die Feed-Invarianz der CVD-Berechnung in `tests/test_cvd_feed_independence.js`.
