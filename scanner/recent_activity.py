"""What every setup did on every symbol in the last few minutes.

Backs the Setup check window: type a stock, see for each setup whether its alert
went out in the last N minutes, or exactly what stopped it. It answers "why did I
not get an alert on X?", which the feed alone cannot, because a blocked alert
never reaches the feed.

It RECORDS as the scanner runs rather than recomputing on request. Recomputing
the last five minutes would need every indicator as it stood on each of those
bars, which nothing keeps. Recording is cheap because of what is stored:

  events       only when something actually happened: an alert pattern fired
               and was sent, blocked, held back by a don't-repeat timer, or is
               still waiting for the rest of an "at least N of" setup. A few
               per symbol per minute at most, pruned by time.
  latest gates for the system setups, which check their gates BEFORE
               looking for an entry: a reference to the result object the
               evaluator already built on the last bar. Nothing is copied or
               formatted until someone asks.

Written from the scanner thread and read from uvicorn threads, so the event
lists sit behind one lock held only for an append or a copy.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Optional

import pandas as pd

KEEP_SECONDS = 20 * 60            # the window offers up to 15 minutes; keep a margin
MAX_EVENTS_PER_SYMBOL = 400

SENT, BLOCKED, REPEAT, WAITING, SUPPRESSED = "sent", "blocked", "repeat", "waiting", "suppressed"


def _epoch(ts: Any) -> float:
    try:
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        return t.timestamp()
    except Exception:
        return time.time()


class RecentActivity:
    def __init__(self, keep_seconds: int = KEEP_SECONDS) -> None:
        self._keep = keep_seconds
        self._lock = threading.Lock()
        self._events: dict[str, deque] = {}
        # latest evaluation, by reference: (bar timestamp as given, object)
        self.system_results: dict[str, tuple[Any, list]] = {}
        self.de_results: dict[str, tuple[Any, list]] = {}

    # ── writes (scanner thread) ──────────────────────────────────────────────
    def add(self, symbol: str, ts: Any, source: str, setup: str, direction: str,
            outcome: str, trigger: str = "", reasons: Optional[list[str]] = None) -> None:
        ev = (_epoch(ts), source, setup, direction or "", outcome, trigger or "", tuple(reasons or ()))
        with self._lock:
            d = self._events.get(symbol)
            if d is None:
                d = self._events[symbol] = deque(maxlen=MAX_EVENTS_PER_SYMBOL)
            d.append(ev)
            cutoff = ev[0] - self._keep
            while d and d[0][0] < cutoff:
                d.popleft()

    # These run for every symbol on every bar, so they store the timestamp as
    # given and leave the conversion to the rare read.
    def set_system_results(self, symbol: str, ts: Any, results: list) -> None:
        self.system_results[symbol] = (ts, results)

    def set_de_results(self, symbol: str, ts: Any, results: list) -> None:
        self.de_results[symbol] = (ts, results)

    # ── reads (API threads) ──────────────────────────────────────────────────
    def events(self, symbol: str, since_epoch: float) -> list[dict]:
        with self._lock:
            evs = list(self._events.get(symbol, ()))
        return [{"ts": e[0], "source": e[1], "setup": e[2], "direction": e[3], "outcome": e[4],
                 "trigger": e[5], "reasons": list(e[6])}
                for e in evs if e[0] >= since_epoch]


def describe_check(c: Any) -> str:
    """A failed condition as "what it has, what it needs".

    GateCheck reasons are written as the comparison itself ("$101.2 >= $10K"),
    which reads as a true statement when shown next to the word blocked.
    """
    try:
        from scanner.conditions import CATALOG, OP_LABEL
        d = CATALOG.get(c.name)
        name = d.name if d is not None else str(c.name).replace("_", " ")
        reason = str(c.reason or "")
        for lab in sorted(set(OP_LABEL.values()), key=len, reverse=True):
            sep = f" {lab} "
            if sep in reason:
                have, need = reason.split(sep, 1)
                return f"{name} {have} (needs {lab} {need})"
        return f"{name}: {reason}" if reason else name
    except Exception:
        return f"{getattr(c, 'name', '?')}: {getattr(c, 'reason', '')}"


# ── the Setup check report ───────────────────────────────────────────────────

_RANK = {"sent": 0, "blocked": 1, "waiting": 2, "repeat": 3, "suppressed": 4, "quiet": 5}
_SOURCE_LABEL = {"custom": "CS", "system": "System"}


def _latest_bar(state: Any) -> tuple[Optional[float], Optional[float]]:
    """(epoch of the symbol's last 1-min bar, its close)."""
    try:
        b = state.last_1m[-1]
        return _epoch(b["timestamp"]), float(b["close"])
    except Exception:
        return None, None


def _universe_now(profiles: Any, code: str, custom_profile: Optional[str], sym: str) -> Optional[str]:
    """Why the universe filter would block this symbol, or None when it would not.
    Static only: membership is fixed for the session, so this is exact."""
    if profiles is None:
        return None
    try:
        cp = profiles.for_setup(code, custom_profile)
        if cp is None or not cp.static or cp.members is None:
            return None
        return None if sym in cp.members else f"not in the {cp.name} universe"
    except Exception:
        return None


def _params_now(scanner: Any, profiles: Any, setup: dict, state: Any, direction: str) -> list[str]:
    """What the setup's parameters would say if its alert fired on the latest bar."""
    if profiles is None:
        return []
    conds = list(profiles.params_for(setup.get("parameter_set"))) + list(setup.get("parameters") or [])
    if not conds:
        return []
    try:
        from scanner.conditions import ConditionCtx
        sym = state.symbol
        bar = dict(state.last_1m[-1]) if getattr(state, "last_1m", None) else None
        fund = scanner._fundamentals_for(sym) if hasattr(scanner, "_fundamentals_for") else None
        ctx = ConditionCtx(state=state, series=getattr(scanner, "_series", {}).get(sym), bar=bar,
                           session="rth", direction=direction, fundamentals=fund,
                           regime=getattr(scanner, "_regime", None))
        res = profiles.check_conditions(conds, ctx)
        return [describe_check(c) for c in res.checks if not c.passed]
    except Exception as exc:
        return [f"could not evaluate parameters ({exc})"]


def build_setup_check(scanner: Any, custom_setups: list[dict], names: dict, profiles: Any,
                      symbol: str, minutes: int = 5) -> dict:
    """Every setup, what it did on `symbol` in the last `minutes`, and why."""
    sym = symbol.strip().upper()
    states = getattr(scanner, "_states", {}) or {}
    state = states.get(sym)
    act: Optional[RecentActivity] = getattr(scanner, "activity", None)
    if state is None:
        return {"symbol": sym, "found": False, "setups": [],
                "message": f"{sym} is not in the scanner universe, so nothing was evaluated on it."}

    last_epoch, price = _latest_bar(state)
    ref = (last_epoch + 60) if last_epoch else time.time()
    since = ref - minutes * 60
    events = act.events(sym, since) if act is not None else []
    by_setup: dict[str, list[dict]] = {}
    for e in events:
        by_setup.setdefault(e["setup"], []).append(e)

    rows: list[dict] = []

    def row(code: str, source: str, name: str, now: list[dict]) -> None:
        evs = sorted(by_setup.get(code, []), key=lambda e: e["ts"], reverse=True)
        status = min((e["outcome"] for e in evs), key=lambda o: _RANK.get(o, 9)) if evs else "quiet"
        rows.append({"id": code, "name": name, "source": _SOURCE_LABEL.get(source, source),
                     "status": status, "events": evs, "now": now})

    # CS setups: no gates before the alert, so "now" is what the universe and
    # the parameters would say if the alert fired on the latest bar
    if getattr(scanner, "_custom_evaluator", None) is not None:
        for s in custom_setups:
            if not s.get("enabled", True):
                continue
            now: list[dict] = []
            uni = _universe_now(profiles, s["id"], s.get("universe_profile"), sym)
            dirs = ["long", "short"] if s.get("direction", "all") == "all" else [s["direction"]]
            for d in dirs:
                why = ([uni] if uni else []) + _params_now(scanner, profiles, s, state, d)
                now.append({"direction": d, "ok": not why, "reasons": why})
            row(s["id"], "custom", s.get("name") or s["id"], now)

    # System setups: each setup's own gate list from the last bar, by reference
    system_latest: dict[str, tuple[float, Any]] = {}
    for store in ((act.system_results if act is not None else {}), (act.de_results if act is not None else {})):
        got = store.get(sym)
        if got:
            for r in got[1]:
                system_latest[r.setup] = (got[0], r)
    from scanner import plugins
    systems = [s.code for s in plugins.SYSTEM_SETUPS if getattr(scanner, s.evaluator, None) is not None]
    for code in systems:
        uni = _universe_now(profiles, code, None, sym)
        got = system_latest.get(code)
        if got is None:
            now = [{"direction": "", "ok": None, "reasons": ([uni] if uni else []) + ["not evaluated yet"]}]
        else:
            ts_, r = _epoch(got[0]), got[1]
            why = ([uni] if uni else []) + r.failed_gates()
            if not why and not r.fired:
                why = ["gates pass, waiting for its entry"]
                now = [{"direction": r.direction, "ok": None, "reasons": why, "ts": ts_}]
            else:
                now = [{"direction": r.direction, "ok": not why, "reasons": why, "ts": ts_}]
        row(code, "system", names.get(code, code), now)

    rows.sort(key=lambda r: (_RANK.get(r["status"], 9), r["name"].lower()))
    return {"symbol": sym, "found": True, "price": price, "last_bar": last_epoch,
            "minutes": minutes, "since": since, "generated": time.time(),
            "recording": act is not None, "setups": rows}
