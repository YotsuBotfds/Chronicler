"""M53b: Validation oracle runner.

Usage: python -m chronicler.validate --batch-dir <path> --oracles all
"""
from __future__ import annotations
import argparse, json, statistics, sys
from collections import Counter, defaultdict
from math import ceil
from pathlib import Path

SCRUB_KEYS = {"generated_at"}
BUNDLE_FILENAME = "chronicle_bundle.json"
EVENT_NAME_TO_CODE = {
    "death": 0,
    "migration": 1,
    "rebellion": 2,
    "occupation_switch": 3,
    "loyalty_flip": 4,
    "birth": 5,
    "dissolution": 6,
}

def scrubbed_equal(a: dict, b: dict) -> bool:
    """Compare two bundles ignoring transient metadata fields."""
    def _scrub(d):
        if isinstance(d, dict):
            return {k: _scrub(v) for k, v in d.items() if k not in SCRUB_KEYS}
        if isinstance(d, list):
            return [_scrub(x) for x in d]
        return d
    return _scrub(a) == _scrub(b)


def load_bundles(batch_dir: Path) -> list[tuple[Path, dict]]:
    """Load chronicle bundles from a batch directory or bundle path."""
    if batch_dir.is_file():
        bundle_paths = [batch_dir]
    else:
        bundle_paths = sorted(batch_dir.rglob(BUNDLE_FILENAME))

    bundles: list[tuple[Path, dict]] = []
    for bundle_path in bundle_paths:
        try:
            bundles.append((bundle_path, json.loads(bundle_path.read_text(encoding="utf-8"))))
        except Exception as exc:
            raise RuntimeError(f"Failed to load bundle: {bundle_path}") from exc
    return bundles


