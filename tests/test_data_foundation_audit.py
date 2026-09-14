#!/usr/bin/env python3
"""Tests for scripts/data_foundation_audit.py (Slice A — Data Foundation Audit)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import data_foundation_audit  # type: ignore


GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"


def test_audit_golden_fixtures_offline():
    """Audit standard golden master fixtures directory offline."""
    report = data_foundation_audit.audit_directory(GOLDEN_DIR)
    assert report["ok"] is True
    assert "fixtures" in report
    assert len(report["fixtures"]) >= 5

    # Check that standard symbols are present
    symbols = {f["symbol"] for f in report["fixtures"]}
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"}.issubset(symbols)

    for item in report["fixtures"]:
        assert item["total_candles"] >= 5000 or item["filename"] == "sample_valid.csv"
        assert item["closed_candles"] == item["total_candles"]
        assert item["duplicates"] == 0
        assert item["null_or_zero_candles"] == 0
        assert item["outliers"] == 0
        if item["filename"] != "sample_valid.csv":
            assert item["provenance"] == "real"
            assert item["wf_eligible"] is True
            assert item["start_iso"] is not None
            assert item["end_iso"] is not None


def test_audit_detects_duplicates_and_gaps(tmp_path):
    """Detect duplicate timestamps and time gaps."""
    csv_file = tmp_path / "TEST_1h.csv"
    base_ts = 1700000000  # seconds
    step = 3600

    # 10 bars, with 1 duplicate at index 2, and 1 gap (skips index 5)
    rows = [
        ["time", "open", "high", "low", "close", "volume"],
        [base_ts + 0 * step, 100, 105, 95, 102, 1000],
        [base_ts + 1 * step, 102, 106, 101, 104, 1100],
        [base_ts + 1 * step, 102, 106, 101, 104, 1100],  # duplicate
        [base_ts + 2 * step, 104, 108, 103, 105, 1200],
        [base_ts + 3 * step, 105, 107, 102, 103, 1300],
        [base_ts + 5 * step, 103, 109, 100, 108, 1400],  # gap of 1 bar (step*2)
        [base_ts + 6 * step, 108, 110, 105, 107, 1500],
    ]
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    result = data_foundation_audit.audit_csv_file(csv_file)
    assert result["total_candles"] == 7
    assert result["duplicates"] == 1
    assert result["gaps"] == 1
    assert result["null_or_zero_candles"] == 0
    assert result["outliers"] == 0


def test_audit_detects_null_and_outlier_candles(tmp_path):
    """Detect null, zero, negative prices and geometric outliers."""
    csv_file = tmp_path / "ANOMALY_1h.csv"
    base_ts = 1700000000
    step = 3600

    rows = [
        ["timestamp", "open", "high", "low", "close", "volume"],
        [base_ts + 0 * step, 100, 105, 95, 102, 1000],          # normal
        [base_ts + 1 * step, 0, 105, 95, 102, 1000],            # zero open (null/zero)
        [base_ts + 2 * step, 100, 90, 95, 92, 1000],            # high < low (outlier)
        [base_ts + 3 * step, 100, 105, 95, 110, 1000],          # close > high (outlier)
        [base_ts + 4 * step, "", 105, 95, 102, 1000],           # empty open (null/zero)
        [base_ts + 5 * step, 100, 105, 95, 102, -50],           # negative volume (null/zero)
    ]
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    result = data_foundation_audit.audit_csv_file(csv_file)
    assert result["null_or_zero_candles"] >= 3
    assert result["outliers"] >= 2


def test_provenance_never_guessed(tmp_path):
    """Ensure provenance is strictly classified as real, synthetic, or unknown."""
    # 1. Unknown provenance (no metadata, no column)
    csv_unknown = tmp_path / "UNKNOWN_1h.csv"
    with csv_unknown.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        writer.writerow([1700000000, 100, 105, 95, 102, 1000])

    res_unknown = data_foundation_audit.audit_csv_file(csv_unknown)
    assert res_unknown["provenance"] == "unknown"

    # 2. Explicit synthetic metadata or column
    csv_synthetic = tmp_path / "SYNTH_1h.csv"
    with csv_synthetic.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume", "provenance"])
        writer.writerow([1700000000, 100, 105, 95, 102, 1000, "synthetic"])

    res_synth = data_foundation_audit.audit_csv_file(csv_synthetic)
    assert res_synth["provenance"] == "synthetic"

    # 3. Explicit real metadata from provenance dict
    metadata = {"source": "TradingView/Pine", "symbol": "BTCUSDT", "timeframe": "1h"}
    res_real = data_foundation_audit.audit_csv_file(csv_unknown, metadata=metadata)
    assert res_real["provenance"] == "real"


def test_wf_eligibility_threshold(tmp_path):
    """Test Walk-Forward eligibility checks based on bar counts and integrity."""
    csv_file = tmp_path / "SHORT_1h.csv"
    base_ts = 1700000000
    step = 3600

    rows = [["time", "open", "high", "low", "close", "volume"]]
    for i in range(100):
        rows.append([base_ts + i * step, 100, 105, 95, 102, 1000])

    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    # With min_wf_bars=500, 100 bars should NOT be eligible
    res = data_foundation_audit.audit_csv_file(csv_file, min_wf_bars=500)
    assert res["wf_eligible"] is False

    # With min_wf_bars=50, 100 bars SHOULD be eligible
    res_pass = data_foundation_audit.audit_csv_file(csv_file, min_wf_bars=50)
    assert res_pass["wf_eligible"] is True


def test_audit_bitget_fetch_mocked(monkeypatch):
    """Audit Bitget public candle fetch source."""
    mock_candles = {
        "code": "00000",
        "msg": "success",
        "data": [
            ["1700000000000", "100.0", "105.0", "95.0", "102.0", "500.0", "51000.0"],
            ["1700003600000", "102.0", "108.0", "101.0", "106.0", "600.0", "63600.0"],
            ["1700007200000", "106.0", "110.0", "104.0", "109.0", "700.0", "76300.0"],
        ]
    }

    def mock_fetch(url, timeout=15):
        return mock_candles

    monkeypatch.setattr(data_foundation_audit, "fetch_json", mock_fetch)

    res = data_foundation_audit.audit_bitget(symbol="BTCUSDT", timeframe="1H", limit=3)
    assert res["symbol"] == "BTCUSDT"
    assert res["timeframe"] == "1H"
    assert res["total_candles"] == 3
    assert res["provenance"] == "real"
    assert res["duplicates"] == 0
    assert res["outliers"] == 0


def test_cli_smoke_offline_exit_0():
    """Verify standard CLI run on golden fixtures prints table and exits 0."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "data_foundation_audit.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "BTCUSDT" in proc.stdout
    assert "ETHUSDT" in proc.stdout
    assert "SOLUSDT" in proc.stdout
    assert "XRPUSDT" in proc.stdout
    assert "DOGEUSDT" in proc.stdout


