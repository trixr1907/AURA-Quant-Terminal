"""AURA v1.8.0 runner self-healing tests."""
from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import bitget_relay as relay


class TestRunnerStaleThreshold(unittest.TestCase):
    def test_calculated_floor_and_scan_multiple(self):
        self.assertEqual(relay.runner_stale_threshold(scan_sec=60, override_raw=None), 180.0)
        self.assertEqual(relay.runner_stale_threshold(scan_sec=120, override_raw=None), 360.0)

    def test_positive_finite_override_wins_including_fraction(self):
        self.assertEqual(relay.runner_stale_threshold(scan_sec=120, override_raw="45.5"), 45.5)

    def test_invalid_override_uses_safe_calculated_fallback(self):
        for value in ("", "nope", "0", "-1", "nan", "inf", "-inf"):
            with self.subTest(value=value):
                self.assertEqual(relay.runner_stale_threshold(scan_sec=60, override_raw=value), 180.0)

    def test_environment_values_are_supported_without_crashing(self):
        with patch.dict("os.environ", {"AURA_BOT_SCAN_SEC": "120", "AURA_RUNNER_STALE_SEC": "240"}, clear=False):
            self.assertEqual(relay.runner_stale_threshold(), 240.0)
        with patch.dict("os.environ", {"AURA_BOT_SCAN_SEC": "invalid", "AURA_RUNNER_STALE_SEC": "invalid"}, clear=False):
            self.assertTrue(math.isfinite(relay.runner_stale_threshold()))
            self.assertGreaterEqual(relay.runner_stale_threshold(), 180.0)


if __name__ == "__main__":
    unittest.main()


class FakeProcess:
    def __init__(self, *, timeout_once=False):
        self.timeout_once = timeout_once
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts = []

    def terminate(self):
        self.terminate_calls += 1

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        if self.timeout_once:
            self.timeout_once = False
            raise relay.subprocess.TimeoutExpired("node", timeout)
        return 0

    def kill(self):
        self.kill_calls += 1


class TestRunnerManagerLifecycle(unittest.TestCase):
    def test_running_true_stall_dumps_once_restarts_and_recovers_after_new_cycle(self):
        old_proc = FakeProcess(timeout_once=True)
        replacement = FakeProcess()
        manager = relay.RunnerManager()
        manager.set_process(old_proc)
        health = {"running": True, "last_cycle_age_sec": 181.0, "cycle_count": 7}

        with patch.object(relay, "_start_runner_if_enabled", return_value=replacement) as start, \
             patch.object(relay.faulthandler, "dump_traceback") as dump:
            first = manager.watchdog(health, now=1000.0, stale_sec=180.0)
            repeated = manager.watchdog(health, now=1001.0, stale_sec=180.0)
            not_yet = manager.watchdog(
                {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 7},
                now=1002.0,
                stale_sec=180.0,
            )
            recovered = manager.watchdog(
                {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 8},
                now=1003.0,
                stale_sec=180.0,
            )
            later = manager.watchdog(
                {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 9},
                now=1004.0,
                stale_sec=180.0,
            )

        self.assertTrue(first["restarted"])
        self.assertFalse(repeated["restarted"])
        self.assertFalse(not_yet["recovered"])
        self.assertTrue(recovered["recovered"])
        self.assertFalse(later["recovered"])
        dump.assert_called_once()
        start.assert_called_once_with()
        self.assertEqual(old_proc.terminate_calls, 1)
        self.assertEqual(old_proc.kill_calls, 1)
        self.assertEqual(old_proc.wait_timeouts, [5, 5])
        self.assertEqual(manager.snapshot(now=1004.0)["runner_restart_count"], 1)
        self.assertEqual(manager.snapshot(now=1004.0)["restarts_24h"], 1)
        self.assertIs(manager.current_process(), replacement)

    def test_fresh_cycle_ignores_running_false(self):
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        result = manager.watchdog(
            {"running": False, "last_cycle_age_sec": 5.0, "cycle_count": 2},
            now=2000.0,
            stale_sec=180.0,
        )
        self.assertFalse(result["restarted"])
        self.assertEqual(manager.snapshot(now=2000.0)["runner_restart_count"], 0)

