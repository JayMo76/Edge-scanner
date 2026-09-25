"""Profiles bound at the _on_bar choke point.

The two properties that matter operationally:
  1. with no engine attached, or every setup on the empty profile, the alert
     stream is byte-identical to before this feature existed
  2. a profile can only ever REMOVE alerts, never add or alter one
"""
from __future__ import annotations

import pandas as pd
import pytest

from scanner.alert_sink import AlertSink
from scanner.custom_setups import CustomEvaluator, CustomSetupStore
from scanner.live_scanner import LiveScanner
from scanner.profiles import (
    ALL_ID,
    ProfileEngine,
    ProfileStore,
    SetupProfiles,
    profile_stats,
)
from tests.helpers import FakeSetupEvaluator

# Every test here builds a scanner with a (fake) system evaluator attached, and
# the assignment store only accepts the installed plugin's setup codes.
pytestmark = pytest.mark.usefixtures("fake_plugin")


class _Collect(AlertSink):
    def __init__(self):
        super().__init__()
        self.alerts: list[dict] = []

    def push(self, alert: dict) -> bool:
        self.alerts.append(alert)
        return True


def _daily(n: int = 60, base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    c = pd.Series([base + i * 0.05 for i in range(n)], index=idx)
    return pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5,
                         "close": c, "volume": 1_000_000.0}, index=idx)


def _bars(symbol: str, n: int = 40, start: str = "2024-01-02 09:30"):
    t0 = pd.Timestamp(start, tz="America/New_York")
    out = []
    for i in range(n):
        px = 100.0 + (i % 5) * 0.5
        ts = (t0 + pd.Timedelta(minutes=i)).tz_convert("UTC")
        out.append({"symbol": symbol, "timestamp": ts, "open": px, "high": px + 0.4,
                    "low": px - 0.4, "close": px + 0.2, "volume": 20_000.0})
    return out


def _build(tmp_path, profile: dict | None, assign_to_custom: bool,
           parameters: list[dict] | None = None,
           param_set: dict | None = None):
    """A scanner with one always-on custom setup.

    `profile` is the universe filter (static conditions, shared by name);
    `parameters` are the setup's own dynamic conditions.
    """
    setups_dir = tmp_path / "setups"
    store = CustomSetupStore(setups_dir, defaults=tmp_path / "none.json")
    store.save({
        "id": "cs_test", "name": "Test", "enabled": True, "mode": "or",
        "direction": "all", "sessions": ["rth"],
        "triggers": [{"id": "consec_candles", "options": ["green"], "params": {"count": 2, "tf": 1}}],
        "universe_profile": (profile["id"] if (profile and assign_to_custom) else ""),
        "parameters": parameters or [],
        "parameter_set": (param_set["id"] if param_set else ""),
    })

    pstore = ProfileStore(tmp_path / "profiles", defaults=tmp_path / "nodefaults.json")
    if profile:
        pstore.save(profile)
    from scanner.profiles import ParamSetStore
    sets = ParamSetStore(tmp_path / "paramsets", defaults=tmp_path / "nodefaults.json")
    if param_set:
        sets.save(param_set)
    engine = ProfileEngine(pstore, SetupProfiles(tmp_path / "assign.json"), sets)

    daily = _daily()
    sc = LiveScanner(["AAA"], None, AlertSink())
    sc.warmup(daily, {"AAA": daily})
    sink = _Collect()
    sc.attach_system(FakeSetupEvaluator(), sink)
    sc.attach_custom(CustomEvaluator(store))
    sc.attach_profiles(engine)
    engine.resolve_members(sc._states)
    return sc, sink, engine


def _run(sc, symbol="AAA"):
    for b in _bars(symbol):
        sc._on_bar(b)


# ── inert when unconfigured ──────────────────────────────────────────────────

def test_no_engine_attached_leaves_the_stream_untouched(tmp_path):
    sc, sink, _ = _build(tmp_path, None, False)
    sc._profiles = None
    _run(sc)
    assert sink.alerts, "the fixture setup should fire"
    assert all("universe_profile" not in a for a in sink.alerts)


def test_the_empty_profile_passes_everything_and_stamps_nothing(tmp_path):
    sc, sink, _ = _build(tmp_path, {"id": ALL_ID, "conditions": []}, True)
    _run(sc)
    assert sink.alerts
    # up_all is empty, so the check short-circuits before stamping the payload
    assert all("universe_profile" not in a for a in sink.alerts)


