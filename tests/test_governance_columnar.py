"""Columnar governance agent rows equal the record-per-agent adapter they replaced.

The ``_legacy_*`` functions are the pre-columnar ``governance_runtime`` code
(``_agent_columns``/``_build_context`` row grouping, the agent branch of
``_elite_metrics`` feeding ``compute_elite_metrics``, and the MMP inputs of
``_advance_psi``), kept here as the oracle.
"""
from __future__ import annotations

import copy
import math
import random

import numpy as np
import pyarrow as pa
import pytest

from chronicler import elite_metrics as g02
from chronicler import governance_runtime as gr
from chronicler import governance_stress as stress
from chronicler.models import GreatPerson
from chronicler.world_gen import generate_world

try:
    from chronicler_agents import AgentSimulator as _AgentSimulator
    _AGENTS_AVAILABLE = isinstance(_AgentSimulator, type)
except Exception:  # pragma: no cover - depends on the optional extension
    _AGENTS_AVAILABLE = False

_NEEDED = ("id", "civ_affinity", "occupation", "satisfaction", "skill", "wealth", "age",
           "settlement_id", "region", "belief")
_OCCUPATIONS = tuple(g02.Occupation)


def _legacy_rows(batch, n_civs):
    columns = {n: batch.column(n).to_pylist() for n in _NEEDED}
    rows, region_beliefs = {}, {}
    for k in range(len(columns["id"])):
        civ_id = columns["civ_affinity"][k]
        if civ_id is None or civ_id >= n_civs:
            continue
        rows.setdefault(civ_id, []).append(k)
        rid, bid = columns["region"][k], columns["belief"][k]
        dist = region_beliefs.setdefault(rid, {})
        dist[bid] = dist.get(bid, 0) + 1
    return columns, rows, region_beliefs


def _legacy_elite(world, civ_idx, civ, gov, columns, by_civ):
    turn = world.turn
    position_bonus = math.fsum(
        gr.INSTITUTION_EFFECTS[gr.g01.InstitutionType(i.institution_type)].elite_position_bonus * i.legitimacy
        for i in gov.institutions)
    divisor = max(1, int(round(gr.ELITE_CALIBRATION.elite_positions_divisor / (1.0 + position_bonus))))
    calibration = g02.EliteCalibration(
        ratchet_up_rate=gr.ELITE_CALIBRATION.ratchet_up_rate,
        ratchet_down_rate=gr.ELITE_CALIBRATION.ratchet_down_rate,
        ratchet_cap=gr.ELITE_CALIBRATION.ratchet_cap,
        elite_positions_divisor=divisor,
    )
    agents, greats = [], []
    gps = [gp for gp in civ.great_persons if gp.active and gp.alive]
    cols = columns
    indices = by_civ.get(civ_idx, [])
    present = {}
    max_wealth = 0.0
    sat_total = 0.0
    for k in indices:
        occ = cols["occupation"][k]
        wealth = float(cols["wealth"][k] or 0.0)
        if not math.isfinite(wealth):
            wealth = 0.0
        sat = gr._unit(cols["satisfaction"][k])
        agents.append(g02.AgentEliteInput(
            int(cols["id"][k]), civ_idx, wealth,
            _OCCUPATIONS[occ] if occ is not None and 0 <= occ < len(_OCCUPATIONS) else g02.Occupation.FARMER,
            gr._unit(cols["skill"][k]), sat))
        present[int(cols["id"][k])] = k
        max_wealth = max(max_wealth, wealth)
        sat_total += sat
    mean_sat = sat_total / len(indices) if indices else gr._unit(civ.stability / 100)
    for key, gp in gr._gp_keys(gps):
        backed = gp.agent_id if gp.agent_id is not None and gp.agent_id in present else None
        greats.append(g02.GreatPersonEliteInput(
            key, civ_idx, backed,
            None if backed is not None else max_wealth,
            None if backed is not None else mean_sat))
    output = g02.compute_elite_metrics(
        turn=turn,
        civilizations=(g02.CivEliteInput(civ_idx, max(0, int(civ.population)),
                                         g02.EliteRatchetState(turn - 1, gov.conspicuous_consumption_index)),),
        agents=tuple(agents), great_persons=tuple(greats),
        calibration=calibration, conventions=gr.ELITE_CONVENTIONS,
    )
    return output.civilizations[0]


