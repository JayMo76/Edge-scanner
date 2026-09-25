"""History from Alpaca must be split-adjusted, and cached apart from raw bars."""
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
from alpaca.data.enums import Adjustment

from scanner.data import alpaca as A


def test_history_requests_are_split_adjusted(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    feed = A.AlpacaFeed(cache_dir=tmp_path / "d", intraday_cache_dir=tmp_path / "m")
    feed._client = MagicMock()
    feed._client.get_stock_bars.return_value = MagicMock(df=pd.DataFrame())
    feed.get_historical_daily("AAA", date(2026, 1, 5), date(2026, 1, 20))
    req = feed._client.get_stock_bars.call_args.args[0]
    assert req.adjustment == Adjustment.SPLIT


def test_the_cache_folders_name_the_adjustment():
    assert A._DEFAULT_DAILY_CACHE.name == "daily_split" and A._DEFAULT_INTRADAY_CACHE.name == "5m_split"
