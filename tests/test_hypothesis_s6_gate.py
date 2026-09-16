#!/usr/bin/env python3
"""Tests for S6 Elevation Gate and Evidence Decay in hypothesis_check.py.

Verifies:
1. S6 elevation requires BOTH S4 Single-Shot Lockbox Pass AND S5 Forward 90-Day Window Criteria.
2. Case (a): Missing or UNUSED lockbox holdout -> model_verdict_lifted: False.
3. Case (b): Lockbox passes, but shadow log has <90d coverage or n < n_min -> model_verdict_lifted: False.
4. Case (c): Both S4 and S5 pass across synthetic 90-day fixture (100 trades, edge +0.2R, DSR > 0.5) -> model_verdict_lifted: True, verdict: S6_PRODUCTION_ELIGIBLE.
5. Case (d): Decay: forward 90d window has negative edge -> model_verdict_lifted: False, status: DECAYED_DEGRADED.
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


PREREG_SETUP = {
    "setup_id": "SETUP-S6-TEST-001",
    "symbol": "BTCUSDT",
    "tf": "1h",
    "regime_context": "TRENDING_BULL",
    "hypothesis": "S6 production eligibility test",
    "params_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    "acceptance": {
        "n_min": 30,
        "edge_min": 0.05,
        "dsr_min": 0.50,
    },
    "bars": 24,
    "status": "PREREGISTERED",
    "frozen_at": "2026-06-01T00:00:00Z",
}

CANDIDATE_RESULT = {
    "setup_id": "SETUP-S6-TEST-001",
    "params_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    "n": 50,
    "edge": 0.15,
    "dsr": 0.65,
}


def generate_synthetic_shadow_trades(
    count: int = 100,
    days_span: int = 90,
    base_edge: float = 0.20,
    now_dt: datetime | None = None,
) -> list[dict]:
    """Generate synthetic forward trades evenly spaced over days_span."""
    end_dt = now_dt or datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
    start_dt = end_dt - timedelta(days=days_span)
    trades = []
    step_sec = (days_span * 86400) / max(1, count)

    for i in range(count):
        trade_dt = start_dt + timedelta(seconds=i * step_sec)
        # Alternate wins/losses to produce positive mean edge ~ base_edge
        # e.g. +1.5R and -1.0R with win rate ~ 48% -> mean ~ +0.20R
        if i % 5 in (0, 1, 2):
            r_net = base_edge + 1.10
            outcome = "hit_tp1"
        else:
            r_net = base_edge - 1.15
            outcome = "hit_sl"

        trades.append({
            "timestamp": trade_dt.isoformat(),
            "symbol": "BTCUSDT",
            "tf": "1h",
            "decision": "ACCEPTED",
            "outcome": outcome,
            "rNet": r_net,
        })
    return trades


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_s6_gate_case_a_no_lockbox_pass():
    """Case (a): No lockbox pass (e.g. UNUSED or unverified) -> model_verdict_lifted is False."""
    shadow_trades = generate_synthetic_shadow_trades(count=100, days_span=90, base_edge=0.20)

    # UNUSED lockbox evaluation
    lockbox_unused = {
        "status": "LOCKED",
        "evaluation_state": "UNUSED",
        "holdout_pass": False,
    }

    chk = hypothesis_check.check_hypothesis(
        CANDIDATE_RESULT,
        prereg_list=[PREREG_SETUP],
        shadow_log_path=shadow_trades,
        lockbox_path=lockbox_unused,
    )

    assert chk["ok"] is True
    assert chk["model_verdict_lifted"] is False
    assert chk["model_verdict"] == "MODEL_NO_EVIDENCE"
    assert chk["verdict"] == "EVIDENCE_CANDIDATE"
    assert chk["lockbox_check"]["pass"] is False


def test_s6_gate_case_b_lockbox_pass_but_shadow_insufficient():
    """Case (b): Lockbox pass exists, but shadow log has n < n_min or insufficient window -> False."""
    # S4 Lockbox passes
    lockbox_passed = {
        "status": "LOCKED",
        "evaluation_state": "PASSED",
        "holdout_pass": True,
        "n": 40,
        "edge": 0.18,
        "dsr": 0.62,
    }

    # Only 10 trades in shadow log (n_min is 30)
    shadow_trades_short = generate_synthetic_shadow_trades(count=10, days_span=90, base_edge=0.20)

    chk = hypothesis_check.check_hypothesis(
        CANDIDATE_RESULT,
        prereg_list=[PREREG_SETUP],
        shadow_log_path=shadow_trades_short,
        lockbox_path=lockbox_passed,
    )

    assert chk["ok"] is True
    assert chk["model_verdict_lifted"] is False
    assert chk["model_verdict"] == "MODEL_NO_EVIDENCE"
    assert chk["lockbox_check"]["pass"] is True
    assert chk["forward_window_check"]["pass"] is False
    assert chk["forward_window_check"]["n"] == 10


def test_s6_gate_case_c_both_s4_and_s5_pass_elevates_to_s6():
    """Case (c): Both S4 Lockbox AND S5 90-day forward window pass -> model_verdict_lifted is True."""
    lockbox_passed = {
        "status": "LOCKED",
        "evaluation_state": "PASSED",
        "holdout_pass": True,
        "n": 60,
        "edge": 0.22,
        "dsr": 0.68,
    }

    # 100 trades over 90 days with positive edge and healthy DSR
    ref_dt = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
    shadow_trades = generate_synthetic_shadow_trades(count=100, days_span=90, base_edge=0.20, now_dt=ref_dt)

    chk = hypothesis_check.check_hypothesis(
        CANDIDATE_RESULT,
        prereg_list=[PREREG_SETUP],
        shadow_log_path=shadow_trades,
        lockbox_path=lockbox_passed,
        now_dt=ref_dt,
    )

    assert chk["ok"] is True
    assert chk["model_verdict_lifted"] is True
    assert chk["model_verdict"] == "EVIDENCE_CONFIRMED"
    assert chk["verdict"] == "S6_PRODUCTION_ELIGIBLE"
    assert chk["status"] == "S6_PRODUCTION_ELIGIBLE"
    assert chk["lockbox_check"]["pass"] is True
    assert chk["forward_window_check"]["pass"] is True
    assert chk["decay_check"]["decayed"] is False


def test_s6_gate_case_d_evidence_decay_demotes():
    """Case (d): Decay: forward performance in 90d window drops negative -> False + degradation."""
    lockbox_passed = {
        "status": "LOCKED",
        "evaluation_state": "PASSED",
        "holdout_pass": True,
    }

    # 50 trades in 90d window but negative edge (-0.15R)
    ref_dt = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
    decayed_trades = generate_synthetic_shadow_trades(count=50, days_span=90, base_edge=-0.15, now_dt=ref_dt)

    chk = hypothesis_check.check_hypothesis(
        CANDIDATE_RESULT,
        prereg_list=[PREREG_SETUP],
        shadow_log_path=decayed_trades,
        lockbox_path=lockbox_passed,
        now_dt=ref_dt,
    )

    assert chk["ok"] is True
    assert chk["model_verdict_lifted"] is False
    assert chk["model_verdict"] == "MODEL_NO_EVIDENCE"
    assert chk["status"] == "DECAYED_DEGRADED"
    assert chk["decay_check"]["decayed"] is True
    assert "DEMOTE" in chk["decay_check"]["action"]