class TestRunnerFreshnessTransition(unittest.TestCase):
    def test_running_flag_is_ignored_and_threshold_boundary_is_fresh(self):
        fresh = relay.runner_dead_transition(
            {},
            {"running": False, "last_cycle_age_sec": 180.0, "cycle_count": 1},
            mode="server",
            now=1000.0,
            stale_sec=180.0,
        )
        stale = relay.runner_dead_transition(
            {},
            {"running": True, "last_cycle_age_sec": 180.1, "cycle_count": 1},
            mode="server",
            now=1000.0,
            stale_sec=180.0,
        )
        self.assertFalse(fresh["notify"])
        self.assertFalse(fresh["stalled"])
        self.assertTrue(stale["notify"])
        self.assertTrue(stale["stalled"])
        self.assertTrue(stale["body"].endswith("Selbstheilung ausgelöst"))

    def test_missing_timestamp_is_stale_only_after_startup_grace(self):
        health = {"running": True, "last_cycle_age_sec": None, "cycle_count": 0}
        grace = relay.runner_dead_transition(
            {}, health, mode="server", now=1099.0, relay_start_time=1000.0, startup_grace_sec=120.0
        )
        expired = relay.runner_dead_transition(
            {}, health, mode="server", now=1120.0, relay_start_time=1000.0, startup_grace_sec=120.0
        )
        self.assertFalse(grace["stalled"])
        self.assertTrue(expired["stalled"])

class TestRunnerWatchdogNotifications(unittest.TestCase):
    def test_alert_then_recovery_notification_only_after_higher_cycle(self):
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        stalled = {"running": True, "last_cycle_age_sec": 181.0, "cycle_count": 4}
        fresh_same = {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 4}
        fresh_next = {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 5}

        with patch.object(relay, "_start_runner_if_enabled", return_value=FakeProcess()), \
             patch.object(relay.faulthandler, "dump_traceback"):
            first = relay.runner_watchdog_cycle({}, stalled, manager=manager, now=1000.0, stale_sec=180.0)
            repeated = relay.runner_watchdog_cycle(first["state"], stalled, manager=manager, now=1001.0, stale_sec=180.0)
            pending = relay.runner_watchdog_cycle(repeated["state"], fresh_same, manager=manager, now=1002.0, stale_sec=180.0)
            recovered = relay.runner_watchdog_cycle(pending["state"], fresh_next, manager=manager, now=1003.0, stale_sec=180.0)
            later = relay.runner_watchdog_cycle(recovered["state"], fresh_next, manager=manager, now=1004.0, stale_sec=180.0)

        self.assertEqual(first["notification"]["priority"], 4)
        self.assertIn("Selbstheilung ausgelöst", first["notification"]["body"])
        self.assertIsNone(repeated["notification"])
        self.assertIsNone(pending["notification"])
        self.assertEqual(recovered["notification"], {
            "title": "AURA Runner-Fehler",
            "body": "Selbstheilung erfolgreich — Runner wieder aktiv",
            "priority": 3,
        } if False else {
            "title": "AURA Runner wieder aktiv",
            "body": "Selbstheilung erfolgreich — Runner wieder aktiv",
            "priority": 3,
        })
        self.assertIsNone(later["notification"])

    def test_p4_fires_even_when_spawn_fails_and_retries_without_dump_spam(self):
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        stalled = {"running": True, "last_cycle_age_sec": 181.0, "cycle_count": 4}
        replacement = FakeProcess()

        with patch.object(relay, "_start_runner_if_enabled", side_effect=[None, replacement]) as start, \
             patch.object(relay.faulthandler, "dump_traceback") as dump:
            first = relay.runner_watchdog_cycle({}, stalled, manager=manager, now=1000.0, stale_sec=180.0)
            second = relay.runner_watchdog_cycle(first["state"], stalled, manager=manager, now=1001.0, stale_sec=180.0)
            third = relay.runner_watchdog_cycle(second["state"], stalled, manager=manager, now=1002.0, stale_sec=180.0)

        self.assertIsNotNone(first["notification"], "P4 must fire on stall transition even if spawn returns None")
        self.assertEqual(first["notification"]["priority"], 4)
        self.assertIn("Selbstheilung ausgelöst", first["notification"]["body"])
        self.assertFalse(first["restarted"])

        self.assertTrue(second["restarted"], "Next watchdog turn must retry spawn for existing stall event")
        self.assertIsNone(second["notification"], "Cooldown must prevent repeated P4 alert")
        self.assertFalse(third["restarted"], "Existing replacement process must not be spawned twice")

        dump.assert_called_once()
        self.assertEqual(start.call_count, 2)

