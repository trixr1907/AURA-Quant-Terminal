"""
bitget_relay.py — AURA v1.1.0 local CORS proxy, web server & state sync
======================================================================
Startet einen lokalen HTTP-Server auf Port 8787.
Fungiert als Webserver für das Dashboard, als transparenter CORS-Proxy
für öffentliche Bitget-Marktdaten (/api/public) sowie als zentraler
State-Sync-Speicher (/api/state) für alle verbundenen Clients (PC, Smartphone, Tablet).

API-Vertrag (für das Dashboard):
  GET  /                 -> Symbiose_Dashboard.html
  GET  /tutorial         -> SYMBIOSE_Tutorial.html
  GET  /serving          -> {"ok": true, "version": "1.1.0", "port": 8787, "mode": "quant_research"}
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
VERSION = "1.1.0"
BITGET_BASE = "https://api.bitget.com"


class PersistenceError(Exception):
    """Internal marker for state storage failures (never exposed to clients)."""


class StatePersistenceError(PersistenceError):
    """Existing state is unreadable or not a JSON object."""


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
MAX_STATE_VALUE_BYTES = 1_000_000
STATE_LOCK = threading.Lock()
ALLOWED_STATE_KEYS = {
    "aura-autobot-state-v2",
    "aura-quant-terminal-active-trades-v1",
    "aura-quant-terminal-history-trades-v1",
}

def _validate_mutations(mutations: Any) -> list[dict] | None:
    """Validate an ID-based batch completely before applying any mutation."""
    if not isinstance(mutations, list) or not mutations or len(mutations) > 1000:
        return None
    validated: list[dict] = []
    for mutation in mutations:
        if not isinstance(mutation, dict):
            return None
        key = mutation.get("key")
        op = mutation.get("op")
        ident = mutation.get("id")
        if key not in {"aura-quant-terminal-active-trades-v1", "aura-quant-terminal-history-trades-v1"}:
            return None
        if op not in {"upsert", "delete"} or not isinstance(ident, str) or not ident or len(ident) > 256:
            return None
        if op == "upsert":
            value = mutation.get("value")
            if not isinstance(value, dict) or value.get("id") != ident:
                return None
            try:
                if len(json.dumps(value, separators=(",", ":")).encode()) > MAX_STATE_VALUE_BYTES:
                    return None
            except (TypeError, ValueError):
                return None
            validated.append({"key": key, "op": op, "id": ident, "value": value})
        else:
            validated.append({"key": key, "op": op, "id": ident})
    return validated


def _apply_mutations_locked(current: dict, mutations: list[dict]) -> dict:
    """Apply a previously validated batch to a copied state while STATE_LOCK is held."""
    next_state = dict(current)
    arrays: dict[str, list] = {}
    for key in {item["key"] for item in mutations}:
        existing = current.get(key, [])
        arrays[key] = list(existing) if isinstance(existing, list) else []
    for mutation in mutations:
        values = arrays[mutation["key"]]
        ident = mutation["id"]
        index = next((i for i, item in enumerate(values) if isinstance(item, dict) and item.get("id") == ident), None)
        if mutation["op"] == "delete":
            if index is not None:
                values.pop(index)
        elif index is None:
            if mutation["key"] == "aura-quant-terminal-history-trades-v1":
                values.insert(0, mutation["value"])
            else:
                values.append(mutation["value"])
        else:
            values[index] = mutation["value"]
    for key, values in arrays.items():
        limit = 200 if key == "aura-quant-terminal-history-trades-v1" else 500
        next_state[key] = values[:limit]
    return next_state


def _save_mutation_batch(mutations: list[dict], expected_rev: int | None = None) -> tuple[dict | None, int, PersistenceError | None]:
    """Atomically validate, apply, and persist an ID mutation batch."""
    with STATE_LOCK:
        current: dict = {}
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            if STATE_FILE.exists():
                loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("shared state must be a JSON object")
                current = loaded
            current_rev = int(current.get("_rev", 0))
            if expected_rev is not None and expected_rev != current_rev:
                return None, current_rev, None
            next_state = _apply_mutations_locked(current, mutations)
            next_state["_updated_at"] = int(time.time())
            next_state["_rev"] = current_rev + 1
            tmp_path = STATE_FILE.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(next_state, indent=2), encoding="utf-8")
            tmp_path.replace(STATE_FILE)
            return next_state, next_state["_rev"], None
        except Exception as exc:
            log.error("Failed to persist mutation batch: %s", exc)
            return None, int(current.get("_rev", 0)) if isinstance(current, dict) else 0, PersistenceError()

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
    """Read shared persistent state; missing file is empty, corruption is fatal."""
    with STATE_LOCK:
        if not STATE_FILE.exists():
            return {}
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.error("Could not parse existing state file: %s", exc)
            raise StatePersistenceError() from exc
        if not isinstance(state, dict):
            log.error("Existing state file is not a JSON object")
            raise StatePersistenceError()
        return state


def _save_shared_state(key: str, val: Any, expected_rev: int | None = None) -> tuple[dict | None, int, PersistenceError | None]:
    """Atomically save one key, rejecting stale revisions before mutation."""
    with STATE_LOCK:
        current: dict = {}
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            current = {}
            if STATE_FILE.exists():
                try:
                    loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                    if not isinstance(loaded, dict):
                        raise ValueError("shared state must be a JSON object")
                    current = loaded
                except Exception:
                    raise PersistenceError("shared state is corrupt")
            current_rev = int(current.get("_rev", 0))
            if expected_rev is not None and expected_rev != current_rev:
                return None, current_rev, None
            current[key] = val
            current["_updated_at"] = int(time.time())
            current["_rev"] = current_rev + 1
            tmp_path = STATE_FILE.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
            tmp_path.replace(STATE_FILE)
            return current, current["_rev"], None
        except Exception as e:
            log.error("Failed to persist shared state: %s", e)
            return None, int(current.get("_rev", 0)) if isinstance(current, dict) else 0, PersistenceError()


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


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter for external API uplink."""

    def __init__(self, rate: float = 10.0, capacity: float = 20.0):
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last_fill = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_fill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_fill = now
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    def reset(self):
        with self.lock:
            self.tokens = self.capacity
            self.last_fill = time.monotonic()


