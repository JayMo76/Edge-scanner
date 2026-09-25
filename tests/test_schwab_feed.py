"""Tests for SchwabFeed that need no credentials and no network.

Covers the two things most likely to break silently: candle parsing (schema
must match AlpacaFeed exactly) and CHART_EQUITY stream decoding (Schwab's own
docs have the field order wrong, so this pins the corrected order).
"""
import pandas as pd
import pytest

from scanner.data import FEEDS, make_feed
from scanner.data.interface import DataFeed
from scanner.data.schwab import SchwabFeed

_ALPACA_COLS = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]


def test_schwab_feed_satisfies_datafeed():
    assert issubclass(SchwabFeed, DataFeed)
    assert not SchwabFeed.__abstractmethods__


def test_schwab_has_alpaca_parity_methods():
    """run_live.py and scanner/api.py call these beyond the ABC."""
    for m in ("get_bars_range", "get_todays_bars", "get_todays_bars_multi", "stop_stream"):
        assert hasattr(SchwabFeed, m), m


def test_candles_to_df_matches_alpaca_schema():
    df = SchwabFeed._candles_to_df({"candles": [
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100, "datetime": 1755792000000},
        {"open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 200, "datetime": 1755792060000},
    ]})
    assert list(df.columns) == _ALPACA_COLS
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert len(df) == 2
    # Schwab supplies neither of these; they must exist as NaN, not be absent.
    assert df["vwap"].isna().all() and df["trade_count"].isna().all()


def test_candles_to_df_empty_is_well_formed():
    df = SchwabFeed._candles_to_df({"candles": []})
    assert df.empty and list(df.columns) == _ALPACA_COLS


def test_make_feed_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown feed"):
        make_feed("polygon")


def test_make_feed_names():
    assert FEEDS == ("alpaca", "schwab")


def test_chart_equity_field_order():
    """Field order is 2=open 3=high 4=low 5=close 6=volume 7=time (epoch ms).
    Schwab's published docs list it differently and are wrong."""
    got = []
    SchwabFeed.handle_message(
        '{"data":[{"service":"CHART_EQUITY","content":['
        '{"key":"AAPL","2":10.0,"3":12.0,"4":9.0,"5":11.0,"6":5000,"7":1755792000000}]}]}',
        got.append)
    assert len(got) == 1
    bar = got[0]
    assert bar["symbol"] == "AAPL"
    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (10.0, 12.0, 9.0, 11.0)
    assert bar["volume"] == 5000
    assert bar["timestamp"] == pd.Timestamp(1755792000000, unit="ms", tz="UTC")


def test_stream_ignores_other_services_and_junk():
    got = []
    SchwabFeed.handle_message(
        '{"data":[{"service":"LEVELONE_EQUITIES","content":[{"key":"AAPL"}]}]}', got.append)
    SchwabFeed.handle_message("not json at all", got.append)
    SchwabFeed.handle_message('{"response":[{"command":"SUBS"}]}', got.append)
    SchwabFeed.handle_message(None, got.append)
    assert got == []


def test_stream_skips_malformed_bar_but_keeps_good_ones():
    """One bad payload must not kill the stream for the rest of the batch."""
    got = []
    SchwabFeed.handle_message(
        '{"data":[{"service":"CHART_EQUITY","content":['
        '{"key":"BAD","2":1.0},'
        '{"key":"GOOD","2":1.0,"3":2.0,"4":0.5,"5":1.5,"6":10,"7":1755792000000}]}]}',
        got.append)
    assert [b["symbol"] for b in got] == ["GOOD"]


def test_multiple_bars_in_one_message():
    got = []
    SchwabFeed.handle_message(
        '{"data":[{"service":"CHART_EQUITY","content":['
        '{"key":"AAPL","2":1.0,"3":2.0,"4":0.5,"5":1.5,"6":10,"7":1755792000000},'
        '{"key":"MSFT","2":3.0,"3":4.0,"4":2.5,"5":3.5,"6":20,"7":1755792000000}]}]}',
        got.append)
    assert [b["symbol"] for b in got] == ["AAPL", "MSFT"]


# ── Schwab price-history parameter validity ───────────────────────────────────
# These run schwabdev's OWN validator over every timeframe this feed offers.
# Schwab rejects an unstated periodType with 400 Bad Request (it silently
# defaults to "day", which only permits frequencyType="minute"), so this
# catches the mistake offline instead of costing an auth cycle to discover.

def test_every_timeframe_is_a_valid_schwab_combination():
    from datetime import datetime
    from schwabdev.validation import _Validator
    from scanner.data.schwab import _FREQ

    v = _Validator(enabled=True)
    for tf, (ptype, ftype, freq) in _FREQ.items():
        v._v_price_history(
            symbol="SPY", periodType=ptype, period=None,
            frequencyType=ftype, frequency=freq,
            startDate=datetime(2026, 1, 1), endDate=datetime(2026, 2, 1),
            needExtendedHoursData=True, needPreviousClose=None,
        )   # raises ValueError on an invalid pairing


def test_period_type_is_always_supplied():
    """The 400 that started this: periodType omitted entirely."""
    from scanner.data.schwab import _FREQ
    assert all(len(t) == 3 and t[0] for t in _FREQ.values())


def test_minute_timeframes_use_day_period_type():
    from scanner.data.schwab import _FREQ
    for tf in ("1Min", "5Min", "15Min", "30Min"):
        ptype, ftype, freq = _FREQ[tf]
        assert (ptype, ftype) == ("day", "minute"), tf
        assert freq in {1, 5, 10, 15, 30}, tf


def test_daily_and_weekly_do_not_use_day_period_type():
    from scanner.data.schwab import _FREQ
    for tf in ("Day", "1Week"):
        ptype, ftype, _ = _FREQ[tf]
        assert ptype != "day", f"{tf}: periodType 'day' only allows 'minute'"
