"""Universe profiles (scanner/profiles.py): store, compile, membership, check."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from scanner.conditions import ConditionCtx, ConditionError
from scanner.profiles import (
    ALL_ID,
    BarProfileCache,
    ProfileEngine,
    ProfileError,
    ProfileStore,
    SetupProfiles,
    compile_profile,
    normalize_profile,
    profile_hash,
    summary_lines,
)


def _state(**kw):
    base = dict(symbol="AAA", adv20=6_000_000.0, prior_close=50.0, atr_d1=1.0,
                chart_quality=70.0, rvol=1.5, session_volume=900_000.0,
                dist_vwap_pct=-3.0, gap_pct=2.0, _last_close=50.0)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def store(tmp_path) -> ProfileStore:
    return ProfileStore(tmp_path / "profiles")


@pytest.fixture
def engine(tmp_path) -> ProfileEngine:
    return ProfileEngine(ProfileStore(tmp_path / "profiles"),
                         SetupProfiles(tmp_path / "assign.json"))


# ── normalize ────────────────────────────────────────────────────────────────

def test_normalize_requires_a_safe_id():
    with pytest.raises(ProfileError):
        normalize_profile({"id": "../escape"})
    with pytest.raises(ProfileError):
        normalize_profile({"id": ""})


def test_normalize_rejects_an_unknown_condition():
    with pytest.raises(ConditionError):
        normalize_profile({"id": "p", "conditions": [{"id": "no_such"}]})


def test_normalize_rejects_the_same_condition_twice():
    """Conditions AND together, so a duplicate is a user mistake, not a filter."""
    with pytest.raises(ProfileError):
        normalize_profile({"id": "p", "conditions": [
            {"id": "price", "value": 5}, {"id": "price", "value": 10}]})


def test_a_dynamic_condition_is_rejected_from_a_profile():
    """A universe answers what KIND of stock this is, and every answer is fixed
    for the session. Anything that changes bar to bar is a setup parameter."""
    with pytest.raises(ProfileError, match="parameter"):
        normalize_profile({"id": "p", "conditions": [{"id": "rvol", "value": 1.5}]})


def test_two_different_static_conditions_are_allowed():
    p = normalize_profile({"id": "p", "conditions": [
        {"id": "market_cap", "op": "gte", "value": 3e8},
        {"id": "float_shares", "op": "lte", "value": 2e7}]})
    assert len(p["conditions"]) == 2


def test_normalize_caps_the_condition_count():
    with pytest.raises(ProfileError):
        normalize_profile({"id": "p", "conditions": [
            {"id": "price", "value": v} for v in range(1, 30)]})


def _cond(cid: str, value: float, op: str = "gte", option: str = "") -> dict:
    """One normalized condition, the shape a setup stores in `parameters`."""
    return {"id": cid, "op": op, "value": value, "option": option, "params": {}}


# ── hashing ──────────────────────────────────────────────────────────────────

def test_the_hash_tracks_the_conditions_not_the_cosmetics():
    a = normalize_profile({"id": "p", "name": "One", "color": "#fff",
                           "conditions": [{"id": "price", "value": 10}]})
    b = normalize_profile({"id": "p", "name": "Two", "color": "#000",
                           "conditions": [{"id": "price", "value": 10}]})
    c = normalize_profile({"id": "p", "conditions": [{"id": "price", "value": 20}]})
    assert profile_hash(a) == profile_hash(b)
    assert profile_hash(a) != profile_hash(c)


# ── store ────────────────────────────────────────────────────────────────────

def test_the_store_seeds_defaults_only_when_empty(tmp_path):
    s = ProfileStore(tmp_path / "p")
    ids = {p["id"] for p in s.load_all()}
    assert ALL_ID in ids and "up_liquid_movers" in ids

    s.save({"id": "up_all", "name": "Renamed", "conditions": []})
    again = ProfileStore(tmp_path / "p")
    assert next(p for p in again.load_all() if p["id"] == ALL_ID)["name"] == "Renamed"


def test_save_preserves_created_at_and_moves_updated_at(store):
    first = store.save({"id": "mine", "name": "Mine", "conditions": []})
    second = store.save({"id": "mine", "name": "Mine v2", "conditions": []})
    assert second["createdAt"] == first["createdAt"]
    assert second["updatedAt"] >= first["updatedAt"]


def test_the_all_profile_cannot_be_deleted(store):
    assert store.delete(ALL_ID) is False
    assert store.get(ALL_ID) is not None


def test_delete_removes_a_user_profile(store):
    store.save({"id": "mine", "conditions": []})
    assert store.delete("mine") is True
    assert store.get("mine") is None


# ── assignments ──────────────────────────────────────────────────────────────

def test_every_system_key_defaults_to_the_all_profile(tmp_path, fake_plugin):
    a = SetupProfiles(tmp_path / "a.json")
    m = a.load()
    assert set(m) == {"X1", "X2"}
    assert set(m.values()) == {ALL_ID}


def test_the_default_assignment_keys_follow_the_installed_plugin(tmp_path):
    from scanner import plugins
    m = SetupProfiles(tmp_path / "a.json").load()
    assert set(plugins.SYSTEM_CODES) <= set(m)


def test_assignments_reject_an_unknown_key(tmp_path):
    a = SetupProfiles(tmp_path / "a.json")
    with pytest.raises(ProfileError):
        a.save({"NOPE": "up_all"})


def test_assigning_null_falls_back_to_the_all_profile(tmp_path, fake_plugin):
    a = SetupProfiles(tmp_path / "a.json")
    a.save({"X1": "up_liquid_movers"})
    assert a.load()["X1"] == "up_liquid_movers"
    a.save({"X1": None})
    assert a.load()["X1"] == ALL_ID


# ── compile + membership ─────────────────────────────────────────────────────

def test_compile_puts_every_stored_condition_in_the_static_half():
    p = normalize_profile({"id": "p", "conditions": [
        {"id": "price", "value": 10},
        {"id": "avg_vol_20d", "value": 1e6},
    ]})
    cp = compile_profile(p)
    assert [c["id"] for c in cp.static] == ["price", "avg_vol_20d"]
    assert cp.dynamic == []      # a dynamic condition can no longer be stored


def test_members_resolve_from_the_conditions(engine):
    engine.store.save({"id": "liq", "conditions": [{"id": "price", "value": 20}]})
    engine.reload()
    states = {"AAA": _state(prior_close=50.0, _last_close=50.0),
              "BBB": _state(symbol="BBB", prior_close=5.0, _last_close=5.0)}
    engine.resolve_members(states)
    assert engine.members("liq") == frozenset({"AAA"})


def test_a_profile_with_no_conditions_has_no_member_set(engine):
    engine.reload()
    engine.resolve_members({"AAA": _state()})
    assert engine.members(ALL_ID) is None      # None means "everyone"


def test_price_membership_works_before_any_bar_has_arrived(engine):
    """Static resolution runs at warmup, when _last_close is still None.

    Without the prior_close fallback in ConditionCtx.price this silently
    empties every member set that uses a price floor.
    """
    engine.store.save({"id": "px", "conditions": [{"id": "price", "value": 20}]})
    engine.reload()
    fresh = SimpleNamespace(symbol="AAA", prior_close=50.0, _last_close=None,
                            adv20=1e6, atr_d1=1.0, chart_quality=70.0)
    engine.resolve_members({"AAA": fresh})
    assert engine.members("px") == frozenset({"AAA"})


def test_invalidate_clears_every_member_set(engine):
    engine.store.save({"id": "px", "conditions": [{"id": "price", "value": 1}]})
    engine.reload()
    engine.resolve_members({"AAA": _state()})
    assert engine.members("px") is not None
    engine.invalidate_members()
    assert engine.members("px") is None


# ── check ────────────────────────────────────────────────────────────────────

def test_the_all_profile_passes_everything(engine):
    r = engine.check(engine.get(ALL_ID), ConditionCtx(state=_state()))
    assert r.passed is True and r.checks == []


def test_a_setup_parameter_blocks_at_fire_time(engine):
    """Dynamic conditions live on the setup now, not in the profile."""
    ctx = ConditionCtx(state=_state(rvol=1.2), bar={"close": 50.0})
    r = engine.check_conditions([_cond("rvol", 5.0)], ctx)
    assert r.passed is False
    assert r.checks[0].name == "rvol" and r.checks[0].value == 1.2


def test_a_setup_with_no_parameters_passes(engine):
    assert engine.check_conditions([], ConditionCtx(state=_state())).passed is True


def test_membership_short_circuits_the_static_half_on_a_pass(engine):
    engine.store.save({"id": "liq", "conditions": [{"id": "price", "value": 20}]})
    engine.reload()
    engine.resolve_members({"AAA": _state()})
    inside = engine.check(engine.get("liq"), ConditionCtx(state=_state(symbol="AAA")))
    assert inside.passed is True
    assert [c.name for c in inside.checks] == ["universe_static"], "one lookup, not N evaluations"


def test_a_membership_miss_reports_which_condition_blocked(engine):
    """An unattributed block is untunable, so a miss pays for the detail."""
    engine.store.save({"id": "liq", "conditions": [
        {"id": "price", "value": 20}, {"id": "atr_pct", "value": 0.1}]})
    engine.reload()
    engine.resolve_members({"AAA": _state()})
    outside = engine.check(engine.get("liq"),
                           ConditionCtx(state=_state(symbol="ZZZ", prior_close=5.0,
                                                     _last_close=5.0)))
    assert outside.passed is False
    named = {c.name: c.passed for c in outside.checks}
    assert named == {"price": False, "atr_pct": True}


def test_unresolved_membership_evaluates_inline_rather_than_assuming(engine):
    """A profile checked before warmup must not wave symbols through."""
    engine.store.save({"id": "liq", "conditions": [{"id": "price", "value": 100}]})
    engine.reload()
    assert engine.members("liq") is None
    r = engine.check(engine.get("liq"), ConditionCtx(state=_state(), bar={"close": 50.0}))
    assert r.passed is False
    assert r.checks[0].name == "price"


def test_the_result_carries_the_profile_identity_for_the_alert_payload(engine):
    engine.store.save({"id": "hot", "name": "Hot", "conditions": [{"id": "price", "value": 1.0}]})
    engine.reload()
    r = engine.check(engine.get("hot"), ConditionCtx(state=_state(), bar={"close": 50.0}))
    js = r.to_json()
    assert js["id"] == "hot" and js["name"] == "Hot" and js["passed"] is True
    assert len(js["hash"]) == 8 and js["checks"][0]["name"] == "price"


# ── de-duplication ───────────────────────────────────────────────────────────

def test_the_bar_cache_evaluates_a_shared_condition_once(engine):
    calls = {"n": 0}
    real = _state()

    class Counting:
        symbol = "AAA"

        def __getattr__(self, k):
            if k == "rvol":
                calls["n"] += 1
                return 2.0
            return getattr(real, k)

    ctx = ConditionCtx(state=Counting(), bar={"close": 50.0})
    cache = BarProfileCache()
    engine.check_conditions([_cond("rvol", 1.0)], ctx, cache)
    engine.check_conditions([_cond("rvol", 1.0)], ctx, cache)
    assert calls["n"] == 1, "identical conditions across setups should resolve once"


def test_the_bar_cache_keeps_different_thresholds_apart(engine):
    ctx = ConditionCtx(state=_state(rvol=2.0), bar={"close": 50.0})
    cache = BarProfileCache()
    assert engine.check_conditions([_cond("rvol", 1.0)], ctx, cache).passed is True
    assert engine.check_conditions([_cond("rvol", 9.0)], ctx, cache).passed is False


# ── resolution for a setup ───────────────────────────────────────────────────

def test_a_custom_setups_own_profile_id_wins(engine):
    engine.store.save({"id": "mine", "conditions": []})
    engine.reload()
    assert engine.for_setup("cs_x", "mine").id == "mine"
    assert engine.for_setup("cs_x", None).id == ALL_ID


def test_an_unknown_profile_id_resolves_to_nothing_and_passes(engine):
    """A deleted profile must not silently block every alert."""
    cp = engine.for_setup("cs_x", "deleted_profile")
    assert cp is None
    assert engine.check(cp, ConditionCtx(state=_state())).passed is True


def test_payload_has_what_the_universe_panel_needs(engine):
    engine.resolve_members({"AAA": _state()})
    p = engine.payload()
    assert {"profiles", "assignments", "system_keys", "members"} <= set(p)
    assert all("summary" in x and "hash" in x for x in p["profiles"])


# ── parameter sets: the mirror of a universe filter ──────────────────────────

def test_a_parameter_set_rejects_a_static_condition(tmp_path):
    from scanner.profiles import ParamSetStore
    st = ParamSetStore(tmp_path / "ps", defaults=tmp_path / "none.json")
    with pytest.raises(ProfileError, match="universe condition"):
        st.save({"id": "ps_x", "conditions": [{"id": "price", "op": "gte", "value": 10}]})


def test_a_universe_filter_still_rejects_a_dynamic_one(tmp_path):
    st = ProfileStore(tmp_path / "up", defaults=tmp_path / "none.json")
    with pytest.raises(ProfileError, match="setup parameter"):
        st.save({"id": "up_x", "conditions": [{"id": "rvol", "op": "gte", "value": 2}]})


def test_a_parameter_set_round_trips_and_is_tagged(tmp_path):
    from scanner.profiles import KIND_PARAMS, ParamSetStore
    st = ParamSetStore(tmp_path / "ps", defaults=tmp_path / "none.json")
    p = st.save({"id": "ps_x", "name": "Hot",
                 "conditions": [{"id": "rvol", "op": "gte", "value": 2.0}]})
    assert p["kind"] == KIND_PARAMS
    assert st.get("ps_x")["conditions"][0]["id"] == "rvol"


def test_params_for_returns_the_sets_conditions(tmp_path):
    from scanner.profiles import ParamSetStore
    sets = ParamSetStore(tmp_path / "ps", defaults=tmp_path / "none.json")
    sets.save({"id": "ps_x", "name": "Hot", "conditions": [{"id": "rvol", "op": "gte", "value": 2.0}]})
    eng = ProfileEngine(ProfileStore(tmp_path / "up", defaults=tmp_path / "none.json"),
                        SetupProfiles(tmp_path / "a.json"), sets)
    assert [c["id"] for c in eng.params_for("ps_x")] == ["rvol"]
    assert eng.params_for("ps_missing") == []
    assert eng.params_for(None) == []


def test_no_parameter_set_is_seeded():
    """No parameter set ships by default. Seeding one would bring back a set
    the dashboard does not show, the next time the paramsets directory
    happens to be empty."""
    from scanner.profiles import ParamSetStore
    import pathlib, tempfile
    st = ParamSetStore(pathlib.Path(tempfile.mkdtemp()))
    assert st.load_all() == []