class TTLCache:
    """Thread-safe in-memory cache with TTL policies by endpoint type."""

    def __init__(self):
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def get_ttl_for_path(self, path: str) -> float:
        p = str(path).lower()
        if "candle" in p or "kline" in p:
            return 60.0
        if "ticker" in p:
            return 5.0
        if "contract" in p or "funding" in p or "open-interest" in p or "orderbook" in p or "depth" in p:
            return 10.0
        return 5.0

    def get(self, key: tuple) -> dict | None:
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expire_at, value = entry
            if now < expire_at:
                return value
            del self._cache[key]
            return None

    def set(self, key: tuple, value: dict, ttl: float) -> None:
        if ttl <= 0:
            return
        now = time.monotonic()
        expire_at = now + ttl
        with self._lock:
            self._cache[key] = (expire_at, value)
            if len(self._cache) > 2000:
                expired = [k for k, (exp, _) in self._cache.items() if now >= exp]
                for k in expired:
                    del self._cache[k]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


UPLINK_RATE_LIMITER = TokenBucketRateLimiter(rate=10.0, capacity=20.0)
PUBLIC_CACHE = TTLCache()


def _public_request_cached(method: str, path: str, params: dict) -> tuple[dict, bool]:
    """Execute a public Bitget request with TTL caching and token bucket rate limiting."""
    method_upper = method.upper()
    cache_key = (
        method_upper,
        path,
        tuple(sorted((str(k), str(v)) for k, v in params.items()))
    )

    if method_upper == "GET":
        cached = PUBLIC_CACHE.get(cache_key)
        if cached is not None:
            return cached, True

    if not UPLINK_RATE_LIMITER.consume():
        return {
            "code": "429",
            "msg": "Relay rate limit exceeded (Token Bucket: 10 req/s, burst 20). Retry shortly.",
            "data": None,
            "_http": 429,
        }, False

    resp = _request(method_upper, path, params, public=True)
    if method_upper == "GET" and isinstance(resp, dict) and resp.get("code") == "00000":
        ttl = PUBLIC_CACHE.get_ttl_for_path(path)
        PUBLIC_CACHE.set(cache_key, resp, ttl)

    return resp, False


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
            host = urllib.parse.urlsplit(f"//{self.headers.get('Host', '')}")
            if (
                host.hostname not in self._ALLOWED_HOSTS
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
            host_port = host.port
            origin_port = origin.port
            # Host and Origin must describe exactly the same authority.  The
            # listener port is deliberately not consulted: Docker/NAT may
            # expose the internal listener on a different external port.
            same_authority = (
                origin.hostname == host.hostname
                and origin.username is None
                and origin.password is None
                and (
                    (host_port is not None and origin_port == host_port)
                    or (host_port is None and origin_port is None)
                )
            )
            valid_origin = (
                origin.scheme in {"http", "https"}
                and same_authority
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

    def _send_json(self, data: dict, status: int = 200, cors_headers: dict[str, str] | None = None, extra_headers: dict[str, str] | None = None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 429:
            self.send_header("Retry-After", "1")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
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
                "version": VERSION,
                "port": PORT,
                "mode": "quant_research",
            })
        elif path == "/api/state":
            if not self._authorize_privileged():
                return
            # Return shared server state for cross-device synchronization.
            try:
                state = _load_shared_state()
            except StatePersistenceError:
                self._send_json({"code": "ERR_STATE_PERSIST", "msg": "state could not be read"}, 500, cors_headers=self._privileged_cors_headers())
                return
            self._send_json({
                "ok": True,
                "data": state,
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
            expected_raw = payload.get("expected_rev")
            if expected_raw is not None and (isinstance(expected_raw, bool) or not isinstance(expected_raw, int) or expected_raw < 0):
                self._send_json({"code": "ERR_INVALID_REV", "msg": "expected_rev must be a non-negative integer"}, 400)
                return
            if "mutations" in payload:
                mutations = _validate_mutations(payload.get("mutations"))
                if mutations is None:
                    self._send_json({"code": "ERR_INVALID_MUTATIONS", "msg": "invalid ID mutation batch"}, 400)
                    return
                saved, rev, persist_error = _save_mutation_batch(mutations, expected_raw)
                if persist_error is not None:
                    self._send_json({"code": "ERR_STATE_PERSIST", "msg": "state could not be persisted"}, 500, cors_headers=self._privileged_cors_headers())
                    return
                if saved is None:
                    self._send_json({
                        "code": "ERR_STATE_CONFLICT",
                        "msg": "state revision is stale; pull current state before retrying",
                        "rev": rev,
                        "state": _load_shared_state(),
                    }, 409, cors_headers=self._privileged_cors_headers())
                    return
                self._send_json({"ok": True, "mutations": len(mutations), "rev": rev, "state": saved}, cors_headers=self._privileged_cors_headers())
                return

            # Legacy single-key writes remain supported for autobot/bootstrap only.
            key = str(payload.get("key", "")).strip()
            val = payload.get("value")
            if not key or key.startswith("_") or key not in ALLOWED_STATE_KEYS:
                self._send_json({"code": "ERR_INVALID_KEY", "msg": "unknown or reserved key"}, 400)
                return
            try:
                serialized_size = len(json.dumps(val).encode())
            except (TypeError, ValueError):
                serialized_size = 0
            if serialized_size > MAX_STATE_VALUE_BYTES:
                self._send_json({"code": "ERR_STATE_TOO_LARGE", "msg": f"value exceeds {MAX_STATE_VALUE_BYTES} bytes"}, 413)
                return
            saved, rev, persist_error = _save_shared_state(key, val, expected_raw)
            if persist_error is not None:
                self._send_json({"code": "ERR_STATE_PERSIST", "msg": "state could not be persisted"}, 500, cors_headers=self._privileged_cors_headers())
                return
            if saved is None:
                self._send_json({"code": "ERR_STATE_CONFLICT", "msg": "state revision is stale; pull current state before retrying", "rev": rev, "state": _load_shared_state()}, 409, cors_headers=self._privileged_cors_headers())
                return
            self._send_json({"ok": True, "key": key, "rev": rev, "state": saved}, cors_headers=self._privileged_cors_headers())
            return

        if path == "/api/public":
            # Public Bitget REST passthrough with TTL caching & Token-Bucket rate limiting.
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
            r, is_cached = _public_request_cached(method, base, merged)
            status = 200
            if isinstance(r, dict) and r.get("code") == "429":
                status = 429
            self._send_json(r, status=status)
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
    log.info("AURA Relay v1.1.0 listening on http://%s:%d", HOST, PORT)
    log.info("Modus: Quant Research & Signal Analysis (Read-Only CORS Proxy + Cross-Device Sync)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Relay gestoppt.")
