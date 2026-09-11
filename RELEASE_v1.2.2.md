# AURA v1.2.2 — TradingView Long/Short Position Tool & Robuste Desktop-Umschaltung

## Überblick

AURA v1.2.2 liefert eine vollständige und detailgetreue Nachbildung des **TradingView Long & Short Position Drawing Tools (Solutions 43000517002 & 43000516992)** in Pine Script v6, behebt das **Origin-Routing der Windows TradingView Desktop-App** und garantiert eine verlässliche Chart-Umschaltung ohne Browser-Umwege.

---

## Highlights in v1.2.2

### 1. 📊 1:1 TradingView Long/Short Position Drawing Tool (v6)
* **Offizielle TradingView-Nachbildung:** Entspricht exakt den Support-Spezifikationen für das Long- und Short-Positions-Zeichenwerkzeug (`43000517002` & `43000516992`).
* **Grüne Gewinn-Zone & Rote Verlust-Zone:** Zeichnet native Gewinnboxen (`#089981`, 80% Deckung) und Verlustboxen (`#f23645`, 80% Deckung) mit klaren Begrenzungslinien und Zwischenzielen (TP1 +1.5R, TP2 +3.0R, TP3 +5.0R).
* **Live-Statistik-Badge:** Zeigt R:R-Verhältnis (z. B. `1 : 2.50`), Kontogröße ($1.000,00), Risiko (5.0%), Positionsmenge, Hebel (10x), Notional und Margin direkt am rechten Chartrand.
* **Permanente Sichtbarkeit:** Das Tool bleibt auf historischen Balken, aktiven Signalen und neuen Assets persistent sichtbar und hat keinen leeren State mehr.
* **1-Klick-Synchronisation:** In den Autobot-Trade-Karten schaltet der Button **`📊 In TV visualisieren`** direkt auf den Bitget-Perpetual-Chart um und kopiert die exakten Levels in die Zwischenablage.

### 2. 🖥️ Robuste Desktop-Umschaltung ohne Browser-Tabs
* **Loopback-Origin-Freigabe:** Der lokale Relay-Server erlaubt ab sofort Anfragen von `localhost`, `127.0.0.1` und lokalen Dateiursprüngen (`null`) für `/api/open-tradingview`.
* **Keine 403-Fehler & kein doppelter Browser-Tab mehr:** Die Umschaltung erfolgt direkt an die Windows-Store-/Desktop-App `TradingView.exe`.
* **Präzises Bitget-Symbolrouting:** Unterstützt alle 488 Bitget USDT-M Perpetuals (`BITGET:<SYMBOL>.P`).

### 3. 🛡️ Einsteigerfreundliche Standardwerte & Transparenz
* **Standard-Konto:** `1.000 USDT`
* **Standard-Risiko:** `5.0%`
* **Standard-Hebel:** `10x`
* **24h-Mindestvolumen:** `500.000 $` (aktiviert rentable Altcoins, filtert Schrottcoins)
* **OOS-Trades & DSR:** `8` Mindesttrades, DSR `0.10` mit klaren Erklärungen im Autobot-Konfigurationspanel.

---

## Verifikation & Release-Status

* **Pytest-Suite:** 175 Tests PASSED.
* **Node.js-Integrationsprüfungen:** 28 Testdateien PASSED.
* **Pine Script v6 Static Check:** 100% konform (995 Zeilen, 0 Syntaxfehler).
* **Release-Check:** `SOFTWARE_GO` (100% bestanden).
