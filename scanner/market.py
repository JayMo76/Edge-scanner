"""Market regime classification.

SPY VWAP position determines overall market direction:
  BULLISH  — SPY price > VWAP by more than the neutral band
  BEARISH  — SPY price < VWAP by more than the neutral band
  NEUTRAL  — price within the band; mixed signals, gates should be cautious
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

_NEUTRAL_BAND = 0.001  # 0.1% either side of VWAP = neutral


class MarketRegime(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


def classify_market(
    spy_price: float,
    spy_vwap: Optional[float],
) -> MarketRegime:
    """Classify market regime from SPY price vs session VWAP.

    Args:
        spy_price: current SPY price (last trade / bar close)
        spy_vwap:  SPY session VWAP; None before the first bar

    Returns:
        MarketRegime enum value.
    """
    if spy_vwap is None or spy_vwap <= 0:
        return MarketRegime.NEUTRAL
    ratio = (spy_price - spy_vwap) / spy_vwap
    if ratio > _NEUTRAL_BAND:
        return MarketRegime.BULLISH
    if ratio < -_NEUTRAL_BAND:
        return MarketRegime.BEARISH
    return MarketRegime.NEUTRAL
