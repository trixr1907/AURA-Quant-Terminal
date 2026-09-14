#!/usr/bin/env python3
"""Tests for Slice B — PreReg and Hypothesis Check.

Covers:
1. Hypothesis-PreReg mandatory fields validation (setup_id, symbol, tf,
   regime_context, hypothesis, params_sha256, acceptance={n_min, edge_min, dsr_min},
   exactly one horizon type: bars or until_date, status=PREREGISTERED, frozen_at ISO).
2. scripts/append_ledger.py with explicit --prereg flag (fails on missing/invalid
   fields, appends compatible record on temp fixtures, preserves backward compatibility).
3. scripts/hypothesis_check.py (checks result against PreReg: exact hash match,
   acceptance criteria evaluation, UNREGISTERED if no match/hash mismatch with exit != 0,
   EVIDENCE_CANDIDATE on match but without lifting model verdict).
4. Strictly temp-fixture based tests with zero modifications to real ledger.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ledger  # noqa: E402


VALID_PREREG = {
    "setup_id": "SETUP-BTC-001",
    "symbol": "BTCUSDT",
    "tf": "1h",
    "regime_context": "TRENDING_BULL",
    "hypothesis": "Breakout above 20-period high with ADX > 25 generates positive edge",
    "params_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "acceptance": {
        "n_min": 30,
        "edge_min": 0.015,
        "dsr_min": 0.50,
    },
    "bars": 24,
    "status": "PREREGISTERED",
    "frozen_at": "2026-09-15T00:00:00Z",
}

VALID_PREREG_UNTIL_DATE = {
    "setup_id": "SETUP-ETH-002",
    "symbol": "ETHUSDT",
    "tf": "4h",
    "regime_context": "VOLATILE",
    "hypothesis": "Mean reversion on lower Bollinger band touch",
    "params_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "acceptance": {
        "n_min": 50,
        "edge_min": 0.02,
        "dsr_min": 0.60,
    },
    "until_date": "2026-12-31T23:59:59Z",
    "status": "PREREGISTERED",
    "frozen_at": "2026-09-15T00:00:00Z",
}


def make_temp_ledger_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """Create isolated temp legacy, chain and checkpoint files for testing."""
    legacy = tmp_path / "TRIALS_LEDGER.md"
    chain = tmp_path / "chain.jsonl"
    checkpoint = tmp_path / "ledger_checkpoint.json"

    legacy.write_bytes(b"legacy-seed-data\n")
    legacy_sha = hashlib.sha256(legacy.read_bytes()).hexdigest()

    # Create initial entry EXP-026
    entry_payload = {
        "id": "EXP-026",
        "date": "2026-09-12",
        "version": "v1.2.9",
        "type": "Prozess-Fix",
        "hypothesis": "Bootstrap entry",
        "change": "Initial chain setup",
        "success_criterion": "Valid ledger chain",
        "result": "Präregistriert",
        "delta": 0,
        "total_model_experiments": 10,
        "status": "PREREGISTERED",
        "prereg_commit": "11d46cd",
        "prev_hash": legacy_sha,
    }
    ordered = {field: entry_payload[field] for field in verify_ledger.FIELD_ORDER}
    entry_hash = hashlib.sha256(verify_ledger.canonical_entry(ordered)).hexdigest()
    entry = {**ordered, "entry_hash": entry_hash}

    chain.write_bytes(verify_ledger.canonical_record(entry))

    cp = {
        "schema_version": 1,
        "last_entry_id": "EXP-026",
        "entry_count": 1,
        "chain_head": entry_hash,
    }
    checkpoint.write_bytes(verify_ledger.canonical_checkpoint(cp))

    return legacy, chain, checkpoint, legacy_sha


# ---------------------------------------------------------------------------
# 1. Hypothesis-PreReg Field Validation Tests
# ---------------------------------------------------------------------------


def test_validate_prereg_valid_cases():
    import hypothesis_check

    # Valid with bars horizon
    assert hypothesis_check.validate_prereg(VALID_PREREG) is True

    # Valid with until_date horizon
    assert hypothesis_check.validate_prereg(VALID_PREREG_UNTIL_DATE) is True


@pytest.mark.parametrize("missing_field", [
    "setup_id", "symbol", "tf", "regime_context", "hypothesis",
    "params_sha256", "acceptance", "status", "frozen_at",
])
def test_validate_prereg_missing_mandatory_fields(missing_field):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    del data[missing_field]
    with pytest.raises(hypothesis_check.PreregValidationError, match=f"missing.*{missing_field}|invalid.*{missing_field}"):
        hypothesis_check.validate_prereg(data)


@pytest.mark.parametrize("empty_field", ["setup_id", "symbol", "tf", "regime_context", "hypothesis"])
def test_validate_prereg_empty_strings(empty_field):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    data[empty_field] = "   "
    with pytest.raises(hypothesis_check.PreregValidationError):
        hypothesis_check.validate_prereg(data)


@pytest.mark.parametrize("invalid_hash", [
    "not-a-hash",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85",   # 63 chars
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b8555",  # 65 chars
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85z",  # invalid hex
    12345,
])
def test_validate_prereg_invalid_params_sha256(invalid_hash):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    data["params_sha256"] = invalid_hash
    with pytest.raises(hypothesis_check.PreregValidationError, match="params_sha256"):
        hypothesis_check.validate_prereg(data)


@pytest.mark.parametrize("bad_acceptance", [
    None,
    "not-a-dict",
    {"edge_min": 0.01, "dsr_min": 0.5},                    # missing n_min
    {"n_min": 30, "dsr_min": 0.5},                         # missing edge_min
    {"n_min": 30, "edge_min": 0.01},                       # missing dsr_min
    {"n_min": -5, "edge_min": 0.01, "dsr_min": 0.5},       # negative n_min
    {"n_min": 0, "edge_min": 0.01, "dsr_min": 0.5},        # zero n_min
    {"n_min": "30", "edge_min": 0.01, "dsr_min": 0.5},     # n_min string
    {"n_min": 30, "edge_min": "0.01", "dsr_min": 0.5},     # edge_min string
    {"n_min": 30, "edge_min": 0.01, "dsr_min": "high"},    # dsr_min string
    {"n_min": True, "edge_min": 0.01, "dsr_min": 0.5},     # boolean n_min
])
def test_validate_prereg_invalid_acceptance(bad_acceptance):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    data["acceptance"] = bad_acceptance
    with pytest.raises(hypothesis_check.PreregValidationError, match="acceptance"):
        hypothesis_check.validate_prereg(data)


def test_validate_prereg_horizon_mutually_exclusive():
    import hypothesis_check

    # Both bars and until_date -> MUST fail
    data_both = copy.deepcopy(VALID_PREREG)
    data_both["until_date"] = "2026-12-31T00:00:00Z"
    with pytest.raises(hypothesis_check.PreregValidationError, match="horizon"):
        hypothesis_check.validate_prereg(data_both)

    # Neither bars nor until_date -> MUST fail
    data_neither = copy.deepcopy(VALID_PREREG)
    del data_neither["bars"]
    with pytest.raises(hypothesis_check.PreregValidationError, match="horizon"):
        hypothesis_check.validate_prereg(data_neither)


@pytest.mark.parametrize("bad_bars", [-1, 0, "24", 24.5, True, None])
def test_validate_prereg_invalid_bars(bad_bars):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    data["bars"] = bad_bars
    with pytest.raises(hypothesis_check.PreregValidationError, match="bars|horizon"):
        hypothesis_check.validate_prereg(data)


@pytest.mark.parametrize("bad_date", ["invalid-date", "2026-13-45", 12345, ""])
def test_validate_prereg_invalid_until_date(bad_date):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG_UNTIL_DATE)
    data["until_date"] = bad_date
    with pytest.raises(hypothesis_check.PreregValidationError, match="until_date|horizon"):
        hypothesis_check.validate_prereg(data)


@pytest.mark.parametrize("bad_status", ["COMPLETED", "DRAFT", "ACTIVE", "", None])
def test_validate_prereg_invalid_status(bad_status):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    data["status"] = bad_status
    with pytest.raises(hypothesis_check.PreregValidationError, match="status"):
        hypothesis_check.validate_prereg(data)


@pytest.mark.parametrize("bad_frozen", ["not-iso", "2026-99-99", "", None])
def test_validate_prereg_invalid_frozen_at(bad_frozen):
    import hypothesis_check

    data = copy.deepcopy(VALID_PREREG)
    data["frozen_at"] = bad_frozen
    with pytest.raises(hypothesis_check.PreregValidationError, match="frozen_at"):
        hypothesis_check.validate_prereg(data)


# ---------------------------------------------------------------------------
# 2. scripts/append_ledger.py PreReg Mode Tests
# ---------------------------------------------------------------------------


def test_append_ledger_prereg_valid(tmp_path):
    """append_ledger with --prereg flag successfully validates and appends to temp ledger."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    prereg_file = tmp_path / "prereg.json"
    prereg_file.write_text(json.dumps(VALID_PREREG, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(prereg_file),
            "--prereg",
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
            "--first-entry-id", "26",
            "--baseline-total", "10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["ok"] is True
    assert out["last_entry_id"] == "EXP-027"
    assert out["entry_count"] == 2

    # Verify that the resulting ledger verifies cleanly with verify_ledger
    verified = verify_ledger.verify_ledger(
        legacy,
        chain,
        checkpoint_path=checkpoint,
        expected_legacy_sha256=seed,
        first_entry_id=26,
        baseline_total=10,
    )
    assert verified["ok"] is True
    assert verified["last_entry_id"] == "EXP-027"
    assert verified["entry_count"] == 2


def test_append_ledger_prereg_invalid_fails(tmp_path):
    """append_ledger with --prereg flag fails if mandatory field is missing."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    bad_prereg = copy.deepcopy(VALID_PREREG)
    del bad_prereg["params_sha256"]

    prereg_file = tmp_path / "bad_prereg.json"
    prereg_file.write_text(json.dumps(bad_prereg, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(prereg_file),
            "--prereg",
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
            "--first-entry-id", "26",
            "--baseline-total", "10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    # Chain must not have been modified
    lines = chain.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_append_ledger_backward_compatibility(tmp_path):
    """Standard non-prereg entry still appends successfully without --prereg flag."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    standard_entry = {
        "date": "2026-09-15",
        "version": "v1.9.0",
        "type": "Prozess-Fix",
        "hypothesis": "Test standard entry",
        "change": "some change",
        "success_criterion": "some criterion",
        "result": "some result",
        "delta": 0,
        "status": "PREREGISTERED",
        "prereg_commit": "abcdef1",
    }
    entry_file = tmp_path / "standard.json"
    entry_file.write_text(json.dumps(standard_entry), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(entry_file),
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
            "--first-entry-id", "26",
            "--baseline-total", "10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# 3. scripts/hypothesis_check.py Verification Tests
# ---------------------------------------------------------------------------


def test_hypothesis_check_matching_candidate_passes(tmp_path):
    """Candidate matching PreReg hash and satisfying acceptance criteria gets EVIDENCE_CANDIDATE."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    # 1. Register PreReg in temp ledger
    prereg_file = tmp_path / "prereg.json"
    prereg_file.write_text(json.dumps(VALID_PREREG, indent=2), encoding="utf-8")

    proc_reg = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(prereg_file),
            "--prereg",
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
            "--first-entry-id", "26",
            "--baseline-total", "10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc_reg.returncode == 0

    # 2. Result satisfying all criteria
    result_data = {
        "setup_id": "SETUP-BTC-001",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "params_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "n": 45,            # n_min was 30 -> PASS
        "edge": 0.025,      # edge_min was 0.015 -> PASS
        "dsr": 0.65,        # dsr_min was 0.50 -> PASS
    }
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(result_data), encoding="utf-8")

    # 3. Run hypothesis_check
    proc_chk = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hypothesis_check.py"),
            "--result-file", str(result_file),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--legacy", str(legacy),
            "--expected-legacy-sha256", seed,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc_chk.returncode == 0, proc_chk.stderr
    chk = json.loads(proc_chk.stdout)
    assert chk["ok"] is True
    assert chk["verdict"] == "EVIDENCE_CANDIDATE"
    # Crucial requirement: registered match does NOT lift model verdict
    assert chk.get("model_verdict_lifted") is False


def test_hypothesis_check_unregistered_fails(tmp_path):
    """Candidate with unregistered setup_id yields UNREGISTERED and exit != 0."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    result_data = {
        "setup_id": "SETUP-UNKNOWN-999",
        "params_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "n": 50,
        "edge": 0.05,
        "dsr": 0.8,
    }
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(result_data), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hypothesis_check.py"),
            "--result-file", str(result_file),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--legacy", str(legacy),
            "--expected-legacy-sha256", seed,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    chk = json.loads(proc.stdout)
    assert chk["verdict"] == "UNREGISTERED"


def test_hypothesis_check_mismatched_hash_fails(tmp_path):
    """Candidate with registered setup_id but mismatched params_sha256 yields UNREGISTERED and exit != 0."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    # Register PreReg
    prereg_file = tmp_path / "prereg.json"
    prereg_file.write_text(json.dumps(VALID_PREREG, indent=2), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(prereg_file),
            "--prereg",
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
        ],
        cwd=ROOT,
        check=True,
    )

    # Different params_sha256
    result_data = {
        "setup_id": "SETUP-BTC-001",
        "params_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "n": 50,
        "edge": 0.05,
        "dsr": 0.8,
    }
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(result_data), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hypothesis_check.py"),
            "--result-file", str(result_file),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--legacy", str(legacy),
            "--expected-legacy-sha256", seed,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    chk = json.loads(proc.stdout)
    assert chk["verdict"] == "UNREGISTERED"


@pytest.mark.parametrize("failing_metric,bad_value", [
    ("n", 15),          # n_min is 30 -> FAIL
    ("edge", 0.005),    # edge_min is 0.015 -> FAIL
    ("dsr", 0.30),      # dsr_min is 0.50 -> FAIL
])
def test_hypothesis_check_failed_acceptance_criteria(tmp_path, failing_metric, bad_value):
    """Candidate matching hash but failing acceptance criteria fails check and exits != 0."""
    legacy, chain, checkpoint, seed = make_temp_ledger_fixture(tmp_path)

    # Register PreReg
    prereg_file = tmp_path / "prereg.json"
    prereg_file.write_text(json.dumps(VALID_PREREG, indent=2), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(prereg_file),
            "--prereg",
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
        ],
        cwd=ROOT,
        check=True,
    )

    result_data = {
        "setup_id": "SETUP-BTC-001",
        "params_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "n": 40,
        "edge": 0.02,
        "dsr": 0.60,
    }
    result_data[failing_metric] = bad_value

    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(result_data), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hypothesis_check.py"),
            "--result-file", str(result_file),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--legacy", str(legacy),
            "--expected-legacy-sha256", seed,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    chk = json.loads(proc.stdout)
    assert chk["verdict"] in ("CRITERIA_NOT_MET", "REJECTED")


def test_hypothesis_check_direct_prereg_file(tmp_path):
    """hypothesis_check directly comparing against a prereg file instead of ledger."""
    prereg_file = tmp_path / "prereg.json"
    prereg_file.write_text(json.dumps(VALID_PREREG, indent=2), encoding="utf-8")

    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({
            "setup_id": "SETUP-BTC-001",
            "params_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "n": 50,
            "edge": 0.03,
            "dsr": 0.75,
        }),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hypothesis_check.py"),
            "--result-file", str(result_file),
            "--prereg-file", str(prereg_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    chk = json.loads(proc.stdout)
    assert chk["verdict"] == "EVIDENCE_CANDIDATE"
    assert chk.get("model_verdict_lifted") is False


# ---------------------------------------------------------------------------
# 4. Invariant: Real Ledger Files Unchanged
# ---------------------------------------------------------------------------


def test_real_ledger_chain_is_untouched():
    """Verify real ledger chain and checkpoint are completely unchanged."""
    res = verify_ledger.verify_ledger()
    assert res["ok"] is True
    assert res["last_entry_id"] == "EXP-032"
    assert res["entry_count"] == 7
    assert res["total_model_experiments"] == 10
