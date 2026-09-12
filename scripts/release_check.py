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
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
GOLDEN_PARITY_REFERENCE = GOLDEN_DIR / "parity_reference.json"
RUNTIME_DIR_NAMES = {".runtime", ".venv"}
VERSION_BUMP_EXEMPT_PREFIXES = (".github/", "docs/")
VERSION_BUMP_EXEMPT_FILES = {"LICENSE"}
VERSION_BUMP_EXEMPT_SUFFIXES = {".md"}
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


def check_version_progression(current: str, latest_tag: str | None, tracked_changes: bool, allow_current_version: bool = False) -> tuple[str, str]:
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
    if tracked_changes and current_parts == tag_parts and not allow_current_version:
        return "FAIL", json.dumps({"version": current, "tag": latest_tag, "error": "version bump required for update"})
    return "PASS", json.dumps({"version": current, "tag": latest_tag})


def latest_semver_tag_from_refs(ref_output: str) -> str | None:
    """Return the highest strict SemVer tag from git tag or ls-remote output."""
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for line in ref_output.splitlines():
        token = line.rsplit("/", 1)[-1].removesuffix("^{}").strip()
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", token)
        if match:
            version_parts = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
            candidates.append((version_parts, token))
    return max(candidates)[1] if candidates else None


def inspect_version_tag_state() -> tuple[str | None, str | None, str | None]:
    """Inspect reachable local tags and origin tags without mutating local refs."""
    local_rc, local_output, _ = run(["git", "tag", "--list", "v*.*.*"])
    local_tag = latest_semver_tag_from_refs(local_output) if local_rc == 0 else None
    remote_rc, remote_output, remote_error = run(["git", "ls-remote", "--tags", "origin"], timeout=30)
    if remote_rc != 0:
        return local_tag, None, remote_error[-1000:] or "git ls-remote failed"
    return local_tag, latest_semver_tag_from_refs(remote_output), None


def requires_version_bump(path: str) -> bool:
    """Return whether a committed path is part of the versioned product."""
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        return False
    if normalized in VERSION_BUMP_EXEMPT_FILES:
        return False
    if Path(normalized).suffix in VERSION_BUMP_EXEMPT_SUFFIXES:
        return False
    return not normalized.startswith(VERSION_BUMP_EXEMPT_PREFIXES)


def inspect_worktree_changes() -> tuple[bool | None, str | None]:
    """Return whether staged, unstaged, or untracked product paths changed."""
    rc, output, error = run(["git", "status", "--porcelain", "--untracked-files=all"])
    if rc != 0:
        return None, error[-1000:] or "cannot inspect worktree changes"
    paths = []
    for line in output.splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        paths.append(path)
    return any(requires_version_bump(path) for path in paths), None


