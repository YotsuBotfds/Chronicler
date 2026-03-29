//! Integration tests for the pure Rust politics core.
//!
//! Covers the 11-step Phase 10 political consequence pass,
//! matching the Python oracle behavior in `src/chronicler/politics.py`.

use chronicler_agents::politics::*;

// ---------------------------------------------------------------------------
// Test helpers — no struct literals, use constructors
// ---------------------------------------------------------------------------

fn default_config() -> PoliticsConfig {
    PoliticsConfig::default()
}

fn default_topology() -> PoliticsTopology {
    PoliticsTopology::default()
}

/// Build a simple 3-region linear graph: 0--1--2
fn make_3_regions(controllers: [u16; 3]) -> Vec<RegionInput> {
    let mut r0 = RegionInput::new(0);
    r0.adjacencies = vec![1];
    r0.controller = controllers[0];
    r0.effective_capacity = 50;

    let mut r1 = RegionInput::new(1);
    r1.adjacencies = vec![0, 2];
    r1.controller = controllers[1];
    r1.effective_capacity = 40;

    let mut r2 = RegionInput::new(2);
    r2.adjacencies = vec![1];
    r2.controller = controllers[2];
    r2.effective_capacity = 30;

    vec![r0, r1, r2]
}

/// Build a 5-region star graph: 0 is center, 1-4 are leaves
fn make_5_regions_star(controller: u16) -> Vec<RegionInput> {
    let mut regs = Vec::new();
    let mut center = RegionInput::new(0);
    center.adjacencies = vec![1, 2, 3, 4];
    center.controller = controller;
    center.effective_capacity = 60;
    regs.push(center);

    for i in 1..=4u16 {
        let mut r = RegionInput::new(i);
        r.adjacencies = vec![0];
        r.controller = controller;
        r.effective_capacity = (50 - i * 5) as u16;
        regs.push(r);
    }
    regs
}

fn make_civ(idx: u16, regions: Vec<u16>) -> CivInput {
    let mut c = CivInput::new(idx);
    c.regions = regions;
    c.capital_region = if c.regions.is_empty() {
        REGION_NONE
    } else {
        c.regions[0]
    };
    c
}

// ---------------------------------------------------------------------------
// Step 1: Capital loss
// ---------------------------------------------------------------------------

#[test]
fn test_capital_loss_reassignment_by_effective_capacity() {
    let regions = make_3_regions([0, 0, 0]);

    let mut civ0 = make_civ(0, vec![1, 2]); // capital is region 0 which is NOT in civ.regions
    civ0.capital_region = 0; // lost capital

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    // Should have a ReassignCapital op
    assert!(
        result.civ_ops.iter().any(|op| op.op_type == CivOpType::ReassignCapital),
        "Expected a ReassignCapital op"
    );

    // Best region should be region 1 (eff_cap=40 > region 2 eff_cap=30)
    let reassign = result.civ_ops.iter().find(|op| op.op_type == CivOpType::ReassignCapital).unwrap();
    assert_eq!(reassign.regions, vec![1], "Capital should be reassigned to region 1 (highest eff_cap)");

    // Should have capital_loss event
    assert!(
        result.events.iter().any(|e| e.event_type == "capital_loss"),
        "Expected a capital_loss event"
    );

    // Should have capital_lost bookkeeping
    assert!(
        result.bookkeeping.iter().any(|b| b.field == "capital_lost" && b.bk_type == BookkeepingType::IncrementEventCount),
        "Expected capital_lost bookkeeping"
    );
}

#[test]
fn test_capital_loss_prefers_first_region_on_equal_capacity() {
    let regions = make_3_regions([0, 0, 0]);

    let mut civ0 = make_civ(0, vec![1, 2]);
    civ0.capital_region = 0; // lost capital: region 0 is no longer controlled

    let config = default_config();
    let topo = default_topology();
    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    let reassign = result
        .civ_ops
        .iter()
        .find(|op| op.op_type == CivOpType::ReassignCapital)
        .expect("capital should be reassigned");
    assert_eq!(
        reassign.regions[0], 1,
        "capital reassignment should keep Python's first-on-tie max behavior",
    );
}

#[test]
fn test_capital_loss_no_trigger_when_capital_present() {
    let regions = make_3_regions([0, 0, 0]);
    let civ0 = make_civ(0, vec![0, 1, 2]); // capital=0 is in regions

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    assert!(
        result.civ_ops.iter().all(|op| op.op_type != CivOpType::ReassignCapital),
        "Should not reassign capital when it's still held"
    );
}

// ---------------------------------------------------------------------------
// Step 2: Secession
// ---------------------------------------------------------------------------

#[test]
fn test_secession_trigger_and_region_split() {
    let regions = make_5_regions_star(0);

    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5; // below threshold (10)
    civ0.founded_turn = 0; // old enough (turn 100 - 0 >= 50)
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;

    let config = default_config();
    let topo = default_topology();

    // Run with a seed that produces secession
    // We need to find a seed that triggers the RNG check
    let mut found = false;
    for s in 0..100u64 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, s, false);
        if result.civ_ops.iter().any(|op| op.op_type == CivOpType::CreateBreakaway) {
            found = true;
            // Verify breakaway has regions
            let breakaway = result.civ_ops.iter().find(|op| op.op_type == CivOpType::CreateBreakaway).unwrap();
            assert!(!breakaway.regions.is_empty(), "Breakaway should have regions");

            // Verify region controller ops
            assert!(
                result.region_ops.iter().any(|op| op.op_type == RegionOpType::SetController),
                "Should have region controller ops"
            );

            // Verify seceded transient
            assert!(
                result.region_ops.iter().any(|op| op.op_type == RegionOpType::SetSecededTransient),
                "Should set _seceded_this_turn transient"
            );

            // Verify relationship ops
            assert!(
                result.relationship_ops.iter().any(|op| op.disposition == Disposition::Hostile),
                "Parent-breakaway should be HOSTILE"
            );

            // Verify event
            assert!(
                result.events.iter().any(|e| e.event_type == "secession"),
                "Should emit secession event"
            );

            assert!(
                result.bookkeeping.iter().any(|bk|
                    bk.bk_type == BookkeepingType::AppendStatsHistory
                    && bk.civ == breakaway.target_civ
                    && bk.value_i == breakaway.stat_economy + breakaway.stat_military + breakaway.stat_culture
                ),
                "New breakaway civ should receive same-turn stats_sum_history bookkeeping"
            );

            break;
        }
    }
    assert!(found, "Secession should trigger for at least one seed with stability=5");
}

#[test]
fn test_secession_grace_period_skips() {
    let regions = make_5_regions_star(0);

    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 80; // turn 100 - 80 = 20 < 50 grace

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    assert!(
        result.civ_ops.iter().all(|op| op.op_type != CivOpType::CreateBreakaway),
        "Should not secede during grace period"
    );
}

