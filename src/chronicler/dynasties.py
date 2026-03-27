"""Dynasty detection, tracking, and event emission (M39).

Dynasties are detected when a promoted named character's parent is also
a promoted named character. Detection is O(1) per promotion via dict lookup.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chronicler.models import Event, GreatPerson


@dataclass
class Dynasty:
    dynasty_id: int
    founder_id: int
    founder_name: str
    civ_id: str
    members: list[int] = field(default_factory=list)
    founded_turn: int = 0
    split_detected: bool = False
    extinct: bool = False


class DynastyRegistry:
    def __init__(self) -> None:
        self.dynasties: list[Dynasty] = []
        self._next_id: int = 1

    def check_promotion(
        self,
        child: GreatPerson,
        named_agents: dict[int, str],
        gp_map: dict[int, GreatPerson],
    ) -> list[Event]:
        events: list[Event] = []

        # M57a: Resolve dynasty from both parents
        parent_0 = gp_map.get(child.parent_id_0) if child.parent_id_0 in named_agents else None
        parent_1 = gp_map.get(child.parent_id_1) if child.parent_id_1 in named_agents else None

        dynasty_0 = parent_0.dynasty_id if parent_0 else None
        dynasty_1 = parent_1.dynasty_id if parent_1 else None

        # Resolution rule (spec Section 3):
        # 1. Exactly one parent has a dynasty → child takes it
        # 2. Both share the same dynasty → child takes it
        # 3. Both have different dynasties → birth parent's; lineage_house records other
        # 4. Neither → founder logic (if parent is named but no dynasty yet)
        chosen_dynasty = None
        lineage_house = 0

        if dynasty_0 is not None and dynasty_1 is not None:
            if dynasty_0 == dynasty_1:
                chosen_dynasty = dynasty_0
            else:
                chosen_dynasty = dynasty_0  # birth parent's dynasty
                lineage_house = dynasty_1
        elif dynasty_0 is not None:
            chosen_dynasty = dynasty_0
        elif dynasty_1 is not None:
            chosen_dynasty = dynasty_1

        if chosen_dynasty is not None:
            dynasty = self._find(chosen_dynasty)
            dynasty.members.append(child.agent_id)
            child.dynasty_id = chosen_dynasty
            child.lineage_house = lineage_house
            return events

        # Rule 4: Neither parent has a dynasty — found a new one from first named parent
        founder_parent = parent_0 or parent_1
        if founder_parent is None:
            return events

        dynasty = Dynasty(
            dynasty_id=self._next_id,
            founder_id=founder_parent.agent_id,
            founder_name=founder_parent.name,
            civ_id=founder_parent.civilization,
            members=[founder_parent.agent_id, child.agent_id],
            founded_turn=child.born_turn,
        )
        self.dynasties.append(dynasty)
        founder_parent.dynasty_id = self._next_id
        child.dynasty_id = self._next_id
        self._next_id += 1

        events.append(Event(
            turn=child.born_turn,
            event_type="dynasty_founded",
            actors=[founder_parent.name, child.name],
            description=(
                f"The House of {founder_parent.name} is established as {child.name}, "
                f"child of the great {founder_parent.role} {founder_parent.name}, rises to prominence"
            ),
            importance=7,
            source="agent",
        ))
        return events

    def check_extinctions(self, gp_map: dict[int, GreatPerson], turn: int) -> list[Event]:
        events: list[Event] = []
        for dynasty in self.dynasties:
            if dynasty.extinct:
                continue
            if all(not gp_map[mid].alive for mid in dynasty.members):
                dynasty.extinct = True
                events.append(Event(
                    turn=turn,
                    event_type="dynasty_extinct",
                    actors=[dynasty.founder_name],
                    description=f"The House of {dynasty.founder_name} has ended — no heir remains",
                    importance=6,
                    source="agent",
                ))
        return events

    def check_splits(self, gp_map: dict[int, GreatPerson], turn: int) -> list[Event]:
        events: list[Event] = []
        for dynasty in self.dynasties:
            if dynasty.split_detected or dynasty.extinct:
                continue
            living_civs = {
                gp_map[mid].civilization
                for mid in dynasty.members
                if gp_map[mid].alive
            }
            if len(living_civs) > 1:
                dynasty.split_detected = True
                civs_str = " and ".join(sorted(living_civs))
                events.append(Event(
                    turn=turn,
                    event_type="dynasty_split",
                    actors=[dynasty.founder_name],
                    description=(
                        f"The House of {dynasty.founder_name} is divided — "
                        f"members serve {civs_str}"
                    ),
                    importance=5,
                    source="agent",
                ))
        return events

    def get_dynasty_for(self, agent_id: int, gp_map: dict[int, GreatPerson]) -> Dynasty | None:
        gp = gp_map.get(agent_id)
        if gp is None or gp.dynasty_id is None:
            return None
        return self._find(gp.dynasty_id)

    def _find(self, dynasty_id: int) -> Dynasty:
        for d in self.dynasties:
            if d.dynasty_id == dynasty_id:
                return d
        raise ValueError(f"Dynasty {dynasty_id} not found")


# ---------------------------------------------------------------------------
# Succession legitimacy scoring
# ---------------------------------------------------------------------------

LEGITIMACY_DIRECT_HEIR = 0.15   # [FROZEN M53 SOFT]
LEGITIMACY_SAME_DYNASTY = 0.08  # [FROZEN M53 SOFT]


def compute_dynasty_legitimacy(candidate: dict, civ) -> float:
    """Compute additive legitimacy bonus for a succession candidate.

    Scoped to the incumbent ruling line — only the current ruler's lineage
    matters, not any living dynasty.
    """
    ruler = civ.leader
    if ruler is None:
        return 0.0

    ruler_agent_id = getattr(ruler, "agent_id", None)
    ruler_dynasty_id = getattr(ruler, "dynasty_id", None)

    cand_parent_ids = (candidate.get("parent_id_0", 0), candidate.get("parent_id_1", 0))
    cand_dynasty_id = candidate.get("dynasty_id")

    # Direct heir: candidate's parent is the current ruler
    if ruler_agent_id is not None and ruler_agent_id != 0:
        if ruler_agent_id in cand_parent_ids and ruler_agent_id != 0:
            return LEGITIMACY_DIRECT_HEIR

    # Same dynasty
    if (
        ruler_dynasty_id is not None
        and cand_dynasty_id is not None
        and ruler_dynasty_id == cand_dynasty_id
    ):
        return LEGITIMACY_SAME_DYNASTY

    return 0.0
