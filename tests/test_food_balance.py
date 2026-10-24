"""Food-balance corrections (2026-10): see docs/integration/food-balance-2026-10.md.

Each test pins one correction: aggregate migration is a no-op for agent-owned
populations.
"""
from __future__ import annotations

import pytest

from chronicler.climate import process_migration
from chronicler.models import (
    Civilization,
    Disposition,
    Leader,
    Region,
    Relationship,
    WorldState,
)


def _civ(name: str, regions: list[str], population: int = 40) -> Civilization:
    return Civilization(
        name=name, population=population, military=30, economy=40, culture=30,
        stability=50, treasury=100, regions=regions,
        leader=Leader(name=f"{name} I", trait="cautious", reign_start=0),
    )


def _overflow_world(agent_mode: str | None) -> WorldState:
    src = Region(name="A", terrain="desert", carrying_capacity=20, resources="mineral",
                 controller="Rome", adjacencies=["B"], population=40)
    dst = Region(name="B", terrain="plains", carrying_capacity=80, resources="fertile",
                 controller="Greece", adjacencies=["A"], population=30)
    rels = {
        "Rome": {"Greece": Relationship(disposition=Disposition.NEUTRAL)},
        "Greece": {"Rome": Relationship(disposition=Disposition.NEUTRAL)},
    }
    world = WorldState(name="T", seed=42, regions=[src, dst],
                       civilizations=[_civ("Rome", ["A"]), _civ("Greece", ["B"], 30)],
                       relationships=rels)
    world.agent_mode = agent_mode
    return world


# --- aggregate migration ------------------------------------------------------

@pytest.mark.parametrize("mode", ["hybrid", "demographics-only"])
def test_overflow_migration_is_noop_for_agent_owned_populations(mode):
    world = _overflow_world(mode)
    before = ([r.population for r in world.regions],
              [(c.population, c.stability) for c in world.civilizations])
    assert process_migration(world) == []
    after = ([r.population for r in world.regions],
             [(c.population, c.stability) for c in world.civilizations])
    assert after == before


@pytest.mark.parametrize("mode", [None, "off", "shadow"])
def test_overflow_migration_still_moves_python_owned_populations(mode):
    world = _overflow_world(mode)
    events = process_migration(world)
    assert [e.event_type for e in events] == ["migration"]
    assert world.regions[0].population < 40
    assert world.regions[1].population > 30
