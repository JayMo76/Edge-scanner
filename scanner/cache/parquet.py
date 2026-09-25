from datetime import date
from pathlib import Path

import pandas as pd

_COLS = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]


def _path(symbol: str, cache_dir: Path) -> Path:
    return Path(cache_dir) / f"{symbol}.parquet"


def load(symbol: str, cache_dir: Path) -> pd.DataFrame | None:
    p = _path(symbol, cache_dir)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def save(symbol: str, df: pd.DataFrame, cache_dir: Path) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    df.to_parquet(_path(symbol, cache_dir))


def is_fresh(symbol: str, cache_dir: Path, as_of: date) -> bool:
    """Return True if the cached data covers through `as_of` (inclusive)."""
    df = load(symbol, cache_dir)
    if df is None or df.empty:
        return False
    latest = df.index.max()
    latest_date = latest.date() if hasattr(latest, "date") else latest
    return latest_date >= as_of
