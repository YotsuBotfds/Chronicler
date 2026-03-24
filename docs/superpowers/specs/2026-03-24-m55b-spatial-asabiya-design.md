# M55b: Spatial Asabiya - Design Spec

> Replaces civ-level asabiya scalar with per-region frontier/interior dynamics. `civ.asabiya` becomes a population-weighted aggregate of regional values. All consumers continue reading `civ.asabiya` unchanged.

**Depends on:** No hard runtime dependency on M55a for core M55b mechanics. M55b uses region adjacency (already exists) and controller fields, not per-agent coordinates. Roadmap sequencing still places M55b after M55a for rollout discipline, and the deferred military projection extension remains follow-up work.

**Phase 6 asabiya unchanged until this lands.** Existing code reads `civ.asabiya`; M55b changes the source, not the API.

---

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Spot mutations -> all owned regions (D-policy) | Preserves civ-level magnitude. Capital-only (A) dilutes in large empires - +0.2 to capital of a 10-region empire with 10% capital pop share becomes +0.02 at civ level. Civ-level bonus term (B) keeps a non-spatial side channel. D preserves existing impact while staying fully regional. |
| D2 | Gradient frontier model, linear f | Removes cliff behavior when a single region flips. Binary frontier/interior is a special case (f in {0,1}) available as a debug comparator. No extra constants beyond r0 and delta. |
| D3 | Foreign = different controller OR uncontrolled | Pure geographic signal, no diplomatic semantics. Uncontrolled wilderness is a frontier in the Turchin sense. Federation allies and vassals count as foreign. Log `different_civ_count` and `uncontrolled_count` separately so M61b can add soft-frontier tuning without refactoring core frontier math. |
| D4 | Phase 10 slot, moved after politics checks | Asabiya tick runs after secession/vassal rebellion/restoration (which write to regions under D-policy) but before collapse check (which reads `civ.asabiya`). Ensures same-turn mutations are captured in aggregation. |
| D5 | Military projection deferred | `ASABIYA_POWER_DROPOFF` constant defined but inactive. Distance-decay formula (`P = A * mean(S) * exp(-d/h)`) wired in a follow-up with dedicated WAR balance tests. Keeps M55b's behavioral change surface contained. |
| D6 | Compute+store variance, don't wire into collapse | `civ.asabiya_variance` computed each turn for observability (analytics, narration, diagnostics). Not wired into collapse predicates - that's an M61b calibration target (`ASABIYA_COLLAPSE_VARIANCE_THRESHOLD`). |
| D7 | RNG offset 1400 collision tracked in M55a | M55b has no RNG consumption (frontier formula is deterministic). If M55a is not merged yet, keep `INITIAL_AGE_STREAM_OFFSET -> 2000` as an open M55a prerequisite before claiming 1400/1401 for spatial streams. |
| D8 | `RegionAsabiya` sub-model on Region | Groups asabiya value + frontier diagnostics (frontier_fraction, neighbor counts). Follows `RegionEcology`/`RegionStockpile` pattern. Keeps Region's flat namespace from growing. |
| D9 | Clean replacement, no feature flag | Old 35-line `apply_asabiya_dynamics` body replaced entirely. No dual-path runtime flag. 200-seed regression via old-commit vs new-commit comparison provides the A/B validation. |
| D10 | Keep `"asabiya"` in `UNBOUNDED_STATS` | Safety net during migration. If any `acc.add(..., "asabiya", ...)` survives by accident, removing it from unbounded routing would cause silent clamping to 0-100. Clean out in a later pass. |
| D11 | First-turn gradient on secession/restoration is intentional | New civs (secession at 0.7, restoration at 0.8) immediately participate in spatial asabiya. At r0=0.05, delta=0.02, max first-tick perturbation is ~3-4%. Values are near equilibrium by design. |

---

## Data Model

### New sub-model: `RegionAsabiya`

```python
class RegionAsabiya(BaseModel):
    asabiya: float = 0.5
    frontier_fraction: float = 0.0
    different_civ_count: int = 0
    uncontrolled_count: int = 0
```

**On Region:** `asabiya_state: RegionAsabiya = Field(default_factory=RegionAsabiya)`

Default `asabiya=0.5` is the midpoint of current world_gen range `uniform(0.4, 0.8)`. Old saves that lack the field get reasonable behavior.

### Civilization changes

