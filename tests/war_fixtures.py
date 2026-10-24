"""Shared builders for the tests/test_war_*.py suite (not a test module)."""
from __future__ import annotations

from chronicler.models import (
    Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
)

# Avalon - Brook - Crag - Dun - Edge, plus a Brook-Edge shortcut.
#   A holds Avalon (capital) and Brook; B holds Crag, Dun (capital) and Edge.
EDGES = [("Avalon", "Brook"), ("Brook", "Crag"), ("Crag", "Dun"), ("Dun", "Edge"), ("Brook", "Edge")]
TERRAIN = {"Avalon": "plains", "Brook": "plains", "Crag": "mountains", "Dun": "plains", "Edge": "forest"}


def make_region(name: str, controller: str | None, population: int) -> Region:
    return Region(name=name, terrain=TERRAIN.get(name, "plains"), carrying_capacity=100,
                  population=population, resources="fertile", controller=controller,
                  cultural_identity=controller)


def make_civ(name: str, regions: list[str], *, military: int, treasury: int, capital: str,
             era: TechEra = TechEra.IRON, trait: str = "cautious") -> Civilization:
    return Civilization(
        name=name, population=0, military=military, economy=40, culture=40, stability=60,
        tech_era=era, treasury=treasury,
        leader=Leader(name=f"Ruler of {name}", trait=trait, reign_start=0),
        regions=list(regions), asabiya=0.6, capital_region=capital,
    )


def war_world(*, seed: int = 7, campaigns: bool = True, pop_a: int = 60, pop_b: int = 40,
              mil_a: int = 60, mil_b: int = 30, treasury_a: int = 300, treasury_b: int = 150) -> WorldState:
    owners = {"Avalon": "A", "Brook": "A", "Crag": "B", "Dun": "B", "Edge": "B"}
    regions = []
    for name in ("Avalon", "Brook", "Crag", "Dun", "Edge"):
        owner = owners[name]
        regions.append(make_region(name, owner, pop_a if owner == "A" else pop_b))
    by_name = {r.name: r for r in regions}
    for a, b in EDGES:
        by_name[a].adjacencies.append(b)
        by_name[b].adjacencies.append(a)
    civs = [
        make_civ("A", ["Avalon", "Brook"], military=mil_a, treasury=treasury_a, capital="Avalon"),
        make_civ("B", ["Crag", "Dun", "Edge"], military=mil_b, treasury=treasury_b, capital="Dun"),
    ]
    for civ in civs:
        civ.population = sum(r.population for r in regions if r.controller == civ.name)
    rels = {"A": {"B": Relationship(disposition=Disposition.HOSTILE)},
            "B": {"A": Relationship(disposition=Disposition.HOSTILE)}}
    world = WorldState(name="WarWorld", seed=seed, turn=0, regions=regions, civilizations=civs,
                       relationships=rels)
    world.campaigns_enabled = campaigns
    return world


def start_war(world: WorldState, attacker: str = "A", defender: str = "B"):
    """Open a war through the campaign layer without raising armies."""
    from chronicler.war.common import build_context
    from chronicler.war.peace import open_war, war_key
    world.active_wars.append((attacker, defender))
    world.war_start_turns[war_key(attacker, defender)] = world.turn
    ctx = build_context(world)
    return ctx, open_war(ctx, world.civ_map[attacker], world.civ_map[defender])


def place_army(world: WorldState, civ: str, region: str, soldiers: int, war_key: str, *,
               morale: int = 700, phase: str = "marching", roster=None, general: str | None = None):
    from chronicler.models import Army
    from chronicler.war.params import POLICY
    serial = world.war_state.next_army_serial
    world.war_state.next_army_serial += 1
    army = Army(army_id=f"army-{serial}", name=f"Army {serial} of {civ}", civ=civ, war_key=war_key,
                region=region, home_region=region, soldiers=soldiers, raised=soldiers, morale=morale,
                rations=soldiers * POLICY.carried_limit, phase=phase, roster=list(roster or []),
                general=general)
    world.war_state.armies.append(army)
    return army


class FakeSnapshot:
    """Minimal Arrow-like batch with the four columns enlistment reads."""

    def __init__(self, rows):
        self.rows = list(rows)  # (id, region, occupation, civ_affinity)
        self.num_rows = len(self.rows)

    def column(self, name):
        idx = {"id": 0, "region": 1, "occupation": 2, "civ_affinity": 3}[name]

        class _Col:
            def __init__(self, values):
                self._values = values

            def to_pylist(self):
                return list(self._values)

        return _Col([row[idx] for row in self.rows])


class FakeSim:
    def __init__(self):
        self.queued: list[int] = []

    def queue_targeted_deaths(self, ids):
        self.queued.extend(ids)


class FakeBridge:
    """Stands in for AgentBridge: snapshot reads and targeted-death queueing."""

    def __init__(self, rows):
        self._sim = FakeSim()
        self.snapshot = FakeSnapshot(rows)
        self.named_agents: dict[int, str] = {}

    def get_snapshot(self):
        return self.snapshot