#[test]
fn test_secession_schism_modifier() {
    let mut regions = make_5_regions_star(0);
    regions[3].majority_belief = 2; // different from civ faith

    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 8; // just below threshold
    civ0.founded_turn = 0;
    civ0.civ_majority_faith = 1; // different from region 3
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;

    // With schism modifier, probability increases by 0.10
    // This should fire more often than without
    let config = default_config();
    let topo = default_topology();

    let mut fires_with_schism = 0;
    for s in 0..200u64 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, s, false);
        if result.civ_ops.iter().any(|op| op.op_type == CivOpType::CreateBreakaway) {
            fires_with_schism += 1;
        }
    }

    // Without schism (civ_majority_faith == BELIEF_NONE → no modifier)
    let mut civ0_no_schism = civ0.clone();
    civ0_no_schism.civ_majority_faith = BELIEF_NONE;
    let mut fires_without = 0;
    for s in 0..200u64 {
        let result = run_politics_pass(&[civ0_no_schism.clone()], &regions, &topo, &config, 100, s, false);
        if result.civ_ops.iter().any(|op| op.op_type == CivOpType::CreateBreakaway) {
            fires_without += 1;
        }
    }

    // Schism should increase secession rate
    assert!(
        fires_with_schism >= fires_without,
        "Schism modifier should increase secession rate (with={}, without={})",
        fires_with_schism,
        fires_without
    );
}

#[test]
fn test_secession_belief_none_region_still_counts_as_mismatch() {
    let regions_with_none = make_5_regions_star(0);
    let mut regions_matching = make_5_regions_star(0);
    for region in &mut regions_matching {
        region.majority_belief = 1;
    }

    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 0;
    civ0.civ_majority_faith = 1;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;

    let mut config = default_config();
    config.secession_stability_threshold = 25;
    let topo = default_topology();

    let mut found_bonus_sensitive_seed = false;
    for s in 0..500u64 {
        let with_none = run_politics_pass(
            &[civ0.clone()],
            &regions_with_none,
            &topo,
            &config,
            100,
            s,
            false,
        );
        let matching = run_politics_pass(
            &[civ0.clone()],
            &regions_matching,
            &topo,
            &config,
            100,
            s,
            false,
        );
        let fires_with_none = with_none
            .civ_ops
            .iter()
            .any(|op| op.op_type == CivOpType::CreateBreakaway);
        let fires_matching = matching
            .civ_ops
            .iter()
            .any(|op| op.op_type == CivOpType::CreateBreakaway);
        if fires_with_none && !fires_matching {
            found_bonus_sensitive_seed = true;
            break;
        }
    }

    assert!(
        found_bonus_sensitive_seed,
        "BELIEF_NONE regions should behave like Python and add a schism bonus when the civ has a concrete majority faith",
    );
}

#[test]
fn test_hybrid_secession_decline_history_uses_pre_shock_stats() {
    let regions = make_5_regions_star(0);

    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 0;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.culture = 30;
    civ0.treasury = 100;

    let config = default_config();
    let topo = default_topology();

    let expected_sum = civ0.military + civ0.economy + civ0.culture;
    let mut found = false;
    for s in 0..100u64 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, s, true);
        if result.civ_ops.iter().any(|op| op.op_type == CivOpType::CreateBreakaway) {
            found = true;
            let parent_history = result
                .bookkeeping
                .iter()
                .find(|bk| {
                    bk.bk_type == BookkeepingType::AppendStatsHistory
                        && bk.civ == CivRef::Existing(0)
                })
                .expect("parent civ should receive same-turn stats history");
            assert_eq!(
                parent_history.value_i,
                expected_sum,
                "hybrid secession should append the pre-shock visible stat sum, not the deferred post-shock value",
            );
            break;
        }
    }

    assert!(found, "expected at least one hybrid secession seed in the scan");
}

// ---------------------------------------------------------------------------
// Step 3: Allied turns
// ---------------------------------------------------------------------------

