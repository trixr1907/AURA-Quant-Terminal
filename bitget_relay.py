"""
bitget_relay.py — AURA v1.0.4 local CORS proxy, web server & state sync
======================================================================
Startet einen lokalen HTTP-Server auf Port 8787.
Fungiert als Webserver für das Dashboard, als transparenter CORS-Proxy
für öffentliche Bitget-Marktdaten (/api/public) sowie als zentraler
State-Sync-Speicher (/api/state) für alle verbundenen Clients (PC, Smartphone, Tablet).

API-Vertrag (für das Dashboard):
  GET  /                 -> Symbiose_Dashboard.html
  GET  /tutorial         -> SYMBIOSE_Tutorial.html
  GET  /serving          -> {"ok": true, "version": "1.0.5", "port": 8787, "mode": "quant_research"}
  GET  /api/state        -> Liefert alle synchronisierten Zustände (Autobot, Trades, Historie)
  POST /api/state        -> Speichert & synchronisiert Zustand zentral auf dem Server
  POST /api/public       -> Bitget public REST (transparent, kein Auth)
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
#  Configuration & Central Shared State
# ---------------------------------------------------------------------------
HOST = os.environ.get("SYM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SYM_PORT", 8787))
BITGET_BASE = "https://api.bitget.com"


def _parse_allowed_hosts(raw: str) -> set[str]:
    """Return loopback plus explicitly configured host names or IP addresses."""
    hosts = {"localhost", "127.0.0.1"}
    for value in raw.split(","):
        candidate = value.strip().lower().rstrip(".")
        if not candidate:
            continue
        try:
            parsed = urllib.parse.urlsplit(f"//{candidate}")
            if (
                parsed.hostname == candidate
                and parsed.port is None
                and parsed.username is None
                and parsed.password is None
            ):
                hosts.add(candidate)
        except (TypeError, ValueError):
            continue
    return hosts


ALLOWED_HOSTS = _parse_allowed_hosts(os.environ.get("AURA_ALLOWED_HOSTS", ""))

STATE_DIR = Path(os.environ.get("AURA_STATE_DIR", Path(__file__).resolve().parent / "data"))
STATE_FILE = STATE_DIR / "aura_shared_state.json"
STATE_LOCK = threading.Lock()
ALLOWED_STATE_KEYS = {
    "aura-autobot-state-v2",
    "aura-quant-terminal-active-trades-v1",
    "aura-quant-terminal-history-trades-v1",
}
MAX_STATE_VALUE_BYTES = 1_000_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("relay")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _load_shared_state() -> dict:
    """Read shared persistent state across all connected devices."""
    with STATE_LOCK:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("Could not parse %s: %s", STATE_FILE, e)
        return {}


def _save_shared_state(key: str, val: Any) -> dict:
    """Save a key/value pair atomically to the shared server state file."""
    with STATE_LOCK:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            current = {}
            if STATE_FILE.exists():
                try:
                    current = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    current = {}
            current[key] = val
            current["_updated_at"] = int(time.time())
            current["_rev"] = int(current.get("_rev", 0)) + 1
            # Write via temporary file for atomic write safety
            tmp_path = STATE_FILE.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
            tmp_path.replace(STATE_FILE)
            return current
        except Exception as e:
            log.error("Failed to persist shared state: %s", e)
            return {}


# ---------------------------------------------------------------------------
#  Bitget Public REST helpers
# ---------------------------------------------------------------------------

def _canonical_request(method: str, path: str, body: dict | None = None) -> tuple[str, bytes, str]:
    """Return the exact query path, transmitted body bytes, and URL."""
    method = method.upper()
    if not isinstance(path, str) or not path.startswith("/api/") or "?" in path or "://" in path:
        raise ValueError("Request path must be a query-free relative /api/ path")
    if body is not None and not isinstance(body, dict):
        raise ValueError("Request body must be an object")
    params = body or {}
    if method == "GET":
        scalar_types = (str, int, float, bool)
        if any(value is None or not isinstance(value, scalar_types) for value in params.values()):
            raise ValueError("GET query values must be non-null scalars")
        query = urllib.parse.urlencode(sorted(params.items())) if params else ""
        request_path = path + ("?" + query if query else "")
        body_bytes = b""
    else:
        request_path = path
        body_bytes = json.dumps(params, sort_keys=True, separators=(",", ":")).encode() if params else b""
    return request_path, body_bytes, BITGET_BASE + request_path


def _request(method: str, path: str, body: dict | None = None, public: bool = True) -> dict:
    """Send a public request to Bitget."""
    method = method.upper()
    request_path, body_bytes, url = _canonical_request(method, path, body)
    req = urllib.request.Request(
        url,
        data=body_bytes or None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode(errors="replace")
        log.error("HTTP %s %s: %s", e.code, path, body_err)
        return {"code": str(e.code), "msg": body_err, "data": None, "_http": e.code}
    except Exception as exc:
        log.error("Request error %s: %s", path, exc)
        return {"code": "ERR", "msg": str(exc), "data": None}


# ---------------------------------------------------------------------------
#  HTTP Request Handler
# ---------------------------------------------------------------------------

class RelayHandler(BaseHTTPRequestHandler):
    _PRIVILEGED_PATHS = {"/api/state"}
    _ALLOWED_HOSTS = ALLOWED_HOSTS

    def log_message(self, format, *args):  # suppress default server log  # noqa: A002
        log.debug(format, *args)

    def _request_path(self) -> str:
        return self.path.split("?", 1)[0]

    def _privileged_cors_headers(self) -> dict[str, str]:
        origin = self.headers.get("Origin")
        if not origin:
            return {}
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Vary": "Origin",
        }

    def _authorize_privileged(self) -> bool:
        try:
            server_port = int(getattr(self.server, "server_port"))
            host = urllib.parse.urlsplit(f"//{self.headers.get('Host', '')}")
            if (
                host.hostname not in self._ALLOWED_HOSTS
                or host.port != server_port
                or host.username is not None
                or host.password is not None
            ):
                raise ValueError("forbidden host")
        except (TypeError, ValueError):
            self._send_json({"code": "ERR_FORBIDDEN_HOST"}, 403, cors_headers={})
            return False

        origin_value = self.headers.get("Origin")
        if origin_value is None:
            return True
        try:
            origin = urllib.parse.urlsplit(origin_value)
            valid_origin = (
                origin.scheme == "http"
                and origin.hostname == host.hostname
                and origin.port == server_port
                and origin.username is None
                and origin.password is None
                and origin.path == ""
                and origin.query == ""
                and origin.fragment == ""
            )
        except (TypeError, ValueError):
            valid_origin = False
        if not valid_origin:
            self._send_json({"code": "ERR_FORBIDDEN_ORIGIN"}, 403, cors_headers={})
            return False
        return True

    def _send_json(self, data: dict, status: int = 200, cors_headers: dict[str, str] | None = None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        headers = CORS_HEADERS if cors_headers is None else cors_headers
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self._write_body(body)

    def _write_body(self, body: bytes) -> None:
        """Write the response body, tolerating client disconnects."""
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            log.debug("client disconnected before response completed")

    def _send_html(self, body: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self._write_body(body)

    def _read_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            return None
        if length < 0 or length > 5_000_000:
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def do_OPTIONS(self):
        path = self._request_path()
        if path in self._PRIVILEGED_PATHS:
            if not self._authorize_privileged():
                return
            cors_headers = self._privileged_cors_headers()
        else:
            cors_headers = CORS_HEADERS
        self.send_response(204)
        for k, v in cors_headers.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        path = self._request_path()
        if path == "/":
            dashboard = Path(__file__).resolve().with_name("Symbiose_Dashboard.html")
            try:
                self._send_html(dashboard.read_bytes())
            except OSError:
                self._send_json({"code": "ERR_DASHBOARD_NOT_FOUND"}, 404)
        elif path == "/tutorial":
            tutorial = Path(__file__).resolve().with_name("SYMBIOSE_Tutorial.html")
            try:
                self._send_html(tutorial.read_bytes())
            except OSError:
                self._send_json({"code": "ERR_TUTORIAL_NOT_FOUND"}, 404)
        elif path == "/serving":
            self._send_json({
                "ok": True,
                "version": "1.0.5",
                "port": PORT,
                "mode": "quant_research",
            })
        elif path == "/api/state":
            if not self._authorize_privileged():
                return
            # Return shared server state for cross-device synchronization
            self._send_json({
                "ok": True,
                "data": _load_shared_state(),
            }, cors_headers=self._privileged_cors_headers())
        else:
            self._send_json({"code": "ERR_NOT_FOUND"}, 404)

    def do_POST(self):
        path = self._request_path()
        if path in self._PRIVILEGED_PATHS and not self._authorize_privileged():
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if path.startswith("/api/") and content_type != "application/json":
            self._send_json({"code": "ERR_CONTENT_TYPE", "msg": "Content-Type must be application/json"}, 415)
            return
        payload = self._read_body()
        if payload is None:
            self._send_json({"code": "ERR_BAD_JSON", "msg": "Request body must be a JSON object"}, 400)
            return

        if path == "/api/state":
            # Central state persistence & synchronization endpoint
            key = str(payload.get("key", "")).strip()
            val = payload.get("value")
            if not key:
                self._send_json({"code": "ERR_INVALID_KEY", "msg": "key is required"}, 400)
                return
            if key.startswith("_") or key not in ALLOWED_STATE_KEYS:
                self._send_json({"code": "ERR_INVALID_KEY", "msg": "unknown or reserved key"}, 400)
                return
            try:
                serialized_size = len(json.dumps(val).encode())
            except (TypeError, ValueError):
                serialized_size = 0
            if serialized_size > MAX_STATE_VALUE_BYTES:
                self._send_json({"code": "ERR_STATE_TOO_LARGE",
                                 "msg": f"value exceeds {MAX_STATE_VALUE_BYTES} bytes"}, 413)
                return
            saved = _save_shared_state(key, val)
            self._send_json(
                {"ok": True, "key": key, "state": saved},
                cors_headers=self._privileged_cors_headers(),
            )
            return

        if path == "/api/public":
            # Public Bitget REST passthrough (no auth).
            raw = payload.get("path") or payload.get("url", "")
            if (
                not isinstance(raw, str)
                or not raw.startswith("/api/")
                or "://" in raw
            ):
                self._send_json({"code": "ERR_BAD_URL", "msg": "Public path must be a relative /api/ path"}, 400)
                return
            base, _, qs = raw.partition("?")
            params = payload.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            merged = dict(params)
            for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True):
                merged.setdefault(k, v)
            method = str(payload.get("method", "GET")).upper()
            r = _request(method, base, merged, public=True)
            self._send_json(r)
        else:
            self._send_json({"code": "ERR_NOT_FOUND"}, 404)


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

class RelayServer(ThreadingHTTPServer):
    """Threaded HTTP server with a larger accept backlog for concurrent clients."""
    request_queue_size = 128


if __name__ == "__main__":
    server = RelayServer((HOST, PORT), RelayHandler)
    log.info("AURA Relay v1.0.5 listening on http://%s:%d", HOST, PORT)
    log.info("Modus: Quant Research & Signal Analysis (Read-Only CORS Proxy + Cross-Device Sync)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Relay gestoppt.")
