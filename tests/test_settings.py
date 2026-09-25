"""Runtime-editable settings (scanner/settings.py) and the Config API.

Guards two things: (1) every code default in the core schema equals the
constant the gates ship with, so a fresh install behaves exactly as before;
(2) a Save hot-applies to the gate functions, persists, and is recorded in
history. Plugin parameters are covered by the plugin's own tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scanner import gates
from scanner.settings import SCHEMA, GateStats, Settings, coerce, settings


@pytest.fixture
def fresh(tmp_path: Path, monkeypatch):
    """A Settings instance on a temp dir, swapped into the gates module."""
    s = Settings(tmp_path / "settings")
    monkeypatch.setattr(gates, "S", s)
    return s


def test_process_settings_are_default_unless_a_file_says_otherwise():
    # The shared singleton used by the live engine; tests must never leave it modified.
    assert settings.hash == "default" or settings.dir.joinpath("current.json").exists()


def test_coerce_validates():
    p = next(x for x in SCHEMA if x.key == "STOP_BARS")
    assert coerce(p, "7") == 7
    with pytest.raises(ValueError):
        coerce(p, 2.5)
    with pytest.raises(ValueError):
        coerce(p, 0)
    t = next(x for x in SCHEMA if x.key == "GATE_MARKET_ALIGN_FROM")
    with pytest.raises(ValueError):
        coerce(t, 24 * 60)
    with pytest.raises(ValueError):
        coerce(p, True)
    with pytest.raises(ValueError):
        coerce(p, float("nan"))
    with pytest.raises(ValueError):
        coerce(p, "abc")


def test_save_hot_applies_and_persists(fresh: Settings, tmp_path: Path):
    assert fresh.hash == "default" and not fresh.is_modified()
    assert gates.gate_rvol(1.2).passed is True                  # default needs 1.00
    ch = fresh.save({"GATE_RVOL_MIN": 1.5}, note="test")
    assert ch == {"GATE_RVOL_MIN": [1.0, 1.5]}
    assert gates.gate_rvol(1.2).passed is False                 # hot-applied
    assert fresh.is_modified() and fresh.hash != "default"
    doc = json.loads((tmp_path / "settings" / "current.json").read_text(encoding="utf-8"))
    assert doc["values"] == {"GATE_RVOL_MIN": 1.5}
    hist = fresh.history()
    assert hist and hist[0]["changes"] == {"GATE_RVOL_MIN": [1.0, 1.5]} and hist[0]["note"] == "test"
    # a fresh instance on the same dir reloads it
    again = Settings(tmp_path / "settings")
    assert again.GATE_RVOL_MIN == 1.5 and again.hash == fresh.hash
    # unknown key / out of range -> ValueError, nothing applied
    with pytest.raises(ValueError):
        fresh.save({"NOPE": 1, "STOP_BARS": 0})
    assert fresh.STOP_BARS == 5
    # saving the same value again is not a change
    assert fresh.save({"GATE_RVOL_MIN": 1.5}) == {}


def test_hash_is_stable_and_tracks_values(tmp_path: Path):
    a = Settings(tmp_path / "a")
    b = Settings(tmp_path / "b")
    a.save({"GATE_VOID_MIN_PCT": 2.0})
    b.save({"GATE_VOID_MIN_PCT": 2.0})
    assert a.hash == b.hash != "default"
    b.save({"GATE_VOID_MIN_PCT": 2.5})
    assert a.hash != b.hash
    b.reset()
    assert b.hash == "default"


def test_unreadable_or_invalid_current_json_falls_back_to_defaults(tmp_path: Path):
    d = tmp_path / "settings"
    d.mkdir()
    (d / "current.json").write_text("{not json", encoding="utf-8")
    assert Settings(d).hash == "default"
    (d / "current.json").write_text(json.dumps({"values": {"GATE_RVOL_MIN": "x", "UNKNOWN": 3,
                                                          "GATE_VOID_MIN_PCT": 2.0}}), encoding="utf-8")
    s = Settings(d)
    assert s.GATE_RVOL_MIN == 1.0 and s.GATE_VOID_MIN_PCT == 2.0


def test_reset_by_setup_resets_shared_params_only(fresh: Settings):
    # STOP_BARS is shared ("*"), the GATE_* params belong to no setup card
    fresh.save({"STOP_BARS": 7, "GATE_RVOL_MIN": 1.5})
    fresh.reset(setup="ANY")
    assert fresh.STOP_BARS == 5 and fresh.GATE_RVOL_MIN == 1.5
    fresh.reset(keys=["GATE_RVOL_MIN"])
    assert not fresh.is_modified()


def test_presets_roundtrip(fresh: Settings):
    fresh.save({"GATE_VOID_MIN_PCT": 2.0})
    fresh.save_preset("aggressive")
    fresh.reset()
    assert fresh.GATE_VOID_MIN_PCT == 1.0
    fresh.apply_preset("aggressive")
    assert fresh.GATE_VOID_MIN_PCT == 2.0
    assert [p["name"] for p in fresh.list_presets()] == ["aggressive"]
    assert fresh.list_presets()[0]["n_modified"] == 1
    with pytest.raises(ValueError):
        fresh.save_preset("../evil")
    with pytest.raises(ValueError):
        fresh.apply_preset("missing")
    assert fresh.delete_preset("aggressive") and fresh.list_presets() == []
    assert fresh.delete_preset("aggressive") is False


def test_gate_stats_counts():
    gs = GateStats()
    from scanner.gates import GateCheck
    gs.record("X1", [GateCheck("gap", True, 1, ""), GateCheck("rvol", False, 0.5, "")], False)
    gs.record("X1", [GateCheck("gap", True, 1, ""), GateCheck("rvol", True, 1.5, "")], True)
    snap = gs.snapshot()
    assert snap["setups"]["X1"]["gates"]["rvol"] == {"pass": 1, "fail": 1}
    assert snap["setups"]["X1"]["evals"] == 2 and snap["setups"]["X1"]["fired"] == 1
    gs.reset()
    assert gs.snapshot()["setups"] == {}


def test_settings_api(tmp_path: Path, monkeypatch):
    import scanner.api_v2 as api_v2
    s = Settings(tmp_path / "settings")
    monkeypatch.setattr(api_v2, "settings", s)
    monkeypatch.setattr(gates, "S", s)

    class FakeScanner:
        _states: dict = {}
        _sector_map: dict = {}
    class FakeAppState:
        scanner = FakeScanner()
    app = FastAPI()
    api_v2.register_v2_routes(app, FakeAppState(), layouts_dir=tmp_path / "l", watchlists_path=tmp_path / "w.json",
                              fundamentals_path=tmp_path / "f.json", universe_csv=tmp_path / "no.csv", sector_csv=tmp_path / "no2.csv")
    c = TestClient(app)
    d = c.get("/api/v2/settings").json()
    assert d["hash"] == "default" and len(d["schema"]) == len(SCHEMA) and d["values"]["GATE_RVOL_MIN"] == 1.0
    r = c.put("/api/v2/settings", json={"values": {"GATE_RVOL_MIN": 1.5}, "note": "api"}).json()
    assert r["ok"] and r["modified"] == {"GATE_RVOL_MIN": 1.5} and r["hash"] != "default"
    assert c.put("/api/v2/settings", json={"values": {"STOP_BARS": -1}}).status_code == 400
    assert c.put("/api/v2/settings/presets/my preset").json()["ok"]
    assert c.post("/api/v2/settings/reset", json={}).json()["modified"] == {}
    assert c.post("/api/v2/settings/presets/my preset/apply").json()["modified"] == {"GATE_RVOL_MIN": 1.5}
    assert c.delete("/api/v2/settings/presets/my preset").json()["ok"]
    assert c.get("/api/v2/settings/stats").json()["setups"] is not None
    assert len(c.get("/api/v2/settings").json()["history"]) >= 3


def test_schema_api_shape():
    rows = Settings.schema()
    keys = [r["key"] for r in rows]
    assert len(keys) == len(set(keys)) == len(SCHEMA)
    for k in ("STOP_BARS", "GATE_RVOL_MIN", "GATE_VOID_MIN_PCT",
              "GATE_RRS_WARMUP_5M_BARS", "GATE_MARKET_ALIGN_FROM"):
        assert k in keys
    for r in rows:
        assert set(r) == {"key", "label", "default", "desc", "setups", "group", "type", "unit", "min", "max", "step", "gate"}
        assert isinstance(r["setups"], list)
    assert Settings.defaults()["STOP_BARS"] == 5


def test_gate_defaults_match_code_constants():
    """The shared gate thresholds are editable settings. Their defaults must
    stay identical to the constants the gates ship with, or the Config panel
    silently changes what the scanner fires on."""
    d = Settings.defaults()
    assert (d["GATE_RVOL_MIN"], d["GATE_VOID_MIN_PCT"]) == (gates._RVOL_MIN, gates._VOID_MIN_PCT)
    assert d["GATE_RRS_WARMUP_5M_BARS"] == gates._RRS_WARMUP_5M_BARS
    assert d["GATE_MARKET_ALIGN_FROM"] == gates._MARKET_OPEN_HOUR_ET * 60 + gates._MARKET_OPEN_MINUTE_ET
    # the shared gate params are not shown on any single setup card
    for p in Settings.schema():
        if p["key"].startswith("GATE_"):
            assert p["setups"] == [], p["key"]


def test_edited_gate_threshold_changes_what_the_gate_returns(tmp_path, monkeypatch):
    """Hot-apply reaches the shared gates: the gate reads the live settings
    object on every call instead of a frozen constant."""
    s = Settings(dir=tmp_path)
    s.load()
    monkeypatch.setattr(gates, "S", s)
    assert gates.gate_rvol(1.1).passed is True          # default 1.00
    s.save({"GATE_RVOL_MIN": 1.5})
    assert gates.gate_rvol(1.1).passed is False
    assert gates.gate_rvol(1.1, threshold=1.0).passed is True   # explicit arg still wins
    s.reset()
    assert gates.gate_rvol(1.1).passed is True
