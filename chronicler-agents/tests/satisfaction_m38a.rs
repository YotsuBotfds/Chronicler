//! M38a satisfaction tests: clergy faction alignment and temple priest bonus.

use chronicler_agents::satisfaction::{compute_satisfaction, compute_satisfaction_with_culture};
use chronicler_agents::signals::CivShock;

fn default_shock() -> CivShock {
    CivShock::default()
}

/// Verify that occ_matches_faction=true gives the +0.05 faction bonus for priests.
/// The clergy faction (dominant_faction=3) maps to priests (occ=4) — M38a.
/// This tests the bonus at the compute_satisfaction level using occ_matches_faction=true.
#[test]
fn test_priest_clergy_faction_alignment() {
    let shock = default_shock();
    let sat_aligned = compute_satisfaction(
        4,     // priest
        0.5, 0.5, 50, 0.0, 0.8,
        false, false,
        true,  // occ_matches_faction = true (clergy dominant faction matched)
        false, 0, 0.0,
        &shock,
    );
    let sat_unaligned = compute_satisfaction(
        4,     // priest
        0.5, 0.5, 50, 0.0, 0.8,
        false, false,
        false, // occ_matches_faction = false
        false, 0, 0.0,
        &shock,
    );
    let diff = sat_aligned - sat_unaligned;
    assert!(
        (diff - 0.05).abs() < 0.001,
        "expected clergy faction alignment bonus of 0.05, got {diff}"
    );
}

/// Verify that a priest in a region with has_temple=true gets +0.10 satisfaction
/// vs has_temple=false (all else equal).
#[test]
fn test_temple_priest_bonus() {
    let shock = default_shock();
    let sat_with_temple = compute_satisfaction_with_culture(
        4,     // priest
        0.5, 0.5, 50, 0.0, 0.8,
        false, false, false, false, 0, 0.0,
        &shock,
        [0xFF, 0xFF, 0xFF], [0xFF, 0xFF, 0xFF],
        0xFF, 0xFF,
        true,  // has_temple
    );
    let sat_no_temple = compute_satisfaction_with_culture(
        4,     // priest
        0.5, 0.5, 50, 0.0, 0.8,
        false, false, false, false, 0, 0.0,
        &shock,
        [0xFF, 0xFF, 0xFF], [0xFF, 0xFF, 0xFF],
        0xFF, 0xFF,
        false, // has_temple
    );
    let diff = sat_with_temple - sat_no_temple;
    assert!(
        (diff - 0.10).abs() < 0.001,
        "expected temple priest bonus of 0.10, got {diff}"
    );
}

/// Verify that a non-priest (farmer, occ=0) gets NO temple bonus even when has_temple=true.
#[test]
fn test_temple_bonus_priest_only() {
    let shock = default_shock();
    let sat_with_temple = compute_satisfaction_with_culture(
        0,     // farmer
        0.5, 0.5, 50, 0.0, 0.8,
        false, false, false, false, 0, 0.0,
        &shock,
        [0xFF, 0xFF, 0xFF], [0xFF, 0xFF, 0xFF],
        0xFF, 0xFF,
        true,  // has_temple — should be ignored for non-priests
    );
    let sat_no_temple = compute_satisfaction_with_culture(
        0,     // farmer
        0.5, 0.5, 50, 0.0, 0.8,
        false, false, false, false, 0, 0.0,
        &shock,
        [0xFF, 0xFF, 0xFF], [0xFF, 0xFF, 0xFF],
        0xFF, 0xFF,
        false, // has_temple
    );
    assert!(
        (sat_with_temple - sat_no_temple).abs() < 0.001,
        "farmer should get no temple bonus, but got diff {}",
        sat_with_temple - sat_no_temple
    );
}
