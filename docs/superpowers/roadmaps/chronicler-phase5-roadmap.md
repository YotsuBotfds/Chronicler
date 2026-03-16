# Chronicler Phase 5 Roadmap — Agent-Based Population Model

> **Status:** Approved. Architectural review by Phoebe applied. Improvement notes integrated. All design decisions locked. Ready for implementation once Phase 4 completion items are resolved.
>
> **Phase 4 prerequisite:** All M19–M24 milestones landed, M19b post-M24 tuning pass converged, narration engine validated across Sonnet/Opus.
>
> **Toolchain:** Python 3.12 (venv for PyO3 ABI), Rust stable, pyo3-arrow, jemalloc (cfg-gated, Linux/WSL only).

---

## Why Agents

Phase 4's aggregate model produces rich emergent histories across 40+ interacting systems. It's working. Phase 5 isn't a fix — it's a capability unlock. Three things agents deliver that aggregates structurally cannot:

1. **Heterogeneous populations within a civ.** A single stability number can't express "satisfied farmers in the river valley, miserable soldiers on the frontier." With agents, a civ's internal geography matters. Secession becomes bottom-up (disloyal border populations) rather than threshold-triggered (stability < 20 → roll dice). This is the difference between "the empire fragmented" and "the frontier provinces had been restless for decades."

2. **Cross-civ loyalty drift without conquest.** Agents near borders can shift affinity to the neighboring civ organically. Cultural assimilation becomes emergent: a prosperous merchant civ absorbs border agents from a declining neighbor, not because a timer expired but because individual agents chose better lives. M16's memetic warfare and M24's information asymmetry gain a population-level substrate to operate on.

3. **Occupation economics as emergent behavior.** Instead of "economy = field on Civilization," economy emerges from merchant count × skill. A plague that kills merchants crashes the economy differently than one that kills farmers. A military-dominant faction that conscripts too many soldiers starves the merchant class. The coupled effects are genuine rather than scripted.

If the Phase 5 review concludes these three outcomes aren't worth the engineering cost, defer to Phase 6 and invest in viewer polish, scenario variety, or narration quality instead. But these are the capabilities that make the Chronicler feel like a living world rather than a spreadsheet with prose.

**Hardware:** 9950X (16C/32T, 192GB DDR5) for agent simulation via Rust + rayon. 4090 for narration (unchanged). Python orchestrates; Rust computes.

---

## Phase 4 Completion Items (before Phase 5 starts)

