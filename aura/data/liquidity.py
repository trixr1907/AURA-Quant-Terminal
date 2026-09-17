"""Canonical liquidity policy for public Bitget futures data."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

POLICY_VERSION = "aura-liquidity-v1"


@dataclass(frozen=True)
class LiquidityAssessment:
    verified: bool
    status: str
    reasons: tuple[str, ...]
    policy_version: str = POLICY_VERSION


@dataclass(frozen=True)
class LiquidityPolicy:
    max_age_ms: int = 120_000
    max_future_skew_ms: int = 5_000
    max_spread_bps: Decimal = Decimal("10")
    min_depth_notional: Decimal = Decimal("5000")
    min_quote_volume_24h: Decimal = Decimal("1000000")
    max_position_depth_fraction: Decimal = Decimal("0.10")

    def evaluate_metrics(
        self,
        *,
        active: bool,
        spread_bps: Decimal,
        bid_depth_notional: Decimal,
        ask_depth_notional: Decimal,
        quote_volume_24h: Decimal,
        event_time_ms: int,
        fetched_at_ms: int,
        decision_time_ms: int,
        book_complete: bool,
    ) -> LiquidityAssessment:
        reasons: list[str] = []
        if not active:
            reasons.append("INSTRUMENT_INACTIVE")
        if not book_complete:
            reasons.append("BOOK_INCOMPLETE")
        if event_time_ms > decision_time_ms + self.max_future_skew_ms:
            reasons.append("FUTURE_EVENT_TIME")
        if fetched_at_ms > decision_time_ms + self.max_future_skew_ms:
            reasons.append("FUTURE_FETCH_TIME")
        if decision_time_ms - event_time_ms > self.max_age_ms or decision_time_ms - fetched_at_ms > self.max_age_ms:
            reasons.append("STALE_SNAPSHOT")
        if spread_bps > self.max_spread_bps:
            reasons.append("SPREAD_TOO_WIDE")
        if bid_depth_notional < self.min_depth_notional:
            reasons.append("BID_DEPTH_TOO_LOW")
        if ask_depth_notional < self.min_depth_notional:
            reasons.append("ASK_DEPTH_TOO_LOW")
        if quote_volume_24h < self.min_quote_volume_24h:
            reasons.append("QUOTE_VOLUME_TOO_LOW")
        verified = not reasons
        return LiquidityAssessment(
            verified=verified,
            status="valid" if verified else ("stale" if any("STALE" in reason or "FUTURE" in reason for reason in reasons) else "insufficient"),
            reasons=tuple(reasons),
        )