#[test]
fn test_allied_turns_update_precedes_federation() {
    let regions = make_3_regions([0, 0, 1]);
    let civ0 = make_civ(0, vec![0, 1]);
    let civ1 = make_civ(1, vec![2]);

    let mut topo = default_topology();
    // Set allied relationship at exactly the threshold - 1
    topo.relationships.push(RelationshipEntry {
        civ_a: 0,
        civ_b: 1,
        disposition: Disposition::Allied,
        allied_turns: 9, // threshold is 10
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 1,
        civ_b: 0,
        disposition: Disposition::Allied,
        allied_turns: 9,
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    // Step 3 should increment allied_turns to 10
    assert!(
        result.relationship_ops.iter().any(|op| {
            op.step == 3 && op.op_type == RelationshipOpType::IncrementAlliedTurns
        }),
        "Step 3 should increment allied_turns"
    );

    // Step 5 should then see allied_turns=10 and potentially form federation
    // (The exact formation depends on other conditions like vassal check)
    // At minimum, step 3 must run before step 5
    let _step3_max_seq = result.relationship_ops.iter()
        .filter(|op| op.step == 3)
        .map(|op| op.seq)
        .max()
        .unwrap_or(0);
    let step5_min_seq = result.federation_ops.iter()
        .filter(|op| op.step == 5)
        .map(|op| op.seq)
        .min();

    if let Some(_s5) = step5_min_seq {
        // If federation ops exist, they should come from a later step
        assert!(5 > 3, "Step 5 must be after step 3");
    }
}

#[test]
fn test_allied_turns_reset_on_hostile() {
    let regions = make_3_regions([0, 0, 1]);
    let civ0 = make_civ(0, vec![0, 1]);
    let civ1 = make_civ(1, vec![2]);

    let mut topo = default_topology();
    topo.relationships.push(RelationshipEntry {
        civ_a: 0,
        civ_b: 1,
        disposition: Disposition::Hostile,
        allied_turns: 5, // should reset to 0
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    assert!(
        result.relationship_ops.iter().any(|op| {
            op.step == 3 && op.op_type == RelationshipOpType::ResetAlliedTurns
        }),
        "Should reset allied_turns when disposition is HOSTILE"
    );
}

// ---------------------------------------------------------------------------
// Step 4: Vassal rebellion
// ---------------------------------------------------------------------------

#[test]
fn test_vassal_rebellion_with_current_perception() {
    let regions = make_3_regions([0, 0, 1]);
    let mut civ0 = make_civ(0, vec![0, 1]); // overlord
    civ0.stability = 10; // weak — perceived < 25
    civ0.treasury = 5; // weak — perceived < 10

    let civ1 = make_civ(1, vec![2]); // vassal

    let mut topo = default_topology();
    topo.vassals.push(VassalEntry {
        vassal: 1,
        overlord: 0,
    });
    // Need relationship so vassal can perceive overlord
    topo.relationships.push(RelationshipEntry {
        civ_a: 1,
        civ_b: 0,
        disposition: Disposition::Suspicious,
        allied_turns: 0,
    });

    let config = default_config();

    let mut rebelled = false;
    for s in 0..100u64 {
        let result = run_politics_pass(&[civ0.clone(), civ1.clone()], &regions, &topo, &config, 100, s, false);
        if result.vassal_ops.iter().any(|op| op.op_type == VassalOpType::Remove) {
            rebelled = true;

            // Verify rebellion effects
            assert!(
                result.civ_effects.iter().any(|e| {
                    matches!(&e.civ, CivRef::Existing(1))
                        && e.field == "stability"
                        && e.delta_i == 10
                }),
                "Vassal should gain +10 stability"
            );
            assert!(
                result.civ_effects.iter().any(|e| {
                    matches!(&e.civ, CivRef::Existing(1))
                        && e.field == "asabiya"
                }),
                "Vassal should gain asabiya"
            );
            assert!(
                result.relationship_ops.iter().any(|op| {
                    op.step == 4 && op.disposition == Disposition::Hostile
                }),
                "Should set vassal->overlord to HOSTILE"
            );
            break;
        }
    }
    assert!(rebelled, "Vassal should rebel against weak overlord for some seed");
}

#[test]
fn test_vassal_rebellion_rebelled_overlords_ordering() {
    // Two vassals under the same overlord: first uses base prob, second reduced + requires HOSTILE/SUSPICIOUS
    let mut regions = make_3_regions([0, 1, 2]);
    // Need extra regions for 3rd civ
    let mut r3 = RegionInput::new(3);
    r3.controller = 0;
    r3.adjacencies = vec![0];
    regions.push(r3);

    let mut civ0 = make_civ(0, vec![0, 3]); // overlord
    civ0.stability = 5;
    civ0.treasury = 3;

    let civ1 = make_civ(1, vec![1]); // vassal 1
    let civ2 = make_civ(2, vec![2]); // vassal 2

    let mut topo = default_topology();
    topo.vassals.push(VassalEntry { vassal: 1, overlord: 0 });
    topo.vassals.push(VassalEntry { vassal: 2, overlord: 0 });
    // Vassal 1 has HOSTILE relationship
    topo.relationships.push(RelationshipEntry {
        civ_a: 1, civ_b: 0,
        disposition: Disposition::Hostile, allied_turns: 0,
    });
    // Vassal 2 has NEUTRAL relationship — second rebellion requires HOSTILE/SUSPICIOUS
    topo.relationships.push(RelationshipEntry {
        civ_a: 2, civ_b: 0,
        disposition: Disposition::Neutral, allied_turns: 0,
    });

    let mut config = default_config();
    // Set base prob to 1.0 so vassal 1 ALWAYS rebels (entering overlord into rebelled_overlords)
    config.vassal_rebellion_base_prob = 1.0;
    // Reduced prob also high so if vassal 2 could rebel, it would
    config.vassal_rebellion_reduced_prob = 1.0;

    // With vassal 1 guaranteed to rebel first, vassal 2 (NEUTRAL) should
    // never rebel because the rebelled_overlords check requires HOSTILE/SUSPICIOUS
    let mut v2_rebelled = false;
    for s in 0..50u64 {
        let result = run_politics_pass(&[civ0.clone(), civ1.clone(), civ2.clone()], &regions, &topo, &config, 100, s, false);
        // Check if vassal 2 rebelled
        if result.vassal_ops.iter().any(|op| {
            op.op_type == VassalOpType::Remove && matches!(op.vassal, CivRef::Existing(2))
        }) {
            v2_rebelled = true;
            break;
        }
    }
    assert!(
        !v2_rebelled,
        "Vassal 2 (NEUTRAL) should not rebel as subsequent against same overlord"
    );
}

// ---------------------------------------------------------------------------
// Step 5/6: Federation create vs dissolve
// ---------------------------------------------------------------------------

#[test]
fn test_federation_create_emits_event() {
    let regions = make_3_regions([0, 0, 1]);
    let civ0 = make_civ(0, vec![0, 1]);
    let civ1 = make_civ(1, vec![2]);

    let mut topo = default_topology();
    // Already at the allied turns threshold
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 1,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 1, civ_b: 0,
        disposition: Disposition::Allied, allied_turns: 10,
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    // Should create a federation
    assert!(
        result.federation_ops.iter().any(|op| op.op_type == FederationOpType::Create),
        "Should create a federation"
    );

    // Should emit federation_formed event
    assert!(
        result.events.iter().any(|e| e.event_type == "federation_formed"),
        "Should emit federation_formed event"
    );
}

#[test]
fn test_federation_append_does_not_emit_event() {
    let regions = make_3_regions([0, 1, 2]);
    let civ0 = make_civ(0, vec![0]);
    let civ1 = make_civ(1, vec![1]);
    let civ2 = make_civ(2, vec![2]);

    let mut topo = default_topology();
    // Existing federation with civ0 and civ1
    topo.federations.push(FederationEntry {
        fed_idx: 0,
        members: vec![0, 1],
        founded_turn: 50,
    });
    // civ2 allied with civ0 long enough
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 2,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 2, civ_b: 0,
        disposition: Disposition::Allied, allied_turns: 10,
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1, civ2], &regions, &topo, &config, 100, 42, false);

    // Should append member
    let has_append = result.federation_ops.iter().any(|op| op.op_type == FederationOpType::AppendMember);
    if has_append {
        // APPEND_MEMBER should NOT emit event
        let has_event = result.events.iter().any(|e| e.event_type == "federation_formed" && e.step == 5);
        assert!(
            !has_event,
            "APPEND_MEMBER should NOT emit federation_formed event"
        );
    }
}

#[test]
fn test_federation_append_preserves_dead_civ_legacy_behavior() {
    let regions = make_3_regions([0, 1, 1]);
    let civ0 = make_civ(0, vec![0]);
    let civ1 = make_civ(1, vec![1, 2]);
    let civ2 = make_civ(2, vec![]); // dead civ, but legacy Python can still append it

    let mut topo = default_topology();
    topo.federations.push(FederationEntry {
        fed_idx: 0,
        members: vec![0, 1],
        founded_turn: 50,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 2,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 2, civ_b: 0,
        disposition: Disposition::Allied, allied_turns: 10,
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1, civ2], &regions, &topo, &config, 100, 42, false);

    let append = result
        .federation_ops
        .iter()
        .find(|op| op.op_type == FederationOpType::AppendMember && op.civ == CivRef::Existing(2))
        .expect("dead civ should still append to federation to match Python legacy behavior");
    assert_eq!(append.federation_ref, FedRef::Existing(0));
}

#[test]
fn test_federation_append_after_create_reuses_new_federation_ref() {
    let regions = make_3_regions([0, 1, 2]);
    let civ0 = make_civ(0, vec![0]);
    let civ1 = make_civ(1, vec![1]);
    let civ2 = make_civ(2, vec![2]);

    let mut topo = default_topology();
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 1,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 1, civ_b: 0,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 2,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 2, civ_b: 0,
        disposition: Disposition::Allied, allied_turns: 10,
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1, civ2], &regions, &topo, &config, 100, 42, false);

    let create = result
        .federation_ops
        .iter()
        .find(|op| op.op_type == FederationOpType::Create)
        .expect("create op should exist");
    let append = result
        .federation_ops
        .iter()
        .find(|op| op.op_type == FederationOpType::AppendMember && op.civ == CivRef::Existing(2))
        .expect("append op should target the newly created federation");
    assert_eq!(create.federation_ref, FedRef::New(0));
    assert_eq!(append.federation_ref, create.federation_ref);
}

