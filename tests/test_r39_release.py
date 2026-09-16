from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import bitget_relay


ROOT = Path(__file__).resolve().parents[1]


def test_server_only_live_node_contract() -> None:
    result = subprocess.run(
        ["node", "tests/test_server_only_live.js"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bot_config_endpoint_persists_next_cycle_values() -> None:
    payload = {
        "profile": "strict",
        "initialEquity": 12_500,
        "riskPerTradePct": 0.75,
        "maxOpenTrades": 2,
        "minScore": 75,
        "mtfNeed": 3,
        "min24hVol": 2_000_000,
        "minOosSamples": 12,
        "minSetupDsr": 0.3,
        "stagnationHours": 8,
    }
    with patch.object(bitget_relay, "_save_shared_state", return_value=({"aura-server-bot-config-v1": payload}, 42, None)) as save:
        saved, rev, error = bitget_relay.save_server_bot_config(payload)
    assert error is None
    assert rev == 42
    assert saved["aura-server-bot-config-v1"]["minScore"] == 75
    save.assert_called_once_with("aura-server-bot-config-v1", payload)
