"""B4 stock/canopy account, controls and dated restore behavior."""
import copy
import pickle
from types import SimpleNamespace

import pytest

from chronicler import harvest_cover as HC, timber_stock as TS
from chronicler.livelihoods import configure_livelihoods
from chronicler.main import _build_parser
from chronicler.timber_stock_state import TimberLedgerRow, TimberSlotStock
from chronicler.world_gen import generate_world


def _world(mode="loss", ratios=(0.1,)):
    world = generate_world(seed=3)
    world.agent_mode = "hybrid"
    args = _build_parser().parse_args(["--timber-stock", "--harvest-cover", "--harvest-cover-mode", mode])
    configure_livelihoods(world, args, agent_mode="hybrid")
    world.regions[0].ecology.forest_cover = TS.woodland_reference_cover()
    world.regions[0].resource_base_yields = [1.0, 1.0, 1.0]
    state = TS._state(world)
    state.ledger_turn = world.turn
    state.ledger = []
    for slot, ratio in enumerate(ratios):
        capacity = TS.effective_capacity(world.regions[0], slot)
        state.ledger.append(TimberLedgerRow(region_id=0, slot=slot, opening=capacity,
            cleared=0, extraction=capacity * (1 - ratio), overdraft=0, regrowth=0,
            removed=0, stock=capacity * ratio, capacity=capacity))
    state.stocks = [TimberSlotStock(region_id=0, slot=r.slot, stock=r.stock) for r in state.ledger]
    return world


def test_canopy_loss_is_dated_and_preserves_every_standing_stock():
    world = _world()
    before = TS._state(world).model_dump()
    HC.finish_phase2(world, None, None, None)
    (row,) = HC._state(world).rows
    assert row.loss == pytest.approx(HC.LOSS_RATE * (HC.GAP_THRESHOLD - 0.1))
    assert row.cover_after == pytest.approx(row.cover_before - row.loss)
    assert TS._state(world).model_dump() == before
    for stock in TS._state(world).stocks:
        assert TS.effective_capacity(world.regions[0], stock.slot) >= stock.stock
    world.turn += 1
    assert HC.snapshot_summary(world)["rows"][0]["loss"] == row.loss
    world.turn += 1
    assert HC.snapshot_summary(world)["rows"] is None


def test_a_shared_canopy_never_clears_an_unharvested_slot():
    world = _world(ratios=(0.0, 1.0))
    before = world.regions[0].ecology.forest_cover
    HC.finish_phase2(world, None, None, None)
    assert world.regions[0].ecology.forest_cover == before
    assert HC._state(world).rows[0].loss == 0


def test_record_only_observes_the_same_proposal_and_changes_nothing_else():
    world = _world("record_only")
    before = copy.deepcopy(world.model_dump())
    HC.finish_phase2(world, None, None, None)
    after = world.model_dump()
    before["livelihoods"].pop("harvest_cover")
    after["livelihoods"].pop("harvest_cover")
    assert before == after
    assert HC._state(world).rows[0].proposed_loss > 0
    assert HC._state(world).rows[0].loss == 0


def test_exact_restore_keeps_one_settlement_and_continues_the_next_turn():
    world = _world()
    HC.finish_phase2(world, None, None, None)
    restored = pickle.loads(pickle.dumps(world))
    with pytest.raises(RuntimeError, match="already settled"):
        HC.finish_phase2(restored, None, None, None)
    for w in (world, restored):
        w.turn += 1
        TS._state(w).ledger_turn = w.turn
        HC.finish_phase2(w, None, None, None)
    assert world.model_dump() == restored.model_dump()


@pytest.mark.parametrize("flags", [[], ["--timber-stock"]])
def test_off_has_no_state_record_or_manifest_entry(flags):
    from chronicler.batch_manifest import simulation_config
    w = generate_world(seed=3)
    args = _build_parser().parse_args(flags)
    configure_livelihoods(w, args, agent_mode="hybrid")
    assert HC._state(w) is None
    assert "harvest_cover" not in simulation_config(args)
    assert "harvest_cover" not in (w.livelihoods.model_dump() if w.livelihoods else {})


def test_prerequisite_and_resume_refusals_and_unknown_frame():
    w = generate_world(seed=3)
    args = _build_parser().parse_args(["--harvest-cover"])
    with pytest.raises(ValueError, match="requires --agents hybrid and --timber-stock"):
        configure_livelihoods(w, args, agent_mode="hybrid")
    world = _world()
    with pytest.raises(ValueError, match="mode change"):
        HC.check_request(world, True, SimpleNamespace(harvest_cover_mode="record_only"),
                         agent_mode="hybrid", timber_on=True)
    with pytest.raises(ValueError, match="--no-harvest-cover"):
        HC.check_request(world, None, SimpleNamespace(harvest_cover_mode=None),
                         agent_mode="hybrid", timber_on=False)
    TS._state(world).ledger_turn = world.turn - 1
    with pytest.raises(RuntimeError, match="this turn's settled"):
        HC.finish_phase2(world, None, None, None)
