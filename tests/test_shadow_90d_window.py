#!/usr/bin/env python3
"""Tests for S5 Shadow Log 90-day rolling window parser and DSR evaluation.

Verifies:
1. Exact 90-day UTC window filtering (excluding older records >90d).
2. Proper parsing of JSONL shadow logs with various timestamp formats.
3. Accurate aggregation of completed trade outcomes.
4. Correct multiple-testing trial floor (DSR_TRIALS = max(45, ledger_trials)).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import hypothesis_check  # noqa: E402


def test_evaluate_forward_window_filters_exact_90_days(tmp_path: Path):
    """Verify that records outside the [ref_dt - 90d, ref_dt] window are excluded."""
    log_file = tmp_path / "shadow_log.jsonl"
    ref_dt = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Old record 120 days ago (should be excluded)
    old_record = {
        "timestamp": (ref_dt - timedelta(days=120)).isoformat(),
        "symbol": "BTCUSDT",
        "outcome": "hit_tp1",
        "rNet": 2.5,
    }
    # 2. Record exactly at 89 days ago (included)
    in_record_1 = {
        "timestamp": (ref_dt - timedelta(days=89)).isoformat(),
        "symbol": "BTCUSDT",
        "outcome": "hit_tp1",
        "rNet": 1.2,
    }
    # 3. Record 45 days ago (included)
    in_record_2 = {
        "timestamp": (ref_dt - timedelta(days=45)).isoformat(),
        "symbol": "BTCUSDT",
        "outcome": "hit_sl",
        "rNet": -0.8,
    }
    # 4. Record 1 day ago (included)
    in_record_3 = {
        "timestamp": (ref_dt - timedelta(days=1)).isoformat(),
        "symbol": "BTCUSDT",
        "outcome": "hit_tp1",
        "rNet": 1.5,
    }
    # 5. Pending record (no closed outcome / pending -> excluded from returns)
    pending_record = {
        "timestamp": (ref_dt - timedelta(days=10)).isoformat(),
        "symbol": "BTCUSDT",
        "outcome": "pending",
        "rNet": 0.0,
    }

    records = [old_record, in_record_1, in_record_2, in_record_3, pending_record]
    with log_file.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    res = hypothesis_check.evaluate_forward_window(
        shadow_log_path=log_file,
        n_min=3,
        edge_min=0.1,
        dsr_min=0.05,
        window_days=90,
        now_dt=ref_dt,
        ledger_trials=10,
    )

    assert res["n"] == 3  # exactly 3 closed trades within 90 days
    # Expected edge: (1.2 - 0.8 + 1.5) / 3 = 1.9 / 3 = 0.6333...
    assert pytest.approx(res["edge"], abs=1e-4) == 1.9 / 3
    assert res["pass"] is True
    assert res["effective_trials"] == 45  # max(45, 10)


def test_evaluate_forward_window_ledger_trials_monotonicity():
    """Verify that a higher verified ledger trial count increases effective trials for DSR."""
    ref_dt = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
    trades = [
        {"timestamp": (ref_dt - timedelta(days=i)).isoformat(), "outcome": "win", "rNet": 0.5 + (0.1 if i % 2 == 0 else -0.1)}
        for i in range(1, 50)
    ]

    res_baseline = hypothesis_check.evaluate_forward_window(
        shadow_log_path=trades,
        n_min=30,
        edge_min=0.1,
        dsr_min=0.4,
        window_days=90,
        now_dt=ref_dt,
        ledger_trials=10,  # Below 45 floor -> becomes 45
    )
    assert res_baseline["effective_trials"] == 45

    res_high_trials = hypothesis_check.evaluate_forward_window(
        shadow_log_path=trades,
        n_min=30,
        edge_min=0.1,
        dsr_min=0.4,
        window_days=90,
        now_dt=ref_dt,
        ledger_trials=150,  # Above 45 floor -> becomes 150
    )
    assert res_high_trials["effective_trials"] == 150
    # More trials must result in lower or equal DSR (monotonicity)
    assert res_high_trials["dsr"] <= res_baseline["dsr"]
