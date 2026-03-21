"""M53b: Validation oracle runner.

Usage: python -m chronicler.validate --batch-dir <path> --oracles all
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

SCRUB_KEYS = {"generated_at"}

def scrubbed_equal(a: dict, b: dict) -> bool:
    """Compare two bundles ignoring transient metadata fields."""
    def _scrub(d):
        if isinstance(d, dict):
            return {k: _scrub(v) for k, v in d.items() if k not in SCRUB_KEYS}
        if isinstance(d, list):
            return [_scrub(x) for x in d]
        return d
    return _scrub(a) == _scrub(b)

def detect_communities(
    edges: list[tuple[int, int, int, int]],
    mem_sigs: dict[int, list[tuple[int, int, int]]],
) -> list[set[int]]:
    """Detect emergent social communities via deterministic label propagation.

    Parameters
    ----------
    edges:
        List of (agent_a, agent_b, bond_type, sentiment).
        BondType: Kin=0, Mentor=1, Friend=2, CoReligionist=3, Marriage=4,
                  Rival=5, ExileBond=6, Grudge=7.
    mem_sigs:
        Mapping agent_id → list of (event_type, turn, severity) memory tuples.

    Returns
    -------
    List of sets, each set being the agent_ids in a qualifying community.
    """
    if not edges:
        return []

    # --- Build undirected adjacency list ----------------------------------
    # adjacency: agent_id -> list of (neighbor_id, bond_type, sentiment)
    adjacency: dict[int, list[tuple[int, int, int]]] = {}
    all_nodes: set[int] = set()
    for a, b, bond_type, sentiment in edges:
        all_nodes.add(a)
        all_nodes.add(b)
        adjacency.setdefault(a, []).append((b, bond_type, sentiment))
        adjacency.setdefault(b, []).append((a, bond_type, sentiment))

    # Also include nodes that appear only in mem_sigs with no edges
    # (they stay in their own singleton label throughout)
    for node in mem_sigs:
        all_nodes.add(node)

    sorted_nodes = sorted(all_nodes)

    # --- Label propagation ------------------------------------------------
    # Initialize each node with its own label (= agent_id for determinism)
    labels: dict[int, int] = {n: n for n in sorted_nodes}

    for _ in range(20):
        changed = False
        for node in sorted_nodes:
            neighbors = adjacency.get(node, [])
            if not neighbors:
                continue
            # Count neighbor labels
            label_counts: dict[int, int] = {}
            for neighbor, _bt, _sent in neighbors:
                lbl = labels[neighbor]
                label_counts[lbl] = label_counts.get(lbl, 0) + 1
            # Most common label; tie-break by minimum label ID
            best_label = min(
                label_counts,
                key=lambda lbl: (-label_counts[lbl], lbl),
            )
            if best_label != labels[node]:
                labels[node] = best_label
                changed = True
        if not changed:
            break

    # --- Group by label ---------------------------------------------------
    groups: dict[int, set[int]] = {}
    for node, lbl in labels.items():
        groups.setdefault(lbl, set()).add(node)

    # --- Edge lookup sets for fast filtering ------------------------------
    # positive_non_kin_pairs: frozenset pairs with bond_type != 0 and sentiment > 0
    positive_non_kin: set[frozenset] = set()
    for a, b, bond_type, sentiment in edges:
        if bond_type != 0 and sentiment > 0:
            positive_non_kin.add(frozenset({a, b}))

    # --- Filter communities -----------------------------------------------
    result: list[set[int]] = []
    for members in groups.values():
        # Rule 1: size >= 5
        if len(members) < 5:
            continue

        # Rule 2: at least 1 non-kin positive edge within the community
        members_list = sorted(members)
        has_positive_non_kin = False
        for i, a in enumerate(members_list):
            for b in members_list[i + 1:]:
                if frozenset({a, b}) in positive_non_kin:
                    has_positive_non_kin = True
                    break
            if has_positive_non_kin:
                break
        if not has_positive_non_kin:
            continue

        # Rule 3: >= 80% of members share at least one common memory
        # signature with at least one other member.
        # Two agents share a memory if they have same event_type and turns
        # within 5 of each other.
        def _mem_key_set(agent_id: int) -> set[tuple[int, int]]:
            """Return set of (event_type, turn) for agent, bucketed by //5."""
            sigs = mem_sigs.get(agent_id, [])
            return {(et, t // 5) for et, t, _sev in sigs}

        mem_keys = {agent: _mem_key_set(agent) for agent in members}

        # An agent "has a shared memory" if its key set intersects with any
        # other member's key set.
        shared_count = 0
        for agent in members:
            my_keys = mem_keys[agent]
            if not my_keys:
                continue
            for other in members:
                if other == agent:
                    continue
                if my_keys & mem_keys[other]:
                    shared_count += 1
                    break

        if shared_count / len(members) < 0.80:
            continue

        result.append(members)

    return result


def compute_needs_diversity(
    needs_data: dict,
    events_data: list[dict],
    need_name: str,
    event_type: int = 1,
    need_divergence: float = 0.2,
    personality_tolerance: float = 0.1,
) -> dict:
    """Oracle 2: Validate that need levels influence agent behavioral event rates.

    Uses a matched-cohort approach: pairs agents that are identical on
    civ_affinity, region, occupation, and personality traits, but diverge on
    the specified need. Compares event rates between low-need and high-need
    halves of each pair.

    Parameters
    ----------
    needs_data:
        Dict of column lists from bulk FFI snapshot. Required keys:
        agent_id, <need_name>, civ_affinity, region, occupation,
        boldness, ambition, loyalty_trait.
    events_data:
        List of dicts with keys: agent_id, event_type, turn.
    need_name:
        The need column to test (e.g. "safety").
    event_type:
        Event type code to count (default 1 = migration).
    need_divergence:
        Minimum absolute difference in need value to qualify a pair
        (default 0.2).
    personality_tolerance:
        Maximum allowed difference in boldness, ambition, loyalty_trait
        for a pair to be considered matched (default 0.1).

    Returns
    -------
    dict with keys:
        pairs_found         – number of matched pairs
        low_need_event_rate – events per agent in low-need group
        high_need_event_rate – events per agent in high-need group
        rate_difference     – low - high (positive = low-need has more events)
    """
    # --- Build per-agent records -------------------------------------------
    ids = needs_data["agent_id"]
    need_vals = needs_data[need_name]
    civ_aff = needs_data["civ_affinity"]
    regions = needs_data["region"]
    occupations = needs_data["occupation"]
    boldness = needs_data["boldness"]
    ambition = needs_data["ambition"]
    loyalty = needs_data["loyalty_trait"]

    agents = []
    for i, aid in enumerate(ids):
        agents.append({
            "id": aid,
            "need": need_vals[i],
            "civ_affinity": civ_aff[i],
            "region": regions[i],
            "occupation": occupations[i],
            "boldness": boldness[i],
            "ambition": ambition[i],
            "loyalty": loyalty[i],
        })

    # --- Count events per agent --------------------------------------------
    event_counts: dict[int, int] = {}
    for ev in events_data:
        if ev["event_type"] == event_type:
            aid = ev["agent_id"]
            event_counts[aid] = event_counts.get(aid, 0) + 1

    # --- Find matched pairs ------------------------------------------------
    low_ids: list[int] = []
    high_ids: list[int] = []
    pairs_found = 0

    used: set[int] = set()
    for i, a in enumerate(agents):
        if a["id"] in used:
            continue
        for j in range(i + 1, len(agents)):
            b = agents[j]
            if b["id"] in used:
                continue
            # Must match on categorical context
            if (
                a["civ_affinity"] != b["civ_affinity"]
                or a["region"] != b["region"]
                or a["occupation"] != b["occupation"]
            ):
                continue
            # Must match on personality within tolerance
            if (
                abs(a["boldness"] - b["boldness"]) > personality_tolerance
                or abs(a["ambition"] - b["ambition"]) > personality_tolerance
                or abs(a["loyalty"] - b["loyalty"]) > personality_tolerance
            ):
                continue
            # Must diverge sufficiently on the target need
            if abs(a["need"] - b["need"]) <= need_divergence:
                continue
            # Pair qualifies
            pairs_found += 1
            used.add(a["id"])
            used.add(b["id"])
            if a["need"] < b["need"]:
                low_ids.append(a["id"])
                high_ids.append(b["id"])
            else:
                high_ids.append(a["id"])
                low_ids.append(b["id"])
            break  # each agent used in at most one pair

    # --- Compute event rates -----------------------------------------------
    def _rate(id_list: list[int]) -> float:
        if not id_list:
            return 0.0
        total = sum(event_counts.get(aid, 0) for aid in id_list)
        return total / len(id_list)

    low_rate = _rate(low_ids)
    high_rate = _rate(high_ids)

    return {
        "pairs_found": pairs_found,
        "low_need_event_rate": low_rate,
        "high_need_event_rate": high_rate,
        "rate_difference": low_rate - high_rate,
    }


def run_determinism_gate(batch_dir: Path) -> dict:
    """Run determinism smoke gate: 2 identical seeds must produce scrubbed-equal output."""
    # Implementation: load two bundles with same seed, compare
    pass

def run_oracles(batch_dir: Path, oracles: list[str]) -> dict:
    """Run specified oracles and return structured report."""
    results = {}
    if "all" in oracles or "determinism" in oracles:
        results["determinism"] = run_determinism_gate(batch_dir)
    return results

def main():
    parser = argparse.ArgumentParser(description="M53b validation oracle runner")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--oracles", nargs="+", default=["all"])
    args = parser.parse_args()
    report = run_oracles(args.batch_dir, args.oracles)
    json.dump(report, sys.stdout, indent=2)

if __name__ == "__main__":
    main()
