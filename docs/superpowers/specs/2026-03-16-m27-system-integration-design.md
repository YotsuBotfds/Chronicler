# M27: System Integration — Design Spec

**Date:** 2026-03-16
**Status:** Draft
**Prerequisites:** M26 Agent Behavior + Shadow Oracle (complete, merged)
**Estimated size:** ~200 Rust, ~500 Python
**Phase:** 5 (Agent-Based Population Model) — third milestone

## Overview

Wire agent-derived stats into the Python turn loop, enabling **hybrid mode** (`--agents=hybrid`). Agent behavior produces emergent civ-level stats that replace the aggregate model's direct stat mutations. The aggregate model remains available as `--agents=off` (default), bit-identical to pre-M27 output.

M27 does not run the full oracle gate validation (M28), does not optimize for scale (M29), and does not add named characters or narrative enrichment (M30).

### Design Principles

1. **StatAccumulator as a batch boundary.** All 76 stat mutations across Phases 1-9 route through a central accumulator. In aggregate mode, the accumulator applies changes directly (bit-identical). In agent mode, it routes changes by classification: guard → skip, guard-action → demand signal, guard-shock → positive/negative shock, signal → shock, keep → apply directly. This replaces 60+ scattered `if not world.agent_mode` guards with a single routing point.

2. **Python tells Rust what happened. Rust decides what it means.** Signals from Python to Rust are declarative (shock magnitudes, demand shifts). Rust interprets them through the existing satisfaction/decision/demographics pipeline. Python never distributes civ-wide effects across regions — that's the Rust tick's job.

3. **One-turn lag for Phase 10 is architecturally clean.** Phase 10 (consequences) runs after the Rust tick. Its signal-category mutations become `pending_shocks` that agents react to next turn. This matches the existing M25/M26 architecture where the Rust tick reads Phases 1-9 signals and doesn't see Phase 10 until next turn.

4. **Two-tier agent events.** Raw agent events (telemetry) stored separately from summary events (narrative). The narrator sees threshold-aggregated summaries; analytics can drill into raw data.

### Design Decisions

**DIPLOMACY asymmetry.** In aggregate mode, DIPLOMACY produces no stat change — only disposition shifts. In agent mode, agents have no direct awareness of disposition. A +0.05 normalized stability shock provides a minimal satisfaction signal so that diplomatic actions have observable population-level effects. This is a deliberate asymmetry accepted because: (a) the bit-identical regression test covers `--agents=off` only, (b) the magnitude is small enough that it won't distort the oracle baseline, and (c) without it, DIPLOMACY would be invisible to the agent model.

**Collapse as catastrophic shock, not direct agent manipulation.** When Phase 10 triggers civ collapse (`military //= 2`, `economy //= 2`), hybrid mode emits a -0.5 shock on military and economy rather than directly killing or demoting agents. The collapse manifests as a 2-3 turn rapid decline through satisfaction crash, which is more realistic and keeps all agent state changes flowing through the normal decision pipeline.

---

## Architecture

```
Python turn loop:
  Phases 1-9 --> StatAccumulator (captures all 76 stat mutations)
                      |
                      +-- aggregate mode: apply all directly (bit-identical)
                      |
                      +-- agent mode: route by classification
                           |
                           +-- Keep (16): apply directly (treasury, asabiya, prestige)
                           +-- Guard (24): skip entirely (agents produce emergently)
                           +-- Guard-action (5-6): --> DemandSignals
                           |                          (via STAT_TO_OCCUPATION mapping)
                           +-- Guard-shock (~6): --> ShockSignals (positive/negative)
                           +-- Signal (22): -------> ShockSignals (normalized to +/-1.0)
                                                     + pending_shocks from last turn
                                                          |
                   -- Rust agent tick ----------------------+
                   Input:  TickSignals (civ_signals extended with shocks + demand shifts)
                   Output: aggregates RecordBatch + events RecordBatch
                   -----------------------------------------
                                                          |
                   Write-back: overwrite 5 civ fields     |
                   Event aggregation: threshold -> timeline|
                                                          v
  Phase 10 --> reads agent-derived values
               ~5 inline guards --> pending_shocks for next turn
```