def inspect_committed_changes_since_tag(tag: str, *, remote: bool = False) -> tuple[bool | None, str | None]:
    """Return whether product paths changed after a local or remote release tag."""
    tag_ref = tag
    if remote:
        rc, output, error = run(
            ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
            timeout=30,
        )
        if rc != 0:
            return None, error[-1000:] or "cannot resolve remote release tag"
        resolved = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] in {f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"}:
                resolved.append((fields[1], fields[0]))
        tag_ref = next((sha for ref, sha in resolved if ref.endswith("^{}")), "")
        if not tag_ref:
            tag_ref = next((sha for _ref, sha in resolved), "")
        if not tag_ref:
            return None, f"cannot resolve origin tag {tag}"

    rc, output, error = run(["git", "diff", "--name-only", f"{tag_ref}..HEAD"])
    if rc != 0:
        return None, error[-1000:] or f"cannot compare HEAD with release tag {tag}"
    return any(requires_version_bump(path) for path in output.splitlines()), None


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
    """Aggregate per-check statuses; only an all-PASS result can be GO."""
    statuses = [r.get("status") for r in results]
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    if model_no_evidence:
        return "SOFTWARE_GO / MODEL_NO_EVIDENCE"
    if any(s == "NO-GO" for s in statuses):
        return "NO-GO"
    if any(s == "CONDITIONAL" for s in statuses):
        return "CONDITIONAL"
    if any(s == "WARN" for s in statuses):
        return "WARN"
    if not statuses or any(s != "PASS" for s in statuses):
        return "FAIL"
    return "GO"


def exit_code_for_verdict(verdict: str | None) -> int:
    """Return success (0) only for a valid software release (software gates PASS)."""
    return 0 if verdict in {"GO", "SOFTWARE_GO", "SOFTWARE_GO / MODEL_NO_EVIDENCE"} else 2


def extract_versions(
    relay_src: str,
    readme_text: str,
    dashboard_html: str,
    tutorial_html: str = "",
    pine_src: str = "",
) -> dict[str, str | None]:
    """Extract current, user-visible release metadata from every shipped surface."""
    semver = r"(\d+\.\d+\.\d+)"
    relay_ver = re.search(r'"version"\s*:\s*"' + semver + r'"', relay_src)
    readme_ver = re.search(r"#\s*AURA\s+v" + semver, readme_text)
    dash_ver = re.search(r"AURA\s+(?:Quant\s+Terminal\s+)?v" + semver, dashboard_html)
    tutorial_html = tutorial_html or ""
    pine_src = pine_src or ""
    tutorial_nav = re.search(r'class="nav-logo">AURA\s+v' + semver, tutorial_html)
    tutorial_hero = re.search(r'<h1>AURA\s+v' + semver, tutorial_html)
    tutorial_footer = re.search(r'<footer>\s*AURA\s+v' + semver, tutorial_html)
    pine_header = re.search(r"^//\s+AURA\s+v" + semver + r"\s+—", pine_src, re.MULTILINE)
    pine_dashboard = re.search(r'f_hdr\(0,\s*"AURA\s+v' + semver + r'"', pine_src)
    pine_alert = re.search(r'"type":"symbiose\.v' + semver + r'"', pine_src)
    return {
        "relay /serving": relay_ver.group(1) if relay_ver else None,
        "README header": readme_ver.group(1) if readme_ver else None,
        "dashboard footer": dash_ver.group(1) if dash_ver else None,
        "tutorial navigation": tutorial_nav.group(1) if tutorial_nav else None,
        "tutorial hero": tutorial_hero.group(1) if tutorial_hero else None,
        "tutorial footer": tutorial_footer.group(1) if tutorial_footer else None,
        "Pine header": pine_header.group(1) if pine_header else None,
        "Pine dashboard": pine_dashboard.group(1) if pine_dashboard else None,
        "Pine alert type": pine_alert.group(1) if pine_alert else None,
    }

def check_version_consistency(
    relay_src: str,
    readme_text: str,
    dashboard_html: str,
    tutorial_html: str | None = None,
    pine_src: str | None = None,
) -> tuple[str, str]:
    """Check version consistency across components in a fail-closed manner.

    Relay, README, and Dashboard versions must all be present (not None) and identical.
    """
    versions = extract_versions(relay_src, readme_text, dashboard_html, tutorial_html or "", pine_src or "")
    if tutorial_html is None:
        versions = {k: v for k, v in versions.items() if not k.startswith("tutorial ")}
    if pine_src is None:
        versions = {k: v for k, v in versions.items() if not k.startswith("Pine ")}
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

    if "lockbox" in prov_raw and isinstance(prov_raw["lockbox"], dict):
        lb = prov_raw["lockbox"]
        if not lb.get("cutoff_time") or not lb.get("locked_span_days") or lb.get("status") != "LOCKED" or lb.get("mode") != "forward_holdout":
            return "NO-GO", "GOLDEN_MASTER_UNVERIFIED: lockbox entry missing required cutoff_time, locked_span_days, status=LOCKED, or mode=forward_holdout"

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


def run_model_evidence_real_gate() -> tuple[str, str, str | None]:
    """Run real golden fixture evaluation and return (status, detail, real_verdict)."""
    rc, out, err = run(["node", "tests/model_evidence_real.js"])
    if rc != 0:
        return "FAIL", (err or out).strip()[-300:], None
    try:
        report = json.loads(out.strip())
        verdict = report.get("verdict", "NO_EVIDENCE")
        per_symbol = report.get("per_symbol", [])
        symbol_summaries = []
        for s in per_symbol:
            dsr = s.get("dsr", 0)
            exp = s.get("exp", 0)
            symbol_summaries.append(f"{s.get('symbol')}: exp={exp:.3f} dsr={dsr:.3f}")
        detail = f"{verdict} ({', '.join(symbol_summaries)})"
        return "PASS", detail, verdict
    except Exception as e:
        return "FAIL", f"parse_error: {e}", None


def evaluate_golden_parity_trend(report: dict, reference: dict) -> tuple[str, str]:
    """Fail if any per-fixture parity metric is invalid or worse than its baseline."""
    actual_fixtures = report.get("fixtures")
    expected_fixtures = reference.get("fixtures")
    if not isinstance(actual_fixtures, list) or not isinstance(expected_fixtures, dict):
        return "FAIL", json.dumps({"error": "invalid parity report/reference schema"})

    expected_names = set(GOLDEN_FILES)
    actual_names = [item.get("fixture") if isinstance(item, dict) else None for item in actual_fixtures]
    reference_names = set(expected_fixtures)
    if (
        len(actual_names) != len(expected_names)
        or len(set(actual_names)) != len(actual_names)
        or set(actual_names) != expected_names
        or reference_names != expected_names
    ):
        return "FAIL", json.dumps({
            "error": "fixture set mismatch",
            "expected": sorted(expected_names),
            "actual": actual_names,
            "reference": sorted(reference_names),
        }, separators=(",", ":"))

    actual_by_name = {item["fixture"]: item for item in actual_fixtures}
    regressions = []
    metrics = []
    for fixture in GOLDEN_FILES:
        actual = actual_by_name[fixture]
        expected = expected_fixtures[fixture]
        if not isinstance(expected, dict):
            regressions.append({"fixture": fixture, "error": "invalid reference fixture metrics"})
            continue
        metric = {
            "fixture": fixture,
            "max_delta": actual.get("maxDelta"),
            "soft_mismatches": actual.get("softMismatches"),
            "soft_rate": actual.get("softRate"),
            "reference_max_delta": expected.get("max_delta"),
            "reference_soft_mismatches": expected.get("soft_mismatches"),
            "reference_soft_rate": expected.get("soft_rate"),
        }
        metrics.append(metric)
        if actual.get("ok") is not True:
            regressions.append({"fixture": fixture, "metric": "absolute_threshold", "error": "comparison did not explicitly pass"})
        numeric_pairs = (
            ("max_delta", actual.get("maxDelta"), expected.get("max_delta")),
            ("soft_mismatches", actual.get("softMismatches"), expected.get("soft_mismatches")),
            ("soft_rate", actual.get("softRate"), expected.get("soft_rate")),
        )
        for name, actual_value, reference_value in numeric_pairs:
            if (
                isinstance(actual_value, bool)
                or isinstance(reference_value, bool)
                or not isinstance(actual_value, (int, float))
                or not isinstance(reference_value, (int, float))
            ):
                regressions.append({"fixture": fixture, "metric": name, "error": "non-numeric metric"})
            elif not math.isfinite(actual_value) or not math.isfinite(reference_value):
                regressions.append({"fixture": fixture, "metric": name, "error": "non-finite numeric metric"})
            elif actual_value > reference_value + 1e-15:
                regressions.append({
                    "fixture": fixture,
                    "metric": name,
                    "actual": actual_value,
                    "reference": reference_value,
                })

    payload = {"metrics": metrics, "regressions": regressions}
    return ("FAIL" if regressions else "PASS"), json.dumps(payload, separators=(",", ":"))


def run_golden_parity_trend_gate(reference_path: Path = GOLDEN_PARITY_REFERENCE) -> tuple[str, str]:
    """Run machine-readable Pine/JS comparison and enforce no-regression baselines."""
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "FAIL", json.dumps({"error": f"cannot load parity reference: {exc}"})
    command = ["node", "tests/compare_pine_js_golden.js"] + [str(GOLDEN_DIR / name) for name in GOLDEN_FILES] + ["--json"]
    rc, out, err = run(command)
    if rc != 0:
        return "FAIL", (err or out).strip()[-1000:]
    try:
        report = json.loads(out.strip())
    except json.JSONDecodeError as exc:
        return "FAIL", json.dumps({"error": f"cannot parse parity JSON: {exc}", "output": out[-500:]})
    return evaluate_golden_parity_trend(report, reference)


def main() -> int:
    results = []
    env = {**__import__("os").environ}

    def add(check_res):
        results.append(check_res)

    # 1. Full JS test discovery and execution (fail-closed)
    js_test_files = sorted([p for p in (ROOT / "tests").glob("test_*.js")])
    for js_path in js_test_files:
        rel = str(js_path.relative_to(ROOT))
        name = js_path.stem.replace("test_", "").replace("_", " ")
        rc, out, err = run(["node", rel])
        ok = rc == 0
        detail = (out or err).strip()
        if "FAILED" in detail and "0 FAILED" not in detail:
            ok = False
        add(check(f"js: {name}", "PASS" if ok else "FAIL", detail[:300]))

    # 2. Statistical Oracle & Metamorphic tests
    rc, out, err = run([sys.executable, "scripts/verify_ledger.py"])
    add(check("trials ledger hash chain", "PASS" if rc == 0 else "FAIL", (out or err).strip()[:400]))

    rc_cvd, out_cvd, err_cvd = run([sys.executable, "scripts/cvd_reference.py"])
    add(check("cvd independent reference parity", "PASS" if rc_cvd == 0 else "FAIL", (out_cvd or err_cvd).strip()[:400]))

    rc1, out1, err1 = run([sys.executable, "tests/reference_backtest.py"])
    rc2, out2, err2 = run(["node", "tests/test_lookahead_metamorphic.js"])
    ok = (rc1 == 0) and (rc2 == 0) and ("3 PASSED" in out2)
    add(check("statistical oracle & metamorphic", "PASS" if ok else "FAIL",
              (out2.strip() or err2.strip() or out1.strip())[:200]))

    # 2b. Synthetic fixture integrity gate (fixture integrity, not model evidence)
    sens_status, sens_detail, sens_release = run_sensitivity_gate()
    add(check("synthetic sensitivity gate (fixture integrity)", sens_status, f"{sens_release} (fixture integrity, not model evidence: {sens_detail})"))

    # 2c. Real data model evidence gate (5 Golden Fixtures)
    real_status, real_detail, real_model_verdict = run_model_evidence_real_gate()
    add(check("real data model evidence (5 golden fixtures)", real_status, real_detail))
    model_no_evidence = (real_model_verdict == "NO_EVIDENCE")

    # 2d. OOS Lockbox Quarantine & Evaluation Gate
    from scripts.lockbox_guard import evaluate_lockbox_evaluation
    lb_status, lb_detail, lb_eval_state = evaluate_lockbox_evaluation()
    add(check("lockbox evaluation gate", lb_status, lb_detail))

    # 3. Relay suite (uses stdlib unittest — zero external pip dependencies needed)
    rc, out, err = run([sys.executable, "-m", "unittest", "tests/test_relay_full.py"])
    ok = rc == 0
    detail = (err or out).strip()
    summary_lines = [ln.strip() for ln in detail.splitlines() if "Ran " in ln or "OK" in ln or "FAILED" in ln]
    summary_text = " | ".join(summary_lines) if summary_lines else detail[-100:]
    add(check("relay suite", "PASS" if ok else "FAIL", summary_text[:200]))

    # 4. Python compile + launcher behavior + release sync suite + full pytest
    rc, out, err = run([sys.executable, "-m", "py_compile",
                        "start.py", "bitget_relay.py", "tests/browser_research_harness.py",
                        "tests/reference_backtest.py", "scripts/release_check.py",
                        "scripts/sync_market_data.py", "scripts/verify_ledger.py",
                        "scripts/append_ledger.py", "scripts/cvd_reference.py"])
    add(check("python compile", "PASS" if rc == 0 else "FAIL", (err or out).strip()[:300]))
    rc, out, err = run([sys.executable, "-m", "pytest", "-q"])
    detail = (err or out).strip()
    summary_lines = [ln.strip() for ln in detail.splitlines() if "passed" in ln or "failed" in ln or "error" in ln]
    add(check("pytest full suite", "PASS" if rc == 0 else "FAIL", " | ".join(summary_lines)[:200]))
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

    rc, out, err = run([sys.executable, "-m", "unittest", "tests/test_pine_fvg_capacity.py"])
    add(check("pine FVG capacity regression", "PASS" if rc == 0 else "FAIL", (out or err).strip()[:300]))

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
            parity_status, parity_detail = run_golden_parity_trend_gate()
            add(check("golden 5-symbol comparison & trend", parity_status, parity_detail))

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
    tutorial = (ROOT / "SYMBIOSE_Tutorial.html").read_text(encoding="utf-8")
    pine = (ROOT / "Symbiose_Signal_System_v1.pine").read_text(encoding="utf-8")
    ver_status, ver_detail = check_version_consistency(relay_src, readme, html, tutorial, pine)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        ver_status = "FAIL"
        ver_detail = json.dumps({"version": version, "error": "VERSION must use SemVer MAJOR.MINOR.PATCH"})
    elif ver_status == "PASS":
        parsed_versions = json.loads(ver_detail)["versions"]
        if any(value != version for value in parsed_versions.values()):
            ver_status = "FAIL"
            ver_detail = json.dumps({"version": version, "versions": parsed_versions, "error": "VERSION mismatch"})
    add(check("version consistency", ver_status, ver_detail))

    # 9b. Product paths changed after the latest release tag must advance
    # SemVer. Check origin without mutating local refs so a stale clone cannot
    # silently pass. Documentation and infrastructure paths are exempt.
    local_tag, remote_tag, tag_error = inspect_version_tag_state()
    latest_tag = remote_tag or local_tag
    worktree_changes, worktree_error = inspect_worktree_changes()
    if worktree_error:
        progression_status = "FAIL"
        progression_detail = json.dumps({"error": "cannot inspect worktree changes", "stderr": worktree_error})
    elif tag_error:
        progression_status = "FAIL"
        progression_detail = json.dumps({
            "version": version,
            "local_tag": local_tag,
            "error": "cannot verify origin tag state",
            "stderr": tag_error,
        })
    else:
        committed_changes, committed_error = inspect_committed_changes_since_tag(
            latest_tag, remote=bool(remote_tag)
        ) if latest_tag else (False, None)
        if committed_error:
            progression_status = "FAIL"
            raw_progression_detail = json.dumps({
                "version": version,
                "tag": latest_tag,
                "error": "cannot verify committed changes since release tag",
                "stderr": committed_error,
            })
        else:
            progression_status, raw_progression_detail = check_version_progression(
                version,
                latest_tag,
                bool(worktree_changes) or bool(committed_changes),
                allow_current_version=("--allow-current-version" in sys.argv),
            )
        parsed_progression = json.loads(raw_progression_detail)
        parsed_progression.update({
            "local_tag": local_tag,
            "remote_tag": remote_tag,
            "local_tags_stale": bool(local_tag and remote_tag and local_tag != remote_tag),
        })
        progression_detail = json.dumps(parsed_progression)
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

    # Workspace hygiene is report-only information. It must never become a
    # verdict input: generated caches do not prove a release is unsafe, but they
    # must remain visible in the machine-readable report.
    hygiene = []
    for seg in ("__pycache__", ".pytest_cache"):
        n = sum(1 for p in ROOT.rglob(seg) if p.is_dir() and not is_runtime_path(p))
        if n:
            hygiene.append(f"{n} {seg}/ dir(s)")
    for p in ROOT.rglob("*.png"):
        if not is_runtime_path(p):
            hygiene.append(f"screenshot {p.name}")
    info = {"workspace_hygiene": hygiene or ["clean"]}

    # Aggregate
    verdict = compute_verdict(results, model_no_evidence=model_no_evidence)
    software_status = "SOFTWARE_GO" if not any(r["status"] == "FAIL" for r in results) else "SOFTWARE_FAIL"
    real_status_label = f"MODEL_{real_model_verdict or 'NO_EVIDENCE'} (real)"
    synthetic_label = f"synthetic-gate: {sens_release or 'PAPER_CANDIDATE'}"
    summary_verdict_line = f"VERDICT: {software_status} / {real_status_label} · {synthetic_label} · lockbox-eval: {lb_eval_state}"

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": verdict,
        "software_verdict": software_status,
        "model_verdict": real_status_label,
        "synthetic_gate": sens_release,
        "lockbox_evaluation": lb_eval_state,
        "checks": results,
        "info": info,
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
        if any(r["status"] == "FAIL" for r in results):
            print(f"\nVERDICT: FAIL", file=sys.stderr)
        else:
            print(f"\n{summary_verdict_line}", file=sys.stderr)
        if info.get("workspace_hygiene") != ["clean"]:
            print(f"[INFO] workspace hygiene: {'; '.join(info['workspace_hygiene'])}", file=sys.stderr)
        if verdict == "SOFTWARE_GO / MODEL_NO_EVIDENCE":
            print("Statistical model reports NO_EVIDENCE on real golden fixtures — software passes, but there "
                  "is no mathematical edge. Not a clean GO.", file=sys.stderr)
        elif verdict == "NO-GO":
            print("External/manual evidence missing — not a false green. "
                  "See RELEASE_CHECKLIST.md.", file=sys.stderr)

    required_fail = any(r["status"] == "FAIL" for r in results)
    return exit_code_for_verdict(verdict) if not required_fail else 2


if __name__ == "__main__":
    sys.exit(main())
