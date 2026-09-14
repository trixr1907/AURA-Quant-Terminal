#!/usr/bin/env python3
"""Data Foundation Audit Engine for AURA Quant Terminal.

Audits candle datasets for completeness, temporal consistency, anomalies,
data provenance, and Walk-Forward (WF) suitability across local CSV fixtures
and public Bitget market endpoints.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"

REAL_SOURCE_KEYWORDS = {
    "tradingview/pine",
    "tradingview",
    "pine script",
    "tradingview pine",
    "independent_reference",
    "independent reference",
    "bitget",
    "bitget futures",
    "binance",
    "real",
    "live",
}

SYNTHETIC_SOURCE_KEYWORDS = {
    "synthetic",
    "synthetic_data",
    "mock",
    "simulated",
    "generated",
}

TIMEFRAME_STEP_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


def parse_timestamp_ms(val: Any) -> int | None:
    """Normalize numeric seconds/ms or ISO strings into integer epoch milliseconds."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    try:
        val_float = float(val_str)
        if val_float < 10_000_000_000:
            return int(val_float * 1000)
        return int(val_float)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def format_iso_utc(ts_ms: int | None) -> str | None:
    """Format epoch milliseconds to ISO 8601 UTC string."""
    if ts_ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def fetch_json(url: str, timeout: int = 15) -> dict:
    """Perform a public HTTPS GET request returning parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AURA-DataFoundationAudit/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_symbol_and_tf_from_filename(filename: str) -> tuple[str | None, str | None]:
    """Extract symbol and timeframe from filenames like BTCUSDT_1h.csv."""
    stem = Path(filename).stem
    m = re.match(r"^([A-Za-z0-9]+)_([0-9]+[mhdMHDwW])$", stem)
    if m:
        return m.group(1).upper(), m.group(2).lower()
    return None, None


def classify_provenance(
    explicit_val: str | None = None,
    metadata_source: str | None = None,
    is_live_bitget: bool = False,
) -> str:
    """Strictly classify provenance into 'real', 'synthetic', or 'unknown'.

    Never guesses from heuristics. Only explicit metadata or columns are used.
    """
    if is_live_bitget:
        return "real"

    for candidate in (explicit_val, metadata_source):
        if not candidate or not isinstance(candidate, str):
            continue
        cleaned = candidate.strip().lower()
        if cleaned in REAL_SOURCE_KEYWORDS or any(kw in cleaned for kw in REAL_SOURCE_KEYWORDS):
            return "real"
        if cleaned in SYNTHETIC_SOURCE_KEYWORDS or any(kw in cleaned for kw in SYNTHETIC_SOURCE_KEYWORDS):
            return "synthetic"

    return "unknown"


def audit_candle_series(
    candles: list[dict[str, Any]],
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    filename: str = "<in-memory>",
    sha256: str | None = None,
    provenance: str = "unknown",
    min_wf_bars: int = 1000,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Audit a list of candle dictionaries with keys t, o, h, l, c, v (and optional metadata)."""
    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    total_candles = len(candles)

    if total_candles == 0:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "filename": filename,
            "sha256": sha256,
            "total_candles": 0,
            "closed_candles": 0,
            "start_iso": None,
            "end_iso": None,
            "start_ts_ms": None,
            "end_ts_ms": None,
            "span_days": 0.0,
            "gaps": 0,
            "duplicates": 0,
            "null_or_zero_candles": 0,
            "outliers": 0,
            "provenance": provenance,
            "wf_eligible": False,
            "min_wf_bars": min_wf_bars,
            "errors": ["No candle records found"],
        }

    seen_timestamps: set[int] = set()
    duplicate_count = 0
    null_or_zero_count = 0
    outlier_count = 0
    timestamps: list[int] = []
    closed_candles = 0

    tf_key = (timeframe or "").lower()
    expected_step_ms = TIMEFRAME_STEP_MS.get(tf_key)

    detected_prov_column: str | None = None

    for c in candles:
        ts = parse_timestamp_ms(c.get("t"))
        if ts is None:
            null_or_zero_count += 1
            continue

        if ts in seen_timestamps:
            duplicate_count += 1
        seen_timestamps.add(ts)
        timestamps.append(ts)

        # Check provenance from row if present
        if "provenance" in c and c["provenance"]:
            detected_prov_column = str(c["provenance"])

        # Check OHLCV validity
        try:
            o = float(c.get("o", 0))
            h = float(c.get("h", 0))
            l = float(c.get("l", 0))
            cl = float(c.get("c", 0))
            v = float(c.get("v", 0)) if c.get("v") is not None else 0.0
        except (ValueError, TypeError):
            null_or_zero_count += 1
            continue

        # Null or zero prices / negative volume
        if o <= 0 or h <= 0 or l <= 0 or cl <= 0 or v < 0:
            null_or_zero_count += 1

        # Outlier checks (geometric violations)
        if h < l or o > h or o < l or cl > h or cl < l:
            outlier_count += 1

    timestamps.sort()
    start_ts = timestamps[0] if timestamps else None
    end_ts = timestamps[-1] if timestamps else None
    span_days = ((end_ts - start_ts) / 86_400_000) if start_ts is not None and end_ts is not None else 0.0

    # Determine step if not explicitly provided
    if not expected_step_ms and len(timestamps) >= 3:
        diffs = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1) if timestamps[i + 1] > timestamps[i]]
        if diffs:
            expected_step_ms = int(statistics.median(diffs))

    # Gap detection
    gap_count = 0
    if expected_step_ms and expected_step_ms > 0 and len(timestamps) > 1:
        threshold = expected_step_ms * 1.5
        for i in range(len(timestamps) - 1):
            delta = timestamps[i + 1] - timestamps[i]
            if delta > threshold:
                gap_count += 1

    # Closed candle calculation
    step = expected_step_ms or 3_600_000
    for ts in timestamps:
        if ts + step <= current_ms:
            closed_candles += 1
        elif end_ts and end_ts < current_ms:
            # Historical dataset entirely before current time
            closed_candles += 1

    if detected_prov_column and provenance == "unknown":
        provenance = classify_provenance(explicit_val=detected_prov_column)

    wf_eligible = (
        total_candles >= min_wf_bars
        and duplicate_count == 0
        and outlier_count == 0
        and null_or_zero_count == 0
        and gap_count <= 2  # tolerate max 2 structural boundary adjustments if any
    )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "filename": filename,
        "sha256": sha256,
        "total_candles": total_candles,
        "closed_candles": closed_candles,
        "start_iso": format_iso_utc(start_ts),
        "end_iso": format_iso_utc(end_ts),
        "start_ts_ms": start_ts,
        "end_ts_ms": end_ts,
        "span_days": round(span_days, 2),
        "gaps": gap_count,
        "duplicates": duplicate_count,
        "null_or_zero_candles": null_or_zero_count,
        "outliers": outlier_count,
        "provenance": provenance,
        "wf_eligible": wf_eligible,
        "min_wf_bars": min_wf_bars,
    }


