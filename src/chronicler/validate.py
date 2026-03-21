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


def detect_inflection_points(
    series: list[float],
    smoothing_window: int = 5,
) -> list[int]:
    """Oracle 3: Detect era inflection points in a time series.

    Uses smoothed-derivative magnitude detection with auto-calibrated
    threshold based on the derivative's own standard deviation. An inflection
    point is a turn where the local slope of the smoothed series exceeds
    3.0 × std of the derivative, indicating a structural shift
    (collapse, rapid growth, recovery) rather than noise.

    Nearby candidate points within ``smoothing_window`` turns are collapsed
    to the single highest-magnitude point to avoid duplicate reporting of
    the same transition.

    Parameters
    ----------
    series:
        List of numeric values (e.g. population per turn).
    smoothing_window:
        Rolling mean window size for smoothing (default 5).

    Returns
    -------
    List of turn indices where inflection points occur (large-magnitude
    slope changes in the smoothed series). Returns an empty list for
    series that are noisy but structurally stable.
    """
    n = len(series)
    if n < smoothing_window + 1:
        return []

    # Step 1: Rolling mean smoothing
    smoothed: list[float] = []
    for i in range(n):
        start = max(0, i - smoothing_window + 1)
        window = series[start : i + 1]
        smoothed.append(sum(window) / len(window))

    # Step 2: First derivative (diff of smoothed values)
    deriv: list[float] = [smoothed[i + 1] - smoothed[i] for i in range(n - 1)]

    # Step 3: Auto-calibrated threshold — 3.0 × std of first derivative.
    # Using derivative std (not series std) keeps the threshold proportional
    # to typical turn-to-turn slope variation, making detection sensitive to
    # structural shifts but blind to slow drift or noise.
    mean_d = sum(deriv) / len(deriv)
    var_d = sum((d - mean_d) ** 2 for d in deriv) / len(deriv)
    std_d = var_d ** 0.5
    threshold = 3.0 * std_d

    if threshold == 0.0:
        # Flat series — no inflection points possible
        return []

    # Step 4: Find points where |derivative| exceeds threshold.
    # Skip the first (smoothing_window - 1) steps to avoid warm-up artifacts
    # from the rolling mean operating on an incomplete window at series start.
    # These represent large structural shifts in the series.
    candidates: list[tuple[int, float]] = []  # (turn_index, abs_magnitude)
    warmup = smoothing_window - 1
    for i, d in enumerate(deriv):
        if i < warmup:
            continue
        if abs(d) > threshold:
            # Turn index in original series: derivative at i spans [i, i+1]
            candidates.append((i + 1, abs(d)))

    if not candidates:
        return []

    # Step 5: Collapse nearby candidates within smoothing_window into single peak
    # Sort by index (already in order), merge clusters.
    inflection_points: list[int] = []
    cluster_start = candidates[0][0]
    cluster_best_idx = candidates[0][0]
    cluster_best_mag = candidates[0][1]

    for turn_idx, mag in candidates[1:]:
        if turn_idx - cluster_start <= smoothing_window:
            # Same cluster — keep best magnitude
            if mag > cluster_best_mag:
                cluster_best_mag = mag
                cluster_best_idx = turn_idx
        else:
            inflection_points.append(cluster_best_idx)
            cluster_start = turn_idx
            cluster_best_idx = turn_idx
            cluster_best_mag = mag

    inflection_points.append(cluster_best_idx)
    return inflection_points


