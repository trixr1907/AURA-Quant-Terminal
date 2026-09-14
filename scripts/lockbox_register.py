#!/usr/bin/env python3
"""Lockbox Registrar & Forward Holdout Lock.

Registers forward holdout lockbox span in provenance manifest.
Enforces confirmation prompt, positive integer day span, atomic write,
and refuses to overwrite an already locked lockbox.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROVENANCE = ROOT / "tests" / "fixtures" / "golden" / "provenance.json"


class LockboxError(Exception):
    """Base error for lockbox registration operations."""


class LockboxAlreadyLockedError(LockboxError):
    """Raised when attempting to overwrite an already locked lockbox."""


class LockboxAbortedError(LockboxError):
    """Raised when user confirmation is rejected or aborted."""


def register_lockbox(
    provenance_path: Path,
    days: int,
    cutoff_time: str | None = None,
    prompt_fn: callable | None = None,
) -> dict:
    """Register a forward holdout lockbox span in the target provenance file."""
    if not isinstance(days, int) or days <= 0:
        raise ValueError(f"--days must be a positive integer, got: {days}")

    prov_path = Path(provenance_path)
    prov: dict = {}
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise LockboxError(f"Failed to parse provenance file {prov_path}: {e}") from e

    existing_lockbox = prov.get("lockbox")
    if isinstance(existing_lockbox, dict) and existing_lockbox.get("status") == "LOCKED":
        raise LockboxAlreadyLockedError(
            f"Lockbox is already LOCKED (cutoff={existing_lockbox.get('cutoff_time')}, "
            f"span={existing_lockbox.get('locked_span_days')} days). "
            "Existing LOCKED lockbox cannot be overwritten."
        )

    # Prompt user for confirmation
    prompt_str = f"Lockbox-Spanne ab heute für {days} Tage sperren? Das kann nicht rückgängig gemacht werden. "
    if prompt_fn is not None:
        response = prompt_fn(prompt_str)
    else:
        try:
            response = input(prompt_str)
        except (EOFError, KeyboardInterrupt) as e:
            raise LockboxAbortedError("Registration aborted by user interrupt or EOF.") from e

    cleaned_response = (response or "").strip().lower()
    if cleaned_response not in ("ja", "yes"):
        raise LockboxAbortedError(
            f"Registration rejected (received '{response.strip()}'). Only explicit 'ja' or 'yes' confirms."
        )

    cutoff_iso = cutoff_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    lockbox_data = {
        "cutoff_time": cutoff_iso,
        "locked_span_days": int(days),
        "status": "LOCKED",
        "mode": "forward_holdout",
        "description": (
            f"All bars with close timestamp >= {cutoff_iso} are strictly locked for "
            "final blind OOS evaluation. No model tuning, parameter selection, or "
            "threshold optimization may access this span."
        ),
    }

    new_prov = {
        "lockbox": lockbox_data,
        **{k: v for k, v in prov.items() if k != "lockbox"},
    }

    # Atomic write
    prov_path.parent.mkdir(parents=True, exist_ok=True)
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
        "status": "LOCKED",
        "mode": "forward_holdout",
        "cutoff_time": cutoff_iso,
        "locked_span_days": int(days),
        "provenance_path": str(prov_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lockbox Registrar & Forward Holdout Lock",
        prog="lockbox_register.py",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register forward holdout lockbox span",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days to lock forward span (positive integer)",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        default=DEFAULT_PROVENANCE,
        help=f"Path to provenance.json (default: {DEFAULT_PROVENANCE})",
    )

    args = parser.parse_args(argv)

    if not args.register:
        # No-op default
        print("No-op: --register flag was not specified. No modifications made.")
        return 0

    if args.days is None or args.days <= 0:
        print("Error: --days must be a positive integer (e.g. --days 60)", file=sys.stderr)
        return 1

    try:
        res = register_lockbox(
            provenance_path=args.provenance,
            days=args.days,
        )
        print(f"Lockbox registered successfully: status=LOCKED, cutoff={res['cutoff_time']}, span={res['locked_span_days']}d")
        return 0
    except LockboxAlreadyLockedError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except LockboxAbortedError as e:
        print(f"Aborted: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
