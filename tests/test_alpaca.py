"""Integration tests for AlpacaFeed — these hit the real Alpaca API.

Needs ALPACA_API_KEY and ALPACA_SECRET_KEY in .env (or the environment); skipped
without them.
Run with: pytest tests/test_alpaca.py -v
"""
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scanner.data.alpaca import AlpacaFeed   # loads .env, so the keys are visible below

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")),
    reason="integration test: needs Alpaca API keys")

# Shared date range used across tests — ask for ~2 weeks ending yesterday
_END = date.today() - timedelta(days=1)
_START = _END - timedelta(days=14)


def test_get_historical_daily_schema(tmp_path):
    """Fetch SPY and verify column names, UTC index, and no NaNs in OHLCV."""
    feed = AlpacaFeed(cache_dir=tmp_path)
    df = feed.get_historical_daily("SPY", _START, _END)

    assert not df.empty, "Expected at least some bars"
    required = {"open", "high", "low", "close", "volume"}
    assert required.issubset(df.columns), f"Missing columns: {required - set(df.columns)}"
    assert df.index.tz is not None, "Index must be UTC timezone-aware"
    assert df[list(required)].notna().all().all(), "NaNs found in OHLCV columns"


def test_get_historical_daily_cache_written(tmp_path):
    """Cache parquet file must exist after a successful fetch."""
    feed = AlpacaFeed(cache_dir=tmp_path)
    feed.get_historical_daily("AAPL", _START, _END)
    assert (tmp_path / "AAPL.parquet").exists()


def test_get_historical_daily_second_call_uses_cache(tmp_path):
    """Second call for a fresh symbol must not hit the Alpaca API."""
    feed = AlpacaFeed(cache_dir=tmp_path)

    # Populate cache
    feed.get_historical_daily("MSFT", _START, _END)

    # Second call — client.get_stock_bars must not be invoked
    with patch.object(feed._client, "get_stock_bars") as mock_bars:
        feed.get_historical_daily("MSFT", _START, _END)
        mock_bars.assert_not_called()


def test_subscribe_minute_bars_calls_stream(tmp_path):
    """subscribe_minute_bars should create a StockDataStream and call run()."""
    from unittest.mock import MagicMock, patch

    feed = AlpacaFeed(cache_dir=tmp_path)
    mock_stream = MagicMock()

    # StockDataStream is a lazy import inside the method, so patch at the source module.
    with patch("alpaca.data.live.StockDataStream", return_value=mock_stream):
        feed.subscribe_minute_bars(["SPY", "AAPL"], lambda bar: None)

    mock_stream.subscribe_bars.assert_called_once()
    mock_stream.run.assert_called_once()


def test_get_snapshot_parses_response(tmp_path):
    """get_snapshot should call get_stock_snapshot and extract price/bid/ask."""
    from unittest.mock import MagicMock, patch

    feed = AlpacaFeed(cache_dir=tmp_path)

    mock_trade = MagicMock()
    mock_trade.price = 182.5
    mock_quote = MagicMock()
    mock_quote.bid_price = 182.48
    mock_quote.ask_price = 182.52

    mock_snap = MagicMock()
    mock_snap.latest_trade = mock_trade
    mock_snap.latest_quote = mock_quote

    with patch.object(feed._client, "get_stock_snapshot", return_value={"AAPL": mock_snap}):
        result = feed.get_snapshot(["AAPL"])

    assert "AAPL" in result
    assert result["AAPL"]["price"]  == pytest.approx(182.5)
    assert result["AAPL"]["bid"]    == pytest.approx(182.48)
    assert result["AAPL"]["ask"]    == pytest.approx(182.52)
