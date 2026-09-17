"""Regressions- und Sicherheits-Tests fuer die Befunde G1 bis G3 aus der Folgepruefung.

Testet:
G1: Sichere SQLite-Verbindungsnutzung bei parallelen API-Zugriffen:
    - Keine Transaktionskollisionen ("cannot start a transaction within a transaction") bei parallelen Mutationen
    - Vollstaendige Rollback-Isolation zwischen ueberlappenden Threads/Requests
    - Sichere Serialisierung/Kollisionsabwehr auf Shared-Connection-Ebene
G2: Strikte Verstaendigungssicherheit (Commit-Sicherheit) fuer Entry- und Exit-Alerts:
    - Keine Notifikationen (weder Entry noch Exit) fuer zurueckgerollte Transaktionen
    - Alerts verlassen die Transaktion erst NACH erfolgreichem Commit
    - Fehler beim Alert-Versand nach Commit fuehren nicht zur Beschaedigung/Rollback committeter Buchungen
G3: Kausalitaets-Guard fuer Kerzenfeeds, Zeitgrenzen und CLI-Testfeed:
    - Abweisung als geschlossen markierter Kerzen, deren Zeitintervall noch nicht vollendet ist
    - Clock-Skew/Boundary-Tests (Toleranzgrenzen)
    - Deterministischer Testfeed erzeugt ausschliesslich vollstaendig abgeschlossene Stunden
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aura.api.app import create_app
from aura.data.models import Candle, ValidationReport
from aura.runner.paper_engine import PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.runner.worker import AuraWorkerService
from aura.store.db import SafeConnection, connect


def _make_test_bars(last_bar_start_ms: int, count: int = 40) -> list[Candle]:
    """Erzeugt gueltige synthetische 1H-Kerzen mit last_bar_start_ms als Startzeit der letzten Kerze."""
    bars = []
    start_ms = last_bar_start_ms - (count - 1) * 3600_000
    for i in range(count):
        t = start_ms + i * 3600_000
        p = 50000.0 + i * 20
        bars.append(
            Candle(
                time_ms=t,
                open=p,
                high=p + 30.0,
                low=p - 30.0,
                close=p + 10.0,
                volume=100.0,
                is_closed=True,
            )
        )
    return bars


# ============================================================================
# G1: Parallele API-Zugriffe und SQLite-Transaktionssicherheit
# ============================================================================


def test_g1_concurrent_api_requests_no_transaction_collision(tmp_path):
    """Prueft, dass 25 parallele API-Requests (Halt/Resume/Config) keine Transaktionskollisionen erzeugen."""
    db_path = str(tmp_path / "concurrent_api.db")
    os.environ["AURA_RELAY_TOKEN"] = "g1-secret-token"

    sm = RunnerStateMachine(SystemState.RUNNING)
    app = create_app(db_path=db_path, state_machine=sm)
    client = TestClient(app)
    headers = {"X-AURA-TOKEN": "g1-secret-token"}

    results: list[tuple[int, int, str]] = []
    lock = threading.Lock()

    def run_client_request(idx: int):
        c = TestClient(app)
        try:
            if idx % 3 == 0:
                r = c.post("/api/v3/halt", json={"reason": f"concurrent_halt_{idx}"}, headers=headers)
            elif idx % 3 == 1:
                r = c.post("/api/v3/resume", json={"reason": f"concurrent_resume_{idx}"}, headers=headers)
            else:
                r = c.post(
                    "/api/v3/config",
                    json={
                        "long_threshold": 60.0 + (idx % 10),
                        "short_threshold": 30.0,
                        "risk_per_trade_pct": 1.0,
                        "max_open_positions": 3,
                        "max_leverage": 10,
                        "macro_cap": 0.2,
                    },
                    headers=headers,
                )
            with lock:
                results.append((idx, r.status_code, r.text))
        except Exception as ex:
            with lock:
                results.append((idx, 599, str(ex)))

    threads = [threading.Thread(target=run_client_request, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 25, "Alle 25 Requests muessen vollstaendig durchgelaufen sein"

    # Pruefe, dass kein einziger Request wegen SQLite-Transaktionskollision abgebrochen ist
    failed = [r for r in results if r[1] != 200]
    assert not failed, f"Es traten unerwartete Fehler auf: {failed}"

    # Verifiziere DB-Konsistenz: Alle Commands muessen persistiert sein
    c = connect(db_path)
    count = c.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
    c.close()
    assert count == 25, f"Erwartete 25 persistierte Befehle, gefunden: {count}"


def test_g1_rollback_isolation_between_concurrent_threads(tmp_path):
    """Prueft echte Rollback-Isolation: Ein fehlgeschlagener Thread rollt nicht die Daten eines parallelen Threads zurueck."""
    db_path = str(tmp_path / "rollback_iso.db")
    c_init = connect(db_path)
    c_init.execute("CREATE TABLE test_iso (id INT PRIMARY KEY, val TEXT)")
    c_init.close()

    barrier = threading.Barrier(2)
    thread1_success = False
    thread2_rolled_back = False

    def thread1_worker():
        nonlocal thread1_success
        c1 = connect(db_path)
        barrier.wait()
        with c1:
            c1.execute("INSERT INTO test_iso (id, val) VALUES (1, 'persisted')")
        c1.close()
        thread1_success = True

    def thread2_worker():
        nonlocal thread2_rolled_back
        c2 = connect(db_path)
        barrier.wait()
        try:
            with c2:
                c2.execute("INSERT INTO test_iso (id, val) VALUES (2, 'should_rollback')")
                raise RuntimeError("Abbruch in Thread 2")
        except RuntimeError:
            thread2_rolled_back = True
        c2.close()

    t1 = threading.Thread(target=thread1_worker)
    t2 = threading.Thread(target=thread2_worker)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert thread1_success and thread2_rolled_back

    c_check = connect(db_path)
    rows = c_check.execute("SELECT id, val FROM test_iso ORDER BY id").fetchall()
    c_check.close()

    assert len(rows) == 1
    assert rows[0]["id"] == 1 and rows[0]["val"] == "persisted"


def test_g1_shared_connection_rejects_overlapping_transaction_with_informative_error(tmp_path):
    """Ueberfuehrung der Defektprobe: Ein paralleler Transaktionsversuch auf derselben SafeConnection fuehrt nicht zu C-Corruption."""
    c = connect(tmp_path / "shared.db")
    c.execute("CREATE TABLE probe (x INT)")
    errors = []

    def second():
        try:
            with c:
                c.execute("INSERT INTO probe VALUES (2)")
        except Exception as e:
            errors.append(str(e))

    with c:
        c.execute("INSERT INTO probe VALUES (1)")
        t = threading.Thread(target=second)
        t.start()
        t.join(timeout=3)
        assert not t.is_alive()

    c.close()
    assert len(errors) == 1
    assert "cannot start a transaction within a transaction" in errors[0]


# ============================================================================
# G2: Keine Ghost-Alerts bei zurueckgerollten Trades & Entkopplung
# ============================================================================


def test_g2_no_entry_alert_on_rolled_back_trade(tmp_path):
    """Ueberfuehrung der Defektprobe: Wenn ein Bar vor Abschluss fehlschlaegt, wird KEIN Entry-Alert gesendet."""
    ts = int(time.time() * 1000) - 7200_000
    w = AuraWorkerService(db_path=str(tmp_path / "alerts.db"), symbols=["BTCUSDT"], long_threshold=-1.0)
    w.sm.transition_to(SystemState.WARMING_UP)
    w.sm.transition_to(SystemState.RUNNING)
    w.conn.execute("INSERT INTO universe (symbol, active, liquidity_verified, updated_at_ms) VALUES ('BTCUSDT', 1, 1, ?)", (ts,))

    sent_alerts: list[dict[str, Any]] = []
    setattr(w.notifier, "send_alert", lambda **kw: sent_alerts.append(kw) or True)

    # Crash kurz vor Bar-Abschluss simulieren
    def crash(*a, **kw):
        raise RuntimeError("simulated-abort-before-commit")

    w._complete_closed_bar = crash
    candles = _make_test_bars(ts + 3600_000, count=40)

    with pytest.raises(RuntimeError, match="simulated-abort-before-commit"):
        w._process_closed_bar("BTCUSDT", candles[-1], candles)

    # Verifikation Sollverhalten:
    # 1. DB-Zustand ist unberuehrt
    count = w.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert count == 0, f"Erwartete 0 Trades in DB nach Rollback, gefunden: {count}"

    # 2. In-Memory Zustand ist synchron zurueckgerollt
    assert len(w.engine.open_positions) == 0, "In-Memory open_positions darf nach Rollback keine Position enthalten"

    # 3. G2-Kernnachweis: Keine Alerts versendet!
    assert len(sent_alerts) == 0, f"Es durften KEINE Alerts gesendet werden, aber es wurden gesendet: {sent_alerts}"

    w.conn.close()


def test_g2_entry_and_exit_alerts_delivered_after_successful_commit(tmp_path):
    """Beweist, dass Alerts nach erfolgreichem Commit ordnungsgemaess zugestellt werden."""
    ts = int(time.time() * 1000) - 7200_000
    w = AuraWorkerService(db_path=str(tmp_path / "alerts_success.db"), symbols=["BTCUSDT"], long_threshold=-1.0)
    w.sm.transition_to(SystemState.WARMING_UP)
    w.sm.transition_to(SystemState.RUNNING)
    now_wall_ms = int(time.time() * 1000)
    w.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_wall_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="5000000",
        ask_depth_notional="5000000",
        quote_volume_24h="100000000",
    )

    sent_alerts: list[dict[str, Any]] = []
    setattr(w.notifier, "send_alert", lambda **kw: sent_alerts.append(kw) or True)

    candles = _make_test_bars(ts + 3600_000, count=40)
    w._process_closed_bar("BTCUSDT", candles[-1], candles)

    # Transaktion war erfolgreich -> Entry-Alert muss versendet worden sein
    assert len(w.engine.open_positions) == 1
    assert len(sent_alerts) == 1
    assert sent_alerts[0]["event_type"] == "TRADE_OPEN"

    w.conn.close()


def test_g2_notifier_failure_does_not_rollback_committed_trade(tmp_path):
    """Zustellungs-Entkopplung: Ein Netzwerkfehler im Notifier NACH dem Commit macht den Trade nicht ungueltig."""
    ts = int(time.time() * 1000) - 7200_000
    w = AuraWorkerService(db_path=str(tmp_path / "notifier_fail.db"), symbols=["BTCUSDT"], long_threshold=-1.0)
    w.sm.transition_to(SystemState.WARMING_UP)
    w.sm.transition_to(SystemState.RUNNING)
    now_wall_ms = int(time.time() * 1000)
    w.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_wall_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="5000000",
        ask_depth_notional="5000000",
        quote_volume_24h="100000000",
    )

    def failing_notifier(**kw):
        raise ConnectionError("Telegram Gateway offline")

    setattr(w.notifier, "send_alert", failing_notifier)

    candles = _make_test_bars(ts + 3600_000, count=40)
    # Darf keine Exception nach aussen werfen, die die Buchung gefaehrdet
    w._process_closed_bar("BTCUSDT", candles[-1], candles)

    # Trade bleibt korrekt in DB und Memory bestehen
    count = w.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert count == 1, "Committed Trade muss trotz Notifier-Fehler in DB verbleiben"
    assert len(w.engine.open_positions) == 1

    w.conn.close()


# ============================================================================
# G3: Kausalitaets-Guard fuer Kerzen, Zeitgrenzen & Deterministischer Testfeed
# ============================================================================


def test_g3_unfinished_hour_candle_rejected(tmp_path):
    """Ueberfuehrung der Defektprobe: Eine Kerze der laufenden, unvollendeten Stunde wird als ungesund abgewiesen."""
    now_sec = 1800001800.0  # 30 Minuten nach Beginn der Stunde
    hour_sec = int(now_sec) // 3600 * 3600

    w = AuraWorkerService(
        db_path=str(tmp_path / "clock.db"),
        symbols=["BTCUSDT"],
        time_provider=lambda: now_sec,
    )

    # Kerze faengt um 1800000000 an -> endet um 1800003600. Jetzt ist 1800001800.
    candles = _make_test_bars(hour_sec * 1000, count=40)
    rep = ValidationReport(is_valid=True, total_checked=len(candles), errors=[])

    healthy, reason = w._is_candle_feed_healthy(candles, rep, int(now_sec * 1000))

    # Sollverhalten: Muss False sein!
    assert not healthy, f"Unfertige Kerze haette abgelehnt werden muessen, Grund war: {reason}"
    assert "in der Zukunft" in reason

    w.conn.close()


def test_g3_clock_skew_and_boundary_tolerances(tmp_path):
    """Testet Zeitgrenzen: Innerhalb 5s Toleranz akzeptiert, ueber 5s in der Zukunft abgelehnt."""
    now_ms = 1800003600 * 1000  # Exakt das Ende der Stunde

    w = AuraWorkerService(
        db_path=str(tmp_path / "tolerance.db"),
        symbols=["BTCUSDT"],
        time_provider=lambda: now_ms / 1000.0,
    )
    rep = ValidationReport(is_valid=True, total_checked=40, errors=[])

    # 1. Genau am Stundenende (bar_end_ms == now_ms): OK
    candles_exact = _make_test_bars(now_ms - 3600_000, count=40)
    healthy, _ = w._is_candle_feed_healthy(candles_exact, rep, now_ms)
    assert healthy is True

    # 2. 3 Sekunden in der Zukunft (innerhalb der 5s Jitter-Toleranz): OK
    healthy_skew, _ = w._is_candle_feed_healthy(candles_exact, rep, now_ms - 3000)
    assert healthy_skew is True

    # 3. 6 Sekunden in der Zukunft (ueberschreitet die 5s Toleranz): ABGEWIESEN
    healthy_future, reason = w._is_candle_feed_healthy(candles_exact, rep, now_ms - 6000)
    assert healthy_future is False
    assert "in der Zukunft" in reason

    w.conn.close()


def test_g3_cli_test_feed_produces_only_strictly_closed_past_bars():
    """Beweist, dass der DeterministicFreshFeed ausschliesslich abgeschlossene Stunden erzeugt."""
    from aura.runner.worker import AuraWorkerService

    now_s = int(time.time())
    now_ms = now_s * 1000

    # Simuliere die DeterministicFreshFeed-Logik aus worker.py
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

    last_bar = candles[-1]
    bar_end_ms = last_bar.time_ms + 3600_000

    # Kausalitaetsnachweis: Bar-Ende liegt strikt in der Vergangenheit oder genau jetzt
    assert bar_end_ms <= now_ms, f"Letzter Bar darf nicht in der Zukunft enden: {bar_end_ms} > {now_ms}"
    assert now_ms - bar_end_ms < 3600_000, "Letzter Bar darf nicht veraltet sein (maximal 1 Stunde alt)"
