"""M56a: Settlement detection tests."""
import pytest
from chronicler.models import Settlement, SettlementStatus, SettlementSummary


class TestSettlementModel:
    def test_candidate_construction_with_sentinel_defaults(self):
        """Candidates use settlement_id=0, name='', founding_turn=0."""
        s = Settlement(
            region_name="Nile Delta",
            last_seen_turn=15,
            population_estimate=42,
            centroid_x=0.3,
            centroid_y=0.7,
            candidate_passes=1,
        )
        assert s.settlement_id == 0
        assert s.name == ""
        assert s.founding_turn == 0
        assert s.status == SettlementStatus.CANDIDATE

    def test_active_settlement_construction(self):
        s = Settlement(
            settlement_id=1,
            name="Nile Delta Settlement 1",
            region_name="Nile Delta",
            founding_turn=30,
            last_seen_turn=45,
            population_estimate=100,
            peak_population=100,
            centroid_x=0.5,
            centroid_y=0.5,
            footprint_cells=[(5, 5), (5, 6)],
            status=SettlementStatus.ACTIVE,
            inertia=3,
        )
        assert s.settlement_id == 1
        assert s.status == SettlementStatus.ACTIVE
        assert s.footprint_cells == [(5, 5), (5, 6)]

    def test_tombstone_zeroed_lifecycle_fields(self):
        s = Settlement(
            settlement_id=1,
            name="Nile Delta Settlement 1",
            region_name="Nile Delta",
            founding_turn=30,
            last_seen_turn=90,
            dissolved_turn=90,
            population_estimate=0,
            peak_population=150,
            centroid_x=0.5,
            centroid_y=0.5,
            status=SettlementStatus.DISSOLVED,
            inertia=0,
            grace_remaining=0,
            candidate_passes=0,
            footprint_cells=[],
        )
        assert s.status == SettlementStatus.DISSOLVED
        assert s.dissolved_turn == 90
        assert s.inertia == 0
        assert s.footprint_cells == []

    def test_settlement_summary_construction(self):
        ss = SettlementSummary(
            settlement_id=1,
            name="Nile Delta Settlement 1",
            region_name="Nile Delta",
            population_estimate=100,
            centroid_x=0.5,
            centroid_y=0.5,
            founding_turn=30,
            status="active",
        )
        assert ss.settlement_id == 1

    def test_status_enum_values(self):
        assert SettlementStatus.CANDIDATE == "candidate"
        assert SettlementStatus.ACTIVE == "active"
        assert SettlementStatus.DISSOLVING == "dissolving"
        assert SettlementStatus.DISSOLVED == "dissolved"


class TestModelIntegration:
    def test_region_settlements_default_empty(self):
        from chronicler.models import Region
        r = Region(name="Test", terrain="plains", carrying_capacity=100, resources="fertile")
        assert r.settlements == []

    def test_worldstate_settlement_fields_default(self):
        from chronicler.models import WorldState
        w = WorldState(name="Test", seed=42)
        assert w.dissolved_settlements == []
        assert w.next_settlement_id == 1
        assert w.settlement_naming_counters == {}
        assert w.settlement_candidates == []

    def test_turnsnapshot_settlement_fields_default(self):
        from chronicler.models import TurnSnapshot
        snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
        assert snap.settlement_count == 0
        assert snap.candidate_count == 0
        assert snap.active_settlements == []
        assert snap.founded_this_turn == []
        assert snap.dissolved_this_turn == []
        assert snap.settlement_source_turn == 0
