"""Pytest wrapper for the separate real online smoke test."""
from __future__ import annotations

import os
import pytest

from scripts.smoke_test_market_data_online import run_online_smoke


@pytest.mark.online
def test_real_bitget_public_market_data_online_smoke():
    """Separater echter Online-Smoke-Test mit kleinem Universum (BTCUSDT, ETHUSDT)."""
    if os.environ.get("AURA_SKIP_ONLINE_SMOKE") == "1":
        pytest.skip("AURA_SKIP_ONLINE_SMOKE=1 gesetzt")

    report = run_online_smoke(["BTCUSDT", "ETHUSDT"])
    if report["status"] == "NOT_RUN":
        pytest.skip(f"Bitget API offline oder nicht erreichbar: {report['errors']}")

    assert report["status"] == "PASS", f"Online smoke test failed: {report['errors']}"
    assert report["contracts_fetched"] > 0
    assert report["tickers_fetched"] > 0
    assert "BTCUSDT" in report["assessments"]
    assert "ETHUSDT" in report["assessments"]