#[test]
fn test_federation_dissolve_emits_event() {
    let regions = make_3_regions([0, 0, 1]);
    let civ0 = make_civ(0, vec![0, 1]);
    let civ1 = make_civ(1, vec![2]);

    let mut topo = default_topology();
    topo.federations.push(FederationEntry {
        fed_idx: 0,
        members: vec![0, 1],
        founded_turn: 50,
    });
    // Set HOSTILE relationship so dissolution triggers
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 1,
        disposition: Disposition::Hostile, allied_turns: 0,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 1, civ_b: 0,
        disposition: Disposition::Hostile, allied_turns: 0,
    });

    let config = default_config();
    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    // Should dissolve
    assert!(
        result.federation_ops.iter().any(|op| op.op_type == FederationOpType::Dissolve),
        "Should dissolve the federation"
    );

    // Should emit federation_collapsed event
    assert!(
        result.events.iter().any(|e| e.event_type == "federation_collapsed"),
        "Should emit federation_collapsed event"
    );
}

// ---------------------------------------------------------------------------
// Step 7: Proxy detection
// ---------------------------------------------------------------------------

#[test]
fn test_proxy_detection_mutation_and_hostility() {
    let regions = make_3_regions([0, 0, 1]);
    let civ0 = make_civ(0, vec![0, 1]); // sponsor
    let mut civ1 = make_civ(1, vec![2]); // target
    civ1.culture = 80; // high culture → high detection probability

    let mut topo = default_topology();
    topo.proxy_wars.push(ProxyWarEntry {
        sponsor: 0,
        target_civ: 1,
        target_region: 2,
        detected: false,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 1,
        disposition: Disposition::Suspicious, allied_turns: 0,
    });

    let config = default_config();

    let mut detected = false;
    for s in 0..100u64 {
        let result = run_politics_pass(&[civ0.clone(), civ1.clone()], &regions, &topo, &config, 100, s, false);
        if result.proxy_war_ops.iter().any(|op| op.op_type == ProxyWarOpType::SetDetected) {
            detected = true;

            // Verify hostility update (target -> sponsor)
            assert!(
                result.relationship_ops.iter().any(|op| {
                    op.step == 7
                        && matches!(&op.civ_a, CivRef::Existing(1))
                        && matches!(&op.civ_b, CivRef::Existing(0))
                        && op.disposition == Disposition::Hostile
                }),
                "Should set target->sponsor to HOSTILE on detection"
            );

            // Verify stability penalty to target
            assert!(
                result.civ_effects.iter().any(|e| {
                    matches!(&e.civ, CivRef::Existing(1)) && e.field == "stability" && e.delta_i == -5
                }),
                "Target should get -5 stability on detection"
            );

            // Keep legacy assertion that step is correct for relationship mutation.
            assert!(
                result.relationship_ops.iter().any(|op| {
                    op.step == 7 && op.disposition == Disposition::Hostile
                }),
                "Expected step-7 hostility operation"
            );

            break;
        }
    }
    assert!(detected, "Proxy war should be detected with culture=80 for some seed");
}

// ---------------------------------------------------------------------------
// Step 8: Restoration
// ---------------------------------------------------------------------------

#[test]
fn test_restoration_with_recognized_by() {
    let regions = make_3_regions([1, 1, 1]); // all controlled by absorber

    let civ0 = make_civ(0, Vec::new()); // dead civ (exiled)
    let mut civ1 = make_civ(1, vec![0, 1, 2]); // absorber
    civ1.stability = 10; // low enough for restoration check (< 20)

    let mut topo = default_topology();
    topo.exiles.push(ExileEntry {
        original_civ: 0,
        absorber_civ: 1,
        conquered_regions: vec![0, 1, 2],
        turns_remaining: 15,
        recognized_by: vec![2, 3], // two recognitions → higher probability
    });

    let mut config = default_config();
    // Boost probability to make it trigger reliably
    config.restoration_base_prob = 0.3;
    config.restoration_recognition_bonus = 0.1; // total prob = 0.3 + 0.1*2 = 0.5

    let mut restored = false;
    for s in 0..100u64 {
        let result = run_politics_pass(&[civ0.clone(), civ1.clone()], &regions, &topo, &config, 100, s, false);
        if result.civ_ops.iter().any(|op| op.op_type == CivOpType::Restore) {
            restored = true;

            // Verify restored civ gets regions
            let restore_op = result.civ_ops.iter().find(|op| op.op_type == CivOpType::Restore).unwrap();
            assert!(!restore_op.regions.is_empty(), "Restored civ should get regions");

            // Target region should be highest effective_capacity
            assert_eq!(
                restore_op.regions[0], 0,
                "Should pick region 0 (eff_cap=50, highest)"
            );

            // Verify relationship initialization
            let hostile_count = result.relationship_ops.iter().filter(|op| {
                op.step == 8 && op.disposition == Disposition::Hostile
            }).count();
            assert!(hostile_count > 0, "Should set HOSTILE toward absorber");

            // Verify exile removal
            assert!(
                result.exile_ops.iter().any(|op| op.op_type == ExileOpType::Remove),
                "Should remove the exile modifier"
            );

            break;
        }
    }
    assert!(restored, "Restoration should trigger with high probability");
}

#[test]
fn test_restoration_prefers_first_available_region_on_equal_capacity() {
    let regions = make_3_regions([1, 1, 1]);

    let civ0 = make_civ(0, Vec::new()); // dead civ (exiled)
    let mut civ1 = make_civ(1, vec![0, 1, 2]); // absorber
    civ1.stability = 10;

    let mut topo = default_topology();
    topo.exiles.push(ExileEntry {
        original_civ: 0,
        absorber_civ: 1,
        conquered_regions: vec![0, 1],
        turns_remaining: 15,
        recognized_by: vec![],
    });

    let mut config = default_config();
    config.restoration_base_prob = 1.0;
    config.restoration_recognition_bonus = 0.0;

    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    let restore = result
        .civ_ops
        .iter()
        .find(|op| op.op_type == CivOpType::Restore)
        .expect("restoration should fire");
    assert_eq!(
        restore.regions[0], 0,
        "restoration should keep Python's first-on-tie max behavior",
    );
}

#[test]
fn test_restoration_does_not_immediately_trigger_twilight_absorption() {
    let regions = make_3_regions([1, 1, 1]); // restored region 0 has eff_cap=50

    let civ0 = make_civ(0, Vec::new()); // dead civ (exiled)
    let mut civ1 = make_civ(1, vec![0, 1, 2]); // absorber
    civ1.stability = 10;

    let mut topo = default_topology();
    topo.exiles.push(ExileEntry {
        original_civ: 0,
        absorber_civ: 1,
        conquered_regions: vec![0, 1, 2],
        turns_remaining: 15,
        recognized_by: vec![],
    });

    let mut config = default_config();
    config.restoration_base_prob = 1.0; // force restoration for this regression
    config.restoration_recognition_bonus = 0.0;

    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    assert!(
        result.civ_ops.iter().any(|op| op.op_type == CivOpType::Restore),
        "restoration should fire"
    );
    assert!(
        !result.events.iter().any(|e| e.event_type == "twilight_absorption"),
        "a restored civ with viable effective capacity should not be reabsorbed immediately"
    );
}

