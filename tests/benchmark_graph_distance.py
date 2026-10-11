"""Small same-input benchmark for the graph_distance BFS change.

Run with ``python tests/benchmark_graph_distance.py``. The baseline is the
pre-change graph_distance body: call shortest_path(), then take path length.
"""

from pathlib import Path
import sys
import timeit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.adjacency import graph_distance, shortest_path


def baseline_graph_distance(adj: dict[str, set[str]], source: str, target: str) -> int:
    path = shortest_path(adj, source, target)
    return -1 if path is None else len(path) - 1


def run_case(size: int, number: int) -> None:
    names = [f"R{i}" for i in range(size)]
    adj = {
        name: {names[(i + offset) % size] for offset in (-2, -1, 1, 2)}
        for i, name in enumerate(names)
    }
    queries = [(source, target) for source in names for target in names]
    for source, target in queries:
        assert baseline_graph_distance(adj, source, target) == graph_distance(adj, source, target)

    def baseline_batch() -> int:
        return sum(baseline_graph_distance(adj, source, target) for source, target in queries)

    def current_batch() -> int:
        return sum(graph_distance(adj, source, target) for source, target in queries)

    baseline = min(timeit.repeat(baseline_batch, repeat=3, number=number)) / number
    current = min(timeit.repeat(current_batch, repeat=3, number=number)) / number
    print(
        f"{size} regions, {len(queries)} same queries: "
        f"baseline {baseline * 1000:.3f} ms, "
        f"current {current * 1000:.3f} ms, "
        f"speedup {baseline / current:.2f}x"
    )


if __name__ == "__main__":
    run_case(8, 100)
    run_case(32, 10)