---

## StatAccumulator

Replaces all 76 direct stat mutations across Phases 1-9. Each phase writes to the accumulator instead of mutating `civ` fields directly.

### Data Structures

```python
@dataclass(slots=True)
class StatChange:
    civ_id: int
    stat: str
    delta: float
    category: str      # "guard", "guard-action", "guard-shock", "signal", "keep"
    stat_at_time: float  # stat value when mutation was recorded

class StatAccumulator:
    def __init__(self):
        self._changes: list[StatChange] = []

    def add(self, civ_idx: int, civ: Civilization, stat: str, delta: float, category: str):
        """Record a stat mutation. civ_idx is the index into world.civilizations."""
        self._changes.append(StatChange(
            civ_idx, stat, delta, category, getattr(civ, stat, 0)
        ))

    def apply(self, world: WorldState) -> None:
        """Aggregate mode: apply all changes directly, in insertion order. Bit-identical."""
        for c in self._changes:
            civ = world.civilizations[c.civ_id]
            current = getattr(civ, c.stat)
            setattr(civ, c.stat, clamp(current + c.delta, STAT_FLOOR.get(c.stat, 0), 100))

    def apply_keep(self, world: WorldState) -> None:
        """Agent mode: apply only keep-category changes (treasury, asabiya, prestige)."""
        for c in self._changes:
            if c.category != "keep":
                continue
            civ = world.civilizations[c.civ_id]
            current = getattr(civ, c.stat)
            setattr(civ, c.stat, clamp(current + c.delta, STAT_FLOOR.get(c.stat, 0), 100))

    def to_shock_signals(self) -> list[CivShock]:
        """Agent mode: convert signal + guard-shock changes to normalized shocks."""
        shocks: dict[int, CivShock] = {}
        for c in self._changes:
            if c.category not in ("signal", "guard-shock"):
                continue
            shock = shocks.setdefault(c.civ_id, CivShock(c.civ_id))
            field = STAT_TO_SHOCK_FIELD[c.stat]
            current_shock = getattr(shock, field)
            normalized = c.delta / max(c.stat_at_time, 1)
            setattr(shock, field, clamp(current_shock + normalized, -1.0, 1.0))
        return list(shocks.values())

    def to_demand_signals(self, civ_capacities: dict[int, int]) -> list[DemandSignal]:
        """Agent mode: convert guard-action changes to demand signals."""
        signals = []
        for c in self._changes:
            if c.category != "guard-action" or c.stat not in STAT_TO_OCCUPATION:
                continue
            occupation = STAT_TO_OCCUPATION[c.stat]
            capacity = max(civ_capacities.get(c.civ_id, 1), 1)
            magnitude = c.delta / capacity * DEMAND_SCALE_FACTOR
            signals.append(DemandSignal(c.civ_id, occupation, magnitude, duration=3))
        return signals
```

### Key Properties

- **Bit-identical pass-through:** `apply()` processes changes in insertion order, matching the original mutation sequence exactly.
- **`stat_at_time` capture:** each `add()` records the stat's value at mutation time, so relative shock normalization uses the correct denominator even when multiple shocks hit the same stat in one turn.
- **Category is set at the call site:** each mutation's classification is written once in the code and doesn't change between modes. The accumulator routes by category only at the end.

### Category Classification

| Category | Count | Rule | Agent-Mode Routing |
|----------|-------|------|--------------------|
| **keep** | ~16 | Treasury, asabiya, prestige. Agents don't model this. | Apply directly |
| **guard** | ~24 | Passive mechanics. Agents produce emergently. | Skip |
| **guard-action** | 5-6 | Action engine policy outcomes (DEVELOP, EXPAND, WAR). | Convert to DemandSignal |
| **guard-shock** | ~6 | Windfalls and external events (discovery, cultural_renaissance). | Convert to ShockSignal |
| **signal** | ~22 | External shocks (drought, earthquake, war bankruptcy). | Convert to ShockSignal |

