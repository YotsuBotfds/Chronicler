"""Ablation oracles: needs method 7's ablation component and cohort method 4
(docs/integration/ablation-oracles.md)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronicler import validation_ablation as va
from chronicler.validation_io import EVENT_NAME_TO_CODE

MIG = EVENT_NAME_TO_CODE["migration"]
REB = EVENT_NAME_TO_CODE["rebellion"]
SWITCH = EVENT_NAME_TO_CODE["occupation_switch"]
NEEDS = ("safety", "material", "social", "spiritual", "autonomy", "purpose")
THRESHOLDS = {"safety": 0.30, "material": 0.30, "social": 0.35, "spiritual": 0.30, "autonomy": 0.35, "purpose": 0.35}
EVENT_OF = {"safety": MIG, "material": MIG, "social": MIG, "spiritual": MIG, "autonomy": REB, "purpose": SWITCH}


def _world(seeds=6, forks=(100, 200), agents=20, deficit="material", plain=2, ablated=1, extra_events=()):
    """Seeds whose agents 0-9 are below ``deficit``'s threshold at each fork
    (every other need above every threshold) and act ``plain`` / ``ablated``
    times over the window in the two arms; agents 10-19 act once in both."""
    runs, arm = [], {"window": 20, "forks": {}}
    for seed in range(seeds):
        matching = ("civ_affinity", "region", "occupation", "boldness", "ambition", "loyalty_trait")
        cols = {"turn": [], "agent_id": [], **{need: [] for need in NEEDS}, **{key: [] for key in matching}}
        events = list(extra_events)
        arm["forks"][seed] = {}
        for fork in forks:
            ablated_turns: dict = {}
            for agent in range(agents):
                cols["turn"].append(fork)
                cols["agent_id"].append(agent)
                for key in matching:
                    cols[key].append(0)
                low = agent < 10
                for need in NEEDS:
                    cols[need].append(THRESHOLDS[need] - 0.1 if low and need == deficit else 0.9)
                code = EVENT_OF[deficit]
                n_plain, n_ablated = (plain, ablated) if low else (1, 1)
                for k in range(n_plain):
                    events.append({"turn": fork + 1 + k, "agent_id": agent, "event_type": code})
                for k in range(n_ablated):
                    ablated_turns.setdefault((agent, code), []).append(fork + 1 + k)
            arm["forks"][seed][fork] = ablated_turns
        runs.append({"seed": seed, "events": events, "needs_columns": cols,
                     "relationship_columns": None, "memory_columns": None,
                     "bundle": {"metadata": {"total_turns": 300}}})
    return runs, arm


def test_ablation_ratio_pools_seeds_with_a_clustered_bound():
    stats = va.ablation_ratio([(10, 12, 10), (10, 30, 20), (5, 0, 0), (0, 4, 4), (8, 9, 8)])
    # Seeds with an empty cohort and those with no event in either arm drop out.
    assert (stats["cohort"], stats["seeds_with_cohort"], stats["informative_seeds"]) == (33, 4, 3)
    assert (stats["plain_events"], stats["ablated_events"]) == (51, 38)
    rr = 51 / 38
    residual = sum((p - rr * a) ** 2 for p, a in ((12, 10), (30, 20), (9, 8)))
    se = (3 / 2 * residual) ** 0.5 / 38
    assert stats["rate_ratio"] == round(rr, 4)
    assert stats["standard_error"] == round(se, 4)
    assert stats["lower_bound"] == round(rr - va._t(0.95, 2) * se, 4)
    assert stats["interval"] == [round(rr - va._t(0.975, 2) * se, 4), round(rr + va._t(0.975, 2) * se, 4)]


def test_ablation_ratio_needs_two_informative_seeds_and_ablated_events():
    one = va.ablation_ratio([(10, 12, 6), (10, 0, 0)])
    assert one["rate_ratio"] == 2.0 and one["lower_bound"] is None and one["interval"] is None
    assert va.judge(one, "increase", 0.10) == ("FAIL", ["not_measured"])
    none = va.ablation_ratio([(10, 3, 0), (10, 2, 0)])
    assert none["rate_ratio"] is None
    assert va.judge(va.ablation_ratio([]), "increase", 0.10) == ("FAIL", ["not_measured"])


def test_judge_needs_the_bound_and_the_minimum_effect():
    stats = {"rate_ratio": 1.12, "standard_error": 0.01, "lower_bound": 1.10, "upper_bound": 1.14}
    assert va.judge(stats, "increase", 0.10) == ("PASS", [])
    assert va.judge({**stats, "rate_ratio": 1.05, "lower_bound": 1.03}, "increase", 0.10) == ("FAIL", ["minimum_effect"])
    assert va.judge({**stats, "lower_bound": 0.99}, "increase", 0.10) == ("FAIL", ["lower_bound"])
    down = {"rate_ratio": 0.80, "standard_error": 0.02, "lower_bound": 0.77, "upper_bound": 0.83}
    assert va.judge(down, "decrease", 0.15) == ("PASS", [])
    assert va.judge({**down, "rate_ratio": 0.90, "upper_bound": 0.93}, "decrease", 0.15) == ("FAIL", ["minimum_effect"])
    assert va.judge({**down, "upper_bound": 1.01}, "decrease", 0.15) == ("FAIL", ["upper_bound"])


def test_needs_component_passes_when_the_terms_raise_the_behaviour():
    runs, arm = _world(plain=2, ablated=1)
    component = va.needs_ablation_component(runs, arm)
    material = component["by_pairing"]["material"]
    assert (material["cohort"], material["plain_events"], material["ablated_events"]) == (120, 240, 120)
    assert material["rate_ratio"] == 2.0 and material["status"] == "PASS"
    # The other required pairings have no cohort here: not measured.
    assert component["status"] == "FAIL"
    assert set(component["failed_pairings"]) == {"autonomy", "social", "purpose", "safety"}
    # Agents above every threshold are the unexposed cohort.
    assert component["unexposed"]["migration"]["cohort"] == 120
    assert component["unexposed"]["migration"]["rate_ratio"] == 1.0
    assert component["by_pairing"]["material"]["plain_by_window_turn"][:2] == [120, 120]
    assert component["forks"] == 12 and component["seeds"] == 6


def test_needs_component_fails_identical_and_reversed_arms():
    runs, arm = _world(plain=1, ablated=1)
    material = va.needs_ablation_component(runs, arm)["by_pairing"]["material"]
    assert material["rate_ratio"] == 1.0 and material["status"] == "FAIL"
    runs, arm = _world(plain=1, ablated=2)
    material = va.needs_ablation_component(runs, arm)["by_pairing"]["material"]
    assert material["rate_ratio"] == 0.5 and "lower_bound" in material["failed_criteria"]


def test_needs_component_counts_the_fork_cohort_over_the_window_only():
    # Events on the fork turn and after the window are not outcomes.
    outside = [{"turn": 100, "agent_id": 0, "event_type": MIG}, {"turn": 121, "agent_id": 0, "event_type": MIG}]
    runs, arm = _world(seeds=3, forks=(100,), extra_events=outside)
    material = va.needs_ablation_component(runs, arm)["by_pairing"]["material"]
    assert material["plain_events"] == 3 * 10 * 2
    runs, arm = _world(seeds=3, forks=(100,))
    arm["forks"][0][100].setdefault((0, MIG), []).extend([100, 121])
    material = va.needs_ablation_component(runs, arm)["by_pairing"]["material"]
    assert material["ablated_events"] == 3 * 10


def test_needs_component_without_arm_or_snapshot():
    runs, arm = _world(seeds=2)
    assert va.needs_ablation_component(runs, None)["status"] == "NOT_RUN"
    arm["forks"][0][150] = {}
    result = va.needs_ablation_component(runs, arm)
    assert result["status"] == "ERROR" and "turn 150" in result["reason"]


def _cohort_world(seeds=6, members_plain=1, members_ablated=2):
    """Agents 0-9 form a community (friends sharing a memory); 10-19 do not."""
    runs, arm = _world(seeds=seeds, forks=(100,), deficit="material", plain=0, ablated=0)
    for run in runs:
        rel = {k: [] for k in ("turn", "agent_id", "target_id", "bond_type", "sentiment")}
        mem = {k: [] for k in ("turn", "agent_id", "event_type", "memory_turn", "valence_sign")}
        for a in range(10):
            for b in (a + 1, a + 2):
                if b < 10:
                    for k, v in zip(rel, (100, a, b, 2, 50)):
                        rel[k].append(v)
            for k, v in zip(mem, (100, a, 0, 90, -1)):
                mem[k].append(v)
        run["relationship_columns"], run["memory_columns"] = rel, mem
        run["events"] = [e for e in run["events"] if e["agent_id"] >= 10]
        for agent in range(10):
            for k in range(members_plain):
                run["events"].append({"turn": 101 + k, "agent_id": agent, "event_type": MIG})
        seed = run["seed"]
        turns = arm["forks"][seed][100]
        for agent in range(10):
            turns[(agent, MIG)] = [101 + k for k in range(members_ablated)]
    return runs, arm


def test_cohort_ablation_passes_when_members_are_anchored():
    runs, arm = _cohort_world(members_plain=1, members_ablated=2)
    result = va.cohort_ablation_result(runs, arm)
    migration = result["members_migration"]
    assert (migration["cohort"], migration["plain_events"], migration["ablated_events"]) == (60, 60, 120)
    assert migration["rate_ratio"] == 0.5 and result["status"] == "PASS"
    assert result["informational"]["non_members_migration"]["rate_ratio"] == 1.0


def test_cohort_ablation_fails_without_anchoring_or_reversed():
    for plain, ablated in ((2, 2), (2, 1)):
        runs, arm = _cohort_world(members_plain=plain, members_ablated=ablated)
        result = va.cohort_ablation_result(runs, arm)
        assert result["status"] == "FAIL" and "upper_bound" in result["failed_criteria"]
        assert "members' migration rate ratio" in result["reason"]
    assert va.cohort_ablation_result(runs, None)["status"] == "NOT_RUN"




def test_needs_method_7_keeps_method_6_and_the_observational_verdict_decides():
    from chronicler.validation_gate import CAUSAL_LABEL_REPORTED
    from chronicler.validation_io import run_needs_oracle

    runs, arm = _world(plain=2, ablated=1)
    method6 = run_needs_oracle(runs, profile="full", method_version=6)
    method7 = run_needs_oracle(runs, profile="full", ablation=arm)
    assert method7["method_version"] == 7
    for key, value in method6.items():
        if key in ("status", "method", "method_version", "criterion"):
            continue
        assert method7[key] == value, key
    assert method7["observational_status"] == method6["status"]
    assert method7["observational_criterion"] == method6["criterion"]
    # Causal oracles not yet required: method 6's verdict decides in every
    # profile; the ablation is computed and labelled as causal evidence.
    assert method7["causal_oracles_required"] is False
    for profile in ("full", "subset", None):
        result = run_needs_oracle(runs, profile=profile, ablation=arm)
        assert result["required_components"] == ["observational"]
        assert result["status"] == run_needs_oracle(runs, profile=profile, method_version=6)["status"]
    # Only the material pairing has a cohort here: it passes, the component
    # (all five required) does not, and the verdict is still method 6's.
    assert method7["ablation"]["by_pairing"]["material"]["status"] == "PASS"
    assert method7["ablation"]["status"] == "FAIL" and method7["status"] == method6["status"]
    assert method7["ablation"]["label"] == CAUSAL_LABEL_REPORTED
    # Without the arm the component is NOT_RUN and the verdict is method 6's.
    no_arm = run_needs_oracle(runs, profile="full")
    assert no_arm["ablation"]["status"] == "NOT_RUN" and no_arm["status"] == method6["status"]
    assert "placebo" not in method7
    assert run_needs_oracle(runs, profile="full", ablation=arm, placebo=arm)["placebo"]["arm"] == "placebo"


def test_needs_method_7_with_causal_oracles_required_decides_by_profile():
    from chronicler.validation_gate import CAUSAL_LABEL_REQUIRED
    from chronicler.validation_io import run_needs_oracle

    runs, arm = _world(plain=2, ablated=1)
    full = run_needs_oracle(runs, profile="full", ablation=arm, require_causal=True)
    assert full["causal_oracles_required"] is True
    assert full["required_components"] == ["ablation"]
    # Four required pairings have no cohort in this world: the ablation, and
    # with it the oracle, fails although method 6 passes.
    assert full["observational_status"] == "PASS"
    assert full["status"] == full["ablation"]["status"] == "FAIL"
    assert full["ablation"]["label"] == CAUSAL_LABEL_REQUIRED
    subset = run_needs_oracle(runs, profile="subset", ablation=arm, require_causal=True)
    assert subset["required_components"] == ["observational"]
    assert subset["status"] == run_needs_oracle(runs, profile="subset", method_version=6)["status"]
    assert run_needs_oracle(runs, ablation=arm, require_causal=True)["required_components"] == [
        "observational", "ablation"]
    # Identical arms: the ablation fails and, required, fails the oracle.
    same_runs, same_arm = _world(plain=1, ablated=1)
    assert run_needs_oracle(same_runs, profile="full", ablation=same_arm, require_causal=True)["status"] == "FAIL"
    assert run_needs_oracle(same_runs, profile="full", require_causal=True)["status"] == "NOT_RUN"


def test_cohort_method_4_keeps_method_3_and_reports_the_ablation():
    from chronicler.validation_gate import CAUSAL_LABEL_REPORTED, COHORT_OBSERVATIONAL_NOTE
    from chronicler.validation_io import run_cohort_oracle

    runs, arm = _cohort_world(members_plain=2, members_ablated=2)
    method3 = run_cohort_oracle(runs, method_version=3)
    method4 = run_cohort_oracle(runs, ablation=arm)
    assert method4["method_version"] == 4 and method4["observational_method_version"] == 3
    for key, value in method3.items():
        if key in ("status", "method", "method_version", "reason"):
            continue
        assert method4[key] == value, key
    assert method4["observational_status"] == method3["status"]
    assert method4["observational_note"] == COHORT_OBSERVATIONAL_NOTE
    assert method4["required_components"] == ["observational"]
    assert method4["status"] == method3["status"]
    assert method4.get("reason") == method3.get("reason")
    ablation = method4["ablation"]
    assert ablation["status"] == "FAIL" and ablation["label"] == CAUSAL_LABEL_REPORTED
    assert ablation["members_migration"]["rate_ratio"] == 1.0
    assert run_cohort_oracle(runs)["ablation"]["status"] == "NOT_RUN"
    assert run_cohort_oracle(runs)["status"] == method3["status"]


def test_cohort_method_4_with_causal_oracles_required_decides_by_the_ablation():
    from chronicler.validation_io import cohort_method_4_result, run_cohort_oracle

    runs, arm = _cohort_world(members_plain=1, members_ablated=2)
    anchored = run_cohort_oracle(runs, ablation=arm, require_causal=True)
    assert anchored["required_components"] == ["ablation"] and anchored["status"] == "PASS"
    runs, arm = _cohort_world(members_plain=2, members_ablated=2)
    flat = run_cohort_oracle(runs, ablation=arm, require_causal=True)
    assert flat["status"] == "FAIL" and "members' migration rate ratio" in flat["reason"]
    assert run_cohort_oracle(runs, require_causal=True)["status"] == "NOT_RUN"
    # The pure combiner re-scores saved components in either mode.
    observational = {"status": "PASS", "method_version": 3, "method": "matched", "analyzed_seeds": 2}
    component = {"status": "FAIL", "reason": "members' migration rate ratio 0.99"}
    reported = cohort_method_4_result(observational, component)
    required = cohort_method_4_result(observational, component, require_causal=True)
    assert (reported["status"], "reason" in reported, reported["analyzed_seeds"]) == ("PASS", False, 2)
    assert (required["status"], required["reason"]) == ("FAIL", "members' migration rate ratio 0.99")


def _report(needs=None, cohort=None, **extra):
    return {"results": {"needs": needs or {"status": "PASS"}, "cohort": cohort or {"status": "PASS"},
                        "community": {"status": "PASS"}}, **extra}


_NEEDS_7 = {"status": "PASS", "method_version": 7, "observational_status": "PASS", "failed_criteria": [],
            "informational_failed_criteria": [], "binding": {"net_concordance_lower_bound": 0.1},
            "ablation": {"status": "FAIL", "failed_pairings": ["material"],
                         "by_pairing": {"material": {"status": "FAIL", "required": True, "rate_ratio": 1.067,
                                                     "interval": [0.947, 1.187]}}}}
_COHORT_4 = {"status": "PASS", "method_version": 4, "observational_status": "PASS",
             "observational_note": "non-discriminating", "required_components": ["observational"],
             "ablation": {"status": "FAIL", "reason": "members' migration rate ratio 0.9884",
                          "members_migration": {"rate_ratio": 0.9884, "interval": [0.984, 0.993]}}}


def test_gate_decides_by_the_observational_components_and_reports_the_causal_ones():
    from chronicler.validation_gate import (
        CAUSAL_LABEL_REPORTED, COHORT_OBSERVATIONAL_NOTE, adjudicate_validation_report, build_gate_decision_payload,
        format_gate_markdown, format_gate_summary,
    )

    report = _report(_NEEDS_7, _COHORT_4)
    for profile in ("full", "subset"):
        decision = adjudicate_validation_report(profile, report)
        assert "needs" not in [item["oracle"] for item in decision["required_failures"]]
        assert "cohort" not in [item["oracle"] for item in decision["required_failures"]]
        informational = {item["oracle"]: item for item in decision["informational_non_pass"]}
        assert informational["needs_ablation"]["reason"].startswith(CAUSAL_LABEL_REPORTED)
        assert "pairings material" in informational["needs_ablation"]["reason"]
        assert informational["cohort_ablation"]["reason"].startswith(CAUSAL_LABEL_REPORTED)
        assert decision["causal_oracles_required"] is False
        assert [(row["oracle"], row["status"], row["decides"]) for row in decision["causal_evidence"]] == [
            ("needs", "FAIL", False), ("cohort", "FAIL", False)]
    decision = adjudicate_validation_report("subset", report)
    markdown = format_gate_markdown(decision, report)
    assert "## Causal evidence (not yet required)" in markdown
    assert "material 1.067 [0.947, 1.187] FAIL" in markdown
    assert "members' migration 0.988 [0.984, 0.993]" in markdown
    assert f"method 3 (observational), {COHORT_OBSERVATIONAL_NOTE}" in markdown
    payload = build_gate_decision_payload(decision, report)
    assert payload["causal_oracles_required"] is False and len(payload["causal_evidence"]) == 2
    assert payload["oracle_statuses"]["cohort"]["reason"] == f"method 3 (observational), {COHORT_OBSERVATIONAL_NOTE}"
    assert "Causal evidence (not yet required): needs ablation=FAIL, cohort ablation=FAIL" in (
        format_gate_summary(decision))


def test_gate_with_causal_oracles_required_decides_by_the_ablations():
    from chronicler.validation_gate import adjudicate_validation_report, format_gate_markdown

    report = _report(_NEEDS_7, _COHORT_4)
    full = adjudicate_validation_report("full", report, require_causal_oracles=True)
    failures = {item["oracle"]: item for item in full["required_failures"]}
    assert "ablation component FAIL (pairings material)" in failures["needs"]["reason"]
    assert failures["cohort"] == {"oracle": "cohort", "status": "FAIL",
                                  "reason": "members' migration rate ratio 0.9884"}
    assert full["causal_oracles_required"] is True
    assert all(row["decides"] for row in full["causal_evidence"])
    assert "## Causal evidence (required)" in format_gate_markdown(full, report)
    # A subset's needs verdict stays observational; its cohort is the ablation's.
    subset = adjudicate_validation_report("subset", report, require_causal_oracles=True)
    assert [item["oracle"] for item in subset["required_failures"]] == ["cohort"]
    assert {item["oracle"] for item in subset["informational_non_pass"]} == {"needs_ablation"}
    # The report's recorded mode applies when the gate is not told.
    recorded = _report(_NEEDS_7, _COHORT_4, causal_oracles_required=True)
    assert not adjudicate_validation_report("subset", recorded)["ok"]
    assert adjudicate_validation_report("subset", recorded, require_causal_oracles=False)["ok"]
    # Ablations that pass decide too; an observational FAIL is then reported.
    passing = {**_NEEDS_7, "ablation": {"status": "PASS"}, "observational_status": "FAIL",
               "failed_criteria": ["seed_fraction"]}
    decision = adjudicate_validation_report(
        "full", _report(passing, {**_COHORT_4, "ablation": {"status": "PASS"}}), require_causal_oracles=True)
    assert not {"needs", "cohort"} & {item["oracle"] for item in decision["required_failures"]}
    assert "needs_observational" in {item["oracle"] for item in decision["informational_non_pass"]}


def test_gate_cohort_method_4_without_its_arm():
    from chronicler.validation_gate import adjudicate_validation_report

    no_arm = {**_COHORT_4, "ablation": {"status": "NOT_RUN", "reason": "no kin_roots ablation arm"}}
    reported = adjudicate_validation_report("subset", _report(cohort=no_arm))
    assert reported["ok"]
    assert {item["oracle"]: item["status"] for item in reported["informational_non_pass"]} == {
        "cohort_ablation": "NOT_RUN"}
    required = adjudicate_validation_report("subset", _report(cohort=no_arm), require_causal_oracles=True)
    assert required["required_failures"] == [
        {"oracle": "cohort", "status": "NOT_RUN", "reason": "no kin_roots ablation arm"}]
    # A report scored with causal oracles required (its statuses NOT_RUN)
    # is re-decided by its components when the gate does not require them.
    needs_no_arm = {**_NEEDS_7, "status": "NOT_RUN", "ablation": {"status": "NOT_RUN"}}
    recorded = _report(needs_no_arm, {**no_arm, "status": "NOT_RUN"}, causal_oracles_required=True)
    assert not adjudicate_validation_report("full", recorded)["ok"]
    decision = adjudicate_validation_report("full", recorded, require_causal_oracles=False)
    assert not {"needs", "cohort"} & {item["oracle"] for item in decision["required_failures"]}


def test_comparator_flags_the_new_methods_for_rebaselining():
    from chronicler.validation_compare import compare_validation_reports

    old = _report({"status": "PASS", "method_version": 6}, {"status": "PASS", "method_version": 3})
    new = _report(_NEEDS_7, _COHORT_4)
    result = compare_validation_reports("subset", old, new, exploratory=True)
    changes = {item["oracle"]: (item["baseline_method_version"], item["current_method_version"])
               for item in result["oracle_method_changes"]}
    assert changes == {"needs": (6, 7), "cohort": (3, 4)}
    assert result["rebaseline_required"] is True
    assert result["new_required_failures"] == []


# ---------------------------------------------------------------------------
# Loading arms
# ---------------------------------------------------------------------------

def _write_events(path: Path, rows):
    import pyarrow as pa
    import pyarrow.ipc as ipc

    table = pa.table({
        "turn": pa.array([r[0] for r in rows], pa.uint32()),
        "agent_id": pa.array([r[1] for r in rows], pa.uint32()),
        "event_type": pa.array([r[2] for r in rows], pa.string()),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with ipc.new_file(path, table.schema) as writer:
        writer.write_table(table)


def _arms_dir(tmp_path: Path, *, prefix_differs=False, wrong_ablation=False):
    from chronicler.ablation_arms import ABLATION_MANIFEST_FILENAME, ABLATION_MANIFEST_KIND
    from chronicler.batch_manifest import file_sha256

    batch = tmp_path / "batch_42"
    rows = [(t, 1, "migration") for t in range(0, 140, 7)]
    _write_events(batch / "seed_42" / "agent_events.arrow", rows)
    (batch / "batch_manifest.json").write_text(json.dumps({
        "kind": "chronicler-batch", "status": "complete", "turns": 150,
        "runs": [{"seed": 42, "dir": "seed_42"}]}), encoding="utf-8")
    arms = tmp_path / "ablation_42"
    fork = arms / "needs" / "seed_42" / "fork_100"
    fork_rows = [r for r in rows if r[0] <= 100] + [(105, 1, "migration"), (110, 2, "rebellion"), (125, 1, "migration")]
    if prefix_differs:
        fork_rows[0] = (0, 9, "migration")
    _write_events(fork / "agent_events.arrow", fork_rows)
    ablation = {"name": "placebo" if wrong_ablation else "needs", "start_turn": 101, "forked_at": 101}
    (fork / "fork.json").write_text(json.dumps({"decision_ablation": ablation}), encoding="utf-8")
    manifest = {
        "kind": ABLATION_MANIFEST_KIND, "schema_version": 1, "status": "complete",
        "plain_manifest_sha256": file_sha256(batch / "batch_manifest.json"),
        "arms": ["needs"], "window_turns": 20, "fork_turns": [100], "seeds": [42],
        "forks": [{"arm": "needs", "seed": 42, "fork_turn": 100, "dir": "needs/seed_42/fork_100",
                   "files": {"agent_events.arrow": file_sha256(fork / "agent_events.arrow"),
                             "fork.json": file_sha256(fork / "fork.json")}}],
    }
    (arms / ABLATION_MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return batch, arms


def test_load_ablation_arms_checks_history_and_reads_the_window(tmp_path):
    pytest.importorskip("pyarrow")
    batch, arms = _arms_dir(tmp_path)
    loaded = va.load_ablation_arms(arms, batch)
    assert loaded["summary"]["status"] == "verified" and loaded["summary"]["forks"] == 1
    window = loaded["arms"]["needs"]["forks"][42][100]
    assert window == {(1, MIG): [105], (2, REB): [110]}


@pytest.mark.parametrize("problem, message", [
    ("prefix", "differs from the plain run before its fork turn"),
    ("ablation", "records ablation"),
    ("plain", "forked from another batch"),
    ("changed", "changed since the arms ran"),
])
def test_load_ablation_arms_refuses(tmp_path, problem, message):
    pytest.importorskip("pyarrow")
    batch, arms = _arms_dir(tmp_path, prefix_differs=problem == "prefix", wrong_ablation=problem == "ablation")
    if problem == "plain":
        (batch / "batch_manifest.json").write_text(
            (batch / "batch_manifest.json").read_text(encoding="utf-8") + " ", encoding="utf-8")
    if problem == "changed":
        info = arms / "needs" / "seed_42" / "fork_100" / "fork.json"
        info.write_text(info.read_text(encoding="utf-8") + " ", encoding="utf-8")
    if problem == "ablation":
        # Re-hash so only the recorded ablation is wrong.
        from chronicler.batch_manifest import file_sha256
        manifest = json.loads((arms / "ablation_manifest.json").read_text(encoding="utf-8"))
        manifest["forks"][0]["files"]["fork.json"] = file_sha256(arms / "needs" / "seed_42" / "fork_100" / "fork.json")
        (arms / "ablation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(va.AblationInputError, match=message):
        va.load_ablation_arms(arms, batch)


def test_fork_rule_matches_the_preregistration():
    from chronicler.ablation_arms import checkpoint_turns, fork_turns

    assert fork_turns(500) == [100, 200, 300, 400]
    assert fork_turns(300) == [100, 200]
    assert fork_turns(200) == [100]
    assert fork_turns(120) == []
    assert checkpoint_turns(500) == [101, 201, 301, 401]


def test_needs_pairings_mirror_the_observational_oracle():
    from chronicler.validation_io import (
        NEEDS_BEHAVIOUR_THRESHOLDS, NEEDS_INFORMATIONAL_PAIRINGS, NEEDS_INFORMATIONAL_THRESHOLDS, NEEDS_PAIRINGS,
    )

    required = [(need, EVENT_NAME_TO_CODE[event]) for need, _t, event, req in va.NEEDS_ABLATION_PAIRINGS if req]
    assert required == list(NEEDS_PAIRINGS)
    informational = [(need, EVENT_NAME_TO_CODE[event]) for need, _t, event, req in va.NEEDS_ABLATION_PAIRINGS
                     if not req]
    assert informational == list(NEEDS_INFORMATIONAL_PAIRINGS)
    thresholds = {need: t for need, t, *_ in va.NEEDS_ABLATION_PAIRINGS}
    assert thresholds == {**NEEDS_BEHAVIOUR_THRESHOLDS, **NEEDS_INFORMATIONAL_THRESHOLDS}
