"""Canonical liquidity policy for public Bitget futures data."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

POLICY_VERSION = "aura-liquidity-v2"


@dataclass(frozen=True)
class LiquidityAssessment:
    verified: bool
    status: str
    reasons: tuple[str, ...]
    policy_version: str = POLICY_VERSION


@dataclass(frozen=True)
class LiquidityPolicy:
    depth_band_bps: Decimal = Decimal("25")
    max_position_depth_fraction: Decimal = Decimal("0.05")
    min_depth_notional: Decimal = Decimal("5000")
    max_spread_bps: Decimal = Decimal("10")
    min_quote_volume_24h: Decimal = Decimal("1000000")
    max_age_ms: int = 120_000
    max_future_skew_ms: int = 5_000
    spec_max_age_ms: int = 3600_000  # 1 hour

    def evaluate_metrics(
        self,
        *,
        active: bool,
        spread_bps: Decimal,
        bid_depth_notional: Decimal,
        ask_depth_notional: Decimal,
        quote_volume_24h: Decimal,
        decision_time_ms: int,
        book_event_time_ms: int | None = None,
        book_fetched_at_ms: int | None = None,
        ticker_event_time_ms: int | None = None,
        ticker_fetched_at_ms: int | None = None,
        event_time_ms: int | None = None,
        fetched_at_ms: int | None = None,
        spec_fetched_at_ms: int | None = None,
        book_complete: bool = True,
    ) -> LiquidityAssessment:
        reasons: list[str] = []
        if not active:
            reasons.append("INSTRUMENT_NOT_ACTIVE")
        if not book_complete:
            reasons.append("BOOK_INCOMPLETE")

        b_event = book_event_time_ms if book_event_time_ms is not None else event_time_ms
        b_fetch = book_fetched_at_ms if book_fetched_at_ms is not None else fetched_at_ms
        t_event = ticker_event_time_ms if ticker_event_time_ms is not None else event_time_ms
        t_fetch = ticker_fetched_at_ms if ticker_fetched_at_ms is not None else fetched_at_ms

        # Book timestamps
        if b_event is None or b_event <= 0:
            reasons.append("BOOK_EVENT_TIME_MISSING")
        else:
            if b_event > decision_time_ms + self.max_future_skew_ms:
                reasons.append("FUTURE_BOOK_EVENT_TIME")
            if decision_time_ms - b_event > self.max_age_ms:
                reasons.append("STALE_BOOK_EVENT_TIME")

        if b_fetch is None or b_fetch <= 0:
            reasons.append("BOOK_FETCH_TIME_MISSING")
        else:
            if b_fetch > decision_time_ms + self.max_future_skew_ms:
                reasons.append("FUTURE_BOOK_FETCH_TIME")
            if decision_time_ms - b_fetch > self.max_age_ms:
                reasons.append("STALE_BOOK_FETCH_TIME")

        # Ticker timestamps
        if t_event is None or t_event <= 0:
            reasons.append("TICKER_EVENT_TIME_MISSING")
        else:
            if t_event > decision_time_ms + self.max_future_skew_ms:
                reasons.append("FUTURE_TICKER_EVENT_TIME")
            if decision_time_ms - t_event > self.max_age_ms:
                reasons.append("STALE_TICKER_EVENT_TIME")

        if t_fetch is None or t_fetch <= 0:
            reasons.append("TICKER_FETCH_TIME_MISSING")
        else:
            if t_fetch > decision_time_ms + self.max_future_skew_ms:
                reasons.append("FUTURE_TICKER_FETCH_TIME")
            if decision_time_ms - t_fetch > self.max_age_ms:
                reasons.append("STALE_TICKER_FETCH_TIME")

        # Spec freshness
        if spec_fetched_at_ms is not None:
            if spec_fetched_at_ms <= 0:
                reasons.append("SPEC_TIMESTAMP_MISSING")
            elif decision_time_ms - spec_fetched_at_ms > self.spec_max_age_ms:
                reasons.append("STALE_SPECIFICATION")

        # Market metrics
        if spread_bps > self.max_spread_bps:
            reasons.append("SPREAD_TOO_WIDE")
        if bid_depth_notional < self.min_depth_notional:
            reasons.append("BID_DEPTH_TOO_LOW")
        if ask_depth_notional < self.min_depth_notional:
            reasons.append("ASK_DEPTH_TOO_LOW")
        if quote_volume_24h < self.min_quote_volume_24h:
            reasons.append("QUOTE_VOLUME_TOO_LOW")

        verified = not reasons
        has_stale = any("STALE" in r or "FUTURE" in r for r in reasons)
        status = "valid" if verified else ("stale" if has_stale else "insufficient")
        return LiquidityAssessment(
            verified=verified,
            status=status,
            reasons=tuple(reasons),
        )
