"""Shared gates the universe conditions use: relative strength vs SPY (5-min
RRS), relative volume, clear air (void) to the next 60-day level, and market
alignment. Each returns a GateResult(passed, value, status)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from scanner.market import MarketRegime
from scanner.settings import settings as S


# One named check with its outcome, as shown in the setup check window and
# recorded per setup in the settings stats.
@dataclass
class GateCheck:
    name: str
    passed: bool
    value: Optional[float]
    reason: str
    # Non-mandatory checks are recorded and shown, but do NOT block an alert.
    # Used for signals that could not be confirmed as independent edges
    # (e.g. an informational momentum check inside a system setup).
    mandatory: bool = True


# ── Thresholds: CODE DEFAULTS. Live values are S.GATE_* (scanner/settings.py),
# editable in the dashboard (Config > Gates). ───────────────────────────────

_RVOL_MIN: float = 1.00          # minimum RVOL
_VOID_MIN_PCT: float = 1.0       # minimum % clear air for void gate
_RRS_WARMUP_5M_BARS: int = 12    # 5-min bars a symbol must have before no_data M5 RRS blocks
_MARKET_OPEN_HOUR_ET: int = 10   # market alignment gate not active before 10:00 ET
_MARKET_OPEN_MINUTE_ET: int = 0



# ── Result containers ─────────────────────────────────────────────────────────

@dataclass
class GateResult:
    passed: Optional[bool]           # True=pass, False=fail, None=no_data
    value: Optional[float | bool]
    status: str = "ok"               # "ok" or "no_data"


def gate_rrs_d1(
    rrs_d1: float,
    rrs_m5: Optional[float],
    direction: str,
    bars_5m_count: int = 0,
) -> GateResult:
    """RRS gate: uses intraday M5 RRS only — no D1 fallback.

    Before the symbol has accumulated _RRS_WARMUP_5M_BARS five-minute bars,
    no_data passes — bars are still building up (including after a mid-session
    restart, which resets intraday bar history to zero).
    After that threshold, no_data blocks — missing M5 RRS indicates a data
    gap, not normal startup, so alerts are suppressed to prevent weak or
    untracked stocks from generating false positives.
    D1 is retained as a display/scoring metric but does not affect gating.
    """
    if rrs_m5 is None or (isinstance(rrs_m5, float) and math.isnan(rrs_m5)):
        if bars_5m_count >= int(S.GATE_RRS_WARMUP_5M_BARS):
            return GateResult(passed=False, value=None, status="rrs_unavailable")
        return GateResult(passed=None, value=None, status="no_data")
    if direction == "long":
        return GateResult(passed=rrs_m5 > 0, value=round(rrs_m5, 4))
    return GateResult(passed=rrs_m5 < 0, value=round(rrs_m5, 4))


def gate_rvol(rvol: Optional[float], threshold: Optional[float] = None) -> GateResult:
    """Relative volume must meet or exceed threshold.

    Returns no_data (blocking) when the volume profile is not yet available.
    Alerts are suppressed until RVOL can actually be measured.
    """
    if rvol is None or math.isnan(rvol):
        return GateResult(passed=None, value=None, status="no_data")
    thr = S.GATE_RVOL_MIN if threshold is None else threshold
    return GateResult(passed=rvol >= thr, value=round(rvol, 2))


def gate_void(
    price: float,
    daily_highs: pd.Series,
    daily_lows: pd.Series,
    direction: str,
    min_pct: Optional[float] = None,
) -> GateResult:
    """Check for clear air (void) between price and the nearest resistance/support.

    For longs: find the nearest prior daily high *above* price.
    For shorts: find the nearest prior daily low *below* price.
    The void must be >= min_pct% of price for the gate to pass.

    If no level exists in that direction the void is considered infinite (pass).
    """
    if direction == "long":
        levels = daily_highs[daily_highs > price]
        if levels.empty:
            return GateResult(passed=True, value=999.0)
        nearest = float(levels.min())
        pct = (nearest - price) / price * 100.0
    else:
        levels = daily_lows[daily_lows < price]
        if levels.empty:
            return GateResult(passed=True, value=999.0)
        nearest = float(levels.max())
        pct = (price - nearest) / price * 100.0

    return GateResult(passed=pct >= (S.GATE_VOID_MIN_PCT if min_pct is None else min_pct), value=round(pct, 2))


def gate_market_align(
    timestamp: pd.Timestamp,
    regime: MarketRegime,
    direction: str,
) -> GateResult:
    """Market must not be against trade direction after 10:00 ET.

    LONG blocked only when market is explicitly BEARISH.
    SHORT blocked only when market is explicitly BULLISH.
    NEUTRAL regime allows both directions (range-bound day).

    Before 10:00 ET the gate is disabled because early-session VWAP is unreliable.
    """
    et = timestamp.tz_convert("America/New_York")
    is_after_10 = (et.hour * 60 + et.minute) >= int(S.GATE_MARKET_ALIGN_FROM)

    if not is_after_10:
        return GateResult(passed=True, value=regime.value)

    if direction == "long":
        passed = regime != MarketRegime.BEARISH   # allow bullish or neutral
    else:
        passed = regime != MarketRegime.BULLISH   # allow bearish or neutral

    return GateResult(passed=passed, value=regime.value)
