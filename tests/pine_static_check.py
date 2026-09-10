#!/usr/bin/env python3
"""
Static Pine v6 sanity check — the minimum gate before a user-controlled TradingView
compile (there is no local Pine compiler).

Checks (per trading-signal-engine-audit skill):
  1. Delimiter balance  () [] {}  after stripping string literals and comments.
  2. `var` inside any function body — HARD COMPILE ERROR in Pine v6 (also f_mtf()).
  3. `ta.*` indented anywhere EXCEPT the f_mtf() request.security context — the
     lazy-evaluation trap (never computed when nested in if/for/other functions).
  4. request.security must use lookahead=barmerge.lookahead_off.

Usage: python3 tests/pine_static_check.py [path-to.pine]
Exit: 0 = all static gates pass. This is NOT a substitute for a real compile.
"""
import re
import sys

PAIRS = {"(": ")", "[": "]", "{": "}"}
MTF_FN = "f_mtf"
FN_RE = re.compile(r"^(f_\w+)\s*\([^)]*\)\s*=>")


def strip_literals_and_comments(src: str) -> str:
    out = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            out.append("\n")
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            out.append(" ")
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            while i < n:
                if src[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "Symbiose_Signal_System_v1.pine"
    src = open(path, encoding="utf-8").read()
    clean = strip_literals_and_comments(src)
    lines = src.splitlines()

    problems = []

    # 1. delimiter balance
    stack = []
    for idx, ch in enumerate(clean):
        if ch in PAIRS:
            stack.append((PAIRS[ch], idx))
        elif ch in ")]}":
            if not stack or stack[-1][0] != ch:
                problems.append(f"delimiter mismatch at clean-char {idx}: unexpected {ch!r}")
                break
            stack.pop()
    if stack:
        problems.append(f"delimiter mismatch: unclosed {[c for c, _ in stack][-5:]}")

    # 2/3. track enclosing function; f_mtf is the only legal indented ta.* context
    current_fn = None
    for lineno, line in enumerate(lines, 1):
        indented = bool(line[: len(line) - len(line.lstrip())])
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        # function definition at top level (possibly with a trailing body expression)
        if not indented:
            m = FN_RE.match(stripped)
            current_fn = m.group(1) if m else None
            # a one-liner body `f_clamp(...) => expr` never contains `var`/`ta.` indented
            continue

        # indented line: inside current_fn body, or a global if/for block
        if re.match(r"^var\s+", stripped) and current_fn:
            problems.append(
                f"line {lineno}: `var` inside function '{current_fn}' — HARD COMPILE ERROR "
                f"in Pine v6: {stripped[:70]}"
            )
        if re.search(r"\bta\.", stripped) and current_fn != MTF_FN:
            where = f"function '{current_fn}'" if current_fn else "global if/for block"
            problems.append(
                f"line {lineno}: indented `ta.*` in {where} (outside f_mtf) — "
                f"lazy-evaluation trap: {stripped[:70]}"
            )

    # 4. request.security lookahead
    sec_calls = re.findall(r"request\.security\([^\n]*\)", src)
    for call in sec_calls:
        if "lookahead=barmerge.lookahead_off" not in call:
            problems.append(f"request.security without lookahead_off: {call[:80]}")

    # 5. Golden-Master plot titles must match the harness FIELD_MAP exactly
    #    (tests/compare_pine_js_golden.js maps on the CSV column names). A renamed
    #    plot would break the TradingView CSV comparison with a "missing column".
    REQUIRED_GM_TITLES = [
        "GM Trend Score",
        "GM Momentum Score",
        "GM Volume Score",
        "GM Structure Score",
        "GM Core Score",
    ]
    for title in REQUIRED_GM_TITLES:
        if re.search(rf"plot\([^,\n]+\s*,\s*\"{re.escape(title)}\"", src) is None:
            problems.append(f"missing Golden-Master plot title: \"{title}\"")

    # 6. FVG zones must be tracked independently, not only through the latest box.
    for required in ("fvgTops", "fvgBots", "fvgDirs", "fvgActives", "for zi = array.size(fvgBoxes) - 1"):
        if required not in src:
            problems.append(f"missing zonal FVG lifecycle marker: {required}")

    # 7. Drawing storage must remain bounded without terminating indicator
    # execution. Mitigated zones are preferred for eviction; if every retained
    # zone is active, the oldest visual zone is evicted as a deterministic
    # fallback. The latest scalar FVG state used by scoring remains untouched.
    fvg_block = src[src.find("// --- Fair Value Gaps"):src.find("// --- Liquiditäts-Pools")]
    if re.search(r"array\.size\(fvgBoxes\)\s*>\s*30[\s\S]{0,300}array\.shift\(fvgBoxes\)", fvg_block):
        problems.append("FVG capacity still blindly shifts the oldest box")
    required_capacity_markers = (
        "MAX_FVG_ZONES = 30",
        "array.size(fvgBoxes) > MAX_FVG_ZONES",
        "if na(removeIdx)",
        "removeIdx := 0",
        "box.delete(array.get(fvgBoxes, removeIdx))",
        "array.remove(fvgActives, removeIdx)",
    )
    for marker in required_capacity_markers:
        if marker not in src:
            problems.append(f"FVG capacity lacks bounded-eviction marker: {marker}")
    if "runtime.error" in fvg_block:
        problems.append("FVG capacity exhaustion still aborts indicator execution")

    if problems:
        print(f"PINE STATIC CHECK: {len(problems)} problem(s) in {path}")
        for p in problems:
            print("  - " + p)
        return 1

    print(f"PINE STATIC CHECK: OK ({path}: {len(lines)} lines, "
          f"{len(sec_calls)} request.security calls, {len(REQUIRED_GM_TITLES)} GM plot titles, "
          f"delimiters balanced)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
