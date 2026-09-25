"""Real Relative Strength (RRS): volatility-adjusted relative strength vs SPY.

NOT RSI. NOT simple percent-change vs SPY.
Volatility-adjusted: a stock only gets credit for strength beyond what its
own ATR would predict given how much SPY moved.

Formula (per bar):
    power_index       = roll_move_spy / atr_spy
    expected_move     = power_index * atr_stock
    RRS               = (roll_move_stock - expected_move) / atr_stock

Production version = rolling SMA of per-bar RRS over `length` periods,
which penalises one-candle spikes and rewards sustained institutional flow.
"""
import pandas as pd

from scanner.indicators.atr import wilder_atr

# Default lookback periods
D1_LENGTH: int = 5   # 5 daily bars  = 1 trading week
M5_LENGTH: int = 12  # 12 five-min bars = 1 hour

# GICS sector ETF map: stock -> sector ETF symbol resolved at warmup
SECTOR_ETF: dict[str, str] = {
    "XLE": "XLE",   # Energy
    "XLU": "XLU",   # Utilities
    "XLK": "XLK",   # Technology
    "XLB": "XLB",   # Materials
    "XLP": "XLP",   # Consumer Staples
    "XLY": "XLY",   # Consumer Discretionary
    "XLC": "XLC",   # Communications
    "XLV": "XLV",   # Healthcare
    "XLF": "XLF",   # Financials
    "XLRE": "XLRE", # Real Estate
    "XLI": "XLI",   # Industrials
}


def _rrs_formula(
    roll_move_stock: float,
    roll_move_bench: float,
    atr_stock: float,
    atr_bench: float,
) -> float:
    """Scalar RRS formula, exposed for unit testing and the worked-example regression tests.

    Args:
        roll_move_stock: close[now] - close[now-length] for the stock
        roll_move_bench: same for the benchmark (SPY or sector ETF)
        atr_stock:       Wilder ATR of the stock over `length` periods
        atr_bench:       Wilder ATR of the benchmark over `length` periods

    Returns:
        RRS value (positive = relative strength, negative = relative weakness)
    """
    power_index = roll_move_bench / atr_bench
    expected_move = power_index * atr_stock
    return (roll_move_stock - expected_move) / atr_stock


def rrs_raw(stock: pd.DataFrame, bench: pd.DataFrame, length: int) -> pd.Series:
    """Per-bar RRS with no smoothing.

    Both DataFrames must have columns: high, low, close.
    They are inner-joined on their index before computation so gaps in
    either series don't corrupt the alignment.

    Returns a Series indexed like the intersection of stock and bench.
    """
    stock, bench = stock.align(bench, join="inner", axis=0)

    atr_s = wilder_atr(stock["high"], stock["low"], stock["close"], length)
    atr_b = wilder_atr(bench["high"], bench["low"], bench["close"], length)

    roll_s = stock["close"] - stock["close"].shift(length)
    roll_b = bench["close"] - bench["close"].shift(length)

    power = roll_b / atr_b
    expected = power * atr_s
    return (roll_s - expected) / atr_s


def rrs(stock: pd.DataFrame, bench: pd.DataFrame, length: int) -> pd.Series:
    """Rolling-average RRS — the production signal.

    SMA of rrs_raw over `length` periods.  A single large candle decays
    back toward zero once it leaves the window; sustained flow stays elevated.

    First (2*length - 1) values will be NaN.
    """
    return rrs_raw(stock, bench, length).rolling(length).mean()
