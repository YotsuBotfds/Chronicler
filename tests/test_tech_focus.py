from chronicler.models import Civilization, Leader


def test_civilization_has_tech_focus_fields():
    civ = Civilization(
        name="Test", population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    assert civ.tech_focuses == []
    assert civ.active_focus is None
