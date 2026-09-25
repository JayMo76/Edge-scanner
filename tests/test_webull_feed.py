from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from scanner.data.webull import WebullFeed


class StubMarket:
    def __init__(self):
        self.calls = []

    def get_batch_history_bar(self, symbols, category, timespan, **kwargs):
        self.calls.append((symbols, timespan, kwargs))
        start = kwargs.get("start_time") or 1700000000000
        return {"data": [{"symbol": symbols[0], "bars": [{
            "time": str(start), "open": "1", "high": "1.2", "low": "0.9",
            "close": "1.1", "volume": "100", "vwap": "1.05"}]}]}

    def get_snapshot(self, symbols, category, **kwargs):
        return {"data": [{"symbol": sym, "price": "1.2"} for sym in symbols]}


def test_webull_market_data_is_normalized_without_alpaca():
    market = StubMarket()
    feed = WebullFeed(data_client=SimpleNamespace(market_data=market))
    got = feed.get_historical_daily("LHSW", date(2023, 11, 14), date(2023, 11, 15))
    assert isinstance(got.index, pd.DatetimeIndex)
    assert got.index.tz is not None
    assert list(got.columns) == ["open", "high", "low", "close", "volume", "vwap", "trade_count"]
    assert feed.get_snapshot(["LHSW"]) == {"LHSW": {"price": 1.2}}
    assert all(span == "D" for _, span, _ in market.calls)


def test_large_watchlist_is_rejected_before_requests():
    market = StubMarket()
    feed = WebullFeed(data_client=SimpleNamespace(market_data=market))
    with pytest.raises(ValueError, match="at most 40"):
        feed.subscribe_minute_bars([f"T{i}" for i in range(41)], lambda _: None)
    assert not market.calls


def test_official_webull_bar_response_shape():
    from scanner.data.webull import _frame, _rows
    payload = [{"symbol": "LHSW", "result": [{
        "time": "2026-09-22T09:00:09.945+0000", "open": "1.0", "high": "1.2",
        "low": "0.9", "close": "1.1", "volume": "125000"}]}]
    frame = _frame(_rows(payload, "LHSW"))
    assert len(frame) == 1
    assert frame.iloc[0]["volume"] == 125000
