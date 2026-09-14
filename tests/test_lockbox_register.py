#!/usr/bin/env python3
"""Tests for Slice D — Lockbox Registrar and Lockbox Guard Integration.

Covers:
1. No-op default (when --register is not specified, file remains unmodified and exits 0).
2. Registration validation (--days positive integer requirement, error on missing/invalid days).
3. Exact prompt check: 'Lockbox-Spanne ab heute für N Tage sperren? Das kann nicht rückgängig gemacht werden.'
4. Confirmed registration only on explicit 'ja' or 'yes' (case-insensitive, whitespace-trimmed).
5. Writes atomic UTC-Cutoff, positive integer days, LOCKED status, forward_holdout mode.
6. Refuses to overwrite existing LOCKED lockbox.
7. Rejection on any other input ('nein', 'no', empty, etc.) exits non-zero and leaves file untouched.
8. Full integration with scripts/lockbox_guard.py on temp fixtures (missing -> NO-GO, registered -> PASS/LOCKED, UNUSED vs HOLD_OUT_DATA_AVAILABLE).
9. Invariant: Real golden fixtures provenance.json is completely untouched.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import lockbox_guard  # noqa: E402

REAL_PROVENANCE = ROOT / "tests" / "fixtures" / "golden" / "provenance.json"


def _sample_provenance_data() -> dict:
    return {
        "BTCUSDT_1h.csv": {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "source": "TradingView/Pine",
            "export_time": "2026-09-08T00:00:00Z",
            "sha256": "460a1aee5a7e7939b74e12082726870adcf1d5731801a1f9b3123d29f72fee14",
            "rows": 100,
        }
    }


def _create_sample_csv(csv_path: Path, timestamps: list[str]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for ts in timestamps:
            writer.writerow([ts, "100.0", "105.0", "99.0", "102.0", "1000"])


# ---------------------------------------------------------------------------
# 1. No-op Default Tests
# ---------------------------------------------------------------------------


def test_noop_default_does_not_modify_file_and_exits_zero(tmp_path):
    """When --register is omitted, command is a no-op, exits 0, and leaves file unchanged."""
    prov_file = tmp_path / "provenance.json"
    initial_content = json.dumps(_sample_provenance_data(), indent=2) + "\n"
    prov_file.write_text(initial_content, encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"Expected exit 0, got {proc.returncode}: {proc.stderr}"
    assert prov_file.read_text(encoding="utf-8") == initial_content


def test_noop_default_without_args_exits_zero():
    """Default invocation with no args exits 0 without error."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "lockbox_register.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Expected exit 0, got {proc.returncode}: {proc.stderr}"


# ---------------------------------------------------------------------------
# 2. Argument Validation Tests
# ---------------------------------------------------------------------------


