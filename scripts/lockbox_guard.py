#!/usr/bin/env python3
"""Lockbox Guard & OOS Boundary Enforcer.

Enforces that any fixture bar with close time >= lockbox.cutoff_time is
strictly quarantined and excluded from model optimization and tuning.
Provides single-shot evaluation enforcement: if a LOCKED holdout has
already been evaluated / consumed, any second evaluation is blocked fail-closed
with LOCKBOX_ALREADY_CONSUMED.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
PROVENANCE_FILE = GOLDEN_DIR / "provenance.json"


class LockboxGuardError(Exception):
    """Base exception for lockbox guard failures."""


class LockboxAlreadyConsumedError(LockboxGuardError):
    """Raised when attempting to evaluate a lockbox holdout that was already consumed."""


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

    if status == "CONSUMED":
        return {
            "status": "FAIL",
            "lockbox_status": "CONSUMED",
            "evaluation_state": "LOCKBOX_ALREADY_CONSUMED",
            "error": "Lockbox holdout has already been evaluated and consumed. Second evaluation is prohibited.",
            "consumed_at": lockbox.get("consumed_at"),
            "evaluation_id": lockbox.get("evaluation_id"),
        }

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


def record_lockbox_evaluation(
    evaluation_id: str,
    evaluation_summary: dict,
    golden_dir: Path | None = None,
) -> dict:
    """Record a single-shot lockbox evaluation and mark the lockbox as CONSUMED.

    Fail-closed: refuses if already CONSUMED.
    """
    g_dir = golden_dir or GOLDEN_DIR
    prov_path = g_dir / "provenance.json"
    if not prov_path.exists():
        raise LockboxGuardError(f"provenance file not found: {prov_path}")

    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    lockbox = prov.get("lockbox", {})

    if lockbox.get("status") == "CONSUMED":
        raise LockboxAlreadyConsumedError(
            f"LOCKBOX_ALREADY_CONSUMED: Lockbox was already evaluated on {lockbox.get('consumed_at')} "
            f"(eval ID: {lockbox.get('evaluation_id')}). Second evaluation is strictly prohibited."
        )

    if lockbox.get("status") != "LOCKED":
        raise LockboxGuardError(f"Cannot consume lockbox with status {lockbox.get('status')!r} (must be LOCKED)")

    consumed_at = datetime.now(timezone.utc).isoformat()
    new_lockbox = {
        **lockbox,
        "status": "CONSUMED",
        "consumed_at": consumed_at,
        "evaluation_id": str(evaluation_id),
        "evaluation_summary": evaluation_summary,
    }

    new_prov = {
        **prov,
        "lockbox": new_lockbox,
    }

    # Atomic write
    temp_file = prov_path.with_name(f".{prov_path.name}.tmp.{os.getpid()}")
    try:
        temp_file.write_text(json.dumps(new_prov, indent=2) + "\n", encoding="utf-8")
        temp_file.replace(prov_path)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass

    return {
        "ok": True,
        "status": "CONSUMED",
        "consumed_at": consumed_at,
        "evaluation_id": str(evaluation_id),
    }


def evaluate_lockbox_evaluation(golden_dir: Path | None = None) -> tuple[str, str, str]:
    """Evaluate lockbox status for release checks.

    Returns (check_status, detail_message, eval_state_label).
    """
    res = inspect_lockbox_fixtures(golden_dir)
    if res.get("evaluation_state") == "LOCKBOX_ALREADY_CONSUMED":
        return "FAIL", f"lockbox-eval: LOCKBOX_ALREADY_CONSUMED ({res.get('error')})", "CONSUMED"
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
