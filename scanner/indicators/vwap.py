import pandas as pd


def session_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Running session VWAP computed from bar-level data.

    Typical price = (high + low + close) / 3
    VWAP = cumsum(tp * volume) / cumsum(volume)

    The index must span a single trading session — call cumsum from bar 0.
    Resets are handled externally by slicing per-session before calling.
    """
    tp = (high + low + close) / 3.0
    cum_tp_vol = (tp * volume).cumsum()
    cum_vol = volume.cumsum()
    return cum_tp_vol / cum_vol


def vwap_update(
    prev_num: float,
    prev_den: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> tuple[float, float, float]:
    """Incremental VWAP update for live processing.

    Returns (new_numerator, new_denominator, new_vwap).
    Seed with prev_num=0, prev_den=0 at session open.
    """
    tp = (high + low + close) / 3.0
    num = prev_num + tp * volume
    den = prev_den + volume
    vwap = num / den if den > 0 else float("nan")
    return num, den, vwap
