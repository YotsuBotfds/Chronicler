# M27: System Integration — Spec Notes

**Date:** 2026-03-16
**Status:** Pre-spec research (Phoebe codebase audit)
**Purpose:** Ground the M27 spec in a complete inventory of the integration surface. These notes catalog every direct stat mutation in `simulation.py` and its phase functions, classify each as guard/keep/signal for agent mode, and identify the shock propagation design needed for M27.

---

## Direct Stat Mutation Inventory

76 direct mutations across 14 files. Traced from `run_turn()` through every phase function.

### Phase 1: Environment (`phase_environment`)

| Line | Mutation | Category | Notes |
|------|----------|----------|-------|
| 136 | `civ.stability -= drain` (drought) | **Signal** | Becomes ecological stress signal to agents |
| 137 | `civ.economy -= 10 × mult` (drought) | **Signal** | Economy shock → agent satisfaction penalty |
| 150 | `distribute_pop_loss(regions, 10 × mult)` (plague) | **Guard** | Agent demographics handle population loss |
| 151 | `sync_civ_population(civ, world)` (plague) | **Guard** | Follows pop loss — guarded together |
| 152 | `civ.stability -= drain` (plague) | **Signal** | Health crisis signal to agents |
| 165 | `civ.economy -= 10 × mult` (earthquake) | **Signal** | Infrastructure damage signal |

**Climate disasters** (`check_disasters` in climate.py):
- Wildfire: `region.forest_cover -= damage` — **Keep** (ecology, not civ stat)
- Flood: `drain_region_pop(region, loss)` — **Guard** (agent demographics)
- Volcano: `drain_region_pop`, `civ.stability -=`, `civ.economy -=` — **Signal** (black swan)
- Pandemic: `distribute_pop_loss`, `civ.stability -=`, `civ.economy -=` — **Guard** pop, **Signal** rest

**Climate migration** (`process_migration` in climate.py):
- `drain_region_pop(source, migrants)` — **Keep** (forced displacement — agents observe as region signal)
- `add_region_pop(target, migrants)` — **Keep** (same)

### Phase 2: Automatic Effects (`apply_automatic_effects`)

| Line | Mutation | Category | Notes |
|------|----------|----------|-------|
| 192 | `civ.treasury -= cost` (military maintenance) | **Keep** | Treasury stays Python-side |
| 200 | `a.treasury += 2` (trade income) | **Keep** | Treasury |
| 202 | `b.treasury += 2` (trade income) | **Keep** | Treasury |
| 206 | `c.treasury += 3` (self-trade) | **Keep** | Treasury |
| 238 | `civ.treasury += bonus` (specialization) | **Keep** | Treasury |
| 239 | `civ.treasury -= penalty` (embargo spec.) | **Keep** | Treasury |
| 256 | `civ.treasury += 1` (black market) | **Keep** | Treasury |
| 257 | `civ.stability -= 3` (black market) | **Signal** | Corruption signal |
| 266 | `c.treasury -= 3` (war costs) | **Keep** | Treasury |
| 269 | `c.stability -= drain` (war bankruptcy) | **Signal** | Economic collapse signal |
| 282 | `civ.military -= strength` (merc spawn) | **Guard** | Agent soldier counts replace military stat |
| 310 | `hirer.military += merc.strength` (merc hire) | **Guard** | Same |
| 309 | `hirer.treasury -= 10` (merc hire cost) | **Keep** | Treasury |

**Politics sub-functions** (called from Phase 2):
- `apply_governing_costs`: `treasury -=`, `stability -=` — **Keep** treasury, **Signal** stability
- `collect_tribute`: `treasury +=/-` — **Keep**
- `apply_proxy_wars`: `treasury -=`, `stability -=`, `economy -=` — **Keep** treasury, **Signal** rest
- `apply_exile_effects`: `stability -=` — **Signal**
- `apply_twilight`: `culture -= 2` — **Guard** (agent culture score replaces)
- `apply_long_peace`: `stability -=`, `economy +=/-` — **Signal** stability, **Guard** economy

### Phase 3: Production (`phase_production`)

| Line | Mutation | Category | Notes |
|------|----------|----------|-------|
| 380 | `civ.treasury += income - penalty` | **Keep** | Treasury |
| 395 | `add_region_pop(r, per_region)` (growth) | **Guard** | Agent fertility handles growth |
| 396 | `sync_civ_population(civ, world)` | **Guard** | Follows pop growth |
| 400 | `drain_region_pop(target, 5)` (instability decline) | **Guard** | Agent mortality handles decline |
| 401 | `sync_civ_population(civ, world)` | **Guard** | Follows pop drain |
| 406 | `add_region_pop(r, 3)` (passive repop) | **Guard** | Agent fertility handles repopulation |
| 407 | `sync_civ_population(civ, world)` | **Guard** | Follows repop |
| 417 | `civ.treasury += mine_count × 2` (mechanization) | **Keep** | Treasury |
| 433 | `civ.stability += recovery` | **Guard** | Agent satisfaction × loyalty replaces stability |