def test_register_missing_days_fails(tmp_path):
    """--register without --days fails with non-zero exit code."""
    prov_file = tmp_path / "provenance.json"
    prov_file.write_text(json.dumps(_sample_provenance_data()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input="ja\n",
    )
    assert proc.returncode != 0


@pytest.mark.parametrize("invalid_days", ["0", "-10", "abc", "30.5"])
def test_register_invalid_days_fails(tmp_path, invalid_days):
    """--register with non-positive integer days fails with non-zero exit code."""
    prov_file = tmp_path / "provenance.json"
    prov_file.write_text(json.dumps(_sample_provenance_data()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            invalid_days,
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input="ja\n",
    )
    assert proc.returncode != 0


# ---------------------------------------------------------------------------
# 3. Confirmation and Prompt Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("confirm_input", ["ja\n", "yes\n", "JA\n", "YES\n", "  ja  \n", "  Yes \n"])
def test_register_confirmed_writes_locked_provenance(tmp_path, confirm_input):
    """Explicit 'ja' or 'yes' confirms registration and writes atomic locked metadata."""
    prov_file = tmp_path / "provenance.json"
    sample_data = _sample_provenance_data()
    prov_file.write_text(json.dumps(sample_data, indent=2), encoding="utf-8")

    days = 60
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            str(days),
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=confirm_input,
    )

    assert proc.returncode == 0, f"Registration failed: {proc.stderr}\n{proc.stdout}"

    # Verify prompt string was present in output
    expected_prompt = f"Lockbox-Spanne ab heute für {days} Tage sperren? Das kann nicht rückgängig gemacht werden."
    combined_out = proc.stdout + proc.stderr
    assert expected_prompt in combined_out, f"Prompt '{expected_prompt}' not found in output: {combined_out}"

    # Verify written JSON structure
    updated = json.loads(prov_file.read_text(encoding="utf-8"))
    assert "lockbox" in updated
    lb = updated["lockbox"]
    assert lb["status"] == "LOCKED"
    assert lb["mode"] == "forward_holdout"
    assert lb["locked_span_days"] == 60
    assert isinstance(lb["locked_span_days"], int)

    # Cutoff time should be a valid UTC ISO timestamp of today
    cutoff = lb["cutoff_time"]
    assert cutoff.endswith("Z") or "+00:00" in cutoff
    dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    assert dt.tzinfo is not None
    today_utc = datetime.now(timezone.utc)
    assert dt.year == today_utc.year
    assert dt.month == today_utc.month
    assert dt.day == today_utc.day

    # Other fixture entries should be preserved
    assert "BTCUSDT_1h.csv" in updated
    assert updated["BTCUSDT_1h.csv"] == sample_data["BTCUSDT_1h.csv"]


@pytest.mark.parametrize("reject_input", ["nein\n", "no\n", "\n", "cancel\n", "ja nein\n", "nope\n"])
def test_register_rejected_exits_nonzero_and_leaves_file_untouched(tmp_path, reject_input):
    """Any response other than explicit ja/yes rejects registration, leaves file untouched, exits non-zero."""
    prov_file = tmp_path / "provenance.json"
    initial_content = json.dumps(_sample_provenance_data(), indent=2) + "\n"
    prov_file.write_text(initial_content, encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            "45",
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=reject_input,
    )

    assert proc.returncode != 0, f"Expected rejection exit code != 0, got {proc.returncode}"
    assert prov_file.read_text(encoding="utf-8") == initial_content


# ---------------------------------------------------------------------------
# 4. Existing LOCKED Protection
# ---------------------------------------------------------------------------


def test_cannot_overwrite_existing_locked_lockbox(tmp_path):
    """Existing LOCKED lockbox must never be overwritten, even if confirmation is provided."""
    prov_file = tmp_path / "provenance.json"
    initial_data = {
        "lockbox": {
            "cutoff_time": "2026-09-01T00:00:00Z",
            "locked_span_days": 90,
            "status": "LOCKED",
            "mode": "forward_holdout",
            "description": "Original locked lockbox",
        },
        **_sample_provenance_data(),
    }
    initial_content = json.dumps(initial_data, indent=2) + "\n"
    prov_file.write_text(initial_content, encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            "30",
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input="ja\n",
    )

    assert proc.returncode != 0, "Expected failure when attempting to overwrite LOCKED lockbox"
    # Content must be completely unchanged
    assert prov_file.read_text(encoding="utf-8") == initial_content


# ---------------------------------------------------------------------------
# 5. Lockbox Guard Integration Tests
# ---------------------------------------------------------------------------


def test_lockbox_guard_integration_unregistered_vs_registered(tmp_path):
    """Test full workflow: Guard sees unregistered -> NO-GO, then register -> LOCKED/UNUSED."""
    golden_tmp = tmp_path / "golden"
    golden_tmp.mkdir()
    prov_file = golden_tmp / "provenance.json"

    # 1. Create CSV fixture with timestamps from past
    csv_file = golden_tmp / "BTCUSDT_1h.csv"
    _create_sample_csv(
        csv_file,
        [
            "2026-08-01T00:00:00Z",
            "2026-08-01T01:00:00Z",
            "2026-08-01T02:00:00Z",
        ],
    )
    prov_data = {
        "BTCUSDT_1h.csv": {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "source": "TradingView/Pine",
            "export_time": "2026-08-01T00:00:00Z",
            "sha256": lockbox_guard.compute_file_sha256(csv_file),
            "rows": 3,
        }
    }
    prov_file.write_text(json.dumps(prov_data, indent=2), encoding="utf-8")

    # 2. Before registration: guard reports NO-GO due to missing lockbox metadata
    res_before = lockbox_guard.inspect_lockbox_fixtures(golden_tmp)
    assert res_before["status"] == "NO-GO"
    assert "lockbox metadata missing" in res_before["error"]

    status_str, detail_str, eval_state = lockbox_guard.evaluate_lockbox_evaluation(golden_tmp)
    assert status_str == "FAIL"
    assert eval_state == "ERROR"

    # 3. Register lockbox via lockbox_register.py
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            "60",
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input="ja\n",
    )
    assert proc.returncode == 0, proc.stderr

    # 4. After registration: guard recognizes LOCKED status and eval_state is UNUSED
    res_after = lockbox_guard.inspect_lockbox_fixtures(golden_tmp)
    assert res_after["status"] == "PASS"
    assert res_after["lockbox_status"] == "LOCKED"
    assert res_after["mode"] == "forward_holdout"
    assert res_after["locked_span_days"] == 60
    assert res_after["total_locked_bars"] == 0
    assert res_after["evaluation_state"] == "UNUSED"

    eval_status, eval_detail, eval_label = lockbox_guard.evaluate_lockbox_evaluation(golden_tmp)
    assert eval_status == "PASS"
    assert eval_label == "UNUSED"
    assert "lockbox-eval: UNUSED" in eval_detail


