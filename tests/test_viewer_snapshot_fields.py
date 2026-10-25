"""Viewer-only snapshot fields: ``history[n].food`` and ``history[n].migration``.

Both are read after the turn from state the simulation already keeps
(mutual aid's food observations and convoys, the agent event log); they touch
no state or RNG and are omitted where the run cannot produce them, so
agents-off bundles keep their bytes. See docs/integration/viewer-systems.md.
"""
from __future__ import annotations

import argparse
import json

import pytest

from chronicler.main import _food_snapshot_fields, _migration_snapshot_fields
from chronicler.models import AgentEventRecord, MutualAidState, MutualAidTransfer, Region, TurnSnapshot
from chronicler.mutual_aid import snapshot_summary


@pytest.fixture
def food_world(make_world):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    world.regions.append(Region(name="Mine", terrain="hills", carrying_capacity=60, resources="mineral",
                                controller=civ.name))
    world.regions.append(Region(name="Waste", terrain="desert", carrying_capacity=10, resources="barren"))
    civ.regions = [world.regions[0].name, "Mine"]
    world.invalidate_region_map()
    world.mutual_aid_enabled = True
    world.agent_mode = "hybrid"
    world.turn = 8  # after completing turn 7
    return world


def _state(controller, turn, suff):
    return MutualAidState(controller=controller, last_observed_turn=turn, food_sufficiency=suff)


def _transfer(turn, donor, recipient, received):
    return MutualAidTransfer(turn=turn, controller="Civ0", donor=donor, recipient=recipient,
                             sent=received, received=received, transit_loss=0.0, treasury_cost=1)


def test_food_summary_reads_the_completed_turn_by_region_index(food_world):
    home = food_world.regions[0].name
    food_world.mutual_aid_state = {
        home: _state("Civ0", 7, 1.734),
        "Mine": _state("Civ0", 7, 0.2049),
        "Waste": _state("Civ0", 5, 0.9),  # stale: not observed in the completed turn
    }
    food_world.mutual_aid_last_transfers = [
        _transfer(7, home, "Mine", {"grain": 2.0, "fish": 0.46}),
        _transfer(6, home, "Mine", {"grain": 9.0}),  # an earlier turn's convoy
    ]
    before = food_world.model_dump_json()
    summary = snapshot_summary(food_world)
    assert summary == {"sufficiency": [1.73, 0.2, None], "aid": [[0, 1, 2.5]]}
    assert food_world.model_dump_json() == before


def test_food_field_needs_mutual_aid_on_an_agent_economy(food_world):
    assert set(_food_snapshot_fields(food_world)) == {"food"}
    food_world.agent_mode = "off"
    assert _food_snapshot_fields(food_world) == {}
    food_world.agent_mode = "hybrid"
    food_world.mutual_aid_enabled = False
    assert _food_snapshot_fields(food_world) == {}


def _move(turn, src, dst, kind="migration"):
    return AgentEventRecord(turn=turn, agent_id=1, event_type=kind, region=src, target_region=dst,
                            civ_affinity=0, occupation=0)


def test_migration_counts_the_completed_turn_by_region_pair(food_world):
    food_world.agent_events_raw = [
        _move(6, 0, 1),            # an earlier turn
        _move(7, 1, 0), _move(7, 0, 1), _move(7, 1, 0),
        _move(7, 2, 2),            # not a move between regions
        _move(7, 0, 9),            # no such region
        _move(7, 0, 2, kind="occupation_switch"),
    ]
    assert _migration_snapshot_fields(food_world) == {"migration": [[0, 1, 1], [1, 0, 2]]}
    # The next turn reads only its own moves (the index serves each turn once appended).
    food_world.agent_events_raw.append(_move(8, 2, 1))
    food_world.turn = 9
    assert _migration_snapshot_fields(food_world) == {"migration": [[2, 1, 1]]}
    food_world.turn = 10
    assert _migration_snapshot_fields(food_world) == {"migration": []}


def test_migration_field_needs_an_agent_event_log(food_world):
    for mode in ("off", "demographics-only", None):
        food_world.agent_mode = mode
        assert _migration_snapshot_fields(food_world) == {}
    food_world.agent_mode = "shadow"
    assert "migration" in _migration_snapshot_fields(food_world)


def test_dormant_fields_are_omitted_from_the_snapshot():
    base = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "food" not in base.model_dump(mode="json")
    assert "migration" not in base.model_dump(mode="json")
    full = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={},
                        food={"sufficiency": [1.0], "aid": []}, migration=[[0, 1, 3]])
    dumped = full.model_dump(mode="json")
    assert dumped["food"] == {"sufficiency": [1.0], "aid": []}
    assert dumped["migration"] == [[0, 1, 3]]
    assert TurnSnapshot.model_validate(dumped) == full


def _run(tmp_path, **flags):
    from chronicler.main import execute_run
    args = argparse.Namespace(
        seed=11, turns=12, civs=3, regions=6,
        output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        pause_every=None, simulate_only=True, **flags,
    )
    execute_run(args)
    return json.loads((tmp_path / "chronicle_bundle.json").read_text(encoding="utf-8"))


def test_agents_off_bundles_carry_neither_field(tmp_path):
    bundle = _run(tmp_path, agents="off")
    assert not any("food" in snap or "migration" in snap for snap in bundle["history"])


@pytest.mark.native
def test_hybrid_bundle_carries_food_and_migration(tmp_path):
    pytest.importorskip("chronicler_agents")
    bundle = _run(tmp_path, agents="hybrid")
    n_regions = len(bundle["world_state"]["regions"])
    history = bundle["history"]
    assert all("food" in snap and "migration" in snap for snap in history)
    for snap in history:
        assert len(snap["food"]["sufficiency"]) == n_regions
        assert all(v is None or 0 <= v <= 2 for v in snap["food"]["sufficiency"])
        for donor, recipient, amount in snap["food"]["aid"]:
            assert 0 <= donor < n_regions and 0 <= recipient < n_regions and amount > 0
        rows = snap["migration"]
        assert rows == sorted(rows)
        assert all(0 <= a < n_regions and 0 <= b < n_regions and a != b and n > 0 for a, b, n in rows)
    assert any(snap["migration"] for snap in history)
    assert any(v is not None for snap in history for v in snap["food"]["sufficiency"])
