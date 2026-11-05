"""RS5 clearing protection with the real native extension: the
``clearing_protection`` region-batch column in both native ``set_region_state``
paths (``EcologySimulator`` and ``AgentSimulator``), its validation, the
consumption/reset of the transient input over several turns, the returned
``clearing_active``/``cover_not_cleared`` receipts, parity of the native tick
with the pure-Python fallback (``ecology._tick_forest``) on the same worlds,
and short native runs whose warden charges close against the accumulator.
docs/integration/clearing-protection.md.
"""
from __future__ import annotations

import copy

import pyarrow as pa
import pytest

from chronicler import clearing_protection as cp
from chronicler.climate import ClimatePhase
from chronicler.ecology import tick_ecology
from chronicler.livelihoods import after_ecology, before_ecology, configure_livelihoods
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world

chronicler_agents = pytest.importorskip("chronicler_agents")
EcologySimulator = chronicler_agents.EcologySimulator
AgentSimulator = chronicler_agents.AgentSimulator

pytestmark = pytest.mark.native

RECEIPTS = ["clearing_active", "cover_not_cleared"]


def _batch(n=3, populations=(40, 40, 10), protection=None, forest=0.5, controller=0):
    data = {
        "region_id": pa.array(range(n), type=pa.uint16()),
        "terrain": pa.array([3] * n, type=pa.uint8()),
        "carrying_capacity": pa.array([60] * n, type=pa.uint16()),
        "population": pa.array(list(populations)[:n], type=pa.uint16()),
        "soil": pa.array([0.6] * n, type=pa.float32()),
        "water": pa.array([0.7] * n, type=pa.float32()),
        "forest_cover": pa.array([forest] * n, type=pa.float32()),
        "controller_civ": pa.array([controller] * n, type=pa.uint8()),
    }
    if protection is not None:
        data["clearing_protection"] = protection
    return pa.record_batch(data)


def _tick(sim, n=3, turn=0, phase=0):
    return sim.tick_ecology(turn, phase, [False] * n, [False] * n)


def _col(batch, name):
    return batch.column(name).to_pylist()


# --- The column in both native paths --------------------------------------------------

@pytest.mark.parametrize("make", [lambda: EcologySimulator(), lambda: AgentSimulator(num_regions=3, seed=42)])
def test_the_column_is_applied_at_the_clearing_decision(make):
    off, on = make(), make()
    off.set_region_state(_batch())
    on.set_region_state(_batch(protection=pa.array([1.0, 0.5, 1.0], type=pa.float32())))
    absent, _ = _tick(off)
    present, _ = _tick(on)
    # Without the column the output keeps its exact schema; with it the two
    # receipts are appended.
    assert not set(RECEIPTS) & set(absent.schema.names)
    assert present.schema.names == absent.schema.names + RECEIPTS
    f_off, f_on = _col(absent, "forest_cover"), _col(present, "forest_cover")
    assert f_off[0] == pytest.approx(0.48, abs=1e-6) and f_on[0] == pytest.approx(0.5, abs=1e-6)   # p = 1
    assert f_on[1] == pytest.approx(0.49, abs=1e-6)                                                 # p = 0.5
    assert f_on[2] == f_off[2]                                    # no pressure: p changes nothing
    assert _col(present, "clearing_active") == [True, True, False]
    assert _col(present, "cover_not_cleared") == pytest.approx([0.02, 0.01, 0.0], abs=1e-7)
    for name in ("soil", "water", "current_turn_yield_0", "mine_soil"):
        assert _col(present, name) == _col(absent, name)


@pytest.mark.parametrize("make", [lambda: EcologySimulator(), lambda: AgentSimulator(num_regions=3, seed=42)])
def test_a_zero_column_is_the_absent_tick_bit_for_bit(make):
    off, zero = make(), make()
    for turn in range(30):
        phase = turn // 6 % 4
        off.set_region_state(_batch())
        zero.set_region_state(_batch(protection=pa.array([0.0] * 3, type=pa.float32())))
        a, ea = _tick(off, turn=turn, phase=phase)
        b, eb = _tick(zero, turn=turn, phase=phase)
        assert b.select(a.schema.names).equals(a)
        assert eb.equals(ea)
        assert _col(b, "cover_not_cleared") == [0.0] * 3


