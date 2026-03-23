import json


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


def test_run_needs_oracle_uses_all_sampled_turns():
    from chronicler.validate import run_needs_oracle

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


def test_run_cohort_oracle_uses_all_sampled_turns():
    from chronicler.validate import run_cohort_oracle

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
    ]

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
        "population": [100] * 30,
        "treasury": list(range(10, 40)),
        "stability": list(range(50, 80)),
        "territory": [2] * 30,
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


def test_run_regression_summary_weights_satisfaction_by_agent_count():
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
    assert result["satisfaction_std"] == 0.185


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