def audit_csv_file(
    file_path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    provenance_override: str | None = None,
    min_wf_bars: int = 1000,
) -> dict[str, Any]:
    """Audit a local CSV candle file."""
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if metadata is None:
        prov_file = path.parent / "provenance.json"
        if prov_file.exists():
            try:
                prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
                if isinstance(prov_data, dict):
                    files_dict = prov_data.get("files")
                    if isinstance(files_dict, dict) and path.name in files_dict:
                        metadata = files_dict[path.name]
                    elif path.name in prov_data and isinstance(prov_data[path.name], dict):
                        metadata = prov_data[path.name]
            except Exception:
                pass

    sha256 = compute_file_sha256(path)
    fn_symbol, fn_tf = parse_symbol_and_tf_from_filename(path.name)

    meta = metadata or {}
    symbol = meta.get("symbol") or fn_symbol or path.stem
    timeframe = meta.get("timeframe") or fn_tf or "unknown"
    meta_source = meta.get("source")

    prov = provenance_override or classify_provenance(metadata_source=meta_source)

    candles: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        headers_raw = next(reader, [])
        headers = [h.strip().lower() for h in headers_raw]

        t_idx = -1
        for col in ("timestamp", "time", "date", "datetime", "ts"):
            if col in headers:
                t_idx = headers.index(col)
                break

        o_idx = headers.index("open") if "open" in headers else -1
        h_idx = headers.index("high") if "high" in headers else -1
        l_idx = headers.index("low") if "low" in headers else -1
        c_idx = headers.index("close") if "close" in headers else -1
        v_idx = headers.index("volume") if "volume" in headers else -1
        prov_idx = headers.index("provenance") if "provenance" in headers else -1

        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue

            entry: dict[str, Any] = {}
            if t_idx >= 0 and len(row) > t_idx:
                entry["t"] = row[t_idx]
            if o_idx >= 0 and len(row) > o_idx:
                entry["o"] = row[o_idx]
            if h_idx >= 0 and len(row) > h_idx:
                entry["h"] = row[h_idx]
            if l_idx >= 0 and len(row) > l_idx:
                entry["l"] = row[l_idx]
            if c_idx >= 0 and len(row) > c_idx:
                entry["c"] = row[c_idx]
            if v_idx >= 0 and len(row) > v_idx:
                entry["v"] = row[v_idx]
            if prov_idx >= 0 and len(row) > prov_idx:
                entry["provenance"] = row[prov_idx]

            candles.append(entry)

    return audit_candle_series(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        filename=path.name,
        sha256=sha256,
        provenance=prov,
        min_wf_bars=min_wf_bars,
    )


