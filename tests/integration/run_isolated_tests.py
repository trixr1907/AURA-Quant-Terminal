import os
import sys
import time
import signal
import subprocess
import urllib.request
import urllib.error
import sqlite3
import tempfile
import socket
from pathlib import Path

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def kill_process(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

if __name__ == "__main__":
    if is_port_in_use(8899):
        print("ERROR: Port 8899 is already in use by a foreign process. Fail-closed.")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "aura_test.db")
        os.environ["AURA_DB_PATH"] = db_path
        os.environ["AURA_RELAY_TOKEN"] = "TEST_INTEGRATION_TOKEN_XYZ"
        os.environ["PYTHONPATH"] = str(project_root)

        print("Starting Uvicorn for tests...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "aura.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8899"],
            cwd=str(project_root),
            env=os.environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        try:
            ready = False
            for _ in range(30):
                if proc.poll() is not None:
                    break
                try:
                    res = urllib.request.urlopen("http://127.0.0.1:8899/api/v3/health")
                    if res.status == 200:
                        ready = True
                        break
                except urllib.error.URLError:
                    time.sleep(0.5)

            if not ready:
                print("Uvicorn failed to start or died early.")
                out, err = proc.communicate(timeout=5)
                print("STDOUT:", out.decode())
                print("STDERR:", err.decode())
                sys.exit(1)
                
            print("Uvicorn is ready! Running DB Fixture...")
            conn = sqlite3.connect(db_path)
            now = int(time.time() * 1000)
            with conn:
                conn.execute("""
                    INSERT INTO trades (id, source, symbol, dir, status, entry_price, current_sl, initial_sl,
                        notional, margin, leverage, opened_at_ms, engine_version, record_schema, timeframe)
                    VALUES ('fixture_t1', 'test_script', 'ETHUSDT', 1, 'open', '2000.0', '1900.0', '1900.0',
                        '2000', '200', 10, ?, 'v2', 3, '1H')
                """, (now - 3600*1000,))
                conn.execute("""
                    INSERT INTO runner_state (id, fsm_state, reason, equity, updated_at_ms)
                    VALUES (1, 'RUNNING', 'UI Integration Test', '10000.0', ?)
                """, (now,))
            conn.close()

            print("Running Playwright tests...")
            test_script = project_root / "tests" / "integration" / "preview_ui_test.py"
            
            # 1. Normal Run
            test_proc = subprocess.run(
                [sys.executable, str(test_script)],
                capture_output=True, text=True, timeout=30
            ) 
            print("--- NORMAL RUN STDOUT ---")
            print(test_proc.stdout)
            if test_proc.stderr:
                print("--- NORMAL RUN STDERR ---")
                print(test_proc.stderr)

            # 2. Negative Run (Intentional Fail)
            print("\nRunning Playwright tests (Negative Control)...")
            env_neg = os.environ.copy()
            env_neg["FAIL_INTENTIONALLY"] = "1"
            neg_proc = subprocess.run(
                [sys.executable, str(test_script)],
                capture_output=True, text=True, timeout=30,
                env=env_neg
            )
            print("--- NEGATIVE RUN STDOUT ---")
            print(neg_proc.stdout)
            if neg_proc.stderr:
                print("--- NEGATIVE RUN STDERR ---")
                print(neg_proc.stderr)
            
            if neg_proc.returncode == 0:
                print("ERROR: Negative Control passed unexpectedly! It should have failed.")
                sys.exit(1)
            else:
                print(f"SUCCESS: Negative control correctly failed with code {neg_proc.returncode}.")
                
            sys.exit(test_proc.returncode)
            
        finally:
            print("Stopping Uvicorn...")
            kill_process(proc)
            print("Done.")
