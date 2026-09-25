"""Unit tests for market regime classification and mandatory gate functions."""

import pandas as pd
import pytest

from scanner.market import MarketRegime, classify_market
from scanner.gates import (
    gate_market_align,
    gate_rrs_d1,
    gate_rvol,
    gate_void,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts(et_str: str) -> pd.Timestamp:
    """Return a UTC timestamp from an ET string like '2024-01-02 10:30'."""
    return pd.Timestamp(et_str, tz="America/New_York").tz_convert("UTC")


def _highs(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B", tz="UTC")
    return pd.Series(values, index=idx)


def _lows(values: list[float]) -> pd.Series:
    return _highs(values)


# ── classify_market ───────────────────────────────────────────────────────────

def test_classify_market_bullish():
    assert classify_market(spy_price=450.0, spy_vwap=448.0) == MarketRegime.BULLISH


def test_classify_market_bearish():
    assert classify_market(spy_price=446.0, spy_vwap=448.0) == MarketRegime.BEARISH


def test_classify_market_neutral_inside_band():
    # 0.05% deviation — inside the 0.1% band
    assert classify_market(spy_price=448.2, spy_vwap=448.0) == MarketRegime.NEUTRAL


def test_classify_market_no_vwap():
    assert classify_market(spy_price=450.0, spy_vwap=None) == MarketRegime.NEUTRAL


def test_classify_market_zero_vwap():
    assert classify_market(spy_price=450.0, spy_vwap=0.0) == MarketRegime.NEUTRAL


# ── gate_rrs_d1 (M5-only gate) ───────────────────────────────────────────────

def test_rrs_m5_long_passes_positive():
    r = gate_rrs_d1(rrs_d1=-1.0, rrs_m5=2.4, direction="long")
    assert r.passed is True
    assert r.value == pytest.approx(2.4)


def test_rrs_m5_long_fails_negative():
    assert gate_rrs_d1(rrs_d1=2.0, rrs_m5=-1.0, direction="long").passed is False


def test_rrs_m5_short_passes_negative():
    assert gate_rrs_d1(rrs_d1=1.0, rrs_m5=-2.0, direction="short").passed is True


def test_rrs_m5_short_fails_positive():
    assert gate_rrs_d1(rrs_d1=-1.0, rrs_m5=1.5, direction="short").passed is False


def test_rrs_m5_zero_fails_both():
    assert gate_rrs_d1(rrs_d1=1.0, rrs_m5=0.0, direction="long").passed is False
    assert gate_rrs_d1(rrs_d1=-1.0, rrs_m5=0.0, direction="short").passed is False


def test_rrs_no_m5_passes_as_no_data_early():
    # Fewer than 12 five-min bars: normal warmup — must not block
    r = gate_rrs_d1(rrs_d1=-1.76, rrs_m5=None, direction="long", bars_5m_count=5)
    assert r.passed is None
    assert r.status == "no_data"


def test_rrs_nan_m5_passes_as_no_data_early():
    r = gate_rrs_d1(rrs_d1=2.0, rrs_m5=float("nan"), direction="long", bars_5m_count=11)
    assert r.passed is None
    assert r.status == "no_data"


def test_rrs_no_m5_blocks_after_warmup():
    # 12+ five-min bars: missing M5 is a data gap — must block
    r = gate_rrs_d1(rrs_d1=1.0, rrs_m5=None, direction="long", bars_5m_count=12)
    assert r.passed is False
    assert r.status == "rrs_unavailable"


def test_rrs_nan_m5_blocks_after_warmup():
    r = gate_rrs_d1(rrs_d1=1.0, rrs_m5=float("nan"), direction="long", bars_5m_count=20)
    assert r.passed is False
    assert r.status == "rrs_unavailable"


def test_rrs_no_m5_zero_bars_passes():
    # Zero bars (fresh start): early warmup — passes
    r = gate_rrs_d1(rrs_d1=-1.76, rrs_m5=None, direction="long")
    assert r.passed is None
    assert r.status == "no_data"


def test_rrs_d1_ignored_when_m5_present():
    # D1 is negative but M5 is positive — gate should pass (M5 wins)
    r = gate_rrs_d1(rrs_d1=-1.76, rrs_m5=0.5, direction="long")
    assert r.passed is True


# ── gate_rvol ─────────────────────────────────────────────────────────────────

def test_rvol_passes_at_threshold():
    r = gate_rvol(1.20)
    assert r.passed is True


def test_rvol_passes_above_threshold():
    assert gate_rvol(2.5).passed is True


def test_rvol_fails_below_threshold():
    assert gate_rvol(0.90).passed is False


def test_rvol_no_data_when_none():
    r = gate_rvol(None)
    assert r.passed is None
    assert r.status == "no_data"


def test_rvol_no_data_when_nan():
    r = gate_rvol(float("nan"))
    assert r.passed is None
    assert r.status == "no_data"


def test_rvol_custom_threshold():
    assert gate_rvol(1.50, threshold=1.80).passed is False
    assert gate_rvol(1.90, threshold=1.80).passed is True


# ── gate_void ─────────────────────────────────────────────────────────────────

def test_void_long_passes_when_enough_air():
    highs = _highs([95.0, 96.0, 110.0])   # next resistance at 110 (+10% above 100)
    lows  = _lows([93.0, 94.0, 108.0])
    r = gate_void(price=100.0, daily_highs=highs, daily_lows=lows, direction="long")
    assert r.passed is True
    assert r.value == pytest.approx(10.0, rel=1e-3)


def test_void_long_fails_tight_resistance():
    # Resistance only 0.5% above price
    highs = _highs([100.5])
    lows  = _lows([98.0])
    r = gate_void(price=100.0, daily_highs=highs, daily_lows=lows, direction="long")
    assert r.passed is False


def test_void_long_passes_no_resistance():
    # No prior highs above price -> infinite void
    highs = _highs([90.0, 92.0, 95.0])
    lows  = _lows([88.0, 90.0, 93.0])
    r = gate_void(price=100.0, daily_highs=highs, daily_lows=lows, direction="long")
    assert r.passed is True
    assert r.value == pytest.approx(999.0)


def test_void_short_passes_when_enough_air():
    highs = _highs([103.0, 105.0])
    lows  = _lows([88.0, 89.0])   # nearest support = max(88, 89) = 89 => 11% below 100
    r = gate_void(price=100.0, daily_highs=highs, daily_lows=lows, direction="short")
    assert r.passed is True
    assert r.value == pytest.approx(11.0, rel=1e-3)


def test_void_short_fails_tight_support():
    highs = _highs([105.0])
    lows  = _lows([99.7])
    r = gate_void(price=100.0, daily_highs=highs, daily_lows=lows, direction="short")
    assert r.passed is False


# ── gate_market_align ─────────────────────────────────────────────────────────

def test_market_align_long_bullish_after_10():
    r = gate_market_align(_ts("2024-01-02 10:30"), MarketRegime.BULLISH, "long")
    assert r.passed is True


def test_market_align_long_bearish_after_10_fails():
    r = gate_market_align(_ts("2024-01-02 11:00"), MarketRegime.BEARISH, "long")
    assert r.passed is False


def test_market_align_short_bearish_after_10():
    r = gate_market_align(_ts("2024-01-02 14:00"), MarketRegime.BEARISH, "short")
    assert r.passed is True


def test_market_align_before_10_always_passes():
    r = gate_market_align(_ts("2024-01-02 09:45"), MarketRegime.BEARISH, "long")
    assert r.passed is True


def test_market_align_exactly_10_passes():
    r = gate_market_align(_ts("2024-01-02 10:00"), MarketRegime.BULLISH, "long")
    assert r.passed is True


def test_market_align_neutral_passes_long_after_10():
    # NEUTRAL no longer blocks longs — only BEARISH does
    r = gate_market_align(_ts("2024-01-02 10:01"), MarketRegime.NEUTRAL, "long")
    assert r.passed is True


def test_market_align_bearish_blocks_long_after_10():
    r = gate_market_align(_ts("2024-01-02 10:01"), MarketRegime.BEARISH, "long")
    assert r.passed is False


def test_market_align_bullish_blocks_short_after_10():
    r = gate_market_align(_ts("2024-01-02 10:01"), MarketRegime.BULLISH, "short")
    assert r.passed is False


def test_market_align_neutral_passes_short_after_10():
    # NEUTRAL no longer blocks shorts — only BULLISH does
    r = gate_market_align(_ts("2024-01-02 10:01"), MarketRegime.NEUTRAL, "short")
    assert r.passed is True