**New field:** `asabiya_variance: float = 0.0`

Alongside existing `asabiya: float = 0.5`. Default 0.0 = no variance, backward compatible. Not wired into gameplay in M55b (D6).

### CivSnapshot

Add `asabiya_variance: float = 0.0` with default for backward compat on older bundles.

### World initialization (world_gen.py)

Post-assignment sync pass: for each controlled region, set `region.asabiya_state.asabiya = civ.asabiya`. Uncontrolled regions keep default 0.5. This ensures the first tick's aggregation reproduces the initial civ value.

---

## Core Tick: `apply_asabiya_dynamics` Replacement

Replace the body of `apply_asabiya_dynamics` at simulation.py:583. Drop the `acc` parameter - the function only runs in Phase 10 without accumulator argument at the call site.

### Step 1: Compute frontier fraction

For each region, iterate adjacencies. Count only neighbors that resolve in `region_map` (valid-neighbor denominator - stale/missing adjacency names do not inflate the count).

```
different_civ_count = neighbors where adj.controller != region.controller and adj.controller is not None
uncontrolled_count = neighbors where adj.controller is None
frontier_fraction = (different_civ_count + uncontrolled_count) / valid_neighbor_count
```

If `valid_neighbor_count == 0`: `frontier_fraction = 0.0` (treat as interior).

Store all three values on `region.asabiya_state`.

### Step 2: Gradient formula on controlled regions

Build `civ_by_name = {c.name: c for c in world.civilizations}` once before the loop.

For each region with a controller:

```
s = region.asabiya_state.asabiya
f = region.asabiya_state.frontier_fraction
s_next = s + r0 * f * s * (1 - s) - delta * (1 - f) * s
```

Then apply folk hero per-turn bonus (after gradient formula, matching legacy ordering from simulation.py:600-610):

```
folk_bonus = compute_folk_hero_asabiya_bonus(civ)
if folk_bonus > 0:
    s_next = s_next + folk_bonus * 0.1
```

Clamp to [0.0, 1.0], round to 4 decimal places. Write to `region.asabiya_state.asabiya`.

Uncontrolled regions: frontier fraction computed (Step 1) but asabiya not ticked. No controller = no civ to have solidarity for.

### Step 3: Civ-level aggregation

For each living civ:

```
mean_asabiya = sum(region_pop * region_asabiya) / total_pop
variance = sum(region_pop * (region_asabiya - mean_asabiya)^2) / total_pop
```

- Write `civ.asabiya = round(mean_asabiya, 4)` (direct assignment, no accumulator)
- Write `civ.asabiya_variance = round(variance, 6)`
- Zero total pop fallback: keep existing `civ.asabiya` unchanged (avoid jumps)

### Constants

| Constant | Value | Calibrate in |
|----------|-------|-------------|
| `ASABIYA_FRONTIER_GROWTH_RATE` (r0) | 0.05 | M61b |
| `ASABIYA_INTERIOR_DECAY_RATE` (delta) | 0.02 | M61b |
| `ASABIYA_POWER_DROPOFF` (h) | defined, inactive | M61b |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | defined, inactive | M61b |

Initial r0/delta values match current `apply_asabiya_dynamics` hardcoded values.

### Phase 10 position

Move `apply_asabiya_dynamics(world)` call from simulation.py:999 to right before the collapse check at simulation.py:1020. This ensures:

1. Politics checks (secession, vassal rebellion, restoration) write D-policy mutations to regions
2. Asabiya tick runs: frontier formula + civ aggregation
3. Collapse check reads updated `civ.asabiya`

**Ordering safety note:** Under the old code, politics checks (check_secession, check_vassal_rebellion) ran after asabiya ticked, so they saw this turn's asabiya. Under M55b, they run before the tick, so they see last turn's aggregate. Verified safe: neither check_secession nor check_vassal_rebellion reads `civ.asabiya` as an input to their probability calculations. If a future milestone adds an asabiya read to these checks, the ordering must be revisited.

**War dilution note:** `action_engine.py:441-456` reads `civ.asabiya` (now a population-weighted average). A large empire with zealous frontier but decadent core fights wars with average solidarity, not frontier solidarity. This makes large empires weaker in war relative to small frontier states - historically plausible (late Roman Empire style). The deferred military projection formula (D5) would fix this by making power distance-dependent, but until it lands, this dilution effect is intentional.

