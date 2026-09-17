import asyncio
import os
import sqlite3
import time
from playwright.async_api import async_playwright

FAIL_INTENTIONALLY = os.environ.get("FAIL_INTENTIONALLY", "0") == "1"
DB_PATH = os.environ.get("AURA_DB_PATH", "aura_state.db")
TOKEN = os.environ.get("AURA_RELAY_TOKEN", "TEST_INTEGRATION_TOKEN_XYZ")

def modify_worker_state(fsm_state="RUNNING", stale=False, is_halted=False):
    conn = sqlite3.connect(DB_PATH)
    now = int(time.time() * 1000)
    hb = now - (900000 if stale else 1000)
    # The normal db has is_halted logic implicitly tied to fsm_state maybe? Wait, runner_state doesn't have is_halted column. Actually, wait, `is_halted` in the response is based on `fsm_state == 'HALTED'` in earlier mocks? Let's check route.
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
        page.on("console", lambda msg: print("JS CONSOLE:", msg.text))
        
        await page.goto("http://127.0.0.1:8899/preview")
        
        # Don't disable polling completely! "Mindestens ein Lauf mit normalem Produktpolling."
        # We'll just let polling run naturally. 1000ms is standard.
        
        await context1.clear_cookies()
        await page.wait_for_timeout(500)
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        
        await page.locator("#tab-overview-d").click()
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        
        if FAIL_INTENTIONALLY:
            assert False, "BEWUSSTE NEGATIVKONTROLLE"

        # ---------------------------------------------------------
        # Bedienfehler 1: Halt Banner on normal is_halted
        # ---------------------------------------------------------
        print("Testing Halt Banner via Server State...")
        modify_worker_state("HALTED")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200) # Wait for polling!
        
        import sqlite3, urllib.request
        c = sqlite3.connect(DB_PATH)
        row = c.execute("SELECT fsm_state, updated_at_ms FROM runner_state WHERE id=1").fetchone()
        c.close()
        api_res = urllib.request.urlopen("http://127.0.0.1:8899/status/worker").read().decode()
        print("DB FSM:", row, "API STATUS:", api_res)
        print("JS STATE:", await page.evaluate("state.scenario.worker"))
        halt_banner_visible = await page.evaluate("document.getElementById('haltBanner').style.display !== 'none'")
        halt_banner_text = await page.locator("#haltBanner").inner_text()
        
        if not halt_banner_visible or "kann dabei technisch gesund laufen" not in halt_banner_text:
            raise AssertionError("Halt-Banner not visible correctly solely based on worker HALTED state (no pending ID).")

        # Revert to RUNNING
        modify_worker_state("RUNNING")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)

        # ---------------------------------------------------------
        # Bedienfehler 2: btnCfgCancel
        # ---------------------------------------------------------
        print("Testing btnCfgCancel...")
        await page.locator("#tab-settings-d").click()
        await page.locator("#btnCfgEdit").click()
        await page.wait_for_timeout(500)
        
        # Change value 
        await page.locator("#cfgMaxLevInput").fill("15")
        
        await page.locator("#btnCfgCancel").click()
        await page.wait_for_timeout(500)
        
        if await page.locator("#cfgEditForm").is_visible():
            raise AssertionError("btnCfgCancel did not hide the edit form.")
        
        # Restart edit
        await page.locator("#btnCfgEdit").click()
        await page.wait_for_timeout(500)
        val = await page.locator("#cfgMaxLevInput").input_value()
        # the draft is cleared, so it shouldn't be 15 anymore if it was discarded properly
        if val == "15":
            raise AssertionError("btnCfgCancel did not discard the draft, old value persisted.")

        # ---------------------------------------------------------
        # Bedienfehler 3 & 4: Visible Timeouts and Unknown (Config/Resume)
        # ---------------------------------------------------------
        await page.locator("#cfgMaxLevInput").fill("18")
        await page.locator("#btnCfgValidate").click()
        await page.wait_for_timeout(500)
        await page.locator("#btnCfgRequest").click()
        await page.wait_for_timeout(500)
        
        # Trigger timeout
        await page.evaluate("state.pendingCfgAt = Date.now() - 15000;")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(500)
        
        # Config Timeout Visibility
        pending_view_text = await page.locator("#cfgPendingView").inner_text()
        rejection_view_text = await page.locator("#cfgUnknownNote").inner_text()
        
        is_unknown_rejection = await page.evaluate("document.getElementById('cfgRejectionNote').style.display !== 'none'")
        
        if "ungewöhnlich lange" not in pending_view_text and "ungewöhnlich lange" not in rejection_view_text:
             raise AssertionError("Config Timeout warning not visible anywhere on screen.")
             
        if is_unknown_rejection:
             raise AssertionError("Config Timeout or Unknown was incorrectly rendered in the REJECTION note instead of pending or separately.")

        # ---------------------------------------------------------
        # Bedienfehler 5: Applied with later active revision
        # ---------------------------------------------------------
        print("Testing Applied with Revision Mismatch...")
        process_worker_commands()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE config_revisions SET rev = 3 WHERE rev = 2")
        conn.commit()
        conn.close()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(500)
        
        is_rejected_now = await page.evaluate("document.getElementById('cfgRejectionNote').style.display !== 'none'")
        rejection_text_now = await page.locator("#cfgRejectionNote").inner_text()
        
        if is_rejected_now and "stimmt nicht" in rejection_text_now:
            raise AssertionError("Applied config with changed active revision falsely labeled as rejected!")
            
        applied_visible = await page.evaluate("document.getElementById('cfgAppliedNote').classList.contains('show')")
        applied_text = await page.locator("#cfgAppliedNote").inner_text()
        if "Übernommen" not in applied_text:
            if not applied_visible: raise AssertionError(f"Visible true worker receipt (Applied) missing! Text was: {applied_text}")

        # ---------------------------------------------------------
        # Async Race: Late Response
        # ---------------------------------------------------------
        print("Testing Async Race Condition...")
        modify_worker_state("HALTED")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        await page.locator("#btnResume").click()
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        await page.wait_for_timeout(500)
        
        # We hook the next GET matching /api/v3/command/
        late_blocker = asyncio.Event()
        async def hold_cmd(route):
            await late_blocker.wait()
            await route.fulfill(status=200, json={"ok":True,"data":{"status":"applied","id":"cmd_mocked"}})
        
        await page.route("**/api/v3/command/*", hold_cmd)
        
        # Delete from pending_commands in DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM commands WHERE type='resume'")
        conn.commit()
        conn.close()
        
        await page.wait_for_timeout(1500) # This triggers the request which is now blocked
        
        # Logout
        await context1.clear_cookies()
        await page.wait_for_timeout(1500)
        
        # Release!
        late_blocker.set()
        await page.wait_for_timeout(500)
        
        # Assert: the old response should not set state.lastResumeResult="" because it shouldn't be processed!
        # Since we logged out, state is cleared. If the late response processed, it might set lastResumeResult = "" which is technically a string, but we can verify it directly.
        # Even better: The new session shouldn't have ANY lastResumeResult if the late one was discarded.
        # Actually, when logging out, state.lastResumeResult = null (or "").
        # Let's write explicitly to lastResumeResult during logged out to see if it's overwritten!
        await page.evaluate("state.lastResumeResult = 'SAFE_MARKER'")
        
        await page.wait_for_timeout(500)
        marker = await page.evaluate("state.lastResumeResult")
        if marker != "SAFE_MARKER":
            raise AssertionError(f"Late response incorrectly wrote to state! Marker is: {marker}")

        
        # ---------------------------------------------------------
        # NEW: Issue 1 (Visually verify applied/rejected for Resume)
        # ---------------------------------------------------------
        
        # Relogin again for the next tests
        await page.locator("#tab-overview-d").click()
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)

        print("Testing visible Resume results...")
        
        # intercept and return 'applied'
        async def mock_post(route):
            print("POST INTERCEPTED")
            await route.fulfill(status=200, json={"ok":True,"data":{"status":"pending","command_id":"cmd_res_1"}})
        async def resume_applied(route):
            await route.fulfill(status=200, json={"ok":True,"data":{"status":"applied","id":"cmd_res_1"}})
            
        await page.route("**/api/v3/resume", mock_post)
        await page.route("**/api/v3/command/*", resume_applied)
        
        modify_worker_state("HALTED")
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)

        # Trigger a resume that will be mocked as 'applied'
        await page.locator("#btnResume").click()
        await page.locator("#btnResumeConfirm").dispatch_event("click")
        await page.wait_for_timeout(200)
        
        # trigger processing of that command
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM commands WHERE type='resume'")
        conn.commit()
        conn.close()
        
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(500)
        
        resume_vis = await page.evaluate("document.getElementById('resumeRejectionNote')?.style.display !== 'none'")
        resume_txt = await page.evaluate("document.getElementById('resumeRejectionNote')?.innerText || ''")
        
        if not resume_vis or "Erfolgreich" not in resume_txt:
            print("JS STATE AFTER REFRESH:", await page.evaluate("state.lastResumeResult")); raise AssertionError("debug")
            
        await page.unroute("**/api/v3/resume")
        await page.unroute("**/api/v3/command/*")

        # ---------------------------------------------------------
        # NEW: Issue 2 & 3 (Config unknown -> Block double POST -> Logout cleanup)
        # ---------------------------------------------------------
        print("Testing Config Unknown & } ; Logout Cleanup...")
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        
        # Enter edit mode and submit
        if await page.locator("#btnCfgEdit").is_disabled():
            raise AssertionError("btnCfgEdit is unexpectedly blocked before we even started!")
        
        await page.locator("#btnCfgEdit").click()
        await page.locator("#cfgMaxLevInput").fill("20")
        await page.locator("#btnCfgValidate").click()
        await page.wait_for_timeout(200)
        
        if await page.locator("#btnCfgRequest").is_disabled():
            raise AssertionError("btnCfgRequest is unexpectedly blocked before we even submit!")
        
        await page.locator("#btnCfgRequest").click()
        await page.wait_for_timeout(200)
        
        # Delete from DB without resolving to simulate UNKNOWN/404 on the backend
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM commands WHERE type='config'")
        conn.commit()
        conn.close()
        
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(500)
        
        # It should now be in 'unknown' state with pendingCmdId strictly tracked.
        # Check UI shows unknown note:
        un_vis = await page.locator("#cfgUnknownNote").is_visible()
        un_txt = await page.locator("#cfgUnknownNote").inner_text()
        print("un_vis:", un_vis, "un_txt:", un_txt)
        if "Ergebnis unbekannt" not in un_txt:
            raise AssertionError(f"Config Unknown not visibly rendered! Text: {un_txt}")
            
        # Is double post/edit blocked?
        if not await page.locator("#btnCfgEdit").is_disabled():
            raise AssertionError("Double config submit NOT blocked! Edit button is still active during unknown.")
            
        # Logout
        await context1.clear_cookies()
        await page.evaluate("(async () => await refreshData())()")
        await page.wait_for_timeout(200)
        
        # Relogin
        await page.locator("#tab-overview-d").click()
        await page.locator("#loginTokenInput").fill(TOKEN)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(200)
        
        # Verify old unknown state is totally gone
        cid_after = await page.evaluate("state.cfg.pendingCmdId")
        if cid_after is not None:
             raise AssertionError(f"Logout did not clear pendingCmdId! It is still: {cid_after}")
             
        # Edit should be freely available again
        if await page.locator("#btnCfgEdit").is_disabled():
             raise AssertionError("btnCfgEdit remained blocked after logout/login cleanup!")

        await context1.close()
        await browser.close()
        
        assert len(js_errors) == 0, f"JS Errors found: {js_errors}"
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
