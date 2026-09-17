import asyncio
import os
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
            if req.method in ["POST", "PUT", "DELETE"]:
                if "api/v3/state" in req.url or "orders" in req.url:
                    forbidden_writes.append(req.url)
                    
        page.on("request", handle_request)
        
        await context.clear_cookies()
        await page.goto("http://127.0.0.1:8899/preview")
        await page.wait_for_timeout(1000)
        
        auth_txt = await page.locator("#pill-auth-txt").inner_text()
        assert auth_txt == "Anonym"

        await page.locator("#loginTokenInput").fill("wrong_token_123")
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        error_msg = await page.locator("#loginError").inner_text()
        assert error_msg == "Fehlerhafte Anmeldung", f"Falsche Token-Erwartung, Error war: {error_msg}"
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"

        if FAIL_INTENTIONALLY:
            assert False, "BEWUSSTE NEGATIVKONTROLLE: Dieser Assert MUSS fehlschlagen und Exit != 0 provozieren."

        correct_token = os.environ.get("AURA_RELAY_TOKEN", "TEST_INTEGRATION_TOKEN_XYZ")
        await page.locator("#loginTokenInput").fill(correct_token)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(1000)
        
        auth_txt = await page.locator("#pill-auth-txt").inner_text()
        assert auth_txt == "Operator", f"Login fehlgeschlagen. Auth war: {auth_txt}"
        
        await page.locator("#tab-paper-d").click()
        await page.wait_for_selector("#openPosTbody")
        await page.wait_for_timeout(500)
        row = page.locator("#openPosTbody tr", has_text="ETHUSDT")
        
        mark_price = await row.locator("td:nth-child(5)").inner_text()
        assert mark_price == "—"
        
        gross_pnl = await row.locator("td:nth-child(6)").inner_text()
        net_pnl = await row.locator("td:nth-child(7)").inner_text()
        assert "USDT" not in gross_pnl
        assert net_pnl == "—"

        await page.locator("#tab-market-d").click()
        await page.wait_for_timeout(500)
        
        btc_event = asyncio.Event()
        eth_event = asyncio.Event()
        
        async def delay_candles(route):
            url = route.request.url
            if "BTCUSDT" in url:
                await btc_event.wait()
            elif "ETHUSDT" in url:
                await eth_event.wait()
            await route.continue_()
            
        await page.route("**/api/public", delay_candles)
        
        await page.locator("select#symbolSelect").select_option("BTCUSDT.P")
        await page.evaluate("renderMarket(); undefined;")
        
        await page.locator("select#symbolSelect").select_option("ETHUSDT.P")
        await page.evaluate("renderMarket(); undefined;")
        
        eth_event.set() 
        await page.wait_for_timeout(500)
        btc_event.set() 
        await page.wait_for_timeout(1000)
        
        await page.unroute("**/api/public")
        
        caption = await page.locator("#chartCaption").inner_text()
        assert "ETHUSDT" in caption
        assert "Bitget:ETHUSDT ·" in caption

        state_held = asyncio.Event()
        state_release = asyncio.Event()
        
        async def hold_state(route):
            state_held.set()
            await state_release.wait()
            await route.continue_()
            
        await page.route("**/api/v3/state**", hold_state)
        await page.evaluate("refreshData(); undefined;")
        
        await state_held.wait()
        await page.locator("#btnLogout").click()
        await page.wait_for_timeout(500)
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"
        
        state_release.set()
        await page.wait_for_timeout(2000)
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"
        await page.unroute("**/api/v3/state**")

        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(500)
        
        bb = await page.locator(".topbar").bounding_box()
        assert bb["width"] <= 390, "Topbar erzeugt Overflow auf 390px Viewport!"
        
        await context.close()
        await browser.close()
        
        assert len(js_errors) == 0, f"Unerwartete JS-Fehler im Renderpfad: {js_errors}"
        assert len(forbidden_writes) == 0, f"Unerlaubte schreibende Requests: {forbidden_writes}"
        
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
