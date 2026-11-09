"""Golden ``StatAccumulator`` trace for the turn-loop consolidation (CON-3).

Records every :meth:`StatAccumulator.add` of a short ``--agents off`` run as
``["add", turn, civ_id, stat, delta, category, stat_at_time]`` and, after each
turn, ``["end", turn, [[name, *TRACE_STATS] per civ]]``. The fixture was
recorded before the treasury seam existed; every later treasury refactor must
reproduce it unchanged (add order, deltas, routing categories, the
``stat_at_time`` the accumulator captured, and the direct writes of the
off-mode Phase 10 through the end-of-turn stats).

Off mode only: Phases 1-9 record into the accumulator and Phase 10 writes
directly (``phase10_acc is None``), so both treasury branches are covered.
The hybrid accumulator path needs the native extension and is covered by the
identity gate instead.

Regenerate (only on an intended correction, never to make a refactor pass)::

    .venv/bin/python tests/support/accumulator_trace.py --write
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/turn_loop/accumulator_trace.json"
SCHEMA_VERSION = 1
TURNS = 12
SEEDS = (1, 2, 3)
TRACE_STATS = ("population", "military", "economy", "culture", "stability",
               "treasury", "prestige", "asabiya")
# (name, world builder, techniques): the conftest ``sample_world`` (two
# civilizations, five regions) and a generated world (four civilizations,
# eight regions), each without and with the techniques state the CLI enables
# by default for new worlds.
CASES = (
    ("sample", False),
    ("sample", True),
    ("generated", False),
    ("generated", True),
)


def sample_world(seed: int):
    """The conftest ``sample_world`` fixture, rebuilt here (fixtures cannot be
    called outside pytest) with ``seed`` as the world seed."""
    from chronicler.models import (
        Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
    )
    regions = [
        Region(name="Verdant Plains", terrain="plains", carrying_capacity=80, resources="fertile", controller="Kethani Empire"),
        Region(name="Iron Peaks", terrain="mountains", carrying_capacity=40, resources="mineral", controller="Dorrathi Clans"),
        Region(name="Sapphire Coast", terrain="coast", carrying_capacity=60, resources="maritime", controller="Kethani Empire"),
        Region(name="Thornwood", terrain="forest", carrying_capacity=50, resources="timber"),
        Region(name="Ashara Desert", terrain="desert", carrying_capacity=30, resources="barren"),
    ]
    civilizations = [
        Civilization(
            name="Kethani Empire", population=70, military=50, economy=80, culture=60, stability=60,
            tech_era=TechEra.IRON, treasury=120,
            leader=Leader(name="Empress Vaelith", trait="calculating", reign_start=0),
            domains=["maritime", "commerce"], values=["Trade", "Order"],
            goal="Expand trade networks to all coastal regions",
            regions=["Verdant Plains", "Sapphire Coast"], asabiya=0.6,
        ),
        Civilization(
            name="Dorrathi Clans", population=40, military=70, economy=30, culture=50, stability=40,
            tech_era=TechEra.IRON, treasury=50,
            leader=Leader(name="Warchief Gorath", trait="aggressive", reign_start=0),
            domains=["mountain", "warfare"], values=["Honor", "Strength"],
            goal="Conquer the Verdant Plains", regions=["Iron Peaks"], asabiya=0.8,
        ),
    ]
    relationships = {
        "Kethani Empire": {"Dorrathi Clans": Relationship(
            disposition=Disposition.SUSPICIOUS,
            grievances=["Border raids in the northern foothills"], trade_volume=2)},
        "Dorrathi Clans": {"Kethani Empire": Relationship(
            disposition=Disposition.HOSTILE,
            grievances=["Kethani merchants exploit mountain resources"], trade_volume=2)},
    }
    return WorldState(
        name="Testworld", seed=seed, turn=0, regions=regions, civilizations=civilizations,
        relationships=relationships, events_timeline=[], active_conditions=[],
        event_probabilities={
            "drought": 0.05, "plague": 0.03, "earthquake": 0.02, "religious_movement": 0.04,
            "discovery": 0.06, "leader_death": 0.03, "rebellion": 0.05, "migration": 0.04,
            "cultural_renaissance": 0.03, "border_incident": 0.08,
        },
    )


def build_world(kind: str, seed: int, techniques: bool):
    if kind == "sample":
        world = sample_world(seed)
    elif kind == "generated":
        from chronicler.world_gen import generate_world
        world = generate_world(seed=seed)
    else:
        raise ValueError(kind)
    if techniques:
        from chronicler.techniques import set_techniques_enabled
        set_techniques_enabled(world, True)
    return world


def _end_row(world) -> list:
    return [[civ.name, *(getattr(civ, stat) for stat in TRACE_STATS)] for civ in world.civilizations]


def trace_run(world, seed: int, turns: int = TURNS) -> list:
    """Run ``turns`` off-mode turns as ``main`` does (a fresh ``ActionEngine``
    per turn, run seed ``seed + turn``) and return the trace records."""
    from chronicler import simulation as sim
    from chronicler.accumulator import StatAccumulator
    from chronicler.action_engine import ActionEngine

    records: list = []
    original = StatAccumulator.add

    def add(self, civ_idx, civ, stat, delta, category):
        original(self, civ_idx, civ, stat, delta, category)
        change = self._changes[-1]
        records.append(["add", world.turn, change.civ_id, change.stat, change.delta,
                        change.category, change.stat_at_time])

    StatAccumulator.add = add
    try:
        for offset in range(turns):
            engine = ActionEngine(world)
            sim.run_turn_result(
                world,
                lambda civ, current, _engine=engine: _engine.select_action(civ, seed=current.seed),
                lambda *_: "",
                seed=seed + offset,
            )
            records.append(["end", world.turn - 1, _end_row(world)])
    finally:
        StatAccumulator.add = original
    return records


def record() -> dict:
    """The full golden document (JSON-normalized)."""
    cases = {}
    for kind, techniques in CASES:
        for seed in SEEDS:
            name = f"{kind}_s{seed}" + ("_techniques" if techniques else "")
            cases[name] = trace_run(build_world(kind, seed, techniques), seed)
    document = {
        "schema_version": SCHEMA_VERSION,
        "turns": TURNS,
        "stats": list(TRACE_STATS),
        "record": "tests/support/accumulator_trace.py",
        "cases": cases,
    }
    return json.loads(json.dumps(document))


def dumps(document: dict) -> str:
    """One record per line, so a difference names its turn and change."""
    lines = ["{", f'  "schema_version": {document["schema_version"]},',
             f'  "turns": {document["turns"]},',
             f'  "stats": {json.dumps(document["stats"])},',
             f'  "record": {json.dumps(document["record"])},', '  "cases": {']
    names = list(document["cases"])
    for index, name in enumerate(names):
        rows = document["cases"][name]
        lines.append(f"    {json.dumps(name)}: [")
        lines.extend(f"      {json.dumps(row)}" + ("," if i < len(rows) - 1 else "")
                     for i, row in enumerate(rows))
        lines.append("    ]" + ("," if index < len(names) - 1 else ""))
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: accumulator_trace.py --write")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(dumps(record()), encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
