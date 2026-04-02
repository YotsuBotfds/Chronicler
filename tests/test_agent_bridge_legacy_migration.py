"""Migrated legacy bridge regressions from the retired test/ tree."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pyarrow as pa

from chronicler.dynasties import DynastyRegistry
from chronicler.models import AgentEventRecord, GreatPerson


def _agent_bridge_class():
    added_stub = False
    if "chronicler_agents" not in sys.modules:
        sys.modules["chronicler_agents"] = MagicMock()
        added_stub = True
    from chronicler.agent_bridge import AgentBridge
    if added_stub:
        sys.modules.pop("chronicler_agents", None)
    return AgentBridge


def _make_bridge():
    AgentBridge = _agent_bridge_class()
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._origin_regions = {}
    bridge._departure_turns = {}
    bridge.gp_by_agent_id = {}
    bridge.dynasty_registry = DynastyRegistry()
    bridge._pending_dynasty_events = []
    bridge._sim = MagicMock()
    return bridge


def _make_region(name: str, controller: str | None = None):
    region = MagicMock()
    region.name = name
    region.controller = controller
    return region


def _make_promotion_batch(rows: list[dict]) -> pa.RecordBatch:
    if not rows:
        return pa.record_batch({
            "agent_id": pa.array([], type=pa.uint32()),
            "parent_id_0": pa.array([], type=pa.uint32()),
            "parent_id_1": pa.array([], type=pa.uint32()),
            "role": pa.array([], type=pa.uint8()),
            "trigger": pa.array([], type=pa.uint8()),
            "skill": pa.array([], type=pa.float32()),
            "life_events": pa.array([], type=pa.uint8()),
            "origin_region": pa.array([], type=pa.uint16()),
            "civ_id": pa.array([], type=pa.uint8()),
        })
    return pa.record_batch({
        "agent_id": pa.array([row["agent_id"] for row in rows], type=pa.uint32()),
        "parent_id_0": pa.array([row.get("parent_id_0", 0) for row in rows], type=pa.uint32()),
        "parent_id_1": pa.array([row.get("parent_id_1", 0) for row in rows], type=pa.uint32()),
        "role": pa.array([row["role"] for row in rows], type=pa.uint8()),
        "trigger": pa.array([row["trigger"] for row in rows], type=pa.uint8()),
        "skill": pa.array([row["skill"] for row in rows], type=pa.float32()),
        "life_events": pa.array([row["life_events"] for row in rows], type=pa.uint8()),
        "origin_region": pa.array([row["origin_region"] for row in rows], type=pa.uint16()),
        "civ_id": pa.array([row.get("civ_id", 0) for row in rows], type=pa.uint8()),
    })


def test_process_promotions_registers_named_agent_and_gp():
    bridge = _make_bridge()
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = []
    civ.prestige = 0
    civ.regions = []
    civ.capital_region = None
    world = MagicMock()
    world.turn = 100
    world.seed = 1
    world.civilizations = [civ]
    world.regions = [_make_region("Aram", controller="Aram")]
    world.agent_events_raw = []
    world._artifact_intents = []

    batch = _make_promotion_batch([
        {
            "agent_id": 42,
            "role": 0,
            "trigger": 1,
            "skill": 0.95,
            "life_events": 1,
            "origin_region": 0,
            "civ_id": 0,
        },
    ])

    with patch("chronicler.agent_bridge._pick_name", return_value="Kiran"), \
         patch("chronicler.agent_bridge.MULE_PROMOTION_PROBABILITY", 0.0):
        created = bridge._process_promotions(batch, world)

    assert len(created) == 1
    assert created[0].source == "agent"
    assert created[0].agent_id == 42
    assert created[0].name == "Kiran"
    assert bridge.named_agents[42] == "Kiran"
    assert bridge.gp_by_agent_id[42].name == "Kiran"


def test_process_deaths_marks_named_character_dead():
    bridge = _make_bridge()
    bridge.named_agents = {42: "Kiran"}

    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization="Aram",
        origin_civilization="Aram",
        born_turn=50,
        source="agent",
        agent_id=42,
    )
    bridge.gp_by_agent_id[42] = gp

    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = [gp]
    world = MagicMock()
    world.turn = 100
    world.civilizations = [civ]
    world.retired_persons = []
    world.regions = []

    events = bridge._process_deaths(
        [
            AgentEventRecord(
                turn=100,
                agent_id=42,
                event_type="death",
                region=0,
                target_region=0,
                civ_affinity=0,
                occupation=1,
            )
        ],
        world,
    )

    assert not gp.alive
    assert gp.fate == "dead"
    assert gp.death_turn == 100
    assert any(event.event_type == "character_death" for event in events)


def test_detect_character_events_emits_notable_migration_and_exile_return():
    bridge = _make_bridge()
    bridge.named_agents = {7: "Vesh", 42: "Kiran"}
    bridge._origin_regions = {7: 2, 42: 0}
    bridge._departure_turns = {7: 50}
    bridge.gp_by_agent_id = {}

    world = MagicMock()
    world.turn = 100
    world.regions = [
        _make_region("Bora"),
        _make_region("Aram"),
        _make_region("C"),
    ]

    events = bridge._detect_character_events(
        [
            AgentEventRecord(
                turn=100,
                agent_id=42,
                event_type="migration",
                region=0,
                target_region=1,
                civ_affinity=0,
                occupation=1,
            ),
            AgentEventRecord(
                turn=100,
                agent_id=7,
                event_type="migration",
                region=1,
                target_region=2,
                civ_affinity=0,
                occupation=3,
            ),
        ],
        world,
    )

    notable = [event for event in events if event.event_type == "notable_migration"]
    exile_returns = [event for event in events if event.event_type == "exile_return"]
    assert len(notable) == 1
    assert notable[0].actors == ["Kiran"]
    assert len(exile_returns) == 1
    assert exile_returns[0].actors == ["Vesh"]


def test_same_tick_promotion_then_migration_detects_named_character():
    bridge = _make_bridge()

    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = []
    civ.prestige = 0
    civ.regions = []
    civ.capital_region = None
    world = MagicMock()
    world.turn = 100
    world.seed = 1
    world.civilizations = [civ]
    world.regions = [
        _make_region("Bora", controller="Aram"),
        _make_region("Aram", controller="Aram"),
    ]
    world.agent_events_raw = []
    world._artifact_intents = []
    world.retired_persons = []

    batch = _make_promotion_batch([
        {
            "agent_id": 42,
            "role": 0,
            "trigger": 1,
            "skill": 0.95,
            "life_events": 3,
            "origin_region": 0,
            "civ_id": 0,
        },
    ])
    migration = AgentEventRecord(
        turn=100,
        agent_id=42,
        event_type="migration",
        region=0,
        target_region=1,
        civ_affinity=0,
        occupation=1,
    )

    with patch("chronicler.agent_bridge._pick_name", return_value="Kiran"), \
         patch("chronicler.agent_bridge.MULE_PROMOTION_PROBABILITY", 0.0):
        bridge._process_promotions(batch, world)

    events = bridge._detect_character_events([migration], world)

    assert any(event.event_type == "notable_migration" for event in events)
    assert "Kiran" in events[0].actors
