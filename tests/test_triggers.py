"""Unit tests for the HOD / LOD breakout test the system setups use."""
import math

import pytest

from scanner.triggers import trigger_hod_breakout


# ── trigger_hod_breakout ──────────────────────────────────────────────────────

def test_hod_breakout_long_fires():
    r = trigger_hod_breakout(high=101.5, low=100.0, prev_hod=101.0, prev_lod=99.0, direction="long")
    assert r.fired is True
    assert r.name == "hod_breakout"
    assert r.value == pytest.approx(0.5)


def test_hod_breakout_long_no_fire_equal_hod():
    r = trigger_hod_breakout(high=101.0, low=100.0, prev_hod=101.0, prev_lod=99.0, direction="long")
    assert r.fired is False
    assert r.value == pytest.approx(0.0)


def test_hod_breakout_long_no_fire_below_hod():
    r = trigger_hod_breakout(high=100.5, low=100.0, prev_hod=101.0, prev_lod=99.0, direction="long")
    assert r.fired is False


def test_hod_breakout_long_no_fire_when_prev_hod_none():
    r = trigger_hod_breakout(high=101.5, low=100.0, prev_hod=None, prev_lod=None, direction="long")
    assert r.fired is False
    assert math.isnan(r.value)


def test_hod_breakout_short_fires():
    r = trigger_hod_breakout(high=101.0, low=98.5, prev_hod=101.0, prev_lod=99.0, direction="short")
    assert r.fired is True
    assert r.name == "hod_breakout"
    assert r.value == pytest.approx(0.5)


def test_hod_breakout_short_no_fire_equal_lod():
    r = trigger_hod_breakout(high=101.0, low=99.0, prev_hod=101.0, prev_lod=99.0, direction="short")
    assert r.fired is False
    assert r.value == pytest.approx(0.0)


def test_hod_breakout_short_no_fire_above_lod():
    r = trigger_hod_breakout(high=101.0, low=99.5, prev_hod=101.0, prev_lod=99.0, direction="short")
    assert r.fired is False


def test_hod_breakout_short_no_fire_when_prev_lod_none():
    r = trigger_hod_breakout(high=101.0, low=98.5, prev_hod=None, prev_lod=None, direction="short")
    assert r.fired is False
    assert math.isnan(r.value)


#
# Builds an *ideal* clean-trend sequence of completed 5-min bars (each carrying the
# slot + vwap_snap/ema9_snap/ema21_snap that state.py attaches on bar completion).
# These prove the trigger CAN fire on perfect input — isolating whether the
# never-fires symptom is the conditions vs. upstream evaluator starvation.

def _conv_bars(
    n: int = 12,
    start_slot: int = 600,     # 600 = 10:00 ET
    base: float = 100.0,
    step: float = 0.1,
    ema9_gap: float = 0.2,     # close - ema9 (within tolerance for a hug)
    vwap: float = 100.0,
    ema21: float = 100.0,
    direction: str = "long",
) -> list[dict]:
    """n clean 5-min bars trending in `direction`, hugging EMA9 above/below VWAP+EMA21."""
    bars = []
    for i in range(n):
        if direction == "long":
            close = base + 1.0 + step * i        # rising, strictly above vwap/ema21
            ema9  = close - ema9_gap             # close >= ema9, |gap| small
        else:
            close = base - 1.0 - step * i        # falling, strictly below vwap/ema21
            ema9  = close + ema9_gap             # close <= ema9
        bars.append({
            "slot": start_slot + i * 5,
            "open": close, "high": close, "low": close,
            "close": close, "volume": 100_000.0,
            "vwap_snap": vwap, "ema9_snap": ema9, "ema21_snap": ema21,
        })
    return bars

