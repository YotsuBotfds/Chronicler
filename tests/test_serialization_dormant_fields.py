"""Dormant and empty optional fields are omitted from serialized output.

The models declare the omission with field-level ``exclude_if``; these tests
pin the rule the earlier wrap serializers implemented: a listed field is
left out of ``model_dump`` and ``model_dump_json`` exactly while it holds
its empty value, and every other field keeps its declaration order.
"""
from __future__ import annotations

import json

import pytest

from chronicler import models as m


# model, constructor arguments, {field: (empty value, a non-empty value)}
CASES = [
    (m.Event, dict(turn=3, event_type="war", actors=["A"], description="d"), {
        "event_id": ("", "3:war:1"), "causes": ([], ["2:x:1"]), "region": (None, "R"),
        "civs": ([], ["A"]), "episode": (None, "onset"), "duration": (None, 4),
        "driver": (None, "wage"),
    }),
    (m.ActiveCondition, dict(condition_type="drought", affected_civs=["A"], duration=2), {
        "condition_id": ("", "c1"), "cause_id": (None, "1:x:1"), "onset_turn": (None, 7),
    }),
    (m.CausalLink, dict(cause_turn=1, cause_event_type="a", effect_turn=2, effect_event_type="b",
                        pattern="p"), {
        "cause_id": ("", "1:a:1"), "effect_id": ("", "2:b:1"), "provenance": ("pattern", "recorded"),
    }),
    (m.VassalRelation, dict(overlord="A", vassal="B"), {
        "stage": (None, "client"), "stage_turn": (None, 5), "integration": (None, 12.5),
        "crown": (None, "K"),
    }),
    (m.Relationship, dict(), {"memory": (None, m.DiplomaticMemory())}),
    (m.CivSnapshot, dict(population=1, military=1, economy=1, culture=1, stability=1, treasury=1,
                         asabiya=0.5, tech_era=m.TechEra.TRIBAL, trait="bold", regions=["R"],
                         leader_name="L", alive=True), {"governance": (None, {"psi": 0.1})}),
]


def _fields_in_order(model_cls, dumped: dict) -> list[str]:
    return [name for name in model_cls.model_fields if name in dumped]


@pytest.mark.parametrize("model_cls,kwargs,dormant", CASES, ids=lambda c: getattr(c, "__name__", ""))
def test_empty_values_are_omitted_and_others_kept(model_cls, kwargs, dormant):
    empty =model_cls(**kwargs, **{k: v[0] for k, v in dormant.items()})
    dumped = empty.model_dump()
    for name in dormant:
        assert name not in dumped
    assert json.loads(empty.model_dump_json()) == empty.model_dump(mode="json")
    full = model_cls(**kwargs, **{k: v[1] for k, v in dormant.items()})
    dumped = full.model_dump()
    for name in dormant:
        assert name in dumped
    # Declaration order is kept; the JSON text is the dict's own order.
    assert list(dumped) == _fields_in_order(model_cls, dumped)
    assert list(json.loads(full.model_dump_json())) == list(dumped)
    # Each field on its own.
    for name, (_, value) in dormant.items():
        one = model_cls(**kwargs, **{name: value})
        keys = set(one.model_dump())
        assert name in keys
        assert keys.isdisjoint(set(dormant) - {name})


def test_world_state_omits_dormant_layers_and_empty_provenance():
    world = m.WorldState(name="w", seed=1)
    dumped = json.loads(world.model_dump_json())
    for name in ("governance", "geography", "contact_ledger", "epidemics", "finance", "diplomacy",
                 "techniques", "maritime", "gp_agendas", "nomads", "cities", "agent_movements",
                 "guilds", "scholarship", "provenance"):
        assert name not in dumped
    assert dumped == world.model_dump(mode="json")
    world.provenance.keys["k"] = "1:x:1"
    assert "provenance" in json.loads(world.model_dump_json())


def test_turn_snapshot_omits_dormant_summaries():
    snap = m.TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    dumped = snap.model_dump()
    for name in ("campaign", "contact", "epidemics", "finance", "diplomacy", "techniques", "maritime",
                 "gp_agendas", "nomads", "cities", "agent_movements", "guilds", "scholarship", "food",
                 "migration"):
        assert name not in dumped
    snap.food = {"r": 1.0}
    snap.migration = []
    dumped = snap.model_dump()
    assert dumped["food"] == {"r": 1.0} and dumped["migration"] == []


def test_region_omits_dormant_optional_fields():
    region = m.Region(name="R", terrain="plains", carrying_capacity=10, resources="fertile")
    dumped = region.model_dump()
    for name in ("latitude_band", "geo", "fishery_collapsed", "stockpile_bootstrap_pending",
                 "persecuting_faith", "food_severe_turns", "food_shortfall", "dearth_cooldown"):
        assert name not in dumped
    region.persecuting_faith = 0
    region.food_shortfall = 0.0
    region.dearth_cooldown = False
    dumped = region.model_dump()
    assert dumped["persecuting_faith"] == 0 and dumped["food_shortfall"] == 0.0
    assert dumped["dearth_cooldown"] is False