### Constant Maps

```python
STAT_TO_OCCUPATION = {
    "military": 1,   # Soldier
    "economy": 2,    # Merchant
    "culture": 3,    # Scholar
}

STAT_TO_SHOCK_FIELD = {
    "stability": "stability_shock",
    "economy": "economy_shock",
    "military": "military_shock",
    "culture": "culture_shock",
}

DEMAND_SCALE_FACTOR = 1.0  # Single tuning constant, calibrate against shadow oracle
```

### Usage in `run_turn`

```python
def run_turn(world, ..., agent_bridge=None):
    acc = StatAccumulator()

    phase_environment(world, seed=seed, acc=acc)
    check_black_swans(world, seed=seed, acc=acc)
    apply_automatic_effects(world, acc=acc)
    phase_production(world, acc=acc)
    phase_technology(world, acc=acc)
    phase_action(world, action_selector=action_selector, acc=acc)
    phase_cultural_milestones(world, acc=acc)
    phase_random_events(world, seed=seed + 100, acc=acc)
    phase_leader_dynamics(world, seed=seed, acc=acc)
    tick_ecology(world, climate_phase, acc=acc)

    if world.agent_mode == "hybrid":
        acc.apply_keep(world)
        shocks = acc.to_shock_signals()
        demands = acc.to_demand_signals(get_civ_capacities(world))
        shocks.extend(world.pending_shocks)
        world.pending_shocks.clear()
        agent_bridge.tick(world, shocks=shocks, demands=demands)
        # write-back handled inside agent_bridge.tick()
    else:
        acc.apply(world)

    phase_consequences(world)
    # ... rest of turn
```

### Performance

The accumulator adds one function call + dataclass construction per stat mutation. ~76 mutations/turn x 500 turns = ~38,000 extra calls. Python overhead: ~8-38us per turn (0.1-0.5us per call). Negligible compared to phase function execution (milliseconds) or narration (seconds).

**Performance gate:** measure with `--simulate-only` (no narration), 500 turns, 5 runs, compare medians. If >5% wall-clock overhead, implement fast-path elision when `agent_bridge is None`.

---

## ShockSignals

Combines signal-category mutations (22), guard-shock mutations (~6), and `pending_shocks` from last turn's Phase 10 into per-civ shock values.

### Data Structure

```python
@dataclass
class CivShock:
    civ_id: int
    stability_shock: float = 0.0
    economy_shock: float = 0.0
    military_shock: float = 0.0
    culture_shock: float = 0.0
```

**Range:** [-1.0, +1.0]. Positive shocks (diplomatic marriage, discovery windfalls) boost satisfaction. Negative shocks (drought, war costs) reduce it.

### Normalization

`shock = delta / max(current_stat, 1)`, clamped to [-1.0, +1.0].

Examples:
- `stability -= 20` when stability is 80 -> shock = -0.25
- `stability -= 20` when stability is 20 -> shock = -1.0 (fragile civ feels it more)
- `culture += 10` when culture is 50 -> shock = +0.20

### Rust-Side: Satisfaction Penalty

`satisfaction.rs` adds a `shock_pen` term using general + specific pattern:

```rust
/// All occupations get baseline sensitivity to all shocks,
/// plus stronger reaction to their domain shock.
let general = shock.stability_shock * 0.15
            + shock.economy_shock * 0.05
            + shock.military_shock * 0.05
            + shock.culture_shock * 0.05;

let specific = match occupation {
    0 => shock.economy_shock * 0.20,    // Farmer: economy-sensitive
    1 => shock.military_shock * 0.20,   // Soldier: military-sensitive
    2 => shock.economy_shock * 0.30,    // Merchant: strongly economy-sensitive
    3 => shock.culture_shock * 0.20,    // Scholar: culture-sensitive
    _ => shock.stability_shock * 0.20,  // Priest: stability-sensitive
};

let shock_pen = general + specific;
// Added to M26's satisfaction formula after existing terms
```

