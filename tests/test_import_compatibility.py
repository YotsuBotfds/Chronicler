"""Compatibility for callers importing historical module attributes directly."""

import random
from dataclasses import dataclass, field as dataclass_field

from chronicler.leaders import _pick_regnal_name as leaders_pick_regnal_name
from chronicler.memory import field as memory_field
from chronicler.models import Civilization, Leader, WorldState, field as models_field
from chronicler.world_gen import _pick_regnal_name as world_gen_pick_regnal_name


def test_module_import_aliases_remain_callable():
    assert memory_field is dataclass_field
    assert models_field is dataclass_field
    assert world_gen_pick_regnal_name is leaders_pick_regnal_name

    @dataclass
    class CallerRecord:
        memories: list[str] = memory_field(default_factory=list)
        counts: dict[str, int] = models_field(default_factory=dict)

    record = CallerRecord()
    assert record.memories == []
    assert record.counts == {}

    civ = Civilization(
        name="Test Realm",
        leader=Leader(name="Founder", trait="bold", reign_start=0),
        leader_name_pool=["Arin"],
    )
    world = WorldState(name="Import compatibility", seed=1, civilizations=[civ])
    _, throne_name, ordinal = world_gen_pick_regnal_name(civ, world, random.Random(1))
    assert (throne_name, ordinal) == ("Arin", 0)
    assert civ.regnal_name_counts["Arin"] == 1
