//! Agent-scale benchmark for the Rust tick (no Python).
//!
//! Builds a synthetic world with spatial attractors, mixed ages, cultures and
//! beliefs so that spatial drift, marriage and formation all do real work, then
//! times `tick_agents` per turn. With `--hash` it prints an FNV-1a digest of the
//! full pool state and of every event, which is how exact-mode identity is
//! checked against a base build at scales the Python pipeline cannot reach.
//!
//! Usage:
//!   cargo run --release --example scale_bench -- \
//!       --agents 20000 --regions 12 --turns 30 --warmup 5 [--seed 42] [--hash]
//!
//! Output is a single JSON line on stdout.

use std::time::Instant;

use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::{
    init_attractors, migration_reset_position, update_attractor_weights, RegionAttractors,
    SpatialDiagnostics, SpatialGrid,
};
use chronicler_agents::{AgentEvent, AgentPool, Occupation, RegionState};

struct Args {
    agents: usize,
    regions: u16,
    turns: u32,
    warmup: u32,
    seed: u64,
    hash: bool,
    mode: String,
}

fn parse_args() -> Args {
    let argv: Vec<String> = std::env::args().collect();
    let mut a = Args {
        agents: 10_000,
        regions: 12,
        turns: 30,
        warmup: 5,
        seed: 42,
        hash: false,
        mode: "exact".to_string(),
    };
    let mut i = 1;
    while i < argv.len() {
        let next = |i: usize| argv.get(i + 1).cloned().unwrap_or_default();
        match argv[i].as_str() {
            "--agents" => { a.agents = next(i).parse().expect("--agents"); i += 2; }
            "--regions" => { a.regions = next(i).parse().expect("--regions"); i += 2; }
            "--turns" => { a.turns = next(i).parse().expect("--turns"); i += 2; }
            "--warmup" => { a.warmup = next(i).parse().expect("--warmup"); i += 2; }
            "--seed" => { a.seed = next(i).parse().expect("--seed"); i += 2; }
            "--mode" => { a.mode = next(i); i += 2; }
            "--hash" => { a.hash = true; i += 1; }
            other => panic!("unknown argument {other}"),
        }
    }
    a
}

/// Process CPU time (user + system, all threads) in seconds, from /proc.
fn process_cpu_seconds() -> f64 {
    let stat = match std::fs::read_to_string("/proc/self/stat") {
        Ok(s) => s,
        Err(_) => return f64::NAN,
    };
    // Fields after the parenthesised command name; utime/stime are fields 14/15.
    let rest = match stat.rfind(')') {
        Some(p) => &stat[p + 2..],
        None => return f64::NAN,
    };
    let fields: Vec<&str> = rest.split_whitespace().collect();
    let utime: f64 = fields.get(11).and_then(|v| v.parse().ok()).unwrap_or(f64::NAN);
    let stime: f64 = fields.get(12).and_then(|v| v.parse().ok()).unwrap_or(f64::NAN);
    (utime + stime) / 100.0 // USER_HZ is 100 on Linux
}

/// Deterministic splitmix64 stream for synthetic setup (independent of sim RNG).
struct SplitMix(u64);
impl SplitMix {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    fn unit(&mut self) -> f32 {
        ((self.next() >> 40) as f32) / ((1u64 << 24) as f32)
    }
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}

fn make_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: if i % 4 == 2 { 25 } else { 55 },
                is_at_war: i % 3 == 1,
                dominant_faction: (i % 3) as u8,
                faction_military: if i % 3 == 1 { 0.55 } else { 0.25 },
                faction_merchant: if i % 3 == 1 { 0.25 } else { 0.40 },
                faction_cultural: if i % 3 == 1 { 0.20 } else { 0.35 },
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
                mean_boldness: 0.0,
                mean_ambition: 0.0,
                mean_loyalty_trait: 0.0,
                faction_clergy: 0.0,
                gini_coefficient: 0.2,
                conquered_this_turn: false,
                priest_tithe_share: 0.0,
                cultural_drift_multiplier: 1.0,
                religion_intensity_multiplier: 1.0,
            })
            .collect(),
        contested_regions: (0..num_regions).map(|i| i % 5 == 0).collect(),
    }
}