def audit_directory(
    dir_path: Path,
    *,
    min_wf_bars: int = 1000,
) -> dict[str, Any]:
    """Audit all CSV files in a directory, checking provenance.json metadata if available."""
    target_dir = Path(dir_path).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return {
            "ok": False,
            "error": f"Directory not found: {target_dir}",
            "fixtures": [],
        }

    prov_map: dict[str, Any] = {}
    prov_file = target_dir / "provenance.json"
    if prov_file.exists():
        try:
            prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
            if isinstance(prov_data, dict):
                # Check for "files" or top-level entries
                files_dict = prov_data.get("files")
                if isinstance(files_dict, dict):
                    prov_map = files_dict
                else:
                    for k, v in prov_data.items():
                        if isinstance(v, dict):
                            prov_map[k] = v
        except Exception:
            pass

    csv_files = sorted(target_dir.glob("*.csv"))
    fixtures: list[dict[str, Any]] = []

    for csv_file in csv_files:
        meta = prov_map.get(csv_file.name)
        res = audit_csv_file(csv_file, metadata=meta, min_wf_bars=min_wf_bars)
        fixtures.append(res)

    total_candles = sum(f["total_candles"] for f in fixtures)
    prov_summary = {
        "real": sum(1 for f in fixtures if f["provenance"] == "real"),
        "synthetic": sum(1 for f in fixtures if f["provenance"] == "synthetic"),
        "unknown": sum(1 for f in fixtures if f["provenance"] == "unknown"),
    }
    wf_eligible_count = sum(1 for f in fixtures if f["wf_eligible"])

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_files": len(fixtures),
        "total_candles": total_candles,
        "provenance_summary": prov_summary,
        "wf_eligible_count": wf_eligible_count,
        "min_wf_bars_threshold": min_wf_bars,
        "fixtures": fixtures,
    }


def audit_bitget(
    symbol: str = "BTCUSDT",
    timeframe: str = "1H",
    limit: int = 300,
    product_type: str = "USDT-FUTURES",
    min_wf_bars: int = 300,
) -> dict[str, Any]:
    """Audit candles fetched directly from Bitget public mix market candle API."""
    tf_clean = timeframe.upper()
    gran_map = {"1M": "1m", "5M": "5m", "15M": "15m", "30M": "30m", "1H": "1H", "4H": "4H", "1D": "1D", "1W": "1W"}
    granularity = gran_map.get(tf_clean, tf_clean)

    url = (
        f"https://api.bitget.com/api/v2/mix/market/candles"
        f"?symbol={symbol}&productType={product_type}&granularity={granularity}&limit={limit}"
    )

    resp = fetch_json(url)
    if not isinstance(resp, dict) or resp.get("code") != "00000" or not isinstance(resp.get("data"), list):
        raise ValueError(f"Bitget market request failed: {resp.get('msg', 'unknown error')}")

    raw_data = resp["data"]
    candles: list[dict[str, Any]] = []
    for row in raw_data:
        if isinstance(row, list) and len(row) >= 6:
            candles.append({
                "t": row[0],
                "o": row[1],
                "h": row[2],
                "l": row[3],
                "c": row[4],
                "v": row[5],
            })

    return audit_candle_series(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        filename=f"bitget://{symbol}_{timeframe}",
        provenance="real",
        min_wf_bars=min_wf_bars,
    )


