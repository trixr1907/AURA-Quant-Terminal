"""Hintergrund-Worker fuer AURA v3 (aura.runner.worker).

Fuehrt Marktdaten-Polling, Signal-Scanning, Risikobewertung, Paper-Trading
und Benachrichtigungen vollstaendig autonom auf dem Server (Proxmox/Docker) aus.
Dokumentiert in docs/ARCHITECTURE.md und ADR-0003.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from aura.core.scoring import analyze_candles
from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.models import Candle, ValidationReport
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
        time_provider: Callable[[], float] = time.time,
        max_stale_age_sec: float = 7200.0,
        instance_id: str | None = None,
    ):
        self.db_path = db_path
        self.poll_interval = poll_interval_sec
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_open_positions = max_open_positions
        self.long_threshold = long_threshold
        self.short_threshold = short_threshold
        self.time_provider = time_provider
        self.max_stale_age_sec = max_stale_age_sec
        self.instance_id = instance_id or f"w_{os.getpid()}_{uuid.uuid4().hex[:6]}"
        self._running = False

        self.conn = connect(self.db_path)
        self.sm = RunnerStateMachine(SystemState.STARTING)
        self.adapter: Any = BitgetMarketAdapter()
        engine_cfg = EngineConfig(risk_per_trade_pct=self.risk_per_trade_pct, max_open_positions=self.max_open_positions)
        self.engine = PaperTradingEngine(config=engine_cfg, conn=self.conn)

        ntfy_url = os.environ.get("AURA_NTFY_URL", "")
        ntfy_cfg = NotificationConfig(enabled=bool(ntfy_url), topic_url=ntfy_url)
        self.notifier = NotificationDispatcher(config=ntfy_cfg, conn=self.conn)

        # R1: Persistierten Zustand (Not-Halt, aktive Konfig) und R4 (verwaiste Claims) wiederherstellen
        self._restore_persisted_state()

    def _snapshot_engine_state(self) -> dict[str, Any]:
        """Erstellt einen In-Memory Snapshot des Engine-Zustands fuer atomare Transaktions-Rollbacks."""
        return {
            "open_positions": copy.deepcopy(self.engine.open_positions),
            "closed_positions": copy.deepcopy(self.engine.closed_positions),
            "equity": self.engine.equity,
        }

    def _restore_engine_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Stellt den In-Memory Engine-Zustand nach einem Rollback synchron wieder her."""
        self.engine.open_positions = snapshot["open_positions"]
        self.engine.closed_positions = snapshot["closed_positions"]
        self.engine.equity = snapshot["equity"]

    def _is_candle_feed_healthy(
        self, candles: list[Candle], report: ValidationReport, now_ms: int
    ) -> tuple[bool, str]:
        """Prueft Schema-Validitaet, Mindest-Historie und zeitliche Frische eines Feeds."""
        if not report or not report.is_valid:
            return False, "ValidationReport unvollstaendig oder ungueltig"
        if not candles:
            return False, "Keine Kerzen empfangen"
        closed = [c for c in candles if c.is_closed]
        if len(closed) < 30:
            return False, f"Zu wenige geschlossene Kerzen ({len(closed)} < 30)"
        last_bar = closed[-1]
        bar_end_ms = last_bar.time_ms + 3600_000
        max_stale_ms = int(self.max_stale_age_sec * 1000)
        if (now_ms - bar_end_ms) > max_stale_ms:
            return False, f"Feed veraltet: Letzter geschlossener Bar endete vor {(now_ms - bar_end_ms)/1000:.0f}s (max: {self.max_stale_age_sec:.0f}s)"
        if last_bar.time_ms > now_ms + 60_000:
            return False, "Feed-Zeitstempel liegt in der Zukunft"
        return True, "OK"

    def _restore_persisted_state(self) -> None:
        """Stellt aktive Konfiguration, Not-Halt-Zustand und verwaiste Bar-Claims aus der DB wieder her."""
        # 1. R4: Verwaiste 'processing'-Bar-Claims aus vorangegangenen Abstuerzen aufraeumen
        try:
            with self.conn:
                self.conn.execute("DELETE FROM processed_bars WHERE decision = 'processing'")
        except Exception as ex:
            logger.debug("processed_bars Clean-Up: %s", ex)

        # 2. R1: Zuletzt angewendete Konfiguration aus config_revisions laden
        try:
            cur = self.conn.execute(
                "SELECT payload, rev FROM config_revisions WHERE applied_at_ms IS NOT NULL ORDER BY rev DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row and row["payload"]:
                cfg = json.loads(row["payload"])
                if "risk_per_trade_pct" in cfg:
                    self.risk_per_trade_pct = float(cfg["risk_per_trade_pct"])
                if "max_open_positions" in cfg:
                    self.max_open_positions = int(cfg["max_open_positions"])
                if "long_threshold" in cfg:
                    self.long_threshold = float(cfg["long_threshold"])
                if "short_threshold" in cfg:
                    self.short_threshold = float(cfg["short_threshold"])
                self.engine.config = EngineConfig(
                    risk_per_trade_pct=self.risk_per_trade_pct,
                    max_open_positions=self.max_open_positions,
                )
                logger.info("Aktive Konfigurations-Revision %s wiederhergestellt", row["rev"])
        except Exception as ex:
            logger.warning("Konnte persistierte Konfiguration nicht laden: %s", ex)

        # 3. R1: Persistierten Not-Halt wiederherstellen
        try:
            cur = self.conn.execute(
                "SELECT type, payload FROM commands WHERE type IN ('halt', 'resume') AND status = 'applied' "
                "ORDER BY applied_at_ms DESC, id DESC LIMIT 1"
            )
            last_cmd = cur.fetchone()

            cur = self.conn.execute("SELECT fsm_state, reason FROM runner_state WHERE id = 1")
            last_runner = cur.fetchone()

            should_halt = False
            halt_reason = "Persistierter Not-Halt nach Neustart wiederhergestellt"
            if last_cmd and last_cmd["type"] == "halt":
                should_halt = True
                p = json.loads(last_cmd["payload"] or "{}")
                halt_reason = str(p.get("reason") or halt_reason)
            elif last_runner and last_runner["fsm_state"] == "HALTED":
                should_halt = True
                halt_reason = str(last_runner["reason"] or halt_reason)

            if should_halt and not self.sm.is_halted:
                self.sm.emergency_halt(halt_reason)
                logger.warning("Not-Halt aus persistentem Zustand wiederhergestellt: %s", halt_reason)
        except Exception as ex:
            logger.warning("Konnte Not-Halt-Status nicht pruefen: %s", ex)

    def start(self, max_cycles: int | None = None) -> None:
        """Startet die Worker-Schleife."""
        self._running = True
        self._setup_signals()
        logger.info("AURA v3 Worker gestartet (DB: %s, Symbole: %s)", self.db_path, self.symbols)

        # Persistierten Zustand vor Start-Uebergaengen aktualisieren
        self._restore_persisted_state()

        if self.sm.is_halted:
            logger.warning("Worker startet im Zustand HALTED (persistierter Not-Halt aktiv: %s)", self.sm.halt_reason)
        else:
            self.sm.transition_to(SystemState.WARMING_UP, "Initialisiere Marktdaten-Feeds")
            warmup_ok = self._warmup_feeds()
            if not warmup_ok:
                logger.warning("Warmup unvollstaendig (Marktdaten offline oder unzureichend). Gehe in DEGRADED.")
                self.sm.mark_degraded("Marktdaten beim Start unvollstaendig oder offline")
            else:
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

    def _warmup_feeds(self) -> bool:
        all_ok = True
        now_ms = int(self.time_provider() * 1000)
        for sym in self.symbols:
            try:
                candles, rep = self.adapter.fetch_candles(sym, granularity="1H", limit=100)
                healthy, err = self._is_candle_feed_healthy(candles, rep, now_ms)
                if healthy:
                    logger.info("Warmup erfolgreich fuer %s (%d Bars geladen)", sym, len(candles))
                else:
                    all_ok = False
                    logger.warning("Warmup Warnung fuer %s: %s (Bars: %d)", sym, err, len(candles) if candles else 0)
            except Exception as ex:
                all_ok = False
                logger.warning("Konnte Warmup fuer %s nicht abschliessen: %s", sym, ex)
        return all_ok

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
                result = f"worker halted by {self.instance_id}"
            elif command_type == "resume":
                applied = self.sm.resume_from_halt(str(payload.get("reason") or "Control-Plane Resume"))
                result = f"worker recovering ({self.instance_id})" if applied else "worker rejected resume"
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
                        (int(self.time_provider() * 1000), revision),
                    )
                applied = True
                result = f"config revision {revision} applied by {self.instance_id}"
            else:
                result = f"unsupported command type: {command_type}"

            with self.conn:
                self.conn.execute(
                    "UPDATE commands SET status = ?, applied_at_ms = ?, result = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (
                        "applied" if applied else "rejected",
                        int(self.time_provider() * 1000),
                        result,
                        command_id,
                    ),
                )

    def _run_cycle(self, cycle: int) -> None:
        logger.debug("Worker-Zyklus #%d gestartet...", cycle)
        self._apply_control_plane_commands()

        now_ms = int(self.time_provider() * 1000)

        # Phase 1: Globale Validierung aller Feeds VOR Trade-Entscheidungen (F2)
        symbol_data: dict[str, tuple[list[Candle], list[Candle]]] = {}
        all_feeds_valid = True
        invalid_reasons: list[str] = []

        for sym in self.symbols:
            try:
                candles, rep = self.adapter.fetch_candles(sym, granularity="1H", limit=60)
                healthy, err = self._is_candle_feed_healthy(candles, rep, now_ms)
                if not healthy:
                    all_feeds_valid = False
                    invalid_reasons.append(f"{sym}: {err}")
                    continue

                self._persist_candles(sym, "1h", candles)
                closed_candles = [c for c in candles if c.is_closed]
                if len(closed_candles) < 30:
                    all_feeds_valid = False
                    invalid_reasons.append(f"{sym}: Zu wenige geschlossene Kerzen ({len(closed_candles)} < 30)")
                    continue

                symbol_data[sym] = (candles, closed_candles)
            except Exception as ex:
                all_feeds_valid = False
                invalid_reasons.append(f"{sym}: Ausnahme {ex}")
                logger.warning("Fehler beim Abruf von %s in Zyklus #%d: %s", sym, cycle, ex)

        # R2 / F2 / F3: State-Transitions basierend auf Feed-Zustand
        if not all_feeds_valid or len(self.symbols) == 0:
            err_summary = "; ".join(invalid_reasons) or "Keine Symbole konfiguriert"
            if self.sm.current_state == SystemState.RUNNING:
                logger.warning("Feeds nicht mehr vollstaendig valide. Schalte RUNNING -> DEGRADED: %s", err_summary)
                self.sm.mark_degraded(f"Feeds unvollstaendig oder veraltet: {err_summary}")
        else:
            if self.sm.current_state in (SystemState.RECOVERING, SystemState.DEGRADED, SystemState.WARMING_UP):
                logger.info("Recovery/Warmup erfolgreich: Alle Feeds synchron, aktuell und valide. Schalte -> RUNNING")
                self.sm.mark_healthy("Recovery erfolgreich: Alle Feeds synchron, aktuell und valide")

        # Phase 2: Bar-Verarbeitung fuer verfuegbare Symbole (F1: atomar mit In-Memory-Rollback)
        for sym, (candles, closed_candles) in symbol_data.items():
            last_bar = closed_candles[-1]
            try:
                self._process_closed_bar(sym, last_bar, closed_candles)
            except Exception as ex:
                logger.warning("Fehler beim Verarbeiten von Bar fuer %s in Zyklus #%d: %s", sym, cycle, ex)

        self._update_runner_state(cycle)

    def _process_closed_bar(self, sym: str, last_bar: Candle, closed_candles: list[Candle]) -> None:
        engine_snapshot = self._snapshot_engine_state()
        pending_alerts: list[dict[str, Any]] = []

        try:
            with self.conn:
                # 1. Bar beanspruchen
                if not self._claim_closed_bar(sym, "1h", last_bar.time_ms):
                    return

                # 2. Bar-Updates fuer bestehende offene Positionen (SL, TP1, TP2, Timestop)
                closed = self.engine.on_bar_update(
                    symbol=sym,
                    high=last_bar.high,
                    low=last_bar.low,
                    close=last_bar.close,
                    bar_time_ms=last_bar.time_ms,
                )
                for pos in closed:
                    pending_alerts.append({
                        "title": f"AURA Trade Closed: {pos.symbol}",
                        "message": f"Grund: {pos.exit_reason} @ {pos.exit_price:.4f} | Realisierter PnL: {pos.realized_pnl:+.2f} USDT",
                        "priority": 4,
                        "event_type": "TRADE_CLOSE",
                    })

                # 3. Signal-Scanning fuer neue Entries (nur wenn System RUNNING ist)
                trade_opened_id = None
                if self.sm.can_open_new_trades():
                    has_open = any(p.symbol == sym for p in self.engine.open_positions.values())
                    if (
                        len(self.engine.open_positions) < self.max_open_positions
                        and not has_open
                        and self._liquidity_is_verified(sym, last_bar.time_ms)
                    ):
                        pos = self._evaluate_and_enter(sym, closed_candles)
                        if pos is not None:
                            trade_opened_id = pos.trade_id
                    elif has_open:
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", f"Bereits offene Position fuer {sym}")
                    elif len(self.engine.open_positions) >= self.max_open_positions:
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", f"Max Positionen ({self.max_open_positions}) erreicht")
                    elif not self._liquidity_is_verified(sym, last_bar.time_ms):
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", "Liquiditaet nicht verifiziert")
                elif self.sm.is_halted:
                    self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", "Not-Halt aktiv")

                # 4. Bar-Verarbeitung abschliessen (decision='completed')
                self._complete_closed_bar(
                    symbol=sym,
                    timeframe="1h",
                    open_time_ms=last_bar.time_ms,
                    decision="completed",
                    trade_id=trade_opened_id,
                )

            # Transaktion erfolgreich committet: Benachrichtigungen zustellen
            for alert in pending_alerts:
                try:
                    self.notifier.send_alert(**alert)
                except Exception as ex:
                    logger.debug("Notifier Fehler: %s", ex)

        except BaseException:
            # Bei Crash / Exception: Rollback in DB durch 'with self.conn:'.
            # In-Memory-Zustand synchron zuruecksetzen!
            self._restore_engine_snapshot(engine_snapshot)
            raise

    def _update_runner_state(self, cycle: int) -> None:
        fsm_state = self.sm.current_state.value
        raw_reason = self.sm.reason or "Normalbetrieb"
        reason = f"[{self.instance_id}] {raw_reason}"
        now_ms = int(self.time_provider() * 1000)
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
        row = self.conn.execute(
            "SELECT decision FROM processed_bars "
            "WHERE source = 'bitget' AND symbol = ? AND timeframe = ? AND open_time_ms = ?",
            (symbol, timeframe, open_time_ms),
        ).fetchone()
        if row is not None:
            return False
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO processed_bars "
            "(source, symbol, timeframe, open_time_ms, processed_at_ms, decision) "
            "VALUES ('bitget', ?, ?, ?, ?, 'processing')",
            (symbol, timeframe, open_time_ms, int(self.time_provider() * 1000)),
        )
        return cursor.rowcount == 1

    def _complete_closed_bar(
        self,
        symbol: str,
        timeframe: str,
        open_time_ms: int,
        decision: str = "completed",
        trade_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.conn.execute(
            "UPDATE processed_bars SET decision = ?, trade_id = ?, detail = ?, processed_at_ms = ? "
            "WHERE source = 'bitget' AND symbol = ? AND timeframe = ? AND open_time_ms = ?",
            (decision, trade_id, detail, int(self.time_provider() * 1000), symbol, timeframe, open_time_ms),
        )

    def _evaluate_and_enter(self, symbol: str, candles: list[Candle]):
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
            return None

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
                return pos
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AURA v3 Autonomer Hintergrund-Worker")
    parser.add_argument("--db", default=os.environ.get("AURA_DB_PATH", "aura_state.db"), help="Pfad zur SQLite-Datenbank")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT", help="Kommagetrennte Symbole")
    parser.add_argument("--interval", type=float, default=60.0, help="Poll-Intervall in Sekunden")
    parser.add_argument("--test-mode", action="store_true", help="Synthetischer Determinismus-Feed fuer Offline-/Lifecycle-Tests")
    args = parser.parse_args()

    sym_list = [s.strip() for s in args.symbols.split(",") if s.strip()]
    worker = AuraWorkerService(db_path=args.db, poll_interval_sec=args.interval, symbols=sym_list)
    if args.test_mode or os.environ.get("AURA_TEST_FEED") == "1":
        class DeterministicFreshFeed:
            def fetch_candles(self, symbol: str, granularity: str = "1H", limit: int = 60):
                now_s = int(time.time())
                now_h = now_s - (now_s % 3600)
                candles = [
                    Candle(
                        time_ms=(now_h - (39 - i) * 3600) * 1000,
                        open=50000.0 + i * 10,
                        high=50050.0 + i * 10,
                        low=49950.0 + i * 10,
                        close=50020.0 + i * 10,
                        volume=100.0,
                        is_closed=True,
                    )
                    for i in range(40)
                ]
                return candles, ValidationReport(is_valid=True, total_checked=len(candles), errors=[])
        worker.adapter = DeterministicFreshFeed()
    worker.start()
