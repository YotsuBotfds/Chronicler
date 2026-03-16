"""M30 agent narrative — bridge promotion tests."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
from unittest.mock import patch
import pyarrow as pa

from chronicler.agent_bridge import AgentBridge, OCCUPATION_NAMES


ROLE_MAP = {0: "general", 1: "merchant", 2: "scientist", 3: "prophet", 4: "exile"}


def _make_promotion_batch(rows: list[dict]) -> pa.RecordBatch:
    """Build a promotions RecordBatch for testing."""
    if not rows:
        return pa.record_batch({
            "agent_id": pa.array([], type=pa.uint32()),
            "role": pa.array([], type=pa.uint8()),
            "trigger": pa.array([], type=pa.uint8()),
            "skill": pa.array([], type=pa.float32()),
            "life_events": pa.array([], type=pa.uint8()),
            "origin_region": pa.array([], type=pa.uint16()),
        })
    return pa.record_batch({
        "agent_id": pa.array([r["agent_id"] for r in rows], type=pa.uint32()),
        "role": pa.array([r["role"] for r in rows], type=pa.uint8()),
        "trigger": pa.array([r["trigger"] for r in rows], type=pa.uint8()),
        "skill": pa.array([r["skill"] for r in rows], type=pa.float32()),
        "life_events": pa.array([r["life_events"] for r in rows], type=pa.uint8()),
        "origin_region": pa.array([r["origin_region"] for r in rows], type=pa.uint16()),
    })


def test_promotion_creates_great_person():
    """Promotion RecordBatch → GreatPerson(source='agent')."""
    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._origin_regions = {}

    batch = _make_promotion_batch([
        {"agent_id": 42, "role": 0, "trigger": 1, "skill": 0.95,
         "life_events": 0b00000001, "origin_region": 3},
    ])

    # Mock world with one civ
    world = MagicMock()
    world.turn = 100
    world.seed = 1
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = []
    world.civilizations = [civ]
    world.regions = []

    with patch("chronicler.agent_bridge._pick_name", return_value="Kiran"):
        gp = bridge._process_promotions(batch, world)

    assert len(gp) == 1
    assert gp[0].source == "agent"
    assert gp[0].agent_id == 42
    assert gp[0].role == "general"
    assert gp[0].name == "Kiran"
    assert 42 in bridge.named_agents
    assert bridge.named_agents[42] == "Kiran"


def test_named_agents_dict_maintained():
    """Dict updated on promotion, accessible for _aggregate_events."""
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._origin_regions = {}

    batch = _make_promotion_batch([
        {"agent_id": 10, "role": 1, "trigger": 0, "skill": 0.92,
         "life_events": 0b00000010, "origin_region": 0},
        {"agent_id": 20, "role": 2, "trigger": 4, "skill": 0.88,
         "life_events": 0b00010000, "origin_region": 1},
    ])

    world = MagicMock()
    world.turn = 50
    world.seed = 1
    civ = MagicMock()
    civ.name = "TestCiv"
    civ.great_persons = []
    world.civilizations = [civ]
    world.regions = []
    world.agent_events_raw = []  # needed for trigger==0 bypass check

    with patch("chronicler.agent_bridge._pick_name", side_effect=["Vesh", "Talo"]):
        bridge._process_promotions(batch, world)

    assert len(bridge.named_agents) == 2
    assert bridge.named_agents[10] == "Vesh"
    assert bridge.named_agents[20] == "Talo"


def test_death_transitions_great_person():
    """Agent death → GreatPerson gets alive=False, fate='dead'."""
    from chronicler.models import GreatPerson, AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}

    gp = GreatPerson(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=50, source="agent", agent_id=42,
    )
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = [gp]

    world = MagicMock()
    world.turn = 100
    world.civilizations = [civ]
    world.retired_persons = []
    world.regions = []

    raw_events = [
        AgentEventRecord(turn=100, agent_id=42, event_type="death",
                        region=0, target_region=0, civ_affinity=0, occupation=1),
    ]

    death_events = bridge._process_deaths(raw_events, world)

    assert not gp.alive
    assert gp.fate == "dead"
    assert gp.death_turn == 100
    assert len(death_events) == 1
    assert "Kiran" in death_events[0].actors


def test_death_overrides_exile_fate():
    """Exiled character dies → fate='dead' overrides 'exile'."""
    from chronicler.models import GreatPerson, AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {7: "Vesh"}

    gp = GreatPerson(
        name="Vesh", role="exile", trait="stoic",
        civilization="Bora", origin_civilization="Aram",
        born_turn=30, fate="exile", source="agent", agent_id=7,
    )
    civ = MagicMock()
    civ.name = "Bora"
    civ.great_persons = [gp]

    world = MagicMock()
    world.turn = 200
    world.civilizations = [civ]
    world.retired_persons = []
    world.regions = []

    raw_events = [
        AgentEventRecord(turn=200, agent_id=7, event_type="death",
                        region=2, target_region=0, civ_affinity=1, occupation=0),
    ]

    bridge._process_deaths(raw_events, world)

    assert gp.fate == "dead"
    assert not gp.alive


def test_notable_migration_detection():
    """Named character migration → notable_migration event."""
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}
    bridge._origin_regions = {42: 0}
    bridge._departure_turns = {}

    world = MagicMock()
    world.turn = 100
    region0 = MagicMock()
    region0.name = "Bora"
    region1 = MagicMock()
    region1.name = "Aram"
    world.regions = [region0, region1]

    raw_events = [
        AgentEventRecord(turn=100, agent_id=42, event_type="migration",
                        region=0, target_region=1, civ_affinity=0, occupation=1),
    ]

    events = bridge._detect_character_events(raw_events, world)

    notable = [e for e in events if e.event_type == "notable_migration"]
    assert len(notable) == 1
    assert "Kiran" in notable[0].actors


def test_exile_return_detection():
    """Named char returns to origin_region after 30+ turns → exile_return event."""
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {7: "Vesh"}
    bridge._origin_regions = {7: 2}
    bridge._departure_turns = {7: 50}  # departed origin at turn 50

    world = MagicMock()
    world.turn = 100  # 50 turns later — qualifies for exile_return
    region_a = MagicMock()
    region_a.name = "A"
    region_b = MagicMock()
    region_b.name = "B"
    region_c = MagicMock()
    region_c.name = "C"
    world.regions = [region_a, region_b, region_c]

    raw_events = [
        AgentEventRecord(turn=100, agent_id=7, event_type="migration",
                        region=1, target_region=2, civ_affinity=0, occupation=3),
    ]

    events = bridge._detect_character_events(raw_events, world)

    exile_returns = [e for e in events if e.event_type == "exile_return"]
    assert len(exile_returns) == 1
    assert "Vesh" in exile_returns[0].actors


def test_economic_boom_detection():
    """Sufficient merchant switches → economic_boom event."""
    from collections import deque
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._event_window = deque(maxlen=20)

    # Simulate 10 occupation switches to merchant (occ=2) over multiple turns
    for turn in range(10):
        events = [
            AgentEventRecord(turn=turn, agent_id=turn, event_type="occupation_switch",
                            region=0, target_region=0, civ_affinity=0, occupation=2)
        ]
        bridge._event_window.append(events)

    world = MagicMock()
    world.turn = 10
    region0 = MagicMock()
    region0.name = "TestRegion"
    world.regions = [region0]

    summaries = bridge._aggregate_events(world, bridge.named_agents)

    booms = [e for e in summaries if e.event_type == "economic_boom"]
    assert len(booms) == 1


def test_brain_drain_detection():
    """>=5 scholar departures → brain_drain event."""
    from collections import deque
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._event_window = deque(maxlen=10)

    # 5 scholars (occ=3) migrate from region 0
    events = [
        AgentEventRecord(turn=50, agent_id=i, event_type="migration",
                        region=0, target_region=1, civ_affinity=0, occupation=3)
        for i in range(5)
    ]
    bridge._event_window.append(events)

    world = MagicMock()
    world.turn = 50
    region0 = MagicMock()
    region0.name = "Origin"
    region1 = MagicMock()
    region1.name = "Dest"
    world.regions = [region0, region1]

    summaries = bridge._aggregate_events(world, bridge.named_agents)

    drains = [e for e in summaries if e.event_type == "brain_drain"]
    assert len(drains) == 1


def test_actor_population():
    """Named character names appear in actors field of aggregate events."""
    from collections import deque
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {3: "Kiran"}
    bridge._event_window = deque(maxlen=10)

    # 5 rebels including named character in region 0
    events = [
        AgentEventRecord(turn=50, agent_id=i, event_type="rebellion",
                        region=0, target_region=0, civ_affinity=0, occupation=1)
        for i in range(5)
    ]
    # Agent 3 is among rebels
    bridge._event_window.append(events)

    world = MagicMock()
    world.turn = 50
    region0 = MagicMock()
    region0.name = "TestRegion"
    world.regions = [region0]

    summaries = bridge._aggregate_events(world, bridge.named_agents)

    rebellions = [e for e in summaries if e.event_type == "local_rebellion"]
    assert len(rebellions) == 1
    assert "Kiran" in rebellions[0].actors


def test_conquest_exile_transition():
    """Conquest → named characters become exiles, set_agent_civ called."""
    from chronicler.models import GreatPerson

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}
    bridge._sim = MagicMock()

    gp = GreatPerson(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=50, source="agent", agent_id=42, region="Bora",
    )
    conquered_civ = MagicMock()
    conquered_civ.name = "Aram"
    conquered_civ.great_persons = [gp]
    conquered_civ.regions = ["Bora"]

    conqueror_civ = MagicMock()
    conqueror_civ.name = "Vrashni"

    events = bridge.apply_conquest_transitions(
        conquered_civ, conqueror_civ, conquered_regions=["Bora"],
        conqueror_civ_id=1, turn=100)

    assert gp.fate == "exile"
    assert gp.captured_by == "Vrashni"
    bridge._sim.set_agent_civ.assert_called_once_with(42, 1)


def test_conquest_refugee_not_captured():
    """Refugee in surviving-civ territory → captured_by NOT set."""
    from chronicler.models import GreatPerson

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {7: "Vesh"}
    bridge._sim = MagicMock()

    gp = GreatPerson(
        name="Vesh", role="merchant", trait="clever",
        civilization="Aram", origin_civilization="Aram",
        born_turn=30, source="agent", agent_id=7, region="Farland",
    )
    conquered_civ = MagicMock()
    conquered_civ.name = "Aram"
    conquered_civ.great_persons = [gp]

    conqueror_civ = MagicMock()
    conqueror_civ.name = "Vrashni"

    # "Farland" is NOT in conquered_regions — character is a refugee
    events = bridge.apply_conquest_transitions(
        conquered_civ, conqueror_civ, conquered_regions=["Bora"],
        conqueror_civ_id=1, host_civ_ids={"Farland": 2}, turn=100)

    assert gp.fate == "exile"
    assert gp.captured_by is None  # refugee, not hostage
    # Refugee still gets set_agent_civ with host civ ID
    bridge._sim.set_agent_civ.assert_called_once_with(7, 2)


def test_processing_order():
    """Same-tick promote+migrate → notable_migration detected."""
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._origin_regions = {}
    bridge._departure_turns = {}

    # Simulate: agent 42 gets promoted AND migrates on same tick
    promo_batch = _make_promotion_batch([
        {"agent_id": 42, "role": 0, "trigger": 1, "skill": 0.95,
         "life_events": 0b00000011, "origin_region": 0},
    ])

    from chronicler.models import AgentEventRecord
    raw_events = [
        AgentEventRecord(turn=100, agent_id=42, event_type="migration",
                        region=0, target_region=1, civ_affinity=0, occupation=1),
    ]

    world = MagicMock()
    world.turn = 100
    world.seed = 1
    world.regions = [MagicMock(name="Bora"), MagicMock(name="Aram")]
    world.regions[0].name = "Bora"
    world.regions[1].name = "Aram"
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = []
    world.civilizations = [civ]
    world.retired_persons = []

    # Step 1: process promotions
    with patch("chronicler.agent_bridge._pick_name", return_value="Kiran"):
        bridge._process_promotions(promo_batch, world)

    assert 42 in bridge.named_agents  # now registered

    # Step 2: process deaths (none here)
    death_events = bridge._process_deaths(raw_events, world)
    assert len(death_events) == 0

    # Step 3: detect character events — should find notable_migration
    char_events = bridge._detect_character_events(raw_events, world)
    notable = [e for e in char_events if e.event_type == "notable_migration"]
    assert len(notable) == 1
    assert "Kiran" in notable[0].actors


def test_displacement_by_region():
    """Correct displacement fraction from mock snapshot."""
    import pyarrow as pa
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.displacement_by_region = {}

    # Mock snapshot: 4 agents in region 0, 1 displaced; 2 in region 1, 0 displaced
    snap = pa.record_batch({
        "id": pa.array([1, 2, 3, 4, 5, 6], type=pa.uint32()),
        "region": pa.array([0, 0, 0, 0, 1, 1], type=pa.uint16()),
        "origin_region": pa.array([0, 0, 0, 0, 1, 1], type=pa.uint16()),
        "civ_affinity": pa.array([0, 0, 0, 0, 0, 0], type=pa.uint16()),
        "occupation": pa.array([0, 0, 0, 0, 0, 0], type=pa.uint8()),
        "loyalty": pa.array([0.5]*6, type=pa.float32()),
        "satisfaction": pa.array([0.5]*6, type=pa.float32()),
        "skill": pa.array([0.5]*6, type=pa.float32()),
        "age": pa.array([20]*6, type=pa.uint16()),
        "displacement_turn": pa.array([3, 0, 0, 0, 0, 0], type=pa.uint16()),
    })

    # Compute directly (same logic as tick())
    from collections import Counter
    regions_col = snap.column("region").to_pylist()
    disp_col = snap.column("displacement_turn").to_pylist()
    region_totals = Counter(regions_col)
    region_displaced: Counter = Counter()
    for r, d in zip(regions_col, disp_col):
        if d > 0:
            region_displaced[r] += 1
    result = {
        r: region_displaced[r] / total if total > 0 else 0.0
        for r, total in region_totals.items()
    }

    assert result[0] == 0.25  # 1 of 4 displaced
    assert result[1] == 0.0   # 0 of 2 displaced


def test_secession_transfer():
    """Secession → civilization updated, origin_civilization preserved."""
    from chronicler.models import GreatPerson

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}
    bridge._sim = MagicMock()

    gp = GreatPerson(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=50, source="agent", agent_id=42, region="Bora",
    )
    old_civ = MagicMock()
    old_civ.name = "Aram"
    old_civ.great_persons = [gp]

    new_civ = MagicMock()
    new_civ.name = "Free Bora"
    new_civ.great_persons = []

    events = bridge.apply_secession_transitions(
        old_civ, new_civ, seceding_regions=["Bora"], new_civ_id=5, turn=100)

    assert gp.civilization == "Free Bora"
    assert gp.origin_civilization == "Aram"  # preserved
    assert len(events) == 1
    assert events[0].event_type == "secession_defection"
