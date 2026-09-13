"""PF-59 relay signal claims and notification policy."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import bitget_relay


class TestSignalClaims(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name)
        self.state_file = self.state_dir / "aura_shared_state.json"
        self.patches = [
            patch.object(bitget_relay, "STATE_DIR", self.state_dir),
            patch.object(bitget_relay, "STATE_FILE", self.state_file),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_claim_is_first_writer_wins_across_two_tabs(self):
        barrier = threading.Barrier(2)
        results: list[bool] = []

        def tab() -> None:
            barrier.wait()
            claimed, _rev, error = bitget_relay._claim_signal_event("trade-1:tp1")
            self.assertIsNone(error)
            results.append(claimed)

        threads = [threading.Thread(target=tab), threading.Thread(target=tab)]
        for item in threads:
            item.start()
        for item in threads:
            item.join()

        self.assertEqual(sorted(results), [False, True])
        persisted = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertIn("trade-1:tp1", persisted["_signal_claims"])

    def test_claim_survives_restart_reload(self):
        first, first_rev, error = bitget_relay._claim_signal_event("trade-2:sl_close", now=1000)
        second, second_rev, error2 = bitget_relay._claim_signal_event("trade-2:sl_close", now=2000)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(second_rev, first_rev)
        self.assertIsNone(error)
        self.assertIsNone(error2)

    def test_pf33_delete_hook_is_absorbed(self):
        self.state_file.write_text(json.dumps({
            "_rev": 0,
            "aura-quant-terminal-active-trades-v1": [{"id": "trade-close"}],
        }), encoding="utf-8")
        with patch.object(bitget_relay, "notify_trade_closed") as legacy_notify:
            saved, _rev, error = bitget_relay._save_mutation_batch([
                {"key": "aura-quant-terminal-active-trades-v1", "op": "delete", "id": "trade-close"}
            ])
        self.assertIsNotNone(saved)
        self.assertIsNone(error)
        legacy_notify.assert_not_called()


class TestNtfyPolicy(unittest.TestCase):
    def test_priority_and_category_headers_are_set(self):
        requests = []
        ran = threading.Event()

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False

        def capture(request, timeout=0):
            requests.append(request)
            ran.set()
            return Response()

        with patch.dict("os.environ", {"AURA_NTFY_URL": "https://ntfy.invalid/runtime-topic"}, clear=False), \
                patch("urllib.request.urlopen", side_effect=capture):
            self.assertTrue(bitget_relay._ntfy_notify("BTC-Regime", "BEAR", category="btc", priority=4))
            ran.wait(1)

        self.assertEqual(requests[0].get_header("Priority"), "4")
        self.assertEqual(requests[0].get_header("Tags"), "btc")

    def test_cooldown_helper_is_category_scoped(self):
        state = {"cooldowns": {"btc": 2000}}
        self.assertFalse(bitget_relay._cooldown_ready(state, "btc", now=1999))
        self.assertTrue(bitget_relay._cooldown_ready(state, "error", now=1999))
        bitget_relay._set_cooldown(state, "error", minutes=60, now=1000)
        self.assertEqual(state["cooldowns"]["error"], 4600)


if __name__ == "__main__":
    unittest.main()
