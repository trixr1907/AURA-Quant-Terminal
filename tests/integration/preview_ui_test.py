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

def count_pending_commands(t="resume"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM commands WHERE type='{t}' AND status='pending'")
    count = cur.fetchone()[0]
    conn.close()
    return count

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

        # 1. Unknown Command State (UI Wait Timeout & Missing ID)
        print("Testing Unknown/Missing Command State...")
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        await page.locator("#btnHalt").click()
        await page.wait_for_timeout(200)
        
        # Simulate wait > timeout
        await page.evaluate("state.pendingHaltAt = Date.now() - 11000;")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        h_res = await page.evaluate("state.lastHaltResult")
        assert "Ergebnis unbekannt" in h_res
        
        # Missing ID (404)
        print("Testing Missing ID (404)...")
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM commands")
        conn.commit()
        conn.close()
        
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        h_res2 = await page.evaluate("state.lastHaltResult")
        assert "Kein Nachweis gefunden" in h_res2

        # 2. Halt not blocked by stale heartbeat
        print("Testing Halt allowed on stale worker...")
        modify_worker_state("RUNNING", True) # Stale
        await page.evaluate("(async () => await refreshData())()")
        
        await page.locator("#btnHalt").click()
        await page.wait_for_timeout(200)
        assert "angefordert" in await page.locator("#toast").inner_text()
        
        # 3. Double Click + Long POST request
        print("Testing Double Click Prevention & Held Posts...")
        modify_worker_state("HALTED", False)
        await page.evaluate("(async () => await refreshData())()")
        
        resume_blocker = asyncio.Event()
        async def mock_resume_hold(route):
            await resume_blocker.wait()
            response = await route.fetch()
            await route.fulfill(response=response)
        
        await page.route("**/api/v3/resume", mock_resume_hold)
        
        await page.locator("#btnResume").click()
        await page.wait_for_timeout(200)
        
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        
        await page.wait_for_timeout(200)
        print("Testing Auth / Logout during open Draft / Post...")
        await context1.clear_cookies()
        await page.evaluate("(async () => await refreshData())()") 
        await page.wait_for_timeout(200)
        
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"
        
        resume_blocker.set()
        await page.wait_for_timeout(500)
        
        assert count_pending_commands("resume") == 1
        
        # 4. Relogin while late POST is answered
        print("Testing Logout -> Relogin -> Late POST")
        await page.unroute("**/api/v3/resume")
        
        resume_blocker2 = asyncio.Event()
        async def mock_resume_hold2(route):
            await resume_blocker2.wait()
            response = await route.fetch()
            await route.fulfill(response=response)

        await page.route("**/api/v3/resume", mock_resume_hold2)

        await page.locator("#tab-overview-d").click()
        await page.wait_for_timeout(200)
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        await page.locator("#btnResume").click()
        await page.wait_for_timeout(200)
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        await page.wait_for_timeout(200)
        
        await context1.clear_cookies()
        await page.evaluate("(async () => await refreshData())()") 
        await page.wait_for_timeout(200)
        
        # Switch to overview to make login form visible
        await page.locator("#tab-overview-d").click()
        await page.wait_for_timeout(200)
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(300)
        
        resume_blocker2.set()
        await page.wait_for_timeout(500)
        
        # 5. Normal Run
        print("Running normal success loop...")
        await page.unroute("**/api/v3/resume")
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        
        process_worker_commands()
        await page.locator("#btnResume").click()
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        await page.wait_for_timeout(500)
        
        process_worker_commands()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(500)
        assert count_pending_commands("resume") == 0
        
        # 6. Config Validation
        print("Testing Config pre flight & 401 Cleanup")
        print("Auth before cfg edit:", await page.evaluate("state.scenario.auth")); await page.evaluate("state.cfg.status = \"editing\"; renderCfg();")
        await page.wait_for_timeout(200); vis1 = await page.locator("#view-settings").is_visible(); vis2 = await page.locator("#cfgEditForm").is_visible(); stat = await page.evaluate("state.cfg.status"); print("state.cfg.status:", stat); print(vis1, vis2); assert vis2
        
        modify_worker_state("RUNNING", True)
        await page.evaluate("(async () => await refreshData())()")
        await page.locator("#btnCfgRequest").dispatch_event("click")
        await page.wait_for_timeout(200)
        
        await context1.clear_cookies()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        assert not await page.locator("#cfgEditForm").is_visible()
        
        await context1.close()
        await browser.close()
        
        assert len(js_errors) == 0, f"JS Errors: {js_errors}"
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
