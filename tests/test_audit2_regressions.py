"""Regressions for the second audit: RVOL interval alignment, the RTH upper
boundary, session rollover, and opening-range date scoping."""
from types import SimpleNamespace

import pandas as pd
import pytest

from scanner.indicators.rvol import compute_rvol
from scanner.state import SymbolState
from scanner.trigger_catalog import EvalCtx, SymbolSeries, _orb, et_minutes


def _bar(ts_et: str, price: float, volume: float = 100.0, sym: str = "AAPL") -> dict:
    ts = pd.Timestamp(ts_et, tz="America/New_York").tz_convert("UTC")
    return {"symbol": sym, "timestamp": ts, "open": price, "high": price + 0.05,
            "low": price - 0.05, "close": price, "volume": volume}


def _daily(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    c = pd.Series([100.0] * n, index=idx)
    return pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c,
                         "volume": 1_000_000.0}, index=idx)


def _flat_state() -> SymbolState:
    st = SymbolState.from_history("AAPL", _daily(), _daily())
    st.volume_profile = pd.Series({m: 500.0 for m in range(0, 390, 5)})
    return st


# ── C1: RVOL compares equal intervals ────────────────────────────────────────

def test_rvol_is_flat_at_normal_pace_every_minute():
    """100 shares a minute against a 500-per-slot baseline is 1.0x on every bar,
    including mid-slot and across slot boundaries (it used to reach 2.0x at 09:39)."""
    st = _flat_state()
    for i in range(45):
        hh, mm = divmod(9 * 60 + 30 + i, 60)
        st.on_bar(_bar(f"2024-01-02 {hh:02d}:{mm:02d}", 100.0))
        assert st.rvol == pytest.approx(1.0), f"minute {i}"


def test_rvol_uneven_profile_prorates_current_slot():
    profile = pd.Series({0: 1000.0, 5: 500.0, 10: 250.0})
    assert compute_rvol(profile, 1000.0, 5) == pytest.approx(1.0)        # boundary: unchanged
    assert compute_rvol(profile, 1200.0, 7) == pytest.approx(1.0)        # 1000 + 500 * 2/5
    assert compute_rvol(profile, 600.0, 3) == pytest.approx(1.0)         # opening slot, prorated
    assert pd.isna(compute_rvol(profile, 100.0, 0))


# ── C2: RTH upper boundary and rollover ──────────────────────────────────────

def test_postmarket_bar_does_not_touch_rth_state():
    st = _flat_state()
    st.on_bar(_bar("2024-01-02 15:59", 100.0, 100.0))
    vwap = st.vwap
    st.on_bar(_bar("2024-01-02 16:00", 200.0, 100.0))
    assert st.session_volume == 100.0
    assert st.vwap == pytest.approx(vwap)
    assert st.high_of_day == pytest.approx(100.05)


def test_live_scanner_resets_on_new_et_date():
    from scanner.live_scanner import LiveScanner
    sc = LiveScanner.__new__(LiveScanner)
    calls = []
    sc.reset_session = lambda: calls.append(1)
    sc._roll_session_if_new_day(_bar("2024-01-02 15:59", 100.0))
    sc._roll_session_if_new_day(_bar("2024-01-02 16:30", 100.0))
    assert calls == []
    sc._roll_session_if_new_day(_bar("2024-01-03 04:00", 100.0))
    assert calls == [1]
    sc._roll_session_if_new_day(_bar("2024-01-02 19:59", 100.0))     # late bar: no roll back
    sc._roll_session_if_new_day(_bar("2024-01-03 09:30", 100.0))
    assert calls == [1]


# ── C3: opening range is today's ─────────────────────────────────────────────

def _feed(series: SymbolSeries, day: str, start: str, prices: list[float]) -> dict:
    h, m = map(int, start.split(":"))
    bar = None
    for i, p in enumerate(prices):
        hh, mm = divmod(h * 60 + m + i, 60)
        bar = _bar(f"{day} {hh:02d}:{mm:02d}", p)
        series.on_bar(bar, et_minutes(bar["timestamp"]), day, None)
    return bar


