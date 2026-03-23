# P4 Codebase Readiness Report — Regional Population

> Post-M20b codebase review. Identifies every population reference in the simulation, flags the architectural gap, and scopes the diff for P4: moving population from civ-level to region-level.
> Written by Phoebe. Read this when writing the P4 spec.

---

## 1. The Core Problem

Population is a single `int` on `Civilization` (1–100 scale). The simulation pretends regions have population by dividing:

```python
region_pop = civ.population // len(civ.regions)
```

This appears in two places (simulation.py:854, climate.py:180) and produces identical fake values for every region a civ controls. A 4-region civ with population 60 has "15 per region" regardless of whether those regions are fertile plains or barren tundra.

**Consequences:**
- Famine triggers identically across all regions of a civ
- Migration calculates surplus from this fake number, not actual regional pressure
- Fertility mechanics (phase 8) are decoupled from where population actually lives
- No population movement between regions of the same civ
- Conquering a region doesn't change population distribution at all

---

## 2. Model Changes Required

### Region Model — Add `population` Field

```python
# models.py, Region class (currently no population field)
class Region(BaseModel):
    name: str
    terrain: str
    carrying_capacity: int
    # ... existing fields ...
    population: int = 0  # NEW: regional population, 0–100 scale per region
```

**Design decision needed:** Scale. Options:
- **Option A: Keep 1–100 per region.** Civ population becomes `sum(region.population for region in civ_regions)`, uncapped. Simple, but a 10-region civ could theoretically reach 1000, breaking all the `clamp(..., 100)` calls.
- **Option B: Population is a share (0.0–1.0) of carrying_capacity.** Region population = `int(region.population * effective_capacity(region))`. Elegant, but every formula needs to convert.
- **Option C: Absolute count, uncapped, with region caps at carrying_capacity.** Most realistic, but requires rethinking the 1–100 stat scale.

**Phoebe's recommendation: Option A with `Civilization.population` becoming a computed property.** The stat floor/ceiling on the *civ aggregate* goes away — individual regions are clamped to `[0, carrying_capacity]` instead. This is the least disruptive to the action engine and narrative prompts, which read `civ.population` as a single number.

### Civilization Model — Derived Population

```python
# models.py, Civilization class
class Civilization(BaseModel):
    # population: int = Field(ge=1, le=100)  # REMOVE this field

    @computed_field
    @property
    def population(self) -> int:
        """Sum of all controlled region populations."""
        # This requires access to regions' population values
        # Problem: Civilization doesn't hold Region references, only names
```

**Architectural snag:** `Civilization` stores `regions: list[str]` (names), not `Region` references. Computing `population` as a property requires access to the `WorldState.regions` list. Options:
- **A: Store population on Region, compute civ total at read sites.** Minimal model change, but every `civ.population` read becomes a lookup.
- **B: Denormalize — keep `Civilization.population` as a cached sum, update after every region population change.** More code to keep in sync, but zero read-site changes.
- **C: Store `Region` references on `Civilization` instead of names.** Big refactor, breaks serialization.

**Phoebe's recommendation: Option B (denormalized cache).** Add a `_sync_population(civ, world)` helper. Call it at the end of any phase that modifies region populations. The sync is cheap (~5 lines), and it means `civ.population` reads in action_engine.py, narrative.py, and main.py don't change at all.

### CivSnapshot — No Change Needed (Yet)

`CivSnapshot.population: int` continues to reflect the civ-level aggregate. The viewer doesn't need per-region population in P4 — that's a viewer milestone. The snapshot already has `region_control`, so per-region pop can be added later as `region_populations: dict[str, int]`.

---

## 3. Every Population Reference — Complete Catalog

### simulation.py (993 lines)

| Line | Phase | Code | P4 Change |
|------|-------|------|-----------|
| 140 | phase_environment (plague) | `civ.population = clamp(civ.population - int(10 * mult), ...)` | Distribute loss across civ's regions proportionally. Or target specific plague-affected regions. |
| 373–381 | phase_production | `if civ.economy > civ.population and civ.stability > 20:` pop grows +5 / pop declines -5 | Growth/decline should happen per region based on local conditions (fertility, infrastructure, economy share). |
| 550 | phase_events (migration event) | `civ.population = clamp(civ.population + 10, ...)` | Add population to a specific border region of receiving civ. |
| 588–589 | phase_events (injected plague) | `civ.population = clamp(civ.population - 10, ...)` | Drain from most populated region or from plague-origin region. |
| 854 | phase_fertility | `region_pop = civ.population // len(civ.regions)` | **Replace with `region.population` direct read.** This is the core fix. |
| 858–860 | phase_fertility | Compares `region_pop` to `eff_cap` for famine/growth | Now uses actual `region.population` vs `effective_capacity(region)`. |
| 889 | phase_fertility (famine) | `civ.population = clamp(civ.population - int(15 * mult), ...)` | Drain from the specific famine region, not the civ aggregate. |
| 898 | phase_fertility (famine spillover) | `neighbor.population = clamp(neighbor.population + 5, ...)` | Add to receiving civ's nearest border region. |

