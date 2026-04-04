//! B6 regression: spatial RNG streams must not collide across agents or
//! between migration and newborn placement.

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

fn spatial_seed(master_seed: &[u8; 32], agent_id: u32) -> [u8; 32] {
    let mut seed = *master_seed;
    let id_bytes = agent_id.to_le_bytes();
    seed[0] ^= id_bytes[0];
    seed[1] ^= id_bytes[1];
    seed[2] ^= id_bytes[2];
    seed[3] ^= id_bytes[3];
    seed
}

fn spatial_stream(region_id: u16, turn: u32, offset: u64) -> u64 {
    ((region_id as u64) << 48) | ((turn as u64) << 16) | offset
}

fn jitter_pair(seed: [u8; 32], stream: u64) -> (f32, f32) {
    let mut rng = ChaCha8Rng::from_seed(seed);
    rng.set_stream(stream);
    (rng.gen::<f32>(), rng.gen::<f32>())
}

#[test]
fn test_formerly_colliding_triples_produce_distinct_jitter() {
    let master = [42u8; 32];
    let offset = 2000u64;
    let seed_a = spatial_seed(&master, 1);
    let seed_b = spatial_seed(&master, 2);
    assert_ne!(seed_a, seed_b, "spatial_seed must produce distinct seeds for distinct agent_ids");
    let stream_a = spatial_stream(10, 0, offset);
    let stream_b = spatial_stream(0, 0, offset);
    let jitter_a = jitter_pair(seed_a, stream_a);
    let jitter_b = jitter_pair(seed_b, stream_b);
    assert_ne!(jitter_a, jitter_b, "Formerly colliding triples must produce distinct jitter");
}

#[test]
fn test_migration_and_newborn_produce_distinct_jitter() {
    let master = [42u8; 32];
    let agent_id = 100u32;
    let region_id = 5u16;
    let turn = 10u32;
    let seed = spatial_seed(&master, agent_id);
    let migration_stream = spatial_stream(region_id, turn, 2000);
    let newborn_stream = spatial_stream(region_id, turn, 2100);
    assert_ne!(migration_stream, newborn_stream);
    let jitter_m = jitter_pair(seed, migration_stream);
    let jitter_n = jitter_pair(seed, newborn_stream);
    assert_ne!(jitter_m, jitter_n, "Migration and newborn jitter must differ");
}

#[test]
fn test_same_inputs_produce_identical_jitter() {
    let master = [42u8; 32];
    let agent_id = 7u32;
    let seed = spatial_seed(&master, agent_id);
    let stream = spatial_stream(3, 5, 2000);
    let jitter_1 = jitter_pair(seed, stream);
    let jitter_2 = jitter_pair(seed, stream);
    assert_eq!(jitter_1, jitter_2, "Same inputs must produce identical jitter");
}
