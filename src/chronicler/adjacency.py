"""Region adjacency graph — computation and graph utilities."""
from __future__ import annotations

import math
from collections import deque

from chronicler.models import Region

SEA_ROUTE_TERRAINS = {"coast", "river"}
SEA_ROUTE_RESOURCES = {"maritime"}


def _build_adj_map(regions: list[Region]) -> dict[str, set[str]]:
    """Build adjacency map from region list."""
    return {r.name: set(r.adjacencies) for r in regions}


def shortest_path(
    regions: list[Region], from_name: str, to_name: str,
) -> list[str] | None:
    """BFS shortest path. Returns list of region names or None."""
    if from_name == to_name:
        return [from_name]
    adj = _build_adj_map(regions)
    visited: set[str] = {from_name}
    queue: deque[list[str]] = deque([[from_name]])
    while queue:
        path = queue.popleft()
        for neighbor in adj.get(path[-1], set()):
            if neighbor == to_name:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return None


def graph_distance(
    regions: list[Region], from_name: str, to_name: str,
) -> int:
    """Shortest path length, or -1 if disconnected."""
    path = shortest_path(regions, from_name, to_name)
    if path is None:
        return -1
    return len(path) - 1


def is_chokepoint(regions: list[Region], name: str) -> bool:
    """True if removing this region disconnects the graph (articulation point).

    Builds adjacency map manually excluding the target — never mutates Region objects.
    """
    if len(regions) <= 2:
        return False
    # Build adj map without the target node
    adj: dict[str, set[str]] = {}
    for r in regions:
        if r.name == name:
            continue
        adj[r.name] = {a for a in r.adjacencies if a != name}
    # BFS from first remaining node
    remaining_names = list(adj.keys())
    visited: set[str] = {remaining_names[0]}
    queue: deque[str] = deque([remaining_names[0]])
    while queue:
        current = queue.popleft()
        for neighbor in adj.get(current, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return len(visited) < len(remaining_names)


def connected_components(regions: list[Region]) -> list[list[str]]:
    """Return connected components as lists of region names."""
    adj = _build_adj_map(regions)
    visited: set[str] = set()
    components: list[list[str]] = []
    for r in regions:
        if r.name in visited:
            continue
        component: list[str] = []
        queue: deque[str] = deque([r.name])
        visited.add(r.name)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def _euclidean(r1: Region, r2: Region) -> float:
    """Euclidean distance between two regions with coordinates."""
    x1, y1 = r1.x or 0.0, r1.y or 0.0
    x2, y2 = r2.x or 0.0, r2.y or 0.0
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def _is_sea_route_eligible(region: Region) -> bool:
    return region.terrain in SEA_ROUTE_TERRAINS or region.resources in SEA_ROUTE_RESOURCES


def _add_edge(r1: Region, r2: Region) -> None:
    """Add symmetric adjacency edge."""
    if r2.name not in r1.adjacencies:
        r1.adjacencies.append(r2.name)
    if r1.name not in r2.adjacencies:
        r2.adjacencies.append(r1.name)


def compute_adjacencies(regions: list[Region], k: int = 3) -> None:
    """Compute adjacency graph in-place.

    Order: 1) preserve explicit, 2) sea routes, 3) k-nearest fills gaps, 4) symmetrize, 5) validate connectivity.
    """
    region_by_name = {r.name: r for r in regions}

    # Step 2: Sea route pass — eligible regions form clique
    sea_eligible = [r for r in regions if _is_sea_route_eligible(r)]
    for i, r1 in enumerate(sea_eligible):
        for r2 in sea_eligible[i + 1:]:
            _add_edge(r1, r2)

    # Step 3: k-nearest fills gaps (only for under-connected regions)
    for r in regions:
        if len(r.adjacencies) >= k:
            continue
        # Sort other regions by distance
        others = [(o, _euclidean(r, o)) for o in regions if o.name != r.name]
        others.sort(key=lambda x: x[1])
        needed = k - len(r.adjacencies)
        for o, _ in others[:needed]:
            if o.name not in r.adjacencies:
                _add_edge(r, o)

    # Step 4: Symmetrize (already done by _add_edge, but ensure)
    for r in regions:
        for adj_name in list(r.adjacencies):
            other = region_by_name.get(adj_name)
            if other and r.name not in other.adjacencies:
                other.adjacencies.append(r.name)

    # Step 5: Validate connectivity — repair if disconnected
    comps = connected_components(regions)
    while len(comps) > 1:
        # Connect nearest pair across first two components
        best_dist = float("inf")
        best_pair: tuple[Region, Region] | None = None
        for n1 in comps[0]:
            for n2 in comps[1]:
                d = _euclidean(region_by_name[n1], region_by_name[n2])
                if d < best_dist:
                    best_dist = d
                    best_pair = (region_by_name[n1], region_by_name[n2])
        if best_pair:
            _add_edge(best_pair[0], best_pair[1])
        comps = connected_components(regions)


def _find_articulation_points(adj: dict[str, list[str]]) -> set[str]:
    """Find articulation points using Tarjan's algorithm."""
    visited: set[str] = set()
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap: set[str] = set()
    timer = [0]

    def dfs(u: str) -> None:
        children = 0
        visited.add(u)
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in adj.get(u, []):
            if v not in visited:
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent[u] is None and children > 1:
                    ap.add(u)
                if parent[u] is not None and low[v] >= disc[u]:
                    ap.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node in adj:
        if node not in visited:
            parent[node] = None
            dfs(node)

    return ap


def classify_regions(adj: dict[str, list[str]]) -> dict[str, str]:
    """Classify regions by graph topology. Called once at world generation.

    - CROSSROADS: 3+ adjacencies (rich but exposed)
    - FRONTIER: exactly 1 adjacency (defensible but isolated)
    - CHOKEPOINT: articulation point (strategic trade toll)
    - STANDARD: everything else
    """
    articulation = _find_articulation_points(adj)
    roles: dict[str, str] = {}
    for name, neighbors in adj.items():
        degree = len(neighbors)
        if degree == 1:
            roles[name] = "frontier"
        elif name in articulation:
            roles[name] = "chokepoint"
        elif degree >= 3:
            roles[name] = "crossroads"
        else:
            roles[name] = "standard"
    return roles