def test_an_unassigned_custom_setup_is_not_screened(tmp_path):
    sc, sink, _ = _build(tmp_path, {"id": "strict", "conditions": [
        {"id": "price", "value": 1e9}]}, assign_to_custom=False)
    _run(sc)
    assert sink.alerts, "a profile nobody points at must not block anything"


# ── a profile only ever removes ──────────────────────────────────────────────

def test_a_blocking_profile_removes_every_alert(tmp_path):
    sc, sink, _ = _build(tmp_path, {"id": "strict", "conditions": [
        {"id": "price", "op": "gte", "value": 1e9}]}, True)
    _run(sc)
    assert sink.alerts == []


def test_a_passing_profile_keeps_the_same_alerts_and_stamps_them(tmp_path):
    base, base_sink, _ = _build(tmp_path / "a", None, False)
    _run(base)

    sc, sink, _ = _build(tmp_path / "b", {"id": "loose", "name": "Loose", "conditions": [
        {"id": "price", "op": "gte", "value": 1.0}]}, True)
    _run(sc)

    assert [a["symbol"] for a in sink.alerts] == [a["symbol"] for a in base_sink.alerts]
    assert [a["timestamp"] for a in sink.alerts] == [a["timestamp"] for a in base_sink.alerts]
    for a in sink.alerts:
        assert a["universe_profile"]["id"] == "loose"
        assert a["universe_profile"]["passed"] is True
        assert a["profile_hash"] == a["universe_profile"]["hash"]


def test_the_profiled_stream_is_always_a_subset(tmp_path):
    """Monotonicity: alerts(profile) is a subset of alerts(no profile)."""
    base, base_sink, _ = _build(tmp_path / "a", None, False)
    _run(base)
    keys_base = {(a["symbol"], str(a["timestamp"]), a["setup"]) for a in base_sink.alerts}

    # session_volume grows through the day, so it is a PARAMETER on the setup,
    # not a universe filter. It still may only ever remove alerts.
    sc, sink, _ = _build(tmp_path / "b", None, False, parameters=[
        {"id": "session_volume", "op": "gte", "value": 200_000}])
    _run(sc)
    keys = {(a["symbol"], str(a["timestamp"]), a["setup"]) for a in sink.alerts}

    assert keys <= keys_base
    assert len(keys) < len(keys_base), "this threshold should block the early bars"


# ── payload and stats ────────────────────────────────────────────────────────

def test_a_blocked_alert_is_counted_with_the_condition_that_blocked_it(tmp_path):
    profile_stats.reset()
    sc, sink, _ = _build(tmp_path, {"id": "strict", "conditions": [
        {"id": "price", "op": "gte", "value": 1e9}]}, True)
    _run(sc)
    snap = profile_stats.snapshot()["setups"]["cs_test"]
    assert snap["checked"] > 0
    assert snap["blocked"] == snap["checked"]
    assert snap["by_condition"]["price"] == snap["blocked"]


def test_a_broken_engine_fails_open_rather_than_silencing_the_scanner(tmp_path):
    class Boom:
        def for_setup(self, *a, **k):
            raise RuntimeError("boom")

    sc, sink, _ = _build(tmp_path, None, False)
    sc.attach_profiles(Boom())
    _run(sc)
    assert sink.alerts, "a bug in the profile layer must not stop alerts"


def test_system_setups_resolve_by_their_wire_code(tmp_path):
    sc, sink, engine = _build(tmp_path, {"id": "blockall", "conditions": [
        {"id": "price", "op": "gte", "value": 1e9}]}, False)
    engine.assignments.save({"X1": "blockall"})
    engine.reload()

    state = sc._states["AAA"]
    bar = _bars("AAA", 1)[0]
    from scanner.profiles import BarProfileCache

    blocked = {"symbol": "AAA", "setup": "X1", "direction": "long"}
    allowed = {"symbol": "AAA", "setup": "X2", "direction": "short"}
    assert sc._passes_profile(blocked, state, bar, "rth", BarProfileCache(), "system") is False
    assert sc._passes_profile(allowed, state, bar, "rth", BarProfileCache(), "system") is True