@pytest.mark.parametrize("make", [lambda: EcologySimulator(), lambda: AgentSimulator(num_regions=3, seed=42)])
def test_the_transient_input_is_consumed_and_reset_every_turn(make):
    sim = make()
    sim.set_region_state(_batch(protection=pa.array([1.0] * 3, type=pa.float32())))
    first, _ = _tick(sim, turn=0)
    assert _col(first, "forest_cover")[0] == pytest.approx(0.5, abs=1e-6)
    # A second tick without a new batch: the input was consumed.
    second, _ = _tick(sim, turn=1)
    assert not set(RECEIPTS) & set(second.schema.names)
    assert _col(second, "forest_cover")[0] == pytest.approx(0.48, abs=1e-6)
    # A new batch without the column resets it (absent = no protection).
    sim.set_region_state(_batch(protection=pa.array([1.0] * 3, type=pa.float32())))
    sim.set_region_state(_batch())
    third, _ = _tick(sim, turn=2)
    assert not set(RECEIPTS) & set(third.schema.names)
    assert _col(third, "forest_cover")[0] == pytest.approx(0.48, abs=1e-6)
    # The input never reaches the checkpoint (EcologySimulator and AgentSimulator alike).
    sim.set_region_state(_batch(protection=pa.array([1.0] * 3, type=pa.float32())))
    with_p = sim.checkpoint_state()
    sim.set_region_state(_batch())
    assert sim.checkpoint_state() == with_p
    assert "clearing_protection" not in type(sim).checkpoint_schema()[2]


@pytest.mark.parametrize("bad", [
    pa.array([1.5, 0.0, 0.0], type=pa.float32()),
    pa.array([-0.1, 0.0, 0.0], type=pa.float32()),
    pa.array([float("nan"), 0.0, 0.0], type=pa.float32()),
    pa.array([None, 0.0, 0.0], type=pa.float32()),
    pa.array([1.0, 0.0, 0.0], type=pa.float64()),
])
@pytest.mark.parametrize("make", [lambda: EcologySimulator(), lambda: AgentSimulator(num_regions=3, seed=42)])
def test_a_malformed_column_is_refused_before_any_change(make, bad):
    sim = make()
    sim.set_region_state(_batch())
    before = sim.checkpoint_state()
    with pytest.raises(ValueError, match="clearing_protection|clearing protection"):
        sim.set_region_state(_batch(populations=(1, 1, 1), protection=bad))
    assert sim.checkpoint_state() == before


# --- Native tick against the Python fallback --------------------------------------------

def _world(*flags, seed=1):
    world = generate_world(seed=seed)
    if flags:
        configure_livelihoods(world, _build_parser().parse_args(list(flags)), agent_mode="off")
    for region in world.regions:
        region.population = 1
    for civ in world.civilizations:
        civ.treasury = 100
    for rid, owner, cover in ((0, 0, 0.6), (1, 0, 0.7), (2, 0, 0.65), (3, 1, 0.55)):
        region = world.regions[rid]
        region.terrain = "forest"
        region.controller = world.civilizations[owner].name
        region.population = region.carrying_capacity
        region.ecology.forest_cover = cover
        region.ecology.water = 0.7
    return world


def _native_runtime(world):
    from chronicler.agent_bridge import configure_ecology_runtime
    sim = EcologySimulator()
    configure_ecology_runtime(sim, world)
    return sim


@pytest.mark.parametrize("mode", ["enforced", "cost_only"])
def test_native_and_python_fallback_agree_tick_by_tick(mode):
    from chronicler.agent_bridge import build_region_batch
    py = _world("--clearing-protection", "--clearing-protection-mode", mode)
    nat = copy.deepcopy(py)
    runtime = _native_runtime(nat)
    phases = [ClimatePhase.TEMPERATE] * 3 + [ClimatePhase.COOLING] * 3 + [ClimatePhase.DROUGHT] * 2
    for k, phase in enumerate(phases):
        if k == 4:                                   # partial funding on one side of the comparison too
            for w in (py, nat):
                w.civilizations[0].treasury = 3
        for w in (py, nat):
            before_ecology(w, acc=None)
        runtime.set_region_state(build_region_batch(nat))
        tick_ecology(nat, phase, acc=None, ecology_runtime=runtime)
        tick_ecology(py, phase, acc=None)
        for w in (py, nat):
            after_ecology(w, acc=None)
            w.turn += 1
        rp = {r.region_id: r for r in py.livelihoods.clearing_protection.frame}
        rn = {r.region_id: r for r in nat.livelihoods.clearing_protection.frame}
        assert rp.keys() == rn.keys() and rp
        for rid in rp:
            a, b = rp[rid], rn[rid]
            assert (a.source, b.source) == ("python", "native")
            assert (a.clearing_active, a.paid_planned, a.p_applied, a.charged) == \
                (b.clearing_active, b.paid_planned, b.p_applied, b.charged)
            assert a.cover_not_cleared == pytest.approx(b.cover_not_cleared, abs=1e-7)
        for i, (a, b) in enumerate(zip(py.regions, nat.regions)):
            # Pressured regions (0-3: clearing, no regrowth) agree to float32
            # precision; elsewhere regrowth's 4-decimal rounding of a float32
            # versus a float64 rate may differ by one step (the legacy
            # parity suite's clamped-field tolerance).
            tol = 1e-6 if i <= 3 else 1.5e-4
            assert a.ecology.forest_cover == pytest.approx(b.ecology.forest_cover, abs=tol), (k, i)
        assert [c.treasury for c in py.civilizations] == [c.treasury for c in nat.civilizations]
    c = py.livelihoods.clearing_protection.counters
    assert c["charged"] > 0 and c["partial_funded_turns"] > 0
    assert (c["cover_not_cleared"] > 0) == (mode == "enforced")


