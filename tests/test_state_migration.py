import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.state_migration import (
    check_disk_space_safety,
    migrate_shared_state_dict,
    migrate_signal_state_dict,
    migrate_state_directory,
    rollback_state_directory,
)


class StateMigrationTests(unittest.TestCase):
    def test_golden_fixture_migrates_without_value_changes(self):
        source = {
            "schema_version": 1,
            "_rev": 7,
            "aura-quant-terminal-active-trades-v1": [{"id": "golden-trade", "entry": 1.25}],
            "aura-quant-terminal-history-trades-v1": [{"id": "golden-history", "parentId": "golden-trade"}],
            "custom": {"preserve": True},
        }
        migrated = migrate_shared_state_dict(source, now=1_700_000_000)
        self.assertEqual(migrated["schema_version"], 2)
        for key, value in source.items():
            if key in {
                "schema_version",
                "aura-quant-terminal-active-trades-v1",
                "aura-quant-terminal-history-trades-v1",
            }:
                continue
            self.assertEqual(migrated[key], value)
        self.assertEqual(migrated["rev"], source.get("rev", source.get("_rev", 0)))
        self.assertEqual(migrated["trades"], migrated["aura-quant-terminal-active-trades-v2"])
        self.assertEqual(migrated["history"], migrated["aura-quant-terminal-history-trades-v2"])
        self.assertEqual(migrated["trades"][0]["id"], "golden-trade")
        self.assertEqual(migrated["trades"][0]["entry"], 1.25)
        self.assertEqual(migrated["history"][0]["parentId"], "golden-trade")
        self.assertIn("funnel24h", migrated)
        self.assertIn("lastHeartbeatAt", migrated)
        self.assertIn("last_digest_date", migrated)

    def test_trade_ids_and_numeric_precision_are_preserved(self):
        source = {
            "schema_version": 1,
            "_rev": 7,
            "aura-quant-terminal-active-trades-v1": [{"id": "sb_fixed", "entry": 0.1234567890123456}],
            "aura-quant-terminal-history-trades-v1": [{"id": "h_fixed", "parentId": "sb_fixed", "realizedPnl": -1.23456789}],
        }
        migrated = migrate_shared_state_dict(source, now=100)
        self.assertEqual(migrated["trades"][0]["id"], "sb_fixed")
        self.assertEqual(migrated["trades"][0]["entry"], 0.1234567890123456)
        self.assertEqual(migrated["history"][0]["parentId"], "sb_fixed")
        self.assertEqual(migrated["history"][0]["realizedPnl"], -1.23456789)
        self.assertEqual(migrated["trades"][0]["record_schema"], 2)
        self.assertEqual(migrated["history"][0]["record_schema"], 2)

    def test_idempotence(self):
        source = {"schema_version": 1, "_rev": 2, "trades": [], "history": []}
        first = migrate_shared_state_dict(source, now=100)
        second = migrate_shared_state_dict(first, now=100)
        self.assertEqual(first, second)

    def test_future_schema_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "schema_version 3"):
            migrate_shared_state_dict({"schema_version": 3})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "aura_shared_state.json").write_text('{"schema_version":3}', encoding="utf-8")
            result = migrate_state_directory(path, now=100)
            self.assertFalse(result["ok"])
            self.assertEqual(result["actions"][0]["status"], "FAIL_FUTURE_VERSION")

    def test_backup_and_rollback_are_byte_identical(self):
        original = '{"schema_version":1,"_rev":9,"custom":1.2300}\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            state_file = path / "aura_shared_state.json"
            state_file.write_text(original, encoding="utf-8")
            original_hash = hashlib.sha256(original.encode()).hexdigest()
            result = migrate_state_directory(path, now=1_700_000_000)
            self.assertTrue(result["ok"])
            self.assertEqual(json.loads(state_file.read_text())["schema_version"], 2)
            backups = list(path.glob("aura_shared_state.json.v1-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(hashlib.sha256(backups[0].read_bytes()).hexdigest(), original_hash)
            preview = rollback_state_directory(path)
            self.assertTrue(preview["dry_run"])
            rolled = rollback_state_directory(path, confirm_yes=True)
            self.assertTrue(rolled["ok"])
            self.assertEqual(hashlib.sha256(state_file.read_bytes()).hexdigest(), original_hash)

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            state_file = path / "aura_shared_state.json"
            state_file.write_text('{"schema_version":1}', encoding="utf-8")
            result = migrate_state_directory(path, dry_run=True, now=100)
            self.assertTrue(result["ok"])
            self.assertEqual(state_file.read_text(), '{"schema_version":1}')
            self.assertFalse(list(path.glob("*.v1-backup-*")))

    def test_signal_center_state_migrates_separately(self):
        source = {"btc": {"regime": "BULL"}, "custom": 9}
        migrated = migrate_signal_state_dict(source, now=100)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["btc"], source["btc"])
        self.assertEqual(migrated["custom"], 9)
        self.assertIn("digest", migrated)
        self.assertIn("health", migrated)

    def test_empty_v1_state_has_no_fake_records(self):
        migrated = migrate_shared_state_dict({"schema_version": 1}, now=100)
        self.assertEqual(migrated["trades"], [])
        self.assertEqual(migrated["history"], [])
        self.assertEqual(migrated["rev"], 0)

    def test_invalid_record_shape_fails_closed_without_writing(self):
        with self.assertRaisesRegex(ValueError, "must be a JSON array"):
            migrate_shared_state_dict({
                "schema_version": 1,
                "aura-quant-terminal-active-trades-v1": {"id": "bad"},
            })
        with self.assertRaisesRegex(ValueError, "contains a non-object record"):
            migrate_shared_state_dict({
                "schema_version": 1,
                "aura-quant-terminal-history-trades-v1": [{"id": "ok"}, "bad"],
            })

    def test_disk_guard_requires_strictly_more_than_twice_state_size(self):
        with patch("scripts.state_migration.shutil.disk_usage") as disk_usage:
            disk_usage.return_value = type("Usage", (), {"free": 200})()
            self.assertFalse(check_disk_space_safety(Path("."), 100))
            disk_usage.return_value = type("Usage", (), {"free": 201})()
            self.assertTrue(check_disk_space_safety(Path("."), 100))
            disk_usage.side_effect = OSError("unavailable")
            self.assertFalse(check_disk_space_safety(Path("."), 100))

    def test_backup_is_exclusive_preserves_mode_and_is_never_overwritten(self):
        original = b'{"schema_version":1,"trades":[],"history":[]}\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            state_file = path / "aura_shared_state.json"
            state_file.write_bytes(original)
            state_file.chmod(0o600)
            first = migrate_state_directory(path, now=1_700_000_000)
            self.assertTrue(first["ok"])
            backup = next(path.glob("aura_shared_state.json.v1-backup-*"))
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)
            backup.write_bytes(b"sentinel")
            state_file.write_bytes(original)
            second = migrate_state_directory(path, now=1_700_000_000)
            self.assertFalse(second["ok"])
            self.assertEqual(backup.read_bytes(), b"sentinel")

    def test_dry_run_missing_directory_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            absent = Path(tmp) / "does-not-exist"
            result = migrate_state_directory(absent, dry_run=True)
            self.assertTrue(result["ok"])
            self.assertFalse(absent.exists())

    def test_signal_state_participates_in_combined_disk_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "aura_shared_state.json").write_text('{"schema_version":1}', encoding="utf-8")
            (path / "aura_signal_center_state.json").write_text('{"schema_version":1}', encoding="utf-8")
            with patch("scripts.state_migration.check_disk_space_safety", return_value=False):
                result = migrate_state_directory(path, now=100)
            self.assertFalse(result["ok"])
            self.assertFalse(list(path.glob("*.v1-backup-*")))
            self.assertEqual(json.loads((path / "aura_signal_center_state.json").read_text())["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
