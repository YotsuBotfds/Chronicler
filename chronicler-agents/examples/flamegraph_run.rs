//! Flamegraph-friendly binary: runs N turns at configurable scale.
//! Usage: cargo flamegraph --example flamegraph_run -- --agents 10000 --regions 24 --turns 500

use std::time::Instant;

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn main() {
    let args: Vec<String> = std::env::args().collect();

    let mut agents = 10_000usize;
    let mut num_regions = 24u16;
    let mut turns = 500u32;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--agents" => { agents = args[i + 1].parse().unwrap(); i += 2; }
            "--regions" => { num_regions = args[i + 1].parse().unwrap(); i += 2; }
            "--turns" => { turns = args[i + 1].parse().unwrap(); i += 2; }
            _ => { i += 1; }
        }
    }

    let agents_per_region = agents / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r,
        terrain: 0,
        carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16,
        soil: 0.7,
        water: 0.5,
        forest_cover: 0.3,
        adjacency_mask: if num_regions <= 32 {
            (if r > 0 { 1u32 << (r - 1) } else { 0 })
                | (if r < num_regions - 1 { 1u32 << (r + 1) } else { 0 })
        } else {
            0
        },
        controller_civ: (r % 4) as u8,
        trade_route_count: 0,
    }).collect();

    let num_civs = (num_regions.min(8)) as usize;
    let signals = TickSignals {
        civs: (0..num_civs)
            .map(|c| CivSignals {
                civ_id: c as u8,
                stability: if c % 4 == 2 { 25 } else { 55 },
                is_at_war: c % 3 == 1,
                dominant_faction: (c % 3) as u8,
                faction_military: if c % 3 == 1 { 0.55 } else { 0.25 },
                faction_merchant: if c % 3 == 1 { 0.25 } else { 0.40 },
                faction_cultural: if c % 3 == 1 { 0.20 } else { 0.35 },
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
            })
            .collect(),
        contested_regions: (0..num_regions as usize).map(|r| r % 5 == 0).collect(),
    };

    let mut pool = AgentPool::new(agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occupations[j % 5], (j % 60) as u16);
        }
    }

    let mut seed = [0u8; 32]; seed[0] = 42;

    eprintln!("Config: {} agents, {} regions, {} turns", agents, num_regions, turns);
    eprintln!("Agents/region: {}", agents_per_region);
    eprintln!("---");

    let total_start = Instant::now();
    for turn in 0..turns {
        let tick_start = Instant::now();
        let events = tick_agents(&mut pool, &regions, &signals, seed, turn);
        let tick_elapsed = tick_start.elapsed();

        if turn % 100 == 0 || turn == turns - 1 {
            eprintln!(
                "Turn {:>4}: {:>6.2}ms | alive: {:>6} | events: {:>4}",
                turn,
                tick_elapsed.as_secs_f64() * 1000.0,
                pool.alive_count(),
                events.len(),
            );
        }
    }
    let total_elapsed = total_start.elapsed();
    eprintln!("---");
    eprintln!("Total: {:.3}s ({:.2}ms avg/turn)", total_elapsed.as_secs_f64(), total_elapsed.as_secs_f64() * 1000.0 / turns as f64);
    eprintln!("Alive: {}", pool.alive_count());
}