class TestRelayNetworkTimeout(unittest.TestCase):
    def test_bitget_request_always_uses_ten_second_timeout(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"code":"00000","data":[]}'

        with patch.object(relay.urllib.request, "urlopen", return_value=Response()) as urlopen:
            result = relay._request("GET", "/api/v2/mix/market/contracts", {})
        self.assertEqual(result["code"], "00000")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

class TestDigestServerEquity(unittest.TestCase):
    def test_server_equity_wins_over_competing_browser_value(self):
        shared = {
            "aura-server-bot-state-v1": {"equity": 10000},
            "aura-autobot-state-v2": {"equity": 1000},
        }
        result = relay.daily_digest_transition({}, shared, now=100000.0, utc_hour=0, restart_timestamps=[])
        self.assertIn("Paper-Equity 10000.00 USDT", result["body"])
        self.assertNotIn("1000.00 USDT", result["body"])

    def test_invalid_server_equity_uses_valid_env_then_default(self):
        for invalid in (None, True, "not-a-number", float("nan"), float("inf")):
            with self.subTest(invalid=invalid), patch.dict("os.environ", {"AURA_BOT_EQUITY": "12345.5"}, clear=False):
                result = relay.daily_digest_transition(
                    {}, {"aura-server-bot-state-v1": {"equity": invalid}}, now=100000.0, utc_hour=0,
                    restart_timestamps=[],
                )
                self.assertIn("Paper-Equity 12345.50 USDT", result["body"])
        with patch.dict("os.environ", {"AURA_BOT_EQUITY": "invalid"}, clear=False):
            result = relay.daily_digest_transition({}, {}, now=100000.0, utc_hour=0, restart_timestamps=[])
        self.assertIn("Paper-Equity 10000.00 USDT", result["body"])

class TestDigestRestartCount(unittest.TestCase):
    def test_digest_counts_only_self_healings_in_previous_24_hours(self):
        now = 200000.0
        result = relay.daily_digest_transition(
            {},
            {"aura-server-bot-state-v1": {"equity": 10000}},
            now=now,
            utc_hour=0,
            restart_timestamps=[now - 10, now - 86399, now - 86401, now + 1],
        )
        self.assertIn("2 Selbstheilungen in 24 h", result["body"])

class TestRunnerReadyVisibility(unittest.TestCase):
    def test_restart_count_is_present_when_health_file_is_missing(self):
        manager = relay.RunnerManager()
        with patch.object(relay, "RUNNER_MANAGER", manager), \
             patch.object(relay.Path, "read_text", side_effect=OSError("missing")):
            health = relay._runner_health(mode="server")
        self.assertEqual(health["runner_restart_count"], 0)

    def test_restart_count_is_merged_with_existing_health(self):
        manager = relay.RunnerManager()
        manager._restart_count = 3
        payload = '{"running":true,"lastCycleAt":1,"cycleCount":9}'
        with patch.object(relay, "RUNNER_MANAGER", manager), \
             patch.object(relay.Path, "read_text", return_value=payload):
            health = relay._runner_health(mode="server")
        self.assertEqual(health["runner_restart_count"], 3)

class TestWatchdogStartupGraceIntegration(unittest.TestCase):
    @patch.object(relay, "_start_runner_if_enabled")
    def test_missing_timestamp_during_startup_grace_does_not_restart(self, start_runner):
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        result = relay.runner_watchdog_cycle(
            {},
            {"running": True, "last_cycle_age_sec": None, "cycle_count": 0},
            manager=manager,
            now=50.0,
            stale_sec=180.0,
            relay_start_time=0.0,
        )
        self.assertFalse(result["restarted"])
        start_runner.assert_not_called()


