"""A6 controls must not suppress or redirect independently active D3 inputs.

Constructed personal/war observations exercise the real dated D3 score builder
and A6 dispatcher. The native seam records installed inputs; it does not move
people, infer a migration motive, or stand in for native lifecycle evaluation.
"""
from __future__ import annotations

import json
import pickle
from types import SimpleNamespace as NS

import pyarrow as pa
import pytest

from chronicler import adaptive_livelihoods as A6, livelihoods as LV
from chronicler import war_consequences as D3
from chronicler.adaptive_livelihoods_state import AdaptiveLivelihoodsState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.main import _build_parser
from chronicler.residence_ledger import LedgerReadRefused
from chronicler.residence_ledger_state import ResidenceLedgerState, ResidenceRow
from chronicler.war_consequences_state import WarConsequencesState
from chronicler.world_gen import generate_world


CHANNELS = ("all", "no_migration_experience", "no_information", "no_work", "no_trade")
PERSONAL_PENALTY = -A6.P_REFUSED * (1 - 1 / A6.REFUSED_WINDOW)


class RecordingSim:
    def __init__(self):
        self.information = self.installed = None
        self.trade_calls = 0

    def get_snapshot(self):
        return pa.record_batch({"id": [1], "region": [0]})

    def set_adaptive_information(self, turn, rows):
        self.information = (turn, rows)
        return [(aid, region, 1) for aid, region in rows]

    def cancel_adaptive_information(self):
        self.information = None

    def set_adaptive_migration(self, turn, rows):
        self.installed = (turn, rows)

    def cancel_adaptive_migration(self):
        self.installed = None

    def usable_trade_destinations(self, ids, turn):
        self.trade_calls += 1
        return [(aid, [1, 2]) for aid in ids]


def _world(*, mode="adapt", rules="3", channels="all", threat=False, memory=False):
    state = AdaptiveLivelihoodsState(mode=mode, rules=rules, decision_channels=channels, last_turn=4)
    if memory:
        state.memory = [{"id": 1, "region": 2, "turn": 4, "kind": "refused"}]
    war = WarConsequencesState(returns={1: {
        "turn": 2, "kind": "released_service", "wars": [["war-a", 1]],
        "home": 1, "home_source_turn": 1,
    }})
    if threat:
        war.threats = {1: {"turn": 4, "region": 0, "wars": [["war-a", 1]]}}
    residence = ResidenceLedgerState(frame_turn=4, frame={}, rows={
        1: ResidenceRow(home=1, home_since=1, res=0, res_since=3, first_seen=1, move_from=1),
    })
    return NS(seed=7, turn=5, agent_mode="hybrid", regions=[
        NS(name="a", adjacencies=["b", "c"]), NS(name="b", adjacencies=["a", "c"]),
        NS(name="c", adjacencies=["a", "b"]),
    ], war_state=NS(armies=[], ended_wars=[NS(war_key="war-a", start_turn=1, ended_turn=3)]),
        livelihoods=NS(adaptive_livelihoods=state, war_consequences=war, residence_ledger=residence))


def _install(world):
    sim = RecordingSim()
    A6.before_agent_tick(world, NS(_sim=sim))
    assert sim.installed is not None
    return sim, world.livelihoods.adaptive_livelihoods.frame


def _return_pull():
    # The observed peace is turn 3, consumed at turn 5; no same-turn notice.
    return D3.RETURN_PULL * (1 - 2 / D3.RETURN_WINDOW)


@pytest.mark.parametrize("mode", ["adapt", "record_only", "shuffled"])
def test_rules3_retains_real_d3_home_target_in_every_personal_control(mode):
    world = _world(mode=mode)
    sim, frame = _install(world)
    expected = [(1, 1, _return_pull())]
    assert sim.installed == (5, expected)
    assert frame["d3_rows"] == expected and frame["d3_rows_total"] == 1
    assert frame["a6_rows"] == [] and frame["rows_installed"] == 1
    assert (sim.information is not None) == (mode != "record_only")


