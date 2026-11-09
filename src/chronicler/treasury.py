"""One seam for civilization treasury flows (turn-loop consolidation, CON-3).

:func:`treasury_delta` replaces the dual path that treasury writers spell out
by hand::

    if acc is not None:
        acc.add(civ_index(world, civ.name), civ, "treasury", delta, "keep")
    else:
        civ.treasury += delta          # or max(0, civ.treasury + delta)

with the same arithmetic in both branches. The accumulator branch is
unchanged (same index, same ``stat_at_time``, same list position), so a
caller that switches to the seam changes no outcome. It never skips a zero
delta: the accumulator's change list is index-addressed (watermarks,
checkpoints, tail slices). Stat-neutral callers keep their own guards.

``reason`` labels the flow for an inventory (:data:`TREASURY_REASONS`); it
has no runtime effect. No call site uses the seam yet: sites migrate in later
reviewed steps, each adding its reason.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.accumulator import StatAccumulator
    from chronicler.models import Civilization, WorldState

# How a reason moves money: "fiat" creates it, "sink" destroys it, "transfer"
# moves it between holders, "restore" puts back a recorded value.
TREASURY_REASON_KINDS = ("fiat", "sink", "transfer", "restore")

# reason -> one of TREASURY_REASON_KINDS. Filled as call sites migrate.
TREASURY_REASONS: dict[str, str] = {}


def treasury_delta(world: "WorldState", acc: "StatAccumulator | None", civ: "Civilization",
                   delta, *, reason: str, civ_idx: int | None = None,
                   floor0: bool = False) -> None:
    """Change ``civ.treasury`` by ``delta`` as a ``keep`` accumulator change,
    or directly when ``acc`` is None.

    ``civ_idx``: the civ's index when the caller already has it; otherwise it
    is looked up by name, only on the accumulator branch (a direct write never
    needs it). ``floor0``: the direct branch floors at zero, for the sites
    whose direct write spells ``max(0, ...)``; the accumulator always floors
    when it applies the change.
    """
    if acc is not None:
        if civ_idx is None:
            from chronicler.utils import civ_index
            civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "treasury", delta, "keep")
    elif floor0:
        civ.treasury = max(0, civ.treasury + delta)
    else:
        civ.treasury += delta
