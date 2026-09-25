"""Webull OpenAPI market data adapter for a bounded Edge Scanner watchlist.

The maintained SDK exposes batched historical bars and snapshots, but not the
unbounded Alpaca websocket or a stock-news endpoint. Missing data fails closed.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from scanner.data.interface import DataFeed, Timeframe

log = logging.getLogger(__name__)
_COLUMNS = ("open", "high", "low", "close", "volume", "vwap", "trade_count")
_SPANS = {"1Min": "M1", "5Min": "M5", "15Min": "M15", "30Min": "M30",
          "1Hour": "M60", "4Hour": "M240", "1Week": "W", "Day": "D"}
_ET = ZoneInfo("America/New_York")


def _payload(response):
    status = getattr(response, "status_code", 200)
    if not 200 <= status < 300:
        raise RuntimeError(f"Webull HTTP {status}")
    value = response.json() if hasattr(response, "json") else response
    if isinstance(value, dict):
        if value.get("success") is False or value.get("error"):
            raise RuntimeError("Webull returned a data error")
        for key in ("data", "result", "items", "list"):
            if isinstance(value.get(key), (list, dict)):
                value = value[key]
                break
    return value


def _rows(payload, symbol):
    if isinstance(payload, dict):
        if isinstance(payload.get(symbol), list):
            return payload[symbol]
        if str(payload.get("symbol", "")).upper() == symbol:
            for key in ("bars", "result", "data"):
                if isinstance(payload.get(key), list):
                    return payload[key]
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict) and str(entry.get("symbol", "")).upper() == symbol:
                for key in ("bars", "data", "result"):
                    if isinstance(entry.get(key), list):
                        return entry[key]
        return [row for row in payload if isinstance(row, dict) and "open" in row and "close" in row]
    return []


def _frame(rows):
    records = []
    for row in rows:
        try:
            raw = row.get("time", row.get("timestamp", row.get("t")))
            if raw is None:
                continue
            stamp = pd.to_datetime(float(raw), unit="ms" if float(raw) > 10**10 else "s", utc=True) if str(raw).replace(".", "", 1).isdigit() else pd.to_datetime(raw, utc=True)
            values = {key: float(row[key]) for key in ("open", "high", "low", "close", "volume")}
            if stamp is pd.NaT or values["volume"] < 0 or values["low"] > values["high"]:
                continue
            records.append({"timestamp": stamp, **values,
                            "vwap": float(row["vwap"]) if row.get("vwap") not in (None, "") else float("nan"),
                            "trade_count": float("nan")})
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
    if not records:
        return pd.DataFrame(columns=_COLUMNS, index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
    return pd.DataFrame(records).set_index("timestamp").sort_index().loc[:, list(_COLUMNS)]


class WebullFeed(DataFeed):
    def __init__(self, *, data_client=None, max_symbols: int = 40, poll_seconds: float = 60):
        self.max_symbols = max_symbols
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        if data_client is not None:
            self._client = data_client
            return
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient
        key, secret = os.getenv("WEBULL_APP_KEY"), os.getenv("WEBULL_APP_SECRET")
        if not key or not secret:
            raise ValueError("WEBULL_APP_KEY and WEBULL_APP_SECRET are required")
        api = ApiClient(key, secret, os.getenv("WEBULL_REGION", "us"))
        token_dir = os.getenv("WEBULL_TOKEN_DIR")
        if token_dir:
            api.set_token_dir(token_dir)
        self._client = DataClient(api)

    def _history(self, symbol: str, timeframe: Timeframe, start: date, end: date):
        if timeframe not in _SPANS:
            raise ValueError(f"Unsupported Webull timeframe: {timeframe}")
        # Partition to stay below Webull's 1200-bar response cap. Closed daily
        # windows avoid crossing into the next chunk's first bar.
        step = 1 if timeframe == "1Min" else 4 if timeframe == "5Min" else 90
        parts = []
        cursor = start
        while cursor <= end:
            last = min(cursor + timedelta(days=step - 1), end)
            result = self._client.market_data.get_batch_history_bar(
                symbols=[symbol], category="US_STOCK", timespan=_SPANS[timeframe],
                count="1200", start_time=int(pd.Timestamp(cursor, tz=_ET).timestamp() * 1000),
                end_time=int(pd.Timestamp(last + timedelta(days=1), tz=_ET).timestamp() * 1000) - 1,
                trading_sessions="PRE,RTH,ATH" if timeframe != "Day" else None,
            )
            parts.append(_frame(_rows(_payload(result), symbol)))
            cursor = last + timedelta(days=1)
        frame = pd.concat(parts).sort_index() if parts else _frame([])
        frame = frame[~frame.index.duplicated(keep="last")]
        trading_dates = frame.index.tz_convert(_ET).date
        return frame[(trading_dates >= start) & (trading_dates <= end)]

    def get_historical_daily(self, symbol, start, end):
        return self._history(symbol, "Day", start, end)

    def get_historical_bars(self, symbol, timeframe, start, end):
        return self._history(symbol, timeframe, start, end)

    def get_bars_range(self, symbol, timeframe, start, end):
        return self._history(symbol, timeframe, start, end)

    def _multi(self, symbols, timeframe, start, end, progress=None):
        out = {}
        for index, symbol in enumerate(dict.fromkeys(symbols), 1):
            try:
                frame = self._history(symbol, timeframe, start, end)
                if not frame.empty:
                    out[symbol] = frame
            except Exception as exc:
                log.warning("Webull history missing for %s: %s", symbol, exc)
            if progress:
                progress(index, len(symbols))
        return out

    def get_historical_daily_multi(self, symbols, start, end, workers=0, progress=None):
        return self._multi(symbols, "Day", start, end, progress)

    def get_historical_bars_multi(self, symbols, timeframe, start, end, workers=0, progress=None):
        return self._multi(symbols, timeframe, start, end, progress)

    def get_todays_bars_multi(self, symbols, timeframe="1Min"):
        today = pd.Timestamp.now(tz=_ET).date()
        result = self._multi(symbols, timeframe, today, today)
        # Never seed the current unfinished bar into alert calculations.
        now = pd.Timestamp.now(tz="UTC")
        size = pd.Timedelta(minutes=1 if timeframe == "1Min" else 5)
        return {sym: frame[frame.index + size <= now - pd.Timedelta(seconds=5)]
                for sym, frame in result.items()}

    def get_snapshot(self, symbols):
        result = {}
        for i in range(0, len(symbols), 20):
            batch = symbols[i:i + 20]
            data = _payload(self._client.market_data.get_snapshot(batch, "US_STOCK", extend_hour_required=True))
            entries = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
            for row in entries:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol", "")).upper()
                try:
                    price = float(row.get("extend_hour_last_price") or row.get("price") or row.get("last_price"))
                    if symbol in batch and price > 0:
                        result[symbol] = {"price": price}
                except (ValueError, TypeError):
                    continue
        return result

    def subscribe_minute_bars(self, symbols: list[str], callback: Callable[[dict], None]):
        if len(symbols) > self.max_symbols:
            raise ValueError(f"Webull polling supports at most {self.max_symbols} symbols; got {len(symbols)}")
        seen = {}
        self._stop.clear()
        while not self._stop.is_set():
            try:
                now = pd.Timestamp.now(tz="UTC")
                for offset in range(0, len(symbols), 20):
                    batch = symbols[offset:offset + 20]
                    response = self._client.market_data.get_batch_history_bar(
                        batch, "US_STOCK", "M1", count="3", real_time_required=True,
                        trading_sessions="PRE,RTH,ATH")
                    payload = _payload(response)
                    for symbol in batch:
                        frame = _frame(_rows(payload, symbol))
                        for stamp, bar in frame.iterrows():
                            if stamp + pd.Timedelta(minutes=1) > now - pd.Timedelta(seconds=5):
                                continue  # only closed bars
                            if stamp <= seen.get(symbol, pd.Timestamp(0, tz="UTC")):
                                continue
                            seen[symbol] = stamp
                            callback({"symbol": symbol, "timestamp": stamp, **{k: float(bar[k]) for k in ("open", "high", "low", "close", "volume")}})
            except Exception:
                log.exception("Webull bar poll failed; no synthetic bars emitted")
            self._stop.wait(self.poll_seconds)

    def stop_stream(self):
        self._stop.set()
