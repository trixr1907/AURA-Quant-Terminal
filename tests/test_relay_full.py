"""
test_relay_full.py — Comprehensive tests for AURA v1.0.7 read-only relay
============================================================================
Focus: HTTP serving, public data proxying, canonical request formatting,
error handling, and client disconnect tolerance.
"""

from __future__ import annotations

import json
import threading
import time
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch, MagicMock

import bitget_relay
from bitget_relay import (
    PORT,
    RelayHandler,
    RelayServer,
    _canonical_request,
    _parse_allowed_hosts,
    _request,
)


# ===========================================================================
# 1. CANONICAL REQUEST FORMATTING
# ===========================================================================
class TestCanonicalRequest(unittest.TestCase):
    def test_allowed_hosts_parser_includes_loopback_and_configured_lan_host(self):
        hosts = _parse_allowed_hosts("192.168.8.115, aura.internal")
        self.assertEqual(hosts, {"127.0.0.1", "localhost", "192.168.8.115", "aura.internal"})

    def test_allowed_hosts_parser_rejects_ports_and_userinfo(self):
        hosts = _parse_allowed_hosts("192.168.8.115:8787, user@evil.example, valid.example")
        self.assertEqual(hosts, {"127.0.0.1", "localhost", "valid.example"})

    def test_canonical_get_includes_query_in_url(self):
        path, body_bytes, url = _canonical_request("GET", "/api/v2/mix/market/candles", {
            "symbol": "BTCUSDT", "granularity": "1H", "limit": 1000,
        })
        self.assertEqual(body_bytes, b"")
        self.assertEqual(path, "/api/v2/mix/market/candles?granularity=1H&limit=1000&symbol=BTCUSDT")
        self.assertEqual(url, "https://api.bitget.com/api/v2/mix/market/candles?granularity=1H&limit=1000&symbol=BTCUSDT")

    def test_canonical_post_body_bytes_are_compact_and_deterministic(self):
        path, body_bytes, url = _canonical_request("POST", "/api/v2/mix/market/fills", {
            "symbol": "BTCUSDT", "limit": 50,
        })
        self.assertEqual(path, "/api/v2/mix/market/fills")
        self.assertEqual(body_bytes, b'{"limit":50,"symbol":"BTCUSDT"}')
        self.assertEqual(url, "https://api.bitget.com/api/v2/mix/market/fills")

    def test_canonical_request_rejects_non_object_and_nested_query_values(self):
        with self.assertRaises(ValueError):
            _canonical_request("GET", "/api/v2/test", ["not", "a", "dict"])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            _canonical_request("GET", "/api/v2/test", {"nested": {"a": 1}})
        with self.assertRaises(ValueError):
            _canonical_request("GET", "/api/v2/test", {"null_val": None})

    def test_canonical_request_rejects_embedded_query_and_absolute_path(self):
        with self.assertRaises(ValueError):
            _canonical_request("GET", "/api/v2/test?foo=bar", {})
        with self.assertRaises(ValueError):
            _canonical_request("GET", "https://api.bitget.com/api/v2/test", {})
        with self.assertRaises(ValueError):
            _canonical_request("GET", "not_api_prefix", {})

    def test_canonical_query_encodes_spaces_and_unicode_deterministically(self):
        path, _, _ = _canonical_request("GET", "/api/v2/test", {"symbol": "BTC USDT", "tag": "äöü"})
        self.assertIn("symbol=BTC+USDT", path)
        self.assertIn("tag=%C3%A4%C3%B6%C3%BC", path)