This creates civ-wide satisfaction ripples from any shock, with occupation-specific amplification. Total weight per occupation: 0.45-0.55 depending on which shocks are active.

### FFI

Four new Float32 columns on `civ_signals` RecordBatch:

| Column | Arrow Type | Default |
|--------|-----------|---------|
| `shock_stability` | `Float32` | 0.0 |
| `shock_economy` | `Float32` | 0.0 |
| `shock_military` | `Float32` | 0.0 |
| `shock_culture` | `Float32` | 0.0 |

Python pre-sums all shock sources (signal mutations + guard-shock mutations + pending_shocks) before building the RecordBatch. Rust doesn't need to know the source.

---

## DemandSignals

Derived from guard-action mutations only (action engine policy outcomes). 3-turn linear decay managed Python-side.

### Data Structures

```python
@dataclass
class DemandSignal:
    civ_id: int
    occupation: int     # 0=farmer, 1=soldier, 2=merchant, 3=scholar, 4=priest
    magnitude: float    # initial magnitude from accumulator
    turns_remaining: int  # starts at 3, decremented each turn

class DemandSignalManager:
    def __init__(self):
        self.active: list[DemandSignal] = []

    def add(self, signal: DemandSignal) -> None:
        self.active.append(signal)

    def tick(self) -> dict[int, list[float]]:
        """Decay active signals, aggregate per-civ, return {civ_id: [5 demand shifts]}."""
        per_civ: dict[int, list[float]] = {}
        surviving = []
        for s in self.active:
            effective = s.magnitude * (s.turns_remaining / 3)
            shifts = per_civ.setdefault(s.civ_id, [0.0] * 5)
            shifts[s.occupation] += effective
            s.turns_remaining -= 1
            if s.turns_remaining > 0:
                surviving.append(s)
        self.active = surviving
        return per_civ

    def reset(self) -> None:
        """Clear for batch mode reuse."""
        self.active.clear()
```

### Decay Behavior

Signal is active for 3 turns. Effective magnitude on turn T after creation: `magnitude * (3 - T) / 3` where T in {0, 1, 2}. Total delivered impulse: `2 * magnitude`.

### Magnitude Calibration

`magnitude = delta / max(civ_capacity, 1) * DEMAND_SCALE_FACTOR`

The accumulator captures what the aggregate model would have done. Magnitude is normalized by carrying capacity so the same policy action means more in a smaller society.

**Sanity check:** `DEVELOP` with `economy += 10`, civ capacity 60 -> magnitude = 10/60 * 1.0 = 0.17. Turn 1: merchant ratio goes from 0.10 to ~0.20 after re-normalization. Tapers over 3 turns.

### FFI

Five new Float32 columns on `civ_signals` RecordBatch:

| Column | Arrow Type | Default |
|--------|-----------|---------|
| `demand_shift_farmer` | `Float32` | 0.0 |
| `demand_shift_soldier` | `Float32` | 0.0 |
| `demand_shift_merchant` | `Float32` | 0.0 |
| `demand_shift_scholar` | `Float32` | 0.0 |
| `demand_shift_priest` | `Float32` | 0.0 |

Python passes already-decayed effective values each turn. Rust sees flat numbers.

### Rust-Side: Ratio Adjustment

`target_occupation_ratio` in `satisfaction.rs` takes the civ's demand shift array:

```rust
fn target_occupation_ratio(terrain: u8, soil: f32, water: f32, demand_shifts: [f32; 5]) -> [f32; 5] {
    let mut ratios = base_ratios(terrain, soil, water);
    for i in 0..5 {
        ratios[i] = (ratios[i] + demand_shifts[i]).max(0.01); // floor at 1%
    }
    let sum: f32 = ratios.iter().sum();
    for r in &mut ratios { *r /= sum; }
    ratios
}
```

The 0.01 floor prevents zero demand, avoiding division issues in the demand/supply ratio computation.