def compute_cohort_distinctiveness(
    communities: list[set[int]],
    events_data: list[dict],
    agent_data: dict,
    event_type: int = 1,
) -> dict:
    """Oracle 4: Validate that community membership anchors behavior.

    Compares migration (or other behavioral event) rates between community
    members and a matched control group of non-community agents drawn from
    the same demographic profile (civ_affinity, region, occupation).

    Parameters
    ----------
    communities:
        List of sets of agent_ids, as returned by detect_communities().
    events_data:
        List of dicts with keys: agent_id, event_type, turn.
    agent_data:
        Dict of column lists. Required keys:
        agent_id, civ_affinity, region, occupation.
    event_type:
        Event type code to count (default 1 = migration).

    Returns
    -------
    dict with keys:
        communities_analyzed  – number of communities processed
        community_event_rate  – mean migration rate across all community members
        control_event_rate    – mean migration rate across matched control agents
        effect_direction      – "community_lower", "community_higher", or "equal"
    """
    # --- Build per-agent demographic lookup --------------------------------
    ids = agent_data["agent_id"]
    civ_aff = agent_data["civ_affinity"]
    regions = agent_data["region"]
    occupations = agent_data["occupation"]

    demo: dict[int, tuple] = {}  # agent_id -> (civ_affinity, region, occupation)
    for i, aid in enumerate(ids):
        demo[aid] = (civ_aff[i], regions[i], occupations[i])

    # --- Count events per agent --------------------------------------------
    event_counts: dict[int, int] = {}
    for ev in events_data:
        if ev["event_type"] == event_type:
            aid = ev["agent_id"]
            event_counts[aid] = event_counts.get(aid, 0) + 1

    # --- Identify all community members ------------------------------------
    all_community_ids: set[int] = set()
    for community in communities:
        all_community_ids.update(community)

    # Non-community agents available as controls
    all_agent_ids = set(ids)
    non_community_ids = all_agent_ids - all_community_ids

    # --- For each community, find matched control agents -------------------
    community_ids_used: list[int] = []
    control_ids_used: list[int] = []
    communities_analyzed = 0

    for community in communities:
        communities_analyzed += 1
        members = list(community)

        # Build demographic profile: bucket counts for majority matching
        # Strategy: for each community member, find a non-community agent
        # with the exact same (civ_affinity, region, occupation).
        available_controls = list(non_community_ids)
        used_controls: set[int] = set()

        for member_id in members:
            member_demo = demo.get(member_id)
            if member_demo is None:
                continue
            for ctrl_id in available_controls:
                if ctrl_id in used_controls:
                    continue
                ctrl_demo = demo.get(ctrl_id)
                if ctrl_demo == member_demo:
                    used_controls.add(ctrl_id)
                    break

        community_ids_used.extend(members)
        control_ids_used.extend(used_controls)

    # --- Compute event rates -----------------------------------------------
    def _rate(id_list: list[int]) -> float:
        if not id_list:
            return 0.0
        total = sum(event_counts.get(aid, 0) for aid in id_list)
        return total / len(id_list)

    community_rate = _rate(community_ids_used)
    control_rate = _rate(control_ids_used)

    if community_rate < control_rate:
        direction = "community_lower"
    elif community_rate > control_rate:
        direction = "community_higher"
    else:
        direction = "equal"

    return {
        "communities_analyzed": communities_analyzed,
        "community_event_rate": community_rate,
        "control_event_rate": control_rate,
        "effect_direction": direction,
    }


def check_artifact_lifecycle(
    bundles: list[dict],
    num_civs: int = 4,
) -> dict:
    """Oracle 5: Validate artifact lifecycle rates and diversity.

    Sub-check A (bundle-only):
    - Creation rate per civ per 100 turns should be in 1-3 range.
    - No single artifact_type should exceed 50% of total.
    - Destruction rate (destroyed / total) should be 10-30%.

    Parameters
    ----------
    bundles:
        List of bundle dicts, each containing world_state.artifacts and
        metadata.total_turns.
    num_civs:
        Number of civilizations (used as denominator for creation rate).

    Returns
    -------
    dict with keys:
        creation_rate_per_civ_per_100  – float
        creation_rate_ok               – bool (rate in [1, 3])
        type_diversity_ok              – bool (no single type > 50%)
        destruction_rate               – float
        destruction_rate_ok            – bool (rate in [0.10, 0.30])
        mule_artifact_count            – int
        total_artifacts                – int
    """
    total_artifacts = 0
    destroyed_count = 0
    mule_artifact_count = 0
    total_turns_sum = 0
    type_counts: dict[str, int] = {}

    for bundle in bundles:
        artifacts = bundle.get("world_state", {}).get("artifacts", [])
        total_turns = bundle.get("metadata", {}).get("total_turns", 0)
        total_turns_sum += total_turns

        for art in artifacts:
            total_artifacts += 1
            artifact_type = art.get("artifact_type", "unknown")
            type_counts[artifact_type] = type_counts.get(artifact_type, 0) + 1

            status = art.get("status", "active")
            if status == "destroyed":
                destroyed_count += 1

            if art.get("mule_origin", False):
                mule_artifact_count += 1

    # Creation rate: artifacts per civ per 100 turns
    if num_civs > 0 and total_turns_sum > 0:
        creation_rate = total_artifacts / (num_civs * total_turns_sum / 100.0)
    else:
        creation_rate = 0.0

    creation_rate_ok = 1.0 <= creation_rate <= 3.0

    # Type diversity: no single type > 50% of total
    if total_artifacts > 0:
        max_type_fraction = max(type_counts.values()) / total_artifacts
        type_diversity_ok = max_type_fraction <= 0.5
    else:
        type_diversity_ok = True

    # Destruction rate: destroyed / total
    if total_artifacts > 0:
        destruction_rate = destroyed_count / total_artifacts
    else:
        destruction_rate = 0.0

    destruction_rate_ok = 0.10 <= destruction_rate <= 0.30

    return {
        "creation_rate_per_civ_per_100": creation_rate,
        "creation_rate_ok": creation_rate_ok,
        "type_diversity_ok": type_diversity_ok,
        "destruction_rate": destruction_rate,
        "destruction_rate_ok": destruction_rate_ok,
        "mule_artifact_count": mule_artifact_count,
        "total_artifacts": total_artifacts,
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
