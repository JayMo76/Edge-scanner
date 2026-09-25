import pandas as pd


def ema(close: pd.Series, span: int) -> pd.Series:
    """Standard EMA (alpha = 2/(span+1), adjust=False)."""
    return close.ewm(span=span, adjust=False).mean()


def sma(close: pd.Series, length: int) -> pd.Series:
    """Simple moving average over `length` periods."""
    return close.rolling(length).mean()


def ema_update(prev: float | None, price: float, span: int) -> float:
    """Incremental EMA update for live bar-by-bar processing.

    Seeds from `price` if `prev` is None (first bar of session).
    """
    if prev is None:
        return price
    alpha = 2.0 / (span + 1)
    return alpha * price + (1.0 - alpha) * prev
