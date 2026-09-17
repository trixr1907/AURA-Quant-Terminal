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
import threading
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from typing import Any, Sequence

from aura.core.risk import PositionSize, round_price_to_tick, size_position

logger = logging.getLogger("aura.runner.paper_engine")


@dataclass(frozen=True)
class PaperExecutionPlan:
    symbol: str
    direction: int  # 1 = Long, -1 = Short
    reference_price: Decimal
    effective_fill: Decimal
    sl_price: Decimal
    tp1_price: Decimal
    tp2_price: Decimal
    stop_dist: Decimal
    qty: Decimal
    contracts: int
    margin: Decimal
    leverage: int
    final_notional: Decimal
    risk_budget: Decimal
    nominal_stop_risk: Decimal
    entry_fee: Decimal
    cost_adjusted_stop_risk: Decimal
    spec: dict[str, Any]
    levels_valid: bool = True
    error_reason: str | None = None


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
        self._lock = threading.RLock()
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
        with self._lock:
            cur = self.conn.cursor()

            # Vor dem Neuladen bestehende Speicherlisten zuruecksetzen (verhindert Duplikate bei wiederholtem Aufruf)
            self.open_positions.clear()
            self.closed_positions.clear()

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

    def create_execution_plan(
        self,
        symbol: str,
        direction: int,
        reference_price: Decimal | float,
        sl_price: Decimal | float,
        tp1_price: Decimal | float,
        tp2_price: Decimal | float,
        spec: dict[str, Any] | None = None,
        leverage: int = 10,
        risk_budget: Decimal | float | None = None,
    ) -> PaperExecutionPlan:
        """Erzeugt einen kanonischen Ausfuehrungsplan auf dem effektiven Fill nach Slippage und Tick."""
        try:
            d_ref = Decimal(str(reference_price))
            d_sl = Decimal(str(sl_price))
            d_tp1 = Decimal(str(tp1_price))
            d_tp2 = Decimal(str(tp2_price))
        except (InvalidOperation, ValueError, TypeError) as ex:
            return PaperExecutionPlan(
                symbol=symbol,
                direction=direction,
                reference_price=Decimal("0"),
                effective_fill=Decimal("0"),
                sl_price=Decimal("0"),
                tp1_price=Decimal("0"),
                tp2_price=Decimal("0"),
                stop_dist=Decimal("0"),
                qty=Decimal("0"),
                contracts=0,
                margin=Decimal("0"),
                leverage=leverage,
                final_notional=Decimal("0"),
                risk_budget=Decimal("0"),
                nominal_stop_risk=Decimal("0"),
                entry_fee=Decimal("0"),
                cost_adjusted_stop_risk=Decimal("0"),
                spec=spec or {},
                levels_valid=False,
                error_reason=f"Ungueltige Dezimalwerte: {ex}",
            )

        price_tick_str = str(spec.get("priceTick") or spec.get("price_tick") or "0.0001") if spec else "0.0001"
        try:
            price_tick = Decimal(price_tick_str)
            if price_tick <= 0 or not price_tick.is_finite():
                price_tick = Decimal("0.0001")
        except (InvalidOperation, ValueError):
            price_tick = Decimal("0.0001")

        # Richtungs- und ordertypspezifische Quantisierung der Schutz- und Ziellevel
        if direction == 1:
            d_sl = round_price_to_tick(d_sl, price_tick, rounding=ROUND_DOWN)
            d_tp1 = round_price_to_tick(d_tp1, price_tick, rounding=ROUND_UP)
            d_tp2 = round_price_to_tick(d_tp2, price_tick, rounding=ROUND_UP)
        else:
            d_sl = round_price_to_tick(d_sl, price_tick, rounding=ROUND_UP)
            d_tp1 = round_price_to_tick(d_tp1, price_tick, rounding=ROUND_DOWN)
            d_tp2 = round_price_to_tick(d_tp2, price_tick, rounding=ROUND_DOWN)

        # Effektiver Fill-Preis nach Slippage und Tick-Quantisierung
        slip_bps = Decimal(str(self.config.slippage_bps))
        slip_factor = Decimal("1.0") + (slip_bps / Decimal("10000.0")) * Decimal(str(direction))
        raw_fill = d_ref * slip_factor
        effective_fill = round_price_to_tick(raw_fill, price_tick, rounding=ROUND_HALF_UP)

        # Strikte Pruefung der Level-Reihenfolge gegen den effektiven Fill
        if direction == 1:
            if not (d_sl < effective_fill < d_tp1 <= d_tp2):
                return PaperExecutionPlan(
                    symbol=symbol,
                    direction=direction,
                    reference_price=d_ref,
                    effective_fill=effective_fill,
                    sl_price=d_sl,
                    tp1_price=d_tp1,
                    tp2_price=d_tp2,
                    stop_dist=Decimal("0"),
                    qty=Decimal("0"),
                    contracts=0,
                    margin=Decimal("0"),
                    leverage=leverage,
                    final_notional=Decimal("0"),
                    risk_budget=Decimal("0"),
                    nominal_stop_risk=Decimal("0"),
                    entry_fee=Decimal("0"),
                    cost_adjusted_stop_risk=Decimal("0"),
                    spec=spec or {},
                    levels_valid=False,
                    error_reason="Level-Reihenfolge nach effektivem Fill ungueltig (SL >= Entry oder Entry >= TP1)",
                )
            stop_dist = effective_fill - d_sl
        else:
            if not (d_sl > effective_fill > d_tp1 >= d_tp2):
                return PaperExecutionPlan(
                    symbol=symbol,
                    direction=direction,
                    reference_price=d_ref,
                    effective_fill=effective_fill,
                    sl_price=d_sl,
                    tp1_price=d_tp1,
                    tp2_price=d_tp2,
                    stop_dist=Decimal("0"),
                    qty=Decimal("0"),
                    contracts=0,
                    margin=Decimal("0"),
                    leverage=leverage,
                    final_notional=Decimal("0"),
                    risk_budget=Decimal("0"),
                    nominal_stop_risk=Decimal("0"),
                    entry_fee=Decimal("0"),
                    cost_adjusted_stop_risk=Decimal("0"),
                    spec=spec or {},
                    levels_valid=False,
                    error_reason="Level-Reihenfolge nach effektivem Fill ungueltig (SL <= Entry oder Entry <= TP1)",
                )
            stop_dist = d_sl - effective_fill

        if stop_dist <= 0:
            return PaperExecutionPlan(
                symbol=symbol,
                direction=direction,
                reference_price=d_ref,
                effective_fill=effective_fill,
                sl_price=d_sl,
                tp1_price=d_tp1,
                tp2_price=d_tp2,
                stop_dist=Decimal("0"),
                qty=Decimal("0"),
                contracts=0,
                margin=Decimal("0"),
                leverage=leverage,
                final_notional=Decimal("0"),
                risk_budget=Decimal("0"),
                nominal_stop_risk=Decimal("0"),
                entry_fee=Decimal("0"),
                cost_adjusted_stop_risk=Decimal("0"),
                spec=spec or {},
                levels_valid=False,
                error_reason="Stop-Distanz nach effektivem Fill <= 0",
            )

        # Risikobudget bestimmen
        if risk_budget is None:
            budget = Decimal(str(self.equity)) * Decimal(str(self.config.risk_per_trade_pct)) / Decimal("100.0")
        else:
            budget = Decimal(str(risk_budget))

        # Groessenberechnung strikt auf dem effektiven Fill und der effektiven Stop-Distanz
        sized = size_position(budget, effective_fill, stop_dist, leverage=leverage, spec=spec)
        if sized.qty <= 0 or sized.contracts <= 0:
            return PaperExecutionPlan(
                symbol=symbol,
                direction=direction,
                reference_price=d_ref,
                effective_fill=effective_fill,
                sl_price=d_sl,
                tp1_price=d_tp1,
                tp2_price=d_tp2,
                stop_dist=stop_dist,
                qty=Decimal("0"),
                contracts=0,
                margin=Decimal("0"),
                leverage=leverage,
                final_notional=Decimal("0"),
                risk_budget=budget,
                nominal_stop_risk=Decimal("0"),
                entry_fee=Decimal("0"),
                cost_adjusted_stop_risk=Decimal("0"),
                spec=spec or {},
                levels_valid=False,
                error_reason="Groesse unter Mindestanforderung (contracts=0)",
            )

        d_qty = Decimal(str(sized.qty))
        nominal_stop_risk = d_qty * stop_dist
        if nominal_stop_risk > budget:
            return PaperExecutionPlan(
                symbol=symbol,
                direction=direction,
                reference_price=d_ref,
                effective_fill=effective_fill,
                sl_price=d_sl,
                tp1_price=d_tp1,
                tp2_price=d_tp2,
                stop_dist=stop_dist,
                qty=d_qty,
                contracts=sized.contracts,
                margin=Decimal(str(sized.margin)),
                leverage=leverage,
                final_notional=d_qty * effective_fill,
                risk_budget=budget,
                nominal_stop_risk=nominal_stop_risk,
                entry_fee=Decimal("0"),
                cost_adjusted_stop_risk=Decimal("0"),
                spec=spec or {},
                levels_valid=False,
                error_reason=f"Nominales Stop-Risiko ({nominal_stop_risk}) ueberschreitet Budget ({budget})",
            )

        taker_fee_rate = Decimal(str(self.config.taker_fee))
        entry_fee = d_qty * effective_fill * taker_fee_rate
        exit_fee_sl = d_qty * d_sl * taker_fee_rate
        cost_adjusted_stop_risk = nominal_stop_risk + entry_fee + exit_fee_sl
        final_notional = d_qty * effective_fill

        return PaperExecutionPlan(
            symbol=symbol,
            direction=direction,
            reference_price=d_ref,
            effective_fill=effective_fill,
            sl_price=d_sl,
            tp1_price=d_tp1,
            tp2_price=d_tp2,
            stop_dist=stop_dist,
            qty=d_qty,
            contracts=sized.contracts,
            margin=Decimal(str(sized.margin)),
            leverage=leverage,
            final_notional=final_notional,
            risk_budget=budget,
            nominal_stop_risk=nominal_stop_risk,
            entry_fee=entry_fee,
            cost_adjusted_stop_risk=cost_adjusted_stop_risk,
            spec=spec or {},
            levels_valid=True,
            error_reason=None,
        )

    def execute_plan(
        self,
        plan: PaperExecutionPlan,
        timeframe: str = "1H",
        score: float = 65.0,
        current_time_ms: int | None = None,
    ) -> PaperPosition | None:
        """Bucht einen zuvor geprueften und freigegebenen Ausfuehrungsplan unveraendert."""
        if not plan.levels_valid:
            logger.warning("Trade abgelehnt: Ungueltiger Plan (%s)", plan.error_reason)
            return None

        if len(self.open_positions) >= self.config.max_open_positions:
            logger.info("Trade abgelehnt: Max offene Positionen (%d) erreicht", self.config.max_open_positions)
            return None

        for p in self.open_positions.values():
            if p.symbol == plan.symbol:
                logger.info("Trade abgelehnt: Bereits offene Position fuer %s", plan.symbol)
                return None

        now_ms = current_time_ms or int(time.time() * 1000)
        trade_id = f"trade_{uuid.uuid4().hex[:12]}"
        pos = PaperPosition(
            trade_id=trade_id,
            symbol=plan.symbol,
            timeframe=timeframe,
            direction=plan.direction,
            entry_price=float(plan.effective_fill),
            sl_price=float(plan.sl_price),
            initial_sl_price=float(plan.sl_price),
            tp1_price=float(plan.tp1_price),
            tp2_price=float(plan.tp2_price),
            qty=float(plan.qty),
            contracts=plan.contracts,
            initial_qty=float(plan.qty),
            margin=float(plan.margin),
            leverage=plan.leverage,
            entry_time_ms=now_ms,
            status="open",
            total_fees=float(plan.entry_fee),
            max_price=float(plan.effective_fill),
            min_price=float(plan.effective_fill),
            setup_score=score,
        )

        self.open_positions[trade_id] = pos
        # Entry-Gebuehr ist sofort realisiert und reduziert die Kontoequity.
        self.equity -= float(plan.entry_fee)
        self._persist_trade(pos)
        logger.info(
            "Paper Trade geoeffnet: %s %s @ %.4f (SL: %.4f, TP1: %.4f, Qty: %.4f, Notional: %.2f)",
            "LONG" if plan.direction == 1 else "SHORT",
            plan.symbol,
            pos.entry_price,
            pos.sl_price,
            pos.tp1_price,
            pos.qty,
            float(plan.final_notional),
        )
        return pos

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
        plan: PaperExecutionPlan | None = None,
    ) -> PaperPosition | None:
        """Eröffnet eine neue Paper-Position mit Gebühren- und Slippage-Abzug."""
        if plan is not None:
            return self.execute_plan(plan, timeframe=timeframe, score=score, current_time_ms=current_time_ms)

        plan = self.create_execution_plan(
            symbol=symbol,
            direction=direction,
            reference_price=entry_price,
            sl_price=sl_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            spec=spec,
            leverage=leverage,
        )
        return self.execute_plan(plan, timeframe=timeframe, score=score, current_time_ms=current_time_ms)

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
        # Preis-Breakeven: Stop-Loss wird auf den tatsaechlichen Entry-Fill-Preis gesetzt.
        # Wichtig: Dies ist ein Preis-Breakeven, keine absolute Netto-Verlustfreiheit,
        # da bei Ausloesung des Stops fuer die verbleibende Restmenge noch Exit-Gebuehren
        # (Taker-Fee) und potenzielle Slippage anfallen.
        pos.sl_price = pos.entry_price
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
