"""API Routen fuer AURA v3 (aura.api.routes).

Dokumentiert in docs/ARCHITECTURE.md §6 und docs/SECURITY.md.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
import uuid
from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from aura.api.auth import (
    SESSION_COOKIE_NAME,
    check_login_rate_limit,
    clear_failed_logins,
    create_session,
    destroy_session,
    get_configured_token,
    is_valid_session,
    record_failed_login,
    verify_auth_token,
)
from aura.api.schemas import (
    AuthStatusResponse,
    BotConfigUpdate,
    CloseTradeRequest,
    GenericResponse,
    HaltRequest,
    HealthResponse,
    LoginRequest,
    ResumeRequest,
)
from aura.runner.paper_engine import PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.data.liquidity import POLICY_VERSION
from aura.store.db import connect

router = APIRouter()

# Globale Instanzen fuer den API-Prozess (werden bei create_app initialisiert)
_state_machine: RunnerStateMachine | None = None
_paper_engine: PaperTradingEngine | None = None
_db_conn: sqlite3.Connection | None = None
_db_path: str | None = None
_start_time = time.time()


def set_api_state(
    state_machine: RunnerStateMachine,
    paper_engine: PaperTradingEngine,
    db_conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> None:
    global _state_machine, _paper_engine, _db_conn, _db_path
    _state_machine = state_machine
    _paper_engine = paper_engine
    _db_conn = db_conn
    if db_path is not None:
        _db_path = str(db_path)
    elif db_conn is not None:
        try:
            row = db_conn.execute("PRAGMA database_list").fetchone()
            if row and len(row) > 2 and row[2]:
                _db_path = str(row[2])
            else:
                _db_path = None
        except Exception:
            _db_path = None
    else:
        _db_path = None


def get_state_machine() -> RunnerStateMachine:
    if _state_machine is None:
        raise HTTPException(status_code=500, detail="State Machine nicht initialisiert")
    return _state_machine


def get_paper_engine() -> PaperTradingEngine:
    if _paper_engine is None:
        raise HTTPException(status_code=500, detail="Paper Engine nicht initialisiert")
    _paper_engine._load_state_from_db_if_available()
    return _paper_engine


def get_db() -> Generator[sqlite3.Connection, None, None]:
    if _db_path is not None:
        conn = connect(_db_path)
        try:
            yield conn
        finally:
            conn.close()
    elif _db_conn is not None:
        yield _db_conn
    else:
        raise HTTPException(status_code=500, detail="Datenbank nicht initialisiert")


def _enqueue_command(db: sqlite3.Connection, command_type: str, payload: dict[str, Any]) -> str:
    command_id = f"cmd_{uuid.uuid4().hex}"
    with db:
        db.execute(
            "INSERT INTO commands (id, type, payload, status, created_at_ms) VALUES (?, ?, ?, 'pending', ?)",
            (command_id, command_type, json.dumps(payload), int(time.time() * 1000)),
        )
    return command_id


@router.post("/auth/login", response_model=GenericResponse)
def login_operator(payload: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "127.0.0.1"
    check_login_rate_limit(client_ip)

    configured = get_configured_token()
    if not secrets.compare_digest(payload.token.strip(), configured):
        record_failed_login(client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert: Ungueltiger Authentifizierungs-Token",
        )
    clear_failed_logins(client_ip)

    session_id = create_session()
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=is_https,
    )
    return GenericResponse(
        ok=True,
        message="Anmeldung erfolgreich",
        data={"authenticated": True, "role": "operator"},
    )


@router.post("/auth/logout", response_model=GenericResponse)
def logout_operator(request: Request, response: Response):
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    destroy_session(session_cookie)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return GenericResponse(
        ok=True,
        message="Erfolgreich abgemeldet",
        data={"authenticated": False, "role": "anonymous"},
    )


@router.get("/auth/status", response_model=AuthStatusResponse)
def get_auth_status(request: Request):
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if is_valid_session(session_cookie):
        return AuthStatusResponse(ok=True, authenticated=True, role="operator")

    auth_header = request.headers.get("Authorization")
    x_token = request.headers.get("X-AURA-TOKEN")
    configured = get_configured_token()
    token_to_check = None
    if x_token:
        token_to_check = x_token.strip()
    elif auth_header and auth_header.startswith("Bearer "):
        token_to_check = auth_header.split("Bearer ", 1)[1].strip()

    if token_to_check and secrets.compare_digest(token_to_check, configured):
        return AuthStatusResponse(ok=True, authenticated=True, role="operator")

    return AuthStatusResponse(ok=True, authenticated=False, role="anonymous")


@router.get("/health", response_model=HealthResponse)
def get_health(sm: RunnerStateMachine = Depends(get_state_machine), pe: PaperTradingEngine = Depends(get_paper_engine)):
    state = sm.current_state
    health_status = "healthy"
    if sm.is_halted:
        health_status = "halted"
    elif state == SystemState.DEGRADED:
        health_status = "degraded"
    elif state == SystemState.STARTING:
        health_status = "starting"

    return HealthResponse(
        status=health_status,
        system_state=state.value,
        data_fresh=True,
        active_trades=len(pe.open_positions),
        uptime_seconds=round(time.time() - _start_time, 2),
        timestamp_ms=int(time.time() * 1000),
    )


@router.get("/status")
def get_status(sm: RunnerStateMachine = Depends(get_state_machine), pe: PaperTradingEngine = Depends(get_paper_engine)):
    return {
        "status": sm.get_status(active_count=len(pe.open_positions)),
        "equity": pe.equity,
        "open_positions": len(pe.open_positions),
    }


@router.get("/state")
def get_state(
    sm: RunnerStateMachine = Depends(get_state_machine),
    pe: PaperTradingEngine = Depends(get_paper_engine),
    db: sqlite3.Connection = Depends(get_db),
    _token: str = Depends(verify_auth_token),
):
    # 1. Lade aktive Config-Revision
    cur = db.cursor()
    cur.execute("SELECT payload, rev, applied_at_ms FROM config_revisions ORDER BY rev DESC LIMIT 1")
    cfg_row = cur.fetchone()
    bot_cfg = json.loads(cfg_row["payload"]) if cfg_row else {}
    requested_rev = cfg_row["rev"] if cfg_row else None
    cur.execute(
        "SELECT rev FROM config_revisions WHERE applied_at_ms IS NOT NULL ORDER BY rev DESC LIMIT 1"
    )
    active_row = cur.fetchone()
    active_rev = active_row["rev"] if active_row else None

    # 2. Lade Worker-Zustand aus runner_state
    cur.execute("SELECT fsm_state, reason, equity, cycle_count, updated_at_ms FROM runner_state WHERE id = 1")
    runner_row = cur.fetchone()
    now_ms = int(time.time() * 1000)

    if runner_row:
        worker_status = runner_row["fsm_state"]
        worker_reason = runner_row["reason"]
        worker_cycle = runner_row["cycle_count"]
        last_hb_ms = runner_row["updated_at_ms"]
        data_age_sec = round(max(0.0, (now_ms - last_hb_ms) / 1000.0), 1)
        is_stale = data_age_sec > 120.0
    else:
        worker_status = sm.current_state.value
        worker_reason = sm.reason
        worker_cycle = 0
        last_hb_ms = None
        data_age_sec = None
        is_stale = True

    # 3. Offene Positionen serialisieren
    open_list = [
        {
            "id": p.trade_id,
            "symbol": p.symbol,
            "dir": p.direction,
            "entry_price": p.entry_price,
            "sl_price": p.sl_price,
            "initial_sl_price": p.initial_sl_price,
            "tp1_price": p.tp1_price,
            "tp2_price": p.tp2_price,
            "qty": p.qty,
            "initial_qty": p.initial_qty,
            "margin": p.margin,
            "leverage": p.leverage,
            "opened_at_ms": p.entry_time_ms,
            "timeframe": p.timeframe,
            "status": p.status,
            "tp1_hit": p.tp1_hit,
            "realized_pnl": p.realized_pnl,
            "unrealized_pnl": p.unrealized_pnl,
            "fees": p.total_fees,
            "setup_score": p.setup_score,
            "notes": p.notes,
        }
        for p in pe.open_positions.values()
    ]

    # 4. Geschlossene Positionen serialisieren
    closed_list = [
        {
            "id": p.trade_id,
            "symbol": p.symbol,
            "dir": p.direction,
            "entry_price": p.entry_price,
            "exit_price": p.exit_price,
            "exit_reason": p.exit_reason,
            "realized_pnl": p.realized_pnl,
            "fees": p.total_fees,
            "opened_at_ms": p.entry_time_ms,
            "closed_at_ms": p.exit_time_ms,
            "status": p.status,
            "r_multiple": p.r_multiple,
        }
        for p in pe.closed_positions
    ]

    # 5. Pending Commands & Recent Rejected Commands
    cur.execute("SELECT id, type, status, created_at_ms FROM commands WHERE status = 'pending' ORDER BY created_at_ms")
    pending_cmds = [
        {
            "id": r["id"],
            "type": r["type"],
            "status": r["status"],
            "created_at_ms": r["created_at_ms"],
        }
        for r in cur.fetchall()
    ]

    cur.execute("SELECT id, type, result, applied_at_ms FROM commands WHERE status = 'rejected' ORDER BY id DESC LIMIT 5")
    rejected_cmds = [
        {
            "id": r["id"],
            "type": r["type"],
            "result": r["result"],
            "applied_at_ms": r["applied_at_ms"],
        }
        for r in cur.fetchall()
    ]

    # 6. Shadow Log (Radar / Gate Rejections)
    cur.execute("SELECT ts_ms, symbol, dir, score, decision, reject_reason FROM shadow_log ORDER BY ts_ms DESC, id DESC LIMIT 25")
    radar_rows = [
        {
            "ts_ms": r["ts_ms"],
            "symbol": r["symbol"],
            "dir": r["dir"],
            "score": r["score"],
            "decision": r["decision"],
            "reason": r["reject_reason"],
        }
        for r in cur.fetchall()
    ]

    # Performance Metriken
    total_realized = sum(p.realized_pnl for p in pe.closed_positions)
    total_unrealized = sum(p.unrealized_pnl for p in pe.open_positions.values())
    roi_pct = round(((pe.equity - pe.starting_equity) / pe.starting_equity) * 100.0, 2) if pe.starting_equity > 0 else 0.0
    wins = [p for p in pe.closed_positions if p.realized_pnl > 0]
    win_rate = round((len(wins) / len(pe.closed_positions)) * 100.0, 1) if pe.closed_positions else 0.0

    # 7. Market Data & Explanatory Liquidity State
    cur.execute(
        "SELECT symbol, active, liquidity_verified, vol_24h, updated_at_ms, source, status, "
        "policy_version, event_time_ms, fetched_at_ms, reasons_json, spread_bps, "
        "bid_depth_notional, ask_depth_notional, quote_volume_24h, raw_snapshot_sha256 "
        "FROM universe ORDER BY symbol"
    )
    u_rows = cur.fetchall()
    market_symbols = []
    primary_source = "bitget_rest_v2"
    primary_policy = POLICY_VERSION
    overall_status = "loading" if not u_rows else ("valid" if any(r["liquidity_verified"] for r in u_rows) else "insufficient")
    for r in u_rows:
        keys = r.keys()
        sym_src = r["source"] if "source" in keys and r["source"] else "bitget_rest_v2"
        sym_pol = r["policy_version"] if "policy_version" in keys and r["policy_version"] else POLICY_VERSION
        primary_source = sym_src
        primary_policy = sym_pol
        reasons = json.loads(r["reasons_json"]) if "reasons_json" in keys and r["reasons_json"] else []
        status_val = r["status"] if "status" in keys and r["status"] else ("valid" if r["liquidity_verified"] else "unverified")
        f_ms = r["fetched_at_ms"] if "fetched_at_ms" in keys else None
        age_sec = round((now_ms - f_ms) / 1000.0, 1) if f_ms else None
        if age_sec is not None and age_sec > 900.0 and status_val == "valid":
            status_val = "stale"
        market_symbols.append({
            "symbol": r["symbol"],
            "status": status_val,
            "verified": bool(r["liquidity_verified"]),
            "data_age_seconds": age_sec,
            "reasons": reasons,
            "criteria": {
                "spread_bps": str(r["spread_bps"]) if "spread_bps" in keys and r["spread_bps"] is not None else None,
                "bid_depth_notional": str(r["bid_depth_notional"]) if "bid_depth_notional" in keys and r["bid_depth_notional"] is not None else None,
                "ask_depth_notional": str(r["ask_depth_notional"]) if "ask_depth_notional" in keys and r["ask_depth_notional"] is not None else None,
                "quote_volume_24h": str(r["quote_volume_24h"]) if "quote_volume_24h" in keys and r["quote_volume_24h"] is not None else (str(r["vol_24h"]) if r["vol_24h"] is not None else None),
            },
        })

    if u_rows:
        if all(s["status"] == "source_failed" for s in market_symbols):
            overall_status = "source_failed"
        elif any(s["status"] == "valid" for s in market_symbols):
            overall_status = "valid"
        elif any(s["status"] == "stale" for s in market_symbols):
            overall_status = "stale"
        elif any(s["status"] == "insufficient" for s in market_symbols):
            overall_status = "insufficient"
        else:
            overall_status = market_symbols[0]["status"]

    return {
        "server_time_ms": now_ms,
        "worker": {
            "status": worker_status,
            "is_halted": worker_status == "HALTED",
            "reason": worker_reason,
            "cycle_count": worker_cycle,
            "last_heartbeat_ms": last_hb_ms,
            "data_age_seconds": data_age_sec,
            "is_stale": is_stale,
        },
        "market_data": {
            "source": primary_source,
            "policy_version": primary_policy,
            "status": overall_status,
            "symbols": market_symbols,
        },
        "equity": pe.equity,
        "starting_equity": pe.starting_equity,
        "realized_pnl": total_realized,
        "unrealized_pnl": total_unrealized,
        "roi_pct": roi_pct,
        "win_rate_pct": win_rate,
        "total_closed_trades": len(pe.closed_positions),
        "open_positions": open_list,
        "closed_trades": closed_list,
        "config": bot_cfg,
        "config_rev": active_rev,
        "requested_config_rev": requested_rev,
        "active_config_rev": active_rev,
        "pending_commands": pending_cmds,
        "rejected_commands": rejected_cmds,
        "radar": radar_rows,
        "model_status": "MODEL_NO_EVIDENCE",
        "missing_costs_notice": "Hinweis: 8h-Funding und TP3-Tranchen sind in dieser v3-Version noch nicht modelliert. Status: MODEL_NO_EVIDENCE.",
    }


@router.post("/config", response_model=GenericResponse)
def update_config(
    payload: BotConfigUpdate,
    _token: str = Depends(verify_auth_token),
    db: sqlite3.Connection = Depends(get_db),
    pe: PaperTradingEngine = Depends(get_paper_engine),
):
    """Aktualisiert die Bot-Konfiguration transaktional und inkrementiert die Revision."""
    cur = db.cursor()
    cur.execute(
        "SELECT rev FROM config_revisions WHERE applied_at_ms IS NOT NULL ORDER BY rev DESC LIMIT 1"
    )
    active_row = cur.fetchone()
    current_active_rev = active_row["rev"] if active_row else 0

    # Optimistic locking check against expected_rev
    if payload.expected_rev is not None and payload.expected_rev != current_active_rev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Konfigurationskonflikt: Revision {current_active_rev} ist aktiv, erwartet wurde {payload.expected_rev}. Bitte Konfiguration neu laden.",
        )

    cfg_dict = payload.model_dump(exclude={"expected_rev"})
    cfg_json = json.dumps(cfg_dict)
    now_ms = int(time.time() * 1000)

    # Requested revision remains pending until the worker acknowledges it.
    with db:
        cur = db.execute(
            "INSERT INTO config_revisions (payload, source, created_at_ms, applied_at_ms) "
            "VALUES (?, ?, ?, NULL)",
            (cfg_json, "operator", now_ms),
        )
        next_rev = cur.lastrowid or 1
        command_id = f"cmd_{uuid.uuid4().hex}"
        db.execute(
            "INSERT INTO commands (id, type, payload, status, created_at_ms) VALUES (?, 'set_config', ?, 'pending', ?)",
            (command_id, json.dumps({"rev": next_rev, "config": cfg_dict}), now_ms),
        )

    return GenericResponse(
        ok=True,
        message=f"Konfiguration als Revision {next_rev} angefordert",
        data={
            "requested_rev": next_rev,
            "active_rev": current_active_rev,
            "command_id": command_id,
            "status": "pending",
            "config": cfg_dict,
        },
    )


@router.post("/halt", response_model=GenericResponse)
def trigger_emergency_halt(
    payload: HaltRequest,
    _token: str = Depends(verify_auth_token),
    sm: RunnerStateMachine = Depends(get_state_machine),
    db: sqlite3.Connection = Depends(get_db),
):
    command_id = _enqueue_command(db, "halt", payload.model_dump())
    sm.emergency_halt(reason=payload.reason)
    return GenericResponse(
        ok=True,
        message=f"Not-Halt angefordert: {payload.reason}",
        data={"command_id": command_id, "status": "pending"},
    )


@router.post("/resume", response_model=GenericResponse)
def resume_from_emergency_halt(
    payload: ResumeRequest,
    _token: str = Depends(verify_auth_token),
    sm: RunnerStateMachine = Depends(get_state_machine),
    db: sqlite3.Connection = Depends(get_db),
):
    command_id = _enqueue_command(db, "resume", payload.model_dump())
    ok = sm.resume_from_halt(reason=payload.reason)
    if not ok:
        with db:
            db.execute(
                "UPDATE commands SET status = 'rejected', applied_at_ms = ?, result = ? WHERE id = ?",
                (int(time.time() * 1000), "API state rejected resume", command_id),
            )
        raise HTTPException(status_code=400, detail="Wiederaufnahme aus aktuellem Zustand nicht moeglich")
    return GenericResponse(
        ok=True,
        message=f"Wiederaufnahme angefordert: {payload.reason}",
        data={"command_id": command_id, "status": "pending"},
    )


@router.post("/trades/close", response_model=GenericResponse)
def close_trade_manually(
    payload: CloseTradeRequest,
    _token: str = Depends(verify_auth_token),
    pe: PaperTradingEngine = Depends(get_paper_engine),
):
    if payload.trade_id not in pe.open_positions:
        raise HTTPException(status_code=404, detail=f"Kein offener Trade mit ID {payload.trade_id} gefunden")

    pos = pe.open_positions[payload.trade_id]
    # Schliesse zum aktuellen Einstiegspreis bzw. SL als Fallback
    pe._close_full(pos, exit_price=pos.entry_price, time_ms=int(time.time() * 1000), reason=payload.reason)
    if payload.trade_id in pe.open_positions:
        pe.open_positions.pop(payload.trade_id)
        pe.closed_positions.append(pos)

    return GenericResponse(ok=True, message=f"Trade {payload.trade_id} erfolgreich geschlossen")


@router.get("/history")
def get_history(
    limit: int = Query(default=50, ge=1, le=500),
    db: sqlite3.Connection = Depends(get_db),
):
    cur = db.cursor()
    cur.execute(
        "SELECT id, symbol, dir, entry_price, exit_price, exit_reason, opened_at_ms, closed_at_ms, "
        "realized_pnl, fees, status FROM trades WHERE status = 'closed' ORDER BY closed_at_ms DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    return {
        "count": len(rows),
        "trades": [
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "dir": r["dir"],
                "entry_price": float(r["entry_price"]),
                "exit_price": float(r["exit_price"]) if r["exit_price"] else None,
                "exit_reason": r["exit_reason"],
                "opened_at_ms": r["opened_at_ms"],
                "closed_at_ms": r["closed_at_ms"],
                "realized_pnl": float(r["realized_pnl"]) if r["realized_pnl"] else 0.0,
                "fees": float(r["fees"]) if r["fees"] else 0.0,
            }
            for r in rows
        ],
    }

@router.get("/command/{cmd_id}", response_model=GenericResponse)
def get_command_status(
    cmd_id: str,
    _token: str = Depends(verify_auth_token),
    db: sqlite3.Connection = Depends(get_db),
):
    cur = db.cursor()
    cur.execute("SELECT id, type, status, result, applied_at_ms, created_at_ms FROM commands WHERE id = ?", (cmd_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Command not found")
    return GenericResponse(
        ok=True,
        message="Command found",
        data={
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "result": row["result"],
            "applied_at_ms": row["applied_at_ms"],
            "created_at_ms": row["created_at_ms"]
        }
    )