fn setup(args: &Args) -> (AgentPool, Vec<RegionState>, TickSignals, Vec<RegionAttractors>, [u8; 32]) {
    let mut master_seed = [0u8; 32];
    master_seed[..8].copy_from_slice(&args.seed.to_le_bytes());
    let per_region = args.agents / args.regions as usize;
    let num_civs = (args.regions.min(8)) as usize;
    let regions: Vec<RegionState> = (0..args.regions)
        .map(|r| {
            let mut reg = RegionState::new(r);
            reg.carrying_capacity = per_region.min(u16::MAX as usize) as u16;
            reg.population = per_region.min(u16::MAX as usize) as u16;
            reg.terrain = (r % 3) as u8;
            reg.soil = 0.7;
            reg.water = 0.5;
            reg.forest_cover = 0.3;
            reg.controller_civ = (r as usize % num_civs) as u8;
            reg.resource_types = [0, 1, 255];
            reg.resource_yields = [0.6, 0.3, 0.0];
            reg.resource_base_yield = [0.6, 0.3, 0.0];
            reg.resource_effective_yield = [0.6, 0.3, 0.0];
            reg.is_capital = r % 4 == 0;
            reg.has_temple = r % 3 == 0;
            reg.temple_prestige = if r % 3 == 0 { 0.5 } else { 0.0 };
            reg.majority_belief = (r % 3) as u8;
            reg.trade_route_count = 2;
            reg.merchant_route_margin = 0.3;
            reg
        })
        .collect();
    let signals = make_signals(num_civs, args.regions as usize);
    let mut attractors: Vec<RegionAttractors> = regions
        .iter()
        .enumerate()
        .map(|(i, reg)| init_attractors(args.seed, i as u16, reg))
        .collect();
    for (i, reg) in regions.iter().enumerate() {
        update_attractor_weights(&mut attractors[i], reg);
    }

    let mut rng = SplitMix(args.seed ^ 0xA5A5_5A5A_DEAD_BEEF);
    let mut pool = AgentPool::new(args.agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..args.regions {
        let civ = regions[r as usize].controller_civ;
        for j in 0..per_region {
            // 60/15/10/10/5 occupation mix, as in the FFI initial spawn.
            let pct = (j * 100 / per_region.max(1)) as usize;
            let occ = match pct {
                0..=59 => occupations[0],
                60..=74 => occupations[1],
                75..=84 => occupations[2],
                85..=94 => occupations[3],
                _ => occupations[4],
            };
            let age = rng.below(70) as u16;
            let cv0 = rng.below(6) as u8;
            let cv1 = ((cv0 as u64 + 1 + rng.below(5)) % 6) as u8;
            let mut cv2 = rng.below(6) as u8;
            if cv2 == cv0 || cv2 == cv1 {
                cv2 = 0xFF;
            }
            let belief = (r as u64 % 3 + rng.below(2)) as u8;
            let slot = pool.spawn(
                r, civ, occ, age,
                rng.unit() * 2.0 - 1.0,
                rng.unit() * 2.0 - 1.0,
                rng.unit() * 2.0 - 1.0,
                cv0, cv1, cv2, belief,
            );
            let (x, y) = migration_reset_position(
                pool.ids[slot], pool.occupations[slot], &attractors[r as usize],
                &master_seed, r, 0,
            );
            pool.x[slot] = x;
            pool.y[slot] = y;
            pool.wealth[slot] = rng.unit() * 20.0;
        }
    }
    (pool, regions, signals, attractors, master_seed)
}

struct Fnv(u64);
impl Fnv {
    fn new() -> Self { Fnv(0xcbf2_9ce4_8422_2325) }
    fn bytes(&mut self, b: &[u8]) {
        for &x in b {
            self.0 ^= x as u64;
            self.0 = self.0.wrapping_mul(0x0000_0100_0000_01b3);
        }
    }
    fn u64(&mut self, v: u64) { self.bytes(&v.to_le_bytes()); }
}

fn hash_pool(pool: &AgentPool) -> u64 {
    let mut h = Fnv::new();
    h.u64(pool.capacity() as u64);
    for s in 0..pool.capacity() {
        h.bytes(&[pool.alive[s] as u8]);
        if !pool.alive[s] {
            continue;
        }
        h.bytes(&pool.ids[s].to_le_bytes());
        h.bytes(&pool.regions[s].to_le_bytes());
        h.bytes(&pool.origin_regions[s].to_le_bytes());
        h.bytes(&[pool.civ_affinities[s], pool.occupations[s], pool.beliefs[s]]);
        h.bytes(&pool.loyalties[s].to_bits().to_le_bytes());
        h.bytes(&pool.satisfactions[s].to_bits().to_le_bytes());
        for k in 0..5 {
            h.bytes(&pool.skills[s * 5 + k].to_bits().to_le_bytes());
        }
        h.bytes(&pool.ages[s].to_le_bytes());
        h.bytes(&[pool.displacement_turns[s], pool.life_events[s], pool.promotion_progress[s]]);
        h.bytes(&[pool.cultural_value_0[s], pool.cultural_value_1[s], pool.cultural_value_2[s]]);
        h.bytes(&pool.parent_id_0[s].to_le_bytes());
        h.bytes(&pool.parent_id_1[s].to_le_bytes());
        h.bytes(&pool.wealth[s].to_bits().to_le_bytes());
        h.bytes(&pool.memory_event_types[s]);
        h.bytes(&pool.memory_source_civs[s]);
        for v in pool.memory_turns[s] { h.bytes(&v.to_le_bytes()); }
        for v in pool.memory_intensities[s] { h.bytes(&v.to_le_bytes()); }
        h.bytes(&pool.memory_decay_factors[s]);
        h.bytes(&[pool.memory_gates[s], pool.memory_count[s], pool.memory_is_legacy[s]]);
        for v in [
            pool.need_safety[s], pool.need_material[s], pool.need_social[s],
            pool.need_spiritual[s], pool.need_autonomy[s], pool.need_purpose[s],
        ] {
            h.bytes(&v.to_bits().to_le_bytes());
        }
        let n = pool.rel_count[s] as usize;
        h.bytes(&[pool.rel_count[s]]);
        for k in 0..n {
            h.bytes(&pool.rel_target_ids[s][k].to_le_bytes());
            h.bytes(&pool.rel_sentiments[s][k].to_le_bytes());
            h.bytes(&[pool.rel_bond_types[s][k]]);
            h.bytes(&pool.rel_formed_turns[s][k].to_le_bytes());
        }
        h.bytes(&pool.x[s].to_bits().to_le_bytes());
        h.bytes(&pool.y[s].to_bits().to_le_bytes());
        h.bytes(&pool.settlement_ids[s].to_le_bytes());
    }
    h.0
}

fn hash_events(h: &mut Fnv, events: &[AgentEvent]) {
    h.u64(events.len() as u64);
    for e in events {
        h.bytes(&e.agent_id.to_le_bytes());
        h.bytes(&[e.event_type, e.civ_affinity, e.occupation, e.belief]);
        h.bytes(&e.region.to_le_bytes());
        h.bytes(&e.target_region.to_le_bytes());
        h.bytes(&e.turn.to_le_bytes());
        h.bytes(&e.target_agent_id.to_le_bytes());
        h.bytes(&e.formed_turn.to_le_bytes());
    }
}

fn median(v: &mut Vec<f64>) -> f64 {
    if v.is_empty() {
        return f64::NAN;
    }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = v.len();
    if n % 2 == 1 { v[n / 2] } else { 0.5 * (v[n / 2 - 1] + v[n / 2]) }
}

fn main() {
    let args = parse_args();
    let (mut pool, regions, signals, attractors, master_seed) = setup(&args);
    let mut percentiles: Vec<f32> = vec![0.0; pool.capacity()];
    let mut grids: Vec<SpatialGrid> = Vec::new();
    let mut ev_hash = Fnv::new();
    let mut wall_ms: Vec<f64> = Vec::new();
    let mut cpu_total = 0.0f64;
    let mut wall_total = 0.0f64;
    let mut bonds = 0u64;
    let mut marriages = 0u64;
    let mut pairs_evaluated = 0u64;
    let mut marriage_pairs = 0u64;
    let initial_alive = pool.alive_count();
    let total = args.warmup + args.turns;
    for turn in 0..total {
        if percentiles.len() < pool.capacity() {
            percentiles.resize(pool.capacity(), 0.0);
        }
        let mut diag = SpatialDiagnostics::default();
        let cpu0 = process_cpu_seconds();
        let t0 = Instant::now();
        let (events, _kin, fstats, _demo, _hh, _ms, _ks) = run_tick(
            &args, &mut pool, &regions, &signals, master_seed, turn,
            &mut percentiles, &mut grids, &attractors, &mut diag,
        );
        let dt = t0.elapsed().as_secs_f64();
        let dcpu = process_cpu_seconds() - cpu0;
        if args.hash {
            hash_events(&mut ev_hash, &events);
        }
        if turn >= args.warmup {
            wall_ms.push(dt * 1e3);
            wall_total += dt;
            cpu_total += dcpu;
            bonds += fstats.bonds_formed as u64;
            marriages += fstats.marriages_formed as u64;
            pairs_evaluated += fstats.pairs_evaluated as u64;
            marriage_pairs += fstats.marriage_pairs_evaluated as u64;
        }
    }
    let measured = args.turns.max(1) as f64;
    let mut wall_sorted = wall_ms.clone();
    let med = median(&mut wall_sorted);
    let pool_hash = if args.hash { format!("\"{:016x}\"", hash_pool(&pool)) } else { "null".into() };
    let events_hash = if args.hash { format!("\"{:016x}\"", ev_hash.0) } else { "null".into() };
    println!(
        "{{\"agents\":{},\"regions\":{},\"mode\":\"{}\",\"seed\":{},\"warmup\":{},\"turns\":{},\
\"initial_alive\":{},\"final_alive\":{},\"tick_ms_median\":{:.3},\"tick_ms_mean\":{:.3},\
\"cpu_ms_per_tick\":{:.3},\"bonds_formed\":{},\"marriages_formed\":{},\"pairs_evaluated\":{},\
\"marriage_pairs_evaluated\":{},\"threads\":{},\"pool_hash\":{},\"events_hash\":{}}}",
        args.agents, args.regions, args.mode, args.seed, args.warmup, args.turns,
        initial_alive, pool.alive_count(), med, wall_total * 1e3 / measured,
        cpu_total * 1e3 / measured, bonds, marriages, pairs_evaluated, marriage_pairs,
        rayon::current_num_threads(), pool_hash, events_hash,
    );
}

#[allow(clippy::too_many_arguments)]
fn run_tick(
    args: &Args,
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
    percentiles: &mut [f32],
    grids: &mut Vec<SpatialGrid>,
    attractors: &[RegionAttractors],
    diag: &mut SpatialDiagnostics,
) -> (
    Vec<AgentEvent>,
    u32,
    chronicler_agents::formation::FormationStats,
    chronicler_agents::DemographicDebug,
    chronicler_agents::household::HouseholdStats,
    chronicler_agents::merchant::MerchantTripStats,
    chronicler_agents::knowledge::KnowledgeStats,
) {
    assert!(args.mode == "exact", "this build supports only --mode exact");
    chronicler_agents::tick_agents(
        pool, regions, signals, master_seed, turn, percentiles, grids, attractors, diag,
        &[], None,
    )
}
