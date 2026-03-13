"""End-to-end smoke test — full pipeline with mocked LLM."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path
from chronicler.main import run_chronicle
from chronicler.models import WorldState


class TestEndToEnd:
    def _mock_llm(self, response: str):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_full_pipeline_20_turns(self, tmp_path):
        """Run 20 turns with mocked LLM clients and verify output."""
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm(
            "The merchants of the empire grew bolder, their ships venturing further along the sapphire coast."
        )

        output_path = tmp_path / "chronicle.md"
        state_path = tmp_path / "state.json"

        run_chronicle(
            seed=42,
            num_turns=20,
            num_civs=4,
            num_regions=8,
            output_path=output_path,
            state_path=state_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )

        # Verify chronicle file
        assert output_path.exists()
        content = output_path.read_text()
        assert "Chronicle of" in content
        assert len(content) > 500

        # Verify state file
        assert state_path.exists()
        world = WorldState.load(state_path)
        assert world.turn == 20
        assert len(world.events_timeline) > 0

        # Verify both clients were called
        # sim_client: action selection (4 civs * 20 turns = 80 calls)
        # narrative_client: chronicle (20 calls) + reflections (2 eras * 4 civs = 8 calls)
        assert sim_client.complete.call_count >= 80
        assert narrative_client.complete.call_count >= 20

    def test_output_contains_era_reflections(self, tmp_path):
        """With 20 turns and interval 10, should have era reflections."""
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("The Age of Growth dawned.")

        output_path = tmp_path / "chronicle.md"
        run_chronicle(
            seed=42,
            num_turns=20,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )

        content = output_path.read_text()
        assert "Era:" in content
