"""Compare social/spatial outcomes of two agent-scale runs over seeds.

Inputs are result files from ``scripts/agent_scale_benchmark.py --social``
(JSON) or JSON lines printed by the ``scale_bench`` Rust example. Each input
holds one run per seed; the script prints, per metric, the mean and standard
deviation over seeds for both inputs, the difference of means, and Welch's t
(difference over its standard error). |t| < 2 means the difference is within
seed-to-seed noise.

    python scripts/agent_scale_compare.py exact.json fast.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics

BENCH_METRICS = (
    "bonds_per_1k_agent_turns",
    "marriages_per_1k_agent_turns",
    "same_civ_marriage_share",
    "same_faith_marriage_share",
    "final_mean_rel_count",
    "final_alive",
    "mean_hotspots_per_tick",
    "mean_max_cell_per_tick",
)

RUST_METRICS = (
    "bonds_per_1k_agent_turns",
    "marriages_per_1k_agent_turns",
    "same_faith_marriage_share",
    "married_adult_fraction",
    "mean_rel_count",
    "final_alive",
    "occupied_cell_fraction",
    "mean_hotspots_per_tick",
    "mean_max_cell_per_tick",
)


def _rust_row(d: dict) -> dict:
    turns = max(1, d["agent_turns"])
    faith = d["same_faith_marriages"] + d["cross_faith_marriages"]
    return {
        **d,
        "bonds_per_1k_agent_turns": 1e3 * d["bonds_formed"] / turns,
        "marriages_per_1k_agent_turns": 1e3 * d["marriages_formed"] / turns,
        "same_faith_marriage_share": d["same_faith_marriages"] / max(1, faith),
    }


def load(path: Path) -> tuple[list[dict], tuple[str, ...]]:
    text = path.read_text().strip()
    if text.startswith("{") and "\n{" in text:
        rows = [_rust_row(json.loads(line)) for line in text.splitlines() if line.strip()]
        return rows, RUST_METRICS
    data = json.loads(text)
    if "results" in data:
        rows = [r["social"] for r in data["results"] if "social" in r]
        return rows, BENCH_METRICS
    return [_rust_row(data)], RUST_METRICS


def welch_t(a: list[float], b: list[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    diff = statistics.mean(b) - statistics.mean(a)
    if se == 0:
        return 0.0 if diff == 0 else math.inf
    return diff / se


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("--labels", default="exact,fast")
    args = p.parse_args(argv)
    la, lb = args.labels.split(",")
    rows_a, metrics = load(args.a)
    rows_b, _ = load(args.b)
    print(f"seeds: {la} {len(rows_a)}, {lb} {len(rows_b)}\n")
    print(f"| metric | {la} mean (sd) | {lb} mean (sd) | diff | Welch t |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for m in metrics:
        a = [float(r[m]) for r in rows_a if m in r]
        b = [float(r[m]) for r in rows_b if m in r]
        if not a or not b:
            continue
        sd = lambda v: statistics.stdev(v) if len(v) > 1 else 0.0  # noqa: E731
        print(f"| {m} | {statistics.mean(a):.4g} ({sd(a):.2g}) | {statistics.mean(b):.4g} ({sd(b):.2g}) "
              f"| {statistics.mean(b) - statistics.mean(a):+.3g} | {welch_t(a, b):+.2f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
