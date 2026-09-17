"""Hintergrund-Worker fuer AURA v3 (aura.runner.worker).

Fuehrt Marktdaten-Polling, Signal-Scanning, Risikobewertung, Paper-Trading
und Benachrichtigungen vollstaendig autonom auf dem Server (Proxmox/Docker) aus.
Dokumentiert in docs/ARCHITECTURE.md und ADR-0003.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from aura.core.scoring import analyze_candles
from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.models import Candle
from aura.runner.notifier import NotificationConfig, NotificationDispatcher
from aura.runner.paper_engine import EngineConfig, PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.store.db import connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("aura.worker")


class AuraWorkerService:
    """Autonomer 24/7 Hintergrunddienst."""

    def __init__(
        self,
        db_path: str = "aura_state.db",
        poll_interval_sec: int = 60,
        symbols: list[str] | None = None,
        risk_per_trade_pct: float = 1.0,
        max_open_positions: int = 3,
        long_threshold: float = 75.0,
        short_threshold: float = 25.0,
    ):
        self.db_path = db_path
        self.poll_interval = poll_interval_sec
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_open_positions = max_open_positions
        self.long_threshold = long_threshold
        self.short_threshold = short_threshold
        self._running = False

        self.conn = connect(self.db_path)
        self.sm = RunnerStateMachine(SystemState.STARTING)
        self.adapter = BitgetMarketAdapter()
        engine_cfg = EngineConfig(risk_per_trade_pct=self.risk_per_trade_pct, max_open_positions=self.max_open_positions)
        self.engine = PaperTradingEngine(config=engine_cfg, conn=self.conn)

        ntfy_url = os.environ.get("AURA_NTFY_URL", "")
        ntfy_cfg = NotificationConfig(enabled=bool(ntfy_url), topic_url=ntfy_url)
        self.notifier = NotificationDispatcher(config=ntfy_cfg, conn=self.conn)

    def start(self, max_cycles: int | None = None) -> None:
        """Startet die Worker-Schleife."""
        self._running = True
        self._setup_signals()
        logger.info("AURA v3 Worker gestartet (DB: %s, Symbole: %s)", self.db_path, self.symbols)

        self.sm.transition_to(SystemState.WARMING_UP, "Initialisiere Marktdaten-Feeds")
        self._warmup_feeds()
        self.sm.transition_to(SystemState.RUNNING, "Feeds initialisiert, bereit fuer Signal-Scanning & Execution")

        cycle = 0
        while self._running:
            cycle += 1
            try:
                self._run_cycle(cycle)
            except Exception as ex:
                logger.error("Unerwarteter Fehler im Worker-Zyklus #%d: %s", cycle, ex, exc_info=True)
                self.sm.mark_degraded(f"Zyklus-Fehler: {ex}")

            if max_cycles is not None and cycle >= max_cycles:
                break

            time.sleep(self.poll_interval)

        logger.info("AURA v3 Worker beendet.")

    def stop(self) -> None:
        self._running = False

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGINT, lambda s, f: self.stop())
            signal.signal(signal.SIGTERM, lambda s, f: self.stop())
        except (ValueError, AttributeError):
            # Nicht im Main-Thread (z.B. bei Tests)
            pass

    def _warmup_feeds(self) -> None:
        for sym in self.symbols:
            try:
                candles, rep = self.adapter.fetch_candles(sym, granularity="1H", limit=100)
                if rep.is_valid:
                    logger.info("Warmup erfolgreich fuer %s (%d Bars geladen)", sym, len(candles))
                else:
                    logger.warning("Warmup Warnung fuer %s: %s", sym, rep.errors)
            except Exception as ex:
                logger.warning("Konnte Warmup fuer %s nicht abschliessen: %s", sym, ex)

    def _apply_control_plane_commands(self) -> None:
        """Applies pending API commands through the shared SQLite control plane."""
        rows = self.conn.execute(
            "SELECT id, type, payload FROM commands WHERE status = 'pending' ORDER BY created_at_ms, id"
        ).fetchall()
        for row in rows:
            command_id = row["id"]
            command_type = row["type"]
            payload = json.loads(row["payload"] or "{}")
            applied = False
            result = ""

            if command_type == "halt":
                self.sm.emergency_halt(str(payload.get("reason") or "Control-Plane Not-Halt"))
                applied = True
                result = "worker halted"
            elif command_type == "resume":
                applied = self.sm.resume_from_halt(str(payload.get("reason") or "Control-Plane Resume"))
                result = "worker recovering" if applied else "worker rejected resume"
            elif command_type == "set_config":
                config = payload.get("config") or {}
                revision = int(payload.get("rev"))
                self.engine.config.risk_per_trade_pct = float(config["risk_per_trade_pct"])
                self.engine.config.max_open_positions = int(config["max_open_positions"])
                self.max_open_positions = int(config["max_open_positions"])
                self.long_threshold = float(config["long_threshold"])
                self.short_threshold = float(config["short_threshold"])
                with self.conn:
                    self.conn.execute(
                        "UPDATE config_revisions SET applied_at_ms = ? WHERE rev = ? AND applied_at_ms IS NULL",
                        (int(time.time() * 1000), revision),
                    )
                applied = True
                result = f"config revision {revision} applied"
            else:
                result = f"unsupported command type: {command_type}"

            with self.conn:
                self.conn.execute(
                    "UPDATE commands SET status = ?, applied_at_ms = ?, result = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (
                        "applied" if applied else "rejected",
                        int(time.time() * 1000),
                        result,
                        command_id,
                    ),
                )

    def _run_cycle(self, cycle: int) -> None:
        logger.debug("Worker-Zyklus #%d gestartet...", cycle)
        self._apply_control_plane_commands()

        for sym in self.symbols:
            try:
                candles, rep = self.adapter.fetch_candles(sym, granularity="1H", limit=60)
                if not candles or not rep.is_valid or len(candles) < 30:
                    continue

                self._persist_candles(sym, "1h", candles)
                closed_candles = [c for c in candles if c.is_closed]
                if len(closed_candles) < 30:
                    continue
                last_bar = closed_candles[-1]

                # Positions are managed once for every newly closed bar.
                if not self._claim_closed_bar(sym, "1h", last_bar.time_ms):
                    continue

                # 1. Bar-Updates fuer offene Positionen (SL, TP1, TP2, Timestop)
                closed = self.engine.on_bar_update(
                    symbol=sym,
                    high=last_bar.high,
                    low=last_bar.low,
                    close=last_bar.close,
                    bar_time_ms=last_bar.time_ms,
                )
                for pos in closed:
                    self.notifier.send_alert(
                        title=f"AURA Trade Closed: {pos.symbol}",
                        message=f"Grund: {pos.exit_reason} @ {pos.exit_price:.4f} | Realisierter PnL: {pos.realized_pnl:+.2f} USDT",
                        priority=4,
                        event_type="TRADE_CLOSE",
                    )

                # 2. Signal-Scanning fuer neue Entries (nur wenn System RUNNING ist)
                if self.sm.can_open_new_trades():
                    has_open = any(p.symbol == sym for p in self.engine.open_positions.values())
                    if (
                        len(self.engine.open_positions) < self.max_open_positions
                        and not has_open
                        and self._liquidity_is_verified(sym, last_bar.time_ms)
                    ):
                        self._evaluate_and_enter(sym, closed_candles)
                    elif has_open:
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", f"Bereits offene Position fuer {sym}")
                    elif len(self.engine.open_positions) >= self.max_open_positions:
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", f"Max Positionen ({self.max_open_positions}) erreicht")
                    elif not self._liquidity_is_verified(sym, last_bar.time_ms):
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", "Liquiditaet nicht verifiziert")
                elif self.sm.is_halted:
                    self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", "Not-Halt aktiv")

            except Exception as ex:
                logger.warning("Fehler beim Verarbeiten von %s in Zyklus #%d: %s", sym, cycle, ex)

        self._update_runner_state(cycle)

    def _update_runner_state(self, cycle: int) -> None:
        fsm_state = self.sm.current_state.value
        reason = self.sm.reason or "Normalbetrieb"
        now_ms = int(time.time() * 1000)
        with self.conn:
            self.conn.execute(
                "INSERT INTO runner_state (id, fsm_state, reason, equity, cycle_count, updated_at_ms) "
                "VALUES (1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "fsm_state=excluded.fsm_state, reason=excluded.reason, equity=excluded.equity, "
                "cycle_count=excluded.cycle_count, updated_at_ms=excluded.updated_at_ms",
                (fsm_state, reason, str(self.engine.equity), cycle, now_ms),
            )

    def _log_decision(
        self,
        symbol: str,
        ts_ms: int,
        direction: int,
        score: float | None,
        decision: str,
        reason: str,
    ) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO shadow_log (ts_ms, symbol, timeframe, dir, score, decision, reject_reason, config_sha256, payload) "
                    "VALUES (?, ?, '1h', ?, ?, ?, ?, 'sha256_placeholder', '{}')",
                    (ts_ms, symbol, direction, score, decision, reason),
                )
        except Exception:
            pass

    def _liquidity_is_verified(self, symbol: str, bar_time_ms: int) -> bool:
        row = self.conn.execute(
            "SELECT active, liquidity_verified, updated_at_ms FROM universe WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            return False
        if not bool(row["active"]) or not bool(row["liquidity_verified"]):
            return False
        max_age_ms = 24 * 60 * 60 * 1000
        return 0 <= (bar_time_ms - int(row["updated_at_ms"])) <= max_age_ms

    def _persist_candles(self, symbol: str, timeframe: str, candles: list[Candle]) -> None:
        received_at_ms = int(time.time() * 1000)
        rows = []
        for candle in candles:
            source = candle.provenance.data_source if candle.provenance else "synthetic_fixture"
            source = "bitget" if source.startswith("bitget") else source
            received = candle.provenance.received_time_ms if candle.provenance else received_at_ms
            rows.append(
                (
                    source,
                    symbol,
                    timeframe,
                    candle.time_ms,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    int(candle.is_closed),
                    received,
                )
            )
        with self.conn:
            self.conn.executemany(
                "INSERT INTO candles "
                "(source, symbol, timeframe, open_time_ms, open, high, low, close, volume, closed, received_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source, symbol, timeframe, open_time_ms) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, "
                "volume=excluded.volume, closed=excluded.closed, received_at_ms=excluded.received_at_ms",
                rows,
            )

    def _claim_closed_bar(self, symbol: str, timeframe: str, open_time_ms: int) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO processed_bars "
                "(source, symbol, timeframe, open_time_ms, processed_at_ms, decision) "
                "VALUES ('bitget', ?, ?, ?, ?, 'processing')",
                (symbol, timeframe, open_time_ms, int(time.time() * 1000)),
            )
        return cursor.rowcount == 1

    def _evaluate_and_enter(self, symbol: str, candles: list[Candle]) -> None:
        """Analysiert Kerzen und eroeffnet neue Paper-Position bei hoher Konfluenz."""
        raw_list = [
            {
                "t": c.time_ms,
                "o": c.open,
                "h": c.high,
                "l": c.low,
                "c": c.close,
                "v": c.volume,
            }
            for c in candles
        ]

        analysis = analyze_candles(raw_list)
        if not analysis.score:
            return

        last_idx = len(analysis.score) - 1
        score = analysis.score[last_idx]
        current_price = candles[-1].close
        atr_val = analysis.atr[last_idx] if analysis.atr and analysis.atr[last_idx] > 0 else current_price * 0.02

        direction = None
        sl_price = 0.0
        tp1_price = 0.0
        tp2_price = 0.0

        if score >= self.long_threshold:
            direction = 1  # Long
            sl_price = current_price - 1.5 * atr_val
            tp1_price = current_price + 2.0 * atr_val
            tp2_price = current_price + 3.5 * atr_val
        elif score <= self.short_threshold:
            direction = -1  # Short
            sl_price = current_price + 1.5 * atr_val
            tp1_price = current_price - 2.0 * atr_val
            tp2_price = current_price - 3.5 * atr_val

        if direction is not None:
            spec = {"ctVal": 0.0001, "minSize": 0.0001, "minNotional": 5.0}
            pos = self.engine.open_trade(
                symbol=symbol,
                timeframe="1H",
                direction=direction,
                entry_price=current_price,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                spec=spec,
                leverage=10,
                score=score,
                current_time_ms=candles[-1].time_ms,
            )
            if pos is not None:
                dir_str = "LONG" if direction == 1 else "SHORT"
                logger.info(
                    "Neuer Paper-Trade eroeffnet: #%s %s %s @ %.4f (SL: %.4f, TP1: %.4f)",
                    pos.trade_id,
                    dir_str,
                    symbol,
                    current_price,
                    sl_price,
                    tp1_price,
                )
                self.notifier.send_alert(
                    title=f"AURA Neuer Trade: {dir_str} {symbol}",
                    message=f"Einstieg @ {current_price:.4f} | SL: {sl_price:.4f} | TP1: {tp1_price:.4f} | Qty: {pos.qty}",
                    priority=3,
                    event_type="TRADE_OPEN",
                )


if __name__ == "__main__":
    db_path = os.environ.get("AURA_DB_PATH", "aura_state.db")
    worker = AuraWorkerService(db_path=db_path)
    worker.start()
