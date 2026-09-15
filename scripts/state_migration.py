"""AURA v2.0.0 — State Schema Migration & Rollback Module.

Handles zero-loss, idempotent migration of runtime state (shared state & signal center state)
from Schema v1 to Schema v2 with automatic backup, disk-space guards, and rollback support.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import time
from typing import Any

log = logging.getLogger("state_migration")

TARGET_SCHEMA_VERSION = 2
MIN_DISK_FREE_SAFETY_FACTOR = 2.0


def normalize_trade_record_v2(trade: dict) -> dict:
    """Normalize a trade record to Schema v2 without altering primary keys or numerical values."""
    if not isinstance(trade, dict):
        return {}
    res = dict(trade)
    res["record_schema"] = TARGET_SCHEMA_VERSION
    res["schemaVersion"] = TARGET_SCHEMA_VERSION
    # Ensure ID is preserved exactly
    if "id" not in res and "tradeId" in res:
        res["id"] = res["tradeId"]
    # Ensure standard v2 fields are non-null or defaults
    res.setdefault("coin", str(res.get("coin", "UNKNOWN")))
    res.setdefault("dir", int(res.get("dir", 1)))
    res.setdefault("status", str(res.get("status", "OPEN")))
    res.setdefault("openedAt", res.get("openedAt", int(time.time() * 1000)))
    return res


def normalize_history_record_v2(hist: dict) -> dict:
    """Normalize a history record to Schema v2 without altering primary keys or outcomes."""
    if not isinstance(hist, dict):
        return {}
    res = dict(hist)
    res["record_schema"] = TARGET_SCHEMA_VERSION
    res["schemaVersion"] = TARGET_SCHEMA_VERSION
    # Preserve trade parent reference
    if "parentId" not in res and "tradeId" in res:
        res["parentId"] = res["tradeId"]
    elif "tradeId" not in res and "parentId" in res:
        res["tradeId"] = res["parentId"]
    res.setdefault("coin", str(res.get("coin", "UNKNOWN")))
    res.setdefault("dir", int(res.get("dir", 1)))
    res.setdefault("eventType", str(res.get("eventType", "FULL_CLOSE")))
    res.setdefault("reason", str(res.get("reason", "MANUAL")))
    return res


def migrate_shared_state_dict(v1_state: dict, *, now: float | None = None) -> dict:
    """Transform shared state dictionary to Schema v2 (idempotent, loss-free)."""
    current_time = time.time() if now is None else float(now)
    current_schema = int(v1_state.get("schema_version", 1))
    if current_schema > TARGET_SCHEMA_VERSION:
        raise ValueError(
            f"Cannot migrate state with schema_version {current_schema} > {TARGET_SCHEMA_VERSION}"
        )
    if current_schema == TARGET_SCHEMA_VERSION:
        return dict(v1_state)

    res = dict(v1_state)
    rev = int(res.get("_rev", res.get("rev", 0)))
    res["schema_version"] = TARGET_SCHEMA_VERSION
    res["rev"] = rev
    res["_rev"] = rev

    # Active trades extraction & normalization
    raw_trades = res.get("aura-quant-terminal-active-trades-v2")
    if raw_trades is None:
        raw_trades = res.get("aura-quant-terminal-active-trades-v1")
    if raw_trades is None:
        raw_trades = res.get("trades", [])
    if not isinstance(raw_trades, list):
        raw_trades = []
    normalized_trades = [normalize_trade_record_v2(t) for t in raw_trades if isinstance(t, dict)]

    # History trades extraction & normalization
    raw_history = res.get("aura-quant-terminal-history-trades-v2")
    if raw_history is None:
        raw_history = res.get("aura-quant-terminal-history-trades-v1")
    if raw_history is None:
        raw_history = res.get("history", [])
    if not isinstance(raw_history, list):
        raw_history = []
    normalized_history = [normalize_history_record_v2(h) for h in raw_history if isinstance(h, dict)]

    # Canonical v2 top-level properties
    res["trades"] = normalized_trades
    res["history"] = normalized_history
    res["aura-quant-terminal-active-trades-v2"] = normalized_trades
    res["aura-quant-terminal-history-trades-v2"] = normalized_history

    # Required top-level v2 fields
    autobot_state = res.get("aura-autobot-state-v2", {})
    if not isinstance(autobot_state, dict):
        autobot_state = {}
    server_bot_state = res.get("aura-server-bot-state-v1", {})
    if not isinstance(server_bot_state, dict):
        server_bot_state = {}

    res.setdefault("equity", autobot_state.get("equity", 10000.0))
    res.setdefault("funnel24h", server_bot_state.get("funnel24h", {}))
    res.setdefault("lastHeartbeatAt", server_bot_state.get("lastHeartbeatAt", None))
    res.setdefault("last_digest_date", res.get("last_digest_date", None))
    res.setdefault("_updated_at", int(current_time))
    res["_migrated_at"] = int(current_time)
    res["_migrated_from_schema"] = current_schema
    return res


def migrate_signal_state_dict(v1_signal_state: dict, *, now: float | None = None) -> dict:
    """Transform signal center state dictionary to Schema v2 (idempotent, loss-free)."""
    current_time = time.time() if now is None else float(now)
    current_schema = int(v1_signal_state.get("schema_version", 1))
    if current_schema > TARGET_SCHEMA_VERSION:
        raise ValueError(
            f"Cannot migrate signal state with schema_version {current_schema} > {TARGET_SCHEMA_VERSION}"
        )
    if current_schema == TARGET_SCHEMA_VERSION:
        return dict(v1_signal_state)

    res = dict(v1_signal_state)
    res["schema_version"] = TARGET_SCHEMA_VERSION
    res.setdefault("updated_at", datetime.fromtimestamp(current_time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    res.setdefault("btc", {})
    res.setdefault("digest", {})
    res.setdefault("health", {})
    res["_migrated_at"] = int(current_time)
    res["_migrated_from_schema"] = current_schema
    return res


def check_disk_space_safety(state_dir: Path, required_bytes: int = 1024 * 1024) -> bool:
    """Ensure disk has sufficient free space for atomic write and backup."""
    try:
        usage = shutil.disk_usage(state_dir)
        return usage.free >= max(required_bytes * MIN_DISK_FREE_SAFETY_FACTOR, 10 * 1024 * 1024)
    except Exception:
        return True


def migrate_state_directory(
    state_dir: Path,
    *,
    dry_run: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """Migrate aura_shared_state.json and aura_signal_center_state.json in state_dir."""
    current_time = time.time() if now is None else float(now)
    ts_str = datetime.fromtimestamp(current_time, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    shared_file = state_dir / "aura_shared_state.json"
    signal_file = state_dir / "aura_signal_center_state.json"

    results: dict[str, Any] = {
        "ok": True,
        "state_dir": str(state_dir),
        "dry_run": dry_run,
        "timestamp": ts_str,
        "actions": [],
    }

    # 1. Migrate aura_shared_state.json
    if shared_file.exists():
        try:
            raw_text = shared_file.read_text(encoding="utf-8")
            shared_data = json.loads(raw_text)
            if not isinstance(shared_data, dict):
                raise ValueError("Shared state is not a JSON object")
            current_ver = int(shared_data.get("schema_version", 1))

            if current_ver > TARGET_SCHEMA_VERSION:
                log.error("STATE_VERSION_FUTURE: aura_shared_state.json schema_version %d > %d", current_ver, TARGET_SCHEMA_VERSION)
                results["ok"] = False
                results["actions"].append({
                    "file": "aura_shared_state.json",
                    "status": "FAIL_FUTURE_VERSION",
                    "current_version": current_ver,
                })
            elif current_ver == TARGET_SCHEMA_VERSION:
                results["actions"].append({
                    "file": "aura_shared_state.json",
                    "status": "NOOP_ALREADY_V2",
                    "current_version": current_ver,
                })
            else:
                # Needs migration v1 -> v2
                if not check_disk_space_safety(state_dir, len(raw_text.encode())):
                    log.warning("DISK_SPACE_LOW: Insufficient free space for state migration in %s", state_dir)
                    results["ok"] = False
                    results["actions"].append({
                        "file": "aura_shared_state.json",
                        "status": "FAIL_DISK_SPACE",
                    })
                else:
                    backup_name = f"aura_shared_state.json.v1-backup-{ts_str}"
                    backup_path = state_dir / backup_name
                    migrated = migrate_shared_state_dict(shared_data, now=current_time)
                    if not dry_run:
                        # Write backup first
                        backup_path.write_text(raw_text, encoding="utf-8")
                        # Write migrated state atomically
                        tmp_path = shared_file.with_suffix(".tmp")
                        tmp_path.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
                        tmp_path.replace(shared_file)
                        log.info("MIGRATION_V2_SUCCESS: Migrated aura_shared_state.json from v%d to v2 (backup: %s)", current_ver, backup_name)

                    results["actions"].append({
                        "file": "aura_shared_state.json",
                        "status": "MIGRATED_V2",
                        "from_version": current_ver,
                        "to_version": 2,
                        "backup": backup_name,
                        "trades_count": len(migrated.get("trades", [])),
                        "history_count": len(migrated.get("history", [])),
                    })
        except Exception as exc:
            log.exception("Migration failed for aura_shared_state.json: %s", exc)
            results["ok"] = False
            results["actions"].append({
                "file": "aura_shared_state.json",
                "status": "ERROR",
                "error": str(exc),
            })

    # 2. Migrate aura_signal_center_state.json
    if signal_file.exists():
        try:
            raw_text = signal_file.read_text(encoding="utf-8")
            signal_data = json.loads(raw_text)
            if not isinstance(signal_data, dict):
                raise ValueError("Signal state is not a JSON object")
            current_ver = int(signal_data.get("schema_version", 1))

            if current_ver > TARGET_SCHEMA_VERSION:
                log.error("SIGNAL_STATE_VERSION_FUTURE: aura_signal_center_state.json schema_version %d > %d", current_ver, TARGET_SCHEMA_VERSION)
                results["ok"] = False
                results["actions"].append({
                    "file": "aura_signal_center_state.json",
                    "status": "FAIL_FUTURE_VERSION",
                    "current_version": current_ver,
                })
            elif current_ver == TARGET_SCHEMA_VERSION:
                results["actions"].append({
                    "file": "aura_signal_center_state.json",
                    "status": "NOOP_ALREADY_V2",
                    "current_version": current_ver,
                })
            else:
                backup_name = f"aura_signal_center_state.json.v1-backup-{ts_str}"
                backup_path = state_dir / backup_name
                migrated_sig = migrate_signal_state_dict(signal_data, now=current_time)
                if not dry_run:
                    backup_path.write_text(raw_text, encoding="utf-8")
                    tmp_sig = signal_file.with_suffix(".tmp")
                    tmp_sig.write_text(json.dumps(migrated_sig, indent=2), encoding="utf-8")
                    tmp_sig.replace(signal_file)
                    log.info("MIGRATION_V2_SUCCESS: Migrated aura_signal_center_state.json from v%d to v2 (backup: %s)", current_ver, backup_name)

                results["actions"].append({
                    "file": "aura_signal_center_state.json",
                    "status": "MIGRATED_V2",
                    "from_version": current_ver,
                    "to_version": 2,
                    "backup": backup_name,
                })
        except Exception as exc:
            log.exception("Migration failed for aura_signal_center_state.json: %s", exc)
            results["ok"] = False
            results["actions"].append({
                "file": "aura_signal_center_state.json",
                "status": "ERROR",
                "error": str(exc),
            })

    return results


def find_latest_backup(state_dir: Path, base_name: str) -> Path | None:
    """Find the most recent .v1-backup-* file for a state file."""
    backups = sorted(state_dir.glob(f"{base_name}.v1-backup-*"))
    return backups[-1] if backups else None


def rollback_state_directory(
    state_dir: Path,
    *,
    confirm_yes: bool = False,
) -> dict[str, Any]:
    """Roll back state files to their latest .v1-backup-* snapshots."""
    state_dir = Path(state_dir).resolve()
    shared_file = state_dir / "aura_shared_state.json"
    signal_file = state_dir / "aura_signal_center_state.json"

    latest_shared_backup = find_latest_backup(state_dir, "aura_shared_state.json")
    latest_signal_backup = find_latest_backup(state_dir, "aura_signal_center_state.json")

    results: dict[str, Any] = {
        "ok": True,
        "state_dir": str(state_dir),
        "confirm_yes": confirm_yes,
        "restored": [],
    }

    if not latest_shared_backup and not latest_signal_backup:
        return {
            "ok": False,
            "error": "No .v1-backup-* files found in state directory",
            "state_dir": str(state_dir),
        }

    if not confirm_yes:
        return {
            "ok": True,
            "dry_run": True,
            "message": "Rollback requires confirm_yes=True (--yes) to overwrite current state",
            "candidate_backups": {
                "shared_state": str(latest_shared_backup) if latest_shared_backup else None,
                "signal_state": str(latest_signal_backup) if latest_signal_backup else None,
            }
        }

    if latest_shared_backup and latest_shared_backup.exists():
        raw = latest_shared_backup.read_text(encoding="utf-8")
        tmp = shared_file.with_suffix(".tmp")
        tmp.write_text(raw, encoding="utf-8")
        tmp.replace(shared_file)
        results["restored"].append({
            "target": "aura_shared_state.json",
            "from_backup": latest_shared_backup.name,
        })
        log.info("ROLLBACK_SUCCESS: Restored aura_shared_state.json from %s", latest_shared_backup.name)

    if latest_signal_backup and latest_signal_backup.exists():
        raw_sig = latest_signal_backup.read_text(encoding="utf-8")
        tmp_sig = signal_file.with_suffix(".tmp")
        tmp_sig.write_text(raw_sig, encoding="utf-8")
        tmp_sig.replace(signal_file)
        results["restored"].append({
            "target": "aura_signal_center_state.json",
            "from_backup": latest_signal_backup.name,
        })
        log.info("ROLLBACK_SUCCESS: Restored aura_signal_center_state.json from %s", latest_signal_backup.name)

    return results
