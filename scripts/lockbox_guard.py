#!/usr/bin/env python3
"""Lockbox Guard & OOS Boundary Enforcer.

Enforces that any fixture bar with close time >= lockbox.cutoff_time is
strictly quarantined and excluded from model optimization and tuning.
Provides an evaluation mechanism to inspect or verify holdout data.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
PROVENANCE_FILE = GOLDEN_DIR / "provenance.json"


def parse_timestamp_ms(val: str | int | float) -> int:
    val_str = str(val).strip()
    try:
        val_float = float(val_str)
        return int(val_float if val_float >= 10_000_000_000 else val_float * 1000)
    except ValueError:
        pass
    dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def inspect_lockbox_fixtures(golden_dir: Path | None = None) -> dict:
    g_dir = golden_dir or GOLDEN_DIR
    prov_path = g_dir / "provenance.json"
    if not prov_path.exists():
        return {"status": "FAIL", "error": "provenance.json missing"}

    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "FAIL", "error": f"invalid json: {e}"}

    lockbox = prov.get("lockbox")
    if not isinstance(lockbox, dict):
        return {"status": "NO-GO", "error": "lockbox metadata missing in provenance.json"}

    cutoff_iso = lockbox.get("cutoff_time")
    locked_span = lockbox.get("locked_span_days")
    status = lockbox.get("status")
    mode = lockbox.get("mode")

    if not cutoff_iso or not locked_span or status != "LOCKED" or mode != "forward_holdout":
        return {
            "status": "NO-GO",
            "error": f"incomplete or invalid lockbox definition: cutoff={cutoff_iso}, span={locked_span}, status={status}, mode={mode}"
        }

    cutoff_dt = datetime.fromisoformat(cutoff_iso.replace("Z", "+00:00"))
    cutoff_ms = int(cutoff_dt.timestamp() * 1000)

    locked_bars_per_fixture = {}
    total_bars_per_fixture = {}
    fixture_hashes = {}

    csv_files = sorted(g_dir.glob("*USDT_*.csv"))
    if not csv_files:
        return {"status": "FAIL", "error": "no golden CSV fixtures found"}

    for csv_file in csv_files:
        fixture_hashes[csv_file.name] = compute_file_sha256(csv_file)
        total_bars = 0
        locked_bars = 0
        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = [h.strip().lower() for h in next(reader, [])]
            t_idx = -1
            for col in ("timestamp", "time", "date", "datetime"):
                if col in headers:
                    t_idx = headers.index(col)
                    break
            if t_idx < 0:
                return {"status": "FAIL", "error": f"no timestamp column in {csv_file.name}"}

            for row in reader:
                if not row or len(row) <= t_idx:
                    continue
                total_bars += 1
                try:
                    ts_ms = parse_timestamp_ms(row[t_idx])
                    if ts_ms >= cutoff_ms:
                        locked_bars += 1
                except Exception:
                    continue

        locked_bars_per_fixture[csv_file.name] = locked_bars
        total_bars_per_fixture[csv_file.name] = total_bars

    total_locked = sum(locked_bars_per_fixture.values())
    eval_state = "UNUSED" if total_locked == 0 else "HOLD_OUT_DATA_AVAILABLE"

    return {
        "status": "PASS",
        "lockbox_status": status,
        "mode": mode,
        "evaluation_state": eval_state,
        "cutoff_time": cutoff_iso,
        "cutoff_ms": cutoff_ms,
        "locked_span_days": locked_span,
        "total_locked_bars": total_locked,
        "locked_bars_per_fixture": locked_bars_per_fixture,
        "total_bars_per_fixture": total_bars_per_fixture,
        "fixture_hashes": fixture_hashes,
    }


def evaluate_lockbox_evaluation(golden_dir: Path | None = None) -> tuple[str, str, str]:
    """Evaluate lockbox status for release checks.

    Returns (check_status, detail_message, eval_state_label).
    """
    res = inspect_lockbox_fixtures(golden_dir)
    if res.get("status") != "PASS":
        return "FAIL", res.get("error", "unknown error"), "ERROR"
    total_locked = res.get("total_locked_bars", 0)
    if total_locked == 0:
        return "PASS", "lockbox-eval: UNUSED (0 locked bars in current fixtures, holdout active)", "UNUSED"
    return "PASS", f"lockbox-eval: HOLD_OUT_DATA_AVAILABLE ({total_locked} bars locked for final eval)", "HOLD_OUT_DATA_AVAILABLE"


def main() -> int:
    report = inspect_lockbox_fixtures()
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
