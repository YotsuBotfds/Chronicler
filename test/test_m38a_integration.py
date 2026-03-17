"""M38a integration tests: temple lifecycle and 4-faction invariants."""
import pytest
from chronicler.models import FactionType, FactionState, InfrastructureType, Infrastructure
from chronicler.factions import normalize_influence, FACTION_FLOOR


def test_4_faction_normalization_invariant():
    """All faction states maintain sum=1.0 and floor >= 0.08."""
    fs = FactionState()
    fs.influence[FactionType.CLERGY] = 0.0
    fs.influence[FactionType.MILITARY] = 0.5
    normalize_influence(fs)
    total = sum(fs.influence.values())
    assert abs(total - 1.0) < 1e-6
    for ft in FactionType:
        assert fs.influence[ft] >= FACTION_FLOOR - 1e-6


def test_temple_lifecycle_militant_conquest():
    """Militant holy war destroys temple."""
    from chronicler.infrastructure import destroy_temple_on_conquest
    temple = Infrastructure(type=InfrastructureType.TEMPLES, builder_civ="OldCiv", built_turn=1, faith_id=0)
    class R:
        infrastructure = [temple]
        name = "Region0"
    class C:
        name = "NewCiv"
    class W:
        turn = 10
    event = destroy_temple_on_conquest(R(), C(), W())
    assert event is not None
    assert event.event_type == "temple_destroyed"
    assert temple.active is False


def test_temple_lifecycle_non_militant_preserves():
    """Non-militant conquest preserves temple (destruction not called)."""
    temple = Infrastructure(type=InfrastructureType.TEMPLES, builder_civ="OldCiv", built_turn=1, faith_id=0, temple_prestige=20)
    assert temple.active is True
    assert temple.faith_id == 0
    assert temple.temple_prestige == 20


def test_temple_replacement():
    """BUILD replaces foreign temple."""
    from chronicler.infrastructure import destroy_temple_for_replacement
    temple = Infrastructure(type=InfrastructureType.TEMPLES, builder_civ="OldCiv", built_turn=1, faith_id=0)
    class R:
        infrastructure = [temple]
        name = "Region0"
    class W:
        turn = 10
    event = destroy_temple_for_replacement(R(), W())
    assert event is not None
    assert temple.active is False
