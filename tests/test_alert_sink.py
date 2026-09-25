"""Unit tests for AlertSink — deduplication, ranking, and lifecycle."""
import pandas as pd
import pytest

from scanner.alert_sink import AlertSink


# ── Helpers ───────────────────────────────────────────────────────────────────

def _alert(
    symbol: str = "AAPL",
    direction: str = "long",
    trigger: str = "ema_cross",
    score: int = 70,
    et_str: str = "2024-01-02 10:30",
) -> dict:
    ts = pd.Timestamp(et_str, tz="America/New_York").isoformat()
    return {
        "symbol":     symbol,
        "direction":  direction,
        "trigger":    trigger,
        "score":      score,
        "timestamp":  ts,
        "price":      100.0,
        "conditions": {},
    }


# ── Basic push / len ──────────────────────────────────────────────────────────

def test_push_single_alert_accepted():
    sink = AlertSink()
    assert sink.push(_alert()) is True
    assert len(sink) == 1


def test_push_returns_false_within_cooldown():
    sink = AlertSink(cooldown_minutes=5)
    sink.push(_alert(et_str="2024-01-02 10:30"))
    # Same key, 1 minute later — still within 5-min cooldown
    result = sink.push(_alert(et_str="2024-01-02 10:31"))
    assert result is False
    assert len(sink) == 1


def test_push_accepted_after_cooldown():
    sink = AlertSink(cooldown_minutes=5)
    sink.push(_alert(et_str="2024-01-02 10:30"))
    # Same key, 6 minutes later — cooldown expired
    result = sink.push(_alert(et_str="2024-01-02 10:36"))
    assert result is True
    assert len(sink) == 2


def test_different_symbols_independent_cooldowns():
    sink = AlertSink(cooldown_minutes=5)
    sink.push(_alert(symbol="AAPL", et_str="2024-01-02 10:30"))
    result = sink.push(_alert(symbol="MSFT", et_str="2024-01-02 10:30"))
    assert result is True
    assert len(sink) == 2


def test_different_directions_independent_cooldowns():
    sink = AlertSink(cooldown_minutes=5)
    sink.push(_alert(direction="long",  et_str="2024-01-02 10:30"))
    result = sink.push(_alert(direction="short", et_str="2024-01-02 10:30"))
    assert result is True
    assert len(sink) == 2


def test_different_triggers_independent_cooldowns():
    sink = AlertSink(cooldown_minutes=5)
    sink.push(_alert(trigger="ema_cross",            et_str="2024-01-02 10:30"))
    result = sink.push(_alert(trigger="compression_breakout", et_str="2024-01-02 10:30"))
    assert result is True
    assert len(sink) == 2


# ── Ranking (top) ─────────────────────────────────────────────────────────────

def test_top_returns_sorted_by_score_descending():
    sink = AlertSink()
    for score, sym, et in [(50, "A", "10:00"), (90, "B", "10:01"), (70, "C", "10:02")]:
        sink.push(_alert(symbol=sym, score=score, et_str=f"2024-01-02 {et}"))
    ranked = sink.top()
    scores = [a["score"] for a in ranked]
    assert scores == sorted(scores, reverse=True)


def test_top_n_limits_results():
    sink = AlertSink()
    for i in range(10):
        sink.push(_alert(symbol=f"S{i:02d}", score=i * 10, et_str=f"2024-01-02 10:{i:02d}"))
    assert len(sink.top(3)) == 3
    assert len(sink.top(5)) == 5


def test_top_returns_all_when_fewer_than_n():
    sink = AlertSink()
    sink.push(_alert(symbol="AAPL"))
    sink.push(_alert(symbol="MSFT", et_str="2024-01-02 10:31"))
    assert len(sink.top(10)) == 2


# ── since() ──────────────────────────────────────────────────────────────────

def test_since_filters_by_timestamp():
    sink = AlertSink()
    sink.push(_alert(symbol="A", score=70, et_str="2024-01-02 10:00"))
    sink.push(_alert(symbol="B", score=80, et_str="2024-01-02 11:00"))
    cutoff = pd.Timestamp("2024-01-02 10:30", tz="America/New_York")
    recent = sink.since(cutoff)
    assert len(recent) == 1
    assert recent[0]["symbol"] == "B"


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_empties_alerts_and_cooldown():
    sink = AlertSink(cooldown_minutes=5)
    sink.push(_alert(et_str="2024-01-02 10:30"))
    sink.clear()
    assert len(sink) == 0
    # Cooldown state also cleared: same key should be accepted again
    result = sink.push(_alert(et_str="2024-01-02 10:31"))
    assert result is True


# ── max_size trimming ─────────────────────────────────────────────────────────

def test_max_size_trims_low_score_alerts():
    sink = AlertSink(max_size=3)
    # Push 4 alerts with distinct symbols and scores
    for i, score in enumerate([40, 50, 60, 90]):
        sink.push(_alert(symbol=f"S{i}", score=score, et_str=f"2024-01-02 10:{i:02d}"))
    assert len(sink) == 3
    # Only the 3 highest should remain
    kept_scores = {a["score"] for a in sink.top()}
    assert 40 not in kept_scores