def format_table(report: dict[str, Any]) -> str:
    """Format audit report dictionary into an aligned text table."""
    lines: list[str] = []
    lines.append("=" * 120)
    lines.append(" AURA QUANT TERMINAL — DATA FOUNDATION AUDIT REPORT")
    lines.append(f" Generated: {report.get('generated_at', 'N/A')} | Threshold WF n >= {report.get('min_wf_bars_threshold', 'N/A')}")
    lines.append("=" * 120)

    headers = ["Symbol", "TF", "Total", "Closed", "Start (UTC)", "End (UTC)", "Gaps", "Dup", "Null/0", "Outl", "Provenance", "WF (n>=N)"]
    widths = [10, 5, 8, 8, 20, 20, 6, 5, 7, 6, 12, 11]

    row_fmt = " ".join([f"{{:<{w}}}" for w in widths])
    lines.append(row_fmt.format(*headers))
    lines.append("-" * 120)

    fixtures = report.get("fixtures", [])
    if not fixtures and "symbol" in report:
        fixtures = [report]

    for f in fixtures:
        sym = str(f.get("symbol") or f.get("filename") or "-")
        tf = str(f.get("timeframe") or "-")
        tot = str(f.get("total_candles", 0))
        cls = str(f.get("closed_candles", 0))
        st = str(f.get("start_iso") or "-")
        en = str(f.get("end_iso") or "-")
        gaps = str(f.get("gaps", 0))
        dup = str(f.get("duplicates", 0))
        n0 = str(f.get("null_or_zero_candles", 0))
        outl = str(f.get("outliers", 0))
        prov = str(f.get("provenance", "unknown")).upper()
        wf = "YES" if f.get("wf_eligible") else "NO"

        lines.append(row_fmt.format(sym, tf, tot, cls, st, en, gaps, dup, n0, outl, prov, wf))

    lines.append("-" * 120)
    summary = report.get("provenance_summary", {})
    lines.append(
        f" SUMMARY: Total Files: {report.get('total_files', len(fixtures))} | "
        f"Total Candles: {report.get('total_candles', sum(f.get('total_candles', 0) for f in fixtures))} | "
        f"Real: {summary.get('real', 0)} | Synthetic: {summary.get('synthetic', 0)} | Unknown: {summary.get('unknown', 0)} | "
        f"WF Eligible: {report.get('wf_eligible_count', sum(1 for f in fixtures if f.get('wf_eligible')))}"
    )
    lines.append("=" * 120)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA Data Foundation Audit")
    parser.add_argument("--dir", type=Path, default=DEFAULT_GOLDEN_DIR, help="Directory containing CSV candle files")
    parser.add_argument("--file", type=Path, default=None, help="Single CSV candle file to audit")
    parser.add_argument("--bitget", action="store_true", help="Audit via live Bitget mix market candle fetch")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Symbol for Bitget fetch (default: BTCUSDT)")
    parser.add_argument("--timeframe", "--granularity", type=str, default="1H", help="Timeframe (e.g. 1H, 4H, 15m, 1D)")
    parser.add_argument("--limit", type=int, default=300, help="Candle limit for Bitget fetch (default: 300)")
    parser.add_argument("--min-wf-bars", type=int, default=1000, help="Minimum bars required for Walk-Forward eligibility (default: 1000)")
    parser.add_argument("--json", action="store_true", help="Output JSON directly to stdout")
    parser.add_argument("--json-out", type=Path, default=None, help="Write JSON report to specified file path")
    parser.add_argument("--strict", action="store_true", help="Fail with exit code 1 if any fixture fails integrity or WF suitability")

    args = parser.parse_args()

    if args.bitget:
        try:
            res = audit_bitget(
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit=args.limit,
                min_wf_bars=args.min_wf_bars,
            )
            report = {
                "ok": True,
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_files": 1,
                "total_candles": res.get("total_candles", 0),
                "provenance_summary": {"real": 1, "synthetic": 0, "unknown": 0},
                "wf_eligible_count": 1 if res.get("wf_eligible") else 0,
                "min_wf_bars_threshold": args.min_wf_bars,
                "fixtures": [res],
            }
        except Exception as e:
            sys.stderr.write(f"Bitget audit failed: {e}\n")
            return 1
    elif args.file:
        try:
            res = audit_csv_file(args.file, min_wf_bars=args.min_wf_bars)
            report = {
                "ok": True,
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_files": 1,
                "total_candles": res.get("total_candles", 0),
                "provenance_summary": {
                    "real": 1 if res.get("provenance") == "real" else 0,
                    "synthetic": 1 if res.get("provenance") == "synthetic" else 0,
                    "unknown": 1 if res.get("provenance") == "unknown" else 0,
                },
                "wf_eligible_count": 1 if res.get("wf_eligible") else 0,
                "min_wf_bars_threshold": args.min_wf_bars,
                "fixtures": [res],
            }
        except Exception as e:
            sys.stderr.write(f"File audit failed: {e}\n")
            return 1
    else:
        report = audit_directory(args.dir, min_wf_bars=args.min_wf_bars)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_table(report))

    if args.strict:
        for f in report.get("fixtures", []):
            if not f.get("wf_eligible"):
                return 1

    return 0 if report.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
