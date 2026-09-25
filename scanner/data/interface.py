from abc import ABC, abstractmethod
from datetime import date
from typing import Callable, Literal

import pandas as pd

Timeframe = Literal["1Min", "5Min", "15Min", "30Min", "1Hour", "4Hour", "1Week", "Day"]


class DataFeed(ABC):
    """Abstract data provider. Swap Alpaca for Polygon without touching any signal code."""

    @abstractmethod
    def get_historical_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return OHLCV daily bars as a UTC-indexed DataFrame.

        Index: DatetimeIndex (UTC, tz-aware, one entry per trading day)
        Columns: open, high, low, close, volume, vwap, trade_count
        """

    @abstractmethod
    def get_historical_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return OHLCV bars for an intraday timeframe as a UTC-indexed DataFrame.

        Index: DatetimeIndex (UTC, tz-aware)
        Columns: open, high, low, close, volume, vwap, trade_count
        Used for building the RVOL volume profile (20 days of 5-min bars at warmup).
        """

    @abstractmethod
    def subscribe_minute_bars(self, symbols: list[str], callback: Callable[[dict], None]) -> None:
        """Start streaming 1-min bars; invoke callback(bar) on each bar close.

        bar dict keys: symbol, timestamp (UTC), open, high, low, close, volume, vwap
        """

    @abstractmethod
    def get_snapshot(self, symbols: list[str]) -> dict[str, dict]:
        """Return the latest quote/trade snapshot keyed by symbol."""

    def stop_stream(self) -> None:
        """Stop the live stream started by subscribe_minute_bars.

        Default is a no-op; override in implementations that own the stream
        lifecycle (e.g. AlpacaFeed).
        """
