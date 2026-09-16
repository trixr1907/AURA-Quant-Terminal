"""AURA v3 Datenadapter und Validierung (aura.data)."""

from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.gap_detector import detect_gaps, plan_backfill_chunks
from aura.data.models import (
    Candle,
    ContractSpec,
    DataProvenance,
    ValidationReport,
)
from aura.data.validation import (
    TIMEFRAME_MS,
    validate_candle_series,
    validate_single_candle,
)

__all__ = [
    "Candle",
    "ContractSpec",
    "DataProvenance",
    "ValidationReport",
    "BitgetMarketAdapter",
    "validate_single_candle",
    "validate_candle_series",
    "detect_gaps",
    "plan_backfill_chunks",
    "TIMEFRAME_MS",
]
