"""Shared test builders: synthetic daily history, a SymbolState seeded from it,
and 1-min bars fed one per minute. Setup-agnostic, used by core and plugin tests."""
from __future__ import annotations

import pandas as pd

from scanner.state import SymbolState


def _daily(n=60, base=100.0, step=0.05, vol=20_000_000.0, last_open=None,
           last_close=None, last_high=None, last_low=None) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
    c = pd.Series([base + i * step for i in range(n)], index=idx)
    df = pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c,
                       "volume": vol}, index=idx)
    # Override the last (prior) day so gap / prior_day_chg are controllable
    if last_open is not None:  df.iloc[-1, df.columns.get_loc("open")]  = last_open
    if last_close is not None: df.iloc[-1, df.columns.get_loc("close")] = last_close
    if last_high is not None:  df.iloc[-1, df.columns.get_loc("high")]  = last_high
    if last_low is not None:   df.iloc[-1, df.columns.get_loc("low")]   = last_low
    return df


def _state(symbol="AAPL", adv=20_000_000.0, prior_open=100.0, prior_close=100.0,
           prior_high=101.0, prior_low=99.0) -> SymbolState:
    daily = _daily(vol=adv, last_open=prior_open, last_close=prior_close,
                   last_high=prior_high, last_low=prior_low)
    spy = _daily(base=450.0, step=0.1)
    return SymbolState.from_history(symbol, daily, spy)


def _bar(price, et="2024-01-02 11:00", o=None, h=None, l=None, vol=100_000.0, sym="AAPL"):
    ts = pd.Timestamp(et, tz="America/New_York").tz_convert("UTC")
    o = price if o is None else o
    return {"symbol": sym, "timestamp": ts, "open": o,
            "high": h if h is not None else max(o, price) + 0.05,
            "low":  l if l is not None else min(o, price) - 0.05,
            "close": price, "volume": vol}


def _minutes(start_hhmm: str, n: int):
    """Yield ET time strings start, start+1m, ..."""
    h, m = map(int, start_hhmm.split(":"))
    base = pd.Timestamp(f"2024-01-02 {h:02d}:{m:02d}", tz="America/New_York")
    for i in range(n):
        yield (base + pd.Timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M")


def _feed(state, prices, start="09:30", **kw):
    """Feed a sequence of 1-min bars (one per minute from start). Returns last bar."""
    bar = None
    for et, p in zip(_minutes(start, len(prices)), prices):
        bar = _bar(p, et=et, **kw)
        state.on_bar(bar)
    return bar


def _et_min(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


# ── a fake engine plugin ─────────────────────────────────────────────────────
#
# Core behaviour that involves system setups (profile binding, the setup names
# store, the setup check report, the trigger catalog pass-throughs) is tested
# against these two made-up setups, so the public suite neither needs nor
# depends on a real plugin. install_fake_plugin() swaps them in everywhere the
# core captured the plugin's registry at import time.

from dataclasses import dataclass, field  # noqa: E402

from scanner.plugins import SystemSetup  # noqa: E402

FAKE_SETUPS = (
    SystemSetup("X1", "Fake Long", "long"),
    SystemSetup("X2", "Fake Short", "short"),
)
FAKE_CODES = tuple(s.code for s in FAKE_SETUPS)
FAKE_NAMES = {s.code: s.name for s in FAKE_SETUPS}


@dataclass
class FakeResult:
    """Shaped like a system setup's per-bar result, as RecentActivity reads it."""
    setup: str
    direction: str
    fired: bool
    trigger: str = ""
    reasons: list[str] = field(default_factory=list)

    def failed_gates(self) -> list[str]:
        return list(self.reasons)


class FakeSetupEvaluator:
    """Stand-in for a plugin's system evaluator.

    Every setup in `fire` fires on every regular-session bar; the others report
    one failed gate. Results are recorded on the scanner's RecentActivity the
    way a real evaluator does it."""

    def __init__(self, fire: tuple[str, ...] = (), setups=FAKE_SETUPS) -> None:
        self.fire = set(fire)
        self.setups = setups
        self.activity = None
        self.resets = 0

    def reset(self) -> None:
        """Called by LiveScanner.reset_session()."""
        self.resets += 1

    def on_bar(self, state, bar, spy_rth_chg_pct=None, spy_mom_15m_pct=None) -> list[dict]:
        ts = pd.Timestamp(bar["timestamp"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        et = ts.tz_convert("America/New_York")
        if et.hour * 60 + et.minute < 9 * 60 + 30:
            return []
        results = [FakeResult(s.code, s.direction, s.code in self.fire, f"SYS_{s.code}",
                              [] if s.code in self.fire else ["gap: 0.1 >= 1.0"])
                   for s in self.setups]
        if self.activity is not None:
            self.activity.set_system_results(state.symbol, ts, results)
        return [{"symbol": state.symbol, "setup": r.setup, "direction": r.direction,
                 "trigger": r.trigger, "timestamp": ts.isoformat(), "price": float(bar["close"]),
                 "score": 80, "tier": None, "suggested_stop": None, "stop_pct": None, "context": {}}
                for r in results if r.fired]


def fake_system_check(code, state, spy_state=None) -> dict:
    return {"symbol": state.symbol, "in_universe": True, "setup": code, "fired": False,
            "gates": [{"name": "gap", "passed": False, "value": 0.1, "reason": "0.1 >= 1.0"}]}


def install_fake_plugin(monkeypatch, setups=FAKE_SETUPS) -> tuple[str, ...]:
    """Make the core see `setups` as the installed plugin's system setups.
    Returns their codes."""
    from scanner import custom_setups, plugins, profiles, trigger_catalog
    from scanner.trigger_catalog import TriggerDef

    codes = tuple(s.code for s in setups)
    names = {s.code: s.name for s in setups}
    monkeypatch.setattr(plugins, "SYSTEM_SETUPS", tuple(setups))
    monkeypatch.setattr(plugins, "SYSTEM_CODES", codes)
    monkeypatch.setattr(plugins, "SYSTEM_DEFAULT_NAMES", names)
    monkeypatch.setattr(plugins, "system_check", fake_system_check)
    monkeypatch.setattr(custom_setups, "_SYSTEM_CODES", codes)
    monkeypatch.setattr(custom_setups, "_SYSTEM_DEFAULT_NAMES", names)
    monkeypatch.setattr(profiles, "SYSTEM_KEYS", codes)
    # the catalog's pass-through triggers, as trigger_catalog builds them
    native = [t for t in trigger_catalog.CATALOG if t.source != "system"]
    passthrough = [TriggerDef(f"setup:{s.code}", s.name, "System setups", "Fires when the system setup emits.",
                              s.direction, sessions=("rth",), source="system") for s in setups]
    monkeypatch.setattr(trigger_catalog, "CATALOG", native + passthrough)
    for t in trigger_catalog.BY_ID.copy().values():
        if t.source == "system":
            monkeypatch.delitem(trigger_catalog.BY_ID, t.id)
    for t in passthrough:
        monkeypatch.setitem(trigger_catalog.BY_ID, t.id, t)
    return codes
