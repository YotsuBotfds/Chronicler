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
