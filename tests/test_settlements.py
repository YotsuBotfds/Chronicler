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


class TestMatching:
    def _make_settlement(self, sid, cx, cy, founding, status="active", inertia=3):
        from chronicler.models import Settlement, SettlementStatus
        return Settlement(
            settlement_id=sid, name=f"S{sid}", region_name="R",
            founding_turn=founding, last_seen_turn=founding,
            centroid_x=cx, centroid_y=cy,
            status=SettlementStatus(status), inertia=inertia,
        )

    def _make_cluster(self, cid, cx, cy, pop=10):
        return {
            "component_id": cid, "centroid_x": cx, "centroid_y": cy,
            "population": pop, "cells": {(int(cx * 10), int(cy * 10))},
        }

    def test_match_single_settlement_to_nearest_cluster(self):
        from chronicler.settlements import match_settlements_to_clusters
        settlements = [self._make_settlement(1, 0.5, 0.5, 10)]
        clusters = [
            self._make_cluster(0, 0.52, 0.52),
            self._make_cluster(1, 0.9, 0.9),
        ]
        matched_s, matched_c, unmatched_s, unmatched_c = match_settlements_to_clusters(
            settlements, clusters, source_turn=20
        )
        assert matched_s == {1: 0}
        assert 1 in unmatched_c

    def test_distance_gate_rejects_far_cluster(self):
        from chronicler.settlements import match_settlements_to_clusters
        settlements = [self._make_settlement(1, 0.1, 0.1, 10)]
        clusters = [self._make_cluster(0, 0.9, 0.9)]
        matched_s, matched_c, unmatched_s, unmatched_c = match_settlements_to_clusters(
            settlements, clusters, source_turn=20
        )
        assert matched_s == {}
        assert 1 in unmatched_s
        assert 0 in unmatched_c

    def test_older_settlement_wins_tie(self):
        from chronicler.settlements import match_settlements_to_clusters
        s_old = self._make_settlement(1, 0.5, 0.5, founding=5)
        s_new = self._make_settlement(2, 0.52, 0.52, founding=15)
        clusters = [self._make_cluster(0, 0.51, 0.51)]
        matched_s, _, unmatched_s, _ = match_settlements_to_clusters(
            [s_old, s_new], clusters, source_turn=20
        )
        assert matched_s == {1: 0}
        assert 2 in unmatched_s

    def test_greedy_no_double_assignment(self):
        from chronicler.settlements import match_settlements_to_clusters
        s1 = self._make_settlement(1, 0.5, 0.5, 10)
        s2 = self._make_settlement(2, 0.55, 0.55, 10)
        clusters = [self._make_cluster(0, 0.52, 0.52)]
        matched_s, _, unmatched_s, _ = match_settlements_to_clusters(
            [s1, s2], clusters, source_turn=20
        )
        assert len(matched_s) == 1
        assert len(unmatched_s) == 1