---

## Action-to-Signal Mapping Table

Based on actual `ActionType` enum (`models.py:65-76`) and code audit of each handler.

### Guard-Action (DemandSignal)

| ActionType | Handler | Stat Mutations | Target Occupation |
|-----------|---------|---------------|-------------------|
| `DEVELOP` | `action_engine.py:77-96` | economy +10 OR culture +10 (with factor) | Merchant (if economy) or Scholar (if culture) |
| `EXPAND` | `action_engine.py:99-128` | military -10 (on success) | Soldier (negative — troops deployed) |
| `WAR` | `resolve_war:356-451` | See per-outcome table below | Soldier (negative — casualties, both sides) |

**WAR per-outcome signals:**

| Outcome | Attacker | Defender |
|---------|----------|----------|
| Attacker wins | military -10 (guard-action) | military -20 (guard-action), stability -10 (signal) |
| Defender wins | military -20 (guard-action), stability -10 (signal) | military -10 (guard-action) |
| Stalemate | military -10 (guard-action) | military -10 (guard-action) |

All outcomes: attacker treasury -20 (keep), defender treasury -10 (keep).

### Signal (ShockSignal)

| ActionType | Handler | Stat Mutation | Shock Field |
|-----------|---------|--------------|-------------|
| `WAR` (loser) | `resolve_war` | stability -10 | `stability_shock` |
| `EMBARGO` | `action_engine.py:295-328` | target stability -2 or -5 | `stability_shock` (target civ) |

### Keep / Structural (no agent signal)

| ActionType | Handler | Notes |
|-----------|---------|-------|
| `TRADE` | `action_engine.py:131-152` | Treasury only (keep) |
| `DIPLOMACY` | `action_engine.py:155-198` | Disposition change only (structural). See Design Decisions: DIPLOMACY asymmetry. |
| `BUILD` | `infrastructure.py:127-175` | Treasury + infrastructure placement. Indirect effects via later phases. |
| `MOVE_CAPITAL` | `politics.py:53-84` | Treasury + structural. Creates `ActiveCondition` — drain via Phase 10 conditions (already classified). |
| `FUND_INSTABILITY` | `politics.py:1134-1174` | Treasury + creates `ProxyWar`. Drain via Phase 2 `apply_proxy_wars` (already classified). |
| `INVEST_CULTURE` | `culture.py:139-198` | Treasury + cultural projection. Agent loyalty drift handles assimilation. |
| `EXPLORE` | `exploration.py:73-112` | Treasury + fog of war reveal. No stat mutation. |

---

## Write-Back

After the Rust tick, before Phase 10, agent aggregates overwrite civ and region state.

```python
def _write_back(self, world: WorldState) -> None:
    """Write agent-derived stats to civ and region objects."""
    aggs = self._sim.get_aggregates()
    region_pops = self._sim.get_region_populations()

    # Region populations from agent counts — no clamp in hybrid mode.
    # Agent behavior (migration, mortality from overcrowding) is the population regulator.
    pop_map = dict(zip(
        region_pops.column("region_id").to_pylist(),
        region_pops.column("alive_count").to_pylist(),
    ))
    for i, region in enumerate(world.regions):
        agent_pop = pop_map.get(i, 0)
        if agent_pop > region.carrying_capacity * 2.0:
            logger.warning(f"Region {i} pop {agent_pop} exceeds 2x capacity {region.carrying_capacity}")
        region.population = agent_pop

    # Civ stats from aggregates
    civ_ids = aggs.column("civ_id").to_pylist()
    for i, civ_id in enumerate(civ_ids):
        civ = world.civilizations[civ_id]
        civ.population = sum(world.regions[r].population for r in civ.regions)
        civ.military = aggs.column("military")[i].as_py()
        civ.economy = aggs.column("economy")[i].as_py()
        civ.culture = aggs.column("culture")[i].as_py()
        civ.stability = aggs.column("stability")[i].as_py()
```

