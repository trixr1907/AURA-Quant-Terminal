"""Lueckenerkennung und Backfill-Planung fuer Zeitreihen (aura.data.gap_detector).

Dokumentiert in docs/DATA_CONTRACTS.md.
Garantiert: Kein Datenverlust zwischen historischen Snapshots und Live-Updates.
"""

from __future__ import annotations

from typing import Sequence


def detect_gaps(
    timestamps_ms: Sequence[int],
    interval_ms: int = 3_600_000,
) -> list[tuple[int, int]]:
    """Identifiziert Luecken (fehlende Kerzenintervalle) in einer sortierten Zeitreihe."""
    gaps: list[tuple[int, int]] = []
    if len(timestamps_ms) < 2:
        return gaps

    for i in range(1, len(timestamps_ms)):
        t_prev = timestamps_ms[i - 1]
        t_curr = timestamps_ms[i]
        diff = t_curr - t_prev
        if diff > interval_ms:
            # Luecke von t_prev + interval_ms bis t_curr - interval_ms
            gaps.append((t_prev + interval_ms, t_curr - interval_ms))

    return gaps


def plan_backfill_chunks(
    gap_start_ms: int,
    gap_end_ms: int,
    interval_ms: int = 3_600_000,
    max_chunk_size: int = 100,
) -> list[tuple[int, int]]:
    """Unterteilt eine Luecke in abrufbare Chunks (max_chunk_size Bars)."""
    if gap_start_ms > gap_end_ms:
        return []

    chunks: list[tuple[int, int]] = []
    chunk_duration_ms = max_chunk_size * interval_ms
    current_start = gap_start_ms

    while current_start <= gap_end_ms:
        current_end = min(gap_end_ms, current_start + chunk_duration_ms - interval_ms)
        chunks.append((current_start, current_end))
        current_start = current_end + interval_ms

    return chunks
