"""Tests for the main entry point — end-to-end with mocked LLM."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from chronicler.main import run_chronicle, DEFAULT_CONFIG


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
