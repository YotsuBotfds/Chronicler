"""M53 oracle 1 as its text specifies it: community oracle method 2.

The M53 spec (docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md,
section 6.2, oracle 1) defines a community as a group of 5+ agents with
mutual bonds and shared memories, found by deterministic label propagation
over "friend + co-religionist + kin edges weighted by sentiment", kept when
at least 80% of its members share a memory ``(event_type, turn,
valence_sign)`` and when it holds a non-kin positive-valence edge ("pure
dynastic/family clumps do not count"). Acceptance: qualifying communities in
at least 75% of seeds, 3-15 communities a seed at steady state (turns
100-500), median size 5-12, no community above 5% of its region's
population. docs/integration/spec-communities.md records the reading of
each clause.

Method 1 (``validation_io.detect_communities``) propagates over every edge
(rivals and grudges included), unweighted and across regions, tests its
kin-only exclusion against code 0 (the native mentor; kin is 5), keeps a
group when 80% of members share a 5-turn memory bucket with another member,
and passes a seed with any community of 5+. Its communities hold about nine
in ten living agents. Method 1 is kept, unchanged, as the legacy component:
the in-run community summary of the validation sidecar is built with it.

The detection here (``detect_oracle1_communities``):

* **Edges**: bonds of type friend, co-religionist or kin (the native codes,
  ``ffi_constants.BOND_TYPES``) with positive sentiment, between two living
  agents of the same region at the snapshot (the needs sidecar's region
  column). An edge's weight is the sum of the sentiments of the bond slots
  that join the pair (a symmetric bond has a slot on each side).
* **Label propagation** (as methods 1 and PR #62's informational variant):
  labels start as agent ids; at most 20 sweeps over agents in ascending id
  order, each taking the label of largest summed edge weight among its
  neighbours, ties to the smaller label. Every edge joins one region, so a
  community lies in one region.
* **Kept** when it has at least 5 members, when one of its edges joins two
  members by a non-kin bond (friend or co-religionist), and when one memory
  tuple ``(event_type, memory_turn, valence_sign)``, matched exactly, is
  held by at least 80% of its members.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from .ffi_constants import BOND_CO_RELIGIONIST, BOND_FRIEND, BOND_KIN

COMMUNITY_LEGACY_METHOD_VERSION = 1
COMMUNITY_ORACLE_METHOD_VERSION = 2
COMMUNITY_METHOD_VERSIONS = (COMMUNITY_LEGACY_METHOD_VERSION, COMMUNITY_ORACLE_METHOD_VERSION)

ORACLE1_EDGE_BONDS = frozenset({BOND_FRIEND, BOND_CO_RELIGIONIST, BOND_KIN})
ORACLE1_NON_KIN_BONDS = ORACLE1_EDGE_BONDS - {BOND_KIN}
ORACLE1_MIN_SIZE = 5
# At least 80% of members hold one memory tuple: shared * 5 >= size * 4.
ORACLE1_SHARED_MEMORY_NUMERATOR = 4
ORACLE1_SHARED_MEMORY_DENOMINATOR = 5
ORACLE1_LABEL_SWEEPS = 20
ORACLE1_STEADY_STATE_FIRST_TURN = 100
# Acceptance criteria (spec, oracle 1).
ORACLE1_SEED_FRACTION_MIN = 0.75
ORACLE1_COUNT_BAND = (3.0, 15.0)
ORACLE1_MEDIAN_SIZE_BAND = (5.0, 12.0)
ORACLE1_REGION_SHARE_MAX = 0.05
# The smallest region population in which a community of ORACLE1_MIN_SIZE
# can stay within ORACLE1_REGION_SHARE_MAX (5 / 0.05).
ORACLE1_REGION_POPULATION_FOR_MIN_SIZE = 100

LEGACY_NOTE = (
    "method 1: label propagation over every edge, unweighted and across regions; kin-only "
    "exclusion against code 0 (the native mentor); a seed passes with any community of 5+"
)
SPEC_LABEL = "M53 oracle 1 as specified (method 2)"
_CACHE_KEY = "_oracle1_communities"


def detect_oracle1_communities(edges, regions: dict[int, int], memory_signatures: dict) -> list[set[int]]:
    """Communities of one snapshot as M53 oracle 1 specifies them (module
    docstring). ``edges``: (agent, target, bond type, sentiment) rows of the
    relationship sidecar; ``regions``: agent id -> region of every living
    agent (the needs sidecar); ``memory_signatures``: agent id -> list of
    (event type, memory turn, valence sign). Communities in ascending order
    of their label."""
    weights: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    non_kin_pairs: set[tuple[int, int]] = set()
    for a, b, bond_type, sentiment in edges:
        a, b, bond_type, sentiment = int(a), int(b), int(bond_type), int(sentiment)
        if bond_type not in ORACLE1_EDGE_BONDS or sentiment <= 0 or a == b:
            continue
        region = regions.get(a)
        if region is None or regions.get(b) != region:
            continue
        weights[a][b] += sentiment
        weights[b][a] += sentiment
        if bond_type in ORACLE1_NON_KIN_BONDS:
            non_kin_pairs.add((a, b) if a < b else (b, a))
    nodes = sorted(weights)
    labels = {node: node for node in nodes}
    for _sweep in range(ORACLE1_LABEL_SWEEPS):
        changed = False
        for node in nodes:
            score: dict[int, int] = defaultdict(int)
            for other, weight in weights[node].items():
                score[labels[other]] += weight
            best = min(score, key=lambda label: (-score[label], label))
            if best != labels[node]:
                labels[node] = best
                changed = True
        if not changed:
            break
    groups: dict[int, set[int]] = defaultdict(set)
    for node, label in labels.items():
        groups[label].add(node)
    out = []
    for label in sorted(groups):
        members = groups[label]
        size = len(members)
        if size < ORACLE1_MIN_SIZE:
            continue
        if not any((a, b) in non_kin_pairs for a in members for b in weights[a] if a < b and b in members):
            continue
        held: Counter = Counter()
        for agent in members:
            held.update({(int(e), int(t), int(v)) for e, t, v in memory_signatures.get(agent, ())})
        shared = max(held.values(), default=0)
        if shared * ORACLE1_SHARED_MEMORY_DENOMINATOR < size * ORACLE1_SHARED_MEMORY_NUMERATOR:
            continue
        out.append(members)
    return out


# ---------------------------------------------------------------------------
# Snapshots of a seed run, indexed once per run
# ---------------------------------------------------------------------------

def _turn_rows(columns: dict | None) -> dict[int, list[int]]:
    rows: dict[int, list[int]] = defaultdict(list)
    if columns and columns.get("turn"):
        for index, turn in enumerate(columns["turn"]):
            rows[int(turn)].append(index)
    return rows


def _cache(run: dict) -> dict:
    """Per-run index of the sidecar rows by turn and the communities found
    so far; rebuilt when the run's columns are other objects."""
    key = (id(run.get("relationship_columns")), id(run.get("memory_columns")), id(run.get("needs_columns")))
    cache = run.get(_CACHE_KEY)
    if not isinstance(cache, dict) or cache.get("key") != key:
        cache = {
            "key": key,
            "relationships": _turn_rows(run.get("relationship_columns")),
            "memories": _turn_rows(run.get("memory_columns")),
            "needs": _turn_rows(run.get("needs_columns")),
            "snapshots": {},
        }
        run[_CACHE_KEY] = cache
    return cache


