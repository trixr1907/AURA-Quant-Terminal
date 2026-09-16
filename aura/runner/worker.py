"""Hintergrund-Worker fuer AURA v3 (aura.runner.worker).

Fuehrt Marktdaten-Polling, Bar-Updates, Signal-Scanning und Paper-Trading
vollstaendig autonom auf dem Server (Proxmox/Docker) aus.
Dokumentiert in docs/ARCHITECTURE.md und ADR-0003.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

from aura.data.bitget_adapter import BitgetMarketAdapter
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
    ):
        self.db_path = db_path
        self.poll_interval = poll_interval_sec
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
        self._running = False

        self.conn = connect(self.db_path)
        self.sm = RunnerStateMachine(SystemState.STARTING)
        self.adapter = BitgetMarketAdapter()
        self.engine = PaperTradingEngine(conn=self.conn)

        ntfy_url = os.environ.get("AURA_NTFY_URL", "")
        ntfy_cfg = NotificationConfig(enabled=bool(ntfy_url), topic_url=ntfy_url)
        self.notifier = NotificationDispatcher(config=ntfy_cfg, conn=self.conn)

    def start(self) -> None:
        """Startet die Worker-Schleife."""
        self._running = True
        self._setup_signals()
        logger.info("AURA v3 Worker gestartet (DB: %s, Symbole: %s)", self.db_path, self.symbols)

        self.sm.transition_to(SystemState.WARMING_UP, "Initialisiere Marktdaten-Feeds")
        self._warmup_feeds()
        self.sm.transition_to(SystemState.RUNNING, "Feeds initialisiert, bereit fuer Paper-Trading")

        cycle = 0
        while self._running:
            cycle += 1
            try:
                self._run_cycle(cycle)
            except Exception as ex:
                logger.error("Unerwarteter Fehler im Worker-Zyklus #%d: %s", cycle, ex, exc_info=True)
                self.sm.mark_degraded(f"Zyklus-Fehler: {ex}")

            time.sleep(self.poll_interval)

        logger.info("AURA v3 Worker sauber beendet.")

    def stop(self) -> None:
        self._running = False

    def _setup_signals(self) -> None:
        signal.signal(signal.SIGINT, lambda s, f: self.stop())
        signal.signal(signal.SIGTERM, lambda s, f: self.stop())

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

    def _run_cycle(self, cycle: int) -> None:
        now_ms = int(time.time() * 1000)
        logger.debug("Worker-Zyklus #%d gestartet...", cycle)

        for sym in self.symbols:
            try:
                candles, rep = self.adapter.fetch_candles(sym, granularity="1H", limit=50)
                if not candles or not rep.is_valid:
                    continue

                last_bar = candles[-1]
                # 1. Bar-Updates fuer offene Positionen
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
                        message=f"Grund: {pos.exit_reason} @ {pos.exit_price:.4f} | PnL: {pos.realized_pnl:.2f} USDT",
                        priority=4,
                        event_type="TRADE_CLOSE",
                    )
            except Exception as ex:
                logger.warning("Fehler beim Verarbeiten von %s in Zyklus #%d: %s", sym, cycle, ex)


if __name__ == "__main__":
    db_path = os.environ.get("AURA_DB_PATH", "aura_state.db")
    worker = AuraWorkerService(db_path=db_path)
    worker.start()
