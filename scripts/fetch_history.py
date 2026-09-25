#!/usr/bin/env python
"""Seed the daily bar cache for a list of symbols.

Usage:
    # Use pre-built universe (default):
    python scripts/fetch_history.py

    # Override with an explicit symbol list:
    python scripts/fetch_history.py --symbols SPY,AAPL,MSFT,NVDA,AMZN --days 60

    # Use a custom universe file:
    python scripts/fetch_history.py --universe my_universe.csv
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from scanner.data.alpaca import AlpacaFeed
from scanner.universe import load_universe

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

_DEFAULT_UNIVERSE = Path("data/universe.csv")
_FALLBACK_SYMBOLS = ["SPY", "AAPL", "MSFT", "NVDA", "AMZN"]
DEFAULT_CACHE = Path("data/daily_split")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the daily history cache from Alpaca")
    sym_group = parser.add_mutually_exclusive_group()
    sym_group.add_argument(
        "--symbols",
        help="Comma-separated symbol list (overrides universe file)",
    )
    sym_group.add_argument(
        "--universe",
        help=f"Universe CSV path (default: {_DEFAULT_UNIVERSE})",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Calendar days of history to fetch (default: 60)",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE),
        help=f"Parquet cache directory (default: {DEFAULT_CACHE})",
    )
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.universe:
        try:
            symbols = load_universe(args.universe)
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Loaded {len(symbols)} symbols from {args.universe}")
    elif _DEFAULT_UNIVERSE.exists():
        symbols = load_universe(_DEFAULT_UNIVERSE)
        print(f"Loaded {len(symbols)} symbols from {_DEFAULT_UNIVERSE}")
    else:
        symbols = _FALLBACK_SYMBOLS
        print(f"No universe file found — using default symbols: {', '.join(symbols)}")
    cache_dir = Path(args.cache_dir)
    end = date.today() - timedelta(days=1)   # most recent completed session
    start = end - timedelta(days=args.days)

    print(f"Fetching {len(symbols)} symbol(s) | {start} -> {end} | cache: {cache_dir}")

    feed = AlpacaFeed(cache_dir=cache_dir)
    errors: list[str] = []

    for symbol in symbols:
        try:
            df = feed.get_historical_daily(symbol, start, end)
            latest = df.index.max().date()
            print(f"  OK  {symbol:8s}  {len(df):3d} bars  latest={latest}")
        except Exception as exc:
            print(f"  ERR {symbol:8s}  {exc}")
            errors.append(symbol)

    print()
    if errors:
        print(f"Failed: {', '.join(errors)}")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