# ===========================================================================
# 2. PUBLIC REST REQUEST HANDLING
# ===========================================================================
class TestPublicRequest(unittest.TestCase):
    def test_403_returns_error_dict(self):
        err = urllib.error.HTTPError("https://api.bitget.com/api/v2/test", 403, "Forbidden", Message(), None)
        err.read = MagicMock(return_value=b'{"code":"40014","msg":"IP not allowed"}')
        with patch("urllib.request.urlopen", side_effect=err):
            r = _request("GET", "/api/v2/test")
            self.assertEqual(r["code"], "403")
            self.assertEqual(r["_http"], 403)
            self.assertIn("40014", r["msg"])

    def test_404_returns_error_dict(self):
        err = urllib.error.HTTPError("https://api.bitget.com/api/v2/bad", 404, "Not Found", Message(), None)
        err.read = MagicMock(return_value=b'{"code":"404","msg":"Not found"}')
        with patch("urllib.request.urlopen", side_effect=err):
            r = _request("GET", "/api/v2/bad")
            self.assertEqual(r["code"], "404")

    def test_malformed_json_from_exchange_returns_err_dict(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=mock_resp):
            r = _request("GET", "/api/v2/test")
            self.assertEqual(r["code"], "ERR")
            self.assertTrue(len(r["msg"]) > 0)

    def test_connection_refused_returns_err_dict(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            r = _request("GET", "/api/v2/test")
            self.assertEqual(r["code"], "ERR")
            self.assertIn("Connection refused", r["msg"])

    def test_empty_json_body_does_not_crash_handler(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=mock_resp):
            r = _request("GET", "/api/v2/test")
            self.assertEqual(r, {})


# ----------------------------------------------------------------------------
# 3. HTTP SERVER INTEGRATION
# ----------------------------------------------------------------------------
class TestRelayMutationContract(unittest.TestCase):
    def test_history_upsert_prepends_and_trims_newest_first(self):
        key = "aura-quant-terminal-history-trades-v1"
        current = {key: [{"id": f"old-{i}"} for i in range(205)]}
        result = bitget_relay._apply_mutations_locked(current, [{"key": key, "op": "upsert", "id": "new", "value": {"id": "new"}}])
        self.assertEqual(len(result[key]), 200)
        self.assertEqual(result[key][0]["id"], "new")
        self.assertEqual(result[key][-1]["id"], "old-198")


class TestDockerDeploymentContract(unittest.TestCase):
    def test_dockerfile_prepares_persistent_state_directory_before_non_root_user(self):
        dockerfile = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text(encoding="utf-8")
        prepare = "RUN mkdir -p /var/lib/aura && chown -R aura:aura /var/lib/aura"
        self.assertIn(prepare, dockerfile)
        self.assertLess(dockerfile.index(prepare), dockerfile.index("USER aura"))

    def test_compose_configures_lan_host_and_persistent_state(self):
        compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("AURA_ALLOWED_HOSTS=${AURA_ALLOWED_HOSTS:-127.0.0.1}", compose)
        self.assertIn("AURA_STATE_DIR=/var/lib/aura", compose)
        self.assertIn("aura-state:/var/lib/aura", compose)

    def test_direct_docker_guide_declares_external_port_state_and_allowlist_contract(self):
        guide = (Path(__file__).resolve().parent.parent / "DOCKER_GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("-p 9090:8787", guide)
        self.assertIn("-e AURA_ALLOWED_HOSTS=<HOST-IP-ODER-DNS>", guide)
        self.assertIn("-e AURA_STATE_DIR=/var/lib/aura", guide)
        self.assertIn("-v aura-state:/var/lib/aura", guide)
        self.assertIn("Ersetze `<HOST-IP-ODER-DNS>`", guide)


        root = Path(__file__).resolve().parent.parent
        starters = [
            "DOCKER_START.bat", "docker_start.sh", "smart_homelab_installer.sh",
            "deep_infrastructure_scanner.sh",
        ]
        for name in starters:
            text = (root / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if "docker run" in line and "aura-quant-terminal:latest" in line:
                    self.assertIn("AURA_STATE_DIR=/var/lib/aura", text, name)
                    self.assertIn("aura-state:/var/lib/aura", text, name)
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("AURA_ALLOWED_HOSTS=", compose)


class TestHTTPServer(unittest.TestCase):
    """Spins up a real HTTPServer in a thread; tests actual HTTP lifecycle."""

    @classmethod
    def setUpClass(cls):
        cls.port = 18788
        cls.server = RelayServer(("127.0.0.1", cls.port), RelayHandler)
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

    def _get(self, path: str) -> tuple[int, dict]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())

    def _get_status(self, path: str, headers: dict | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _post(self, path: str, data: dict, headers: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(data).encode()
        request_headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        request_headers.update(headers or {})
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _post_raw(self, path: str, body: bytes, content_type: str = "application/json") -> tuple[int, dict]:
        headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_default_bind_host_is_loopback(self):
        # When SYM_HOST is not set, default is loopback (safe for local use).
        # In Docker, docker-compose sets SYM_HOST=0.0.0.0 explicitly so Docker
        # can forward the port — the container network boundary provides isolation.
        import os
        if os.environ.get("SYM_HOST"):
            self.skipTest("SYM_HOST overridden by environment (e.g. Docker)")
        self.assertEqual(bitget_relay.HOST, "127.0.0.1")

    def test_get_serving_returns_ok(self):
        status, body = self._get("/serving")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["version"], "1.0.7")
        self.assertEqual(body["mode"], "quant_research")

    def test_get_serving_with_querystring(self):
        status, body = self._get("/serving?foo=bar")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_get_serving_prefix_is_not_accepted(self):
        try:
            self._get("/serving-anything")
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_get_root_serves_dashboard(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as resp:
            body = resp.read().decode()
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            self.assertIn("AURA", body)
            self.assertIn("<script>", body)

    def test_get_tutorial_serves_tutorial(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/tutorial", timeout=5) as resp:
            body = resp.read().decode()
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            self.assertIn("AURA", body)

    def test_state_route_rejects_foreign_origin(self):
        status, body = self._get_status("/api/state", {"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")

    def test_state_route_rejects_null_origin(self):
        status, body = self._get_status("/api/state", {"Origin": "null"})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")

    def test_state_route_rejects_forged_host(self):
        status, body = self._get_status("/api/state", {"Host": "evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_HOST")

    def test_get_state_invalid_json_is_500_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "aura_shared_state.json"
            raw = b'{invalid-json-preserve-me'
            state_file.write_bytes(raw)
            with patch.object(bitget_relay, "STATE_FILE", state_file), patch.object(bitget_relay, "STATE_DIR", Path(tmpdir)):
                status, body = self._get_status("/api/state")
            self.assertEqual(status, 500)
            self.assertEqual(body["code"], "ERR_STATE_PERSIST")
            self.assertEqual(state_file.read_bytes(), raw)

    def test_get_state_json_array_is_500_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "aura_shared_state.json"
            raw = b'[{"not":"an-object"}]'
            state_file.write_bytes(raw)
            with patch.object(bitget_relay, "STATE_FILE", state_file), patch.object(bitget_relay, "STATE_DIR", Path(tmpdir)):
                status, body = self._get_status("/api/state")
            self.assertEqual(status, 500)
            self.assertEqual(body["code"], "ERR_STATE_PERSIST")
            self.assertEqual(state_file.read_bytes(), raw)

    def test_get_state_missing_file_is_empty_initial_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "missing.json"
            with patch.object(bitget_relay, "STATE_FILE", state_file), patch.object(bitget_relay, "STATE_DIR", Path(tmpdir)):
                status, body = self._get_status("/api/state")
            self.assertEqual(status, 200)
            self.assertEqual(body, {"ok": True, "data": {}})

    def test_legacy_write_on_corrupt_state_is_500_and_preserves_bytes(self):
        original_file = bitget_relay.STATE_FILE
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "aura_shared_state.json"
            raw = b'{not-json-preserve-me'
            state_file.write_bytes(raw)
            with patch.object(bitget_relay, "STATE_FILE", state_file), patch.object(bitget_relay, "STATE_DIR", Path(tmpdir)):
                status, body = self._post("/api/state", {
                    "key": "aura-autobot-state-v2",
                    "value": {"enabled": True},
                    "expected_rev": 0,
                })
            self.assertEqual(status, 500)
            self.assertEqual(body["code"], "ERR_STATE_PERSIST")
            self.assertEqual(state_file.read_bytes(), raw)
        self.assertIsNotNone(original_file)
    def test_state_mutation_persistence_failure_is_500_not_conflict(self):
        _, current = self._get_status("/api/state")
        with patch("bitget_relay._save_mutation_batch", return_value=(None, current["data"].get("_rev", 0), bitget_relay.PersistenceError())):
            status, body = self._post("/api/state", {
                "expected_rev": current["data"].get("_rev", 0),
                "mutations": [{"key": "aura-quant-terminal-active-trades-v1", "op": "upsert", "id": "persist-fail", "value": {"id": "persist-fail"}}],
            })
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], "ERR_STATE_PERSIST")


    def test_legacy_persistence_failure_is_500_not_conflict(self):
        _, current = self._get_status("/api/state")
        with patch("bitget_relay._save_shared_state", return_value=(None, current["data"].get("_rev", 0), bitget_relay.PersistenceError())):
            status, body = self._post("/api/state", {
                "expected_rev": current["data"].get("_rev", 0),
                "key": "aura-autobot-state-v2",
                "value": {"enabled": True},
            })
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], "ERR_STATE_PERSIST")

    def test_state_mutation_stale_revision_remains_409_conflict(self):
        _, current = self._get_status("/api/state")
        base = current["data"].get("_rev", 0)
        status, first = self._post("/api/state", {"key": "aura-autobot-state-v2", "value": {"marker": "conflict"}, "expected_rev": base})
        self.assertEqual(status, 200)
        status, body = self._post("/api/state", {
            "expected_rev": base,
            "mutations": [{"key": "aura-quant-terminal-active-trades-v1", "op": "upsert", "id": "stale", "value": {"id": "stale"}}],
        })
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], "ERR_STATE_CONFLICT")

    def test_state_write_increments_revision_and_stale_revision_cannot_overwrite(self):
        _, current = self._get_status("/api/state")
        base_rev = current["data"].get("_rev", 0)
        first_status, first = self._post("/api/state", {"key": "aura-autobot-state-v2", "value": {"enabled": True}, "expected_rev": base_rev})
        self.assertEqual(first_status, 200)
        self.assertEqual(first["rev"], first["state"]["_rev"])
        second_status, second = self._post("/api/state", {"key": "aura-autobot-state-v2", "value": {"enabled": False}, "expected_rev": 0})
        self.assertEqual(second_status, 409)
        self.assertEqual(second["code"], "ERR_STATE_CONFLICT")
        self.assertEqual(second["rev"], first["rev"])
        self.assertEqual(second["state"]["aura-autobot-state-v2"], {"enabled": True})

    def test_state_write_accepts_current_revision(self):
        _, current = self._get_status("/api/state")
        base_rev = current["data"].get("_rev", 0)
        _, first = self._post("/api/state", {"key": "aura-autobot-state-v2", "value": {"enabled": True}, "expected_rev": base_rev})
        status, body = self._post("/api/state", {"key": "aura-autobot-state-v2", "value": {"enabled": False}, "expected_rev": first["rev"]})
        self.assertEqual(status, 200)
        self.assertEqual(body["rev"], first["rev"] + 1)
        self.assertEqual(body["state"]["aura-autobot-state-v2"], {"enabled": False})

    def test_state_route_allows_external_docker_port_same_origin(self):
        origin = "http://127.0.0.1:18787"
        with patch.object(RelayHandler, "_ALLOWED_HOSTS", {"localhost", "127.0.0.1"}):
            status, body = self._get_status("/api/state", {"Host": "127.0.0.1:18787", "Origin": origin})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_state_route_rejects_external_port_origin_mismatch(self):
        with patch.object(RelayHandler, "_ALLOWED_HOSTS", {"localhost", "127.0.0.1"}):
            status, body = self._get_status("/api/state", {
                "Host": "127.0.0.1:18787", "Origin": "http://127.0.0.1:9999"
            })
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")

    def test_state_route_allows_exact_same_origin(self):
        origin = f"http://127.0.0.1:{self.port}"
        status, body = self._get_status("/api/state", {"Origin": origin})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_state_route_allows_https_same_origin_for_allowlisted_proxy_host(self):
        origin = "https://aura.example"
        with patch.object(RelayHandler, "_ALLOWED_HOSTS", {"localhost", "127.0.0.1", "aura.example"}):
            status, body = self._get_status("/api/state", {"Host": "aura.example", "Origin": origin})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_state_route_rejects_same_host_with_port_mismatch(self):
        with patch.object(RelayHandler, "_ALLOWED_HOSTS", {"localhost", "127.0.0.1", "aura.example"}):
            status, body = self._get_status("/api/state", {"Host": "aura.example:8787", "Origin": "https://aura.example"})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")

    def test_state_mutation_batch_is_atomic_and_single_revision(self):
        _, current = self._get_status("/api/state")
        base = current["data"].get("_rev", 0)
        status, body = self._post("/api/state", {
            "expected_rev": base,
            "mutations": [
                {"key": "aura-quant-terminal-active-trades-v1", "op": "upsert", "id": "atomic-active", "value": {"id": "atomic-active", "coin": "BTCUSDT"}},
                {"key": "aura-quant-terminal-history-trades-v1", "op": "upsert", "id": "atomic-history", "value": {"id": "atomic-history", "tradeId": "atomic-active"}},
            ],
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["rev"], base + 1)
        self.assertEqual(body["state"]["_rev"], base + 1)

    def test_invalid_state_mutation_batch_has_no_partial_effect(self):
        _, current = self._get_status("/api/state")
        base = current["data"].get("_rev", 0)
        status, body = self._post("/api/state", {
            "expected_rev": base,
            "mutations": [
                {"key": "aura-quant-terminal-active-trades-v1", "op": "upsert", "id": "must-not-appear", "value": {"id": "must-not-appear"}},
                {"key": "not-allowed", "op": "delete", "id": "bad"},
            ],
        })
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "ERR_INVALID_MUTATIONS")
        _, after = self._get_status("/api/state")
        self.assertEqual(after["data"].get("_rev", 0), base)
        ids = {item.get("id") for item in after["data"].get("aura-quant-terminal-active-trades-v1", [])}
        self.assertNotIn("must-not-appear", ids)

    def test_delete_mutation_preserves_other_trade_ids(self):
        _, current = self._get_status("/api/state")
        base = current["data"].get("_rev", 0)
        status, body = self._post("/api/state", {
            "expected_rev": base,
            "mutations": [
                {"key": "aura-quant-terminal-active-trades-v1", "op": "upsert", "id": "keep-id", "value": {"id": "keep-id"}},
                {"key": "aura-quant-terminal-active-trades-v1", "op": "upsert", "id": "delete-id", "value": {"id": "delete-id"}},
            ],
        })
        self.assertEqual(status, 200)
        status, body = self._post("/api/state", {
            "expected_rev": body["rev"],
            "mutations": [{"key": "aura-quant-terminal-active-trades-v1", "op": "delete", "id": "delete-id"}],
        })
        self.assertEqual(status, 200)
        ids = {item.get("id") for item in body["state"]["aura-quant-terminal-active-trades-v1"]}
        self.assertIn("keep-id", ids)
        self.assertNotIn("delete-id", ids)

    def test_state_route_allows_configured_lan_host_and_origin(self):
        origin = f"http://192.168.8.115:{self.port}"
        with patch.object(RelayHandler, "_ALLOWED_HOSTS", {"localhost", "127.0.0.1", "192.168.8.115"}):
            status, body = self._get_status("/api/state", {"Host": f"192.168.8.115:{self.port}", "Origin": origin})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_state_route_rejects_unconfigured_lan_host(self):
        origin = f"http://192.168.8.116:{self.port}"
        with patch.object(RelayHandler, "_ALLOWED_HOSTS", {"localhost", "127.0.0.1", "192.168.8.115"}):
            status, body = self._get_status("/api/state", {"Host": f"192.168.8.116:{self.port}", "Origin": origin})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_HOST")

    def test_state_route_rejects_malformed_origin(self):
        status, body = self._get_status("/api/state", {"Origin": "http://localhost:evil"})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")

    def test_state_route_rejects_origin_with_wrong_port(self):
        status, body = self._get_status("/api/state", {"Origin": "http://127.0.0.1:9999"})
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")

    def test_state_preflight_rejects_foreign_origin_without_cors_headers(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/state",
            headers={"Origin": "https://evil.example"},
            method="OPTIONS",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)
        self.assertIsNone(ctx.exception.headers.get("Access-Control-Allow-Origin"))

    def test_state_preflight_allows_exact_same_origin(self):
        origin = f"http://127.0.0.1:{self.port}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/state",
            headers={"Origin": origin},
            method="OPTIONS",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), origin)

    def test_state_post_rejects_foreign_origin_before_persistence(self):
        with patch("bitget_relay._save_shared_state") as save:
            status, body = self._post("/api/state", {"key": "autobot", "value": {}}, {
                "Origin": "https://evil.example",
            })
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "ERR_FORBIDDEN_ORIGIN")
        save.assert_not_called()

    def test_state_post_rejects_unknown_and_reserved_keys_before_persistence(self):
        for key in ("unknown", "_rev", "_updated_at"):
            with self.subTest(key=key), patch("bitget_relay._save_shared_state") as save:
                status, body = self._post("/api/state", {"key": key, "value": {}})
            self.assertEqual(status, 400)
            self.assertEqual(body["code"], "ERR_INVALID_KEY")
            save.assert_not_called()

    def test_state_post_rejects_oversized_value_before_persistence(self):
        with patch("bitget_relay._save_shared_state") as save:
            status, body = self._post("/api/state", {
                "key": "aura-autobot-state-v2",
                "value": {"blob": "x" * 1_000_001},
            })
        self.assertEqual(status, 413)
        self.assertEqual(body["code"], "ERR_STATE_TOO_LARGE")
        save.assert_not_called()

    def test_get_unknown_path_returns_404(self):
        try:
            self._get("/some/unknown/path")
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_cors_headers_present_on_get(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/serving")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_options_preflight_returns_204(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/public",
            headers={"Origin": "http://localhost:3000"},
            method="OPTIONS",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_public_passthrough_accepts_dashboard_path_shape(self):
        captured = {}

        def fake(method, path, params=None, **kw):
            captured["method"] = method
            captured["path"] = path
            captured["params"] = params
            return {"code": "00000", "data": []}

        with patch("bitget_relay._request", side_effect=fake):
            status, body = self._post("/api/public", {
                "method": "GET",
                "path": "/api/v2/mix/market/candles?symbol=BTCUSDT&granularity=1H&limit=1000",
            })
        self.assertEqual(status, 200)
        self.assertEqual(body["code"], "00000")
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["path"], "/api/v2/mix/market/candles")
        self.assertEqual(captured["params"], {"symbol": "BTCUSDT", "granularity": "1H", "limit": "1000"})

    def test_post_public_bad_url_returns_400(self):
        status, body = self._post_raw("/api/public", b'{"path":"http://evil.com/api"}')
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "ERR_BAD_URL")

    def test_post_public_rejects_non_api_relative_path(self):
        status, body = self._post_raw("/api/public", b'{"path":"/not-an-api-path"}')
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "ERR_BAD_URL")

    def test_post_unknown_route_returns_404_body(self):
        status, body = self._post_raw("/api/nonexistent", b"{}")
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "ERR_NOT_FOUND")

    def test_post_malformed_json_body_returns_400(self):
        status, body = self._post_raw("/api/public", b"not-valid-json")
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "ERR_BAD_JSON")

    def test_post_requires_json_content_type(self):
        status, body = self._post_raw("/api/public", b'{"path":"/api/v2/test"}', content_type="text/plain")
        self.assertEqual(status, 415)
        self.assertEqual(body["code"], "ERR_CONTENT_TYPE")


# ===========================================================================
# 4. CLIENT DISCONNECT TOLERANCE
# ===========================================================================
class TestWriteBodyTolerance(unittest.TestCase):
    def test_write_body_tolerates_broken_pipe(self):
        handler = object.__new__(RelayHandler)
        broken_wfile = MagicMock()
        broken_wfile.write.side_effect = BrokenPipeError(32, "Broken pipe")
        handler.wfile = broken_wfile
        try:
            handler._write_body(b"payload")
        except BrokenPipeError:
            self.fail("_write_body must swallow BrokenPipeError without raising")


if __name__ == "__main__":
    unittest.main()
