# AURA v1.2.1 — Pine Trade Forecasting, TV-Desktop-Direktumschaltung & Einsteiger-Transparenz

## Überblick

AURA v1.2.1 bringt ein interaktives **Trade-Forecasting-Overlay in Pine Script v6**, optimierte und realistische **Default-Parameter (1.000 USDT Startkapital, 5% Risiko, 10x Hebel, 500k $ 24h-Mindestvolumen)**, maximale **Transparenz mit Einsteiger-Schnellguide** im Autobot-Konfigurationspanel und eine **zuverlässige direkte TradingView-Desktop-Integration** ohne doppelte Web-Browser-Tabs.

---

## Neu in v1.2.1

### 1. 📊 1:1 TradingView Long/Short Position Tool & Trade Forecasting (v6)
* **1:1 TradingView Position-Tool (Solutions 43000517002 & 43000516992):** In `Symbiose_Signal_System_v1.pine` wurde das native TradingView Long & Short Position Drawing Tool vollständig nachgebildet.
* **Exakte Preislevels & R:R-Boxen:** Zeichnet dynamisch Entry (Grau/Cyan), Stop-Loss (Rot), TP1 (+1.5R Hellgrün), TP2 (+3.0R Grün) und TP3 (+5.0R Smaragdgrün) sowie halbtransparente Gewinn- (`#089981`) und Verlustzonen (`#f23645`) in den Chart.
* **Live-Statistik-Badge:** Informatives TradingView-Positions-Badge mit Kontogröße, Risiko ($ und %), Hebel (10x), Notional, Margin und exaktem Chance-Risiko-Verhältnis (R:R).
* **Universelle Persistenz:** Zeigt auch auf historischen Candles oder neuen Charts sofort die passenden Levels und bleibt niemals unsichtbar.
* **1-Klick-Visualisierung:** Jede aktive Autobot-Position verfügt über den Button `📊 In TV visualisieren`. Ein Klick schaltet TradingView auf das Asset um und kopiert den maßgeschneiderten Pine-Script-Code mit den konkreten Entry-, SL- und TP-Werten in die Zwischenablage.

### 2. 🛡️ Verbesserte, praxistaugliche Defaultwerte
* **Header-Konto:** Standardmäßig auf `1.000 USDT` gesetzt (vorher 10.000).
* **Header-Risiko:** Standardmäßig auf `5.0%` gesetzt (vorher 1.0%).
* **Autobot-Startkapital:** `1.000 USDT` synchronisiert mit dem Terminal.
* **Autobot-Risiko:** `5.0%` mit dynamischer Margin-Berechnung nach Stop-Loss-Distanz.
* **Maximaler Hebel:** `10x` als solider Standard für Krypto-Futures weit vor der Liquidation.
* **24h-Mindestvolumen:** `500.000 $` (vorher 2.000.000 $). Filtert marktfeine Schrottcoins heraus, lässt aber profitable und liquide Altcoins durch den Funnel.
* **OOS-Historientests:** `8` Mindesttrades als gesunder statistischer Evidenzwert.
* **Setup-DSR (Zufallsschutz):** `0.10` für robusten Schutz gegen Overfitting bei aktiver Signalgenerierung.

### 3. 💡 Transparenz & Einsteiger-Schnellguide
* **Mikro-Erklärungen unter jedem Feld:** Kurze und verständliche Hilfetexte erklären direkt unter jedem Parameter, was er bewirkt und welcher Wertebereich empfohlen wird.
* **Integrierter Schnellguide:** Aufklappbare Box im Autobot-Panel erläutert Kernkonzepte wie Positionsgrößen-Berechnung nach SL, Out-of-Sample-Validierung und Deflated Sharpe Ratio ohne Trader-Kauderwelsch.

### 4. 🖥️ Nahtlose TradingView Desktop-Integration
* **Keine doppelten Web-Tabs:** Wenn der Desktop-Relay aktiv ist, schaltet Windows die TradingView-Desktop-App direkt auf den Coin um (`BITGET:<SYMBOL>.P`), ohne einen redundanten Web-Tab zu öffnen.
* **Kanonische Symbole:** Einheitliche Formatierung aller Bitget USDT-M Perpetuals inklusive Meme-Coins mit Multiplikator (`1000BONK`, `1000PEPE`, etc.).

---

## Verifikation & Release-Status

* **Testsuite:** 175 Pytest-Tests & 57 Subtests PASSED.
* **Node.js-Integrationsprüfungen:** 6/6 Suites PASSED.
* **Pine Script v6 Static Check:** 100% konform (907 Zeilen, 0 Syntaxfehler).
* **Paket:** `symbiose.zip` gebaut, SHA-256 verifiziert, Smoke-Test bestanden.
