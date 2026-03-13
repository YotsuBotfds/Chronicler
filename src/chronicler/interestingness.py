"""Interestingness scoring for chronicle runs."""
from __future__ import annotations

from chronicler.types import RunResult


DEFAULT_WEIGHTS: dict[str, float] = {
    "war_count": 3,
    "collapse_count": 5,
    "named_event_count": 1,
    "distinct_action_count": 1,
    "reflection_count": 2,
    "tech_advancement_count": 2,
    "max_stat_swing": 1,
}


def score_run(result: RunResult, weights: dict[str, float] | None = None) -> float:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    return (
        result.war_count * w["war_count"]
        + result.collapse_count * w["collapse_count"]
        + result.named_event_count * w["named_event_count"]
        + result.distinct_action_count * w["distinct_action_count"]
        + result.reflection_count * w["reflection_count"]
        + result.tech_advancement_count * w["tech_advancement_count"]
        + result.max_stat_swing * w["max_stat_swing"]
    )


def find_boring_civs(result: RunResult, threshold: float = 0.6) -> list[str]:
    boring = []
    for civ_name, actions in result.action_distribution.items():
        total = sum(actions.values())
        if total == 0:
            continue
        for action_type, count in actions.items():
            pct = count / total
            if pct > threshold:
                boring.append(f"{civ_name} ({action_type} {pct:.0%})")
                break
    return boring
