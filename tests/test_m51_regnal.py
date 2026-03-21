"""M51 Regnal Naming Tests."""
from chronicler.models import Leader, Civilization


def test_leader_has_regnal_fields():
    leader = Leader(name="King Kiran", trait="bold", reign_start=0)
    assert leader.agent_id is None
    assert leader.dynasty_id is None
    assert leader.throne_name is None
    assert leader.regnal_ordinal == 0


def test_leader_with_regnal_data():
    leader = Leader(name="King Kiran II", trait="bold", reign_start=100,
                    agent_id=42, dynasty_id=1, throne_name="Kiran", regnal_ordinal=2)
    assert leader.throne_name == "Kiran"
    assert leader.regnal_ordinal == 2


def test_civilization_has_regnal_name_counts():
    civ = Civilization(name="Aram", leader=Leader(name="Founder", trait="bold", reign_start=0))
    assert civ.regnal_name_counts == {}
    civ.regnal_name_counts["Kiran"] = 1
    assert civ.regnal_name_counts["Kiran"] == 1
