"""Tests for Auftrag 3: Fast-Crash Detector & Crash-Loop Protection."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import bitget_relay as relay


class MockChildProcess:
    def __init__(self, returncode: int = 1):
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return self.returncode


class TestRunnerCrashDetector(unittest.TestCase):
    def test_fast_crash_triggers_immediate_restart_and_count(self):
        manager = relay.RunnerManager()
        proc = MockChildProcess(returncode=1)
        manager.set_process(proc, started_at=1000.0)

        replacement = MockChildProcess(returncode=0)
        with patch.object(relay, "_start_runner_if_enabled", return_value=replacement) as mock_start:
            # Crash happens at 1002.0 (2 seconds after start, < 10s)
            res = manager.handle_child_exit(returncode=1, now=1002.0)
            self.assertTrue(res["restarted"])
            self.assertTrue(res["fast_crash"])
            mock_start.assert_called_once()

        snap = manager.snapshot(now=1002.0)
        self.assertEqual(snap["runner_crash_count"], 1)
        self.assertEqual(snap["fast_crash_count"], 1)
        self.assertFalse(snap["crash_loop_detected"])
        self.assertEqual(snap["runner_restart_count"], 1)

    def test_three_consecutive_fast_crashes_trigger_crash_loop_detected(self):
        manager = relay.RunnerManager()
        p1 = MockChildProcess(returncode=1)
        manager.set_process(p1, started_at=1000.0)

        with patch.object(relay, "_start_runner_if_enabled", side_effect=[
            MockChildProcess(returncode=1),
            MockChildProcess(returncode=1),
            MockChildProcess(returncode=0),
        ]):
            # Crash 1 at +2s
            manager.handle_child_exit(returncode=1, now=1002.0)
            # Crash 2 at +3s
            manager.handle_child_exit(returncode=1, now=1005.0)
            # Crash 3 at +2s
            manager.handle_child_exit(returncode=1, now=1007.0)

        snap = manager.snapshot(now=1007.0)
        self.assertEqual(snap["runner_crash_count"], 3)
        self.assertEqual(snap["fast_crash_count"], 3)
        self.assertTrue(snap["crash_loop_detected"])
        self.assertEqual(snap["runner_restart_count"], 3)

    def test_slow_exit_resets_fast_crash_streak(self):
        manager = relay.RunnerManager()
        p1 = MockChildProcess(returncode=1)
        manager.set_process(p1, started_at=1000.0)

        with patch.object(relay, "_start_runner_if_enabled", side_effect=[
            MockChildProcess(returncode=1),
            MockChildProcess(returncode=0),
        ]):
            # 1 fast crash
            manager.handle_child_exit(returncode=1, now=1003.0)
            self.assertEqual(manager.snapshot()["fast_crash_count"], 1)

            # Next exit happens after 200s (slow exit >= 10s)
            manager.handle_child_exit(returncode=0, now=1203.0)
            snap = manager.snapshot(now=1203.0)
            self.assertEqual(snap["runner_crash_count"], 2)
            self.assertEqual(snap["fast_crash_count"], 0)
            self.assertFalse(snap["crash_loop_detected"])

    def test_watchdog_healthy_recovery_resets_fast_crash_streak(self):
        manager = relay.RunnerManager()
        p1 = MockChildProcess(returncode=1)
        manager.set_process(p1, started_at=1000.0)

        with patch.object(relay, "_start_runner_if_enabled", return_value=MockChildProcess()):
            manager.handle_child_exit(returncode=1, now=1002.0)
            manager.handle_child_exit(returncode=1, now=1005.0)

        self.assertEqual(manager.snapshot()["fast_crash_count"], 2)

        # Runner performs healthy advance
        health = {"running": True, "last_cycle_age_sec": 5.0, "cycle_count": 1}
        res = manager.watchdog(health, now=1020.0, stale_sec=180.0)
        self.assertTrue(res["recovered"])
        self.assertEqual(manager.snapshot()["fast_crash_count"], 0)
        self.assertFalse(manager.snapshot()["crash_loop_detected"])

    def test_status_page_shows_crash_loop_violation_and_crashes(self):
        with patch.dict("os.environ", {"AURA_BOT_MODE": "server"}):
            with patch.object(relay.RUNNER_MANAGER, "snapshot", return_value={
                "runner_restart_count": 5,
                "runner_crash_count": 5,
                "fast_crash_count": 3,
                "crash_loop_detected": True,
                "restart_timestamps": [],
                "restarts_24h": 5,
                "recovery_pending": False,
            }):
                html = relay.render_status_html(now=1000.0, disk_free_mb_override=2000.0)
                self.assertIn("HANDLUNGSBEDARF", html)
                self.assertIn("Crash-Loop erkannt", html)
                self.assertIn("CRASH-LOOP", html)


if __name__ == "__main__":
    unittest.main()
