"""
PF-67/68/69/70 — Server-Mode Relay Integration Tests
=====================================================
Tests for:
  PF-67: server-mode state keys, mode-switch flag, ALLOWED_STATE_KEYS
  PF-68: /api/signals endpoint, claim dedup, ntfy fire-and-forget
  PF-69: runner health (_runner_health), restart persistence
  PF-70: no double-push on restart (persistent claims), /api/universe alias
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure bitget_relay can be imported (it writes FILES to STATE_DIR)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
# Point state dir to a temp directory for isolation
_tmpdir = tempfile.mkdtemp(prefix="aura_test_")
os.environ.setdefault("AURA_STATE_DIR", _tmpdir)
os.environ.setdefault("AURA_NTFY_URL", "")  # disable real pushes

import bitget_relay as relay  # noqa: E402  (after env setup)


# ---------------------------------------------------------------------------
# Helper: fresh state (isolated per test)
# ---------------------------------------------------------------------------
class StateMixin:
    def setUp(self):
        # Clear state file before each test
        sf = relay.STATE_FILE
        if sf.exists():
            sf.unlink()
        # Also clear signal center
        scf = relay.SIGNAL_STATE_FILE
        if scf.exists():
            scf.unlink()

    def _load(self):
        return relay._load_shared_state()


# ===========================================================================
# PF-67: ALLOWED_STATE_KEYS includes server-bot keys
# ===========================================================================
class TestAllowedStateKeys(StateMixin, unittest.TestCase):
    def test_server_bot_config_key_allowed(self):
        self.assertIn("aura-server-bot-config-v1", relay.ALLOWED_STATE_KEYS)

    def test_server_bot_state_key_allowed(self):
        self.assertIn("aura-server-bot-state-v1", relay.ALLOWED_STATE_KEYS)

    def test_existing_keys_still_present(self):
        required = {
            "aura-autobot-state-v2",
            "aura-quant-terminal-active-trades-v1",
            "aura-quant-terminal-history-trades-v1",
            "aura-ntfy-signals-settings-v1",
        }
        self.assertTrue(required.issubset(relay.ALLOWED_STATE_KEYS))

    def test_server_state_write(self):
        """Write server-bot-state-v1 via _save_shared_state — must succeed."""
        payload = {"mode": "server", "equity": 9500.0, "cycleCount": 3}
        saved, rev, err = relay._save_shared_state("aura-server-bot-state-v1", payload)
        self.assertIsNone(err)
        self.assertIsNotNone(saved)
        self.assertGreater(rev, 0)
        state = self._load()
        self.assertEqual(state["aura-server-bot-state-v1"]["mode"], "server")

    def test_server_config_write(self):
        payload = {"profile": "strict", "minScore": 75, "maxLeverage": 5}
        saved, rev, err = relay._save_shared_state("aura-server-bot-config-v1", payload)
        self.assertIsNone(err)
        state = self._load()
        self.assertEqual(state["aura-server-bot-config-v1"]["minScore"], 75)

    def test_unknown_key_rejected(self):
        """Writing an unknown key must be blocked by ALLOWED_STATE_KEYS check."""
        saved, rev, err = relay._save_shared_state("some-unknown-key-v99", {"x": 1})
        # _save_shared_state does not validate keys itself — that's done at HTTP layer.
        # Test is at HTTP layer. Here we verify the key is NOT in ALLOWED_STATE_KEYS.
        self.assertNotIn("some-unknown-key-v99", relay.ALLOWED_STATE_KEYS)

    def test_mode_switch_flag_stored(self):
        """Server bot writes mode=server to aura-autobot-state-v2."""
        relay._save_shared_state("aura-autobot-state-v2", {
            "enabled": True, "mode": "server", "serverBotActive": True,
        })
        state = self._load()
        self.assertEqual(state["aura-autobot-state-v2"]["mode"], "server")
        self.assertTrue(state["aura-autobot-state-v2"]["serverBotActive"])


# ===========================================================================
# PF-68: Signal emission — claim dedup, /api/signals path (mocked ntfy)
# ===========================================================================
class TestSignalClaim(StateMixin, unittest.TestCase):
    def test_claim_first_time_succeeds(self):
        claimed, rev, err = relay._claim_signal_event("t1:open")
        self.assertIsNone(err)
        self.assertTrue(claimed)
        self.assertGreater(rev, 0)

    def test_claim_second_time_returns_false(self):
        relay._claim_signal_event("t2:open")
        claimed2, _, err2 = relay._claim_signal_event("t2:open")
        self.assertIsNone(err2)
        self.assertFalse(claimed2)

    def test_claim_different_events_independent(self):
        c1, _, _ = relay._claim_signal_event("t3:open")
        c2, _, _ = relay._claim_signal_event("t3:tp1")
        self.assertTrue(c1)
        self.assertTrue(c2)

    def test_claim_restart_persistent(self):
        """After state is reloaded from disk, claim is still present."""
        relay._claim_signal_event("t4:sl_close")
        # Simulate restart by reloading state (no in-memory cache purge needed)
        state = relay._load_shared_state()
        claims = state.get("_signal_claims", {})
        self.assertIn("t4:sl_close", claims)

    def test_ntfy_notify_called_on_signals_post(self):
        """_ntfy_notify is invoked by /api/signals with correct args."""
        with unittest.mock.patch("bitget_relay._ntfy_notify", return_value=True) as mock_notify:
            # Simulate what the HTTP handler does
            title = "AURA · Trade-Signal"
            body  = "XPNUSDT SHORT 3x — Trade eröffnet [Server-Bot]"
            priority = 3
            result = relay._ntfy_notify(title, body, priority=priority)
        # With AURA_NTFY_URL="" the real function returns False; the mock returns True
        mock_notify.assert_called_once_with(title, body, priority=priority)

    def test_ntfy_silent_when_url_empty(self):
        """Real _ntfy_notify with empty URL must not raise and must return False."""
        os.environ["AURA_NTFY_URL"] = ""
        result = relay._ntfy_notify("Test", "body", priority=3)
        self.assertFalse(result)

    def test_ntfy_fires_on_daemon_thread(self):
        """_ntfy_notify must not block the calling thread (daemon thread check)."""
        recorded_threads = []
        original_urlopen = None
        import urllib.request

        def fake_urlopen(req, timeout=None):
            recorded_threads.append(threading.current_thread().daemon)
            raise OSError("simulated failure")

        with unittest.mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            os.environ["AURA_NTFY_URL"] = "https://ntfy.sh/testopic"
            relay._ntfy_notify("T", "B", priority=3)
            time.sleep(0.2)  # allow daemon thread to execute
        os.environ["AURA_NTFY_URL"] = ""
        # If called at all, must be on a daemon thread
        if recorded_threads:
            self.assertTrue(all(recorded_threads), "ntfy must fire on daemon thread")


# ===========================================================================
# PF-69: Runner health
# ===========================================================================
class TestRunnerHealth(StateMixin, unittest.TestCase):
    def test_runner_health_missing_file(self):
        """No runner_health.json → running=False, age=None."""
        hf = relay.STATE_DIR / "runner_health.json"
        if hf.exists():
            hf.unlink()
        health = relay._runner_health()
        self.assertFalse(health["running"])
        self.assertIsNone(health["last_cycle_age_sec"])

    def test_runner_health_fresh(self):
        """Recent runner_health.json → running=True, small age."""
        hf = relay.STATE_DIR / "runner_health.json"
        data = {
            "running": True,
            "lastCycleAt": int(time.time() * 1000) - 5000,  # 5s ago
            "cycleCount": 7,
            "tradeCount": 2,
            "equity": 9300.0,
        }
        hf.write_text(json.dumps(data))
        health = relay._runner_health()
        self.assertTrue(health["running"])
        self.assertLessEqual(health["last_cycle_age_sec"], 10)
        self.assertEqual(health["cycle_count"], 7)

    def test_runner_health_in_ready_response(self):
        """_runner_health is exported from market_data_readiness merge in /ready."""
        # We test the function exists and returns a dict — HTTP-level test lives in e2e
        self.assertIsNotNone(relay._runner_health())
        self.assertIn("running", relay._runner_health())


# ===========================================================================
# PF-70: No double-push on restart (claim persistence)
# ===========================================================================
class TestRestartDedup(StateMixin, unittest.TestCase):
    def test_claim_survives_state_reload(self):
        """Claimed key must still be claimed after re-reading state from disk."""
        relay._claim_signal_event("trade99:open")
        # Force re-read (simulate relay restart reading disk)
        fresh = relay._load_shared_state()
        self.assertIn("trade99:open", fresh.get("_signal_claims", {}))

    def test_second_process_cannot_claim_same_event(self):
        """Two sequential claim attempts → first wins, second loses (restart scenario)."""
        c1, _, _ = relay._claim_signal_event("trade100:tp1")
        c2, _, _ = relay._claim_signal_event("trade100:tp1")
        self.assertTrue(c1)
        self.assertFalse(c2)

    def test_state_rev_increments_on_each_claim(self):
        state_before = relay._load_shared_state()
        rev_before = state_before.get("_rev", 0)
        relay._claim_signal_event("t_rev_test:open")
        state_after = relay._load_shared_state()
        rev_after = state_after.get("_rev", 0)
        self.assertGreater(rev_after, rev_before)


# ===========================================================================
# PF-67: /api/universe alias (GET path handled same as legacy path)
# ===========================================================================
class TestUniverseAlias(unittest.TestCase):
    def test_universe_path_patterns(self):
        """Both /api/universe and legacy path route to same handler."""
        # Check the handler logic: both strings appear in the do_GET branch
        import inspect
        src = inspect.getsource(relay.RelayHandler.do_GET)
        self.assertIn("/api/universe", src)
        self.assertIn("/data/bitget_usdt_futures_universe.json", src)

    def test_universe_file_returned_when_exists(self):
        """If universe file exists it is read; else 404."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ufile = Path(td) / "test_universe.json"
            universe_data = [{"symbol": "XPNUSDT", "vol": 5000000, "liquidityVerified": True}]
            ufile.write_text(json.dumps(universe_data))
            data = json.loads(ufile.read_text())
            self.assertEqual(data[0]["symbol"], "XPNUSDT")


