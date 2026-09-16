#!/usr/bin/env python3
"""Tests for Cost Model Unification (F3: S3 = S5 canonical costs 0.1% / 0.1% / 0.1%).

Verifies that all 5 evidence and execution paths in the repository share identical
canonical cost defaults: makerFee = 0.001 (0.1%), takerFee = 0.001 (0.1%), slippage = 0.001 (0.1%):
1. Symbiose_Dashboard.html (App.slippage default, resolveSlippage fallback, evaluateTimeStopOptions defaults, simulateRange fee defaults)
2. tests/model_evidence_real.js (golden fixture WF baseline options)
3. tests/reference_backtest.py (DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE, DEFAULT_SLIPPAGE)
4. shadow_collector.js (DEFAULT_COSTS = { makerFee: 0.001, takerFee: 0.001, slippage: 0.001 })
5. headless_autobot.js (DEFAULT_CONFIG = { makerFee: 0.001, takerFee: 0.001, slippage: 0.001 })
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import reference_backtest  # noqa: E402


def test_dashboard_cost_model_defaults():
    """Path 1: Verify Dashboard HTML specifies canonical 0.001/0.001/0.001 defaults."""
    html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")

    # App initial state: slippage 0.001
    assert re.search(r"fees:\s*\{\s*taker:\s*null,\s*maker:\s*null\s*\},\s*slippage:\s*0\.001\b", html)

    # resolveSlippage fallback returns 0.001
    assert re.search(r"function\s+resolveSlippage\(value\)\s*\{\s*return\s+Number\.isFinite\(\+value\)\s*&&\s*\+value\s*>\s*0\s*\?\s*\+value\s*:\s*0\.001;", html)

    # evaluateTimeStopOptions uses 0.001 defaults
    assert re.search(r"makerFee\s*=\s*options\.makerFee\s*\?\?\s*\(.+?\?\s*App\.fees\?\.maker\s*:\s*0\.001\)\s*\?\?\s*0\.001;", html)
    assert re.search(r"takerFee\s*=\s*options\.takerFee\s*\?\?\s*\(.+?\?\s*App\.fees\?\.taker\s*:\s*0\.001\)\s*\?\?\s*0\.001;", html)
    assert re.search(r"slippage\s*=\s*resolveSlippage\(options\.slippage\s*\?\?\s*\(.+?\?\s*App\.slippage\s*:\s*0\.001\)\);", html)

    # simulateRange fallback fees: 0.001
    assert re.search(r"entryFee\s*=\s*params\.makerFee\s*!=\s*null\s*\?\s*params\.makerFee\s*:\s*\(params\.takerFee\s*!=\s*null\s*\?\s*params\.takerFee\s*:\s*0\.001\);", html)
    assert re.search(r"exitFee\s*=\s*params\.takerFee\s*!=\s*null\s*\?\s*params\.takerFee\s*:\s*0\.001;", html)


def test_model_evidence_real_cost_defaults():
    """Path 2: Verify tests/model_evidence_real.js uses 0.001/0.001/0.001."""
    js = (ROOT / "tests" / "model_evidence_real.js").read_text(encoding="utf-8")

    assert "makerFee: 0.001" in js
    assert "takerFee: 0.001" in js
    assert "slippage: 0.001" in js
    assert "makerFee: 0.0002" not in js
    assert "takerFee: 0.0006" not in js
    assert "slippage: 0.0005" not in js


def test_reference_backtest_cost_defaults():
    """Path 3: Verify tests/reference_backtest.py constants are 0.001."""
    assert reference_backtest.DEFAULT_MAKER_FEE == 0.001
    assert reference_backtest.DEFAULT_TAKER_FEE == 0.001
    assert reference_backtest.DEFAULT_SLIPPAGE == 0.001


def test_shadow_collector_cost_defaults():
    """Path 4: Verify shadow_collector.js uses DEFAULT_COSTS with 0.001."""
    js = (ROOT / "shadow_collector.js").read_text(encoding="utf-8")

    assert re.search(r"const\s+DEFAULT_COSTS\s*=\s*\{[^}]*makerFee:\s*0\.001[^}]*takerFee:\s*0\.001[^}]*slippage:\s*0\.001[^}]*\};", js, re.DOTALL)


def test_headless_autobot_cost_defaults():
    """Path 5: Verify headless_autobot.js profile defaults use 0.001/0.001/0.001."""
    js = (ROOT / "headless_autobot.js").read_text(encoding="utf-8")

    assert re.search(r"makerFee:\s*0\.001,\s*takerFee:\s*0\.001,\s*slippage:\s*0\.001", js)
