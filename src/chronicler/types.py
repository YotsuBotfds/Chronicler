"""Shared types for workflow modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunResult:
    """Aggregate stats from a single chronicle run.

    Fields are computed inside execute_run() and returned without
    the full WorldState to keep batch memory usage low.
    """
    seed: int
    output_dir: Path
    war_count: int
    collapse_count: int
    named_event_count: int
    distinct_action_count: int
    reflection_count: int
    tech_advancement_count: int
    max_stat_swing: float
    action_distribution: dict[str, dict[str, int]]
    dominant_faction: str
    total_turns: int
    boring_civs: list[str] = field(default_factory=list)