### climate.py (237 lines)

| Line | Code | P4 Change |
|------|------|-----------|
| 180 | `region_pop = civ.population // len(civ.regions)` | **Replace with `region.population` direct read.** Second instance of the fake division. |
| 183 | `if eff_cap >= region_pop * 0.5:` | Uses real `region.population` now. |
| 186 | `surplus = region_pop - eff_cap` | Uses real `region.population` now. |
| 216 | `recv_civ.population += amount` | Add to the specific receiving region, not civ aggregate. |
| 219, 228 | `civ.population = max(civ.population - surplus, 1)` | Drain from the specific source region. |

### politics.py (1088 lines)

| Line | Code | P4 Change |
|------|------|-----------|
| 131 | `split_pop = math.floor(civ.population * ratio)` | Sum population of regions going to the seceding entity. The seceding civ gets those regions' population directly. |
| 209 | `civ.population = max(civ.population - split_pop, 1)` | Parent civ loses the seceded regions' actual population (automatic if using region-level pop). |
| 818 | `Civilization(..., population=30, ...)` (restoration) | Distribute 30 across the restored civ's region(s). Single region → `region.population = 30`. |
| 943 | `civ.population = clamp(civ.population - 3, ...)` (twilight drain) | Drain from most populated region, or spread across all regions. |

### emergence.py (646 lines)

| Line | Code | P4 Change |
|------|------|-----------|
| 277–279 | `civ.population = clamp(civ.population - pop_loss, ...)` (pandemic) | Distribute loss across pandemic-affected regions (tracked by `world.pandemic_state` which has `region_name`). |
| 377 | `civ.population = clamp(civ.population - 20, ...)` (supervolcano) | Drain from regions near the eruption. |

### action_engine.py (643 lines)

| Line | Code | P4 Change |
|------|------|-----------|
| 614 | `if civ.population >= 80 and len(civ.regions) <= 2:` (situational weight) | **No change needed** if `civ.population` remains a computed/cached aggregate. The weight check is about civ-level overcrowding. |

### main.py (793 lines)

| Line | Code | P4 Change |
|------|------|-----------|
| 222 | `population=civ.population` (snapshot capture) | **No change needed** — reads civ aggregate for CivSnapshot. |
| 413, 426 | `civ.population + civ.military + ...` (RunResult stats) | **No change needed** — reads civ aggregate. |

### narrative.py

| Line | Code | P4 Change |
|------|------|-----------|
| 304 | `f"- Population: {civ.population}/100"` | Update format string if scale changes. If civ pop is now uncapped sum, change denominator or show as absolute. |
| 345 | `f" Pop {civ.population}"` | Same — cosmetic only. |

### scenario.py

| Line | Code | P4 Change |
|------|------|-----------|
| 53 | `CivOverride.population: int | None = Field(default=None, ge=1, le=100)` | Update validators if scale changes. Consider adding per-region population overrides. |
| 421–422 | `civ.population = override.population` | Distribute override across civ's regions. |

### world_gen.py (249 lines)

| Line | Code | P4 Change |
|------|------|-----------|
| 130 | `population=rng.randint(30, 70)` | **Replace with per-region population assignment.** Distribute initial population across starting regions based on carrying capacity. |

### interactive.py

| Line | Code | P4 Change |
|------|------|-----------|
| 73 | `f"pop:{civ.population}"` (status display) | **No change needed** if civ aggregate still works. |

---

## 4. The Two Fake-Division Sites

These are the highest-priority fixes — the entire reason P4 exists:

**Site 1: simulation.py:854 (phase_fertility)**
```python
region_pop = civ.population // len(civ.regions) if civ.regions else 0
```
This drives famine detection, fertility-based growth, and overpopulation pressure. With regional population, this becomes simply `region.population`.

**Site 2: climate.py:180 (process_migration)**
```python
region_pop = civ.population // len(civ.regions)
```
This drives climate migration — when a region's effective capacity drops below half its "population," surplus population flees to adjacent regions. With regional population, the migration calculation becomes physically meaningful: population flees *from* overpopulated regions *to* underpopulated ones.

---

## 5. New Mechanics Unlocked by Regional Population

Once population lives on regions, these become natural extensions (not required for P4, but enabled by it):

1. **Intra-civ migration:** Population moves between a civ's own regions toward higher fertility/capacity. Currently impossible.
2. **Conquest population transfer:** When a region changes hands, its population stays. Currently, conquering a region changes `region.controller` but population is just re-divided across the new region set.
3. **Region-specific famine:** Tundra region starves while coastal region thrives. Currently impossible — famine is per-civ.
4. **Population as conquest incentive:** Rich regions are worth conquering for their population, not just territory count.
5. **Refugee mechanics:** War displaces population from contested regions to safer ones.