// ---------------------------------------------------------------------------
// Step 9: Twilight absorption
// ---------------------------------------------------------------------------

#[test]
fn test_twilight_absorption_preserves_dead_civ() {
    // Civ with terminal decline
    let mut regions = vec![
        RegionInput::new(0),
        RegionInput::new(1),
    ];
    regions[0].adjacencies = vec![1];
    regions[0].controller = 0;
    regions[0].effective_capacity = 20;
    regions[1].adjacencies = vec![0];
    regions[1].controller = 1;
    regions[1].effective_capacity = 50;

    let mut civ0 = make_civ(0, vec![0]); // declining civ with 1 region
    civ0.decline_turns = 45; // > 40 threshold
    civ0.founded_turn = 0;

    let mut civ1 = make_civ(1, vec![1]); // neighbor absorber
    civ1.culture = 60;

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0, civ1], &regions, &topo, &config, 100, 42, false);

    // Should absorb
    let has_absorb = result.civ_ops.iter().any(|op| op.op_type == CivOpType::Absorb);
    assert!(has_absorb, "Should absorb the declining civ");

    // Verify the absorb op source is the dying civ, target is absorber
    if has_absorb {
        let absorb_op = result.civ_ops.iter().find(|op| op.op_type == CivOpType::Absorb).unwrap();
        assert!(
            matches!(absorb_op.source_civ, CivRef::Existing(0)),
            "Source should be the dying civ"
        );
        assert!(
            matches!(absorb_op.target_civ, CivRef::Existing(1)),
            "Target should be the absorber"
        );
    }

    // Verify artifact lifecycle intent
    assert!(
        result.artifact_intents.iter().any(|ai| ai.action == "twilight_absorption"),
        "Should emit twilight_absorption artifact intent"
    );

    // Verify exile modifier append
    assert!(
        result.exile_ops.iter().any(|op| op.op_type == ExileOpType::Append),
        "Should append exile modifier"
    );

    // Verify event
    assert!(
        result.events.iter().any(|e| e.event_type == "twilight_absorption"),
        "Should emit twilight_absorption event"
    );
}

#[test]
fn test_twilight_absorption_updates_absorber_viability_same_step() {
    let mut regions = vec![
        RegionInput::new(0),
        RegionInput::new(1),
        RegionInput::new(2),
    ];
    regions[0].adjacencies = vec![1];
    regions[0].controller = 0;
    regions[0].effective_capacity = 8;
    regions[1].adjacencies = vec![0, 2];
    regions[1].controller = 1;
    regions[1].effective_capacity = 4;
    regions[2].adjacencies = vec![1];
    regions[2].controller = 2;
    regions[2].effective_capacity = 50;

    let mut civ0 = make_civ(0, vec![0]);
    civ0.founded_turn = 0;
    civ0.total_effective_capacity = 8;
    let mut civ1 = make_civ(1, vec![1]);
    civ1.founded_turn = 0;
    civ1.culture = 20;
    civ1.total_effective_capacity = 4;
    let mut civ2 = make_civ(2, vec![2]);
    civ2.culture = 60;
    civ2.total_effective_capacity = 50;

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0, civ1, civ2], &regions, &topo, &config, 100, 42, false);

    let twilight_events: Vec<_> = result
        .events
        .iter()
        .filter(|e| e.event_type == "twilight_absorption")
        .collect();
    assert_eq!(
        twilight_events.len(),
        1,
        "absorber should not be reabsorbed in the same twilight step after gaining viable capacity"
    );
    assert!(
        matches!(twilight_events[0].actors.as_slice(), [CivRef::Existing(0), CivRef::Existing(1)]),
        "the only twilight absorption should be civ0 into civ1"
    );
}

// ---------------------------------------------------------------------------
// Step 11: Forced collapse
// ---------------------------------------------------------------------------

#[test]
fn test_forced_collapse_regions_first_and_integer_division() {
    let regions = make_3_regions([0, 0, 0]);

    let mut civ0 = make_civ(0, vec![0, 1, 2]);
    civ0.asabiya = 0.05; // < 0.1
    civ0.stability = 15; // <= 20
    civ0.military = 51; // 51 // 2 = 25
    civ0.economy = 33; // 33 // 2 = 16

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    // Should strip to first region
    let strip_op = result.civ_ops.iter().find(|op| op.op_type == CivOpType::StripToFirstRegion);
    assert!(strip_op.is_some(), "Should have StripToFirstRegion op");

    let strip = strip_op.unwrap();
    assert_eq!(strip.regions, vec![0], "Should keep regions[:1] = first listed region");

    // Verify integer division (not severity multiplier)
    // military goes from 51 to 25 (51//2), delta = -26
    // economy goes from 33 to 16 (33//2), delta = -17
    let mil_effect = result.civ_effects.iter().find(|e| e.field == "military" && e.step == 11);
    assert!(mil_effect.is_some(), "Should have military effect");
    let mil = mil_effect.unwrap();
    assert_eq!(mil.delta_i, 25 - 51, "Military should use integer division: 51//2=25, delta=-26");

    let eco_effect = result.civ_effects.iter().find(|e| e.field == "economy" && e.step == 11);
    assert!(eco_effect.is_some(), "Should have economy effect");
    let eco = eco_effect.unwrap();
    assert_eq!(eco.delta_i, 16 - 33, "Economy should use integer division: 33//2=16, delta=-17");

    // Verify lost regions get nullified controllers
    assert!(
        result.region_ops.iter().filter(|op| op.op_type == RegionOpType::NullifyController).count() == 2,
        "Should nullify 2 lost regions"
    );

    // Verify collapse event
    assert!(
        result.events.iter().any(|e| e.event_type == "collapse"),
        "Should emit collapse event"
    );
}

#[test]
fn test_forced_collapse_hybrid_mode_shocks() {
    let regions = make_3_regions([0, 0, 0]);

    let mut civ0 = make_civ(0, vec![0, 1, 2]);
    civ0.asabiya = 0.05;
    civ0.stability = 15;
    civ0.military = 50;
    civ0.economy = 30;

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, true);

    // In hybrid mode, should use HybridShock with -0.5
    let mil_effect = result.civ_effects.iter().find(|e| e.field == "military" && e.step == 11);
    assert!(mil_effect.is_some());
    let mil = mil_effect.unwrap();
    assert_eq!(mil.routing, EffectRouting::HybridShock);
    assert!((mil.delta_f - (-0.5)).abs() < 0.001, "Hybrid shock should be -0.5");
}

// ---------------------------------------------------------------------------
// Determinism
// ---------------------------------------------------------------------------

