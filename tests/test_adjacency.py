"""Tests for region adjacency graph utilities."""
from chronicler.adjacency import (
    compute_adjacencies, shortest_path, graph_distance,
    is_chokepoint, connected_components,
)
from chronicler.models import Region


def _make_regions(names_and_adj: dict[str, list[str]]) -> list[Region]:
    """Helper: create regions with given adjacencies."""
    return [
        Region(name=n, terrain="plains", carrying_capacity=50,
               resources="fertile", adjacencies=adj)
        for n, adj in names_and_adj.items()
    ]


def test_shortest_path_direct():
    regions = _make_regions({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    assert shortest_path(regions, "A", "C") == ["A", "B", "C"]


def test_shortest_path_no_path():
    regions = _make_regions({"A": ["B"], "B": ["A"], "C": []})
    assert shortest_path(regions, "A", "C") is None


def test_graph_distance():
    regions = _make_regions({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    assert graph_distance(regions, "A", "C") == 2
    assert graph_distance(regions, "A", "A") == 0


def test_graph_distance_accepts_prebuilt_adjacency_map():
    adj = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}
    assert shortest_path(adj, "A", "C") == ["A", "B", "C"]
    assert graph_distance(adj, "A", "C") == 2


def test_graph_distance_disconnected():
    regions = _make_regions({"A": [], "B": []})
    assert graph_distance(regions, "A", "B") == -1


def test_is_chokepoint():
    # B is the only connection between A and C
    regions = _make_regions({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    assert is_chokepoint(regions, "B") is True
    assert is_chokepoint(regions, "A") is False


def test_connected_components_single():
    regions = _make_regions({"A": ["B"], "B": ["A"]})
    comps = connected_components(regions)
    assert len(comps) == 1


def test_connected_components_multiple():
    regions = _make_regions({"A": ["B"], "B": ["A"], "C": ["D"], "D": ["C"]})
    comps = connected_components(regions)
    assert len(comps) == 2


def test_compute_adjacencies_k_nearest():
    """Regions without adjacencies get k-nearest neighbors."""
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0),
        Region(name="B", terrain="plains", carrying_capacity=50,
               resources="fertile", x=1.0, y=0.0),
        Region(name="C", terrain="plains", carrying_capacity=50,
               resources="fertile", x=2.0, y=0.0),
    ]
    compute_adjacencies(regions, k=2)
    assert "B" in regions[0].adjacencies
    assert "A" in regions[1].adjacencies
    assert "C" in regions[1].adjacencies


def test_compute_adjacencies_preserves_explicit():
    """Scenario-authored adjacencies are preserved."""
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0, adjacencies=["C"]),
        Region(name="B", terrain="plains", carrying_capacity=50,
               resources="fertile", x=1.0, y=0.0),
        Region(name="C", terrain="plains", carrying_capacity=50,
               resources="fertile", x=10.0, y=10.0, adjacencies=["A"]),
    ]
    compute_adjacencies(regions, k=2)
    # A's explicit adjacency to C preserved even though C is far away
    assert "C" in regions[0].adjacencies


def test_compute_adjacencies_sea_routes():
    """Coastal/river regions connect to each other."""
    regions = [
        Region(name="Coast1", terrain="coast", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0),
        Region(name="Coast2", terrain="coast", carrying_capacity=50,
               resources="fertile", x=100.0, y=100.0),
        Region(name="Inland", terrain="plains", carrying_capacity=50,
               resources="fertile", x=1.0, y=0.0),
    ]
    compute_adjacencies(regions, k=2)
    assert "Coast2" in regions[0].adjacencies  # sea route
    assert "Coast1" in regions[1].adjacencies  # sea route


def test_compute_adjacencies_connectivity_repair():
    """Disconnected regions get connected."""
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0),
        Region(name="B", terrain="plains", carrying_capacity=50,
               resources="fertile", x=100.0, y=100.0),
    ]
    compute_adjacencies(regions, k=1)
    # Must be connected despite k=1 and large distance
    comps = connected_components(regions)
    assert len(comps) == 1


def test_compute_adjacencies_k_nearest_fills_gaps_only():
    """k-nearest only adds edges for under-connected regions."""
    regions = [
        Region(name="Hub", terrain="coast", carrying_capacity=50,
               resources="fertile", x=5.0, y=5.0),
        Region(name="Coast2", terrain="coast", carrying_capacity=50,
               resources="fertile", x=6.0, y=5.0),
        Region(name="Coast3", terrain="coast", carrying_capacity=50,
               resources="fertile", x=7.0, y=5.0),
        Region(name="Inland", terrain="plains", carrying_capacity=50,
               resources="fertile", x=5.0, y=6.0),
    ]
    compute_adjacencies(regions, k=3)
    # Inland should still get connections from k-nearest
    assert len([r for r in regions if r.name == "Inland"][0].adjacencies) >= 1
