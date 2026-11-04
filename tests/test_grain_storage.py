"""Pure contracts for the opt-in public storage asset; no native mock work."""
from __future__ import annotations

from copy import deepcopy
import pickle

import pyarrow as pa
import pytest

from chronicler import grain_reserves as reserves
from chronicler import grain_storage as S
from chronicler.accumulator import StatAccumulator
from chronicler.economy import FIXED_GOODS
from chronicler.grain_reserves_state import GrainReserveState
from chronicler.world_gen import generate_world


@pytest.fixture
def world():
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    reserves.set_grain_reserves_enabled(w, True)
    reserves._ensure(w)
    civ = w.civilizations[0]
    civ.regions = [r.name for r in w.regions]
    civ.treasury = 100
    w.civilizations[1].regions = []
    for r, granary in zip(w.regions, w.grain_reserves.granaries):
        r.controller = civ.name
        r.stockpile.goods = {"timber": 20.0}
        granary.owner = 0
        granary.grain = 0
    return w


class Commitments:
    def __init__(self, world, timber_reserved=0, timber_pending=0):
        rows = [(i, j, timber_reserved if g == "timber" and i == 0 else 0.0,
                 timber_pending if g == "timber" and i == 0 else 0.0)
                for i in range(len(world.regions)) for j, g in enumerate(FIXED_GOODS)]
        self.batch = pa.record_batch([pa.array([r[0] for r in rows], type=pa.uint16()),
                                      pa.array([r[1] for r in rows], type=pa.uint8()),
                                      pa.array([r[2] for r in rows], type=pa.float32()),
                                      pa.array([r[3] for r in rows], type=pa.float32())],
                                     names=["region_id", "good_slot", "reserved", "pending_departure"])

    def get_stockpile_commitments(self):
        return self.batch


def prepare(w, demand=(10.0, 10.0, 10.0), **kwargs):
    return S.prepare_storage_work(w, demand, commitments={}, **kwargs)


def tick(w, work=None):
    plan = prepare(w)
    S.finish_storage_work(w, plan, plan.requests if work is None else work)
    w.turn += 1
    return plan


def test_disabled_and_old_state_are_unchanged(world):
    before = world.model_dump_json()
    plan = S.prepare_storage_work(world, [], simulator=None)
    assert plan.requests == [0.0] * 3
    S.finish_storage_work(world, plan, [0.0] * 3)
    assert world.model_dump_json() == before
    assert S.storage_limit(world, 0) is None
    assert S.storage_spoilage(world, 0, .03) == .03
    assert S.storage_snapshot(world) is None
    assert '"storage"' not in world.grain_reserves.model_dump_json()
    old_pickle = deepcopy(world.grain_reserves.__getstate__())
    old_pickle["__dict__"].pop("storage", None)
    restored = GrainReserveState.__new__(GrainReserveState)
    restored.__setstate__(old_pickle)
    assert restored.storage is None
    assert "storage" not in GrainReserveState.model_validate_json(
        world.grain_reserves.model_dump_json()).model_dump(mode="json")


def test_disabled_pickle_filter_never_mutates_live_fields(world):
    state = world.grain_reserves
    before = deepcopy(state.__dict__)
    fields = state.__pydantic_fields_set__.copy()
    first = pickle.dumps(state)
    assert state.__dict__ == before
    assert state.storage is None
    assert state.__pydantic_fields_set__ == fields
    assert pickle.dumps(state) == first
    restored = pickle.loads(first)
    assert restored.storage is None
    assert pickle.dumps(restored) == first
    assert restored.storage is None


def test_inherited_asset_wear_and_snapshot_are_explicit(world):
    state = S.enable_storage(world)
    world.grain_reserves.granaries[0].grain = 55.0
    tick(world)
    assert [a.capacity for a in state.assets] == [55.0, 40.0, 40.0]
    assert all(a.condition == pytest.approx(.99) for a in state.assets)
    assert S.storage_limit(world, 0) == pytest.approx(55.0 * .99)
    assert S.storage_spoilage(world, 0, .03) == pytest.approx(.0307)
    assert all(r.treasury_paid == r.delivered == 0 for r in state.receipts)
    before = world.model_dump_json()
    snapshot = S.storage_snapshot(world)
    snapshot.as_dict()["assets"][0]["condition"] = 0
    assert snapshot.as_dict()["assets"][0]["condition"] == pytest.approx(.99)
    with pytest.raises(AttributeError):
        snapshot._payload = "changed"
    assert world.model_dump_json() == before
    assert pickle.loads(pickle.dumps(world.grain_reserves)).storage.assets[0].capacity == 55