def _legacy_mmp(columns, indices):
    return stress.mmp_from_agents([columns["wealth"][k] for k in indices],
                                  [columns["age"][k] or 0 for k in indices],
                                  [columns["settlement_id"][k] or 0 for k in indices], gr.STRESS)


def _scalars(m):
    return (m.elite_positions, m.elite_qualifier_count, m.elite_office_holder_count,
            m.frustrated_aspirant_count, m.conspicuous_consumption_index.hex(), m.emp.hex())


def _assert_matches_legacy(world, batch):
    world._agent_snapshot = batch
    ctx = gr._build_context(world, None)
    n_civs = len(world.civilizations)
    columns, by_civ, beliefs = _legacy_rows(batch, n_civs)
    assert {c: list(v) for c, v in ctx.rows["by_civ"].items()} == by_civ
    assert all(isinstance(c, int) for c in ctx.rows["by_civ"])
    # Consumers read region totals and the share of one faith (never a null key).
    for rid in range(len(world.regions)):
        for faith in range(n_civs + 2):
            old, new = beliefs.get(rid, {}), ctx.region_beliefs.get(rid, {})
            assert (sum(old.values()), old.get(faith, 0)) == (sum(new.values()), new.get(faith, 0))
    for civ_idx, civ in enumerate(world.civilizations):
        gov = gr._ensure_state(world, civ)
        gov.conspicuous_consumption_index = 0.37
        # Several office counts, so the cut through the ranked candidates moves.
        for population in (civ.population, 60, 150, 400, 2000):
            civ.population = population
            reference = _legacy_elite(world, civ_idx, civ, copy.deepcopy(gov), columns, by_civ)
            counts = gr._elite_metrics(world, civ_idx, civ, copy.deepcopy(gov), ctx)
            assert _scalars(counts) == _scalars(reference)
        indices = by_civ.get(civ_idx, [])
        new_mmp = stress.mmp_from_agent_arrays(
            ctx.rows["columns"]["wealth"][ctx.rows["by_civ"].get(civ_idx, gr._NO_ROWS)],
            ctx.rows["columns"]["age"][ctx.rows["by_civ"].get(civ_idx, gr._NO_ROWS)],
            ctx.rows["columns"]["settlement_id"][ctx.rows["by_civ"].get(civ_idx, gr._NO_ROWS)], gr.STRESS)
        old_mmp = _legacy_mmp(columns, indices)
        assert new_mmp[0].hex() == old_mmp[0].hex()
        assert [v.hex() for v in new_mmp[2:]] == [v.hex() for v in old_mmp[2:]]
        assert abs(new_mmp[1]) == abs(old_mmp[1])


def _world(seed):
    world = generate_world(seed=seed, num_regions=10, num_civs=4)
    gr.set_governance_enabled(world, True)
    world.turn = 12
    return world


def _add_great_persons(world, rng, ids):
    for civ_idx, civ in enumerate(world.civilizations):
        for k in range(rng.choice([0, 1, 3])):
            agent_id = rng.choice(ids + [None, 10 ** 6 + k]) if ids else None
            civ.great_persons.append(GreatPerson(
                name=f"Notable {civ_idx}-{k % 2}", role="general", trait="bold",
                civilization=civ.name, origin_civilization=civ.name, born_turn=3,
                agent_id=agent_id))


