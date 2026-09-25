"""Shared entry-trigger helpers.

Holds the HOD / LOD breakout test the system setups use as an entry trigger.
Composable triggers for custom setups live in scanner/trigger_catalog.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class TriggerResult:
    fired: bool
    name: str
    value: float  # numeric context (EMA spread, breakout %, etc.)


def trigger_hod_breakout(
    high: float,
    low: float,
    prev_hod: Optional[float],
    prev_lod: Optional[float],
    direction: str,
) -> TriggerResult:
    """New session high (long) or new session low (short).

    Long:  current bar's high exceeds the prior high-of-day.
    Short: current bar's low is below the prior low-of-day.

    Returns no-fire on the first bar of the session (no prior HOD/LOD yet).
    value = magnitude of the breakout in points.
    """
    if direction == "long":
        if prev_hod is None:
            return TriggerResult(fired=False, name="hod_breakout", value=math.nan)
        fired = high > prev_hod
        value = round(high - prev_hod, 4) if fired else 0.0
    else:
        if prev_lod is None:
            return TriggerResult(fired=False, name="hod_breakout", value=math.nan)
        fired = low < prev_lod
        value = round(prev_lod - low, 4) if fired else 0.0
    return TriggerResult(fired=fired, name="hod_breakout", value=value)
