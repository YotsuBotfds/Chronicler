"""Test helper: the former ``chronicler.main.run_chronicle`` keyword API.

``run_chronicle`` was a legacy wrapper with no production caller; it was
removed from ``chronicler.main`` (DEAD-5a). The tests that drive whole runs
through its keyword arguments use this copy, which builds the same
``argparse.Namespace`` and delegates to ``execute_run``.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from chronicler.main import execute_run

if TYPE_CHECKING:
    from chronicler.llm import LLMClient
    from chronicler.scenario import ScenarioConfig


def run_chronicle(
    seed: int = 42,
    num_turns: int = 50,
    num_civs: int = 4,
    num_regions: int = 8,
    output_path: Path = Path("output/chronicle.md"),
    state_path: Path | None = None,
    sim_client: "LLMClient | None" = None,
    narrative_client: "LLMClient | None" = None,
    reflection_interval: int = 10,
    resume_path: Path | None = None,
    use_llm_actions: bool = False,
    scenario_config: "ScenarioConfig | None" = None,
) -> None:
    """Build the legacy argument namespace and delegate to ``execute_run``."""
    args = argparse.Namespace(
        seed=seed,
        turns=num_turns,
        civs=num_civs,
        regions=num_regions,
        output=str(output_path),
        state=str(state_path) if state_path else None,
        resume=str(resume_path) if resume_path else None,
        reflection_interval=reflection_interval,
        llm_actions=use_llm_actions,
        scenario=None,  # Pass scenario_config directly
        pause_every=None,
    )
    execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        scenario_config=scenario_config,
    )
