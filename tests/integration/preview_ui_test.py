
import asyncio
import os
import sqlite3
import time
from playwright.async_api import async_playwright

FAIL_INTENTIONALLY = os.environ.get("FAIL_INTENTIONALLY", "0") == "1"
DB_PATH = os.environ.get("AURA_DB_PATH", "aura_state.db")
TOKEN = os.environ.get("AURA_RELAY_TOKEN", "TEST_INTEGRATION_TOKEN_XYZ")

def modify_worker_state(fsm_state="RUNNING", stale=False):
    conn = sqlite3.connect(DB_PATH)
    now = int(time.time() * 1000)
    hb = now - (900000 if stale else 1000)
    conn.execute(
        "UPDATE runner_state SET fsm_state = ?, updated_at_ms = ? WHERE id = 1",
        (fsm_state, hb)
    )
    conn.commit()
    conn.close()

def process_worker_commands():
    from aura.runner.worker import AuraWorkerService
    w = AuraWorkerService(db_path=DB_PATH)
    w._apply_control_plane_commands()
    w.conn.close()

async def run_tests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context1 = await browser.new_context()
        page = await context1.new_page()
        
        js_errors = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        
        await page.goto("http://127.0.0.1:8899/preview")
        await page.evaluate("let m=setTimeout(()=>{}); for(let i=0;i<=m;i++) clearInterval(i);")
        
        await context1.clear_cookies()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        await page.locator("#tab-overview-d").click()
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        
        if FAIL_INTENTIONALLY:
            assert False, "BEWUSSTE NEGATIVKONTROLLE"

        modify_worker_state("RUNNING", False)
        await page.evaluate("(async () => await refreshData())()")
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)

        # 1. Config Edit via Real Clicks (Regression Red Test)
        print("Testing Config full flow clicking...")
        await page.locator("#btnCfgEdit").click()
        # Ensure editing form actually appeared
        if not await page.locator("#cfgEditForm").is_visible():
            raise AssertionError("Form #cfgEditForm did not become visible after clicking #btnCfgEdit!")
            
        await page.locator("#cfgMaxLevInput").fill("15"); await page.locator("#cfgRiskInput").fill("1"); await page.locator("#cfgMaxPosInput").fill("5")
        await page.locator("#btnCfgValidate").click()
        await page.wait_for_timeout(200)
        
        # Now we should see the request button
        if not await page.locator("#btnCfgRequest").is_visible():
            raise AssertionError("Form #btnCfgRequest not visible after validation!")
        
        await page.locator("#btnCfgRequest").click()
        await page.wait_for_timeout(200)
        
        # After requesting, it should be pending visibly
        txt = await page.locator("#cfgStatusBadge").inner_text(); assert "ausstehend".upper() in txt
        
        process_worker_commands()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(500)
        
        # 2. Halt Timeout Display
        print("Testing Halt Timeout Visibility...")
        await page.locator("#btnHalt").click()
        await page.wait_for_timeout(200)
        
        # Simulate local time moving way past 10s timeout
        await page.evaluate("state.pendingHaltAt = Date.now() - 12000;")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        vis_text = await page.locator("#haltBanner").inner_text()
        if "ungewöhnlich lange" not in vis_text:
            raise AssertionError(f"Halt timeout text not visible on UI. Text: {vis_text}")
            
        # 3. 404 Unknown Retention
        print("Testing Unknown Command retention...")
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM commands")
        conn.commit()
        conn.close()
        
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        # State should retain pendingHaltId explicitly
        halt_id = await page.evaluate("state.pendingHaltId")
        if not halt_id:
            raise AssertionError("pendingHaltId was incorrectly set to null on 404/Unknown!")
            
        vis_text_2 = await page.locator("#haltBanner").inner_text()
        if "UNBEKANNT" not in vis_text_2 or "Kein Nachweis" not in vis_text_2:
            raise AssertionError("Unknown status correctly not rejected, but UI didn't show 'Kein Nachweis'")

        # 4. /state=401 intercept cleanup
        print("Testing /state 401 cleanup...")
        await page.route("**/api/v3/state", lambda route: route.fulfill(status=401, json={"detail":"Unauthorized"}))
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        if await page.locator("#pill-auth-txt").inner_text() != "Anonym":
            raise AssertionError("/state 401 intercept did not trigger handleLogoutClean!")
        
        await page.unroute("**/api/v3/state")
        
        # Relogin for next
        await page.locator("#tab-overview-d").click()
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        
        # 5. Late Command Fetch after logout
        print("Testing late command fetch after logout...")
        await page.locator("#tab-settings-d").click()
        modify_worker_state("HALTED", False)
        process_worker_commands()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)

        # Drop previous pending state safely
        await page.evaluate("state.pendingHaltId = null")
        
        await page.locator("#btnResume").click()
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        await page.wait_for_timeout(200)
        
        late_blocker = asyncio.Event()
        async def hold_command(route):
            await late_blocker.wait()
            # Fulfill with 'applied'
            await route.fulfill(status=200, json={"ok":True, "data":{"status":"applied", "id": "cmd_abc"}})
            
        await page.route("**/api/v3/command/*", hold_command)
        
        # Simulate removal from pending_commands
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM commands WHERE type='resume'")
        conn.commit()
        conn.close()
        
        # Trigger refreshData -> will start awaiting /api/v3/command/*
        asyncio.create_task(page.evaluate("(async () => await refreshData())()"))
        await page.wait_for_timeout(100)
        
        # Logout
        await context1.clear_cookies()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        # Release late command fetch! it returns "applied"
        late_blocker.set()
        await page.wait_for_timeout(500)
        
        if await page.evaluate("state.lastResumeResult"):
             raise AssertionError("Late command fetch response applied changes to the logged-out state!")

        await context1.close()
        await browser.close()
        
        assert len(js_errors) == 0, f"JS Errors found: {js_errors}"
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
