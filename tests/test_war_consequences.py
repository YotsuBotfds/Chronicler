"""D3 campaign wounds reuse the existing health authority and stable ids."""
from types import SimpleNamespace as NS

import pyarrow as pa
import pytest

from chronicler import war_consequences as d3
from chronicler.health_care_state import HealthCareState, InjuryEpisode
from chronicler.war_consequences_state import WarConsequencesState


def world(mode="active"):
    return NS(seed=7, turn=3, agent_mode="hybrid", health_care=HealthCareState(),
              livelihoods=NS(war_consequences=WarConsequencesState(mode=mode)))


def bridge(ids):
    return NS(_sim=NS(get_snapshot=lambda: pa.record_batch({"id": ids})))


def test_wounds_partition_campaign_selected_victims_deterministically():
    w = world()
    victims = [(i, 0) for i in range(1, 101)]
    army = NS(army_id=1)
    dead, wounds = d3.split_victims(w, army, victims, "battle")
    assert set(dead).isdisjoint(wounds)
    assert sorted(dead + wounds) == victims
    assert 10 < len(wounds) < 50
    assert d3.split_victims(w, army, victims, "battle") == (dead, wounds)
    assert len(w.livelihoods.war_consequences.pending) == len(wounds)


def test_attrition_and_default_off_are_never_wounds():
    w = world()
    victims = [(i, 0) for i in range(1, 50)]
    assert d3.split_victims(w, NS(army_id=1), victims, "attrition") == (victims, [])
    w.livelihoods.war_consequences = None
    assert d3.split_victims(w, NS(army_id=1), victims, "battle") == (victims, [])


def test_record_only_keeps_every_selected_death():
    w = world("record_only")
    victims = [(i, 0) for i in range(1, 101)]
    assert d3.split_victims(w, NS(army_id=1), victims, "battle") == (victims, [])
    assert all(r["kind"] == "would_wound" for r in w.livelihoods.war_consequences.pending)
    d3.phase10(w, None, None, bridge([]))
    assert not w.health_care.episodes


def test_wounds_are_appended_after_health_finish_merge_existing_and_skip_dead():
    w = world()
    w.health_care.episodes = [InjuryEpisode(agent_id=1, onset_turn=1, remaining=1, origin_region=0)]
    for aid in (1, 2, 3):
        d3._note(w, "wounded", id=aid, army=1, region=0, cause="battle")
    assert len(w.health_care.episodes) == 1
    d3.phase10(w, None, None, bridge([1, 2]))
    assert [e.agent_id for e in w.health_care.episodes] == [1, 2]
    assert [e.remaining for e in w.health_care.episodes] == [2, 2]
    assert w.health_care.episodes[0].onset_turn == 1
    with pytest.raises(RuntimeError, match="already settled"):
        d3.phase10(w, None, None, bridge([1, 2]))


def test_failed_tick_pending_is_never_applied_later_and_pool_reset_drops_ids():
    w = world()
    d3._note(w, "wounded", id=1, army=1, region=0, cause="battle")
    w.turn += 1
    d3.phase10(w, None, None, bridge([1]))
    assert not w.health_care.episodes
    d3._note(w, "wounded", id=1, army=1, region=0, cause="battle")
    d3.on_pool_reset(w)
    assert not w.livelihoods.war_consequences.pending


def test_history_is_bounded_and_reports_loss():
    w = world()
    for aid in range(1, 301):
        d3._note(w, "released", id=aid, army=1, region=0, cause="demobilised")
    d3.phase10(w, None, None, bridge([]))
    record = d3.snapshot_summary(w)
    assert len(record["history"]) == d3.MAX_HISTORY
    assert record["history_dropped"] == 300 - d3.MAX_HISTORY


def test_late_release_is_committed_once_after_phase10_and_output_is_bounded():
    import pickle
    w = world()
    d3.phase10(w, None, None, bridge([]))
    for aid in range(1, 301):
        d3.note_release(w, NS(army_id=1), [(aid, 0)], "demobilized")
    state = w.livelihoods.war_consequences
    assert not state.pending
    assert len(state.frame["events"]) == d3.MAX_HISTORY
    assert state.frame["events_dropped"] == 300 - d3.MAX_HISTORY
    assert state.counters["released"] == 300
    restored = pickle.loads(pickle.dumps(state))
    w.livelihoods.war_consequences = restored
    d3.note_release(w, NS(army_id=1), [(300, 0)], "demobilized")
    assert restored.counters["released"] == 300


def test_many_wounds_all_reach_health_even_when_bundle_events_are_capped():
    w = world()
    for aid in range(1, 301):
        d3._note(w, "wounded", id=aid, army=1, region=0, cause="battle")
    d3.phase10(w, None, None, bridge(list(range(1, 301))))
    state = w.livelihoods.war_consequences
    assert len(w.health_care.episodes) == 300
    assert len(state.frame["events"]) == d3.MAX_HISTORY
    assert state.frame["events_dropped"] == 300 - d3.MAX_HISTORY


def test_real_casualty_hook_removes_wounds_without_booking_them_as_deaths():
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.war.armies import apply_casualties
    from chronicler.war.common import build_context
    from tests.war_fixtures import war_world, start_war, place_army
    w = war_world(pop_a=100)
    w.agent_mode = "hybrid"
    w.livelihoods = LivelihoodsState()
    object.__setattr__(w.livelihoods, "war_consequences", WarConsequencesState())
    w.health_care = HealthCareState()
    _, war = start_war(w)
    army = place_army(w, "A", "Avalon", 30, war.war_key,
                      roster=[(aid, 0) for aid in range(1, 31)])
    queued = []
    ctx = build_context(w, bridge=NS(_sim=NS(queue_targeted_deaths=queued.extend)))
    old_pop = w.regions[0].population
    killed = apply_casualties(ctx, army, 30, cause="battle")
    wounds = [r["id"] for r in w.livelihoods.war_consequences.pending if r["kind"] == "wounded"]
    assert 0 < len(wounds) < 30
    assert killed + len(wounds) == 30
    assert army.soldiers == 0 and not army.roster
    assert army.casualties == killed and len(queued) == killed
    assert not set(queued).intersection(wounds)
    assert w.regions[0].population == old_pop - killed
    d3.phase10(w, None, None, bridge(wounds))
    assert [e.agent_id for e in w.health_care.episodes] == sorted(wounds)
