#!/usr/bin/env python3
"""AURA PreReg Assistant — Interactive & CLI Generator for Hypothesis-PreReg entries.

Produces a validated JSON entry file for `scripts/append_ledger.py --prereg`.
Enforces the Two-Step Preregistration Protocol:
  Step 1 (this tool): Define hypothesis, compute deterministic setup_id & params_sha256,
                      validate schema via `hypothesis_check.validate_prereg`, write entry JSON.
  Step 2 (owner/researcher): Explicitly review and append to the Ledger via
                      `python3 scripts/append_ledger.py --prereg --entry-file <path>`.

Evidence Guardrail:
  This script does NOT write to the ledger directly, preventing accidental or automated
  unverified registrations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

# Ensure scripts directory is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from hypothesis_check import validate_prereg, PreregValidationError
except ImportError as err:
    sys.stderr.write(f"ERROR: Cannot import validate_prereg from hypothesis_check: {err}\n")
    sys.exit(1)


def compute_setup_id(symbol: str, tf: str, setup_class: str) -> str:
    """Compute deterministic setup identifier.

    Format: <SYMBOL>_<TF>_<SETUP_CLASS> (normalized: upper, clean characters).
    """
    sym = re.sub(r"[^A-Za-z0-9]", "", symbol).upper()
    timeframe = tf.strip().lower()
    s_class = re.sub(r"[^A-Za-z0-9_]", "_", setup_class).upper().strip("_")
    return f"{sym}_{timeframe}_{s_class}"


def compute_params_sha256(params: dict | list | str | int | float | bool | None) -> str:
    """Compute canonical SHA-256 hash over JSON parameters."""
    canonical_json = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def build_prereg_entry(
    *,
    symbol: str,
    tf: str,
    setup_class: str,
    regime_context: str,
    hypothesis: str,
    params: dict | list,
    n_min: int,
    edge_min: float,
    dsr_min: float,
    bars: int | None = None,
    until_date: str | None = None,
    frozen_at: str | None = None,
    author: str | None = None,
    lockbox_ref: str | None = None,
    prereg_commit: str | None = None,
) -> dict:
    """Construct and validate a full Hypothesis-PreReg entry dictionary."""
    setup_id = compute_setup_id(symbol, tf, setup_class)
    params_sha = compute_params_sha256(params)

    if frozen_at is None:
        frozen_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    entry: dict = {
        "setup_id": setup_id,
        "symbol": symbol.strip().upper(),
        "tf": tf.strip().lower(),
        "regime_context": regime_context.strip(),
        "hypothesis": hypothesis.strip(),
        "params_sha256": params_sha,
        "parameters": params,
        "acceptance": {
            "n_min": int(n_min),
            "edge_min": float(edge_min),
            "dsr_min": float(dsr_min),
        },
        "status": "PREREGISTERED",
        "frozen_at": frozen_at,
    }

    if bars is not None:
        entry["bars"] = int(bars)
    elif until_date is not None:
        entry["until_date"] = str(until_date).strip()
    else:
        raise ValueError("Must provide either 'bars' or 'until_date' as evaluation horizon.")

    if author:
        entry["author"] = str(author).strip()
    if lockbox_ref:
        entry["lockbox_ref"] = str(lockbox_ref).strip()
    if prereg_commit:
        entry["prereg_commit"] = str(prereg_commit).strip()

    # Validate against canonical prereg schema
    validate_prereg(entry)
    return entry


def interactive_wizard() -> dict:
    """Run interactive CLI wizard prompting for all required hypothesis fields."""
    print("==================================================================")
    print("  AURA Hypothesis Pre-Registration Assistant (Two-Step Generator)")
    print("==================================================================")
    print("Erstellt einen validierten Hypothesis-PreReg-Eintrag vor Backtest-Start.")
    print("Hinweis: Schreibt nicht in den Ledger, sondern erzeugt eine Entry-Datei.\n")

    symbol = input("1. Symbol (z.B. BTCUSDT, ETHUSDT): ").strip()
    tf = input("2. Timeframe (z.B. 4h, 1h, 15m): ").strip()
    setup_class = input("3. Setup-Klasse (z.B. PB_MOM, BREAKOUT_VOL, MEAN_REV): ").strip()
    regime_context = input("4. Regime-Kontext (z.B. TRENDING_BULL_ADX_GT25, VOLATILITY_EXPANSION): ").strip()
    hypothesis = input("5. Falsifizierbare Hypothese (Klartext): ").strip()

    print("\n--- Parameter-Spezifikation (JSON) ---")
    params_input = input("6. Parameter-JSON (oder Pfad zu .json Datei, leer = '{}'): ").strip()
    if params_input.endswith(".json") and os.path.exists(params_input):
        with open(params_input, "r", encoding="utf-8") as f:
            params = json.load(f)
    elif params_input:
        params = json.loads(params_input)
    else:
        params = {}

    print("\n--- Acceptance Criteria (Falsifikations-Schwellen) ---")
    n_min_str = input("7. n_min (Minimale Trade-Anzahl, z.B. 30): ").strip()
    n_min = int(n_min_str or 30)
    edge_min_str = input("8. edge_min (Minimaler R-Erwartungswert pro Trade, z.B. 0.15): ").strip()
    edge_min = float(edge_min_str or 0.15)
    dsr_min_str = input("9. dsr_min (Deflated Sharpe Ratio Min, z.B. 0.10): ").strip()
    dsr_min = float(dsr_min_str or 0.10)

    print("\n--- Evaluierungs-Horizont ---")
    horizon_type = input("10. Horizont-Typ ([b]ars oder [d]ate) [b]: ").strip().lower()
    bars = None
    until_date = None
    if horizon_type in ("d", "date"):
        until_date = input("    until_date (ISO-8601, z.B. 2026-12-31T23:59:59Z): ").strip()
    else:
        bars_str = input("    bars (z.B. 500, 1000): ").strip()
        bars = int(bars_str or 500)

    author = input("11. Autor / Forscher (optional, z.B. ivo): ").strip() or None
    lockbox_ref = input("12. Lockbox-Referenz (optional, z.B. LB-2026-Q1-HOLD): ").strip() or None

    return build_prereg_entry(
        symbol=symbol,
        tf=tf,
        setup_class=setup_class,
        regime_context=regime_context,
        hypothesis=hypothesis,
        params=params,
        n_min=n_min,
        edge_min=edge_min,
        dsr_min=dsr_min,
        bars=bars,
        until_date=until_date,
        author=author,
        lockbox_ref=lockbox_ref,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AURA Hypothesis Pre-Registration Generator (Two-Step Prereg Wizard)"
    )
    parser.add_argument("--symbol", help="Trading pair (e.g. BTCUSDT)")
    parser.add_argument("--tf", help="Timeframe (e.g. 4h, 1h, 15m)")
    parser.add_argument("--setup-class", help="Setup classification (e.g. PB_MOM)")
    parser.add_argument("--regime", help="Market regime context")
    parser.add_argument("--hypothesis", help="Hypothesis statement")
    parser.add_argument("--params-json", help="Inline JSON string of strategy parameters")
    parser.add_argument("--params-file", help="Path to JSON file containing strategy parameters")
    parser.add_argument("--n-min", type=int, default=30, help="Minimum sample size (default: 30)")
    parser.add_argument("--edge-min", type=float, default=0.15, help="Minimum R-edge threshold (default: 0.15)")
    parser.add_argument("--dsr-min", type=float, default=0.10, help="Minimum DSR threshold (default: 0.10)")
    parser.add_argument("--bars", type=int, help="Horizon in bars (mutually exclusive with --until-date)")
    parser.add_argument("--until-date", help="Horizon until ISO-8601 date (e.g. 2026-12-31T23:59:59Z)")
    parser.add_argument("--author", help="Author / Researcher name")
    parser.add_argument("--lockbox-ref", help="Optional Lockbox holdout reference")
    parser.add_argument("--out", default="prereg_entry.json", help="Output file path (default: prereg_entry.json)")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive batch mode")

    args = parser.parse_args()

    try:
        if args.non_interactive or (args.symbol and args.hypothesis):
            if not args.symbol or not args.tf or not args.setup_class or not args.regime or not args.hypothesis:
                sys.stderr.write(
                    "ERROR: In non-interactive mode, --symbol, --tf, --setup-class, --regime, and --hypothesis are required.\n"
                )
                return 1

            if args.bars is None and args.until_date is None:
                args.bars = 500  # Default horizon

            if args.params_file:
                with open(args.params_file, "r", encoding="utf-8") as f:
                    params = json.load(f)
            elif args.params_json:
                params = json.loads(args.params_json)
            else:
                params = {}

            entry = build_prereg_entry(
                symbol=args.symbol,
                tf=args.tf,
                setup_class=args.setup_class,
                regime_context=args.regime,
                hypothesis=args.hypothesis,
                params=params,
                n_min=args.n_min,
                edge_min=args.edge_min,
                dsr_min=args.dsr_min,
                bars=args.bars,
                until_date=args.until_date,
                author=args.author,
                lockbox_ref=args.lockbox_ref,
            )
        else:
            entry = interactive_wizard()

        # Write output file
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)
            f.write("\n")

        # Display preview & confirmation
        print("\n==================================================================")
        print("  PreReg-Eintrag erfolgreich validiert und geschrieben!")
        print("==================================================================")
        print(f"Datei:         {out_path}")
        print(f"Setup-ID:      {entry['setup_id']}")
        print(f"Params-SHA256: {entry['params_sha256']}")
        print(f"Status:        {entry['status']}")
        print(f"Kriterien:     n_min={entry['acceptance']['n_min']}, edge_min={entry['acceptance']['edge_min']}, dsr_min={entry['acceptance']['dsr_min']}")
        horizon_str = f"{entry['bars']} Bars" if "bars" in entry else str(entry.get("until_date"))
        print(f"Horizont:      {horizon_str}")
        print("------------------------------------------------------------------")
        print("Zwei-Schritt-Protokoll: Der Ledger wurde NICHT verändert.")
        print("Um diesen Eintrag bewusst in den Ledger aufzunehmen, führe aus:")
        print(f"\n  python3 scripts/append_ledger.py --prereg --entry-file {out_path}\n")
        return 0

    except (PreregValidationError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"\nFEHLER bei der PreReg-Generierung: {exc}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\nAbgebrochen durch Benutzer.\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
