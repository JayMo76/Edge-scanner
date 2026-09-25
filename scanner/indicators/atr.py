import pandas as pd


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Wilder's Average True Range.

    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    Smoothed with Wilder's EMA: alpha = 1/length, seeded from the first bar.
    First (length-1) values are NaN (min_periods enforced).
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