def test_cli_json_output(tmp_path):
    """Verify CLI --json and --json-out options."""
    json_path = tmp_path / "audit.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "data_foundation_audit.py"),
            "--json-out",
            str(json_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert json_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert len(data["fixtures"]) >= 5

    # Also test stdout --json
    proc_json = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "data_foundation_audit.py"),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc_json.returncode == 0
    stdout_data = json.loads(proc_json.stdout)
    assert stdout_data["ok"] is True


def test_cli_file_and_strict_mode(tmp_path):
    """Verify CLI --file and --strict flags."""
    # Auditing a valid golden file with strict should pass
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "data_foundation_audit.py"),
            "--file",
            str(GOLDEN_DIR / "BTCUSDT_1h.csv"),
            "--strict",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0

    # Auditing sample_valid (1 bar) with default threshold 1000 and strict should exit 1
    proc_fail = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "data_foundation_audit.py"),
            "--file",
            str(GOLDEN_DIR / "sample_valid.csv"),
            "--strict",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc_fail.returncode == 1


def test_parse_timestamp_variations():
    """Verify timestamp parser handles ms, seconds, and ISO formats."""
    assert data_foundation_audit.parse_timestamp_ms(1700000000) == 1700000000000
    assert data_foundation_audit.parse_timestamp_ms(1700000000000) == 1700000000000
    assert data_foundation_audit.parse_timestamp_ms("1700000000") == 1700000000000
    assert data_foundation_audit.parse_timestamp_ms("2024-01-01T00:00:00Z") == 1704067200000
    assert data_foundation_audit.parse_timestamp_ms("invalid") is None
    assert data_foundation_audit.parse_timestamp_ms(None) is None


def test_empty_series_audit():
    """Verify auditing empty series fail-safely returns 0 stats and wf_eligible False."""
    res = data_foundation_audit.audit_candle_series([], symbol="EMPTY", timeframe="1h")
    assert res["total_candles"] == 0
    assert res["wf_eligible"] is False
    assert "errors" in res