---

## Spot Mutation Migration (D-policy)

All sites that write `civ.asabiya` directly migrate to D-policy: apply delta to `region.asabiya_state.asabiya` for all regions where `region.controller == civ.name`. Clamp each region to [0.0, 1.0].

### Mutation sites

| Source | File:Line | Delta | Phase | All three branches (hybrid/acc/else) |
|--------|-----------|-------|-------|--------------------------------------|
| Fallen empire | politics.py:1216-1221 | +boost | Phase 2 (simulation.py:410) | Yes - migrate all branches |
| Supervolcano folk hero bonus | emergence.py:464 | +0.05 | Phase 1 (check_black_swans) | Yes |
| Cultural works | simulation.py:1169 | +0.05 | Phase 10 (cultural milestones) | Yes |
| Coup | leaders.py:339 | +0.1 | Phase 7 (leader_death successor path) | Yes - note: `acc` branch is dead code (all callers pass acc=None), only else branch is live |
| Vassal rebellion | politics.py:533-542 | +0.2 | Phase 10 (politics checks) | Yes - hybrid, acc, and else branches all need D-policy |

**Phase ordering note:** `apply_fallen_empire` runs in Phase 2 (simulation.py:410), well before the Phase 10 asabiya tick. Its +boost D-policy regional write will be in place when the gradient formula runs. The boost compounds with frontier growth: a fallen-empire frontier region at asabiya `s` gets boosted to `s + boost`, then frontier growth applies to `s + boost`. This interaction is small (boost is 0.05, growth contribution is ~0.05 * f * s * (1 - s)) and produces the correct behavior: fallen empires have slightly elevated frontier cohesion. Document but do not special-case.

### Special cases

| Source | File:Line | Behavior |
|--------|-----------|----------|
| Secession new civ | politics.py:267 | Initialize `RegionAsabiya(asabiya=0.7)` on breakaway regions. The constructor-level `asabiya=0.7` on the Civilization object is now redundant (tick will overwrite it) but harmless as a fallback for any code that reads before the first aggregation. |
| Restoration | politics.py:1060, 1074 | Set `asabiya=0.8` on restored civ - also initialize region asabiya_state to 0.8 for restored regions |
| Scenario override | scenario.py:518 | Sync override value to all controlled regions' asabiya_state |

### Folk hero per-turn

The per-turn folk hero bonus in `apply_asabiya_dynamics` (currently simulation.py:606-610) stays inside the tick body as the only in-tick effect. All other spot mutations happen at their natural source phases; the tick just reads regional values and computes.

### Conquest/region transfer

When a region changes controller (WAR, EXPAND), its `asabiya_state` persists. The conquering civ inherits the region's existing solidarity. Historically sensible - a conquered frontier province does not instantly adopt the conqueror's cohesion.

### Accumulator cleanup

- Remove all `acc.add(civ_idx, civ, "asabiya", ...)` calls from migrated sites
- Replace with direct regional writes (D-policy loop)
- Keep `"asabiya"` in `UNBOUNDED_STATS` as safety net (D10)
- Update comment at simulation.py:1450 ("Apply treasury, asabiya, prestige") to remove asabiya reference

---

## Testing Strategy

### Unit tests

1. **Frontier fraction computation**
   - 3 neighbors: 1 same-civ, 1 different-civ, 1 uncontrolled -> f = 2/3
   - All same-civ -> f = 0.0
   - All foreign -> f = 1.0
   - No valid neighbors -> f = 0.0
   - Stale adjacency name (not in region_map) excluded from denominator

2. **Gradient formula correctness**
   - Frontier (f=1.0): logistic growth, slows near 1.0
   - Interior (f=0.0): linear decay toward 0
   - Mixed (f=0.5): growth and decay partially cancel
   - Boundary: asabiya=0.0 stays 0.0 (logistic fixed point)
   - Boundary: asabiya=1.0 decays if f < 1.0

3. **Civ-level aggregation**
   - 2 regions, equal pop, asabiya 0.3/0.7 -> mean 0.5, variance 0.04
   - 2 regions, 90/10 pop split -> weighted mean skewed toward high-pop
   - Single region -> variance = 0.0
   - Zero total pop -> civ.asabiya unchanged