---

## 6. Mid-Turn Population Read Problem

Several phases read `civ.population` but don't write it. Others write it but don't read it. The turn phase order matters:

```
Phase 0: action_resolution    — reads civ.population (action weights)
Phase 1: environment          — WRITES civ.population (plague)
Phase 2: diplomacy_tick       — no population reference
Phase 3: production           — WRITES civ.population (growth/decline)
Phase 4: trade                — no population reference
Phase 5: events               — WRITES civ.population (migration, plague)
Phase 6: politics             — WRITES civ.population (secession, twilight)
Phase 7: leaders              — no population reference
Phase 8: fertility            — READS+WRITES civ.population (famine, growth)
Phase 9: degradation          — no population reference
Phase 10: tech                — no population reference
```

With regional population, the sync problem emerges: if Phase 1 drains population from a region, does Phase 3's growth check see the updated value? **Yes, if we modify regions in place** — which is already how every other stat works. The denormalized `civ.population` cache needs to be synced at the *end* of each phase that writes region populations, not at the start.

**Recommended sync pattern:**
```python
def _sync_civ_population(civ: Civilization, world: WorldState) -> None:
    """Recompute civ.population from its controlled regions."""
    civ.population = sum(
        r.population for r in world.regions
        if r.controller == civ.name
    )
```

Call after: phase_environment, phase_production, phase_events, phase_politics, phase_fertility.

---

## 7. World Gen: Initial Distribution

Current: `population=rng.randint(30, 70)` per civ, no region assignment.

**P4 world gen should:**
1. Assign population to regions based on `carrying_capacity` ratios
2. Each civ's starting population gets split across its 1–2 starting regions
3. Uncontrolled regions start with `population = 0`

Example:
```python
# Civ starts with pop=50, two regions: capacity 80 and capacity 40
# Ratio: 80/(80+40) = 0.67, 40/(80+40) = 0.33
# Region 1 gets 33, Region 2 gets 17
total_cap = sum(effective_capacity(r) for r in starting_regions)
for region in starting_regions:
    share = effective_capacity(region) / total_cap if total_cap > 0 else 1 / len(starting_regions)
    region.population = round(total_pop * share)
```

---

## 8. Scope Estimate

| Category | Files | Lines Changed (est.) |
|----------|-------|---------------------|
| Model: `Region.population` field | models.py | ~3 |
| Model: validators/constraints | models.py | ~5 |
| World gen: initial distribution | world_gen.py | ~15 |
| Simulation: phase_fertility rewrite | simulation.py | ~30 |
| Simulation: plague, growth, migration (5 sites) | simulation.py | ~25 |
| Climate: migration rewrite | climate.py | ~20 |
| Politics: secession, twilight, restoration | politics.py | ~15 |
| Emergence: pandemic, supervolcano | emergence.py | ~10 |
| Scenario: population override | scenario.py | ~5 |
| Sync helper + calls | simulation.py | ~15 |
| Narrative: format strings | narrative.py | ~4 |
| **Total** | **8 files** | **~147 lines** |

This is a medium-sized refactor. The line count is modest, but the *blast radius* is wide — 8 files, touching the core simulation loop in 5 phases. Every change needs the same careful "region-level, then sync" pattern.

---

## 9. Test Impact

The existing test suite (986+ tests) should catch regressions *if* the `civ.population` aggregate continues to work as before. Tests that:
- Assert specific `civ.population` values after events → need updating for regional distribution
- Check famine triggering → will fire differently since regions have real populations
- Check migration mechanics → results will change since surplus is now physical, not fabricated

**Recommendation:** Run the full suite after P4 implementation, expect ~20-40 test failures in simulation/climate/politics tests, fix by updating expected values to match regional distribution logic.

---

## 10. What Does NOT Change

- `CivSnapshot` schema (population stays as civ aggregate)
- Action engine weights (reads civ aggregate)
- Narrative prompts (cosmetic, reads civ aggregate)
- Bundle format (no schema break)
- TurnSnapshot (add `region_populations: dict[str, int]` later, not required for P4)
- Interestingness scoring
- Analytics module
- Memory streams
- Chronicle compilation

---

## 11. Dependencies and Ordering

P4 blocks:
- **M21 (Regional Economy)** — economy follows population as the next stat to regionalize
- **M22 (Faction Succession)** — faction support tied to regional population
- **M23 (Alliance Overhaul)** — combined military power uses population as a factor
- **M24 (Information Asymmetry)** — fog of war reveals population data

P4 depends on:
- **Nothing.** It's independent of M20a/M20b (narrative pipeline) and M19/M19b (analytics/tuning).

**Land P4 before any M21-M24 work begins.**
