"""Tests for snapshot models and bundle assembly."""
import argparse
import json
import pytest
from chronicler.models import (
    CivSnapshot, RelationshipSnapshot, TurnSnapshot, TechEra, Region,
)
from chronicler.scenario import RegionOverride, ScenarioConfig, apply_scenario
from chronicler.models import WorldState, Leader, Civilization, Relationship, Disposition
from chronicler.bundle import assemble_bundle, write_bundle
from chronicler.models import ChronicleEntry, NarrativeRole


def _entry(turn, narrative):
    """Helper to build a minimal ChronicleEntry for bundle tests."""
    return ChronicleEntry(
        turn=turn, covers_turns=(turn, turn),
        events=[], named_events=[],
        narrative=narrative, importance=5.0,
        narrative_role=NarrativeRole.RESOLUTION,
        causal_links=[],
    )


class TestSnapshotModels:
    def test_civ_snapshot_round_trip(self):
        snap = CivSnapshot(
            population=70, military=50, economy=80, culture=60, stability=60,
            treasury=120, asabiya=0.6, tech_era=TechEra.IRON,
            trait="calculating", regions=["Verdant Plains", "Sapphire Coast"],
            leader_name="Empress Vaelith", alive=True,
        )
        data = json.loads(snap.model_dump_json())
        restored = CivSnapshot.model_validate(data)
        assert restored.population == 70
        assert restored.tech_era == TechEra.IRON
        assert restored.trait == "calculating"
        assert restored.alive is True
        assert restored.regions == ["Verdant Plains", "Sapphire Coast"]

    def test_relationship_snapshot_round_trip(self):
        snap = RelationshipSnapshot(disposition="hostile")
        data = json.loads(snap.model_dump_json())
        restored = RelationshipSnapshot.model_validate(data)
        assert restored.disposition == "hostile"

    def test_turn_snapshot_round_trip(self):
        snap = TurnSnapshot(
            turn=5,
            civ_stats={
                "Kethani Empire": CivSnapshot(
                    population=70, military=50, economy=80, culture=60,
                    stability=60, treasury=120, asabiya=0.6,
                    tech_era=TechEra.IRON, trait="calculating",
                    regions=["Verdant Plains"], leader_name="Empress Vaelith",
                    alive=True,
                ),
            },
            region_control={"Verdant Plains": "Kethani Empire", "Thornwood": None},
            relationships={
                "Kethani Empire": {
                    "Dorrathi Clans": RelationshipSnapshot(disposition="suspicious"),
                },
            },
        )
        data = json.loads(snap.model_dump_json())
        restored = TurnSnapshot.model_validate(data)
        assert restored.turn == 5
        assert restored.civ_stats["Kethani Empire"].population == 70
        assert restored.region_control["Thornwood"] is None
        assert restored.relationships["Kethani Empire"]["Dorrathi Clans"].disposition == "suspicious"


class TestRegionCoordinates:
    def test_region_defaults_to_no_coordinates(self):
        r = Region(name="Plains", terrain="plains", carrying_capacity=50, resources="fertile")
        assert r.x is None
        assert r.y is None

    def test_region_with_coordinates(self):
        r = Region(name="Plains", terrain="plains", carrying_capacity=50, resources="fertile",
                    x=0.3, y=0.7)
        assert r.x == 0.3
        assert r.y == 0.7


class TestRegionCoordinatePropagation:
    def test_apply_scenario_copies_coordinates(self, sample_world):
        config = ScenarioConfig(
            name="coord_test",
            regions=[
                RegionOverride(name="Verdant Plains", x=0.2, y=0.8),
            ],
        )
        apply_scenario(sample_world, config)
        region = next(r for r in sample_world.regions if r.name == "Verdant Plains")
        assert region.x == 0.2
        assert region.y == 0.8

    def test_apply_scenario_leaves_coords_none_when_absent(self, sample_world):
        config = ScenarioConfig(
            name="no_coord_test",
            regions=[
                RegionOverride(name="Verdant Plains", terrain="desert"),
            ],
        )
        apply_scenario(sample_world, config)
        region = next(r for r in sample_world.regions if r.name == "Verdant Plains")
        assert region.x is None
        assert region.y is None


