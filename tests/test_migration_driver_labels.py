"""Migration drivers on agent migration events and the mass_migration summary.

The native decision records each migration's largest utility term (household
followers carry their lead's) in the ``migration_driver`` column of the agent
events; the bridge names it, puts the dominant one on ``mass_migration`` (and
each named character's ``notable_migration``) and words the description by it.
Files and extensions without the column read as recording no driver.
See docs/integration/navigation-famine-labels.md.
"""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from chronicler import agent_bridge
from chronicler import provenance as prov
from chronicler.models import (
    MIGRATION_DRIVER_NAMES,
    NO_MIGRATION_DRIVER,
    AgentEventRecord,
    Event,
    migration_driver_name,
)

ROOT = Path(__file__).resolve().parents[1]
CODE = {name: i for i, name in enumerate(MIGRATION_DRIVER_NAMES)}


def test_driver_names_follow_the_native_term_order():
    src = (ROOT / "chronicler-agents/src/migration_drivers.rs").read_text(encoding="utf-8")
    block = src[src.index("pub const MIGRATION_TERM_NAMES"):]
    block = block[:block.index("];")]
    assert tuple(re.findall(r'"([a-z_]+)"', block)) == MIGRATION_DRIVER_NAMES
    assert migration_driver_name(CODE["frontier"]) == "frontier"
    assert migration_driver_name(len(MIGRATION_DRIVER_NAMES)) is None  # decided with no positive term
    assert migration_driver_name(NO_MIGRATION_DRIVER) is None
    assert migration_driver_name(None) is None


def _migrations(region: int, target: int, drivers: list[int], turn: int = 3) -> list[AgentEventRecord]:
    return [AgentEventRecord(turn, 100 + i, "migration", region, target, 0, 0, migration_driver=d)
            for i, d in enumerate(drivers)]


def test_dominant_driver_is_the_most_common_label():
    f, h, w = CODE["frontier"], CODE["famine_memory"], CODE["wage"]
    assert agent_bridge.dominant_migration_driver(_migrations(0, 1, [f, f, h, h, h])) == "famine_memory"
    # Ties: the lower term index.
    assert agent_bridge.dominant_migration_driver(_migrations(0, 1, [w, w, f, f])) == "frontier"
    assert agent_bridge.dominant_migration_driver(_migrations(0, 1, [NO_MIGRATION_DRIVER] * 3)) is None
    assert agent_bridge.dominant_migration_driver(_migrations(0, 1, [len(MIGRATION_DRIVER_NAMES), h])) == "famine_memory"


def _bridge(events: list[AgentEventRecord]):
    bridge = agent_bridge.AgentBridge.__new__(agent_bridge.AgentBridge)
    bridge._sim = None
    bridge._event_window = deque([events], maxlen=20)
    return bridge


@pytest.mark.parametrize("driver, wording", [
    ("frontier", "left {src} to settle {dst}"),
    ("wage", "left {src} for work in {dst}"),
    ("chain", "followed kin from {src} to {dst}"),
    ("urban", "left {src} for the city in {dst}"),
    ("famine_memory", "fled hunger in {src} for {dst}"),
    ("persecution_memory", "fled persecution in {src} for {dst}"),
    ("battle_memory", "fled war in {src} for {dst}"),
    ("low_satisfaction", "left hardship in {src} for {dst}"),
    ("opp_capacity", "left {src} for better prospects in {dst}"),
])
def test_mass_migration_carries_and_words_its_driver(sample_world, driver, wording):
    src, dst = sample_world.regions[0].name, sample_world.regions[1].name
    events = _migrations(0, 1, [CODE[driver]] * 6 + [CODE["opp_news"]] * 2)
    out = [e for e in _bridge(events)._aggregate_events(sample_world, {}) if e.event_type == "mass_migration"]
    assert len(out) == 1
    ev = out[0]
    assert ev.driver == driver
    assert ev.description == f"8 farmers {wording.format(src=src, dst=dst)}"
    assert json.loads(ev.model_dump_json())["driver"] == driver


def test_mass_migration_without_drivers_reads_as_before(sample_world):
    src, dst = sample_world.regions[0].name, sample_world.regions[1].name
    events = _migrations(0, 1, [NO_MIGRATION_DRIVER] * 8)
    (ev,) = [e for e in _bridge(events)._aggregate_events(sample_world, {}) if e.event_type == "mass_migration"]
    assert ev.driver is None
    assert ev.description == f"8 farmers fled {src} for {dst}"
    assert "driver" not in json.loads(ev.model_dump_json())