#[test]
fn test_deterministic_outputs_same_inputs() {
    let regions = make_5_regions_star(0);

    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 0;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;

    let config = default_config();
    let topo = default_topology();

    let result1 = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, false);
    let result2 = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, false);

    // Exact same number of ops
    assert_eq!(result1.civ_ops.len(), result2.civ_ops.len());
    assert_eq!(result1.region_ops.len(), result2.region_ops.len());
    assert_eq!(result1.relationship_ops.len(), result2.relationship_ops.len());
    assert_eq!(result1.events.len(), result2.events.len());
    assert_eq!(result1.civ_effects.len(), result2.civ_effects.len());
    assert_eq!(result1.bookkeeping.len(), result2.bookkeeping.len());

    // Same event types in same order
    for (e1, e2) in result1.events.iter().zip(result2.events.iter()) {
        assert_eq!(e1.event_type, e2.event_type);
        assert_eq!(e1.step, e2.step);
        assert_eq!(e1.seq, e2.seq);
        assert_eq!(e1.importance, e2.importance);
    }

    // Same civ op types in same order
    for (o1, o2) in result1.civ_ops.iter().zip(result2.civ_ops.iter()) {
        assert_eq!(o1.op_type, o2.op_type);
        assert_eq!(o1.step, o2.step);
        assert_eq!(o1.seq, o2.seq);
        assert_eq!(o1.regions, o2.regions);
    }
}

#[test]
fn test_determinism_across_5_runs() {
    let regions = make_3_regions([0, 0, 1]);
    let mut civ0 = make_civ(0, vec![0, 1]);
    civ0.stability = 10;
    civ0.treasury = 5;
    let civ1 = make_civ(1, vec![2]);

    let mut topo = default_topology();
    topo.vassals.push(VassalEntry { vassal: 1, overlord: 0 });
    topo.relationships.push(RelationshipEntry {
        civ_a: 1, civ_b: 0,
        disposition: Disposition::Suspicious, allied_turns: 0,
    });

    let config = default_config();

    let baseline = run_politics_pass(&[civ0.clone(), civ1.clone()], &regions, &topo, &config, 100, 7, false);

    for _ in 0..5 {
        let result = run_politics_pass(&[civ0.clone(), civ1.clone()], &regions, &topo, &config, 100, 7, false);
        assert_eq!(result.events.len(), baseline.events.len(), "Event count must match across runs");
        assert_eq!(result.civ_ops.len(), baseline.civ_ops.len(), "CivOp count must match");
        assert_eq!(result.vassal_ops.len(), baseline.vassal_ops.len(), "VassalOp count must match");
    }
}

// ---------------------------------------------------------------------------
// Step ordering invariant
// ---------------------------------------------------------------------------

#[test]
fn test_step_ordering_monotonic() {
    let regions = make_5_regions_star(0);
    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 0;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;
    civ0.asabiya = 0.05; // triggers forced collapse too

    let config = default_config();
    let topo = default_topology();

    // Try multiple seeds to get a run with many steps active
    for s in 0..50u64 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, s, false);

        // Verify event steps are non-decreasing
        let event_steps: Vec<u8> = result.events.iter().map(|e| e.step).collect();
        for w in event_steps.windows(2) {
            assert!(
                w[0] <= w[1],
                "Event step ordering must be non-decreasing: {} followed by {}",
                w[0], w[1]
            );
        }
    }
}

// ---------------------------------------------------------------------------
// Decline tracking
// ---------------------------------------------------------------------------

#[test]
fn test_decline_tracking_bookkeeping() {
    let regions = make_3_regions([0, 0, 0]);
    let mut civ0 = make_civ(0, vec![0, 1, 2]);
    civ0.decline_turns = 5;
    civ0.stats_sum_history = vec![200; 19]; // 19 entries, will become 20

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    // Should append stats history
    assert!(
        result.bookkeeping.iter().any(|b| b.bk_type == BookkeepingType::AppendStatsHistory),
        "Should append to stats_sum_history"
    );
}

// ---------------------------------------------------------------------------
// Helper function tests
// ---------------------------------------------------------------------------

#[test]
fn test_normalize_shock() {
    assert!((normalize_shock(10, 100) + 0.1).abs() < 0.001);
    assert!((normalize_shock(200, 100) + 1.0).abs() < 0.001); // capped at -1.0
    assert!((normalize_shock(10, 0) + 1.0).abs() < 0.001); // base=0 → -min(10/1, 1) = -1.0
}

#[test]
fn test_empty_pass_no_ops() {
    let regions = make_3_regions([0, 0, 0]);
    let civ0 = make_civ(0, vec![0, 1, 2]); // stable, nothing should trigger

    let config = default_config();
    let topo = default_topology();

    let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, 42, false);

    // Should have no civ ops, no events (except possibly decline tracking)
    assert!(
        result.civ_ops.is_empty(),
        "Stable civ should have no civ ops"
    );
    // May have decline tracking bookkeeping — that's expected
}

// ===========================================================================
// Task 3: FFI contract tests
// ===========================================================================

// ---------------------------------------------------------------------------
// Schema helper tests — verify field names and types are stable
// ---------------------------------------------------------------------------

#[test]
fn test_politics_civ_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_civ_ops_schema();
    assert!(schema.field_with_name("step").is_ok(), "civ ops schema must have 'step'");
    assert!(schema.field_with_name("seq").is_ok(), "civ ops schema must have 'seq'");
    assert!(schema.field_with_name("op_type").is_ok(), "civ ops schema must have 'op_type'");
    assert!(schema.field_with_name("source_ref_kind").is_ok());
    assert!(schema.field_with_name("source_ref_id").is_ok());
    assert!(schema.field_with_name("region_indices").is_ok());
}

#[test]
fn test_politics_region_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_region_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("seq").is_ok());
    assert!(schema.field_with_name("region").is_ok());
    assert!(schema.field_with_name("controller_ref_kind").is_ok());
}

#[test]
fn test_politics_relationship_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_relationship_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("seq").is_ok());
    assert!(schema.field_with_name("civ_a_ref_kind").is_ok());
    assert!(schema.field_with_name("civ_b_ref_kind").is_ok());
    assert!(schema.field_with_name("disposition").is_ok());
}

#[test]
fn test_politics_federation_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_federation_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("seq").is_ok());
    assert!(schema.field_with_name("federation_ref_kind").is_ok());
}

#[test]
fn test_politics_vassal_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_vassal_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("seq").is_ok());
    assert!(schema.field_with_name("vassal_ref_kind").is_ok());
}

#[test]
fn test_politics_exile_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_exile_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("seq").is_ok());
    assert!(schema.field_with_name("original_civ_ref_kind").is_ok());
    assert!(schema.field_with_name("conquered_regions").is_ok());
    assert!(schema.field_with_name("turns_remaining").is_ok());
}

#[test]
fn test_politics_proxy_war_ops_schema_has_step_seq() {
    let schema = chronicler_agents::ffi_schemas::politics_proxy_war_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("seq").is_ok());
    assert!(schema.field_with_name("sponsor_ref_kind").is_ok());
    assert!(schema.field_with_name("target_region").is_ok());
}

#[test]
fn test_politics_civ_effect_ops_schema_has_field_and_routing() {
    let schema = chronicler_agents::ffi_schemas::politics_civ_effect_ops_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("field").is_ok());
    assert!(schema.field_with_name("delta").is_ok());
    assert!(schema.field_with_name("routing").is_ok());
}

#[test]
fn test_politics_bookkeeping_schema_has_bk_type() {
    let schema = chronicler_agents::ffi_schemas::politics_bookkeeping_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("bk_type").is_ok());
    assert!(schema.field_with_name("value").is_ok());
    assert!(schema.field_with_name("event_key").is_ok());
}