class TestRunnerPauseAwareness(unittest.TestCase):
    def test_paused_runner_heartbeat_fresh_no_restart_no_p4(self):
        """Auftrag A.1 & A.3: 10 min pause with fresh heartbeats does not trigger stall or P4."""
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        paused_health = {
            "running": True,
            "paused": True,
            "paused_by": "browser",
            "last_cycle_age_sec": 600.0,  # 10 minutes since last full trade cycle
            "last_heartbeat_age_sec": 5.0,  # fresh heartbeat every 60s
            "cycle_count": 11,
        }
        with patch.object(relay, "_start_runner_if_enabled") as start:
            result = relay.runner_watchdog_cycle({}, paused_health, manager=manager, now=2000.0, stale_sec=180.0)
            self.assertFalse(result["stalled"])
            self.assertFalse(result["restarted"])
            self.assertIsNone(result["notification"])
            start.assert_not_called()

    def test_paused_runner_stale_heartbeat_triggers_heal_and_p4(self):
        """Auftrag A.3: Genuine death during pause (heartbeat missing/stale) triggers P4 and self-healing."""
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        dead_paused_health = {
            "running": True,
            "paused": True,
            "paused_by": "browser",
            "last_cycle_age_sec": 600.0,
            "last_heartbeat_age_sec": 181.0,  # dead during pause
            "cycle_count": 11,
        }
        with patch.object(relay, "_start_runner_if_enabled", return_value=FakeProcess()) as start, \
             patch.object(relay.faulthandler, "dump_traceback"):
            result = relay.runner_watchdog_cycle({}, dead_paused_health, manager=manager, now=2000.0, stale_sec=180.0)
            self.assertTrue(result["stalled"])
            self.assertTrue(result["restarted"])
            self.assertIsNotNone(result["notification"])
            self.assertEqual(result["notification"]["priority"], 4)
            self.assertIn("Selbstheilung ausgelöst", result["notification"]["body"])
            start.assert_called_once()

    def test_pause_end_resumes_clean_cycle(self):
        """Auftrag A.3: When pause ends and next cycle runs, staleness is fully reset."""
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        resumed_health = {
            "running": True,
            "paused": False,
            "paused_by": None,
            "last_cycle_age_sec": 2.0,
            "last_heartbeat_age_sec": 2.0,
            "cycle_count": 12,
        }
        result = relay.runner_watchdog_cycle({}, resumed_health, manager=manager, now=2000.0, stale_sec=180.0)
        self.assertFalse(result["stalled"])
        self.assertFalse(result["restarted"])
        self.assertIsNone(result["notification"])

    def test_ready_health_parsing_ignores_legacy_paused_fields_in_server_mode(self):
        """R39: server mode exposes heartbeat age but never reports browser pause ownership."""
        payload = '{"running":true,"lastCycleAt":1000,"lastHeartbeatAt":99000,"paused":true,"pausedBy":"browser","cycleCount":5,"tradeCount":0,"equity":10000}'
        with patch.object(relay.Path, "read_text", return_value=payload), \
             patch.object(relay.time, "time", return_value=100.0):
            health = relay._runner_health(mode="server")
            self.assertFalse(health["paused"])
            self.assertIsNone(health["paused_by"])
            self.assertEqual(health["last_cycle_age_sec"], 99.0)
            self.assertEqual(health["last_heartbeat_age_sec"], 1.0)


class TestWatchdogHealUncoupledFromAlertCooldown(unittest.TestCase):
    def test_second_stall_within_alert_cooldown_triggers_heal_without_p4(self):
        """Auftrag C: Second stall within 3600s alert cooldown triggers heal and increments count, without second P4."""
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        stalled_1 = {"running": True, "last_cycle_age_sec": 181.0, "cycle_count": 5}
        stalled_2 = {"running": True, "last_cycle_age_sec": 185.0, "cycle_count": 5}

        with patch.object(relay, "_start_runner_if_enabled", side_effect=[FakeProcess(), FakeProcess()]) as start, \
             patch.object(relay.faulthandler, "dump_traceback"):
            # 1st stall at t=1000 -> P4 + Heal #1
            turn_1 = relay.runner_watchdog_cycle({}, stalled_1, manager=manager, now=1000.0, stale_sec=180.0)
            self.assertTrue(turn_1["stalled"])
            self.assertTrue(turn_1["restarted"])
            self.assertIsNotNone(turn_1["notification"])
            self.assertEqual(turn_1["notification"]["priority"], 4)
            self.assertEqual(manager.snapshot(now=1000.0)["runner_restart_count"], 1)

            # 2nd stall at t=1500 (within 3600s cooldown) -> NO P4, but Heal #2 executes!
            turn_2 = relay.runner_watchdog_cycle(turn_1["state"], stalled_2, manager=manager, now=1500.0, stale_sec=180.0)
            self.assertTrue(turn_2["stalled"])
            self.assertTrue(turn_2["restarted"])
            self.assertIsNone(turn_2["notification"], "Notification must be suppressed by cooldown")
            self.assertEqual(manager.snapshot(now=1500.0)["runner_restart_count"], 2)
            self.assertEqual(start.call_count, 2)


