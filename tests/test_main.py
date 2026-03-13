"""Tests for the main entry point — end-to-end with mocked LLM."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from chronicler.main import run_chronicle, DEFAULT_CONFIG


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
