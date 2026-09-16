"""Paritaetstests: aura.core vs. tests/reference_backtest.py und Fixtures (P2).

Beweist, dass die neue modulare Python-Engine deterministisch identische
Ergebnisse zur geprueften Referenzimplementierung liefert.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from aura.core import stats
from tests import reference_backtest as ref


@pytest.fixture
def returns_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "backtest" / "returns.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def trades_fixture() -> list:
    path = Path(__file__).parent / "fixtures" / "backtest" / "trades.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_dsr_parity_with_reference(returns_fixture):
    for name, rets in returns_fixture.items():
        ref_dsr = ref.calc_dsr(rets, num_trials=18)
        new_dsr = stats.calc_dsr(rets, num_trials=18)
        assert math.isclose(ref_dsr["dsr"], new_dsr.dsr, abs_tol=1e-9), f"DSR mismatch on {name}"
        assert math.isclose(ref_dsr["sharpe"], new_dsr.sharpe, abs_tol=1e-9)
        assert math.isclose(ref_dsr["skew"], new_dsr.skew, abs_tol=1e-9)
        assert math.isclose(ref_dsr["kurt"], new_dsr.kurt, abs_tol=1e-9)


def test_pava_parity_with_reference(trades_fixture):
    ref_sampled = ref.calibrate(trades_fixture)
    new_calib_fn = stats.calibrate_probabilities(trades_fixture)

    for s_str, ref_val in ref_sampled.items():
        s = float(s_str)
        new_val = new_calib_fn(s)
        assert math.isclose(ref_val, new_val, abs_tol=1e-9), f"PAVA mismatch at score={s}"


def test_trade_evaluation_parity(trades_fixture):
    ref_ev = ref.evaluate_trades(trades_fixture)
    new_ev = stats.evaluate_trades(trades_fixture)

    assert ref_ev["total"] == new_ev.total
    assert ref_ev["wins"] == new_ev.wins
    assert ref_ev["losses"] == new_ev.losses
    assert math.isclose(ref_ev["wr"], new_ev.win_rate, abs_tol=1e-9)
    assert math.isclose(ref_ev["exp"], new_ev.expectancy_r, abs_tol=1e-9)
    assert math.isclose(ref_ev["maxDd"], new_ev.max_drawdown_r, abs_tol=1e-9)


def test_accounting_reconciliation_parity(trades_fixture):
    ref_rec = ref.reconcile(10000.0, trades_fixture, risk_per_r=100.0)
    new_rec = stats.reconcile_accounting(10000.0, trades_fixture, risk_per_r=100.0)

    assert ref_rec["ok"] == new_rec.is_reconciled
    assert math.isclose(ref_rec["startingEquity"], new_rec.starting_equity, abs_tol=1e-9)
    assert math.isclose(ref_rec["endingEquity"], new_rec.ending_equity, abs_tol=1e-9)
    assert math.isclose(ref_rec["realizedPnl"], new_rec.realized_pnl, abs_tol=1e-9)
    assert math.isclose(ref_rec["unrealizedPnl"], new_rec.unrealized_pnl, abs_tol=1e-9)
    assert math.isclose(ref_rec["fees"], new_rec.fees, abs_tol=1e-9)


def test_selection_objective_parity():
    for exp, n in [(0.5, 1), (0.2, 5), (1.1, 20)]:
        ref_obj = ref.selection_objective(exp, n, min_train_trades=2)
        new_obj = stats.selection_objective(exp, n, min_trades=2)
        assert math.isclose(ref_obj, new_obj, abs_tol=1e-9)
