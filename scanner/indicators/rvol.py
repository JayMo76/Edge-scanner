"""Relative Volume (RVOL).

For each 5-minute slot of the regular session, compute the 20-day average
volume for that slot.  RVOL = today's cumulative volume divided by the
sum of those slot averages up to the current time of day.

This makes RVOL time-of-day aware: heavy volume in the first 30 minutes
is not compared against the full-day average.
"""
import pandas as pd

_MARKET_OPEN_MINUTES = 9 * 60 + 30   # 9:30 ET = 570 minutes since midnight
_SESSION_MINUTES = 6 * 60 + 30       # 6.5 hour session = 390 minutes
_SLOT_MINUTES = 5


def build_volume_profile(bars_5m: pd.DataFrame) -> pd.Series:
    """Compute per-slot average volume from 20 days of 5-min bars.

    Args:
        bars_5m: UTC-indexed 5-min bar DataFrame with a `volume` column.
                 Should contain ~20 trading days of data.

    Returns:
        Series indexed by minutes-from-open (0, 5, 10, ..., 385),
        values = mean volume across all sessions at that slot.
    """
    et = bars_5m.copy()
    et.index = bars_5m.index.tz_convert("America/New_York")

    minutes_since_midnight = et.index.hour * 60 + et.index.minute
    slot = (minutes_since_midnight // 5) * 5 - _MARKET_OPEN_MINUTES

    et = et.copy()
    et["slot"] = slot.values
    session_bars = et[(et["slot"] >= 0) & (et["slot"] < _SESSION_MINUTES)]

    return session_bars.groupby("slot")["volume"].mean()


def compute_rvol(
    profile: pd.Series,
    cum_vol: float,
    minutes_from_open: int,
) -> float:
    """Current RVOL given the volume profile and today's cumulative volume.

    Numerator and denominator must cover the SAME elapsed interval. `cum_vol`
    runs up to `minutes_from_open`, so the expected volume does too: every fully
    elapsed 5-min slot, plus the slot in progress prorated by the minutes of it
    that have elapsed. Counting only completed slots (the old behaviour) made a
    stock trading at exactly its normal pace read 2.0x at 09:39, then snap back
    to 1.0x at 09:40, a sawtooth on every slot boundary.

    Args:
        profile:           output of build_volume_profile
        cum_vol:           shares traded today so far
        minutes_from_open: RTH minutes that `cum_vol` covers. After the 09:37
                           1-min bar closes that is 8 (09:30 through 09:37).
                           On a 5-min boundary no proration applies.

    Returns:
        RVOL ratio; NaN if profile is empty or nothing has elapsed.
    """
    if profile.empty or minutes_from_open <= 0:
        return float("nan")
    minutes_from_open = min(int(minutes_from_open), _SESSION_MINUTES)
    cur_slot = (minutes_from_open // _SLOT_MINUTES) * _SLOT_MINUTES
    expected = float(profile[profile.index < cur_slot].sum())
    into_slot = minutes_from_open - cur_slot
    if into_slot and cur_slot in profile.index:
        expected += float(profile.loc[cur_slot]) * into_slot / _SLOT_MINUTES
    if expected <= 0:
        return float("nan")
    return cum_vol / expected