### Phase 4: Technology (`phase_technology`)

No direct stat mutations. Tech advancement modifies `civ.tech_era` and `civ.active_focus` (structural, not stats). Focus effects may modify stats indirectly via `apply_focus_effects` — needs audit of `tech_focus.py` during spec writing.

### Phase 5: Action (`phase_action`)

| Line | Mutation | Category | Notes |
|------|----------|----------|-------|
| 459 | `resolve_action(civ, action, world)` | **Mixed** | Entire action engine. See below. |
| 468 | `setattr(civ, stat, halved)` (crisis halving) | **Guard** | Only if underlying stat was guarded |

**`resolve_action`** (action_engine.py) is the largest single integration surface. Each action type produces stat modifications:

| Action | Stats Modified | Category |
|--------|---------------|----------|
| `EXPAND_TERRITORY` | military -, treasury - | **Guard** mil, **Keep** treasury |
| `BUILD_INFRASTRUCTURE` | economy +, treasury - | **Guard** eco, **Keep** treasury |
| `INVEST_CULTURE` | culture +, treasury - | **Guard** culture, **Keep** treasury |
| `RAISE_MILITARY` | military +, treasury - | **Guard** mil, **Keep** treasury |
| `DIPLOMATIC_MARRIAGE` | stability + | **Guard** stability |
| `RELIGIOUS_CAMPAIGN` | culture +, stability ± | **Guard** both |
| `TRADE_AGREEMENT` | economy +, treasury + | **Guard** eco, **Keep** treasury |
| `ESPIONAGE` | target.stability -, target.military - | **Guard** both |
| `FORTIFY` | military + | **Guard** |
| `WAGE_WAR` | military ±, treasury -, economy ± | **Guard** mil/eco, **Keep** treasury |

### Phase 6: Cultural Milestones (`phase_cultural_milestones`)

| Line | Mutation | Category | Notes |
|------|----------|----------|-------|
| 849 | `civ.asabiya += 0.05` | **Keep** | Asabiya is not agent-derived |
| 850 | `civ.culture += 5` | **Guard** | Agent culture score replaces |
| 851 | `civ.prestige += 2` | **Keep** | Prestige is not agent-derived |

### Phase 7: Random Events (`_apply_event_effects`)

| Event | Stats Modified | Category |
|-------|---------------|----------|
| `leader_death` | stability - | **Signal** |
| `rebellion` | stability -, military - | **Guard** mil, **Signal** stability |
| `discovery` | culture +10, economy +10 | **Guard** both |
| `religious_movement` | culture +10, stability - | **Guard** culture, **Signal** stability |
| `cultural_renaissance` | culture +20, stability +10 | **Guard** both |
| `migration` | `add_region_pop` +10, stability - | **Guard** pop, **Signal** stability |
| `border_incident` | stability - | **Signal** |

### Phase 9: Ecology (`tick_ecology`)

No direct civ stat mutations. Modifies `region.soil`, `region.water`, `region.forest_cover`, `region.population` (via famine). Famine events produce `drain_region_pop` calls — **Guard** in agent mode.

### Phase 10: Consequences (`phase_consequences`)

| Line | Mutation | Category | Notes |
|------|----------|----------|-------|
| 674 | `civ.stability -= drain` (conditions) | **Signal** | Ongoing condition effects |
| 715 | `civ.military //= 2` (collapse) | **Guard** | Agent loyalty cascade replaces |
| 716 | `civ.economy //= 2` (collapse) | **Guard** | Same |

**Politics sub-functions** (called from Phase 10):
- `check_capital_loss`: `stability -= 20` — **Signal**
- `check_secession`: `military -=`, `economy -=`, `treasury -=`, `stability -=` — **Guard** mil/eco, **Keep** treasury, **Signal** stability
- `check_vassal_rebellion`: `stability += 10` — **Guard**
- `check_federation_dissolution`: `stability -= 15` — **Signal**
- `check_congress`: `stability -= 5` — **Signal**

---

## Classification Summary

| Category | Count | Rule |
|----------|-------|------|
| **Guard** | ~38 | Agent model produces this stat emergently. Skip in agent mode. |
| **Signal** | ~22 | External shock. Keep the event, convert stat drain to agent signal. |
| **Keep** | ~16 | Treasury or structural. Agents don't model this. Run unchanged. |

---

## Shock Propagation Design

The 22 **Signal** mutations need a new mechanism. Currently: drought fires → `civ.stability -= 3`. In agent mode: drought fires → agents receive a signal → satisfaction drops → stability emerges lower.

### Proposed: `ShockSignals` Extension to `TickSignals`

