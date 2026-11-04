"""Completed native diagnostic histories keep values and canonical outer keys."""
from types import SimpleNamespace

import pytest

import chronicler.agent_bridge as bridge_module
import chronicler.economy as economy_module
from test_agent_bridge import _bare_agent_bridge


class StatsSimulator:
    def __init__(self, records):
        self.records = records
        self.index = -1
        self.calls = []

    def set_merchant_route_graph(self, route):
        self.calls.append("route")

    def tick(self, turn, signals):
        self.index += 1
        self.calls.append("tick")
        return []

    def get_relationship_stats(self):
        self.calls.append("relationship")
        return self.records[self.index]["relationship"].copy()

    def get_household_stats(self):
        self.calls.append("household")
        return self.records[self.index]["household"].copy()

    def get_merchant_trip_stats(self):
        self.calls.append("merchant")
        return self.records[self.index]["merchant"].copy()

    def get_knowledge_stats(self):
        self.calls.append("knowledge")
        return self.records[self.index]["knowledge"].copy()


def assert_same_values(actual, expected):
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        found = actual[key]
        assert type(found) is type(value)
        if isinstance(value, float):
            assert found.hex() == value.hex()  # Includes the sign of zero.
        elif isinstance(value, dict):
            assert list(found) == list(value)  # Nested by-type order is retained.
            assert_same_values(found, value)
        else:
            assert found == value


@pytest.mark.parametrize("entrypoint", ["tick", "tick_agents"])
@pytest.mark.parametrize("family", ["household", "merchant", "knowledge", "relationship"])
def test_completed_stat_history_sorts_only_outer_keys(monkeypatch, entrypoint, family):
    household = {"z_future": -0.0, "births_unmarried_parent": 7.0,
                 "inheritance_wealth_lost": 0.0, "a_future": 1.25}
    merchant = {"z_future": -0.0, "total_in_transit_qty": 2.5,
                "active_trips": 3.0, "a_future": 0.0}
    knowledge = {"z_future": -0.0, "packets_created": 5.0, "mean_age": 0.0,
                 "created_religious": 3.0, "created_trade": 2.0, "created_threat": 1.0,
                 "transmitted_religious": 6.0, "transmitted_trade": 5.0,
                 "transmitted_threat": 4.0, "a_future": 1.25}
    relationship = {"z_future": -0.0, "bonds_formed": 3.0, "a_future": 1.25}
    first = dict(household=household, merchant=merchant, knowledge=knowledge, relationship=relationship)
    second = {name: dict(reversed(list(record.items()))) for name, record in first.items()}
    second["household"]["births_unmarried_parent"] = 8.0
    second["merchant"]["active_trips"] = 4.0
    second["knowledge"]["packets_created"] = 6.0
    second["relationship"]["bonds_formed"] = 4.0
    simulator = StatsSimulator([first, second])
    bridge = _bare_agent_bridge(sim=simulator)
    bridge._collect_rel_stats = family == "relationship"
    world = SimpleNamespace(turn=0)
    monkeypatch.setattr(economy_module, "build_merchant_route_graph", lambda world: None)
    monkeypatch.setattr(bridge_module, "build_signals", lambda *args, **kwargs: None)
    monkeypatch.setattr(bridge, "sync_regions", lambda world: simulator.calls.append("sync"))
    monkeypatch.setattr(bridge, "_refresh_snapshot_metrics", lambda world: None)
    monkeypatch.setattr(bridge, "_apply_demographics_clamp", lambda world: None)
    monkeypatch.setattr(bridge, "_write_economy_sidecar", lambda *args: None)
    for turn in range(2):
        world.turn = turn
        assert getattr(bridge, entrypoint)(world) == []
    per_tick = (["sync"] if entrypoint == "tick" else []) + ["route", "tick"]
    per_tick += (["relationship"] if family == "relationship" else [])
    per_tick += ["household", "merchant", "knowledge"]
    assert simulator.calls == per_tick * 2
    histories = {"household": bridge.household_stats,
                 "merchant": bridge.merchant_trip_stats,
                 "knowledge": bridge.knowledge_stats,
                 "relationship": bridge.relationship_stats}
    if family != "relationship":
        assert bridge.relationship_stats == []  # Disabled collection makes no getter call.
    history = histories[family]
    assert len(history) == 2
    for index, record in enumerate(history):
        assert list(record) == sorted(record)
        expected = simulator.records[index][family].copy()
        if family == "knowledge":
            expected = {
                "z_future": -0.0, "a_future": 1.25,
                "packets_created": 5 + index, "mean_age": 0.0,
                "created_by_type": {"threat": 1, "trade": 2, "religious": 3},
                "transmitted_by_type": {"threat": 4, "trade": 5, "religious": 6},
            }
        assert_same_values(record, expected)
        assert "a_future" in record and "z_future" in record
