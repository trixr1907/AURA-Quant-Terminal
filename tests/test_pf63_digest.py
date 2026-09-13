"""PF-63 tests for daily digest and persistent data-dead alerts."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import bitget_relay


class TestDailyDigest(unittest.TestCase):
    def test_digest_is_once_per_utc_day_and_contains_required_state(self):
        now = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc).timestamp()
        shared = {
            "aura-autobot-state-v2": {"equity": 1234.5},
            "aura-quant-terminal-active-trades-v1": [{"id": "open"}],
            "aura-quant-terminal-history-trades-v1": [
                {"closedAt": int((now - 60) * 1000), "realizedPnlGross": 12.25},
                {"closedAt": int((now - 90000) * 1000), "realizedPnlGross": 999},
            ],
        }
        state = {"btc": {"base": "BEAR"}, "digest": {}}
        result = bitget_relay.daily_digest_transition(state, shared, now=now, utc_hour=7)
        self.assertTrue(result["notify"])
        self.assertIn("1 offene Position", result["body"])
        self.assertIn("1 Schluss in 24h", result["body"])
        self.assertIn("+12.25 USDT", result["body"])
        self.assertIn("1234.50 USDT", result["body"])
        self.assertIn("BEAR", result["body"])
        again = bitget_relay.daily_digest_transition(result["state"], shared, now=now + 3600, utc_hour=7)
        self.assertFalse(again["notify"])

    def test_digest_counts_autobot_positions_and_history(self):
        now = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc).timestamp()
        shared = {
            "aura-autobot-state-v2": {
                "equity": 975.5,
                "trades": [{"id": "autobot-open"}],
                "history": [{"closedAt": int((now - 60) * 1000), "realizedPnlGross": -3.5}],
            },
            "aura-quant-terminal-active-trades-v1": [{"id": "manual-open"}],
            "aura-quant-terminal-history-trades-v1": [],
        }
        result = bitget_relay.daily_digest_transition({"btc": {"base": "BULL"}}, shared, now=now, utc_hour=7)
        self.assertIn("2 offene Positionen", result["body"])
        self.assertIn("1 Schluss in 24h", result["body"])
        self.assertIn("-3.50 USDT", result["body"])

    def test_digest_respects_disabled_env(self):
        with patch.dict("os.environ", {"AURA_NTFY_DIGEST": "0"}, clear=False):
            self.assertFalse(bitget_relay.digest_enabled())
        with patch.dict("os.environ", {"AURA_NTFY_DIGEST_UTC": "off"}, clear=True):
            self.assertFalse(bitget_relay.digest_enabled())


class TestFeedErrorAlert(unittest.TestCase):
    def test_error_waits_five_minutes_then_uses_sixty_minute_cooldown(self):
        state = {"health": {}}
        first = bitget_relay.feed_error_transition(state, "upstream timeout", now=1000)
        self.assertFalse(first["notify"])
        early = bitget_relay.feed_error_transition(first["state"], "upstream timeout", now=1299)
        self.assertFalse(early["notify"])
        due = bitget_relay.feed_error_transition(early["state"], "upstream timeout", now=1301)
        self.assertTrue(due["notify"])
        self.assertIn("upstream timeout", due["body"])
        cooled = bitget_relay.feed_error_transition(due["state"], "upstream timeout", now=1301 + 3599)
        self.assertFalse(cooled["notify"])
        repeated = bitget_relay.feed_error_transition(cooled["state"], "upstream timeout", now=1301 + 3600)
        self.assertTrue(repeated["notify"])

    def test_success_resets_error_chain_but_preserves_cooldown(self):
        state = {
            "health": {
                "first_error_at": 1000,
                "last_error_at": 1301,
                "last_error": "offline",
                "data_dead_cooldown_until": 4901,
            }
        }
        recovered = bitget_relay.feed_success_transition(state, now=1400)
        health = recovered["health"]
        self.assertIsNone(health["first_error_at"])
        self.assertIsNone(health["last_error_at"])
        self.assertIsNone(health["last_error"])
        self.assertEqual(health["data_dead_cooldown_until"], 4901)
        self.assertEqual(health["last_success_at"], 1400)

    def test_runtime_cycle_persists_error_cooldown_and_priority(self):
        sent = []
        with tempfile.TemporaryDirectory() as tmp:
            signal_file = Path(tmp) / "signals.json"
            with patch.object(bitget_relay, "SIGNAL_STATE_FILE", signal_file), \
                 patch.object(bitget_relay, "_ntfy_notify", side_effect=lambda *a, **kw: sent.append((a, kw)) or True), \
                 patch.dict("os.environ", {"AURA_NTFY_ERRORS": "1"}, clear=False):
                bitget_relay.run_signal_center_cycle(lambda: (_ for _ in ()).throw(RuntimeError("feed offline")), now=1000)
                bitget_relay.run_signal_center_cycle(lambda: (_ for _ in ()).throw(RuntimeError("feed offline")), now=1301)
                bitget_relay.run_signal_center_cycle(lambda: (_ for _ in ()).throw(RuntimeError("feed offline")), now=1302)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1]["priority"], 4)
        self.assertEqual(sent[0][1]["category"], "errors")


if __name__ == "__main__":
    unittest.main()
