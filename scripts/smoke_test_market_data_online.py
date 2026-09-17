#!/usr/bin/env python3
"""
Separate real online smoke test for Bitget public market and liquidity data.
Requirements:
- Small universe (BTCUSDT, ETHUSDT)
- Tests public endpoints: contracts, tickers, merge-depth
- Tests normalization, depth parsing, liquidity policy evaluation, and SQLite persistence
- Honest network error reporting (no artificial success)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.liquidity import LiquidityPolicy, POLICY_VERSION
from aura.data.market_updater import MarketDataUpdater
from aura.store.db import connect


def run_online_smoke(symbols: list[str] | None = None) -> dict:
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]

    report: dict = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "symbols": symbols,
        "policy_version": POLICY_VERSION,
        "contracts_fetched": 0,
        "tickers_fetched": 0,
        "depths": {},
        "assessments": {},
        "status": "UNKNOWN",
        "errors": [],
    }

    adapter = BitgetMarketAdapter(timeout=10.0, max_retries=2)
    policy = LiquidityPolicy()

    # 1. Test Contract Specs
    try:
        t0 = time.time()
        specs = adapter.fetch_contract_specs()
        dt = round(time.time() - t0, 3)
        if not specs:
            report["errors"].append("fetch_contract_specs returned 0 specs or invalid payload")
            report["status"] = "FAIL"
            return report
        report["contracts_fetched"] = len(specs)
        specs_by_symbol = {s.symbol: s for s in specs}
        for s in symbols:
            if s not in specs_by_symbol:
                report["errors"].append(f"Symbol {s} not found in public contract specs")
                report["status"] = "FAIL"
                return report
        print(f"[OK] {len(specs)} Contract Specs geladen in {dt}s. Zielsymbole {symbols} vorhanden.")
    except Exception as ex:
        report["errors"].append(f"Contract specs network error: {ex}")
        report["status"] = "NOT_RUN" if isinstance(ex, (ConnectionError, TimeoutError, OSError)) else "FAIL"
        return report

    # 2. Test Tickers
    try:
        t0 = time.time()
        tickers_raw, _, raw_sha = adapter.fetch_all_tickers()
        dt = round(time.time() - t0, 3)
        if not tickers_raw or tickers_raw.get("code") != "00000":
            report["errors"].append(f"fetch_all_tickers failed: {tickers_raw.get('msg') if tickers_raw else 'None'}")
            report["status"] = "FAIL"
            return report
        tickers = {t["symbol"]: t for t in tickers_raw.get("data", []) if t.get("symbol")}
        report["tickers_fetched"] = len(tickers)
        print(f"[OK] {len(tickers)} Tickers geladen in {dt}s.")
    except Exception as ex:
        report["errors"].append(f"Tickers network error: {ex}")
        report["status"] = "NOT_RUN" if isinstance(ex, (ConnectionError, TimeoutError, OSError)) else "FAIL"
        return report

    # 3. Test Orderbook Depth & Liquidity Policy in isolated DB
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = connect(tmp.name)
        updater = MarketDataUpdater(
            conn=conn,
            adapter=adapter,
            policy=policy,
            symbols=symbols,
        )

        updater.persist_contract_specs([specs_by_symbol[s] for s in symbols])

        for s in symbols:
            try:
                t0 = time.time()
                depth_raw, fetched_ms, sha = adapter.fetch_orderbook_depth(s, limit=50)
                dt = round(time.time() - t0, 3)
                if not depth_raw or depth_raw.get("code") != "00000":
                    msg = depth_raw.get("msg") if depth_raw else "None"
                    report["errors"].append(f"Depth for {s} failed: {msg}")
                    continue

                spread, bid_d, ask_d, best_bid, best_ask, ok = adapter.parse_depth_metrics(depth_raw)
                if not ok:
                    report["errors"].append(f"Depth metrics for {s} unparseable")
                    continue

                ticker = tickers.get(s, {})
                vol_str = str(ticker.get("usdtVolume") or ticker.get("quoteVolume") or "0")
                quote_vol = Decimal(vol_str) if vol_str else Decimal("0")
                event_ms = int(depth_raw.get("requestTime") or fetched_ms)

                assessment = policy.evaluate_metrics(
                    active=True,
                    spread_bps=spread,
                    bid_depth_notional=bid_d,
                    ask_depth_notional=ask_d,
                    quote_volume_24h=quote_vol,
                    event_time_ms=event_ms,
                    fetched_at_ms=fetched_ms,
                    decision_time_ms=int(time.time() * 1000),
                    book_complete=True,
                )

                updater.persist_universe_snapshot(
                    symbol=s,
                    assessment=assessment,
                    spread_bps=spread,
                    bid_depth=bid_d,
                    ask_depth=ask_d,
                    quote_vol=quote_vol,
                    event_ms=event_ms,
                    fetched_ms=fetched_ms,
                    raw_sha=sha,
                )

                report["depths"][s] = {
                    "latency_sec": dt,
                    "spread_bps": str(spread),
                    "bid_depth_notional": str(bid_d),
                    "ask_depth_notional": str(ask_d),
                    "best_bid": str(best_bid),
                    "best_ask": str(best_ask),
                    "quote_vol_24h": str(quote_vol),
                }
                report["assessments"][s] = {
                    "status": assessment.status,
                    "verified": assessment.verified,
                    "reasons": list(assessment.reasons),
                }
                print(
                    f"[OK] {s}: Spread={spread:.3f}bps, BidDepth=${bid_d:,.0f}, "
                    f"AskDepth=${ask_d:,.0f}, Status={assessment.status}, Verified={assessment.verified}"
                )
            except Exception as ex:
                report["errors"].append(f"Depth loop error for {s}: {ex}")

        # 4. Verify SQLite persistence integrity
        rows = conn.execute("SELECT symbol, active, liquidity_verified, status FROM universe").fetchall()
        persisted = {r["symbol"]: (r["active"], r["liquidity_verified"], r["status"]) for r in rows}
        if len(persisted) != len(symbols):
            report["errors"].append(f"Expected {len(symbols)} persisted rows, found {len(persisted)}")
        else:
            print(f"[OK] Alle {len(symbols)} Symbole erfolgreich in DB persistiert: {persisted}")

    if not report["errors"]:
        report["status"] = "PASS"
    else:
        report["status"] = "FAIL"

    return report


if __name__ == "__main__":
    rep = run_online_smoke()
    print("\n--- ONLINE SMOKE RESULT ---")
    print(json.dumps(rep, indent=2))
    sys.exit(0 if rep["status"] == "PASS" else 1)
