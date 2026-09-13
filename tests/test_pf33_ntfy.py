"""
test_pf33_ntfy.py — Legacy ntfy compatibility contract

The public helper remains backward-compatible. Active-trade delete mutations no
longer emit independently because PF-59 owns semantic close-event deduplication.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import tempfile
import urllib.error
import urllib.request

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bitget_relay
from bitget_relay import _ntfy_notify, notify_trade_closed


class TestNtfyDisabledWhenNotConfigured(unittest.TestCase):
    """No AURA_NTFY_URL → _ntfy_notify must be silent no-op."""

    def setUp(self):
        os.environ.pop("AURA_NTFY_URL", None)

    def test_ntfy_noop_when_env_not_set(self):
        """Must not call urlopen when AURA_NTFY_URL is absent."""
        with patch("urllib.request.urlopen") as mock_open:
            _ntfy_notify("test title", "test body")
            # Give daemon thread a moment to run
            time.sleep(0.05)
            mock_open.assert_not_called()

    def test_ntfy_noop_when_env_empty_string(self):
        """Empty string must also be treated as disabled."""
        os.environ["AURA_NTFY_URL"] = ""
        try:
            with patch("urllib.request.urlopen") as mock_open:
                _ntfy_notify("test title", "test body")
                time.sleep(0.05)
                mock_open.assert_not_called()
        finally:
            os.environ.pop("AURA_NTFY_URL", None)


class TestNtfyHappyPath(unittest.TestCase):
    """When AURA_NTFY_URL is set, _ntfy_notify sends a correct POST."""

    NTFY_URL = "http://ntfy.example.com/aura-alerts"

    def setUp(self):
        os.environ["AURA_NTFY_URL"] = self.NTFY_URL

    def tearDown(self):
        os.environ.pop("AURA_NTFY_URL", None)

    def _call_and_wait(self, title: str, body: str, mock_open: MagicMock) -> None:
        """Call _ntfy_notify and wait briefly for the daemon thread."""
        _ntfy_notify(title, body)
        deadline = time.monotonic() + 1.0
        while not mock_open.called and time.monotonic() < deadline:
            time.sleep(0.01)

    def test_sends_post_to_configured_url(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self._call_and_wait("Trade geschlossen", "BTCUSDT +2.5%", mock_open)
            self.assertTrue(mock_open.called, "urlopen should have been called")
            req: urllib.request.Request = mock_open.call_args[0][0]
            self.assertEqual(req.full_url, self.NTFY_URL)
            self.assertEqual(req.get_method(), "POST")

    def test_sends_title_and_body_in_headers_and_data(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self._call_and_wait("Mein Titel", "Nachrichtentext", mock_open)
            req: urllib.request.Request = mock_open.call_args[0][0]
            # Body must contain the message body
            self.assertIn(b"Nachrichtentext", req.data)
            # X-Title header must carry the title
            self.assertIn("Mein Titel", req.get_header("X-title") or req.get_header("X-Title") or "")

    def test_does_not_raise_on_http_error(self):
        """Fire-and-forget: HTTP 500 must not propagate to caller."""
        err = urllib.error.HTTPError(self.NTFY_URL, 500, "Internal Server Error", {}, None)
        with patch("urllib.request.urlopen", side_effect=err):
            # Must not raise
            _ntfy_notify("title", "body")
            time.sleep(0.05)

    def test_does_not_raise_on_connection_error(self):
        """Fire-and-forget: connection refused must not propagate to caller."""
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            _ntfy_notify("title", "body")
            time.sleep(0.05)

    def test_dispatches_on_daemon_thread(self):
        """_ntfy_notify must return immediately without blocking."""
        released = threading.Event()
        original_open = urllib.request.urlopen

        def slow_open(req, **kw):
            time.sleep(0.3)
            released.set()
            raise OSError("mock")

        with patch("urllib.request.urlopen", side_effect=slow_open):
            t0 = time.monotonic()
            _ntfy_notify("title", "body")
            elapsed = time.monotonic() - t0
            # Caller must return in well under 300ms (the mock sleeps 300ms)
            self.assertLess(elapsed, 0.15, "ntfy must be fire-and-forget, returned too slowly")
            released.wait(timeout=1.0)  # wait for background thread to finish

    def test_rejects_non_http_url(self):
        """Only http/https URLs are accepted; file:// must be silently ignored."""
        os.environ["AURA_NTFY_URL"] = "file:///etc/passwd"
        with patch("urllib.request.urlopen") as mock_open:
            _ntfy_notify("title", "body")
            time.sleep(0.05)
            mock_open.assert_not_called()


