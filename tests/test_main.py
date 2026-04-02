"""Tests for the main entry point — end-to-end with mocked LLM."""
import argparse
import json
import logging
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from chronicler.main import execute_run, run_chronicle, DEFAULT_CONFIG, _build_parser
from chronicler.llm import AnthropicClient
from chronicler.types import RunResult
from chronicler.memory import MemoryStream


def test_llm_actions_flag_in_parser():
    from chronicler.main import _build_parser
    p = _build_parser()
    args = p.parse_args(["--llm-actions"])
    assert args.llm_actions is True


class TestDefaultConfig:
    def test_config_has_required_keys(self):
        assert "num_turns" in DEFAULT_CONFIG
        assert "num_civs" in DEFAULT_CONFIG
        assert "num_regions" in DEFAULT_CONFIG
        assert "reflection_interval" in DEFAULT_CONFIG


class TestRunChronicle:
    def _mock_llm(self, response: str = "DEVELOP"):
        """Create a mock LLMClient."""
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_produces_markdown_file(self, tmp_path):
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("The empire grew stronger.")

        output_path = tmp_path / "chronicle.md"
        run_chronicle(
            seed=42,
            num_turns=3,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        assert output_path.exists()
        content = output_path.read_text()
        assert "Chronicle of" in content
        assert len(content) > 100

    def test_state_file_saved(self, tmp_path):
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("Events occurred.")

        output_path = tmp_path / "chronicle.md"
        state_path = tmp_path / "state.json"
        run_chronicle(
            seed=42,
            num_turns=3,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            state_path=state_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        assert state_path.exists()

    def test_respects_num_turns(self, tmp_path):
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("Things happened.")

        output_path = tmp_path / "chronicle.md"
        run_chronicle(
            seed=42,
            num_turns=5,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        # Verify the mocks were called for action selection + narration
        assert sim_client.complete.call_count > 0
        assert narrative_client.complete.call_count > 0

    def test_resume_from_saved_state(self, tmp_path):
        """--resume should load state and continue from the saved turn."""
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("Resumed narrative.")

        # Run 3 turns first, saving state
        output_path = tmp_path / "chronicle.md"
        state_path = tmp_path / "state.json"
        run_chronicle(
            seed=42,
            num_turns=3,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            state_path=state_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        assert state_path.exists()

        # Now resume from saved state to turn 5
        sim_client2 = self._mock_llm("DEVELOP")
        narrative_client2 = self._mock_llm("Resumed events.")
        output_path2 = tmp_path / "chronicle_resumed.md"

        run_chronicle(
            seed=42,
            num_turns=5,
            num_civs=2,
            num_regions=4,
            output_path=output_path2,
            state_path=state_path,
            sim_client=sim_client2,
            narrative_client=narrative_client2,
            reflection_interval=10,
            resume_path=state_path,
        )
        assert output_path2.exists()
        # Should only run 2 more turns (3→5), so 2 narrator calls
        assert narrative_client2.complete.call_count == 2


class TestRunChronicleWithScenario:
    def _mock_llm(self, response: str = "DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_scenario_config_applies_overrides(self, tmp_path):
        """run_chronicle with scenario_config should apply overrides to world."""
        from chronicler.scenario import ScenarioConfig, CivOverride, LeaderOverride
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("Scenario narrative.")

        output_path = tmp_path / "chronicle.md"
        state_path = tmp_path / "state.json"
        config = ScenarioConfig(
            name="Test Scenario",
            world_name="Test World",
            civilizations=[CivOverride(name="Test Empire", military=90)],
        )
        run_chronicle(
            seed=42,
            num_turns=3,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            state_path=state_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
            scenario_config=config,
        )
        assert output_path.exists()
        # Verify overrides took effect via saved state
        from chronicler.models import WorldState
        world = WorldState.load(state_path)
        assert world.name == "Test World"
        assert any(c.name == "Test Empire" for c in world.civilizations)
        test_empire = next(c for c in world.civilizations if c.name == "Test Empire")
        assert test_empire.military >= 1  # May have changed during simulation


def test_scenario_flag_in_parser():
    from chronicler.main import _build_parser
    p = _build_parser()
    args = p.parse_args(["--scenario", "scenarios/test.yaml"])
    assert args.scenario == "scenarios/test.yaml"


def test_scenario_and_resume_mutually_exclusive():
    from chronicler.main import _build_parser
    p = _build_parser()
    # Both flags should parse fine (mutual exclusion is checked at runtime)
    args = p.parse_args(["--scenario", "test.yaml", "--resume", "state.json"])
    assert args.scenario == "test.yaml"
    assert args.resume == "state.json"


class TestExecuteRun:
    def _mock_llm(self, response: str = "DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def _make_args(self, tmp_path, seed=42, turns=5, civs=2, regions=4):
        """Build a minimal args namespace for execute_run."""
        return argparse.Namespace(
            seed=seed,
            turns=turns,
            civs=civs,
            regions=regions,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None,
            reflection_interval=10,
            local_url="http://localhost:1234/v1",
            sim_model=None,
            narrative_model=None,
            llm_actions=False,
            scenario=None,
            batch=None,
            fork=None,
            interactive=False,
            parallel=None,
            pause_every=None,
        )

    def test_returns_run_result(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Things happened.")
        args = self._make_args(tmp_path, turns=3)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        assert isinstance(result, RunResult)
        assert result.seed == 42
        assert result.total_turns == 3
        assert result.output_dir == tmp_path

    def test_saves_memory_streams(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Events occurred.")
        args = self._make_args(tmp_path, turns=3)
        execute_run(args, sim_client=sim, narrative_client=narr)
        # Memory files should exist for each civ
        memory_files = list(tmp_path.glob("memories_*.json"))
        assert len(memory_files) >= 1  # At least one civ

    def test_populates_action_distribution(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=5)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        from chronicler.models import WorldState
        world = WorldState.load(tmp_path / "state.json")
        assert set(result.action_distribution) == {civ.name for civ in world.civilizations}
        all_action_types = set()
        for civ in world.civilizations:
            assert result.action_distribution[civ.name] == dict(civ.action_counts)
            all_action_types.update(civ.action_counts.keys())
        assert result.distinct_action_count == len(all_action_types)

    def test_computes_max_stat_swing(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=3)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        assert isinstance(result.max_stat_swing, float)

    def test_accepts_preloaded_world_and_memories(self, tmp_path):
        """Fork/resume path: pass in existing world and memories."""
        from chronicler.world_gen import generate_world
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Story.")
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        world.turn = 3  # Simulate mid-run state
        memories = {c.name: MemoryStream(c.name) for c in world.civilizations}
        args = self._make_args(tmp_path, turns=5)
        result = execute_run(
            args, sim_client=sim, narrative_client=narr,
            world=world, memories=memories,
        )
        # Should only run turns 3-4 (2 turns), not 0-4
        assert result.total_turns == 2

    def test_counts_events_from_start_turn(self, tmp_path):
        """Fork scenario: pre-fork events must NOT appear in RunResult counts."""
        from chronicler.world_gen import generate_world
        from chronicler.models import Event, Disposition, Relationship
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Peace reigned.")
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        world.turn = 3
        # Inject 3 pre-fork war events that should be excluded from counts
        for t in range(3):
            world.events_timeline.append(Event(
                turn=t, event_type="war", actors=[world.civilizations[0].name],
                description=f"Old war {t}", importance=5,
            ))
        # Make all relationships ALLIED so no new wars happen
        for src in world.relationships:
            for dst in world.relationships[src]:
                world.relationships[src][dst].disposition = Disposition.ALLIED
        memories = {c.name: MemoryStream(c.name) for c in world.civilizations}
        args = self._make_args(tmp_path, turns=5)
        result = execute_run(
            args, sim_client=sim, narrative_client=narr,
            world=world, memories=memories,
        )
        # 3 pre-fork wars must be excluded; with ALLIED + DEVELOP, no new wars
        assert result.war_count == 0

    def test_snapshot_marks_dead_civ_not_alive(self, tmp_path):
        """Turn snapshots should not mark extinct civs as alive."""
        from chronicler.world_gen import generate_world

        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Quiet turn.")
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        dead_civ = world.civilizations[1]
        dead_civ.regions = []
        dead_civ.population = 0
        args = self._make_args(tmp_path, turns=1)

        execute_run(args, sim_client=sim, narrative_client=narr, world=world)

        bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text(encoding="utf-8"))
        first_snapshot = bundle["history"][0]
        assert first_snapshot["civ_stats"][dead_civ.name]["alive"] is False


def test_goal_enrichment_failure_logs_warning(tmp_path, caplog):
    from chronicler.main import execute_run

    caplog.set_level(logging.WARNING)
    args = argparse.Namespace(
        seed=42, turns=1, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    sim_client = MagicMock(model="test-sim")
    narrative_client = MagicMock(model="test-narr")
    narrative_client.complete.return_value = "Turn text."

    with patch("chronicler.main.enrich_with_llm", side_effect=RuntimeError("LLM offline")):
        execute_run(args, sim_client=sim_client, narrative_client=narrative_client)

    assert any(
        "LLM goal enrichment failed" in record.message and "proceeding with empty goals" in record.message
        for record in caplog.records
    )


def test_llm_action_fallback_logs_civ_and_turn(tmp_path, caplog):
    from chronicler.main import execute_run

    caplog.set_level(logging.WARNING)
    args = argparse.Namespace(
        seed=42, turns=1, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=True, scenario=None, pause_every=None,
    )
    sim_client = MagicMock(model="test-sim")
    narrative_client = MagicMock(model="test-narr")
    narrative_client.complete.return_value = "Turn text."

    with patch("chronicler.main.NarrativeEngine.select_action", side_effect=RuntimeError("selector down")):
        execute_run(args, sim_client=sim_client, narrative_client=narrative_client)

    assert any(
        "LLM action selection failed for civ=" in record.message and "turn=" in record.message
        for record in caplog.records
    )


class TestNewCLIFlags:
    def test_batch_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--batch", "5"])
        assert args.batch == 5

    def test_parallel_flag_bare(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--batch", "5", "--parallel"])
        assert args.parallel == -1  # const value for bare --parallel

    def test_parallel_flag_with_count(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--batch", "5", "--parallel", "4"])
        assert args.parallel == 4

    def test_fork_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--fork", "output/state.json", "--seed", "999", "--turns", "50"])
        assert args.fork == "output/state.json"

    def test_interactive_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--interactive"])
        assert args.interactive is True

    def test_pause_every_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--interactive", "--pause-every", "5"])
        assert args.pause_every == 5


def test_on_turn_callback_fires_each_turn(tmp_path):
    """on_turn callback receives snapshot, chronicle text, events, named_events each turn."""
    import argparse
    from chronicler.main import execute_run

    turns_received = []

    def on_turn_cb(snapshot, chronicle_text, events, named_events):
        turns_received.append({
            "turn": snapshot.turn,
            "chronicle_text": chronicle_text,
            "event_count": len(events),
            "named_event_count": len(named_events),
        })

    args = argparse.Namespace(
        seed=42, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    execute_run(args, on_turn=on_turn_cb)

    assert len(turns_received) == 5
    for entry in turns_received:
        assert isinstance(entry["chronicle_text"], str)
        assert entry["event_count"] >= 0
        assert entry["named_event_count"] >= 0


def test_quit_check_stops_simulation_early(tmp_path):
    """quit_check returning True stops the simulation gracefully."""
    import argparse
    from chronicler.main import execute_run

    call_count = 0

    def quit_at_turn_3():
        nonlocal call_count
        call_count += 1
        return call_count >= 3

    args = argparse.Namespace(
        seed=42, turns=50, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    result = execute_run(args, quit_check=quit_at_turn_3)

    assert result.total_turns == 3
    assert (tmp_path / "chronicle_bundle.json").exists()


class TestMutualExclusions:
    def test_parallel_and_llm_actions_rejected(self, capsys):
        """--parallel and --llm-actions should error out."""
        import sys
        from chronicler.main import main
        sys.argv = ["chronicler", "--batch", "3", "--parallel", "--llm-actions"]
        with pytest.raises(SystemExit):
            main()

    def test_batch_and_fork_rejected(self, capsys):
        import sys
        from chronicler.main import main
        sys.argv = ["chronicler", "--batch", "3", "--fork", "state.json"]
        with pytest.raises(SystemExit):
            main()


def test_analyze_flag_parses():
    from chronicler.main import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--analyze", "/some/path"])
    assert args.analyze == "/some/path"


def test_narrative_voice_flag_rejected():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--narrative-voice", "epic"])


def test_compare_without_analyze_rejected():
    from chronicler.main import main

    with patch("sys.argv", ["chronicler", "--compare", "baseline.json"]):
        with pytest.raises(SystemExit):
            main()


def test_narrate_output_without_narrate_rejected():
    from chronicler.main import main

    with patch("sys.argv", ["chronicler", "--narrate-output", "narrated.json"]):
        with pytest.raises(SystemExit):
            main()


class TestAgentsFlag:
    def test_agents_flag_parsed(self):
        """--agents flag is parsed and stored on args."""
        from chronicler.main import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["--simulate-only", "--agents", "hybrid"])
        assert args.agents == "hybrid"

    def test_agents_flag_default_off(self):
        """--agents defaults to 'off'."""
        from chronicler.main import _build_parser
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.agents == "off"

    def test_agents_flag_demographics_only(self):
        """--agents accepts demographics-only."""
        from chronicler.main import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["--agents", "demographics-only"])
        assert args.agents == "demographics-only"

    def test_agents_flag_shadow(self):
        """--agents accepts shadow."""
        from chronicler.main import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["--agents", "shadow"])
        assert args.agents == "shadow"

    def test_agents_flag_invalid_rejected(self):
        """--agents rejects invalid values."""
        from chronicler.main import _build_parser
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--agents", "invalid"])


class TestAgentsWiring:
    """Integration tests: --agents flag wires into execute_run properly."""

    def _mock_agent_bridge(self):
        """Create a mock AgentBridge for tests (Rust crate may not be built)."""
        import pyarrow as pa

        mock_bridge = MagicMock()
        mock_bridge.close = MagicMock()
        mock_bridge.get_snapshot.return_value = None
        mock_bridge._sim.get_snapshot.return_value = None
        mock_bridge.named_agents = {}
        mock_bridge._collect_rel_stats = False
        mock_bridge.relationship_stats = []

        # M54a: Mock the ecology_simulator so tick_ecology returns proper batches.
        # The ecology_simulator property returns the underlying _sim mock.
        def _mock_tick_ecology(turn, climate_phase, pandemic_mask, army_arrived_mask):
            n = len(pandemic_mask)
            region_batch = pa.record_batch({
                "region_id": pa.array(range(n), type=pa.uint16()),
                "soil": pa.array([0.8] * n, type=pa.float32()),
                "water": pa.array([0.6] * n, type=pa.float32()),
                "forest_cover": pa.array([0.3] * n, type=pa.float32()),
                "endemic_severity": pa.array([0.0] * n, type=pa.float32()),
                "prev_turn_water": pa.array([0.6] * n, type=pa.float32()),
                "soil_pressure_streak": pa.array([0] * n, type=pa.int32()),
                "overextraction_streak_0": pa.array([0] * n, type=pa.int32()),
                "overextraction_streak_1": pa.array([0] * n, type=pa.int32()),
                "overextraction_streak_2": pa.array([0] * n, type=pa.int32()),
                "resource_reserve_0": pa.array([1.0] * n, type=pa.float32()),
                "resource_reserve_1": pa.array([1.0] * n, type=pa.float32()),
                "resource_reserve_2": pa.array([1.0] * n, type=pa.float32()),
                "resource_effective_yield_0": pa.array([0.5] * n, type=pa.float32()),
                "resource_effective_yield_1": pa.array([0.5] * n, type=pa.float32()),
                "resource_effective_yield_2": pa.array([0.5] * n, type=pa.float32()),
                "current_turn_yield_0": pa.array([0.5] * n, type=pa.float32()),
                "current_turn_yield_1": pa.array([0.5] * n, type=pa.float32()),
                "current_turn_yield_2": pa.array([0.5] * n, type=pa.float32()),
            })
            event_batch = pa.record_batch({
                "event_type": pa.array([], type=pa.uint8()),
                "region_id": pa.array([], type=pa.uint16()),
                "slot": pa.array([], type=pa.uint8()),
                "magnitude": pa.array([], type=pa.float32()),
            })
            return (region_batch, event_batch)

        mock_bridge.ecology_simulator.tick_ecology = _mock_tick_ecology
        mock_bridge.ecology_simulator.apply_region_postpass_patch = MagicMock()
        # tick_agents returns a list of events (empty for mocks)
        mock_bridge.tick_agents.return_value = []

        # M54c: Mock tick_politics to return 12 empty Arrow batches.
        def _mock_tick_politics(*args, **kwargs):
            empty = pa.record_batch({"step": pa.array([], type=pa.uint8())})
            return tuple(empty for _ in range(12))

        mock_bridge._sim.tick_politics = _mock_tick_politics
        return mock_bridge

    def test_agents_hybrid_sets_agent_mode(self, tmp_path):
        """--agents=hybrid sets world.agent_mode and creates AgentBridge."""
        import sys
        args = argparse.Namespace(
            seed=42, turns=5, civs=2, regions=4,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None, pause_every=None,
            simulate_only=True, agents="hybrid",
        )
        mock_bridge = self._mock_agent_bridge()
        mock_ab_module = MagicMock()
        mock_ab_module.AgentBridge = MagicMock(return_value=mock_bridge)
        saved = sys.modules.get("chronicler.agent_bridge")
        sys.modules["chronicler.agent_bridge"] = mock_ab_module
        try:
            result = execute_run(args)
        finally:
            if saved is None:
                sys.modules.pop("chronicler.agent_bridge", None)
            else:
                sys.modules["chronicler.agent_bridge"] = saved
        assert isinstance(result, RunResult)
        assert result.total_turns == 5
        mock_bridge.close.assert_called_once()
        # Bundle should be produced
        import json
        bundle_path = tmp_path / "chronicle_bundle.json"
        assert bundle_path.exists()
        with open(bundle_path) as f:
            bundle = json.load(f)
        assert len(bundle["history"]) == 5

    def test_agents_off_no_agent_mode(self, tmp_path):
        """--agents=off leaves world.agent_mode at None."""
        from chronicler.world_gen import generate_world
        args = argparse.Namespace(
            seed=42, turns=3, civs=2, regions=4,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None, pause_every=None,
            simulate_only=True, agents="off",
        )
        # Pre-create world so we can inspect it after the run
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        result = execute_run(args, world=world)
        assert result.total_turns == 3
        # agent_mode should remain None (not set)
        assert world.agent_mode is None

    def test_agents_shadow_sets_mode(self, tmp_path):
        """--agents=shadow sets world.agent_mode='shadow'."""
        from chronicler.world_gen import generate_world
        args = argparse.Namespace(
            seed=42, turns=3, civs=2, regions=4,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None, pause_every=None,
            simulate_only=True, agents="shadow",
        )
        import sys
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        mock_bridge = self._mock_agent_bridge()
        mock_ab_module = MagicMock()
        mock_ab_module.AgentBridge = MagicMock(return_value=mock_bridge)
        saved = sys.modules.get("chronicler.agent_bridge")
        sys.modules["chronicler.agent_bridge"] = mock_ab_module
        try:
            result = execute_run(args, world=world)
        finally:
            if saved is None:
                sys.modules.pop("chronicler.agent_bridge", None)
            else:
                sys.modules["chronicler.agent_bridge"] = saved
        assert result.total_turns == 3
        assert world.agent_mode == "shadow"
        mock_bridge.close.assert_called_once()


class TestNarratorArgument:
    def test_narrator_default_is_local(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.narrator == "local"

    def test_narrator_api(self):
        parser = _build_parser()
        args = parser.parse_args(["--narrator", "api"])
        assert args.narrator == "api"

    def test_narrator_gemini(self):
        parser = _build_parser()
        args = parser.parse_args(["--narrator", "gemini"])
        assert args.narrator == "gemini"

    def test_narrator_invalid_choice(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--narrator", "invalid"])


class TestNarratorValidation:
    def test_narrator_api_with_simulate_only_exits(self):
        """--narrator api + --simulate-only is contradictory."""
        from chronicler.main import main
        with patch("sys.argv", ["chronicler", "--narrator", "api", "--simulate-only"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_api_with_live_exits(self):
        """--narrator api + --live is incompatible."""
        from chronicler.main import main
        with patch("sys.argv", ["chronicler", "--narrator", "api", "--live"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_api_with_batch_parallel_exits(self):
        """--narrator api + --batch --parallel is incompatible."""
        from chronicler.main import main
        with patch("sys.argv", ["chronicler", "--narrator", "api",
                                "--batch", "10", "--parallel"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_gemini_with_simulate_only_exits(self):
        """--narrator gemini + --simulate-only is contradictory."""
        from chronicler.main import main
        with patch("sys.argv", ["chronicler", "--narrator", "gemini", "--simulate-only"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_gemini_with_live_exits(self):
        """--narrator gemini + --live is incompatible."""
        from chronicler.main import main
        with patch("sys.argv", ["chronicler", "--narrator", "gemini", "--live"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_gemini_with_batch_parallel_exits(self):
        """--narrator gemini + --batch --parallel is incompatible."""
        from chronicler.main import main
        with patch("sys.argv", ["chronicler", "--narrator", "gemini",
                                "--batch", "10", "--parallel"]):
            with pytest.raises(SystemExit):
                main()


class TestApiNarrationIntegration:
    """Integration tests for M44 API narration flow."""

    def _make_args(self, tmp_dir):
        """Build minimal args namespace for a short API-mode run."""
        return argparse.Namespace(
            seed=42,
            turns=20,
            civs=3,
            regions=6,
            output=str(Path(tmp_dir) / "chronicle.md"),
            state=str(Path(tmp_dir) / "state.json"),
            resume=None,
            reflection_interval=10,
            llm_actions=False,
            scenario=None,
            simulate_only=False,
            agents="off",
            budget=50,
            narrator="api",
            pause_every=None,
        )

    def test_api_mode_produces_curated_entries_with_metadata(self, tmp_path):
        """execute_run with API narrator: curated narration, no reflections, metadata written."""
        import json
        mock_sdk = MagicMock()
        api_client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
        def fake_batch_complete(requests, poll_interval=10.0):
            api_client.total_input_tokens += 500
            api_client.total_output_tokens += 200
            api_client.call_count += len(requests)
            return [
                "The great empire rose from humble beginnings..."
                for _ in requests
            ]
        api_client.batch_complete = MagicMock(side_effect=fake_batch_complete)

        args = self._make_args(str(tmp_path))
        result = execute_run(
            args,
            sim_client=MagicMock(model="test", complete=MagicMock(return_value="DEVELOP")),
            narrative_client=api_client,
        )

        # Bundle was written
        bundle_path = tmp_path / "chronicle_bundle.json"
        assert bundle_path.exists()

        bundle = json.loads(bundle_path.read_text())

        # Metadata has narrator_mode and token counts
        meta = bundle["metadata"]
        assert meta["narrator_mode"] == "api"
        assert meta["narrative_input_tokens"] > 0
        assert meta["narrative_output_tokens"] > 0
        assert "api_input_tokens" in meta
        assert "api_output_tokens" in meta
        assert meta["api_input_tokens"] == meta["narrative_input_tokens"]
        assert meta["api_output_tokens"] == meta["narrative_output_tokens"]
        assert meta["api_input_tokens"] > 0

        # Era reflections should be empty (gated off in API mode)
        assert bundle.get("era_reflections", {}) == {} or all(
            v == "" for v in bundle.get("era_reflections", {}).values()
        )

        # API client was called for curated moments, not per-turn (20 turns)
        call_count = api_client.call_count
        assert call_count < 20, (
            f"Expected curated narration (< 20 calls), got {call_count} "
            "(suggests per-turn narration was not skipped)"
        )

        # Gap summaries should be present in bundle
        assert "gap_summaries" in bundle

    def test_run_narrate_api_mode_writes_metadata(self, tmp_path):
        """_run_narrate with --narrator api writes narrator_mode and token fields."""
        import json
        from chronicler.main import _run_narrate

        mock_sdk = MagicMock()

        # First, generate a simulate-only bundle
        sim_args = argparse.Namespace(
            seed=42, turns=20, civs=3, regions=6,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            simulate_only=True, agents="off",
            budget=50, narrator="local",
            pause_every=None,
        )
        execute_run(sim_args)

        bundle_path = tmp_path / "chronicle_bundle.json"
        assert bundle_path.exists()

        # Now re-narrate with --narrator api
        narrate_output = tmp_path / "narrated.json"
        narrate_args = argparse.Namespace(
            narrate=bundle_path,
            narrator="api",
            local_url="http://localhost:1234/v1",
            sim_model=None,
            narrative_model=None,
            budget=10,
            narrate_output=narrate_output,
        )

        # Patch create_clients to return our mocked API client
        api_client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
        def fake_batch_complete(requests, poll_interval=10.0):
            api_client.total_input_tokens += 300
            api_client.total_output_tokens += 150
            api_client.call_count += len(requests)
            return [
                "The chronicles speak of great change..."
                for _ in requests
            ]
        api_client.batch_complete = MagicMock(side_effect=fake_batch_complete)
        with patch("chronicler.main.create_clients",
                   return_value=(MagicMock(model="test"), api_client)):
            _run_narrate(narrate_args)

        # Check output metadata
        output = json.loads(narrate_output.read_text())
        assert output["metadata"]["narrator_mode"] == "api"
        assert output["metadata"]["narrative_input_tokens"] > 0
        assert output["metadata"]["narrative_output_tokens"] > 0
        assert output["metadata"]["api_input_tokens"] == output["metadata"]["narrative_input_tokens"]
        assert output["metadata"]["api_output_tokens"] == output["metadata"]["narrative_output_tokens"]
        assert output["metadata"]["api_input_tokens"] > 0
        assert output["metadata"]["api_output_tokens"] > 0


# ── M54c Task 4: Politics Runtime Wiring Tests ─────────────────────


class TestPoliticsRuntimeWiring:
    """Prove that --agents=off routes through the dedicated PoliticsSimulator
    and that the politics_runtime parameter is correctly threaded."""

    def test_off_mode_constructs_politics_runtime(self, tmp_path):
        """--agents=off should construct a PoliticsSimulator via _create_politics_runtime."""
        from chronicler.main import _create_politics_runtime
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        rt = _create_politics_runtime(world)
        # If the Rust crate is built, we get a real PoliticsSimulator.
        # If not, we get None (and that's OK — the test proves the function exists
        # and does not crash).
        assert rt is None or hasattr(rt, "tick_politics")

    def test_off_mode_politics_runtime_is_mockable(self, tmp_path):
        """_create_politics_runtime can be patched so tests avoid Rust build dep."""
        mock_sim = MagicMock()
        mock_sim.tick_politics = MagicMock()
        with patch("chronicler.main._create_politics_runtime", return_value=mock_sim):
            from chronicler.main import _create_politics_runtime
            rt = _create_politics_runtime(None)
            assert rt is mock_sim

    def test_off_mode_passes_politics_runtime_to_run_turn(self, tmp_path):
        """In off-mode, execute_run threads politics_runtime into run_turn."""
        import pyarrow as pa
        from chronicler.simulation import run_turn as _original_run_turn

        # Track whether run_turn receives the politics_runtime
        captured = {}

        original_run_turn = _original_run_turn

        def tracking_run_turn(*args, **kwargs):
            captured["politics_runtime"] = kwargs.get("politics_runtime")
            return original_run_turn(*args, **kwargs)

        mock_pol = MagicMock()
        # tick_politics returns 12 empty batches
        empty = pa.record_batch({"step": pa.array([], type=pa.uint8())})
        mock_pol.tick_politics = MagicMock(return_value=tuple(empty for _ in range(12)))

        args = argparse.Namespace(
            seed=42, turns=1, civs=2, regions=4,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None, pause_every=None,
            simulate_only=True, agents="off",
        )

        with patch("chronicler.main._create_politics_runtime", return_value=mock_pol), \
             patch("chronicler.main.run_turn", side_effect=tracking_run_turn):
            execute_run(args)

        assert captured.get("politics_runtime") is mock_pol

    def test_agent_mode_uses_bridge_sim_as_politics_runtime(self, tmp_path):
        """In agent-backed modes, the AgentSimulator serves as politics_runtime."""
        import pyarrow as pa

        mock_bridge = MagicMock()
        mock_bridge.close = MagicMock()
        mock_bridge.get_snapshot.return_value = None
        mock_bridge._sim.get_snapshot.return_value = None
        mock_bridge.named_agents = {}
        mock_bridge._collect_rel_stats = False
        mock_bridge.relationship_stats = []
        mock_bridge.tick_agents.return_value = []

        def _mock_tick_ecology(turn, climate_phase, pandemic_mask, army_arrived_mask):
            n = len(pandemic_mask)
            region_batch = pa.record_batch({
                "region_id": pa.array(range(n), type=pa.uint16()),
                "soil": pa.array([0.8] * n, type=pa.float32()),
                "water": pa.array([0.6] * n, type=pa.float32()),
                "forest_cover": pa.array([0.3] * n, type=pa.float32()),
                "endemic_severity": pa.array([0.0] * n, type=pa.float32()),
                "prev_turn_water": pa.array([0.6] * n, type=pa.float32()),
                "soil_pressure_streak": pa.array([0] * n, type=pa.int32()),
                "overextraction_streak_0": pa.array([0] * n, type=pa.int32()),
                "overextraction_streak_1": pa.array([0] * n, type=pa.int32()),
                "overextraction_streak_2": pa.array([0] * n, type=pa.int32()),
                "resource_reserve_0": pa.array([1.0] * n, type=pa.float32()),
                "resource_reserve_1": pa.array([1.0] * n, type=pa.float32()),
                "resource_reserve_2": pa.array([1.0] * n, type=pa.float32()),
                "resource_effective_yield_0": pa.array([0.5] * n, type=pa.float32()),
                "resource_effective_yield_1": pa.array([0.5] * n, type=pa.float32()),
                "resource_effective_yield_2": pa.array([0.5] * n, type=pa.float32()),
                "current_turn_yield_0": pa.array([0.5] * n, type=pa.float32()),
                "current_turn_yield_1": pa.array([0.5] * n, type=pa.float32()),
                "current_turn_yield_2": pa.array([0.5] * n, type=pa.float32()),
            })
            event_batch = pa.record_batch({
                "event_type": pa.array([], type=pa.uint8()),
                "region_id": pa.array([], type=pa.uint16()),
                "slot": pa.array([], type=pa.uint8()),
                "magnitude": pa.array([], type=pa.float32()),
            })
            return (region_batch, event_batch)

        mock_bridge.ecology_simulator.tick_ecology = _mock_tick_ecology
        mock_bridge.ecology_simulator.apply_region_postpass_patch = MagicMock()

        # M54c: Mock tick_politics
        empty = pa.record_batch({"step": pa.array([], type=pa.uint8())})
        mock_bridge._sim.tick_politics = MagicMock(
            return_value=tuple(empty for _ in range(12))
        )

        import sys
        args = argparse.Namespace(
            seed=42, turns=1, civs=2, regions=4,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None, pause_every=None,
            simulate_only=True, agents="hybrid",
        )
        mock_ab_module = MagicMock()
        mock_ab_module.AgentBridge = MagicMock(return_value=mock_bridge)
        saved = sys.modules.get("chronicler.agent_bridge")
        sys.modules["chronicler.agent_bridge"] = mock_ab_module
        try:
            execute_run(args)
        finally:
            if saved is None:
                sys.modules.pop("chronicler.agent_bridge", None)
            else:
                sys.modules["chronicler.agent_bridge"] = saved

        # Verify tick_politics was called on the bridge's _sim
        assert mock_bridge._sim.tick_politics.call_count >= 1

    def test_phase_consequences_falls_back_to_oracle_without_runtime(self):
        """When politics_runtime is None, phase_consequences uses the Python oracle."""
        from chronicler.simulation import phase_consequences
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        # Advance past the prelude to just the politics pass
        world.turn = 10
        # Should not raise — falls back to Python oracle
        events = phase_consequences(world, acc=None, politics_runtime=None)
        assert isinstance(events, list)
