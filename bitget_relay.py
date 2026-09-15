"""
bitget_relay.py — AURA v1.10.1 local CORS proxy, web server & state sync
======================================================================
Startet einen lokalen HTTP-Server auf Port 8787.
Fungiert als Webserver für das Dashboard, als transparenter CORS-Proxy
für öffentliche Bitget-Marktdaten (/api/public) sowie als zentraler
State-Sync-Speicher (/api/state) für alle verbundenen Clients (PC, Smartphone, Tablet).

API-Vertrag (für das Dashboard):
  GET  /                 -> Symbiose_Dashboard.html
  GET  /tutorial         -> SYMBIOSE_Tutorial.html
  GET  /status           -> Human Status Page (HTML)
  GET  /serving          -> {"ok": true, "version": "1.10.1", "port": 8787, "mode": "quant_research"}
  GET  /api/state        -> Liefert alle synchronisierten Zustände (Autobot, Trades, Historie)
  POST /api/state        -> Speichert & synchronisiert Zustand zentral auf dem Server
  POST /api/public       -> Bitget public REST (transparent, kein Auth)
  POST /api/signals      -> Push-Notification via ntfy (PF-68: Server-Bot signal emission)
  GET  /api/universe     -> Cached universe list (liquid contracts)
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import faulthandler
import html
import json
import logging
import math
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

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
#  Configuration & Central Shared State
# ---------------------------------------------------------------------------
HOST = os.environ.get("SYM_HOST", "127.0.0.1")
PORT = int(os.environ.get("SYM_PORT", 8787))
_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"
if not _VERSION_FILE.exists():
    raise RuntimeError(
        f"CRITICAL DEPLOYMENT ERROR: VERSION file missing at {_VERSION_FILE}. "
        "AURA Relay requires a valid VERSION file to start (fail-closed)."
    )
VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip()
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
RELAY_START_TIME = time.time()
STATE_FILE = STATE_DIR / "aura_shared_state.json"
SIGNAL_STATE_FILE = STATE_DIR / "aura_signal_center_state.json"
SIGNAL_STATE_LOCK = threading.Lock()
MAX_STATE_VALUE_BYTES = 1_000_000
STATE_LOCK = threading.Lock()
ALLOWED_STATE_KEYS = {
    "aura-autobot-state-v2",
    "aura-quant-terminal-active-trades-v1",
    "aura-quant-terminal-history-trades-v1",
    "aura-ntfy-signals-settings-v1",
    # PF-67: server-bot config (written by Dashboard panel) and runtime state (written by runner)
    "aura-server-bot-config-v1",
    "aura-server-bot-state-v1",
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
            # Dashboard close events own their ntfy notification after winning a
            # persistent signal claim. The former PF-33 delete hook is absorbed
            # here so one semantic close cannot produce a second relay push.
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
#  PF-59: central ntfy signal policy and persistent claims
# ---------------------------------------------------------------------------

def _cooldown_ready(state: dict, category: str, *, now: float | None = None) -> bool:
    """Return whether a persisted category cooldown has elapsed."""
    current = time.time() if now is None else float(now)
    cooldowns = state.get("cooldowns", {}) if isinstance(state, dict) else {}
    return current >= float(cooldowns.get(category, 0) or 0)


def _set_cooldown(state: dict, category: str, minutes: int, *, now: float | None = None) -> None:
    """Persist a category-specific cooldown deadline in a state object."""
    current = time.time() if now is None else float(now)
    cooldowns = state.setdefault("cooldowns", {})
    cooldowns[category] = current + max(0, int(minutes)) * 60


def _claim_signal_event(key: Any, *, now: float | None = None) -> tuple[bool, int, PersistenceError | None]:
    """Atomically claim one dashboard event across tabs and process restarts."""
    if not isinstance(key, str) or not key or len(key) > 512:
        return False, 0, PersistenceError("invalid signal claim")
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
            claims = current.get("_signal_claims", {})
            if not isinstance(claims, dict):
                raise ValueError("signal claims must be a JSON object")
            if key in claims:
                return False, current_rev, None
            next_state = dict(current)
            next_claims = dict(claims)
            claimed_at = int(time.time() if now is None else float(now))
            next_claims[key] = claimed_at
            next_state["_signal_claims"] = next_claims
            next_state["_updated_at"] = claimed_at
            next_state["_rev"] = current_rev + 1
            tmp_path = STATE_FILE.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(next_state, indent=2), encoding="utf-8")
            tmp_path.replace(STATE_FILE)
            return True, next_state["_rev"], None
        except Exception as exc:
            log.error("Failed to persist signal claim: %s", exc)
            return False, int(current.get("_rev", 0)) if isinstance(current, dict) else 0, PersistenceError()


# ---------------------------------------------------------------------------
#  PF-33/PF-59: opt-in ntfy push notifications
# ---------------------------------------------------------------------------
# Activated by setting AURA_NTFY_URL to an ntfy topic URL, e.g.:
#   AURA_NTFY_URL=https://ntfy.sh/<TOPIC-NAME>
# When the variable is absent or empty, every notification is a silent no-op.
# All network I/O runs on a daemon thread — callers are never blocked.

def _ntfy_notify(title: str, body: str, *, category: str = "general", priority: int = 3) -> bool:
    """Fire-and-forget ntfy push notification. Silent no-op when disabled."""
    url = os.environ.get("AURA_NTFY_URL", "").strip()
    if not url:
        return False
    # Validate: only http/https accepted
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return False
    except Exception:
        return False

    safe_priority = min(5, max(1, int(priority)))
    safe_category = "".join(char for char in str(category).lower() if char.isalnum() or char in {"-", "_"})[:32] or "general"

    def _send() -> None:
        try:
            req = urllib.request.Request(
                url,
                data=body.encode("utf-8"),
                headers={
                    "X-Title": title,
                    "Priority": str(safe_priority),
                    "Tags": safe_category,
                    "Content-Type": "text/plain; charset=utf-8",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as exc:
            log.debug("ntfy notification failed (non-critical): %s", exc)

    t = threading.Thread(target=_send, daemon=True, name="ntfy-notify")
    t.start()
    return True


def notify_trade_closed(trade: dict) -> None:
    """Send a human-readable push notification when a trade is deleted/closed."""
    symbol = trade.get("symbol", "?")
    trade_id = trade.get("id", "?")
    side = trade.get("side", "")
    pnl = trade.get("pnl")
    pnl_str = f"  PnL: {pnl:+.2f}" if isinstance(pnl, (int, float)) else ""
    title = f"AURA Trade geschlossen: {symbol}"
    body = f"ID: {trade_id}  Symbol: {symbol}  Seite: {side}{pnl_str}"
    _ntfy_notify(title, body)


# ---------------------------------------------------------------------------
#  PF-62/PF-63: 24/7 BTC regime watcher, digest, and feed health
# ---------------------------------------------------------------------------

def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no", ""}


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(float(value) * alpha + out[-1] * (1.0 - alpha))
    return out


def _atr_series(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float]:
    n = len(close)
    out = [0.0] * n
    if n < period + 1:
        return out
    true_range = [0.0] * n
    true_range[0] = high[0] - low[0]
    for i in range(1, n):
        true_range[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out[period] = sum(true_range[1 : period + 1]) / period
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + true_range[i]) / period
    return out


def _adx_series(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float]:
    n = len(close)
    out = [0.0] * n
    if n < 2 * period + 1:
        return out
    true_range = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        true_range[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = sum(true_range[1 : period + 1])
    plus = sum(plus_dm[1 : period + 1])
    minus = sum(minus_dm[1 : period + 1])
    dx = [0.0] * n
    for i in range(period, n):
        if i > period:
            atr = atr - atr / period + true_range[i]
            plus = plus - plus / period + plus_dm[i]
            minus = minus - minus / period + minus_dm[i]
        plus_di = 100.0 * plus / atr if atr > 0 else 0.0
        minus_di = 100.0 * minus / atr if atr > 0 else 0.0
        dx[i] = 100.0 * abs(plus_di - minus_di) / (plus_di + minus_di) if plus_di + minus_di > 0 else 0.0
    out[2 * period - 1] = sum(dx[period : 2 * period]) / period
    for i in range(2 * period, n):
        out[i] = (out[i - 1] * (period - 1) + dx[i]) / period
    return out


def classify_btc_regime(candles: list[dict]) -> dict:
    """Classify BTC with the Dashboard EMA/ADX/Squeeze formulas."""
    if not isinstance(candles, list) or len(candles) < 200:
        raise ValueError("at least 200 valid candles are required")
    try:
        high = [float(item["h"]) for item in candles]
        low = [float(item["l"]) for item in candles]
        close = [float(item["c"]) for item in candles]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid BTC candle") from exc
    if not all(math.isfinite(x) and x > 0 for x in high + low + close):
        raise ValueError("BTC candles must contain finite positive prices")
    ema50 = _ema_series(close, 50)[-1]
    ema200 = _ema_series(close, 200)[-1]
    atr = _atr_series(high, low, close, 14)
    adx = _adx_series(high, low, close, 14)[-1]
    sample = close[-20:]
    mean = sum(sample) / 20
    variance = sum((x - mean) ** 2 for x in sample) / 20
    stddev = math.sqrt(variance)
    bb_width = (2.0 * stddev) / (mean or 1.0)
    kc_width = (4.0 * atr[-1]) / (mean or 1.0)
    squeeze = bb_width < kc_width and atr[-1] > 0
    bull = close[-1] > ema200 and ema50 > ema200
    bear = close[-1] < ema200 and ema50 < ema200
    base = "SIDEWAYS" if squeeze else "BULL" if bull else "BEAR" if bear else "SIDEWAYS"
    return {
        "base": base,
        "squeeze": squeeze,
        "adx": adx,
        "trend_strong": adx >= 20,
        "close": close[-1],
        "ema50": ema50,
        "ema200": ema200,
        "candle_close_ms": int(float(candles[-1].get("t", 0))),
    }


def _iso_utc(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def btc_regime_transition(state: dict, current: dict, *, now: float | None = None, cooldown_minutes: int = 30) -> dict:
    """Update regime state and decide whether this semantic transition may alert."""
    current_time = time.time() if now is None else float(now)
    previous = state.get("btc", {}) if isinstance(state, dict) else {}
    previous_base = previous.get("base")
    previous_signal_base = previous.get("signal_base", previous_base)
    squeeze = bool(current.get("squeeze", False))
    current_signal_base = previous_signal_base if squeeze else current["base"]
    changed = previous_signal_base is not None and previous_signal_base != current_signal_base
    last_notified = float(previous.get("last_notified_at", 0) or 0)
    cooldown_ready = current_time - last_notified >= max(0, cooldown_minutes) * 60
    notify = changed and not squeeze and cooldown_ready
    strong = "Trend stark" if float(current.get("adx", 0)) >= 20 else "Trend schwach"
    if current["base"] == "BULL":
        structure = "BTC über EMA200 & EMA50 über EMA200. Bot-Gate blockiert jetzt Shorts."
    elif current["base"] == "BEAR":
        structure = "BTC unter EMA200 & EMA50 unter EMA200. Bot-Gate blockiert jetzt Longs."
    else:
        structure = "BTC ohne sauberen EMA50/EMA200-Trend. Bot-Gate wartet auf Richtung."
    body = f"{current['base']} ab jetzt — {structure} ADX {float(current.get('adx', 0)):.1f} ({strong})."
    next_btc = dict(current)
    next_btc["signal_base"] = current_signal_base
    next_btc["regime_changed_at"] = _iso_utc(current_time) if changed else previous.get("regime_changed_at", _iso_utc(current_time))
    next_btc["last_success_at"] = _iso_utc(current_time)
    if notify:
        next_btc["last_notified_at"] = current_time
    elif last_notified:
        next_btc["last_notified_at"] = last_notified
    return {"notify": notify, "body": body, "btc": next_btc}


def _load_signal_state() -> dict:
    with SIGNAL_STATE_LOCK:
        if not SIGNAL_STATE_FILE.exists():
            return {"schema_version": 1}
        try:
            value = json.loads(SIGNAL_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            raise StatePersistenceError() from exc
        if not isinstance(value, dict):
            raise StatePersistenceError()
        return value


def _save_signal_state(state: dict) -> None:
    with SIGNAL_STATE_LOCK:
        SIGNAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SIGNAL_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(SIGNAL_STATE_FILE)


def _parse_bitget_candles(response: dict, *, now_ms: int | None = None) -> list[dict]:
    if not isinstance(response, dict) or response.get("code") != "00000" or not isinstance(response.get("data"), list):
        raise ValueError("Bitget BTC candle request failed")
    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    parsed = []
    for row in response["data"]:
        if not isinstance(row, list) or len(row) < 6:
            continue
        timestamp = int(row[0])
        if timestamp + 3_600_000 > current_ms:
            continue
        parsed.append({"t": timestamp, "o": float(row[1]), "h": float(row[2]), "l": float(row[3]), "c": float(row[4]), "v": float(row[5])})
    parsed.sort(key=lambda item: item["t"])
    return parsed


def _fetch_btc_closed_candles() -> list[dict]:
    response, _ = _public_request_cached("GET", "/api/v2/mix/market/candles", {
        "symbol": "BTCUSDT", "productType": "USDT-FUTURES", "granularity": "1H", "limit": 300,
    })
    return _parse_bitget_candles(response)


def run_btc_regime_cycle(fetch_candles=_fetch_btc_closed_candles, *, now: float | None = None) -> dict:
    current_time = time.time() if now is None else float(now)
    state = _load_signal_state()
    regime = classify_btc_regime(fetch_candles())
    cooldown = int(os.environ.get("AURA_NTFY_BTC_COOLDOWN_MIN", "30"))
    transition = btc_regime_transition(state, regime, now=current_time, cooldown_minutes=cooldown)
    state["schema_version"] = 1
    state["btc"] = transition["btc"]
    state = feed_success_transition(state, now=current_time)
    state["updated_at"] = _iso_utc(current_time)
    _save_signal_state(state)
    if transition["notify"] and _env_enabled("AURA_NTFY_BTC", True):
        _ntfy_notify("AURA BTC-Regime gewechselt", transition["body"], category="btc", priority=4)
    return regime


def digest_enabled() -> bool:
    raw = os.environ.get("AURA_NTFY_DIGEST")
    if raw is not None:
        return _env_enabled("AURA_NTFY_DIGEST", True)
    hour = os.environ.get("AURA_NTFY_DIGEST_UTC", "7").strip().lower()
    return hour not in {"off", "false", "none", "disabled", "-1"}


def _event_timestamp_seconds(event: dict) -> float:
    raw = event.get("closedAt", event.get("closed_at", event.get("exitAt", 0)))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value / 1000.0 if value > 10_000_000_000 else value


def _event_pnl(event: dict) -> float:
    for key in ("realizedPnlGross", "realizedPnl", "netPnl", "pnl"):
        value = event.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            return float(value)
    return 0.0


def daily_digest_transition(
    state: dict,
    shared: dict,
    *,
    now: float | None = None,
    utc_hour: int = 7,
    restart_timestamps: list[float] | tuple[float, ...] | None = None,
) -> dict:
    current_time = time.time() if now is None else float(now)
    utc_hour = min(23, max(0, int(utc_hour)))
    date_key = time.strftime("%Y-%m-%d", time.gmtime(current_time))
    hour = time.gmtime(current_time).tm_hour
    next_state = dict(state) if isinstance(state, dict) else {}
    digest = dict(next_state.get("digest", {}))
    due = hour >= utc_hour and digest.get("last_sent_utc_date") != date_key
    shared = shared if isinstance(shared, dict) else {}
    autobot = shared.get("aura-autobot-state-v2", {})
    server_bot = shared.get("aura-server-bot-state-v1", {})
    equity_raw = server_bot.get("equity") if isinstance(server_bot, dict) else None
    if not isinstance(equity_raw, (int, float)) or isinstance(equity_raw, bool) or not math.isfinite(float(equity_raw)):
        equity_raw = os.environ.get("AURA_BOT_EQUITY", "10000")
    try:
        equity = float(equity_raw)
    except (TypeError, ValueError):
        equity = 10000.0
    if not math.isfinite(equity):
        equity = 10000.0
    manual_open = shared.get("aura-quant-terminal-active-trades-v1", [])
    manual_history = shared.get("aura-quant-terminal-history-trades-v1", [])
    autobot_open = autobot.get("trades", []) if isinstance(autobot, dict) else []
    autobot_history = autobot.get("history", []) if isinstance(autobot, dict) else []
    open_count = (len(manual_open) if isinstance(manual_open, list) else 0) + (len(autobot_open) if isinstance(autobot_open, list) else 0)
    history = []
    if isinstance(manual_history, list):
        history.extend(manual_history)
    if isinstance(autobot_history, list):
        history.extend(autobot_history)
    recent = [item for item in history if isinstance(item, dict) and current_time - _event_timestamp_seconds(item) <= 86400 and _event_timestamp_seconds(item) <= current_time]
    pnl = sum(_event_pnl(item) for item in recent)
    restarts = restart_timestamps or ()
    restart_count_24h = sum(
        1 for stamp in restarts
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
        and math.isfinite(float(stamp)) and current_time - 86400.0 <= float(stamp) <= current_time
    )
    btc = next_state.get("btc", {})
    base = btc.get("base", "UNBEKANNT") if isinstance(btc, dict) else "UNBEKANNT"
    body = (
        f"Paper-Equity {equity:.2f} USDT · {open_count} offene Position"
        f"{'en' if open_count != 1 else ''} · BTC {base} · {len(recent)} Schluss"
        f"{'e' if len(recent) != 1 else ''} in 24h · PnL {pnl:+.2f} USDT"
        f" · {restart_count_24h} Selbstheilungen in 24 h"
    )

    shadow_info = _shadow_health()
    if shadow_info.get("enabled"):
        state_dir = Path(os.environ.get("AURA_STATE_DIR") or STATE_DIR)
        log_path = state_dir / "shadow_log.jsonl"
        acc_rs = []
        rej_rs = []
        total_entries = 0
        total_eval = 0
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            total_entries += 1
                            if rec.get("outcome") is not None:
                                total_eval += 1
                                r_val = rec.get("r_net", rec.get("rNet"))
                                if r_val is not None:
                                    try:
                                        r_float = float(r_val)
                                        if rec.get("decision") == "ACCEPTED":
                                            acc_rs.append(r_float)
                                        else:
                                            rej_rs.append(r_float)
                                    except (TypeError, ValueError):
                                        pass
                        except Exception:
                            continue
            except Exception:
                pass

        acc_avg_str = f"{sum(acc_rs)/len(acc_rs):+.2f}R" if acc_rs else "N/A"
        rej_avg_str = f"{sum(rej_rs)/len(rej_rs):+.2f}R" if rej_rs else "N/A"
        body += f" · Schatten: {total_entries} Setups beobachtet, {total_eval} bewertet, Ø-R {acc_avg_str} vs. {rej_avg_str}"

    funnel_info = _funnel_health()
    if funnel_info.get("scanned", 0) > 0 or funnel_info.get("reject_reasons"):
        scanned = funnel_info.get("scanned", 0)
        candidates = funnel_info.get("radar_passed", 0)
        selected = funnel_info.get("selected", 0)
        rejects = funnel_info.get("reject_reasons", {})
        sorted_rejects = sorted(rejects.items(), key=lambda x: x[1], reverse=True)
        if sorted_rejects:
            top_str = ", ".join(f"{k} ({v})" for k, v in sorted_rejects[:3])
        else:
            top_str = "keine"
        body += f" · Funnel 24 h: {scanned} gescannt · {candidates} Kandidaten · {selected} selected · Top-Absagen: {top_str}"

    if due:
        digest["last_sent_utc_date"] = date_key
        next_state["digest"] = digest
    return {"notify": due, "body": body, "state": next_state}


def runner_stale_threshold(
    scan_sec: float | str | None = None,
    override_raw: float | str | None = None,
) -> float:
    """Return the configured positive stale threshold with a safe fallback."""
    if scan_sec is None:
        scan_sec = os.environ.get("AURA_BOT_SCAN_SEC", "60")
    try:
        scan_value = float(scan_sec)
    except (TypeError, ValueError):
        scan_value = 60.0
    if not math.isfinite(scan_value) or scan_value <= 0:
        scan_value = 60.0
    fallback = max(3.0 * scan_value, 180.0)

    if override_raw is None:
        override_raw = os.environ.get("AURA_RUNNER_STALE_SEC")
    try:
        override = float(override_raw)
    except (TypeError, ValueError):
        return fallback
    return override if math.isfinite(override) and override > 0 else fallback


def runner_dead_transition(
    state: dict,
    runner_health: dict,
    *,
    mode: str = "server",
    now: float | None = None,
    relay_start_time: float | None = None,
    startup_grace_sec: float = 120.0,
    stale_sec: float | None = None,
) -> dict:
    """Trigger P4 alert with 60 min cooldown when server runner is dead or stale.
    
    Startup Grace: suppresses dead-runner alarms during the initial startup window
    until the runner has completed at least one full cycle (cycle_count >= 1) or
    until the grace period (default: 120s) after relay start expires.
    """
    current_time = time.time() if now is None else float(now)
    start_time = (RELAY_START_TIME if now is None else 0.0) if relay_start_time is None else float(relay_start_time)
    next_state = dict(state) if isinstance(state, dict) else {}
    health = dict(next_state.get("runner_health_alert", {}))
    
    if mode != "server":
        return {"notify": False, "stalled": False, "body": "", "state": next_state}

    cycle_count = runner_health.get("cycle_count")
    if cycle_count is None:
        cycle_count = runner_health.get("cycleCount", 0)
    try:
        cycle_count = int(cycle_count or 0)
    except (ValueError, TypeError):
        cycle_count = 0

    paused = bool(runner_health.get("paused", False))
    threshold = runner_stale_threshold() if stale_sec is None else float(stale_sec)
    if paused:
        heartbeat_age = runner_health.get("last_heartbeat_age_sec")
        if heartbeat_age is None:
            heartbeat_age = runner_health.get("last_cycle_age_sec")
        is_stale = (
            heartbeat_age is None
            or not isinstance(heartbeat_age, (int, float))
            or not math.isfinite(float(heartbeat_age))
            or float(heartbeat_age) > threshold
        )
        display_age = heartbeat_age
    else:
        cycle_age = runner_health.get("last_cycle_age_sec")
        is_stale = (
            cycle_age is None
            or not isinstance(cycle_age, (int, float))
            or not math.isfinite(float(cycle_age))
            or float(cycle_age) > threshold
        )
        display_age = cycle_age

    # Startup grace: do not alert before runner has completed its first cycle,
    # provided we are still within the initial grace window after relay startup.
    in_startup_grace = (cycle_count < 1) and ((current_time - start_time) < startup_grace_sec)
    if in_startup_grace:
        return {"notify": False, "stalled": False, "body": "", "state": next_state}

    if is_stale:
        cooldown_until = float(health.get("cooldown_until", 0) or 0)
        notify = current_time >= cooldown_until
        health["last_error_at"] = current_time
        if notify:
            health["alerted_at"] = current_time
            health["cooldown_until"] = current_time + 3600.0  # 60 min cooldown
        next_state["runner_health_alert"] = health
        age_str = f"{display_age:.0f}s" if isinstance(display_age, (int, float)) and math.isfinite(float(display_age)) else "unbekannt"
        return {
            "notify": notify,
            "stalled": True,
            "body": f"AURA Server-Autobot reagiert nicht mehr (letzter Zyklus vor {age_str}). Selbstheilung ausgelöst",
            "state": next_state,
        }
    else:
        # Runner is healthy: clear error state but preserve cooldown timestamp
        health["last_error_at"] = None
        next_state["runner_health_alert"] = health
        return {"notify": False, "stalled": False, "body": "", "state": next_state}


def runner_watchdog_cycle(
    state: dict,
    runner_health: dict,
    *,
    manager: "RunnerManager",
    now: float | None = None,
    stale_sec: float | None = None,
    relay_start_time: float | None = None,
) -> dict:
    """Apply alert cooldown plus one atomic manager lifecycle transition."""
    transition = runner_dead_transition(
        state,
        runner_health,
        mode="server",
        now=now,
        relay_start_time=relay_start_time,
        stale_sec=stale_sec,
    )
    if not transition["stalled"]:
        cycle_count = RunnerManager._cycle_count(runner_health)
        age = runner_health.get("last_cycle_age_sec") if not runner_health.get("paused") else runner_health.get("last_heartbeat_age_sec")
        in_startup_grace = (
            cycle_count < 1
            and age is None
            and float(time.time() if now is None else now)
            - float(RELAY_START_TIME if relay_start_time is None else relay_start_time) < 120.0
        )
        lifecycle = (
            {"restarted": False, "recovered": False}
            if in_startup_grace
            else manager.watchdog(runner_health, now=now, stale_sec=stale_sec)
        )
        notification = None
        if lifecycle["recovered"]:
            notification = {
                "title": "AURA Runner wieder aktiv",
                "body": "Selbstheilung erfolgreich — Runner wieder aktiv",
                "priority": 3,
            }
        return {"state": transition["state"], "stalled": transition["stalled"], "notification": notification, **lifecycle}

    lifecycle = manager.watchdog(runner_health, now=now, stale_sec=stale_sec)
    notification = None
    if transition["notify"]:
        notification = {
            "title": "AURA Runner-Fehler",
            "body": transition["body"],
            "priority": 4,
        }
    return {"state": transition["state"], "stalled": transition["stalled"], "notification": notification, **lifecycle}


def feed_success_transition(state: dict, *, now: float | None = None) -> dict:
    """End one consecutive feed-error period without shortening its cooldown."""
    current_time = time.time() if now is None else float(now)
    next_state = dict(state) if isinstance(state, dict) else {}
    health = dict(next_state.get("health", {}))
    health.update({
        "first_error_at": None,
        "last_error_at": None,
        "last_error": None,
        "last_success_at": current_time,
    })
    next_state["health"] = health
    return next_state


def feed_error_transition(state: dict, reason: str, *, now: float | None = None) -> dict:
    current_time = time.time() if now is None else float(now)
    next_state = dict(state) if isinstance(state, dict) else {}
    health = dict(next_state.get("health", {}))
    first_error = float(health.get("first_error_at", current_time) or current_time)
    cooldown_until = float(health.get("data_dead_cooldown_until", 0) or 0)
    notify = current_time - first_error > 300 and current_time >= cooldown_until
    health.update({
        "first_error_at": first_error,
        "last_error_at": current_time,
        "last_error": str(reason)[:300],
    })
    if notify:
        health["data_dead_alerted_at"] = current_time
        health["data_dead_cooldown_until"] = current_time + 3600
    next_state["health"] = health
    return {
        "notify": notify,
        "body": f"BTC-Marktdaten seit mehr als 5 Minuten nicht verfügbar: {str(reason)[:180]}",
        "state": next_state,
    }


def run_signal_center_cycle(fetch_candles=_fetch_btc_closed_candles, *, now: float | None = None) -> dict:
    """Run one scheduler-safe cycle and persist every success/failure decision."""
    current_time = time.time() if now is None else float(now)
    try:
        regime = run_btc_regime_cycle(fetch_candles, now=current_time)
        state = _load_signal_state()
        try:
            shared = _load_shared_state()
        except StatePersistenceError:
            shared = {}
        digest_raw = os.environ.get("AURA_NTFY_DIGEST_UTC", "7").strip().lower()
        digest_hour = 7 if digest_raw in {"off", "false", "none", "disabled", "-1"} else int(digest_raw)
        digest = daily_digest_transition(
            state,
            shared,
            now=current_time,
            utc_hour=digest_hour,
            restart_timestamps=RUNNER_MANAGER.snapshot(now=current_time)["restart_timestamps"],
        )
        if digest["notify"] and digest_enabled():
            _ntfy_notify("AURA Tages-Digest", digest["body"], category="digest", priority=1)
        digest["state"]["updated_at"] = _iso_utc(current_time)
        _save_signal_state(digest["state"])

        bot_mode = os.environ.get("AURA_BOT_MODE", "").strip().lower()
        if bot_mode == "server":
            watchdog = runner_watchdog_cycle(
                _load_signal_state(),
                _runner_health(),
                manager=RUNNER_MANAGER,
                now=current_time,
            )
            notification = watchdog["notification"]
            if notification and _env_enabled("AURA_NTFY_ERRORS", True):
                _ntfy_notify(
                    notification["title"],
                    notification["body"],
                    category="errors",
                    priority=notification["priority"],
                )
            _save_signal_state(watchdog["state"])

        return {"ok": True, "regime": regime, "digest": digest["notify"]}
    except Exception as exc:
        try:
            state = _load_signal_state()
        except StatePersistenceError:
            state = {"schema_version": 1}
        error = feed_error_transition(state, str(exc), now=current_time)
        error["state"]["updated_at"] = _iso_utc(current_time)
        _save_signal_state(error["state"])
        if error["notify"] and _env_enabled("AURA_NTFY_ERRORS", True):
            _ntfy_notify("AURA Datenfehler", error["body"], category="errors", priority=4)
        return {"ok": False, "error": str(exc), "notified": error["notify"]}


def _signal_center_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            run_signal_center_cycle()
        except Exception:
            log.exception("Signal-Center cycle crashed; continuing scheduler loop")
        wait = 300.0 - (time.time() % 300.0)
        stop_event.wait(max(1.0, wait))


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
        with urllib.request.urlopen(req, timeout=10) as resp:
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


# PF-69: Runner health — reads runner_health.json written by headless_autobot.js
def _runner_health(*, mode: str | None = None) -> dict:
    eff_mode = os.environ.get("AURA_BOT_MODE", "").strip().lower() if mode is None else str(mode).strip().lower()
    snap = RUNNER_MANAGER.snapshot()
    restart_count = snap.get("runner_restart_count", 0)
    crash_count = snap.get("runner_crash_count", 0)
    crash_loop = snap.get("crash_loop_detected", False)
    if eff_mode != "server":
        return {
            "mode": "none",
            "bot_enabled": False,
            "running": False,
            "state": "not_configured",
        }

    health_path = STATE_DIR / "runner_health.json"
    try:
        data = json.loads(health_path.read_text(encoding="utf-8"))
        last_cycle = data.get("lastCycleAt")
        last_heartbeat = data.get("lastHeartbeatAt", last_cycle)
        age_sec: float | None = None
        if isinstance(last_cycle, (int, float)) and last_cycle > 0:
            age_sec = round((time.time() * 1000 - last_cycle) / 1000, 1)
        heartbeat_age_sec: float | None = None
        if isinstance(last_heartbeat, (int, float)) and last_heartbeat > 0:
            heartbeat_age_sec = round((time.time() * 1000 - last_heartbeat) / 1000, 1)
        paused = bool(data.get("paused", False))
        paused_by = data.get("pausedBy", data.get("paused_by", None)) if paused else None
        running = bool(data.get("running", False))
        state_str = "paused" if paused else ("running" if running else "stopped")
        return {
            "mode": "server",
            "bot_enabled": True,
            "running": running,
            "state": state_str,
            "last_cycle_age_sec": age_sec,
            "last_heartbeat_age_sec": heartbeat_age_sec,
            "paused": paused,
            "paused_by": paused_by,
            "cycle_count": data.get("cycleCount", 0),
            "trade_count": data.get("tradeCount", 0),
            "equity": data.get("equity"),
            "runner_restart_count": restart_count,
            "runner_crash_count": crash_count,
            "crash_loop_detected": crash_loop,
        }
    except (OSError, json.JSONDecodeError, TypeError):
        return {
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
            "runner_restart_count": restart_count,
            "runner_crash_count": crash_count,
            "crash_loop_detected": crash_loop,
        }


# Slice C: Shadow Collector health — reports {enabled, entries, pending_outcomes, evaluated}
def _shadow_health() -> dict:
    env_shadow = os.environ.get("AURA_SHADOW", "").strip().lower()
    enabled = env_shadow not in {"0", "false", "off", "no"}
    if not enabled:
        return {
            "enabled": False,
            "entries": 0,
            "pending_outcomes": 0,
            "evaluated": 0,
        }
    state_dir = Path(os.environ.get("AURA_STATE_DIR") or STATE_DIR)
    stats_path = state_dir / "shadow_stats.json"
    if stats_path.exists():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            if isinstance(stats, dict) and "entries" in stats:
                return {
                    "enabled": True,
                    "entries": int(stats.get("entries", 0)),
                    "pending_outcomes": int(stats.get("pending_outcomes", 0)),
                    "evaluated": int(stats.get("evaluated", 0)),
                }
        except Exception:
            pass

    log_path = state_dir / "shadow_log.jsonl"
    if not log_path.exists():
        return {
            "enabled": True,
            "entries": 0,
            "pending_outcomes": 0,
            "evaluated": 0,
        }
    entries = 0
    evaluated = 0
    pending = 0
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    entries += 1
                    if rec.get("outcome") is not None:
                        evaluated += 1
                    else:
                        pending += 1
                except Exception:
                    continue
    except Exception:
        pass
    return {
        "enabled": True,
        "entries": entries,
        "pending_outcomes": pending,
        "evaluated": evaluated,
    }


def mask_ntfy_url(url: str | None) -> str:
    """Mask ntfy URL so topic names are never exposed in plain text.
    
    Topic name is masked to at most first 6 characters followed by '…'.
    E.g. 'https://ntfy.sh/aura-live-signals-test123' -> 'https://ntfy.sh/aura-l…'
    """
    if not url or not isinstance(url, str) or not url.strip():
        return "Nicht konfiguriert"
    clean = url.strip()
    parsed = urllib.parse.urlparse(clean)
    if not parsed.netloc:
        return (clean[:6] + "…") if len(clean) > 6 else clean
    topic = parsed.path.lstrip("/")
    if not topic:
        return f"{parsed.scheme}://{parsed.netloc}"
    masked_topic = (topic[:6] + "…") if len(topic) > 6 else (topic[:2] + "…" if len(topic) > 2 else "…")
    return f"{parsed.scheme}://{parsed.netloc}/{masked_topic}"


def _format_berlin_time(dt_utc: datetime) -> str:
    """Format UTC datetime into Europe/Berlin local time string."""
    if ZoneInfo is not None:
        try:
            return dt_utc.astimezone(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            pass
    return dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC")


def _funnel_health() -> dict:
    """Read 24h rolling funnel summary from runner_health.json or shared state."""
    state_dir = Path(os.environ.get("AURA_STATE_DIR") or STATE_DIR)
    health_path = state_dir / "runner_health.json"
    if health_path.exists():
        try:
            data = json.loads(health_path.read_text(encoding="utf-8"))
            f24 = data.get("funnel24h")
            if isinstance(f24, dict):
                return {
                    "scanned": int(f24.get("scanned", 0)),
                    "radar_passed": int(f24.get("radar_passed", f24.get("radarFiltered", 0))),
                    "wf_evaluated": int(f24.get("wf_evaluated", f24.get("wfEvaluated", 0))),
                    "selected": int(f24.get("selected", 0)),
                    "reject_reasons": dict(f24.get("reject_reasons", f24.get("rejects", {}))),
                }
        except Exception:
            pass
    return {
        "scanned": 0,
        "radar_passed": 0,
        "wf_evaluated": 0,
        "selected": 0,
        "reject_reasons": {},
    }


def render_status_html(
    *,
    now: float | None = None,
    disk_free_mb_override: float | None = None,
    disk_total_mb_override: float | None = None,
    state_dir_override: Path | None = None,
) -> str:
    """Render the self-contained human-readable status page for GET /status."""
    current_time = time.time() if now is None else float(now)
    state_dir = state_dir_override or Path(os.environ.get("AURA_STATE_DIR") or STATE_DIR)

    readiness = market_data_readiness()
    snapshot = market_data_health_snapshot()
    runner = _runner_health()
    shadow = _shadow_health()
    funnel = _funnel_health()
    signal_state = _load_signal_state()

    bot_mode = os.environ.get("AURA_BOT_MODE", "").strip().lower()
    bot_enabled = bot_mode == "server"
    ntfy_url = os.environ.get("AURA_NTFY_URL", "").strip()
    masked_ntfy = mask_ntfy_url(ntfy_url)
    has_ntfy = bool(ntfy_url)

    # Disk usage
    if disk_free_mb_override is not None:
        free_mb = float(disk_free_mb_override)
        total_mb = float(disk_total_mb_override or free_mb)
    else:
        try:
            usage = shutil.disk_usage(state_dir)
            free_mb = usage.free / (1024 * 1024)
            total_mb = usage.total / (1024 * 1024)
        except Exception:
            free_mb = 1024.0
            total_mb = 10240.0

    free_gb = free_mb / 1024.0
    total_gb = total_mb / 1024.0

    state_size_bytes = 0
    if state_dir.exists():
        try:
            state_size_bytes = sum(f.stat().st_size for f in state_dir.glob("**/*") if f.is_file())
        except Exception:
            pass
    state_size_mb = state_size_bytes / (1024 * 1024)

    # Violations / Health logic
    violations: list[str] = []
    threshold = runner_stale_threshold()

    if bot_mode == "server":
        if runner.get("crash_loop_detected"):
            violations.append("Crash-Loop erkannt: Runner stürzt wiederholt kurz nach dem Start ab (>= 3 schnelle Abstürze).")
        runner_state = runner.get("state", "stopped")
        if runner_state == "stopped" or not runner.get("running"):
            violations.append("Server-Bot ist aktiviert (AURA_BOT_MODE=server), aber der Runner läuft nicht (Status: gestoppt).")
        elif runner.get("paused"):
            hb_age = runner.get("last_heartbeat_age_sec")
            if hb_age is None or hb_age > threshold:
                age_display = f"{hb_age:.1f}s" if hb_age is not None else "unbekannt"
                violations.append(f"Server-Bot ist pausiert, aber der Heartbeat ist veraltet ({age_display} > Schwelle {threshold:.0f}s).")
        else:
            cycle_age = runner.get("last_cycle_age_sec")
            if cycle_age is None or cycle_age > threshold:
                age_display = f"{cycle_age:.1f}s" if cycle_age is not None else "unbekannt"
                violations.append(f"Server-Bot-Runner ist nicht frisch (letzter Scan vor {age_display} > Schwelle {threshold:.0f}s).")

    last_error = snapshot.get("last_error_code")
    if last_error is not None:
        violations.append(f"Market-Data-Fehler aktiv: {html.escape(str(last_error))}")

    if free_mb <= 500.0:
        violations.append(f"Festplattenspeicher knapp: {free_mb:.1f} MB frei (Minimum: 500 MB).")

    is_ok = len(violations) == 0
    banner_status = "ALLES OK" if is_ok else "HANDLUNGSBEDARF"
    banner_class = "banner-ok" if is_ok else "banner-error"

    # Uptime & Timestamps
    uptime_sec = max(0.0, current_time - float(RELAY_START_TIME))
    hours, remainder = divmod(int(uptime_sec), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours} Std. {minutes} Min. {seconds} Sek." if hours > 0 else f"{minutes} Min. {seconds} Sek."

    dt_utc = datetime.fromtimestamp(current_time, timezone.utc)
    utc_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    berlin_str = _format_berlin_time(dt_utc)

    # Digest timestamp
    digest_date = signal_state.get("digest", {}).get("last_sent_utc_date", "noch nie")
    if not digest_date:
        digest_date = "noch nie"

    restarts_24h = RUNNER_MANAGER.snapshot(now=current_time).get("runner_restart_count", 0)

    # Format violations HTML
    if violations:
        violations_html = "<ul class=\"violations-list\">" + "".join(
            f"<li>{html.escape(v)}</li>" for v in violations
        ) + "</ul>"
    else:
        violations_html = "<div class=\"banner-sub\">Alle Kernkomponenten, Runner-Heartbeats und Speicherprüfungen arbeiten fehlerfrei.</div>"

    # Runner display strings
    cycle_age = runner.get("last_cycle_age_sec")
    cycle_age_str = f"{cycle_age:.1f}s" if isinstance(cycle_age, (int, float)) else "—"
    runner_paused = bool(runner.get("paused", False))
    runner_paused_by = runner.get("paused_by")
    paused_display = f"Ja ({html.escape(str(runner_paused_by))})" if runner_paused else "Nein"

    # Mode note
    if bot_mode != "server":
        mode_note = "<span class=\"note\">(Bewusst nicht als Server-Bot konfiguriert)</span>"
    else:
        mode_note = "<span class=\"note-ok\">(AURA_BOT_MODE=server)</span>"

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AURA Status — Confluence Terminal</title>
<style>
:root {{
  --bg: #090d16;
  --panel: #0f172a;
  --border: #1e293b;
  --txt: #f8fafc;
  --mut: #94a3b8;
  --dim: #64748b;
  --cyn: #00f5d4;
  --gn: #10b981;
  --rd: #ef4444;
  --yw: #f59e0b;
  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  --sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--txt);
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.5;
  padding: 24px 16px;
  display: flex;
  justify-content: center;
}}
.container {{
  width: 100%;
  max-width: 900px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}}
header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding-bottom: 14px;
}}
.logo-title {{
  display: flex;
  align-items: center;
  gap: 10px;
}}
.logo {{
  font-family: var(--mono);
  font-weight: 900;
  font-size: 18px;
  color: var(--cyn);
  letter-spacing: 0.1em;
}}
.badge {{
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(0, 245, 212, 0.12);
  color: var(--cyn);
  border: 1px solid rgba(0, 245, 212, 0.3);
  text-transform: uppercase;
}}
.header-right {{
  font-family: var(--mono);
  font-size: 11px;
  color: var(--mut);
}}
.banner {{
  border-radius: 10px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.banner-ok {{
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid var(--gn);
}}
.banner-error {{
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid var(--rd);
}}
.banner-head {{
  display: flex;
  align-items: center;
  gap: 10px;
}}
.banner-title {{
  font-family: var(--mono);
  font-weight: 900;
  font-size: 20px;
  letter-spacing: 0.05em;
}}
.banner-ok .banner-title {{ color: var(--gn); }}
.banner-error .banner-title {{ color: var(--rd); }}
.banner-sub {{
  color: var(--mut);
  font-size: 12px;
}}
.violations-list {{
  margin-top: 6px;
  padding-left: 20px;
  color: #fca5a5;
  font-size: 12.5px;
}}
.violations-list li {{
  margin-bottom: 4px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}}
.card {{
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.card-head {{
  font-size: 11px;
  font-weight: 700;
  color: var(--cyn);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.row {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  padding: 3px 0;
}}
.row:last-child {{ border-bottom: 0; }}
.label {{ color: var(--mut); }}
.val {{ font-family: var(--mono); font-weight: 600; color: var(--txt); }}
.val-ok {{ color: var(--gn); }}
.val-warn {{ color: var(--yw); }}
.val-err {{ color: var(--rd); }}
.note {{ font-size: 10.5px; color: var(--dim); display: block; margin-top: 2px; }}
.note-ok {{ font-size: 10.5px; color: var(--gn); display: block; margin-top: 2px; }}
footer {{
  margin-top: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: var(--dim);
}}
.doctor-hint {{
  color: var(--mut);
  font-family: var(--mono);
}}
.doctor-cmd {{
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--cyn);
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo-title">
      <span class="logo">AURA</span>
      <span class="badge">STATUS</span>
    </div>
    <div class="header-right">
      <span>v{html.escape(VERSION)}</span> · <span>quant_research</span>
    </div>
  </header>

  <div class="banner {banner_class}">
    <div class="banner-head">
      <span class="banner-title">{banner_status}</span>
    </div>
    {violations_html}
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-head">Version &amp; Build</div>
      <div class="row"><span class="label">Version</span><span class="val">v{html.escape(VERSION)}</span></div>
      <div class="row"><span class="label">Relay-Port</span><span class="val">{PORT}</span></div>
      <div class="row"><span class="label">Modus</span><span class="val">quant_research</span></div>
      <div class="row"><span class="label">Verdict</span><span class="val" style="font-size:10px">SOFTWARE_GO / MODEL_NO_EVIDENCE</span></div>
    </div>

    <div class="card">
      <div class="card-head">Bot-Modus &amp; Konfiguration</div>
      <div class="row"><span class="label">Modus</span><span class="val">{html.escape(runner.get("mode", "none"))}</span></div>
      <div class="row"><span class="label">Bot Aktiv</span><span class="val {'val-ok' if bot_enabled else 'val-warn'}">{'Ja' if bot_enabled else 'Nein'}</span></div>
      <div class="row"><span class="label">Status</span><span class="val">{html.escape(str(runner.get("state", "not_configured")))}</span></div>
      {mode_note}
    </div>

    <div class="card">
      <div class="card-head">Headless Runner (24/7)</div>
      <div class="row"><span class="label">Scan-Zyklen</span><span class="val">{runner.get("cycle_count", 0)}</span></div>
      <div class="row"><span class="label">Letzter Zyklus</span><span class="val">{cycle_age_str}</span></div>
      <div class="row"><span class="label">Pausiert</span><span class="val">{paused_display}</span></div>
      <div class="row"><span class="label">Restarts (24h)</span><span class="val">{restarts_24h}</span></div>
      <div class="row"><span class="label">Crashes</span><span class="val {'val-err' if runner.get('crash_loop_detected') else ('val-warn' if runner.get('runner_crash_count', 0) > 0 else 'val')}">{runner.get('runner_crash_count', 0)}{' (CRASH-LOOP)' if runner.get('crash_loop_detected') else ''}</span></div>
    </div>

    <div class="card">
      <div class="card-head">Schatten-Kollektor (OOS)</div>
      <div class="row"><span class="label">Status</span><span class="val {'val-ok' if shadow.get('enabled') else 'val-warn'}">{'Aktiviert' if shadow.get('enabled') else 'Deaktiviert'}</span></div>
      <div class="row"><span class="label">Beobachtet</span><span class="val">{shadow.get("entries", 0)} Setups</span></div>
      <div class="row"><span class="label">Ausstehend</span><span class="val">{shadow.get("pending_outcomes", 0)}</span></div>
      <div class="row"><span class="label">Evaluiert</span><span class="val">{shadow.get("evaluated", 0)}</span></div>
    </div>

    <div class="card">
      <div class="card-head">Tages-Digest &amp; Benachrichtigung</div>
      <div class="row"><span class="label">Letzter Digest</span><span class="val">{html.escape(str(digest_date))}</span></div>
      <div class="row"><span class="label">Sendezeit</span><span class="val">07:00 UTC</span></div>
      <div class="row"><span class="label">ntfy Push</span><span class="val {'val-ok' if has_ntfy else 'val-warn'}">{'Konfiguriert' if has_ntfy else 'Nicht konfiguriert'}</span></div>
      <div class="row"><span class="label">ntfy URL</span><span class="val" style="font-size:10.5px">{html.escape(masked_ntfy)}</span></div>
    </div>

    <div class="card">
      <div class="card-head">State-Verzeichnis &amp; Disk</div>
      <div class="row"><span class="label">Pfad</span><span class="val" style="font-size:10px">{html.escape(str(state_dir))}</span></div>
      <div class="row"><span class="label">State-Größe</span><span class="val">{state_size_mb:.2f} MB</span></div>
      <div class="row"><span class="label">Freier Speicher</span><span class="val {'val-ok' if free_mb > 500 else 'val-err'}">{free_gb:.2f} GB frei ({free_mb:.0f} MB)</span></div>
      <div class="row"><span class="label">Gesamtspeicher</span><span class="val">{total_gb:.2f} GB</span></div>
    </div>

    <div class="card">
      <div class="card-head">Uptime &amp; Serverzeit</div>
      <div class="row"><span class="label">Uptime</span><span class="val">{html.escape(uptime_str)}</span></div>
      <div class="row"><span class="label">Serverzeit (UTC)</span><span class="val" style="font-size:11px">{html.escape(utc_str)}</span></div>
      <div class="row"><span class="label">Serverzeit (Berlin)</span><span class="val" style="font-size:11px">{html.escape(berlin_str)}</span></div>
    </div>

    <div class="card">
      <div class="card-head">Funnel (24 h)</div>
      <div class="row"><span class="label">Gescannt</span><span class="val">{funnel.get("scanned", 0)}</span></div>
      <div class="row"><span class="label">Radar-Kandidaten</span><span class="val">{funnel.get("radar_passed", 0)}</span></div>
      <div class="row"><span class="label">WF-Evaluiert</span><span class="val">{funnel.get("wf_evaluated", 0)}</span></div>
      <div class="row"><span class="label">Ausgewählt (Trades)</span><span class="val">{funnel.get("selected", 0)}</span></div>
    </div>
  </div>

  <footer>
    <div class="doctor-hint">
      Diagnose-Befehl in der Docker-VM: <span class="doctor-cmd">scripts/ops/aura_doctor.sh</span>
    </div>
    <div>
      AURA v{html.escape(VERSION)} · Confluence Terminal (read-only research) · VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE
    </div>
  </footer>
</div>
</body>
</html>
"""

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
        elif path == "/data/bitget_usdt_futures_universe.json" or path == "/api/universe":
            universe_file = Path(
                os.environ.get("AURA_UNIVERSE_PATH")
                or (Path(__file__).resolve().parent / "data" / "bitget_usdt_futures_universe.json")
            )
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
        elif path == "/status":
            html_content = render_status_html()
            self._send_html(html_content.encode("utf-8"))
        elif path == "/ready":
            readiness = market_data_readiness()
            # PF-69: include runner health (last cycle age)
            runner_health = _runner_health()
            bot_enabled = (os.environ.get("AURA_BOT_MODE", "").strip().lower() == "server")
            shadow_health = _shadow_health()
            funnel_health = _funnel_health()
            self._send_json({
                **readiness,
                "bot_enabled": bot_enabled,
                "mode": "server" if bot_enabled else "none",
                "runner": runner_health,
                "shadow": shadow_health,
                "funnel24h": funnel_health,
            }, 200 if readiness["ok"] else 503)
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
            if "signal_claim" in payload:
                claim = payload.get("signal_claim")
                key = claim.get("key") if isinstance(claim, dict) else None
                claimed, rev, claim_error = _claim_signal_event(key)
                if claim_error is not None:
                    self._send_json({"code": "ERR_SIGNAL_CLAIM", "msg": "signal claim could not be persisted"}, 400, cors_headers=self._privileged_cors_headers())
                    return
                self._send_json({"ok": True, "claimed": claimed, "rev": rev}, cors_headers=self._privileged_cors_headers())
                return
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

        if path == "/api/signals":
            # PF-68: Server-Bot signal emission — relay-side ntfy push.
            # Runner has already claimed the event via /api/state signal_claim.
            # This endpoint just performs the actual ntfy push so the runner
            # never needs AURA_NTFY_URL in its own environment.
            title    = str(payload.get("title", "AURA · Signal")).strip()[:128]
            body     = str(payload.get("body", "")).strip()[:1024]
            priority = int(payload.get("priority", 3))
            if not body:
                self._send_json({"code": "ERR_EMPTY_BODY"}, 400)
                return
            sent = _ntfy_notify(title, body, priority=priority)
            self._send_json({"ok": sent})
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
#  PF-66: Headless Paper-Autobot Runner Process Manager
# ---------------------------------------------------------------------------

