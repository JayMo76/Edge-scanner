#!/usr/bin/env python
"""Is Schwab data a match for Alpaca's? One command, side by side.

    python scripts/schwab_auth.py          # first, if the login is older than 7 days
    python scripts/check_schwab_match.py   # about an hour the first time (cold cache)

1. Checks the Schwab login and the 5-minute history depth (the relative-volume
   profile wants 20 trading days).
2. Builds universes at the "all", "wide" and "default" threshold sets
   ("all" first: it fills the Schwab daily cache the other two reuse) and
   compares, for each:
     data parity   alpaca:nasdaq vs schwab:nasdaq  (same symbol list, only the data differs)
     end to end    alpaca:alpaca vs schwab:nasdaq  (what switching DATA_PROVIDER changes)
3. Prints one summary table. Full reports: data/universe_compare/.

Ready when every overlap is >= 97% and the differences are explained (list
differences, or near-cutoff data differences). Needs both Alpaca and Schwab logins.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _login_and_depth() -> None:
    from scanner.data.schwab import SchwabFeed, refresh_token_age_days
    age = refresh_token_age_days()
    print(f"Schwab login age: {'unknown' if age is None else f'{age:.1f} days'}")
    feed = SchwabFeed()                      # raises with instructions if expired
    end = date.today() - timedelta(days=1)
    df = feed.get_bars_range("SPY", "5Min", end - timedelta(days=45), end)
    days = df.index.tz_convert("America/New_York").normalize().nunique() if len(df) else 0
    print(f"SPY 5-minute history: {days} trading days returned for a 45-day request "
          f"({'enough' if days >= 20 else 'SHORT: the relative-volume profile will use fewer than 20 days'})")


def _compare(a: str, b: str, preset: str) -> dict:
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "compare_universes.py"),
                        "--a", a, "--b", b, "--preset", preset, "--reuse"],
                       cwd=REPO, capture_output=True, text=True)
    out = r.stdout + r.stderr
    get = lambda label: (re.search(rf"\| {re.escape(label)} \| ([^|]+) \|", out) or [None, "?"])[1].strip()
    return {"a": get(f"{a} universe"), "b": get(f"{b} universe"), "overlap": get("overlap (in both / in either)"),
            "report": (re.search(r"full report: (.+)", out) or [None, out[-300:]])[1].strip()}


def main() -> int:
    _login_and_depth()
    rows = []
    for preset in ("all", "wide", "default"):
        for label, a in (("data parity", "alpaca:nasdaq"), ("end to end", "alpaca:alpaca")):
            print(f"comparing {label} ({preset}) ...", flush=True)
            rows.append((preset, label, _compare(a, "schwab:nasdaq", preset)))
    print("\n| thresholds | comparison | Alpaca | Schwab | overlap |\n|---|---|---|---|---|")
    for preset, label, r in rows:
        print(f"| {preset} | {label} | {r['a']} | {r['b']} | {r['overlap']} |")
    print("\nReports:")
    for _, _, r in rows:
        print(f"  {r['report']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
