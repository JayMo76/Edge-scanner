#!/usr/bin/env python
"""Authenticate with Schwab and smoke-test what the scanner actually needs.

    python scripts/schwab_auth.py

Run this interactively (it prompts you to paste a URL). You will need to
re-run it roughly WEEKLY: Schwab's refresh token expires every 7 days and
there is no way to renew it without a browser.

What the first run does:
  1. Opens a browser to Schwab's consent page.
  2. You approve, land on your callback URL, and the page FAILS TO LOAD.
     That is expected and fine. Nothing listens on that URL. Copy the whole
     address bar (it carries ?code=...) and paste it at the prompt.
  3. Tokens are written to ~/.schwabdev/tokens.db for reuse.

Then it checks the three things that decide whether the scanner can run on
Schwab at all, in order of how likely they are to fail:

  quotes         -> market data works
  price history  -> warmup / RVOL profile works
  userPreference -> THE STREAMER works. This is a Trader API endpoint, so a
                    market-data-only app passes the first two and fails here.
                    Without it there is no live 1-min bar feed.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
os.chdir(_REPO_ROOT)
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)


def _ok(msg: str) -> None:
    print(f"  [ OK ]  {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"  [FAIL]  {msg}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Schwab auth + capability smoke test")
    ap.add_argument("--reauth", action="store_true",
                    help="Force a brand new authorization. Use after changing the "
                         "app's API products if cached tokens keep 401ing on the "
                         "new endpoints (the old token carries the old scopes).")
    args = ap.parse_args()

    key    = os.environ.get("SCHWAB_APP_KEY")
    secret = os.environ.get("SCHWAB_APP_SECRET")
    cb     = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    if not key or not secret:
        sys.exit("SCHWAB_APP_KEY / SCHWAB_APP_SECRET missing from .env")

    print(f"\nSchwab auth + smoke test")
    print(f"  app key      : {key[:4]}...{key[-4:]} (len {len(key)})")
    print(f"  callback url : {cb}")
    print()
    print("  BEFORE YOU CLICK APPROVE, read these three:")
    print("   1. The callback page WILL fail to load (ERR_SSL_PROTOCOL_ERROR, or")
    print("      'this site can't provide a secure connection'). That is correct.")
    print("      Nothing listens on that URL. Copy the address bar anyway.")
    print("   2. The code expires in ~30 SECONDS. Have this window visible and")
    print("      paste immediately, or you start over.")
    print("   3. What you paste MUST start with https:// . Chrome hides the scheme")
    print("      in the address bar; without it schwabdev parses the code wrong")
    print("      and the exchange fails with a confusing error.")
    print()

    import schwabdev
    client = schwabdev.Client(app_key=key, app_secret=secret, callback_url=cb)

    if args.reauth:
        print("  Forcing a new authorization (old token carries the old scopes)")
        client.tokens.update_tokens(force_refresh_token=True)

    # ── token status ─────────────────────────────────────────────────────────
    try:
        t = client.tokens
        issued = getattr(t, "_refresh_token_issued", None)
        if issued is not None:
            left = timedelta(seconds=getattr(t, "_refresh_token_timeout", 0)) - (
                datetime.now(issued.tzinfo) - issued)
            days = left.total_seconds() / 86400
            print(f"\n  refresh token expires in {days:.1f} days "
                  f"({'re-run this script before then' if days < 8 else 'ok'})")
    except Exception as exc:
        print(f"  (could not read token expiry: {exc})")

    print("\nChecking what the scanner needs:\n")
    results = {}

    # 1. quotes -> market data
    try:
        r = client.quotes(symbols=["SPY"], fields="quote")
        r.raise_for_status()
        q = (r.json() or {}).get("SPY", {}).get("quote", {})
        _ok(f"quotes           SPY last={q.get('lastPrice')} vol={q.get('totalVolume')}")
        results["quotes"] = True
    except Exception as exc:
        _fail(f"quotes           {exc}")
        results["quotes"] = False

    # 2. price history -> warmup
    try:
        end = date.today()
        r = client.price_history(
            symbol="SPY", periodType="month", frequencyType="daily", frequency=1,
            startDate=datetime.combine(end - timedelta(days=10), datetime.min.time()),
            endDate=datetime.combine(end, datetime.max.time()))
        r.raise_for_status()
        candles = (r.json() or {}).get("candles", [])
        _ok(f"price history    {len(candles)} daily candles for SPY")
        results["history"] = bool(candles)
        if candles:
            last = candles[-1]
            ts = datetime.fromtimestamp(last["datetime"] / 1000)
            print(f"          latest: {ts:%Y-%m-%d}  close={last['close']}  vol={last['volume']:,}")
    except Exception as exc:
        _fail(f"price history    {exc}")
        results["history"] = False

    # 3. userPreference -> the streamer (Trader API scope)
    try:
        r = client.preferences()
        r.raise_for_status()
        info = ((r.json() or {}).get("streamerInfo") or [{}])[0]
        url = info.get("streamerSocketUrl")
        if url:
            _ok(f"streamer info    {url[:48]}...")
            results["stream"] = True
        else:
            _fail("streamer info    responded but carried no streamerSocketUrl")
            results["stream"] = False
    except Exception as exc:
        _fail(f"streamer info    {exc}")
        print("          ^ this is /trader/v1/userPreference. If it 401s, your app")
        print("            is market-data-only and CANNOT open the live bar stream.")
        print("            Enable 'Accounts and Trading' on the app in the portal.")
        results["stream"] = False

    print()
    if all(results.values()):
        print("  ALL GREEN. Next: python scripts/compare_feeds.py --symbols AAPL,MU,NVDA,TSM")
    elif results.get("history"):
        print("  Historical data works; the live stream does not.")
        print("  You can still run compare_feeds.py to check data agreement.")
    else:
        print("  Not usable yet. If everything 401s, the app is probably still")
        print("  'Approved - Pending' rather than 'Ready For Use' in the portal.")
    print()


if __name__ == "__main__":
    main()