```rust
pub struct ShockSignals {
    pub per_civ: Vec<CivShock>,
}

pub struct CivShock {
    pub civ_id: u8,
    pub stability_shock: f32,    // -1.0 to 0.0, applied as satisfaction penalty
    pub economy_shock: f32,      // -1.0 to 0.0, applied as merchant satisfaction penalty
    pub military_shock: f32,     // -1.0 to 0.0, applied as soldier satisfaction penalty
    pub culture_shock: f32,      // -1.0 to 0.0, applied as scholar/priest satisfaction penalty
}
```

Python builds `ShockSignals` by accumulating all **Signal**-category mutations during Phases 1–9 as normalized shock values instead of direct stat writes. The satisfaction formula adds a `shock_penalty` term:

```rust
let shock_pen = match occupation {
    0 => shock.economy_shock * 0.3 + shock.stability_shock * 0.2,  // Farmer
    1 => shock.military_shock * 0.3 + shock.stability_shock * 0.2, // Soldier
    2 => shock.economy_shock * 0.4 + shock.stability_shock * 0.1,  // Merchant
    3 => shock.culture_shock * 0.3 + shock.stability_shock * 0.2,  // Scholar
    _ => shock.stability_shock * 0.4,                               // Priest
};
```

This preserves the event's impact without bypassing the agent model. A drought that would have drained 3 stability becomes a satisfaction penalty that causes agents to become dissatisfied → stability drops emergently. The magnitude is tunable per-occupation.

### Open Question: Timing

Shocks accumulate during Phases 1–9. The Rust tick runs between Phase 9 and Phase 10. Shocks from Phase 10 (consequences) are *not* available until the *next* turn's tick. This is consistent with M25/M26's architecture — the Rust tick reads signals from the current turn's Phases 1–9 and doesn't see Phase 10 outcomes until next turn.

Phase 10's stat mutations that are classified as **Signal** (ongoing conditions, capital loss, federation dissolution) will naturally lag by one turn in agent mode. This is acceptable — a drought's second-turn drain reaches agents one turn later than it would in aggregate mode, but the magnitude is similar.

---

## Guard Implementation Strategy

Two approaches:

### Option A: Per-Mutation Guards

```python
if not world.agent_mode:
    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
```

38 guard statements. Invasive, hard to audit for completeness, mixes agent-mode logic into every phase.

### Option B: Stat Accumulator Pattern

```python
# Before Phases 1–9:
stat_changes = StatAccumulator()

# In each phase:
stat_changes.add(civ, "stability", -drain)  # instead of direct mutation

# After Phase 9, before Rust tick:
if world.agent_mode:
    shock_signals = stat_changes.to_shock_signals()  # convert to agent signals
else:
    stat_changes.apply(world)  # apply as direct mutations
```

Centralizes the guard logic. Each phase writes to the accumulator instead of directly mutating stats. The accumulator either applies changes (aggregate mode) or converts to shock signals (agent mode). Requires refactoring all 38 guard-category mutations to use the accumulator — significant but clean.

**Recommendation: Option B.** It's more work upfront but eliminates the risk of missing a guard. It also gives shadow mode a free comparison point — the accumulator captures what the aggregate model *would have done*, which the oracle can compare against what agents *actually did*.

---

## Action Engine Integration

`resolve_action` in `action_engine.py` is the most complex integration point. Each of the ~12 action types produces a different combination of stat changes. In agent mode, the action engine needs to:

1. **Still select actions** — the action engine's *selection* logic (which action a civ takes) should remain unchanged. The civ's stats that feed selection are now agent-derived, but the selection algorithm doesn't care about the source.

2. **Convert action *outcomes* to signals** — instead of `civ.military += 10` for RAISE_MILITARY, the action produces a signal that agents interpret. For military: more agents switch to soldier occupation. For economy: merchant satisfaction increases. This is the hardest part of M27 — each action type needs an agent-mode signal translation.

3. **Keep treasury effects** — all treasury mutations in action outcomes stay. Treasury is Python-side.

This needs a per-action-type mapping table in the M27 spec.

---

## Files That Need Modification in M27

| File | Changes |
|------|---------|
| `simulation.py` | StatAccumulator wiring, shock signal construction |
| `action_engine.py` | StatAccumulator integration for all action types |
| `politics.py` | StatAccumulator for 9 functions (21 mutations) |
| `climate.py` | Guard population drains, convert shocks to signals |
| `ecology.py` | Guard famine population drains |
| `emergence.py` | Guard black swan stat effects |
| `agent_bridge.py` | Accept ShockSignals, extend `build_signals` |
| `ffi.rs` | Parse ShockSignals RecordBatch |
| `signals.rs` | Add CivShock struct and parsing |
| `satisfaction.rs` | Add shock_penalty term |
| `tick.rs` | Thread ShockSignals through tick pipeline |
