use chronicler_agents::sort::{morton_interleave, radix_sort_u64, SPATIAL_SORT_AGENT_THRESHOLD};

#[test]
fn test_morton_interleave_known_values() {
    assert_eq!(morton_interleave(0, 0), 0);
    assert_eq!(morton_interleave(0xFF, 0xFF), 0xFFFF);
    assert_eq!(morton_interleave(1, 0), 1); // x bit 0
    assert_eq!(morton_interleave(0, 1), 2); // y bit 0
}

#[test]
fn test_morton_interleave_pattern() {
    // x=2 (0b10), y=0 → interleaved = 0b0100 = 4
    assert_eq!(morton_interleave(2, 0), 4);
    // x=0, y=2 (0b10) → interleaved = 0b1000 = 8
    assert_eq!(morton_interleave(0, 2), 8);
}

#[test]
fn test_radix_sort_preserves_order() {
    let keys = vec![30u64, 10, 20, 10];
    let sorted = radix_sort_u64(&keys);
    // Stable sort: 10@1 before 10@3
    assert_eq!(sorted, vec![1, 3, 2, 0]);
}

#[test]
fn test_radix_sort_empty() {
    let keys: Vec<u64> = vec![];
    let sorted = radix_sort_u64(&keys);
    assert!(sorted.is_empty());
}

#[test]
fn test_radix_sort_single() {
    let keys = vec![42u64];
    let sorted = radix_sort_u64(&keys);
    assert_eq!(sorted, vec![0]);
}

#[test]
fn test_radix_sort_already_sorted() {
    let keys = vec![1u64, 2, 3, 4, 5];
    let sorted = radix_sort_u64(&keys);
    assert_eq!(sorted, vec![0, 1, 2, 3, 4]);
}

#[test]
fn test_radix_sort_reverse() {
    let keys = vec![5u64, 4, 3, 2, 1];
    let sorted = radix_sort_u64(&keys);
    assert_eq!(sorted, vec![4, 3, 2, 1, 0]);
}

#[test]
fn test_radix_sort_large_keys() {
    // Test with keys that exercise high bytes
    let keys = vec![u64::MAX, 0, u64::MAX / 2, 1];
    let sorted = radix_sort_u64(&keys);
    // Expected order: 0, 1, MAX/2, MAX
    assert_eq!(keys[sorted[0]], 0);
    assert_eq!(keys[sorted[1]], 1);
    assert_eq!(keys[sorted[2]], u64::MAX / 2);
    assert_eq!(keys[sorted[3]], u64::MAX);
}

#[test]
fn test_sort_determinism() {
    let keys = vec![100u64, 50, 200, 50, 150];
    let s1 = radix_sort_u64(&keys);
    let s2 = radix_sort_u64(&keys);
    assert_eq!(s1, s2);
}

#[test]
fn test_threshold_constant() {
    assert_eq!(SPATIAL_SORT_AGENT_THRESHOLD, 100_000);
}