class TestLifecycle:
    def _make_world_stub(self):
        """Minimal world stub for lifecycle testing."""
        from chronicler.models import WorldState, Region
        w = WorldState(name="Test", seed=42)
        r = Region(name="TestRegion", terrain="plains", carrying_capacity=1000, resources="fertile", controller="TestCiv")
        w.regions = [r]
        return w

    def test_candidate_promotion_after_persistence(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle, CANDIDATE_PERSISTENCE
        w = self._make_world_stub()
        cand = Settlement(
            region_name="TestRegion", last_seen_turn=0,
            centroid_x=0.5, centroid_y=0.5, population_estimate=50,
            candidate_passes=CANDIDATE_PERSISTENCE - 1,
        )
        w.settlement_candidates = [cand]
        matched_candidates = {0: 0}
        clusters = [{"component_id": 0, "centroid_x": 0.51, "centroid_y": 0.51, "population": 55, "cells": {(5, 5)}}]
        events = process_lifecycle(w, "TestRegion", matched_candidates, {}, clusters, set(), set(), source_turn=30)
        assert len(w.settlement_candidates) == 0
        region = w.region_map["TestRegion"]
        assert len(region.settlements) == 1
        s = region.settlements[0]
        assert s.status == SettlementStatus.ACTIVE
        assert s.settlement_id == 1
        assert s.name == "TestRegion Settlement 1"
        assert s.inertia == 1
        assert s.founding_turn == 30
        assert any(e.event_type == "settlement_founded" for e in events)

    def test_candidate_dropped_when_unmatched(self):
        from chronicler.models import Settlement
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        cand = Settlement(region_name="TestRegion", last_seen_turn=0, candidate_passes=1)
        w.settlement_candidates = [cand]
        events = process_lifecycle(w, "TestRegion", {}, {}, [], set(), set(), source_turn=30)
        assert len(w.settlement_candidates) == 0

    def test_new_candidate_created_from_unclaimed_cluster(self):
        from chronicler.models import SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        clusters = [{"component_id": 0, "centroid_x": 0.3, "centroid_y": 0.4, "population": 30, "cells": {(3, 4)}, "region_name": "TestRegion"}]
        unclaimed_cluster_ids = {0}
        events = process_lifecycle(w, "TestRegion", {}, {}, clusters, unclaimed_cluster_ids, set(), source_turn=15)
        assert len(w.settlement_candidates) == 1
        c = w.settlement_candidates[0]
        assert c.status == SettlementStatus.CANDIDATE
        assert c.candidate_passes == 1
        assert c.region_name == "TestRegion"

    def test_active_settlement_inertia_increment(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="TestRegion Settlement 1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25, population_estimate=50,
            status=SettlementStatus.ACTIVE, inertia=2, footprint_cells=[(5, 5)],
        )
        w.regions[0].settlements = [s]
        matched_active = {1: 0}
        clusters = [{"component_id": 0, "centroid_x": 0.52, "centroid_y": 0.52, "population": 60, "cells": {(5, 5)}}]
        process_lifecycle(w, "TestRegion", {}, matched_active, clusters, set(), set(), source_turn=40)
        updated = w.regions[0].settlements[0]
        assert updated.inertia == 3
        assert updated.population_estimate == 60
        assert updated.last_seen_turn == 40

    def test_active_unmatched_enters_dissolving(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle, DISSOLVE_GRACE
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="S1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25,
            status=SettlementStatus.ACTIVE, inertia=1,
        )
        w.regions[0].settlements = [s]
        unmatched_active = {1}
        process_lifecycle(w, "TestRegion", {}, {}, [], set(), unmatched_active, source_turn=40)
        updated = w.regions[0].settlements[0]
        assert updated.status == SettlementStatus.DISSOLVING
        assert updated.grace_remaining == DISSOLVE_GRACE

    def test_dissolving_revived_on_match(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="S1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25,
            status=SettlementStatus.DISSOLVING, grace_remaining=1,
        )
        w.regions[0].settlements = [s]
        matched_active = {1: 0}
        clusters = [{"component_id": 0, "centroid_x": 0.5, "centroid_y": 0.5, "population": 30, "cells": {(5, 5)}}]
        process_lifecycle(w, "TestRegion", {}, matched_active, clusters, set(), set(), source_turn=40)
        updated = w.regions[0].settlements[0]
        assert updated.status == SettlementStatus.ACTIVE
        assert updated.inertia == 1

    def test_dissolving_tombstoned_after_grace(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="S1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25, peak_population=100,
            status=SettlementStatus.DISSOLVING, grace_remaining=1,
            footprint_cells=[(5, 5)],
        )
        w.regions[0].settlements = [s]
        unmatched_active = {1}
        events = process_lifecycle(w, "TestRegion", {}, {}, [], set(), unmatched_active, source_turn=40)
        assert len(w.regions[0].settlements) == 0
        assert len(w.dissolved_settlements) == 1
        tomb = w.dissolved_settlements[0]
        assert tomb.status == SettlementStatus.DISSOLVED
        assert tomb.dissolved_turn == 40
        assert tomb.inertia == 0
        assert tomb.footprint_cells == []
        assert any(e.event_type == "settlement_dissolved" for e in events)

    def test_naming_counter_never_reused(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle, CANDIDATE_PERSISTENCE
        w = self._make_world_stub()
        c1 = Settlement(region_name="TestRegion", last_seen_turn=0, candidate_passes=CANDIDATE_PERSISTENCE - 1)
        w.settlement_candidates = [c1]
        process_lifecycle(w, "TestRegion", {0: 0}, {}, [{"component_id": 0, "centroid_x": 0.5, "centroid_y": 0.5, "population": 50, "cells": {(5,5)}}], set(), set(), source_turn=30)
        first_name = w.regions[0].settlements[0].name
        first_id = w.regions[0].settlements[0].settlement_id
        c2 = Settlement(region_name="TestRegion", last_seen_turn=0, candidate_passes=CANDIDATE_PERSISTENCE - 1)
        w.settlement_candidates = [c2]
        process_lifecycle(w, "TestRegion", {0: 1}, {}, [{"component_id": 1, "centroid_x": 0.8, "centroid_y": 0.8, "population": 50, "cells": {(8,8)}}], set(), set(), source_turn=45)
        second = w.regions[0].settlements[1]
        assert second.settlement_id == first_id + 1
        assert second.name != first_name
        assert "Settlement 2" in second.name

    def test_inertia_cap_scales_with_age_and_population(self):
        from chronicler.settlements import compute_inertia_cap
        cap_young = compute_inertia_cap(age_turns=10, population=30)
        cap_old = compute_inertia_cap(age_turns=200, population=500)
        assert cap_old > cap_young
        assert cap_old <= 10  # MAX_INERTIA_CAP


class TestCandidateMatching:
    def test_candidate_match_by_proximity(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import match_settlements_to_clusters
        cand = Settlement(
            region_name="R", last_seen_turn=15,
            centroid_x=0.5, centroid_y=0.5, candidate_passes=1,
        )
        cluster = {
            "component_id": 0, "centroid_x": 0.52, "centroid_y": 0.52,
            "population": 10, "cells": {(5, 5)},
        }
        matched_s, _, _, _ = match_settlements_to_clusters(
            [cand], [cluster], source_turn=30
        )
        assert 0 in matched_s

    def test_candidate_higher_passes_wins(self):
        from chronicler.models import Settlement
        from chronicler.settlements import match_settlements_to_clusters
        c1 = Settlement(region_name="R", last_seen_turn=15, centroid_x=0.5, centroid_y=0.5, candidate_passes=3)
        c2 = Settlement(region_name="R", last_seen_turn=15, centroid_x=0.52, centroid_y=0.52, candidate_passes=1)
        cluster = {"component_id": 0, "centroid_x": 0.51, "centroid_y": 0.51, "population": 10, "cells": {(5, 5)}}
        matched_s, _, unmatched_s, _ = match_settlements_to_clusters(
            [c1, c2], [cluster], source_turn=30
        )
        assert 0 in matched_s  # c1 (index 0, passes=3) wins over c2 (index 1, passes=1)
        assert 1 in unmatched_s


class TestRunSettlementTick:
    def _make_world_with_snapshot(self, agent_positions_by_region=None):
        """Create a world with a mock agent snapshot."""
        import pyarrow as pa
        from chronicler.models import WorldState, Region

        w = WorldState(name="Test", seed=42, turn=15)
        regions = [
            Region(name="R0", terrain="plains", carrying_capacity=1000, resources="fertile", controller="Civ1"),
            Region(name="R1", terrain="coast", carrying_capacity=500, resources="maritime", controller="Civ2"),
        ]
        w.regions = regions

        if agent_positions_by_region is not None:
            ids, reg_col, xs, ys = [], [], [], []
            agent_id = 1
            for r_idx, positions in agent_positions_by_region.items():
                for x, y in positions:
                    ids.append(agent_id)
                    reg_col.append(r_idx)
                    xs.append(x)
                    ys.append(y)
                    agent_id += 1
            batch = pa.RecordBatch.from_arrays(
                [pa.array(ids, type=pa.uint32()),
                 pa.array(reg_col, type=pa.uint16()),
                 pa.array(xs, type=pa.float32()),
                 pa.array(ys, type=pa.float32())],
                names=["id", "region", "x", "y"],
            )
            w._agent_snapshot = batch
        else:
            w._agent_snapshot = None
        return w

    def test_off_mode_returns_empty_and_sets_diagnostics(self):
        from chronicler.settlements import run_settlement_tick
        w = self._make_world_with_snapshot(None)
        events = run_settlement_tick(w, source_turn=15, force=False)
        assert events == []
        diag = getattr(w, '_settlement_diagnostics', None)
        assert diag is not None
        assert diag["detection_executed"] is False
        assert diag["reason"] == "mode_off_no_snapshot"

    def test_non_detection_turn_skips(self):
        from chronicler.settlements import run_settlement_tick
        w = self._make_world_with_snapshot({0: [(0.5, 0.5)]})
        w.turn = 7
        events = run_settlement_tick(w, source_turn=7, force=False)
        assert events == []
        diag = w._settlement_diagnostics
        assert diag["detection_executed"] is False
        assert diag["reason"] == "not_detection_turn"

    def test_forced_detection_runs(self):
        from chronicler.settlements import run_settlement_tick
        w = self._make_world_with_snapshot({0: [(0.5, 0.5)]})
        w.turn = 7
        events = run_settlement_tick(w, source_turn=7, force=True)
        diag = w._settlement_diagnostics
        assert diag["detection_executed"] is True
        assert diag["reason"] == "forced_terminal"

    def test_detection_with_cluster_creates_candidate(self):
        from chronicler.settlements import run_settlement_tick, DENSITY_FLOOR
        positions = [(0.51 + i * 0.005, 0.51) for i in range(DENSITY_FLOOR + 1)]
        w = self._make_world_with_snapshot({0: positions})
        w.turn = 15
        run_settlement_tick(w, source_turn=15, force=False)
        assert len(w.settlement_candidates) == 1
        assert w.settlement_candidates[0].region_name == "R0"

    def test_diagnostics_schema_on_detection_pass(self):
        from chronicler.settlements import run_settlement_tick, DENSITY_FLOOR
        positions = [(0.51 + i * 0.005, 0.51) for i in range(DENSITY_FLOOR + 1)]
        w = self._make_world_with_snapshot({0: positions})
        w.turn = 15
        run_settlement_tick(w, source_turn=15, force=False)
        diag = w._settlement_diagnostics
        assert diag["detection_executed"] is True
        assert "matching_stats" in diag
        assert "per_region" in diag
        assert "global" in diag
        assert "source_turn" in diag
        assert diag["source_turn"] == 15

    def test_source_turn_stashed_on_world(self):
        from chronicler.settlements import run_settlement_tick, DENSITY_FLOOR
        positions = [(0.51 + i * 0.005, 0.51) for i in range(DENSITY_FLOOR + 1)]
        w = self._make_world_with_snapshot({0: positions})
        w.turn = 15
        run_settlement_tick(w, source_turn=15, force=False)
        assert getattr(w, '_settlement_source_turn', None) == 15


class TestIntegration:
    def test_run_turn_accepts_force_settlement_detection(self):
        """Verify run_turn signature accepts the new parameter without error."""
        import inspect
        from chronicler.simulation import run_turn
        sig = inspect.signature(run_turn)
        assert "force_settlement_detection" in sig.parameters

    def test_off_mode_snapshot_shape_stable(self):
        """TurnSnapshot has settlement fields at defaults in off-mode."""
        from chronicler.models import TurnSnapshot
        snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
        assert snap.settlement_count == 0
        assert snap.active_settlements == []
        assert snap.founded_this_turn == []
        assert snap.dissolved_this_turn == []
