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


class TestDetectionGrid:
    def test_cell_assignment_basic(self):
        from chronicler.settlements import assign_cell
        assert assign_cell(0.55, 0.73) == (5, 7)

    def test_cell_assignment_origin(self):
        from chronicler.settlements import assign_cell
        assert assign_cell(0.0, 0.0) == (0, 0)

    def test_cell_assignment_near_boundary(self):
        from chronicler.settlements import assign_cell
        assert assign_cell(0.999, 0.999) == (9, 9)

    def test_cell_assignment_exact_boundary(self):
        from chronicler.settlements import assign_cell
        assert assign_cell(0.5, 0.5) == (5, 5)


class TestDensityGrid:
    def test_build_density_grid_basic(self):
        from chronicler.settlements import build_density_grid
        agents = [
            (0.55, 0.55), (0.56, 0.55), (0.57, 0.55),  # cell (5,5)
            (0.55, 0.65), (0.56, 0.65),                  # cell (5,6)
            (0.01, 0.01),                                  # cell (0,0)
        ]
        grid = build_density_grid(agents)
        assert grid[(5, 5)] == 3
        assert grid[(5, 6)] == 2
        assert grid[(0, 0)] == 1

    def test_find_dense_cells_with_floor(self):
        from chronicler.settlements import find_dense_cells
        grid = {(5, 5): 10, (5, 6): 3, (0, 0): 1}
        dense = find_dense_cells(grid, region_agent_count=14)
        assert (5, 5) in dense
        assert (5, 6) not in dense
        assert (0, 0) not in dense

    def test_find_dense_cells_with_fraction(self):
        from chronicler.settlements import find_dense_cells
        grid = {(5, 5): 10, (5, 6): 8, (0, 0): 2}
        dense = find_dense_cells(grid, region_agent_count=1000)
        assert len(dense) == 0

    def test_find_dense_cells_all_dense(self):
        from chronicler.settlements import find_dense_cells
        grid = {(5, 5): 10, (5, 6): 8}
        dense = find_dense_cells(grid, region_agent_count=18)
        assert (5, 5) in dense
        assert (5, 6) in dense


import math

class TestConnectedComponents:
    def test_single_cell_cluster(self):
        from chronicler.settlements import find_connected_components
        dense = {(5, 5)}
        components = find_connected_components(dense)
        assert len(components) == 1
        assert components[0] == {(5, 5)}

    def test_two_adjacent_cells(self):
        from chronicler.settlements import find_connected_components
        dense = {(5, 5), (5, 6)}
        components = find_connected_components(dense)
        assert len(components) == 1
        assert components[0] == {(5, 5), (5, 6)}

    def test_diagonal_adjacency_connects(self):
        from chronicler.settlements import find_connected_components
        dense = {(5, 5), (6, 6)}
        components = find_connected_components(dense)
        assert len(components) == 1

    def test_two_separate_clusters(self):
        from chronicler.settlements import find_connected_components
        dense = {(0, 0), (0, 1), (8, 8), (9, 8)}
        components = find_connected_components(dense)
        assert len(components) == 2
        cells_0 = components[0]
        cells_1 = components[1]
        assert (0, 0) in cells_0 or (0, 1) in cells_0
        assert (8, 8) in cells_1 or (9, 8) in cells_1

    def test_l_shape_single_component(self):
        from chronicler.settlements import find_connected_components
        dense = {(3, 3), (4, 3), (5, 3), (5, 4), (5, 5)}
        components = find_connected_components(dense)
        assert len(components) == 1
        assert len(components[0]) == 5

    def test_row_major_discovery_order(self):
        from chronicler.settlements import find_connected_components
        dense = {(5, 0), (5, 9)}
        components = find_connected_components(dense)
        assert len(components) == 2
        assert (5, 0) in components[0]
        assert (5, 9) in components[1]

    def test_empty_input(self):
        from chronicler.settlements import find_connected_components
        components = find_connected_components(set())
        assert components == []


class TestExtractClusters:
    def test_extract_clusters_basic(self):
        from chronicler.settlements import extract_clusters
        agents = [
            (0.51, 0.51), (0.52, 0.52), (0.53, 0.51),
            (0.54, 0.52), (0.55, 0.51), (0.56, 0.52),
        ]
        clusters = extract_clusters(agents)
        assert len(clusters) == 1
        c = clusters[0]
        assert c["population"] == 6
        assert c["cells"] == {(5, 5)}
        assert 0.50 < c["centroid_x"] < 0.57
        assert 0.50 < c["centroid_y"] < 0.53

    def test_extract_clusters_no_dense_cells(self):
        from chronicler.settlements import extract_clusters
        agents = [(0.1, 0.1), (0.3, 0.3), (0.5, 0.5), (0.7, 0.7)]
        clusters = extract_clusters(agents)
        assert clusters == []

    def test_extract_clusters_two_clusters(self):
        from chronicler.settlements import extract_clusters
        agents = (
            [(0.11 + i * 0.01, 0.11) for i in range(6)]
            + [(0.81 + i * 0.01, 0.81) for i in range(6)]
        )
        clusters = extract_clusters(agents)
        assert len(clusters) == 2