def oracle1_turns(run: dict) -> list[int]:
    """Turns with a graph snapshot (relationships or memories) and a needs
    snapshot: the turns the detection can be run on."""
    cache = _cache(run)
    graph = set(cache["relationships"]) | set(cache["memories"])
    return sorted(graph & set(cache["needs"]))


def oracle1_snapshot(run: dict, turn: int) -> dict | None:
    """``{"turn", "communities", "regions"}`` of one turn of a seed run (None
    without a needs snapshot or a graph snapshot at that turn). ``regions``
    maps every living agent to its region."""
    cache = _cache(run)
    snapshots = cache["snapshots"]
    if turn in snapshots:
        return snapshots[turn]
    needs_rows = cache["needs"].get(turn)
    if not needs_rows or (turn not in cache["relationships"] and turn not in cache["memories"]):
        snapshots[turn] = None
        return None
    needs = run["needs_columns"]
    regions = {int(needs["agent_id"][i]): int(needs["region"][i]) for i in needs_rows}
    edges = []
    rel = run.get("relationship_columns") or {}
    for i in cache["relationships"].get(turn, ()):
        edges.append((rel["agent_id"][i], rel["target_id"][i], rel["bond_type"][i], rel["sentiment"][i]))
    signatures: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    mem = run.get("memory_columns") or {}
    for i in cache["memories"].get(turn, ()):
        signatures[int(mem["agent_id"][i])].append(
            (int(mem["event_type"][i]), int(mem["memory_turn"][i]), int(mem["valence_sign"][i])))
    snapshot = {"turn": turn, "communities": detect_oracle1_communities(edges, regions, signatures),
                "regions": regions}
    snapshots[turn] = snapshot
    return snapshot


