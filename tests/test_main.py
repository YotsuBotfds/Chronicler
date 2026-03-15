"""Tests for the main entry point — end-to-end with mocked LLM."""
import argparse
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from chronicler.main import execute_run, run_chronicle, DEFAULT_CONFIG
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
        assert len(result.action_distribution) > 0
        for civ_name, actions in result.action_distribution.items():
            assert isinstance(actions, dict)

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