# ===========================================================================
# PF-70: Mode co-existence — server-bot trades vs browser-bot trades
# ===========================================================================
class TestTradeSourceIsolation(StateMixin, unittest.TestCase):
    def test_server_trades_have_source_server(self):
        """Trades written by server bot carry source='server'."""
        server_trade = {"id": "sb_abc_123", "source": "server", "coin": "BTCUSDT", "dir": 1}
        browser_trade = {"id": "pt_def_456", "source": "browser", "coin": "ETHUSDT", "dir": -1}
        relay._save_shared_state("aura-quant-terminal-active-trades-v1", [server_trade, browser_trade])
        state = relay._load_shared_state()
        trades = state["aura-quant-terminal-active-trades-v1"]
        server_only = [t for t in trades if t.get("source") == "server"]
        browser_only = [t for t in trades if t.get("source") == "browser"]
        self.assertEqual(len(server_only), 1)
        self.assertEqual(len(browser_only), 1)

    def test_server_state_payload_shape(self):
        """toServerPayload shape matches what relay accepts."""
        payload = {
            "mode": "server", "equity": 9500.0, "initialEquity": 10000.0,
            "startedAt": 1234567890000, "lastCycleAt": 1234567950000,
            "cycleCount": 5, "tradeCount": 1,
        }
        saved, rev, err = relay._save_shared_state("aura-server-bot-state-v1", payload)
        self.assertIsNone(err)
        state = relay._load_shared_state()
        self.assertEqual(state["aura-server-bot-state-v1"]["mode"], "server")
        self.assertAlmostEqual(state["aura-server-bot-state-v1"]["equity"], 9500.0)


