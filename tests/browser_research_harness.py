from __future__ import annotations

import asyncio
import glob
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]

# External hosts the dashboard may legitimately contact for fallback/context data
# (Binance/Bybit/CoinGecko/FNG/CoinLore). Everything else must never be reached.
ALLOWED_EXTERNAL_HOSTS = {
    "api.bitget.com", "api.binance.com", "data-api.binance.vision",
    "api.bybit.com", "api.coingecko.com", "api.alternative.me",
    "api.coinlore.net", "fapi.binance.com", "fapi.binance.vision",
}
ALLOWED_WS_HOSTS = {
    "stream.binance.com",
    "data-stream.binance.vision",
}


def discover_chromium() -> str | None:
    """Return a locally installed Chromium / Chrome executable across Linux, Windows, macOS."""
    candidates = []
    # Linux / WSL playwright cache
    candidates.extend(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    # Windows playwright cache
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(glob.glob(str(Path(local_app_data) / "ms-playwright/chromium-*/chrome-win*/chrome.exe")))
    candidates.extend(glob.glob(str(Path.home() / "AppData/Local/ms-playwright/chromium-*/chrome-win*/chrome.exe")))
    # Windows system Chrome / Edge fallbacks
    for sys_path in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(sys_path):
            candidates.append(sys_path)
    # macOS
    candidates.extend(glob.glob(str(Path.home() / "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium")))

    return sorted(candidates, reverse=True)[0] if candidates else None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_relay(port: int) -> subprocess.Popen:
    env = {**os.environ, "SYM_PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, "bitget_relay.py"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_serving(port: int, timeout: float = 10.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/serving", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.05)
    return False


async def run_case(port: int, chromium: str | None = None) -> dict:
    """Execute the full browser assertion suite against a relay on `port`."""
    url = f"http://127.0.0.1:{port}/"
    console_errors: list[str] = []
    page_errors: list[str] = []
    requests: list[dict] = []
    blocked_external: set[str] = set()
    unexpected_external: list[str] = []
    ws_hosts: list[str] = []

    async with async_playwright() as p:
        if chromium:
            browser = await p.chromium.launch(headless=True, executable_path=chromium)
        else:
            browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("websocket", lambda ws: ws_hosts.append(urllib.parse.urlparse(ws.url).hostname or ""))

        async def route_handler(route):
            request = route.request
            host = urllib.parse.urlparse(request.url).hostname or ""
            if host in ("127.0.0.1", "localhost"):
                if request.url.endswith("/api/public"):
                    # Mock empty public data response so no real network traffic occurs.
                    await route.fulfill(status=200, content_type="application/json", body=json.dumps({"code": "00000", "data": []}))
                    return
                await route.continue_()
                return
            if host in ALLOWED_EXTERNAL_HOSTS:
                blocked_external.add(host)
            else:
                unexpected_external.append(request.url)
            await route.fulfill(status=200, content_type="application/json", body="null")

        await page.route("**/*", route_handler)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_selector("#chart", timeout=15_000)
        await page.evaluate("""() => {
          const btn = document.getElementById('release-notes-ok');
          if (btn) btn.click();
        }""")

        title = await page.title()
        assert "AURA" in title.upper(), title

        # Information hierarchy: the optimizer belongs directly below Setup
        # Validation; market context remains in-page, while Action Radar uses
        # an accessible off-canvas drawer instead of consuming page height.
        layout = await page.evaluate("""() => {
          const terminal = document.querySelector('.terminal-grid');
          const main = document.querySelector('main.focus-column');
          const aside = document.querySelector('aside#radarcard.radar-drawer');
          const mtf = main && main.querySelector('#mtfcard');
          const derivatives = main && main.querySelector('#derivatives-card');
          const sig = main && main.querySelector('#sigcard');
          const optimizer = main && main.querySelector('#time-stop-optimizer');
          const research = main && main.querySelector('.research-stack');
          const hero = document.querySelector('main.focus-column > #hero');
          const chart = document.querySelector('.validation-grid #chart');
          const backtest = document.querySelector('.backtest-panel #bttbl');
          const opener = document.getElementById('radar-open');
          return {
            macro: !!document.querySelector('.macrobar #macro-btc'),
            terminalColumns: terminal ? getComputedStyle(terminal).gridTemplateColumns.split(' ').length : 0,
            contextOrder: !!(mtf && derivatives && mtf.compareDocumentPosition(derivatives) & Node.DOCUMENT_POSITION_FOLLOWING),
            optimizerInResearch: !!(research && optimizer && research.contains(optimizer)),
            optimizerAfterValidation: !!(sig && optimizer && sig.compareDocumentPosition(optimizer) & Node.DOCUMENT_POSITION_FOLLOWING),
            optimizerOutsideBacktest: !document.querySelector('.backtest-panel #auto-timestop'),
            radarOutsideMain: !!(aside && main && !main.contains(aside)),
            radarScrollable: aside ? ['auto', 'scroll'].includes(getComputedStyle(document.getElementById('radarlist')).overflowY) : false,
            radarInitiallyClosed: !!(aside && aside.getAttribute('aria-hidden') === 'true' && opener && opener.getAttribute('aria-expanded') === 'false'),
            timeStopPresent: !!document.querySelector('#time-stop-optimizer #auto-timestop'),
            timeStopBelowValidation: !!(sig && optimizer && optimizer.getBoundingClientRect().top >= sig.getBoundingClientRect().bottom),
            hero: !!hero,
            chartBelowHero: !!(hero && chart && hero.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING),
            backtestBelowChart: !!(chart && backtest && chart.compareDocumentPosition(backtest) & Node.DOCUMENT_POSITION_FOLLOWING),
          };
        }""")
        assert layout["macro"], layout
        assert layout["terminalColumns"] >= 1 and layout["contextOrder"], layout
        assert layout["optimizerInResearch"] and layout["optimizerAfterValidation"], layout
        assert layout["optimizerOutsideBacktest"] and layout["timeStopPresent"] and layout["timeStopBelowValidation"], layout
        assert layout["radarOutsideMain"] and layout["radarScrollable"], layout
        assert layout["radarInitiallyClosed"], layout
        assert layout["hero"] and layout["chartBelowHero"] and layout["backtestBelowChart"], layout

        # Drawer behavior: open, close with Escape, and restore trigger focus.
        await page.locator('#radar-open').click()
        drawer_open = await page.evaluate("""() => ({
          open: document.getElementById('radarcard').classList.contains('open'),
          hidden: document.getElementById('radarcard').getAttribute('aria-hidden'),
          expanded: document.getElementById('radar-open').getAttribute('aria-expanded'),
          backdrop: document.getElementById('radar-backdrop').classList.contains('open'),
        })""")
        assert drawer_open == {"open": True, "hidden": "false", "expanded": "true", "backdrop": True}, drawer_open
        await page.keyboard.press('Escape')
        drawer_closed = await page.evaluate("""() => ({
          open: document.getElementById('radarcard').classList.contains('open'),
          hidden: document.getElementById('radarcard').getAttribute('aria-hidden'),
          expanded: document.getElementById('radar-open').getAttribute('aria-expanded'),
          focused: document.activeElement === document.getElementById('radar-open'),
        })""")
        assert drawer_closed == {"open": False, "hidden": "true", "expanded": "false", "focused": True}, drawer_closed

        # Responsive drawer path: mobile trigger stays touch-sized and the
        # drawer fills the viewport without horizontal overflow.
        await page.set_viewport_size({"width": 390, "height": 844})
        mobile = await page.evaluate("""() => {
          const launcher = document.getElementById('radar-open').getBoundingClientRect();
          const drawer = document.getElementById('radarcard').getBoundingClientRect();
          return {
            launcherWidth: launcher.width,
            launcherHeight: launcher.height,
            drawerWidth: drawer.width,
            viewportWidth: innerWidth,
            overflow: document.documentElement.scrollWidth - innerWidth,
          };
        }""")
        assert mobile["launcherWidth"] >= 44 and mobile["launcherHeight"] >= 44, mobile
        assert mobile["drawerWidth"] <= mobile["viewportWidth"] + 0.5 and mobile["overflow"] <= 0, mobile
        await page.set_viewport_size({"width": 1440, "height": 1000})

        # The Time-Stop optimizer must execute and apply a bounded result.
        optimizer = await page.evaluate("""async () => {
          const button = document.getElementById('auto-timestop');
          const input = document.getElementById('timestop');
          const status = document.getElementById('timestop-status');
          if (!button || !input || !status) return {present: false};
          if (!App.data.candles || !App.data.chart) return {present: true, loaded: false};
          await autoOptimizeTimeStop();
          return {
            present: true,
            loaded: true,
            value: Number(input.value),
            appValue: Number(App.timeStopBars),
            status: status.textContent,
            enabled: !button.disabled,
          };
        }""")
        assert optimizer["present"], optimizer
        if optimizer.get("loaded"):
            assert 5 <= optimizer["value"] <= 30, optimizer
            assert optimizer["value"] == optimizer["appValue"], optimizer
            assert "Bestes Ergebnis" in optimizer["status"] and optimizer["enabled"], optimizer

        # Read-only invariant: privileged controls and credential inputs are 100% absent.
        forbidden_selectors = [
            "#btgexec", "#el-relay", "#el-key", "#el-secret", "#el-pass",
            "#el-arm", "#el-long", "#el-short", "#el-mode", "#el-log",
            "#el-pos", "#el-test", "#el-auto",
        ]
        for sel in forbidden_selectors:
            count = await page.locator(sel).count()
            assert count == 0, f"Privileged element '{sel}' must be completely removed from DOM (found {count})"

        # Verify core analysis UI elements are present
        assert await page.locator("#chart").count() == 1, "Chart canvas must be present"
        assert await page.locator("#symsel").count() == 1, "Symbol selector must be present"
        assert await page.locator("#tfgrp").count() == 1, "Timeframe group must be present"

        # Invariant: privileged request functions must NOT exist on window/global
        forbidden_fns = ["placeMarketOrder", "relayOp", "elTest", "elPositions", "maybeAutoExec", "dataCoherence", "reportOrderStatus", "readKeys"]
        for fn in forbidden_fns:
            is_def = await page.evaluate(f"typeof window.{fn} !== 'undefined'")
            assert not is_def, f"Privileged function '{fn}' must be removed from JS scope"

        # Generation-token guard: stale async write protection
        stale_gen = await page.evaluate("""async () => {
          const origKlines = fetchKlines;
          const staleCandles = [{ t: 111111, o: 1, h: 2, l: 0.5, c: 1.5, v: 1 }];
          let resolveStale = null;
          fetchKlines = () => new Promise(res => { resolveStale = () => res({ candles: staleCandles, source: 'STALE' }); });
          const before = (App.data.candles || []).map(c => c.t).join(',');
          const p = loadChartData();
          App.gen += 1;
          App.symbol = 'ETHUSDT';
          resolveStale();
          await p.catch(() => {});
          fetchKlines = origKlines;
          return { before, after: (App.data.candles || []).map(c => c.t).join(','), symbol: App.symbol };
        }""")
        assert stale_gen["after"] == stale_gen["before"], stale_gen
        assert stale_gen["symbol"] == "ETHUSDT", stale_gen

        # XSS injection probes
        xss = await page.evaluate("""() => {
          const payload = '<img src=x onerror="window.__xss=1">USDT';
          window.__xss = 0;
          App.universe = [{ symbol: payload, vol: 1e9, chg: 0.05, funding: 0.001, oi: 1, price: 5000 }];
          renderMarketPulse();
          populateSymbols();
          return {
            escOut: esc(payload),
            xssFired: window.__xss === 1,
            injectedImgs: document.querySelectorAll('#mp-movers img, #mp-funding img, #symsel img').length,
            moversText: document.getElementById('mp-movers').textContent,
          };
        }""")
        assert xss["escOut"] == "&lt;img src=x onerror=&quot;window.__xss=1&quot;&gt;USDT", xss
        assert xss["xssFired"] is False, xss
        assert xss["injectedImgs"] == 0, xss
        assert "<img" in xss["moversText"], xss

        # Paper-Trade Tracker & SOTA Leverage UI verification
        tracker_eval = await page.evaluate("""() => {
          // Inject v1/v2 active and historical test records
          const activeSample = [
            {
              schemaVersion: 2,
              id: 'pt_test_btc',
              coin: 'BTCUSDT',
              dir: 1,
              entry: 60000,
              markPrice: 61500,
              initialMargin: 200,
              remainingMargin: 200,
              leverage: 10,
              initialSl: 59000,
              currentSl: 59000,
              tp: 64000,
              autoBe: true,
              beActive: false,
              trailSl: false,
              openedAt: Date.now() - 3600000,
              status: 'OPEN'
            },
            {
              schemaVersion: 2,
              id: 'pt_test_eth',
              coin: 'ETHUSDT',
              dir: -1,
              entry: 3000,
              markPrice: 2900,
              initialMargin: 100,
              remainingMargin: 100,
              leverage: 5,
              initialSl: 3100,
              currentSl: 3100,
              tp: 2700,
              autoBe: true,
              beActive: false,
              trailSl: false,
              openedAt: Date.now() - 7200000,
              status: 'OPEN'
            }
          ];
          const histSample = [
            {
              schemaVersion: 2,
              id: 'th_sample_1',
              tradeId: 'pt_sample_1',
              eventType: 'FULL_CLOSE',
              fractionClosed: 1.0,
              coin: 'SOLUSDT',
              dir: 1,
              entry: 140,
              exit: 155,
              marginClosed: 100,
              leverage: 10,
              notionalClosed: 1000,
              quantityClosed: 1000 / 140,
              initialSl: 135,
              finalSl: 135,
              tp: 155,
              initialRiskAmountClosed: (1000 / 140) * 5,
              realizedPnlGross: 107.14,
              realizedRoiPct: 107.14,
              realizedR: 3.0,
              reason: 'TP_HIT',
              openedAt: Date.now() - 10000000,
              closedAt: Date.now() - 5000000,
              holdingMs: 5000000
            }
          ];
          
          saveTrades(activeSample);
          saveTradeHistory(histSample);
          
          // Set live prices for active coins
          tradePrices['BTCUSDT'] = 61500;
          tradePrices['ETHUSDT'] = 2900;
          
          renderLiveTrades();
          renderTradeHistory();
          
          // Test BTC bias display
          App.data.btcScore = 78.5;
          App.data.btcRegime = 1;
          App.data.btcUpdatedAt = Date.now();
          renderStatus();
          
          const tradeCards = document.querySelectorAll('#trade-list .trade-card');
          const histCards = document.querySelectorAll('#trade-history-list .history-card');
          const pkOpen = document.getElementById('pkpi-open');
          const pkMargin = document.getElementById('pkpi-margin');
          const btcBar = document.getElementById('macro-btc-bar');
          const btcEl = document.getElementById('macro-btc');
          
          return {
            activeCount: tradeCards.length,
            histCount: histCards.length,
            pkOpenText: pkOpen ? pkOpen.textContent : '',
            pkMarginText: pkMargin ? pkMargin.textContent : '',
            hasPartialButtons: tradeCards.length > 0 && !!tradeCards[0].querySelector('[data-action-tp25]') && !!tradeCards[0].querySelector('[data-action-tp50]'),
            hasBeButton: tradeCards.length > 0 && !!tradeCards[0].querySelector('[data-action-be]'),
            btcRole: btcBar ? btcBar.getAttribute('role') : null,
            btcValNow: btcBar ? btcBar.getAttribute('aria-valuenow') : null,
            btcText: btcEl ? btcEl.textContent : '',
          };
        }""")
        assert tracker_eval["activeCount"] == 2, tracker_eval
        assert tracker_eval["histCount"] == 1, tracker_eval
        assert tracker_eval["pkOpenText"] == "2", tracker_eval
        assert "300.00" in tracker_eval["pkMarginText"], tracker_eval
        assert tracker_eval["hasPartialButtons"] and tracker_eval["hasBeButton"], tracker_eval
        assert tracker_eval["btcRole"] == "progressbar", tracker_eval
        assert tracker_eval["btcValNow"] == "79", tracker_eval
        assert "BULL" in tracker_eval["btcText"], tracker_eval

        # Test responsive viewports and touch targets at 1440px, 390px, and 320px
        for width, height in [(1440, 1000), (390, 844), (320, 640)]:
            await page.set_viewport_size({"width": width, "height": height})
            vp_check = await page.evaluate(f"""() => {{
              const docWidth = document.documentElement.scrollWidth;
              const winWidth = window.innerWidth;
              const overflow = docWidth - winWidth;
              const addBtn = document.getElementById('trade-add');
              const tcBtns = Array.from(document.querySelectorAll('.tc-btn'));
              let minTcBtnHeight = 999;
              tcBtns.forEach(b => {{
                const r = b.getBoundingClientRect();
                if (r.height < minTcBtnHeight) minTcBtnHeight = r.height;
              }});
              return {{
                width: {width},
                overflow: overflow,
                addBtnHeight: addBtn ? addBtn.getBoundingClientRect().height : 0,
                minTcBtnHeight: minTcBtnHeight < 999 ? minTcBtnHeight : 0,
              }};
            }}""")
            assert vp_check["overflow"] <= 0.5, f"Horizontal overflow at {width}px viewport: {vp_check['overflow']}px"
            if width <= 620:
                assert vp_check["minTcBtnHeight"] >= 44, f"Touch target height < 44px on {width}px: {vp_check['minTcBtnHeight']}px"

        await page.set_viewport_size({"width": 1440, "height": 1000})

        # Test manual trade form interactions and projection
        form_check = await page.evaluate("""() => {
          const addBtn = document.getElementById('trade-add');
          const formBox = document.getElementById('trade-form');
          if (addBtn) addBtn.click();
          const formVisible = formBox && !formBox.classList.contains('hidden');
          
          const coinIn = document.getElementById('trade-coin');
          const dirIn = document.getElementById('trade-dir');
          const entryIn = document.getElementById('trade-entry');
          const marginIn = document.getElementById('trade-margin');
          const levIn = document.getElementById('trade-leverage');
          const slIn = document.getElementById('trade-sl');
          const tpIn = document.getElementById('trade-tp');
          
          if (coinIn) coinIn.value = 'SOLUSDT';
          if (dirIn) dirIn.value = '1';
          if (entryIn) entryIn.value = '150';
          if (marginIn) marginIn.value = '100';
          if (levIn) levIn.value = '10';
          if (slIn) slIn.value = '145';
          if (tpIn) tpIn.value = '165';
          
          renderTradeProjection();
          const projBox = document.getElementById('trade-projection');
          return {
            formVisible,
            projText: projBox ? projBox.textContent : '',
          };
        }""")
        assert form_check["formVisible"], form_check
        assert "Notional: 1000.00 USDT" in form_check["projText"], form_check
        assert "R:R: 1:3.00" in form_check["projText"], form_check

        # Clean up test localStorage
        await page.evaluate("""() => {
          localStorage.removeItem('aura-quant-terminal-active-trades-v1');
          localStorage.removeItem('aura-quant-terminal-history-trades-v1');
          renderLiveTrades();
          renderTradeHistory();
        }""")

        ge = await page.evaluate("""() => {
          window.__xss = 0;
          showGlobalError('<img src=x onerror="window.__xss=1">boom');
          const el = document.getElementById('globerr');
          return { fired: window.__xss === 1, imgs: el.querySelectorAll('img').length, text: el.textContent };
        }""")
        assert ge["fired"] is False and ge["imgs"] == 0, ge
        assert "<img" in ge["text"], ge
        await page.evaluate("showGlobalError('')")

        await browser.close()

    assert not page_errors, page_errors
    assert not unexpected_external, unexpected_external
    assert blocked_external <= ALLOWED_EXTERNAL_HOSTS, blocked_external
    assert set(ws_hosts) <= ALLOWED_WS_HOSTS, ws_hosts

    return {
        "title": title,
        "page_errors": page_errors,
        "console_error_count": len(console_errors),
        "blocked_external": sorted(blocked_external),
        "unexpected_external": unexpected_external,
    }


async def main() -> None:
    chromium = discover_chromium()
    runs: list[dict] = []
    used_ports: list[int] = []
    runs_count = int(os.environ.get("SYM_BROWSER_RUNS", "10"))

    for i in range(runs_count):
        port = free_port()
        used_ports.append(port)
        relay = start_relay(port)
        try:
            assert wait_serving(port), "relay did not become ready"
            result = await run_case(port, chromium)
            runs.append(result)
        finally:
            relay.terminate()
            try:
                relay.wait(timeout=5)
            except subprocess.TimeoutExpired:
                relay.kill()

    # Determinism: every run must produce an identical observable result.
    first = runs[0]
    assert all(r == first for r in runs), f"non-identical runs:\n{json.dumps(runs, indent=2)}"

    for port in used_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))

    print(json.dumps({**first, "runs": len(runs), "identical": True}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
