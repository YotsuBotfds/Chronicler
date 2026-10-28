"""Community oracle method 2 (M53 oracle 1 as specified) and cohort method
6 on its communities (docs/integration/spec-communities.md); the bond-type
mirror against the Rust enum (native behaviour in
tests/test_spec_communities_native.py)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from chronicler import validation_communities as vc
from chronicler.ffi_constants import BOND_TYPES, POSITIVE_VALENCE_BONDS

ROOT = Path(__file__).resolve().parents[1]
FRIEND, KIN, CORELIG = BOND_TYPES["friend"], BOND_TYPES["kin"], BOND_TYPES["co_religionist"]
MENTOR, RIVAL, MARRIAGE = BOND_TYPES["mentor"], BOND_TYPES["rival"], BOND_TYPES["marriage"]
EXILE, GRUDGE = BOND_TYPES["exile_bond"], BOND_TYPES["grudge"]
FAMINE = (0, 90, -1)


# ---------------------------------------------------------------------------
# The bond-type mirror
# ---------------------------------------------------------------------------

def _rust_source() -> str:
    return (ROOT / "chronicler-agents" / "src" / "relationships.rs").read_text(encoding="utf-8")


def test_bond_type_mirror_matches_the_rust_enum():
    body = re.search(r"pub enum BondType \{(.*?)\n\}", _rust_source(), re.S).group(1)
    variants = re.findall(r"^\s*(\w+)\s*=\s*(\d+)\s*,", body, re.M)
    assert len(variants) == 8
    rust = {re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower(): int(code) for name, code in variants}
    assert rust == BOND_TYPES
    positive = re.search(r"fn is_positive_valence\(bond_type: u8\) -> bool \{\s*matches!\(bond_type, ([\d |]+)\)",
                         _rust_source()).group(1)
    assert {int(code) for code in positive.split("|")} == POSITIVE_VALENCE_BONDS


def test_validators_take_bond_codes_from_the_mirror():
    from chronicler import validation_ablation as va

    assert va.COMMUNITY_KIN_BOND == KIN == 5
    assert va.SPEC_COMMUNITY_BOND_TYPES == vc.ORACLE1_EDGE_BONDS == {FRIEND, CORELIG, KIN}
    assert va.COMMUNITY_TIE_BOND_TYPES == POSITIVE_VALENCE_BONDS - {MARRIAGE}
    assert vc.ORACLE1_NON_KIN_BONDS == {FRIEND, CORELIG}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _clique(members, bond=FRIEND, sentiment=50):
    return [(a, b, bond, sentiment) for a in members for b in members if a != b]


def _sigs(members, memory=FAMINE):
    return {a: [memory] for a in members}


def test_detection_keeps_five_friends_sharing_a_memory():
    members = range(1, 6)
    regions = {a: 0 for a in members}
    assert vc.detect_oracle1_communities(_clique(members), regions, _sigs(members)) == [set(members)]
    # Four is too few.
    assert vc.detect_oracle1_communities(_clique(range(1, 5)), regions, _sigs(members)) == []
    # Co-religionists count as friends do; kin edges join, but a pure kin clump is excluded.
    assert vc.detect_oracle1_communities(_clique(members, CORELIG), regions, _sigs(members)) == [set(members)]
    assert vc.detect_oracle1_communities(_clique(members, KIN), regions, _sigs(members)) == []
    mixed = _clique(members, KIN) + [(1, 2, FRIEND, 10)]
    assert vc.detect_oracle1_communities(mixed, regions, _sigs(members)) == [set(members)]


@pytest.mark.parametrize("bond", [MENTOR, RIVAL, MARRIAGE, EXILE, GRUDGE])
def test_detection_ignores_bonds_the_spec_does_not_name(bond):
    members = range(1, 6)
    regions = {a: 0 for a in members}
    assert vc.detect_oracle1_communities(_clique(members, bond), regions, _sigs(members)) == []
    # Method 1 propagates over them (and tests its kin-only rule against code 0).
    from chronicler.validation_io import detect_communities
    assert detect_communities(_clique(members, bond), _sigs(members)) == ([set(members)] if bond != MENTOR else [])


def test_detection_needs_positive_sentiment_one_region_and_living_agents():
    members = range(1, 6)
    regions = {a: 0 for a in members}
    assert vc.detect_oracle1_communities(_clique(members, sentiment=0), regions, _sigs(members)) == []
    assert vc.detect_oracle1_communities(_clique(members, sentiment=-20), regions, _sigs(members)) == []
    split = {**regions, 5: 1}
    assert vc.detect_oracle1_communities(_clique(members), split, _sigs(members)) == []
    dead = {a: 0 for a in range(1, 5)}  # agent 5 has no needs row: not alive at the snapshot
    assert vc.detect_oracle1_communities(_clique(members), dead, _sigs(members)) == []


def test_detection_weights_edges_by_sentiment():
    # Agent 5 has one strong friend in {1-4} and two weak ones in {6-9}: by
    # sentiment it joins the first group, by edge count it would join the second.
    first, second = range(1, 5), range(6, 10)
    edges = _clique(first) + _clique(second) + [(5, 1, FRIEND, 100), (1, 5, FRIEND, 100),
                                                (5, 6, FRIEND, 10), (6, 5, FRIEND, 10),
                                                (5, 7, FRIEND, 10), (7, 5, FRIEND, 10)]
    agents = list(first) + [5] + list(second)
    found = vc.detect_oracle1_communities(edges, {a: 0 for a in agents}, _sigs(agents))
    assert set(range(1, 6)) in found and all(5 not in group for group in found if group != set(range(1, 6)))


def test_detection_needs_one_memory_tuple_held_by_four_in_five():
    members = list(range(1, 11))
    regions = {a: 0 for a in members}
    edges = _clique(members)
    eight = {a: [FAMINE] for a in members[:8]}
    assert vc.detect_oracle1_communities(edges, regions, eight) == [set(members)]
    seven = {a: [FAMINE] for a in members[:7]}
    assert vc.detect_oracle1_communities(edges, regions, seven) == []
    # The tuple matches exactly: another valence or another turn is another memory.
    other_sign = {**seven, 8: [(0, 90, 1)]}
    assert vc.detect_oracle1_communities(edges, regions, other_sign) == []
    other_turn = {**seven, 8: [(0, 91, -1)]}
    assert vc.detect_oracle1_communities(edges, regions, other_turn) == []
    # Pairwise sharing is not enough: halves sharing different memories.
    halves = {a: [FAMINE] if a <= 5 else [(1, 95, -1)] for a in members}
    assert vc.detect_oracle1_communities(edges, regions, halves) == []


def test_detection_is_deterministic_and_order_free():
    members = list(range(1, 13))
    regions = {a: 0 for a in members}
    edges = _clique(members[:6]) + _clique(members[6:], CORELIG) + [(6, 7, FRIEND, 5)]
    first = vc.detect_oracle1_communities(edges, regions, _sigs(members))
    assert first == vc.detect_oracle1_communities(list(reversed(edges)), regions, _sigs(members))
    assert sorted(len(group) for group in first) == [6, 6]


# ---------------------------------------------------------------------------
# The spec component and method 2
# ---------------------------------------------------------------------------

def _run(seed, turns=(100, 110), region_population=100, communities=1, size=5, total_turns=140):
    """One region of ``region_population`` agents with ``communities``
    friend cliques of ``size`` sharing a memory, at each of ``turns``."""
    rel = {k: [] for k in ("turn", "agent_id", "target_id", "bond_type", "sentiment")}
    mem = {k: [] for k in ("turn", "agent_id", "event_type", "memory_turn", "valence_sign")}
    needs = {k: [] for k in ("turn", "agent_id", "region", "civ_affinity", "occupation", "satisfaction")}
    for turn in turns:
        for agent in range(region_population):
            for key, value in zip(needs, (turn, agent, 0, 0, 0, 0.5)):
                needs[key].append(value)
        for c in range(communities):
            group = range(c * size, (c + 1) * size)
            for a, b, bond, sentiment in _clique(group):
                for key, value in zip(rel, (turn, a, b, bond, sentiment)):
                    rel[key].append(value)
            for a in group:
                for key, value in zip(mem, (turn, a, *FAMINE)):
                    mem[key].append(value)
    return {"seed": seed, "relationship_columns": rel, "memory_columns": mem, "needs_columns": needs,
            "bundle": {"metadata": {"total_turns": total_turns}}, "events": []}


def test_spec_component_passes_the_spec_world():
    runs = [_run(seed, communities=3, region_population=300) for seed in range(4)]
    spec = vc.spec_component(runs)
    assert spec["status"] == "PASS" and spec["failed_criteria"] == []
    assert (spec["analyzed_seeds"], spec["seeds_with_communities"], spec["snapshots"]) == (4, 4, 8)
    assert (spec["mean_community_count"], spec["median_size"], spec["communities"]) == (3.0, 5, 24)
    assert spec["region_share"]["max"] == 0.0167 and spec["region_share"]["communities_above"] == 0
    assert spec["members_share_of_living_agents"]["median"] == 0.05


def test_spec_component_measures_each_criterion():
    # A community of 5 is 5% of a region of 100 (within the bound) and 10% of 50.
    at_bound = vc.spec_component([_run(seed, communities=3) for seed in range(4)])
    assert at_bound["region_share"]["max"] == 0.05 and "region_share" not in at_bound["failed_criteria"]
    small = vc.spec_component([_run(seed, communities=3, region_population=50) for seed in range(4)])
    assert small["failed_criteria"] == ["region_share"] and small["status"] == "FAIL"
    assert small["region_share"]["communities_above"] == 24 and small["region_share"]["fraction_above"] == 1.0
    assert small["region_share"]["communities_in_regions_of_at_least"] == {"population": 100, "communities": 0}
    assert "24 of 24 communities above 5% of their region" in small["reason"]
    few = vc.spec_component([_run(seed, communities=2, region_population=300) for seed in range(4)])
    assert few["failed_criteria"] == ["community_count"]
    large = vc.spec_component([_run(seed, communities=3, size=13, region_population=900) for seed in range(4)])
    assert large["failed_criteria"] == ["median_size"]
    # Communities in fewer than 75% of the seeds (two of four).
    sparse = [_run(seed, communities=6, region_population=300) for seed in range(2)]
    sparse += [_run(seed, communities=1, size=4, region_population=300) for seed in range(2, 4)]
    assert "seed_fraction" in vc.spec_component(sparse)["failed_criteria"]
    # Steady state: snapshots before turn 100 are left out when later ones exist.
    early = vc.spec_component([_run(seed, turns=(50, 100), communities=3, region_population=300)
                               for seed in range(4)])
    assert early["snapshots"] == 4
    assert vc.spec_component([])["status"] == "SKIP"
    assert vc.spec_component([{"seed": 1, "needs_columns": None}])["status"] == "SKIP"


def test_community_method_2_reports_the_spec_component_and_method_1_decides():
    from chronicler.validation_io import run_community_oracle

    runs = [_run(seed, communities=3, region_population=50) for seed in range(4)]
    method1 = run_community_oracle(runs, method_version=1)
    method2 = run_community_oracle(runs)
    assert method1["status"] == "PASS" and "method_version" not in method1
    assert method2["method_version"] == 2 and method2["status"] == "PASS"
    assert method2["required_components"] == ["legacy"] and method2["spec_required"] is False
    assert method2["component_statuses"] == {"legacy": "PASS", "spec": "FAIL"}
    assert method2["spec"]["failed_criteria"] == ["region_share"]
    assert vc.community_method_1_result(method2) == method1
    for key in ("analyzed_seeds", "required_seed_count", "qualifying_seed_count", "per_seed"):
        assert method2[key] == method1[key]
    # Required, the spec component decides (pure re-scoring of saved components).
    required = vc.community_method_2_result(method1, method2["spec"], spec_required=True)
    assert required["status"] == "FAIL" and required["reason"].startswith("failed region_share")
    assert run_community_oracle(runs, spec_required=True)["status"] == "FAIL"
    for bad in (0, 3, True, "2"):
        with pytest.raises(ValueError, match="method_version"):
            run_community_oracle(runs, method_version=bad)
    assert run_community_oracle([]) == run_community_oracle([], method_version=1) == {
        "status": "SKIP", "reason": "no_bundles"}


def test_gate_lists_the_spec_component_without_deciding():
    from chronicler.validation_gate import adjudicate_validation_report, format_gate_markdown
    from chronicler.validation_io import run_community_oracle

    runs = [_run(seed, communities=3, region_population=50) for seed in range(4)]
    report = {"results": {"needs": {"status": "PASS"}, "cohort": {"status": "PASS"},
                          "community": run_community_oracle(runs)}}
    decision = adjudicate_validation_report("subset", report)
    assert decision["ok"] and decision["required_failures"] == []
    items = {item["oracle"]: item for item in decision["informational_non_pass"]}
    assert items["community_spec"]["status"] == "FAIL"
    assert "region_share" in items["community_spec"]["reason"]
    assert "method 1 decides; spec component (M53 oracle 1 as specified) FAIL" in format_gate_markdown(
        decision, report)
    required = {"results": {**report["results"], "community": run_community_oracle(runs, spec_required=True)}}
    decision = adjudicate_validation_report("subset", required)
    assert [item["oracle"] for item in decision["required_failures"]] == ["community"]


def test_comparator_flags_community_and_cohort_method_changes():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    def report(community, cohort):
        return {"results": {"needs": {"status": "PASS", "method_version": 8},
                            "community": community, "cohort": cohort}}

    old = report({"status": "PASS"}, {"status": "PASS", "method_version": 5})
    new = report({"status": "PASS", "method_version": 2, "legacy_status": "PASS", "spec": {"status": "FAIL"}},
                 {"status": "PASS", "method_version": 6})
    for profile in ("subset", "full"):
        result = compare_validation_reports(profile, old, new, exploratory=True)
        changes = {item["oracle"]: (item["baseline_method_version"], item["current_method_version"])
                   for item in result["oracle_method_changes"]}
        assert changes == {"community": (1, 2), "cohort": (5, 6)}
        assert result["rebaseline_required"] is True and result["new_required_failures"] == []
        assert "| community | 1 | PASS | 2 | PASS |" in format_comparison_markdown(result)
    # Method 2 against method 2 compares statuses again.
    failing = report({"status": "FAIL", "method_version": 2, "legacy_status": "FAIL", "spec": {"status": "FAIL"}},
                     {"status": "PASS", "method_version": 6})
    result = compare_validation_reports("subset", new, failing, exploratory=True)
    assert result["rebaseline_required"] is False
    assert [(item["oracle"], item["status"]) for item in result["new_required_failures"]] == [("community", "FAIL")]


def test_cohort_method_6_observational_takes_method_2_members_and_reports_matching():
    from chronicler.validation_io import EVENT_NAME_TO_CODE, run_cohort_oracle

    runs = [_run(seed, turns=(100,), communities=2, region_population=20) for seed in range(3)]
    for run in runs:
        # The members (0-9) migrate less than the other ten agents.
        run["events"] = [{"turn": 105, "agent_id": agent, "event_type": EVENT_NAME_TO_CODE["migration"]}
                         for agent in range(10, 20)]
    result = run_cohort_oracle(runs)
    assert result["method_version"] == 6 and result["community_method_version"] == 2
    assert result["status"] == run_cohort_oracle(runs, method_version=5)["status"] == "PASS"
    matching = result["matching"]
    assert (matching["snapshots"], matching["members"], matching["matched_members"]) == (3, 30, 30)
    assert matching["match_rate"] == 1.0 and matching["chosen_snapshots"]["match_rate"] == 1.0
    assert [record["members"] for record in result["per_seed"]] == [10, 10, 10]


@pytest.mark.parametrize("population,size,forced,eligible_failures", [
    (99, 5, 6, 0),
    (100, 5, 0, 0),
    (100, 6, 0, 6),
])
def test_capacity_diagnostic_matches_actual_method_2_counters(
    population, size, forced, eligible_failures,
):
    from chronicler.community_admissibility import diagnose_report

    spec = vc.spec_component([
        _run(42, communities=3, size=size, region_population=population),
    ])
    report = {
        "results": {
            "community": vc.community_method_2_result({"status": "PASS"}, spec),
        },
    }
    original_status = spec["status"]
    result = diagnose_report(report)
    assert result["observations"] == 6
    assert result["structurally_forced_region_share_failures"] == forced
    assert result["region_share_failures_among_capacity_eligible_observations"] == eligible_failures
    assert result["observations_within_region_share_bound"] == 6 - forced - eligible_failures
    assert report["results"]["community"]["spec"]["status"] == original_status
