"""Setup check: what every setup did on a stock in the last few minutes, and why.

Driven through a real LiveScanner (the choke point, the sinks and the evaluators
are what record), using the fixtures from test_profile_binding.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scanner.recent_activity import RecentActivity, build_setup_check
from tests.test_profile_binding import _Collect, _build, _run

# The scanner fixture attaches a fake system evaluator (setups X1 / X2).
pytestmark = pytest.mark.usefixtures("fake_plugin")


def _report(sc, engine, symbol="AAA", minutes=60):
    # The fixture's setup fires at 09:32 and its bars run to 10:09, so the tests
    # look back an hour; the window itself is tested on RecentActivity below.
    custom = sc._custom_evaluator.store.load_all()
    return build_setup_check(sc, custom, {"X1": "Renamed X1"}, engine, symbol, minutes)


def _row(rep, sid):
    return next(r for r in rep["setups"] if r["id"] == sid)


def test_an_alert_that_went_out_reads_sent(tmp_path):
    sc, sink, engine = _build(tmp_path, None, False)
    _run(sc)
    assert sink.alerts
    row = _row(_report(sc, engine), "cs_test")
    assert row["status"] == "sent" and row["source"] == "CS"
    assert all(e["outcome"] == "sent" for e in row["events"])


def test_a_universe_block_says_which_filter(tmp_path):
    sc, sink, engine = _build(tmp_path, {"id": "strict", "name": "Strict", "conditions": [
        {"id": "price", "op": "gte", "value": 1e9}]}, True)
    _run(sc)
    assert sink.alerts == []
    row = _row(_report(sc, engine), "cs_test")
    assert row["status"] == "blocked"
    assert any("Last price $101.2 (needs >= $10K) (Strict universe)" == why
               for e in row["events"] for why in e["reasons"])
    assert all(not n["ok"] and "not in the Strict universe" in n["reasons"] for n in row["now"])


def test_a_parameter_block_names_the_parameter_and_its_value(tmp_path):
    sc, sink, engine = _build(tmp_path, None, False, parameters=[
        {"id": "rvol", "op": "gte", "value": 50.0}])
    _run(sc)
    assert sink.alerts == []
    row = _row(_report(sc, engine), "cs_test")
    assert row["status"] == "blocked"
    assert any(why.startswith("Relative volume") for e in row["events"] for why in e["reasons"])


def test_a_sink_that_swallows_the_alert_reads_repeat(tmp_path):
    class _Deny(_Collect):
        def push(self, alert):
            return False
    sc, _, engine = _build(tmp_path, None, False)
    sc._custom_sink = _Deny()
    _run(sc)
    assert _row(_report(sc, engine), "cs_test")["status"] == "repeat"


def test_every_engine_is_listed_with_its_state_now(tmp_path):
    sc, _, engine = _build(tmp_path, None, False)
    _run(sc)
    rep = _report(sc, engine)
    sources = {r["source"] for r in rep["setups"]}
    assert sources == {"CS", "System"}
    x1 = _row(rep, "X1")
    assert x1["name"] == "Renamed X1" and x1["now"]           # the display name passed in
    x2 = _row(rep, "X2")
    assert x2["name"] == "X2"                                  # no name given: the code
    assert x2["now"][0]["ok"] is False and x2["now"][0]["reasons"] == ["gap: 0.1 >= 1.0"]


def test_a_system_alert_that_went_out_reads_sent(tmp_path):
    from tests.helpers import FakeSetupEvaluator
    sc, sink, engine = _build(tmp_path, None, False)
    sc.attach_system(FakeSetupEvaluator(fire=("X1",)), sink)
    _run(sc)
    rep = _report(sc, engine)
    assert _row(rep, "X1")["status"] == "sent" and _row(rep, "X1")["source"] == "System"
    assert _row(rep, "X2")["status"] == "quiet"


def test_without_a_plugin_only_custom_setups_are_listed(tmp_path, monkeypatch):
    from tests.helpers import install_fake_plugin
    sc, _, engine = _build(tmp_path, None, False)
    install_fake_plugin(monkeypatch, setups=())
    _run(sc)
    assert {r["source"] for r in _report(sc, engine)["setups"]} == {"CS"}


def test_sent_setups_sort_first(tmp_path):
    sc, _, engine = _build(tmp_path, None, False)
    _run(sc)
    rep = _report(sc, engine)
    assert rep["setups"][0]["status"] == "sent"


def test_a_symbol_outside_the_universe_is_not_found(tmp_path):
    sc, _, engine = _build(tmp_path, None, False)
    rep = _report(sc, engine, symbol="ZZZZ")
    assert rep["found"] is False and rep["setups"] == []


def test_the_window_only_includes_its_last_minutes():
    act = RecentActivity()
    t0 = pd.Timestamp("2024-01-02 15:00", tz="UTC")
    for m in (0, 4, 8, 12):
        act.add("AAA", t0 + pd.Timedelta(minutes=m), "custom", "cs_x", "long", "sent")
    since = (t0 + pd.Timedelta(minutes=13)).timestamp() - 5 * 60
    assert len(act.events("AAA", since)) == 2


def test_old_events_are_pruned_as_new_ones_arrive():
    act = RecentActivity(keep_seconds=60)
    t0 = pd.Timestamp("2024-01-02 15:00", tz="UTC")
    act.add("AAA", t0, "custom", "cs_x", "long", "sent")
    act.add("AAA", t0 + pd.Timedelta(minutes=5), "custom", "cs_x", "long", "sent")
    assert len(act.events("AAA", 0)) == 1


# ── the route ────────────────────────────────────────────────────────────────

from tests.test_api_v2 import client  # noqa: E402,F401  (pytest fixture)


def test_the_check_route_answers_for_a_scanned_symbol_and_refuses_others(client):  # noqa: F811
    ok = client.get("/api/v2/check/aaa?minutes=5").json()
    assert ok["found"] is True and ok["symbol"] == "AAA" and ok["minutes"] == 5
    assert ok["recording"] is False          # the fake scanner records nothing, and says so
    missing = client.get("/api/v2/check/ZZZZ").json()
    assert missing["found"] is False and "not in the scanner universe" in missing["message"]
    assert client.get("/api/v2/check/AAA?minutes=60").status_code == 422
