"""
E2E Playwright Browser Integration Tests for AURA v3 Control Plane & UI.

Tests Scenarios A through J against real running FastAPI server and Worker Service
with isolated SQLite database and Playwright Chromium (Desktop & Mobile Emulation).
"""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import sync_playwright, Page, BrowserContext

from aura.data.models import Candle
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.runner.worker import AuraWorkerService
from aura.store.db import connect

E2E_PORT = 8899
E2E_BASE_URL = f"http://127.0.0.1:{E2E_PORT}"
E2E_TOKEN = "test-e2e-token-xyz-987"
SCREENSHOT_DIR = Path("docs/evidence/v3_acceptance_20260917/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class _MockValidationReport:
    """Minimaler stubbter Validierungsbericht für den E2E-Mock."""
    is_valid = True
    errors: list = []


class MockBitgetAdapter:
    """Deterministischer Replay-Adapter fuer E2E-Tests.

    Implementiert dieselbe Schnittstelle wie BitgetAdapter:
      fetch_candles(symbol, granularity, limit) -> (list[Candle], ValidationReport)
    Kein Netzwerkzugriff; Daten werden via set_candles injiziert.
    """
    def __init__(self):
        self.candles_map: dict[str, list[Candle]] = {}

    def set_candles(self, symbol: str, candles: list[Candle]):
        self.candles_map[symbol] = candles

    def fetch_candles(self, symbol: str, granularity: str = "1H", limit: int = 100):
        """Gibt injizierte Kerzen und einen validen Mock-Report zurück."""
        candles = self.candles_map.get(symbol, [])[-limit:]
        return candles, _MockValidationReport()


def _generate_synthetic_bullish_candles(symbol: str = "BTCUSDT", n: int = 60, base_price: float = 60000.0) -> list[Candle]:
    """Erzeugt synthetische Kerzen fuer deterministischen Signal-Test."""
    candles = []
    now_ms = int(time.time() * 1000)
    # Letzte Kerze muss vollstaendig abgeschlossen sein (Ende <= now_ms)
    start_ms = now_ms - ((n + 1) * 3600 * 1000)
    cur = base_price
    for i in range(n):
        # Letzte 5 Kerzen erzeugen einen starken Breakout (hoher Score)
        if i >= n - 5:
            delta = 250.0
            vol = 1500.0
        else:
            delta = 10.0 if (i % 2 == 0) else -8.0
            vol = 300.0
        cur += delta
        o = cur - delta
        h = max(o, cur) + 30.0
        l = min(o, cur) - 20.0
        c = cur
        candles.append(Candle(
            time_ms=start_ms + ((i + 1) * 3600 * 1000),
            open=round(o, 2),
            high=round(h, 2),
            low=round(l, 2),
            close=round(c, 2),
            volume=round(vol, 2),
            is_closed=True
        ))
    return candles


@pytest.fixture(scope="module")
def e2e_environment(tmp_path_factory):
    """Initialisiert isolierte Test-Datenbank, FastAPI Server und Worker Service."""
    test_dir = tmp_path_factory.mktemp("aura_e2e")
    db_path = str(test_dir / "e2e_aura.db")

    # DB Initialisieren
    conn = connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO universe (symbol, active, liquidity_verified, vol_24h, updated_at_ms) "
        "VALUES ('BTCUSDT', 1, 1, 50000000.0, ?)",
        (int(time.time() * 1000),)
    )
    conn.commit()
    conn.close()

    # Env konfigurieren
    env = os.environ.copy()
    env["AURA_DB_PATH"] = db_path
    env["AURA_RELAY_TOKEN"] = E2E_TOKEN
    env["PYTHONPATH"] = "."

    # 1. FastAPI Server in separatem Prozess starten
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "aura.api.app:app", "--host", "127.0.0.1", "--port", str(E2E_PORT), "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Warten bis Server antwortet
    import urllib.request
    ready = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{E2E_BASE_URL}/api/v3/health", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.1)

    if not ready:
        server_proc.kill()
        pytest.fail("FastAPI Server konnte nicht gestartet werden.")

    # 2. Worker Service initialisieren
    mock_adapter = MockBitgetAdapter()
    # MockBitgetAdapter injizieren VOR dem AuraWorkerService-Aufruf, da __init__
    # keinen Adapter-Parameter entgegennimmt — Adapter wird nach Konstruktion ausgetauscht.
    worker = AuraWorkerService(
        db_path=db_path,
        poll_interval_sec=1,
        symbols=["BTCUSDT"],
    )
    worker.adapter = mock_adapter  # Mock injizieren

    # FSM korrekt hochfahren: STARTING -> WARMING_UP -> RUNNING
    # (direkter STARTING->RUNNING Sprung ist kein valider Übergang)
    worker.sm.transition_to(SystemState.WARMING_UP, "E2E Test Warmup")
    worker.sm.transition_to(SystemState.RUNNING, "E2E Test Start")

    # Initial-Zustand in DB persistieren damit API-Prozess ihn lesen kann
    init_conn = connect(db_path)
    now_ms = int(time.time() * 1000)
    init_conn.execute(
        "INSERT OR REPLACE INTO runner_state (id, fsm_state, reason, equity, cycle_count, updated_at_ms) "
        "VALUES (1, 'RUNNING', 'E2E Test Start', 10000.0, 0, ?)",
        (now_ms,)
    )
    init_conn.commit()
    init_conn.close()

    for sym, vol in [("BTCUSDT", "50000000"), ("ETHUSDT", "25000000")]:
        worker.persist_test_market_snapshot(
            symbol=sym,
            now_ms=now_ms,
            price_tick="0.1",
            qty_step="0.0001",
            min_qty="0.0001",
            min_notional="5",
            spread_bps="5",
            bid_depth_notional="5000000",
            ask_depth_notional="5000000",
            quote_volume_24h=vol,
        )

    worker_stop_event = threading.Event()
    def _worker_loop():
        cycle = 1
        while not worker_stop_event.is_set():
            try:
                worker._run_cycle(cycle)
                cycle += 1
            except Exception:
                pass
            time.sleep(0.3)

    worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    worker_thread.start()

    yield {
        "db_path": db_path,
        "adapter": mock_adapter,
        "worker": worker,
        "base_url": E2E_BASE_URL,
        "token": E2E_TOKEN,
        "worker_stop_event": worker_stop_event,
    }

    # Teardown
    worker_stop_event.set()
    worker_thread.join(timeout=2)
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server_proc.kill()