@pytest.mark.parametrize("channels", CHANNELS)
def test_channel_ablations_preserve_d3_and_only_the_declared_personal_input(channels):
    world = _world(channels=channels, memory=True)
    sim, frame = _install(world)
    assert frame["d3_rows"] == [(1, 1, _return_pull())]
    assert frame["migration_rows_would"] == [(1, 2, PERSONAL_PENALTY)]
    expected_personal = [] if channels == "no_migration_experience" else [(1, 2, PERSONAL_PENALTY)]
    assert frame["a6_rows"] == expected_personal
    assert sim.installed == (5, [(1, 1, _return_pull()), *expected_personal])
    assert (sim.information is not None) == (channels != "no_information")
    assert frame["information_gate_installed"] == (channels != "no_information")


def test_shuffled_permutes_own_penalty_before_adding_the_unchanged_return_pull():
    world = _world(mode="shuffled", memory=True)
    sim, frame = _install(world)
    # There are exactly two adjacent choices: A6's target 2 rotates to 1.
    # D3 remains a dated pull toward home 1 rather than rotating to 2.
    assert frame["migration_rows_would"] == [(1, 2, PERSONAL_PENALTY)]
    assert frame["a6_rows"] == [(1, 1, PERSONAL_PENALTY)]
    assert frame["d3_rows"] == [(1, 1, _return_pull())]
    assert sim.installed[1] == [(1, 1, PERSONAL_PENALTY + _return_pull())]


@pytest.mark.parametrize("mode", ["adapt", "record_only", "shuffled"])
def test_return_and_evacuation_overlap_once_under_the_same_combined_cap(mode):
    sim, frame = _install(_world(mode=mode, threat=True))
    assert frame["d3_rows"] == [(1, 1, D3.EVACUATE_PULL), (1, 2, D3.EVACUATE_PULL),
                                 (1, 1, _return_pull())]
    assert sim.installed[1] == [(1, 1, A6.P_CAP), (1, 2, D3.EVACUATE_PULL)]
    assert frame["rows_total"] == frame["rows_installed"] == 2


def test_legacy_rules2_explicitly_retains_the_old_record_and_shuffle_coupling():
    normal, _ = _install(_world(rules="2"))
    recorded, _ = _install(_world(rules="2", mode="record_only"))
    shuffled, _ = _install(_world(rules="2", mode="shuffled"))
    assert normal.installed[1] == [(1, 1, _return_pull())]
    assert recorded.installed[1] == []
    assert shuffled.installed[1] == [(1, 2, _return_pull())]
    # The corrected control differs for the exact same personal/war inputs.
    corrected, _ = _install(_world(rules="3", mode="record_only"))
    assert corrected.installed[1] == normal.installed[1]


def test_record_only_d3_and_attached_service_are_not_turned_into_active_war_scores():
    world = _world(mode="record_only")
    world.livelihoods.war_consequences.mode = "record_only"
    sim, frame = _install(world)
    assert sim.installed[1] == frame["d3_rows"] == []
    world = _world(memory=True)
    world.war_state.armies = [NS(roster=[(1, 0)])]
    sim, frame = _install(world)
    assert frame["d3_rows"] == []
    assert sim.installed[1] == [(1, 2, PERSONAL_PENALTY)]


@pytest.mark.parametrize("channels", CHANNELS)
def test_work_and_trade_controls_retain_other_choices_and_the_d3_dispatch(channels):
    world = _world(channels=channels)
    state = world.livelihoods.adaptive_livelihoods
    state.work = [{"turn": 4, "id": 1, "kind": "workshop", "net_milli": -100}]
    assert A6.accepts_offer(world, 1, "workshop") == (channels == "no_work")
    assert A6.declined_ids(world, "workshop") == ([] if channels == "no_work" else [1])
    # Another person's experience never refuses this person's offer.
    assert A6.accepts_offer(world, 2, "workshop")
    state.trade_experience = [{"turn": 4, "id": 1, "region": 2, "outcome": "returned"}]
    sim, frame = _install(world)
    known = A6.trade_destinations(world, sim, [1])
    if channels == "no_trade":
        assert known is None and sim.trade_calls == 0
        assert A6.accepts_trade_destination(world, 1, 2, known)
    else:
        assert known == {1: {1, 2}} and sim.trade_calls == 1
        assert not A6.accepts_trade_destination(world, 1, 2, known)
        assert A6.accepts_trade_destination(world, 1, 1, known)
    assert frame["d3_rows"] == sim.installed[1] == [(1, 1, _return_pull())]


