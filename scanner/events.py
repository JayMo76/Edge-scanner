"""Server-side event ring buffer + the HOD/LOD hook for Dashboard V2.

The dashboard polls `GET /api/v2/events?since=<seq>` every 2 s instead of
opening another WebSocket. `EventBuffer` keeps the last `maxlen` events with a
monotonic `seq` so a client can page forward with no duplicates.

`make_hodlod_hook` is called from run_live.py's `_on_bar` diagnostic wrapper
AFTER the scanner has processed the bar, so `SymbolState.high_of_day` /
`low_of_day` already include it. It never raises: an exception in the hook
must never take down the scanner's bar loop.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

log = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


class EventBuffer:
    """Thread-safe ring buffer of `{seq, type, symbol, price, ts}` events."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._buf: deque[dict] = deque(maxlen=maxlen)
        self._seq = 0
        self._lock = threading.Lock()

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def push(self, type: str, symbol: str, price: Optional[float], ts: object) -> int:
        """Append an event; returns its seq."""
        if isinstance(ts, (pd.Timestamp, datetime)):
            ts_out = ts.isoformat()
        else:
            ts_out = ts
        with self._lock:
            self._seq += 1
            self._buf.append({
                "seq": self._seq, "type": type, "symbol": symbol,
                "price": price, "ts": ts_out,
            })
            return self._seq

    def since(self, seq: int, limit: int = 200) -> tuple[int, list[dict]]:
        """Events with seq > `seq`, oldest first, capped at `limit`.

        Returns (latest_seq, events). A client that fell more than `maxlen`
        events behind simply gets the oldest we still have.
        """
        limit = max(1, int(limit))
        with self._lock:
            latest = self._seq
            if seq >= latest:
                return latest, []
            items = [e for e in self._buf if e["seq"] > seq]
        return latest, items[:limit]

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


def _et_date(timestamp: object) -> Optional[str]:
    try:
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(_ET).strftime("%Y-%m-%d")
    except Exception:
        return None


def make_hodlod_hook(scanner, buffer: EventBuffer) -> Callable[[dict], None]:
    """Build a post-bar hook that emits HOD/LOD events on strictly new extremes.

    Per symbol we keep (date, hod, lod). The first observation on a given ET
    date seeds silently (mid-session restarts must not spray a flood of
    "new highs"). Subsequent bars emit when hod rises or lod falls. Pre-09:30
    bars leave hod/lod as None and are ignored. SPY is skipped.
    """
    last_seen: dict[str, tuple[str, float, float]] = {}

    def hook(bar: dict) -> None:
        try:
            symbol = bar.get("symbol")
            if not symbol or symbol == "SPY":
                return
            state = scanner._states.get(symbol)
            if state is None:
                return
            hod = state.high_of_day
            lod = state.low_of_day
            if hod is None or lod is None:
                return
            day = _et_date(bar.get("timestamp"))
            if day is None:
                return
            prev = last_seen.get(symbol)
            if prev is None or prev[0] != day:
                last_seen[symbol] = (day, hod, lod)
                return
            _, p_hod, p_lod = prev
            ts = bar.get("timestamp")
            if hod > p_hod:
                buffer.push("HOD", symbol, hod, ts)
            if lod < p_lod:
                buffer.push("LOD", symbol, lod, ts)
            if hod > p_hod or lod < p_lod:
                last_seen[symbol] = (day, hod, lod)
        except Exception as exc:  # never let the dashboard hook hurt the scanner
            log.debug("hodlod hook error: %s", exc)

    return hook
