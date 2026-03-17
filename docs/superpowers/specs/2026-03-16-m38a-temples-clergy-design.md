# M38a: Temples & Clergy Faction

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M37 (belief systems) for `civ_majority_faith`, conversion signals, belief registry. M36 (cultural identity) for penalty cap infrastructure and `is_named` bit. M35a/M35b (rivers, disease, depletion) for regional ecology context. M22 (faction succession) for faction candidate generation pattern.
>
> **Scope:** Temples as faith-bound infrastructure with conversion boost and prestige accumulation. Clergy as fourth political faction with event-driven influence, tithe mechanic, succession candidate, and action weight modifiers. ~33 lines Rust, ~205 lines Python, ~250 lines tests.

---

## Overview

M37 adds per-agent religious belief with event-driven conversion and doctrine-biased faiths. But religion has no institutional power — no buildings, no political faction, no economic lever. Priests convert agents but have no organizational structure. Faith spreads but doesn't accumulate political capital.

M38a adds the institutional layer. Temples are physical infrastructure that project faith (+50% conversion boost) and accumulate prestige. Clergy is a fourth political faction competing with military, merchant, and cultural for policy influence, succession candidates, and treasury allocation. Tithes give clergy an economic dimension — religious institutions derive power from the economy they serve, creating alliance-tension dynamics with the merchant faction.

**Design principle:** Temples are standard infrastructure following existing patterns. Clergy is event-driven following existing faction patterns. No new abstractions, no new Rust tick stages, no new action types. The complexity is in the 4th faction wiring (Arrow schema, normalization, satisfaction alignment, regression baseline), not in novel mechanics.

---

## Design Decisions

### Decision 1: Standard Infrastructure (Not Enhanced)

Temples are a new `InfrastructureType` following the existing BUILD/infrastructure pattern. Effects are passive modifiers on the region. No "sacred site" behavior, no pilgrimage mechanics, no faith-dominance influence.

**Why not enhanced:** M38b explicitly owns pilgrimages, with the dependency arrow pointing backward: "Destination: Highest-prestige temple region in their faith (requires M38a temples)." M38b reads temple data. M38a doesn't need to know pilgrimage mechanics exist. Adding sacred site behavior now pulls M38b's pilgrimage targeting forward before the schism and persecution systems that contextualize it.

**Data model foresight:** Temples carry `faith_id` and `temple_prestige` — inert in M38a, consumed by M38b. This avoids a retrofit migration.

### Decision 2: Faith-Bound Temples

