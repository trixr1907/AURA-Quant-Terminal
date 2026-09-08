#!/usr/bin/env python3
"""Run every automated verification gate with research-only verdict semantics.

External/manual evidence is limited to TradingView compilation. Mathematical
parity between Pine Script and JavaScript requires independently verified
Golden-Master fixtures with machine-readable provenance. Without independent
provenance (or with self-comparison fixtures), the gate fails closed with
GOLDEN_MASTER_UNVERIFIED. The statistical gate determines whether any model
edge is evidenced.
"""
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
RUNTIME_DIR_NAMES = {".runtime", ".venv"}
GOLDEN_FILES = [
    "BTCUSDT_1h.csv",
    "ETHUSDT_1h.csv",
    "SOLUSDT_1h.csv",
    "XRPUSDT_4h.csv",
    "DOGEUSDT_4h.csv",
]
ALLOWED_PROVENANCE_SOURCES = {
    "TradingView/Pine",
    "TradingView",
    "Pine Script",
    "TradingView Pine",
    "independent_reference",
    "independent reference",
}
# The five hard sub-scores are always compared; the external compile+export are the
# only two gates that CANNOT be produced locally.
SECRET_PATTERNS = [
    (r"-----BEGIN[ A-Z]*PRIVATE KEY-----", "PEM private key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"BITGET_API_(KEY|SECRET|PASSPHRASE)\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{8,}", "Bitget credential value"),
]


def check_version_progression(current: str, latest_tag: str | None, tracked_changes: bool) -> tuple[str, str]:
    """Require strict SemVer and a version bump after the latest release tag."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", current)
    if not match:
        return "FAIL", json.dumps({"version": current, "error": "VERSION must use SemVer MAJOR.MINOR.PATCH"})
    if not latest_tag:
        return "PASS", json.dumps({"version": current, "baseline": None})
    tag_match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", latest_tag)
    if not tag_match:
        return "FAIL", json.dumps({"version": current, "tag": latest_tag, "error": "latest release tag is not SemVer"})
    current_parts = tuple(int(value) for value in match.groups())
    tag_parts = tuple(int(value) for value in tag_match.groups())
    if current_parts < tag_parts:
        return "FAIL", json.dumps({"version": current, "tag": latest_tag, "error": "version regressed"})
    if tracked_changes and current_parts == tag_parts:
        return "FAIL", json.dumps({"version": current, "tag": latest_tag, "error": "version bump required for update"})
    return "PASS", json.dumps({"version": current, "tag": latest_tag})


def run(cmd, cwd=ROOT, env=None, timeout=900):
    """Run a command; return (exit_code, stdout, stderr)."""
    child_env = dict(env) if env is not None else {**__import__("os").environ}
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    cur_path = child_env.get("PATH", "")
    if "/usr/local/bin" not in cur_path:
        child_env["PATH"] = f"/usr/local/bin:{cur_path}" if cur_path else "/usr/local/bin"
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def check(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def is_runtime_path(path: Path) -> bool:
    """Return whether a path belongs to a generated local runtime."""
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return False
    return any(part in RUNTIME_DIR_NAMES for part in relative.parts)


# ---------------------------------------------------------------------------
#  Honest release gate (TEIL 3): the statistical edge is COMPUTED, never assumed.
# ---------------------------------------------------------------------------

def parse_sensitivity_report(text: str) -> dict | None:
    """Parse the JSON report emitted by tests/sensitivity_release_gates.js."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def classify_sensitivity(report: dict | None) -> tuple[str, str]:
    """Map the computed statistical release state to a check status.

    NO_EVIDENCE must block a clean release (it is a NO-GO, never a silent green).
    """
    if not isinstance(report, dict):
        return "FAIL", "sensitivity report not valid JSON"
    release = report.get("release")
    reasons = "; ".join(report.get("reasons", [])) or "no reasons recorded"
    if release == "NO_EVIDENCE":
        return "NO-GO", f"MODEL_NO_EVIDENCE: {reasons}"
    if release == "RESEARCH_ONLY":
        return "CONDITIONAL", f"RESEARCH_ONLY (edge unstable): {reasons}"
    if release == "PAPER_CANDIDATE":
        return "PASS", "PAPER_CANDIDATE (synthetic edge present — still paper)"
    return "FAIL", f"unknown sensitivity release state: {release!r}"


def compute_verdict(results: list[dict], model_no_evidence: bool = False) -> str:
    """Aggregate per-check statuses into the honest final verdict.

    A clean GO is only possible when nothing FAILed AND the statistical model did
    not report NO_EVIDENCE. Missing external evidence remains a NO-GO, never a GO.
    """
    statuses = [r.get("status") for r in results]
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    if model_no_evidence:
        return "SOFTWARE_GO / MODEL_NO_EVIDENCE"
    if any(s == "NO-GO" for s in statuses):
        return "NO-GO"
    return "GO"


def extract_versions(relay_src: str, readme_text: str, dashboard_html: str) -> dict[str, str | None]:
    """Extract SemVer strings from Relay, README, and Dashboard."""
    semver = r"(\d+\.\d+\.\d+)"
    relay_ver = re.search(r'"version"\s*:\s*"' + semver + r'"', relay_src)
    readme_ver = re.search(r"#\s*AURA\s+v" + semver, readme_text)
    dash_ver = re.search(r"AURA\s+(?:Quant\s+Terminal\s+)?v" + semver, dashboard_html)
    return {
        "relay /serving": relay_ver.group(1) if relay_ver else None,
        "README header": readme_ver.group(1) if readme_ver else None,
        "dashboard footer": dash_ver.group(1) if dash_ver else None,
    }

def check_version_consistency(relay_src: str, readme_text: str, dashboard_html: str) -> tuple[str, str]:
    """Check version consistency across components in a fail-closed manner.

    Relay, README, and Dashboard versions must all be present (not None) and identical.
    """
    versions = extract_versions(relay_src, readme_text, dashboard_html)
    stale_changelog = re.findall(r"### v(\d+\.\d+(?:\.\d+)?)[^\n]*\(aktuelle Fassung\)", readme_text)
    vals = list(versions.values())
    if any(v is None for v in vals):
        return "FAIL", json.dumps({"versions": versions, "error": "missing version", "stale_changelog_markers": stale_changelog}, ensure_ascii=False)
    distinct = set(vals)
    if len(distinct) != 1:
        return "FAIL", json.dumps({"versions": versions, "error": "mismatched versions", "stale_changelog_markers": stale_changelog}, ensure_ascii=False)
    return "PASS", json.dumps({"versions": versions, "stale_changelog_markers": stale_changelog}, ensure_ascii=False)

def is_self_comparison_csv(content_or_path: str | Path) -> tuple[bool, str]:
    """Check if a Golden Master CSV matches the known local self-comparison generator pattern.

    A file is rejected as self-comparison if ALL of these criteria are met:
    1. Header starts with 'timestamp,open,high,low,close,volume,GM Trend Score,'
    2. No empty/'na'/'NaN'/'n/a' score cell in the entire file
    3. The first 235 data rows have all five GM score columns exactly equal to '50.00'
    """
    if isinstance(content_or_path, Path):
        text = content_or_path.read_text(encoding="utf-8", errors="replace")
    elif isinstance(content_or_path, str) and "\n" not in content_or_path and Path(content_or_path).is_file():
        text = Path(content_or_path).read_text(encoding="utf-8", errors="replace")
    else:
        text = str(content_or_path)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 236:  # header + 235 rows
        return False, "less than 235 data rows"

    header = lines[0]
    expected_header_prefix = "timestamp,open,high,low,close,volume,GM Trend Score,"
    if not header.startswith(expected_header_prefix):
        return False, "header does not start with local generator prefix"

    headers = [h.strip() for h in header.split(",")]
    score_col_names = [
        "GM Trend Score", "GM Momentum Score", "GM Volume Score",
        "GM Structure Score", "GM Core Score"
    ]
    score_indices = []
    for name in score_col_names:
        try:
            score_indices.append(headers.index(name))
        except ValueError:
            return False, f"missing expected score column: {name}"

    # Check for empty / na / NaN in score columns
    for line in lines[1:]:
        cols = [c.strip() for c in line.split(",")]
        if len(cols) <= max(score_indices):
            continue
        for s_idx in score_indices:
            val = cols[s_idx]
            if val == "" or val.lower() in ("na", "nan", "n/a"):
                return False, "contains na/NaN/empty score cells (external warmup pattern)"

    # Check first 235 data rows for exact 50.00 in all five score columns
    for line_idx in range(1, 236):
        cols = [c.strip() for c in lines[line_idx].split(",")]
        if len(cols) <= max(score_indices):
            return False, f"row {line_idx} has insufficient columns"
        scores = [cols[i] for i in score_indices]
        if not all(s == "50.00" for s in scores):
            return False, f"row {line_idx} score is not 50.00: {scores}"

    return True, "matches known local self-comparison generator pattern"

def verify_golden_authenticity(
    golden_dir: Path,
    golden_files: list[str],
    provenance_path: Path | None = None,
) -> tuple[str, str]:
    """Verify Golden Master fixtures fail-closed against provenance and authenticity rules."""
    unverified = []
    for f in golden_files:
        path = golden_dir / f
        if not path.exists():
            return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: missing fixture {f}"
        is_self_comp, _reason = is_self_comparison_csv(path)
        if is_self_comp:
            unverified.append(f)

    if unverified:
        return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: self-comparison fixture detected ({', '.join(unverified)})"

    prov_file = provenance_path or (golden_dir / "provenance.json")
    if not prov_file.exists() or not prov_file.is_file():
        return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: missing provenance manifest ({prov_file.name})"

    try:
        prov_raw = json.loads(prov_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: invalid provenance JSON ({exc})"

    if not isinstance(prov_raw, dict):
        return "NO-GO", "GOLDEN_MASTER_UNVERIFIED: provenance root must be a JSON object"

    fixtures_map = prov_raw.get("fixtures", prov_raw) if isinstance(prov_raw.get("fixtures"), dict) else prov_raw

    for f in golden_files:
        entry = fixtures_map.get(f)
        if not isinstance(entry, dict):
            return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: missing provenance entry for {f}"

        sha = entry.get("sha256")
        source = entry.get("source")
        export_time = entry.get("export_time") or entry.get("export_date") or entry.get("exported_at")
        symbol = entry.get("symbol")
        timeframe = entry.get("timeframe")

        missing_fields = []
        if not sha:
            missing_fields.append("sha256")
        if not source:
            missing_fields.append("source")
        if not export_time:
            missing_fields.append("export_time")
        if not symbol:
            missing_fields.append("symbol")
        if not timeframe:
            missing_fields.append("timeframe")

        if missing_fields:
            return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: incomplete provenance metadata for {f} (missing: {', '.join(missing_fields)})"

        if str(source).strip() not in ALLOWED_PROVENANCE_SOURCES:
            return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: untrusted provenance source '{source}' for {f}"

        actual_sha = hashlib.sha256((golden_dir / f).read_bytes()).hexdigest().lower()
        expected_sha = str(sha).strip().lower()
        if actual_sha != expected_sha:
            return "NO-GO", f"GOLDEN_MASTER_UNVERIFIED: sha256 mismatch for {f} (expected {expected_sha}, got {actual_sha})"

    return "PASS", "all golden master fixtures verified with independent provenance"


def run_sensitivity_gate() -> tuple[str, str, str | None]:
    """Run the sensitivity sweep and return (status, detail, release_state)."""
    rc, out, err = run(["node", "tests/sensitivity_release_gates.js"])
    if rc != 0:
        return "FAIL", (err or out).strip()[-300:], None
    report = parse_sensitivity_report(out)
    status, detail = classify_sensitivity(report)
    release_state = report.get("release") if isinstance(report, dict) else None
    return status, detail, release_state


def main() -> int:
    results = []
    env = {**__import__("os").environ}

    def add(check_res):
        results.append(check_res)

    # 1. Engine suite
    rc, out, err = run(["node", "tests/test_engine_full.js"])
    ok = rc == 0 and "0 FAILED" in out
    summary_line = next((ln for ln in out.splitlines() if "PASSED" in ln and "FAILED" in ln), "")
    add(check("engine suite", "PASS" if ok else "FAIL",
              summary_line.strip() or (err or out).strip()[-200:]))
    if not ok:
        add(check("engine suite (detail)", "FAIL", (err or out)[-1500:]))

    # 1b. Radar batching, zero-volume early exit, and user sort/filter behavior
    rc, out, err = run(["node", "tests/test_radar_progressive.js"])
    add(check("radar progressive rendering", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))
    rc, out, err = run(["node", "tests/test_radar_sorting.js"])
    add(check("radar smart sorting", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))
    rc, out, err = run(["node", "tests/test_autobot_entry_gate.js"])
    add(check("autobot entry gate", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))

    # 1c. Live trade tracker
    rc, out, err = run(["node", "tests/test_live_trade_tracker.js"])
    add(check("live trade tracker", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))
    rc, out, err = run(["node", "tests/test_websocket_generation.js"])
    add(check("websocket generation guard", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))
    rc, out, err = run(["node", "tests/test_relay_origin.js"])
    add(check("relay origin selection", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))

    # 1d. SMC Sessions & Killzones (Single Source of Truth)
    rc, out, err = run(["node", "tests/test_smc_sessions.js"])
    add(check("smc sessions suite", "PASS" if rc == 0 else "FAIL",
              (out or err).strip()[:300]))

    # 2. Statistical Oracle & Metamorphic tests
    rc1, out1, err1 = run([sys.executable, "tests/reference_backtest.py"])
    rc2, out2, err2 = run(["node", "tests/test_lookahead_metamorphic.js"])
    ok = (rc1 == 0) and (rc2 == 0) and ("3 PASSED" in out2)
    add(check("statistical oracle & metamorphic", "PASS" if ok else "FAIL",
              (out2.strip() or err2.strip() or out1.strip())[:200]))

    # 2b. Honest release gate: the model's edge is COMPUTED from a sensitivity
    # sweep, never asserted by hand. NO_EVIDENCE -> verdict must not be a clean GO.
    sens_status, sens_detail, sens_release = run_sensitivity_gate()
    add(check("statistical release gate (sensitivity)", sens_status, sens_detail))
    model_no_evidence = sens_release == "NO_EVIDENCE"

    # 3. Relay suite (uses stdlib unittest — zero external pip dependencies needed)
    rc, out, err = run([sys.executable, "-m", "unittest", "tests/test_relay_full.py"])
    ok = rc == 0
    detail = (err or out).strip()
    summary_lines = [ln.strip() for ln in detail.splitlines() if "Ran " in ln or "OK" in ln or "FAILED" in ln]
    summary_text = " | ".join(summary_lines) if summary_lines else detail[-100:]
    add(check("relay suite", "PASS" if ok else "FAIL", summary_text[:200]))

    # 4. Python compile + launcher behavior + release sync suite
    rc, out, err = run([sys.executable, "-m", "py_compile",
                        "start.py", "bitget_relay.py", "tests/browser_research_harness.py",
                        "tests/reference_backtest.py", "scripts/release_check.py",
                        "scripts/sync_market_data.py"])
    add(check("python compile", "PASS" if rc == 0 else "FAIL", (err or out).strip()[:300]))
    rc, out, err = run([sys.executable, "-m", "unittest", "tests/test_launcher.py"])
    detail = (err or out).strip()
    summary_lines = [ln.strip() for ln in detail.splitlines() if "Ran " in ln or "OK" in ln or "FAILED" in ln]
    add(check("smart launcher suite", "PASS" if rc == 0 else "FAIL", " | ".join(summary_lines)[:200]))
    rc, out, err = run([sys.executable, "-m", "unittest", "tests/test_research_cleanup.py"])
    detail = (err or out).strip()
    summary_lines = [ln.strip() for ln in detail.splitlines() if "Ran " in ln or "OK" in ln or "FAILED" in ln]
    add(check("research-only cleanup", "PASS" if rc == 0 else "FAIL", " | ".join(summary_lines)[:200]))
    rc, out, err = run([sys.executable, "-m", "unittest", "tests/test_release_sync.py"])
    detail = (err or out).strip()
    summary_lines = [ln.strip() for ln in detail.splitlines() if "Ran " in ln or "OK" in ln or "FAILED" in ln]
    add(check("release sync suite", "PASS" if rc == 0 else "FAIL", " | ".join(summary_lines)[:200]))

    # 5. Dashboard JS syntax (extract <script> block, node --check)
    html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    if not m:
        add(check("dashboard JS syntax", "FAIL", "no <script> block found"))
    else:
        tmp = ROOT / "tests" / ".release_dashboard_check.js"
        tmp.write_text(m.group(1), encoding="utf-8")
        rc, out, err = run(["node", "--check", str(tmp.relative_to(ROOT))])
        tmp.unlink(missing_ok=True)
        add(check("dashboard JS syntax", "PASS" if rc == 0 else "FAIL", (err or out).strip()[:300]))

    # 6. Pine static rules
    rc, out, err = run([sys.executable, "tests/pine_static_check.py"])
    add(check("pine static rules", "PASS" if rc == 0 else "FAIL", (out or err).strip()[:300]))

    # 7. Golden-Master: harness self-test (required) + authenticity + five real fixtures (external)
    rc, out, err = run(["node", "tests/test_compare_pine_js_golden.js"])
    add(check("golden harness self-test", "PASS" if rc == 0 else "FAIL", (out or err).strip()[:300]))

    present = [f for f in GOLDEN_FILES if (GOLDEN_DIR / f).exists()]
    missing = [f for f in GOLDEN_FILES if f not in present]
    if missing:
        add(check("golden master authenticity", "NO-GO",
                  f"GOLDEN_MASTER_UNVERIFIED: missing TradingView exports: {', '.join(missing)}"))
        add(check("golden 5-symbol comparison", "NO-GO",
                  f"missing TradingView exports: {', '.join(missing)} (external/manual)"))
    else:
        auth_status, auth_detail = verify_golden_authenticity(GOLDEN_DIR, GOLDEN_FILES)
        add(check("golden master authenticity", auth_status, auth_detail))
        if auth_status != "PASS":
            add(check("golden 5-symbol comparison", "NO-GO",
                      f"blocked by golden master authenticity ({auth_detail})"))
        else:
            rc, out, err = run(["node", "tests/compare_pine_js_golden.js"]
                               + [str(GOLDEN_DIR / f) for f in GOLDEN_FILES])
            add(check("golden 5-symbol comparison", "PASS" if rc == 0 else "FAIL",
                      (out or err).strip()[:400]))

    # 8. Deterministic browser E2E (requires playwright)
    rc, out, err = run([sys.executable, "tests/browser_research_harness.py"], env=env, timeout=1800)
    detail = (out or err).strip()
    tail = detail.splitlines()[-1] if detail else ""
    if rc != 0 and ("No module named 'playwright'" in detail or "No module named playwright" in detail):
        add(check("browser E2E (deterministic)", "CONDITIONAL",
                  "SKIPPED: playwright not installed in current Python env (pip install playwright && playwright install chromium)"))
    else:
        add(check("browser E2E (deterministic)", "PASS" if rc == 0 else "FAIL", tail[:400]))

    # 9. Documentation/version consistency (fail-closed)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    relay_src = (ROOT / "bitget_relay.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ver_status, ver_detail = check_version_consistency(relay_src, readme, html)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        ver_status = "FAIL"
        ver_detail = json.dumps({"version": version, "error": "VERSION must use SemVer MAJOR.MINOR.PATCH"})
    elif ver_status == "PASS":
        parsed_versions = json.loads(ver_detail)["versions"]
        if any(value != version for value in parsed_versions.values()):
            ver_status = "FAIL"
            ver_detail = json.dumps({"version": version, "versions": parsed_versions, "error": "VERSION mismatch"})
    add(check("version consistency", ver_status, ver_detail))

    # 9b. Every update after a release tag must advance SemVer.
    tag_rc, latest_tag, _ = run(["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*"])
    latest_tag = latest_tag.strip() if tag_rc == 0 else None
    changes_rc, changes, changes_err = run(["git", "status", "--porcelain", "--untracked-files=all"])
    if changes_rc != 0:
        progression_status = "FAIL"
        progression_detail = json.dumps({"error": "cannot inspect tracked changes", "stderr": changes_err[-1000:]})
    else:
        progression_status, progression_detail = check_version_progression(version, latest_tag, bool(changes.strip()))
    add(check("version progression", progression_status, progression_detail))

    # 10. Secret-pattern and generated-file scan
    hits = []
    scan_exts = (".py", ".md", ".html", ".json", ".js", ".pine")
    for path in ROOT.rglob("*"):
        if is_runtime_path(path):
            continue
        if not path.is_file() or path.suffix not in scan_exts:
            continue
        if ".release_dashboard_check.js" in path.name:
            continue
        if any(seg in path.parts for seg in (".pytest_cache", "__pycache__")):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat, label in SECRET_PATTERNS:
            for match in re.finditer(pat, text):
                line = text[:match.start()].count("\n") + 1
                hits.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    add(check("secret scan", "PASS" if not hits else "FAIL",
              "; ".join(hits[:10]) if hits else "no credential values found"))

    # Workspace hygiene (report only — never delete generated user state)
    hygiene = []
    for seg in ("__pycache__", ".pytest_cache"):
        n = sum(1 for p in ROOT.rglob(seg) if p.is_dir() and not is_runtime_path(p))
        if n:
            hygiene.append(f"{n} {seg}/ dir(s)")
    for p in ROOT.rglob("*.png"):
        if not is_runtime_path(p):
            hygiene.append(f"screenshot {p.name}")
    add(check("workspace hygiene (report)", "PASS" if not hygiene else "CONDITIONAL",
              "; ".join(hygiene) if hygiene else "clean"))

    # Aggregate
    verdict = compute_verdict(results, model_no_evidence=model_no_evidence)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": verdict,
        "checks": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Stamp the verdict for build_package.py's guard (and for reproducibility).
    (ROOT / "scripts" / ".release_verdict.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if "--json-only" not in sys.argv:
        print("\n=== AURA RELEASE CHECK ===", file=sys.stderr)
        for r in results:
            flag = {"PASS": "[OK]   ", "FAIL": "[FAIL] ", "NO-GO": "[NOGO] ",
                    "CONDITIONAL": "[WARN] "}.get(r["status"], "[??]   ")
            print(f"{flag}{r['name']:34s} {r['detail'][:110]}", file=sys.stderr)
        print(f"\nVERDICT: {verdict}", file=sys.stderr)
        if verdict == "SOFTWARE_GO / MODEL_NO_EVIDENCE":
            print("Statistical model reports NO_EVIDENCE — software passes, but there "
                  "is no mathematical edge. Not a clean GO.", file=sys.stderr)
        elif verdict == "NO-GO":
            print("External/manual evidence missing — not a false green. "
                  "See RELEASE_CHECKLIST.md.", file=sys.stderr)

    required_fail = any(r["status"] == "FAIL" for r in results)
    return 2 if required_fail else 0


if __name__ == "__main__":
    sys.exit(main())