def _random_batch(rng, n, n_civs, n_regions, *, nulls=False):
    def maybe_null(values):
        return [None if nulls and rng.random() < 0.03 else v for v in values]

    special = [float("nan"), float("inf"), -float("inf"), -0.0, 0.0, -1.0, 1.0, 2.0, 0.3, 0.8]
    unit = [rng.choice(special) if rng.random() < 0.1 else rng.random() for _ in range(n)]
    skill = [rng.choice(special) if rng.random() < 0.1 else rng.choice([rng.random(), 0.8, 0.95])
             for _ in range(n)]
    wealth = [rng.choice(special) if rng.random() < 0.1 else rng.choice([1.0, 2.0, rng.random() * 40])
              for _ in range(n)]
    return pa.record_batch({
        "id": pa.array(rng.sample(range(5 * n + 10), n), type=pa.uint32()),
        "civ_affinity": pa.array(maybe_null([rng.choice(list(range(n_civs)) + [n_civs, 254, 255])
                                             for _ in range(n)]), type=pa.uint8()),
        "occupation": pa.array(maybe_null([rng.choice([0, 1, 2, 3, 4, 4, 7]) for _ in range(n)]),
                               type=pa.uint8()),
        "satisfaction": pa.array(maybe_null(unit), type=pa.float32()),
        "skill": pa.array(maybe_null(skill), type=pa.float32()),
        "wealth": pa.array(maybe_null(wealth), type=pa.float32()),
        "age": pa.array(maybe_null([rng.randrange(80) for _ in range(n)]), type=pa.uint16()),
        "settlement_id": pa.array(maybe_null([rng.choice([0, 0, 3, 9]) for _ in range(n)]),
                                  type=pa.uint16()),
        "region": pa.array(maybe_null([rng.randrange(n_regions) for _ in range(n)]), type=pa.uint16()),
        "belief": pa.array(maybe_null([rng.choice([0, 1, 2, 3, 255]) for _ in range(n)]), type=pa.uint8()),
    })


@pytest.mark.parametrize("seed", range(12))
def test_synthetic_snapshot_matches_legacy_adapter(seed):
    rng = random.Random(seed)
    world = _world(seed)
    n = rng.choice([0, 1, 5, 40, 400, 3000])
    batch = _random_batch(rng, n, len(world.civilizations), len(world.regions))
    _add_great_persons(world, rng, batch.column("id").to_pylist())
    _assert_matches_legacy(world, batch)


@pytest.mark.parametrize("seed", range(4))
def test_snapshot_with_null_cells_matches_legacy_adapter(seed):
    rng = random.Random(100 + seed)
    world = _world(seed)
    batch = _random_batch(rng, 600, len(world.civilizations), len(world.regions), nulls=True)
    # The record adapter crashed on null ids, so ids stay non-null here.
    _add_great_persons(world, rng, batch.column("id").to_pylist())
    _assert_matches_legacy(world, batch)


def test_running_sum_matches_sequential_python_addition():
    rng = np.random.default_rng(5)
    for n in (1, 2, 3, 17, 1000, 65_537):
        values = rng.random(n).astype(np.float32).astype(np.float64)
        values[rng.random(n) < 0.1] = 0.0
        total = 0.0
        for v in values.tolist():
            total += v
        assert float(np.cumsum(values)[-1]).hex() == total.hex()


@pytest.mark.native
@pytest.mark.skipif(not _AGENTS_AVAILABLE, reason="Rust agent extension not available")
def test_native_snapshot_matches_legacy_adapter():
    from chronicler.agent_bridge import AgentBridge
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn

    world = generate_world(seed=21, num_regions=10, num_civs=4)
    gr.set_governance_enabled(world, True)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    for i in range(12):
        run_turn(world, lambda civ, w: ActionEngine(w).select_action(civ, seed=21 + w.turn),
                 lambda w, e: "", seed=21 + i, agent_bridge=bridge)
    batch = bridge._sim.get_snapshot()
    assert batch.num_rows > 0
    ids = batch.column("id").to_pylist()
    _add_great_persons(world, random.Random(4), ids[:50])
    _assert_matches_legacy(world, batch)
