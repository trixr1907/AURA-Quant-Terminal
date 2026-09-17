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

    # Inverted orderbook where bid == ask
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["100", "1"]], "bids": [["100", "1"]]}})[5] is False

    # Empty bids or asks
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [], "bids": [["100", "1"]]}})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["100", "1"]], "bids": []}})[5] is False

    # Malformed data
    assert BitgetMarketAdapter.parse_depth_metrics({"data": None})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["not_a_number", "1"]], "bids": [["100", "1"]]}})[5] is False

    # Non-positive prices or quantities
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["0", "1"]], "bids": [["100", "1"]]}})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["105", "0"]], "bids": [["100", "1"]]}})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["105", "-1"]], "bids": [["100", "1"]]}})[5] is False
    assert BitgetMarketAdapter.parse_depth_metrics({"data": {"asks": [["-105", "1"]], "bids": [["100", "1"]]}})[5] is False

    # Out of order levels (asks not ascending, bids not descending)
    unsorted_asks = {"data": {"asks": [["105", "1"], ["102", "1"]], "bids": [["100", "1"], ["99", "1"]]}}
    assert BitgetMarketAdapter.parse_depth_metrics(unsorted_asks)[5] is False

    unsorted_bids = {"data": {"asks": [["102", "1"], ["105", "1"]], "bids": [["99", "1"], ["100", "1"]]}}
    assert BitgetMarketAdapter.parse_depth_metrics(unsorted_bids)[5] is False


def test_depth_band_25bps_filtering():
    # Mid is 10,000. 25 bps is 25 USDT -> Asks up to 10,025, Bids down to 9,975.
    depth = {
        "data": {
            "asks": [
                ["10005", "1"],  # In band: 10,005 USDT
                ["10020", "2"],  # In band: 20,040 USDT
                ["10030", "5"],  # Out of band (>10025): excluded
            ],
            "bids": [
                ["9995", "1"],   # In band: 9,995 USDT
                ["9980", "2"],   # In band: 19,960 USDT
                ["9970", "5"],   # Out of band (<9975): excluded
            ],
        }
    }
    spread, bid_depth, ask_depth, best_bid, best_ask, ok = BitgetMarketAdapter.parse_depth_metrics(
        depth, max_depth_band_bps=Decimal("25")
    )
    assert ok is True
    assert best_bid == Decimal("9995")
    assert best_ask == Decimal("10005")
    assert ask_depth == Decimal("10005") + Decimal("20040")
    assert bid_depth == Decimal("9995") + Decimal("19960")


def test_round_price_to_tick():
    from aura.core.risk import round_price_to_tick
    assert round_price_to_tick(Decimal("81234.567"), Decimal("0.1")) == Decimal("81234.6")
    assert round_price_to_tick(Decimal("2512.345"), Decimal("0.01")) == Decimal("2512.35")
    assert round_price_to_tick(Decimal("0.123456"), Decimal("0.0001")) == Decimal("0.1235")


def test_independent_timestamp_freshness_evaluation():
    policy = LiquidityPolicy()
    now_ms = 1_000_000_000

    # All fresh -> valid
    res = policy.evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("10000"),
        ask_depth_notional=Decimal("10000"),
        quote_volume_24h=Decimal("2000000"),
        book_event_time_ms=now_ms - 10_000,
        book_fetched_at_ms=now_ms - 10_000,
        ticker_event_time_ms=now_ms - 10_000,
        ticker_fetched_at_ms=now_ms - 10_000,
        spec_fetched_at_ms=now_ms - 10_000,
        decision_time_ms=now_ms,
        book_complete=True,
    )
    assert res.verified is True

    # Stale orderbook (>120s) -> invalid
    res_stale_book = policy.evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("10000"),
        ask_depth_notional=Decimal("10000"),
        quote_volume_24h=Decimal("2000000"),
        book_event_time_ms=now_ms - 121_000,
        book_fetched_at_ms=now_ms - 10_000,
        ticker_event_time_ms=now_ms - 10_000,
        ticker_fetched_at_ms=now_ms - 10_000,
        spec_fetched_at_ms=now_ms - 10_000,
        decision_time_ms=now_ms,
        book_complete=True,
    )
    assert res_stale_book.verified is False
    assert "STALE_BOOK_EVENT_TIME" in res_stale_book.reasons

    # Stale ticker (>120s) -> invalid
    res_stale_ticker = policy.evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("10000"),
        ask_depth_notional=Decimal("10000"),
        quote_volume_24h=Decimal("2000000"),
        book_event_time_ms=now_ms - 10_000,
        book_fetched_at_ms=now_ms - 10_000,
        ticker_event_time_ms=now_ms - 121_000,
        ticker_fetched_at_ms=now_ms - 10_000,
        spec_fetched_at_ms=now_ms - 10_000,
        decision_time_ms=now_ms,
        book_complete=True,
    )
    assert res_stale_ticker.verified is False
    assert "STALE_TICKER_EVENT_TIME" in res_stale_ticker.reasons

    # Stale spec (>24h) -> invalid
    res_stale_spec = policy.evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("10000"),
        ask_depth_notional=Decimal("10000"),
        quote_volume_24h=Decimal("2000000"),
        book_event_time_ms=now_ms - 10_000,
        book_fetched_at_ms=now_ms - 10_000,
        ticker_event_time_ms=now_ms - 10_000,
        ticker_fetched_at_ms=now_ms - 10_000,
        spec_fetched_at_ms=now_ms - 86_401_000,
        decision_time_ms=now_ms,
        book_complete=True,
    )
    assert res_stale_spec.verified is False
    assert "STALE_SPECIFICATION" in res_stale_spec.reasons

    # Future skew (>5s) -> invalid
    res_future_book = policy.evaluate_metrics(
        active=True,
        spread_bps=Decimal("5"),
        bid_depth_notional=Decimal("10000"),
        ask_depth_notional=Decimal("10000"),
        quote_volume_24h=Decimal("2000000"),
        book_event_time_ms=now_ms + 5001,
        book_fetched_at_ms=now_ms,
        ticker_event_time_ms=now_ms,
        ticker_fetched_at_ms=now_ms,
        spec_fetched_at_ms=now_ms,
        decision_time_ms=now_ms,
        book_complete=True,
    )
    assert res_future_book.verified is False
    assert "FUTURE_BOOK_EVENT_TIME" in res_future_book.reasons


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
