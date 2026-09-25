"""Trigger latch and unit fixes reported in edge-scanner issue #18 (thanks to
neusse, who audited them in the Edge-Scanner-NG fork).

All offline: synthetic 1-minute bars through a real SymbolState and the
CustomEvaluator, in the order LiveScanner uses.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scanner.conditions import CATALOG as CONDITIONS, ConditionCtx
from scanner.custom_setups import CustomEvaluator, CustomSetupStore
from tests.helpers import _bar, _minutes, _state

NY = "America/New_York"


def _setup(sid, triggers, **kw):
    d = {"id": sid, "name": sid, "enabled": True, "mode": "or", "direction": "all",
         "sessions": ["rth"], "triggers": triggers}
    d.update(kw)
    return d


def _evaluator(tmp_path: Path, *setups) -> CustomEvaluator:
    store = CustomSetupStore(tmp_path / "custom", defaults=tmp_path / "none.json")
    for s in setups:
        store.save(s)
    return CustomEvaluator(store)


def _live(ev, state, bar):
    state.on_bar(bar)
    return ev.on_bar(state, bar, set())


def _replay(ev, state, bar):
    """What startup seeding does: state and candle rings, never the triggers."""
    state.on_bar(bar)
    ts = pd.Timestamp(bar["timestamp"]).tz_convert(NY)
    ev.series(state.symbol).on_bar(bar, ts.hour * 60 + ts.minute, ts.strftime("%Y-%m-%d"),
                                   state.vwap)


# ── 1. one trigger, two settings, two latches ────────────────────────────────

def _rvol_state():
    return SimpleNamespace(symbol="AAA", vwap=None, rvol=1.0)


def _rvol_bar(et):
    return _bar(100.0, et=et, sym="AAA")


def test_two_rvol_thresholds_each_fire_on_their_own_cross(tmp_path):
    ev = _evaluator(tmp_path,
                    _setup("cs_lo", [{"id": "rvol_cross", "params": {"threshold": 1.5}}]),
                    _setup("cs_hi", [{"id": "rvol_cross", "params": {"threshold": 3.0}}]))
    st = _rvol_state()
    fired = []
    for et, rv in zip(_minutes("09:30", 3), (1.0, 2.0, 3.1)):
        st.rvol = rv
        fired.append(sorted(a["setup"] for a in ev.on_bar(st, _rvol_bar(et), set())))
    # The 1.5x latch used to be the 3x one too, so 3x never saw its cross.
    assert fired == [[], ["cs_lo"], ["cs_hi"]]


def test_consecutive_candles_rearm_after_the_streak_breaks(tmp_path):
    ev = _evaluator(tmp_path, _setup("cs_c", [{"id": "consec_candles", "options": ["green"],
                                               "params": {"count": 2, "tf": 1}}]))
    st = _state(symbol="AAA")
    # green, green, red, green, green, then one more bar to complete the last candle
    opens_closes = [(100.0, 100.5), (100.5, 101.0), (101.0, 100.6), (100.6, 101.0),
                    (101.0, 101.4), (101.4, 101.5)]
    hits = []
    for i, (et, (o, c)) in enumerate(zip(_minutes("09:30", len(opens_closes)), opens_closes)):
        if _live(ev, st, _bar(c, et=et, o=o, sym="AAA")):
            hits.append(i)
    assert len(hits) == 2, hits


# ── 2. premarket and startup ─────────────────────────────────────────────────

def test_a_premarket_streak_is_not_new_at_the_open_for_an_rth_only_setup(tmp_path):
    # Latches follow premarket even for a setup that alerts only in the regular
    # session: a streak that began at 08:00 is not a new streak at 09:30.
    ev = _evaluator(tmp_path, _setup("cs_c", [{"id": "consec_candles", "options": ["green"],
                                               "params": {"count": 2, "tf": 1}}]))
    st = _state(symbol="AAA")
    for i, et in enumerate(_minutes("09:26", 6)):
        out = _live(ev, st, _bar(100.0 + i * 0.2, et=et, o=100.0 + i * 0.2 - 0.1, sym="AAA"))
        assert out == [], et


def _gap_day(ev, st, until="11:00", live=False):
    """Open at 105 against a 100 close, then drift, from 09:30 to `until`."""
    n = (pd.Timestamp(f"2024-01-02 {until}") - pd.Timestamp("2024-01-02 09:30")).seconds // 60
    out = []
    for i, et in enumerate(_minutes("09:30", n)):
        bar = _bar(105.0 + (i % 3) * 0.1, et=et, sym="AAA")
        if live:
            out.extend(_live(ev, st, bar))
        else:
            _replay(ev, st, bar)
    return out


def _gap_setup():
    return _setup("cs_gap", [{"id": "gap", "options": ["up"], "params": {"min_pct": 2.0}}])


def test_a_live_session_alerts_the_gap_at_the_open(tmp_path):
    ev = _evaluator(tmp_path, _gap_setup())
    out = _gap_day(ev, _state(symbol="AAA", prior_close=100.0), until="09:32", live=True)
    assert [a["setup"] for a in out] == ["cs_gap"]


def test_a_start_after_the_open_does_not_alert_the_mornings_gap(tmp_path):
    ev = _evaluator(tmp_path, _gap_setup())
    st = _state(symbol="AAA", prior_close=100.0)
    _gap_day(ev, st)
    now = pd.Timestamp("2024-01-02 11:00", tz=NY)
    assert ev.prime({"AAA": st}, now_et=now) == 1
    assert _live(ev, st, _bar(105.2, et="2024-01-02 11:00", sym="AAA")) == []


def test_without_priming_the_replayed_gap_would_alert_late(tmp_path):
    ev = _evaluator(tmp_path, _gap_setup())
    st = _state(symbol="AAA", prior_close=100.0)
    _gap_day(ev, st)
    assert _live(ev, st, _bar(105.2, et="2024-01-02 11:00", sym="AAA"))


def test_no_gap_alert_when_the_open_was_never_seen(tmp_path):
    # A symbol caught up from quotes mid-session has no opening bar; its first
    # live bar's open is where it trades now, not where it opened.
    ev = _evaluator(tmp_path, _gap_setup())
    st = _state(symbol="AAA", prior_close=100.0)
    assert _live(ev, st, _bar(105.2, et="2024-01-02 11:00", sym="AAA")) == []


# ── 5a. near a level means it has not broken it ──────────────────────────────

def _near_hod_run(tmp_path, last_high):
    ev = _evaluator(tmp_path, _setup("cs_n", [{"id": "near_hod", "options": ["high"]}]))
    st = _state(symbol="AAA")
    # HOD 100.5 on the first bar, then bars well below it (enough for the
    # 20-candle ATR) so the latch is off
    _live(ev, st, _bar(95.0, et="2024-01-02 09:30", o=95.0, h=100.5, l=94.5, sym="AAA"))
    for et in _minutes("09:31", 22):
        _live(ev, st, _bar(95.0, et=et, o=95.0, h=95.5, l=94.5, sym="AAA"))
    return _live(ev, st, _bar(100.2, et="2024-01-02 09:53", o=99.9, h=last_high, l=99.9, sym="AAA"))


def test_near_hod_fires_on_an_approach(tmp_path):
    assert _near_hod_run(tmp_path, last_high=100.4)


def test_near_hod_does_not_fire_on_a_bar_that_broke_the_high(tmp_path):
    assert _near_hod_run(tmp_path, last_high=101.0) == []


# ── short interest: fraction in the cache, percent in the setting ────────────

def test_short_pct_condition_reads_percent():
    ctx = ConditionCtx(state=None, fundamentals={"short_pct_float": 0.139})
    assert abs(CONDITIONS["short_pct_float"].resolve(ctx, "", {}) - 13.9) < 1e-9
    assert CONDITIONS["short_pct_float"].resolve(ConditionCtx(state=None, fundamentals={}), "", {}) is None


# ── range break volume: minute against minute ────────────────────────────────

def _rb_setup(**params):
    q = {"bars": 5, "tf": 5, "max_range_pct": 1.5}
    q.update(params)
    return _setup("cs_rb", [{"id": "range_break", "options": ["up"], "params": q}], direction="long")


def _rb_fires(tmp_path, breakout_volume, **params):
    ev = _evaluator(tmp_path, _rb_setup(**params))
    st = _state(symbol="AAA", prior_close=100.0)
    for i, et in enumerate(_minutes("09:30", 25)):              # five quiet 5-min candles
        _live(ev, st, _bar(100.0 + (i % 2) * 0.1, et=et, sym="AAA", vol=1000.0))
    return _live(ev, st, _bar(101.0, et="2024-01-02 09:55", sym="AAA", vol=breakout_volume))


def test_range_break_compares_the_breaking_minute_with_the_average_minute(tmp_path):
    # the range trades 1,000 shares a minute: 6x is 6,000
    assert _rb_fires(tmp_path / "a", 6000.0, vol_min=6.0)
    assert _rb_fires(tmp_path / "b", 5900.0, vol_min=6.0) == []


def test_a_saved_candle_multiple_converts_to_the_same_alerts(tmp_path):
    # 1.2x a 5-minute candle (5,000) was 6,000 shares; converted to 6.0x a minute
    from scanner.custom_setups import migrate_trigger
    t = migrate_trigger({"id": "range_break", "params": {"vol_mult": 1.2, "tf": 5.0}})
    assert t["params"] == {"vol_min": 6.0, "tf": 5.0}
    assert _rb_fires(tmp_path / "a", 6000.0, vol_mult=1.2)
    assert _rb_fires(tmp_path / "b", 5900.0, vol_mult=1.2) == []


def test_a_setup_file_saved_before_the_change_loads_converted(tmp_path):
    import json
    d = tmp_path / "custom"
    d.mkdir()
    (d / "cs_old.json").write_text(json.dumps(_rb_setup(vol_mult=1.2) | {"id": "cs_old"}))
    store = CustomSetupStore(d, defaults=tmp_path / "none.json")
    params = store.load_all()[0]["triggers"][0]["params"]
    assert params["vol_min"] == 6.0 and "vol_mult" not in params
    assert store.get("cs_old")["triggers"][0]["params"]["vol_min"] == 6.0
