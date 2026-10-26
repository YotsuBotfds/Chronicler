import json
import pytest


def _write_minimal_bundle(seed_dir, seed: int = 42, total_turns: int = 20):
    seed_dir.mkdir()
    bundle = {
        "metadata": {"generated_at": "2026-04-01T00:00:00Z", "seed": seed, "total_turns": total_turns},
        "world_state": {},
        "history": [],
        "events_timeline": [],
        "named_events": [],
        "chronicle_entries": [],
        "era_reflections": {},
    }
    (seed_dir / "chronicle_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")


def test_run_oracles_rejects_unknown_names_even_when_all_is_present(tmp_path):
    from chronicler.validate import ValidationRequestError, run_oracles

    with pytest.raises(ValidationRequestError, match="unknown_oracles: bogus"):
        run_oracles(tmp_path, ["all", "bogus"])


def test_run_oracles_rejects_mixing_all_with_explicit_oracles(tmp_path):
    from chronicler.validate import ValidationRequestError, run_oracles

    with pytest.raises(ValidationRequestError, match="all cannot be combined"):
        run_oracles(tmp_path, ["all", "needs"])


def test_validate_main_returns_nonzero_for_unknown_oracle_combined_with_all(tmp_path, capsys):
    from chronicler import validate

    assert validate.main(["--batch-dir", str(tmp_path), "--oracles", "all", "bogus"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "unknown_oracles: bogus" in payload["reason"]


def test_validation_io_main_matches_facade_unknown_oracle_behavior(tmp_path, capsys):
    from chronicler import validation_io

    assert validation_io.main(["--batch-dir", str(tmp_path), "--oracles", "all", "bogus"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "unknown_oracles: bogus" in payload["reason"]


def test_determinism_scrubbed_comparison():
    """Scrubbed comparison ignores generated_at timestamp."""
    bundle_a = {"metadata": {"generated_at": "2026-03-21T10:00:00Z", "seed": 42},
                "world_state": {"turn": 100}, "history": {"Aram": []}}
    bundle_b = {"metadata": {"generated_at": "2026-03-21T10:05:00Z", "seed": 42},
                "world_state": {"turn": 100}, "history": {"Aram": []}}
    from chronicler.validate import scrubbed_equal
    assert scrubbed_equal(bundle_a, bundle_b)

    bundle_c = dict(bundle_b)
    bundle_c["world_state"] = {"turn": 101}
    assert not scrubbed_equal(bundle_a, bundle_c)


def test_run_determinism_gate_passes_with_duplicate_seed_bundles(tmp_path):
    from chronicler.validate import run_determinism_gate

    seed_a = tmp_path / "seed_42_a"
    seed_b = tmp_path / "seed_42_b"
    seed_a.mkdir()
    seed_b.mkdir()

    bundle_a = {
        "metadata": {"generated_at": "2026-03-21T10:00:00Z", "seed": 42},
        "world_state": {"turn": 100, "population": 50},
    }
    bundle_b = {
        "metadata": {"generated_at": "2026-03-21T10:05:00Z", "seed": 42},
        "world_state": {"turn": 100, "population": 50},
    }
    (seed_a / "chronicle_bundle.json").write_text(json.dumps(bundle_a), encoding="utf-8")
    (seed_b / "chronicle_bundle.json").write_text(json.dumps(bundle_b), encoding="utf-8")

    result = run_determinism_gate(tmp_path)
    assert result["status"] == "PASS"
    assert result["pairs_checked"] == 1
    assert result["duplicate_seeds"] == [42]
    assert result["mismatches"] == []


def test_run_determinism_gate_fails_on_scrubbed_difference(tmp_path):
    from chronicler.validate import run_determinism_gate

    seed_a = tmp_path / "seed_42_a"
    seed_b = tmp_path / "seed_42_b"
    seed_a.mkdir()
    seed_b.mkdir()

    bundle_a = {
        "metadata": {"generated_at": "2026-03-21T10:00:00Z", "seed": 42},
        "world_state": {"turn": 100, "population": 50},
    }
    bundle_b = {
        "metadata": {"generated_at": "2026-03-21T10:05:00Z", "seed": 42},
        "world_state": {"turn": 101, "population": 50},
    }
    (seed_a / "chronicle_bundle.json").write_text(json.dumps(bundle_a), encoding="utf-8")
    (seed_b / "chronicle_bundle.json").write_text(json.dumps(bundle_b), encoding="utf-8")

    result = run_determinism_gate(tmp_path)
    assert result["status"] == "FAIL"
    assert result["pairs_checked"] == 1
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["seed"] == 42


def test_load_seed_runs_keeps_only_oracle_bundle_fields(tmp_path):
    """Full-profile batches do not fit in memory as whole bundles: seed runs
    keep only what the oracles read, with derived series from the full data."""
    from chronicler.validate import load_seed_runs

    seed_dir = tmp_path / "seed_42"
    seed_dir.mkdir()
    civ = {"population": 30, "treasury": -2, "stability": 40, "regions": ["A"],
           "prestige": 5, "gini": 0.3, "great_persons": [{"name": "x"}], "factions": {"m": 1}}
    bundle = {
        "metadata": {"seed": 42, "total_turns": 2},
        "world_state": {"turn": 2, "agent_mode": "off", "regions": [{"population": 30}],
                        "artifacts": [{"status": "lost"}], "events_timeline": [{"turn": 1}]},
        "history": [{"turn": 1, "civ_stats": {"Aram": civ}, "relationships": {"big": 1}},
                    {"turn": 2, "civ_stats": {"Aram": dict(civ, population=35)}}],
        "events_timeline": [{"turn": 1}, {"turn": 2, "event_type": "famine", "actors": ["Aram"]}],
        "named_events": [],
    }
    (seed_dir / "chronicle_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

    (run,) = load_seed_runs(tmp_path)
    assert run["civ_trajectories"][0]["turn"] == [1, 2]
    assert run["civ_crisis_event_turns"] == {"Aram": [2]}
    kept = {k: v for k, v in civ.items() if k not in ("great_persons", "factions")}
    assert run["bundle"] == {
        "metadata": bundle["metadata"],
        "history": [{"civ_stats": {"Aram": kept}},
                    {"civ_stats": {"Aram": dict(kept, population=35)}}],
        "world_state": {"turn": 2, "agent_mode": "off", "regions": [{"population": 30}],
                        "artifacts": [{"status": "lost"}]},
    }
    assert run["world_population"] == [30, 35]
    assert run["civ_trajectories"][0]["population"] == [30, 35]


def test_agent_events_keep_counted_codes_and_presence(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.ipc as ipc
    from chronicler.validation_io import EVENT_NAME_TO_CODE, _load_agent_events

    def load(names):
        seed_dir = tmp_path / f"seed_{len(names)}"
        seed_dir.mkdir()
        table = pa.table({
            "turn": pa.array(range(len(names)), pa.uint32()),
            "agent_id": pa.array([7] * len(names), pa.uint32()),
            "event_type": pa.array(names),
        })
        with ipc.new_file(seed_dir / "agent_events.arrow", table.schema) as writer:
            writer.write_table(table)
        return _load_agent_events(seed_dir)

    code = EVENT_NAME_TO_CODE
    assert load(["birth", "migration", "death", "rebellion", "occupation_switch", "dissolution"]) == [
        {"turn": 1, "agent_id": 7, "event_type": code["migration"]},
        {"turn": 3, "agent_id": 7, "event_type": code["rebellion"]},
        {"turn": 4, "agent_id": 7, "event_type": code["occupation_switch"]},
    ]
    # Only uncounted events: one is kept so the run still has agent events.
    assert load(["birth", "death"]) == [{"turn": 0, "agent_id": 7, "event_type": code["birth"]}]


def test_arrow_columns_pack_numeric_values_losslessly():
    pa = pytest.importorskip("pyarrow")
    from chronicler.validation_io import _compact_column

    for values, kind in (([1, 2, 300000], pa.uint32()), ([0.1, 2.5], pa.float32()),
                         ([1.0, None], pa.float64()), ([True, False], pa.bool_())):
        column = pa.chunked_array([pa.array(values, kind)])
        packed = _compact_column(column)
        assert list(packed) == column.to_pylist()
        assert [type(v) for v in packed] == [type(v) for v in column.to_pylist()]


def test_run_determinism_gate_skips_without_duplicate_seed_pairs(tmp_path):
    from chronicler.validate import run_determinism_gate

    seed_dir = tmp_path / "seed_42"
    seed_dir.mkdir()
    bundle = {
        "metadata": {"generated_at": "2026-03-21T10:00:00Z", "seed": 42},
        "world_state": {"turn": 100},
    }
    (seed_dir / "chronicle_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

    result = run_determinism_gate(tmp_path)
    assert result["status"] == "SKIP"
    assert result["reason"] == "no_duplicate_seed_pairs"
    assert result["pairs_checked"] == 0


def test_community_detection_finds_clusters():
    """Label propagation finds communities in a graph with clear structure."""
    # Two disconnected cliques of 5 agents each
    edges = [(i, j, 2, 50) for i in range(5) for j in range(i+1, 5)]  # clique 1: friend bonds (type=2)
    edges += [(i, j, 2, 50) for i in range(5, 10) for j in range(i+1, 10)]  # clique 2
    mem_sigs = {i: [(0, 10, -1)] for i in range(10)}  # all share famine memory
    from chronicler.validate import detect_communities
    communities = detect_communities(edges, mem_sigs)
    assert len(communities) == 2
    assert all(len(c) == 5 for c in communities)


def test_community_excludes_kin_only():
    """Communities with only kin bonds are excluded."""
    edges = [(0, 1, 0, 60), (1, 2, 0, 60), (0, 2, 0, 60)]  # bond_type 0 = Kin
    mem_sigs = {0: [(0, 10, -1)], 1: [(0, 10, -1)], 2: [(0, 10, -1)]}
    from chronicler.validate import detect_communities
    communities = detect_communities(edges, mem_sigs)
    assert len(communities) == 0  # excluded: kin-only


def test_needs_diversity_detects_behavioral_difference():
    """Agents with divergent needs show different behavioral event rates."""
    # Synthetic: two groups of agents matched on traits, divergent on safety need
    # Group A (low safety): agent_ids 0-4, safety=0.1 → expect higher migration
    # Group B (high safety): agent_ids 5-9, safety=0.9 → expect lower migration
    needs_data = {
        "agent_id": list(range(10)),
        "safety": [0.1]*5 + [0.9]*5,
        "autonomy": [0.5]*10,
        "social": [0.5]*10,
        "spiritual": [0.5]*10,
        "material": [0.5]*10,
        "purpose": [0.5]*10,
        "civ_affinity": [0]*10,
        "region": [0]*10,
        "occupation": [1]*10,  # all soldiers
        "satisfaction": [0.5]*10,
        "boldness": [0.5]*10,
        "ambition": [0.5]*10,
        "loyalty_trait": [0.5]*10,
    }
    # Events: low-safety agents migrate more
    events_data = [
        {"agent_id": 0, "event_type": 1, "turn": 5},  # migration
        {"agent_id": 1, "event_type": 1, "turn": 7},
        {"agent_id": 2, "event_type": 1, "turn": 9},
        {"agent_id": 3, "event_type": 1, "turn": 11},
        # high-safety agents: only 1 migrates
        {"agent_id": 5, "event_type": 1, "turn": 15},
    ]
    from chronicler.validate import compute_needs_diversity
    result = compute_needs_diversity(
        needs_data=needs_data,
        events_data=events_data,
        need_name="safety",
        need_divergence=0.2,
    )
    assert result["pairs_found"] > 0
    assert result["low_need_event_rate"] > result["high_need_event_rate"]


def test_era_inflection_detects_collapse():
    """Detect inflection point when population drops >30%."""
    pop_series = [100]*50 + [60]*50  # sharp drop at t=50
    from chronicler.validate import detect_inflection_points
    points = detect_inflection_points(pop_series, smoothing_window=5)
    assert any(45 <= p <= 55 for p in points)


def test_era_inflection_no_false_positive_on_noise():
    """Noisy but stable series produces no inflection points."""
    import random; random.seed(42)
    pop_series = [100 + random.randint(-5, 5) for _ in range(100)]
    from chronicler.validate import detect_inflection_points
    points = detect_inflection_points(pop_series, smoothing_window=5)
    assert len(points) == 0


def _era_trajectory(name, population, *, treasury=None, stability=None, start_turn=1):
    n = len(population)
    return {
        "civ_name": name,
        "turn": list(range(start_turn, start_turn + n)),
        "population": population,
        "treasury": treasury if treasury is not None else [100] * n,
        "stability": stability if stability is not None else [40] * n,
        "territory": [2] * n,
        "prestige": [0] * n,
    }


# Civ A declines slowly from 100 to 60 over turns 41-80: a 40% collapse that
# no inflection of its own signals marks (the slope stays under 3 sigma).
_SLOW_DECLINE = [100] * 40 + [100 - k for k in range(1, 41)] + [60] * 40


def test_collapse_episodes_find_every_collapse_on_the_smoothed_series():
    from chronicler.validate import detect_collapse_episodes

    twice = [100] * 20 + [60] * 20 + [100] * 20 + [50] * 20
    episodes = detect_collapse_episodes(twice)
    assert len(episodes) == 2
    (p1, t1, pv1, tv1), (p2, t2, pv2, tv2) = episodes
    assert p1 < t1 < p2 < t2 and pv1 == pv2 == 100 and tv1 == 60 and tv2 == 50
    # A one-turn dip of a small population is not a collapse once smoothed.
    assert detect_collapse_episodes([40] * 20 + [25] + [40] * 20) == []
    # Without a rebound the fall stays one episode, down to its lowest point.
    assert [(e[2], e[3]) for e in detect_collapse_episodes([100] * 10 + [60] * 10 + [70] * 10 + [30] * 10)] == [(100, 30)]
    # A civ that dies collapses to zero.
    assert detect_collapse_episodes([50] * 20 + [0] * 20)[0][3] == 0


def test_era_oracle_needs_the_collapsing_civs_own_signal():
    """Another civ's treasury jump no longer covers a collapse."""
    from chronicler.validate import detect_inflection_points, run_era_oracle

    assert all(not detect_inflection_points([float(v) for v in series])
               for series in (_SLOW_DECLINE, [100] * 120, [40] * 120, [2] * 120))
    rich = [100] * 60 + [1000] * 60  # civ B's treasury jumps at turn 61
    assert detect_inflection_points([float(v) for v in rich])
    run = {"seed": 1, "civ_trajectories": [
        _era_trajectory("A", _SLOW_DECLINE),
        _era_trajectory("B", [80] * 120, treasury=rich),
    ]}
    result = run_era_oracle([run])
    assert result["silent_collapse_seeds"] == 1
    assert [(e["civ"], e["peak_turn"]) for e in result["silent_collapse_episodes"]] == [("A", 40)]
    assert result["per_seed"][0]["collapse_count"] == 1


def test_era_oracle_counts_a_recorded_crisis_of_the_collapsing_civ():
    from chronicler.validate import run_era_oracle

    def seed(crises):
        return {"seed": 1, "civ_crisis_event_turns": crises, "civ_trajectories": [
            _era_trajectory("A", _SLOW_DECLINE), _era_trajectory("B", [80] * 120)]}

    assert run_era_oracle([seed({"A": [70]})])["silent_collapse_seeds"] == 0  # during the fall
    assert run_era_oracle([seed({"A": [37]})])["silent_collapse_seeds"] == 0  # within 5 turns before the peak
    marked = run_era_oracle([seed({"A": [70]})])
    assert (marked["collapses_marked_by_era_signal"], marked["collapses_marked_by_crisis_only"]) == (0, 1)
    assert run_era_oracle([seed({"B": [70]})])["silent_collapse_seeds"] == 1  # another civ's crisis
    assert run_era_oracle([seed({"A": [10, 130]})])["silent_collapse_seeds"] == 1  # long before, long after


def test_era_crisis_turns_keep_only_crises_that_name_the_civ():
    from chronicler.validation_io import ERA_CRISIS_EVENT_TYPES, _civ_crisis_event_turns

    bundle = {"events_timeline": [
        {"turn": 5, "event_type": "famine", "actors": ["A"]},
        {"turn": 6, "event_type": "epidemic", "actors": ["B"], "civs": ["A"]},
        {"turn": 7, "event_type": "develop", "actors": ["A"]},
        {"turn": 8, "event_type": "loan_taken", "actors": ["A"]},
        {"turn": 9, "event_type": "war", "actors": ["A", "B"]},
    ]}
    assert _civ_crisis_event_turns(bundle) == {"A": [5, 6, 9], "B": [6, 9]}
    assert {"famine", "epidemic", "war", "mass_migration", "civ_conquered"} <= ERA_CRISIS_EVENT_TYPES
    assert not {"develop", "loan_taken", "trade", "build_started"} & ERA_CRISIS_EVENT_TYPES


def test_era_oracle_reads_a_late_civs_series_on_world_turns():
    """A seceded civ's index 0 is its first world turn, not turn 1."""
    from chronicler.validate import run_era_oracle

    run = {"seed": 1, "civ_crisis_event_turns": {"S": [150]}, "civ_trajectories": [
        _era_trajectory("S", _SLOW_DECLINE, start_turn=101)]}
    # The fall runs over world turns 141-180; a crisis at turn 150 marks it.
    assert run_era_oracle([run])["silent_collapse_seeds"] == 0
    run["civ_crisis_event_turns"] = {"S": [50]}  # index 50 would be inside the fall
    assert run_era_oracle([run])["silent_collapse_episodes"][0]["peak_turn"] == 140


def test_era_oracle_seed_fractions():
    from chronicler.validate import run_era_oracle

    rich = [100] * 60 + [1000] * 60  # B's treasury and stability each turn once
    calm = [20] * 100 + [60] * 20

    def seed(number, silent):
        crises = {} if silent else {"A": [60]}
        return {"seed": number, "civ_crisis_event_turns": crises, "civ_trajectories": [
            _era_trajectory("A", _SLOW_DECLINE),
            _era_trajectory("B", [80] * 120, treasury=rich, stability=calm)]}

    one_in_ten = run_era_oracle([seed(n, n == 0) for n in range(10)])
    assert (one_in_ten["status"], one_in_ten["silent_collapse_seeds"]) == ("PASS", 1)
    two_in_ten = run_era_oracle([seed(n, n < 2) for n in range(10)])
    assert (two_in_ten["status"], two_in_ten["silent_collapse_seeds"]) == ("FAIL", 2)
    assert one_in_ten["seeds_with_inflections"] == 10


def test_cohort_distinctiveness_detects_anchoring():
    """Community members migrate less than matched non-community agents."""
    from chronicler.validate import compute_cohort_distinctiveness
    # Community: agents 0-4 (low migration)
    communities = [{0, 1, 2, 3, 4}]
    # Events: community agents migrate rarely, non-community agents migrate more
    events_data = [
        # Community: 1 migration
        {"agent_id": 0, "event_type": 1, "turn": 10},
        # Non-community: 4 migrations
        {"agent_id": 5, "event_type": 1, "turn": 5},
        {"agent_id": 6, "event_type": 1, "turn": 8},
        {"agent_id": 7, "event_type": 1, "turn": 12},
        {"agent_id": 8, "event_type": 1, "turn": 15},
    ]
    # Agent demographics for matching
    agent_data = {
        "agent_id": list(range(10)),
        "civ_affinity": [0]*10,
        "region": [0]*10,
        "occupation": [1]*10,  # all soldiers
    }
    result = compute_cohort_distinctiveness(
        communities=communities,
        events_data=events_data,
        agent_data=agent_data,
    )
    assert result["community_event_rate"] < result["control_event_rate"]
    assert result["communities_analyzed"] == 1


def test_artifact_oracle_checks_creation_rate():
    """Artifact oracle validates creation rate per civ per 100 turns."""
    from chronicler.validate import check_artifact_lifecycle
    bundles = [{"world_state": {"artifacts": [
        {"artifact_type": "relic", "status": "active", "owner_civ": "Aram", "mule_origin": False, "prestige_value": 3},
        {"artifact_type": "artwork", "status": "active", "owner_civ": "Aram", "mule_origin": True, "prestige_value": 2},
        {"artifact_type": "weapon", "status": "destroyed", "owner_civ": "Aram", "mule_origin": False, "prestige_value": 2},
    ]}, "metadata": {"total_turns": 500, "seed": 42}}]
    result = check_artifact_lifecycle(bundles, num_civs=4)
    assert "creation_rate_per_civ_per_100" in result
    assert "type_diversity_ok" in result


def test_arc_classifier_rags_to_riches():
    """Rising trajectory classified as Rags to Riches."""
    from chronicler.validate import classify_civ_arc
    trajectory = {"population": list(range(50, 150))}
    arc = classify_civ_arc(trajectory)
    assert arc == "rags_to_riches"


def test_arc_classifier_prestige_only_successor_is_not_rags_to_riches():
    from chronicler.validate import classify_civ_arc

    trajectory = {
        "population": [1] * 80,
        "territory": [1] * 80,
        "prestige": list(range(80)),
    }

    assert classify_civ_arc(trajectory) != "rags_to_riches"


def test_arc_classifier_prestige_masked_tiny_remnant_after_boom_is_not_rags_to_riches():
    from chronicler.validate import classify_civ_arc

    trajectory = {
        "population": [1] * 20 + [10] * 20 + [2] * 20,
        "territory": [1] * 60,
        "prestige": list(range(1, 61)),
    }

    assert classify_civ_arc(trajectory) == "icarus"


def test_arc_classifier_prestige_masked_material_boom_bust_is_not_stable():
    from chronicler.validate import classify_civ_arc

    trajectory = {
        "population": [10] * 20 + [35] * 20 + [0] * 20,
        "territory": [1] * 20 + [3] * 20 + [0] * 20,
        "prestige": list(range(1, 61)),
    }

    arc = classify_civ_arc(trajectory)

    assert arc == "icarus"


def test_arc_classifier_prestige_masked_material_collapse_is_not_stable():
    from chronicler.validate import classify_civ_arc

    trajectory = {
        "population": [30] * 20 + [12] * 20 + [0] * 20,
        "territory": [3] * 20 + [1] * 20 + [0] * 20,
        "prestige": list(range(1, 61)),
    }

    arc = classify_civ_arc(trajectory)

    assert arc == "riches_to_rags"


def test_arc_classifier_icarus():
    """Rise then fall classified as Icarus."""
    from chronicler.validate import classify_civ_arc
    pop = list(range(50, 100)) + list(range(100, 50, -1))
    trajectory = {"population": pop}
    arc = classify_civ_arc(trajectory)
    assert arc == "icarus"


def test_arc_classifier_terminal_collapse_prefers_riches_to_rags():
    from chronicler.validate import classify_civ_arc

    # Brief early rise, then sustained terminal decline to extinction.
    # The local derivative pattern starts up then down, but the coarse thirds
    # summary is dominated by decline.
    trajectory = {"population": [20, 30, 50, 40, 30, 20, 10, 0, 0, 0, 0, 0, 0, 0, 0]}

    assert classify_civ_arc(trajectory) == "riches_to_rags"


def test_arc_classifier_long_horizon_modest_peak_extinction_prefers_riches_to_rags():
    from chronicler.validate import classify_civ_arc

    population = [40] * 60 + [55] * 60 + [90] * 40 + [45] * 40 + [0] * 300
    trajectory = {"population": population}

    assert len(population) >= 400
    assert classify_civ_arc(trajectory) == "riches_to_rags"


def test_arc_classifier_man_in_a_hole():
    from chronicler.validate import classify_civ_arc
    pop = list(range(100, 50, -1)) + list(range(50, 110))
    trajectory = {"population": pop}
    assert classify_civ_arc(trajectory) == "man_in_a_hole"


def test_arc_classifier_cinderella():
    from chronicler.validate import classify_civ_arc
    pop = list(range(50, 90)) + list(range(90, 60, -1)) + list(range(60, 110))
    trajectory = {"population": pop}
    assert classify_civ_arc(trajectory) == "cinderella"


def test_arc_classifier_oedipus():
    from chronicler.validate import classify_civ_arc
    pop = list(range(100, 60, -1)) + list(range(60, 110)) + list(range(110, 50, -1))
    trajectory = {"population": pop}
    assert classify_civ_arc(trajectory) == "oedipus"


def test_artifact_lifecycle_counts_lost_and_destroyed():
    """Oracle 5 loss rate should include both LOST and DESTROYED artifacts."""
    from chronicler.validate import check_artifact_lifecycle
    bundles = [{
        "world_state": {"artifacts": [
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "monument", "status": "lost", "mule_origin": False},
            {"artifact_type": "treatise", "status": "destroyed", "mule_origin": False},
            {"artifact_type": "epic", "status": "active", "mule_origin": True},
        ]},
        "metadata": {"total_turns": 100},
    }]
    result = check_artifact_lifecycle(bundles)
    # 2 of 4 artifacts are lost or destroyed = 0.50
    assert result["loss_destruction_count"] == 2
    assert result["loss_destruction_rate"] == 0.50


def test_artifact_loss_band_is_calibrated_for_living_worlds():
    """2026-10: 2-30% with both loss channels alive (see the extinction-fix doc)."""
    from chronicler.validate import check_artifact_lifecycle, run_artifact_oracle

    def batch(lost, destroyed, active):
        statuses = ["lost"] * lost + ["destroyed"] * destroyed + ["active"] * active
        types = ["relic", "artwork", "monument", "treatise"]
        return [{
            "world_state": {"artifacts": [
                {"artifact_type": types[i % 4], "status": s, "mule_origin": False}
                for i, s in enumerate(statuses)
            ]},
            "metadata": {"total_turns": 500},
        }]

    living = check_artifact_lifecycle(batch(lost=1, destroyed=2, active=97))  # 3%
    assert living["loss_destruction_rate_ok"] and living["loss_channels_ok"]
    assert (living["lost_count"], living["destroyed_count"]) == (1, 2)
    broken = check_artifact_lifecycle(batch(lost=0, destroyed=1, active=99))  # 1%
    assert not broken["loss_destruction_rate_ok"]
    no_capture_loss = check_artifact_lifecycle(batch(lost=0, destroyed=5, active=95))
    assert no_capture_loss["loss_destruction_rate_ok"] and not no_capture_loss["loss_channels_ok"]
    fragile = check_artifact_lifecycle(batch(lost=20, destroyed=15, active=65))  # 35%
    assert not fragile["loss_destruction_rate_ok"]
    runs = [{"bundle": b} for b in batch(lost=0, destroyed=5, active=95)]
    assert run_artifact_oracle(runs)["status"] == "PARTIAL"


def test_artifact_lifecycle_creation_rate():
    """Creation rate sanity check."""
    from chronicler.validate import check_artifact_lifecycle
    bundles = [{
        "world_state": {"artifacts": [
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "monument", "status": "active", "mule_origin": False},
        ]},
        "metadata": {"total_turns": 100},
    }]
    result = check_artifact_lifecycle(bundles, num_civs=4)
    # 2 artifacts / (4 civs * 100/100) = 0.5
    assert result["creation_rate_per_civ_per_100"] == 0.5


def test_artifact_lifecycle_accepts_stochastic_lower_creation_tolerance():
    """Long-horizon duplicate-suppressed artifact runs can land just under 1.0."""
    from chronicler.validate import check_artifact_lifecycle

    artifact_types = ["relic"] * 7 + ["artwork"] * 6 + ["treatise"] * 5
    artifacts = [
        {
            "artifact_type": artifact_type,
            "status": "lost" if idx < 2 else "active",
            "owner_civ": "Aram",
            "mule_origin": False,
            "prestige_value": 2,
        }
        for idx, artifact_type in enumerate(artifact_types)
    ]
    bundles = [{
        "world_state": {"artifacts": artifacts},
        "metadata": {"total_turns": 500, "seed": 42},
    }]

    result = check_artifact_lifecycle(bundles, num_civs=4)

    assert result["creation_rate_per_civ_per_100"] == 0.9
    assert result["creation_rate_strict_ok"] is False
    assert result["creation_rate_ok"] is True
    assert result["creation_rate_adjudication"] == "stochastic_tolerance"
    assert result["type_diversity_ok"] is True
    assert result["loss_destruction_rate_ok"] is True


def test_artifact_lifecycle_type_diversity():
    """No single type > 50%."""
    from chronicler.validate import check_artifact_lifecycle
    bundles = [{
        "world_state": {"artifacts": [
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "relic", "status": "active", "mule_origin": False},
            {"artifact_type": "epic", "status": "active", "mule_origin": False},
        ]},
        "metadata": {"total_turns": 100},
    }]
    result = check_artifact_lifecycle(bundles)
    assert result["type_diversity_ok"] is False  # relic = 75%


def test_classify_civ_arc_monotone_down():
    from chronicler.validate import classify_civ_arc
    traj = {"population": [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]}
    assert classify_civ_arc(traj) == "riches_to_rags"


def test_classify_civ_arc_monotone_up():
    from chronicler.validate import classify_civ_arc
    traj = {"population": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]}
    assert classify_civ_arc(traj) == "rags_to_riches"


def test_classify_civ_arc_stable():
    from chronicler.validate import classify_civ_arc
    traj = {"population": [50] * 30}
    assert classify_civ_arc(traj) == "stable"


def test_run_community_oracle_uses_best_sampled_turn():
    from chronicler.validate import run_community_oracle

    clique_edges = [(i, j, 2, 50) for i in range(5) for j in range(i + 1, 5)]
    relationship_columns = {
        "turn": [100] * len(clique_edges),
        "agent_id": [a for a, _b, _bt, _sent in clique_edges],
        "target_id": [b for _a, b, _bt, _sent in clique_edges],
        "bond_type": [bt for _a, _b, bt, _sent in clique_edges],
        "sentiment": [sent for _a, _b, _bt, sent in clique_edges],
    }
    memory_columns = {
        "turn": [100] * 5 + [110],
        "agent_id": [0, 1, 2, 3, 4, 99],
        "event_type": [0, 0, 0, 0, 0, 1],
        "memory_turn": [95, 95, 95, 95, 95, 110],
        "valence_sign": [-1, -1, -1, -1, -1, 1],
    }

    result = run_community_oracle([{
        "seed": 42,
        "relationship_columns": relationship_columns,
        "memory_columns": memory_columns,
    }])

    assert result["status"] == "PASS"
    assert result["qualifying_seed_count"] == 1
    assert result["per_seed"][0]["snapshot_turn"] == 100
    assert result["per_seed"][0]["qualifying_communities"] == 1


def test_needs_best_of_uses_all_sampled_turns():
    from chronicler.validate import run_needs_oracle_best_of as run_needs_oracle

    turn_10 = {
        "agent_id": list(range(10)),
        "safety": [0.1] * 5 + [0.9] * 5,
        "autonomy": [0.5] * 10,
        "social": [0.5] * 10,
        "spiritual": [0.5] * 10,
        "material": [0.5] * 10,
        "purpose": [0.5] * 10,
        "civ_affinity": [0] * 10,
        "region": [0] * 10,
        "occupation": [1] * 10,
        "satisfaction": [0.5] * 10,
        "boldness": [0.5] * 10,
        "ambition": [0.5] * 10,
        "loyalty_trait": [0.5] * 10,
    }
    turn_100 = {
        "agent_id": list(range(10)),
        "safety": [0.5] * 10,
        "autonomy": [0.5] * 10,
        "social": [0.5] * 10,
        "spiritual": [0.5] * 10,
        "material": [0.5] * 10,
        "purpose": [0.5] * 10,
        "civ_affinity": [0] * 10,
        "region": [0] * 10,
        "occupation": [1] * 10,
        "satisfaction": [0.5] * 10,
        "boldness": [0.5] * 10,
        "ambition": [0.5] * 10,
        "loyalty_trait": [0.5] * 10,
    }
    needs_columns = {"turn": [10] * 10 + [100] * 10}
    for key in turn_10:
        needs_columns[key] = turn_10[key] + turn_100[key]

    events = [
        {"agent_id": 0, "event_type": 1, "turn": 12},
        {"agent_id": 1, "event_type": 1, "turn": 14},
        {"agent_id": 2, "event_type": 1, "turn": 16},
        {"agent_id": 3, "event_type": 1, "turn": 18},
        {"agent_id": 5, "event_type": 1, "turn": 19},
    ]

    result = run_needs_oracle([{
        "seed": 7,
        "bundle": {"metadata": {"total_turns": 140}},
        "needs_columns": needs_columns,
        "events": events,
    }])

    assert result["status"] == "PASS"
    assert result["seeds_with_expected_sign"] == 1
    assert result["per_seed"][0]["snapshot_turn"] == 10
    assert result["per_seed"][0]["need_name"] == "safety"


def test_needs_candidate_priority_prefers_expected_sign():
    from chronicler.validate import _needs_candidate_priority

    negative = {
        "pairs_found": 5,
        "rate_difference": -2.0,
        "effect_size": 2.5,
    }
    positive = {
        "pairs_found": 2,
        "rate_difference": 0.5,
        "effect_size": 0.5,
    }

    assert _needs_candidate_priority(positive, 100) > _needs_candidate_priority(negative, 50)


REBELLION = 2  # validation_io.EVENT_NAME_TO_CODE["rebellion"]
MIGRATION = 1


def _needs_rows(agents):
    """Snapshot columns for (agent_id, region, needs overrides) rows."""
    names = ("safety", "autonomy", "social", "spiritual", "material", "purpose")
    columns = {name: [] for name in ("agent_id", "region", *names)}
    for agent_id, region, needs in agents:
        columns["agent_id"].append(agent_id)
        columns["region"].append(region)
        for name in names:
            columns[name].append(needs.get(name, 0.5))
    count = len(agents)
    columns.update(
        civ_affinity=[0] * count, occupation=[1] * count, satisfaction=[0.5] * count,
        boldness=[0.5] * count, ambition=[0.5] * count, loyalty_trait=[0.5] * count,
    )
    return columns


def _autonomy_confound_run():
    """One seed where rebellion's own autonomy boost reverses the pairing.

    Snapshot at turn 100. Regions 0-3: quiet pairs; the low-autonomy agent
    rebels once in the next 20 turns, the high one never. Regions 4-7: the
    high agent reads 0.6 only because it rebelled before the snapshot (+0.10
    per rebellion; turn 95, or a burst at 50-52 for region 7) and keeps
    rebelling, three times; its low partner never does.
    """
    rows, events = [], []
    for region in range(4):
        low, high = 2 * region, 2 * region + 1
        rows += [(low, region, {"autonomy": 0.1}), (high, region, {"autonomy": 0.5})]
        events.append({"agent_id": low, "event_type": REBELLION, "turn": 105})
    for region in range(4, 8):
        low, high = 2 * region, 2 * region + 1
        rows += [(low, region, {"autonomy": 0.1}), (high, region, {"autonomy": 0.6})]
        prior = (50, 51, 52) if region == 7 else (95,)
        events += [{"agent_id": high, "event_type": REBELLION, "turn": t} for t in prior]
        events += [{"agent_id": high, "event_type": REBELLION, "turn": t} for t in (102, 108, 115)]
    columns = _needs_rows(rows)
    return {
        "seed": 3,
        "bundle": {"metadata": {"total_turns": 140}},
        "needs_columns": {"turn": [100] * len(rows), **columns},
        "events": events,
    }


def test_needs_best_of_autonomy_confound_reverses_then_exclusion_restores():
    from chronicler.validate import run_needs_oracle_best_of as run_needs_oracle

    run = _autonomy_confound_run()

    confounded = run_needs_oracle([run], exclude_prior_rebels=False)
    assert confounded["status"] == "FAIL"
    assert confounded["seeds_with_expected_sign"] == 0
    seed = confounded["per_seed"][0]
    assert (seed["need_name"], seed["pairs_found"]) == ("autonomy", 8)
    # 4 low-agent rebellions against 12 high-agent ones: low / high = 1/3.
    assert seed["rate_difference"] == pytest.approx(4 / 8 - 12 / 8)

    fixed = run_needs_oracle([run])
    assert fixed["autonomy_excludes_prior_rebels"] is True
    assert fixed["status"] == "PASS"
    assert fixed["seeds_with_expected_sign"] == 1
    seed = fixed["per_seed"][0]
    # Prior rebels, including the turn 50-52 burst, are left out; their
    # partners have no one to pair with.
    assert (seed["need_name"], seed["pairs_found"]) == ("autonomy", 4)
    assert seed["rate_difference"] == pytest.approx(1.0)
    assert run["events"] == _autonomy_confound_run()["events"]


def test_needs_autonomy_exclusion_counts_rebellions_through_the_snapshot_turn():
    from chronicler.validation_io import _first_event_turns, _without_agents_with_event_by

    # Sidecars are written after the snapshot turn's agent tick, so a
    # rebellion on turn 100 precedes the turn-100 reading.
    events = [
        {"agent_id": 1, "event_type": REBELLION, "turn": 100},
        {"agent_id": 2, "event_type": REBELLION, "turn": 101},
        {"agent_id": 3, "event_type": MIGRATION, "turn": 99},
        {"agent_id": 4, "event_type": REBELLION, "turn": 130},
        {"agent_id": 4, "event_type": REBELLION, "turn": 12},
    ]
    columns = _needs_rows([(agent_id, 0, {}) for agent_id in range(5)])
    first = _first_event_turns(events, REBELLION)
    assert first == {1: 100, 2: 101, 4: 12}

    kept = _without_agents_with_event_by(columns, first, 100)
    assert kept["agent_id"] == [0, 2, 3]
    assert all(len(values) == 3 for values in kept.values())
    assert _without_agents_with_event_by(columns, first, 11) is columns


def test_needs_best_of_rebel_exclusion_leaves_other_pairings_unchanged():
    from chronicler.validate import run_needs_oracle_best_of as run_needs_oracle

    # Material -> migration among agents who all rebelled just before the
    # snapshot: only the autonomy pairing drops prior rebels.
    rows = []
    for region in range(3):
        rows += [(2 * region, region, {"material": 0.1}), (2 * region + 1, region, {"material": 0.6})]
    events = [{"agent_id": agent_id, "event_type": REBELLION, "turn": 99} for agent_id in range(6)]
    events += [{"agent_id": 2 * region, "event_type": MIGRATION, "turn": 104} for region in range(3)]
    run = {
        "seed": 4,
        "bundle": {"metadata": {"total_turns": 140}},
        "needs_columns": {"turn": [100] * len(rows), **_needs_rows(rows)},
        "events": events,
    }

    before = run_needs_oracle([run], exclude_prior_rebels=False)
    after = run_needs_oracle([run])
    assert before["per_seed"] == after["per_seed"]
    assert after["per_seed"][0]["need_name"] == "material"
    assert after["per_seed"][0]["pairs_found"] == 3
    assert after["status"] == "PASS"


# --- Needs oracle method 2: pooled matched pairs -------------------------


def _seed_copies(run, seeds):
    return [{**run, "seed": seed} for seed in seeds]


def _reference_needs_pairs(needs_data, need_name, need_divergence, personality_tolerance):
    """Method 1's all-agents scan, verbatim, as the matching reference."""
    agents = [
        {
            "id": aid, "need": needs_data[need_name][i], "civ_affinity": needs_data["civ_affinity"][i],
            "region": needs_data["region"][i], "occupation": needs_data["occupation"][i],
            "boldness": needs_data["boldness"][i], "ambition": needs_data["ambition"][i],
            "loyalty": needs_data["loyalty_trait"][i],
        }
        for i, aid in enumerate(needs_data["agent_id"])
    ]
    pairs, used = [], set()
    for i, a in enumerate(agents):
        if a["id"] in used:
            continue
        for b in agents[i + 1:]:
            if b["id"] in used:
                continue
            if (a["civ_affinity"], a["region"], a["occupation"]) != (b["civ_affinity"], b["region"], b["occupation"]):
                continue
            if any(abs(a[k] - b[k]) > personality_tolerance for k in ("boldness", "ambition", "loyalty")):
                continue
            if abs(a["need"] - b["need"]) <= need_divergence:
                continue
            used.update((a["id"], b["id"]))
            pairs.append((a["id"], b["id"]) if a["need"] < b["need"] else (b["id"], a["id"]))
            break
    return pairs


@pytest.mark.parametrize("gap", [0.1, 0.2])
def test_match_needs_pairs_equals_the_all_agents_scan(gap):
    import random
    from chronicler.validation_io import _match_needs_pairs

    rng = random.Random(11)
    count = 400
    columns = {
        "agent_id": rng.sample(range(10_000), count),
        "civ_affinity": [rng.randrange(3) for _ in range(count)],
        "region": [rng.randrange(4) for _ in range(count)],
        "occupation": [rng.randrange(2) for _ in range(count)],
        # Coarse grids put many trait gaps exactly at the tolerance.
        "boldness": [rng.randrange(5) / 10 for _ in range(count)],
        "ambition": [rng.randrange(4) / 10 for _ in range(count)],
        "loyalty_trait": [rng.randrange(4) / 10 for _ in range(count)],
        "material": [rng.random() for _ in range(count)],
    }
    expected = _reference_needs_pairs(columns, "material", gap, 0.1)
    assert len(expected) > 20
    assert _match_needs_pairs(columns, "material", gap, 0.1) == expected


def test_pooled_net_concordance_and_sign_test_by_hand():
    from chronicler.validation_io import _pooled_net_concordance, _sign_test_p

    pooled = _pooled_net_concordance([(5, 1), (3, 3), (0, 0), (4, 0)], 0.95)
    # (4 + 0 + 4) / 16; residuals 1, 9, 4; SE sqrt(3/2 * 14) / 16; t(0.95, 2) = 2.919986.
    assert pooled["clusters"] == 3
    assert pooled["net_concordance"] == pytest.approx(0.5)
    assert pooled["standard_error"] == pytest.approx(21 ** 0.5 / 16)
    assert pooled["lower_bound"] == pytest.approx(0.5 - 2.919986 * 21 ** 0.5 / 16, abs=1e-5)
    assert _pooled_net_concordance([(3, 1)], 0.95)["lower_bound"] is None
    assert _pooled_net_concordance([(0, 0)], 0.95)["net_concordance"] is None
    assert _sign_test_p(5, 0) == pytest.approx(1 / 32)
    assert _sign_test_p(3, 3) == pytest.approx(42 / 64)
    assert _sign_test_p(0, 0) == 1.0


def _material_world(seed: int, low_movers: int, high_movers: int, *, turn: int = 100, total_turns: int = 140):
    """One seed: cells of two matched agents, material 0.2 against 0.7.

    In the first ``low_movers`` cells the low-material agent migrates once in
    the outcome window; in the next ``high_movers`` cells its partner does.
    """
    rows, events = [], []
    cells = low_movers + high_movers + 2
    for region in range(cells):
        low, high = 2 * region, 2 * region + 1
        rows += [(low, region, {"material": 0.2}), (high, region, {"material": 0.7})]
        if region < low_movers:
            events.append({"agent_id": low, "event_type": MIGRATION, "turn": turn + 5})
        elif region < low_movers + high_movers:
            events.append({"agent_id": high, "event_type": MIGRATION, "turn": turn + 5})
    return {
        "seed": seed,
        "bundle": {"metadata": {"total_turns": total_turns}},
        "needs_columns": {"turn": [turn] * len(rows), **_needs_rows(rows)},
        "events": events,
    }


def test_needs_oracle_passes_when_lower_need_agents_act_more():
    from chronicler.validate import run_needs_oracle

    runs = [_material_world(seed, 8 + seed % 3, 2) for seed in range(10)]
    result = run_needs_oracle(runs)

    assert result["status"] == "PASS"
    assert result["method_version"] == 3
    assert result["failed_criteria"] == []
    assert result["seeds_with_expected_sign"] == 10
    assert (result["concordant_pairs"], result["discordant_pairs"]) == (sum(8 + s % 3 for s in range(10)), 20)
    assert result["net_concordance_lower_bound"] > 0.5
    material = result["by_pairing"]["material"]
    assert material["pairs"] == sum(12 + s % 3 for s in range(10))
    assert result["per_seed"][0]["by_pairing"] == {"material": [12, 8, 2]}
    assert result["per_seed"][0]["sign_test_p"] == pytest.approx(56 / 1024, abs=1e-4)
    # Every low agent (0.2) is below the material threshold (0.30): the
    # binding pairs are all the pairs.
    binding = result["binding"]
    assert (binding["concordant_pairs"], binding["discordant_pairs"]) == (
        result["concordant_pairs"], result["discordant_pairs"])
    assert binding["net_concordance_lower_bound"] == result["net_concordance_lower_bound"]
    assert result["per_seed"][0]["binding"] == [12, 8, 2]
    assert result["per_seed"][0]["binding_by_pairing"] == {"material": [12, 8, 2]}


def _material_world_above_threshold(seed: int, binding_low_movers: int, binding_high_movers: int):
    """The passing world, plus cells whose low agent is above the threshold.

    Ten cells pair material 0.45 against 0.75 (neither binds) and the low
    agent migrates; ``binding_*`` cells pair 0.2 against 0.7 as before.
    """
    run = _material_world(seed, binding_low_movers, binding_high_movers)
    columns = run["needs_columns"]
    first = len(columns["agent_id"])
    rows = []
    for cell in range(10):
        low, high = first + 2 * cell, first + 2 * cell + 1
        region = 1000 + cell
        rows += [(low, region, {"material": 0.45}), (high, region, {"material": 0.75})]
        run["events"].append({"agent_id": low, "event_type": MIGRATION, "turn": 105})
    extra = _needs_rows(rows)
    for name in columns:
        columns[name] = columns[name] + (extra[name] if name != "turn" else [100] * len(rows))
    return run


def test_needs_oracle_binding_pairs_must_carry_the_effect():
    from chronicler.validate import run_needs_oracle

    # Above the threshold the low agents move (as when other channels carry
    # the association); among binding pairs the event falls either way, as
    # with the need terms zeroed.
    runs = [_material_world_above_threshold(seed, 3 + seed % 2, 4 - seed % 2) for seed in range(10)]
    result = run_needs_oracle(runs)

    assert result["net_concordance_lower_bound"] > 0
    assert result["seeds_with_expected_sign"] == 10
    binding = result["binding"]
    assert binding["thresholds"]["material"] == 0.30
    assert (binding["concordant_pairs"], binding["discordant_pairs"]) == (35, 35)
    assert binding["net_concordance"] == 0.0
    assert result["failed_criteria"] == ["binding_lower_bound"]
    assert result["status"] == "FAIL"

    # Method 2 alone passes the same seeds.
    pooled = run_needs_oracle(runs, require_binding=False)
    assert pooled["status"] == "PASS"
    assert pooled["method_version"] == 2
    assert "binding" not in pooled and "binding" not in pooled["per_seed"][0]
    assert {k: v for k, v in result.items() if k not in ("binding", "per_seed", "status", "failed_criteria",
                                                         "method_version", "criterion")} == {
        k: v for k, v in pooled.items() if k not in ("per_seed", "status", "failed_criteria",
                                                     "method_version", "criterion")}

    # With the effect among the binding pairs too, method 3 passes.
    runs = [_material_world_above_threshold(seed, 8 + seed % 3, 2) for seed in range(10)]
    result = run_needs_oracle(runs)
    assert result["status"] == "PASS"
    assert result["binding"]["net_concordance_lower_bound"] > 0.5


def test_needs_oracle_fails_without_binding_pairs():
    from chronicler.validate import run_needs_oracle

    # Only above-threshold pairs: no binding pairs, no bound.
    runs = [_material_world_above_threshold(seed, 0, 0) for seed in range(10)]
    result = run_needs_oracle(runs)
    assert result["net_concordance_lower_bound"] > 0
    assert result["binding"]["informative_pairs"] == 0
    assert result["binding"]["net_concordance_lower_bound"] is None
    assert result["failed_criteria"] == ["binding_lower_bound"]
    assert result["status"] == "FAIL"


def test_needs_oracle_thresholds_mirror_the_native_constants():
    import re
    from pathlib import Path

    from chronicler.narrative import _NEED_THRESHOLDS
    from chronicler.validation_io import NEEDS_BEHAVIOUR_THRESHOLDS, NEEDS_PAIRINGS

    root = Path(__file__).resolve().parents[1]
    agent = (root / "chronicler-agents/src/agent.rs").read_text(encoding="utf-8")
    assert set(NEEDS_BEHAVIOUR_THRESHOLDS) == {need for need, _event in NEEDS_PAIRINGS}
    for need, threshold in NEEDS_BEHAVIOUR_THRESHOLDS.items():
        match = re.search(rf"pub const {need.upper()}_THRESHOLD: f32 = ([0-9.]+);", agent)
        assert match, need
        assert float(match.group(1)) == pytest.approx(threshold), need
        assert _NEED_THRESHOLDS[need] == pytest.approx(threshold), need


@pytest.mark.parametrize("break_kind", ["no_link", "reversed", "shuffled"])
def test_needs_oracle_fails_when_needs_no_longer_predict_behavior(break_kind):
    import random
    from chronicler.validate import run_needs_oracle

    if break_kind == "no_link":
        # The event falls on either agent: as many seeds one way as the other.
        runs = [_material_world(seed, 7, 5) if seed % 2 else _material_world(seed, 5, 7) for seed in range(10)]
    elif break_kind == "reversed":
        runs = [_material_world(seed, 2, 8 + seed % 3) for seed in range(10)]
    else:
        # The passing world above with each cell's needs permuted among its agents.
        runs = [_material_world(seed, 8 + seed % 3, 2) for seed in range(20)]
        rng = random.Random(5)
        for run in runs:
            columns = run["needs_columns"]
            for start in range(0, len(columns["agent_id"]), 2):
                if rng.random() < 0.5:
                    pair = columns["material"][start:start + 2]
                    columns["material"][start:start + 2] = pair[::-1]
    result = run_needs_oracle(runs)

    assert result["status"] == "FAIL"
    assert "net_concordance_lower_bound" in result["failed_criteria"]
    assert result["net_concordance_lower_bound"] <= 0
    if break_kind == "reversed":
        assert result["net_concordance"] < -0.5
        assert result["seeds_with_reversed_sign"] == 10


def test_needs_oracle_seed_fraction_fails_when_few_seeds_carry_the_pool():
    from chronicler.validate import run_needs_oracle

    # Four seeds with a strong effect, six balanced: the pooled bound is above
    # zero, but 4 of 10 seeds is below the 60% fraction.
    runs = [_material_world(seed, 20, 0) for seed in range(4)]
    runs += [_material_world(seed, 1, 1) for seed in range(4, 10)]
    result = run_needs_oracle(runs)

    assert result["net_concordance_lower_bound"] > 0
    assert (result["seeds_with_expected_sign"], result["required_seed_count"]) == (4, 6)
    assert result["failed_criteria"] == ["seed_fraction"]
    assert result["status"] == "FAIL"


def test_needs_oracle_needs_two_seeds_with_informative_pairs():
    from chronicler.validate import run_needs_oracle

    result = run_needs_oracle([_material_world(1, 10, 0)])
    assert result["net_concordance"] == 1.0
    assert result["net_concordance_lower_bound"] is None
    assert result["status"] == "FAIL"


def test_needs_oracle_pools_every_snapshot_whose_window_fits():
    from chronicler.validate import run_needs_oracle

    early = _material_world(0, 3, 0, turn=10)
    middle = _material_world(0, 2, 0, turn=100)
    # Turn 130: 130 + 20 > 140 turns, so its discordant pairs are not scored.
    late = _material_world(0, 0, 4, turn=130)
    columns = {name: early["needs_columns"][name] + middle["needs_columns"][name] + late["needs_columns"][name]
               for name in early["needs_columns"]}
    run = {"bundle": {"metadata": {"total_turns": 140}}, "needs_columns": columns,
           "events": early["events"] + middle["events"] + late["events"]}
    result = run_needs_oracle(_seed_copies(run, [1, 2]))

    seed = result["per_seed"][0]
    assert seed["snapshots"] == 2
    assert (seed["concordant"], seed["discordant"]) == (5, 0)
    assert seed["by_pairing"] == {"material": [9, 5, 0]}
    assert result["status"] == "PASS"


def test_needs_oracle_autonomy_confound_reverses_then_exclusion_restores():
    from chronicler.validate import run_needs_oracle

    runs = _seed_copies(_autonomy_confound_run(), [3, 4, 5])

    confounded = run_needs_oracle(runs, exclude_prior_rebels=False)
    assert confounded["status"] == "FAIL"
    autonomy = confounded["by_pairing"]["autonomy"]
    # Per seed: four quiet pairs with a rebellious low agent, four recidivists.
    assert (autonomy["pairs"], autonomy["concordant"], autonomy["discordant"]) == (24, 12, 12)
    assert confounded["net_concordance"] == 0.0

    fixed = run_needs_oracle(runs)
    assert fixed["autonomy_excludes_prior_rebels"] is True
    assert fixed["status"] == "PASS"
    autonomy = fixed["by_pairing"]["autonomy"]
    assert (autonomy["pairs"], autonomy["concordant"], autonomy["discordant"]) == (12, 12, 0)


def test_needs_rebel_exclusion_leaves_other_pairings_unchanged():
    from chronicler.validate import run_needs_oracle

    rows = []
    for region in range(3):
        rows += [(2 * region, region, {"material": 0.1}), (2 * region + 1, region, {"material": 0.6})]
    events = [{"agent_id": agent_id, "event_type": REBELLION, "turn": 99} for agent_id in range(6)]
    events += [{"agent_id": 2 * region, "event_type": MIGRATION, "turn": 104} for region in range(3)]
    run = {
        "bundle": {"metadata": {"total_turns": 140}},
        "needs_columns": {"turn": [100] * len(rows), **_needs_rows(rows)},
        "events": events,
    }
    runs = _seed_copies(run, [4, 5])

    before = run_needs_oracle(runs, exclude_prior_rebels=False)
    after = run_needs_oracle(runs)
    assert before["per_seed"] == after["per_seed"]
    assert after["per_seed"][0]["by_pairing"] == {"material": [3, 3, 0]}
    assert after["status"] == "PASS"


def test_run_cohort_oracle_uses_all_sampled_turns(monkeypatch):
    from chronicler.validate import run_cohort_oracle
    from chronicler import validation_io

    clique_edges = [(i, j, 2, 50) for i in range(5) for j in range(i + 1, 5)]
    relationship_columns = {
        "turn": [10] * len(clique_edges),
        "agent_id": [a for a, _b, _bt, _sent in clique_edges],
        "target_id": [b for _a, b, _bt, _sent in clique_edges],
        "bond_type": [bt for _a, _b, bt, _sent in clique_edges],
        "sentiment": [sent for _a, _b, _bt, sent in clique_edges],
    }
    memory_columns = {
        "turn": [10] * 5 + [100],
        "agent_id": [0, 1, 2, 3, 4, 99],
        "event_type": [0, 0, 0, 0, 0, 1],
        "memory_turn": [10, 10, 10, 10, 10, 100],
        "valence_sign": [-1, -1, -1, -1, -1, 1],
    }

    turn_10 = {
        "agent_id": list(range(10)),
        "civ_affinity": [0] * 10,
        "region": [0] * 10,
        "occupation": [1] * 10,
        "satisfaction": [0.5] * 10,
        "boldness": [0.5] * 10,
        "ambition": [0.5] * 10,
        "loyalty_trait": [0.5] * 10,
    }
    turn_100 = {
        "agent_id": list(range(10)),
        "civ_affinity": [0] * 10,
        "region": [0] * 10,
        "occupation": [1] * 10,
        "satisfaction": [0.5] * 10,
        "boldness": [0.5] * 10,
        "ambition": [0.5] * 10,
        "loyalty_trait": [0.5] * 10,
    }
    needs_columns = {"turn": [10] * 10 + [100] * 10}
    for key in turn_10:
        needs_columns[key] = turn_10[key] + turn_100[key]

    events = [
        {"agent_id": 0, "event_type": 1, "turn": 10},
        {"agent_id": 5, "event_type": 1, "turn": 12},
        {"agent_id": 6, "event_type": 1, "turn": 14},
        {"agent_id": 7, "event_type": 1, "turn": 16},
        {"agent_id": 8, "event_type": 1, "turn": 18},
        {"agent_id": 0, "event_type": 2, "turn": 11},
        {"agent_id": 1, "event_type": 2, "turn": 13},
        {"agent_id": 2, "event_type": 2, "turn": 15},
        {"agent_id": 5, "event_type": 2, "turn": 17},
    ]
    original_events = [event.copy() for event in events]
    scans = []
    rates = {}
    original_filter = validation_io._filter_events_window
    original_distinctiveness = validation_io.compute_cohort_distinctiveness

    def record_window(source, start_turn, window=20):
        assert source is events
        scans.append((start_turn, window))
        return original_filter(source, start_turn, window=window)

    def record_rates(*args, **kwargs):
        outcome = original_distinctiveness(*args, **kwargs)
        rates[kwargs["event_type"]] = (
            outcome["community_event_rate"], outcome["control_event_rate"],
        )
        return outcome

    monkeypatch.setattr(validation_io, "_filter_events_window", record_window)
    monkeypatch.setattr(validation_io, "compute_cohort_distinctiveness", record_rates)

    result = run_cohort_oracle([{
        "seed": 9,
        "bundle": {"metadata": {"total_turns": 140}},
        "relationship_columns": relationship_columns,
        "memory_columns": memory_columns,
        "needs_columns": needs_columns,
        "events": events,
    }])

    assert result["status"] == "PASS"
    assert result["seeds_with_expected_direction"] == 1
    assert result["per_seed"][0]["snapshot_turn"] == 10
    assert result["per_seed"][0]["migration_effect_direction"] == "community_lower"
    assert result["per_seed"][0]["rebellion_effect_direction"] == "community_higher"
    assert rates == {1: (0.2, 0.8), 2: (0.6, 0.2)}
    assert scans == [(10, 20)]
    assert events == original_events


def test_cohort_candidate_priority_prefers_expected_direction():
    from chronicler.validate import _cohort_candidate_priority

    unexpected_migration = {
        "effect_direction": "community_higher",
        "effect_size": -2.0,
    }
    unexpected_rebellion = {
        "effect_direction": "community_lower",
        "effect_size": 1.0,
    }
    expected_migration = {
        "effect_direction": "community_lower",
        "effect_size": 0.3,
    }
    expected_rebellion = {
        "effect_direction": "equal",
        "effect_size": 0.0,
    }

    assert _cohort_candidate_priority(expected_migration, expected_rebellion, 100) > _cohort_candidate_priority(
        unexpected_migration,
        unexpected_rebellion,
        50,
    )


def test_run_arc_oracle_uses_full_trajectory_signals():
    from chronicler.validate import run_arc_oracle

    trajectory = {
        "population": list(range(50, 80)),
        "treasury": list(range(10, 40)),
        "stability": list(range(50, 80)),
        "territory": [2 + i // 10 for i in range(30)],
        "prestige": list(range(5, 35)),
    }

    result = run_arc_oracle([{"seed": 1, "civ_trajectories": [trajectory]}])

    assert result["per_seed"][0]["arc_types"] == ["rags_to_riches"]


def test_run_regression_summary_counts_alive_by_regions():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{
                "civ_stats": {
                    "Alive Realm": {
                        "regions": ["R1"],
                        "gini": 0.5,
                        "treasury": 10,
                        "alive": False,
                    },
                    "Dead Realm": {
                        "regions": [],
                        "gini": 0.0,
                        "treasury": 0,
                        "alive": True,
                    },
                },
            }],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "civ_0": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 5, "1": 5},
                        "gini": 0.5,
                    }
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["civ_survival_counts"] == [1]
    assert result["gini_in_range_fraction"] == 1.0


def test_run_regression_summary_tracks_initial_named_full_survival():
    from chronicler.validate import run_regression_summary

    initial = {
        name: {"regions": [f"R{i}"], "gini": 0.4, "treasury": 10}
        for i, name in enumerate(["A", "B", "C", "D"])
    }
    successors = {
        name: {"regions": [f"R{i}"], "gini": 0.4, "treasury": 10}
        for i, name in enumerate(["E", "F", "G", "H"])
    }
    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": initial}, {"civ_stats": successors}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "E": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["civ_survival_counts"] == [4]
    assert result["civ_exact_four_region_fraction"] == 1.0
    assert result["civ_full_survival_fraction"] == 0.0


def test_run_regression_summary_prefers_validation_summary_gini():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{
                "civ_stats": {
                    "Alive Realm": {
                        "regions": ["R1"],
                        "gini": 0.0,
                        "treasury": 10,
                    },
                },
            }],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "civ_0": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 5, "1": 5},
                        "gini": 0.5,
                    }
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["gini_in_range_fraction"] == 1.0