class TestHealingReceiptDelivery(unittest.TestCase):
    def test_p3_receipt_delivered_on_completed_follow_up_cycle(self):
        """Auftrag B: After watchdog restart, first completed follow-up cycle delivers P3 receipt."""
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        stalled = {"running": True, "last_cycle_age_sec": 181.0, "cycle_count": 10}
        healthy_followup = {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 11}
        subsequent_cycle = {"running": True, "last_cycle_age_sec": 1.0, "cycle_count": 12}

        with patch.object(relay, "_start_runner_if_enabled", return_value=FakeProcess()), \
             patch.object(relay.faulthandler, "dump_traceback"):
            # Turn 1: Stall & restart
            turn_1 = relay.runner_watchdog_cycle({}, stalled, manager=manager, now=1000.0, stale_sec=180.0)
            self.assertTrue(turn_1["restarted"])
            self.assertEqual(turn_1["notification"]["priority"], 4)

            # Turn 2: Follow-up cycle completes (cycle 10 -> 11) -> P3 receipt sent!
            turn_2 = relay.runner_watchdog_cycle(turn_1["state"], healthy_followup, manager=manager, now=1060.0, stale_sec=180.0)
            self.assertFalse(turn_2["restarted"])
            self.assertTrue(turn_2["recovered"])
            self.assertIsNotNone(turn_2["notification"])
            self.assertEqual(turn_2["notification"]["priority"], 3)
            self.assertEqual(turn_2["notification"]["title"], "AURA Runner wieder aktiv")
            self.assertEqual(turn_2["notification"]["body"], "Selbstheilung erfolgreich — Runner wieder aktiv")

            # Turn 3: Normal next cycle -> no more P3 receipt
            turn_3 = relay.runner_watchdog_cycle(turn_2["state"], subsequent_cycle, manager=manager, now=1120.0, stale_sec=180.0)
            self.assertFalse(turn_3["recovered"])
            self.assertIsNone(turn_3["notification"])

    def test_p3_receipt_delivered_when_recovering_in_paused_mode(self):
        """Auftrag B: If runner restarts and recovers into healthy paused mode, P3 receipt is delivered."""
        manager = relay.RunnerManager()
        manager.set_process(FakeProcess())
        stalled = {"running": True, "last_cycle_age_sec": 181.0, "cycle_count": 10}
        paused_followup = {
            "running": True,
            "paused": True,
            "paused_by": "browser",
            "last_cycle_age_sec": 181.0,
            "last_heartbeat_age_sec": 1.0,
            "cycle_count": 10,
        }

        with patch.object(relay, "_start_runner_if_enabled", return_value=FakeProcess()), \
             patch.object(relay.faulthandler, "dump_traceback"):
            turn_1 = relay.runner_watchdog_cycle({}, stalled, manager=manager, now=1000.0, stale_sec=180.0)
            self.assertTrue(turn_1["restarted"])

            turn_2 = relay.runner_watchdog_cycle(turn_1["state"], paused_followup, manager=manager, now=1060.0, stale_sec=180.0)
            self.assertTrue(turn_2["recovered"])
            self.assertIsNotNone(turn_2["notification"])
            self.assertEqual(turn_2["notification"]["priority"], 3)
            self.assertEqual(turn_2["notification"]["body"], "Selbstheilung erfolgreich — Runner wieder aktiv")

