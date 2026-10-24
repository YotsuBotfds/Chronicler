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
    straight = _advance(_world(42), 45)
    first = _advance(_world(42), 30)
    # The save point carries live state in all three systems.
    assert first.epidemics.deaths_total > 0
    assert first.finance.loans
    assert first.diplomacy.treaties
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


def test_maritime_with_all_three_runs_and_persists_state():
    world = _advance(_sea_world(), 30)
    counters = world.maritime.counters
    assert counters["fleets_commissioned"] > 0 and counters["naval_battles"] > 0
    assert counters["sea_trade"] > 0 and counters["piracy_losses"] > 0
    assert world.epidemics.deaths_total > 0 and world.finance.loans and world.diplomacy.treaties
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.maritime == world.maritime


def test_save_load_resume_identity_with_maritime_and_all_three_on(tmp_path):
    straight = _advance(_sea_world(), 45)
    first = _advance(_sea_world(), 30)
    # The save point carries fleets at sea and live state in every system.
    assert first.maritime.fleets
    assert first.epidemics.deaths_total > 0 and first.finance.loans and first.diplomacy.treaties
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_maritime_with_all_three_is_deterministic():
    a = _advance(_sea_world(), 30)
    b = _advance(_sea_world(), 30)
    assert a.model_dump_json() == b.model_dump_json()
