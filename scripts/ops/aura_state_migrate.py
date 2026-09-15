#!/usr/bin/env python3
"""AURA State Migration CLI — dry-run, migrate, and rollback operations."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys

# Support execution from repository root and packaged runtime.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.state_migration import migrate_state_directory, rollback_state_directory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate or roll back AURA runtime state Schema v1 ↔ v2"
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.environ.get("AURA_STATE_DIR", REPO_ROOT / "data")),
        help="State directory (default: AURA_STATE_DIR or ./data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report migration actions without writing state or backups",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Restore the latest .v1-backup-* files",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive rollback overwrite",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.rollback:
        result = rollback_state_directory(args.state_dir, confirm_yes=args.yes)
    else:
        result = migrate_state_directory(args.state_dir, dry_run=args.dry_run)

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
