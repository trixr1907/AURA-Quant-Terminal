"""PF-62 tests for the persistent BTC regime watcher."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import bitget_relay

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "BTCUSDT_1h.csv"


def load_fixture(limit: int = 600) -> list[dict]:
    with FIXTURE.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))[-limit:]
    return [
        {
            "t": int(float(row.get("timestamp") or row.get("time") or 0)),
            "o": float(row.get("open") or row.get("Open")),
            "h": float(row.get("high") or row.get("High")),
            "l": float(row.get("low") or row.get("Low")),
            "c": float(row.get("close") or row.get("Close")),
            "v": float(row.get("volume") or row.get("Volume")),
        }
        for row in rows
    ]


class TestBtcRegimeParity(unittest.TestCase):
    def test_python_matches_javascript_on_golden_fixture(self):
        candles = load_fixture()
        py = bitget_relay.classify_btc_regime(candles)
        proc = subprocess.run(
            ["node", str(ROOT / "scripts" / "btc_regime_dashboard_export.js"), str(FIXTURE), "600"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        js = json.loads(proc.stdout)
        self.assertEqual(py["base"], js["base"])
        self.assertEqual(py["squeeze"], js["squeeze"])
        for key in ("close", "ema50", "ema200", "adx"):
            self.assertAlmostEqual(py[key], js[key], places=8)

    def test_regime_change_cooldown_and_squeeze_are_signal_disciplined(self):
        previous = {
            "btc": {
                "base": "BULL",
                "squeeze": False,
                "regime_changed_at": "2026-09-14T06:00:00Z",
                "last_notified_at": 1000.0,
            }
        }
        bear = {"base": "BEAR", "squeeze": False, "adx": 24.0, "close": 90.0, "ema50": 95.0, "ema200": 100.0}
        decision = bitget_relay.btc_regime_transition(previous, bear, now=1000.0 + 31 * 60, cooldown_minutes=30)
        self.assertTrue(decision["notify"])
        self.assertIn("Bot-Gate blockiert jetzt Longs", decision["body"])

        blocked = bitget_relay.btc_regime_transition(previous, bear, now=1000.0 + 29 * 60, cooldown_minutes=30)
        self.assertFalse(blocked["notify"])

        squeeze = dict(bear, base="SIDEWAYS", squeeze=True)
        silent = bitget_relay.btc_regime_transition(previous, squeeze, now=1000.0 + 31 * 60, cooldown_minutes=30)
        self.assertFalse(silent["notify"])
        self.assertEqual(silent["btc"]["signal_base"], "BULL")

        squeeze_exit = dict(previous, btc=silent["btc"])
        resumed_bull = {**bear, "base": "BULL", "squeeze": False}
        resumed = bitget_relay.btc_regime_transition(squeeze_exit, resumed_bull, now=1000.0 + 32 * 60, cooldown_minutes=30)
        self.assertFalse(resumed["notify"], "pure squeeze entry/exit must stay silent")

        changed_under_squeeze = dict(bear, base="BEAR", squeeze=False)
        changed = bitget_relay.btc_regime_transition(squeeze_exit, changed_under_squeeze, now=1000.0 + 33 * 60, cooldown_minutes=30)
        self.assertTrue(changed["notify"], "a real structural change hidden by squeeze must alert on exit")

    def test_cycle_persists_regime_and_does_not_repeat_after_restart(self):
        now = datetime(2026, 9, 14, 7, 5, tzinfo=timezone.utc).timestamp()
        regime = {"base": "BEAR", "squeeze": False, "adx": 24.0, "close": 90.0, "ema50": 95.0, "ema200": 100.0}
        notifications = []
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "signals.json"
            with patch.object(bitget_relay, "SIGNAL_STATE_FILE", state_file), \
                 patch.object(bitget_relay, "classify_btc_regime", return_value=regime), \
                 patch.object(bitget_relay, "_ntfy_notify", side_effect=lambda *a, **kw: notifications.append((a, kw)) or True):
                first = bitget_relay.run_btc_regime_cycle(lambda: load_fixture(), now=now)
                second = bitget_relay.run_btc_regime_cycle(lambda: load_fixture(), now=now + 300)
        self.assertEqual(first["base"], "BEAR")
        self.assertEqual(second["base"], "BEAR")
        self.assertEqual(notifications, [])  # Initial baseline and unchanged restart are silent.


if __name__ == "__main__":
    unittest.main()