def test_run_regression_summary_uses_latest_nonempty_sidecar_gini():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "civ_0": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    }
                },
                "200": {},
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["satisfaction_mean"] == 0.5
    assert result["gini_in_range_fraction"] == 1.0


def test_run_regression_summary_pools_satisfaction_across_all_sidecar_turns():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "early": {
                        "satisfaction_mean": 0.4,
                        "satisfaction_std": 0.1,
                        "agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    }
                },
                "200": {
                    "late": {
                        "satisfaction_mean": 0.6,
                        "satisfaction_std": 0.1,
                        "agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    }
                },
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["satisfaction_mean"] == 0.5
    assert result["satisfaction_std"] == 0.1414


def test_run_regression_summary_pools_satisfaction_std_across_civ_moments():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "civ_0": {
                        "satisfaction_mean": 0.2,
                        "satisfaction_std": 0.05,
                        "agent_count": 1,
                        "occupation_counts": {"0": 1},
                        "gini": 0.4,
                    },
                    "civ_1": {
                        "satisfaction_mean": 0.6,
                        "satisfaction_std": 0.2,
                        "agent_count": 9,
                        "occupation_counts": {"0": 3, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["satisfaction_mean"] == 0.56
    assert result["satisfaction_std"] == 0.2251


def test_run_regression_summary_ignores_tiny_civs_for_occupation_distribution():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "tiny_tail": {
                        "satisfaction_mean": 0.2,
                        "satisfaction_std": 0.05,
                        "agent_count": 1,
                        "occupation_counts": {"0": 1},
                        "gini": 0.4,
                    },
                    "healthy_civ": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["occupation_ok"] is True


def test_run_regression_summary_tolerates_rare_transient_occupation_spikes():
    from chronicler.validate import run_regression_summary

    balanced = {
        f"balanced_{i}": {
            "satisfaction_mean": 0.5,
            "satisfaction_std": 0.15,
            "agent_count": 10,
            "controlled_agent_count": 10,
            "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
            "controlled_occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
            "gini": 0.5,
        }
        for i in range(25)
    }
    balanced["one_transient_spike"] = {
        "satisfaction_mean": 0.5,
        "satisfaction_std": 0.15,
        "agent_count": 10,
        "controlled_agent_count": 10,
        "occupation_counts": {"0": 8, "1": 1, "2": 1},
        "controlled_occupation_counts": {"0": 8, "1": 1, "2": 1},
        "gini": 0.5,
    }
    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {"agent_aggregates_by_turn": {"100": balanced}},
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["occupation_ok"] is True
    assert 0.0 < result["occupation_violation_fraction"] < 0.01


def test_run_regression_summary_ignores_uncontrolled_civ_bucket_for_occupation_distribution():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "uncontrolled_tail": {
                        "satisfaction_mean": 0.4,
                        "satisfaction_std": 0.05,
                        "agent_count": 6,
                        "controlled_agent_count": 0,
                        "occupation_counts": {"0": 5, "3": 1},
                        "controlled_occupation_counts": {},
                        "gini": 0.4,
                    },
                    "healthy_civ": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "controlled_agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "controlled_occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["occupation_ok"] is True
    assert result["occupation_source"] == "controlled"


def test_run_regression_summary_falls_back_to_all_occupations_for_legacy_schema():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "legacy_balanced": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["occupation_ok"] is True
    assert result["occupation_source"] == "legacy_fallback"


def test_run_regression_summary_does_not_treat_zero_controlled_sidecar_as_occupation_balance():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "displaced_but_balanced": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "controlled_agent_count": 0,
                        "occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "controlled_occupation_counts": {},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["occupation_ok"] is False
    assert result["occupation_source"] == "none"


def test_run_regression_summary_uses_controlled_occupations_for_mixed_buckets():
    from chronicler.validate import run_regression_summary

    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{"civ_stats": {}}],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "mixed_bucket": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 30,
                        "controlled_agent_count": 10,
                        "occupation_counts": {"0": 24, "1": 2, "2": 2, "3": 1, "4": 1},
                        "controlled_occupation_counts": {"0": 4, "1": 2, "2": 2, "3": 1, "4": 1},
                        "gini": 0.5,
                    },
                }
            }
        },
        "events": [],
    }

    result = run_regression_summary([run])

    assert result["occupation_ok"] is True
    assert result["occupation_source"] == "controlled"


