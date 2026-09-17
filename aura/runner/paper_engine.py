"""Kanonische Paper-Trading-Engine (aura.runner.paper_engine).

Befunde behoben:
  * Q-01: Exakte Equity-Verrechnung (state.equity += realized_pnl - fees).
  * Q-02: Vollstaendige TP1/TP2-Exits mit 50%-Teilschliessung und BE-Nachzug.
  * Q-03: Konservative Intrabar-Policy (bei SL+TP-Treffer im selben Bar gewinnt SL).
  * Q-04: Korrekte Exit-Begruendung (timestop, tp1_partial, tp2_hit, sl_hit, manual_close).
  * Q-05: Transaktionale Persistenz in SQLite.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from aura.core.risk import PositionSize, size_position

logger = logging.getLogger("aura.runner.paper_engine")


@dataclass
class PaperPosition:
    trade_id: str
    symbol: str
    timeframe: str
    direction: int  # 1 = Long, -1 = Short
    entry_price: float
    sl_price: float
    initial_sl_price: float
    tp1_price: float
    tp2_price: float
    qty: float
    contracts: int
    initial_qty: float
    margin: float
    leverage: int
    entry_time_ms: int
    status: str  # 'open', 'partial_tp1', 'closed'
    tp1_hit: bool = False
    exit_price: float | None = None
    exit_time_ms: int | None = None
    exit_reason: str | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_fees: float = 0.0
    r_multiple: float = 0.0
    max_price: float = 0.0
    min_price: float = 0.0
    setup_score: float = 50.0
    notes: str = ""


@dataclass
class EngineConfig:
    starting_equity: float = 10000.0
    maker_fee: float = 0.0002  # 0.02% (Bitget Maker)
    taker_fee: float = 0.0006  # 0.06% (Bitget Taker)
    slippage_bps: float = 1.5   # 1.5 bps (0.015%)
    max_open_positions: int = 5
    max_hold_bars: int = 72     # Timestop nach 72 Bars (z.B. 72h bei 1h)
    risk_per_trade_pct: float = 1.0
    intrabar_conservative: bool = True  # Wenn SL und TP im selben Bar: SL gewinnt


class PaperTradingEngine:
    """Server-authoritative Paper-Engine mit exaktem PnL-Accounting."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        conn: sqlite3.Connection | None = None,
    ):
        self.config = config or EngineConfig()
        self.conn = conn
        self.equity: float = self.config.starting_equity
        self.starting_equity: float = self.config.starting_equity
        self.open_positions: dict[str, PaperPosition] = {}
        self.closed_positions: list[PaperPosition] = []
        self._load_state_from_db_if_available()

    def _load_state_from_db_if_available(self) -> None:
        if not self.conn:
            return
        cur = self.conn.cursor()

        # 1. Offene Positionen laden
        cur.execute(
            "SELECT id, symbol, dir, entry_price, current_sl, initial_sl, "
            "tp1, tp2, notional, margin, leverage, opened_at_ms, timeframe, remaining_qty, entry_fee, "
            "status, tp1_hit, realized_pnl, fees FROM trades WHERE status = 'open'"
        )
        entry_fees_paid = 0.0
        realized_from_open = 0.0
        for row in cur.fetchall():
            ep = float(row["entry_price"])
            sl = float(row["current_sl"])
            margin = float(row["margin"])
            lev = int(row["leverage"])
            initial_notional = float(row["notional"])
            initial_qty = (initial_notional / ep) if ep > 0 else 0.0
            tp1_hit = bool(row["tp1_hit"])
            qty = float(row["remaining_qty"]) if row["remaining_qty"] is not None else (
                (initial_qty * 0.5) if tp1_hit else initial_qty
            )
            entry_fees_paid += (
                float(row["entry_fee"])
                if row["entry_fee"] is not None
                else float(row["fees"] or 0.0)
            )
            realized_from_open += float(row["realized_pnl"] or 0.0)

            pos = PaperPosition(
                trade_id=row["id"],
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                direction=int(row["dir"]),
                entry_price=ep,
                sl_price=sl,
                initial_sl_price=float(row["initial_sl"]),
                tp1_price=float(row["tp1"]) if row["tp1"] else (ep * 1.05),
                tp2_price=float(row["tp2"]) if row["tp2"] else (ep * 1.10),
                qty=qty,
                contracts=1,
                initial_qty=initial_qty,
                margin=margin,
                leverage=lev,
                entry_time_ms=int(row["opened_at_ms"]),
                status="partial_tp1" if tp1_hit else "open",
                tp1_hit=tp1_hit,
                realized_pnl=float(row["realized_pnl"] or 0.0),
                total_fees=float(row["fees"] or 0.0),
            )
            self.open_positions[pos.trade_id] = pos

        # 2. Geschlossene Positionen & Equity-Historie laden
        cur.execute(
            "SELECT id, symbol, dir, entry_price, current_sl, initial_sl, "
            "tp1, tp2, notional, margin, leverage, opened_at_ms, closed_at_ms, exit_price, exit_reason, "
            "timeframe, entry_fee, status, tp1_hit, realized_pnl, fees "
            "FROM trades WHERE status = 'closed' ORDER BY closed_at_ms ASC"
        )
        total_realized = realized_from_open
        for row in cur.fetchall():
            ep = float(row["entry_price"])
            margin = float(row["margin"])
            lev = int(row["leverage"])
            initial_notional = float(row["notional"])
            qty = (initial_notional / ep) if ep > 0 else 0.0
            pnl = float(row["realized_pnl"] or 0.0)
            fees = float(row["fees"] or 0.0)
            entry_fee = (
                float(row["entry_fee"])
                if row["entry_fee"] is not None
                else 0.0
            )
            entry_fees_paid += entry_fee
            total_realized += pnl

            pos = PaperPosition(
                trade_id=row["id"],
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                direction=int(row["dir"]),
                entry_price=ep,
                sl_price=float(row["current_sl"]),
                initial_sl_price=float(row["initial_sl"]),
                tp1_price=float(row["tp1"]) if row["tp1"] else (ep * 1.05),
                tp2_price=float(row["tp2"]) if row["tp2"] else (ep * 1.10),
                qty=qty,
                contracts=1,
                initial_qty=qty,
                margin=margin,
                leverage=lev,
                entry_time_ms=int(row["opened_at_ms"]),
                exit_time_ms=int(row["closed_at_ms"]) if row["closed_at_ms"] else None,
                exit_price=float(row["exit_price"]) if row["exit_price"] else None,
                exit_reason=row["exit_reason"],
                status="closed",
                tp1_hit=bool(row["tp1_hit"]),
                realized_pnl=pnl,
                total_fees=fees,
            )
            self.closed_positions.append(pos)

        # Equity = Start minus alle Entry-Gebuehren plus bereits realisierte Netto-Exits.
        self.equity = self.starting_equity - entry_fees_paid + total_realized

    def open_trade(
        self,
        symbol: str,
        timeframe: str,
        direction: int,
        entry_price: float,
        sl_price: float,
        tp1_price: float,
        tp2_price: float,
        spec: dict[str, Any] | None = None,
        leverage: int = 10,
        score: float = 65.0,
        current_time_ms: int | None = None,
    ) -> PaperPosition | None:
        """Eröffnet eine neue Paper-Position mit Gebühren- und Slippage-Abzug."""
        if len(self.open_positions) >= self.config.max_open_positions:
            logger.info("Trade abgelehnt: Max offene Positionen (%d) erreicht", self.config.max_open_positions)
            return None

        # Pruefe ob bereits eine Position fuer dieses Symbol offen ist
        for p in self.open_positions.values():
            if p.symbol == symbol:
                logger.info("Trade abgelehnt: Bereits offene Position fuer %s", symbol)
                return None

        stop_dist = abs(entry_price - sl_price)
        if stop_dist <= 0:
            logger.warning("Trade abgelehnt: SL distanz <= 0")
            return None

        risk_amt = self.equity * (self.config.risk_per_trade_pct / 100.0)
        sized = size_position(risk_amt, entry_price, stop_dist, leverage=leverage, spec=spec)
        if sized.contracts <= 0 or sized.qty <= 0:
            logger.info("Trade abgelehnt: Groesse unter Mindestanforderung (contracts=0)")
            return None

        # Slippage beim Einstieg (Taker)
        slip_factor = (1.0 + (self.config.slippage_bps / 10000.0) * direction)
        fill_price = entry_price * slip_factor

        # Entry Fee (Taker)
        entry_fee = sized.qty * fill_price * self.config.taker_fee

        now_ms = current_time_ms or int(time.time() * 1000)
        trade_id = f"trade_{uuid.uuid4().hex[:12]}"

        pos = PaperPosition(
            trade_id=trade_id,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            entry_price=fill_price,
            sl_price=sl_price,
            initial_sl_price=sl_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            qty=sized.qty,
            contracts=sized.contracts,
            initial_qty=sized.qty,
            margin=sized.margin,
            leverage=leverage,
            entry_time_ms=now_ms,
            status="open",
            total_fees=entry_fee,
            max_price=fill_price,
            min_price=fill_price,
            setup_score=score,
        )

        self.open_positions[trade_id] = pos
        # Entry-Gebuehr ist sofort realisiert und reduziert die Kontoequity.
        self.equity -= entry_fee
        self._persist_trade(pos)
        logger.info(
            "Paper Trade geoeffnet: %s %s @ %.4f (SL: %.4f, TP1: %.4f)",
            "LONG" if direction == 1 else "SHORT",
            symbol,
            fill_price,
            sl_price,
            tp1_price,
        )
        return pos

    @staticmethod
    def _timeframe_ms(timeframe: str) -> int:
        units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
        normalized = timeframe.strip().lower()
        if len(normalized) < 2 or normalized[-1] not in units:
            raise ValueError(f"Nicht unterstuetzter Timeframe: {timeframe}")
        amount = int(normalized[:-1])
        if amount <= 0:
            raise ValueError(f"Nicht unterstuetzter Timeframe: {timeframe}")
        return amount * units[normalized[-1]]

    def on_bar_update(
        self,
        symbol: str,
        high: float,
        low: float,
        close: float,
        bar_time_ms: int,
        bar_idx: int = 0,
    ) -> list[PaperPosition]:
        """Aktualisiert alle offenen Positionen gegen den neuen Bar.

        Behandelt Intrabar-Kollisionen, TP1-Teilschliessungen, SL-Hits und Timestops.
        """
        closed_in_bar: list[PaperPosition] = []
        to_remove = []

        for trade_id, pos in list(self.open_positions.items()):
            if pos.symbol != symbol:
                continue

            # Update Max/Min Preise
            pos.max_price = max(pos.max_price, high)
            pos.min_price = min(pos.min_price, low) if pos.min_price > 0 else low

            dir_ = pos.direction
            entry = pos.entry_price
            sl = pos.sl_price
            tp1 = pos.tp1_price
            tp2 = pos.tp2_price

            # Pruefe Trigger
            sl_hit = (low <= sl) if dir_ == 1 else (high >= sl)
            tp1_hit = (high >= tp1) if dir_ == 1 else (low <= tp1)
            tp2_hit = (high >= tp2) if dir_ == 1 else (low <= tp2)

            # Intrabar-Kollision: SL und TP im selben Bar getroffen
            if sl_hit and (tp1_hit or tp2_hit):
                if self.config.intrabar_conservative:
                    # Konservative Policy: SL wird ausgefuehrt
                    self._close_full(pos, sl, bar_time_ms, "sl_hit_intrabar_collision")
                    closed_in_bar.append(pos)
                    to_remove.append(trade_id)
                    continue

            # 1. Normaler SL Hit
            if sl_hit:
                self._close_full(pos, sl, bar_time_ms, "sl_hit")
                closed_in_bar.append(pos)
                to_remove.append(trade_id)
                continue

            # 2. TP2 Hit (Vollschliessung)
            if tp2_hit:
                self._close_full(pos, tp2, bar_time_ms, "tp2_hit")
                closed_in_bar.append(pos)
                to_remove.append(trade_id)
                continue

            # 3. TP1 Hit (50% Teilschliessung & SL auf BE nachziehen)
            if tp1_hit and not pos.tp1_hit:
                self._execute_tp1_partial(pos, tp1, bar_time_ms)
                continue

            # 4. Timestop Pruefung
            holding_ms = bar_time_ms - pos.entry_time_ms
            max_ms = self.config.max_hold_bars * self._timeframe_ms(pos.timeframe)
            if holding_ms >= max_ms:
                self._close_full(pos, close, bar_time_ms, "timestop")
                closed_in_bar.append(pos)
                to_remove.append(trade_id)
                continue

            # Unrealized PnL aktualisieren
            current_diff = (close - entry) * dir_
            pos.unrealized_pnl = pos.qty * current_diff
            self._persist_trade(pos)

        for tid in to_remove:
            if tid in self.open_positions:
                pos = self.open_positions.pop(tid)
                self.closed_positions.append(pos)

        return closed_in_bar

    def _execute_tp1_partial(self, pos: PaperPosition, fill_price: float, time_ms: int) -> None:
        """Fuehrt 50% TP1-Teilverkauf aus und zieht den Stop auf Breakeven."""
        closed_qty = pos.qty * 0.5
        remaining_qty = pos.qty - closed_qty

        # PnL fuer die 50% Tranche
        gross_pnl = (fill_price - pos.entry_price) * pos.direction * closed_qty
        exit_fee = closed_qty * fill_price * self.config.maker_fee
        net_partial = gross_pnl - exit_fee

        pos.realized_pnl += net_partial
        pos.total_fees += exit_fee
        pos.qty = remaining_qty
        pos.tp1_hit = True
        pos.status = "partial_tp1"
        pos.sl_price = pos.entry_price  # Breakeven Stop
        pos.notes = f"TP1 @ {fill_price:.4f} (50% Teilgewinn: {net_partial:.2f})"

        # Equity-Gutschrift fuer den realisierten Teilgewinn
        self.equity += net_partial

        self._persist_trade(pos)
        logger.info(
            "TP1 erreicht fuer %s: 50%% geschlossen @ %.4f, SL auf BE (%.4f) gezogen",
            pos.symbol,
            fill_price,
            pos.sl_price,
        )

    def _close_full(
        self,
        pos: PaperPosition,
        exit_price: float,
        time_ms: int,
        reason: str,
    ) -> None:
        """Schliesst die restliche Position vollstaendig und aktualisiert die Gesamtequity."""
        # Slippage bei SL/Timestop (Taker), Maker bei normalem Limit TP
        is_taker = "sl" in reason or "timestop" in reason or "manual" in reason
        fee_rate = self.config.taker_fee if is_taker else self.config.maker_fee
        slip = (self.config.slippage_bps / 10000.0) * (-pos.direction) if is_taker else 0.0
        final_price = exit_price * (1.0 + slip)

        gross_pnl = (final_price - pos.entry_price) * pos.direction * pos.qty
        exit_fee = pos.qty * final_price * fee_rate
        net_pnl = gross_pnl - exit_fee

        pos.realized_pnl += net_pnl
        pos.total_fees += exit_fee
        pos.exit_price = final_price
        pos.exit_time_ms = time_ms
        pos.exit_reason = reason
        pos.status = "closed"
        pos.unrealized_pnl = 0.0

        # R-Multiple Berechnung
        init_risk = pos.initial_qty * abs(pos.entry_price - pos.initial_sl_price)
        pos.r_multiple = (pos.realized_pnl / init_risk) if init_risk > 0 else 0.0

        # Mandats-Garantie Q-01: Exakte Equity-Verrechnung
        self.equity += net_pnl

        self._persist_trade(pos)
        logger.info(
            "Trade %s geschlossen (%s) @ %.4f, Realisierter Net-PnL: %.2f USDT (R: %.2f)",
            pos.symbol,
            reason,
            final_price,
            pos.realized_pnl,
            pos.r_multiple,
        )

    def _persist_trade(self, pos: PaperPosition) -> None:
        if not self.conn:
            return
        stored_notional = pos.initial_qty * pos.entry_price
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO trades (
                    id, source, symbol, dir, status, entry_price, current_sl, initial_sl,
                    tp1, tp2, tp1_hit, notional, margin, leverage, opened_at_ms,
                    closed_at_ms, exit_price, exit_reason, realized_pnl, fees,
                    engine_version, record_schema, entry_fee, timeframe, remaining_qty
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    current_sl = excluded.current_sl,
                    tp1_hit = excluded.tp1_hit,
                    closed_at_ms = excluded.closed_at_ms,
                    exit_price = excluded.exit_price,
                    exit_reason = excluded.exit_reason,
                    realized_pnl = excluded.realized_pnl,
                    fees = excluded.fees,
                    remaining_qty = excluded.remaining_qty
                """,
                (
                    pos.trade_id,
                    "server",
                    pos.symbol,
                    pos.direction,
                    "closed" if pos.status == "closed" else "open",
                    str(pos.entry_price),
                    str(pos.sl_price),
                    str(pos.initial_sl_price),
                    str(pos.tp1_price),
                    str(pos.tp2_price),
                    1 if pos.tp1_hit else 0,
                    str(stored_notional),
                    str(pos.margin),
                    pos.leverage,
                    pos.entry_time_ms,
                    pos.exit_time_ms,
                    str(pos.exit_price) if pos.exit_price is not None else None,
                    pos.exit_reason,
                    str(pos.realized_pnl),
                    str(pos.total_fees),
                    "3.0.0-dev",
                    3,
                    str(pos.initial_qty * pos.entry_price * self.config.taker_fee),
                    pos.timeframe,
                    str(pos.qty),
                ),
            )
