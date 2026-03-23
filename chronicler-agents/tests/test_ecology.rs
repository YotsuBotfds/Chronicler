//! M54a integration tests: ecology region schema expansion.

use chronicler_agents::RegionState;

#[test]
fn test_region_new_has_ecology_defaults() {
    let r = RegionState::new(0);
    assert!((r.disease_baseline - 0.0).abs() < f32::EPSILON);
    assert!((r.capacity_modifier - 1.0).abs() < f32::EPSILON);
    assert_eq!(r.resource_base_yield, [0.0, 0.0, 0.0]);
    assert_eq!(r.resource_effective_yield, [0.0, 0.0, 0.0]);
    assert_eq!(r.resource_suspension, [false, false, false]);
    assert!(!r.has_irrigation);
    assert!(!r.has_mines);
    assert_eq!(r.active_focus, 0);
    assert!((r.prev_turn_water - 0.0).abs() < f32::EPSILON);
    assert_eq!(r.soil_pressure_streak, 0);
    assert_eq!(r.overextraction_streak, [0, 0, 0]);
}

#[test]
fn test_region_ecology_fields_independent_from_legacy() {
    // Ensure new ecology fields don't interfere with existing resource_yields/resource_reserves
    let r = RegionState::new(3);
    // Legacy resource_yields starts at [0.0; 3] (mutable same-turn yields)
    assert_eq!(r.resource_yields, [0.0, 0.0, 0.0]);
    // New base yields also start at [0.0; 3]
    assert_eq!(r.resource_base_yield, [0.0, 0.0, 0.0]);
    // Legacy resource_reserves starts at [1.0; 3]
    assert_eq!(r.resource_reserves, [1.0, 1.0, 1.0]);
    // These are separate fields — mutating one does not affect the other
    let mut r2 = r.clone();
    r2.resource_base_yield[0] = 2.5;
    assert_eq!(r2.resource_yields[0], 0.0);
    r2.resource_yields[1] = 1.0;
    assert_eq!(r2.resource_base_yield[1], 0.0);
}

#[test]
fn test_region_new_has_existing_endemic_severity_unchanged() {
    // endemic_severity already existed on RegionState; verify it still defaults to 0.0
    let r = RegionState::new(0);
    assert!((r.endemic_severity - 0.0).abs() < f32::EPSILON);
}