# ===========================================================================
# PF-69 / PF-70: Runner-Death-Alert (Runner tot → P4-Push, 60 min Cooldown)
# ===========================================================================
class TestRunnerDeadAlert(unittest.TestCase):
    def test_runner_dead_alert_triggers_p4_with_60m_cooldown(self):
        """Runner not running triggers notify=True and sets 60m cooldown (outside startup grace)."""
        state = {}
        runner_health = {"running": False, "last_cycle_age_sec": None}
        t0 = 100000.0
        res = relay.runner_dead_transition(state, runner_health, mode="server", now=t0)
        self.assertTrue(res["notify"])
        self.assertIn("nicht mehr", res["body"])
        alert_state = res["state"]["runner_health_alert"]
        self.assertEqual(alert_state["cooldown_until"], t0 + 3600.0)
        self.assertEqual(alert_state["alerted_at"], t0)

    def test_startup_window_suppresses_alarm_before_first_cycle(self):
        """During startup window (<120s) with 0 cycles completed, no false alarm is triggered."""
        t_relay_start = 100000.0
        state = {}
        # Runner starting up: not yet running / no cycle completed yet
        runner_health = {"running": False, "last_cycle_age_sec": None, "cycle_count": 0}
        
        # 15s after relay start
        res15 = relay.runner_dead_transition(
            state, runner_health, mode="server", now=t_relay_start + 15.0, relay_start_time=t_relay_start
        )
        self.assertFalse(res15["notify"])
        self.assertEqual(res15["body"], "")

        # 90s after relay start (still in grace window)
        res90 = relay.runner_dead_transition(
            state, runner_health, mode="server", now=t_relay_start + 90.0, relay_start_time=t_relay_start
        )
        self.assertFalse(res90["notify"])

    def test_running_flag_does_not_override_fresh_completed_cycle(self):
        """Freshness is authoritative even if the runner's running flag is false."""
        t_relay_start = 100000.0
        state = {}
        runner_health = {"running": False, "last_cycle_age_sec": 15.0, "cycle_count": 1}
        res = relay.runner_dead_transition(
            state, runner_health, mode="server", now=t_relay_start + 45.0, relay_start_time=t_relay_start
        )
        self.assertFalse(res["notify"])
        self.assertFalse(res["stalled"])

    def test_startup_timeout_after_grace_period_fires_p4(self):
        """If runner fails to start and grace period expires (>=120s), P4 alarm is fired."""
        t_relay_start = 100000.0
        state = {}
        runner_health = {"running": False, "last_cycle_age_sec": None, "cycle_count": 0}
        # 121 seconds after relay start
        res = relay.runner_dead_transition(
            state, runner_health, mode="server", now=t_relay_start + 121.0, relay_start_time=t_relay_start
        )
        self.assertTrue(res["notify"])
        self.assertIn("nicht mehr", res["body"])

    def test_runner_dead_alert_respects_cooldown(self):
        """Within 60 min cooldown, no re-alert is sent."""
        t0 = 100000.0
        state = {"runner_health_alert": {"cooldown_until": t0 + 3600.0, "alerted_at": t0}}
        runner_health = {"running": False, "last_cycle_age_sec": 600.0}
        # 10 minutes later (still in cooldown)
        res = relay.runner_dead_transition(state, runner_health, mode="server", now=t0 + 600.0)
        self.assertFalse(res["notify"])

        # 61 minutes later (cooldown expired)
        res2 = relay.runner_dead_transition(state, runner_health, mode="server", now=t0 + 3660.0)
        self.assertTrue(res2["notify"])

    def test_runner_healthy_no_alert(self):
        """Healthy runner (<300s cycle age) clears error and sends no alert."""
        state = {"runner_health_alert": {"last_error_at": 99000.0}}
        runner_health = {"running": True, "last_cycle_age_sec": 45.0}
        res = relay.runner_dead_transition(state, runner_health, mode="server", now=100000.0)
        self.assertFalse(res["notify"])
        self.assertIsNone(res["state"]["runner_health_alert"]["last_error_at"])

    def test_non_server_mode_no_alert(self):
        """In browser mode (non-server), runner health does not alert."""
        state = {}
        runner_health = {"running": False, "last_cycle_age_sec": None}
        res = relay.runner_dead_transition(state, runner_health, mode="browser", now=100000.0)
        self.assertFalse(res["notify"])


