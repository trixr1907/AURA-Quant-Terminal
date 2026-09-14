"""
Slice C: Shadow Collector Unit and Integration Tests (Python)
============================================================
Tests for:
  1. /ready endpoint returns shadow: { enabled, entries, pending_outcomes, evaluated }
  2. _shadow_health helper reads shadow log / shadow stats
  3. daily_digest_transition includes Schatten summary when enabled
  4. daily_digest_transition excludes Schatten summary when disabled (AURA_SHADOW=0)
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import bitget_relay as relay


class TestShadowHealthAndReady(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aura_shadow_py_")
        self.state_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shadow_health_disabled_when_env_zero(self):
        with patch.dict(os.environ, {"AURA_SHADOW": "0", "AURA_STATE_DIR": str(self.state_dir)}):
            health = relay._shadow_health()
            self.assertFalse(health["enabled"])
            self.assertEqual(health["entries"], 0)
            self.assertEqual(health["pending_outcomes"], 0)
            self.assertEqual(health["evaluated"], 0)

    def test_shadow_health_reads_log_and_stats(self):
        log_file = self.state_dir / "shadow_log.jsonl"
        records = [
            # Pending outcome (no outcome field)
            {
                "ts": "2026-09-14T10:00:00Z",
                "symbol": "BTCUSDT",
                "tf": "1h",
                "dir": 1,
                "score": 80.0,
                "regime": 1,
                "adx": 25.0,
                "atrPct": 1.5,
                "decision": "ACCEPTED",
                "reject_reason": None,
                "signal_price": 60000.0,
                "params_sha256": "abc1234567890",
            },
            # Evaluated accepted outcome
            {
                "ts": "2026-09-14T11:00:00Z",
                "symbol": "ETHUSDT",
                "tf": "1h",
                "dir": 1,
                "score": 77.0,
                "regime": 1,
                "adx": 22.0,
                "atrPct": 2.0,
                "decision": "ACCEPTED",
                "reject_reason": None,
                "signal_price": 3000.0,
                "params_sha256": "abc1234567890",
                "outcome": "hit_tp1",
                "r_net": 1.25,
            },
            # Evaluated rejected outcome
            {
                "ts": "2026-09-14T12:00:00Z",
                "symbol": "SOLUSDT",
                "tf": "15m",
                "dir": -1,
                "score": 20.0,
                "regime": -1,
                "adx": 19.0,
                "atrPct": 3.0,
                "decision": "REJECTED",
                "reject_reason": "MODEL_NO_EVIDENCE",
                "signal_price": 150.0,
                "params_sha256": "abc1234567890",
                "outcome": "hit_sl",
                "r_net": -1.05,
            },
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        with patch.dict(os.environ, {"AURA_SHADOW": "1", "AURA_STATE_DIR": str(self.state_dir)}):
            health = relay._shadow_health()
            self.assertTrue(health["enabled"])
            self.assertEqual(health["entries"], 3)
            self.assertEqual(health["pending_outcomes"], 1)
            self.assertEqual(health["evaluated"], 2)


class TestShadowDigest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aura_shadow_digest_")
        self.state_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_digest_includes_shadow_when_enabled(self):
        now = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc).timestamp()
        log_file = self.state_dir / "shadow_log.jsonl"
        records = [
            # 1 accepted, evaluated to +1.20R
            {
                "ts": "2026-09-14T01:00:00Z",
                "decision": "ACCEPTED",
                "outcome": "hit_tp1",
                "r_net": 1.20,
            },
            # 1 rejected, evaluated to -0.80R
            {
                "ts": "2026-09-14T02:00:00Z",
                "decision": "REJECTED",
                "outcome": "hit_sl",
                "r_net": -0.80,
            },
            # 1 observed pending
            {
                "ts": "2026-09-14T03:00:00Z",
                "decision": "REJECTED",
                "reject_reason": "LIQUIDITY",
            },
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        shared = {"aura-server-bot-state-v1": {"equity": 10000.0}}
        state = {"btc": {"base": "BULL"}, "digest": {}}

        with patch.dict(os.environ, {"AURA_SHADOW": "1", "AURA_STATE_DIR": str(self.state_dir)}):
            result = relay.daily_digest_transition(state, shared, now=now, utc_hour=7)
            self.assertTrue(result["notify"])
            body = result["body"]
            self.assertIn("Schatten: 3 Setups beobachtet, 2 bewertet", body)
            self.assertIn("+1.20R vs. -0.80R", body)

    def test_digest_omits_shadow_when_disabled(self):
        now = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc).timestamp()
        shared = {"aura-server-bot-state-v1": {"equity": 10000.0}}
        state = {"btc": {"base": "BULL"}, "digest": {}}

        with patch.dict(os.environ, {"AURA_SHADOW": "0", "AURA_STATE_DIR": str(self.state_dir)}):
            result = relay.daily_digest_transition(state, shared, now=now, utc_hour=7)
            self.assertTrue(result["notify"])
            body = result["body"]
            self.assertNotIn("Schatten:", body)