class TestBundleAssembly:
    def test_assemble_bundle_has_all_keys(self, sample_world):
        history = [
            TurnSnapshot(
                turn=1,
                civ_stats={
                    "Kethani Empire": CivSnapshot(
                        population=70, military=50, economy=80, culture=60,
                        stability=60, treasury=120, asabiya=0.6,
                        tech_era=TechEra.IRON, trait="calculating",
                        regions=["Verdant Plains"], leader_name="Empress Vaelith",
                        alive=True,
                    ),
                    "Dorrathi Clans": CivSnapshot(
                        population=40, military=70, economy=30, culture=50,
                        stability=40, treasury=50, asabiya=0.8,
                        tech_era=TechEra.IRON, trait="aggressive",
                        regions=["Iron Peaks"], leader_name="Warchief Gorath",
                        alive=True,
                    ),
                },
                region_control={"Verdant Plains": "Kethani Empire", "Iron Peaks": "Dorrathi Clans"},
                relationships={
                    "Kethani Empire": {"Dorrathi Clans": RelationshipSnapshot(disposition="suspicious")},
                    "Dorrathi Clans": {"Kethani Empire": RelationshipSnapshot(disposition="hostile")},
                },
            ),
        ]
        chronicle_entries = [_entry(1, "The empires clashed.")]
        era_reflections = {10: "## Era: Turns 1-10\n\nReflection text."}

        bundle = assemble_bundle(
            world=sample_world,
            history=history,
            chronicle_entries=chronicle_entries,
            era_reflections=era_reflections,
            sim_model="test-model",
            narrative_model="test-model",
            interestingness_score=None,
        )

        assert "world_state" in bundle
        assert "history" in bundle
        assert "events_timeline" in bundle
        assert "named_events" in bundle
        assert "chronicle_entries" in bundle
        assert "era_reflections" in bundle
        assert "metadata" in bundle

    def test_chronicle_entries_serialized_as_list(self, sample_world):
        history = []
        entries = [
            _entry(1, "Turn one prose."),
            _entry(2, "Turn two prose."),
        ]
        bundle = assemble_bundle(
            world=sample_world, history=history,
            chronicle_entries=entries, era_reflections={},
            sim_model="m", narrative_model="m",
            interestingness_score=None,
        )
        assert isinstance(bundle["chronicle_entries"], list)
        assert len(bundle["chronicle_entries"]) == 2
        assert bundle["chronicle_entries"][0]["turn"] == 1
        assert bundle["chronicle_entries"][0]["narrative"] == "Turn one prose."
        assert bundle["chronicle_entries"][1]["turn"] == 2
        assert bundle["chronicle_entries"][1]["narrative"] == "Turn two prose."

    def test_metadata_fields(self, sample_world):
        bundle = assemble_bundle(
            world=sample_world, history=[], chronicle_entries=[],
            era_reflections={}, sim_model="sim-v1", narrative_model="narr-v2",
            interestingness_score=42.5,
        )
        meta = bundle["metadata"]
        assert meta["seed"] == 42
        assert meta["sim_model"] == "sim-v1"
        assert meta["narrative_model"] == "narr-v2"
        assert meta["interestingness_score"] == 42.5
        assert meta["scenario_name"] is None
        assert "generated_at" in meta
        assert "total_turns" in meta

    def test_events_timeline_serialized(self, sample_world):
        from chronicler.models import Event
        sample_world.events_timeline = [
            Event(turn=1, event_type="war", actors=["A", "B"],
                  description="A attacked B", importance=7),
        ]
        bundle = assemble_bundle(
            world=sample_world, history=[], chronicle_entries=[],
            era_reflections={}, sim_model="m", narrative_model="m",
            interestingness_score=None,
        )
        assert len(bundle["events_timeline"]) == 1
        assert bundle["events_timeline"][0]["event_type"] == "war"
        assert bundle["events_timeline"][0]["importance"] == 7

    def test_named_events_serialized(self, sample_world):
        from chronicler.models import NamedEvent
        sample_world.named_events = [
            NamedEvent(name="Battle of Iron Peaks", event_type="battle",
                       turn=3, actors=["A", "B"], region="Iron Peaks",
                       description="A great battle", importance=8),
        ]
        bundle = assemble_bundle(
            world=sample_world, history=[], chronicle_entries=[],
            era_reflections={}, sim_model="m", narrative_model="m",
            interestingness_score=None,
        )
        assert len(bundle["named_events"]) == 1
        assert bundle["named_events"][0]["name"] == "Battle of Iron Peaks"


