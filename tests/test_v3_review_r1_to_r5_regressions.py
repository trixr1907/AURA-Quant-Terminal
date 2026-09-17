"""Regressions- und Sicherheits-Tests fuer Review-Befunde R1 bis R5.

Testet:
R1: Persistenter Not-Halt und Wiederherstellung der wirksamen Konfiguration nach Neustart.
R2: Resume-Recovery auf RUNNING nur bei validen Feeds (keine Entry-Freigabe bei Fehlern/Offline).
R3: Echte SQLite-Transaktions-Atomizitaet mit Rollback bei Exceptions (kein autocommit).
R4: Absturzsichere Bar-Verarbeitung ohne verlorene Verarbeitung und ohne Duplikate.
R5: Reale Worker-Prozess-Unterbrechung und Wiederaufnahme auf derselben Datenbank.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aura.data.models import Candle, ValidationReport
from aura.runner.paper_engine import EngineConfig, PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.runner.worker import AuraWorkerService
from aura.store.db import connect


class MockFeedAdapter:
    """Kontrollierbarer Marktdaten-Adapter fuer isolierte Tests."""

    def __init__(self, is_valid: bool = True, candles: list[Candle] | None = None):
        self.is_valid = is_valid
        self.candles = candles or []

    def fetch_candles(self, symbol: str, granularity: str = "1H", limit: int = 60):
        rep = ValidationReport(
            is_valid=self.is_valid,
            total_checked=len(self.candles),
            errors=[] if self.is_valid else ["feed_offline_or_invalid"],
        )
        return list(self.candles), rep


def _make_dummy_candles(num_bars: int = 40, base_price: float = 50000.0) -> list[Candle]:
    candles = []
    now_ms = 1_700_000_000_000
    for i in range(num_bars):
        p = base_price + i * 50
        candles.append(
            Candle(
                time_ms=now_ms + i * 3600_000,
                open=p - 10,
                high=p + 40,
                low=p - 20,
                close=p + 10,
                volume=100.0,
                is_closed=True,
            )
        )
    return candles


class TestR1PersistentHaltAndConfig:
    """R1: Quittierter Not-Halt und aktive Konfiguration muessen nach Worker-Neustart erhalten bleiben."""

    def test_halt_persists_across_worker_restarts(self, tmp_path: Path):
        db_path = str(tmp_path / "r1_halt.db")

        # 1. Erster Worker startet, erhaelt Halt-Befehl und fuehrt ihn aus
        w1 = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w1.adapter = MockFeedAdapter(is_valid=True, candles=_make_dummy_candles())
        w1.sm.transition_to(SystemState.WARMING_UP)
        w1.sm.transition_to(SystemState.RUNNING)

        # Halt-Kommando in DB einstellen und Zyklus ausfuehren
        w1.conn.execute(
            "INSERT INTO commands (id, type, payload, status, created_at_ms) "
            "VALUES ('cmd_halt_r1', 'halt', '{\"reason\":\"Operator R1 Halt\"}', 'pending', ?)",
            (int(time.time() * 1000),),
        )
        w1._run_cycle(1)
        assert w1.sm.is_halted is True
        assert w1.sm.current_state == SystemState.HALTED
        w1.conn.close()

        # 2. Zweiter Worker instanziieren und starten (simuliert Neustart)
        w2 = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w2.adapter = MockFeedAdapter(is_valid=True, candles=_make_dummy_candles())
        w2.start(max_cycles=1)

        # Der Not-Halt MUSS nach Neustart aktiv bleiben!
        assert w2.sm.is_halted is True, "Not-Halt ging bei Neustart verloren!"
        assert w2.sm.current_state == SystemState.HALTED, f"FSM-Zustand nach Neustart war {w2.sm.current_state.value} statt HALTED"
        assert w2.sm.can_open_new_trades() is False, "can_open_new_trades() war True trotz Not-Halt!"
        w2.conn.close()

    def test_active_config_restored_across_worker_restarts(self, tmp_path: Path):
        db_path = str(tmp_path / "r1_cfg.db")

        # 1. Konfiguration in DB schreiben und anwenden
        conn = connect(db_path)
        cfg_payload = (
            '{"risk_per_trade_pct": 3.5, "max_open_positions": 8, "max_leverage": 15, '
            '"long_threshold": 80.0, "short_threshold": 20.0, "dry_run": true}'
        )
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO config_revisions (payload, source, created_at_ms, applied_at_ms) VALUES (?, 'operator', ?, ?)",
            (cfg_payload, now_ms, now_ms),
        )
        conn.close()

        # 2. Worker instanziieren und pruefen, ob angewendete Konfiguration geladen wird
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        assert w.risk_per_trade_pct == 3.5, f"risk_per_trade_pct war {w.risk_per_trade_pct} statt 3.5"
        assert w.max_open_positions == 8, f"max_open_positions war {w.max_open_positions} statt 8"
        assert w.long_threshold == 80.0
        assert w.engine.config.risk_per_trade_pct == 3.5
        assert w.engine.config.max_open_positions == 8
        w.conn.close()


class TestR2ResumeRecoveryAndHealthGating:
    """R2: Resume darf erst nach erfolgreicher Datenpruefung auf RUNNING schalten."""

    def test_resume_stays_recovering_if_feeds_invalid_or_offline(self, tmp_path: Path):
        db_path = str(tmp_path / "r2_offline.db")
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w.adapter = MockFeedAdapter(is_valid=False, candles=[])  # Offline/Ungueltig
        w.sm.transition_to(SystemState.WARMING_UP)
        w.sm.transition_to(SystemState.RUNNING)
        w.sm.emergency_halt("Test Halt")
        assert w.sm.is_halted is True

        # Resume anfordern
        now_ms = int(time.time() * 1000)
        w.conn.execute(
            "INSERT INTO commands (id, type, payload, status, created_at_ms) "
            "VALUES ('cmd_resume_r2', 'resume', '{\"reason\":\"Test Resume\"}', 'pending', ?)",
            (now_ms,),
        )
        w._run_cycle(1)
        # Nach Resume befindet sich das System zunaechst in RECOVERING
        assert w.sm.current_state in (SystemState.RECOVERING, SystemState.DEGRADED)
        # Weil der Feed offline ist, darf das System NICHT auf RUNNING gehen!
        assert w.sm.can_open_new_trades() is False

        # Weiterer Zyklus mit ungesundem Feed
        w._run_cycle(2)
        assert w.sm.current_state != SystemState.RUNNING
        assert w.sm.can_open_new_trades() is False
        w.conn.close()

    def test_resume_recovers_to_running_when_feeds_are_valid(self, tmp_path: Path):
        db_path = str(tmp_path / "r2_healthy.db")
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w.adapter = MockFeedAdapter(is_valid=True, candles=_make_dummy_candles())
        w.sm.transition_to(SystemState.WARMING_UP)
        w.sm.transition_to(SystemState.RUNNING)
        w.sm.emergency_halt("Test Halt")
        assert w.sm.is_halted is True

        # Resume anfordern
        now_ms = int(time.time() * 1000)
        w.conn.execute(
            "INSERT INTO commands (id, type, payload, status, created_at_ms) "
            "VALUES ('cmd_resume_r2_ok', 'resume', '{\"reason\":\"Test Resume Valid\"}', 'pending', ?)",
            (now_ms,),
        )
        w._run_cycle(1)
        # Da Feeds valide sind, muss der Worker RECOVERING -> RUNNING abschliessen!
        assert w.sm.current_state == SystemState.RUNNING, f"Zustand war {w.sm.current_state.value} statt RUNNING"
        assert w.sm.can_open_new_trades() is True
        w.conn.close()


class TestR3DatabaseTransactionAtomicity:
    """R3: with conn muss bei Exceptions echten Rollback garantieren (kein Autocommit-Rest)."""

    def test_with_conn_rolls_back_on_exception(self, tmp_path: Path):
        db_path = str(tmp_path / "r3_atomicity.db")
        c = connect(db_path)
        c.execute("CREATE TABLE atomicity_probe (val INT)")

        try:
            with c:
                c.execute("INSERT INTO atomicity_probe VALUES (42)")
                raise RuntimeError("Absichtlicher Abbruch im Transaktionsblock")
        except RuntimeError:
            pass

        count = c.execute("SELECT count(*) FROM atomicity_probe").fetchone()[0]
        assert count == 0, f"Rollback fehlgeschlagen! {count} Zeilen wurden committet trotz Exception."
        c.close()


class TestR4CrashResilientBarProcessing:
    """R4: Abgebrochene Bar-Verarbeitung darf nicht permanent uebersprungen werden."""

    def test_incomplete_claim_is_retried_after_restart(self, tmp_path: Path):
        db_path = str(tmp_path / "r4_recovery.db")

        # 1. Worker beansprucht Bar, stuertzt aber vor Abschluss ab
        w1 = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        claimed = w1._claim_closed_bar("BTCUSDT", "1h", 12345678000)
        assert claimed is True
        # Simulation: Crash ohne _complete_closed_bar
        w1.conn.close()

        # 2. Worker 2 startet neu
        w2 = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        # Der unvollstaendige Bar MUSS zur Wiederaufnahme bereit sein!
        reclaimed = w2._claim_closed_bar("BTCUSDT", "1h", 12345678000)
        assert reclaimed is True, "Unfertig verarbeiteter Bar wurde dauerhaft uebersprungen!"

        # Bar nun regulaer abschliessen
        w2._complete_closed_bar("BTCUSDT", "1h", 12345678000, decision="completed")
        w2.conn.close()

        # 3. Worker 3 startet: Ein fertig verarbeiteter Bar darf NICHT erneut verarbeitet werden
        w3 = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        claimed_again = w3._claim_closed_bar("BTCUSDT", "1h", 12345678000)
        assert claimed_again is False, "Bereits abgeschlossener Bar wurde faelschlicherweise doppelt beansprucht!"
        w3.conn.close()


class TestR5RealSubprocessWorkerRestart:
    """R5: Tatsaechlicher Subprozess-Neustart des Workers ohne SQL-Manipulation."""

    def test_real_worker_subprocess_lifecycle_and_restart(self, tmp_path: Path):
        db_path = str(tmp_path / "r5_subprocess.db")
        conn = connect(db_path)
        # Universe vorbereiten
        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO universe (symbol, active, liquidity_verified, vol_24h, updated_at_ms) "
            "VALUES ('BTCUSDT', 1, 1, 1000000.0, ?)",
            (now_ms,),
        )
        conn.close()

        env = os.environ.copy()
        env["AURA_DB_PATH"] = db_path
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

        # 1. Starte echten Worker-Subprozess mit CLI-Flags
        cmd = [sys.executable, "-m", "aura.runner.worker", "--db", db_path, "--symbols", "BTCUSDT", "--interval", "1"]
        proc1 = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            # Warten bis echter Worker laeuft und Heartbeat in runner_state schreibt
            started = False
            for _ in range(50):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute("SELECT fsm_state, cycle_count FROM runner_state WHERE id = 1").fetchone()
                c.close()
                if row and row["cycle_count"] >= 1:
                    started = True
                    break
            assert started, "Worker-Prozess #1 hat keinen Heartbeat geschrieben!"

            # 2. Halt-Befehl ueber DB senden (wie von API)
            c = connect(db_path)
            c.execute(
                "INSERT INTO commands (id, type, payload, status, created_at_ms) "
                "VALUES ('cmd_proc_halt', 'halt', '{\"reason\":\"Subprocess Halt Test\"}', 'pending', ?)",
                (int(time.time() * 1000),),
            )
            c.close()

            # Warten bis echter Worker den Not-Halt quittiert
            halted = False
            for _ in range(50):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute("SELECT fsm_state FROM runner_state WHERE id = 1").fetchone()
                c.close()
                if row and row["fsm_state"] == "HALTED":
                    halted = True
                    break
            assert halted, "Worker-Prozess #1 hat Halt nicht quittiert!"

        finally:
            # Worker #1 hart beenden (kill)
            proc1.terminate()
            try:
                proc1.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc1.kill()

        # 3. Zweiter Worker-Subprozess auf derselben Datenbank starten (Restart nach Crash/Kill)
        proc2 = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            # Pruefen, dass Worker #2 im Not-Halt bleibt und diesen nicht vergisst
            restarted_in_halt = False
            for _ in range(50):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute("SELECT fsm_state, cycle_count FROM runner_state WHERE id = 1").fetchone()
                c.close()
                if row and row["cycle_count"] >= 1:
                    if row["fsm_state"] == "HALTED":
                        restarted_in_halt = True
                        break
            assert restarted_in_halt, "Worker-Prozess #2 hat den Not-Halt nach Neustart ueberschrieben!"

            # 4. Resume-Befehl senden
            c = connect(db_path)
            c.execute(
                "INSERT INTO commands (id, type, payload, status, created_at_ms) "
                "VALUES ('cmd_proc_resume', 'resume', '{\"reason\":\"Subprocess Resume Test\"}', 'pending', ?)",
                (int(time.time() * 1000),),
            )
            c.close()

            # Warten bis Worker #2 den Resume verarbeitet und wieder laeuft
            resumed = False
            for _ in range(50):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute("SELECT fsm_state FROM runner_state WHERE id = 1").fetchone()
                c.close()
                if row and row["fsm_state"] in ("RUNNING", "RECOVERING"):
                    resumed = True
                    break
            assert resumed, "Worker-Prozess #2 hat Resume nicht quittiert!"

        finally:
            proc2.terminate()
            try:
                proc2.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc2.kill()
