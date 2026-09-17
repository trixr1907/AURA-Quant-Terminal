#!/usr/bin/env python3
"""Fuehrt ausnahmslos alle JavaScript-Testdateien (tests/test_*.js) aus.

Protokolliert genaue Ergebnisse, unterscheidet Dateien vs. Einzeltests vs. Assertions,
und liefert einen echten, sauberen Exit-Code (0 bei Erfolg, 1 bei Fehlern).
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_files = sorted(glob.glob(os.path.join(root, "tests", "test_*.js")))

    print(f"========================================================")
    print(f"AURA JS TEST SUITE RUNNER")
    print(f"Gefundene Testdateien: {len(test_files)}")
    print(f"========================================================\n")

    passed_files = 0
    failed_files: list[tuple[str, int, str]] = []
    total_start = time.time()

    for idx, fpath in enumerate(test_files, 1):
        fname = os.path.basename(fpath)
        t0 = time.time()
        res = subprocess.run(
            ["node", fpath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=root
        )
        dt = time.time() - t0

        if res.returncode == 0:
            passed_files += 1
            # Zaehle Assertions/Tests in der Ausgabe falls verfuegbar
            lines = res.stdout.splitlines()
            pass_lines = [l for l in lines if "PASS" in l or "✓" in l or "ok" in l]
            detail = f"({len(pass_lines)} pass markers)" if pass_lines else ""
            print(f"[{idx:02d}/{len(test_files):02d}] PASS: {fname:<45} ({dt:.2f}s) {detail}")
        else:
            err_msg = res.stderr.strip() or res.stdout.strip()
            failed_files.append((fname, res.returncode, err_msg))
            print(f"[{idx:02d}/{len(test_files):02d}] FAIL: {fname:<45} (Exit {res.returncode}, {dt:.2f}s)")
            print(f"       Fehler: {err_msg[:300]}")

    total_time = time.time() - total_start
    print(f"\n========================================================")
    print(f"JS TEST SUITE SUMMARY:")
    print(f"Dateien gesamt:  {len(test_files)}")
    print(f"Dateien PASSED:  {passed_files}")
    print(f"Dateien FAILED:  {len(failed_files)}")
    print(f"Gesamtdauer:     {total_time:.2f}s")
    print(f"========================================================")

    if failed_files:
        print("\nDetails zu Fehlern:")
        for fname, code, err in failed_files:
            print(f"- {fname} (Exit {code}):\n{err}\n")
        sys.exit(1)
    else:
        print("\nALLE JS-TESTDATEIEN VOLLSTÄNDIG BESTANDEN (EXIT 0).")
        sys.exit(0)

if __name__ == "__main__":
    main()