class TestWriteBundle:
    def test_write_bundle_creates_file(self, tmp_path):
        bundle = {"world_state": {}, "metadata": {"seed": 42}}
        path = tmp_path / "output" / "chronicle_bundle.json"
        write_bundle(bundle, path)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["metadata"]["seed"] == 42

    def test_write_bundle_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "bundle.json"
        write_bundle({"test": True}, path)
        assert path.exists()


class TestSnapshotCapture:
    def _make_args(self, tmp_path, seed=42, turns=5):
        return argparse.Namespace(
            seed=seed,
            turns=turns,
            civs=2,
            regions=5,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None,
            reflection_interval=10,
            llm_actions=False,
            scenario=None,
            pause_every=None,
        )

    def test_bundle_written_on_completion(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=5)
        execute_run(args)
        bundle_path = tmp_path / "chronicle_bundle.json"
        assert bundle_path.exists()

    def test_bundle_contains_correct_history_length(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=5)
        execute_run(args)
        bundle_path = tmp_path / "chronicle_bundle.json"
        bundle = json.loads(bundle_path.read_text())
        assert len(bundle["history"]) == 5

    def test_bundle_history_has_all_civs(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=3)
        execute_run(args)
        bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
        for snapshot in bundle["history"]:
            assert len(snapshot["civ_stats"]) == 2
            for civ_data in snapshot["civ_stats"].values():
                assert civ_data["alive"] is True

    def test_bundle_history_has_relationships(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=3)
        execute_run(args)
        bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
        for snapshot in bundle["history"]:
            assert "relationships" in snapshot
            assert len(snapshot["relationships"]) > 0

    def test_bundle_has_events_timeline(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=5)
        execute_run(args)
        bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
        assert "events_timeline" in bundle
        assert isinstance(bundle["events_timeline"], list)

    def test_bundle_has_named_events(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=5)
        execute_run(args)
        bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
        assert "named_events" in bundle
        assert isinstance(bundle["named_events"], list)

    def test_bundle_metadata_has_models(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=3)
        execute_run(args)
        bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
        meta = bundle["metadata"]
        assert "sim_model" in meta
        assert "narrative_model" in meta
        assert "interestingness_score" in meta

    def test_existing_outputs_unchanged(self, tmp_path):
        from chronicler.main import execute_run
        args = self._make_args(tmp_path, turns=3)
        execute_run(args)
        assert (tmp_path / "state.json").exists()
        assert (tmp_path / "chronicle.md").exists()


class TestBundleSize:
    @pytest.mark.slow
    def test_500_turn_bundle_under_5mb(self, tmp_path):
        from chronicler.main import execute_run
        args = argparse.Namespace(
            seed=1, turns=500, civs=5, regions=10,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=50,
            llm_actions=False, scenario=None, pause_every=None,
        )
        execute_run(args)
        bundle_path = tmp_path / "chronicle_bundle.json"
        size_mb = bundle_path.stat().st_size / (1024 * 1024)
        assert size_mb < 20, f"Bundle is {size_mb:.2f}MB, expected < 20MB"
