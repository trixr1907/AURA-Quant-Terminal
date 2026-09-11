# AURA v1.2.1 — Pine Trade Forecasting, TV-Desktop-Direktumschaltung & Einsteiger-Transparenz

## Überblick

AURA v1.2.1 bringt ein interaktives **Trade-Forecasting-Overlay in Pine Script v6**, optimierte und realistische **Default-Parameter (1.000 USDT Startkapital, 5% Risiko, 10x Hebel, 500k $ 24h-Mindestvolumen)**, maximale **Transparenz mit Einsteiger-Schnellguide** im Autobot-Konfigurationspanel und eine **zuverlässige direkte TradingView-Desktop-Integration** ohne doppelte Web-Browser-Tabs.

---

## Neu in v1.2.1

### 1. 📊 Pine Script Trade Forecasting & Execution Overlay (v6)
* **Visuelle Trade-Projektion:** In `Symbiose_Signal_System_v1.pine` wurde die Input-Gruppe `7) Trade Forecasting & Execution` integriert.
* **Exakte Preislevels & R:R-Boxen:** Zeichnet dynamisch Entry (Cyan), Stop-Loss (Rot), TP1 (+1.5R Hellgrün), TP2 (+3.0R Grün) und TP3 (+5.0R Smaragdgrün) sowie halbtransparente Gewinn- und Verlustzonen in die Zukunft.
* **Status-Badge:** Informatives Karten-Badge am rechten Rand mit Hebel, Trade-Notiz, prozentualem Risiko und Take-Profit-Distanzen.
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
