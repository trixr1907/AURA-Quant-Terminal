"""Datenmodelle und Provenienz-Tracking (aura.data.models).

Dokumentiert in docs/DATA_CONTRACTS.md.
Alle Zeitstempel sind UTC-Millisekunden (INTEGER).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DataProvenance:
    data_source: str  # 'bitget_rest' | 'bitget_ws' | 'sqlite_cache' | 'synthetic_fixture'
    market: str       # 'USDT-FUTURES'
    instrument: str   # z.B. 'BTCUSDT'
    event_time_ms: int
    received_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    timezone: str = "UTC"
    processing_version: str = "3.0.0-dev"
    is_proxy: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Candle:
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0
    is_closed: bool = True
    provenance: DataProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "is_closed": self.is_closed,
        }


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    product_type: str
    symbol_type: str
    symbol_status: str
    price_tick: Decimal
    qty_step: Decimal
    min_qty: Decimal
    min_notional: Decimal
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    max_leverage: int
    event_time_ms: int
    fetched_at_ms: int
    raw_snapshot_sha256: str = "sha256_uncalculated"
    source: str = "bitget_rest_v2"

    def risk_spec(self) -> dict[str, Decimal]:
        return {
            "qtyStep": self.qty_step,
            "minQty": self.min_qty,
            "minNotional": self.min_notional,
        }


@dataclass
class ValidationReport:
    is_valid: bool
    total_checked: int
    errors: list[str] = field(default_factory=list)
    gaps: list[tuple[int, int]] = field(default_factory=list)  # (gap_start_ms, gap_end_ms)
    duplicates: list[int] = field(default_factory=list)
