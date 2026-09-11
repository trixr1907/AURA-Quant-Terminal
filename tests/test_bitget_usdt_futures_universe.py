from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.sync_market_data import normalize_usdt_futures_contracts


ROOT = Path(__file__).resolve().parents[1]


class TestBitgetUsdtFuturesUniverse(unittest.TestCase):
    def test_normalizer_accepts_only_active_usdt_m_perpetuals(self):
        contracts = [
            {"symbol": "BTCUSDT", "baseCoin": "BTC", "quoteCoin": "USDT", "symbolType": "perpetual", "symbolStatus": "normal", "deliveryTime": ""},
            {"symbol": "ETHUSDT", "baseCoin": "ETH", "quoteCoin": "USDT", "symbolType": "perpetual", "symbolStatus": "online", "deliveryTime": None},
            {"symbol": "BTCUSD", "baseCoin": "BTC", "quoteCoin": "USD", "symbolType": "perpetual", "symbolStatus": "normal"},
            {"symbol": "OLDUSDT", "baseCoin": "OLD", "quoteCoin": "USDT", "symbolType": "perpetual", "symbolStatus": "off"},
            {"symbol": "DATEDUSDT_260925", "baseCoin": "DATED", "quoteCoin": "USDT", "symbolType": "delivery", "symbolStatus": "normal", "deliveryTime": "1790294400000"},
        ]

        result = normalize_usdt_futures_contracts(contracts, {})

        self.assertEqual([row["symbol"] for row in result], ["BTCUSDT", "ETHUSDT"])
        self.assertTrue(all(row["productType"] == "USDT-FUTURES" for row in result))
        self.assertTrue(all(row["contractType"] == "perpetual" for row in result))

    def test_checked_in_snapshot_has_only_strict_bitget_usdt_m_contracts(self):
        snapshot = json.loads((ROOT / "data" / "bitget_usdt_futures_universe.json").read_text(encoding="utf-8"))
        contracts = snapshot["contracts"]

        self.assertEqual(snapshot["total_contracts"], len(contracts))
        self.assertGreater(len(contracts), 100)
        self.assertEqual(len({row["symbol"] for row in contracts}), len(contracts))
        for row in contracts:
            self.assertTrue(row["symbol"].endswith("USDT"))
            self.assertNotIn("_", row["symbol"])
            self.assertEqual(row["quoteCoin"], "USDT")
            self.assertEqual(row["productType"], "USDT-FUTURES")
            self.assertEqual(row["contractType"], "perpetual")
            self.assertIn(row["symbolStatus"], {"normal", "online"})

    def test_dashboard_has_no_cross_exchange_universe_fallback(self):
        html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
        start = html.index("async function fetchUniverseFallback()")
        end = html.index("\nasync function loadUniverse()", start)
        fallback = html[start:end]

        self.assertNotIn("api.binance.com", fallback)
        self.assertNotIn("binance.vision", fallback)
        self.assertNotIn("api.bybit.com", fallback)
        self.assertIn("bitget_usdt_futures_universe.json", fallback)
        self.assertIn("isActiveBitgetUsdtFuture", html)

    def test_dashboard_market_selection_is_strictly_bitget_usdt_m(self):
        html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
        fetch_start = html.index("async function fetchKlines(")
        fetch_end = html.index("\nasync function fetchTicker(", fetch_start)
        ticker_end = html.index("\nasync function fetchFNG(", fetch_end)
        market_path = html[fetch_start:ticker_end]

        self.assertIn("return await bitgetKlines(symbol, tf, target)", market_path)
        self.assertIn("return await bitgetTicker(symbol)", market_path)
        self.assertNotIn("binanceKlinesPaged", market_path)
        self.assertNotIn("bybitKlines", market_path)
        self.assertNotIn("cgKlines", market_path)
        self.assertNotIn('id="source"', html)
        self.assertIn("isUniverseSymbol", html)
        self.assertIn("aktiver Bitget USDT-M Future verfügbar", html)

    def test_tradingview_bridge_is_pinned_to_bitget_perpetual(self):
        html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")

        self.assertNotIn('value="binance_perp"', html)
        self.assertNotIn('value="bitget_spot"', html)
        self.assertIn("const TRADINGVIEW_MARKETS = {\n  bitget_perp", html)


if __name__ == "__main__":
    unittest.main()
