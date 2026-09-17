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
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from pathlib import Path
from typing import Any, Callable

from aura.core.risk import round_price_to_tick, size_position
from aura.core.scoring import analyze_candles
from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.liquidity import LiquidityPolicy, POLICY_VERSION
from aura.data.market_updater import MarketDataUpdater
from aura.data.models import Candle, ValidationReport
from aura.runner.notifier import NotificationConfig, NotificationDispatcher
from aura.runner.paper_engine import EngineConfig, PaperExecutionPlan, PaperTradingEngine
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
        self.liquidity_policy = LiquidityPolicy()
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

        self.market_updater = MarketDataUpdater(
            conn=self.conn,
            adapter=self.adapter,
            policy=self.liquidity_policy,
            symbols=self.symbols,
            min_interval_sec=float(os.environ.get("AURA_MARKET_UPDATE_INTERVAL", "60.0")),
            time_provider=self.time_provider,
        )

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
        # G3 Kausalitaets-Guard: Eine als geschlossen markierte Kerze darf nicht in der Zukunft enden!
        # Erlaubt maximal 5000ms Toleranz fuer Netzwerk-Jitter und Clock-Skew
        if bar_end_ms > now_ms + 5_000:
            return False, f"Geschlossene Kerze unvollstaendig: Bar-Ende {bar_end_ms} liegt in der Zukunft (jetzt: {now_ms})"
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

        # Initialen Worker-Zustand und Instanz-ID sofort nach dem Booten in die DB schreiben
        self._update_runner_state(0)

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

        # Market Data & Liquidity Update (wenn Adapter dies unterstuetzt und nicht explizit isoliert)
        if os.environ.get("AURA_DISABLE_AUTO_SYNC") != "1" and hasattr(self.adapter, "fetch_orderbook_depth"):
            try:
                self.market_updater.adapter = self.adapter
                self.market_updater.time_provider = self.time_provider
                self.market_updater.update_cycle()
            except Exception as ex:
                logger.warning("MarketDataUpdater Zyklusfehler: %s", ex)

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
                    ):
                        pos = self._evaluate_and_enter(sym, closed_candles, pending_alerts=pending_alerts)
                        if pos is not None:
                            trade_opened_id = pos.trade_id
                    elif has_open:
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", f"Bereits offene Position fuer {sym}")
                    elif len(self.engine.open_positions) >= self.max_open_positions:
                        self._log_decision(sym, last_bar.time_ms, 0, None, "REJECTED", f"Max Positionen ({self.max_open_positions}) erreicht")
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

        except BaseException:
            # Bei Crash / Exception waehrend der DB-Transaktion:
            # Rollback in DB durch 'with self.conn:'.
            # In-Memory-Zustand synchron zuruecksetzen!
            self._restore_engine_snapshot(engine_snapshot)
            raise

        # Transaktion ERFOLGREICH committet: Benachrichtigungen erst jetzt zustellen.
        # Fehler beim Versenden gefaehrden nicht die Datenintegritaet der bereits committeten Buchung.
        for alert in pending_alerts:
            try:
                self.notifier.send_alert(**alert)
            except Exception as ex:
                logger.warning("Notifier Fehler beim Senden von %s: %s", alert.get("event_type"), ex)

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

    def persist_test_market_snapshot(
        self,
        *,
        symbol: str,
        now_ms: int,
        price_tick: str,
        qty_step: str,
        min_qty: str,
        min_notional: str,
        spread_bps: str,
        bid_depth_notional: str,
        ask_depth_notional: str,
        quote_volume_24h: str,
        source: str = "bitget_rest_v2",
        book_event_time_ms: int | None = None,
        book_fetched_at_ms: int | None = None,
        ticker_event_time_ms: int | None = None,
        ticker_fetched_at_ms: int | None = None,
        spec_fetched_at_ms: int | None = None,
    ) -> None:
        """Persist an explicitly synthetic, policy-evaluated fixture snapshot."""
        b_evt = book_event_time_ms if book_event_time_ms is not None else now_ms
        b_fetch = book_fetched_at_ms if book_fetched_at_ms is not None else now_ms
        t_evt = ticker_event_time_ms if ticker_event_time_ms is not None else now_ms
        t_fetch = ticker_fetched_at_ms if ticker_fetched_at_ms is not None else now_ms
        s_fetch = spec_fetched_at_ms if spec_fetched_at_ms is not None else now_ms

        assessment = self.liquidity_policy.evaluate_metrics(
            active=True,
            spread_bps=Decimal(spread_bps),
            bid_depth_notional=Decimal(bid_depth_notional),
            ask_depth_notional=Decimal(ask_depth_notional),
            quote_volume_24h=Decimal(quote_volume_24h),
            book_event_time_ms=b_evt,
            book_fetched_at_ms=b_fetch,
            ticker_event_time_ms=t_evt,
            ticker_fetched_at_ms=t_fetch,
            spec_fetched_at_ms=s_fetch,
            decision_time_ms=now_ms,
            book_complete=True,
        )
        overall_event_ms = min(b_evt, t_evt)
        overall_fetched_ms = min(b_fetch, t_fetch)
        with self.conn:
            self.conn.execute(
                "INSERT INTO instrument_specs "
                "(symbol, source, product_type, symbol_type, symbol_status, base_coin, quote_coin, settle_coin, "
                "price_tick, qty_step, min_qty, min_notional, maker_fee_rate, taker_fee_rate, max_leverage, "
                "event_time_ms, fetched_at_ms, raw_snapshot_sha256) "
                "VALUES (?, ?, 'USDT-FUTURES', 'perpetual', 'normal', ?, 'USDT', 'USDT', ?, ?, ?, ?, "
                "'0.0002', '0.0006', 50, ?, ?, 'synthetic_fixture') "
                "ON CONFLICT(symbol) DO UPDATE SET price_tick=excluded.price_tick, qty_step=excluded.qty_step, "
                "min_qty=excluded.min_qty, min_notional=excluded.min_notional, event_time_ms=excluded.event_time_ms, "
                "fetched_at_ms=excluded.fetched_at_ms, source=excluded.source",
                (symbol, source, symbol.removesuffix("USDT"), price_tick, qty_step, min_qty, min_notional, s_fetch, s_fetch),
            )
            self.conn.execute(
                "INSERT INTO universe "
                "(symbol, active, liquidity_verified, vol_24h, updated_at_ms, source, status, policy_version, "
                "event_time_ms, fetched_at_ms, book_event_time_ms, book_fetched_at_ms, ticker_event_time_ms, "
                "ticker_fetched_at_ms, reasons_json, spread_bps, bid_depth_notional, ask_depth_notional, "
                "quote_volume_24h, raw_snapshot_sha256) "
                "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synthetic_fixture') "
                "ON CONFLICT(symbol) DO UPDATE SET active=excluded.active, liquidity_verified=excluded.liquidity_verified, "
                "vol_24h=excluded.vol_24h, updated_at_ms=excluded.updated_at_ms, source=excluded.source, "
                "status=excluded.status, policy_version=excluded.policy_version, event_time_ms=excluded.event_time_ms, "
                "fetched_at_ms=excluded.fetched_at_ms, book_event_time_ms=excluded.book_event_time_ms, "
                "book_fetched_at_ms=excluded.book_fetched_at_ms, ticker_event_time_ms=excluded.ticker_event_time_ms, "
                "ticker_fetched_at_ms=excluded.ticker_fetched_at_ms, reasons_json=excluded.reasons_json, spread_bps=excluded.spread_bps, "
                "bid_depth_notional=excluded.bid_depth_notional, ask_depth_notional=excluded.ask_depth_notional, "
                "quote_volume_24h=excluded.quote_volume_24h, raw_snapshot_sha256=excluded.raw_snapshot_sha256",
                (
                    symbol, int(assessment.verified), float(Decimal(quote_volume_24h)), now_ms,
                    source, assessment.status, POLICY_VERSION, overall_event_ms, overall_fetched_ms,
                    b_evt, b_fetch, t_evt, t_fetch, json.dumps(list(assessment.reasons)),
                    spread_bps, bid_depth_notional, ask_depth_notional, quote_volume_24h,
                ),
            )

    def record_market_source_failure(self, symbols: list[str], now_ms: int, reason: str) -> None:
        with self.conn:
            for symbol in symbols:
                self.conn.execute(
                    "INSERT INTO universe "
                    "(symbol, active, liquidity_verified, updated_at_ms, source, status, policy_version, "
                    "fetched_at_ms, reasons_json) VALUES (?, 0, 0, ?, 'bitget_rest_v2', 'source_failed', ?, ?, ?) "
                    "ON CONFLICT(symbol) DO UPDATE SET liquidity_verified=0, status='source_failed', "
                    "updated_at_ms=excluded.updated_at_ms, fetched_at_ms=excluded.fetched_at_ms, reasons_json=excluded.reasons_json",
                    (symbol, now_ms, POLICY_VERSION, now_ms, json.dumps([reason])),
                )

    def _liquidity_is_verified(
        self,
        symbol: str,
        decision_time_ms: int,
        *,
        planned_notional: str | float | Decimal | None = None,
        direction: int | None = None,
    ) -> bool:
        row = self.conn.execute(
            "SELECT active, liquidity_verified, status, policy_version, event_time_ms, fetched_at_ms, "
            "book_event_time_ms, book_fetched_at_ms, ticker_event_time_ms, ticker_fetched_at_ms, "
            "bid_depth_notional, ask_depth_notional FROM universe WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        spec = self.conn.execute(
            "SELECT qty_step, min_qty, min_notional, symbol_status, symbol_type, quote_coin, settle_coin, fetched_at_ms "
            "FROM instrument_specs WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None or spec is None:
            return False
        if not bool(row["active"]) or not bool(row["liquidity_verified"]) or row["status"] != "valid":
            return False
        if row["policy_version"] != POLICY_VERSION:
            return False

        # Independent timestamp freshness checks (strictly required without legacy fallback)
        book_evt = row["book_event_time_ms"]
        book_fetch = row["book_fetched_at_ms"]
        ticker_evt = row["ticker_event_time_ms"]
        ticker_fetch = row["ticker_fetched_at_ms"]
        spec_fetch = spec["fetched_at_ms"]

        if any(ts is None for ts in (book_evt, book_fetch, ticker_evt, ticker_fetch, spec_fetch)):
            return False

        # Book freshness
        book_evt_age = decision_time_ms - int(book_evt)
        book_fetch_age = decision_time_ms - int(book_fetch)
        if book_evt_age < -self.liquidity_policy.max_future_skew_ms or book_fetch_age < -self.liquidity_policy.max_future_skew_ms:
            return False
        if book_evt_age > self.liquidity_policy.max_age_ms or book_fetch_age > self.liquidity_policy.max_age_ms:
            return False

        # Ticker freshness
        ticker_evt_age = decision_time_ms - int(ticker_evt)
        ticker_fetch_age = decision_time_ms - int(ticker_fetch)
        if ticker_evt_age < -self.liquidity_policy.max_future_skew_ms or ticker_fetch_age < -self.liquidity_policy.max_future_skew_ms:
            return False
        if ticker_evt_age > self.liquidity_policy.max_age_ms or ticker_fetch_age > self.liquidity_policy.max_age_ms:
            return False

        # Spec freshness and validity
        spec_age = decision_time_ms - int(spec_fetch)
        if spec_age < -self.liquidity_policy.max_future_skew_ms or spec_age > self.liquidity_policy.spec_max_age_ms:
            return False
        if spec["symbol_status"] != "normal" or spec["symbol_type"] != "perpetual" or spec["quote_coin"] != "USDT" or spec["settle_coin"] != "USDT":
            return False

        # Sizing and side depth
        if planned_notional is None or direction not in (-1, 1):
            return False
        try:
            notional = Decimal(str(planned_notional))
            side_depth = Decimal(str(row["ask_depth_notional"] if direction == 1 else row["bid_depth_notional"]))
        except (InvalidOperation, ValueError):
            return False
        return notional > 0 and notional <= side_depth * self.liquidity_policy.max_position_depth_fraction

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

    def _evaluate_and_enter(
        self,
        symbol: str,
        candles: list[Candle],
        pending_alerts: list[dict[str, Any]] | None = None,
    ):
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
            spec_row = self.conn.execute(
                "SELECT qty_step, min_qty, min_notional, max_leverage, price_tick FROM instrument_specs WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if spec_row is None:
                self._log_decision(symbol, candles[-1].time_ms, direction, score, "REJECTED", "Instrumentenspezifikation fehlt")
                return None

            price_tick = Decimal(str(spec_row["price_tick"])) if spec_row["price_tick"] else Decimal("0.0001")
            spec = {
                "qtyStep": spec_row["qty_step"],
                "minQty": spec_row["min_qty"],
                "minNotional": spec_row["min_notional"],
                "priceTick": str(price_tick),
            }
            leverage = min(10, int(spec_row["max_leverage"]))
            risk_budget = Decimal(str(self.engine.equity)) * Decimal(str(self.engine.config.risk_per_trade_pct)) / Decimal("100")

            # Kanonischen Ausfuehrungsplan auf effektivem Fill (nach Slippage/Tick) und gequantelten Schutzleveln bilden:
            plan = self.engine.create_execution_plan(
                symbol=symbol,
                direction=direction,
                reference_price=current_price,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                spec=spec,
                leverage=leverage,
                risk_budget=risk_budget,
            )
            if not plan.levels_valid:
                self._log_decision(symbol, candles[-1].time_ms, direction, score, "REJECTED", plan.error_reason or "Ungueltiger Ausfuehrungsplan")
                return None

            # Liquiditaetspruefung strikt auf dem finalen Notional des Ausfuehrungsplans:
            decision_time_ms = int(self.time_provider() * 1000)
            if not self._liquidity_is_verified(
                symbol,
                decision_time_ms,
                planned_notional=plan.final_notional,
                direction=direction,
            ):
                self._log_decision(symbol, candles[-1].time_ms, direction, score, "REJECTED", "Liquiditaet oder ausfuehrungsspezifische Tiefe nicht verifiziert")
                return None

            # Bucht exakt den freigegebenen Plan ohne zweiten Sizing- oder Preisshift:
            pos = self.engine.execute_plan(
                plan=plan,
                timeframe="1H",
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
                    pos.entry_price,
                    pos.sl_price,
                    pos.tp1_price,
                )
                alert_payload = {
                    "title": f"AURA Neuer Trade: {dir_str} {symbol}",
                    "message": f"Einstieg @ {pos.entry_price:.4f} | SL: {pos.sl_price:.4f} | TP1: {pos.tp1_price:.4f} | Qty: {pos.qty}",
                    "priority": 3,
                    "event_type": "TRADE_OPEN",
                }
                if pending_alerts is not None:
                    pending_alerts.append(alert_payload)
                else:
                    self.notifier.send_alert(**alert_payload)
                self._log_decision(
                    symbol,
                    candles[-1].time_ms,
                    direction,
                    score,
                    "ACCEPTED",
                    f"Paper Trade #{pos.trade_id} @ {pos.entry_price:.4f}",
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
                # Letzte vollstaendig abgeschlossene Stunde (strikt in der Vergangenheit)
                last_closed_h = (now_s - (now_s % 3600)) - 3600
                candles = [
                    Candle(
                        time_ms=(last_closed_h - (39 - i) * 3600) * 1000,
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
