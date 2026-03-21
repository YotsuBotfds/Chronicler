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
