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
                allowed = ["/api/v3/auth/login", "/api/v3/auth/logout", "/api/public", "/api/v3/config", "/api/v3/halt", "/api/v3/resume"]
                path = req.url.split("?")[0].replace("http://127.0.0.1:8899", "")
                if path not in allowed:
                    forbidden_writes.append(f"{req.method} {req.url}")
        page.on("request", handle_request)
        
        await context.clear_cookies()
        await page.goto("http://127.0.0.1:8899/preview")
        
        await page.evaluate("let m=setTimeout(()=>{}); for(let i=0;i<=m;i++) clearInterval(i);")
        await page.wait_for_timeout(500)
        
        correct_token = os.environ.get("AURA_RELAY_TOKEN", "TEST_INTEGRATION_TOKEN_XYZ")
        await page.locator("#loginTokenInput").fill(correct_token)
        await page.locator("#btnLoginSubmit").click()
        await page.wait_for_timeout(500)
        assert await page.locator("#pill-auth-txt").inner_text() == "Operator"

        if FAIL_INTENTIONALLY:
            assert False, "BEWUSSTE NEGATIVKONTROLLE"

        # --- 1. Halt Request & Ack ---
        print("Testing Halt Request...")
        await page.locator("#tab-settings-d").click()
        await page.wait_for_timeout(500)
        
        real_fetch_halt = []
        async def mock_halt(route):
            real_fetch_halt.append(1)
            await route.fulfill(json={"ok": True, "message": "Halt", "data": {"command_id": "cmd_halt_1"}})
        await page.route("**/api/v3/halt", mock_halt)
        
        await page.locator("#btnHalt").click()
        await page.wait_for_timeout(200)
        assert len(real_fetch_halt) == 1
        
        async def mock_state_halt_pending(route):
            await route.fulfill(json={"active_config_rev": 1, "pending_cmds": [{"id": "cmd_halt_1"}], "config": {}, "open_positions": [], "closed_trades": []})
        await page.route("**/api/v3/state**", mock_state_halt_pending)
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(200)
        
        async def mock_state_halt_ack(route):
            await route.fulfill(json={"active_config_rev": 1, "pending_cmds": [], "config": {}, "open_positions": [], "closed_trades": []})
        await page.unroute("**/api/v3/state**")
        await page.route("**/api/v3/state**", mock_state_halt_ack)
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(200)

        # --- 2. Unknown/Stale Worker Resume Block ---
        print("Testing Stale Resume Block...")
        async def mock_worker_stale(route):
            await route.fulfill(json={"is_halted": False, "fsm_state": "RUNNING", "worker_known": True, "stale": True, "data_age_seconds": 150})
        await page.route("**/status/worker", mock_worker_stale)
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(200)

        await page.locator("#btnResume").click()
        await page.wait_for_timeout(200)
        assert not await page.locator("#resumeConfirmRow").is_visible(), "Resume block failed on stale worker."

        async def mock_worker_fresh_halted(route):
            await route.fulfill(json={"is_halted": True, "fsm_state": "HALTED", "worker_known": True, "stale": False, "data_age_seconds": 10})
        await page.unroute("**/status/worker")
        await page.route("**/status/worker", mock_worker_fresh_halted)
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(200)

        # --- 3. Resume Request & Ack ---
        print("Testing Resume Request...")
        real_fetch_resume = []
        async def mock_resume(route):
            real_fetch_resume.append(1)
            await route.fulfill(json={"ok": True, "message": "Resume", "data": {"command_id": "cmd_res_1"}})
        await page.route("**/api/v3/resume", mock_resume)

        await page.locator("#btnResume").click()
        await page.wait_for_timeout(200)
        assert await page.locator("#resumeConfirmRow").is_visible()
        
        await page.locator("#btnResumeConfirm").click()
        await page.wait_for_timeout(500)
        assert len(real_fetch_resume) == 1
        assert "angefordert" in await page.locator("#resumePendingNote").inner_text()

        async def mock_state_res_ack_resume(route):
             await route.fulfill(json={"active_config_rev": 1, "pending_cmds": [], "config": {}, "open_positions": [], "closed_trades": []})
        await page.unroute("**/api/v3/state**")
        await page.route("**/api/v3/state**", mock_state_res_ack_resume)
        
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(200)
        assert not await page.locator("#resumePendingNote").is_visible()

        # --- 4. Disconnect during Write ---
        print("Testing Write Disconnect...")
        async def mock_halt_disconnect(route):
            await route.abort("failed")
        await page.unroute("**/api/v3/halt")
        await page.route("**/api/v3/halt", mock_halt_disconnect)
        await page.locator("#btnHalt").click()
        await page.wait_for_timeout(200)
        assert "unbekannt" in (await page.locator("#toast").inner_text()).lower()
        
        # --- 5. Config Conflict 409 ---
        print("Testing Config Conflict 409...")
        await page.locator("#btnCfgEdit").click()
        await page.locator("#cfgMaxLevInput").fill("15")
        await page.locator("#btnCfgValidate").click()
        await page.wait_for_timeout(100)
        
        async def mock_cfg_409(route):
            await route.fulfill(status=409, json={"detail": "Conflict expected rev"})
        await page.route("**/api/v3/config", mock_cfg_409)
        
        await page.locator("#btnCfgRequest").click()
        await page.wait_for_timeout(500)
        assert "Konflikt" in await page.locator("#cfgValidationErrors").inner_text()
        assert await page.locator("#cfgDiffView").is_visible()
        
        # --- 6. Config Success & Ack ---
        print("Testing Config Success & Ack...")
        async def mock_cfg_200(route):
            await route.fulfill(status=200, json={"ok": True, "data": {"command_id": "cmd_cfg_1", "requested_rev": 2}})
        await page.unroute("**/api/v3/config")
        await page.route("**/api/v3/config", mock_cfg_200)
        
        async def mock_state_cfg_pending(route):
             await route.fulfill(json={"active_config_rev": 1, "pending_cmds": [{"id": "cmd_cfg_1"}], "config": {}, "open_positions": [], "closed_trades": []})
        await page.unroute("**/api/v3/state**")
        await page.route("**/api/v3/state**", mock_state_cfg_pending)
        
        await page.locator("#btnCfgRequest").click()
        await page.wait_for_timeout(500)
        assert await page.locator("#cfgPendingView").is_visible()
        
        async def mock_state_cfg_ack(route):
             await route.fulfill(json={"active_config_rev": 2, "pending_cmds": [], "config": {}, "open_positions": [], "closed_trades": []})
        await page.unroute("**/api/v3/state**")
        await page.route("**/api/v3/state**", mock_state_cfg_ack)
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(500)
        assert await page.locator("#cfgActiveView").is_visible()
        assert "#2" in await page.locator("#cfgRevisionDisplay").inner_text()

        # --- 7. Config Reject ---
        print("Testing Config Reject...")
        await page.locator("#btnCfgEdit").click()
        await page.locator("#btnCfgValidate").click()
        
        async def mock_cfg_200_2(route):
            await route.fulfill(status=200, json={"ok": True, "data": {"command_id": "cmd_cfg_2", "requested_rev": 3}})
        await page.unroute("**/api/v3/config")
        await page.route("**/api/v3/config", mock_cfg_200_2)
        
        async def mock_state_cfg_pending_2(route):
             await route.fulfill(json={"active_config_rev": 2, "pending_cmds": [{"id":"cmd_cfg_2"}], "config": {}, "open_positions": [], "closed_trades": []})
        await page.unroute("**/api/v3/state**")
        await page.route("**/api/v3/state**", mock_state_cfg_pending_2)
        
        await page.locator("#btnCfgRequest").click()
        await page.wait_for_timeout(500)
        assert await page.locator("#cfgPendingView").is_visible()
        
        async def mock_state_cfg_reject(route):
             await route.fulfill(json={"active_config_rev": 2, "pending_cmds": [], "config": {}, "open_positions": [], "closed_trades": [], "rejected_cmds": [{"id": "cmd_cfg_2", "result": "Worker reject"}]})
        await page.unroute("**/api/v3/state**")
        await page.route("**/api/v3/state**", mock_state_cfg_reject)
        await page.evaluate("(async () => { fetchGen++; await refreshData(); })()")
        await page.wait_for_timeout(500)
        assert await page.locator("#cfgActiveView").is_visible()
        assert await page.locator("#cfgRejectionNote").is_visible()

        # --- 8. Logout Clean ---
        print("Testing Logout Clean...")
        await page.locator("#btnResume").click()
        await page.wait_for_timeout(200)
        assert await page.locator("#resumeConfirmRow").is_visible()
        
        await page.locator("#btnLogout").click()
        await page.wait_for_timeout(500)
        
        assert not await page.locator("#resumeConfirmRow").is_visible()
        assert await page.locator("#pill-auth-txt").inner_text() == "Anonym"

        await context.close()
        await browser.close()
        
        assert len(js_errors) == 0, f"JS Errors found: {js_errors}"
        assert len(forbidden_writes) == 0, f"Forbidden Writes: {forbidden_writes}"
        print("Alle Integrationstests BESTANDEN.")

if __name__ == "__main__":
    asyncio.run(run_tests())
