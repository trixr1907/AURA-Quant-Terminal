# AURA v1.1.8 — TradingView Basic Bridge

## Überblick

AURA v1.1.8 verbindet Setup Discovery und TradingView in einem ausdrücklich mit TradingView Basic/Free kompatiblen Workflow. Keine Funktion benötigt Webhooks, technische Premium-Alarme oder Multi-Chart-Layouts.

## Neu

- TradingView Bridge direkt unter der Hero Opportunity.
- Auswahl zwischen Bitget Perpetual, Binance Perpetual und Bitget Spot.
- Optionaler Start in einem gespeicherten kostenlosen AURA-Chart-Layout.
- Laden des aktuellen Coins und Timeframes bei gleichzeitigem Kopieren des Pine-v6-Scripts.
- Navigation zum vorigen oder nächsten vollständigen Radar-Kandidaten.
- Kopierbare Top-30-, LONG- und SHORT-Symbollisten mit festem Basic-Limit von 30 Symbolen.
- Kopierbare Preisalarm-Vorlagen für Entry, Stop und TP1.
- Kopierbare Setup-Notiz mit reproduzierbarem Rücksprung-Link zu AURA.
- Rücksprung-Links akzeptieren ausschließlich validierte USDT-Symbole und die Timeframes 15m, 1h, 4h und 1d.
- Pine-Auslieferung über die lokalen Relay-Routen `/pine` und `/Symbiose_Signal_System_v1.pine`.

## Ehrliche Grenzen

- AURA kann Pine-Code nicht automatisch im TradingView Pine Editor installieren oder ausführen.
- AURA legt keine TradingView-Alarme automatisch an.
- Die Preisalarm-Vorlagen werden kopiert und müssen im TradingView-Dialog manuell übernommen werden.
- Radar-Kandidaten und lokal gemessener Edge sind keine global validierte Strategie-Evidenz.

## Verifikation

- TradingView URL-, Symbol-, Layout- und Timeframe-Tests.
- Basic-QoL-Tests für 30-Symbol-Limit, Richtungsfilter, Preisalarme, Setup-Notiz und Rücksprung-Link.
- Relay-Tests für die Pine-Auslieferung.
- Vollständige Python- und JavaScript-Regressionstests.
- Release-Gate bleibt fail-closed mit `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
