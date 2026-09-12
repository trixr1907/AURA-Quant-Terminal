"""
bitget_relay.py — AURA v1.2.7 local CORS proxy, web server & state sync
======================================================================
Startet einen lokalen HTTP-Server auf Port 8787.
Fungiert als Webserver für das Dashboard, als transparenter CORS-Proxy
für öffentliche Bitget-Marktdaten (/api/public) sowie als zentraler
State-Sync-Speicher (/api/state) für alle verbundenen Clients (PC, Smartphone, Tablet).

API-Vertrag (für das Dashboard):
  GET  /                 -> Symbiose_Dashboard.html
  GET  /tutorial         -> SYMBIOSE_Tutorial.html
  GET  /serving          -> {"ok": true, "version": "1.2.7", "port": 8787, "mode": "quant_research"}
  GET  /api/state        -> Liefert alle synchronisierten Zustände (Autobot, Trades, Historie)
  POST /api/state        -> Speichert & synchronisiert Zustand zentral auf dem Server
  POST /api/public       -> Bitget public REST (transparent, kein Auth)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
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
_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"
VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip() if _VERSION_FILE.exists() else "1.2.7"
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


def _valid_tradingview_url(url: Any) -> str | None:
    """Accept only canonical HTTPS TradingView chart links."""
    if not isinstance(url, str) or len(url) > 2000:
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"tradingview.com", "www.tradingview.com"}
        or not parsed.path.startswith("/chart/")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        return None
    return urllib.parse.urlunsplit(("https", "www.tradingview.com", parsed.path, parsed.query, ""))


def open_tradingview_desktop(url: Any) -> bool:
    """Ask the host OS to route a chart URL into TradingView Desktop."""
    safe_url = _valid_tradingview_url(url)
    if safe_url is None:
        return False

    # 1. Windows (Native Python on Windows NT or WSL)
    is_win = sys.platform == "win32" or os.name == "nt"
    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME")) or os.path.exists("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")

    if is_win or is_wsl:
        powershell = (
            "powershell.exe"
            if is_win
            else (shutil.which("powershell.exe") or "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        )
        escaped_url = safe_url.replace("'", "''")
        ps_code = f"""
