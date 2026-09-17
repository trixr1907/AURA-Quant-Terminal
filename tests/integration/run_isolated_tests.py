import os
import sys
import time
import signal
import asyncio
import subprocess
import urllib.request
import urllib.error
import sqlite3

os.environ["AURA_DB_PATH"] = "/tmp/aura_test.db"
if os.path.exists(os.environ["AURA_DB_PATH"]):
    os.remove(os.environ["AURA_DB_PATH"])

os.environ["AURA_RELAY_TOKEN"] = "TEST_INTEGRATION_TOKEN_XYZ"

print("Starting Uvicorn for tests...")
proc = subprocess.Popen(
    ["python3.12", "-m", "uvicorn", "aura.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8899"],
    cwd="/home/ivo/projects/AURA_v2",
    env=os.environ,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

try:
    ready = False
    for _ in range(30):
        try:
            res = urllib.request.urlopen("http://127.0.0.1:8899/api/v3/health")
            if res.status == 200:
                ready = True
                break
        except urllib.error.URLError:
            pass
        time.sleep(0.5)

    if not ready:
        print("Uvicorn failed to start.")
        print(proc.stderr.read().decode()); sys.exit(1)
        
    print("Uvicorn is ready! Running DB Fixture...")
    conn = sqlite3.connect("/tmp/aura_test.db")
    now = int(time.time() * 1000)
    with conn:
        conn.execute("""
            INSERT INTO trades (id, source, symbol, dir, status, entry_price, current_sl, initial_sl,
                notional, margin, leverage, opened_at_ms, engine_version, record_schema, timeframe)
            VALUES ('fixture_t1', 'test_script', 'SOLUSDT', 1, 'open', '150.0', '140.0', '140.0',
                '1500', '150', 10, ?, 'v2', 3, '1H')
        """, (now - 3600*1000,))
        conn.execute("""
            INSERT INTO runner_state (id, fsm_state, reason, equity, updated_at_ms)
            VALUES (1, 'RUNNING', 'UI Integration Test', '10000.0', ?)
        """, (now,))
    conn.close()

    print("Running Playwright tests...")
    res = subprocess.run(["python3.12", "/home/ivo/projects/AURA_v2/tests/integration/preview_ui_test.py"], capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)
        
    sys.exit(res.returncode)
        
finally:
    print("Stopping Uvicorn...")
    proc.send_signal(signal.SIGTERM)
    proc.wait()
    if os.path.exists("/tmp/aura_test.db"):
        os.remove("/tmp/aura_test.db")
    print("Done.")
