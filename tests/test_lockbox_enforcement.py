#!/usr/bin/env python3
"""Tests for S4 Lockbox Single-Shot Enforcement in lockbox_guard.py.

Verifies:
1. Lockbox evaluation on LOCKED holdout can be recorded and transitions status to CONSUMED.
2. Attempting a second evaluation on an already CONSUMED lockbox fails closed with LockboxAlreadyConsumedError.
3. inspect_lockbox_fixtures reports LOCKBOX_ALREADY_CONSUMED and status FAIL on consumed lockbox.
4. Real golden fixtures provenance remains strictly untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lockbox_guard  # noqa: E402


def make_temp_golden_dir(tmp_path: Path) -> Path:
    g_dir = tmp_path / "golden"
    g_dir.mkdir(parents=True, exist_ok=True)

    prov = {
        "lockbox": {
            "cutoff_time": "2026-09-10T00:00:00Z",
            "locked_span_days": 60,
            "status": "LOCKED",
            "mode": "forward_holdout",
            "description": "quarantined holdout",
        },
        "BTCUSDT_1h.csv": {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "source": "TradingView/Pine",
            "export_time": "2026-09-08T00:00:00Z",
            "sha256": "dummy",
            "rows": 5,
        }
    }
    (g_dir / "provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")

    # CSV fixture (timestamp > 2026-09-10T00:00:00Z -> locked bar)
    csv_content = (
        "timestamp,open,high,low,close,volume\n"
        "1725753600000,50000,51000,49000,50500,100\n"
        "1725840000000,50500,51500,49500,51000,100\n"
        "1800000000000,60000,61000,59000,60500,100\n"  # 1800000000000 is 2027 > cutoff -> locked bar
    )
    (g_dir / "BTCUSDT_1h.csv").write_text(csv_content, encoding="utf-8")
    return g_dir


def test_lockbox_initial_state_and_first_evaluation(tmp_path: Path):
    """Initial state is LOCKED with holdout bars; first evaluation records successfully."""
    g_dir = make_temp_golden_dir(tmp_path)

    # Initial inspection
    insp = lockbox_guard.inspect_lockbox_fixtures(golden_dir=g_dir)
    assert insp["status"] == "PASS"
    assert insp["lockbox_status"] == "LOCKED"
    assert insp["total_locked_bars"] == 1

    # First evaluation consumption
    res = lockbox_guard.record_lockbox_evaluation(
        evaluation_id="EVAL-S4-001",
        evaluation_summary={"exp": 0.15, "dsr": 0.55, "trades": 35},
        golden_dir=g_dir,
    )
    assert res["ok"] is True
    assert res["status"] == "CONSUMED"


def test_lockbox_second_evaluation_blocked_fail_closed(tmp_path: Path):
    """Second evaluation attempt raises LockboxAlreadyConsumedError and inspect reports FAIL."""
    g_dir = make_temp_golden_dir(tmp_path)

    # First eval
    lockbox_guard.record_lockbox_evaluation(
        evaluation_id="EVAL-S4-001",
        evaluation_summary={"exp": 0.15},
        golden_dir=g_dir,
    )

    # Second eval must raise LockboxAlreadyConsumedError
    with pytest.raises(lockbox_guard.LockboxAlreadyConsumedError, match="LOCKBOX_ALREADY_CONSUMED"):
        lockbox_guard.record_lockbox_evaluation(
            evaluation_id="EVAL-S4-002",
            evaluation_summary={"exp": 0.18},
            golden_dir=g_dir,
        )

    # Inspection must now report FAIL
    insp = lockbox_guard.inspect_lockbox_fixtures(golden_dir=g_dir)
    assert insp["status"] == "FAIL"
    assert insp["lockbox_status"] == "CONSUMED"
    assert insp["evaluation_state"] == "LOCKBOX_ALREADY_CONSUMED"

    # evaluate_lockbox_evaluation must report FAIL
    check_status, detail, label = lockbox_guard.evaluate_lockbox_evaluation(golden_dir=g_dir)
    assert check_status == "FAIL"
    assert "LOCKBOX_ALREADY_CONSUMED" in detail
    assert label == "CONSUMED"


def test_real_provenance_lockbox_remains_locked_and_unused():
    """Verify real repository provenance.json is untouched (LOCKED and UNUSED)."""
    check_status, detail, label = lockbox_guard.evaluate_lockbox_evaluation()
    assert check_status == "PASS"
    assert label == "UNUSED"
    assert "UNUSED" in detail
