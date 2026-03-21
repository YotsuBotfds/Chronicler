"""M51 Regnal Naming Tests."""
from chronicler.models import Leader, Civilization
from chronicler.leaders import to_roman, strip_title


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


def test_strip_title_single_word():
    assert strip_title("Emperor Kiran") == "Kiran"


def test_strip_title_multi_word():
    assert strip_title("High Priestess Mira") == "Mira"


def test_strip_title_no_title():
    assert strip_title("Kiran") == "Kiran"


def test_strip_title_with_numeral():
    assert strip_title("Kiran III") == "Kiran"


def test_to_roman():
    assert to_roman(2) == "II"
    assert to_roman(3) == "III"
    assert to_roman(4) == "IV"
    assert to_roman(9) == "IX"
    assert to_roman(14) == "XIV"
    assert to_roman(20) == "XX"