def test_a_system_alert_is_screened_by_its_own_profile_end_to_end(tmp_path):
    """Through _on_bar: X1's profile blocks X1's alerts and nobody else's."""
    sc, sink, engine = _build(tmp_path, {"id": "blockall", "conditions": [
        {"id": "price", "op": "gte", "value": 1e9}]}, False)
    sc.attach_system(FakeSetupEvaluator(fire=("X1", "X2")), sink)
    engine.assignments.save({"X1": "blockall"})
    engine.reload()
    engine.resolve_members(sc._states)
    _run(sc)
    setups = {a["setup"] for a in sink.alerts}
    assert "X1" not in setups and {"X2", "cs_test"} <= setups


def test_reset_session_clears_stats_and_member_sets(tmp_path):
    sc, sink, engine = _build(tmp_path, {"id": "px", "conditions": [
        {"id": "price", "op": "gte", "value": 1.0}]}, True)
    _run(sc)
    assert engine.members("px") is not None
    sc.reset_session()
    assert engine.members("px") is None
    assert profile_stats.snapshot()["setups"] == {}


def test_the_alert_payload_carries_the_parameters_that_were_checked(tmp_path):
    """Downstream clients need to see what screened a signal, and the
    universe and the parameters are two different answers to that."""
    sc, sink, _ = _build(tmp_path, None, False, parameters=[
        {"id": "session_volume", "op": "gte", "value": 1}])
    _run(sc)
    assert sink.alerts, "the setup should still fire"
    a = sink.alerts[0]
    assert [c["name"] for c in a["parameters"]] == ["session_volume"]
    assert a["parameters"][0]["passed"] is True


def test_a_parameter_can_block_without_any_universe_filter(tmp_path):
    """Parameters are evaluated even when the setup has no universe filter at
    all, which is the common case now that the two are separate."""
    sc, sink, _ = _build(tmp_path, None, False, parameters=[
        {"id": "session_volume", "op": "gte", "value": 10**12}])
    _run(sc)
    assert sink.alerts == []


# ── named parameter sets ─────────────────────────────────────────────────────

def test_a_parameter_set_blocks_the_same_way_an_inline_parameter_does(tmp_path):
    base, base_sink, _ = _build(tmp_path / "a", None, False)
    _run(base)
    assert base_sink.alerts

    sc, sink, _ = _build(tmp_path / "b", None, False, param_set={
        "id": "ps_x", "name": "Impossible",
        "conditions": [{"id": "session_volume", "op": "gte", "value": 10**12}]})
    _run(sc)
    assert sink.alerts == []


def test_the_set_and_the_setups_own_parameters_are_anded(tmp_path):
    """Listing a condition in both is not a conflict: the tighter one wins."""
    sc, sink, _ = _build(
        tmp_path, None, False,
        parameters=[{"id": "session_volume", "op": "gte", "value": 10**12}],
        param_set={"id": "ps_x", "name": "Loose",
                   "conditions": [{"id": "session_volume", "op": "gte", "value": 1}]})
    _run(sc)
    assert sink.alerts == [], "a loose shared value must not loosen a tight local one"


def test_a_set_can_tighten_but_a_setup_cannot_loosen_it(tmp_path):
    sc, sink, _ = _build(
        tmp_path, None, False,
        parameters=[{"id": "session_volume", "op": "gte", "value": 1}],
        param_set={"id": "ps_x", "name": "Tight",
                   "conditions": [{"id": "session_volume", "op": "gte", "value": 10**12}]})
    _run(sc)
    assert sink.alerts == []


def test_an_unknown_parameter_set_passes_rather_than_blocking(tmp_path):
    """Deleting a set must not silence every setup that referenced it."""
    sc, sink, _ = _build(tmp_path, None, False)
    sc._custom_evaluator.plan.setups[0]["parameter_set"] = "ps_deleted"
    _run(sc)
    assert sink.alerts


def test_the_alert_records_the_set_conditions_it_was_checked_against(tmp_path):
    sc, sink, _ = _build(tmp_path, None, False, param_set={
        "id": "ps_x", "name": "Any volume",
        "conditions": [{"id": "session_volume", "op": "gte", "value": 1}]})
    _run(sc)
    assert sink.alerts
    assert [c["name"] for c in sink.alerts[0]["parameters"]] == ["session_volume"]
