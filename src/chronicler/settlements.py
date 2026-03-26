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


from chronicler.models import Settlement, SettlementStatus, Event


def compute_inertia_cap(age_turns: int, population: int) -> int:
    """Compute max inertia for a settlement based on age and population."""
    return min(
        BASE_INERTIA_CAP + age_turns // AGE_BONUS_INTERVAL + population // POP_BONUS_INTERVAL,
        MAX_INERTIA_CAP,
    )


def _cluster_by_id(clusters: list[dict]) -> dict[int, dict]:
    """Index clusters by component_id for O(1) lookup."""
    return {c["component_id"]: c for c in clusters}


def process_lifecycle(
    world,
    region_name: str,
    matched_candidates: dict[int, int],
    matched_active: dict[int, int],
    clusters: list[dict],
    unclaimed_cluster_ids: set[int],
    unmatched_settlement_ids: set[int],
    source_turn: int,
) -> list[Event]:
    """Process lifecycle transitions for one region in one detection pass."""
    events: list[Event] = []
    cluster_map = _cluster_by_id(clusters)
    region_map = world.region_map

    if not hasattr(world, '_settlement_founded_this_turn'):
        world._settlement_founded_this_turn = []
    if not hasattr(world, '_settlement_dissolved_this_turn'):
        world._settlement_dissolved_this_turn = []
    if not hasattr(world, '_settlement_transitions'):
        world._settlement_transitions = []
    target_region = region_map.get(region_name)
    if target_region is None:
        return events

    # --- 1. Update matched active/dissolving settlements ---
    for s in target_region.settlements:
        if s.settlement_id in matched_active:
            c = cluster_map[matched_active[s.settlement_id]]
            s.centroid_x = c["centroid_x"]
            s.centroid_y = c["centroid_y"]
            s.footprint_cells = sorted(c["cells"])
            s.population_estimate = c["population"]
            s.peak_population = max(s.peak_population, c["population"])
            s.last_seen_turn = source_turn
            if s.status == SettlementStatus.DISSOLVING:
                old_status = s.status
                s.status = SettlementStatus.ACTIVE
                s.inertia = 1
                s.grace_remaining = 0
                world._settlement_transitions.append({
                    "settlement_id": s.settlement_id, "name": s.name,
                    "region_name": target_region.name,
                    "from_status": old_status.value, "to_status": s.status.value,
                    "reason": "revived_on_match",
                })
            else:
                cap = compute_inertia_cap(source_turn - s.founding_turn, s.population_estimate)
                s.inertia = min(s.inertia + 1, cap)

    # --- 2. Handle unmatched active/dissolving settlements ---
    to_remove = []
    for s in target_region.settlements:
        if s.settlement_id not in unmatched_settlement_ids:
            continue
        if s.status == SettlementStatus.ACTIVE:
            old_status = s.status
            s.inertia -= 1
            if s.inertia <= 0:
                s.status = SettlementStatus.DISSOLVING
                s.grace_remaining = DISSOLVE_GRACE
                s.inertia = 0
                world._settlement_transitions.append({
                    "settlement_id": s.settlement_id, "name": s.name,
                    "region_name": target_region.name,
                    "from_status": old_status.value, "to_status": s.status.value,
                    "reason": "entered_dissolving",
                })
        elif s.status == SettlementStatus.DISSOLVING:
            s.grace_remaining -= 1
            if s.grace_remaining <= 0:
                s.status = SettlementStatus.DISSOLVED
                s.dissolved_turn = source_turn
                s.inertia = 0
                s.grace_remaining = 0
                s.candidate_passes = 0
                s.footprint_cells = []
                world.dissolved_settlements.append(s)
                to_remove.append(s)
                controller = target_region.controller
                events.append(Event(
                    turn=source_turn,
                    event_type="settlement_dissolved",
                    actors=[controller] if controller else [],
                    description=f"The settlement of {s.name} in {target_region.name} has been abandoned",
                    importance=3,
                    source="agent",
                ))
                world._settlement_dissolved_this_turn.append(s.settlement_id)
                world._settlement_transitions.append({
                    "settlement_id": s.settlement_id, "name": s.name,
                    "region_name": target_region.name,
                    "from_status": "dissolving", "to_status": "dissolved",
                    "reason": "dissolved_grace_expired",
                })
    for s in to_remove:
        target_region.settlements.remove(s)

    # --- 3. Process matched candidates ---
    promoted_indices: set[int] = set()
    old_candidates = [c for c in world.settlement_candidates if c.region_name == region_name]
    other_candidates = [c for c in world.settlement_candidates if c.region_name != region_name]
    for cand_idx, comp_id in matched_candidates.items():
        if cand_idx >= len(old_candidates):
            continue
        cand = old_candidates[cand_idx]
        c = cluster_map.get(comp_id)
        if c is not None:
            cand.centroid_x = c["centroid_x"]
            cand.centroid_y = c["centroid_y"]
            cand.footprint_cells = sorted(c["cells"])
            cand.population_estimate = c["population"]
            cand.last_seen_turn = source_turn
        cand.candidate_passes += 1
        if cand.candidate_passes >= CANDIDATE_PERSISTENCE:
            cand.settlement_id = world.next_settlement_id
            world.next_settlement_id += 1
            seq = world.settlement_naming_counters.get(cand.region_name, 1)
            cand.name = f"{cand.region_name} Settlement {seq}"
            world.settlement_naming_counters[cand.region_name] = seq + 1
            cand.founding_turn = source_turn
            cand.status = SettlementStatus.ACTIVE
            cand.inertia = 1
            cand.candidate_passes = 0
            cand.peak_population = max(cand.peak_population, cand.population_estimate)
            target = region_map.get(cand.region_name)
            if target is not None:
                target.settlements.append(cand)
            promoted_indices.add(cand_idx)
            controller = target.controller if target else None
            events.append(Event(
                turn=source_turn,
                event_type="settlement_founded",
                actors=[controller] if controller else [],
                description=f"A settlement has formed in {cand.region_name}: {cand.name}",
                importance=4,
                source="agent",
            ))
            world._settlement_founded_this_turn.append(cand.settlement_id)
            world._settlement_transitions.append({
                "settlement_id": cand.settlement_id, "name": cand.name,
                "region_name": cand.region_name,
                "from_status": "candidate", "to_status": "active",
                "reason": "promoted_persistence",
            })

    # --- 4. Rebuild candidate list ---
    new_candidates = []
    for idx, cand in enumerate(old_candidates):
        if idx in promoted_indices:
            continue
        if idx in matched_candidates:
            new_candidates.append(cand)

    # --- 5. Create new candidates from unclaimed clusters ---
    for comp_id in sorted(unclaimed_cluster_ids):
        c = cluster_map.get(comp_id)
        if c is None:
            continue
        new_candidates.append(Settlement(
            region_name=region_name,
            last_seen_turn=source_turn,
            centroid_x=c["centroid_x"],
            centroid_y=c["centroid_y"],
            footprint_cells=sorted(c["cells"]),
            population_estimate=c["population"],
            candidate_passes=1,
        ))

    world.settlement_candidates = other_candidates + new_candidates
    return events


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