def check_unconfigured_bot_startup() -> bool:
    """Warn loudly if bot state history exists but AURA_BOT_MODE is not set to 'server'."""
    mode = os.environ.get("AURA_BOT_MODE", "").strip().lower()
    if mode == "server":
        return False

    has_history = False
    try:
        state = _load_shared_state()
        bot_state = state.get("aura-server-bot-state-v1")
        if isinstance(bot_state, dict):
            if (
                int(bot_state.get("cycle_count", bot_state.get("cycleCount", 0)) or 0) > 0
                or bool(bot_state.get("trades"))
                or bool(bot_state.get("history"))
            ):
                has_history = True
    except Exception:
        pass

    if not has_history:
        health_path = STATE_DIR / "runner_health.json"
        try:
            if health_path.exists():
                hdata = json.loads(health_path.read_text(encoding="utf-8"))
                if (
                    int(hdata.get("cycleCount", hdata.get("cycle_count", 0)) or 0) > 0
                    or int(hdata.get("tradeCount", hdata.get("trade_count", 0)) or 0) > 0
                ):
                    has_history = True
        except Exception:
            pass

    if not has_history:
        return False

    log.error(
        "Bot-State-Historie vorhanden, aber AURA_BOT_MODE nicht gesetzt — "
        "Server-Bot ist DEAKTIVIERT (vermutlich verlorene ENV bei manueller Container-Operation)."
    )
    ntfy_url = os.environ.get("AURA_NTFY_URL", "").strip()
    if ntfy_url:
        _ntfy_notify(
            "AURA Server-Bot deaktiviert",
            "WARNUNG: Bot-State-Historie vorhanden, aber AURA_BOT_MODE ist nicht gesetzt. "
            "Der Server-Bot laeuft nicht! Bitte Container mit korrekter ENV starten.",
            category="warnings",
            priority=3,
        )
    else:
        log.error(
            "AURA_NTFY_URL fehlt ebenfalls — Push-Warnung unmoeglich. "
            "Siehe docs/deployment/SERVER_BOT_GUIDE.md"
        )
    return True


