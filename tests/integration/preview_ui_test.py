import asyncio
import os
import json
from playwright.async_api import async_playwright

FAIL_INTENTIONALLY = os.environ.get("FAIL_INTENTIONALLY", "0") == "1"

async def run_tests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        js_errors = []
        forbidden_writes = []
        
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        def handle_request(req):
            if req.method in ["POST", "PUT", "DELETE", "PATCH"]:
                allowed = ["/api/v3/auth/login", "/api/v3/auth/logout", "/api/public"]
                path = req.url.split("?")[0].replace("http://127.0.0.1:8899", "")
                if not any(a == path for a in allowed):
                    forbidden_writes.append(f"{req.method} {req.url}")
                    
        page.on("request", handle_request)
        
        await context.clear_cookies()
        await page.goto("http://127.0.0.1:8899/preview")
        await page.wait_for_timeout(500)
        
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"

        # Login Fake
        await page.locator("#loginTokenInput").fill("wrong_token_123")
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        
        if FAIL_INTENTIONALLY:
            assert False, "BEWUSSTE NEGATIVKONTROLLE"

        # Login Real
        correct_token = os.environ.get("AURA_RELAY_TOKEN", "TEST_INTEGRATION_TOKEN_XYZ")
        await page.locator("#loginTokenInput").fill(correct_token)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(1000)
        assert await page.locator("#pill-auth-txt").inner_text() == "Operator"
        
        # Validate PnL
        await page.locator("#tab-paper-d").click()
        await page.wait_for_selector("#openPosTbody")
        await page.wait_for_timeout(200)
        row = page.locator("#openPosTbody tr", has_text="ETHUSDT")
        
        assert (await row.locator("td:nth-child(5)").inner_text()) == "—"
        
        gross_pnl = await row.locator("td:nth-child(6)").inner_text()
        net_pnl = await row.locator("td:nth-child(7)").inner_text()
        assert gross_pnl == "0,00", f"Gross PnL war {gross_pnl} anstatt 0,00"
        assert net_pnl == "—", f"Net PnL war {net_pnl} anstatt —"

        # R4 Chart Race
        await page.locator("#tab-market-d").click()
        await page.wait_for_timeout(200)
        
        btc_event = asyncio.Event()
        eth_event = asyncio.Event()
        
        async def delay_candles(route):
            if route.request.method == "POST":
                # Ensure post_data_json doesn't raise if missing
                try:
                    post_data = route.request.post_data_json
                    if post_data and "path" in post_data:
                        if "BTCUSDT" in post_data["path"]:
                            await btc_event.wait()
                        elif "ETHUSDT" in post_data["path"]:
                            await eth_event.wait()
                except Exception:
                    pass
            await route.continue_()
            
        await page.route("**/api/public", delay_candles)
        
        await page.locator("select#symbolSelect").select_option("BTCUSDT.P")
        await page.evaluate("renderMarket(); undefined;")
        
        await page.locator("select#symbolSelect").select_option("ETHUSDT.P")
        await page.evaluate("renderMarket(); undefined;")
        
        eth_event.set()
        await page.wait_for_timeout(400)
        btc_event.set()
        await page.wait_for_timeout(800)
        await page.unroute("**/api/public")
        
        caption = await page.locator("#chartCaption").inner_text()
        assert "ETHUSDT" in caption
        assert "Bitget:ETHUSDT ·" in caption

        # R4 Logout Race
        state_held = asyncio.Event()
        state_release = asyncio.Event()
        
        async def hold_state(route):
            r = await route.fetch()
            state_held.set()
            await state_release.wait()
            await route.fulfill(response=r)
            
        await page.route("**/api/v3/state**", hold_state)
        await page.evaluate("refreshData(); undefined;")
        
        await state_held.wait()
        await page.locator("#btnLogout").click()
        await page.wait_for_timeout(400)
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"
        
        state_release.set()
        await page.wait_for_timeout(800)
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"
        await page.unroute("**/api/v3/state**")

        # Layout 390px
        await page.set_viewport_size({"width": 390, "height": 844})
        
        await page.locator("#tab-overview-m").click()
        await page.wait_for_timeout(200)

        # Login again for all tabs check
        correct_token = os.environ.get("AURA_RELAY_TOKEN", "TEST_INTEGRATION_TOKEN_XYZ")
        await page.locator("#loginTokenInput").fill(correct_token)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(1000)

        tabs_to_test = ["#tab-overview-m", "#tab-market-m", "#tab-paper-m", "#tab-settings-m"]
        for tab in tabs_to_test:
            await page.locator(tab).click()
            await page.wait_for_timeout(200)
            is_no_overflow = await page.evaluate("document.documentElement.scrollWidth <= 390")
            assert is_no_overflow, f"Overflow (scrollWidth > 390) detected auf Tab {tab}!"
        
        
        # --- R1 Matrix Tests ---
        await page.locator("#tab-overview-m").click()

        async def test_matrix(w_halt, w_fsm, w_known, w_stale, feed_stat,
                              exp_w_pill, exp_f_pill, exp_w_ov, exp_f_ov):
            async def m_w(route):
                await route.fulfill(json={
                    "is_halted": w_halt, "fsm_state": w_fsm,
                    "worker_known": w_known, "stale": w_stale, "data_age_seconds": 10
                })
            async def m_s(route):
                await route.fulfill(json={
                    "market_data": {"status": feed_stat, "symbols": []}
                })
            await page.route("**/status/worker", m_w)
            await page.route("**/api/v3/state**", m_s)
            
            await page.evaluate("refreshData(); undefined;")
            await page.wait_for_timeout(300)
            
            pill_w = await page.locator("#pill-worker-txt").inner_text()
            pill_f = await page.locator("#pill-feed-txt").inner_text()
            assert exp_w_pill in pill_w, f"Pill Worker exp '{exp_w_pill}' but was '{pill_w}'"
            assert exp_f_pill in pill_f, f"Pill Feed exp '{exp_f_pill}' but was '{pill_f}'"

            # Use textContent or innerText of the parent container for Overview
            ov_w_el = page.locator("#ovWorkerState")
            ov_w = await ov_w_el.inner_text()
            ov_f_el = page.locator("#ovConnState")
            ov_f = await ov_f_el.inner_text()
            
            assert exp_w_ov in ov_w.replace("\n", " "), f"Overview Worker exp '{exp_w_ov}' but was '{ov_w}'"
            assert exp_f_ov in ov_f.replace("\n", " "), f"Overview Feed exp '{exp_f_ov}' but was '{ov_f}'"
            
            await page.unroute("**/status/worker")
            await page.unroute("**/api/v3/state**")

        # CASE 1: RUNNING + frischer Worker + valide Marktdaten
        await test_matrix(False, "RUNNING", True, False, "valid",
                          "RUNNING", "frisch", "RUNNING — Worker läuft", "Verbunden, Daten aktuell")
                          
        # CASE 2: RUNNING + frischer Worker + source_failed-Marktdaten
        # RUNNING worker must STAY RUNNING! ONLY market feed is source_failed.
        await test_matrix(False, "RUNNING", True, False, "source_failed",
                          "RUNNING", "source_failed", "RUNNING — Worker läuft", "Verbunden, Datenzustand: veraltet")

        # CASE 3: RUNNING + veralteter Worker + valide Marktdaten
        await test_matrix(False, "RUNNING", True, True, "valid",
                          "VERALTET", "frisch", "nicht bestätigt", "Verbunden, Daten aktuell")

        # CASE 4: frischer HALTED-Worker + valide Marktdaten
        await test_matrix(True, "RUNNING", True, False, "valid",
                          "HALTED", "frisch", "Angehalten", "Verbunden, Daten aktuell")

        # CASE 5: fehlender/unbekannter Worker + valide Marktdaten
        await test_matrix(False, "UNKNOWN", False, False, "valid",
                          "UNBEKANNT", "frisch", "nicht bestätigt", "Verbunden, Daten aktuell")
                          

        await context.close()
        await browser.close()
        
        assert len(js_errors) == 0, f"JS-Fehler aufgetreten: {js_errors}"
        assert len(forbidden_writes) == 0, f"Unerlaubte schreibende Requests: {forbidden_writes}"
        
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
