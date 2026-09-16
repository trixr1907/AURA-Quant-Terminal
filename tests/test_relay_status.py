#!/usr/bin/env python3
"""Tests for Auftrag A: Human Status Page GET /status in bitget_relay.py.

Covers:
1. mask_ntfy_url helper: ensures topics are masked and never exposed in plain text.
2. render_status_html:
   - ALLES OK banner when nominal.
   - HANDLUNGSBEDARF banner under at least 3 distinct failure scenarios:
     * Server-bot active but runner stopped/stale.
     * Active market data error code.
     * Low disk space (<= 500 MB).
   - Sensitive ntfy topics never leak into HTML.
   - Version consistency with VERSION / /serving.
   - Self-contained HTML (no external scripts or links).
3. HTTP server integration: GET /status returns 200 and text/html; charset=utf-8.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import bitget_relay


class TestNtfyMasking(unittest.TestCase):
    """Verify ntfy URL masking guarantees."""

    def test_empty_or_none(self):
        self.assertEqual(bitget_relay.mask_ntfy_url(None), "Nicht konfiguriert")
        self.assertEqual(bitget_relay.mask_ntfy_url(""), "Nicht konfiguriert")
        self.assertEqual(bitget_relay.mask_ntfy_url("   "), "Nicht konfiguriert")

    def test_standard_topic_masked(self):
        url = "https://ntfy.sh/aura-live-secret-topic-987"
        masked = bitget_relay.mask_ntfy_url(url)
        self.assertEqual(masked, "https://ntfy.sh/aura-l…")
        self.assertNotIn("secret", masked)
        self.assertNotIn("987", masked)

    def test_custom_host_masked(self):
        url = "http://push.myhomelab.local:8080/super-secret-feed"
        masked = bitget_relay.mask_ntfy_url(url)
        self.assertEqual(masked, "http://push.myhomelab.local:8080/super-…")
        self.assertNotIn("secret-feed", masked)

    def test_short_topic_masked(self):
        self.assertEqual(bitget_relay.mask_ntfy_url("https://ntfy.sh/abc"), "https://ntfy.sh/ab…")
        self.assertEqual(bitget_relay.mask_ntfy_url("https://ntfy.sh/a"), "https://ntfy.sh/…")


class TestRenderStatusHtml(unittest.TestCase):
    """Test unit rendering and health logic for render_status_html."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="aura_status_test_")
        self.state_dir = Path(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_nominal_ok_banner_mode_none(self):
        """When bot is not in server mode (default/mode=none), banner is ALLES OK."""
        with patch.dict(os.environ, {"AURA_BOT_MODE": "none", "AURA_NTFY_URL": ""}, clear=False):
            with patch("bitget_relay.market_data_health_snapshot", return_value={"last_error_code": None, "last_success_age_seconds": 5.0, "inflight": 0}):
                html = bitget_relay.render_status_html(
                    disk_free_mb_override=2048.0,
                    state_dir_override=self.state_dir,
                )
                self.assertIn("ALLES OK", html)
                self.assertIn("banner-ok", html)
                self.assertNotIn("HANDLUNGSBEDARF", html)
                self.assertIn("scripts/ops/aura_doctor.sh", html)
                self.assertIn(f"v{bitget_relay.VERSION}", html)
                self.assertIn("SOFTWARE_GO / MODEL_NO_EVIDENCE", html)
                self.assertIn("Bewusst nicht als Server-Bot konfiguriert", html)

    def test_nominal_ok_banner_server_mode(self):
        """When bot is in server mode and runner is fresh, banner is ALLES OK."""
        runner_health = {
            "mode": "server",
            "bot_enabled": True,
            "running": True,
            "state": "running",
            "last_cycle_age_sec": 12.0,
            "last_heartbeat_age_sec": 12.0,
            "paused": False,
            "paused_by": None,
            "cycle_count": 42,
            "trade_count": 0,
            "equity": 10000.0,
        }
        with patch.dict(os.environ, {"AURA_BOT_MODE": "server", "AURA_NTFY_URL": "https://ntfy.sh/secret-topic-12345"}, clear=False):
            with patch("bitget_relay._runner_health", return_value=runner_health):
                with patch("bitget_relay.market_data_health_snapshot", return_value={"last_error_code": None, "last_success_age_seconds": 5.0, "inflight": 0}):
                    html = bitget_relay.render_status_html(
                        disk_free_mb_override=4096.0,
                        state_dir_override=self.state_dir,
                    )
                    self.assertIn("ALLES OK", html)
                    self.assertIn("banner-ok", html)
                    self.assertIn("Server-Only Live seit v2.5.0 — kein Pause mehr, Dashboard ist Viewer+Config", html)
                    self.assertIn("Nein (Server-Only Live seit v2.5.0)", html)
                    self.assertIn("Bot Aktiv</span><span class=\"val val-ok\">Ja", html)
                    # Secret topic must be masked
                    self.assertNotIn("secret-topic-12345", html)
                    self.assertIn("https://ntfy.sh/secret…", html)

    def test_fail_mode_1_server_bot_runner_stopped(self):
        """Failure mode 1: AURA_BOT_MODE=server but runner is stopped."""
        runner_health = {
            "mode": "server",
            "bot_enabled": True,
            "running": False,
            "state": "stopped",
            "last_cycle_age_sec": None,
            "last_heartbeat_age_sec": None,
            "paused": False,
            "paused_by": None,
            "cycle_count": 0,
            "trade_count": 0,
            "equity": None,
        }
        with patch.dict(os.environ, {"AURA_BOT_MODE": "server"}, clear=False):
            with patch("bitget_relay._runner_health", return_value=runner_health):
                with patch("bitget_relay.market_data_health_snapshot", return_value={"last_error_code": None, "last_success_age_seconds": 5.0, "inflight": 0}):
                    html = bitget_relay.render_status_html(
                        disk_free_mb_override=2048.0,
                        state_dir_override=self.state_dir,
                    )
                    self.assertIn("HANDLUNGSBEDARF", html)
                    self.assertIn("banner-error", html)
                    self.assertIn("Runner läuft nicht", html)

    def test_fail_mode_1b_server_bot_runner_stale_cycle(self):
        """Failure mode 1b: AURA_BOT_MODE=server, runner is running but cycle is stale (> threshold)."""
        runner_health = {
            "mode": "server",
            "bot_enabled": True,
            "running": True,
            "state": "running",
            "last_cycle_age_sec": 500.0,
            "last_heartbeat_age_sec": 500.0,
            "paused": False,
            "paused_by": None,
            "cycle_count": 10,
            "trade_count": 0,
            "equity": 10000.0,
        }
        with patch.dict(os.environ, {"AURA_BOT_MODE": "server", "AURA_RUNNER_STALE_SEC": "180"}, clear=False):
            with patch("bitget_relay._runner_health", return_value=runner_health):
                with patch("bitget_relay.market_data_health_snapshot", return_value={"last_error_code": None, "last_success_age_seconds": 5.0, "inflight": 0}):
                    html = bitget_relay.render_status_html(
                        disk_free_mb_override=2048.0,
                        state_dir_override=self.state_dir,
                    )
                    self.assertIn("HANDLUNGSBEDARF", html)
                    self.assertIn("Server-Bot-Runner ist nicht frisch", html)

    def test_fail_mode_2_market_data_error(self):
        """Failure mode 2: Market data health has an active error code."""
        with patch.dict(os.environ, {"AURA_BOT_MODE": "none"}, clear=False):
            with patch("bitget_relay.market_data_health_snapshot", return_value={"last_error_code": "BITGET_HTTP_502", "last_success_age_seconds": 200.0, "inflight": 0}):
                html = bitget_relay.render_status_html(
                    disk_free_mb_override=2048.0,
                    state_dir_override=self.state_dir,
                )
                self.assertIn("HANDLUNGSBEDARF", html)
                self.assertIn("Market-Data-Fehler aktiv: BITGET_HTTP_502", html)

    def test_fail_mode_3_low_disk_space(self):
        """Failure mode 3: Disk free space is <= 500 MB."""
        with patch.dict(os.environ, {"AURA_BOT_MODE": "none"}, clear=False):
            with patch("bitget_relay.market_data_health_snapshot", return_value={"last_error_code": None, "last_success_age_seconds": 5.0, "inflight": 0}):
                html = bitget_relay.render_status_html(
                    disk_free_mb_override=320.5,
                    state_dir_override=self.state_dir,
                )
                self.assertIn("HANDLUNGSBEDARF", html)
                self.assertIn("Festplattenspeicher knapp: 320.5 MB frei", html)

    def test_self_contained_html(self):
        """Ensure the rendered HTML has no external resources (scripts or stylesheets)."""
        html = bitget_relay.render_status_html(state_dir_override=self.state_dir)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link rel=\"stylesheet\"", html)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<meta charset=\"utf-8\">", html)


    def test_server_mode_ignores_legacy_paused_health_flag(self):
        payload = '{"running":true,"lastCycleAt":99000,"lastHeartbeatAt":99000,"paused":true,"pausedBy":"browser","cycleCount":5,"tradeCount":0,"equity":10000}'
        with patch.object(bitget_relay.Path, "read_text", return_value=payload), \
             patch.object(bitget_relay.time, "time", return_value=100.0):
            health = bitget_relay._runner_health(mode="server")
        self.assertFalse(health["paused"])
        self.assertIsNone(health["paused_by"])
        self.assertEqual(health["state"], "running")


class TestStatusHttpEndpoint(unittest.TestCase):
    """Integration test: start relay on ephemeral port and request GET /status."""

    @classmethod
    def setUpClass(cls):
        cls.server = bitget_relay.ThreadingHTTPServer(("127.0.0.1", 0), bitget_relay.RelayHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        for _ in range(20):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/serving", timeout=0.5)
                break
            except Exception:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_status_200_html(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            content_type = resp.headers.get("Content-Type", "")
            self.assertIn("text/html", content_type)
            self.assertIn("charset=utf-8", content_type.lower())
            body = resp.read().decode("utf-8")
            self.assertIn("<!DOCTYPE html>", body)
            self.assertIn("AURA Status", body)
            self.assertIn("ALLES OK", body)


if __name__ == "__main__":
    unittest.main()
