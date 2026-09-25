"""The suggested stop every setup alert carries: the low (long) or high (short)
of the last STOP_BARS one-minute bars, including the signal bar."""
from __future__ import annotations

from typing import Optional

from scanner.settings import settings as S
from scanner.state import SymbolState


def compute_stop(state: SymbolState, bar: dict, direction: str) -> tuple[Optional[float], Optional[float]]:
    """Stop = low (long) / high (short) of the last STOP_BARS 1-min bars including this one.
    Returns (stop_price, stop_pct). stop_pct is abs distance as % of price."""
    bars = state.last_1m[-int(S.STOP_BARS):]
    if not bars:
        return None, None
    price = bar["close"]
    if direction == "long":
        stop = min(b["low"] for b in bars)
    else:
        stop = max(b["high"] for b in bars)
    if price <= 0:
        return stop, None
    return stop, abs(price - stop) / price * 100.0
