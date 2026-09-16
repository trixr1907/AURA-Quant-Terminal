"""Unit- und Validierungstests fuer aura.data (P4).

Prueft Schema-Validierung, Kerzen-Invarianten, Duplikat- und Gap-Erkennung
sowie Bitget-Adapter Parsing und Provenienz-Tracking.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from aura.data import (
    BitgetMarketAdapter,
    Candle,
    detect_gaps,
    plan_backfill_chunks,
    validate_candle_series,
    validate_single_candle,
)


class TestCandleValidation:
    def test_single_candle_valid(self):
        c = Candle(
            time_ms=1735689600000,
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=500.0,
        )
        ok, errs = validate_single_candle(c)
        assert ok is True
        assert len(errs) == 0

    def test_single_candle_invalid_invariants(self):
        # High kleiner als Close -> ungueltig
        c1 = {"time": 1735689600000, "open": 100.0, "high": 101.0, "low": 95.0, "close": 105.0, "volume": 10.0}
        ok1, errs1 = validate_single_candle(c1)
        assert ok1 is False
        assert any("High" in e for e in errs1)

        # Low groesser als Open -> ungueltig
        c2 = {"time": 1735689600000, "open": 100.0, "high": 110.0, "low": 102.0, "close": 105.0, "volume": 10.0}
        ok2, errs2 = validate_single_candle(c2)
        assert ok2 is False
        assert any("Low" in e for e in errs2)

    def test_candle_series_detects_duplicates_and_order(self):
        series = [
            {"time": 1000000000000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 10.0},
            {"time": 1000000000000, "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 10.0},  # Duplikat
        ]
        rep = validate_candle_series(series, "1h")
        assert rep.is_valid is False
        assert len(rep.duplicates) == 1


class TestGapDetection:
    def test_detect_gaps_in_series(self):
        # 1h Interval = 3600000ms
        t0 = 1735689600000
        # Reihe mit Sprung von Bar 1 zu Bar 4 (Luecke: Bar 2, Bar 3)
        timestamps = [t0, t0 + 3600000, t0 + 4 * 3600000]
        gaps = detect_gaps(timestamps, interval_ms=3600000)
        assert len(gaps) == 1
        assert gaps[0] == (t0 + 2 * 3600000, t0 + 3 * 3600000)

    def test_plan_backfill_chunks(self):
        # 250 Bars Luecke mit max 100 Bars pro Chunk -> 3 Chunks (100, 100, 50)
        start = 1000
        end = 1000 + 249 * 10
        chunks = plan_backfill_chunks(start, end, interval_ms=10, max_chunk_size=100)
        assert len(chunks) == 3
        assert chunks[0] == (1000, 1000 + 99 * 10)
        assert chunks[1] == (1000 + 100 * 10, 1000 + 199 * 10)
        assert chunks[2] == (1000 + 200 * 10, end)


class TestBitgetAdapter:
    def test_parse_mocked_candles(self):
        adapter = BitgetMarketAdapter()
        mock_response = {
            "code": "00000",
            "msg": "success",
            "data": [
                ["1735693200000", "100.0", "105.0", "98.0", "104.0", "500.0", "52000.0"],
                ["1735689600000", "95.0", "101.0", "94.0", "100.0", "400.0", "39000.0"],
            ],
        }

        with patch.object(adapter, "_http_get_json", return_value=mock_response):
            candles, report = adapter.fetch_candles("BTCUSDT", granularity="1H")
            assert len(candles) == 2
            # Chronologisch sortiert
            assert candles[0].time_ms == 1735689600000
            assert candles[1].time_ms == 1735693200000
            assert candles[0].is_closed is True
            assert candles[1].is_closed is False  # Letzter Bar als laufend markiert
            assert candles[0].provenance is not None
            assert candles[0].provenance.instrument == "BTCUSDT"
            assert report.is_valid is True
