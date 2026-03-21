"""M53 Baseline Metrics Collector.

Reads bundles + sidecars from a batch run and extracts baseline metrics.
Also collects current constant values from source files.

Usage: PYTHONPATH=src python scripts/m53_baseline.py --batch-dir output/m53/baseline
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def collect_rust_constants(agent_rs: Path) -> dict:
    """Extract all [CALIBRATE M53] tagged constants from agent.rs."""
    constants = {}
    text = agent_rs.read_text()
    for line in text.splitlines():
        if "[CALIBRATE M53]" not in line:
            continue
        # Match: pub const NAME: TYPE = VALUE;
        m = re.match(r"\s*pub const (\w+):\s*\w+\s*=\s*(.+?)\s*;", line)
        if m:
            name, value = m.group(1), m.group(2)
            # Parse numeric value
            try:
                if "." in value:
                    constants[name] = float(value)
                else:
                    constants[name] = int(value)
            except ValueError:
                constants[name] = value
    return constants


def collect_python_constants(src_dir: Path) -> dict:
    """Collect [CALIBRATE] tagged constants from Python source files."""
    constants = {}
    for py_file in [
        src_dir / "action_engine.py",
        src_dir / "agent_bridge.py",
        src_dir / "artifacts.py",
        src_dir / "dynasties.py",
        src_dir / "narrative.py",
    ]:
        if not py_file.exists():
            continue
        for line in py_file.read_text().splitlines():
            if "CALIBRATE" not in line:
                continue
            m = re.match(r"\s*(\w+)\s*=\s*(.+?)(?:\s*#.*)?$", line)
            if m:
                name, value = m.group(1), m.group(2).strip()
                try:
                    constants[name] = eval(value)  # noqa: S307 — safe for numeric literals
                except Exception:
                    constants[name] = value
    return constants


def extract_bundle_metrics(bundle_path: Path) -> dict:
    """Extract key metrics from a single bundle."""
    with open(bundle_path) as f:
        bundle = json.load(f)

    metrics = {}
    ws = bundle.get("world_state", {})
    meta = bundle.get("metadata", {})
    history = bundle.get("history", [])

    # Basic sim info
    metrics["seed"] = meta.get("seed", 0)
    metrics["total_turns"] = meta.get("total_turns", len(history))

    # Civ survival
    civs = ws.get("civilizations", [])
    alive_civs = sum(1 for c in civs if len(c.get("regions", [])) > 0)
    metrics["civs_alive"] = alive_civs
    metrics["civs_total"] = len(civs)

    # Artifacts
    artifacts = ws.get("artifacts", [])
    metrics["artifact_count"] = len(artifacts)
    metrics["artifact_destroyed"] = sum(1 for a in artifacts if a.get("status") == "destroyed")
    metrics["artifact_mule"] = sum(1 for a in artifacts if a.get("mule_origin"))

    # Great persons
    gps = meta.get("great_persons", ws.get("great_persons", []))
    metrics["great_person_count"] = len(gps)

    # Named events
    named_events = bundle.get("named_events", [])
    metrics["named_event_count"] = len(named_events)

    return metrics


def extract_sidecar_metrics(sidecar_dir: Path) -> dict:
    """Extract metrics from validation sidecar files."""
    metrics = {
        "edges_by_turn": {},
        "mem_sig_agents_by_turn": {},
        "satisfaction_by_turn": {},
    }

    for f in sorted(sidecar_dir.glob("graph_turn_*.json")):
        turn = int(f.stem.split("_")[-1])
        data = json.loads(f.read_text())
        metrics["edges_by_turn"][turn] = len(data.get("edges", []))
        metrics["mem_sig_agents_by_turn"][turn] = len(data.get("memory_signatures", {}))

    agent_counts = {}
    for f in sorted(sidecar_dir.glob("aggregate_turn_*.json")):
        turn = int(f.stem.split("_")[-1])
        data = json.loads(f.read_text())
        agg = data.get("aggregates", data)
        if agg:
            sat_means = [v["satisfaction_mean"] for v in agg.values() if "satisfaction_mean" in v]
            if sat_means:
                metrics["satisfaction_by_turn"][turn] = round(sum(sat_means) / len(sat_means), 4)
            agent_counts[turn] = sum(v.get("agent_count", 0) for v in agg.values())

    metrics["agent_counts_by_turn"] = agent_counts
    # Find population peak and extinction turn
    if agent_counts:
        metrics["agent_peak"] = max(agent_counts.values())
        metrics["agent_peak_turn"] = max(agent_counts, key=agent_counts.get)
        alive_turns = [t for t, c in agent_counts.items() if c > 0]
        metrics["agent_extinction_turn"] = max(alive_turns) + 10 if alive_turns else 0

    return metrics


def main():
    parser = argparse.ArgumentParser(description="M53 Baseline Metrics Collector")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--output", default="tuning/m53_baseline.yaml", type=Path)
    args = parser.parse_args()

    # Collect constants
    project_root = Path(__file__).parent.parent
    rust_constants = collect_rust_constants(project_root / "chronicler-agents" / "src" / "agent.rs")
    python_constants = collect_python_constants(project_root / "src" / "chronicler")

    # Collect bundle metrics
    bundle_files = sorted(args.batch_dir.rglob("chronicle_bundle.json"))
    print(f"Found {len(bundle_files)} bundles")

    all_metrics = []
    for bf in bundle_files:
        m = extract_bundle_metrics(bf)
        # Check for sidecar
        sidecar_dir = bf.parent / "validation_summary"
        if sidecar_dir.exists():
            m["sidecar"] = extract_sidecar_metrics(sidecar_dir)
        all_metrics.append(m)

    # Aggregate
    if not all_metrics:
        print("No bundles found!")
        sys.exit(1)

    n = len(all_metrics)
    agg = {
        "seeds": n,
        "civs_alive_mean": round(sum(m["civs_alive"] for m in all_metrics) / n, 2),
        "civs_alive_min": min(m["civs_alive"] for m in all_metrics),
        "civs_alive_max": max(m["civs_alive"] for m in all_metrics),
        "artifact_count_mean": round(sum(m["artifact_count"] for m in all_metrics) / n, 2),
        "great_person_count_mean": round(sum(m["great_person_count"] for m in all_metrics) / n, 2),
        "named_event_count_mean": round(sum(m["named_event_count"] for m in all_metrics) / n, 2),
    }

    # Sidecar aggregates — use PEAK data (population collapses at default constants)
    sat_peaks = []
    edge_peaks = []
    mem_peaks = []
    extinction_turns = []
    agent_peaks = []
    for m in all_metrics:
        sc = m.get("sidecar", {})
        if sc.get("satisfaction_by_turn"):
            # Use first non-zero turn (population still alive)
            alive_sats = {t: v for t, v in sc["satisfaction_by_turn"].items()
                         if sc.get("agent_counts_by_turn", {}).get(t, 0) > 0}
            if alive_sats:
                sat_peaks.append(sum(alive_sats.values()) / len(alive_sats))
        if sc.get("edges_by_turn"):
            edge_peaks.append(max(sc["edges_by_turn"].values()))
        if sc.get("mem_sig_agents_by_turn"):
            mem_peaks.append(max(sc["mem_sig_agents_by_turn"].values()))
        if sc.get("agent_extinction_turn"):
            extinction_turns.append(sc["agent_extinction_turn"])
        if sc.get("agent_peak"):
            agent_peaks.append(sc["agent_peak"])
    if sat_peaks:
        agg["satisfaction_while_alive_mean"] = round(sum(sat_peaks) / len(sat_peaks), 4)
    if edge_peaks:
        agg["edges_peak_mean"] = round(sum(edge_peaks) / len(edge_peaks), 1)
    if mem_peaks:
        agg["memory_agents_peak_mean"] = round(sum(mem_peaks) / len(mem_peaks), 1)
    if extinction_turns:
        agg["agent_extinction_turn_mean"] = round(sum(extinction_turns) / len(extinction_turns), 1)
        agg["agent_extinction_turn_min"] = min(extinction_turns)
        agg["agent_extinction_turn_max"] = max(extinction_turns)
    if agent_peaks:
        agg["agent_peak_mean"] = round(sum(agent_peaks) / len(agent_peaks), 1)

    # Write YAML-ish output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write("# M53 Baseline — all constants at default values\n")
        f.write(f"# Generated from {n} seeds\n\n")

        f.write("## Aggregate Metrics\n")
        for k, v in agg.items():
            f.write(f"{k}: {v}\n")

        f.write("\n## Rust Constants (agent.rs)\n")
        for k, v in sorted(rust_constants.items()):
            f.write(f"{k}: {v}\n")

        f.write("\n## Python Constants\n")
        for k, v in sorted(python_constants.items()):
            f.write(f"{k}: {v}\n")

    print(f"\nBaseline written to {args.output}")
    print(f"  Seeds: {n}")
    print(f"  Civs alive (mean): {agg['civs_alive_mean']}")
    print(f"  Artifacts (mean): {agg['artifact_count_mean']}")
    if sat_peaks:
        print(f"  Satisfaction while alive (mean): {agg['satisfaction_while_alive_mean']}")
    if edge_peaks:
        print(f"  Edges peak (mean): {agg['edges_peak_mean']}")
    if extinction_turns:
        print(f"  Agent extinction turn (mean): {agg['agent_extinction_turn_mean']}")
    if agent_peaks:
        print(f"  Agent population peak (mean): {agg['agent_peak_mean']}")


if __name__ == "__main__":
    main()
