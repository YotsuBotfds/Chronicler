"""Tests for M45 deeds population."""
from chronicler.models import GreatPerson, GreatPersonDeed
from chronicler.great_persons import _append_deed, DEEDS_CAP

DEEDS_CAP_EXPECTED = 10


def _make_gp(**kwargs) -> GreatPerson:
    defaults = dict(
        name="TestChar", role="general", trait="bold",
        civilization="TestCiv", origin_civilization="TestCiv",
        born_turn=1, source="agent", agent_id=1,
    )
    defaults.update(kwargs)
    return GreatPerson(**defaults)


def test_deeds_cap():
    gp = _make_gp()
    for i in range(15):
        _append_deed(gp, f"Deed {i}")
    assert len(gp.deeds) == DEEDS_CAP_EXPECTED
    assert gp.deeds[0].text == "Deed 5"
    assert gp.deeds[-1].text == "Deed 14"


def test_append_deed_cap():
    """_append_deed trims to DEEDS_CAP after overflow."""
    gp = _make_gp()
    for i in range(15):
        _append_deed(gp, f"Deed {i}")
    assert len(gp.deeds) == DEEDS_CAP
    assert gp.deeds[0].text == "Deed 5"
    assert gp.deeds[-1].text == "Deed 14"


def test_append_deed_under_cap():
    """_append_deed does not trim when under cap."""
    gp = _make_gp()
    for i in range(5):
        _append_deed(gp, f"Deed {i}")
    assert len(gp.deeds) == 5
    assert gp.deeds[0].text == "Deed 0"
    assert gp.deeds[-1].text == "Deed 4"


def test_deed_format_promotion():
    """Promoted-as deed format matches expected template."""
    gp = _make_gp()
    _append_deed(gp, "Promoted as general in Riverdale")
    assert gp.deeds[-1].text == "Promoted as general in Riverdale"


def test_deed_format_death():
    """Died-in deed format matches expected template."""
    gp = _make_gp(region="Ashfields")
    _append_deed(gp, f"Died in {gp.region or 'unknown'}")
    assert gp.deeds[-1].text == "Died in Ashfields"


def test_deed_format_death_unknown_region():
    """Died-in deed falls back to 'unknown' when region is None."""
    gp = _make_gp(region=None)
    _append_deed(gp, f"Died in {gp.region or 'unknown'}")
    assert gp.deeds[-1].text == "Died in unknown"


def test_deed_format_retirement():
    """Retired-in deed format matches expected template."""
    gp = _make_gp(region="Northpeak")
    _append_deed(gp, f"Retired in {gp.region or 'unknown'}")
    assert gp.deeds[-1].text == "Retired in Northpeak"


def test_deed_format_conquest_exile():
    """Conquest exile deed format matches expected template."""
    gp = _make_gp(region="StolenProvince")
    _append_deed(gp, f"Exiled after conquest of {gp.region or 'unknown'}")
    assert gp.deeds[-1].text == "Exiled after conquest of StolenProvince"


def test_deed_format_exile_return():
    """Exile return deed format matches expected template."""
    gp = _make_gp()
    _append_deed(gp, "Returned to Homeland after 35 turns")
    assert gp.deeds[-1].text == "Returned to Homeland after 35 turns"


def test_deed_format_migration():
    """Migration deed format matches expected template."""
    gp = _make_gp()
    _append_deed(gp, "Migrated from EasternPlains to WesternCoast")
    assert gp.deeds[-1].text == "Migrated from EasternPlains to WesternCoast"


def test_deed_format_secession():
    """Secession defection deed format matches expected template."""
    gp = _make_gp()
    _append_deed(gp, "Defected to NewRepublic during secession")
    assert gp.deeds[-1].text == "Defected to NewRepublic during secession"


def test_deed_format_pilgrimage_departure():
    """Pilgrimage departure deed format matches expected template."""
    gp = _make_gp()
    _append_deed(gp, "Departed on pilgrimage to GreatTemple")
    assert gp.deeds[-1].text == "Departed on pilgrimage to GreatTemple"


def test_deed_format_pilgrimage_return():
    """Pilgrimage return deed format matches expected template."""
    gp = _make_gp()
    _append_deed(gp, "Returned from pilgrimage as Prophet")
    assert gp.deeds[-1].text == "Returned from pilgrimage as Prophet"


def test_deeds_initially_empty():
    """GreatPerson starts with empty deeds list."""
    gp = _make_gp()
    assert gp.deeds == []


def test_deeds_exact_cap_no_trim():
    """Exactly DEEDS_CAP deeds does not trigger trimming."""
    gp = _make_gp()
    for i in range(DEEDS_CAP):
        _append_deed(gp, f"Deed {i}")
    assert len(gp.deeds) == DEEDS_CAP
    assert gp.deeds[0].text == "Deed 0"


# ---------------------------------------------------------------------------
# Task 2: GreatPersonDeed model tests
# ---------------------------------------------------------------------------

def test_great_person_deed_model():
    deed = GreatPersonDeed(text="Led a campaign", region="Ashfields", turn=47, civ="Aram")
    assert deed.text == "Led a campaign"
    assert deed.region == "Ashfields"
    assert deed.turn == 47
    assert deed.civ == "Aram"


def test_great_person_deed_defaults():
    deed = GreatPersonDeed(text="Something happened")
    assert deed.region is None
    assert deed.turn is None
    assert deed.civ is None


def test_legacy_string_deeds_normalized():
    gp = _make_gp()
    gp_data = gp.model_dump()
    gp_data["deeds"] = ["Old deed string", "Another old deed"]
    loaded = GreatPerson(**gp_data)
    assert len(loaded.deeds) == 2
    assert isinstance(loaded.deeds[0], GreatPersonDeed)
    assert loaded.deeds[0].text == "Old deed string"
    assert loaded.deeds[0].region is None
    assert loaded.deeds[0].turn is None
    assert loaded.deeds[0].civ is None


def test_structured_deeds_round_trip():
    gp = _make_gp()
    gp.deeds = [GreatPersonDeed(text="Led campaign", region="Ashfields", turn=47, civ="Aram")]
    data = gp.model_dump(mode="json")
    loaded = GreatPerson(**data)
    assert isinstance(loaded.deeds[0], GreatPersonDeed)
    assert loaded.deeds[0].region == "Ashfields"
    assert loaded.deeds[0].turn == 47


# ---------------------------------------------------------------------------
# Task 3: _append_deed structured deed tests
# ---------------------------------------------------------------------------

def test_append_deed_creates_structured_deed():
    gp = _make_gp(region="Ashfields", civilization="Aram")
    _append_deed(gp, "Led a campaign", region="Ashfields", turn=47, civ="Aram")
    assert isinstance(gp.deeds[-1], GreatPersonDeed)
    assert gp.deeds[-1].text == "Led a campaign"
    assert gp.deeds[-1].region == "Ashfields"
    assert gp.deeds[-1].turn == 47
    assert gp.deeds[-1].civ == "Aram"


def test_append_deed_defaults_none():
    gp = _make_gp()
    _append_deed(gp, "Something happened")
    assert isinstance(gp.deeds[-1], GreatPersonDeed)
    assert gp.deeds[-1].region is None
    assert gp.deeds[-1].turn is None


def test_append_deed_cap_structured():
    gp = _make_gp()
    for i in range(15):
        _append_deed(gp, f"Deed {i}", region=f"R{i}", turn=i)
    assert len(gp.deeds) == DEEDS_CAP
    assert gp.deeds[0].text == "Deed 5"
    assert gp.deeds[0].region == "R5"
    assert gp.deeds[-1].text == "Deed 14"