def test_private_commitments_and_shared_rounded_treasury_partial_work(world):
    S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 4)
    S.set_storage_policy(world, 1, "expand", 4)
    world.civilizations[0].treasury = 3
    world.regions[0].stockpile.goods["timber"] = 10
    plan = S.prepare_storage_work(world, [10, 10, 10], simulator=Commitments(world, 6, 2))
    assert plan.requests == [1.5, 0.0, 0.0]
    assert world.regions[0].stockpile.goods["timber"] == 8.5
    assert world.civilizations[0].treasury == 3
    acc = StatAccumulator()
    S.finish_storage_work(world, plan, [.5, 0, 0], acc=acc)
    assert world.regions[0].stockpile.goods["timber"] == 9.5
    assert world.civilizations[0].treasury == 3
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == 2
    receipt = world.grain_reserves.storage.receipts[0]
    assert (receipt.timber_reserved, receipt.timber_used, receipt.timber_returned,
            receipt.treasury_paid, receipt.expansion_progress) == (1.5, .5, 1.0, 1, .5)


def test_expansion_is_paid_multi_turn_and_cannot_exceed_resources(world):
    state = S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 4)
    for turn in range(3):
        plan = tick(world)
        assert plan.requests[0] == 4
        assert state.assets[0].capacity == (50 if turn == 2 else 40)
    assert state.assets[0].expansion_progress == 0
    assert state.assets[0].condition == pytest.approx(.97)
    assert world.civilizations[0].treasury == 76
    assert world.regions[0].stockpile.goods["timber"] == 8


def test_repair_needs_complete_batch_and_survives_controller_change(world):
    state = S.enable_storage(world)
    tick(world)
    state.assets[0].condition = .5
    S.set_storage_policy(world, 0, "maintain", 2)
    tick(world)
    assert state.assets[0].condition == pytest.approx(.49)
    assert state.assets[0].repair_progress == 2
    region = world.regions[0]
    world.civilizations[0].regions.remove(region.name)
    world.civilizations[1].regions.append(region.name)
    region.controller = world.civilizations[1].name
    world.civilizations[1].treasury = 100
    tick(world)
    assert state.assets[0].owner == 1
    assert state.assets[0].repair_progress == 0
    assert state.assets[0].condition == pytest.approx(.58)
    assert state.assets[0].capacity == 40
    region.controller = None
    tick(world)
    assert state.assets[0].owner == -1
    assert state.assets[0].condition == pytest.approx(.57)
    assert state.receipts[0].requested == 0


def test_invalid_delivery_and_native_failure_rollback_held_timber(world):
    state = S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 4)
    before = deepcopy(world.model_dump(mode="json"))
    plan = prepare(world)
    assert world.regions[0].stockpile.goods["timber"] == 16
    with pytest.raises(ValueError, match="within request"):
        S.finish_storage_work(world, plan, [4.1, 0, 0])
    S.rollback_storage_work(world, plan)
    assert world.model_dump(mode="json") == before
    assert state.assets == [None, None, None]
    with pytest.raises(ValueError, match="lifecycle"):
        S.rollback_storage_work(world, plan)
    second = prepare(world)
    S.finish_storage_work(world, second, [0, 0, 0])
    assert world.regions[0].stockpile.goods["timber"] == 20
    assert world.civilizations[0].treasury == 100


def test_enable_after_granary_switch_and_zero_work_have_no_cost():
    w = generate_world(seed=42, num_regions=3, num_civs=1)
    w.agent_mode = "hybrid"
    reserves.set_grain_reserves_enabled(w, True)
    assert w.grain_reserves.granaries == []
    state = S.enable_storage(w)
    assert len(w.grain_reserves.granaries) == len(state.assets) == 3
    for region in w.regions:
        region.stockpile.goods["timber"] = 10
    before = [(c.treasury) for c in w.civilizations]
    plan = prepare(w)
    assert plan.requests == [0, 0, 0]
    S.finish_storage_work(w, plan, [0, 0, 0])
    assert [c.treasury for c in w.civilizations] == before
    assert all(r.stockpile.goods["timber"] == 10 for r in w.regions)


