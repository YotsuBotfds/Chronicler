"""Saved stable ids stay bound to the native pool they name (offline).

``livelihoods.bind_native_pool`` closes id-bound records when a run's
simulator is not the one the records were bound to (a legacy state-file
resume rebuilds the pool under reused ids), and an exact checkpoint load
re-binds the restored pool without a reset. Derived from the identity
contract in AGENTS.md and checkpoint-continuation.md, section 2.
"""
from __future__ import annotations

import pickle
from types import SimpleNamespace

from chronicler import learning_cohorts as L5
from chronicler import livelihoods
from chronicler import relocation_costs as L7
from chronicler import workshop_payroll as L6
from chronicler.learning_cohorts_state import Cohort, CohortMember, LearningCohortState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.relocation_costs_state import RelocationCostsState
from chronicler.workshop_payroll_state import OwedWage, WorkshopFirm, WorkshopPayrollState


def _bridge():
    return SimpleNamespace(_sim=object())


def _cohort(cohort_id: int, members: list[int]) -> Cohort:
    return Cohort(cohort_id=cohort_id, seat_id=0, region=0, founder=1, founded_turn=1,
                  seat_name="Academy", formed_turn=2, sessions=1,
                  members=[CohortMember(agent_id=m, joined_turn=2, occupation=0, skill_at_join=0.2,
                                        attended=2, last_attended_turn=8) for m in members])


def _world(*, turn: int = 7):
    state = LivelihoodsState()
    state.workshop_payroll = WorkshopPayrollState(firms=[WorkshopFirm(
        site=0, region=0, settlement_id=1, city_name="A", opened_turn=1,
        owed=[OwedWage(agent_id=11, amount=1500, since_turn=5), OwedWage(agent_id=12, amount=250, since_turn=6)])])
    state.relocation_costs = RelocationCostsState(tracked=[21, 22], tracked_turn=6, origins={21: 3, 22: 4})
    return SimpleNamespace(turn=turn, livelihoods=state)


def test_the_first_binding_of_a_fresh_run_changes_nothing():
    world = SimpleNamespace(turn=0, livelihoods=LivelihoodsState())
    world.livelihoods.relocation_costs = RelocationCostsState()
    before = world.livelihoods.model_dump()
    livelihoods.bind_native_pool(world, _bridge())
    assert world.livelihoods.model_dump() == before


def test_a_new_pool_lapses_owed_wages_and_drops_tracked_arrivals():
    world = _world()
    livelihoods.bind_native_pool(world, _bridge())
    firm = world.livelihoods.workshop_payroll.firms[0]
    assert firm.owed == []
    assert firm.totals["owed_pool_reset"] == 1750
    assert firm.history[-1] == (7, "owed_pool_reset", 1750)
    assert world.livelihoods.workshop_payroll.counters["owed_pool_reset"] == 1750
    reloc = world.livelihoods.relocation_costs
    assert (reloc.tracked, reloc.tracked_turn, reloc.origins) == ([], None, {})
    assert reloc.counters["pool_resets"] == 1


def test_the_same_pool_is_bound_once_and_never_reset_again():
    world, bridge = _world(), _bridge()
    livelihoods.bind_native_pool(world, bridge)
    world.livelihoods.workshop_payroll.firms[0].owed = [OwedWage(agent_id=13, amount=40, since_turn=7)]
    for _ in range(3):
        livelihoods.bind_native_pool(world, bridge)
    assert [o.agent_id for o in world.livelihoods.workshop_payroll.firms[0].owed] == [13]


def test_an_exact_load_rebinds_without_a_reset_and_the_binding_is_never_pickled():
    world, bridge = _world(), _bridge()
    livelihoods.bind_native_pool(world, bridge, reset=False)
    assert world.livelihoods._pool_sim == id(bridge._sim)
    restored = pickle.loads(pickle.dumps(world.livelihoods))
    assert restored._pool_sim is None
    assert pickle.dumps(world.livelihoods) == pickle.dumps(_world().livelihoods)   # never bound
    fresh = SimpleNamespace(turn=world.turn, livelihoods=restored)
    livelihoods.bind_native_pool(fresh, _bridge(), reset=False)   # run_checkpoint._rebind_markers
    assert [o.agent_id for o in restored.workshop_payroll.firms[0].owed] == [11, 12]
    assert restored.relocation_costs.origins == {21: 3, 22: 4}


def test_a_state_pickled_before_the_binding_existed_still_loads():
    state = LivelihoodsState()
    blob = state.__getstate__()
    blob = {**blob, "__pydantic_private__": None}
    loaded = LivelihoodsState.__new__(LivelihoodsState)
    loaded.__setstate__(blob)
    assert loaded._pool_sim is None


def test_no_simulator_or_no_container_is_a_no_op():
    world = _world()
    livelihoods.bind_native_pool(world, None)
    livelihoods.bind_native_pool(world, SimpleNamespace(_sim=None))
    assert world.livelihoods.workshop_payroll.firms[0].owed
    livelihoods.bind_native_pool(SimpleNamespace(turn=1, livelihoods=None), _bridge())


def test_open_cohorts_close_with_reason_pool_reset_and_nobody_keeps_progress():
    world = SimpleNamespace(turn=9, livelihoods=LivelihoodsState())
    state = world.livelihoods.learning_cohorts = LearningCohortState()
    cohort = _cohort(1, [31, 32])
    state.cohorts = [cohort]
    livelihoods.bind_native_pool(world, _bridge())
    assert state.cohorts == []
    assert cohort.status == "closed" and cohort.closed_reason == "pool_reset" and cohort.closed_turn == 9
    assert {m.status for m in cohort.members} == {"exited"}
    assert {m.exit_reason for m in cohort.members} == {"pool_reset"}
    assert state.counters["exit_pool_reset"] == 2 and state.counters["cohorts_pool_reset"] == 1
