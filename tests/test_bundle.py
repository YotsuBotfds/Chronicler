"""Tests for snapshot models and bundle assembly."""
import json
import pytest
from chronicler.models import (
    CivSnapshot, RelationshipSnapshot, TurnSnapshot, TechEra,
)


class TestSnapshotModels:
    def test_civ_snapshot_round_trip(self):
        snap = CivSnapshot(
            population=7, military=5, economy=8, culture=6, stability=6,
            treasury=12, asabiya=0.6, tech_era=TechEra.IRON,
            trait="calculating", regions=["Verdant Plains", "Sapphire Coast"],
            leader_name="Empress Vaelith", alive=True,
        )
        data = json.loads(snap.model_dump_json())
        restored = CivSnapshot.model_validate(data)
        assert restored.population == 7
        assert restored.tech_era == TechEra.IRON
        assert restored.trait == "calculating"
        assert restored.alive is True
        assert restored.regions == ["Verdant Plains", "Sapphire Coast"]

    def test_relationship_snapshot_round_trip(self):
        snap = RelationshipSnapshot(disposition="hostile")
        data = json.loads(snap.model_dump_json())
        restored = RelationshipSnapshot.model_validate(data)
        assert restored.disposition == "hostile"

    def test_turn_snapshot_round_trip(self):
        snap = TurnSnapshot(
            turn=5,
            civ_stats={
                "Kethani Empire": CivSnapshot(
                    population=7, military=5, economy=8, culture=6,
                    stability=6, treasury=12, asabiya=0.6,
                    tech_era=TechEra.IRON, trait="calculating",
                    regions=["Verdant Plains"], leader_name="Empress Vaelith",
                    alive=True,
                ),
            },
            region_control={"Verdant Plains": "Kethani Empire", "Thornwood": None},
            relationships={
                "Kethani Empire": {
                    "Dorrathi Clans": RelationshipSnapshot(disposition="suspicious"),
                },
            },
        )
        data = json.loads(snap.model_dump_json())
        restored = TurnSnapshot.model_validate(data)
        assert restored.turn == 5
        assert restored.civ_stats["Kethani Empire"].population == 7
        assert restored.region_control["Thornwood"] is None
        assert restored.relationships["Kethani Empire"]["Dorrathi Clans"].disposition == "suspicious"
