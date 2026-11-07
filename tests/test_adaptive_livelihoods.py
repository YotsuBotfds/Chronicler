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