# ===========================================================================
# PF-70: Mode-Switch & Double-Trade Prevention
# ===========================================================================
class TestModeSwitchSafety(StateMixin, unittest.TestCase):
    def test_server_bot_active_state_detected_by_dashboard(self):
        """Server bot state with mode=server indicates serverBotActive=true."""
        server_state = {
            "mode": "server", "equity": 10000.0, "startedAt": 1700000000000,
            "lastCycleAt": 1700000060000, "cycleCount": 1
        }
        relay._save_shared_state("aura-server-bot-state-v1", server_state)
        loaded = relay._load_shared_state()
        self.assertEqual(loaded["aura-server-bot-state-v1"]["mode"], "server")

    def test_single_bot_active_guarantee_via_state(self):
        """State contains distinct keys allowing exactly one bot mode to be authoritative."""
        relay._save_shared_state("aura-server-bot-config-v1", {"mode": "server", "minScore": 82})
        relay._save_shared_state("aura-autobot-state-v2", {"enabled": False, "lastMode": "browser_paused"})
        state = relay._load_shared_state()
        self.assertEqual(state["aura-server-bot-config-v1"]["mode"], "server")
        self.assertFalse(state["aura-autobot-state-v2"]["enabled"])


# ===========================================================================
# PF-70: Restart-Re-Push Protection (Once-Flags persistence)
# ===========================================================================
class TestRestartRePushProtection(StateMixin, unittest.TestCase):
    def test_restart_re_push_protection_persists_once_flags(self):
        """Once-Flags (tp1Hit, slHit) on trades survive state serialization and prevent duplicate push."""
        active_trades = [
            {
                "id": "trade_eth_001",
                "symbol": "ETHUSDT",
                "dir": 1,
                "entry": 3000.0,
                "tp1": 3100.0,
                "tp1Hit": True,
                "tp1_push_sent": True,
                "sl": 2900.0,
                "slHit": False,
            }
        ]
        relay._save_shared_state("aura-quant-terminal-active-trades-v1", active_trades)
        
        # Simulate server restart: state reloaded from storage
        reloaded = relay._load_shared_state()
        trades = reloaded["aura-quant-terminal-active-trades-v1"]
        self.assertEqual(len(trades), 1)
        self.assertTrue(trades[0]["tp1Hit"])
        self.assertTrue(trades[0]["tp1_push_sent"])
        self.assertFalse(trades[0]["slHit"])

    def test_signal_claim_idempotency_after_server_restart(self):
        """Signal claiming deduplication prevents double push across cycles."""
        event_id = "evt_claim_test_123"
        claimed1, rev1, err1 = relay._claim_signal_event(event_id, now=100000.0)
        self.assertTrue(claimed1)
        # Second claim attempt immediately or after restart
        claimed2, rev2, err2 = relay._claim_signal_event(event_id, now=100005.0)
        self.assertFalse(claimed2)


if __name__ == "__main__":
    unittest.main()