def oracle1_needs_columns(run: dict, turn: int) -> dict | None:
    """The needs sidecar's columns at ``turn`` (``_needs_snapshot_from_columns``'s
    ``columns``, from the per-run index)."""
    rows = _cache(run)["needs"].get(turn)
    if not rows:
        return None
    return {name: [values[i] for i in rows] for name, values in run["needs_columns"].items() if name != "turn"}


def oracle1_communities(run: dict, turn: int) -> list[set[int]]:
    """Method 2's communities at ``turn`` (none without the snapshots)."""
    snapshot = oracle1_snapshot(run, turn)
    return snapshot["communities"] if snapshot is not None else []


# ---------------------------------------------------------------------------
# The spec component and method 2's result
# ---------------------------------------------------------------------------

def _quantile(values: list, fraction: float):
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)] if ordered else None


def _r(value, digits: int = 4):
    return round(value, digits) if value is not None else None


def spec_component(seed_runs: list[dict]) -> dict:
    """Method 2's spec component: the communities of
    ``detect_oracle1_communities`` at every steady-state snapshot (turns >=
    100 with graph and needs sidecars; a run shorter than that uses all of
    them, as method 1 does) judged by oracle 1's acceptance criteria:

    * ``seed_fraction``: a community at some snapshot in at least 75% of
      the analyzed seeds;
    * ``community_count``: the mean over seeds of each seed's mean count
      per snapshot within 3-15;
    * ``median_size``: the median size of every community found (all
      snapshots of all seeds) within 5-12;
    * ``region_share``: no community above 5% of its region's population,
      the living agents of the region at the snapshot (the needs sidecar's
      rows). Every edge joins one region, so each community has one."""
    from .validation_io import _sample_turns, required_seed_count

    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}
    per_seed = []
    sizes: list[int] = []
    shares: list[float] = []
    region_populations: list[int] = []
    member_shares: list[float] = []
    above = 0
    in_large_regions = 0
    snapshot_total = 0
    for run in seed_runs:
        turns = _sample_turns(oracle1_turns(run), min_turn=ORACLE1_STEADY_STATE_FIRST_TURN)
        if not turns:
            continue
        counts = []
        seed_sizes = []
        seed_max_share = 0.0
        seed_above = 0
        for turn in turns:
            snapshot = oracle1_snapshot(run, turn)
            if snapshot is None:
                continue
            regions = snapshot["regions"]
            population = Counter(regions.values())
            communities = snapshot["communities"]
            counts.append(len(communities))
            members = 0
            for community in communities:
                region = regions[next(iter(community))]
                share = len(community) / population[region]
                sizes.append(len(community))
                seed_sizes.append(len(community))
                shares.append(share)
                region_populations.append(population[region])
                seed_max_share = max(seed_max_share, share)
                if share > ORACLE1_REGION_SHARE_MAX + 1e-12:
                    above += 1
                    seed_above += 1
                if population[region] >= ORACLE1_REGION_POPULATION_FOR_MIN_SIZE:
                    in_large_regions += 1
                members += len(community)
            if regions:
                member_shares.append(members / len(regions))
        if not counts:
            continue
        snapshot_total += len(counts)
        per_seed.append({
            "seed": run.get("seed"),
            "snapshots": len(counts),
            "communities": sum(counts),
            "mean_count": _r(sum(counts) / len(counts)),
            "median_size": statistics.median(seed_sizes) if seed_sizes else None,
            "max_region_share": _r(seed_max_share),
            "communities_above_region_share": seed_above,
        })
    if not per_seed:
        return {"status": "SKIP", "reason": "no graph and needs sidecars at a common turn "
                                            "(the community summary is method 1's)"}
    analyzed = len(per_seed)
    with_communities = sum(1 for record in per_seed if record["communities"] > 0)
    required = required_seed_count(analyzed, ORACLE1_SEED_FRACTION_MIN)
    seed_means = [record["mean_count"] for record in per_seed]
    mean_count = sum(seed_means) / analyzed
    median_size = statistics.median(sizes) if sizes else None
    count_lo, count_hi = ORACLE1_COUNT_BAND
    size_lo, size_hi = ORACLE1_MEDIAN_SIZE_BAND
    failed = []
    if with_communities < required:
        failed.append("seed_fraction")
    if not count_lo <= mean_count <= count_hi:
        failed.append("community_count")
    if median_size is None or not size_lo <= median_size <= size_hi:
        failed.append("median_size")
    if above:
        failed.append("region_share")
    result = {
        "status": "FAIL" if failed else "PASS",
        "label": SPEC_LABEL,
        "failed_criteria": failed,
        "criteria": {
            "seed_fraction": f"communities in at least {ORACLE1_SEED_FRACTION_MIN:.0%} of seeds",
            "community_count": f"mean communities a seed per steady-state snapshot within "
                               f"{count_lo:g}-{count_hi:g}",
            "median_size": f"median community size within {size_lo:g}-{size_hi:g}",
            "region_share": f"no community above {ORACLE1_REGION_SHARE_MAX:.0%} of its region's living agents "
                            "at the snapshot",
        },
        "steady_state_first_turn": ORACLE1_STEADY_STATE_FIRST_TURN,
        "analyzed_seeds": analyzed,
        "required_seed_count": required,
        "seeds_with_communities": with_communities,
        "snapshots": snapshot_total,
        "communities": len(sizes),
        "mean_community_count": _r(mean_count),
        "median_seed_mean_count": _r(statistics.median(seed_means)),
        "seeds_in_count_band": sum(1 for value in seed_means if count_lo <= value <= count_hi),
        "median_size": median_size,
        "size_p90": _quantile(sizes, 0.9),
        "max_size": max(sizes) if sizes else None,
        "region_share": {
            "measure": "community size over the living agents of its region at the snapshot",
            "max": _r(max(shares)) if shares else None,
            "median": _r(_quantile(shares, 0.5)),
            "communities_above": above,
            "fraction_above": _r(above / len(shares)) if shares else None,
            "median_region_population": _quantile(region_populations, 0.5),
            "communities_in_regions_of_at_least": {
                "population": ORACLE1_REGION_POPULATION_FOR_MIN_SIZE, "communities": in_large_regions},
        },
        "members_share_of_living_agents": {
            "median": _r(_quantile(member_shares, 0.5)),
            "mean": _r(sum(member_shares) / len(member_shares)) if member_shares else None,
        },
        "per_seed": per_seed,
    }
    if failed:
        result["reason"] = "failed " + ", ".join(failed) + _failure_detail(result)
    return result


