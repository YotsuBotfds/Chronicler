from types import SimpleNamespace as NS

import pyarrow as pa
import pytest

from chronicler import adaptive_livelihoods as a6
from chronicler.adaptive_livelihoods_state import AdaptiveLivelihoodsState


def world(mode="adapt"):
    return NS(seed=7, turn=5, agent_mode="hybrid", agent_events_raw=[], regions=[
        NS(name="a", adjacencies=["b", "c"]), NS(name="b", adjacencies=["a", "c"]),
        NS(name="c", adjacencies=["a", "b"])],
        livelihoods=NS(adaptive_livelihoods=AdaptiveLivelihoodsState(mode=mode)))


class Sim:
    installed = None

    def get_snapshot(self):
        return pa.record_batch({"id": [1], "region": [0]})

    def set_adaptive_migration(self, turn, rows):
        self.installed = (turn, rows)

    def cancel_adaptive_migration(self):
        self.installed = None

    def take_adaptive_migration_receipt(self):
        return self.installed[0], [(1, 0, 2, 0)], 0, 0


def test_penalties_expire_refuse_future_and_cap_without_changing_memory():
    state = AdaptiveLivelihoodsState(memory=[
        {"id": 1, "region": 2, "turn": t, "kind": "refused"} for t in (0, 3, 4, 5, 6)])
    assert a6.penalty_rows(state, 5) == [(1, 2, -a6.P_CAP)]
    assert a6.penalty_rows(state, 30) == []
    assert len(state.memory) == 5


@pytest.mark.parametrize("mode", ["adapt", "record_only", "shuffled"])
def test_mode_controls_signal_only_and_keeps_exact_refusal_receipt(mode):
    w, sim = world(mode), Sim()
    state = w.livelihoods.adaptive_livelihoods
    state.memory = [{"id": 1, "region": 1, "turn": 4, "kind": "refused"},
                    {"id": 1, "region": 2, "turn": 4, "kind": "left_soon"}]
    raw = a6.penalty_rows(state, w.turn)
    a6.before_agent_tick(w, NS(_sim=sim))
    rows = sim.installed[1]
    if mode == "record_only":
        assert rows == []
    else:
        assert len(rows) == len(raw)
        assert sorted(v for _, _, v in rows) == sorted(v for _, _, v in raw)
        assert (rows == raw) == (mode == "adapt")
    a6.after_agent_tick(w, NS(_sim=sim))
    assert state.memory[-1] == {"turn": 5, "id": 1, "kind": "refused", "region": 2, "origin": 0, "gate": 0}
    a6.rollback_agent_tick(w, NS(_sim=sim))
    assert sim.installed is None


def test_individual_work_choice_is_dated_specific_and_unknown_is_not_a_loss():
    w = world()
    a6.note_work(w, 1, "repair", paid_milli=0, withheld_milli=100, title_forgone_milli=0)
    assert a6.accepts_offer(w, 1, "repair")  # cannot read same-turn outcome
    w.turn += 1
    assert not a6.accepts_offer(w, 1, "repair")
    assert a6.accepts_offer(w, 1, "training")
    assert a6.accepts_offer(w, 2, "repair")
    a6.note_work(w, 2, "repair", paid_milli=0, withheld_milli=100)
    w.turn += 1
    assert a6.accepts_offer(w, 2, "repair")  # unknown forgone title
    w.livelihoods.adaptive_livelihoods.mode = "record_only"
    assert a6.accepts_offer(w, 1, "repair")


def test_pool_reset_and_gap_close_old_identity_and_experience():
    w, sim = world(), Sim()
    state = w.livelihoods.adaptive_livelihoods
    state.last_turn = 1
    state.memory = [{"id": 1, "region": 2, "turn": 1, "kind": "refused"}]
    a6.before_agent_tick(w, NS(_sim=sim))
    assert not state.memory and state.counters["unobserved_gaps"] == 1
    a6.on_pool_reset(w)
    assert state.frame is None and state.last_turn == -1


def test_mode_and_rules_conflicts_are_rejected():
    w = world()
    with pytest.raises(ValueError, match="cannot change"):
        a6.set_adaptive_livelihoods_enabled(w, True, args=NS(adaptive_livelihoods_mode="shuffled"))


def test_repeated_offer_probes_are_one_observation_and_pool_reset_clears_cached_ids():
    w = world()
    a6.note_work(w, 1, "repair", paid_milli=0, withheld_milli=100, title_forgone_milli=0)
    w.turn += 1
    assert not a6.accepts_offer(w, 1, "repair")
    assert not a6.accepts_offer(w, 1, "repair")
    state = w.livelihoods.adaptive_livelihoods
    assert state.counters["would_decline_repair"] == 1 and len(state.offers) == 1
    a6.on_pool_reset(w)
    assert a6.accepts_offer(w, 1, "repair")  # id may name a different person


