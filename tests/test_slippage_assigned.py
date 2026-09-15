import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")


def test_dashboard_has_nonzero_slippage_default_and_spec_assignment():
    assert re.search(r"fees:\s*\{\s*taker:\s*null,\s*maker:\s*null\s*\},\s*slippage:\s*0\.0005\b", DASHBOARD)
    assert re.search(r"App\.slippage\s*=\s*[^;]+", DASHBOARD)


def test_contract_spec_slippage_falls_back_when_missing_or_zero():
    assignment = re.search(r"App\.slippage\s*=\s*([^;]+);", DASHBOARD)
    assert assignment is not None
    expression = assignment.group(1)
    assert "spec.slippage" in expression
    assert "0.0005" in expression
    assert "||" in expression, "zero must be treated as an invalid slippage spec"


def test_walk_forward_callers_normalize_zero_slippage():
    assert "function resolveSlippage" in DASHBOARD
    calls_with_app_slippage = re.findall(
        r"runWalkForwardBacktest\([^;]+?App\.slippage[^;]+?\);",
        DASHBOARD,
        flags=re.DOTALL,
    )
    assert len(calls_with_app_slippage) == 3
    assert all("slippage: resolveSlippage(App.slippage)" in call for call in calls_with_app_slippage)
    assert re.search(
        r"const slippage = resolveSlippage\(options\.slippage \?\?.+?App\.slippage.+?\);",
        DASHBOARD,
    )
