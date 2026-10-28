"""Controlled episodes and accounting; no medical or mortality model."""
from types import SimpleNamespace
import pytest
from chronicler.health_care import (
    health_care_active, health_care_on, set_health_care_enabled,
    prepare_health_care, finish_health_care, snapshot_summary, validate_health_care,
)
from chronicler.health_care_state import HealthCareState, InjuryEpisode


class Sim:
    def __init__(self, *, cared=True, new=(), moved=False):
        self.cared, self.new, self.moved = cared, list(new), moved
        self.prepared = None
    def prepare_health_work(self, ids, excluded, urban, impairment, care):
        self.prepared = (ids, excluded, urban, impairment, care)
        return [(aid, 0, 2 if self.cared and care else 0, care if self.cared else 0.) for aid in ids]
    def finish_health_work(self, turn, rate):
        ids, _, _, impairment, care = self.prepared
        new, self.new = self.new, []
        return ([(aid, int(self.moved)) for aid in ids], new,
                [(0, impairment * len(ids), care * len(ids) if self.cared else 0.,
                  len(ids) if self.cared and care else 0), (1, 0., 0., 0)])


def world(sample_world):
    sample_world.agent_mode = "hybrid"
    set_health_care_enabled(sample_world, True)
    sample_world.health_care.injury_rate = 0.
    return sample_world


def episode():
    return InjuryEpisode(agent_id=1, onset_turn=-1, remaining=2., origin_region=0)


def tick(w, sim):
    bridge = SimpleNamespace(_sim=sim)
    prepare_health_care(w, bridge)
    events = finish_health_care(w, bridge)
    w.turn += 1
    return events


def test_absent_and_dormant_state_stay_omitted(sample_world):
    assert not health_care_on(sample_world)
    assert "health_care" not in sample_world.model_dump()
    prepare_health_care(sample_world, None)
    assert finish_health_care(sample_world, None) == []
    set_health_care_enabled(sample_world, True)
    sample_world.agent_mode = "off"
    assert health_care_on(sample_world) and not health_care_active(sample_world)
    assert snapshot_summary(sample_world) == {}
    set_health_care_enabled(sample_world, False)
    assert "health_care" not in sample_world.model_dump()


def test_care_ablation_fixed_cohort_and_snapshot_is_dated(sample_world):
    w = world(sample_world)
    w.health_care.episodes = [episode()]
    tick(w, Sim())
    summary = snapshot_summary(w)
    assert summary["recoveries"] == 1 and summary["episodes"] == 0
    assert summary["impaired_work"] == .5 and summary["care_work"] == .2
    assert summary["cared_recovery_progress"] == 2.
    assert summary["source_turn"] == w.turn - 1
    frozen = summary["regions"][0]["region_name"]
    w.regions[0].name = "Later name"
    assert snapshot_summary(w)["regions"][0]["region_name"] == frozen
    w.health_care = HealthCareState(episodes=[episode()], injury_rate=0., care_enabled=False)
    tick(w, Sim())
    assert snapshot_summary(w)["episodes"] == 1
    assert snapshot_summary(w)["care_work"] == 0.
    tick(w, Sim())
    assert snapshot_summary(w)["recoveries"] == 1


def test_new_onset_has_no_retroactive_work_cost_and_survives_json(sample_world):
    w = world(sample_world)
    events = tick(w, Sim(new=[(3, 0, 1)]))
    assert len(events) == 1
    summary = snapshot_summary(w)
    assert summary["new_injuries"] == 1 and summary["impaired_work"] == 0.
    assert summary["regions"][1]["episodes"] == 1
    loaded = type(w).model_validate_json(w.model_dump_json())
    assert loaded.health_care.episodes == w.health_care.episodes
    assert loaded.health_care._prepared is None


def test_moves_and_deaths_cleanup_without_changing_population(sample_world):
    w = world(sample_world)
    w.health_care = HealthCareState(episodes=[episode()], care_enabled=False)
    pops = [r.population for r in w.regions]
    tick(w, Sim(cared=False, moved=True))
    assert snapshot_summary(w)["regions"][1]["episodes"] == 1
    sim = Sim()
    sim.finish_health_work = lambda *args: ([], [], [(0, .5, .0, 0)])
    tick(w, sim)
    assert w.health_care.episodes == []
    assert snapshot_summary(w)["censored_episodes"] == 1
    assert snapshot_summary(w)["recoveries"] == 0
    assert [r.population for r in w.regions] == pops


def test_duplicate_ids_old_native_and_double_finish_fail_clearly(sample_world):
    w = world(sample_world)
    w.health_care.episodes = [episode(), episode()]
    with pytest.raises(ValueError, match="duplicate"):
        validate_health_care(w)
    w.health_care.episodes = []
    with pytest.raises(RuntimeError, match="fresh native"):
        prepare_health_care(w, SimpleNamespace(_sim=object()))
    with pytest.raises(RuntimeError, match="preparation"):
        finish_health_care(w, SimpleNamespace(_sim=Sim()))
    sim = Sim()
    tick(w, sim)
    with pytest.raises(RuntimeError, match="preparation"):
        finish_health_care(w, SimpleNamespace(_sim=sim))


def test_stale_and_future_summaries_are_unrecorded(sample_world):
    w = world(sample_world)
    tick(w, Sim())
    assert snapshot_summary(w)
    w.turn += 1
    assert snapshot_summary(w) == {}
    w.health_care.last_tick_turn = w.turn + 1
    assert snapshot_summary(w) == {}
