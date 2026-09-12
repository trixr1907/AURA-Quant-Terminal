import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
GOLDEN_FILES = [
    "BTCUSDT_1h.csv",
    "ETHUSDT_1h.csv",
    "SOLUSDT_1h.csv",
    "XRPUSDT_4h.csv",
    "DOGEUSDT_4h.csv",
]


def test_cvd_reference_script_executes_and_passes():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "cvd_reference.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert len(data["fixtures"]) == 5
    for item in data["fixtures"]:
        assert item["bars"] >= 5000
        assert item["flip_count"] == 0
        assert item["max_relative_drift"] <= 1e-10


def test_cvd_reference_detects_mutated_js_engine(tmp_path):
    import cvd_reference

    csv_path = GOLDEN_DIR / "sample_valid.csv"
    py_res = cvd_reference.compute_python_reference(csv_path)
    mutated_js = {
        "cvd": [v + 10.0 for v in py_res["cvd"]],
        "ema_cvd": list(py_res["ema_cvd"]),
        "delta": list(py_res["delta"]),
    }
    comparison = cvd_reference.compare_series("sample_valid.csv", py_res, mutated_js)
    assert comparison["flip_count"] > 0 or comparison["max_relative_drift"] > 1e-10
    assert comparison["passed"] is False
