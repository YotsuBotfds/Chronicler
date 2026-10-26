"""Narration, curation and live transport read the record as of their turn.

Reproductions of the historical-parity review (each failed on ``main``
``fc01d6e``) and the convention of ``chronicler.historical_context``.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from chronicler.models import (
    CivSnapshot,
    Event,
    GreatPerson,
    GreatPersonDeed,
    NarrativeMoment,
    NarrativeRole,
    TechEra,
    TurnSnapshot,
)


def _row(population: int = 100, regions=("R1",), gini: float = 0.0) -> CivSnapshot:
    return CivSnapshot(
        population=population, military=50, economy=50, culture=50, stability=50,
        treasury=100, asabiya=0.5, tech_era=TechEra.IRON, trait="bold",
        regions=list(regions), leader_name="Leader", alive=bool(regions), gini=gini,
    )


def _snap(turn: int, civs: dict[str, CivSnapshot], control: dict | None = None) -> TurnSnapshot:
    return TurnSnapshot(turn=turn, civ_stats=civs, region_control=control or {}, relationships={})


def _moment(turn_range, events, anchor=None) -> NarrativeMoment:
    return NarrativeMoment(
        anchor_turn=anchor if anchor is not None else turn_range[0],
        turn_range=turn_range, events=events, named_events=[], score=8.0,
        causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
    )


def _gp(name, civ, born, **kw) -> GreatPerson:
    return GreatPerson(name=name, role=kw.pop("role", "general"), trait="bold", civilization=civ,
                       origin_civilization=kw.pop("origin", civ), born_turn=born, source="agent",
                       agent_id=kw.pop("agent_id"), **kw)


def _engine(world=None):
    from chronicler.narrative import NarrativeEngine
    engine = NarrativeEngine(sim_client=MagicMock(model="t"), narrative_client=MagicMock(model="t"))
    engine._world = world
    return engine


def _turn10_case():
    """A turn-10 moment of civ A in a run that ended after turn 499."""
    from chronicler.models import WorldState
    world = WorldState(name="W", seed=1, turn=500, regions=[], civilizations=[])
    moment = _moment((10, 10), [Event(turn=10, event_type="local_rebellion", actors=["A"],
                                      description="Unrest in A", importance=7, source="agent")])
    early = _gp("Asha", "A", 2, agent_id=1, deeds=[
        GreatPersonDeed(text="Won at the ford", region="R1", turn=5, civ="A"),
        GreatPersonDeed(text="Conquered the east", region="R9", turn=400, civ="A"),
    ], memories=[{"event_type": 1, "source_civ": 0, "turn": 8, "intensity": 70},
                 {"event_type": 6, "source_civ": 0, "turn": 420, "intensity": 90}],
        needs={"safety": 0.1, "material": 0.9, "social": 0.9, "spiritual": 0.9,
               "autonomy": 0.9, "purpose": 0.9},
        agent_bonds=[{"target_id": 2, "bond_type": 6, "sentiment": 50, "formed_turn": 6},
                     {"target_id": 3, "bond_type": 1, "sentiment": -90, "formed_turn": 350}])
    late = _gp("Borun", "A", 300, agent_id=3, deeds=[
        GreatPersonDeed(text="Promoted as general", region="R2", turn=300, civ="A")])
    friend = _gp("Cael", "A", 4, agent_id=2, active=False, alive=False, fate="dead", death_turn=200)
    history = [_snap(t, {"A": _row()}) for t in range(1, 13)]
    return world, moment, [early, late, friend], history


class TestNarrationAsOf:
    """Item 1: the curated narrator's characters are the ones known at the moment."""

    def test_future_people_and_deeds_stay_out_of_a_turn_10_prompt(self):
        world, moment, people, history = _turn10_case()
        prep = _engine(world)._prepare_narration_prompts(
            [moment], history, great_persons=people,
            agent_name_map={1: "Asha", 2: "Cael", 3: "Borun"},
        )[0]
        prompt = prep["prompt"]
        assert "Asha" in prompt and "Won at the ford" in prompt
        assert "Borun" not in prompt                      # born at turn 300
        assert "Conquered the east" not in prompt         # deed of turn 400
        assert "turn 420" not in prompt                   # memory of turn 420
        assert "since turn 350" not in prompt             # bond formed at turn 350
        assert "Safety LOW" not in prompt                 # needs observed at turn 499
        # Cael died at turn 200: an active general of A at turn 10.
        assert "- General Cael [bold] (A) [active]:" in prompt

    def test_status_is_the_status_at_the_moment(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        world, _moment_, people, history = _turn10_case()
        record = HistoricalRecord(history=history, great_persons=people, world=world)
        view = record.view(AsOf.after(10))
        assert [c.name for c in view.characters] == ["Asha", "Cael"]
        assert view.character("Cael").status == "active"
        assert record.view(AsOf.after(200)).character("Cael").status == "dead"
        assert record.view(AsOf.after(199)).character("Cael").status == "active"

    def test_a_character_born_at_the_moment_is_known_at_its_end_not_its_start(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        gp = _gp("Dara", "A", 10, agent_id=9)
        record = HistoricalRecord(great_persons=[gp])
        assert record.view(AsOf.after(10)).character("Dara") is not None
        assert record.view(AsOf.before(10)).character("Dara") is None

    def test_bridge_values_apply_only_to_the_observed_turn(self):
        from chronicler.narrative import build_agent_context_for_moment
        from chronicler.historical_context import AsOf, HistoricalRecord
        world, moment, people, history = _turn10_case()
        history[10] = _snap(11, {"A": _row(gini=0.25)})
        record = HistoricalRecord(history=history, great_persons=people, world=world,
                                  gini_by_civ={0: 0.9}, displacement_by_region={0: 0.5})
        ctx = build_agent_context_for_moment(moment, people, {}, view=record.view(AsOf.after(10)),
                                             civ_idx=0)
        assert ctx.gini_coefficient == pytest.approx(0.25)    # the snapshot after turn 10
        assert ctx.displacement_observed is False
        late = _moment((499, 499), moment.events)
        ctx = build_agent_context_for_moment(late, people, {}, view=record.view(AsOf.after(499)),
                                             civ_idx=0)
        assert ctx.gini_coefficient == pytest.approx(0.9)
        assert ctx.displacement_fraction == pytest.approx(0.5)


class TestGapSummaries:
    """Item 2: a gap's summary includes its last turn and is ordered."""

    def _moments(self):
        a = _moment((0, 2), [Event(turn=1, event_type="war", actors=["A"], description="w", importance=5)])
        b = _moment((6, 8), [Event(turn=7, event_type="war", actors=["A"], description="w", importance=5)])
        return [a, b]

    def test_a_change_during_the_last_gap_turn_is_counted(self):
        from chronicler.curator import build_gap_summaries
        # Gap turns 3-5. Turn 5 (snapshot 6) moves the population.
        history = [_snap(t, {"A": _row(100 if t <= 5 else 140)}) for t in range(1, 10)]
        [gap] = build_gap_summaries(self._moments(), [], history)
        assert gap.turn_range == (3, 5)
        assert gap.stat_deltas == {"A": {"population": 40}}

    def test_stat_delta_keys_are_sorted(self):
        from chronicler.curator import build_gap_summaries
        names = ["Zeta", "Alpha", "Mu", "Beta", "Omega", "Kappa", "Delta", "Eta"]
        history = [_snap(t, {n: _row(100 if t <= 3 else 100 + i + 1) for i, n in enumerate(names)})
                   for t in range(1, 10)]
        [gap] = build_gap_summaries(self._moments(), [], history)
        assert list(gap.stat_deltas) == sorted(names)
        assert json.dumps(gap.model_dump()) == json.dumps(gap.model_dump())


class TestLiveRangeNarration:
    """Item 4: live range narration gets the world the CLI narration gets."""

    def test_live_range_narration_passes_the_world(self, monkeypatch, sample_world):
        from chronicler import llm
        from chronicler.live import LiveServer
        from chronicler.narrative import NarrativeEngine

        captured: dict = {}

        def spy(self_engine, moments, history, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(NarrativeEngine, "narrate_batch", spy)
        monkeypatch.setattr(llm, "create_clients", lambda **kw: (llm.MechanicalClient(), llm.MechanicalClient()))
        civ = sample_world.civilizations[0].name
        world = sample_world.model_copy(update={"turn": 3})
        init = {
            "world_state": world.model_dump(mode="json"),
            "history": [_snap(t, {civ: _row()}).model_dump(mode="json") for t in (1, 2, 3)],
            "events_timeline": [Event(turn=1, event_type="war", actors=[civ], description="w",
                                      importance=8).model_dump(mode="json")],
            "named_events": [], "metadata": {"seed": 1},
        }
        LiveServer(port=0)._narrate_range_sync(init, {"narrator": "local"}, 1, 2)
        assert captured.get("world") is not None
        assert captured["world"].name == world.name

    def test_live_and_cli_narration_read_a_bundle_the_same_way(self, monkeypatch):
        """Both paths take their inputs from narration_inputs.from_bundle."""
        from chronicler import llm, narration_inputs
        from chronicler.live import LiveServer, _build_init_data_from_bundle, _validate_legacy_live_bundle
        from chronicler.narrative import NarrativeEngine

        calls: list = []
        real = narration_inputs.from_bundle

        def spy_inputs(bundle, **kw):
            calls.append(kw)
            return real(bundle, **kw)

        captured: dict = {}
        monkeypatch.setattr(narration_inputs, "from_bundle", spy_inputs)
        monkeypatch.setattr(NarrativeEngine, "narrate_batch",
                            lambda self, m, h, **kw: captured.update(kw) or [])
        monkeypatch.setattr(llm, "create_clients", lambda **kw: (llm.MechanicalClient(), llm.MechanicalClient()))
        bundle = _validate_legacy_live_bundle(json.loads(FIXTURE.read_text(encoding="utf-8")))
        init = _build_init_data_from_bundle(bundle)
        turns = [s["turn"] for s in init["history"]]
        LiveServer(port=0)._narrate_range_sync(init, {"narrator": "local"}, turns[0], turns[-1])
        assert calls and captured["world"] is not None
        assert captured["historiography"] is not None and captured["languages"] is not None


# ---------------------------------------------------------------------------
# Item 4: one transport contract
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "viewer" / "src" / "__fixtures__" / "transport_bundle.json"


class TestTransportContract:
    def test_snapshot_systems_are_the_optional_snapshot_fields(self):
        from chronicler.transport import SNAPSHOT_FIELDS, SNAPSHOT_SYSTEMS
        optional = [name for name, f in TurnSnapshot.model_fields.items() if f.exclude_if is not None]
        assert list(SNAPSHOT_SYSTEMS) == optional
        assert list(SNAPSHOT_FIELDS) == [n for n in TurnSnapshot.model_fields if n not in optional]

    def test_the_fixture_holds_every_system(self):
        from chronicler.bundle_codec import load_bundle
        from chronicler.transport import BUNDLE_CARRIERS, BUNDLE_SYSTEMS, SNAPSHOT_SYSTEMS
        bundle = load_bundle(FIXTURE)
        assert bundle["metadata"]["bundle_version"] == 6
        for snap in bundle["history"]:
            assert set(SNAPSHOT_SYSTEMS) <= set(snap)
        assert set(BUNDLE_SYSTEMS + BUNDLE_CARRIERS) <= set(bundle)

    def test_batch_lab_and_reconnect_keep_every_system(self):
        """batch_load_bundle (validated bundle) and the init it builds for reconnect."""
        from chronicler.bundle_codec import load_bundle
        from chronicler.live import _build_init_data_from_bundle, _validate_legacy_live_bundle
        from chronicler.transport import BUNDLE_CARRIERS, BUNDLE_SYSTEMS, SNAPSHOT_SYSTEMS
        static = load_bundle(FIXTURE)
        loaded = _validate_legacy_live_bundle(json.loads(FIXTURE.read_text(encoding="utf-8")))
        init = _build_init_data_from_bundle(loaded)
        for payload in (loaded, init):
            for key in BUNDLE_SYSTEMS + BUNDLE_CARRIERS:
                assert payload[key] == static[key], key
            for got, want in zip(payload["history"], static["history"], strict=True):
                for key in SNAPSHOT_SYSTEMS:
                    assert got[key] == want[key], key

    def test_streaming_turns_and_completion_rebuild_the_bundle_for_reconnect(self):
        """Turn messages (as run_live sends them) then the completed message."""
        from chronicler.bundle_codec import load_bundle
        from chronicler.live import apply_completed_message, apply_turn_message
        from chronicler.transport import BUNDLE_SYSTEMS, SNAPSHOT_SYSTEMS, TURN_MESSAGE_KEYS
        static = load_bundle(FIXTURE)
        init = {"type": "init", "state": "running", "world_state": static["world_state"], "history": [],
                "chronicle_entries": {}, "events_timeline": [], "named_events": [], "era_reflections": {},
                "metadata": static["metadata"]}
        for snap in static["history"]:
            message = dict(snap, type="turn", chronicle_text="", events=[], named_events=[])
            apply_turn_message(init, message)
        apply_completed_message(init, {"type": "completed",
                                       "systems": {k: static[k] for k in BUNDLE_SYSTEMS}})
        assert init["history"] == static["history"]  # no turn-message keys in the rows
        assert not any(k in row for row in init["history"] for k in TURN_MESSAGE_KEYS)
        for key in BUNDLE_SYSTEMS:
            assert init[key] == static[key]
        assert all(set(SNAPSHOT_SYSTEMS) <= set(row) for row in init["history"])

    def test_completed_systems_read_the_written_bundle(self, tmp_path):
        from chronicler.live import completed_systems
        from chronicler.transport import BUNDLE_SYSTEMS
        out = tmp_path / "chronicle_bundle.json"
        out.write_bytes(FIXTURE.read_bytes())
        assert sorted(completed_systems(out)) == sorted(BUNDLE_SYSTEMS)
        assert completed_systems(tmp_path / "missing.json") == {}


# ---------------------------------------------------------------------------
# Item 6: malformed version-6 patches
# ---------------------------------------------------------------------------

_FIRST = {"turn": 1, "civ_stats": {"A": {"population": 1}}, "active_wars": [["A", "B"]]}


@pytest.mark.parametrize("delta, needle", [
    ([_FIRST, {"active_wars": {"~l": [[5, 1]]}}], "history_delta[1]"),
    ([_FIRST, {"active_wars": {"~l": 3}}], "'~l' must be a list"),
    ([_FIRST, {"~o": ["turn", "nope"]}], "'~o'"),
    ([_FIRST, {"active_wars": {"~l": [], "~n": "x"}}], "'~n'"),
    ([_FIRST, {"active_wars": {"~l": [], "~n": 9}}], "'~n'"),
    ([_FIRST, {"~d": 5}], "'~d'"),
    ([_FIRST, {"~d": ["missing"]}], "'~d'"),
    ([_FIRST, {"active_wars": {"~t": [1]}}], "needs '~l'"),
    ([_FIRST, {"civ_stats": {"~l": []}}], "object patch"),
    ([_FIRST, {"turn": {"~t": []}}], "against a int"),
    ([_FIRST, {"turn": {"~r": 2, "x": 1}}], "'~r'"),
    ([_FIRST, ["x"]], "must be an object"),
    ({"turn": 1}, "must be a list"),
    (["not a snapshot"], "history_delta[0]"),
])
def test_malformed_history_delta_raises_a_clear_error(delta, needle):
    from chronicler.bundle_codec import BundleDecodeError, decode_bundle
    with pytest.raises(BundleDecodeError) as info:
        decode_bundle({"history_delta": delta, "metadata": {"bundle_version": 6}})
    assert needle in str(info.value)
    assert isinstance(info.value, ValueError)


def test_the_live_loader_reports_a_malformed_delta():
    from chronicler.live import _validate_legacy_live_bundle
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bundle["history_delta"][2] = {"active_wars": {"~l": [[99, 1]]}}
    with pytest.raises(ValueError, match=r"history_delta\[2\]"):
        _validate_legacy_live_bundle(bundle)


def test_valid_deltas_decode_as_before():
    from chronicler.bundle_codec import decode_history, encode_history
    history = [_FIRST, {"turn": 2, "civ_stats": {}, "active_wars": []},
               {"turn": 3, "civ_stats": {"B": {"population": 2}}, "active_wars": [["A", "B"], ["B", "C"]]}]
    assert decode_history(encode_history(history)) == history


# ---------------------------------------------------------------------------
# The convention itself
# ---------------------------------------------------------------------------

class TestAsOf:
    def test_phases_reduce_to_the_completed_turn(self):
        from chronicler.historical_context import AsOf, Phase
        assert AsOf.after(10) == AsOf(10, Phase.END)
        assert (AsOf.after(10).completed, AsOf.after(10).snapshot_turn) == (10, 11)
        assert (AsOf.before(10).completed, AsOf.before(10).snapshot_turn) == (9, 10)
        assert AsOf.at_snapshot(10) == AsOf.before(10)
        assert AsOf.after(10).knows(10) and not AsOf.before(10).knows(10)
        assert not AsOf.after(10).knows(None)

    def test_the_snapshot_is_never_a_later_one(self):
        from chronicler.historical_context import AsOf, HistoricalRecord, snapshot_as_of
        history = [_snap(t, {"A": _row()}) for t in (1, 5, 9)]
        record = HistoricalRecord(history=history)
        assert record.snapshot(AsOf.after(7)).turn == 5
        assert snapshot_as_of(history, AsOf.after(7)).turn == 5
        assert record.snapshot(AsOf.after(8)).turn == 9
        assert record.snapshot(AsOf.before(0)) is None

    def test_views_are_immutable_and_cached(self):
        import dataclasses
        from chronicler.historical_context import AsOf, HistoricalRecord
        world, _m, people, history = _turn10_case()
        record = HistoricalRecord(history=history, great_persons=people, world=world)
        view = record.view(AsOf.after(10))
        assert record.view(AsOf.after(10)) is view
        with pytest.raises(dataclasses.FrozenInstanceError):
            view.observed = True
        with pytest.raises(TypeError):
            view.character("Asha").memories[0]["turn"] = 1

    def test_observations_follow_observed_through(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        world, _m, people, history = _turn10_case()
        assert HistoricalRecord(world=world).observed_through == 499
        assert HistoricalRecord(history=history).observed_through == 11
        assert HistoricalRecord(world=world, observed_through=None).observed_at(AsOf.after(1))
        record = HistoricalRecord(great_persons=people, world=world)
        assert record.view(AsOf.after(499)).character("Asha").needs is not None
        assert record.view(AsOf.after(498)).character("Asha").needs is None

    def test_memories_fade_so_a_strong_one_was_at_least_as_strong(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        from chronicler.narrative import render_memory
        gp = _gp("Edda", "A", 1, agent_id=5, memories=[
            {"event_type": 1, "source_civ": 0, "turn": 3, "intensity": 70},
            {"event_type": 1, "source_civ": 0, "turn": 4, "intensity": 40},
            {"event_type": 1, "source_civ": 0, "turn": 5, "intensity": 10}])
        from chronicler.models import WorldState
        record = HistoricalRecord(great_persons=[gp], world=WorldState(name="W", seed=1, turn=100,
                                                                       regions=[], civilizations=[]))
        ch = record.view(AsOf.after(20)).character("Edda")
        assert [m["turn"] for m in ch.memories] == [3, 4] and not ch.memory_strength_observed
        lines = [render_memory(dict(m), ["A"], ch.memory_strength_observed) for m in ch.memories]
        assert lines == ["combat against the A (turn 3, vivid)", "combat against the A (turn 4)"]

    def test_hostage_status_and_role_as_of_the_capture(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        gp = GreatPerson(name="Ivo", role="hostage", trait="bold", civilization="B", origin_civilization="A",
                         born_turn=2, source="agent", agent_id=8, is_hostage=True, captured_by="B",
                         pre_hostage_role="general")
        taken = Event(turn=40, event_type="hostage_taken", actors=["B", "A"],
                      description="B takes Ivo hostage from A.", importance=6)
        record = HistoricalRecord(great_persons=[gp], events=[taken], observed_through=99)
        before, after = record.view(AsOf.after(30)).character("Ivo"), record.view(AsOf.after(40)).character("Ivo")
        assert (before.role, before.is_hostage, before.civilization) == ("general", False, "A")
        assert (after.role, after.is_hostage, after.captured_by) == ("hostage", True, "B")

    def test_bonds_dissolved_later_were_live_at_the_moment(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        a = _gp("Ana", "A", 1, agent_id=1)
        b = _gp("Bo", "A", 1, agent_id=2)
        record = HistoricalRecord(great_persons=[a, b], observed_through=99,
                                  dissolved_edges_by_turn={50: [(1, 2, 6, 10)]},
                                  agent_name_map={1: "Ana", 2: "Bo"})
        view = record.view(AsOf.after(20))
        rels = view.relationships(view.characters, (18, 20), per_character_bonds=True)
        assert rels == [{"type": "friend", "character_a": "Ana", "character_b": "Bo", "since_turn": 10}]
        late = record.view(AsOf.after(50))
        rels = late.relationships(late.characters, (50, 50), per_character_bonds=True)
        assert [r["type"] for r in rels] == ["friend (dissolved)"]

    def test_settlements_come_from_the_snapshot(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        from chronicler.models import SettlementSummary
        def town(i, region, pop):
            return SettlementSummary(settlement_id=i, name=f"T{i}", region_name=region, population_estimate=pop,
                                     centroid_x=0, centroid_y=0, founding_turn=1, status="active")
        snap = _snap(11, {"A": _row()}, control={"R1": "A", "R2": "B"})
        snap.active_settlements = [town(1, "R1", 50), town(2, "R2", 900), town(3, "R1", 70)]
        view = HistoricalRecord(history=[snap]).view(AsOf.after(10))
        assert [s.name for s in view.settlements("A")] == ["T3", "T1"]


# ---------------------------------------------------------------------------
# In-world accounts as of the moment (consistency follow-ups; failed on main
# dae4ba5: the narrator's account block and the mechanical chronicle reported
# losses dated after the moment, for every chronicler)
# ---------------------------------------------------------------------------

def _account_row(event_id, chron, text, stance="victory", transforms=(), lost=None, cause=None, turn=10):
    return [event_id, chron, turn, stance, [list(t) for t in transforms], [], text, lost, cause]


def _accounts_field():
    """Two courts' accounts of a turn-10 battle; court:1's archive is sacked at turn 300.

    A turn-20 famine is told by two temples whose archives fall at turns 100
    and 300: at the end every copy is lost (no ``lost`` divergence), at turn
    200 one copy survives (``lost``).
    """
    from chronicler.historiography import ACCOUNT_COLUMNS
    return {
        "chroniclers": [{"id": "court:0", "name": "the A chronicles"},
                        {"id": "court:1", "name": "the B chronicles"},
                        {"id": "temple:0", "name": "the temple scribes of A"},
                        {"id": "temple:1", "name": "the temple scribes of B"}],
        "archives": [
            {"owner": "court:1", "losses": [{"turn": 300, "cause": "sack", "region_name": "Reeds",
                                             "event_id": "300:occupation:0"}]},
            {"owner": "temple:0", "losses": [{"turn": 100, "cause": "fire", "region_name": "Ash",
                                              "event_id": "100:fire:0"}]},
            {"owner": "temple:1", "losses": [{"turn": 300, "cause": "sack", "region_name": "Reeds",
                                              "event_id": "300:occupation:0"}]},
        ],
        "account_columns": list(ACCOUNT_COLUMNS),
        "accounts": [
            _account_row("10:war:0", "court:0", "A won at the ford.",
                         transforms=[("inflate", {"of": "enemy losses", "true": 3, "claimed": 9})]),
            _account_row("10:war:0", "court:1", "B held the ford.", transforms=[("claim", {})],
                         lost=300, cause="sack"),
            _account_row("20:famine:0", "temple:0", "The gods struck B.", stance="disaster",
                         transforms=[("divine", {"mode": "punish", "target": "B"})], lost=100, cause="fire",
                         turn=20),
            _account_row("20:famine:0", "temple:1", "The rains failed.", stance="disaster",
                         lost=300, cause="sack", turn=20),
        ],
        "contested": [{"event_id": "10:war:0", "divergence": ["lost", "magnitude", "outcome"]},
                      {"event_id": "20:famine:0", "divergence": ["divine"]}],
    }


def _battle():
    return Event(turn=10, event_type="war", actors=["A", "B"], description="Battle at the ford",
                 importance=8, event_id="10:war:0")


class TestAccountsAsOf:
    """The narrator sees only the losses dated at or before the moment's last turn."""

    def test_a_later_loss_is_not_in_the_narrator_prompt(self):
        from chronicler.historiography import AccountIndex
        engine = _engine(None)
        engine._accounts = AccountIndex(_accounts_field())
        prep = engine._prepare_narration_prompts([_moment((10, 10), [_battle()])], [])[0]
        prompt = prep["prompt"]
        assert "IN-WORLD ACCOUNTS" in prompt
        assert "turn 300" not in prompt and "no account survives" not in prompt
        assert "the B chronicles (claim): “B held the ford.”" in prompt  # its copy stood at turn 10
        assert set(prep["account_ids"]) == {"court:0/10:war:0", "court:1/10:war:0"}

    def test_a_later_loss_is_not_in_the_mechanical_chronicle(self):
        from chronicler.historiography import AccountIndex
        from chronicler.llm import MechanicalClient
        from chronicler.narrative import NarrativeEngine
        engine = NarrativeEngine(MechanicalClient(), MechanicalClient())
        [entry] = engine.narrate_batch([_moment((10, 10), [_battle()])], [],
                                       historiography=AccountIndex(_accounts_field()))
        assert "No account from the B chronicles survives" not in entry.narrative
        assert "Though the B chronicles say: “B held the ford.”" in entry.narrative

    def test_the_view_after_the_loss_reports_it(self):
        from chronicler.historical_context import AsOf
        from chronicler.historiography import AccountIndex
        index = AccountIndex(_accounts_field())
        before, after = index.as_of(AsOf.after(299)), index.as_of(AsOf.after(300))
        assert "turn 300" not in before.prompt_block([_battle()])[0]
        assert "the B chronicles: lost (archive sacked, turn 300); no account survives" in after.prompt_block(
            [_battle()])[0]
        # The final index is the view after the last loss.
        assert after.prompt_block([_battle()]) == index.prompt_block([_battle()])
        assert after.passage([_battle()]) == index.passage([_battle()])
        assert index.as_of(AsOf.before(300)).accounts_for("10:war:0")[1]["lost_turn"] is None

    def test_divergence_is_the_divergence_at_the_moment(self):
        from chronicler.historical_context import AsOf
        from chronicler.historiography import AccountIndex
        index = AccountIndex(_accounts_field())
        kinds = lambda view, eid: view.contested.get(eid, {}).get("divergence", [])
        assert kinds(index.as_of(AsOf.after(10)), "10:war:0") == ["magnitude", "outcome"]
        assert kinds(index.as_of(AsOf.after(300)), "10:war:0") == ["lost", "magnitude", "outcome"]
        # Every copy is lost at the end; at turn 200 one still stood.
        assert kinds(index.as_of(AsOf.after(50)), "20:famine:0") == ["divine"]
        assert kinds(index.as_of(AsOf.after(200)), "20:famine:0") == ["divine", "lost"]
        assert kinds(index.as_of(AsOf.after(300)), "20:famine:0") == ["divine"]
        famine = Event(turn=20, event_type="famine", actors=["B"], description="Famine", importance=7,
                       event_id="20:famine:0")
        block = index.as_of(AsOf.after(200)).prompt_block([famine])[0]
        assert "lost (archive burned, turn 100)" in block and "turn 300" not in block
        assert "“The rains failed.”" in block

    def test_the_record_routes_accounts_through_its_views(self):
        from chronicler.historical_context import AsOf, HistoricalRecord
        from chronicler.historiography import AccountIndex
        index = AccountIndex(_accounts_field())
        record = HistoricalRecord(accounts=index)
        view = record.view(AsOf.after(10))
        assert view.accounts is record.view(AsOf.after(10)).accounts
        assert view.accounts.accounts_for("10:war:0")[1]["lost_turn"] is None
        assert HistoricalRecord().view(AsOf.after(10)).accounts is None
