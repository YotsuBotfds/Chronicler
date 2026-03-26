# src/chronicler/settlements.py
"""M56a: Settlement detection, matching, lifecycle, and diagnostics."""
import logging
import math

logger = logging.getLogger(__name__)

# --- Calibration constants [CALIBRATE M61b] ---
GRID_SIZE = 10
DENSITY_FLOOR = 5
DENSITY_FRACTION = 0.03
SETTLEMENT_DETECTION_INTERVAL = 15
MAX_MATCH_DISTANCE = 0.25
CANDIDATE_PERSISTENCE = 2
BASE_INERTIA_CAP = 3
AGE_BONUS_INTERVAL = 50
POP_BONUS_INTERVAL = 100
MAX_INERTIA_CAP = 10
DISSOLVE_GRACE = 2


def assign_cell(x: float, y: float) -> tuple[int, int]:
    """Map agent (x, y) in [0, 1) to grid cell (cx, cy)."""
    cx = min(int(x * GRID_SIZE), GRID_SIZE - 1)
    cy = min(int(y * GRID_SIZE), GRID_SIZE - 1)
    return (cx, cy)


def build_density_grid(agent_positions: list[tuple[float, float]]) -> dict[tuple[int, int], int]:
    """Count agents per grid cell. Returns {(cx, cy): count}."""
    grid: dict[tuple[int, int], int] = {}
    for x, y in agent_positions:
        cell = assign_cell(x, y)
        grid[cell] = grid.get(cell, 0) + 1
    return grid


def find_dense_cells(
    grid: dict[tuple[int, int], int],
    region_agent_count: int,
) -> set[tuple[int, int]]:
    """Return set of cells exceeding density threshold."""
    threshold = max(DENSITY_FLOOR, region_agent_count * DENSITY_FRACTION)
    return {cell for cell, count in grid.items() if count >= threshold}


def find_connected_components(
    dense_cells: set[tuple[int, int]],
) -> list[set[tuple[int, int]]]:
    """Find connected components of dense cells using 8-neighbor adjacency.

    Scans in row-major order (cy=0..GRID_SIZE-1, cx=0..GRID_SIZE-1) for
    deterministic component discovery order.
    """
    if not dense_cells:
        return []

    visited: set[tuple[int, int]] = set()
    components: list[set[tuple[int, int]]] = []

    for cy in range(GRID_SIZE):
        for cx in range(GRID_SIZE):
            if (cx, cy) not in dense_cells or (cx, cy) in visited:
                continue
            component: set[tuple[int, int]] = set()
            queue = [(cx, cy)]
            visited.add((cx, cy))
            while queue:
                cur_x, cur_y = queue.pop(0)
                component.add((cur_x, cur_y))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = cur_x + dx, cur_y + dy
                        if (nx, ny) in dense_cells and (nx, ny) not in visited:
                            visited.add((nx, ny))
                            queue.append((nx, ny))
            components.append(component)

    return components


def extract_clusters(
    agent_positions: list[tuple[float, float]],
) -> list[dict]:
    """Run full detection pipeline on a list of (x, y) positions.

    Returns list of cluster dicts, each with keys:
        - component_id: int (discovery order)
        - population: int
        - centroid_x: float
        - centroid_y: float
        - cells: set[tuple[int, int]]
    """
    if not agent_positions:
        return []

    grid = build_density_grid(agent_positions)
    dense = find_dense_cells(grid, region_agent_count=len(agent_positions))
    if not dense:
        return []

    components = find_connected_components(dense)

    cell_to_component: dict[tuple[int, int], int] = {}
    for comp_id, cells in enumerate(components):
        for cell in cells:
            cell_to_component[cell] = comp_id

    comp_sum_x: list[float] = [0.0] * len(components)
    comp_sum_y: list[float] = [0.0] * len(components)
    comp_pop: list[int] = [0] * len(components)

    for x, y in agent_positions:
        cell = assign_cell(x, y)
        comp_id = cell_to_component.get(cell)
        if comp_id is not None:
            comp_sum_x[comp_id] += x
            comp_sum_y[comp_id] += y
            comp_pop[comp_id] += 1

    clusters = []
    for comp_id, cells in enumerate(components):
        pop = comp_pop[comp_id]
        if pop == 0:
            continue
        clusters.append({
            "component_id": comp_id,
            "population": pop,
            "centroid_x": comp_sum_x[comp_id] / pop,
            "centroid_y": comp_sum_y[comp_id] / pop,
            "cells": cells,
        })
    return clusters


def _centroid_distance(s, c) -> float:
    dx = s.centroid_x - c["centroid_x"]
    dy = s.centroid_y - c["centroid_y"]
    return math.sqrt(dx * dx + dy * dy)


def match_settlements_to_clusters(
    settlements: list,
    clusters: list[dict],
    source_turn: int,
) -> tuple[dict[int, int], dict[int, int], set[int], set[int]]:
    """Two-pass matching is handled by the caller. This does Pass 1 (or Pass 2).

    Returns:
        matched_s: {settlement_id (or candidate_index): cluster component_id}
        matched_c: {cluster component_id: settlement_id (or candidate_index)}
        unmatched_s: set of settlement_ids (or candidate_indices) not matched
        unmatched_c: set of cluster component_ids not matched
    """
    pairs = []
    for s_idx, s in enumerate(settlements):
        s_key = s.settlement_id if s.settlement_id != 0 else s_idx
        for c in clusters:
            dist = _centroid_distance(s, c)
            if dist <= MAX_MATCH_DISTANCE:
                if s.settlement_id != 0:
                    age = source_turn - s.founding_turn
                    pairs.append((dist, -age, s.settlement_id, c["component_id"], s_key))
                else:
                    pairs.append((dist, -s.candidate_passes, s_idx, c["component_id"], s_idx))

    pairs.sort(key=lambda p: (p[0], p[1], p[2], p[3]))

    matched_s: dict[int, int] = {}
    matched_c: dict[int, int] = {}
    used_s: set[int] = set()
    used_c: set[int] = set()

    for _, _, s_key, c_key, s_key_out in pairs:
        if s_key_out in used_s or c_key in used_c:
            continue
        matched_s[s_key_out] = c_key
        matched_c[c_key] = s_key_out
        used_s.add(s_key_out)
        used_c.add(c_key)

    all_s_keys = {s.settlement_id if s.settlement_id != 0 else i for i, s in enumerate(settlements)}
    all_c_keys = {c["component_id"] for c in clusters}
    unmatched_s = all_s_keys - used_s
    unmatched_c = all_c_keys - used_c

    return matched_s, matched_c, unmatched_s, unmatched_c