def test_planning_tests_pressure_in_the_precision_of_the_deciding_engine():
    """Review B 2026-11-05: with a tuned ``ecology.forest_pop_ratio`` f32 cannot
    represent (0.65; capacity 180, population 117) the native f32 decision
    clears while a float64 plan saw no pressure, so the clearing went
    unprotected (``not_planned``). Planning now follows the engine Phase 9
    names: native plans pressure and protects, the Python fallback neither."""
    from chronicler.agent_bridge import build_region_batch
    world = _world("--clearing-protection")
    world.tuning_overrides = {"ecology.forest_pop_ratio": 0.65}
    for region in world.regions:
        region.population = 1
    r0 = world.regions[0]
    r0.carrying_capacity, r0.population, r0.ecology.forest_cover = 180, 117, 0.6
    py, nat = world, copy.deepcopy(world)
    runtime = _native_runtime(nat)
    before_ecology(nat, acc=None, native=True)
    before_ecology(py, acc=None, native=False)
    assert cp.under_pressure(nat, nat.regions[0]) and not cp.under_pressure(py, py.regions[0])
    runtime.set_region_state(build_region_batch(nat))
    tick_ecology(nat, ClimatePhase.TEMPERATE, acc=None, ecology_runtime=runtime)
    tick_ecology(py, ClimatePhase.TEMPERATE, acc=None)
    for w in (py, nat):
        after_ecology(w, acc=None)
    native_row = {r.region_id: r for r in nat.livelihoods.clearing_protection.frame}.get(0)
    assert native_row is not None and native_row.clearing_active and native_row.pressure_planned
    assert native_row.p_applied == 1.0 and native_row.cover_not_cleared > 0
    assert not [u for u in nat.livelihoods.clearing_protection.unprotected if u.region_id == 0]
    assert 0 not in {r.region_id for r in py.livelihoods.clearing_protection.frame}
    assert py.regions[0].ecology.forest_cover == pytest.approx(0.6)          # no clearing in float64
    assert nat.regions[0].ecology.forest_cover == pytest.approx(0.6)         # cleared, then fully protected


def test_an_extension_that_ignores_the_column_is_refused():
    world = _world("--clearing-protection")
    before_ecology(world, acc=None)
    batch = _batch()                                 # a tick output without receipts
    with pytest.raises(RuntimeError, match="clearing receipts"):
        cp.observe_native(world, batch)


# --- Short native runs: cover kept and the books close --------------------------------------

def _run(mode, agents, turns=40, seed=1, monkeypatch=None, tmp_path=None):
    import argparse

    from chronicler.main import execute_run
    charges = []
    real = cp.after_ecology

    def audited(world, acc):
        start = acc.checkpoint() if acc is not None else 0
        treasury = [c.treasury for c in world.civilizations]
        events = real(world, acc)
        state = world.livelihoods.clearing_protection
        booked = {}
        if acc is not None:
            for change in acc._changes[start:]:
                assert change.stat == "treasury" and change.category == "keep"
                booked[change.civ_id] = booked.get(change.civ_id, 0) - change.delta
        else:
            booked = {i: a - c.treasury for i, (a, c) in enumerate(zip(treasury, world.civilizations))
                      if a != c.treasury}
        receipts = {}
        for r in state.frame:
            assert r.source == "native"
            if r.charged:
                receipts[r.payer] = receipts.get(r.payer, 0) + r.charged
        assert booked == receipts
        charges.append(sum(receipts.values()))
        return events

    monkeypatch.setattr(cp, "after_ecology", audited)
    folder = tmp_path / f"{agents}_{mode}"
    args = argparse.Namespace(
        seed=seed, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, simulate_only=True, agents=agents, tuning_overrides={},
        clearing_protection=True, clearing_protection_mode=mode,
    )
    execute_run(args)
    monkeypatch.undo()
    return charges, folder


@pytest.mark.parametrize("agents", ["off", "hybrid"])
def test_a_native_run_keeps_protected_cover_and_its_charges_close(agents, monkeypatch, tmp_path):
    import json
    runs = {}
    for mode in ("enforced", "cost_only"):
        charges, folder = _run(mode, agents, monkeypatch=monkeypatch, tmp_path=tmp_path)
        state = json.loads((folder / "state.json").read_text())
        runs[mode] = (charges, state["livelihoods"]["clearing_protection"])
    (ce, se), (cc, sc) = runs["enforced"], runs["cost_only"]
    assert sum(ce) == se["counters"]["charged"] > 0
    assert sum(cc) == sc["counters"]["charged"] > 0
    assert se["counters"]["cover_not_cleared"] > 0 and sc["counters"]["cover_not_cleared"] == 0
    assert sc["counters"]["cover_would_keep"] > 0
