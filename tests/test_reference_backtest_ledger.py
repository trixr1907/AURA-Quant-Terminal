import json
import re
from pathlib import Path

import tests.reference_backtest as reference_backtest


ROOT = Path(__file__).resolve().parents[1]


def test_load_ledger_trials_reads_total_model_experiments(tmp_path: Path):
    checkpoint = tmp_path / "ledger_checkpoint.json"
    checkpoint.write_text(json.dumps({"total_model_experiments": 120}), encoding="utf-8")

    assert reference_backtest.load_ledger_trials(checkpoint) == 120


def test_load_ledger_trials_falls_back_for_invalid_checkpoint(tmp_path: Path):
    checkpoint = tmp_path / "ledger_checkpoint.json"
    checkpoint.write_text("{}", encoding="utf-8")

    assert reference_backtest.load_ledger_trials(checkpoint) == 10


def test_dashboard_embeds_verified_ledger_trial_total():
    dashboard = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")

    assert "const VERIFIED_LEDGER_TRIALS = 10;" in dashboard
    assert "function loadVerifiedLedgerTrials()" in dashboard
    assert "const LEGACY_PHASE_D_TRIALS = 45;" in dashboard
    assert "const DSR_TRIALS = Math.max(LEGACY_PHASE_D_TRIALS, LEDGER_TRIALS);" in dashboard
    assert re.search(r"const totalTrials\s*=\s*Math\.max\(currentSearchTrials,\s*DSR_TRIALS\);", dashboard)


def test_reference_dsr_trials_never_drop_below_legacy_floor(tmp_path: Path):
    checkpoint = tmp_path / "ledger_checkpoint.json"
    checkpoint.write_text(json.dumps({"total_model_experiments": 120}), encoding="utf-8")

    assert reference_backtest.reference_dsr_trials(checkpoint) == 120

    checkpoint.write_text(json.dumps({"total_model_experiments": 10}), encoding="utf-8")
    assert reference_backtest.reference_dsr_trials(checkpoint) == 45