Single function, single pass, no clamp, no population double-sync. `civ.population` derived from region populations (agent counts). Other four stats from `compute_aggregates` directly.

---

## Phase 10 Handling

The accumulator spans Phases 1-9 only. Phase 10 runs after the Rust tick against agent-derived values with inline guards.

### Decision Logic

`check_secession`, `check_vassal_rebellion`, `check_capital_loss`, etc. read `civ.stability`, `civ.military`, etc. — which are now agent-derived in hybrid mode. Correct behavior: these decisions should respond to what agents actually produced. No changes needed.

### Signal Mutations -> pending_shocks

```python
# check_capital_loss:
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(civ.id, stability_shock=normalize(-20, civ.stability)))
else:
    civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)

# check_federation_dissolution: stability -= 15 -> pending_shocks
# check_congress: stability -= 5 -> pending_shocks
# ongoing conditions: stability -= drain -> pending_shocks
```

### Collapse Guards -> Catastrophic Shock

```python
# Collapse (stability at floor + conditions):
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(civ.id, military_shock=-0.5, economy_shock=-0.5))
else:
    civ.military //= 2
    civ.economy //= 2
```

### pending_shocks Lifecycle

```python
# WorldState gains:
pending_shocks: list[CivShock] = field(default_factory=list)

# In run_turn, agent mode, before Rust tick:
shocks = acc.to_shock_signals()
shocks.extend(world.pending_shocks)   # fold in last turn's Phase 10
world.pending_shocks.clear()
```

**Total Phase 10 guards: ~5**, all in `simulation.py` + `politics.py`. Auditable by inspection.

---

## Agent Events Integration

Two-tier system. Raw events for analytics, threshold-aggregated summaries for narrative.

### Raw Storage

```python
@dataclass(slots=True)
class AgentEventRecord:
    turn: int
    agent_id: int
    event_type: str      # "death", "rebellion", "migration", "occupation_switch", "loyalty_flip", "birth"
    region: int
    target_region: int   # migration destination, 0 otherwise
    civ_affinity: int
    occupation: int      # 0-4, agent's occupation at time of event
```

`agent_bridge.tick()` converts the Arrow events RecordBatch to `AgentEventRecord` objects, appends to `world.agent_events_raw`. Bundle serialization writes them as a separate `agent_events` Arrow IPC file.

### M26 Schema Addition (Prerequisite)

M26's `AgentEvent` struct needs `occupation: u8` added before M26 implementation:

```rust
pub struct AgentEvent {
    pub agent_id: u32,
    pub event_type: u8,
    pub region: u16,
    pub target_region: u16,
    pub civ_affinity: u8,
    pub turn: u32,
    pub occupation: u8,  // NEW -- agent's occupation at time of event
}
```

### Summary Aggregation

`AgentBridge` holds a 10-turn sliding window (`deque`, bounded at 10 turns x ~300 events/turn, ~72KB) for multi-turn pattern detection. After each tick, applies threshold checks and emits summary `Event` objects into `events_timeline`:

| Pattern | Threshold | Event Type | Importance |
|---------|-----------|-----------|------------|
| Rebellion | >=5 agents in one region | `local_rebellion` | 7 |
| Mass migration | >=8 agents leave one region in one tick | `mass_migration` | 5 |
| Demographic crisis | Region loses >30% agents over 10 turns | `demographic_crisis` | 7 |
| Occupation shift | >25% of region switches occupation in one tick | `occupation_shift` | 5 |
| Loyalty cascade | >=10 agents flip civ_affinity in one region over 5 turns | `loyalty_cascade` | 6 |

Thresholds from M30's event table, pulled forward to M27 so M30 is a description upgrade, not a new system.

### Description Templates

```python
SUMMARY_TEMPLATES = {
    "mass_migration": "{count} {occ_majority} fled {source_region} for {target_region}",
    "local_rebellion": "Rebellion erupted in {region} as {count} discontented {occ_majority} rose up",
    "demographic_crisis": "{region} lost {pct}% of its population over {window} turns",
    "occupation_shift": "{count} agents in {region} switched to {new_occupation}",
    "loyalty_cascade": "{count} residents of {region} shifted allegiance to {target_civ}",
}
```

