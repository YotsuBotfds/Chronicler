"""Epidemiology, finance and diplomacy switched on together.

Each system has its own suite; these tests cover running them in one world:
save/load resume identity, determinism, and every system's state being live.
"""
from __future__ import annotations

import chronicler.contact_ledger as cl
import chronicler.diplomacy as dp
import chronicler.epidemiology as ep
import chronicler.finance as F
from chronicler.action_engine import ActionEngine
from chronicler.models import WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


def _world(seed: int = 42) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    F.set_finance_enabled(world, True)
    dp.set_diplomacy_enabled(world, True)
    return world


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def test_all_three_systems_run_and_persist_state():
    world = _advance(_world(42), 40)
    assert world.epidemics is not None
    assert world.finance is not None
    assert world.diplomacy is not None
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.epidemics == world.epidemics
    assert dumped.finance == world.finance
    assert dumped.diplomacy == world.diplomacy


def test_save_load_resume_identity_with_all_three_on(tmp_path):
    # Save at the first turn from 30 on where all three systems carry live
    # state (an epidemic has killed, a loan is outstanding, a treaty stands).
    first = _advance(_world(42), 30)
    while not (first.epidemics.deaths_total > 0 and first.finance.loans
               and first.diplomacy.treaties):
        assert first.turn < 80, "no turn with live state in all three systems"
        _advance(first, 1)
    straight = _advance(_world(42), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_all_three_on_is_deterministic():
    a = _advance(_world(7), 30)
    b = _advance(_world(7), 30)
    assert a.model_dump_json() == b.model_dump_json()


# --- Maritime together with epidemiology, finance and diplomacy -------------------------

def _sea_world(seed: int = 11) -> WorldState:
    """A procedural world with sea zones, so fleets, blockades and piracy run."""
    import chronicler.maritime as mt
    world = generate_world(seed=seed, num_regions=32, num_civs=8, worldgen="procedural")
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    F.set_finance_enabled(world, True)
    dp.set_diplomacy_enabled(world, True)
    mt.set_maritime_enabled(world, True)
    return world


def _all_four_live(world: WorldState) -> bool:
    m = world.maritime
    return bool(m.fleets and m.counters["naval_battles"] > 0 and m.counters["sea_trade"] > 0
                and world.epidemics.deaths_total > 0 and world.finance.loans
                and world.diplomacy.treaties)


def _live_save_point() -> WorldState:
    """The first turn from 30 on where every system carries live state:
    fleets at sea after a naval battle, sea trade, an epidemic death, a loan
    and a treaty."""
    world = _advance(_sea_world(), 30)
    while not _all_four_live(world):
        assert world.turn < 90, "no turn with live state in all four systems"
        _advance(world, 1)
    return world


def test_maritime_with_all_three_runs_and_persists_state():
    world = _live_save_point()
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.maritime == world.maritime
    assert dumped.model_dump_json() == world.model_dump_json()


def test_save_load_resume_identity_with_maritime_and_all_three_on(tmp_path):
    first = _live_save_point()
    straight = _advance(_sea_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_maritime_with_all_three_is_deterministic():
    a = _advance(_sea_world(), 30)
    b = _advance(_sea_world(), 30)
    assert a.model_dump_json() == b.model_dump_json()


# --- All five: techniques and maritime with epidemiology, finance and diplomacy --------

def _five_world() -> WorldState:
    import chronicler.techniques as tq
    world = _sea_world()
    tq.set_techniques_enabled(world, True)
    return world


def test_save_load_resume_identity_with_all_five_on(tmp_path):
    first = _advance(_five_world(), 30)
    assert first.techniques is not None and first.maritime.fleets
    assert first.finance.loans and first.diplomacy.treaties
    assert first.epidemics.deaths_total > 0
    straight = _advance(_five_world(), 45)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


# --- Great-person agendas on top of all five --------------------------------------------

def _six_world() -> WorldState:
    """All five systems plus great-person agendas and the governance bucket."""
    import chronicler.gp_agendas as ga
    from chronicler.governance_runtime import set_governance_enabled
    world = _five_world()
    set_governance_enabled(world, True)
    ga.set_gp_agendas_enabled(world, True)
    return world


def test_save_load_resume_identity_with_agendas_and_all_five_on(tmp_path):
    import chronicler.gp_agendas as ga
    first = _advance(_six_world(), 30)
    while not any(ga._is_open(r) for r in first.gp_agendas.records.values()):
        assert first.turn < 90, "no turn with an open great-person agenda"
        _advance(first, 1)
    assert first.techniques is not None and first.maritime.fleets
    assert first.finance.loans and first.diplomacy.treaties
    assert first.gp_agendas.counts["declared"] > 0
    straight = _advance(_six_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.gp_agendas == first.gp_agendas
    _advance(resumed, 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


# --- Nomads with every other system: the ledger, epidemiology, finance, diplomacy,
# --- techniques and maritime ---------------------------------------------------------------

def _all_world() -> WorldState:
    """Seed 11 (32 regions, 8 civs) has a nomadic and two agro-pastoral peoples."""
    import chronicler.nomads as nm
    world = _five_world()
    nm.set_nomads_enabled(world, True)
    return world


def _nomads_live(world: WorldState) -> bool:
    n = world.nomads
    return bool(sum(n.herds) > 0 and n.counters["raids"] + n.counters["raids_repulsed"] > 0
                and any(m != 0 for i, m in enumerate(n.modes) if world.civilizations[i].regions))


def _all_live_save_point() -> WorldState:
    """The first turn from 30 on where herds graze, a raid has happened and
    every other system carries live state."""
    world = _advance(_all_world(), 30)
    while not (_nomads_live(world) and _all_four_live(world) and world.techniques is not None):
        assert world.turn < 120, "no turn with live state in every system"
        _advance(world, 1)
    return world


def test_nomads_with_every_system_run_and_persist_state():
    world = _all_live_save_point()
    assert world.nomads.raids or world.nomads.counters["raids"] > 0
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.nomads == world.nomads
    assert dumped.model_dump_json() == world.model_dump_json()


def test_save_load_resume_identity_with_nomads_and_every_system_on(tmp_path):
    first = _all_live_save_point()
    straight = _advance(_all_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_nomads_with_every_system_is_deterministic():
    a = _advance(_all_world(), 30)
    b = _advance(_all_world(), 30)
    assert a.model_dump_json() == b.model_dump_json()


# --- Everything: nomads and great-person agendas with all five systems -----------------

def _everything_world() -> WorldState:
    import chronicler.gp_agendas as ga
    from chronicler.governance_runtime import set_governance_enabled
    world = _all_world()
    set_governance_enabled(world, True)
    ga.set_gp_agendas_enabled(world, True)
    return world


def test_save_load_resume_identity_with_everything_on(tmp_path):
    first = _advance(_everything_world(), 30)
    while not (_nomads_live(first) and first.gp_agendas.counts["declared"] > 0
               and first.finance.loans and first.diplomacy.treaties):
        assert first.turn < 120, "no turn with live nomads, agendas, loans and treaties"
        _advance(first, 1)
    straight = _advance(_everything_world(), first.turn + 15)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()
