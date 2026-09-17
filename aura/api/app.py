"""FastAPI Anwendungs-Fabrik fuer AURA v3 (aura.api.app).

Kombiniert API v3, Legacy-Kompatibilitaet, Security-Middleware und Web-Dashboard.
Dokumentiert in docs/ARCHITECTURE.md und docs/SECURITY.md.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from aura import __version__ as _AURA_VERSION
from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from aura.api.auth import SecurityHeadersMiddleware, get_configured_token, verify_auth_token
from aura.api.routes import router as v3_router, set_api_state
from aura.runner.paper_engine import PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.store.db import connect

logger = logging.getLogger("aura.api")


PUBLIC_ALLOWED_PREFIXES = (
    "/api/v2/mix/market/candles",
    "/api/v2/mix/market/ticker",
    "/api/v2/mix/market/tickers",
    "/api/v2/mix/market/contracts",
    "/api/v2/mix/market/history-fund-rate",
    "/api/v2/mix/market/open-interest",
)


class PublicMarketCache:
    def __init__(self):
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def get_ttl(self, path: str) -> float:
        p = path.lower()
        if "candle" in p or "kline" in p:
            return 15.0
        if "ticker" in p:
            return 3.0
        if "contract" in p or "history-fund-rate" in p or "open-interest" in p:
            return 10.0
        return 5.0

    def get(self, key: tuple) -> dict | None:
        now = time.monotonic()
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            exp, val = item
            if now < exp:
                return val
            del self._cache[key]
            return None

    def set(self, key: tuple, val: dict, ttl: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._cache[key] = (now + ttl, val)


_PUBLIC_CACHE = PublicMarketCache()

_MAX_PARAM_KEY_LEN = 64
_MAX_PARAM_VAL_LEN = 128
_MAX_PARAMS_COUNT = 12


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Verhindert, dass urllib automatisch Redirects folgt (SSRF-Schutz)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, f"Redirect verweigert: {newurl}", headers, fp)


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def create_app(
    db_path: str | Path | None = None,
    conn: sqlite3.Connection | None = None,
    state_machine: RunnerStateMachine | None = None,
    paper_engine: PaperTradingEngine | None = None,
) -> FastAPI:
    """Erstellt und konfiguriert die AURA v3 FastAPI Anwendung."""
    app = FastAPI(
        title="AURA Quant Terminal API",
        version="3.0.0-dev",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 1. DB & State initialisieren
    actual_db_path = str(db_path) if db_path else os.environ.get("AURA_DB_PATH", "aura_state.db")
    if conn is None:
        conn = connect(actual_db_path)
    else:
        try:
            row = conn.execute("PRAGMA database_list").fetchone()
            if row and len(row) > 2 and row[2]:
                actual_db_path = str(row[2])
        except Exception:
            pass

    sm = state_machine or RunnerStateMachine()
    pe = paper_engine or PaperTradingEngine(conn=conn)
    set_api_state(sm, pe, db_conn=conn, db_path=actual_db_path)

    # 2. Middlewares
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. API v3 Routen
    app.include_router(v3_router, prefix="/api/v3", tags=["v3"])

    # 4. Legacy-Kompatibilitaets-Routen fuer bestehende Dashboards & Tools
    @app.get("/api/state")
    def legacy_get_state():
        cur = conn.cursor()
        cur.execute("SELECT payload FROM config_revisions ORDER BY rev DESC LIMIT 1")
        row = cur.fetchone()
        cfg = json.loads(row["payload"]) if row else {}

        active_trades = [
            {
                "tradeId": p.trade_id,
                "symbol": p.symbol,
                "dir": p.direction,
                "entryPrice": p.entry_price,
                "sl": p.sl_price,
                "tp1": p.tp1_price,
                "tp2": p.tp2_price,
                "qty": p.qty,
                "margin": p.margin,
                "leverage": p.leverage,
                "openedAt": p.entry_time_ms,
                "status": p.status,
                "tp1Hit": p.tp1_hit,
                "realizedPnl": p.realized_pnl,
                "unrealizedPnl": p.unrealized_pnl,
            }
            for p in pe.open_positions.values()
        ]

        return {
            "version": 3,
            "equity": pe.equity,
            "startingEquity": pe.starting_equity,
            "autobotState": {
                "active": not sm.is_halted,
                "state": sm.current_state.value,
                "trades": active_trades,
                "config": cfg,
            },
        }

    @app.get("/api/universe")
    def get_cached_universe():
        universe_file = Path(__file__).parent.parent.parent / "data" / "bitget_usdt_futures_universe.json"
        if universe_file.exists():
            return JSONResponse(content=json.loads(universe_file.read_text(encoding="utf-8")))
        return {"total_contracts": 0, "contracts": []}

    @app.post("/api/public")
    async def proxy_public_market(payload: dict = Body(...)):
        """Öffentlicher Marktdaten-Proxy für Bitget-REST-Endpunkte.

        Nur explizit freigegebene öffentliche /api/v2/mix/market/-Pfade sind erlaubt.
        Keine Auth-Daten, keine Cookies werden an den Upstream weitergereicht.
        Redirects sind deaktiviert (SSRF-Schutz via _NoRedirectHandler).
        _PUBLIC_CACHE puffert Antworten; dies dient der Lastreduzierung,
        nicht als Ratenbegrenzung – für Ratenbegrenzung ist ein dediziertes
        Rate-Limiting-Layer erforderlich.
        """
        raw_path = payload.get("path") or payload.get("url", "")
        if not isinstance(raw_path, str) or not raw_path.startswith("/api/v2/mix/market/") or "://" in raw_path:
            raise HTTPException(status_code=400, detail="Pfad unzulaessig oder nicht in der Allowlist")

        base_path, _, qs = raw_path.partition("?")
        if not any(base_path.startswith(prefix) for prefix in PUBLIC_ALLOWED_PREFIXES):
            raise HTTPException(status_code=400, detail="Endpunkt nicht erlaubt")

        # Merge params; enforce key/value length and count limits (R2)
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        merged: dict[str, str] = {}
        for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True):
            k_s, v_s = str(k)[:_MAX_PARAM_KEY_LEN], str(v)[:_MAX_PARAM_VAL_LEN]
            merged.setdefault(k_s, v_s)
        for k, v in params.items():
            k_s, v_s = str(k)[:_MAX_PARAM_KEY_LEN], str(v)[:_MAX_PARAM_VAL_LEN]
            merged.setdefault(k_s, v_s)
        if len(merged) > _MAX_PARAMS_COUNT:
            raise HTTPException(status_code=400, detail="Zu viele Query-Parameter")

        cache_key = (base_path, tuple(sorted(merged.items())))
        cached = _PUBLIC_CACHE.get(cache_key)
        if cached is not None:
            return cached

        query_str = urllib.parse.urlencode(merged)
        target_url = f"https://api.bitget.com{base_path}"
        if query_str:
            target_url += f"?{query_str}"

        req = urllib.request.Request(
            target_url,
            headers={"User-Agent": "AURA-Quant-Terminal/3.0"},
        )
        try:
            # R1: _NO_REDIRECT_OPENER verweigert HTTP-Redirects (SSRF-Schutz)
            with _NO_REDIRECT_OPENER.open(req, timeout=8.0) as resp:
                body = json.loads(resp.read(256 * 1024).decode("utf-8"))
                if body.get("code") == "00000":
                    _PUBLIC_CACHE.set(cache_key, body, _PUBLIC_CACHE.get_ttl(base_path))
                return body
        except urllib.error.HTTPError as ex:
            raise HTTPException(status_code=ex.code, detail=f"Bitget Upstream HTTP {ex.code}")
        except Exception as ex:
            raise HTTPException(status_code=502, detail=f"Bitget Upstream Fehler: {str(ex)}")

    @app.get("/serving")
    def get_serving():
        """Liefert die serverseitige Backend-Version für den Client-Reload-Banner.

        Das Dashboard zeigt einen Reload-Hinweis wenn AURA_CLIENT_VERSION
        (im HTML hardcodiert) von dieser Version abweicht.
        Die Version stammt aus aura.__version__ (single source of truth).
        """
        return {"ok": True, "version": _AURA_VERSION}

    # ---------------------------------------------------------------------------
    # Hilfsfunktion: Worker-Zustand autoritativ aus DB lesen
    # ---------------------------------------------------------------------------
    _WORKER_ACTIVE_STATES = frozenset({"RUNNING", "WARMING_UP", "RECOVERING"})
    _STALE_THRESHOLD_S = 120.0

    def _read_worker_status_from_db() -> dict:
        """Liest runner_state aus DB. Kein Auth nötig, kein Portfolio-Zustand.

        Semantik der Felder:
          fsm_state      — letzter persistierter Zustand des Workers
          is_halted      — Worker ist im Not-Halt (Einstiege gesperrt)
          entries_locked — Entry-Gate geschlossen (HALTED, STARTING, veraltete Daten oder kein Eintrag)
          stale          — letzter Heartbeat > _STALE_THRESHOLD_S Sekunden alt
          worker_known   — ob ein runner_state-Eintrag in der DB existiert
          reason         — Halt-Grund (nur gesetzt wenn HALTED)
          data_age_seconds — Sekunden seit letztem Heartbeat (None wenn kein Eintrag)
        """
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT fsm_state, reason, updated_at_ms FROM runner_state WHERE id = 1"
            )
            row = cur.fetchone()
        except Exception as ex:
            logger.warning("runner_state DB-Lesefehler: %s", ex)
            row = None

        now_ms = int(time.time() * 1000)

        if row is None:
            # Kein Eintrag: fail-closed — keine Entry-Freigabe ohne verifizierten Zustand
            return {
                "fsm_state": "UNKNOWN",
                "is_halted": False,
                "entries_locked": True,
                "stale": True,
                "worker_known": False,
                "reason": None,
                "data_age_seconds": None,
            }

        fsm_state = row[0] if isinstance(row, (tuple, list)) else row["fsm_state"]
        reason = row[1] if isinstance(row, (tuple, list)) else row["reason"]
        updated_ms = row[2] if isinstance(row, (tuple, list)) else row["updated_at_ms"]

        age_s = round((now_ms - (updated_ms or 0)) / 1000.0, 1) if updated_ms else None
        stale = (age_s is None) or (age_s > _STALE_THRESHOLD_S)
        is_halted = (fsm_state == "HALTED")
        # Entry-Gate: nur freigeben wenn RUNNING/WARMING_UP/RECOVERING UND frisch
        entries_locked = is_halted or stale or (fsm_state not in _WORKER_ACTIVE_STATES)

        return {
            "fsm_state": fsm_state,
            "is_halted": is_halted,
            "entries_locked": entries_locked,
            "stale": stale,
            "worker_known": True,
            "reason": reason if is_halted else None,
            "data_age_seconds": age_s,
        }

    @app.get("/status/worker")
    def get_worker_status():
        """Öffentlicher Worker-Zustandsendpunkt — kein Auth erforderlich.

        Liefert ausschließlich den persistierten Worker-Zustand aus der DB.
        Kein Portfolio, keine Trades, keine Konfiguration, keine Equitydaten.
        Datenquelle: runner_state (id=1), die der Worker bei jedem Heartbeat schreibt.

        Verbraucher:
          - Dashboard (anonyme Statusanzeige im Autobot-Panel)
          - fetchReadyFunnel() (bot_enabled-Flag)
          - Externe Monitoring-Tools
        """
        return _read_worker_status_from_db()

    @app.get("/ready")
    def get_ready():
        """Health-Probe für Orchestratoren und Dashboard-Startup-Checks.

        Liest den Worker-Zustand direkt aus der DB (runner_state),
        nicht aus der In-Memory-SM des API-Prozesses.

        bot_enabled=True nur wenn Worker RUNNING/WARMING_UP/RECOVERING UND frischer Heartbeat.
        STARTING, HALTED, fehlender oder veralteter Eintrag → bot_enabled=False (fail-closed).
        """
        ws = _read_worker_status_from_db()
        return {
            "ok": True,
            "mode": "server",
            "bot_enabled": not ws["entries_locked"],
            "is_halted": ws["is_halted"],
            "worker_known": ws["worker_known"],
            "stale": ws["stale"],
            "system_state": ws["fsm_state"],
            "data_age_seconds": ws["data_age_seconds"],
        }

    @app.get("/pine", response_class=PlainTextResponse)
    @app.get("/Symbiose_Signal_System_v1.pine", response_class=PlainTextResponse)
    def serve_pine_script():
        """Liefert das Pine-Skript für TradingView-Bridge im Dashboard.

        Verbraucher: Symbiose_Dashboard.html Zeile ~3837 (loadPineScript).
        Gibt 404 zurück wenn die Datei nicht im Projektroot liegt –
        das Dashboard behandelt diesen Fall bereits als nicht-kritisch.
        """
        pine_file = Path(__file__).parent.parent.parent / "Symbiose_Signal_System_v1.pine"
        if pine_file.exists():
            return PlainTextResponse(content=pine_file.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="Pine script not found")

    @app.get("/data/bitget_usdt_futures_universe.json", response_class=JSONResponse)
    def serve_universe_json():
        u_file = Path(__file__).parent.parent.parent / "data" / "bitget_usdt_futures_universe.json"
        if u_file.exists():
            return JSONResponse(content=json.loads(u_file.read_text(encoding="utf-8")))
        raise HTTPException(status_code=404, detail="Universe file not found")

    @app.get("/", response_class=HTMLResponse)
    def serve_dashboard():
        """Liefert das reaktive AURA Dashboard aus."""
        dash_path = Path(__file__).parent.parent.parent / "Symbiose_Dashboard.html"
        if dash_path.exists():
            return HTMLResponse(content=dash_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>AURA v3 Running</h1>")

    return app


# Standard-ASGI-Instanz fuer Uvicorn/Gunicorn
app = create_app()