class TestNotifyTradeClosed(unittest.TestCase):
    """notify_trade_closed() must build a human-readable message."""

    def setUp(self):
        os.environ["AURA_NTFY_URL"] = "http://ntfy.example.com/aura"

    def tearDown(self):
        os.environ.pop("AURA_NTFY_URL", None)

    def test_includes_symbol_and_id(self):
        trade = {"id": "t1", "symbol": "BTCUSDT", "side": "Long", "pnl": 42.5}
        calls_made: list[tuple] = []

        orig = bitget_relay._ntfy_notify

        def capture(title, body):
            calls_made.append((title, body))

        with patch.object(bitget_relay, "_ntfy_notify", side_effect=capture):
            notify_trade_closed(trade)

        self.assertTrue(calls_made, "notify_trade_closed must call _ntfy_notify")
        title, body = calls_made[0]
        self.assertIn("BTCUSDT", title + body)
        self.assertIn("t1", title + body)

    def test_noop_without_env(self):
        os.environ.pop("AURA_NTFY_URL", None)
        with patch("urllib.request.urlopen") as mock_open:
            notify_trade_closed({"id": "x", "symbol": "ETHUSDT"})
            time.sleep(0.05)
            mock_open.assert_not_called()


class TestMutationBatchAbsorbsLegacyNotify(unittest.TestCase):
    """PF-59 owns close pushes, so PF-33's delete hook must stay silent."""

    def setUp(self):
        os.environ["AURA_NTFY_URL"] = "http://ntfy.example.com/aura"
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["AURA_STATE_DIR"] = self._tmpdir.name
        bitget_relay.STATE_DIR = Path(self._tmpdir.name)
        bitget_relay.STATE_FILE = bitget_relay.STATE_DIR / "aura_shared_state.json"
        # Seed state with one active trade
        state = {
            "_rev": 0,
            "aura-quant-terminal-active-trades-v1": [
                {"id": "t-del-1", "symbol": "SOLUSDT", "side": "Short", "pnl": -10.0}
            ],
        }
        bitget_relay.STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

    def tearDown(self):
        os.environ.pop("AURA_NTFY_URL", None)
        os.environ.pop("AURA_STATE_DIR", None)
        self._tmpdir.cleanup()
        bitget_relay.STATE_DIR = Path(
            os.environ.get("AURA_STATE_DIR", Path(bitget_relay.__file__).resolve().parent / "data")
        )
        bitget_relay.STATE_FILE = bitget_relay.STATE_DIR / "aura_shared_state.json"

    def test_delete_mutation_does_not_trigger_legacy_notify(self):
        notified: list[dict] = []

        def capture(trade):
            notified.append(trade)

        with patch.object(bitget_relay, "notify_trade_closed", side_effect=capture):
            mutations = [
                {"key": "aura-quant-terminal-active-trades-v1", "op": "delete", "id": "t-del-1"}
            ]
            saved, rev, err = bitget_relay._save_mutation_batch(mutations)
        self.assertIsNotNone(saved)
        self.assertFalse(notified, "PF-33 delete hook must be absorbed to avoid a second close push")

    def test_upsert_mutation_does_not_trigger_notify(self):
        notified: list[dict] = []

        def capture(trade):
            notified.append(trade)

        with patch.object(bitget_relay, "notify_trade_closed", side_effect=capture):
            mutations = [
                {
                    "key": "aura-quant-terminal-active-trades-v1",
                    "op": "upsert",
                    "id": "t-new-1",
                    "value": {"id": "t-new-1", "symbol": "XRPUSDT"},
                }
            ]
            bitget_relay._save_mutation_batch(mutations)
        self.assertFalse(notified, "notify_trade_closed must NOT be called on upsert")


if __name__ == "__main__":
    unittest.main(verbosity=2)
