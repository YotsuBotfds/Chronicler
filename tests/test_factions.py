"""Tests for faction system — influence, power struggles, weight modifiers, succession."""
import pytest
from chronicler.models import FactionType, FactionState, Civilization, Leader, CivSnapshot


class TestFactionDataModel:
    def test_faction_type_values(self):
        assert FactionType.MILITARY.value == "military"
        assert FactionType.MERCHANT.value == "merchant"
        assert FactionType.CULTURAL.value == "cultural"

    def test_faction_state_defaults(self):
        fs = FactionState()
        assert fs.influence[FactionType.MILITARY] == pytest.approx(0.33)
        assert fs.influence[FactionType.MERCHANT] == pytest.approx(0.33)
        assert fs.influence[FactionType.CULTURAL] == pytest.approx(0.34)
        assert fs.power_struggle is False
        assert fs.power_struggle_turns == 0

    def test_civilization_has_factions(self):
        leader = Leader(name="Test", trait="bold", reign_start=0)
        civ = Civilization(
            name="TestCiv", population=50, military=40, economy=60,
            culture=30, stability=70, regions=["r1"], leader=leader,
        )
        assert isinstance(civ.factions, FactionState)
        assert civ.founded_turn == 0

    def test_civ_snapshot_has_factions(self):
        snap = CivSnapshot(
            population=50, military=40, economy=60, culture=30,
            stability=70, treasury=100, asabiya=0.5, tech_era="tribal",
            trait="bold", regions=["r1"], leader_name="Test", alive=True,
        )
        assert snap.factions is None
