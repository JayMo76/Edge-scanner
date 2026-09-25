"""Chart quality score.

Composite 0-100 score over the last 20 daily bars combining:
  - Choppiness (50%): decisive candles (high body/range ratio)
  - Extension  (50%): price not over-extended beyond EMA8

Gappiness (overnight gaps) was removed — gaps are news events unrelated
to how a stock trades intraday and unfairly penalise catalyst names.

Weights and thresholds are [TUNABLE] starting points.
"""
import pandas as pd

_WINDOW = 20          # daily bars
_BODY_RATIO_MIN = 0.0 # 0 = completely indecisive
_EXT_MAX_ATR = 4.0    # 4× ATR -> extension score = 0


def chart_quality(
    daily: pd.DataFrame,
    ema8: pd.Series,
    atr: pd.Series,
    window: int = _WINDOW,
) -> float:
    """Return a 0-100 quality score for the stock's daily chart.

    Args:
        daily: daily OHLCV DataFrame (aligned index)
        ema8:  daily EMA(8) series (same index as daily)
        atr:   daily ATR series (same index as daily)
        window: number of recent bars to analyse

    Returns:
        Composite quality score 0-100 (higher = cleaner chart).
        Returns 50.0 when insufficient history.
    """
    if len(daily) < window:
        return 50.0

    recent = daily.iloc[-window:]

    # ── Choppiness ───────────────────────────────────────────────────────
    body = (recent["close"] - recent["open"]).abs()
    rng = (recent["high"] - recent["low"]).replace(0, float("nan"))
    body_ratio = (body / rng).mean()
    choppiness_score = float(body_ratio) * 100.0

    # ── Extension ────────────────────────────────────────────────────────
    last_close = float(daily["close"].iloc[-1])
    last_ema8 = float(ema8.iloc[-1])
    last_atr = float(atr.iloc[-1])
    if last_atr == 0 or pd.isna(last_atr) or pd.isna(last_ema8):
        ext_atr = 0.0
    else:
        ext_atr = abs(last_close - last_ema8) / last_atr
    extension_score = max(0.0, 100.0 * (1.0 - ext_atr / _EXT_MAX_ATR))

    quality = 0.5 * choppiness_score + 0.5 * extension_score
    return round(min(100.0, max(0.0, quality)), 1)