Temples carry a `faith_id: int` set at build time (builder civ's `civ_majority_faith`). The +50% conversion boost applies only when the temple's faith matches the dominant converting faith. Prestige accumulates per-temple.

**Why not faith-blind:** A temple to the Sun God boosting Moon God conversion is incoherent. The guard clause (`if temple.faith_id == target_faith`) is one line in Python signal computation. M38b needs `faith_id` for pilgrimage targeting ("highest-prestige temple *of their faith*") — adding it now avoids retrofitting all M38a temples later.

**Conquered temples retain their original faith.** Foreign holy sites that resist cultural integration — narratively rich, strategically interesting. See Temple Conquest Lifecycle below.

### Decision 3: Event-Driven Clergy Influence

Clergy influence shifts via events in `tick_factions()`, matching the existing 3-faction pattern. The roadmap formula (`sum(priest_loyalty × priest_count) / total_civ_population`) describes the target correlation, not the M38a computation method. Agent-derived faction influence for all four factions is a candidate for M47 or Phase 7.

**Why not agent-derived:** Three momentum-based factions and one reactive faction normalize against each other every turn. The reactive one becomes the swing vote in every normalization because it moves faster than the others can respond. Agent-derived clergy influence is instantaneous — a plague that kills 60% of priests crashes clergy influence *that turn*, propagating through systems tuned for sluggish faction dynamics. Event-driven sourcing lets the 4th faction slot be validated in isolation. If the regression baseline fails, the cause is the slot, not a second influence-sourcing architecture.

**Migration path:** When agent-derived influence is desired, migrate all four factions at once. One milestone, one pattern change, one before/after comparison, no permanent asymmetry.

### Decision 4: Proxy Tithe from Trade Income

Tithes use `civ.trade_income` as the base until M41 adds agent wealth. `compute_tithe_base()` helper isolates the swap point.

**Why not defer tithes:** A faction without an economic dimension isn't a faction — it's a buff. The three existing factions each have economic levers (war spoils, trade income, INVEST_CULTURE spending). Clergy needs one to compete.

**Why not flat temple income:** Tithes mean clergy power derives from economic health — prosperous trade → fat tithes → strong clergy. This creates natural alliance-tension with merchants (both want trade to succeed, merchants resent the tax). Flat income means clergy revenue is independent of the economy. No alliance, no tension, no emergent dynamics.

**One treasury, four factions.** Tithes credit the civ's existing treasury. Clergy influence over spending comes from faction action weight modifiers, not a parallel purse.

### Decision 5: Clergy Nominates Own Succession Candidate

Same pattern as military/merchant/cultural. When `clergy_influence >= 0.15`, generate a priest-archetype candidate. No endorsement mechanic, no dual-threshold gating.

**Why not endorsement:** The existing three factions don't endorse each other's candidates — they compete. Endorsement requires scoring alignment between candidates and faith, coupling succession to the belief system. That coupling doesn't exist and shouldn't be introduced in M38a.

**Candidate traits reflect institutional character, not theology.** High loyalty trait, Tradition as primary cultural value, Order as secondary. The connection to the actual faith system is indirect — a civ with high clergy influence probably has lots of priests spreading their faith. The succession candidate reflects the institution's political character, not its doctrines.

### Decision 6: Temple Priest Satisfaction Bonus Is Faith-Blind

`has_temple: bool` on RegionState gives +0.10 to all priests in the region regardless of their faith. A minority-faith priest in a foreign temple gets the bonus.

**Known simplification.** At +0.10 affecting only minority-faith priests in templed regions, the impact is negligible. If M38b needs faith-specific temple support (e.g., persecution exemption for priests of the temple's faith), a second signal (`temple_faith_id: u8` on RegionState) should be added at that milestone.

### Decision 7: Majority-Faith Divergence Cascade Is Intentional

If a civ's `civ_majority_faith` diverges from a temple's `faith_id` (due to M37 conversion), the temple stops providing the priest satisfaction bonus (`has_temple` computed as `temple.faith_id == controller.civ_majority_faith`). This is intentional — institutional support requires political alignment. The cascade (lower satisfaction → fewer priests → lower clergy influence) is an emergent consequence.

---

## Temple Infrastructure

### Build Constraints

- Cost: `TEMPLE_BUILD_COST` = 10 treasury
- Build time: `TEMPLE_BUILD_TURNS` = 3 turns
- Max `MAX_TEMPLES_PER_REGION` = 1 per region
- Max `MAX_TEMPLES_PER_CIV` = 3 per civ `[CALIBRATE]`
- Built via existing BUILD action in Phase 5

### Temple Model

Temple data lives on the existing Infrastructure model (or subclass — implementation plan verifies compatibility):

```python
# On Infrastructure or Temple subclass:
faith_id: int = -1        # -1 = not a temple; ≥0 = belief registry index
temple_prestige: int = 0  # +1/turn, consumed by M38b pilgrimages
```

`faith_id` set at build time to builder civ's `civ_majority_faith`. Frozen after construction — does not track civ faith changes.

### Effects (Passive, Per-Turn While Active)

| Effect | Mechanism | Scope |
|--------|-----------|-------|
| +50% conversion rate | Multiplicative boost to `conversion_rate`, only when `temple.faith_id == conversion_target_belief` | Python signal computation |
| +0.10 priest satisfaction | `has_temple` bool on RegionState → Rust `satisfaction.rs` | Rust, faith-blind (Decision 6) |
| +1 prestige/turn on temple | `temple_prestige += 1` each turn | Python Phase 10, M38b consumer |
| +1 prestige/turn on civ | Existing civ prestige system | Python Phase 10 |

### Temple Conquest Lifecycle

| Scenario | Result |
|----------|--------|
| Militant holy war conquers templed region | Temple destroyed (named event, importance 5), slot open |
| Non-militant conquest of templed region | Temple survives, retains `faith_id`, old faith boosted |
| Conqueror BUILDs temple in region with foreign temple | Old temple destroyed (named event, importance 5), new one built |
| Conqueror leaves foreign temple | Old faith gets +50% conversion boost, prestige keeps ticking |

```python
# Temple conquest lifecycle:
if conquest and temple_exists:
    if attacker_militant and different_faith:
        destroy_temple(region)  # named event, importance 5

# Temple BUILD in occupied region:
if region.temple and region.temple.faith_id != builder_faith:
    destroy_temple(region)  # prerequisite destruction, named event
    build_temple(region, builder_faith)
```

Non-militant conquerors inherit the old temple. Strategic tension: destroy it (BUILD replacement) to remove conversion pressure, or leave it and accept the foreign faith boost. Destruction requires spending a BUILD action — opportunity cost, not free.

### BUILD Action Integration

Temple added to `infrastructure.handle_build()` with trait-weighted priority. Clergy-dominant civs prefer temples. Existing BUILD selection logic (region hash, trait priority, affordability check) applies unchanged.

---

## Fourth Faction: Clergy

### Normalization Change (3 → 4 Factions)

| Parameter | Old (3 factions) | New (4 factions) |
|-----------|-------------------|-------------------|
| Faction floor | 0.10 | 0.08 |
| Faction count | 3 | 4 |
| Sum | 1.0 | 1.0 |
| FactionType enum | MILITARY, MERCHANT, CULTURAL | MILITARY, MERCHANT, CULTURAL, CLERGY |

Each existing faction loses ~2.5% base influence from renormalization. Decision 9 regression baseline catches behavioral drift from this shift.

Default influence for new civs: `{MILITARY: 0.25, MERCHANT: 0.25, CULTURAL: 0.25, CLERGY: 0.25}`. Existing civs get `CLERGY: floor (0.08)` with others renormalized.

### Event-Driven Influence Shifts

Added to `tick_factions()`, same mechanism as military/merchant/cultural:

| Event | Shift | Source Phase | Cap |
|-------|-------|-------------|-----|
| Temple built | +0.03 | Phase 5 (BUILD) | Per event |
| Conversion success (≥5% of any region converted this turn) | +0.01 | Phase 10 (snapshot) | **Per-civ, max +0.01/turn** |
| Holy war won (Militant conquest of different-faith region) | +0.04 | Phase 5 (WAR) | Per event |
| Temple destroyed (conquest or replaced) | -0.03 | Phase 5 | Per event |
| Priest death above baseline (≥5% priest population loss) | -0.01 per 5% loss | Phase 10 (demographics delta) | Per-civ |

**Conversion success is per-civ, not per-region.** A Proselytizing civ with 10 regions under active missionary pressure gets at most +0.01/turn from conversion, not +0.01 per converting region. This matches the other factions' pattern where events are per-civ (one event per war won, not per-region conquered simultaneously).

### Clergy Action Weight Modifiers

Added to `FACTION_WEIGHTS` in `factions.py`:

```python
FactionType.CLERGY: {
    "INVEST_CULTURE": 1.5,  # Religious propaganda
    "BUILD": 1.4,           # Temple construction priority
    "DIPLOMACY": 1.3,       # Religious diplomacy
    "WAR": 0.7,             # Clergy prefers conversion over conquest
    "TRADE": 0.8,           # Tithes benefit from trade, not the priority
}
```

**WAR 0.7 × holy war +0.15 interaction:** A clergy-dominant civ with Militant doctrine gets competing signals — institutional preference for peace (WAR × 0.7 multiplicative) and doctrinal drive for holy war (WAR + 0.15 additive from M37). These operate at different levels in `action_engine.py` (faction weight is multiplicative on base action weight, holy war bonus is additive to utility score). The tension between doctrine and institution is intentional and narratively rich: Militant clergy-dominant civs still fight holy wars, just slightly less eagerly than Militant military-dominant civs. The implementation plan should include a step verifying this computation order.

### Tithe Mechanic

Per-turn in Phase 10, after trade income is computed:

```python
def compute_tithe_base(civ, snapshot=None):
    """M38a: trade_income proxy. M41: sum(merchant_wealth)."""
    return civ.trade_income

# In tick_factions() or Phase 10 consequences:
if civ.factions.influence[FactionType.CLERGY] >= TITHE_THRESHOLD:
    tithe = TITHE_RATE * compute_tithe_base(civ)
    civ.treasury += tithe
```

**Gating:** Tithes only collected when `clergy_influence >= TITHE_THRESHOLD` (0.15). Below the threshold, clergy doesn't have enough institutional power to tax. This prevents floor-level clergy (0.08) from generating free treasury.

**Known edge case:** The 0.15 step function can cause oscillation near the threshold (clergy hits 0.15 → tithes start → temples built → clergy rises; temple destroyed → 0.14 → tithes stop). The oscillation window is narrow. M47 can smooth with a linear ramp if testing shows jitter.

**Treasury flow:** Tithes credit the civ's existing treasury. No parallel purse. Clergy influence over how treasury gets spent comes from faction action weight modifiers.

**M41 migration:** One-line change in `compute_tithe_base()`:

```python
# M41:
def compute_tithe_base(civ, snapshot=None):
    return sum(agent.wealth for agent in civ_agents if agent.occupation == MERCHANT)
```

### Succession Integration

When `clergy_influence >= CLERGY_NOMINATION_THRESHOLD` (0.15):

- Generate clergy candidate with priest-archetype traits:
  - High loyalty trait (consistent with priest occupation personality)
  - Tradition as primary cultural value
  - Order as secondary cultural value
- Candidate enters weighted selection pool alongside military/merchant/cultural candidates
- No faith-specific traits — candidate reflects institutional character, not theology

Same code path as other three factions. One more iteration of the existing faction-candidate loop.

### Power Struggle Participation

Clergy participates in power struggles using existing mechanics unchanged. When top two factions differ by <0.15 and second >0.40, power struggle triggers. Same stability drain (-3/turn for 5 turns). No clergy-specific power struggle behavior.

---

## Rust-Side Changes

### CivSignals Extension (signals.rs)

```rust
pub faction_clergy: f32,  // New field
// dominant_faction: u8 now supports value 3 (clergy)
```

### Arrow Schema (ffi.rs)

One new Float32 column (`faction_clergy`) in civ signal RecordBatch. One new Bool column (`has_temple`) in region RecordBatch.

### Satisfaction (satisfaction.rs)

Occupation-faction alignment extended:

```rust
let occ_matches = match dominant_faction {
    0 => occ == 1,  // military -> soldiers
    1 => occ == 2,  // merchant -> merchants
    2 => occ == 3,  // cultural -> scholars
    3 => occ == 4,  // clergy -> priests
    _ => false,
};

let faction_influence = match occ {
    1 => cs.faction_military,
    2 => cs.faction_merchant,
    3 => cs.faction_cultural,
    4 => cs.faction_clergy,
    _ => 0.0,
};
```

Temple priest bonus:

```rust
if occ == 4 && region.has_temple {
    satisfaction += TEMPLE_PRIEST_BONUS;  // 0.10 [CALIBRATE]
}
```

### RegionState (region.rs)

```rust
has_temple: bool,  // Python-computed: active temple with faith matching controller's civ_majority_faith
```

### No New Modules, No New Tick Stages

All Rust changes are additions to existing code paths. Total: ~33 lines.

---

## Python-Side Changes

### agent_bridge.py

`FACTION_MAP` extended with `"clergy": 3`. `build_signals()` adds `faction_clergy` column. `build_region_batch()` adds `has_temple` column (computed: region has active temple with `faith_id == controller.civ_majority_faith`).

### Conversion Signal Integration

In `compute_conversion_signals()` (religion.py, M37):

```python
# Temple boost — faith-bound guard clause
if region.temple and region.temple.active and region.temple.faith_id == target_faith:
    conversion_rate *= (1.0 + TEMPLE_CONVERSION_BOOST)  # 1.5×
```

One line in existing M37 signal computation. Does not reopen M37's conversion architecture.

---

## Constants

All `[CALIBRATE]` for M47:

| Constant | Default | Location | Purpose |
|----------|---------|----------|---------|
| `TEMPLE_BUILD_COST` | 10 | Python | Treasury cost |
| `TEMPLE_BUILD_TURNS` | 3 | Python | Build time |
| `MAX_TEMPLES_PER_REGION` | 1 | Python | Build constraint |
| `MAX_TEMPLES_PER_CIV` | 3 | Python | Build constraint |
| `TEMPLE_CONVERSION_BOOST` | 0.50 | Python | Multiplicative boost when faith matches |
| `TEMPLE_PRIEST_BONUS` | 0.10 | Rust | Satisfaction bonus for priests in templed regions |
| `TEMPLE_PRESTIGE_PER_TURN` | 1 | Python | Per-temple prestige accumulation |
| `CIV_PRESTIGE_PER_TEMPLE` | 1 | Python | Per-temple civ prestige contribution |
| `TITHE_RATE` | 0.10 | Python | Fraction of tithe base → treasury |
| `TITHE_THRESHOLD` | 0.15 | Python | Min clergy influence for tithes |
| `CLERGY_NOMINATION_THRESHOLD` | 0.15 | Python | Min clergy influence for succession |
| `FACTION_FLOOR` | 0.08 | Python | Per-faction minimum (was 0.10) |
| `EVT_TEMPLE_BUILT` | +0.03 | Python | Clergy influence shift |
| `EVT_CONVERSION_SUCCESS` | +0.01 | Python | Per-civ max, ≥5% threshold |
| `EVT_HOLY_WAR_WON` | +0.04 | Python | Militant inter-faith conquest |
| `EVT_TEMPLE_DESTROYED` | -0.03 | Python | Conquest or BUILD replacement |
| `EVT_PRIEST_LOSS` | -0.01 | Python | Per 5% priest population loss |

---

## Validation

### Tier 1: Structural Unit Tests (Must Pass)

| Test | Verifies |
|------|----------|
| 4-faction normalization: sum to 1.0, each ≥ 0.08 | Floor and sum invariant |
| Clergy at floor (0.08): no nomination, no tithes | Threshold gating |
| Clergy at 0.20: nomination fires, tithe collected | Above-threshold behavior |
| Temple BUILD: faith_id set to builder's civ_majority_faith | Faith binding |
| Temple BUILD in region with foreign temple: old destroyed, event fired | Replacement lifecycle |
| Militant conquest of templed region: temple destroyed | Holy war destruction |
| Non-militant conquest: temple survives, faith_id unchanged | Preservation |
| Temple conversion boost: applies only when temple faith == converting faith | Guard clause |
| Temple conversion boost: no effect when faiths differ | Negative case |
| Priest satisfaction: +0.10 in templed region (Rust) | has_temple wiring |
| Tithe: `TITHE_RATE × trade_income` credits treasury | Treasury flow |
| `compute_tithe_base()` returns `civ.trade_income` | Helper contract for M41 swap |
| Clergy candidate traits: high loyalty, Tradition primary, Order secondary | Template |
| `faction_clergy` in CivSignals Arrow schema: round-trip write/read | FFI correctness |
| `has_temple` in region RecordBatch: round-trip | FFI correctness |
| Event shifts: each event type produces correct influence delta | Event table |
| Conversion success event: per-civ cap (max +0.01/turn regardless of region count) | Anti-stacking |

### Tier 2: Regression Harness (200 Seeds × 200 Turns, Must Pass Tolerances)

| Test | Tolerance | Verifies |
|------|-----------|----------|
| Decision 9 baseline: clergy at floor, 0 events → action distributions within ±2% of 3-faction baseline | ±2% | Renormalization stability |
| Decision 9 baseline: succession winner match rate ≥95% against 3-faction baseline | ≥95% | Succession stability |
| Temple conversion boost: templed regions with matching faith convert 30-60% faster than untempled | ±15% | +50% boost propagation |
| Tithe treasury: civs with clergy ≥0.15 accumulate 5-15% more treasury than baseline | ±5% | Tithe magnitude |
| Economy regression: non-clergy treasury/trade within ±10% of pre-M38a | ±10% | No destabilization |
| `--agents=off` regression: output identical to pre-M38a | Exact | Agent-independent unchanged |

### Tier 3: Characterization (200 Seeds × 500 Turns, Documented Report)

| Metric | What It Reveals |
|--------|-----------------|
| Clergy influence trajectory: mean/median over time by civ archetype | Which civs naturally develop strong clergy |
| Temple survival rate: % surviving 100 turns post-construction | Destruction frequency |
| Faction dominance distribution: 4-way dominant counts at turn 100, 300, 500 | Clergy competitiveness |
| Tithe contribution: % of total treasury from tithes over 500 turns | Economic significance |
| Succession outcomes: clergy-candidate win rate by clergy influence level | Institutional power curve |
| Holy war × clergy interaction: action distribution for Militant vs non-Militant clergy-dominant civs | WAR 0.7 × holy war +0.15 net effect |

Report output: `docs/superpowers/analytics/m38a-temples-clergy-report.md`.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `signals.rs` | Add `faction_clergy: f32` to CivSignals | ~3 |
| `ffi.rs` | Add `faction_clergy` Float32 column to civ signal schema. Add `has_temple` Bool column to region schema. | ~12 |
| `satisfaction.rs` | Extend `dominant_faction` match for 3→occ 4. Extend `faction_influence` match for occ 4→`faction_clergy`. Temple priest bonus. | ~15 |
| `region.rs` | Add `has_temple: bool` to RegionState | ~3 |
| `models.py` | `FactionType.CLERGY`. `faith_id`/`temple_prestige` on Infrastructure. Default faction influence updated. | ~15 |
| `factions.py` | Floor 0.10→0.08. `FACTION_WEIGHTS[CLERGY]`. `tick_factions()` clergy event shifts with per-civ cap. Tithe computation and gating. Clergy candidate template. | ~80 |
| `infrastructure.py` | `TEMPLE` type. `faith_id` assignment at build. Max-per-region/civ checks. Militant conquest destruction. BUILD-replaces logic. Prestige tick. | ~60 |
| `agent_bridge.py` | `FACTION_MAP` extended. `faction_clergy` in `build_signals()`. `has_temple` in `build_region_batch()`. | ~15 |
| `action_engine.py` | Temple trait priority in BUILD selection. Conversion success event detection (per-civ, ≥5%). | ~20 |
| `religion.py` | `compute_tithe_base()` helper. Temple conversion boost guard clause in `compute_conversion_signals()`. | ~15 |
| `simulation.py` | Temple prestige tick in Phase 10. Clergy influence initialization. | ~10 |
| Tests (Rust) | Tier 1: FFI round-trip, satisfaction alignment, temple priest bonus. | ~60 |
| Tests (Python) | Tier 1: normalization, thresholds, temple lifecycle, events, tithe. Tier 2: regression harness. | ~190 |

**Total:** ~33 lines Rust (production), ~215 lines Python (production), ~250 lines tests.

### What Doesn't Change

- `culture.py` — M36 cultural drift unchanged
- `ecology.py` — resource/ecology unchanged
- `politics.py` — reads faction influence (now includes clergy), but reading logic is faction-agnostic
- `pool.rs` — no new agent fields
- `tick.rs` — no new stages
- Bundle format unchanged
- `--agents=off` mode: faction system is Python-only, works without agents. Tithes and faction shifts function normally. Temple conversion boost applies to M37 conversion signals (zero in `--agents=off`, so boost is no-op). Priest satisfaction bonus moot without agents. Behavior unchanged.

---

## Implementation Plan Notes

These notes are for the implementation plan, not the spec itself:

1. **factions.py should be broken into substeps:** (a) normalization + FACTION_WEIGHTS, (b) event shifts + per-civ cap in tick_factions(), (c) tithe + succession candidate. Six distinct changes in one file — monolithic diff is hard to review.

2. **Read existing Infrastructure model before writing temple extension.** If Infrastructure is a strict Pydantic model, adding `faith_id`/`temple_prestige` may require subclassing. The plan should verify compatibility first.

3. **Verify WAR × clergy computation order** in `action_engine.py`. Faction weight (multiplicative) and holy war bonus (additive) interact — confirm Militant clergy-dominant civs still fight holy wars, just less eagerly than Militant military-dominant civs.

---

## Forward Dependencies

| Milestone | How M38a Enables It |
|-----------|-------------------|
| M38b (Schisms & Persecution) | Reads `temple_prestige` for pilgrimage destinations ("highest-prestige temple of their faith"). Temple destruction in schism events uses `EVT_TEMPLE_DESTROYED`. Persecution penalty uses remaining -0.15 cap budget. If faith-specific temple support needed (persecution exemption), add `temple_faith_id: u8` to RegionState at M38b. |
| M39 (Family & Lineage) | Family faith inheritance interacts with temple presence — children born in templed regions of matching faith. |
| M41 (Wealth) | `compute_tithe_base()` swaps from `civ.trade_income` to `sum(merchant_wealth)`. One-line change in isolated helper. |
| M47 (Tuning Pass) | All `[CALIBRATE]` constants tuned. Agent-derived faction influence migration for all four factions (roadmap formula). Tithe step function smoothing if oscillation observed. Tier 3 report provides calibration targets. |
