"""Decision ablations: validation arms with one native decision term off.

``--decision-ablation NAME --ablation-start-turn T`` runs a seed exactly as
the plain run does until turn T, then switches one term of the native agent
decision off (``AgentSimulator.set_decision_ablation``,
``chronicler-agents/src/scale.rs``):

* ``needs``: the need modifiers of the rebel, migrate, switch and stay
  utilities and the autonomy factor of loyalty drift (needs still evolve);
* ``kin_roots``: the marriage and home-bond parts of a migrant's roots;
* ``placebo``: no term; the decision draws come from another random stream;
* ``community_anchor``: the community anchor (``--community-anchoring``,
  ``chronicler.community_anchoring``; a world without it has no anchor to
  switch off, and the arm is refused there).

The plain run and the arm share every turn before T, so the needs and
cohort oracles compare what the same agents do after T with and without
the term (docs/integration/ablation-oracles.md). The switch draws nothing
of its own; a run without it makes no native call it did not make before.
"""
from __future__ import annotations

from typing import Any

DECISION_ABLATIONS = ("needs", "kin_roots", "placebo", "community_anchor")


def decision_ablation_from_args(args: Any, agent_mode: str) -> tuple[str, int] | None:
    """``(name, start turn)`` from the CLI arguments, or None when the run
    ablates nothing. Both options or neither; an agent pool is required."""
    name = getattr(args, "decision_ablation", None)
    start = getattr(args, "ablation_start_turn", None)
    if name is None and start is None:
        return None
    if name is None:
        raise ValueError("--ablation-start-turn requires --decision-ablation")
    if start is None:
        raise ValueError("--decision-ablation requires --ablation-start-turn")
    if name not in DECISION_ABLATIONS:
        raise ValueError(f"--decision-ablation must be one of {DECISION_ABLATIONS}, got {name!r}")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError(f"--ablation-start-turn must be a turn (an integer >= 0), got {start!r}")
    if agent_mode == "off":
        raise ValueError("--decision-ablation requires an agent pool (--agents hybrid, shadow or demographics-only)")
    return name, start


def apply_decision_ablation(simulator: Any, ablation: tuple[str, int] | None) -> None:
    """Send the ablation to a native ``AgentSimulator``; nothing for None."""
    if ablation is None:
        return
    if not hasattr(simulator, "set_decision_ablation"):
        raise RuntimeError(
            "the installed chronicler_agents extension predates decision ablations; "
            "rebuild it to use --decision-ablation"
        )
    name, start = ablation
    simulator.set_decision_ablation([name], int(start))
