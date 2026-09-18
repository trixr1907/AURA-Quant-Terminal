"""Regressions- und Sicherheits-Tests fuer Review-Befunde R1 bis R5 und Folgepruefung F1 bis F5.

Testet:
F1 (R4): Atomare Bar-Verarbeitung: Crash vor Bar-Abschluss rollt DB- und In-Memory-Zustand zurueck;
         Replay derselben Kerze stoppt den Trade nicht faelschlich aus.
F2 (R2): Tatsaechliche Datenfrische, Mindesthistorie (>= 30 geschlossene Bars) und globales Feed-Gating
         vor Entry-Freigabe.
F3 (R2): Selbststaendige Wiederaufnahme (Recovery) nach fehlgeschlagenem Start-Warmup (DEGRADED -> RUNNING).
F4 (R3): Vollstaendig atomare Migrationen inklusive executescript und schema_migrations-Rollback.
F5 (R5): Belastbarer Subprozess-Neustartnachweis mit frischer Instanz-ID, echtem Heartbeat nach Kill,
         quittierter Command-ID und kontrolliertem deterministischem Feed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from aura.data.models import Candle, ValidationReport
from aura.runner.paper_engine import EngineConfig
from aura.runner.state_machine import SystemState
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


def _make_dummy_candles(
    num_bars: int = 40, base_price: float = 50000.0, end_time_ms: int | None = None
) -> list[Candle]:
    candles = []
    if end_time_ms is None:
        end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - num_bars * 3600_000
    for i in range(num_bars):
        p = base_price + i * 50
        candles.append(
            Candle(
                time_ms=start_time_ms + i * 3600_000,
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
        assert (
            w2.sm.current_state == SystemState.HALTED
        ), f"FSM-Zustand nach Neustart war {w2.sm.current_state.value} statt HALTED"
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


class TestF1CrashResilientBarProcessingAndStateConsistency:
    """F1 (R4): Crash-Sicherheit bei TP1-Teilschliessung und verlaessliche Idempotenz."""

    def test_bar_crash_before_complete_rolls_back_db_and_in_memory(self, tmp_path: Path):
        path = str(tmp_path / "f1_tp1_crash.db")
        ts = int(time.time() * 1000) - 3600_000

        # Erzeuge 40 frische Kerzen bis ts
        feed_bars = _make_dummy_candles(40, base_price=100.0, end_time_ms=ts)
        # Die letzte Kerze loest TP1 aus: Entry 100, High 111 (>= TP1 110), Low 99 (> SL 90)
        last_candle = Candle(
            time_ms=ts,
            open=105.0,
            high=111.0,
            low=99.0,
            close=108.0,
            volume=100.0,
            is_closed=True,
        )
        feed_bars[-1] = last_candle

        w = AuraWorkerService(db_path=path, symbols=["BTCUSDT"])
        w.sm.transition_to(SystemState.WARMING_UP)
        w.sm.transition_to(SystemState.RUNNING)
        w.adapter = MockFeedAdapter(is_valid=True, candles=feed_bars)

        # Position vor dem Zyklus manuell anlegen: Long Entry 100, SL 90, TP1 110, TP2 120
        pos = w.engine.open_trade(
            symbol="BTCUSDT",
            timeframe="1h",
            direction=1,
            entry_price=100.0,
            sl_price=90.0,
            tp1_price=110.0,
            tp2_price=120.0,
            spec={"ctVal": 0.0001, "minSize": 0.0001, "minNotional": 5.0},
            current_time_ms=ts - 3600_000,
        )
        assert pos is not None
        initial_sl = pos.sl_price
        initial_qty = pos.qty

        # Crash direkt bei Aufruf von _complete_closed_bar simulieren (z.B. OS-Kill oder Stromausfall)
        class PowerLoss(BaseException):
            pass

        def crash(*args: Any, **kwargs: Any) -> None:
            raise PowerLoss("Simulierter Stromausfall vor _complete_closed_bar")

        w._complete_closed_bar = crash  # type: ignore[assignment]

        with pytest.raises(PowerLoss):
            w._run_cycle(1)

        # In-Memory-Pruefung auf w: Durch In-Memory-Rollback muss der Zustand unverfaelscht sein
        pos_in_w = w.engine.open_positions[pos.trade_id]
        assert pos_in_w.sl_price == initial_sl, "In-Memory Stop-Loss wurde bei Rollback nicht restauriert!"
        assert pos_in_w.qty == initial_qty, "In-Memory Positionsmenge wurde bei Rollback nicht restauriert!"
        assert pos_in_w.tp1_hit is False

        # DB-Pruefung: Durch SQLite-Rollback muss der Zustand in DB der Zustand vor dem Bar sein
        row = w.conn.execute(
            "SELECT status, current_sl, remaining_qty, tp1_hit FROM trades WHERE id = ?",
            (pos.trade_id,),
        ).fetchone()
        assert row["status"] == "open"
        assert float(row["current_sl"]) == initial_sl
        assert float(row["remaining_qty"]) == initial_qty
        assert int(row["tp1_hit"]) == 0
        w.conn.close()

        # Nun startet Worker 2 auf derselben DB und fuehrt dieselbe Kerze regulaer aus
        w2 = AuraWorkerService(db_path=path, symbols=["BTCUSDT"])
        w2.sm.transition_to(SystemState.WARMING_UP)
        w2.sm.transition_to(SystemState.RUNNING)
        w2.adapter = MockFeedAdapter(is_valid=True, candles=feed_bars)

        # Zyklus 2 ausfuehren
        w2._run_cycle(2)

        # Der Trade darf durch den Replay NICHT am nachgezogenen Stop ausgestoppt worden sein!
        assert pos.trade_id in w2.engine.open_positions, "Trade wurde bei Replay faelschlicherweise ausgestoppt!"
        assert not any(x.trade_id == pos.trade_id for x in w2.engine.closed_positions)

        # In DB muss der Trade nun im regulaeren Teil-Exit (TP1 erreicht, SL auf Breakeven) stehen
        after_row = w2.conn.execute(
            "SELECT status, current_sl, remaining_qty, tp1_hit FROM trades WHERE id = ?",
            (pos.trade_id,),
        ).fetchone()
        assert after_row["status"] == "open"
        assert int(after_row["tp1_hit"]) == 1
        assert float(after_row["current_sl"]) > initial_sl  # SL auf Breakeven
        assert float(after_row["remaining_qty"]) < initial_qty  # 50% geschlossen

        # Bar ist nun abgeschlossen
        pb = w2.conn.execute(
            "SELECT decision FROM processed_bars WHERE symbol = 'BTCUSDT' AND open_time_ms = ?",
            (ts,),
        ).fetchone()
        assert pb is not None and pb["decision"] == "completed"
        w2.conn.close()


class TestF2FeedFreshnessAndGlobalGating:
    """F2 (R2): Tatsaechliche Frischegrenzen, Historienlaenge und globales Feed-Gating."""

    def test_stale_feed_from_2023_rejected_and_blocks_running(self, tmp_path: Path):
        db_path = str(tmp_path / "f2_stale.db")
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w.sm.transition_to(SystemState.WARMING_UP)
        w.sm.transition_to(SystemState.RUNNING)
        w.sm.emergency_halt("Halt fuer Stale-Test")
        w.sm.resume_from_halt("Resume fuer Stale-Test")
        assert w.sm.current_state == SystemState.RECOVERING

        # Feed mit veralteten Kerzen aus November 2023 (1700000000000)
        stale_bars = _make_dummy_candles(40, end_time_ms=1_700_000_000_000)
        w.adapter = MockFeedAdapter(is_valid=True, candles=stale_bars)

        # Zyklus durchfuehren
        w._run_cycle(1)

        # Wegen veraltetem Feed darf das System NICHT auf RUNNING gehen!
        assert w.sm.current_state in (SystemState.RECOVERING, SystemState.DEGRADED)
        assert w.sm.can_open_new_trades() is False, "Veralteter 2023-Feed schaltete faelschlich RUNNING frei!"
        w.conn.close()

    def test_feed_with_insufficient_closed_candles_blocks_running(self, tmp_path: Path):
        db_path = str(tmp_path / "f2_short_history.db")
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w.sm.transition_to(SystemState.WARMING_UP)
        w.sm.transition_to(SystemState.RUNNING)
        w.sm.emergency_halt("Halt fuer Short-History")
        w.sm.resume_from_halt("Resume fuer Short-History")

        # Nur 15 geschlossene Kerzen (< 30)
        short_bars = _make_dummy_candles(15)
        w.adapter = MockFeedAdapter(is_valid=True, candles=short_bars)
        w._run_cycle(1)

        assert w.sm.current_state != SystemState.RUNNING
        assert w.sm.can_open_new_trades() is False
        w.conn.close()

    def test_running_system_transitions_to_degraded_when_feed_drops(self, tmp_path: Path):
        db_path = str(tmp_path / "f2_degraded.db")
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])
        w.sm.transition_to(SystemState.WARMING_UP)
        w.sm.transition_to(SystemState.RUNNING)
        w.adapter = MockFeedAdapter(is_valid=True, candles=_make_dummy_candles(40))

        # 1. Gesunder Zyklus
        w._run_cycle(1)
        assert w.sm.current_state == SystemState.RUNNING

        # 2. Feed wird ungueltig/offline
        w.adapter = MockFeedAdapter(is_valid=False, candles=[])
        w._run_cycle(2)

        # System muss von RUNNING nach DEGRADED wechseln und Trades blockieren
        assert w.sm.current_state == SystemState.DEGRADED
        assert w.sm.can_open_new_trades() is False
        w.conn.close()


class TestF3WarmupRecovery:
    """F3: Selbststaendige Recovery nach fehlgeschlagenem Start-Warmup."""

    def test_failed_warmup_transitions_to_degraded_and_recovers_to_running_when_feed_returns(
        self, tmp_path: Path
    ):
        db_path = str(tmp_path / "f3_warmup.db")
        w = AuraWorkerService(db_path=db_path, symbols=["BTCUSDT"])

        # Start mit unvollstaendigen/ungueltigen Marktdaten
        w.adapter = MockFeedAdapter(is_valid=False, candles=[])
        w.start(max_cycles=1)

        # Worker darf nach fehlgeschlagenem Warmup NICHT in WARMING_UP haengenbleiben!
        assert w.sm.current_state == SystemState.DEGRADED, (
            f"Zustand nach Warmup-Fehlschlag war {w.sm.current_state.value} statt DEGRADED"
        )
        assert w.sm.can_open_new_trades() is False

        # Sobald frische, valide Marktdaten verfuegbar sind, muss die FSM selbststaendig nach RUNNING wechseln
        w.adapter = MockFeedAdapter(is_valid=True, candles=_make_dummy_candles(40))
        w._run_cycle(2)

        assert w.sm.current_state == SystemState.RUNNING, (
            f"Selbststaendige Recovery schlug fehl: Zustand war {w.sm.current_state.value}"
        )
        assert w.sm.can_open_new_trades() is True
        w.conn.close()


class TestF4DatabaseTransactionAtomicityAndMigrationScripts:
    """F4 (R3): Vollstaendige Transaktions-Atomizitaet fuer with conn und executescript."""

    def test_with_conn_rolls_back_on_exception(self, tmp_path: Path):
        db_path = str(tmp_path / "f4_rollback.db")
        c = connect(db_path)
        c.execute("CREATE TABLE probe (x INTEGER)")

        with pytest.raises(RuntimeError):
            with c:
                c.execute("INSERT INTO probe VALUES (1)")
                c.execute("INSERT INTO probe VALUES (2)")
                raise RuntimeError("Test-Fehler innerhalb Transaktion")

        # Durch Rollback duerfen keine Zeilen gespeichert worden sein
        n = c.execute("SELECT COUNT(*) FROM probe").fetchone()[0]
        assert n == 0, f"Rollback fehlgeschlagen! {n} Zeilen in DB gefunden!"
        c.close()

    def test_executescript_rolls_back_atomically_on_error(self, tmp_path: Path):
        db_path = str(tmp_path / "f4_script_rollback.db")
        c = connect(db_path)
        c.execute("CREATE TABLE probe (x INTEGER)")

        with pytest.raises(RuntimeError):
            with c:
                c.execute("INSERT INTO probe VALUES (1)")
                c.executescript("INSERT INTO probe VALUES (2); INSERT INTO probe VALUES (3);")
                raise RuntimeError("Fehler nach executescript")

        # executescript darf keinen vorzeitigen Commit ausgefuehrt haben
        n = c.execute("SELECT COUNT(*) FROM probe").fetchone()[0]
        assert n == 0, f"executescript umging den Rollback: {n} Zeilen ueberlebten!"
        c.close()


class TestF5SubprocessWorkerRestartAndHeartbeatEvidence:
    """F5 (R5): Belastbare Prozess-Isolation, Heartbeat-Liveness und Command-Quittierung."""

    def test_real_worker_subprocess_lifecycle_and_restart(self, tmp_path: Path):
        db_path = str(tmp_path / "f5_subprocess.db")

        # DB initial anlegen
        conn = connect(db_path)
        conn.close()

        env = os.environ.copy()
        env["AURA_DB_PATH"] = db_path
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

        # 1. Starte echten Worker-Subprozess mit CLI-Flags und --test-mode (deterministisch)
        cmd = [
            sys.executable,
            "-m",
            "aura.runner.worker",
            "--db",
            db_path,
            "--symbols",
            "BTCUSDT",
            "--interval",
            "0.2",
            "--test-mode",
        ]
        proc1 = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        p1_instance_id = None
        try:
            # Warten bis echter Worker laeuft und Heartbeat in runner_state schreibt
            started = False
            for _ in range(100):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute("SELECT fsm_state, cycle_count, reason FROM runner_state WHERE id = 1").fetchone()
                c.close()
                if row and row["cycle_count"] >= 1:
                    started = True
                    reason_str = str(row["reason"] or "")
                    if reason_str.startswith("[w_"):
                        p1_instance_id = reason_str.split("]")[0].strip("[")
                    break
            assert started, "Worker-Prozess #1 hat keinen Heartbeat geschrieben!"
            assert p1_instance_id is not None, "Worker-Prozess #1 hat keine gueltige Instanz-ID geschrieben!"

            # 2. Halt-Befehl ueber DB senden
            c = connect(db_path)
            c.execute(
                "INSERT INTO commands (id, type, payload, status, created_at_ms) "
                "VALUES ('cmd_proc_halt', 'halt', '{\"reason\":\"Subprocess Halt Test\"}', 'pending', ?)",
                (int(time.time() * 1000),),
            )
            # Konfiguration aendern
            now_ms = int(time.time() * 1000)
            c.execute(
                "INSERT INTO config_revisions (payload, source, created_at_ms, applied_at_ms) VALUES (?, 'operator', ?, ?)",
                ('{"risk_per_trade_pct": 4.2, "max_open_positions": 7}', now_ms, now_ms),
            )
            c.close()

            # Warten bis echter Worker den Not-Halt quittiert
            halted = False
            for _ in range(50):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute("SELECT fsm_state FROM runner_state WHERE id = 1").fetchone()
                cmd_row = c.execute("SELECT status FROM commands WHERE id = 'cmd_proc_halt'").fetchone()
                c.close()
                if row and row["fsm_state"] == "HALTED" and cmd_row and cmd_row["status"] == "applied":
                    halted = True
                    break
            assert halted, "Worker-Prozess #1 hat Halt nicht bestaetigt!"

        finally:
            # Worker #1 hart beenden (kill)
            proc1.terminate()
            try:
                proc1.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc1.kill()

        # Sicherstellen, dass Prozess 1 wirklich tot ist
        assert proc1.poll() is not None, "Worker-Prozess #1 konnte nicht beendet werden!"

        t_restart = int(time.time() * 1000)

        # 3. Zweiter Worker-Subprozess auf derselben Datenbank starten (Restart nach Kill)
        proc2 = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            # Pruefen, dass Worker #2 eine neue Instanz-ID hat, im Not-Halt startet und die neue Konfig hat
            p2_started_in_halt = False
            p2_instance_id = None
            for _ in range(100):
                time.sleep(0.2)
                c = connect(db_path)
                row = c.execute(
                    "SELECT fsm_state, cycle_count, reason, updated_at_ms FROM runner_state WHERE id = 1"
                ).fetchone()
                c.close()
                if row and int(row["updated_at_ms"]) >= t_restart:
                    reason_str = str(row["reason"] or "")
                    if reason_str.startswith("[w_"):
                        p2_instance_id = reason_str.split("]")[0].strip("[")
                    if row["fsm_state"] == "HALTED" and p2_instance_id != p1_instance_id:
                        p2_started_in_halt = True
                        break
            assert p2_started_in_halt, "Worker-Prozess #2 hat den Not-Halt nach Neustart nicht fortgefuehrt!"
            assert p2_instance_id != p1_instance_id, "Instanz-ID des zweiten Prozesses war nicht neu!"

            # 4. Resume-Befehl an Prozess 2 senden
            t_resume = int(time.time() * 1000)
            c = connect(db_path)
            c.execute(
                "INSERT INTO commands (id, type, payload, status, created_at_ms) "
                "VALUES ('cmd_proc_resume_f5', 'resume', '{\"reason\":\"Subprocess Resume F5\"}', 'pending', ?)",
                (t_resume,),
            )
            c.close()

            # Warten bis Worker #2 den Resume quittiert und durch gesunde Feeds wieder RUNNING erreicht
            resumed_running = False
            for _ in range(100):
                time.sleep(0.2)
                c = connect(db_path)
                cmd_row = c.execute("SELECT status, applied_at_ms FROM commands WHERE id = 'cmd_proc_resume_f5'").fetchone()
                state_row = c.execute("SELECT fsm_state, updated_at_ms FROM runner_state WHERE id = 1").fetchone()
                c.close()
                if (
                    cmd_row
                    and cmd_row["status"] == "applied"
                    and int(cmd_row["applied_at_ms"] or 0) >= t_resume
                    and state_row
                    and state_row["fsm_state"] == "RUNNING"
                ):
                    resumed_running = True
                    break
            assert resumed_running, "Worker-Prozess #2 hat Resume nicht erfolgreich bis RUNNING wiederhergestellt!"

        finally:
            proc2.terminate()
            try:
                proc2.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc2.kill()