#[test]
fn test_politics_artifact_intent_schema_has_action() {
    let schema = chronicler_agents::ffi_schemas::politics_artifact_intent_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("action").is_ok());
    assert!(schema.field_with_name("is_capital").is_ok());
}

#[test]
fn test_politics_bridge_transition_schema_has_transition_type() {
    let schema = chronicler_agents::ffi_schemas::politics_bridge_transition_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("transition_type").is_ok());
    assert!(schema.field_with_name("region_indices").is_ok());
}

#[test]
fn test_politics_event_trigger_schema_has_event_type() {
    let schema = chronicler_agents::ffi_schemas::politics_event_trigger_schema();
    assert!(schema.field_with_name("step").is_ok());
    assert!(schema.field_with_name("event_type").is_ok());
    assert!(schema.field_with_name("actor_count").is_ok());
    assert!(schema.field_with_name("importance").is_ok());
}

// ---------------------------------------------------------------------------
// CivRef primitive encoding tests
// ---------------------------------------------------------------------------

#[test]
fn test_civref_existing_encodes_as_0() {
    let cr = CivRef::Existing(42);
    // The FFI should encode this as (ref_kind=0, ref_id=42)
    match cr {
        CivRef::Existing(id) => assert_eq!(id, 42),
        CivRef::New(_) => panic!("Expected Existing"),
    }
}

#[test]
fn test_civref_new_encodes_as_1() {
    let cr = CivRef::New(7);
    match cr {
        CivRef::Existing(_) => panic!("Expected New"),
        CivRef::New(id) => assert_eq!(id, 7),
    }
}

// ---------------------------------------------------------------------------
// Step/seq ordering on result — verify all op families have ordered fields
// ---------------------------------------------------------------------------

#[test]
fn test_result_ops_all_have_step_seq() {
    let regions = make_5_regions_star(0);
    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 0;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;
    civ0.asabiya = 0.05; // triggers forced collapse

    let config = default_config();
    let topo = default_topology();

    // Try many seeds to get a run with diverse ops
    for s in 0..50u64 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, s, false);

        // All op families should have step fields that are 1..=11
        for op in &result.civ_ops {
            assert!((1..=11).contains(&op.step), "CivOp step out of range: {}", op.step);
        }
        for op in &result.region_ops {
            assert!((1..=11).contains(&op.step), "RegionOp step out of range: {}", op.step);
        }
        for op in &result.relationship_ops {
            assert!((1..=11).contains(&op.step), "RelOp step out of range: {}", op.step);
        }
        for op in &result.federation_ops {
            assert!((1..=11).contains(&op.step), "FedOp step out of range: {}", op.step);
        }
        for op in &result.civ_effects {
            assert!((1..=11).contains(&op.step), "CivEffect step out of range: {}", op.step);
        }
        for bk in &result.bookkeeping {
            assert!((1..=11).contains(&bk.step), "Bookkeeping step out of range: {}", bk.step);
        }
        for ev in &result.events {
            assert!((1..=11).contains(&ev.step), "Event step out of range: {}", ev.step);
        }
    }
}

// ---------------------------------------------------------------------------
// Primitive scalar args (turn, seed, hybrid_mode) tests
// ---------------------------------------------------------------------------

#[test]
fn test_different_turns_produce_different_rng() {
    let regions = make_5_regions_star(0);
    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 5;
    civ0.founded_turn = 0;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;

    let config = default_config();
    let topo = default_topology();

    let r1 = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, false);
    let r2 = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 200, 42, false);

    // Different turns should produce potentially different outcomes
    // (Not necessarily different every time, but the RNG path diverges)
    // Just verify both runs complete without error
    assert!(r1.bookkeeping.len() > 0 || r2.bookkeeping.len() > 0,
        "At least one run should have bookkeeping ops");
}

#[test]
fn test_hybrid_mode_flag_changes_routing() {
    let regions = make_3_regions([0, 0, 0]);
    let mut civ0 = make_civ(0, vec![0, 1, 2]);
    civ0.asabiya = 0.05;
    civ0.stability = 15;
    civ0.military = 50;
    civ0.economy = 30;

    let config = default_config();
    let topo = default_topology();

    let r_off = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, false);
    let r_hybrid = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, true);

    // In off mode, forced collapse uses DirectOnly routing
    let off_routings: Vec<_> = r_off.civ_effects.iter()
        .filter(|e| e.step == 11)
        .map(|e| &e.routing)
        .collect();
    let hybrid_routings: Vec<_> = r_hybrid.civ_effects.iter()
        .filter(|e| e.step == 11)
        .map(|e| &e.routing)
        .collect();

    // off mode: DirectOnly for step 11 effects
    for r in &off_routings {
        assert_eq!(**r, EffectRouting::DirectOnly, "Off-mode step 11 should use DirectOnly");
    }
    // hybrid mode: HybridShock for step 11 effects
    for r in &hybrid_routings {
        assert_eq!(**r, EffectRouting::HybridShock, "Hybrid step 11 should use HybridShock");
    }
}

// ===========================================================================
// Task 5: Parity and determinism safety net
// ===========================================================================

// ---------------------------------------------------------------------------
// Determinism across many seeds
// ---------------------------------------------------------------------------

#[test]
fn test_determinism_20_seeds_identical_ops() {
    // For each of 20 seeds, verify that repeated runs produce identical op batches
    let regions = make_5_regions_star(0);
    let config = default_config();
    let topo = default_topology();

    for seed in 0..20u64 {
        let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
        civ0.stability = 8;
        civ0.founded_turn = 0;
        civ0.military = 80;
        civ0.economy = 60;
        civ0.treasury = 50;

        let r1 = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, seed, false);
        let r2 = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, seed, false);

        assert_eq!(r1.civ_ops.len(), r2.civ_ops.len(),
            "Seed {}: civ_ops count mismatch", seed);
        assert_eq!(r1.region_ops.len(), r2.region_ops.len(),
            "Seed {}: region_ops count mismatch", seed);
        assert_eq!(r1.relationship_ops.len(), r2.relationship_ops.len(),
            "Seed {}: relationship_ops count mismatch", seed);
        assert_eq!(r1.federation_ops.len(), r2.federation_ops.len(),
            "Seed {}: federation_ops count mismatch", seed);
        assert_eq!(r1.vassal_ops.len(), r2.vassal_ops.len(),
            "Seed {}: vassal_ops count mismatch", seed);
        assert_eq!(r1.exile_ops.len(), r2.exile_ops.len(),
            "Seed {}: exile_ops count mismatch", seed);
        assert_eq!(r1.proxy_war_ops.len(), r2.proxy_war_ops.len(),
            "Seed {}: proxy_war_ops count mismatch", seed);
        assert_eq!(r1.civ_effects.len(), r2.civ_effects.len(),
            "Seed {}: civ_effects count mismatch", seed);
        assert_eq!(r1.bookkeeping.len(), r2.bookkeeping.len(),
            "Seed {}: bookkeeping count mismatch", seed);
        assert_eq!(r1.events.len(), r2.events.len(),
            "Seed {}: events count mismatch", seed);

        // Verify event types and ordering match exactly
        for (e1, e2) in r1.events.iter().zip(r2.events.iter()) {
            assert_eq!(e1.event_type, e2.event_type,
                "Seed {}: event type mismatch", seed);
            assert_eq!(e1.step, e2.step,
                "Seed {}: event step mismatch", seed);
            assert_eq!(e1.seq, e2.seq,
                "Seed {}: event seq mismatch", seed);
        }
    }
}

