"""Offline contract tests for Bitget instrument and liquidity data."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from aura.core.risk import size_position
from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.liquidity import LiquidityPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "bitget_public_v2_20260917.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_official_contract_fixture_normalizes_two_distinct_specs_without_defaults():
    raw = _fixture()
    specs = BitgetMarketAdapter.parse_contract_specs(
        raw["contracts"], fetched_at_ms=raw["provenance"]["retrieved_at_ms"]
    )
    by_symbol = {spec.symbol: spec for spec in specs}

    assert set(by_symbol) == {"BTCUSDT", "ETHUSDT"}
    assert by_symbol["BTCUSDT"].qty_step == Decimal("0.0001")
    assert by_symbol["BTCUSDT"].price_tick == Decimal("0.1")
    assert by_symbol["ETHUSDT"].qty_step == Decimal("0.01")
    assert by_symbol["ETHUSDT"].price_tick == Decimal("0.01")
    assert by_symbol["BTCUSDT"].settle_coin == "USDT"
    assert by_symbol["BTCUSDT"].symbol_type == "perpetual"
    assert by_symbol["BTCUSDT"].event_time_ms == raw["contracts"]["requestTime"]


def test_missing_required_contract_field_is_rejected_instead_of_defaulted():
    row = dict(_fixture()["contracts"]["data"][0])
    del row["sizeMultiplier"]
    payload = {"code": "00000", "msg": "success", "requestTime": 1, "data": [row]}

    with pytest.raises(ValueError, match="sizeMultiplier"):
        BitgetMarketAdapter.parse_contract_specs(payload, fetched_at_ms=2)


@pytest.mark.parametrize(
    ("spread_bps", "expected"),
    [(Decimal("9.999"), True), (Decimal("10"), True), (Decimal("10.001"), False)],
)
def test_liquidity_spread_threshold_boundaries(spread_bps: Decimal, expected: bool):
    policy = LiquidityPolicy()
    assessment = policy.evaluate_metrics(
        active=True,
        spread_bps=spread_bps,
        bid_depth_notional=Decimal("5000"),
        ask_depth_notional=Decimal("5000"),
        quote_volume_24h=Decimal("1000000"),
        event_time_ms=1_000_000,
        fetched_at_ms=1_000_000,
        decision_time_ms=1_000_000,
        book_complete=True,
    )
    assert assessment.verified is expected


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("bid_depth_notional", Decimal("4999.99"), False),
        ("bid_depth_notional", Decimal("5000"), True),
        ("bid_depth_notional", Decimal("5000.01"), True),
        ("ask_depth_notional", Decimal("4999.99"), False),
        ("ask_depth_notional", Decimal("5000"), True),
        ("ask_depth_notional", Decimal("5000.01"), True),
        ("quote_volume_24h", Decimal("999999.99"), False),
        ("quote_volume_24h", Decimal("1000000"), True),
        ("quote_volume_24h", Decimal("1000000.01"), True),
    ],
)
def test_liquidity_depth_and_volume_threshold_boundaries(field: str, value: Decimal, expected: bool):
    metrics = {
        "active": True,
        "spread_bps": Decimal("5"),
        "bid_depth_notional": Decimal("5000"),
        "ask_depth_notional": Decimal("5000"),
        "quote_volume_24h": Decimal("1000000"),
        "event_time_ms": 1_000_000,
        "fetched_at_ms": 1_000_000,
        "decision_time_ms": 1_000_000,
        "book_complete": True,
    }
    metrics[field] = value
    assert LiquidityPolicy().evaluate_metrics(**metrics).verified is expected


@pytest.mark.parametrize(
    ("delta_ms", "expected"),
    [
        (119_999, True),   # under max age (120s)
        (120_000, True),   # exactly on max age boundary
        (120_001, False),  # over max age
    ],
)
def test_liquidity_age_boundaries(delta_ms: int, expected: bool):
    decision_time_ms = 1_000_000
    event_time_ms = decision_time_ms - delta_ms
    res = LiquidityPolicy().evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("5000"),
        ask_depth_notional=Decimal("5000"),
        quote_volume_24h=Decimal("1000000"),
        event_time_ms=event_time_ms,
        fetched_at_ms=event_time_ms,
        decision_time_ms=decision_time_ms,
        book_complete=True,
    )
    assert res.verified is expected


@pytest.mark.parametrize(
    ("skew_ms", "expected"),
    [
        (4_999, True),   # under max future skew (5000ms)
        (5_000, True),   # exactly on boundary
        (5_001, False),  # over max future skew
    ],
)
def test_liquidity_future_skew_boundaries(skew_ms: int, expected: bool):
    decision_time_ms = 1_000_000
    event_time_ms = decision_time_ms + skew_ms
    res = LiquidityPolicy().evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("5000"),
        ask_depth_notional=Decimal("5000"),
        quote_volume_24h=Decimal("1000000"),
        event_time_ms=event_time_ms,
        fetched_at_ms=decision_time_ms,
        decision_time_ms=decision_time_ms,
        book_complete=True,
    )
    assert res.verified is expected


def test_depth_parser_handles_official_btc_and_eth_and_rejects_anomalies():
    raw = _fixture()
    spread, bid_depth, ask_depth, best_bid, best_ask, ok = BitgetMarketAdapter.parse_depth_metrics(
        raw["depths"]["BTCUSDT"]
    )
    assert ok is True
    assert spread > 0 and spread < 1
    assert bid_depth > 500_000
    assert ask_depth > 500_000
    assert best_ask > best_bid

    # Crossed orderbook (bid >= ask) is rejected
    crossed = {"data": {"asks": [["100", "1"]], "bids": [["105", "1"]]}}
    assert BitgetMarketAdapter.parse_depth_metrics(crossed)[5] is False

    # Empty bids or asks
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [], "bids": [["100", "1"]]}})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["100", "1"]], "bids": []}})[5] is False

    # Malformed data
    assert BitgetMarketAdapter.parse_depth_metrics({"data": None})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["not_a_number", "1"]], "bids": [["100", "1"]]}})[5] is False


@pytest.mark.parametrize(
    ("event_time_ms", "fetched_at_ms", "book_complete", "reason"),
    [
        (879_999, 879_999, True, "STALE"),
        (1_005_001, 1_000_000, True, "FUTURE"),
        (1_000_000, 1_000_000, False, "BOOK_INCOMPLETE"),
    ],
)
def test_liquidity_rejects_stale_future_and_incomplete_books(
    event_time_ms: int, fetched_at_ms: int, book_complete: bool, reason: str
):
    result = LiquidityPolicy().evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("5000"),
        ask_depth_notional=Decimal("5000"),
        quote_volume_24h=Decimal("1000000"),
        event_time_ms=event_time_ms,
        fetched_at_ms=fetched_at_ms,
        decision_time_ms=1_000_000,
        book_complete=book_complete,
    )
    assert result.verified is False
    assert any(reason in actual for actual in result.reasons)


def test_decimal_sizing_uses_real_btc_and_eth_steps_without_exceeding_risk_budget():
    raw = _fixture()
    specs = BitgetMarketAdapter.parse_contract_specs(
        raw["contracts"], fetched_at_ms=raw["provenance"]["retrieved_at_ms"]
    )
    by_symbol = {spec.symbol: spec for spec in specs}

    btc = size_position(Decimal("10"), Decimal("80000"), Decimal("123.4567"), 10, by_symbol["BTCUSDT"].risk_spec())
    eth = size_position(Decimal("10"), Decimal("2500"), Decimal("17.3"), 10, by_symbol["ETHUSDT"].risk_spec())

    assert Decimal(str(btc.qty)) % Decimal("0.0001") == 0
    assert Decimal(str(eth.qty)) % Decimal("0.01") == 0
    assert Decimal(str(btc.actual_risk_amt)) <= Decimal("10")
    assert Decimal(str(eth.actual_risk_amt)) <= Decimal("10")
