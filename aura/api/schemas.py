"""Pydantic Schemas fuer AURA v3 API (aura.api.schemas).

Strikte Typisierung und Wertebereichs-Validierung aller Payloads.
Dokumentiert in docs/SECURITY.md.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "halted", "starting"]
    system_state: str
    version: str = "3.0.0-dev"
    data_fresh: bool
    active_trades: int
    uptime_seconds: float
    timestamp_ms: int


class LoginRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256, description="Authentifizierungs-Token / Passwort")


class AuthStatusResponse(BaseModel):
    ok: bool = True
    authenticated: bool
    role: str = "anonymous"


class BotConfigUpdate(BaseModel):
    risk_per_trade_pct: float = Field(ge=0.1, le=5.0, description="Risiko pro Trade in %")
    max_open_positions: int = Field(ge=1, le=20, description="Maximal gleichzeitig offene Trades")
    max_leverage: int = Field(ge=1, le=50, description="Maximal zulaessiger Hebel")
    long_threshold: float = Field(ge=50.0, le=95.0, description="Mindest-Score fuer Long")
    short_threshold: float = Field(ge=5.0, le=50.0, description="Hoechst-Score fuer Short")
    macro_cap: float = Field(ge=0.0, le=25.0, description="Maximaler Makro-Score-Einfluss")
    dry_run: bool = Field(default=True, description="Paper-Trading Modus aktiv")
    ntfy_enabled: bool = Field(default=True, description="Push-Benachrichtigungen aktiv")
    expected_rev: int | None = Field(default=None, description="Erwartete aktive/letzte Revision fuer Optimistic Locking")


class HaltRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=200, description="Begruendung fuer den Not-Halt")


class ResumeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=200, description="Begruendung fuer Wiederaufnahme")


class CloseTradeRequest(BaseModel):
    trade_id: str = Field(min_length=3, max_length=64, description="ID des zu schliessenden Trades")
    reason: str = Field(default="manual_close", description="Schliessungsbegruendung")


class GenericResponse(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] | None = None