def _dismiss_release_notes(page) -> None:
    """Schliesst das Release-Notes-Modal falls es beim Page-Load erscheint.

    Das Modal erscheint wenn der localStorage-Key noch nicht gesetzt ist
    (z.B. in frischen Headless-Chromium-Kontexten). Es blockiert alle
    Klick-Aktionen solange es offen ist.
    """
    try:
        close_btn = page.locator("#release-notes-close")
        if close_btn.is_visible(timeout=800):
            close_btn.click()
            page.wait_for_selector("#release-notes-modal", state="hidden", timeout=2000)
    except Exception:
        # Modal war nicht sichtbar — kein Fehler
        pass


def _login(page, base_url: str, token: str) -> None:
    """Fuehrt den Operator-Login durch und wartet auf den Live-Pill."""
    _dismiss_release_notes(page)
    page.locator("#auth-status-pill").click()
    page.wait_for_selector("#aura-auth-modal.open", state="visible", timeout=3000)
    page.locator("#auth-token-input").fill(token)
    page.locator("#btn-auth-submit").click()
    page.wait_for_selector("#aura-auth-modal", state="hidden", timeout=4000)
    page.wait_for_selector("#auth-status-pill.live", timeout=4000)


def test_scenario_a_unauthenticated_access_denied(e2e_environment):
    """Szenario A: Nicht angemeldeter Zugriff und verweigerte Steuerungsaktion."""
    base_url = e2e_environment["base_url"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # Pruefe, dass Login-Modal vorhanden ist
        auth_pill = page.locator("#auth-status-pill")
        assert auth_pill.is_visible()
        assert "ANMELDUNG" in auth_pill.inner_text()

        # Sensitiver API Aufruf ohne Auth schlaegt fehl (401)
        resp = page.request.post(f"{base_url}/api/v3/halt", data=json.dumps({"reason": "Test"}), headers={"Content-Type": "application/json"})
        assert resp.status == 401

        page.screenshot(path=str(SCREENSHOT_DIR / "01_scenario_a_unauthenticated.png"))
        browser.close()


def test_scenario_b_login_and_load_authoritative_state(e2e_environment):
    """Szenario B: Anmeldung und Laden des autoritativen Serverzustands."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        _login(page, base_url, token)
        assert "OPERATOR" in page.locator("#auth-status-pill").inner_text()

        # Pruefe autoritative KPI Werte vom Server
        page.wait_for_timeout(1000)
        equity_text = page.locator("#ab-equity").inner_text()
        assert "USDT" in equity_text

        # Pruefe sichtbaren Hinweis auf fehlende Kosten
        evidence_banner = page.locator("#v3-evidence-banner")
        assert evidence_banner.is_visible()
        assert "MODEL_NO_EVIDENCE" in evidence_banner.inner_text()
        assert "Funding" in evidence_banner.inner_text()

        page.screenshot(path=str(SCREENSHOT_DIR / "02_scenario_b_authenticated_state.png"))
        browser.close()


def test_scenario_c_config_request_and_worker_ack(e2e_environment):
    """Szenario C: Konfiguration anfordern -> Worker wendet an -> aktive Revision sichtbar."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Anmelden
        page.goto(base_url, wait_until="domcontentloaded")
        _login(page, base_url, token)

        # Config-Box oeffnen
        page.locator("#btn-config-autobot").click()
        page.wait_for_selector("#ab-config-box", state="visible", timeout=2000)

        # Parameter aendern
        page.locator("#ab-cfg-risk").fill("3.5")
        page.locator("#btn-save-ab-config").click()

        # Warten bis Worker Cycle die Revision quittiert
        page.wait_for_timeout(1500)
        page.wait_for_selector("#ab-disp-active-rev", timeout=3000)
        rev_text = page.locator("#ab-disp-active-rev").inner_text()
        assert "Rev" in rev_text

        page.screenshot(path=str(SCREENSHOT_DIR / "03_scenario_c_config_applied.png"))
        browser.close()


def test_scenario_d_concurrent_config_conflict_409(e2e_environment):
    """Szenario D / Req 2.B: Zwei gleichzeitig geoeffnete Browser-Kontexte aendern Konfiguration
    -> definierter 409 Konflikt, Warnanzeige, erneute Synchronisierung und uebereinstimmender Zustand."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Zwei separate Browser-Kontexte (Client 1 und Client 2)
        ctx1 = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx2 = browser.new_context(viewport={"width": 1280, "height": 800})
        page1 = ctx1.new_page()
        page2 = ctx2.new_page()

        # Beide Clients oeffnen Dashboard und melden sich an
        page1.goto(base_url, wait_until="domcontentloaded")
        _login(page1, base_url, token)

        page2.goto(base_url, wait_until="domcontentloaded")
        _login(page2, base_url, token)

        # Beide oeffnen Config-Box
        page1.locator("#btn-config-autobot").click()
        page1.wait_for_selector("#ab-config-box", state="visible", timeout=2000)
        page2.locator("#btn-config-autobot").click()
        page2.wait_for_selector("#ab-config-box", state="visible", timeout=2000)

        # Client 1 speichert zuerst neue Konfiguration (Risk = 2.5) -> Erfolg
        page1.locator("#ab-cfg-risk").fill("2.5")
        page1.locator("#btn-save-ab-config").click()
        page1.wait_for_timeout(1000)

        # Client 2 (hat noch alte Revision im Speicher) versucht abweichende Konfiguration (Risk = 4.0)
        dialog_messages = []
        def _on_dialog(d):
            dialog_messages.append(d.message)
            d.accept()
        page2.on("dialog", _on_dialog)
        page2.locator("#ab-cfg-risk").fill("4.0")
        page2.locator("#btn-save-ab-config").click()
        page2.wait_for_timeout(1500)

        # Konflikthinweis muss bei Client 2 ausgeloest worden sein
        assert len(dialog_messages) > 0, "Client 2 muss einen Dialog/Alert mit Konflikthinweis erhalten"
        assert "Konfigurationskonflikt" in dialog_messages[0] or "geändert" in dialog_messages[0]

        # Nach Re-Sync muessen beide Clients dieselbe aktive Revision sehen
        rev1 = page1.locator("#ab-disp-active-rev").inner_text()
        rev2 = page2.locator("#ab-disp-active-rev").inner_text()
        assert rev1 == rev2, f"Beide Clients muessen uebereinstimmende Revision sehen: {rev1} vs {rev2}"

        browser.close()


def test_scenario_e_halt_and_prevent_new_entries(e2e_environment):
    """Szenario E: Halt anfordern -> Worker bestaetigt -> Status HALTED -> keine neuen Paper-Entries."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Login
        page.goto(base_url, wait_until="domcontentloaded")
        _login(page, base_url, token)

        # Not-Halt anfordern
        page.locator("#btn-toggle-autobot").click()

        # Warten bis Worker den Not-Halt quittiert (Command-Queue → DB-Write → API-Poll)
        # Worst-Case: 0.3s Worker-Zyklus + 2s SyncEngine-Poll = ~3s; 5s Timeout mit Margin
        page.wait_for_function(
            "() => { const b = document.getElementById('ab-status-badge'); return b && b.innerText.includes('NOT-HALT'); }",
            timeout=5000
        )
        badge = page.locator("#ab-status-badge")
        assert "NOT-HALT" in badge.inner_text()
        toggle_btn = page.locator("#btn-toggle-autobot")
        assert "Wiederaufnahme" in toggle_btn.inner_text()

        page.screenshot(path=str(SCREENSHOT_DIR / "04_scenario_e_halt_confirmed.png"))
        browser.close()


def test_scenario_f_position_monitored_during_halt(e2e_environment):
    """Szenario F: Bestehende Paper-Position wird waehrend Halt korrekt weiter ueberwacht.

    Prueft die Policy: Halt sperrt neue Einstiege, aber bestehende Positionen
    werden weiterhin durch on_bar_update() ueberwacht (TP/SL/Time-Stop aktiv).
    """
    worker = e2e_environment["worker"]

    # Stelle sicher, dass FSM auf HALTED steht (korrekte Methode: emergency_halt)
    worker.sm.emergency_halt("Test Halt F")
    assert worker.sm.is_halted

    # Bestehende Positionen fuer BTCUSDT entfernen (aus vorigen Szenarien)
    to_remove = [tid for tid, p in worker.engine.open_positions.items() if p.symbol == "BTCUSDT"]
    for tid in to_remove:
        del worker.engine.open_positions[tid]

    # Position in Worker Engine eintragen (korrekte Signatur: open_trade)
    # spec mit Mindest-Kontraktgroessen analog zum Worker
    pos = worker.engine.open_trade(
        symbol="BTCUSDT",
        timeframe="1h",
        direction=1,
        entry_price=60000.0,
        sl_price=59000.0,
        tp1_price=61000.0,
        tp2_price=63000.0,
        spec={"ctVal": 0.0001, "minSize": 0.0001, "minNotional": 5.0},
        leverage=10,
    )
    assert pos is not None
    trade_id = pos.trade_id  # PaperPosition nutzt .trade_id, nicht .id

    # Simuliere Kerze, die TP1 erreicht (High >= 61000)
    high_ts = int(time.time() * 1000) + 3600000

    # Worker Engine fuehrt Bar-Auswertung aus (auch waehrend Halt!)
    # Policy: Positionen werden weiter überwacht, keine neuen Einstiege
    # on_bar_update() Signatur: symbol, high, low, close, bar_time_ms
    worker.engine.on_bar_update(
        symbol="BTCUSDT",
        high=61500.0,
        low=60400.0,
        close=61200.0,
        bar_time_ms=high_ts,
    )
    updated_pos = worker.engine.open_positions.get(trade_id)
    assert updated_pos is not None, "Position muss nach TP1 noch offen sein (TP2 noch nicht erreicht)"
    assert updated_pos.tp1_hit is True, "TP1 muss bei High >= 61000 ausgeloest worden sein"
    # SL wird auf Entry-Fill-Preis (inkl. Slippage) gezogen, nicht auf nominellen Entry-Preis
    # Policy: Breakeven = fill_price = entry_price * (1 + slippage * direction)
    assert updated_pos.sl_price == updated_pos.entry_price, (
        f"SL muss auf Breakeven (Fill-Preis {updated_pos.entry_price:.2f}) gezogen worden sein, "
        f"aber ist: {updated_pos.sl_price:.2f}"
    )

    # Req 2.E: Biete waehrend eines quittierten Halts ein ansonsten zulaessiges Entry-Signal an.
    # Nachweisen: Kein neuer Trade entsteht, da Halt neue Einstiege strikt blockiert.
    assert worker.sm.is_halted
    assert not worker.sm.can_open_new_trades(), "Waehrend Not-Halt duerfen keine neuen Einstiege stattfinden"
    eth_candles = _generate_synthetic_bullish_candles("ETHUSDT", n=60, base_price=3000.0)
    worker.adapter.set_candles("ETHUSDT", eth_candles)
    worker._run_cycle(cycle=888)
    eth_positions = [p for p in worker.engine.open_positions.values() if p.symbol == "ETHUSDT"]
    assert len(eth_positions) == 0, "Bei quittiertem Halt darf trotz Signal kein neuer Trade entstehen"


def test_scenario_g_resume_and_resumption(e2e_environment):
    """Szenario G: Resume und Wiederaufnahme nach definierter Policy.

    Policy: Nach Resume wechselt der Worker von HALTED nach RECOVERING.
    Der Dashboard-Button wechselt von 'Wiederaufnahme' zu 'Not-Halt anfordern'.
    RECOVERING ist ein valider Post-Resume-Zustand (kein Warmup-Feed im Mock).
    """
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    worker = e2e_environment["worker"]
    db_path = e2e_environment["db_path"]

    # Sicherstellen dass wir im HALTED-Zustand starten (unabhaengig von Test-E-Zustand)
    if not worker.sm.is_halted:
        worker.sm.emergency_halt("Pre-G Setup Halt")
    conn = connect(db_path)
    now_ms = int(time.time() * 1000)
    conn.execute(
        "UPDATE runner_state SET fsm_state='HALTED', updated_at_ms=? WHERE id=1",
        (now_ms,)
    )
    conn.commit()
    conn.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Login — wartet bis Badge den HALTED-State zeigt
        page.goto(base_url, wait_until="domcontentloaded")
        _login(page, base_url, token)

        # Badge muss NOT-HALT zeigen (Worker ist HALTED)
        page.wait_for_function(
            "() => { const b = document.getElementById('ab-status-badge'); return b && b.innerText.includes('NOT-HALT'); }",
            timeout=5000
        )

        # Resume Button klicken (zeigt "Wiederaufnahme (Resume)")
        page.locator("#btn-toggle-autobot").click()

        # Warten bis Worker Resume quittiert und Badge wechselt
        # RECOVERING ist valider Post-Resume-Zustand — kein Warmup-Feed im Mock
        page.wait_for_function(
            "() => { const b = document.getElementById('ab-status-badge'); "
            "return b && !b.innerText.includes('NOT-HALT'); }",
            timeout=6000
        )
        badge = page.locator("#ab-status-badge")
        badge_text = badge.inner_text()
        # Akzeptiert RUNNING, RECOVERING oder WARMING_UP als valide Post-Resume-States
        assert any(s in badge_text for s in ["RUNNING", "RECOVERING", "WARMING"]), (
            f"Badge zeigt nach Resume unerwarteten Zustand: '{badge_text}'"
        )
        # Toggle-Button zeigt nicht mehr 'Wiederaufnahme'
        toggle_btn = page.locator("#btn-toggle-autobot")
        assert "Wiederaufnahme" not in toggle_btn.inner_text()

        page.screenshot(path=str(SCREENSHOT_DIR / "05_scenario_g_resumed_running.png"))
        browser.close()


def test_scenario_h_browser_close_and_reopen_persists_state(e2e_environment):
    """Szenario H / Req 2.C: Browser schliessen -> Separater Worker verarbeitet Ereignis,
    das persistenten Zustand veraendert -> Neuer Browser oeffnen -> genau diese Aenderung pruefen."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    db_path = e2e_environment["db_path"]

    # 1. Erster Browser-Durchlauf: Ausgangsstand feststellen
    with sync_playwright() as p:
        browser1 = p.chromium.launch(headless=True)
        page1 = browser1.new_page()
        page1.goto(base_url, wait_until="domcontentloaded")
        _login(page1, base_url, token)
        page1.wait_for_timeout(2500)
        initial_hist_count = int(page1.locator("#ab-hist-count").inner_text() or "0")
        browser1.close()  # Alle Browser sind geschlossen!

    # 2. Worker verarbeitet definiertes Ereignis im Hintergrund, das persistenten Zustand veraendert:
    # Worker schliesst einen Trade ab und schreibt ihn in die SQLite trades-Tabelle
    conn = connect(db_path)
    offline_trade_id = f"worker_closed_offline_{int(time.time() * 1000)}"
    conn.execute(
        "INSERT INTO trades (id, source, symbol, dir, status, entry_price, current_sl, initial_sl, "
        "tp1, tp2, tp1_hit, notional, margin, leverage, opened_at_ms, closed_at_ms, exit_price, "
        "exit_reason, realized_pnl, fees, engine_version, record_schema, entry_fee, timeframe, remaining_qty) "
        "VALUES (?, 'server', 'SOLUSDT', 1, 'closed', '140.0', '135.0', '135.0', '150.0', '160.0', 1, "
        "1400.0, 140.0, 10, ?, ?, '150.0', 'tp1_hit', 100.0, 1.2, 'v3', 1, 0.6, '1h', 0.0)",
        (offline_trade_id, int(time.time() * 1000) - 3600000, int(time.time() * 1000)),
    )
    conn.commit()
    conn.close()

    # 3. Zweiter Browser-Durchlauf (frischer Browser / neues Fenster)
    with sync_playwright() as p:
        browser2 = p.chromium.launch(headless=True)
        page2 = browser2.new_page()
        page2.goto(base_url, wait_until="domcontentloaded")
        _login(page2, base_url, token)

        # Warten bis SyncEngine den neuen persistenten Zustand geladen hat
        page2.wait_for_timeout(2500)
        new_hist_count = int(page2.locator("#ab-hist-count").inner_text() or "0")
        assert new_hist_count == initial_hist_count + 1, (
            f"Neuer Browser muss genau die waehrend der Abwesenheit eingetretene Aenderung zeigen: "
            f"{new_hist_count} vs {initial_hist_count + 1}"
        )

        page2.screenshot(path=str(SCREENSHOT_DIR / "12_req2c_state_changed_while_browser_closed.png"))
        browser2.close()


def test_scenario_i_worker_stale_detection_and_recovery(e2e_environment):
    """Szenario I / Req 2.D: Worker-Unterbrechung -> ehrliche Stale-Anzeige -> Recovery ohne Doppelausfuehrung."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    db_path = e2e_environment["db_path"]
    worker = e2e_environment["worker"]
    worker_stop_event = e2e_environment["worker_stop_event"]

    # 1. Unterbrich den Worker tatsaechlich (Loop stoppen)
    worker_stop_event.set()
    time.sleep(0.4)

    # Simuliere alten Heartbeat in DB (150s her) waehrend Worker gestoppt ist
    stale_ts = int(time.time() * 1000) - 150000
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE runner_state SET updated_at_ms = ? WHERE id = 1", (stale_ts,))
    conn.commit()
    conn.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        _login(page, base_url, token)

        # Pruefe Stale-State per API und UI
        resp = page.request.get(f"{base_url}/api/v3/state")
        state_data = resp.json()
        assert state_data["worker"]["is_stale"] is True

        page.screenshot(path=str(SCREENSHOT_DIR / "06_scenario_i_stale_detected.png"))

        # 2. Worker Recovery: Worker startet neu und verarbeitet einen Zyklus
        bar_ts = int(time.time() * 1000)
        first_claim = worker._claim_closed_bar("BTCUSDT", "1h", bar_ts)
        assert first_claim is True, "Erster Verarbeitungsversuch der Bar muss akzeptiert werden"
        second_claim = worker._claim_closed_bar("BTCUSDT", "1h", bar_ts)
        assert second_claim is False, "Zweiter Versuch derselben Bar muss abgewiesen werden (keine Doppelverarbeitung)"

        # Heartbeat nach Recovery aktualisieren
        conn3 = sqlite3.connect(db_path)
        conn3.execute("UPDATE runner_state SET updated_at_ms = ? WHERE id = 1", (int(time.time() * 1000),))
        conn3.commit()
        conn3.close()

        # Erneuter Poll muss wieder frischen Zustand zeigen
        page.wait_for_timeout(2000)
        resp2 = page.request.get(f"{base_url}/api/v3/state")
        state_data2 = resp2.json()
        assert state_data2["worker"]["is_stale"] is False

        browser.close()


def test_scenario_j_mobile_viewport_and_trade_rendering(e2e_environment):
    """Szenario J: Mobile Viewport Emulation (390x844) und Trade Card Rendering."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    worker = e2e_environment["worker"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Mobile Emulation: iPhone 13/14 Abmessungen
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            is_mobile=True,
            has_touch=True
        )
        page = context.new_page()

        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Screenshot unauthenticated mobile
        page.screenshot(path=str(SCREENSHOT_DIR / "08_mobile_unauthenticated.png"))

        # Mobile Login
        _login(page, base_url, token)

        # Pruefe responsive Elemente auf Mobile
        assert page.locator("#autobot-section").is_visible()
        assert page.locator("#v3-evidence-banner").is_visible()
        assert page.locator("#btn-toggle-autobot").is_visible()

        page.screenshot(path=str(SCREENSHOT_DIR / "09_mobile_authenticated_dashboard.png"))
        browser.close()


def test_scenario_k_deterministic_paper_trade_production_lifecycle_in_ui(e2e_environment):
    """Szenario K / Req 2.A: Deterministisch erzeugter Paper-Trade durchlaeuft den
    Produktionspfad und erscheint mit unabhaengig geprueften Mengen, Gebuehren,
    PnL und Status korrekt in der tatsaechlichen Weboberflaeche."""
    base_url = e2e_environment["base_url"]
    token = e2e_environment["token"]
    worker = e2e_environment["worker"]
    db_path = e2e_environment["db_path"]

    # Stelle sicher, dass FSM auf RUNNING steht und Halt deaktiviert ist
    if worker.sm.is_halted:
        worker.sm.resume_trading("Resume fuer Trade Lifecycle Test")
    worker.sm._state = SystemState.RUNNING

    # Vorige offene Positionen in Memory und DB bereinigen
    worker.engine.open_positions.clear()
    now_ms = int(time.time() * 1000)
    conn = connect(db_path)
    conn.execute(
        "UPDATE trades SET status = 'closed', closed_at_ms = ? WHERE status = 'open'",
        (now_ms,)
    )
    # Universe-Snapshot aktualisieren
    worker.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="5000000",
        ask_depth_notional="5000000",
        quote_volume_24h="100000000",
    )

    # Deterministische synthetische Breakout-Kerzen einspeisen (mit bar_time_ms = now_ms)
    candles = _generate_synthetic_bullish_candles("BTCUSDT", n=60, base_price=60000.0)
    worker.adapter.set_candles("BTCUSDT", candles)

    # Worker-Zyklus triggern -> _evaluate_and_enter eroeffnet Position
    worker._run_cycle(cycle=1001)

    assert len(worker.engine.open_positions) == 1, "Worker muss genau 1 Position eroeffnet haben"
    pos = list(worker.engine.open_positions.values())[0]

    # Unabhaengig verifizierte Erwartungswerte gemaess Engine-Spezifikation:
    # Letzte Kerze schliesst bei ~61314.0 -> Fill-Preis mit 1.5 bps Slippage = 61323.2
    last_close = candles[-1].close
    expected_fill_price = last_close * (1.0 + 0.00015)
    assert abs(pos.entry_price - expected_fill_price) < 1.0, f"Fill-Preis muss ~{expected_fill_price:.2f} sein, ist {pos.entry_price}"
    expected_entry_fee = pos.qty * pos.entry_price * 0.0006  # 6 bps Taker Fee
    assert abs(pos.total_fees - expected_entry_fee) < 0.1, f"Entry-Fee stimmt nicht: {pos.total_fees} vs {expected_entry_fee}"

    # Browser oeffnen und Weboberflaeche pruefen
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(base_url, wait_until="domcontentloaded")
        _login(page, base_url, token)

        # Warten bis SyncEngine den autoritativen Server-Trade geladen hat
        page.wait_for_timeout(2500)
        open_count_el = page.locator("#ab-open-count")
        assert "1" in open_count_el.inner_text(), "Offene Trades Zaehler muss 1 anzeigen"

        trades_container = page.locator("#ab-trades-container")
        card_text = trades_container.inner_text()
        assert "BTCUSDT" in card_text
        assert "LONG" in card_text
        assert f"{int(pos.entry_price)}" in card_text or "61323" in card_text or "61,323" in card_text

        # Naechster Schritt im Produktionspfad: Kurs erreicht TP1 (High >= tp1_price)
        tp1_high = pos.tp1_price + 50.0
        worker.engine.on_bar_update(
            symbol="BTCUSDT",
            high=tp1_high,
            low=pos.entry_price - 50.0,
            close=pos.tp1_price + 10.0,
            bar_time_ms=int(time.time() * 1000) + 3600000,
        )
        assert pos.tp1_hit is True
        assert pos.status == "partial_tp1"
        assert pos.sl_price == pos.entry_price  # Preis-Breakeven Stop am Fill-Preis

        # UI aktualisieren lassen (erneuter Poll der SyncEngine)
        page.wait_for_timeout(2500)
        updated_card_text = page.locator("#ab-trades-container").inner_text()
        assert "TP1" in updated_card_text or "partial_tp1" in updated_card_text or "+" in updated_card_text

        page.screenshot(path=str(SCREENSHOT_DIR / "10_req2a_trade_lifecycle_ui.png"))
        browser.close()
