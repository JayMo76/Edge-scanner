#!/usr/bin/env python
"""Install the setup library (scanner/setup_library.json) into data/setups/custom/.

    python scripts/install_setup_library.py            # add the ones that are missing
    python scripts/install_setup_library.py --dry-run  # validate and list, change nothing

`custom_setups_defaults.json` only seeds an EMPTY install, so a setup added to the
library later would never reach a machine that already has setups. This adds every
library id that is not on disk and NEVER overwrites one that is, so edits made in
the Setups panel survive a re-run.

When the scanner is up the setups go in through its API, which hot-reloads the
evaluator: they are live on the next bar with no restart. When it is down they are
written through the same store the scanner reads at start.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanner.custom_setups import CustomSetupStore, normalize_setup  # noqa: E402

LIBRARY = Path(__file__).resolve().parents[1] / "scanner" / "setup_library.json"


def _api(base: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--api", default="http://localhost:7777", help="scanner base url")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    setups = json.loads(LIBRARY.read_text(encoding="utf-8"))["setups"]
    for s in setups:
        normalize_setup(s)                       # fail before touching anything

    try:
        have = {c["id"] for c in _api(args.api, "GET", "/api/v2/setups")["custom"]}
        live = True
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        store = CustomSetupStore()
        have = {c["id"] for c in store.load_all()}
        live = False
    print(f"scanner {'is up: installing through the API (hot reload)' if live else 'is down: writing to disk'}")

    for s in setups:
        if s["id"] in have:
            print(f"  keep   {s['id']}  (already installed, not overwritten)")
            continue
        if args.dry_run:
            print(f"  would add {s['id']}  {s['name']}")
        elif live:
            try:
                _api(args.api, "PUT", f"/api/v2/setups/{s['id']}", s)
                print(f"  added  {s['id']}  {s['name']}")
            except urllib.error.HTTPError as exc:
                # The library validated against THIS checkout above, so a 400 here
                # means the running scanner predates a condition or trigger the
                # setup uses. Nothing was written; restart it and run this again.
                why = exc.read().decode(errors="replace")[:160]
                print(f"  SKIP   {s['id']}  the running scanner rejected it, restart it and re-run ({why})")
        else:
            store.save(s, sid=s["id"])
            print(f"  added  {s['id']}  {s['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
