"""API Routen fuer AURA v3 (aura.api.routes).

Dokumentiert in docs/ARCHITECTURE.md §6 und docs/SECURITY.md.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from aura.api.auth import verify_auth_token
from aura.api.schemas import (
    BotConfigUpdate,
    CloseTradeRequest,
    GenericResponse,
    HaltRequest,
    HealthResponse,
    ResumeRequest,
)
from aura.runner.paper_engine import PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.store.db import connect

router = APIRouter()

# Globale Instanzen fuer den API-Prozess (werden bei create_app initialisiert)
_state_machine: RunnerStateMachine | None = None
_paper_engine: PaperTradingEngine | None = None
_db_conn: sqlite3.Connection | None = None
_start_time = time.time()


def set_api_state(
    state_machine: RunnerStateMachine,
    paper_engine: PaperTradingEngine,
    db_conn: sqlite3.Connection,
) -> None:
    global _state_machine, _paper_engine, _db_conn
    _state_machine = state_machine
    _paper_engine = paper_engine
    _db_conn = db_conn


def get_state_machine() -> RunnerStateMachine:
    if _state_machine is None:
        raise HTTPException(status_code=500, detail="State Machine nicht initialisiert")
    return _state_machine


def get_paper_engine() -> PaperTradingEngine:
    if _paper_engine is None:
        raise HTTPException(status_code=500, detail="Paper Engine nicht initialisiert")
    _paper_engine._load_state_from_db_if_available()
    return _paper_engine


def get_db() -> sqlite3.Connection:
    if _db_conn is None:
        raise HTTPException(status_code=500, detail="Datenbank nicht initialisiert")
    return _db_conn


def _enqueue_command(db: sqlite3.Connection, command_type: str, payload: dict[str, Any]) -> str:
    command_id = f"cmd_{uuid.uuid4().hex}"
    with db:
        db.execute(
            "INSERT INTO commands (id, type, payload, status, created_at_ms) VALUES (?, ?, ?, 'pending', ?)",
            (command_id, command_type, json.dumps(payload), int(time.time() * 1000)),
        )
    return command_id


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
def get_state(pe: PaperTradingEngine = Depends(get_paper_engine), db: sqlite3.Connection = Depends(get_db)):
    # Lade aktive Config-Revision
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

    # Offene Positionen serialisieren
    open_list = [
        {
            "id": p.trade_id,
            "symbol": p.symbol,
            "dir": p.direction,
            "entry_price": p.entry_price,
            "sl_price": p.sl_price,
            "tp1_price": p.tp1_price,
            "tp2_price": p.tp2_price,
            "qty": p.qty,
            "margin": p.margin,
            "leverage": p.leverage,
            "opened_at_ms": p.entry_time_ms,
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

    # Geschlossene Positionen serialisieren
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
        }
        for p in pe.closed_positions
    ]

    return {
        "equity": pe.equity,
        "starting_equity": pe.starting_equity,
        "open_positions": open_list,
        "closed_trades": closed_list,
        "config": bot_cfg,
        "config_rev": active_rev,
        "requested_config_rev": requested_rev,
        "active_config_rev": active_rev,
        "server_time_ms": int(time.time() * 1000),
    }


@router.post("/config", response_model=GenericResponse)
def update_config(
    payload: BotConfigUpdate,
    _token: str = Depends(verify_auth_token),
    db: sqlite3.Connection = Depends(get_db),
    pe: PaperTradingEngine = Depends(get_paper_engine),
):
    """Aktualisiert die Bot-Konfiguration transaktional und inkrementiert die Revision."""
    cfg_dict = payload.model_dump()
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
            "active_rev": None,
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