def test_training_uses_personal_failed_progress_and_preserves_commitments_value():
    w = world()
    for _ in range(2):
        a6.note_work(w, 1, "academy_training", paid_milli=0, withheld_milli=0,
                     progress=False, source="personal no-seat receipt")
        w.turn += 1
    assert not a6.accepts_offer(w, 1, "academy_training")
    assert a6.accepts_offer(w, 1, "apprenticeship")
    a6.note_work(w, 1, "academy_training", paid_milli=0, withheld_milli=100,
                 progress=True, source="personal attended receipt")
    w.turn += 1
    assert a6.accepts_offer(w, 1, "academy_training")


def test_real_payroll_hook_supplies_personal_paid_and_withheld_receipts():
    from tests.test_workshop_payroll import _world, FakeSim, _build, _turn
    w, sim = _world(), FakeSim()
    _build(w, sim)
    state = AdaptiveLivelihoodsState()
    object.__setattr__(w.livelihoods, "adaptive_livelihoods", state)
    _turn(w, sim, output=1.2)
    assert {r["id"] for r in state.work} == {10, 20}
    assert all(r["paid_milli"] == 150 and r["withheld_milli"] == 90 and r["net_milli"] == 60
               and r["title_forgone_milli"] == 0 for r in state.work)
    assert a6.declined_ids(w, "workshop") == []


def test_real_unpaid_work_receipt_can_refuse_a_later_work_offer():
    from tests.test_workshop_payroll import _world, FakeSim, _build, _turn
    w, sim = _world(mode="unpaid_labor"), FakeSim()
    _build(w, sim)
    state = AdaptiveLivelihoodsState()
    object.__setattr__(w.livelihoods, "adaptive_livelihoods", state)
    _turn(w, sim, output=1.2)
    assert all(r["paid_milli"] == 0 and r["withheld_milli"] == 90 and r["net_milli"] == -90
               for r in state.work)
    assert a6.declined_ids(w, "workshop") == [10, 20]


def test_new_training_enrollment_consumes_dated_failure_experience():
    from tests.test_learning_cohorts import _world, FakeSim, person, turn
    w = _world()
    w.turn = 3
    sim = FakeSim([person(1, occ=1), person(2, occ=2)])
    state = AdaptiveLivelihoodsState(last_turn=2, work=[
        {"turn": t, "id": aid, "kind": "academy_training", "progress": False, "net_milli": None}
        for t in (1, 2) for aid in (1, 2)])
    object.__setattr__(w.livelihoods, "adaptive_livelihoods", state)
    outcome = turn(w, sim)
    assert not outcome.cohorts  # both personally decline; minimum cohort cannot form
    assert len(state.offers) == 2 and all(not o["accepted"] for o in state.offers)


def test_forgone_title_is_unknown_in_a_retail_pilot_without_a_counterfactual_receipt():
    w = world()
    w.livelihoods.household_retail = NS(enabled=True, mode="retail", region=lambda rid: NS() if rid == 0 else None)
    assert a6.forgone_title(w, 0) is None
    assert a6.forgone_title(w, 1) == 0
    assert a6.forgone_title(w, 0, occupation=2) == 0


def test_work_history_is_bounded_deduplicated_and_resumes_after_pickle(monkeypatch):
    import pickle
    monkeypatch.setattr(a6, "MAX_WORK", 3)
    w = world()
    for aid in (7, 3, 5, 9, 1):
        a6.note_work(w, aid, "repair", paid_milli=aid, withheld_milli=0, title_forgone_milli=0)
    state = w.livelihoods.adaptive_livelihoods
    assert sorted(r["id"] for r in state.work) == [5, 7, 9]
    assert state.counters["work_dropped"] == 2
    state = pickle.loads(pickle.dumps(state))
    w.livelihoods.adaptive_livelihoods = state
    a6.note_work(w, 9, "repair", paid_milli=999, withheld_milli=0, title_forgone_milli=0)
    assert next(r for r in state.work if r["id"] == 9)["paid_milli"] == 9
    a6.note_work(w, 10, "repair", paid_milli=10, withheld_milli=0, title_forgone_milli=0)
    assert sorted(r["id"] for r in state.work) == [7, 9, 10]


def test_native_refusal_frame_samples_preserve_total_and_full_bounded_memory():
    w, sim = world(), Sim()
    sim.take_adaptive_migration_receipt = lambda: (5, [(i, 0, 1, 0) for i in range(500)], 7, 3)
    a6.before_agent_tick(w, NS(_sim=sim))
    a6.after_agent_tick(w, NS(_sim=sim))
    state = w.livelihoods.adaptive_livelihoods
    assert len(state.memory) == 500
    assert len(state.frame["refusals"]) == len(state.frame["receipt"][1]) == 256
    assert state.frame["refusals_total"] == 500 and state.frame["refusals_dropped"] == 244
    assert state.frame["receipt"][2:] == (7, 3)