`occ_majority` computed via `Counter` over constituent events' `occupation` field.

### Model Change

`Event` gains one optional field:

```python
source: str = "aggregate"  # "aggregate" or "agent"
```

Curator doesn't special-case it — importance scoring handles priority. Analytics and M28 oracle can filter by source.

### Bridge Statefulness

`AgentBridge` is instantiated once per run. Instance state:
- Sliding window: `deque` of recent raw events (last 10 turns)
- `DemandSignalManager`: active demand signals with decay state

`reset()` clears both for batch-mode reuse.

---

## world.agent_mode Flag

`WorldState` gains an `agent_mode` field set from CLI `--agents` flag:

| Value | Behavior |
|-------|----------|
| `None` / `"off"` | Phase 4 aggregate. No accumulator routing, no bridge. `acc.apply()` runs. |
| `"demographics-only"` | M25 mode. Bridge ticks, clamps populations. `acc.apply()` runs (aggregate stats still drive). |
| `"shadow"` | M26 mode. Both models run, agent stats discarded. `acc.apply()` runs. |
| `"hybrid"` | M27 mode. `acc.apply_keep()` + signals + write-back. Agent stats drive civ fields. |

The accumulator routing (`apply_keep` + `to_shock_signals` + `to_demand_signals`) only activates when `agent_mode == "hybrid"`. All other modes use `acc.apply()` for bit-identical behavior.

---

## Files That Need Modification

### Python

| File | Changes |
|------|---------|
| `simulation.py` | `StatAccumulator` wiring in `run_turn`, `acc` parameter threading to all phase functions, Phase 10 inline guards (~5), `pending_shocks` lifecycle |
| `action_engine.py` | ~12 stat mutations routed through `acc.add()` with guard-action/signal/keep categories |
| `politics.py` | ~21 stat mutations routed through `acc.add()` across 9 functions |
| `climate.py` | ~6 stat mutations routed through `acc.add()`, population drains classified as guard |
| `ecology.py` | Famine population drains classified as guard |
| `emergence.py` | Black swan stat effects classified as guard-shock |
| `culture.py` | Cultural milestone stat effects classified as guard-shock |
| `agent_bridge.py` | `build_signals` extended (9 new columns), `_write_back`, event aggregation, `DemandSignalManager`, sliding window |
| `models.py` | `Event.source` field, `AgentEventRecord` dataclass, `CivShock` dataclass, `DemandSignal` dataclass, `StatChange` dataclass, `world.agent_mode` field, `world.pending_shocks` field, `world.agent_events_raw` field |
| `bundle.py` | Serialize `agent_events_raw` as Arrow IPC in bundle |

### Rust

| File | Changes |
|------|---------|
| `signals.rs` | Parse 9 new `civ_signals` columns (4 shock + 5 demand) |
| `satisfaction.rs` | Add `shock_pen` term (general + specific pattern), add `demand_shifts` parameter to `target_occupation_ratio` |
| `ffi.rs` | Accept extended `civ_signals` schema |
| `tick.rs` | Thread shock signals and demand shifts through tick pipeline |

---

## Testing Strategy

### Python Tests

**1. StatAccumulator bit-identical test.** 100-turn run with accumulator in aggregate mode (`acc.apply()`) vs. 100-turn run without accumulator (direct mutations). Compare every field on every `Civilization` object after each turn. Fail if any field differs.

**2. StatAccumulator routing test.** Known set of (civ, stat, delta, category) inputs. Verify `to_shock_signals()` only processes `signal` + `guard-shock`, `to_demand_signals()` only processes `guard-action`, `apply_keep()` only processes `keep`.

**3. Shock normalization test.** `stability -= 20` at stability 80 -> -0.25. At stability 20 -> -1.0. At stability 0 -> -1.0 (denominator guarded). Positive: `stability += 10` at stability 50 -> +0.20.