$url = '{escaped_url}'
$candidates = @()
try {{
    $pkg = Get-AppxPackage *TradingView* -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pkg -and $pkg.InstallLocation) {{
        $candidates += Join-Path $pkg.InstallLocation 'TradingView.exe'
    }}
}} catch {{}}
$candidates += (Get-ChildItem -Path "$env:ProgramFiles\\WindowsApps\\TradingView.Desktop_*\\TradingView.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
$candidates += "$env:ProgramFiles\\TradingView Desktop\\TradingView.exe"
$candidates += "${{env:ProgramFiles(x86)}}\\TradingView Desktop\\TradingView.exe"
$candidates += "$env:LOCALAPPDATA\\Programs\\TradingView\\TradingView.exe"
$candidates += "$env:LOCALAPPDATA\\Programs\\TradingView Desktop\\TradingView.exe"

$found = $null
foreach ($c in $candidates) {{
    if ($c -and (Test-Path $c)) {{
        $found = $c
        break
    }}
}}

if ($found) {{
    Start-Process -FilePath $found -ArgumentList $url
    exit 0
}} else {{
    $cmd = Get-Command TradingView.exe -ErrorAction SilentlyContinue
    if ($cmd) {{
        Start-Process -FilePath 'TradingView.exe' -ArgumentList $url
        exit 0
    }} else {{
        exit 1
    }}
}}
"""
        try:
            encoded = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
            completed = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # 2. macOS
    if sys.platform == "darwin":
        try:
            completed = subprocess.run(
                ["open", "-a", "TradingView", safe_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0:
                return True
            completed = subprocess.run(
                ["open", safe_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # 3. Native Linux desktop
    if sys.platform.startswith("linux"):
        try:
            completed = subprocess.run(
                ["tradingview", safe_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0:
                return True
            completed = subprocess.run(
                ["xdg-open", safe_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    return False



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
        retry_after = e.headers.get("Retry-After") if e.headers else None
        try:
            retry_after_seconds = max(0.0, min(float(retry_after), 2.0)) if retry_after is not None else None
        except (TypeError, ValueError):
            retry_after_seconds = None
        log.error("HTTP %s %s: %s", e.code, path, body_err)
        result = {"code": str(e.code), "msg": body_err, "data": None, "_http": e.code}
        if retry_after_seconds is not None:
            result["_retry_after"] = retry_after_seconds
        return result
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


UPLINK_RATE_LIMITER = TokenBucketRateLimiter(rate=15.0, capacity=30.0)
PUBLIC_CACHE = TTLCache()
UPSTREAM_429_RETRIES = 2
UPSTREAM_429_FALLBACK_SECONDS = 0.15
UPSTREAM_429_MAX_BACKOFF_SECONDS = 1.0
READINESS_FRESH_SECONDS = 90.0
_sleep = time.sleep

class MarketDataHealth:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_success_monotonic: float | None = None
        self.last_error_code: str | None = None
        self.inflight = 0

MARKET_DATA_HEALTH = MarketDataHealth()

def reset_market_data_health() -> None:
    with MARKET_DATA_HEALTH.lock:
        MARKET_DATA_HEALTH.last_success_monotonic = None
        MARKET_DATA_HEALTH.last_error_code = None
        MARKET_DATA_HEALTH.inflight = 0

def record_market_data_result(response: dict) -> None:
    code = str(response.get("code", "ERR")) if isinstance(response, dict) else "ERR"
    with MARKET_DATA_HEALTH.lock:
        if code == "00000":
            MARKET_DATA_HEALTH.last_success_monotonic = time.monotonic()
            MARKET_DATA_HEALTH.last_error_code = None
        else:
            MARKET_DATA_HEALTH.last_error_code = code

def market_data_health_snapshot() -> dict:
    with MARKET_DATA_HEALTH.lock:
        last_success = MARKET_DATA_HEALTH.last_success_monotonic
        age = None if last_success is None else max(0.0, time.monotonic() - last_success)
        return {
            "last_success_age_seconds": age,
            "last_error_code": MARKET_DATA_HEALTH.last_error_code,
            "inflight": MARKET_DATA_HEALTH.inflight,
        }

def market_data_readiness() -> dict:
    snapshot = market_data_health_snapshot()
    age = snapshot["last_success_age_seconds"]
    if age is None:
        return {"ok": False, "code": "MARKET_DATA_NOT_READY", **snapshot}
    if age > READINESS_FRESH_SECONDS:
        return {"ok": False, "code": "MARKET_DATA_STALE", **snapshot}
    return {"ok": True, "code": "MARKET_DATA_READY", **snapshot}

class SingleFlight:
    def __init__(self):
        self._lock = threading.Lock()
        self._inflight: dict[tuple, threading.Event] = {}
        self._results: dict[tuple, dict] = {}

    def begin(self, key: tuple) -> tuple[threading.Event, bool]:
        with self._lock:
            event = self._inflight.get(key)
            if event is not None:
                return event, False
            event = threading.Event()
            self._results.pop(key, None)
            self._inflight[key] = event
            with MARKET_DATA_HEALTH.lock:
                MARKET_DATA_HEALTH.inflight += 1
            return event, True

    def result(self, key: tuple) -> dict | None:
        with self._lock:
            return self._results.get(key)

    def finish(self, key: tuple, event: threading.Event, result: dict) -> None:
        with self._lock:
            if self._inflight.get(key) is event:
                self._results[key] = result
                del self._inflight[key]
                with MARKET_DATA_HEALTH.lock:
                    MARKET_DATA_HEALTH.inflight = max(0, MARKET_DATA_HEALTH.inflight - 1)
                event.set()

PUBLIC_SINGLEFLIGHT = SingleFlight()

def _upstream_request_with_backoff(method: str, path: str, params: dict) -> dict:
    response: dict = {"code": "ERR", "data": None}
    for attempt in range(UPSTREAM_429_RETRIES + 1):
        response = _request(method, path, params, public=True)
        if not isinstance(response, dict) or response.get("_http") != 429:
            record_market_data_result(response if isinstance(response, dict) else {"code": "ERR"})
            return response
        if attempt == UPSTREAM_429_RETRIES:
            limited = {"code": "UPSTREAM_RATE_LIMIT", "msg": "Bitget upstream rate limit; retry later.", "data": None, "_http": 429}
            record_market_data_result(limited)
            return limited
        delay = response.get("_retry_after")
        if not isinstance(delay, (int, float)):
            delay = min(UPSTREAM_429_MAX_BACKOFF_SECONDS, UPSTREAM_429_FALLBACK_SECONDS * (2 ** attempt))
        _sleep(max(0.0, min(float(delay), UPSTREAM_429_MAX_BACKOFF_SECONDS)))
    return response

def _public_request_cached(method: str, path: str, params: dict) -> tuple[dict, bool]:
    """Cache public GETs and coalesce identical misses without blocking other keys."""
    method_upper = method.upper()
    cache_key = (method_upper, path, tuple(sorted((str(k), str(v)) for k, v in params.items())))
    if method_upper != "GET":
        if not UPLINK_RATE_LIMITER.consume():
            return {"code": "RELAY_BUSY", "msg": "Relay rate limit exceeded; retry shortly.", "data": None, "_http": 429}, False
        return _upstream_request_with_backoff(method_upper, path, params), False

    cached = PUBLIC_CACHE.get(cache_key)
    if cached is not None:
        return cached, True
    event, leader = PUBLIC_SINGLEFLIGHT.begin(cache_key)
    if not leader:
        event.wait()
        cached = PUBLIC_CACHE.get(cache_key)
        if cached is not None:
            return cached, True
        shared = PUBLIC_SINGLEFLIGHT.result(cache_key)
        if shared is not None:
            return shared, False
        return {"code": "RELAY_BUSY", "msg": "Identical relay request did not produce a result; retry shortly.", "data": None, "_http": 503}, False

    response: dict = {"code": "RELAY_BUSY", "msg": "Relay request interrupted.", "data": None, "_http": 503}
    try:
        cached = PUBLIC_CACHE.get(cache_key)
        if cached is not None:
            response = cached
            return response, True
        if not UPLINK_RATE_LIMITER.consume():
            response = {"code": "RELAY_BUSY", "msg": "Relay rate limit exceeded; retry shortly.", "data": None, "_http": 429}
            return response, False
        response = _upstream_request_with_backoff(method_upper, path, params)
        if response.get("code") == "00000":
            PUBLIC_CACHE.set(cache_key, response, PUBLIC_CACHE.get_ttl_for_path(path))
        return response, False
    finally:
        PUBLIC_SINGLEFLIGHT.finish(cache_key, event, response)


# ---------------------------------------------------------------------------
#  HTTP Request Handler
# ---------------------------------------------------------------------------

class RelayHandler(BaseHTTPRequestHandler):
    _PRIVILEGED_PATHS = {"/api/state", "/api/open-tradingview"}
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
            "Access-Control-Allow-Origin": origin if origin != "null" else "*",
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

        path = self._request_path()
        origin_value = self.headers.get("Origin")
        if origin_value is None:
            return True
        if path == "/api/open-tradingview" and origin_value == "null":
            return True
        try:
            origin = urllib.parse.urlsplit(origin_value)
            host_port = host.port
            origin_port = origin.port
            loopback_hosts = {"127.0.0.1", "localhost", "::1"}
            is_loopback_dispatch = (
                path == "/api/open-tradingview"
                and host.hostname in loopback_hosts
                and origin.hostname in loopback_hosts
            )
            # Host and Origin must describe exactly the same authority (or both be loopback for desktop dispatch).
            # The listener port is deliberately not consulted: Docker/NAT may
            # expose the internal listener on a different external port.
            same_authority = (
                (origin.hostname == host.hostname or is_loopback_dispatch)
                and origin.username is None
                and origin.password is None
                and (
                    is_loopback_dispatch
                    or (host_port is not None and origin_port == host_port)
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

    def _send_text(self, body: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
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
        elif path in ("/pine", "/Symbiose_Signal_System_v1.pine"):
            pine_file = Path(__file__).resolve().with_name("Symbiose_Signal_System_v1.pine")
            try:
                self._send_text(pine_file.read_bytes())
            except OSError:
                self._send_json({"code": "ERR_PINE_NOT_FOUND"}, 404)
        elif path == "/data/bitget_usdt_futures_universe.json":
            universe_file = Path(__file__).resolve().parent / "data" / "bitget_usdt_futures_universe.json"
            try:
                self._send_json(json.loads(universe_file.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                self._send_json({"code": "ERR_UNIVERSE_NOT_FOUND"}, 404)
        elif path == "/serving":
            self._send_json({
                "ok": True,
                "version": VERSION,
                "port": PORT,
                "mode": "quant_research",
            })
        elif path == "/ready":
            readiness = market_data_readiness()
            self._send_json(readiness, 200 if readiness["ok"] else 503)
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

        if path == "/api/open-tradingview":
            url = payload.get("url")
            if _valid_tradingview_url(url) is None:
                self._send_json({"code": "ERR_INVALID_TRADINGVIEW_URL"}, 400, cors_headers=self._privileged_cors_headers())
                return
            if not open_tradingview_desktop(url):
                self._send_json({"code": "ERR_TRADINGVIEW_DESKTOP"}, 503, cors_headers=self._privileged_cors_headers())
                return
            self._send_json({"ok": True, "target": "desktop_association"}, cors_headers=self._privileged_cors_headers())
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
            if isinstance(r, dict) and r.get("_http") in {429, 503}:
                status = int(r["_http"])
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
    log.info("AURA Relay v%s listening on http://%s:%d", VERSION, HOST, PORT)
    log.info("Modus: Quant Research & Signal Analysis (Read-Only CORS Proxy + Cross-Device Sync)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Relay gestoppt.")
