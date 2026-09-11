#!/usr/bin/env python3
"""
AURA — Automated Canonical Market Data & Universe Synchronizer.

Fetches and saves ALL active Bitget USDT-M Futures pairs with contract specs.
Golden-Master fixtures cannot and must not be generated via JavaScript engine.
They must be independently exported from TradingView/Pine Script.

Usage:
  python scripts/sync_market_data.py
  python scripts/sync_market_data.py --universe-only
  python scripts/sync_market_data.py --golden-only
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"


def fetch_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AURA/1.1.8"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_active_usdt_perpetual(contract: dict) -> bool:
    """Return whether a contract is an active Bitget USDT-M perpetual."""
    symbol = str(contract.get("symbol") or "").upper()
    quote_coin = str(contract.get("quoteCoin") or "").upper()
    status = str(contract.get("symbolStatus") or "").lower()
    delivery_time = str(contract.get("deliveryTime") or "").strip()
    return (
        quote_coin == "USDT"
        and symbol.endswith("USDT")
        and "_" not in symbol
        and str(contract.get("symbolType") or "perpetual").lower() == "perpetual"
        and status in {"normal", "online"}
        and delivery_time in {"", "0"}
    )


def normalize_usdt_futures_contracts(contracts: list[dict], tickers: dict[str, dict]) -> list[dict]:
    """Normalize the verified Bitget USDT-FUTURES contract response."""
    universe = []
    for contract in contracts:
        if not _is_active_usdt_perpetual(contract):
            continue
        symbol = str(contract["symbol"]).upper()
        ticker = tickers.get(symbol, {})
        universe.append({
            "symbol": symbol,
            "baseCoin": contract.get("baseCoin"),
            "quoteCoin": "USDT",
            "productType": "USDT-FUTURES",
            "contractType": str(contract.get("symbolType") or "perpetual").lower(),
            "symbolStatus": str(contract.get("symbolStatus") or "").lower(),
            "sizeMultiplier": float(contract.get("sizeMultiplier") or 1.0),
            "makerFeeRate": float(contract.get("makerFeeRate") or 0.0002),
            "takerFeeRate": float(contract.get("takerFeeRate") or 0.0006),
            "minTradeNum": float(contract.get("minTradeNum") or 1.0),
            "minTradeUSDT": float(contract.get("minTradeUSDT") or 5.0),
            "maxLever": int(contract.get("maxLever") or 50),
            "pricePlace": int(contract.get("pricePlace") or 2),
            "volumePlace": int(contract.get("volumePlace") or 2),
            "priceEndStep": float(contract.get("priceEndStep") or 0.01),
            "lastPrice": float(ticker.get("lastPr") or 0.0),
            "change24h": float(ticker.get("change24h") or 0.0),
            "usdtVolume": float(ticker.get("usdtVolume") or ticker.get("quoteVolume") or 0.0),
            "fundingRate": float(ticker.get("fundingRate") or 0.0),
            "holdingAmount": float(ticker.get("holdingAmount") or 0.0),
        })
    universe.sort(key=lambda row: row["usdtVolume"], reverse=True)
    return universe


def sync_universe() -> list[dict]:
    print("[1/3] Synchronisiere Bitget USDT-M Futures Universum …")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Tickers (Preise, Volumen, Funding, OI)
    t_url = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
    t_resp = fetch_json(t_url)
    if t_resp.get("code") != "00000":
        raise RuntimeError(f"Bitget Tickers Error: {t_resp.get('msg')}")
    tickers = {t["symbol"]: t for t in t_resp.get("data", []) if t.get("symbol")}

    # 2. Contracts (Spezifikationen, Multiplier, Limits, Status)
    c_url = "https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES"
    c_resp = fetch_json(c_url)
    if c_resp.get("code") != "00000":
        raise RuntimeError(f"Bitget Contracts Error: {c_resp.get('msg')}")
    contracts = c_resp.get("data", [])

    universe = normalize_usdt_futures_contracts(contracts, tickers)
    out_path = DATA_DIR / "bitget_usdt_futures_universe.json"
    out_path.write_text(json.dumps({
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_contracts": len(universe),
        "contracts": universe
    }, indent=2), encoding="utf-8")

    print(f"  -> {len(universe)} aktive Bitget USDT-M Futures Kontrakte synchronisiert.")
    print(f"  -> Gespeichert in: {out_path.relative_to(ROOT)}")
    return universe




def main():
    parser = argparse.ArgumentParser(description="AURA Market Data Synchronizer")
    parser.add_argument("--universe-only", action="store_true", help="Sync only Bitget USDT-M contracts universe (default behavior)")
    parser.add_argument("--golden-only", action="store_true", help="Former golden sync path (disabled: requires manual TradingView export)")
    args = parser.parse_args()

    print("=== AURA CANONICAL DATA SYNCHRONIZER ===")
    if args.golden_only:
        print(
            "ERROR: Golden-Master fixtures cannot be automatically generated with JavaScript.\n"
            "Golden-Master fixtures must be independently exported from TradingView/Pine Script\n"
            "or an independent reference source into tests/fixtures/golden/.\n"
            "Existing Golden Master CSV files were not modified.",
            file=sys.stderr
        )
        return 1

    sync_universe()
    return 0

if __name__ == "__main__":
    sys.exit(main())
