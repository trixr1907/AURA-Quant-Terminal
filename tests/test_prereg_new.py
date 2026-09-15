#!/usr/bin/env python3
"""Tests for Auftrag F: scripts/prereg_new.py (Evidence PreReg Assistant).

Covers:
1. Deterministic setup_id generation.
2. Deterministic params_sha256 calculation (sorted keys, canonical JSON).
3. build_prereg_entry schema validation via validate_prereg.
4. CLI non-interactive mode execution and output file generation.
5. Horizon validation (bars vs. until_date).
6. Evidence Protection: ensures execution of prereg_new.py NEVER alters the Ledger chain.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import hypothesis_check
import prereg_new


class TestPreRegAssistant(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_deterministic_setup_id(self):
        """Verify setup_id normalizes symbols, timeframe, and setup class."""
        s1 = prereg_new.compute_setup_id("BTC/USDT", "4H", "Pullback Momentum")
        self.assertEqual(s1, "BTCUSDT_4h_PULLBACK_MOMENTUM")

        s2 = prereg_new.compute_setup_id("ethusdt", "15m", "breakout_vol")
        self.assertEqual(s2, "ETHUSDT_15m_BREAKOUT_VOL")

    def test_deterministic_params_sha256(self):
        """Verify params_sha256 is key-order independent and matches canonical JSON SHA256."""
        p1 = {"b": 2, "a": 1, "nested": {"y": "test", "x": [3, 2, 1]}}
        p2 = {"nested": {"x": [3, 2, 1], "y": "test"}, "a": 1, "b": 2}

        h1 = prereg_new.compute_params_sha256(p1)
        h2 = prereg_new.compute_params_sha256(p2)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_build_prereg_entry_valid(self):
        """Verify build_prereg_entry constructs a schema-valid Hypothesis-PreReg object."""
        entry = prereg_new.build_prereg_entry(
            symbol="BTCUSDT",
            tf="4h",
            setup_class="PB_MOM",
            regime_context="TRENDING_BULL_ADX_GT25",
            hypothesis="Higher timeframe momentum pullback yields positive EV.",
            params={"ema_fast": 20, "ema_slow": 50, "adx_min": 25},
            n_min=30,
            edge_min=0.15,
            dsr_min=0.10,
            bars=500,
            author="ivo",
        )

        # Validate with official hypothesis_check validator
        self.assertTrue(hypothesis_check.validate_prereg(entry))
        self.assertEqual(entry["setup_id"], "BTCUSDT_4h_PB_MOM")
        self.assertEqual(entry["status"], "PREREGISTERED")
        self.assertEqual(entry["bars"], 500)

    def test_build_prereg_entry_date_horizon(self):
        """Verify build_prereg_entry with until_date horizon."""
        entry = prereg_new.build_prereg_entry(
            symbol="ETHUSDT",
            tf="1h",
            setup_class="BREAKOUT",
            regime_context="VOLATILITY_EXPANSION",
            hypothesis="Channel breakout in high volume regime.",
            params={},
            n_min=25,
            edge_min=0.20,
            dsr_min=0.12,
            until_date="2026-12-31T23:59:59Z",
        )
        self.assertTrue(hypothesis_check.validate_prereg(entry))
        self.assertIn("until_date", entry)
        self.assertNotIn("bars", entry)

    def test_cli_non_interactive_generation(self):
        """Verify CLI non-interactive mode generates valid entry JSON file."""
        out_file = Path(self.tmp_dir) / "test_entry.json"
        script_path = SCRIPTS_DIR / "prereg_new.py"

        cmd = [
            sys.executable,
            str(script_path),
            "--non-interactive",
            "--symbol", "SOLUSDT",
            "--tf", "15m",
            "--setup-class", "MEAN_REV",
            "--regime", "RANGING_LOW_VOL",
            "--hypothesis", "Bollinger band mean reversion in tight range.",
            "--params-json", '{"bb_period": 20, "bb_std": 2.0}',
            "--n-min", "40",
            "--edge-min", "0.12",
            "--dsr-min", "0.08",
            "--bars", "1000",
            "--author", "ivo",
            "--out", str(out_file),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"CLI stderr: {result.stderr}")
        self.assertTrue(out_file.exists())

        with open(out_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertTrue(hypothesis_check.validate_prereg(data))
        self.assertEqual(data["setup_id"], "SOLUSDT_15m_MEAN_REV")
        self.assertEqual(data["acceptance"]["n_min"], 40)

    def test_two_step_design_evidence_protection(self):
        """Ensure running prereg_new.py NEVER modifies or appends to trials_ledger_chain.jsonl."""
        ledger_path = Path(__file__).resolve().parent.parent / "docs" / "research" / "trials_ledger_chain.jsonl"
        before_content = ledger_path.read_text(encoding="utf-8")
        before_mtime = ledger_path.stat().st_mtime_ns

        out_file = Path(self.tmp_dir) / "prereg.json"
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "prereg_new.py"),
            "--non-interactive",
            "--symbol", "BTCUSDT",
            "--tf", "1h",
            "--setup-class", "TEST_CLASS",
            "--regime", "BULL",
            "--hypothesis", "Test protection",
            "--out", str(out_file),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

        after_content = ledger_path.read_text(encoding="utf-8")
        after_mtime = ledger_path.stat().st_mtime_ns

        self.assertEqual(before_content, after_content, "trials_ledger_chain.jsonl must remain byte-identical")
        self.assertEqual(before_mtime, after_mtime, "trials_ledger_chain.jsonl mtime must not change")


if __name__ == "__main__":
    unittest.main()