| Item | Status | Notes |
|------|--------|-------|
| M19b post-M24 tuning | In progress | Third tuning pass. Must converge on 34/34 before Phase 5 starts. |
| M20b — Batch Runner GUI | Deferred | BatchPanel in M12c setup lobby, wrapping M19 CLI. Config panel, inline analytics, compare mode. |
| Viewer extensions (M21–M24) | Deferred | Tech focus badge, faction influence bar, ecology variables on region hover, intelligence quality indicator. ~300 lines TS total. |
| Treasury cap fix (M24) | Ready | `politics.py:400` — `max_value=500` in vassal rebellion perception. Change to 9999 or remove cap. Logic error, not tuning. |
| Pin Python version | **Decided: 3.12** | Use Python 3.12 venv for the Rust bridge (PyO3 + pyo3-arrow). 3.14 is too bleeding-edge for stable PyO3 support. System Python can remain 3.14; the chronicler-agents build targets the 3.12 venv ABI. |
| Windows jemalloc guard | **Decided: cfg-gate** | `#[cfg(not(target_os = "windows"))]` with system allocator fallback. Develop on Windows with system allocator, run performance benchmarks on WSL or Linux. No workflow disruption. |
| Rust toolchain decision | **Decided: stable** | Stay on stable Rust. M29 SIMD uses auto-vectorization (enabled by M26's branchless satisfaction) or the `wide` crate. `std::simd` deferred until it stabilizes. |
| Bundle schema version | Ready | Add `bundle_version` or `agent_model_version` field to bundle metadata. Viewer and downstream tools need to handle bundles with and without agent data — version field lets consumers detect schema without guessing. |
| `demographics-only` mode guard | **Decided: clamp** | Add `min(pop, carrying_capacity × 1.2)` clamp to demographics-only mode so it produces bounded results if accidentally run for 500 turns. One line, prevents nonsense output. |

---

## Design Decisions (Locked)

These were open questions in the original draft. Locked by Phoebe with rationale.

### Decision 1: Agent Count Scales to Carrying Capacity

Scaled with floor 20, cap 500 per region. Fixed-count makes a desert region identical to a river valley in simulation fidelity, which defeats the purpose. Rayon's work-stealing handles 10:1 load imbalance without issue — the 9950X has 32 threads and agent ticks are microsecond-scale per agent. A typical map with 24 regions at varied capacities produces ~3,000–6,000 total agents.

### Decision 2: FFI Boundary Uses Apache Arrow

The original draft spec'd numpy-compatible `&[f32]` slices. This works for homogeneous arrays but breaks down when structured data crosses the boundary — event reporting needs (agent_id, region, event_type) tuples, oracle comparison needs labeled columns, and the batch runner needs to serialize agent snapshots.

Apache Arrow via `pyo3-arrow` (using the Arrow PyCapsule Interface) on the Rust side and `pyarrow` on the Python side provides zero-copy columnar exchange with schema. The 9950X's memory bandwidth makes Arrow's overhead negligible. This is the direction the Rust-Python ecosystem is converging on (Polars, DataFusion, Lance all use it).

Concrete implications for M25:
- `chronicler-agents/Cargo.toml` depends on `pyo3` and `pyo3-arrow` (via the Arrow PyCapsule Interface — zero-copy by default, avoids the IPC serialization path that raw `arrow-rs` can fall into)
- `ffi.rs` exposes `RecordBatch` views via `pyo3-arrow` owned types (`PyArray`, not `&PyArray` — references don't trigger zero-copy extraction)
- Python side accepts standard `pyarrow.RecordBatch` (PyCapsule is interoperable) but the Rust side uses the lighter `arro3-core` (~7MB vs PyArrow's ~100MB)
- Agent snapshots for the bundle are Arrow IPC, not JSON (keeps bundle size manageable at 10K agents)

### Decision 3: No Agent Personality in Phase 5

The occupation + satisfaction + loyalty triangle is already a 3-variable decision space. Adding personality (bold, cautious, greedy) creates a fourth axis that's hard to tune and harder to validate against the oracle. Defer to Phase 6 if narrative quality demands it.

### Decision 4: Demographic Birth/Death Model

Age-dependent mortality with satisfaction-influenced fertility. Fixed rates make the agent model a fancy random walk — the entire point is that "famine kills young farmers" is mechanically different from "famine reduces population by 15." The 30% complexity increase over a fixed-rate model is the cost of the capability that justifies building agents in the first place.

Specifics:
- Mortality: base rate by age bracket (young 0.5%, adult 1%, elder 5%) × ecological stress multiplier (low water, low soil → higher mortality for farmers)
- Fertility: satisfaction > 0.5 AND age in fertile range → birth probability scaled by ecology (farmer base 3%, others 1.5%)
- Dead agents release their pool slot; births claim free slots from the arena

### Decision 5: Viewer Stays at Civ Level (Mostly)

Agent-level visualization is scoped tightly to avoid building SimCity:
- Population heatmap by region (density overlay on existing map — already near this from Phase 4 region data)
- Occupation distribution bar chart per region (on region hover, alongside ecology variables)
- Named character mentions in the chronicle panel (text, not map markers)

No agent-level map markers, no individual agent tracking UI, no pathfinding visualization.

### Decision 6: Crate Name is `chronicler-agents`

It's what it is. `chronicler-core` implies it's the foundation of everything, which is aspirational but not true while Python is still the orchestrator.

---

## Hybrid Tick Ordering

The original draft left the timing of the Rust agent tick underspecified ("Python runs phases, then Rust ticks agents"). This creates a circular dependency: agent satisfaction depends on ecology (Phase 9), which depends on population (agent count), which depends on the agent tick.

**Resolution: the Rust tick runs between Phase 9 and Phase 10.**

```
Phase  1: Environment (climate, conditions, terrain transitions)
Phase  2: Economy (trade routes, income, tribute, treasury)
Phase  3: Politics (governing costs, vassal checks, congress, secession)
Phase  4: Military (maintenance, war costs, mercenaries)
Phase  5: Diplomacy (disposition drift, federation checks, peace)
Phase  6: Culture (prestige, value drift, assimilation, movements)
Phase  7: Tech (advancement rolls, focus selection, focus effects)
Phase  8: Action selection + resolution (action engine)
Phase  9: Ecology (soil/water/forest tick, terrain transitions, famine checks)

── Rust agent tick ──
  Read:  ecology state, war outcomes, faction dominance, civ stability
  Tick:  satisfaction → decisions → migration → occupation → loyalty → birth/death
  Write: agent aggregates → civ stats (population, military, economy, culture, stability)
  Emit:  agent events (rebellion, migration cascade, occupation shift, demographic crisis)
─────────────────────

Phase 10: Consequences (emergence, factions, succession, named events, snapshot)
```

Agents react to the ecology and political state that just updated. Their aggregate stats are written to `Civilization` objects before Phase 10's consequences processing. Agent-emitted events (local rebellion, demographic crisis) are appended to `events_timeline` and processed by Phase 10's faction tick and emergence checks.

On turn 1, agents initialize from the world-gen population distribution. No chicken-and-egg problem — the first tick has valid ecology state from world gen.

---

## Milestone Overview

| Milestone | Name | Est. Lines | Summary |
|-----------|------|-----------|---------|
| M25 | Rust Core + Arrow Bridge | ~800 Rust, ~200 Python | PyO3 crate, Agent struct, Arrow FFI, rayon thread pool |
| M26 | Agent Behavior + Shadow Oracle | ~1,400 Rust, ~300 Python | Decision model, demographics, shadow-mode oracle comparison |
| M27 | System Integration | ~600 Rust, ~400 Python | Wire agent aggregates into Python turn loop, hybrid mode |
| M28 | Oracle Gate | ~200 Python | Final 200-seed validation, pass/fail criteria, convergence report |
| M29 | Scale & Performance | ~400 Rust | 10K+ agents, profiling, arena allocation, SIMD |
| M30 | Agent Narrative | ~500 Python, ~200 Rust | Named characters, agent events, curator integration |

**Dependency graph:**
```
Phase 4 complete → M25 → M26 (includes shadow oracle) → M27 → M28 (gate)
                                                    ↘           ↗
                                                     M29
                                            M28 → M30
```

Key change from original: M28 is now a gate (pass/fail checkpoint), not a build milestone. The comparison framework is built during M26's shadow mode.

---

## M25: Rust Core + Arrow Bridge

> **Shipped 2026-03-16.** 15 commits on `feature/m25-rust-core-arrow-bridge`. 16 Rust tests + 46 Python tests green. Benchmark: ~174μs (target <500μs). Version deviations from draft below: pyo3 0.23→0.28, pyo3-arrow 0.5→0.17, arrow 54→58. Implementation details in `docs/superpowers/specs/2026-03-15-m25-rust-core-arrow-bridge-design.md`.

**Goal:** Establish the Rust crate, define the Agent struct with demographic fields, prove rayon parallelism works, and build the Arrow FFI data exchange layer.

### Agent State

```rust
#[repr(u8)]
enum Occupation {
    Farmer = 0,
    Soldier = 1,
    Merchant = 2,
    Scholar = 3,
    Priest = 4,
}

struct Agent {
    id: u32,
    region: u16,              // index into region array
    origin_region: u16,       // where this agent was born/created — never changes
    civ_affinity: u16,        // which civ this agent identifies with
    occupation: Occupation,
    loyalty: f32,             // 0.0–1.0, toward current civ
    satisfaction: f32,        // 0.0–1.0, drives migration/rebellion
    skill: f32,               // 0.0–1.0, occupation-specific competence
    age: u16,                 // turns alive
    displacement_turn: u16,   // turn when agent last changed regions (0 = never moved)
    alive: bool,
}
```

`origin_region` and `displacement_turn` cost 4 bytes total per agent but enable displacement tracking, refugee narratives ("agents displaced from their homeland for 50+ turns"), and nostalgia-driven loyalty drift toward origin civ. Without these fields, M30's named character histories lose their most compelling arc: the exile who returns.

Agent state is stored as **struct-of-arrays** (SoA), not array-of-structs, for cache efficiency and SIMD potential:

```rust
struct AgentPool {
    ids: Vec<u32>,
    regions: Vec<u16>,
    origin_regions: Vec<u16>,
    civ_affinities: Vec<u16>,
    occupations: Vec<u8>,
    loyalties: Vec<f32>,
    satisfactions: Vec<f32>,
    skills: Vec<f32>,
    ages: Vec<u16>,
    displacement_turns: Vec<u16>,
    alive: Vec<bool>,
    count: usize,
    // Arena: free-list for dead agent slots
    free_slots: Vec<usize>,
}
```

### FFI Boundary — Arrow

Python ↔ Rust data exchange via Apache Arrow `RecordBatch`, not raw numpy slices:

```rust
// Rust side — expose agent state as Arrow RecordBatch via pyo3-arrow
use pyo3_arrow::PyRecordBatch;
use arrow::record_batch::RecordBatch;
use pyo3::prelude::*;

#[pyclass]
struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    rng_seed: u64,
}

#[pymethods]
impl AgentSimulator {
    fn get_snapshot(&self) -> PyResult<PyObject> {
        // Returns Arrow RecordBatch via pyarrow interop
        // Zero-copy for contiguous f32/u16 arrays
        let batch = self.pool.to_record_batch()?;
        Python::with_gil(|py| batch.to_pyarrow(py))
    }

    fn get_aggregates(&self) -> PyResult<PyObject> {
        // Returns per-civ aggregated stats as Arrow RecordBatch
        // Columns: civ_id, population, military, economy, culture, stability
        let agg = self.pool.compute_aggregates(&self.regions)?;
        Python::with_gil(|py| agg.to_pyarrow(py))
    }

    fn set_region_state(&mut self, batch: PyObject) -> PyResult<()> {
        // Receive region ecology/capacity as Arrow RecordBatch from Python
        Python::with_gil(|py| {
            let rb = RecordBatch::from_pyarrow(py, &batch)?;
            self.regions = RegionState::from_record_batch(&rb)?;
            Ok(())
        })
    }

    fn tick(&mut self, turn: u32, signals: PyObject) -> PyResult<PyObject> {
        // signals: Arrow RecordBatch with war outcomes, faction shifts, etc.
        // Returns: Arrow RecordBatch of agent events emitted this tick
        // ...
    }
}
```

```python
# Python side
import pyarrow as pa
from chronicler_agents import AgentSimulator

sim = AgentSimulator(num_regions=24, seed=42, region_capacities=[...])

# Each turn, between Phase 9 and Phase 10:
signals = pa.record_batch({
    "war_outcomes": [...],
    "ecology_soil": [...],
    "ecology_water": [...],
    "faction_dominant": [...],
})
agent_events = sim.tick(turn=world.turn, signals=signals)
aggregates = sim.get_aggregates()  # pa.RecordBatch → write to Civ objects
```

### Rayon Integration

Region-partitioned parallel tick with deterministic scheduling:

```rust
use rayon::prelude::*;
use rand_chacha::ChaCha8Rng;
use rand::SeedableRng;

fn tick_agents(pool: &mut AgentPool, regions: &[RegionState], master_seed: [u8; 32], turn: u32) {
    // Partition agents by region index (deterministic order)
    let mut region_groups = pool.partition_by_region();

    // Parallel tick: each region's agents processed independently
    // Cross-region effects (migration) collected as pending moves
    region_groups
        .par_iter_mut()
        .for_each(|group| {
            // ChaCha8Rng with stream splitting — cryptographically independent
            // streams without correlation artifacts from XOR-based seed derivation
            let mut rng = ChaCha8Rng::from_seed(master_seed);
            rng.set_stream(group.region_id as u64 * 1000 + turn as u64);
            tick_region_agents(group, &regions[group.region_id], &mut rng);
        });

    // Sequential: apply pending migrations, births, deaths
    pool.apply_pending_migrations();
    pool.apply_births_deaths();
    pool.compact_dead_slots();  // return dead agent slots to free_slots
}
```

Deterministic scheduling: regions processed in index order (0, 1, 2, ...). Rayon's work-stealing reorders execution but not results — each region's output is independent. Per-region RNG uses `ChaCha8Rng` with native stream splitting (`set_stream()`) — this provides mathematically independent streams by construction, avoiding the correlation artifacts that XOR-based seed derivation can produce with simple PRNGs. ChaCha8 is fast (faster than ChaCha20) and the Rust Rand Book explicitly recommends `set_stream()` for parallel simulation.

### Deliverables

- `chronicler-agents/` crate with `Cargo.toml`, `lib.rs`, `agent.rs`, `pool.rs`, `ffi.rs`
- `pyo3` + `pyo3-arrow` + `rand_chacha` dependencies, Arrow RecordBatch FFI via PyCapsule Interface
- `tikv-jemallocator` as global allocator (consistently outperforms system allocator for arena-style allocation patterns)
- Release profile: `codegen-units = 1`, `lto = true`, `opt-level = 3` (enables cross-function optimization for tight inner loops)
- PyO3 bindings callable from Python: `AgentSimulator` class
- Benchmark: 6,000 agents × 1 tick (age + die only) < 0.5ms on 9950X
- Integration test: Python creates simulator, runs 10 ticks, reads Arrow snapshot back
- Arena allocation: dead agent slots reused, no Vec reallocation during simulation

### What This Milestone Does NOT Do

- No agent decision-making (agents just age and die via demographic model)
- No interaction with existing Python simulation systems
- No narrative integration
- No oracle comparison

---

## M26: Agent Behavior + Shadow Oracle

**Goal:** Agents make decisions each tick. Shadow mode runs agents alongside aggregate model and begins oracle comparison.

### Occupation Distribution

Each region's agent population distributes across occupations based on civ focus, ecology, and faction dominance:

| Occupation | Produces | Influenced By |
|-----------|----------|---------------|
| Farmer | Food (population capacity) | Soil quality, water, AGRICULTURE focus |
| Soldier | Military strength | WAR weight, civ stability, military faction |
| Merchant | Economy, trade income | Trade routes, COMMERCE focus, merchant faction |
| Scholar | Culture, tech advancement | SCHOLARSHIP focus, cultural faction |
| Priest | Stability, loyalty | Religious movements, traditions |

### Decision Model

Each tick, agents evaluate in order (short-circuit: first triggered decision executes, rest skipped):

1. **Rebel?** — loyalty < 0.2 AND satisfaction < 0.2 AND ≥ 5 same-region agents also below thresholds → emit rebellion event. Highest priority because rebellion is irreversible this tick.
2. **Migrate?** — satisfaction < 0.3 AND adjacent region (same or different civ) has higher expected satisfaction → queue migration. Displacement_turn updated.
3. **Switch occupation?** — current occupation's regional demand < 0.5 × supply AND alternative has demand > 1.5 × supply → switch (skill resets to 0.3, grows 0.05/turn).
4. **Loyalty drift** — if region borders another civ: loyalty drifts toward the civ whose agents in this region have higher mean satisfaction. Drift rate: ±0.02/turn. Below 0.3 loyalty, agent switches civ_affinity.

### Satisfaction Formula

```
satisfaction = base_satisfaction(occupation, region)
             + civ_stability_bonus     // civ.stability / 200, range 0.0–0.5
             + demand_supply_bonus     // (demand - supply) / max(supply, 1) × 0.2, clamped ±0.2
             - overcrowding_penalty    // max(0, (pop / capacity - 1.0) × 0.3)
             - war_penalty             // 0.15 if civ at war, 0.25 if this region is contested
             + faction_alignment       // 0.05 if occupation matches dominant faction
             - displacement_penalty    // 0.10 if displacement_turn > 0 AND region != origin_region
```

`base_satisfaction` by occupation × ecology:
- Farmer: `0.4 + soil × 0.3 + water × 0.2` (range 0.4–0.9 in good ecology)
- Soldier: `0.5 + (military_faction_influence × 0.3)` (range 0.5–0.8)
- Merchant: `0.4 + (trade_routes_in_region / 3) × 0.3` (range 0.4–0.7)
- Scholar: `0.5 + (cultural_faction_influence × 0.2)` (range 0.5–0.7)
- Priest: `0.6 - (stability_drain_this_turn / 30)` (range 0.4–0.6)

### Demographics

Runs after decisions, within the same tick:

```
Mortality:
  age < 20:   base 0.005 × ecological_stress_multiplier
  age 20–60:  base 0.010 × ecological_stress_multiplier × war_casualty_multiplier
  age > 60:   base 0.050 × ecological_stress_multiplier
  ecological_stress_multiplier = 1.0 + max(0, 0.5 - soil) + max(0, 0.5 - water)  // range 1.0–2.0
  war_casualty_multiplier = 2.0 if soldier AND civ at war, else 1.0

Fertility:
  Eligible: alive, age 16–45, satisfaction > 0.4
  Base rate: 0.03 (farmer), 0.015 (all others)
  Ecology modifier: × (0.5 + soil × 0.5)  // range 0.5–1.0
  Newborn: age=0, origin_region=parent's region, occupation=Farmer, skill=0.1, loyalty=parent's loyalty
```

### Shadow Mode

M26 runs agents in **shadow mode**: the aggregate Python simulation drives all stats and decisions as before. The Rust agent tick runs in parallel, receiving the same ecology/war/faction signals, but its outputs are *discarded* — civ stats still come from the aggregate model.

Instead, M26 *compares* agent-derived aggregates against the actual aggregate stats each turn:

```python
# In simulation.py, after Phase 9, before Phase 10:
if agent_mode == "shadow":
    agent_events = sim.tick(turn=world.turn, signals=build_signals(world))
    agent_aggs = sim.get_aggregates()  # what agents think the civ stats should be
    shadow_log.append({
        "turn": world.turn,
        "agent_stats": agent_aggs.to_pydict(),
        "aggregate_stats": {c.name: extract_stats(c) for c in world.civilizations},
    })
    # Discard agent_aggs — aggregate model still drives
```

At end of run, `shadow_log` feeds the oracle comparison framework (KS tests, distribution plots). This catches behavior-model bugs *before* integration.

### Shadow Oracle Comparison

Built during M26, not deferred to M28. Compares agent-derived distributions against aggregate distributions across a 50-seed shadow batch:

```python
from scipy.stats import ks_2samp, anderson_ksamp
import numpy as np

def shadow_oracle_report(shadow_logs: list[dict]) -> OracleReport:
    """Compare agent-derived and aggregate stat distributions at checkpoints."""
    checkpoints = [100, 250, 500]
    metrics = ["population", "military", "economy", "culture", "stability"]
    # Bonferroni correction: 15 comparisons → α = 0.05/15 ≈ 0.003
    # Without correction, P(≥1 false positive) = 1 - 0.95^15 ≈ 54%
    bonferroni_alpha = 0.05 / (len(metrics) * len(checkpoints))
    results = []
    for metric in metrics:
        for turn in checkpoints:
            agent_vals = extract_at_turn(shadow_logs, "agent_stats", metric, turn)
            agg_vals = extract_at_turn(shadow_logs, "aggregate_stats", metric, turn)
            # KS test (overall distribution shape)
            ks_stat, ks_p = ks_2samp(agent_vals, agg_vals)
            # Anderson-Darling (tail-sensitive — catches pathological extremes KS misses)
            ad_stat, _, ad_p = anderson_ksamp([agent_vals, agg_vals])
            results.append(OracleResult(metric, turn, ks_stat, ks_p, ad_p, bonferroni_alpha))

    # Correlation structure validation — catches correlated failures that
    # pass univariate tests (e.g., agent model has high military ↔ low economy
    # correlation that the aggregate model doesn't produce)
    correlation_checks = [("military", "economy"), ("culture", "stability")]
    for m1, m2 in correlation_checks:
        for turn in checkpoints:
            agent_m1 = extract_at_turn(shadow_logs, "agent_stats", m1, turn)
            agent_m2 = extract_at_turn(shadow_logs, "agent_stats", m2, turn)
            agg_m1 = extract_at_turn(shadow_logs, "aggregate_stats", m1, turn)
            agg_m2 = extract_at_turn(shadow_logs, "aggregate_stats", m2, turn)
            corr_delta = abs(
                np.corrcoef(agent_m1, agent_m2)[0, 1] -
                np.corrcoef(agg_m1, agg_m2)[0, 1]
            )
            results.append(CorrelationResult(m1, m2, turn, corr_delta))  # pass if < 0.15

    return OracleReport(results)
```

**Shadow mode exit criteria:** 5 core metrics × 3 checkpoints = 15 distribution comparisons (Bonferroni-corrected α = 0.003). If ≥ 12/15 pass both KS and Anderson-Darling tests, and all correlation structure checks have delta < 0.15, the agent behavior model is producing distributions compatible with the aggregate model. Proceed to M27 integration. If < 12/15 pass, tune agent behavior parameters before proceeding.

### Deliverables

- `behavior.rs`: decision logic per agent per tick (rebel → migrate → switch → drift)
- `occupation.rs`: occupation distribution, switching, demand/supply computation
- `satisfaction.rs`: satisfaction formula implementation (prefer branchless style — replace `max(0, x)` with `x * (x > 0) as f32`, compute all bonuses/penalties unconditionally and zero irrelevant ones with masks — this enables reliable auto-vectorization without explicit SIMD intrinsics)
- `demographics.rs`: age-dependent mortality, satisfaction-influenced fertility
- `src/chronicler/shadow.py`: shadow mode wiring, shadow log capture
- `src/chronicler/shadow_oracle.py`: KS comparison framework, report generation
- Tests: deterministic seed → identical agent state after N ticks
- Benchmark: 6,000 agents with full decision model + demographics < 3ms/tick
- Shadow oracle report from 50-seed × 500-turn shadow run

---

## M27: System Integration

> **Spec notes:** `docs/superpowers/specs/2026-03-16-m27-integration-spec-notes.md` — complete stat mutation inventory (76 mutations across 14 files), guard/keep/signal classification, shock propagation design, and StatAccumulator architecture recommendation.

**Goal:** Wire agent-level outputs into the existing Python simulation. Agent behavior produces emergent civ-level stats. Hybrid mode is live.

### Stat Derivation

Phase 4's civ stats are directly computed. Phase 5 derives them from agent aggregates:

| Stat | Phase 4 (aggregate) | Phase 5 (agent-derived) | Scaling |
|------|---------------------|------------------------|---------|
| Population | Direct field | Count of alive agents with matching civ_affinity | 1 agent = 1 population unit |
| Military | Direct field, ±events | Sum of (soldier.skill) across civ's agents | Normalized to 0–100 scale |
| Economy | Direct field, ±trade | Sum of (merchant.skill) + trade income | Normalized to 0–100 scale |
| Culture | Direct field, ±events | Sum of (scholar.skill) + priest.skill × 0.3 | Normalized to 0–100 scale |
| Stability | Direct drain/recovery | Mean(satisfaction) × Mean(loyalty) × 100 | Direct 0–100 mapping |

Normalization: agent-derived raw values are mapped to the 0–100 scale using the civ's carrying capacity as reference. A civ at full capacity with all max-skill agents = 100. This keeps Phase 4's action engine weight thresholds, event triggers, and phase logic unchanged.

### Hybrid Architecture

```
Python turn loop (--agents mode):
  Phases 1–9: Run unchanged (ecology, politics, actions, etc.)
              BUT skip direct stat modifications (pop growth, military ±, etc.)
              Phase outcomes (war results, trade, famine) stored as signals

  ── Rust agent tick (between Phase 9 and Phase 10) ──
    Input:  signals RecordBatch (war outcomes, ecology state, factions, etc.)
    Process: satisfaction → decisions → migration → occupation → loyalty → demographics
    Output: aggregates RecordBatch (per-civ stats) + events RecordBatch (agent events)
  ──────────────────────────────────────────────────────

  Write agent aggregates → Civilization objects
  Append agent events → world.events_timeline
  Phase 10: Consequences (factions, succession, emergence, named events, snapshot)
            Processes agent events alongside aggregate events — no special casing
```

### Signal Protocol

Signals from Python → Rust each tick:

| Signal | Source Phase | Data |
|--------|-------------|------|
| `war_outcomes` | Phase 8 | List of (attacker_civ, defender_civ, outcome, contested_region) |
| `ecology_state` | Phase 9 | Per-region (soil, water, forest, effective_capacity) |
| `faction_dominant` | Phase 10 prev turn | Per-civ dominant faction type |
| `trade_routes` | Phase 2 | Per-region active trade route count |
| `civ_at_war` | Phase 8 | Per-civ boolean |
| `civ_stability` | Phase 10 prev turn | Per-civ stability (for priest satisfaction) |

All signals are Arrow RecordBatches. Python builds them from world state; Rust reads them as typed columns.

### Modified Python Phases

Phases that currently modify civ stats directly need guards:

```python
# In simulation.py, before each direct stat modification:
if not world.agent_mode:
    civ.population += growth  # aggregate mode: direct modification
# In agent mode: skip. Agent demographics handle population.
# Similar guards for military ±, economy ±, culture ± in combat/trade/culture phases.
```

Phases that don't modify stats (politics, diplomacy, action selection) run unchanged. The action engine reads civ stats the same way — it doesn't know whether they came from agents or direct computation.

### Deliverables

- `integration.rs`: aggregate computation, stat normalization
- `signals.rs`: signal RecordBatch parsing
- `src/chronicler/agent_bridge.py`: Python ↔ Rust per-tick data exchange
- Modified `simulation.py`: agent-mode guards, Rust tick placement between Phase 9–10
- Integration tests: 100-turn hybrid simulation produces valid bundles
- Regression test: `--agents` off → bit-identical to Phase 4 output

---

## M28: Oracle Gate

**Goal:** Final validation that hybrid mode produces statistically similar distributions to aggregate mode. This is a pass/fail checkpoint, not a build milestone. The comparison framework was built in M26.

### Validation Protocol

200-seed × 500-turn batch, run twice: once with `--agents`, once without. Compare using the M26 oracle framework.

### Exit Criteria

All 34 M19b exit criteria re-evaluated on agent-model output. Pass thresholds:

| Category | Requirement |
|----------|-------------|
| Core 5 stats | KS + Anderson-Darling p > Bonferroni-corrected α at turns 100, 250, 500 (15 comparisons). Correlation structure delta < 0.15 for key metric pairs. |
| War frequency | Within ±20% of aggregate mean |
| Faction dynamics | Same dominant faction type in ≥ 70% of runs |
| Ecology trajectories | Soil/water/forest means within ±15% at checkpoints |
| Event firing rates | Each M13–M24 event type within 2× of aggregate rate |
| Civ lifetime | Mean turns-alive within ±15% |

### Expected Divergences (acceptable)

- **Migration frequency:** Agent model produces 2–5× more migrations (individual movement vs population-level). Pattern (direction, terrain preference) should match.
- **Rebellion timing:** Agent model may trigger 10–30 turns earlier (local dissatisfaction clusters form before civ-level stability drops).
- **Population noise:** Agent demographic model adds stochastic noise to smooth aggregate curves. Mean should match within 10%; variance will be higher.
- **Secession geography:** Agent loyalty drift means secession regions may differ from aggregate model's distance-based selection. This is a *feature* — it's more realistic.

### Failure Protocol

If the oracle gate fails:
1. Identify which metrics diverge
2. Classify: behavior bug (agent model wrong) vs emergent divergence (agent model reveals something aggregate missed)
3. Behavior bugs → fix in `behavior.rs`, re-run
4. Emergent divergences → document, adjust pass thresholds if the agent behavior is defensible
5. Re-run oracle gate

### Deliverables

- `oracle_report.json`: per-metric comparison results with KS statistics
- CLI: `chronicler validate-oracle ./agent_batch ./aggregate_batch`
- Pass/fail determination with justification for any threshold adjustments

---

## M29: Scale & Performance

**Goal:** Optimize the Rust agent model for 10,000+ agents at interactive speed. This milestone can run in parallel with M27 integration work.

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Tick time (6K agents) | < 3ms | 32 threads on 9950X |
| Tick time (10K agents) | < 5ms | 32 threads on 9950X |
| Memory per agent | < 48 bytes | SoA layout, no heap allocation per agent |
| 500-turn simulation (6K agents) | < 3 seconds | Full run including Python orchestration + Arrow exchange |
| 500-turn simulation (10K agents) | < 6 seconds | Full run including Python orchestration + Arrow exchange |
| Batch (200 × 500 turns × 6K agents) | < 12 minutes | `--parallel 30` on 9950X |

### Optimization Strategies

1. **SoA layout** (established in M25) — cache-line-friendly sequential access
2. **Region partitioning** — agents within a region share no state with other regions during tick; cross-region effects (migration) collected and applied after parallel phase
3. **Rayon work-stealing** — automatic load balancing across 32 threads for unequal region sizes
4. **Arena allocation** — pre-allocated agent pool with free-list, dead agent slots reused for births. Zero Vec reallocation during simulation.
5. **SIMD for satisfaction** — if M26's branchless satisfaction formula auto-vectorizes cleanly (check with `cargo asm`), this is already solved. If profiling shows satisfaction is still the bottleneck after branchless rewrites, add explicit SIMD via `std::simd` (nightly) or the `wide` crate to process 8 agents simultaneously (AVX2 = 8 × f32)
6. **Arrow zero-copy** — agent snapshot export to Python avoids serialization; Arrow RecordBatch wraps existing SoA Vec buffers

### Profiling

Use `criterion` for micro-benchmarks (per-function) and `flamegraph` for macro profiling (full 500-turn run). Profile at realistic agent counts (3K, 6K, 10K, 20K) and measure:
- Tick time breakdown: satisfaction (expected 40%), decisions (30%), demographics (20%), migration apply (10%)
- Arrow FFI overhead per tick (target: < 0.5ms)
- Memory: peak RSS, allocation rate, fragmentation from arena reuse
- Agent pool cache efficiency: measure whether alive agents become too scattered across the SoA arrays after many death/birth cycles (defeats cache prefetching). If >20% mortality spikes cause measurable slowdown, evaluate periodic full compaction (every 50 turns, O(n) copy amortized) or bitmap alive-filtering

### Deliverables

- Criterion benchmarks for: `tick_region_agents`, `compute_satisfaction`, `apply_migrations`, `compute_aggregates`
- Flamegraph analysis of 500-turn × 10K agent run
- Memory usage report (peak RSS, fragmentation)
- Before/after comparison for each optimization applied

---

## M30: Agent Narrative

> **Spec notes:** `docs/superpowers/specs/2026-03-16-m30-narrative-spec-notes.md` — design decisions on merging agent characters into GreatPerson model, conquest/secession transfer rules, curator scoring adjustments, narration prompt changes, NamedCharacterRegistry architecture, and windowed event detection.

**Goal:** Agent-level events produce richer narrative material. Named characters emerge from the simulation and appear in chronicles.

### Named Characters

Agents are promoted to **named characters** when they meet any threshold:

| Trigger | Threshold | Rationale |
|---------|-----------|-----------|
| High skill | skill > 0.9 for 20+ turns | Mastery → notable figure |
| Rebellion leader | Led a local_rebellion event | Political significance |
| Long displacement | displacement_turn > 0 AND turns since > 50 | Exile narrative |
| Serial migrant | 3+ region changes | Wanderer archetype |
| Occupation versatility | 3+ occupation switches | Polymath / survivor |
| Loyalty flipper | Changed civ_affinity | Defector / convert |

Named characters:
- Get procedurally generated names (from civ's cultural name pool)
- Are tracked in a Rust-side `NamedCharacterRegistry` (max 50 per run, max 10 per civ — prevents a dominant hegemony from monopolizing all named character slots and ensures narrative representation across civs)
- Record personal history: `Vec<(turn, event_type, region)>` — compact timeline
- Can become great person candidates (feeding M17's system — generals from veteran soldiers, merchants from high-skill traders)

### Agent-Level Event Types

| Event | Trigger | Importance |
|-------|---------|-----------|
| `local_rebellion` | ≥ 5 agents rebel in a region | 7 |
| `loyalty_cascade` | ≥ 10 agents shift civ_affinity in one region in 5 turns | 6 |
| `demographic_crisis` | Region loses > 30% agents in 10 turns | 7 |
| `occupation_shift` | > 25% of region switches occupation in 5 turns | 5 |
| `economic_boom` | Region merchant count doubles in 20 turns | 5 |
| `brain_drain` | ≥ 5 scholars leave a region in 10 turns | 5 |
| `notable_migration` | Named character moves regions | 4 |
| `exile_return` | Named character returns to origin_region after 30+ turns away | 6 |

### Narration Integration

Agent events feed into the existing M20a curator pipeline. The curator scores agent events alongside aggregate events using the same importance-weighted selection. Agent events provide texture ("the frontier garrisons deserted en masse"); aggregate events provide structure ("war broke out between Vrashni and Kethani").

The narrator receives agent context in `NarrationContext`:

```python
agent_context = {
    "named_characters": [
        {"name": "Kael", "occupation": "merchant", "region": "Amber Coast",
         "history": "born in Jade Valley, displaced by war, migrated twice"},
    ],
    "population_mood": "restless",      # from mean satisfaction
    "dominant_occupation": "soldiers",   # most common in affected regions
    "recent_migrations": 12,            # agent migrations in last 10 turns
    "displacement_fraction": 0.15,      # fraction of agents not in origin_region
}
```

### Deliverables

- `named_characters.rs`: character promotion, registry, history tracking
- `agent_events.rs`: event detection from agent state deltas (compare turn N vs N-1)
- Modified `curator.py`: scores agent events alongside aggregate events (no special weighting — importance field handles priority)
- Modified narrative prompt: includes agent_context block
- Test: 500-turn narration with agents includes at least 5 named character references
- Test: agent events appear in `events_timeline` and are processed by Phase 10

---

## ~~M31: Agent Tuning Pass~~ — DEFERRED TO PHASE 6

**Status:** Skipped. M30's calibration thresholds (promotion rates, character-reference bonus, event window counts) will all be recalibrated in Phase 6's comprehensive tuning pass (M47), which tunes 25+ constants across personality, culture, religion, wealth, and supply chain systems simultaneously. Running M31 independently would produce numbers obsolete by M34.

**bundle_version: 2** bump ships with M30 (named characters + agent events in bundle). Narrative quality review folded into M47.

---

## Cross-Cutting Concerns

### Determinism

Agent simulation is fully deterministic given a seed. Three mechanisms ensure this:

1. **Region processing order:** regions processed in index order (0, 1, 2, ...). Rayon parallelizes execution but each region's output depends only on its own agents and the shared signals — no cross-region data races.
2. **ChaCha8Rng with stream splitting:** each region gets a `ChaCha8Rng` seeded from the master seed with `set_stream(region_id × 1000 + turn)`. This provides cryptographically independent streams by construction — no risk of correlated sequences from XOR-based seed derivation. Same region, same turn, same decisions regardless of thread assignment.
3. **Migration ordering:** pending migrations applied in agent_id order after all regions complete. Ties (two agents want the same slot) resolved by lower agent_id wins.

### Backward Compatibility

Phase 5 uses fine-grained `--agents` flags for development, debugging, and regression isolation:

- `--agents=off` (default) — Phase 4 aggregate simulation, bit-identical output
- `--agents=demographics-only` (M25) — agents age and die but don't make decisions. Tests Rust crate + Arrow bridge without behavior complexity
- `--agents=shadow` (M26) — both models run, agent outputs discarded, oracle comparison logged. Isolates behavior-model bugs from integration bugs
- `--agents=hybrid` (M27+) — agent stats drive civ stats, full integration
- `--agent-narrative` (M30) — named characters and agent events in chronicles. Independent of agent tick mode (can run with `hybrid` or `shadow`)

If a bug appears in hybrid mode, check whether it reproduces in shadow mode (behavior bug) or only in hybrid mode (integration bug). Bundle format is unchanged — consumer code (viewer, narrator, analytics) doesn't know whether stats came from agents or aggregates. Agent-specific data (snapshots, named characters) is added as optional fields in the bundle; absent when running in aggregate mode.

### Testing Strategy

| Level | What | Where |
|-------|------|-------|
| Unit | Individual agent decisions, satisfaction formula, demographic rates | `chronicler-agents/tests/` |
| Integration | Rust ↔ Python Arrow bridge, aggregate computation, signal parsing | `tests/test_agent_bridge.py` |
| Shadow | Agent distributions vs aggregate distributions (M26) | `tests/test_shadow_oracle.py` |
| Oracle gate | 200-seed full validation (M28) | `scripts/run_oracle_gate.py` |
| Performance | Criterion benchmarks, scaling analysis (M29) | `chronicler-agents/benches/` |
| Narrative | Named character presence in chronicles (M30) | `tests/test_agent_narrative.py` |
| Regression | `--agents` off produces identical output to Phase 4 | `tests/test_regression.py` |

### Migration Path

```
M25: Rust crate exists. Python simulation unchanged. Agents can be created and ticked (age+die).
M26: Agents make decisions. Shadow mode: both models run, compare, discard agent stats.
     Shadow oracle comparison identifies behavior-model issues early.
M27: Hybrid mode: agent stats drive civ stats. Python phases still handle politics/actions/ecology.
     Agent events appear in events_timeline.
M28: Oracle gate: 200-seed validation. Pass → agents are primary. Fail → iterate M26/M27.
M29: Performance optimization (can overlap with M27/M28).
M30: Agent narrative: named characters, agent events in chronicles.
M31: [DEFERRED] Agent tuning pass folded into Phase 6 M47 (full-system calibration).
Post-M30: Aggregate model retained as --no-agents fallback and test oracle.
```

---

## Estimated Effort

| Milestone | Estimated Days | Risk | Notes |
|-----------|---------------|------|-------|
| M25 | 3–5 | Low | Arrow FFI is well-documented; PyO3 + pyo3-arrow is a known pattern |
| M26 | 6–10 | Medium | Behavior tuning is iterative; shadow oracle adds scope but catches bugs early |
| M27 | 4–6 | Medium | Integration surface area is large; agent-mode guards across simulation.py |
| M28 | 1–2 | Low | Framework built in M26; this is just the full 200-seed run + report |
| M29 | 3–5 | Low–Medium | Profiling-driven; may overlap with M27/M28 |
| M30 | 4–6 | Medium | Narrative quality is subjective; named character system is mechanical |
| ~~M31~~ | — | — | Deferred to Phase 6 M47 |
| **Total** | **21–34** | | |

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agent model produces fundamentally different dynamics than aggregate | High | Shadow oracle in M26 catches this early; oracle gate in M28 provides formal checkpoint |
| Arrow FFI overhead dominates tick time | Medium | Benchmark in M25; fall back to raw numpy if Arrow > 1ms/tick |
| Rayon scheduling non-determinism | High | Region-index ordering + ChaCha8Rng stream splitting; verified by determinism test in M25 |
| Agent behavior tuning takes longer than aggregate tuning | Medium | Satisfaction formula has fewer free parameters than aggregate's ~250 constants; shadow oracle provides automated feedback |
| 10K agents × 200 seeds × 500 turns exceeds memory | Low | SoA at 48 bytes/agent × 10K = 480KB per run; 200 concurrent runs = 96MB. Negligible on 192GB |
| Named character system produces boring narratives | Medium | M30 deliverable includes narrative quality review; promotion thresholds are tunable |
| jemalloc unavailable on Windows | Low | cfg-gate with system allocator fallback; performance benchmarks run on WSL or Linux. Dev workflow on Windows uses system allocator (slower but functional) |
| PyO3 ABI mismatch | Medium | Pin Python version in project config; CI builds against the same version used in the venv |

---

## Phase 6 Considerations

Ideas evaluated during Phase 5 planning that were deferred as out-of-scope. Documented here so they aren't lost.

### Utility-Based Agent Decisions

Phase 5's decision model uses priority-ordered short-circuit (rebel → migrate → switch → drift). An alternative is weighted utility selection: each action computes a utility score, agent picks `argmax(utility + noise)`. This is more expressive than thresholds — a farmer near both the migration and rebellion thresholds would choose based on relative urgency rather than fixed priority. It also makes tuning more transparent (continuous weights vs threshold ordering). Deferred because: the short-circuit model is simpler to validate against the oracle (less behavioral variance → cleaner KS tests), and we haven't seen it run yet. If Phase 5's decision model produces flat or unrealistic dynamics, utility-based selection is the first upgrade to evaluate.

### Agent Personality

A fourth axis (bold, cautious, greedy) on top of occupation + satisfaction + loyalty. Deferred per Decision 3 — hard to tune, harder to validate. Revisit if narrative quality demands it after M30.

### Metamodel Validation

Building a surrogate model of the ABM and comparing response surfaces. State of the art in ABM validation literature but a significant investment. Better suited for a post-M28 quality pass if the standard statistical tests prove insufficient.

### Wasserstein Distance for Multivariate Validation

Earth mover's distance for comparing multivariate distributions. More informative than independent univariate tests but medium effort. Consider if correlation structure checks (added in Phase 5) prove too coarse.
