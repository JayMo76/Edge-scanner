#!/usr/bin/env python
"""Refresh the Schwab history cache after the close, so the next start is fast.

    python scripts/refresh_schwab_cache.py                 # data/universe_all.csv if present, else data/universe.csv
    python scripts/refresh_schwab_cache.py --universe data/my_list.csv

Schwab serves ONE symbol per history request at about 120 a minute, and the
scanner needs yesterday's daily and 5-minute bars for every symbol at startup.
On a whole-market universe that is about two hours of requests, so doing it at
startup means a two-hour start. Run this after the close instead (a scheduled
task at 17:30 ET on weekdays: see the user guide), and the morning start finds
everything already cached and takes minutes.

REST only: it never opens a stream and never binds a port, so it is safe to run
while a scanner is live. Same date ranges as run_live.py. Logs to
data/schwab/refresh.log.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

from scanner.data import make_feed        # noqa: E402
from scanner.universe import load_universe  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--universe", default="", help="universe CSV (default: data/universe_all.csv, else data/universe.csv)")
    ap.add_argument("--history-days", type=int, default=380)
    ap.add_argument("--intraday-days", type=int, default=20)
    args = ap.parse_args()

    log_dir = Path("data/schwab")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(log_dir / "refresh.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    log = logging.getLogger("refresh")

    universe = Path(args.universe) if args.universe else \
        (Path("data/universe_all.csv") if Path("data/universe_all.csv").exists() else Path("data/universe.csv"))
    symbols = load_universe(universe)
    log.info("refreshing Schwab cache for %d symbols from %s", len(symbols), universe)
    feed = make_feed("schwab")
    end = date.today() if time.localtime().tm_hour >= 17 else date.today() - timedelta(days=1)
    t0 = time.time()

    def tick(done: int, total: int, label: str) -> None:
        if done % 500 == 0 or done == total:
            log.info("%s %d/%d  %.0fs", label, done, total, time.time() - t0)

    daily = feed.get_historical_daily_multi(["SPY"] + symbols, end - timedelta(days=args.history_days), end,
                                            progress=lambda d, n: tick(d, n, "daily"))
    bars = feed.get_historical_bars_multi(symbols, "5Min", end - timedelta(days=args.intraday_days * 2 + 5), end,
                                          progress=lambda d, n: tick(d, n, "5m"))
    log.info("done: %d daily, %d intraday, %.0f min", len(daily), len(bars), (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