def test_run_regression_summary_skips_bundle_gini_when_final_sidecar_is_empty():
    from chronicler.validate import run_regression_summary

    run_with_gini = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{
                "civ_stats": {
                    "Alive Realm": {
                        "regions": ["R1"],
                        "gini": 0.0,
                        "treasury": 10,
                    },
                },
            }],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "civ_0": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 10,
                        "occupation_counts": {"0": 5, "1": 5},
                        "gini": 0.5,
                    }
                }
            }
        },
        "events": [],
    }
    run_without_measurable_gini = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [{
                "civ_stats": {
                    "Tail Realm": {
                        "regions": ["R2"],
                        "gini": 0.0,
                        "treasury": 10,
                    },
                },
            }],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {}
            }
        },
        "events": [],
    }

    result = run_regression_summary([run_with_gini, run_without_measurable_gini])

    assert result["gini_in_range_fraction"] == 1.0


def test_run_regression_summary_accepts_calibrated_full_gate_floor_miss():
    from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary

    initial_civs = {
        name: {"regions": [name], "gini": 0.5, "treasury": 10}
        for name in ("A", "B", "C", "D")
    }
    final_civs = {
        name: {"regions": [name], "gini": 0.5, "treasury": 10}
        for name in ("A", "B", "C")
    }
    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [
                {"civ_stats": initial_civs},
                {"civ_stats": final_civs},
            ],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "controlled_civ": {
                        "satisfaction_mean": 0.405,
                        "satisfaction_std": 0.15,
                        "agent_count": 100,
                        "controlled_agent_count": 100,
                        "occupation_counts": {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10},
                        "controlled_occupation_counts": {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10},
                        "gini": 0.5,
                    },
                },
            },
        },
        "events": (
            [{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 450
            + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 250
        ),
    }

    result = run_regression_summary([run])

    assert result["satisfaction_mean"] == 0.405
    assert result["latest_satisfaction_mean"] == 0.405
    assert result["migration_rate_per_agent_turn"] == 0.045
    assert result["satisfaction_mean_ok"] is False
    assert result["satisfaction_mean_calibrated_ok"] is True
    assert result["latest_satisfaction_mean_ok"] is False
    assert result["latest_satisfaction_mean_calibrated_ok"] is True
    assert result["migration_rate_ok"] is False
    assert result["migration_rate_calibrated_ok"] is True
    assert result["strict_regression_failed_checks"] == [
        "satisfaction_mean",
        "latest_satisfaction_mean",
        "migration_rate_per_agent_turn",
    ]
    assert result["calibrated_floor_failed_checks"] == []
    assert result["calibrated_floor_relaxed_checks"] == [
        "satisfaction_mean",
        "latest_satisfaction_mean",
        "migration_rate_per_agent_turn",
    ]
    diagnostics = result["regression_floor_diagnostics"]
    assert diagnostics["satisfaction_mean"]["strict_min_delta"] == -0.045
    assert diagnostics["satisfaction_mean"]["calibrated_min_delta"] == 0.005
    assert diagnostics["latest_satisfaction_mean"]["strict_min_delta"] == -0.045
    assert diagnostics["migration_rate_per_agent_turn"]["strict_min_delta"] == -0.005
    assert diagnostics["migration_rate_per_agent_turn"]["calibrated_min_delta"] == 0.0
    assert result["strict_regression_ok"] is False
    assert result["calibrated_floor_ok"] is True
    assert result["regression_adjudication"] == "calibrated_floor"
    assert result["status"] == "PASS"


def test_run_regression_summary_requires_current_schema_occupation_evidence_coverage():
    from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary

    def make_run(idx: int, with_evidence: bool) -> dict:
        counts = {"0": 2, "1": 1, "2": 1, "3": 1} if with_evidence else {}
        controlled_count = 5 if with_evidence else 0
        return {
            "bundle": {
                "metadata": {"total_turns": 100},
                "history": [
                    {"civ_stats": {"A": {"regions": ["A"], "gini": 0.5, "treasury": 10}}},
                    {"civ_stats": {"B": {"regions": ["B"], "gini": 0.5, "treasury": 10}}},
                ],
            },
            "validation_summary": {
                "agent_aggregates_by_turn": {
                    "100": {
                        f"civ_{idx}": {
                            "satisfaction_mean": 0.5,
                            "satisfaction_std": 0.15,
                            "agent_count": 100,
                            "controlled_agent_count": controlled_count,
                            "occupation_counts": {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10},
                            "controlled_occupation_counts": counts,
                            "gini": 0.5,
                        },
                    },
                },
            },
            "events": (
                [{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 500
                + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 250
            ),
        }

    runs = [make_run(0, True)] + [make_run(idx, False) for idx in range(1, 20)]

    result = run_regression_summary(runs)

    assert result["occupation_source"] == "controlled"
    assert result["occupation_evidence_run_fraction"] == 0.05
    assert result["occupation_ok"] is False
    assert result["status"] == "FAIL"


def test_run_regression_summary_requires_latest_satisfaction_to_clear_floor():
    from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary

    initial_civs = {
        name: {"regions": [name], "gini": 0.5, "treasury": 10}
        for name in ("A", "B", "C", "D")
    }
    final_civs = {
        name: {"regions": [name], "gini": 0.5, "treasury": 10}
        for name in ("A", "B", "C")
    }
    balanced_counts = {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10}
    run = {
        "bundle": {
            "metadata": {"total_turns": 100},
            "history": [
                {"civ_stats": initial_civs},
                {"civ_stats": final_civs},
            ],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "early_good": {
                        "satisfaction_mean": 0.65,
                        "satisfaction_std": 0.15,
                        "agent_count": 100,
                        "controlled_agent_count": 100,
                        "occupation_counts": balanced_counts,
                        "controlled_occupation_counts": balanced_counts,
                        "gini": 0.5,
                    },
                },
                "200": {
                    "latest_bad": {
                        "satisfaction_mean": 0.35,
                        "satisfaction_std": 0.15,
                        "agent_count": 100,
                        "controlled_agent_count": 100,
                        "occupation_counts": balanced_counts,
                        "controlled_occupation_counts": balanced_counts,
                        "gini": 0.5,
                    },
                },
            },
        },
        "events": (
            [{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 500
            + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 250
        ),
    }

    result = run_regression_summary([run])

    assert result["satisfaction_mean"] == 0.5
    assert result["latest_satisfaction_mean"] == 0.35
    assert result["strict_regression_failed_checks"] == ["latest_satisfaction_mean"]
    assert result["calibrated_floor_failed_checks"] == ["latest_satisfaction_mean"]
    assert result["calibrated_floor_relaxed_checks"] == []
    diagnostics = result["regression_floor_diagnostics"]["latest_satisfaction_mean"]
    assert diagnostics["strict_ok"] is False
    assert diagnostics["calibrated_ok"] is False
    assert diagnostics["strict_min_delta"] == -0.1
    assert diagnostics["calibrated_min_delta"] == -0.05
    assert result["strict_regression_ok"] is False
    assert result["calibrated_floor_ok"] is False
    assert result["regression_adjudication"] == "fail"
    assert result["status"] == "FAIL"


def _late_satisfaction_run(samples: dict[int, float], total_turns: int = 500) -> dict:
    from chronicler.validate import EVENT_NAME_TO_CODE

    civs = {name: {"regions": [name], "gini": 0.5, "treasury": 10} for name in ("A", "B", "C", "D")}
    counts = {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10}
    return {
        "bundle": {"metadata": {"total_turns": total_turns},
                   "history": [{"civ_stats": civs}, {"civ_stats": dict(civs, D={"regions": []})}]},
        "validation_summary": {"agent_aggregates_by_turn": {
            str(turn): ({"civ": {"satisfaction_mean": mean, "satisfaction_std": 0.15, "agent_count": 100,
                                 "controlled_agent_count": 100, "occupation_counts": counts,
                                 "controlled_occupation_counts": counts, "gini": 0.5}}
                        if mean is not None else {})
            for turn, mean in samples.items()
        }},
        "events": ([{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 3000
                   + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 1500),
    }


def test_latest_satisfaction_pools_the_late_run_not_its_last_sample():
    """2026-10: the final sample falls on the same season in every world."""
    from chronicler.validate import run_regression_summary

    # Every 10 turns; the last sample is a harvest-time high.
    samples = {turn: 0.58 for turn in range(10, 500, 10)} | {500: 0.70}
    result = run_regression_summary([_late_satisfaction_run(samples)])
    assert result["final_sample_satisfaction_mean"] == 0.70
    assert result["latest_satisfaction_window_turns"] == 60
    # Turns 450-500: five samples at 0.58 and one at 0.70.
    assert result["latest_satisfaction_mean"] == round((5 * 0.58 + 0.70) / 6, 4)
    assert result["latest_satisfaction_mean_ok"] is True


def test_latest_satisfaction_still_catches_a_late_collapse():
    from chronicler.validate import run_regression_summary

    samples = {turn: 0.62 for turn in range(10, 440, 10)} | {turn: 0.30 for turn in range(440, 510, 10)}
    result = run_regression_summary([_late_satisfaction_run(samples)])
    assert result["latest_satisfaction_mean"] == 0.30  # turn 440 is outside (440, 500]
    assert "latest_satisfaction_mean" in result["calibrated_floor_failed_checks"]
    # A world whose agents died: the window ends at the last living sample.
    dying = {turn: 0.60 for turn in range(10, 200, 10)} | {200: 0.31, 210: None, 220: None}
    dead = run_regression_summary([_late_satisfaction_run(dying, total_turns=220)])
    assert dead["final_sample_satisfaction_mean"] == 0.31
    assert dead["latest_satisfaction_mean"] == round((5 * 0.60 + 0.31) / 6, 4)


def test_run_regression_summary_rejects_incomplete_controlled_occupation_counts():
    from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary

    def make_run(idx: int, complete_counts: bool) -> dict:
        controlled_counts = (
            {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10}
            if complete_counts else {"0": 1}
        )
        return {
            "bundle": {
                "metadata": {"total_turns": 100},
                "history": [
                    {"civ_stats": {"A": {"regions": ["A"], "gini": 0.5, "treasury": 10}}},
                    {"civ_stats": {"B": {"regions": ["B"], "gini": 0.5, "treasury": 10}}},
                ],
            },
            "validation_summary": {
                "agent_aggregates_by_turn": {
                    "100": {
                        f"civ_{idx}": {
                            "satisfaction_mean": 0.5,
                            "satisfaction_std": 0.15,
                            "agent_count": 100,
                            "controlled_agent_count": 100,
                            "occupation_counts": {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10},
                            "controlled_occupation_counts": controlled_counts,
                            "gini": 0.5,
                        },
                    },
                },
            },
            "events": (
                [{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 500
                + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 250
            ),
        }

    runs = [make_run(idx, complete_counts=idx < 4) for idx in range(20)]

    result = run_regression_summary(runs)

    assert result["occupation_source"] == "controlled"
    assert result["occupation_evidence_run_fraction"] == 0.2
    assert result["occupation_ok"] is False
    assert result["status"] == "FAIL"


def test_run_regression_summary_rejects_latest_controlled_occupation_collapse():
    from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary

    initial_civs = {
        name: {"regions": [name], "gini": 0.5, "treasury": 10}
        for name in ("A", "B", "C", "D")
    }
    final_civs = {
        name: {"regions": [name], "gini": 0.5, "treasury": 10}
        for name in ("A", "B", "C")
    }
    balanced_counts = {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10}
    early_balanced = {
        f"balanced_{idx}": {
            "satisfaction_mean": 0.5,
            "satisfaction_std": 0.15,
            "agent_count": 100,
            "controlled_agent_count": 100,
            "occupation_counts": balanced_counts,
            "controlled_occupation_counts": balanced_counts,
            "gini": 0.5,
        }
        for idx in range(20)
    }
    run = {
        "bundle": {
            "metadata": {"total_turns": 10},
            "history": [
                {"civ_stats": initial_civs},
                {"civ_stats": final_civs},
            ],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": early_balanced,
                "200": {
                    "collapsed_latest": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 1000,
                        "controlled_agent_count": 1000,
                        "occupation_counts": {"0": 1000},
                        "controlled_occupation_counts": {"0": 1000},
                        "gini": 0.5,
                    },
                },
            },
        },
        "events": (
            [{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 750
            + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 375
        ),
    }

    result = run_regression_summary([run])

    assert result["occupation_violation_fraction"] <= 0.01
    assert result["latest_occupation_violation_fraction"] > 0.70
    assert result["occupation_ok"] is False
    assert result["status"] == "FAIL"


def test_run_regression_summary_rejects_incomplete_latest_controlled_counts():
    from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary

    balanced_counts = {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10}
    run = {
        "bundle": {
            "metadata": {"total_turns": 10},
            "history": [
                {"civ_stats": {"A": {"regions": ["A"], "gini": 0.5, "treasury": 10}}},
                {"civ_stats": {"B": {"regions": ["B"], "gini": 0.5, "treasury": 10}}},
            ],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {
                    "early_complete": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 100,
                        "controlled_agent_count": 100,
                        "occupation_counts": balanced_counts,
                        "controlled_occupation_counts": balanced_counts,
                        "gini": 0.5,
                    },
                },
                "200": {
                    "latest_incomplete": {
                        "satisfaction_mean": 0.5,
                        "satisfaction_std": 0.15,
                        "agent_count": 100,
                        "controlled_agent_count": 100,
                        "occupation_counts": balanced_counts,
                        "controlled_occupation_counts": {"0": 1},
                        "gini": 0.5,
                    },
                },
            },
        },
        "events": (
            [{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 50
            + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 25
        ),
    }

    result = run_regression_summary([run])

    assert result["occupation_evidence_run_fraction"] == 1.0
    assert result["latest_occupation_incomplete_run_fraction"] == 1.0
    assert result["occupation_ok"] is False
    assert result["status"] == "FAIL"


def test_run_oracles_rejects_unknown_names(tmp_path):
    from chronicler.validate import ValidationRequestError, run_oracles

    with pytest.raises(ValidationRequestError, match="unknown_oracles"):
        run_oracles(tmp_path, ["bogus"])


def test_run_oracles_needs_skip_includes_reason_when_sidecars_absent(tmp_path):
    from chronicler.validate import run_oracles

    seed_dir = tmp_path / "seed_42"
    _write_minimal_bundle(seed_dir)

    report = run_oracles(tmp_path, ["needs"])

    assert report["results"]["needs"]["status"] == "SKIP"
    assert report["results"]["needs"]["reason"] == "no_needs_sidecars"


def test_run_oracles_regression_skips_when_agent_events_sidecar_missing(tmp_path):
    from chronicler.validate import run_oracles

    seed_dir = tmp_path / "seed_42"
    _write_minimal_bundle(seed_dir)

    report = run_oracles(tmp_path, ["regression"])

    assert report["results"]["regression"]["status"] == "SKIP"
    assert report["results"]["regression"]["reason"] == "incomplete_agent_event_inputs"


def test_validate_main_rejects_nonfinite_serialized_report(monkeypatch, tmp_path, capsys):
    from chronicler import validate

    monkeypatch.setattr(
        validate,
        "run_oracles",
        lambda batch_dir, oracles: {
            "batch_dir": str(batch_dir),
            "oracles": list(oracles),
            "results": {"needs": {"status": "PASS", "metric": float("nan")}},
        },
    )

    exit_code = validate.main(["--batch-dir", str(tmp_path), "--oracles", "needs"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "could not serialize validation report" in payload["reason"]


def test_validation_io_main_rejects_nonfinite_serialized_report(monkeypatch, tmp_path, capsys):
    from chronicler import validation_io

    monkeypatch.setattr(
        validation_io,
        "run_oracles",
        lambda batch_dir, oracles: {
            "batch_dir": str(batch_dir),
            "oracles": list(oracles),
            "results": {"needs": {"status": "PASS", "metric": float("nan")}},
        },
    )

    exit_code = validation_io.main(["--batch-dir", str(tmp_path), "--oracles", "needs"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "could not serialize validation report" in payload["reason"]


def test_validate_main_rejects_nonstring_keys_that_would_duplicate_in_json(monkeypatch, tmp_path, capsys):
    from chronicler import validate

    monkeypatch.setattr(
        validate,
        "run_oracles",
        lambda batch_dir, oracles: {
            "batch_dir": str(batch_dir),
            "oracles": list(oracles),
            "results": {"needs": {1: "int", "1": "str", "status": "PASS"}},
        },
    )

    exit_code = validate.main(["--batch-dir", str(tmp_path), "--oracles", "needs"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "could not serialize validation report" in payload["reason"]
    assert "JSON object keys must be strings" in payload["reason"]


def test_validation_io_main_rejects_nonstring_keys_that_would_duplicate_in_json(monkeypatch, tmp_path, capsys):
    from chronicler import validation_io

    monkeypatch.setattr(
        validation_io,
        "run_oracles",
        lambda batch_dir, oracles: {
            "batch_dir": str(batch_dir),
            "oracles": list(oracles),
            "results": {"needs": {None: "none", "null": "str", "status": "PASS"}},
        },
    )

    exit_code = validation_io.main(["--batch-dir", str(tmp_path), "--oracles", "needs"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "could not serialize validation report" in payload["reason"]
    assert "JSON object keys must be strings" in payload["reason"]


def test_validate_main_returns_nonzero_for_unknown_oracle(tmp_path, capsys):
    from chronicler.validate import main

    exit_code = main(["--batch-dir", str(tmp_path), "--oracles", "bogus"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "unknown_oracles" in payload["reason"]


def test_validate_main_returns_nonzero_for_missing_batch_path(tmp_path, capsys):
    from chronicler.validate import main

    missing = tmp_path / "missing_batch"
    exit_code = main(["--batch-dir", str(missing), "--oracles", "needs"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "batch path does not exist" in payload["reason"]


def test_validate_main_returns_nonzero_when_pyarrow_missing_for_required_arrow_input(
    tmp_path,
    monkeypatch,
    capsys,
):
    from chronicler import validate

    seed_dir = tmp_path / "seed_42"
    _write_minimal_bundle(seed_dir)
    (seed_dir / "agent_events.arrow").write_bytes(b"not-a-real-arrow-file")

    monkeypatch.setattr("chronicler.validation_io._has_pyarrow", lambda: False)

    exit_code = validate.main(["--batch-dir", str(tmp_path), "--oracles", "regression"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert "regression oracle requires pyarrow" in payload["reason"]


@pytest.mark.parametrize(
    ("oracle_name", "expected_reason"),
    [
        ("needs", "no_needs_sidecars"),
        ("cohort", "no_community_seed_pairs"),
    ],
)
def test_validate_main_skips_when_pyarrow_missing_but_oracle_has_no_other_inputs(
    tmp_path,
    monkeypatch,
    capsys,
    oracle_name,
    expected_reason,
):
    from chronicler import validate

    seed_dir = tmp_path / "seed_42"
    _write_minimal_bundle(seed_dir)
    (seed_dir / "agent_events.arrow").write_bytes(b"not-a-real-arrow-file")

    monkeypatch.setattr("chronicler.validation_io._has_pyarrow", lambda: False)
    monkeypatch.setattr("chronicler.validation_io._load_agent_events", lambda _seed_dir: [])

    exit_code = validate.main(["--batch-dir", str(tmp_path), "--oracles", oracle_name])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["results"][oracle_name]["status"] == "SKIP"
    assert payload["results"][oracle_name]["reason"] == expected_reason


@pytest.mark.parametrize(
    ("oracle_name", "required_files", "expected_phrase"),
    [
        ("needs", ["validation_needs.arrow", "agent_events.arrow"], "needs oracle requires pyarrow"),
        (
            "cohort",
            ["validation_relationships.arrow", "validation_needs.arrow", "agent_events.arrow"],
            "cohort oracle requires pyarrow",
        ),
    ],
)
def test_validate_main_returns_nonzero_when_pyarrow_missing_for_required_oracle_inputs(
    tmp_path,
    monkeypatch,
    capsys,
    oracle_name,
    required_files,
    expected_phrase,
):
    from chronicler import validate

    seed_dir = tmp_path / "seed_42"
    _write_minimal_bundle(seed_dir)
    for filename in required_files:
        (seed_dir / filename).write_bytes(b"not-a-real-arrow-file")

    monkeypatch.setattr("chronicler.validation_io._has_pyarrow", lambda: False)

    exit_code = validate.main(["--batch-dir", str(tmp_path), "--oracles", oracle_name])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["status"] == "ERROR"
    assert expected_phrase in payload["reason"]