4. **D-policy spot mutations**
   - 3-region civ gets +0.1 coup -> all 3 regions increase by 0.1
   - Region at 0.95 gets +0.1 -> clamped to 1.0
   - Secession: breakaway regions initialized to 0.7
   - Restoration: restored region initialized to 0.8

5. **Folk hero per-turn in tick**
   - Bonus applied after gradient formula (ordering test)
   - No folk heroes -> no bonus term

6. **Branch-matrix tests**
   - For each migrated mutation site: verify hybrid, acc-path, and direct/off branches all produce the same D-policy regional write

7. **No-scalar-write guard**
   - CI-level grep (or test assertion) that no code writes `civ.asabiya +=`, `civ.asabiya = min(civ.asabiya +`, or `acc.add(..., "asabiya", ...)` outside the aggregation function

8. **Restoration + scenario sync**
   - Restoration fires -> region asabiya_state initialized to 0.8
   - Scenario override -> region asabiya_state synced to override value

9. **Snapshot compatibility**
   - `CivSnapshot` with missing `asabiya_variance` field loads cleanly (default 0.0)

10. **Invariant bounds**
    - Over 50+ turns: every `region.asabiya_state.asabiya` in [0.0, 1.0], every `civ.asabiya` in [0.0, 1.0], every `civ.asabiya_variance` in [0.0, 0.25]

### Integration tests

11. **Multi-turn convergence**
    - 20 turns, fixed topology. Frontier regions trend toward high asabiya, interior toward low. Verify monotonic trend per category.

12. **Conquest changes frontier status**
    - Civ A conquers from Civ B -> verify frontier fractions update on both sides

13. **Phase 10 ordering**
    - Vassal rebellion writes +0.2 to regions -> tick aggregates -> collapse check sees updated value. Civ at asabiya=0.08 + rebellion boost must not falsely collapse.

14. **Determinism**
    - Same seed, same topology -> identical asabiya values over 50 turns. No RNG in tick - sanity check for floating-point ordering stability.

15. **`--agents=off` parity**
    - Both modes produce structurally similar asabiya ranges. Not bit-identical (different mutation paths) but no pathological extremes.

### Regression (200-seed)

Old commit vs new commit comparison. Key metrics:
- Mean asabiya per turn distribution
- Collapse frequency
- War outcome distribution
- Secession frequency

Expect behavioral shift (spatial model is fundamentally different) but no pathological extremes (all civs at 0, all at 1, or collapse rate doubling).

---

## Deferred to follow-up milestones

| Item | Target | Notes |
|------|--------|-------|
| Military projection `P = A * mean(S) * exp(-d/h)` | Follow-up / M61b | Constant defined inactive. Needs dedicated WAR balance tests. |
| Collapse variance predicate | M61b | `asabiya_variance > threshold` as collapse trigger. Data available from M55b. |
| Soft frontier factor for federation/vassal neighbors | M61b | Landlocked allies may decay to zero. `different_civ_count`/`uncontrolled_count` logged for this. |
| RNG offset 1400 resolution | M55a prerequisite | M55b is unaffected, but M55a should move `INITIAL_AGE_STREAM_OFFSET` to 2000 before claiming 1400/1401 for spatial streams. |
| Remove `"asabiya"` from `UNBOUNDED_STATS` | Post-M55b cleanup | Once all `acc.add` asabiya calls confirmed gone. |

---

## Files touched

| File | Changes |
|------|---------|
| `models.py` | Add `RegionAsabiya`, add field on `Region`, add `asabiya_variance` on `Civilization` and `CivSnapshot` |
| `simulation.py` | Replace `apply_asabiya_dynamics` body, move call site, migrate cultural works mutation |
| `world_gen.py` | Post-assignment region asabiya sync |
| `emergence.py` | Migrate folk hero mutation to D-policy |
| `leaders.py` | Migrate coup mutation to D-policy |
| `politics.py` | Migrate vassal rebellion, fallen empire, secession, restoration to D-policy |
| `scenario.py` | Add region sync after asabiya override |
| `traditions.py` | No changes (compute_folk_hero_asabiya_bonus reads civ, not asabiya field) |
| `narrative.py` | No changes (reads civ.asabiya, unchanged API) |
| `action_engine.py` | No changes (reads civ.asabiya, unchanged API) |
| `accumulator.py` | Keep `"asabiya"` in UNBOUNDED_STATS, update comments |
| `main.py` | Add asabiya_variance to CivSnapshot |

