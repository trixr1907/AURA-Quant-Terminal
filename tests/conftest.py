"""Global pytest configuration and isolation fixtures."""
from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def isolate_market_data_network_sync(monkeypatch):
    """
    Prevent offline tests from accidentally making live background HTTP calls
    to Bitget market endpoints, preserving test-harness isolation.
    """
    if "AURA_DISABLE_AUTO_SYNC" not in os.environ:
        monkeypatch.setenv("AURA_DISABLE_AUTO_SYNC", "1")
