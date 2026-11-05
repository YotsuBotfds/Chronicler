"""RS1 apprenticeship and skill continuity (``--apprenticeship``, default off).

Recovery-skills groundwork (RS0): the switch, its mode and inert stubs of the
livelihoods package protocol (:mod:`chronicler.livelihoods`) and of the
cross-lane API. Enabling it records the switch and nothing else: no phase
hook exists yet, no person, money, skill or asset changes. The RS1 lane fills
in the mechanism of the phase plan
(``docs/superpowers/roadmaps/recovery-skills-phase.md``, RS1).

Requires ``--workshops`` in ``operate`` mode and ``--agents hybrid``. Modes
(``--apprenticeship-mode``): ``train`` (default) and the cost-retaining
control ``no_qualification``.

RS0 seams (stable signatures, inert bodies):

* :func:`qualified_ids`: the workshop-qualified stable ids present in a
  region, for RS2 repair crews; ``[]`` until RS1.
* :func:`before_crews`: :mod:`chronicler.workshops` calls it before the
  native crew planner while this switch is active (apprenticeship seats are
  reserved first); a no-op.
* :func:`operating_wear`: the wear of a funded operating workshop site this
  turn, which :mod:`chronicler.workshops` applies while this switch is
  active; ``0.0`` (condition untouched).
"""
from __future__ import annotations

from chronicler.apprenticeship_state import MODES, ApprenticeshipState


def _state(world) -> ApprenticeshipState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "apprenticeship", None) if container is not None else None


def set_apprenticeship_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--apprenticeship-mode``, default ``train``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "apprenticeship_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.apprenticeship = state = ApprenticeshipState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def apprenticeship_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.workshops import workshops_active
    return workshops_active(world) and world.livelihoods.workshops.mode == "operate"


def snapshot_summary(world) -> dict:
    """The completed-turn observation (RS0: the switch only; never final state)."""
    state = _state(world)
    return {"schema_version": 1, "stage": "RS0", "enabled": state.enabled, "mode": state.mode,
            "counters": dict(state.counters)}


# ---------------------------------------------------------------------------
# RS0 cross-lane seams (inert until the RS1 lane)
# ---------------------------------------------------------------------------

def qualified_ids(world, region: int) -> list[int]:
    """RS0 seam: stable ids holding a workshop qualification, alive and present
    in ``region`` (an index in ``world.regions``), ascending. RS0 stub: ``[]``."""
    return []


def before_crews(world, sim, requests: list) -> None:
    """RS0 seam: called by :func:`chronicler.workshops.prepare_phase2` before
    the native crew planner while this switch is active, with the native
    simulator and the turn's site requests ``(site, region, settlement,
    diverted fraction, max workers)``. RS0 stub: a no-op."""
    return None


def operating_wear(world, site) -> float:
    """RS0 seam: this turn's net wear (in [0, 1]) of the funded operating
    workshop ``site`` (a :class:`chronicler.workshops_state.WorkshopSite`),
    applied by :mod:`chronicler.workshops` at settlement while this switch is
    active. RS0 stub: ``0.0`` (condition untouched)."""
    return 0.0