def test_zero_treasury_and_subcoin_work_cannot_overcommit(world):
    state = S.enable_storage(world)
    for rid in range(3):
        S.set_storage_policy(world, rid, "expand", .3)
    world.civilizations[0].treasury = 1
    plan = prepare(world)
    assert plan.requests[0] > 0
    assert plan.requests[1:] == [0.0, 0.0]
    assert plan.requests[0] <= .3
    S.finish_storage_work(world, plan, plan.requests)
    assert world.civilizations[0].treasury == 0
    assert state.receipts[0].treasury_paid == 1
    world.turn += 1
    second = prepare(world)
    assert second.requests == [0, 0, 0]
    S.finish_storage_work(world, second, second.requests)
    assert all(r.treasury_paid == 0 for r in state.receipts)


def test_preexisting_keep_debits_limit_reservations_across_regions(world):
    S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 4)
    S.set_storage_policy(world, 1, "expand", 4)
    civ = world.civilizations[0]
    civ.treasury = 10
    acc = StatAccumulator()
    acc.add(0, civ, "treasury", -7, "keep")
    plan = prepare(world, acc=acc)
    assert plan.requests == [1.5, 0.0, 0.0]
    S.finish_storage_work(world, plan, plan.requests, acc=acc)
    acc.apply_keep(world)
    assert civ.treasury == 0


def test_bad_work_result_never_charges_and_failed_hold_can_be_rolled_back(world):
    S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 4)
    plan = prepare(world)
    for delivered in ([1], [float("nan"), 0, 0], [-1, 0, 0], [4.1, 0, 0]):
        with pytest.raises(ValueError):
            S.finish_storage_work(world, plan, delivered)
    assert world.civilizations[0].treasury == 100
    assert world.grain_reserves.storage.assets == [None, None, None]
    S.rollback_storage_work(world, plan)
    assert world.regions[0].stockpile.goods["timber"] == 20


def test_exact_resume_retains_mixed_region_policies_and_rejects_changes(world):
    from types import SimpleNamespace
    from chronicler.main import _adopt_checkpoint_args, _build_parser
    S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 2)
    S.set_storage_policy(world, 1, "maintain", 1)
    saved = SimpleNamespace(state=SimpleNamespace(world=world, seed=42, num_turns=8,
        run_config={"simulation_args": {"grain_storage": True,
                                       "grain_storage_policy": None,
                                       "grain_storage_work_budget": None}}))
    parser = _build_parser()
    args = parser.parse_args([])
    before = world.grain_reserves.storage.model_dump_json()
    assert _adopt_checkpoint_args(parser, args, saved) == []
    assert args.grain_storage is True
    assert args.grain_storage_policy is None
    assert args.grain_storage_work_budget is None
    assert world.grain_reserves.storage.model_dump_json() == before
    for flags in (["--no-grain-storage"], ["--grain-storage-policy", "maintain"],
                  ["--grain-storage-work-budget", "2"]):
        conflicts = _adopt_checkpoint_args(parser, parser.parse_args(flags), saved)
        assert any("conflicts with the checkpoint" in c for c in conflicts)
        assert world.grain_reserves.storage.model_dump_json() == before


def test_checkpoint_refuses_pending_work_without_writing_or_losing_hold(world, tmp_path):
    from types import SimpleNamespace
    from chronicler.run_checkpoint import CheckpointError, write_checkpoint
    S.enable_storage(world)
    S.set_storage_policy(world, 0, "expand", 4)
    before = world.model_dump_json()
    plan = prepare(world)
    with pytest.raises(RuntimeError, match="pending plan"):
        S.set_storage_policy(world, 0, "neglect", 0)
    target = tmp_path / "pending.ckpt"
    with pytest.raises(CheckpointError, match="completed turn boundary"):
        write_checkpoint(target, SimpleNamespace(world=world))
    assert not target.exists()
    assert world.regions[0].stockpile.goods["timber"] == 16
    S.rollback_storage_work(world, plan)
    assert world.model_dump_json() == before