@pytest.mark.parametrize("tf", [5, 15, 30, 60])
def test_orb_uses_todays_opening_candle(tf):
    s = SymbolSeries("X")
    _feed(s, "2024-01-02", "09:30", [100.0] * (tf + 1))
    # day 2 opens at 200; one bar past the opening candle, crossing its high
    bar = _feed(s, "2024-01-03", "09:30", [200.0] * tf + [199.0, 200.5])
    ctx = EvalCtx(state=SimpleNamespace(symbol="X"), series=s, bar=bar,
                  et_min=et_minutes(bar["timestamp"]), session="rth", external=set())
    fire = _orb(ctx, tf, True)
    assert fire is not None
    assert fire.value == pytest.approx(200.05)


def test_orb_ignores_seeded_history():
    s = SymbolSeries("X")
    idx = pd.date_range("2024-01-02 09:30", periods=78, freq="5min", tz="America/New_York")
    s.seed_intraday(pd.DataFrame({"open": 50.0, "high": 50.5, "low": 49.5, "close": 50.0,
                                  "volume": 1000.0}, index=idx.tz_convert("UTC")))
    bar = _feed(s, "2024-01-03", "09:30", [200.0] * 5 + [199.0, 200.5])
    ctx = EvalCtx(state=SimpleNamespace(symbol="X"), series=s, bar=bar,
                  et_min=et_minutes(bar["timestamp"]), session="rth", external=set())
    assert _orb(ctx, 5, True).value == pytest.approx(200.05)


# ── C4: one stalled subscriber must not delay the rest ───────────────────────

def test_blocked_client_does_not_stall_healthy_client(tmp_path, monkeypatch):
    import asyncio
    from scanner import feed_hub
    from scanner.feed_hub import FeedHub, Subscription

    monkeypatch.setattr(feed_hub, "_SEND_TIMEOUT", 0.2)

    async def run():
        hub = FeedHub(store_dir=tmp_path)
        got, closed = [], []
        never = asyncio.Event()

        async def blocked(msg):
            await never.wait()

        async def healthy(msg):
            got.append(msg)

        async def close():
            closed.append(1)

        sub = Subscription.from_params({})
        hub.add_client(blocked, sub, "stuck", close=close)      # first in line, as in the audit probe
        hub.add_client(healthy, sub, "ok")
        loop = asyncio.create_task(hub.broadcast_loop())
        for i in range(25):
            hub.publish({"symbol": "AAPL", "setup": "x", "direction": "long", "price": 1.0 + i}, "custom")
        await asyncio.sleep(0.6)
        loop.cancel()
        return hub, got, closed

    hub, got, closed = asyncio.run(run())
    assert len(got) == 25                                  # healthy client got every alert
    assert [c["name"] for c in hub.clients()] == ["ok"]    # stuck one was disconnected
    assert closed == [1] and hub.dropped_clients == 1
    assert hub._queue.qsize() == 0                         # producer queue drained


# ── C5: local by default ─────────────────────────────────────────────────────

def test_origin_policy():
    from scanner.api import origin_is_local
    assert origin_is_local(None)                                   # scripts and bots send no Origin
    assert origin_is_local("http://localhost:5173")
    assert origin_is_local("http://127.0.0.1:7777")
    assert not origin_is_local("https://example.com")
    assert not origin_is_local("http://localhost.example.com")
    assert origin_is_local("http://192.168.1.5:7777", host="192.168.1.5:7777")    # --host on a LAN
    assert not origin_is_local("http://192.168.1.9:7777", host="192.168.1.5:7777")


def test_servers_bind_loopback_by_default():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for rel in ("scripts/run_live.py", "scanner/api.py"):
        assert "0.0.0.0" not in (root / rel).read_text(encoding="utf-8"), rel


# ── C11 / C15: validation contract and atomic presets ────────────────────────

@pytest.mark.parametrize("field,bad", [("repeat_sec", "not-a-number"), ("and_window_min", "inf"),
                                       ("min_triggers", "nan"), ("repeat_sec", [1])])
def test_bad_numeric_field_is_a_setup_error(field, bad):
    from scanner.custom_setups import SetupError, normalize_setup
    raw = {"id": "cs_test", "name": "t", "triggers": [{"id": "hod"}], field: bad}
    with pytest.raises(SetupError):
        normalize_setup(raw)
