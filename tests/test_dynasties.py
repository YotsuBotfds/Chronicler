"""Tests for dynasty detection, extinction, and split logic."""
from chronicler.dynasties import Dynasty, DynastyRegistry
from chronicler.models import GreatPerson


def _make_gp(agent_id: int, name: str, civ: str = "Ashara",
             parent_id_0: int = 0, parent_id_1: int = 0,
             alive: bool = True) -> GreatPerson:
    gp = GreatPerson(
        name=name, role="general", trait="bold",
        civilization=civ, origin_civilization=civ,
        born_turn=10, source="agent", agent_id=agent_id,
        parent_id_0=parent_id_0, parent_id_1=parent_id_1,
    )
    gp.alive = alive
    return gp


class TestDynastyDetection:
    def test_no_dynasty_when_parent_not_promoted(self):
        registry = DynastyRegistry()
        named_agents = {10: "Kiran"}
        gp_map = {10: _make_gp(10, "Kiran", parent_id_0=0)}
        child = _make_gp(20, "Tala", parent_id_0=99)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert len(events) == 0
        assert child.dynasty_id is None

    def test_dynasty_founded_on_parent_child_pair(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", parent_id_0=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent}
        child = _make_gp(20, "Tala", parent_id_0=10)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_founded"
        assert events[0].importance == 7
        assert parent.dynasty_id is not None
        assert child.dynasty_id == parent.dynasty_id
        assert registry.dynasties[0].founder_name == "Kiran"

    def test_child_joins_existing_dynasty(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", parent_id_0=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent}
        child1 = _make_gp(20, "Tala", parent_id_0=10)
        registry.check_promotion(child1, named_agents, gp_map)
        dynasty_id = child1.dynasty_id
        child2 = _make_gp(30, "Sera", parent_id_0=10)
        events = registry.check_promotion(child2, named_agents, gp_map)
        assert child2.dynasty_id == dynasty_id
        assert len(registry.dynasties) == 1
        assert 30 in registry.dynasties[0].members


class TestDynastyExtinction:
    def test_extinction_when_all_dead(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran")
        child = _make_gp(20, "Tala", parent_id_0=10)
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
        child = _make_gp(20, "Tala", parent_id_0=10)
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
        child = _make_gp(20, "Tala", parent_id_0=10, civ="Verath")
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
        child = _make_gp(20, "Tala", parent_id_0=10, civ="Verath")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        registry.check_splits(gp_map, turn=99)
        events = registry.check_splits(gp_map, turn=100)
        assert len(events) == 0

    def test_no_split_when_same_civ(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id_0=10, civ="Ashara")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        events = registry.check_splits(gp_map, turn=100)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# M57a: Dual-parent dynasty resolution
# ---------------------------------------------------------------------------

class TestDualParentDynastyResolution:
    """Tests for the four dynasty resolution rules with dual parents."""

    def test_single_parent_with_dynasty_child_inherits(self):
        """Rule 1: Single parent (parent_id_0) with dynasty -> child inherits it."""
        registry = DynastyRegistry()
        parent_0 = _make_gp(10, "Kiran", parent_id_0=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent_0}
        # First, found a dynasty via a child so parent_0 gets a dynasty
        first_child = _make_gp(15, "Alia", parent_id_0=10)
        registry.check_promotion(first_child, named_agents, gp_map)
        dynasty_id = parent_0.dynasty_id
        assert dynasty_id is not None
        # Now promote a new child with only parent_id_0 set
        gp_map[15] = first_child
        named_agents[15] = "Alia"
        child = _make_gp(20, "Tala", parent_id_0=10, parent_id_1=0)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert child.dynasty_id == dynasty_id
        assert child.lineage_house == 0

    def test_two_parents_same_dynasty_child_inherits(self):
        """Rule 2: Two parents in the same dynasty -> child inherits, lineage_house = 0."""
        registry = DynastyRegistry()
        parent_0 = _make_gp(10, "Kiran", parent_id_0=0)
        parent_1 = _make_gp(11, "Sera", parent_id_0=0)
        named_agents = {10: "Kiran", 11: "Sera"}
        gp_map = {10: parent_0, 11: parent_1}
        # Found dynasty with parent_0
        first_child = _make_gp(15, "Alia", parent_id_0=10)
        registry.check_promotion(first_child, named_agents, gp_map)
        dynasty_id = parent_0.dynasty_id
        # Manually assign parent_1 to same dynasty (as if they married in)
        parent_1.dynasty_id = dynasty_id
        registry.dynasties[0].members.append(11)
        gp_map[15] = first_child
        named_agents[15] = "Alia"
        # Child with both parents in same dynasty
        child = _make_gp(20, "Tala", parent_id_0=10, parent_id_1=11)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert child.dynasty_id == dynasty_id
        assert child.lineage_house == 0

    def test_two_parents_different_dynasties_birth_parent_wins(self):
        """Rule 3: Two parents with different dynasties -> birth parent's dynasty,
        lineage_house = other dynasty id."""
        registry = DynastyRegistry()
        # Create two separate dynasties
        parent_a = _make_gp(10, "Kiran", parent_id_0=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent_a}
        child_a = _make_gp(15, "Alia", parent_id_0=10)
        registry.check_promotion(child_a, named_agents, gp_map)
        dynasty_0 = parent_a.dynasty_id

        parent_b = _make_gp(50, "Drago", parent_id_0=0)
        named_agents[50] = "Drago"
        gp_map[50] = parent_b
        gp_map[15] = child_a
        named_agents[15] = "Alia"
        child_b = _make_gp(55, "Vari", parent_id_0=50)
        registry.check_promotion(child_b, named_agents, gp_map)
        dynasty_1 = parent_b.dynasty_id

        assert dynasty_0 is not None
        assert dynasty_1 is not None
        assert dynasty_0 != dynasty_1

        # Now: child with parent_id_0=10 (dynasty_0), parent_id_1=50 (dynasty_1)
        gp_map[55] = child_b
        named_agents[55] = "Vari"
        child = _make_gp(100, "Mira", parent_id_0=10, parent_id_1=50)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert child.dynasty_id == dynasty_0  # birth parent's dynasty
        assert child.lineage_house == dynasty_1  # other parent's dynasty

    def test_neither_parent_in_dynasty_founder_logic(self):
        """Rule 4: Neither parent has a dynasty -> founder logic triggers."""
        registry = DynastyRegistry()
        parent_0 = _make_gp(10, "Kiran", parent_id_0=0)
        parent_1 = _make_gp(11, "Sera", parent_id_0=0)
        # Neither has a dynasty_id
        assert parent_0.dynasty_id is None
        assert parent_1.dynasty_id is None
        named_agents = {10: "Kiran", 11: "Sera"}
        gp_map = {10: parent_0, 11: parent_1}
        # Child with both parents set, neither in a dynasty
        child = _make_gp(20, "Tala", parent_id_0=10, parent_id_1=11)
        events = registry.check_promotion(child, named_agents, gp_map)
        # Should found a new dynasty (parent-child pair detected)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_founded"
        assert parent_0.dynasty_id is not None
        assert child.dynasty_id == parent_0.dynasty_id

    def test_dynasty_via_parent_id_1_only(self):
        """When only parent_id_1 is a named agent with dynasty, child inherits."""
        registry = DynastyRegistry()
        parent_1 = _make_gp(11, "Sera", parent_id_0=0)
        named_agents = {11: "Sera"}
        gp_map = {11: parent_1}
        # Found dynasty via parent_1
        first_child = _make_gp(15, "Alia", parent_id_0=11)
        registry.check_promotion(first_child, named_agents, gp_map)
        dynasty_id = parent_1.dynasty_id
        assert dynasty_id is not None
        gp_map[15] = first_child
        named_agents[15] = "Alia"
        # Child where parent_id_0 is unknown, parent_id_1 is the named parent
        child = _make_gp(20, "Tala", parent_id_0=999, parent_id_1=11)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert child.dynasty_id == dynasty_id
