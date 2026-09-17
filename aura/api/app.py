"""FastAPI Anwendungs-Fabrik fuer AURA v3 (aura.api.app).

Kombiniert API v3, Legacy-Kompatibilitaet, Security-Middleware und Web-Dashboard.
Dokumentiert in docs/ARCHITECTURE.md und docs/SECURITY.md.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aura.api.auth import SecurityHeadersMiddleware, get_configured_token, verify_auth_token
from aura.api.routes import router as v3_router, set_api_state
from aura.runner.paper_engine import PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine
from aura.store.db import connect

logger = logging.getLogger("aura.api")


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
    if conn is None:
        actual_db_path = db_path or os.environ.get("AURA_DB_PATH", "aura_state.db")
        conn = connect(actual_db_path)

    sm = state_machine or RunnerStateMachine()
    pe = paper_engine or PaperTradingEngine(conn=conn)
    set_api_state(sm, pe, conn)

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