def required_seed_count(total_seeds: int, fraction: float) -> int:
    """Return the minimum passing seed count for a fractional threshold."""
    if total_seeds <= 0:
        return 0
    return max(1, ceil(total_seeds * fraction))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_turns(sidecar_dir: Path, prefix: str) -> list[int]:
    turns = []
    for path in sorted(sidecar_dir.glob(f"{prefix}_turn_*.json")):
        try:
            turns.append(int(path.stem.rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return turns


def _choose_snapshot_turn(available_turns: list[int], target_turn: int) -> int | None:
    if not available_turns:
        return None
    return min(available_turns, key=lambda turn: (abs(turn - target_turn), turn))


def _load_graph_snapshot(sidecar_dir: Path, turn: int | None) -> dict | None:
    if turn is None:
        return None
    path = sidecar_dir / f"graph_turn_{turn:03d}.json"
    if not path.exists():
        return None
    raw = _read_json(path)
    return {
        "turn": raw["turn"],
        "edges": [tuple(edge) for edge in raw.get("edges", [])],
        "memory_signatures": {
            int(agent_id): [tuple(sig) for sig in sigs]
            for agent_id, sigs in raw.get("memory_signatures", {}).items()
        },
    }


def _load_needs_snapshot(sidecar_dir: Path, turn: int | None) -> dict | None:
    if turn is None:
        return None
    path = sidecar_dir / f"needs_turn_{turn:03d}.json"
    if not path.exists():
        return None
    return _read_json(path)


def _read_arrow_columns(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        import pyarrow.ipc as ipc
    except ImportError:
        return None
    table = ipc.open_file(path).read_all()
    return table.to_pydict()


def _load_canonical_graph_snapshot(seed_dir: Path, target_turn: int) -> dict | None:
    rel_cols = _read_arrow_columns(seed_dir / "validation_relationships.arrow")
    mem_cols = _read_arrow_columns(seed_dir / "validation_memory_signatures.arrow")
    if rel_cols is None and mem_cols is None:
        return None

    available_turns: set[int] = set()
    if rel_cols and rel_cols.get("turn"):
        available_turns.update(int(turn) for turn in rel_cols["turn"])
    if mem_cols and mem_cols.get("turn"):
        available_turns.update(int(turn) for turn in mem_cols["turn"])
    chosen_turn = _choose_snapshot_turn(sorted(available_turns), target_turn)
    if chosen_turn is None:
        return None

    edges: list[tuple[int, int, int, int]] = []
    if rel_cols:
        for idx, turn in enumerate(rel_cols.get("turn", [])):
            if int(turn) != chosen_turn:
                continue
            edges.append((
                int(rel_cols["agent_id"][idx]),
                int(rel_cols["target_id"][idx]),
                int(rel_cols["bond_type"][idx]),
                int(rel_cols["sentiment"][idx]),
            ))

    mem_sigs: dict[int, list[tuple[int, int, int]]] = {}
    if mem_cols:
        for idx, turn in enumerate(mem_cols.get("turn", [])):
            if int(turn) != chosen_turn:
                continue
            agent_id = int(mem_cols["agent_id"][idx])
            mem_sigs.setdefault(agent_id, []).append((
                int(mem_cols["event_type"][idx]),
                int(mem_cols["memory_turn"][idx]),
                int(mem_cols["valence_sign"][idx]),
            ))

    return {
        "turn": chosen_turn,
        "edges": edges,
        "memory_signatures": mem_sigs,
    }


def _load_canonical_needs_snapshot(seed_dir: Path, target_turn: int) -> dict | None:
    cols = _read_arrow_columns(seed_dir / "validation_needs.arrow")
    if not cols or not cols.get("turn"):
        return None
    chosen_turn = _choose_snapshot_turn(sorted({int(turn) for turn in cols["turn"]}), target_turn)
    if chosen_turn is None:
        return None

    filtered: dict[str, list] = {}
    for name, values in cols.items():
        if name == "turn":
            continue
        filtered[name] = [
            values[idx]
            for idx, turn in enumerate(cols["turn"])
            if int(turn) == chosen_turn
        ]
    return {"turn": chosen_turn, "columns": filtered}


def _load_validation_summary(seed_dir: Path) -> dict | None:
    path = seed_dir / "validation_summary.json"
    if not path.exists():
        return None
    return _read_json(path)


def _load_validation_community_summary(seed_dir: Path) -> dict | None:
    path = seed_dir / "validation_community_summary.json"
    if not path.exists():
        return None
    return _read_json(path)


def _load_agent_events(seed_dir: Path) -> list[dict]:
    path = seed_dir / "agent_events.arrow"
    if not path.exists():
        return []
    try:
        import pyarrow.ipc as ipc
    except ImportError:
        return []

    table = ipc.open_file(path).read_all()
    data = table.to_pydict()
    events: list[dict] = []
    event_names = data.get("event_type", [])
    for idx, event_name in enumerate(event_names):
        mapped_type = EVENT_NAME_TO_CODE.get(event_name)
        if mapped_type is None:
            continue
        events.append({
            "turn": data["turn"][idx],
            "agent_id": data["agent_id"][idx],
            "event_type": mapped_type,
        })
    return events


def _world_population_series(bundle: dict) -> list[int]:
    series: list[int] = []
    for snapshot in bundle.get("history", []):
        civ_stats = snapshot.get("civ_stats", {})
        series.append(sum(stats.get("population", 0) for stats in civ_stats.values()))
    return series


def _civ_trajectories(bundle: dict) -> list[dict]:
    histories: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {
            "population": [],
            "treasury": [],
            "stability": [],
            "territory": [],
            "prestige": [],
        }
    )
    for snapshot in bundle.get("history", []):
        for civ_name, civ_stats in snapshot.get("civ_stats", {}).items():
            histories[civ_name]["population"].append(civ_stats.get("population", 0))
            histories[civ_name]["treasury"].append(civ_stats.get("treasury", 0))
            histories[civ_name]["stability"].append(civ_stats.get("stability", 0))
            histories[civ_name]["territory"].append(len(civ_stats.get("regions", []) or []))
            histories[civ_name]["prestige"].append(civ_stats.get("prestige", 0))
    return [
        {"civ_name": civ_name, **signals}
        for civ_name, signals in histories.items()
    ]


def load_seed_runs(batch_dir: Path) -> list[dict]:
    """Load exported bundle + sidecar data for each seed in a batch."""
    runs: list[dict] = []
    for bundle_path, bundle in load_bundles(batch_dir):
        seed_dir = bundle_path.parent
        sidecar_dir = seed_dir / "validation_summary"
        total_turns = int(bundle.get("metadata", {}).get("total_turns", 0) or 0)
        target_turn = max(10, int(round(total_turns / 20.0) * 10)) if total_turns else 10
        graph_snapshot = _load_canonical_graph_snapshot(seed_dir, target_turn)
        if graph_snapshot is None and sidecar_dir.exists():
            graph_turn = _choose_snapshot_turn(_snapshot_turns(sidecar_dir, "graph"), target_turn)
            graph_snapshot = _load_graph_snapshot(sidecar_dir, graph_turn)
        needs_snapshot = _load_canonical_needs_snapshot(seed_dir, target_turn)
        if needs_snapshot is None and sidecar_dir.exists():
            needs_turn = _choose_snapshot_turn(_snapshot_turns(sidecar_dir, "needs"), target_turn)
            needs_snapshot = _load_needs_snapshot(sidecar_dir, needs_turn)
        runs.append({
            "bundle_path": bundle_path,
            "seed_dir": seed_dir,
            "seed": bundle.get("metadata", {}).get("seed"),
            "bundle": bundle,
            "events": _load_agent_events(seed_dir),
            "graph_snapshot": graph_snapshot,
            "needs_snapshot": needs_snapshot,
            "validation_summary": _load_validation_summary(seed_dir),
            "validation_community_summary": _load_validation_community_summary(seed_dir),
            "world_population": _world_population_series(bundle),
            "civ_trajectories": _civ_trajectories(bundle),
        })
    return runs


def _filter_events_window(events: list[dict], start_turn: int, window: int = 20) -> list[dict]:
    end_turn = start_turn + window
    return [
        event for event in events
        if start_turn <= int(event.get("turn", -1)) < end_turn
    ]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cohen_d(sample_a: list[float], sample_b: list[float]) -> float:
    if not sample_a or not sample_b:
        return 0.0
    mean_a = _mean(sample_a)
    mean_b = _mean(sample_b)
    if len(sample_a) == 1 and len(sample_b) == 1:
        return mean_a - mean_b
    var_a = statistics.pvariance(sample_a) if len(sample_a) > 1 else 0.0
    var_b = statistics.pvariance(sample_b) if len(sample_b) > 1 else 0.0
    pooled_num = ((len(sample_a) - 1) * var_a) + ((len(sample_b) - 1) * var_b)
    pooled_den = max(1, len(sample_a) + len(sample_b) - 2)
    pooled_var = pooled_num / pooled_den
    pooled_std = pooled_var ** 0.5
    if pooled_std == 0.0:
        return mean_a - mean_b
    return (mean_a - mean_b) / pooled_std


def _collapse_nearby_points(points: list[int], radius: int = 5) -> list[int]:
    if not points:
        return []
    points = sorted(points)
    collapsed = [points[0]]
    for point in points[1:]:
        if point - collapsed[-1] > radius:
            collapsed.append(point)
    return collapsed


def _trajectory_metric_series(trajectory: dict) -> dict[str, list[float]]:
    return {
        "population": [float(v) for v in trajectory.get("population", [])],
        "treasury": [float(v) for v in trajectory.get("treasury", [])],
        "stability": [float(v) for v in trajectory.get("stability", [])],
        "territory": [float(v) for v in trajectory.get("territory", [])],
        "prestige": [float(v) for v in trajectory.get("prestige", [])],
    }


def _trajectory_composite_series(trajectory: dict) -> list[float]:
    series_map = _trajectory_metric_series(trajectory)
    available: list[list[float]] = []
    for values in series_map.values():
        if not values:
            continue
        baseline = abs(values[0]) if values[0] != 0 else max(abs(v) for v in values) or 1.0
        available.append([value / baseline for value in values])
    if not available:
        return trajectory.get("population", [])
    length = min(len(series) for series in available)
    return [
        sum(series[idx] for series in available) / len(available)
        for idx in range(length)
    ]


def _agent_count_by_turn(validation_summary: dict | None) -> dict[int, int]:
    if not validation_summary:
        return {}
    counts: dict[int, int] = {}
    for turn_str, civ_aggs in validation_summary.get("agent_aggregates_by_turn", {}).items():
        counts[int(turn_str)] = sum(
            int(civ_data.get("agent_count", 0))
            for civ_data in civ_aggs.values()
        )
    return counts

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

    low_counts = [event_counts.get(aid, 0) for aid in low_ids]
    high_counts = [event_counts.get(aid, 0) for aid in high_ids]
    low_rate = _rate(low_ids)
    high_rate = _rate(high_ids)

    return {
        "pairs_found": pairs_found,
        "low_need_event_rate": low_rate,
        "high_need_event_rate": high_rate,
        "rate_difference": low_rate - high_rate,
        "effect_size": _cohen_d(low_counts, high_counts),
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
    satisfaction_tolerance: float = 0.10,
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
    satisfactions = agent_data.get("satisfaction", [0.0] * len(ids))

    demo: dict[int, tuple] = {}  # agent_id -> (civ_affinity, region, occupation, satisfaction)
    for i, aid in enumerate(ids):
        demo[aid] = (civ_aff[i], regions[i], occupations[i], satisfactions[i])

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
            member_civ, member_region, member_occ, member_sat = member_demo
            for ctrl_id in available_controls:
                if ctrl_id in used_controls:
                    continue
                ctrl_demo = demo.get(ctrl_id)
                if ctrl_demo is None:
                    continue
                ctrl_civ, ctrl_region, ctrl_occ, ctrl_sat = ctrl_demo
                if (
                    ctrl_civ == member_civ
                    and ctrl_region == member_region
                    and ctrl_occ == member_occ
                    and abs(float(ctrl_sat) - float(member_sat)) <= satisfaction_tolerance
                ):
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

    community_counts = [event_counts.get(aid, 0) for aid in community_ids_used]
    control_counts = [event_counts.get(aid, 0) for aid in control_ids_used]
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
        "effect_size": _cohen_d(control_counts, community_counts),
    }


def check_artifact_lifecycle(
    bundles: list[dict],
    num_civs: int = 4,
) -> dict:
    """Oracle 5: Validate artifact lifecycle rates and diversity.

    Sub-check A (bundle-only):
    - Creation rate per civ per 100 turns should be in 1-3 range.
    - No single artifact_type should exceed 50% of total.
    - Loss/destruction rate ((lost + destroyed) / total) should be 10-30%.

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
        loss_destruction_count         – int
        loss_destruction_rate          – float
        loss_destruction_rate_ok       – bool (rate in [0.10, 0.30])
        mule_artifact_count            – int
        total_artifacts                – int
    """
    total_artifacts = 0
    loss_destruction_count = 0
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
            if status in ("destroyed", "lost"):
                loss_destruction_count += 1

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

    # Loss/destruction rate: (lost + destroyed) / total
    if total_artifacts > 0:
        loss_destruction_rate = loss_destruction_count / total_artifacts
    else:
        loss_destruction_rate = 0.0

    loss_destruction_rate_ok = 0.10 <= loss_destruction_rate <= 0.30

    return {
        "creation_rate_per_civ_per_100": creation_rate,
        "creation_rate_ok": creation_rate_ok,
        "type_diversity_ok": type_diversity_ok,
        "loss_destruction_count": loss_destruction_count,
        "loss_destruction_rate": loss_destruction_rate,
        "loss_destruction_rate_ok": loss_destruction_rate_ok,
        "mule_artifact_count": mule_artifact_count,
        "total_artifacts": total_artifacts,
    }


def classify_civ_arc(trajectory: dict) -> str:
    """Oracle 6: Classify a civilization's trajectory into one of six emotional arc families.

    Based on Kurt Vonnegut's story shapes. Uses a thirds-based analysis of a
    smoothed population series to determine the dominant arc pattern.

    Parameters
    ----------
    trajectory:
        Dict with at least a "population" key containing a list of numeric values.

    Returns
    -------
    One of: "rags_to_riches", "riches_to_rags", "icarus", "oedipus",
    "cinderella", "man_in_a_hole", "stable".
    """
    pop = _trajectory_composite_series(trajectory)
    n = len(pop)
    if n == 0:
        return "stable"

    # Step 1: Smooth the population series with rolling mean
    window = max(10, n // 10)
    smoothed: list[float] = []
    for i in range(n):
        start = max(0, i - window + 1)
        chunk = pop[start: i + 1]
        smoothed.append(sum(chunk) / len(chunk))

    # Step 2: Split into thirds and compute mean for each third
    third = max(1, n // 3)
    first_mean = sum(smoothed[:third]) / third
    # Middle third: avoid overlap at boundaries for small series
    mid_start = third
    mid_end = 2 * third
    mid_chunk = smoothed[mid_start:mid_end] if mid_end > mid_start else [smoothed[mid_start]]
    middle_mean = sum(mid_chunk) / len(mid_chunk)
    last_chunk = smoothed[2 * third:] if smoothed[2 * third:] else [smoothed[-1]]
    last_mean = sum(last_chunk) / len(last_chunk)

    # Step 3: Stable check — all thirds within 20% of each other
    overall_mean = (first_mean + middle_mean + last_mean) / 3.0
    if overall_mean != 0.0:
        max_dev = max(
            abs(first_mean - overall_mean),
            abs(middle_mean - overall_mean),
            abs(last_mean - overall_mean),
        )
        if max_dev / abs(overall_mean) <= 0.20:
            return "stable"
    else:
        # All values are zero — treat as stable
        return "stable"

    # Step 4: Classify by pattern of thirds
    # rags_to_riches: monotone up
    if first_mean < middle_mean < last_mean:
        return "rags_to_riches"

    # riches_to_rags: monotone down
    if first_mean > middle_mean > last_mean:
        return "riches_to_rags"

    # icarus: up then down (middle is the peak)
    if middle_mean > first_mean and middle_mean > last_mean:
        return "icarus"

    # For the down-then-up family, distinguish by final level vs start
    if first_mean > middle_mean and last_mean > middle_mean:
        # cinderella: recovers to at least starting level
        if last_mean >= first_mean:
            return "cinderella"
        # man_in_a_hole: partial recovery but doesn't reach start
        # oedipus: down-up-down — requires last < first, use oedipus when
        # last < first (same condition as man_in_a_hole without further info)
        # Per spec: oedipus = middle < first AND middle < last AND last < first
        # man_in_a_hole = first > middle AND last > middle AND last < first
        # Both conditions are identical from thirds analysis — use oedipus as
        # the canonical name here for partial recovery with final < start.
        # Spec says oedipus: last < first; man_in_a_hole: last < first too.
        # Differentiate: oedipus ends lower (last < middle average baseline),
        # man_in_a_hole ends in middle recovery range.
        # Simple heuristic: if last is closer to first or above midpoint,
        # it's man_in_a_hole; if last is near the trough, it's oedipus.
        # Use midpoint of (first, middle) as divider:
        midpoint = (first_mean + middle_mean) / 2.0
        if last_mean >= midpoint:
            return "man_in_a_hole"
        else:
            return "oedipus"

    # Fallback
    return "stable"


def run_determinism_gate(batch_dir: Path) -> dict:
    """Run determinism smoke gate: 2 identical seeds must produce scrubbed-equal output."""
    bundles = load_bundles(batch_dir)
    by_seed: dict[int, list[tuple[Path, dict]]] = defaultdict(list)

    for bundle_path, bundle in bundles:
        seed = bundle.get("metadata", {}).get("seed")
        if seed is None:
            continue
        by_seed[int(seed)].append((bundle_path, bundle))

    duplicate_seed_groups = {
        seed: items for seed, items in by_seed.items() if len(items) >= 2
    }
    if not duplicate_seed_groups:
        return {
            "status": "SKIP",
            "reason": "no_duplicate_seed_pairs",
            "pairs_checked": 0,
            "duplicate_seeds": [],
            "mismatches": [],
        }

    pairs_checked = 0
    mismatches: list[dict] = []
    for seed, items in sorted(duplicate_seed_groups.items()):
        ref_path, ref_bundle = items[0]
        for other_path, other_bundle in items[1:]:
            pairs_checked += 1
            if not scrubbed_equal(ref_bundle, other_bundle):
                mismatches.append({
                    "seed": seed,
                    "reference": str(ref_path),
                    "candidate": str(other_path),
                })

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "reason": "bundles_match" if not mismatches else "scrubbed_bundle_mismatch",
        "pairs_checked": pairs_checked,
        "duplicate_seeds": sorted(duplicate_seed_groups.keys()),
        "mismatches": mismatches,
    }


def run_community_oracle(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    qualifying_seed_count = 0
    analyzed_seeds = 0
    per_seed: list[dict] = []

    for run in seed_runs:
        graph_snapshot = run.get("graph_snapshot")
        community_summary = run.get("validation_community_summary")
        if graph_snapshot:
            analyzed_seeds += 1
            communities = detect_communities(
                graph_snapshot["edges"],
                graph_snapshot["memory_signatures"],
            )
            qualifying = [community for community in communities if len(community) >= 5]
            if qualifying:
                qualifying_seed_count += 1
            per_seed.append({
                "seed": run.get("seed"),
                "snapshot_turn": graph_snapshot["turn"],
                "qualifying_communities": len(qualifying),
                "source": "raw",
            })
            continue
        if not community_summary:
            continue
        turns = sorted(int(turn) for turn in community_summary.get("community_summary_by_turn", {}).keys())
        if not turns:
            continue
        analyzed_seeds += 1
        chosen_turn = turns[-1]
        summary = community_summary["community_summary_by_turn"].get(str(chosen_turn), {})
        cluster_count = sum(int(region.get("cluster_count", 0)) for region in summary.values())
        structural_issue = any(float(region.get("max_cluster_fraction", 0.0)) > 0.05 for region in summary.values())
        if cluster_count > 0 and not structural_issue:
            qualifying_seed_count += 1
        per_seed.append({
            "seed": run.get("seed"),
            "snapshot_turn": chosen_turn,
            "qualifying_communities": cluster_count,
            "structural_issue": structural_issue,
            "source": "summary",
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_community_inputs"}

    required = required_seed_count(analyzed_seeds, 0.75)
    return {
        "status": "PASS" if qualifying_seed_count >= required else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "qualifying_seed_count": qualifying_seed_count,
        "per_seed": per_seed,
    }


def run_needs_oracle(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    analyzed_seeds = 0
    seeds_with_expected_sign = 0
    total_pairs = 0
    effect_sizes: list[float] = []
    per_seed: list[dict] = []
    need_event_configs = [
        ("autonomy", EVENT_NAME_TO_CODE["rebellion"]),
        ("social", EVENT_NAME_TO_CODE["migration"]),
        ("purpose", EVENT_NAME_TO_CODE["occupation_switch"]),
        ("material", EVENT_NAME_TO_CODE["migration"]),
        ("safety", EVENT_NAME_TO_CODE["migration"]),
    ]

    for run in seed_runs:
        needs_snapshot = run.get("needs_snapshot")
        if not needs_snapshot:
            continue
        analyzed_seeds += 1
        snapshot_turn = int(needs_snapshot["turn"])
        events_window = _filter_events_window(run["events"], snapshot_turn, window=20)
        candidates: list[tuple[str, int, dict]] = []
        for need_name, event_type in need_event_configs:
            if need_name not in needs_snapshot["columns"]:
                continue
            result = compute_needs_diversity(
                needs_snapshot["columns"],
                events_window,
                need_name,
                event_type=event_type,
            )
            candidates.append((need_name, event_type, result))

        best_need = None
        best_event_type = None
        best_result = {"pairs_found": 0, "rate_difference": 0.0, "effect_size": 0.0}
        if candidates:
            best_need, best_event_type, best_result = max(
                candidates,
                key=lambda item: (
                    item[2].get("pairs_found", 0),
                    abs(float(item[2].get("effect_size", 0.0))),
                    abs(float(item[2].get("rate_difference", 0.0))),
                ),
            )

        pairs_found = int(best_result.get("pairs_found", 0))
        rate_difference = float(best_result.get("rate_difference", 0.0))
        effect_size = abs(float(best_result.get("effect_size", 0.0)))
        total_pairs += pairs_found
        effect_sizes.append(effect_size)
        if pairs_found > 0 and rate_difference > 0 and effect_size > 0.10:
            seeds_with_expected_sign += 1
        per_seed.append({
            "seed": run.get("seed"),
            "snapshot_turn": snapshot_turn,
            "pairs_found": pairs_found,
            "need_name": best_need,
            "event_type": best_event_type,
            "rate_difference": rate_difference,
            "effect_size": round(effect_size, 4),
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_needs_sidecars"}

    required = required_seed_count(analyzed_seeds, 0.60)
    median_effect_size = statistics.median(effect_sizes) if effect_sizes else 0.0
    return {
        "status": "PASS" if seeds_with_expected_sign >= required and median_effect_size > 0.10 else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "seeds_with_expected_sign": seeds_with_expected_sign,
        "total_pairs": total_pairs,
        "median_effect_size": median_effect_size,
        "per_seed": per_seed,
    }


def run_era_oracle(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    analyzed_seeds = 0
    seeds_with_inflections = 0
    silent_collapse_seeds = 0
    per_seed: list[dict] = []

    for run in seed_runs:
        trajectories = run.get("civ_trajectories", [])
        if not trajectories:
            continue
        analyzed_seeds += 1
        inflection_points: list[int] = []
        silent_collapse = False
        signal_hits: Counter[str] = Counter()
        for trajectory in trajectories:
            for signal_name, series in _trajectory_metric_series(trajectory).items():
                if len(series) < 10:
                    continue
                points = detect_inflection_points(series)
                inflection_points.extend(points)
                signal_hits[signal_name] += len(points)
            pop_series = trajectory.get("population", [])
            if len(pop_series) >= 10:
                peak_value = max(pop_series)
                peak_turn = pop_series.index(peak_value)
                if peak_value > 0:
                    post_peak = pop_series[peak_turn:]
                    trough_value = min(post_peak) if post_peak else peak_value
                    if trough_value <= peak_value * 0.70:
                        trough_turn = peak_turn + post_peak.index(trough_value)
                        if not any(abs(point - trough_turn) <= 5 for point in inflection_points):
                            silent_collapse = True

        collapsed = _collapse_nearby_points(inflection_points, radius=5)
        if len(collapsed) >= 2:
            seeds_with_inflections += 1
        if silent_collapse:
            silent_collapse_seeds += 1
        per_seed.append({
            "seed": run.get("seed"),
            "inflection_count": len(collapsed),
            "inflection_turns": collapsed,
            "silent_collapse": silent_collapse,
            "signal_hits": dict(signal_hits),
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_history_series"}

    required = required_seed_count(analyzed_seeds, 0.80)
    max_silent = analyzed_seeds * 0.10
    return {
        "status": "PASS" if seeds_with_inflections >= required and silent_collapse_seeds <= max_silent else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "seeds_with_inflections": seeds_with_inflections,
        "silent_collapse_seeds": silent_collapse_seeds,
        "per_seed": per_seed,
    }


def run_cohort_oracle(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    analyzed_seeds = 0
    seeds_with_expected_direction = 0
    effect_sizes: list[float] = []
    per_seed: list[dict] = []

    for run in seed_runs:
        graph_snapshot = run.get("graph_snapshot")
        needs_snapshot = run.get("needs_snapshot")
        if not graph_snapshot or not needs_snapshot:
            continue
        communities = detect_communities(
            graph_snapshot["edges"],
            graph_snapshot["memory_signatures"],
        )
        if not communities:
            continue
        analyzed_seeds += 1
        snapshot_turn = int(graph_snapshot["turn"])
        events_window = _filter_events_window(run["events"], snapshot_turn, window=20)
        migration_result = compute_cohort_distinctiveness(
            communities,
            events_window,
            needs_snapshot["columns"],
            event_type=EVENT_NAME_TO_CODE["migration"],
        )
        rebellion_result = compute_cohort_distinctiveness(
            communities,
            events_window,
            needs_snapshot["columns"],
            event_type=EVENT_NAME_TO_CODE["rebellion"],
        )
        expected = (
            migration_result.get("effect_direction") == "community_lower"
            or rebellion_result.get("effect_direction") == "community_higher"
        )
        strongest_effect = max(
            abs(float(migration_result.get("effect_size", 0.0))),
            abs(float(rebellion_result.get("effect_size", 0.0))),
        )
        effect_sizes.append(strongest_effect)
        if expected and strongest_effect > 0.10:
            seeds_with_expected_direction += 1
        per_seed.append({
            "seed": run.get("seed"),
            "snapshot_turn": snapshot_turn,
            "communities_analyzed": migration_result.get("communities_analyzed", 0),
            "migration_effect_direction": migration_result.get("effect_direction"),
            "migration_effect_size": round(float(migration_result.get("effect_size", 0.0)), 4),
            "rebellion_effect_direction": rebellion_result.get("effect_direction"),
            "rebellion_effect_size": round(float(rebellion_result.get("effect_size", 0.0)), 4),
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_community_seed_pairs"}

    required = required_seed_count(analyzed_seeds, 0.60)
    median_effect_size = statistics.median(effect_sizes) if effect_sizes else 0.0
    return {
        "status": "PASS" if seeds_with_expected_direction >= required and median_effect_size > 0.10 else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "seeds_with_expected_direction": seeds_with_expected_direction,
        "median_effect_size": median_effect_size,
        "per_seed": per_seed,
    }


def run_artifact_oracle(seed_runs: list[dict]) -> dict:
    bundles = [run["bundle"] for run in seed_runs]
    if not bundles:
        return {"status": "SKIP", "reason": "no_bundles"}
    result = check_artifact_lifecycle(bundles)
    all_pass = (
        result["creation_rate_ok"]
        and result["type_diversity_ok"]
        and result["loss_destruction_rate_ok"]
    )
    any_pass = (
        result["creation_rate_ok"]
        or result["type_diversity_ok"]
        or result["loss_destruction_rate_ok"]
    )
    return {
        "status": "PASS" if all_pass else ("PARTIAL" if any_pass else "FAIL"),
        **result,
    }


def run_arc_oracle(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    arc_counts: dict[str, int] = {}
    arc_families: set[str] = set()
    per_seed: list[dict] = []
    seeds_with_three_types = 0

    for run in seed_runs:
        seed_arcs: list[str] = []
        for trajectory in run.get("civ_trajectories", []):
            population = trajectory.get("population", [])
            if len(population) < 10:
                continue
            arc = classify_civ_arc({"population": population})
            seed_arcs.append(arc)
            arc_counts[arc] = arc_counts.get(arc, 0) + 1
            if arc != "stable":
                arc_families.add(arc)
        distinct_types = len(set(seed_arcs))
        if distinct_types >= 3:
            seeds_with_three_types += 1
        per_seed.append({
            "seed": run.get("seed"),
            "arc_types": seed_arcs,
            "distinct_type_count": distinct_types,
        })

    total_civs = sum(arc_counts.values())
    if total_civs == 0:
        return {"status": "SKIP", "reason": "no_civ_trajectories"}

    dominance_violations = {
        arc: count / total_civs
        for arc, count in arc_counts.items()
        if count / total_civs > 0.40
    }
    families_ok = len(arc_families) >= 5
    dominance_ok = not dominance_violations
    diversity_ok = seeds_with_three_types >= required_seed_count(len(per_seed), 0.50)

    return {
        "status": "PASS" if families_ok and dominance_ok and diversity_ok else "FAIL",
        "families_found": sorted(arc_families),
        "family_count": len(arc_families),
        "arc_counts": dict(sorted(arc_counts.items())),
        "dominance_violations": dominance_violations,
        "seeds_with_three_types": seeds_with_three_types,
        "per_seed": per_seed,
    }


def run_regression_summary(seed_runs: list[dict]) -> dict:
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    satisfaction_means: list[float] = []
    satisfaction_stds: list[float] = []
    occupation_shares: list[float] = []
    final_ginis: list[float] = []
    final_civ_survivals: list[int] = []
    negative_treasury_runs = 0
    total_agent_turns = 0.0
    migration_events = 0
    rebellion_events = 0

    for run in seed_runs:
        validation_summary = run.get("validation_summary") or {}
        agent_aggregates = validation_summary.get("agent_aggregates_by_turn", {})
        if agent_aggregates:
            final_turn = max(int(turn) for turn in agent_aggregates.keys())
            final_aggregates = agent_aggregates[str(final_turn)]
            for civ_data in final_aggregates.values():
                satisfaction_means.append(float(civ_data.get("satisfaction_mean", 0.0)))
                satisfaction_stds.append(float(civ_data.get("satisfaction_std", 0.0)))
                count = max(1, int(civ_data.get("agent_count", 0)))
                for occ_count in civ_data.get("occupation_counts", {}).values():
                    occupation_shares.append(float(occ_count) / count)

            sampled_counts = _agent_count_by_turn(validation_summary)
            if sampled_counts:
                avg_agents = _mean(list(sampled_counts.values()))
                total_turns = int(run["bundle"].get("metadata", {}).get("total_turns", 0) or 0)
                total_agent_turns += avg_agents * total_turns

        final_snapshot = run["bundle"].get("history", [])[-1] if run["bundle"].get("history") else {}
        civ_stats = final_snapshot.get("civ_stats", {})
        alive_civs = 0
        for civ_data in civ_stats.values():
            if civ_data.get("alive"):
                alive_civs += 1
            final_ginis.append(float(civ_data.get("gini", 0.0)))
        final_civ_survivals.append(alive_civs)

        treasury_streaks: dict[str, int] = defaultdict(int)
        treasury_bad = False
        for snapshot in run["bundle"].get("history", []):
            for civ_name, civ_data in snapshot.get("civ_stats", {}).items():
                if float(civ_data.get("treasury", 0.0)) < 0:
                    treasury_streaks[civ_name] += 1
                    if treasury_streaks[civ_name] > 50:
                        treasury_bad = True
                else:
                    treasury_streaks[civ_name] = 0
        if treasury_bad:
            negative_treasury_runs += 1

        migration_events += sum(1 for event in run["events"] if event["event_type"] == EVENT_NAME_TO_CODE["migration"])
        rebellion_events += sum(1 for event in run["events"] if event["event_type"] == EVENT_NAME_TO_CODE["rebellion"])

    migration_rate = migration_events / total_agent_turns if total_agent_turns else 0.0
    rebellion_rate = rebellion_events / total_agent_turns if total_agent_turns else 0.0
    occupation_ok = all(0.0 < share <= 0.70 for share in occupation_shares) if occupation_shares else False
    satisfaction_mean_ok = 0.45 <= _mean(satisfaction_means) <= 0.65 if satisfaction_means else False
    satisfaction_std_ok = 0.10 <= _mean(satisfaction_stds) <= 0.25 if satisfaction_stds else False
    gini_ok = sum(1 for g in final_ginis if 0.30 <= g <= 0.70) >= max(1, int(len(final_ginis) * 0.20))
    civ_survival_ok = all(1 <= count <= 4 for count in final_civ_survivals) if final_civ_survivals else False
    treasury_ok = negative_treasury_runs <= max(1, int(len(seed_runs) * 0.30))

    overall_ok = (
        satisfaction_mean_ok
        and satisfaction_std_ok
        and (0.02 <= rebellion_rate <= 0.08 if total_agent_turns else False)
        and (0.05 <= migration_rate <= 0.15 if total_agent_turns else False)
        and gini_ok
        and occupation_ok
        and civ_survival_ok
        and treasury_ok
    )

    return {
        "status": "PASS" if overall_ok else "FAIL",
        "satisfaction_mean": round(_mean(satisfaction_means), 4) if satisfaction_means else None,
        "satisfaction_std": round(_mean(satisfaction_stds), 4) if satisfaction_stds else None,
        "migration_rate_per_agent_turn": round(migration_rate, 6),
        "rebellion_rate_per_agent_turn": round(rebellion_rate, 6),
        "gini_in_range_fraction": round(sum(1 for g in final_ginis if 0.30 <= g <= 0.70) / len(final_ginis), 4) if final_ginis else None,
        "occupation_ok": occupation_ok,
        "civ_survival_counts": final_civ_survivals,
        "treasury_bad_seed_count": negative_treasury_runs,
    }


def run_oracles(batch_dir: Path, oracles: list[str]) -> dict:
    """Run specified oracles and return a structured report."""
    selected = set(oracles)
    if "all" in selected:
        selected = {
            "determinism",
            "community",
            "needs",
            "era",
            "cohort",
            "artifacts",
            "arcs",
            "regression",
        }

    results: dict[str, dict] = {}
    seed_runs: list[dict] | None = None

    def ensure_seed_runs() -> list[dict]:
        nonlocal seed_runs
        if seed_runs is None:
            seed_runs = load_seed_runs(batch_dir)
        return seed_runs

    if "determinism" in selected:
        results["determinism"] = run_determinism_gate(batch_dir)
    if "community" in selected:
        results["community"] = run_community_oracle(ensure_seed_runs())
    if "needs" in selected:
        results["needs"] = run_needs_oracle(ensure_seed_runs())
    if "era" in selected:
        results["era"] = run_era_oracle(ensure_seed_runs())
    if "cohort" in selected:
        results["cohort"] = run_cohort_oracle(ensure_seed_runs())
    if "artifacts" in selected:
        results["artifacts"] = run_artifact_oracle(ensure_seed_runs())
    if "arcs" in selected:
        results["arcs"] = run_arc_oracle(ensure_seed_runs())
    if "regression" in selected:
        results["regression"] = run_regression_summary(ensure_seed_runs())

    return {
        "batch_dir": str(batch_dir),
        "oracles": sorted(selected),
        "results": results,
    }

def main():
    parser = argparse.ArgumentParser(description="M53b validation oracle runner")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--oracles", nargs="+", default=["all"])
    args = parser.parse_args()
    report = run_oracles(args.batch_dir, args.oracles)
    json.dump(report, sys.stdout, indent=2)

if __name__ == "__main__":
    main()