def _failure_detail(result: dict) -> str:
    share = result["region_share"]
    return (f" (seeds with communities {result['seeds_with_communities']} of {result['analyzed_seeds']}, "
            f"mean count {result['mean_community_count']}, median size {result['median_size']}, "
            f"{share['communities_above']} of {result['communities']} communities above "
            f"{ORACLE1_REGION_SHARE_MAX:.0%} of their region)")


def community_spec_required(spec_required: bool | None = None) -> bool:
    from .validation_gate import COMMUNITY_SPEC_REQUIRED

    return COMMUNITY_SPEC_REQUIRED if spec_required is None else bool(spec_required)


def community_method_2_result(legacy: dict, spec: dict, *, spec_required: bool | None = None) -> dict:
    """Community oracle method 2 from method 1's ``legacy`` result and the
    ``spec`` component (``spec_component``). The status is the deciding
    component's: method 1's unless the spec component is required
    (``spec_required``, default ``validation_gate.COMMUNITY_SPEC_REQUIRED``).
    Method 1's fields stay at the top level, as cohort method 4 keeps method
    3's. Pure: it re-scores saved components under either rule."""
    spec_required = community_spec_required(spec_required)
    statuses = {"legacy": str(legacy.get("status") or "MISSING"), "spec": str(spec.get("status") or "MISSING")}
    deciding = "spec" if spec_required else "legacy"
    result = {
        "status": statuses[deciding],
        "method": "legacy_and_spec",
        "method_version": COMMUNITY_ORACLE_METHOD_VERSION,
        "spec_required": spec_required,
        "required_components": [deciding],
        "component_statuses": statuses,
        "legacy_status": statuses["legacy"],
        "legacy_note": LEGACY_NOTE,
    }
    if legacy.get("reason"):
        result["legacy_reason"] = legacy["reason"]
    for key, value in legacy.items():
        if key in ("status", "reason", "per_seed"):
            continue
        result[key] = value
    if statuses[deciding] != "PASS":
        reason = (spec if spec_required else legacy).get("reason")
        if reason:
            result["reason"] = reason
    result["spec"] = spec
    if "per_seed" in legacy:
        result["per_seed"] = legacy["per_seed"]
    return result


