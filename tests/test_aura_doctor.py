#!/usr/bin/env python3
"""Tests for Auftrag B: scripts/ops/aura_doctor.sh diagnostic tool.

Covers:
1. Syntax validation via bash -n.
2. CLI help output and exit code 0.
3. JSON output structure and schema compliance.
4. Masked output guarantees (secret topics never exposed in output).
5. Integration with mocked relay endpoint.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCTOR_SCRIPT = ROOT / "scripts" / "ops" / "aura_doctor.sh"


class MockRelayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/serving":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "version": "1.10.1", "port": 8787, "mode": "quant_research"}')
        elif self.path == "/ready":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "bot_enabled": true, "mode": "server", "state": "running", "cycle_count": 15, "last_cycle_age_sec": 10.5, "paused": false}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class TestAuraDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="doctor_test_")
        self.state_dir = Path(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_bash_syntax_clean(self):
        """Ensure script passes bash -n syntax check."""
        res = subprocess.run(["bash", "-n", str(DOCTOR_SCRIPT)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"bash -n failed: {res.stderr}")

    def test_help_flag_exits_zero(self):
        """Ensure --help returns 0 and prints usage."""
        res = subprocess.run([str(DOCTOR_SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("AURA Doctor", res.stdout)
        self.assertIn("Verwendung:", res.stdout)

    def test_json_output_structure(self):
        """Ensure --json outputs valid parseable JSON with expected keys."""
        res = subprocess.run(
            [str(DOCTOR_SCRIPT), "--json", "--state-dir", str(self.state_dir)],
            capture_output=True,
            text=True
        )
        # May exit 0 or 1 depending on container presence, but JSON must be valid
        self.assertTrue(len(res.stdout.strip()) > 0)
        data = json.loads(res.stdout)
        self.assertIn("status", data)
        self.assertIn("counts", data)
        self.assertIn("checks", data)
        self.assertIn("pass", data["counts"])
        self.assertIn("warn", data["counts"])
        self.assertIn("fail", data["counts"])
        self.assertIsInstance(data["checks"], list)

    def test_mocked_relay_integration(self):
        """Test with mock relay responding to /serving and /ready."""
        server = HTTPServer(("127.0.0.1", 0), MockRelayHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        # Create dummy env file
        env_file = self.state_dir / "aura_bot.env"
        env_file.write_text("AURA_BOT_MODE=server\nAURA_NTFY_URL=https://ntfy.sh/secret-topic-9999\n", encoding="utf-8")

        try:
            res = subprocess.run(
                [
                    str(DOCTOR_SCRIPT),
                    "--json",
                    "--relay-url", f"http://127.0.0.1:{port}",
                    "--state-dir", str(self.state_dir),
                ],
                capture_output=True,
                text=True
            )
            data = json.loads(res.stdout)
            checks_by_id = {c["id"]: c for c in data["checks"]}
            self.assertEqual(checks_by_id["relay_serving"]["status"], "PASS")
            self.assertEqual(checks_by_id["bot_ready"]["status"], "PASS")
            self.assertEqual(checks_by_id["env_file"]["status"], "PASS")
            # Ensure secret topic is never leaked
            self.assertNotIn("secret-topic-9999", res.stdout)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
