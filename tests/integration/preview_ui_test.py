import asyncio
from playwright.async_api import async_playwright

async def run_tests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        network_calls = []
        public_payloads = []
        js_errors = []
        
        def handle_request(request):
            network_calls.append({"method": request.method, "url": request.url})
            if "/api/public" in request.url and request.method == "POST":
                public_payloads.append(request.post_data)
                
        page.on("request", handle_request)
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        print("=== Test 1: Laden (keine JS Fehler) ===")
        await context.clear_cookies()
        await page.goto("http://127.0.0.1:8899/preview")
        await page.wait_for_timeout(1000)
        print(f"JS Errors: {js_errors}")

        print("\n=== Test 2: Login & Fehlende Bewertungsmarke ===")
        await page.evaluate("""fetch('/api/v3/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({token: 'aura_dev_insecure_token_change_in_prod'})
            })""")
        await page.evaluate("refreshData()")
        await page.wait_for_timeout(1000)
        
        await page.locator("#tab-paper-d").click()
        await page.wait_for_timeout(500)
        # Check "Bewertungsmarke" cell inside the Paper table
        # Find row for SOLUSDT
        mark_value = await page.evaluate("""
            Array.from(document.querySelectorAll('#openPosTbody tr')).find(tr => tr.innerText.includes('SOLUSDT')).cells[4].innerText
        """)
        print(f"Auth State logged in: {await page.locator('#pill-auth-txt').inner_text()}")
        print(f"Bewertungsmarke fuer SOLUSDT: {mark_value} (erwartet '—')")

        print("\n=== Test 3: Symbolnormalisierung & OHLC Mapping ===")
        await page.locator("#tab-market-d").click()
        await page.evaluate("""
            document.querySelector('select#symbolSelect').value = 'BTCUSDT.P';
            document.querySelector('select#symbolSelect').dispatchEvent(new Event('change'));
        """)
        await page.wait_for_timeout(1000)
        print("Captured /api/public payloads:", public_payloads[-1] if public_payloads else "None")
        print("Chart Caption:", await page.locator("#chartCaption").inner_text())

        print("\n=== Test 4: Unterschiedliche Worker-/Marktdatenfrische ===")
        worker_txt = await page.locator("#pill-worker-txt").inner_text()
        feed_txt = await page.locator("#pill-feed-txt").inner_text()
        print(f"Worker-Status: {worker_txt}, Marktdaten-Feed: {feed_txt}")

        print("\n=== Test 5: Verspätete State-Antwort nach Logout ===")
        async def delay_state(route):
            await asyncio.sleep(1.0)
            await route.continue_()
            
        await page.route("**/api/v3/state**", delay_state)
        await page.evaluate("refreshData()") # fires delayed fetch
        # logout immediately
        await page.evaluate("fetch('/api/v3/auth/logout', {method: 'POST'})")
        # second fetch overwrites auth
        await page.evaluate("refreshData()")
        await page.wait_for_timeout(200)
        immediate_auth = await page.locator("#pill-auth-txt").inner_text()
        
        # Wait for the delayed response to arrive
        await page.wait_for_timeout(1500)
        delayed_auth = await page.locator("#pill-auth-txt").inner_text()
        equity_display = await page.locator("#ovEquity").inner_text()
        print(f"Immediate post-logout auth: {immediate_auth}")
        print(f"Delayed response arrived. Auth remains: {delayed_auth}")
        print(f"Equity cleared: {equity_display}")
        await page.unroute("**/api/v3/state**")

        print("\n=== Test 6: Sitzungsablauf (State 401 clearing) ===")
        # Login again
        await page.evaluate("""fetch('/api/v3/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({token: 'aura_dev_insecure_token_change_in_prod'})
            })""")
        await page.evaluate("refreshData()")
        await page.wait_for_timeout(1000)
        print("Re-logged in. Auth:", await page.locator("#pill-auth-txt").inner_text())
        
        # Manually clear session cookie to simulate expiry 
        await context.clear_cookies()
        await page.evaluate("refreshData()")
        await page.wait_for_timeout(1000)
        print("After session expiry. Auth:", await page.locator("#pill-auth-txt").inner_text())

        print("\n=== Test 7: API-Ausfall und Wiederverbindung ===")
        await page.route("**/api/v3/auth/status", lambda r: r.abort())
        await page.evaluate("refreshData()")
        await page.wait_for_timeout(1000)
        print("API Drop. Conn State:", await page.locator("#pill-conn-txt").inner_text())
        
        await page.unroute("**/api/v3/auth/status")
        # Login needed again because auth request was aborted and we lost the refresh data pipeline correctly
        await page.evaluate("""fetch('/api/v3/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({token: 'aura_dev_insecure_token_change_in_prod'})
            })""")
        await page.evaluate("refreshData()")
        await page.wait_for_timeout(1000)
        print("API Restore. Conn State:", await page.locator("#pill-conn-txt").inner_text())

        print("\n=== Test 8: Kontrolle unerwarteter Schreib-Requests ===")
        write_endpoints = [r["url"] for r in network_calls if r["method"] not in ["GET", "OPTIONS"] and "public" not in r["url"] and "login" not in r["url"] and "logout" not in r["url"]]
        print("Unexpected Write Requests:", write_endpoints)
        
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