def community_method_1_result(result: dict) -> dict:
    """Method 1's result from a method 2 ``result`` (its legacy component);
    a method 1 result is returned as it is."""
    if result.get("method_version") != COMMUNITY_ORACLE_METHOD_VERSION:
        return result
    legacy = {"status": result["legacy_status"]}
    if result.get("legacy_reason"):
        legacy["reason"] = result["legacy_reason"]
    skip = {"status", "reason", "method", "method_version", "spec_required", "required_components",
            "component_statuses", "legacy_status", "legacy_note", "legacy_reason", "spec", "per_seed"}
    for key, value in result.items():
        if key not in skip:
            legacy[key] = value
    if "per_seed" in result:
        legacy["per_seed"] = result["per_seed"]
    return legacy


__all__ = [
    "COMMUNITY_LEGACY_METHOD_VERSION", "COMMUNITY_ORACLE_METHOD_VERSION", "COMMUNITY_METHOD_VERSIONS",
    "ORACLE1_EDGE_BONDS", "ORACLE1_NON_KIN_BONDS", "ORACLE1_MIN_SIZE", "ORACLE1_COUNT_BAND",
    "ORACLE1_MEDIAN_SIZE_BAND", "ORACLE1_REGION_SHARE_MAX", "ORACLE1_SEED_FRACTION_MIN",
    "detect_oracle1_communities", "oracle1_turns", "oracle1_snapshot", "oracle1_communities",
    "spec_component", "community_method_2_result", "community_method_1_result", "community_spec_required",
]
