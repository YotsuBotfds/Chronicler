"""Techniques switched on together with epidemiology, finance and diplomacy.

Each system has its own suite (``test_techniques.py`` and the wave-3 suites);
these tests cover running all four in one world: save/load resume identity,
determinism, every system's state being live, and the technique effects
reaching the other systems' hooks.
"""
from __future__ import annotations

import chronicler.contact_ledger as cl
import chronicler.diplomacy as dp
import chronicler.epidemiology as ep
import chronicler.finance as F
import chronicler.techniques as T
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
    T.set_techniques_enabled(world, True)
    return world


def _advance(world: WorldState, turns: int) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    return world


def test_all_four_systems_run_and_persist_state():
    world = _advance(_world(42), 60)
    assert world.epidemics is not None and world.finance is not None
    assert world.diplomacy is not None and world.techniques is not None
    assert world.techniques.rows and world.techniques.counts.get("invented", 0) > 0
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.epidemics == world.epidemics
    assert dumped.finance == world.finance
    assert dumped.diplomacy == world.diplomacy
    assert dumped.techniques == world.techniques


def test_save_load_resume_identity_with_all_four_on(tmp_path):
    straight = _advance(_world(42), 75)
    first = _advance(_world(42), 60)
    # The save point carries live state in every system.
    assert first.epidemics.deaths_total > 0
    assert first.finance.loans
    assert first.diplomacy.treaties
    assert any(0.0 < row[2] < 0.9 for row in first.techniques.rows), "practice still spreading"
    path = tmp_path / "state.json"
    first.save(path)
    resumed = _advance(WorldState.load(path), 15)
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_all_four_on_is_deterministic():
    a = _advance(_world(7), 50)
    b = _advance(_world(7), 50)
    assert a.model_dump_json() == b.model_dump_json()


def test_technique_effects_reach_epidemiology_and_finance():
    world = _advance(_world(42), 60)
    st = world.techniques
    # Seed medicine and banking practice into the first civ's regions and re-measure.
    owner = world.civilizations[0]
    members = [i for i, r in enumerate(world.regions) if r.controller == owner.name]
    assert members
    rows = {(r[0], r[1]): r for r in st.rows}
    for key in ("writing", "herbalism", "physicians", "coinage", "law_codes", "banking", "lazarets"):
        k = T.TECHNIQUE_INDEX[key]
        for r in members:
            rows[(r, k)] = (r, k, 0.9, -1, T.CH_SEEDED, 0)
    st.rows = [rows[k] for k in sorted(rows)]
    st.civ_levels[0] = sorted({**dict(st.civ_levels[0]),
                               **{T.TECHNIQUE_INDEX[k]: 0.9 for k in ("banking", "lazarets", "law_codes")}}.items())
    st.invalidate()
    cfr = T.epidemic_cfr_factors(world)
    assert all(cfr[r] < 1.0 for r in members)
    assert T.quarantine_efficacy(world, owner.name, ep.QUARANTINE_EFFICACY) > ep.QUARANTINE_EFFICACY
    f = world.finance.civs[0]
    base = (F.DOMESTIC_WEALTH_SHARE * f.merchant_wealth
            + F.DOMESTIC_REVENUE_TURNS * f.revenue_ema * F._merchant_influence(owner)) * f.domestic_trust
    expected = max(0, int(base * T.credit_factor(world, 0)) - F.outstanding_debt(world, 0, F.DOMESTIC))
    assert T.credit_factor(world, 0) > 1.2
    assert F._domestic_capacity(world, 0, owner, f) == expected