def _start_runner_if_enabled() -> subprocess.Popen | None:
    """Start headless_autobot.js as a managed child process if AURA_BOT_MODE=server."""
    mode = os.environ.get("AURA_BOT_MODE", "").strip().lower()
    if mode != "server":
        return None
    runner_script = Path(__file__).resolve().parent / "headless_autobot.js"
    if not runner_script.exists():
        log.warning("Headless autobot script missing at %s — server bot not started", runner_script)
        return None
    node = shutil.which("node") or os.environ.get("SYM_NODE")
    if not node:
        log.error("Node.js not found in PATH — cannot start headless autobot")
        return None
    env = dict(os.environ)
    env["AURA_BOT_MODE"] = "server"
    env["AURA_RELAY_URL"] = f"http://127.0.0.1:{PORT}"
    try:
        proc = subprocess.Popen(
            [node, str(runner_script)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        log.info("Headless Paper Autobot started (PID %d)", proc.pid)

        # Background thread to log runner output and detect exit
        def _log_runner_output():
            if proc.stdout:
                for line in proc.stdout:
                    log.info("[Runner] %s", line.rstrip())
            try:
                proc.poll()
                RUNNER_MANAGER.handle_child_exit(proc.returncode)
            except Exception:
                pass

        t = threading.Thread(target=_log_runner_output, daemon=True, name="autobot-runner-log")
        t.start()
        return proc
    except Exception as exc:
        log.error("Failed to start headless autobot: %s", exc)
        return None


class RunnerManager:
    """Coordinate runner ownership, fast crash detection, and self-healing without holding locks over I/O."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Any = None
        self._process_started_at: float | None = None
        self._restart_count = 0
        self._restart_timestamps: list[float] = []
        self._recovery_cycle_count: int | None = None
        self._recovery_pending = False
        self._stall_active = False
        self._restart_in_progress = False
        self._last_restart_at: float | None = None
        self._last_dump_at: float = 0.0
        self._crash_count = 0
        self._fast_crash_count = 0
        self._last_crash_at: float | None = None

    def set_process(self, process: Any, *, started_at: float | None = None) -> None:
        with self._lock:
            self._process = process
            self._process_started_at = time.time() if started_at is None else float(started_at)

    def current_process(self) -> Any:
        with self._lock:
            return self._process

    def handle_child_exit(self, returncode: int | None = None, *, now: float | None = None) -> dict:
        """Handle early/unexpected exit of the runner child process with fast-crash detection."""
        current_time = time.time() if now is None else float(now)
        with self._lock:
            if self._restart_in_progress:
                return {"restarted": False, "fast_crash": False}
            started = self._process_started_at if self._process_started_at is not None else current_time
            elapsed = max(0.0, current_time - started)
            is_fast = elapsed < 10.0
            self._crash_count += 1
            self._last_crash_at = current_time
            if is_fast:
                self._fast_crash_count += 1
                log.warning(
                    "RUNNER_CRASH_FAST: Runner process exited with code %s after %.1fs (<10s). Consecutive fast crashes: %d",
                    returncode,
                    elapsed,
                    self._fast_crash_count,
                )
            else:
                self._fast_crash_count = 0
                log.warning(
                    "RUNNER_EXIT: Runner process exited with code %s after %.1fs",
                    returncode,
                    elapsed,
                )
            self._restart_in_progress = True
            old_process = self._process

        if old_process is not None:
            try:
                if hasattr(old_process, "poll") and old_process.poll() is None:
                    old_process.terminate()
                    old_process.wait(timeout=2)
            except Exception:
                pass

        replacement = _start_runner_if_enabled()
        with self._lock:
            self._process = replacement
            self._process_started_at = current_time
            if replacement is not None:
                self._restart_count += 1
                self._restart_timestamps.append(current_time)
                self._last_restart_at = current_time
                self._recovery_pending = True
                log.warning("RUNNER_HEAL: Immediate runner restart #%d executed after child exit", self._restart_count)
            self._restart_in_progress = False
        return {"restarted": replacement is not None, "fast_crash": is_fast}

    def snapshot(self, *, now: float | None = None) -> dict:
        current_time = time.time() if now is None else float(now)
        cutoff = current_time - 86400.0
        with self._lock:
            self._restart_timestamps = [stamp for stamp in self._restart_timestamps if stamp >= cutoff]
            recent = list(self._restart_timestamps)
            return {
                "runner_restart_count": self._restart_count,
                "runner_crash_count": self._crash_count,
                "fast_crash_count": self._fast_crash_count,
                "crash_loop_detected": self._fast_crash_count >= 3,
                "restart_timestamps": recent,
                "restarts_24h": len(recent),
                "recovery_pending": self._recovery_pending or (self._recovery_cycle_count is not None),
            }

    @staticmethod
    def _cycle_count(health: dict) -> int:
        try:
            return int(health.get("cycle_count", health.get("cycleCount", 0)) or 0)
        except (TypeError, ValueError):
            return 0

    def watchdog(self, health: dict, *, now: float | None = None, stale_sec: float | None = None) -> dict:
        current_time = time.time() if now is None else float(now)
        threshold = runner_stale_threshold() if stale_sec is None else float(stale_sec)
        cycle_count = self._cycle_count(health)
        paused = bool(health.get("paused", False))
        if paused:
            check_age = health.get("last_heartbeat_age_sec")
            if check_age is None:
                check_age = health.get("last_cycle_age_sec")
        else:
            check_age = health.get("last_cycle_age_sec")
        stale = check_age is None or not isinstance(check_age, (int, float)) or not math.isfinite(float(check_age)) or float(check_age) > threshold

        with self._lock:
            recovery_cycle = self._recovery_cycle_count
            recovery_needed = self._recovery_pending or (recovery_cycle is not None)
            if recovery_needed and not stale:
                # Require cycle count advance, or a completed cycle in restarted process, or active pause
                cycle_advanced = (recovery_cycle is None) or (cycle_count > recovery_cycle) or (cycle_count > 0 and cycle_count < recovery_cycle)
                if cycle_advanced or paused:
                    self._recovery_cycle_count = None
                    self._recovery_pending = False
                    self._stall_active = False
                    self._fast_crash_count = 0
                    log.info("RUNNER_RECOVERED: Runner healthy after restart (cycle=%d, paused=%s)", cycle_count, paused)
                    return {"restarted": False, "recovered": True}
            if not stale:
                if not recovery_needed:
                    self._stall_active = False
                return {"restarted": False, "recovered": False}
            if self._restart_in_progress:
                return {"restarted": False, "recovered": False}
            # Suppress rapid duplicate restarts within 5s grace window of previous restart
            if self._last_restart_at is not None and (current_time - self._last_restart_at) < 5.0:
                return {"restarted": False, "recovered": False}
            needs_dump = not self._stall_active or (current_time - self._last_dump_at) > 300.0
            self._stall_active = True
            self._restart_in_progress = True
            old_process = self._process

        if needs_dump:
            self._last_dump_at = current_time
            log.error("RUNNER_STALL_STACK_DUMP: runner cycle stale; dumping all relay threads")
            try:
                sys.stderr.flush()
                faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
                sys.stderr.flush()
            except Exception:
                log.exception("RUNNER_STALL_STACK_DUMP_FAILED")

        if old_process is not None:
            try:
                old_process.terminate()
                old_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                old_process.kill()
                try:
                    old_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log.error("Runner did not exit after terminate and kill timeouts")
            except Exception:
                log.exception("Controlled runner stop failed")

        replacement = _start_runner_if_enabled()
        with self._lock:
            self._process = replacement
            if replacement is not None:
                self._restart_count += 1
                self._restart_timestamps.append(current_time)
                self._last_restart_at = current_time
                self._recovery_cycle_count = cycle_count
                self._recovery_pending = True
                log.warning("RUNNER_HEAL: Runner restart #%d executed (staleness detected)", self._restart_count)
            self._restart_in_progress = False
        return {"restarted": replacement is not None, "recovered": False}

    def stop(self) -> None:
        process = self.current_process()
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.error("Runner shutdown exceeded terminate and kill timeouts")


RUNNER_MANAGER = RunnerManager()


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

class RelayServer(ThreadingHTTPServer):
    """Threaded HTTP server with a larger accept backlog for concurrent clients."""
    request_queue_size = 128


if __name__ == "__main__":
    check_unconfigured_bot_startup()
    signal_stop = threading.Event()
    RUNNER_MANAGER.set_process(_start_runner_if_enabled())
    signal_thread = threading.Thread(
        target=_signal_center_loop,
        args=(signal_stop,),
        daemon=True,
        name="aura-signal-center",
    )
    signal_thread.start()
    server = RelayServer((HOST, PORT), RelayHandler)
    log.info("AURA Relay v%s listening on http://%s:%d", VERSION, HOST, PORT)
    log.info("Modus: Quant Research & Signal Analysis (Read-Only CORS Proxy + Cross-Device Sync)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Relay gestoppt.")
    finally:
        signal_stop.set()
        if RUNNER_MANAGER.current_process() is not None:
            log.info("Terminating headless autobot runner...")
            RUNNER_MANAGER.stop()