def test_corrected_dispatch_restores_exactly_and_rollback_clears_both_native_inputs():
    original = _world(mode="shuffled", memory=True)
    restored = pickle.loads(pickle.dumps(original))
    plain_sim, plain_frame = _install(original)
    resumed_sim, resumed_frame = _install(restored)
    assert plain_sim.installed == resumed_sim.installed
    assert plain_sim.information == resumed_sim.information
    assert plain_frame == resumed_frame
    assert original.livelihoods.adaptive_livelihoods.model_dump() == restored.livelihoods.adaptive_livelihoods.model_dump()
    A6.rollback_agent_tick(restored, NS(_sim=resumed_sim))
    assert resumed_sim.installed is resumed_sim.information is None
    assert restored.livelihoods.adaptive_livelihoods.frame is None


def test_corrected_dispatch_still_refuses_same_turn_residence_knowledge():
    world = _world()
    world.livelihoods.residence_ledger.frame_turn = world.turn
    sim = RecordingSim()
    with pytest.raises(LedgerReadRefused, match="same-turn"):
        A6.before_agent_tick(world, NS(_sim=sim))
    assert sim.installed is sim.information is None


def test_old_json_and_pickle_missing_control_fields_retain_rules2_all():
    old = {"enabled": True, "mode": "record_only", "last_turn": 4, "memory": []}
    loaded = AdaptiveLivelihoodsState.model_validate_json(json.dumps(old))
    assert (loaded.rules, loaded.decision_channels) == ("2", "all")
    historical = AdaptiveLivelihoodsState()
    historical.__dict__.pop("decision_channels")
    historical.__dict__.pop("rules")
    restored = pickle.loads(pickle.dumps(historical))
    assert (restored.rules, restored.decision_channels) == ("2", "all")


def test_corrected_rules_are_explicit_and_existing_version_defaults_are_not_promoted():
    world = NS(livelihoods=NS(adaptive_livelihoods=None))
    A6.set_adaptive_livelihoods_enabled(world, True)
    assert (world.livelihoods.adaptive_livelihoods.rules,
            world.livelihoods.adaptive_livelihoods.decision_channels) == ("2", "all")
    explicit = NS(livelihoods=NS(adaptive_livelihoods=None))
    A6.set_adaptive_livelihoods_enabled(explicit, True, args=NS(adaptive_livelihoods_rules="3"))
    assert explicit.livelihoods.adaptive_livelihoods.rules == "3"
    world.livelihoods.adaptive_livelihoods = AdaptiveLivelihoodsState(mode="record_only")
    A6.set_adaptive_livelihoods_enabled(world, True)
    assert world.livelihoods.adaptive_livelihoods.rules == "2"


@pytest.mark.parametrize("field,value", [("mode", "record_only"), ("rules", "2"),
                                         ("decision_channels", "no_work")])
def test_saved_model_conflicts_are_refused_without_mutation(field, value):
    world = _world()
    before = world.livelihoods.adaptive_livelihoods.model_dump_json()
    with pytest.raises(ValueError, match="cannot change"):
        A6.set_adaptive_livelihoods_enabled(world, True, args=NS(**{"adaptive_livelihoods_" + field: value}))
    assert world.livelihoods.adaptive_livelihoods.model_dump_json() == before


def _args(*flags):
    return _build_parser().parse_args(["--agents", "hybrid", "--simulate-only", *flags])


def test_cli_refuses_orphan_channels_before_creating_any_livelihood_state():
    world = generate_world(seed=7)
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="requires --adaptive-livelihoods"):
        LV.configure_livelihoods(world, _args("--adaptive-livelihoods-decision-channels", "no_work"), agent_mode="hybrid")
    assert world.model_dump_json() == before


def test_cli_refuses_rules2_channels_and_saved_channel_conflicts_before_mutation():
    world = generate_world(seed=7)
    world.agent_mode = "hybrid"
    world.livelihoods = LivelihoodsState(residence_ledger=ResidenceLedgerState())
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="requires rules3"):
        LV.configure_livelihoods(world, _args("--adaptive-livelihoods", "--adaptive-livelihoods-rules", "2",
                                            "--adaptive-livelihoods-decision-channels", "no_work"), agent_mode="hybrid")
    assert world.model_dump_json() == before
    world.livelihoods.adaptive_livelihoods = AdaptiveLivelihoodsState(rules="3")
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="conflicts with the saved world"):
        LV.configure_livelihoods(world, _args("--adaptive-livelihoods-decision-channels", "no_work"), agent_mode="hybrid")
    assert world.model_dump_json() == before
