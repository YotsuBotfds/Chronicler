"""Tests for dynasty detection, extinction, and split logic."""
from chronicler.dynasties import Dynasty, DynastyRegistry
from chronicler.models import GreatPerson


def _make_gp(agent_id: int, name: str, civ: str = "Ashara",
             parent_id: int = 0, alive: bool = True) -> GreatPerson:
    gp = GreatPerson(
        name=name, role="general", trait="bold",
        civilization=civ, origin_civilization=civ,
        born_turn=10, source="agent", agent_id=agent_id,
        parent_id=parent_id,
    )
    gp.alive = alive
    return gp


class TestDynastyDetection:
    def test_no_dynasty_when_parent_not_promoted(self):
        registry = DynastyRegistry()
        named_agents = {10: "Kiran"}
        gp_map = {10: _make_gp(10, "Kiran", parent_id=0)}
        child = _make_gp(20, "Tala", parent_id=99)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert len(events) == 0
        assert child.dynasty_id is None

    def test_dynasty_founded_on_parent_child_pair(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", parent_id=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent}
        child = _make_gp(20, "Tala", parent_id=10)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_founded"
        assert events[0].importance == 7
        assert parent.dynasty_id is not None
        assert child.dynasty_id == parent.dynasty_id
        assert registry.dynasties[0].founder_name == "Kiran"

    def test_child_joins_existing_dynasty(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", parent_id=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent}
        child1 = _make_gp(20, "Tala", parent_id=10)
        registry.check_promotion(child1, named_agents, gp_map)
        dynasty_id = child1.dynasty_id
        child2 = _make_gp(30, "Sera", parent_id=10)
        events = registry.check_promotion(child2, named_agents, gp_map)
        assert child2.dynasty_id == dynasty_id
        assert len(registry.dynasties) == 1
        assert 30 in registry.dynasties[0].members


class TestDynastyExtinction:
    def test_extinction_when_all_dead(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran")
        child = _make_gp(20, "Tala", parent_id=10)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        parent.alive = False
        child.alive = False
        events = registry.check_extinctions(gp_map, turn=100)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_extinct"
        assert registry.dynasties[0].extinct

    def test_no_extinction_while_member_alive(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran")
        child = _make_gp(20, "Tala", parent_id=10)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        parent.alive = False
        events = registry.check_extinctions(gp_map, turn=100)
        assert len(events) == 0
        assert not registry.dynasties[0].extinct


class TestDynastySplit:
    def test_split_on_different_civs(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id=10, civ="Verath")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        events = registry.check_splits(gp_map, turn=100)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_split"
        assert events[0].importance == 5
        assert registry.dynasties[0].split_detected

    def test_split_one_shot(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id=10, civ="Verath")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        registry.check_splits(gp_map, turn=99)
        events = registry.check_splits(gp_map, turn=100)
        assert len(events) == 0

    def test_no_split_when_same_civ(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id=10, civ="Ashara")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        events = registry.check_splits(gp_map, turn=100)
        assert len(events) == 0
