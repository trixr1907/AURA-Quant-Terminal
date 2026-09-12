#!/usr/bin/env python3
"""Append one validated trials-ledger record and checkpoint it."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path

from verify_ledger import (
    BASELINE_TOTAL,
    CHAIN_LEDGER,
    FIRST_ENTRY_ID,
    LEGACY_LEDGER,
    LEGACY_SHA256,
    LEDGER_CHECKPOINT,
    FIELD_ORDER,
    ID_RE,
    LedgerVerificationError,
    canonical_checkpoint,
    canonical_entry,
    canonical_record,
    verify_ledger,
)

INPUT_FIELDS = (
    "date", "version", "type", "hypothesis", "change", "success_criterion",
    "result", "delta", "status", "prereg_commit",
)


def _load_entry_fields(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LedgerVerificationError(f"cannot read entry file: {exc}") from exc
    if not isinstance(data, dict) or set(data) != set(INPUT_FIELDS):
        raise LedgerVerificationError(f"entry file must contain exactly: {', '.join(INPUT_FIELDS)}")
    if any(not isinstance(data[field], str) or not data[field].strip() for field in INPUT_FIELDS if field != "delta"):
        raise LedgerVerificationError("entry text fields must be non-empty strings")
    if isinstance(data["delta"], bool) or not isinstance(data["delta"], int) or data["delta"] not in (0, 1):
        raise LedgerVerificationError("entry delta must be integer 0 or 1")
    return data


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def append_ledger(
    entry_fields: dict,
    *,
    legacy_path: Path = LEGACY_LEDGER,
    chain_path: Path = CHAIN_LEDGER,
    checkpoint_path: Path = LEDGER_CHECKPOINT,
    expected_legacy_sha256: str = LEGACY_SHA256,
    first_entry_id: int = FIRST_ENTRY_ID,
    baseline_total: int = BASELINE_TOTAL,
) -> dict:
    """Append one entry under an advisory lock, then replace the checkpoint atomically."""
    lock_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        verified = verify_ledger(
            legacy_path,
            chain_path,
            checkpoint_path=checkpoint_path,
            expected_legacy_sha256=expected_legacy_sha256,
            first_entry_id=first_entry_id,
            baseline_total=baseline_total,
        )
        match = ID_RE.fullmatch(verified["last_entry_id"])
        if match is None:
            raise LedgerVerificationError("verified last entry id is invalid")
        payload = {
            "id": f"EXP-{int(match.group(1)) + 1:03d}",
            **entry_fields,
            "total_model_experiments": verified["total_model_experiments"] + entry_fields["delta"],
            "prev_hash": verified["chain_head"],
        }
        ordered = {field: payload[field] for field in FIELD_ORDER}
        entry = {**ordered, "entry_hash": hashlib.sha256(canonical_entry(ordered)).hexdigest()}
        record = canonical_record(entry)

        fd = os.open(chain_path, os.O_WRONLY | os.O_APPEND)
        try:
            written = os.write(fd, record)
            if written != len(record):
                raise OSError(f"short ledger append: {written}/{len(record)} bytes")
            os.fsync(fd)
        finally:
            os.close(fd)

        checkpoint = {
            "schema_version": 1,
            "last_entry_id": entry["id"],
            "entry_count": verified["entry_count"] + 1,
            "chain_head": entry["entry_hash"],
        }
        _atomic_replace(checkpoint_path, canonical_checkpoint(checkpoint))
        return {"ok": True, **checkpoint, "total_model_experiments": payload["total_model_experiments"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-file", required=True, type=Path)
    parser.add_argument("--legacy", type=Path, default=LEGACY_LEDGER)
    parser.add_argument("--chain", type=Path, default=CHAIN_LEDGER)
    parser.add_argument("--checkpoint", type=Path, default=LEDGER_CHECKPOINT)
    parser.add_argument("--expected-legacy-sha256", default=LEGACY_SHA256)
    parser.add_argument("--first-entry-id", type=int, default=FIRST_ENTRY_ID)
    parser.add_argument("--baseline-total", type=int, default=BASELINE_TOTAL)
    args = parser.parse_args()
    try:
        fields = _load_entry_fields(args.entry_file)
        result = append_ledger(
            fields,
            legacy_path=args.legacy,
            chain_path=args.chain,
            checkpoint_path=args.checkpoint,
            expected_legacy_sha256=args.expected_legacy_sha256,
            first_entry_id=args.first_entry_id,
            baseline_total=args.baseline_total,
        )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (LedgerVerificationError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