def test_lockbox_guard_with_locked_holdout_bars(tmp_path):
    """When fixture contains bars >= cutoff_time, guard recognizes HOLD_OUT_DATA_AVAILABLE."""
    golden_tmp = tmp_path / "golden"
    golden_tmp.mkdir()
    prov_file = golden_tmp / "provenance.json"

    # Cutoff is today (or registered today). Add 2 bars before today, 3 bars after cutoff
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    csv_file = golden_tmp / "BTCUSDT_1h.csv"
    _create_sample_csv(
        csv_file,
        [
            "2026-01-01T00:00:00Z",
            "2026-01-01T01:00:00Z",
            today_iso,
            "2026-12-31T22:00:00Z",
            "2026-12-31T23:00:00Z",
        ],
    )

    prov_file.write_text(json.dumps(_sample_provenance_data()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            "90",
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input="yes\n",
    )
    assert proc.returncode == 0

    res = lockbox_guard.inspect_lockbox_fixtures(golden_tmp)
    assert res["status"] == "PASS"
    assert res["lockbox_status"] == "LOCKED"
    assert res["total_locked_bars"] == 3
    assert res["evaluation_state"] == "HOLD_OUT_DATA_AVAILABLE"

    eval_status, eval_detail, eval_label = lockbox_guard.evaluate_lockbox_evaluation(golden_tmp)
    assert eval_status == "PASS"
    assert eval_label == "HOLD_OUT_DATA_AVAILABLE"
    assert "3 bars locked" in eval_detail


# ---------------------------------------------------------------------------
# 6. Direct Function & Edge Case Tests
# ---------------------------------------------------------------------------


def test_register_lockbox_direct_api(tmp_path):
    """Test register_lockbox function directly with custom cutoff and prompt_fn."""
    import lockbox_register

    prov_file = tmp_path / "subdir" / "provenance.json"
    res = lockbox_register.register_lockbox(
        provenance_path=prov_file,
        days=30,
        cutoff_time="2026-09-15T12:00:00Z",
        prompt_fn=lambda prompt: "ja",
    )

    assert res["ok"] is True
    assert res["status"] == "LOCKED"
    assert res["cutoff_time"] == "2026-09-15T12:00:00Z"
    assert res["locked_span_days"] == 30

    data = json.loads(prov_file.read_text(encoding="utf-8"))
    assert data["lockbox"]["cutoff_time"] == "2026-09-15T12:00:00Z"


def test_register_lockbox_invalid_json_fails(tmp_path):
    """Corrupted JSON in provenance file raises LockboxError and exits non-zero."""
    prov_file = tmp_path / "provenance.json"
    prov_file.write_text("{corrupted-json", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lockbox_register.py"),
            "--register",
            "--days",
            "30",
            "--provenance",
            str(prov_file),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input="ja\n",
    )
    assert proc.returncode != 0


# ---------------------------------------------------------------------------
# 7. Invariant: Real Fixture Untouched
# ---------------------------------------------------------------------------


def test_real_golden_provenance_untouched():
    """Verify that the real tests/fixtures/golden/provenance.json is valid and unchanged."""
    assert REAL_PROVENANCE.exists(), "Real golden provenance.json must exist"
    prov = json.loads(REAL_PROVENANCE.read_text(encoding="utf-8"))
    assert "lockbox" in prov
    assert prov["lockbox"]["status"] == "LOCKED"
    assert prov["lockbox"]["mode"] == "forward_holdout"
    assert prov["lockbox"]["locked_span_days"] == 60
    assert prov["lockbox"]["cutoff_time"] == "2026-09-10T00:00:00Z"
