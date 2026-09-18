# AURA Instrumenten- und Liquiditätsvertrag v1

Stand: 2026-09-17. Dieses Dokument beschreibt eine konservative Betriebsannahme für Paper-Entries, keinen statistisch optimierten Gewinnnachweis. `MODEL_NO_EVIDENCE` bleibt unverändert.

## Quelle und API-Vertrag

Öffentliche Bitget Classic Contract REST API v2, am 2026-09-17 geprüft:

- Contract Config: `GET https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES`
  - Offizielle Dokumentation: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market#get-contract-config
- All Symbol Ticker: `GET https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES`
  - Offizielle Dokumentation: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market#get-all-symbol-ticker
- Merge Depth: `GET https://api.bitget.com/api/v2/mix/market/merge-depth?symbol={SYMBOL}&productType=USDT-FUTURES&precision=scale0&limit=50`
  - Offizielle Dokumentation: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market#get-merge-depth

Alle Endpunkte sind öffentlich und benötigen keine Exchange-Schlüssel. Der Updater verwendet ausschließlich `USDT-FUTURES` und akzeptiert nur `symbolType=perpetual`, `symbolStatus=normal`, `quoteCoin=USDT` und `USDT` in `supportMarginCoins`.

## Kanonische Instrumentenspezifikation

Bitget-Futures verwenden für `size` die Menge der Base Coin. Deshalb ist `sizeMultiplier` der erlaubte Mengen-Schritt in Base-Coin-Einheiten und kein generischer Kontraktwert (`ctVal`). Die kanonischen Felder sind:

- `symbol`, `product_type`, `symbol_type`, `symbol_status`
- `base_coin`, `quote_coin`, `settle_coin=USDT`
- `price_tick = priceEndStep × 10^(-pricePlace)` in Quote Coin pro Base Coin
- `qty_step = sizeMultiplier` in Base Coin
- `min_qty = minTradeNum` in Base Coin
- `min_notional = minTradeUSDT` in USDT
- `maker_fee_rate`, `taker_fee_rate`, `max_leverage`

Pflichtfelder werden als Dezimalstrings geparst und validiert. Fehlende, nullwertige, negative oder widersprüchliche Werte erzeugen keine Spezifikation. Es gibt keine erfundenen Null- oder Börsen-Defaults.

## Liquiditäts-Policy `aura-liquidity-v2`

Entscheidungszeit ist die aktuelle Worker-/Updater-Uhr, nicht die Startzeit einer Kerze. Ein Snapshot ist höchstens 120 Sekunden alt; mehr als 5 Sekunden Zukunftsabweichung blockieren.

Ein Symbol gilt nur dann allgemein als geprüft, wenn alle Kriterien erfüllt sind:

1. kompatibler, aktiver USDT-M-Perpetual-Kontrakt mit vollständiger Spezifikation;
2. vollständiges Orderbuch mit mindestens einer gültigen, sortierten Bid- und Ask-Seite und `best_ask > best_bid > 0`;
3. relativer Spread `(ask-bid)/mid` höchstens 10 Basispunkte;
4. auf jeder Seite mindestens 5.000 USDT kumuliertes Notional innerhalb ±25 Basispunkten um den Mid;
5. 24h-Quote-Volumen aus dem Ticker mindestens 1.000.000 USDT;
6. Ticker und Orderbuch erfüllen dieselbe Freshness-Grenze.

Die Schwellen sind konservative, versionierte Betriebsannahmen. Hohes 24h-Volumen oder ein aktiver Vertrag allein genügt ausdrücklich nicht.

## Ausführungsspezifische Prüfung

Vor jedem neuen Paper-Entry wird das bereits abgerundete Positionsnotional zusätzlich gegen die Snapshot-Tiefe der benötigten Seite geprüft:

- Long benötigt Ask-Tiefe, Short Bid-Tiefe.
- Positionsnotional darf höchstens 5 % der verfügbaren Bandtiefe (im ±25 bps Band) betragen.
- Fehlendes geplantes Notional, fehlende Seite oder veralteter Snapshot blockiert.

Ein positiver allgemeiner Marktstatus ist daher weder eine automatische Trade-Freigabe noch ein Nachweis realer Ausführbarkeit, Nettoergebnisse oder Profitabilität.

## Persistenz und Fehlerzustände

Die Datenbank speichert Spezifikation, Quelle, Exchange-Eventzeit, Abrufzeit, Rohsnapshot-Hash und relevante Messwerte sowie Policy-Version, Ergebnis und maschinenlesbare Ablehnungsgründe. Statuswerte:

- `loading`: noch kein abgeschlossener Abruf;
- `valid`: Policy bestanden und aktuell;
- `insufficient`: Abruf valide, aber Kriterien nicht erfüllt;
- `stale`: letzter Snapshot zu alt oder aus der Zukunft;
- `source_failed`: aktueller Abruf fehlgeschlagen.

Ein Quellenfehler setzt kein positives Flag fort. Neustart und Recovery prüfen das Alter gegen die aktuelle Uhr erneut. Bestehende Paper-Positionen werden weiterhin verwaltet; ausschließlich neue Entries werden blockiert.