class _Batch:
    """Duck-typed RecordBatch for the bridge's event conversion."""

    def __init__(self, columns: dict[str, list]):
        self._columns = columns
        self.num_rows = len(next(iter(columns.values())))
        self.schema = type("S", (), {"names": list(columns)})()

    def column(self, name):
        return pa.array(self._columns[name])


def _columns(extra: dict | None = None) -> dict[str, list]:
    cols = {"agent_id": [1, 2], "event_type": [2, 0], "region": [0, 0], "target_region": [1, 0],
            "civ_affinity": [0, 0], "occupation": [0, 0]}
    cols.update(extra or {})
    return cols


def test_event_conversion_reads_the_column_and_tolerates_its_absence():
    bridge = agent_bridge.AgentBridge.__new__(agent_bridge.AgentBridge)
    convert = agent_bridge.AgentBridge._convert_events
    with_column = convert(bridge, _Batch(_columns({"migration_driver": [CODE["chain"], NO_MIGRATION_DRIVER]})), 5)
    assert [e.migration_driver for e in with_column] == [CODE["chain"], NO_MIGRATION_DRIVER]
    without = convert(bridge, _Batch(_columns()), 5)
    assert [e.migration_driver for e in without] == [NO_MIGRATION_DRIVER] * 2


def test_agent_events_file_round_trip_and_old_files(tmp_path, sample_world):
    from chronicler.bundle import write_agent_events_arrow
    from chronicler.validation_io import _load_agent_events

    sample_world.agent_events_raw = _migrations(0, 1, [CODE["frontier"], NO_MIGRATION_DRIVER])
    path = write_agent_events_arrow(sample_world, tmp_path)
    table = ipc.open_file(path).read_all()
    assert table.column("migration_driver").to_pylist() == [CODE["frontier"], NO_MIGRATION_DRIVER]
    # A file written before the column still loads for the oracles.
    old = tmp_path / "old"
    old.mkdir()
    batch = pa.record_batch({k: v for k, v in table.to_pydict().items() if k != "migration_driver"})
    with pa.OSFile(str(old / "agent_events.arrow"), "wb") as fh:
        writer = ipc.new_file(fh, batch.schema)
        writer.write_batch(batch)
        writer.close()
    assert len(_load_agent_events(old)) == len(_load_agent_events(tmp_path)) == 2


def test_voluntary_moves_cite_no_distress(sample_world):
    region = sample_world.regions[0].name
    world = sample_world
    prov.begin_turn(world)
    famine = Event(turn=world.turn, event_type="famine", actors=[world.civilizations[0].name],
                   description="Famine", importance=8, region=region)
    prov.observe(world, [famine])
    settle = Event(turn=world.turn, event_type="mass_migration", actors=[], description="settle",
                   importance=5, source="agent", region=region, driver="frontier")
    flee = Event(turn=world.turn, event_type="mass_migration", actors=[], description="flee",
                 importance=5, source="agent", region=region, driver="famine_memory")
    assert prov.CAUSE_RULES["mass_migration"](world, settle) == []
    assert famine.event_id in prov.CAUSE_RULES["mass_migration"](world, flee)


def test_chroniclers_tell_a_settlement_wave_as_no_calamity():
    from chronicler import historiography as H

    settle = Event(turn=1, event_type="mass_migration", actors=["A"], description="", driver="frontier")
    flee = Event(turn=1, event_type="mass_migration", actors=["A"], description="", driver="persecution")
    older = Event(turn=1, event_type="mass_migration", actors=["A"], description="")
    assert H._stance(None, settle, "A") == ("neutral", None)
    assert H._stance(None, flee, "A") == ("disaster", None)
    assert H._stance(None, older, "A") == ("disaster", None)


@pytest.mark.native
def test_native_migrations_carry_their_drivers(tmp_path):
    pytest.importorskip("chronicler_agents")
    import chronicler.main as cli

    out = tmp_path / "run"
    args = cli._build_parser().parse_args([
        "--seed", "42", "--turns", "60", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only",
        "--output", str(out / "chronicle.md"), "--state", str(out / "state.json"),
    ])
    cli.execute_run(args)
    table = ipc.open_file(out / "agent_events.arrow").read_all().to_pydict()
    rows = list(zip(table["event_type"], table["migration_driver"]))
    moves = [code for kind, code in rows if kind == "migration"]
    assert moves and all(0 <= code <= len(MIGRATION_DRIVER_NAMES) for code in moves)
    assert all(code == NO_MIGRATION_DRIVER for kind, code in rows if kind != "migration")
    state = json.loads((out / "state.json").read_text())
    waves = [e for e in state["events_timeline"] if e["event_type"] == "mass_migration"]
    assert waves and all(e.get("driver") in MIGRATION_DRIVER_NAMES for e in waves)