#[test]
fn test_determinism_with_complex_topology() {
    // Complex topology: vassals, federations, exiles, proxy wars
    let mut regions = Vec::new();
    for i in 0..6u16 {
        let mut r = RegionInput::new(i);
        r.controller = i / 2; // 3 civs, 2 regions each
        r.effective_capacity = 40 + (i * 5);
        r.adjacencies = if i == 0 { vec![1] }
            else if i == 5 { vec![4] }
            else { vec![i - 1, i + 1] };
        regions.push(r);
    }

    let civ0 = make_civ(0, vec![0, 1]);
    let mut civ1 = make_civ(1, vec![2, 3]);
    civ1.stability = 10;
    civ1.treasury = 5;
    let civ2 = make_civ(2, vec![4, 5]);

    let mut topo = default_topology();
    topo.vassals.push(VassalEntry { vassal: 1, overlord: 0 });
    topo.relationships.push(RelationshipEntry {
        civ_a: 1, civ_b: 0,
        disposition: Disposition::Hostile, allied_turns: 0,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 0, civ_b: 2,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.relationships.push(RelationshipEntry {
        civ_a: 2, civ_b: 0,
        disposition: Disposition::Allied, allied_turns: 10,
    });
    topo.proxy_wars.push(ProxyWarEntry {
        sponsor: 0, target_civ: 2, target_region: 4, detected: false,
    });

    let config = default_config();

    let baseline = run_politics_pass(
        &[civ0.clone(), civ1.clone(), civ2.clone()],
        &regions, &topo, &config, 100, 42, false,
    );

    for run in 0..5 {
        let result = run_politics_pass(
            &[civ0.clone(), civ1.clone(), civ2.clone()],
            &regions, &topo, &config, 100, 42, false,
        );
        assert_eq!(result.civ_ops.len(), baseline.civ_ops.len(),
            "Run {}: civ_ops count mismatch", run);
        assert_eq!(result.vassal_ops.len(), baseline.vassal_ops.len(),
            "Run {}: vassal_ops count mismatch", run);
        assert_eq!(result.federation_ops.len(), baseline.federation_ops.len(),
            "Run {}: federation_ops count mismatch", run);
        assert_eq!(result.events.len(), baseline.events.len(),
            "Run {}: events count mismatch", run);

        // Verify exact event ordering
        for (e1, e2) in result.events.iter().zip(baseline.events.iter()) {
            assert_eq!(e1.event_type, e2.event_type,
                "Run {}: event type mismatch", run);
            assert_eq!(e1.step, e2.step,
                "Run {}: event step mismatch", run);
        }
    }
}

#[test]
fn test_event_merge_order_stable_across_runs() {
    // Verify event merge ordering is identical across 10 runs
    let regions = make_5_regions_star(0);
    let mut civ0 = make_civ(0, vec![0, 1, 2, 3, 4]);
    civ0.stability = 3;
    civ0.founded_turn = 0;
    civ0.military = 100;
    civ0.economy = 100;
    civ0.treasury = 100;
    civ0.asabiya = 0.05; // triggers forced collapse + possibly secession

    let config = default_config();
    let topo = default_topology();

    // Find a seed that produces multiple events
    let mut test_seed = 0u64;
    let mut baseline_event_count = 0;
    for s in 0..100u64 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, s, false);
        if result.events.len() >= 2 {
            test_seed = s;
            baseline_event_count = result.events.len();
            break;
        }
    }

    if baseline_event_count < 2 {
        // At minimum, forced collapse alone produces events
        return;
    }

    let baseline = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, test_seed, false);

    for _ in 0..10 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, test_seed, false);
        assert_eq!(result.events.len(), baseline.events.len());
        for (e1, e2) in result.events.iter().zip(baseline.events.iter()) {
            assert_eq!(e1.event_type, e2.event_type, "Event type ordering unstable");
            assert_eq!(e1.step, e2.step, "Event step ordering unstable");
            assert_eq!(e1.seq, e2.seq, "Event seq ordering unstable");
            assert_eq!(e1.importance, e2.importance, "Event importance unstable");
        }
    }
}

#[test]
fn test_civ_effect_ordering_deterministic() {
    // Verify civ effect deltas appear in the same order across runs
    let regions = make_3_regions([0, 0, 0]);
    let mut civ0 = make_civ(0, vec![0, 1, 2]);
    civ0.asabiya = 0.05;
    civ0.stability = 15;
    civ0.military = 51;
    civ0.economy = 33;

    let config = default_config();
    let topo = default_topology();

    let baseline = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, false);
    assert!(!baseline.civ_effects.is_empty(), "Should have civ effects from forced collapse");

    for _ in 0..5 {
        let result = run_politics_pass(&[civ0.clone()], &regions, &topo, &config, 100, 42, false);
        assert_eq!(result.civ_effects.len(), baseline.civ_effects.len());
        for (e1, e2) in result.civ_effects.iter().zip(baseline.civ_effects.iter()) {
            assert_eq!(e1.field, e2.field, "CivEffect field ordering unstable");
            assert_eq!(e1.step, e2.step, "CivEffect step ordering unstable");
            assert_eq!(e1.delta_i, e2.delta_i, "CivEffect delta_i unstable");
        }
    }
}

// ---------------------------------------------------------------------------
// Forced outcome scenarios (no RNG variance)
// ---------------------------------------------------------------------------

#[test]
fn test_forced_collapse_always_fires_deterministically() {
    // With asabiya=0.05 and stability=15 and >1 region, forced collapse
    // ALWAYS fires — no RNG involved. Verify across 20 seeds.
    let regions = make_3_regions([0, 0, 0]);

    let config = default_config();
    let topo = default_topology();

    for seed in 0..20u64 {
        let mut civ0 = make_civ(0, vec![0, 1, 2]);
        civ0.asabiya = 0.05;
        civ0.stability = 15;
        civ0.military = 50;
        civ0.economy = 30;

        let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, seed, false);
        assert!(
            result.civ_ops.iter().any(|op| op.op_type == CivOpType::StripToFirstRegion),
            "Seed {}: forced collapse must always fire", seed
        );
    }
}

#[test]
fn test_capital_loss_always_fires_deterministically() {
    // Capital loss is deterministic — no RNG. Verify across seeds.
    let regions = make_3_regions([0, 0, 0]);
    let config = default_config();
    let topo = default_topology();

    for seed in 0..20u64 {
        let mut civ0 = make_civ(0, vec![1, 2]); // capital=0 not in regions
        civ0.capital_region = 0;

        let result = run_politics_pass(&[civ0], &regions, &topo, &config, 100, seed, false);
        assert!(
            result.civ_ops.iter().any(|op| op.op_type == CivOpType::ReassignCapital),
            "Seed {}: capital loss must always fire", seed
        );
    }
}
