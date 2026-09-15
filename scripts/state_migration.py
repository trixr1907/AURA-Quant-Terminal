"""AURA runtime-state Schema v1 to v2 migration and rollback."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator

log = logging.getLogger("state_migration")

TARGET_SCHEMA_VERSION = 2
MIN_DISK_FREE_SAFETY_FACTOR = 2.0
_STATE_FILES = (
    "aura_shared_state.json",
    "aura_signal_center_state.json",
)
_BACKUP_RE = re.compile(
    r"^(aura_(?:shared|signal_center)_state\.json)\.v1-backup-"
    r"(\d{8}T\d{12}Z)$"
)


def _schema_version(value: dict, label: str) -> int:
    raw = value.get("schema_version", 1)
    if isinstance(raw, bool):
        raise ValueError(f"{label} schema_version must be an integer")
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} schema_version must be an integer") from exc
    if version < 1:
        raise ValueError(f"{label} schema_version must be >= 1")
    if version > TARGET_SCHEMA_VERSION:
        raise ValueError(
            f"{label} schema_version {version} is newer than build "
            f"{TARGET_SCHEMA_VERSION} — rollback image or restore backup"
        )
    return version


def normalize_trade_record_v2(trade: dict) -> dict:
    """Add only the v2 record envelope; preserve every existing value."""
    if not isinstance(trade, dict):
        raise ValueError("trade records must be JSON objects")
    result = dict(trade)
    result["record_schema"] = TARGET_SCHEMA_VERSION
    return result


def normalize_history_record_v2(history: dict) -> dict:
    """Add only the v2 record envelope; preserve IDs and all existing values."""
    if not isinstance(history, dict):
        raise ValueError("history records must be JSON objects")
    result = dict(history)
    result["record_schema"] = TARGET_SCHEMA_VERSION
    return result


def _record_list(state: dict, canonical: str, v2_key: str, v1_key: str) -> list:
    for key in (v2_key, v1_key, canonical):
        if key in state:
            value = state[key]
            if not isinstance(value, list):
                raise ValueError(f"{key} must be a JSON array")
            if not all(isinstance(item, dict) for item in value):
                raise ValueError(f"{key} contains a non-object record")
            return value
    return []


def migrate_shared_state_dict(v1_state: dict, *, now: float | None = None) -> dict:
    """Transform shared runtime state to Schema v2, structurally only."""
    if not isinstance(v1_state, dict):
        raise ValueError("shared state must be a JSON object")
    current_schema = _schema_version(v1_state, "shared state")
    if current_schema == TARGET_SCHEMA_VERSION:
        return dict(v1_state)

    current_time = time.time() if now is None else float(now)
    result = dict(v1_state)
    revision_raw = result.get("_rev", result.get("rev", 0))
    if isinstance(revision_raw, bool):
        raise ValueError("shared state revision must be an integer")
    try:
        revision = int(revision_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("shared state revision must be an integer") from exc

    raw_trades = _record_list(
        result,
        "trades",
        "aura-quant-terminal-active-trades-v2",
        "aura-quant-terminal-active-trades-v1",
    )
    raw_history = _record_list(
        result,
        "history",
        "aura-quant-terminal-history-trades-v2",
        "aura-quant-terminal-history-trades-v1",
    )
    trades = [normalize_trade_record_v2(item) for item in raw_trades]
    history = [normalize_history_record_v2(item) for item in raw_history]

    result["schema_version"] = TARGET_SCHEMA_VERSION
    result["rev"] = revision
    result["_rev"] = revision
    result["trades"] = trades
    result["history"] = history
    result["aura-quant-terminal-active-trades-v2"] = trades
    result["aura-quant-terminal-history-trades-v2"] = history

    autobot = result.get("aura-autobot-state-v2")
    server_bot = result.get("aura-server-bot-state-v1")
    autobot = autobot if isinstance(autobot, dict) else {}
    server_bot = server_bot if isinstance(server_bot, dict) else {}
    result.setdefault("equity", autobot.get("equity", server_bot.get("equity")))
    result.setdefault("funnel24h", server_bot.get("funnel24h", {}))
    result.setdefault("lastHeartbeatAt", server_bot.get("lastHeartbeatAt"))
    result.setdefault("last_digest_date", None)
    result.setdefault("_updated_at", int(current_time))
    result["_migrated_at"] = int(current_time)
    result["_migrated_from_schema"] = current_schema
    return result


def migrate_signal_state_dict(v1_signal_state: dict, *, now: float | None = None) -> dict:
    """Transform signal-center state to Schema v2 without changing values."""
    if not isinstance(v1_signal_state, dict):
        raise ValueError("signal state must be a JSON object")
    current_schema = _schema_version(v1_signal_state, "signal state")
    if current_schema == TARGET_SCHEMA_VERSION:
        return dict(v1_signal_state)

    current_time = time.time() if now is None else float(now)
    result = dict(v1_signal_state)
    result.setdefault("digest", {})
    result.setdefault("health", {})
    result["schema_version"] = TARGET_SCHEMA_VERSION
    result["_migrated_at"] = int(current_time)
    result["_migrated_from_schema"] = current_schema
    return result


def check_disk_space_safety(state_dir: Path, required_bytes: int) -> bool:
    """Fail closed unless free bytes are strictly greater than twice input size."""
    try:
        usage = shutil.disk_usage(state_dir)
    except OSError:
        return False
    return usage.free > max(1, required_bytes) * MIN_DISK_FREE_SAFETY_FACTOR


@contextmanager
def _state_lock(state_dir: Path) -> Iterator[None]:
    """Serialize migration/rollback processes with an advisory file lock."""
    lock_path = state_dir / ".aura-state-migration.lock"
    lock_file = lock_path.open("a+b")
    try:
        os.chmod(lock_path, 0o600)
        try:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - Windows launcher compatibility
            import msvcrt
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        yield
    finally:
        try:
            try:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover - Windows launcher compatibility
                import msvcrt
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        finally:
            lock_file.close()


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_exclusive_backup(path: Path, raw: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, mode)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


def _atomic_write(path: Path, raw: bytes, mode: int) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        tmp_path.unlink(missing_ok=True)


def _load_candidate(path: Path) -> tuple[bytes, dict, int]:
    raw = path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    mode = stat.S_IMODE(path.stat().st_mode)
    return raw, parsed, mode


def migrate_state_directory(
    state_dir: Path,
    *,
    dry_run: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """Migrate both runtime-state files after a complete fail-closed preflight."""
    current_time = time.time() if now is None else float(now)
    timestamp = datetime.fromtimestamp(current_time, timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    state_dir = Path(state_dir).resolve()
    result: dict[str, Any] = {
        "ok": True,
        "state_dir": str(state_dir),
        "dry_run": dry_run,
        "timestamp": timestamp,
        "actions": [],
    }

    if not state_dir.exists():
        if dry_run:
            return result
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result["ok"] = False
            result["error"] = f"state directory is not writable: {exc}"
            return result
    if not state_dir.is_dir():
        result["ok"] = False
        result["error"] = "state directory is not a directory"
        return result

    candidates: list[dict[str, Any]] = []
    current_name = "runtime state"
    try:
        for name in _STATE_FILES:
            current_name = name
            path = state_dir / name
            if not path.exists():
                continue
            raw, parsed, mode = _load_candidate(path)
            version = _schema_version(parsed, name)
            if version == TARGET_SCHEMA_VERSION:
                result["actions"].append({
                    "file": name,
                    "status": "NOOP_ALREADY_V2",
                    "current_version": version,
                })
                continue
            migrated = (
                migrate_shared_state_dict(parsed, now=current_time)
                if name == "aura_shared_state.json"
                else migrate_signal_state_dict(parsed, now=current_time)
            )
            backup_name = f"{name}.v1-backup-{timestamp}"
            backup = state_dir / backup_name
            if backup.exists():
                raise FileExistsError(f"backup already exists: {backup_name}")
            candidates.append({
                "name": name,
                "path": path,
                "raw": raw,
                "mode": mode,
                "version": version,
                "migrated": migrated,
                "backup": backup,
            })

        required_bytes = sum(len(item["raw"]) for item in candidates)
        if candidates and not check_disk_space_safety(state_dir, required_bytes):
            raise OSError(
                "insufficient disk space: migration requires free bytes > "
                f"2 × {required_bytes}"
            )
    except Exception as exc:
        status = "FAIL_FUTURE_VERSION" if "newer than build" in str(exc) else "FAIL_PREFLIGHT"
        result["ok"] = False
        result["actions"].append({"file": current_name, "status": status, "error": str(exc)})
        result["error"] = str(exc)
        log.error("STATE_MIGRATION_PREFLIGHT_FAILED: %s", exc)
        return result

    for item in candidates:
        migrated_bytes = json.dumps(item["migrated"], indent=2).encode("utf-8")
        action = {
            "file": item["name"],
            "status": "MIGRATED_V2",
            "from_version": item["version"],
            "to_version": TARGET_SCHEMA_VERSION,
            "backup": item["backup"].name,
        }
        if item["name"] == "aura_shared_state.json":
            action["trades_count"] = len(item["migrated"]["trades"])
            action["history_count"] = len(item["migrated"]["history"])
        result["actions"].append(action)
        if dry_run:
            continue
        try:
            with _state_lock(state_dir):
                # Revalidate bytes under the process lock before publishing.
                if item["path"].read_bytes() != item["raw"]:
                    raise RuntimeError(f"{item['name']} changed during migration")
                _write_exclusive_backup(item["backup"], item["raw"], item["mode"])
                _atomic_write(item["path"], migrated_bytes, item["mode"])
            log.info(
                "MIGRATION_V2_SUCCESS: Migrated %s from v%d to v2 (backup: %s)",
                item["name"],
                item["version"],
                item["backup"].name,
            )
        except Exception as exc:
            log.error("STATE_MIGRATION_WRITE_FAILED for %s: %s", item["name"], exc)
            result["ok"] = False
            result["error"] = str(exc)
            return result
    return result


def find_latest_backup(state_dir: Path, base_name: str) -> Path | None:
    """Return the newest validly named v1 backup by filesystem mtime."""
    candidates = []
    for path in Path(state_dir).glob(f"{base_name}.v1-backup-*"):
        match = _BACKUP_RE.fullmatch(path.name)
        if match and match.group(1) == base_name and path.is_file():
            candidates.append(path)
    return max(candidates, key=lambda item: item.stat().st_mtime_ns, default=None)


def rollback_state_directory(
    state_dir: Path,
    *,
    confirm_yes: bool = False,
) -> dict[str, Any]:
    """Restore latest valid v1 backups after explicit confirmation."""
    state_dir = Path(state_dir).resolve()
    backups = {
        name: find_latest_backup(state_dir, name)
        for name in _STATE_FILES
    }
    available = {name: path for name, path in backups.items() if path is not None}
    if not available:
        return {
            "ok": False,
            "error": "No valid .v1-backup-* files found in state directory",
            "state_dir": str(state_dir),
        }
    for name, backup in available.items():
        try:
            parsed = json.loads(backup.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict) or int(parsed.get("schema_version", 1)) != 1:
                raise ValueError("backup is not Schema v1")
        except Exception as exc:
            return {"ok": False, "error": f"invalid backup {backup.name}: {exc}"}

    if not confirm_yes:
        return {
            "ok": True,
            "dry_run": True,
            "message": "Rollback requires --yes to overwrite current state",
            "candidate_backups": {
                name: str(path) for name, path in available.items()
            },
        }

    result: dict[str, Any] = {
        "ok": True,
        "state_dir": str(state_dir),
        "confirm_yes": True,
        "restored": [],
    }
    try:
        with _state_lock(state_dir):
            for name, backup in available.items():
                target = state_dir / name
                raw = backup.read_bytes()
                mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else stat.S_IMODE(backup.stat().st_mode)
                _atomic_write(target, raw, mode)
                result["restored"].append({
                    "target": name,
                    "from_backup": backup.name,
                })
                log.info("ROLLBACK_SUCCESS: Restored %s from %s", name, backup.name)
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
    return result