**4. DemandSignalManager test.** Add signal magnitude 0.17, duration 3. Three `tick()` calls -> 0.17, 0.113, 0.057. Fourth -> expired, empty.

**5. Write-back test.** Mock `compute_aggregates` RecordBatch. Call `_write_back`. Verify civ fields match, region populations match, no clamp applied.

**6. Event aggregation threshold test.** 10 migrations from same region in one tick -> `mass_migration` fires (>=8). 7 -> no summary. Template produces correct `occ_majority` and region names.

**7. Sliding window test.** Inject events over 12 turns -> window retains last 10. `loyalty_cascade` pattern (10 flips in one region over 5 turns) -> fires. Same 10 over 6 turns -> does not fire.

**8. Phase 10 guard test.** 20-turn hybrid run. Trigger capital loss. Verify `civ.stability` not mutated directly, `pending_shocks` contains shock, next turn's signals include it.

**9. Hybrid integration test.** 100-turn hybrid simulation with real WorldState and seed. Verify: valid bundle, no crashes, all civ stats in [0, 100], region populations > 0 for controlled regions, `agent_events_raw` populated, at least one summary event with `source="agent"`.

### Rust Tests

**10. Shock penalty unit test.** Known shock values + occupation -> verify general + specific penalty matches hand-computed values. All 5 occupations, non-zero shocks on all 4 channels.

**11. Demand shift ratio test.** `target_occupation_ratio` with `demand_shifts = [0, 0.17, 0, 0, 0]`. Verify soldier ratio increases, all ratios sum to 1.0, no ratio below 0.01.

**12. Extended signals parsing test.** Arrow RecordBatch with all 9 new columns. Verify parsed correctly. Test with zero values.

### Regression

**13. Aggregate mode regression.** `--agents=off` produces bit-identical output to pre-M27 code. Validates accumulator and `agent_mode` flag don't affect aggregate mode.

### Performance

**14. Accumulator overhead.** 500-turn `--simulate-only` run, 5 runs, compare medians before vs. after. If >5%, implement fast-path elision.

### Convergence Diagnostic

**15. Demand-to-aggregate convergence test.** Two 50-turn runs diverging at turn 25 with forced `WAR` action (richest single-action test: both demand signal via soldier casualties and shock signal via loser stability). Compare military and stability at turn 50 (25 turns after action). Agent-derived within +/-30% of aggregate. Calibration diagnostic, not pass/fail gate — catches gross `DEMAND_SCALE_FACTOR` miscalibration before M28's 200-seed oracle gate. If consistent undershoot, raise factor. If overshoot, lower.

---

## What This Milestone Does NOT Do

- **No 200-seed oracle validation** (M28) — comparison framework exists from M26; full gate runs in M28
- **No scale optimization** (M29) — no SIMD, no BitVec, no compaction. Agent count stays at 6K
- **No named characters or narrative enrichment** (M30) — summary events use templates. M30 adds character references
- **No new action types** — existing 11 types get signal translations where applicable
- **No changes to action selection logic** — `select_action` reads civ stats the same way; doesn't know whether they came from agents or aggregates
- **No changes to Rust decision model** — M26's satisfaction, behavior, demographics formulas unchanged. M27 adds shock penalty and demand shift inputs but doesn't tune thresholds or weights
- **No shadow-mode removal** — `--agents=shadow` continues to work. Hybrid mode is additive
- **No aggregate model removal** — `--agents=off` remains the default, bit-identical to pre-M27

## What M28 Will Build On

- Hybrid mode produces agent-derived stats that drive the full simulation
- `compute_aggregates` provides stat derivation validated against aggregate baseline
- Events RecordBatch provides rebellion/migration events merged into `events_timeline`
- Oracle framework (M26) runs against hybrid-mode output for 200-seed validation
- Demand-to-aggregate convergence diagnostic (test 15) provides early `DEMAND_SCALE_FACTOR` calibration
