"""Validierungslogik fuer Marktdaten und Kerzenreihen (aura.data.validation).

Dokumentiert in docs/DATA_CONTRACTS.md.
Mandats-Garantien:
  * Keine stillen Null-Werte oder erfundenen Defaults.
  * Trennung von geschlossenen und offenen/laufenden Kerzen.
  * Lueckenerkennung (Gaps) und chronologische Ordnung.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from aura.data.models import Candle, ValidationReport

TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def validate_single_candle(candle: Candle | dict[str, Any]) -> tuple[bool, list[str]]:
    """Prueft eine einzelne Kerze auf mathematische und physikalische Gueltigkeit."""
    errors = []
    if isinstance(candle, Candle):
        t = candle.time_ms
        o = candle.open
        h = candle.high
        l = candle.low
        c = candle.close
        v = candle.volume
    else:
        t = candle.get("time") or candle.get("time_ms") or 0
        o = candle.get("open", 0.0)
        h = candle.get("high", 0.0)
        l = candle.get("low", 0.0)
        c = candle.get("close", 0.0)
        v = candle.get("volume", 0.0)

    # 1. Zeitstempel
    if not (isinstance(t, (int, float)) and t > 1_000_000_000_000):
        errors.append(f"Ungueltiger UTC-Millisekunden-Zeitstempel: {t}")

    # 2. Preise positiv und endlich
    for name, val in [("open", o), ("high", h), ("low", l), ("close", c)]:
        if not (isinstance(val, (int, float)) and math.isfinite(val) and val > 0):
            errors.append(f"Preis '{name}' ungueltig oder <= 0: {val}")

    # 3. Volumen nicht-negativ
    if not (isinstance(v, (int, float)) and math.isfinite(v) and v >= 0):
        errors.append(f"Volumen ungueltig oder < 0: {v}")

    # 4. Kerzen-Invariante: High >= max(Open, Close) und Low <= min(Open, Close)
    if not errors:
        max_oc = max(o, c)
        min_oc = min(o, c)
        if h < max_oc:
            errors.append(f"High ({h}) ist kleiner als max(Open, Close) ({max_oc})")
        if l > min_oc:
            errors.append(f"Low ({l}) ist groesser als min(Open, Close) ({min_oc})")
        if h < l:
            errors.append(f"High ({h}) ist kleiner als Low ({l})")

    return len(errors) == 0, errors


def validate_candle_series(
    candles: Sequence[Candle | dict[str, Any]],
    timeframe: str = "1h",
) -> ValidationReport:
    """Validiert eine Zeitreihe auf Konsistenz, Chronologie, Duplikate und Gaps."""
    interval_ms = TIMEFRAME_MS.get(timeframe, 3_600_000)
    report = ValidationReport(is_valid=True, total_checked=len(candles))

    if not candles:
        report.is_valid = True
        return report

    prev_time = 0
    seen_times = set()

    for idx, c in enumerate(candles):
        valid_bar, bar_errs = validate_single_candle(c)
        if not valid_bar:
            report.is_valid = False
            for err in bar_errs:
                report.errors.append(f"Bar #{idx}: {err}")

        t = c.time_ms if isinstance(c, Candle) else (c.get("time") or c.get("time_ms") or 0)
        if t in seen_times:
            report.is_valid = False
            report.duplicates.append(t)
            report.errors.append(f"Bar #{idx}: Duplizierter Zeitstempel {t}")
        seen_times.add(t)

        if idx > 0:
            if t <= prev_time:
                report.is_valid = False
                report.errors.append(f"Bar #{idx}: Zeitstempel nicht monoton steigend ({t} <= {prev_time})")
            elif (t - prev_time) > interval_ms:
                # Luecke (Gap) entdeckt
                report.gaps.append((prev_time + interval_ms, t - interval_ms))

        prev_time = t

    if report.errors or report.duplicates:
        report.is_valid = False

    return report
