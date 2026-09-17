import asyncio
from playwright.async_api import async_playwright, expect
import urllib.parse
import json

async def run_tests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        network_calls = []
        js_errors = []
        
        page.on("request", lambda request: network_calls.append({"method": request.method, "url": request.url}))
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        # Start without cookies
        await context.clear_cookies()
        await page.goto("http://127.0.0.1:8899/preview")
        await page.wait_for_timeout(1000)
        
        assert len(js_errors) == 0, f"Unerwartete JS-Fehler: {js_errors}"
        
        # Test: Anon-Zustand + UI-Login 
        auth_txt = await page.locator("#pill-auth-txt").inner_text()
        assert auth_txt == "Anonym"

        # Login per UI Form (I4)
        # Use WRONG token first (Negativkontrolle)
        # Assuming the UI element is correctly added to DOM via our previous injection
        await page.locator("#loginTokenInput").fill("wrong_token_123")
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        error_msg = await page.locator("#loginError").inner_text()
        assert error_msg == "Fehlerhafte Anmeldung", f"Falsche Token-Erwartung, Error war: {error_msg}"
        auth_txt = await page.locator("#pill-auth-txt").inner_text()
        assert auth_txt == "Anonym"

        # Use CORRECT token
        correct_token = "TEST_INTEGRATION_TOKEN_XYZ"
        await page.locator("#loginTokenInput").fill(correct_token)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(1000)
        
        auth_txt = await page.locator("#pill-auth-txt").inner_text()
        assert auth_txt == "Operator", f"Login fehlgeschlagen. Auth war: {auth_txt}"
        
        # PnL Check (I2) & Bewertungsmarke
        await page.locator("#tab-paper-d").click()
        await page.wait_for_selector("#openPosTbody")
        await page.wait_for_timeout(500)
        row = page.locator("#openPosTbody tr", has_text="SOLUSDT")
        
        # Verify mark price "—"
        mark_price = await row.locator("td:nth-child(5)").inner_text()
        assert mark_price == "—", f"Bewertungsmarke entsprach nicht '—', sondern {mark_price}"
        
        gross_pnl = await row.locator("td:nth-child(6)").inner_text()
        net_pnl = await row.locator("td:nth-child(7)").inner_text()
        assert "USDT" not in gross_pnl # PnL formatting check
        assert net_pnl == "—", "Erfundenes NetPnl ohne Daten!"

        # I3 / I1: Kerzen Map & Symbolnormalisierung & Race-Condition beim Wechsel
        await page.locator("#tab-market-d").click()
        await page.wait_for_timeout(500)
        
        # Abort late fetch implicitly via playwright route race condition (Race-verwerfen)
        wait_for_fetch = asyncio.Event()
        async def delay_candles(route):
            await wait_for_fetch.wait() # Blockiert Route
            await route.continue_()
            
        await page.route("**/api/public", delay_candles)
        
        # 1. Klicke ein Symbol -> Fetch 1 startet
        await page.locator("select#symbolSelect").select_option("BTCUSDT.P")
        await page.wait_for_timeout(200)
        # 2. Klicke ein ANDERES Symbol -> Fetch 2 startet
        await page.locator("select#symbolSelect").select_option("ETHUSDT.P")
        await page.wait_for_timeout(200)
        
        # Jetzt beide Routen freigeben
        wait_for_fetch.set()
        await page.wait_for_timeout(1500)
        await page.unroute("**/api/public")
        
        # Wir erwarten, dass er bei ETHUSDT.P (zweiter) verblieben ist, auch wenn BTC (erster) langsamer eintrudelt.
        caption = await page.locator("#chartCaption").inner_text()
        assert "ETHUSDT" in caption, "Chart Caption spiegelt nicht das zuletzt gewaehlte Symbol wider!"
        assert "Bitget:ETHUSDT ·" in caption, f"Normalisierung fehlt in Chart Caption, ist: {caption}"
        
        # I4: Logout-Race
        async def delay_state(route):
            await asyncio.sleep(2.0)
            await route.continue_()
            
        await page.route("**/api/v3/state**", delay_state)
        await page.evaluate("refreshData()")
        await page.locator("#btnLogout").click()
        # Erneuter refresh feuert und ist instant wegen 401 unauth (loescht DOM)
        await page.wait_for_timeout(200)
        auth_now = await page.locator("#pill-auth-txt").inner_text()
        assert auth_now == "Anonym"
        
        # Warten auf verzoegertes stateRes (altes request von vorher)
        await page.wait_for_timeout(2500)
        auth_later = await page.locator("#pill-auth-txt").inner_text()
        assert auth_later == "Anonym", "Alter State-Call hat nach Logout den DOM ueberschrieben!"
        await page.unroute("**/api/v3/state**")

        await context.close()
        await browser.close()
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
