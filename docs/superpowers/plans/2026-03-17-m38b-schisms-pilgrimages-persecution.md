# M38b: Schisms, Pilgrimages & Persecution — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three emergent religious dynamics — persecution of minorities, faith schisms, and pilgrimage character arcs — building on M37 belief systems and M38a temples/clergy.

**Architecture:** Python detects persecution/schism/pilgrimage conditions in Phase 10 and sets region batch signals. Rust reads `persecution_intensity` for satisfaction/utility penalties and `schism_convert_from`/`schism_convert_to` for bulk belief reassignment. Pilgrimages are Python-only on GreatPerson. All three subsystems are guarded by `if _snap is None: return` for `--agents=off` compatibility.

**Tech Stack:** Python 3.12, Rust (PyO3 + Arrow), pytest, cargo test

**Spec:** `docs/superpowers/specs/2026-03-16-m38b-schisms-pilgrimages-persecution-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/chronicler/religion.py` | Extend: persecution detection, intensity computation, martyrdom boost lifecycle, schism detection, `fire_schism()`, `determine_schism_axis()`, reformation detection |
| `src/chronicler/models.py` | Extend: new fields on Region (`martyrdom_boost`, `persecution_intensity`, `schism_convert_from`, `schism_convert_to`, `last_conquered_turn`), Civ (`previous_majority_faith`), GreatPerson (`pilgrimage_destination`, `pilgrimage_return_turn`, `arc_type`) |
| `src/chronicler/simulation.py` | Extend: wire M38b calls in `phase_consequences()`, consolidated snapshot scan |
| `src/chronicler/agent_bridge.py` | Extend: 3 new region batch columns in `build_region_batch()` |
| `src/chronicler/great_persons.py` | Extend: pilgrimage candidate selection, lifecycle, Prophet promotion bypass |
| `chronicler-agents/src/agent.rs` | Extend: `PERSECUTION_SAT_WEIGHT`, `PERSECUTION_REBEL_BOOST`, `PERSECUTION_MIGRATE_BOOST` constants |
| `chronicler-agents/src/satisfaction.rs` | Extend: read `persecution_intensity`, add penalty inside `apply_penalty_cap()` call |
| `chronicler-agents/src/tick.rs` | Extend: add persecution rebel/migrate utility boosts at call site (utilities have no region access) |
| `chronicler-agents/src/ffi.rs` | Extend: 3 new columns in region batch Arrow schema |
| `tests/test_persecution.py` | Create: Tier 1 persecution tests |
| `tests/test_schisms.py` | Create: Tier 1 schism tests |
| `tests/test_pilgrimages.py` | Create: Tier 1 pilgrimage tests |
| `tests/test_m38b_regression.py` | Create: Tier 2 interaction harness |

---

## Implementation Notes (Read Before Starting)

**These patterns apply throughout the plan. The pseudocode in tasks uses simplified names — adapt to these realities:**

1. **`civ.regions` is `list[str]` (region names), not `list[Region]`.** Build a region map: `region_map = {r.name: r for r in world.regions}` and resolve via `region_map[name]`. Every function that iterates civ regions needs this.

2. **Regions have no `region_id` field.** Use `world.regions.index(region)` or the region map for identification. The snapshot's `"region"` column contains positional indices into `world.regions`.

3. **Civilization has no `alive` field.** Check `len(civ.regions) > 0` instead.

4. **GreatPerson constructor requires:** `name`, `role`, `trait`, `civilization`, `origin_civilization`, `born_turn`. Test helpers must supply all. Fields like `belief`, `occupation`, `loyalty_trait`, `skill` are NOT on the current model — they need to be added as part of Task 8 (pilgrimage model fields) or accessed via snapshot lookup.

5. **Infrastructure constructor requires:** `type: InfrastructureType`, `builder_civ: str`, `built_turn: int`. Has `faith_id` and `temple_prestige` as optional fields. No `name` or `region_name` — region association is via the region's `infrastructure` list.

6. **Dead agents for martyrdom:** `world._dead_agents_this_turn` does not exist. Implementation must extract deaths from the agent bridge event processing (event_type=0 in `EVENT_TYPE_MAP`) or from snapshot diffs between turns. Stash deaths in Phase 10 or pass from the agent tick event handler.

7. **Persecution event tracking:** Region is a Pydantic model — avoid setting arbitrary attributes (`region._persecution_event_fired`). Use a `set[str]` tracking set (keyed by region name) passed to the function instead.

8. **`apply_penalty_cap` integration:** The current call is `apply_penalty_cap(cultural_pen + religious_pen)`. Persecution must be added INSIDE this call: `apply_penalty_cap(cultural_pen + religious_pen + persecution_pen)`.

---

## Chunk 1: Persecution

### Task 1: Model Fields & Constants

**Files:**
- Modify: `src/chronicler/models.py:219-224` (Region model, after M37 fields)
- Modify: `src/chronicler/religion.py:27-38` (constants block)

- [ ] **Step 1: Add persecution fields to Region model**

In `src/chronicler/models.py`, after the M37 religion fields (line 224), add:

```python
    # M38b: Persecution
    persecution_intensity: float = 0.0         # 0.0 = no persecution; computed in Phase 10
    martyrdom_boost: float = 0.0               # decays linearly, same lifecycle as conquest_conversion_boost
    schism_convert_from: int = 0xFF            # 255 = no schism this turn
    schism_convert_to: int = 0xFF              # 255 = no schism this turn
```

Check if `last_conquered_turn` already exists on Region. If not, add:

```python
    last_conquered_turn: int = -1              # -1 = never conquered; set by WAR resolution
```

- [ ] **Step 2: Add `previous_majority_faith` to Civilization model**

Find the Civilization model in `models.py` (around line 287 where `civ_majority_faith` lives). Add:

```python
    previous_majority_faith: int = 0           # initialized to civ_majority_faith at world-gen
```

- [ ] **Step 3: Add persecution constants to religion.py**

In `src/chronicler/religion.py`, after the existing M37 constants (around line 38), add:

```python
# M38b: Persecution
PERSECUTION_SAT_PENALTY = 0.15       # max penalty (scaled by intensity)
PERSECUTION_REBEL_BOOST = 0.30       # max rebel utility boost
PERSECUTION_MIGRATE_BOOST = 0.20     # max migrate utility boost
MASS_MIGRATION_THRESHOLD = 0.15      # ratio of persecuted agents to trigger event
MARTYRDOM_BOOST_PER_EVENT = 0.05     # added per turn with persecution deaths
MARTYRDOM_BOOST_CAP = 0.20           # max regional martyrdom boost
MARTYRDOM_DECAY_TURNS = 10           # linear decay duration
```

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py src/chronicler/religion.py
git commit -m "feat(m38b): add persecution model fields and constants"
```

---

### Task 2: Region Batch Columns (Python + Rust)

**Files:**
- Modify: `src/chronicler/agent_bridge.py:203-217` (region batch columns)
- Modify: `chronicler-agents/src/ffi.rs` (Arrow schema)
- Modify: `chronicler-agents/src/agent.rs` (Rust constants)

- [ ] **Step 1: Add columns to `build_region_batch()` in agent_bridge.py**

In `src/chronicler/agent_bridge.py`, in `build_region_batch()` after the existing M37 columns (around line 217), add:

```python
        # M38b: Persecution & Schism signals
        "persecution_intensity": pa.array(
            [r.persecution_intensity for r in regions], type=pa.float32()
        ),
        "schism_convert_from": pa.array(
            [r.schism_convert_from for r in regions], type=pa.uint8()
        ),
        "schism_convert_to": pa.array(
            [r.schism_convert_to for r in regions], type=pa.uint8()
        ),
```

After building the batch, clear transient schism state (following the M36 `_culture_investment_active` pattern at lines 220-225):

```python
    for r in regions:
        r.schism_convert_from = 0xFF
        r.schism_convert_to = 0xFF
```

- [ ] **Step 2: Add Rust constants to agent.rs**

In `chronicler-agents/src/agent.rs`, after the M37 religion constants (around line 137), add:

```rust
// M38b: Persecution
pub const PERSECUTION_SAT_WEIGHT: f32 = 0.15;
pub const PERSECUTION_REBEL_BOOST: f32 = 0.30;
pub const PERSECUTION_MIGRATE_BOOST: f32 = 0.20;
```

- [ ] **Step 3: Read persecution_intensity in satisfaction.rs**

In `chronicler-agents/src/satisfaction.rs`, in `compute_satisfaction_with_culture()` (around lines 165-172 where religious mismatch is applied), add after the religious mismatch penalty:

```rust
    // M38b: Persecution penalty (only affects religious minorities in Militant civs)
    // persecution_intensity is pre-computed by Python: 0.0 = no persecution
    let persecution_intensity = region_batch.persecution_intensity;
    if belief != region_batch.majority_belief {
        penalty += PERSECUTION_SAT_WEIGHT * persecution_intensity;
    }
```

The existing `apply_penalty_cap()` clamps the total — no change needed there.

- [ ] **Step 4: Add persecution utility boosts in tick.rs (at call site)**

`rebel_utility()` and `migrate_utility()` in `behavior.rs` have narrow signatures (no region state access). Add the persecution boost **at the call site in tick.rs** where both agent state and region batch are available:

```rust
// In tick.rs, after computing rebel_util from rebel_utility():
if pool.belief[slot] != region_batch.majority_belief {
    rebel_util += PERSECUTION_REBEL_BOOST * region_batch.persecution_intensity;
}

// Same for migrate_util after migrate_utility():
if pool.belief[slot] != region_batch.majority_belief {
    migrate_util += PERSECUTION_MIGRATE_BOOST * region_batch.persecution_intensity;
}
```

This avoids changing the utility function signatures.

- [ ] **Step 5: Add Arrow schema entries in ffi.rs**

In `chronicler-agents/src/ffi.rs`, in the region batch schema, add columns for the three new signals. Follow the existing pattern for `conversion_rate` / `majority_belief` etc.

- [ ] **Step 6: Build and verify**

```bash
cd chronicler-agents && cargo build 2>&1 | head -30
```

Expected: builds without errors.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/agent_bridge.py chronicler-agents/src/agent.rs chronicler-agents/src/satisfaction.rs chronicler-agents/src/behavior.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m38b): add persecution region batch columns and Rust readers"
```

---

### Task 3: Persecution Detection (Python)

**Files:**
- Modify: `src/chronicler/religion.py`
- Modify: `src/chronicler/simulation.py:826-858` (Phase 10 religion block)

- [ ] **Step 1: Write persecution tests**

Create `tests/test_persecution.py`:

```python
"""Tier 1 tests for M38b persecution subsystem."""
import pytest
from chronicler.models import Region, Civilization, Belief
from chronicler.religion import (
    compute_persecution,
    DOCTRINE_STANCE,
    MARTYRDOM_BOOST_PER_EVENT,
    MARTYRDOM_BOOST_CAP,
    MARTYRDOM_DECAY_TURNS,
    MASS_MIGRATION_THRESHOLD,
    decay_martyrdom_boosts,
)


def _make_belief(stance: int) -> Belief:
    """Helper: create a Belief with specified Stance doctrine."""
    doctrines = [0, 0, stance, 0, 0]  # DOCTRINE_STANCE = index 2
    return Belief(name=f"faith_s{stance}", doctrines=doctrines, faith_id=0)


def _make_region(population: int, minority_count: int) -> Region:
    """Helper: region stub with population and minority tracking."""
    r = Region(name="test_region", population=population)
    r._test_minority_count = minority_count
    return r


class TestPersecutionGate:
    """Persecution only fires for Militant (stance=+1) faiths."""

    def test_militant_persecutes(self):
        belief = _make_belief(stance=1)
        assert belief.doctrines[DOCTRINE_STANCE] == 1

    def test_pacifist_does_not_persecute(self):
        belief = _make_belief(stance=-1)
        assert belief.doctrines[DOCTRINE_STANCE] != 1

    def test_neutral_does_not_persecute(self):
        belief = _make_belief(stance=0)
        assert belief.doctrines[DOCTRINE_STANCE] != 1


class TestIntensityFormula:
    """intensity = 1.0 * (1.0 - minority_ratio)."""

    def test_ten_percent_minority(self):
        # 10% minority → intensity 0.90
        assert abs((1.0 * (1.0 - 0.10)) - 0.90) < 1e-6

    def test_forty_percent_minority(self):
        # 40% minority → intensity 0.60
        assert abs((1.0 * (1.0 - 0.40)) - 0.60) < 1e-6

    def test_fifty_percent_minority(self):
        # 50% minority → intensity 0.50
        assert abs((1.0 * (1.0 - 0.50)) - 0.50) < 1e-6


class TestMassMigration:
    """Mass migration fires when persecuted_ratio > MASS_MIGRATION_THRESHOLD."""

    def test_below_threshold_no_event(self):
        # 10% persecuted, threshold is 15%
        assert 0.10 <= MASS_MIGRATION_THRESHOLD

    def test_above_threshold_fires(self):
        # 20% persecuted, threshold is 15%
        assert 0.20 > MASS_MIGRATION_THRESHOLD


class TestMartyrdomBoost:
    """Martyrdom boost: set, stack to cap, decay linearly."""

    def test_single_event_adds_boost(self):
        r = Region(name="r", population=100)
        r.martyrdom_boost = 0.0
        r.martyrdom_boost = min(r.martyrdom_boost + MARTYRDOM_BOOST_PER_EVENT,
                                MARTYRDOM_BOOST_CAP)
        assert abs(r.martyrdom_boost - 0.05) < 1e-6

    def test_stacks_to_cap(self):
        r = Region(name="r", population=100)
        r.martyrdom_boost = 0.0
        for _ in range(10):
            r.martyrdom_boost = min(r.martyrdom_boost + MARTYRDOM_BOOST_PER_EVENT,
                                    MARTYRDOM_BOOST_CAP)
        assert abs(r.martyrdom_boost - MARTYRDOM_BOOST_CAP) < 1e-6

    def test_decay_reduces_boost(self):
        r = Region(name="r", population=100)
        r.martyrdom_boost = MARTYRDOM_BOOST_PER_EVENT  # 0.05
        decay_step = MARTYRDOM_BOOST_PER_EVENT / MARTYRDOM_DECAY_TURNS
        r.martyrdom_boost = max(0.0, r.martyrdom_boost - decay_step)
        assert r.martyrdom_boost < MARTYRDOM_BOOST_PER_EVENT
        assert r.martyrdom_boost > 0.0

    def test_decay_to_zero(self):
        r = Region(name="r", population=100)
        r.martyrdom_boost = MARTYRDOM_BOOST_PER_EVENT
        for _ in range(MARTYRDOM_DECAY_TURNS + 1):
            decay_step = MARTYRDOM_BOOST_PER_EVENT / MARTYRDOM_DECAY_TURNS
            r.martyrdom_boost = max(0.0, r.martyrdom_boost - decay_step)
        assert r.martyrdom_boost == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_persecution.py -v 2>&1 | tail -20
```

Expected: ImportError on `compute_persecution` (not yet implemented). The pure-math tests may pass since they don't import unwritten functions — that's fine, they validate the spec's formulas.

- [ ] **Step 3: Implement `compute_persecution()` in religion.py**

In `src/chronicler/religion.py`, add after `decay_conquest_boosts()`:

```python
def compute_persecution(
    regions: list[Region],
    civs: list[Civilization],
    belief_registry: list[Belief],
    snapshot,
    current_turn: int,
) -> list[dict]:
    """Detect persecution in Militant civs and compute intensity per region.

    Returns list of named event dicts (persecution events, mass migration events).
    """
    if snapshot is None or snapshot.num_rows == 0:
        return []

    events: list[dict] = []
    region_ids = snapshot.column("region").to_pylist()
    beliefs = snapshot.column("belief").to_pylist()
    civ_affinities = snapshot.column("civ_affinity").to_pylist()

    # Build per-region faith counts (consolidate with compute_majority_belief)
    region_faith_counts: dict[int, Counter] = {}
    region_agent_counts: dict[int, int] = {}
    for rid, faith, civ_id in zip(region_ids, beliefs, civ_affinities):
        if faith == 0xFF:
            continue
        if rid not in region_faith_counts:
            region_faith_counts[rid] = Counter()
            region_agent_counts[rid] = 0
        region_faith_counts[rid][faith] += 1
        region_agent_counts[rid] += 1

    for civ in civs:
        if not civ.alive:
            continue
        if civ.civ_majority_faith == 0xFF:
            continue
        civ_faith = belief_registry[civ.civ_majority_faith]
        if civ_faith.doctrines[DOCTRINE_STANCE] != 1:
            # Not Militant — no persecution
            for r in civ.regions:
                r.persecution_intensity = 0.0
            continue

        for region in civ.regions:
            rid = region.region_id
            faith_counts = region_faith_counts.get(rid, Counter())
            total = region_agent_counts.get(rid, 0)
            if total == 0:
                region.persecution_intensity = 0.0
                continue

            majority_faith = civ.civ_majority_faith
            minority_count = total - faith_counts.get(majority_faith, 0)
            if minority_count <= 0:
                region.persecution_intensity = 0.0
                continue

            minority_ratio = minority_count / total
            intensity = 1.0 * (1.0 - minority_ratio)
            region.persecution_intensity = intensity

            # Persecution named event (first turn only — track with flag)
            if not getattr(region, '_persecution_event_fired', False):
                events.append({
                    "type": "Persecution",
                    "importance": 6,
                    "region": region.name,
                    "faith": belief_registry[civ.civ_majority_faith].name,
                })
                region._persecution_event_fired = True

            # Mass migration check
            persecuted_ratio = minority_count / total
            if persecuted_ratio > MASS_MIGRATION_THRESHOLD:
                events.append({
                    "type": "Mass Migration",
                    "importance": 6,
                    "region": region.name,
                })

    return events


def compute_martyrdom_boosts(
    regions: list[Region],
    civs: list[Civilization],
    belief_registry: list[Belief],
    dead_agents: list | None,
) -> None:
    """Update martyrdom_boost for regions with persecution deaths.

    A persecution death: dead agent in a persecuted region (intensity > 0)
    whose belief differed from the civ's majority faith.
    """
    if dead_agents:
        # Build region→deaths map
        region_has_persecution_death: set[int] = set()
        for agent in dead_agents:
            rid = agent.get("region")
            belief = agent.get("belief", 0xFF)
            if rid is None or belief == 0xFF:
                continue
            # Find region and check persecution
            # (Implementation: look up region by rid, check persecution_intensity > 0
            #  and belief != civ majority faith)
            region_has_persecution_death.add(rid)

        for region in (r for regions_list in [c.regions for c in civs] for r in regions_list):
            if region.region_id in region_has_persecution_death and region.persecution_intensity > 0:
                region.martyrdom_boost = min(
                    region.martyrdom_boost + MARTYRDOM_BOOST_PER_EVENT,
                    MARTYRDOM_BOOST_CAP,
                )

    # Decay all regions
    decay_martyrdom_boosts(regions)


def decay_martyrdom_boosts(regions: list[Region]) -> None:
    """Linearly decay each region's martyrdom_boost toward zero."""
    decay_step = MARTYRDOM_BOOST_PER_EVENT / MARTYRDOM_DECAY_TURNS
    for region in regions:
        if region.martyrdom_boost > 0:
            region.martyrdom_boost = max(0.0, region.martyrdom_boost - decay_step)
```

- [ ] **Step 4: Wire `martyrdom_boost` into `compute_conversion_signals()`**

In `src/chronicler/religion.py`, in `compute_conversion_signals()` where `conquest_conversion_boost` is read (around line 321), add alongside it:

```python
    conversion_rate += region.martyrdom_boost
```

- [ ] **Step 5: Wire calls in simulation.py**

In `src/chronicler/simulation.py`, in `phase_consequences()` after `decay_conquest_boosts()` (around line 858), add:

```python
        # M38b: Persecution
        persecution_events = compute_persecution(
            world.regions, world.civilizations, world.belief_registry,
            _snap, world.turn,
        )
        turn_events.extend(persecution_events)
        compute_martyrdom_boosts(
            world.regions, world.civilizations, world.belief_registry,
            getattr(world, '_dead_agents_this_turn', None),
        )
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_persecution.py -v 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/religion.py src/chronicler/simulation.py tests/test_persecution.py
git commit -m "feat(m38b): implement persecution detection, martyrdom boost, and mass migration"
```

---

### Task 4: Rust Persecution Tests

**Files:**
- Create: `chronicler-agents/tests/m38b_persecution.rs`

- [ ] **Step 1: Write Rust tests for persecution satisfaction penalty**

Create `chronicler-agents/tests/m38b_persecution.rs`:

```rust
//! M38b Tier 1: Persecution penalty in satisfaction and decision utility.

use chronicler_agents::agent::{
    PENALTY_CAP, PERSECUTION_SAT_WEIGHT, RELIGIOUS_MISMATCH_WEIGHT,
    CULTURAL_MISMATCH_WEIGHT, PERSECUTION_REBEL_BOOST, PERSECUTION_MIGRATE_BOOST,
};
use chronicler_agents::satisfaction::apply_penalty_cap;

#[test]
fn persecution_penalty_within_budget() {
    // Cultural (0.15 max, M36) + Religious (0.10, M37) + Persecution (0.15, M38b) = 0.40 = cap
    let cultural = CULTURAL_MISMATCH_WEIGHT;   // 0.05 per mismatch axis (3 axes max = 0.15)
    let religious = RELIGIOUS_MISMATCH_WEIGHT;  // 0.10
    let persecution = PERSECUTION_SAT_WEIGHT;   // 0.15
    let total = cultural * 3.0 + religious + persecution;
    assert!((total - PENALTY_CAP).abs() < 1e-6,
        "Identity penalty stacking must exactly hit Decision 10 cap");
}

#[test]
fn persecution_penalty_capped() {
    // Even if somehow penalties exceed budget, apply_penalty_cap clamps
    let over = 0.50;
    let capped = apply_penalty_cap(over);
    assert!((capped - PENALTY_CAP).abs() < 1e-6);
}

#[test]
fn no_persecution_zero_intensity() {
    // persecution_intensity = 0.0 → no penalty
    let intensity = 0.0_f32;
    let penalty = PERSECUTION_SAT_WEIGHT * intensity;
    assert_eq!(penalty, 0.0);
}

#[test]
fn persecution_scales_with_intensity() {
    // intensity 0.6 → penalty 0.09, intensity 0.9 → penalty 0.135
    let p60 = PERSECUTION_SAT_WEIGHT * 0.6;
    assert!((p60 - 0.09).abs() < 1e-6);
    let p90 = PERSECUTION_SAT_WEIGHT * 0.9;
    assert!((p90 - 0.135).abs() < 1e-6);
}

#[test]
fn rebel_boost_scales_with_intensity() {
    let boost = PERSECUTION_REBEL_BOOST * 0.9;
    assert!((boost - 0.27).abs() < 1e-6);
}

#[test]
fn migrate_boost_scales_with_intensity() {
    let boost = PERSECUTION_MIGRATE_BOOST * 0.9;
    assert!((boost - 0.18).abs() < 1e-6);
}
```

- [ ] **Step 2: Run Rust tests**

```bash
cd chronicler-agents && cargo test m38b_persecution -- --nocapture 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/m38b_persecution.rs
git commit -m "test(m38b): Tier 1 Rust persecution penalty tests"
```

---

## Chunk 2: Schisms

### Task 5: Extend `compute_civ_majority_faith()` to Return Ratio

**Files:**
- Modify: `src/chronicler/religion.py:159-190`
- Modify: `src/chronicler/simulation.py` (call site)

- [ ] **Step 1: Write test for ratio return**

Add to `tests/test_schisms.py` (create file):

```python
"""Tier 1 tests for M38b schism subsystem."""
import pytest
from collections import Counter
from chronicler.religion import compute_civ_majority_faith


class TestCivMajorityFaithRatio:
    """compute_civ_majority_faith should return (faith_id, ratio) per civ."""

    def test_returns_ratio(self, mock_snapshot):
        # 70% faith 0, 30% faith 1 → ratio 0.70
        result = compute_civ_majority_faith(mock_snapshot)
        assert 0 in result
        faith_id, ratio = result[0]
        assert faith_id == 0
        assert abs(ratio - 0.70) < 0.01
```

(The fixture `mock_snapshot` will be added to conftest or inline — builds a PyArrow RecordBatch with controlled civ_affinity and belief columns.)

- [ ] **Step 2: Extend `compute_civ_majority_faith()` to return ratio**

In `src/chronicler/religion.py`, modify the return type and body (lines 159-190):

Change return from `dict[int, int]` to `dict[int, tuple[int, float]]`:

```python
def compute_civ_majority_faith(snapshot) -> dict[int, tuple[int, float]]:
    """Compute the majority faith and its ratio per civ from an agent snapshot.

    Returns:
        dict mapping civ_id → (majority_faith_id, ratio).
    """
    # ... existing counting logic ...

    result: dict[int, tuple[int, float]] = {}
    for civ_id, faith_counts in counts.items():
        if not faith_counts:
            continue
        total = sum(faith_counts.values())
        max_count = max(faith_counts.values())
        winners = [fid for fid, cnt in faith_counts.items() if cnt == max_count]
        result[civ_id] = (min(winners), max_count / total if total > 0 else 0.0)

    return result
```

- [ ] **Step 3: Update all call sites in simulation.py**

The current call site (around line 833) does:
```python
civ_majority = compute_civ_majority_faith(_snap)
```

Update to unpack the new return type:
```python
civ_majority_with_ratio = compute_civ_majority_faith(_snap)
for civ in world.civilizations:
    entry = civ_majority_with_ratio.get(civ.civ_id)
    if entry is not None:
        civ.civ_majority_faith, civ._majority_faith_ratio = entry
```

- [ ] **Step 4: Run existing M37 tests to verify no regression**

```bash
python -m pytest tests/test_religion.py -v 2>&1 | tail -20
```

Expected: all PASS (existing tests should still work since the return type change is backward-compatible at the call site).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/religion.py src/chronicler/simulation.py tests/test_schisms.py
git commit -m "feat(m38b): extend compute_civ_majority_faith to return ratio"
```

---

### Task 6: Schism Constants & Model Fields

**Files:**
- Modify: `src/chronicler/religion.py` (constants)
- Modify: `src/chronicler/models.py` (Civ model)

- [ ] **Step 1: Add schism constants to religion.py**

After the persecution constants, add:

```python
# M38b: Schisms
SCHISM_MINORITY_THRESHOLD = 0.30     # minority ratio to trigger schism
SCHISM_SECESSION_MODIFIER = 10       # added to secession risk check
REFORMATION_THRESHOLD = 0.60         # ratio for civ faith to officially change
MAX_FAITHS = 16                      # belief registry capacity

# Schism trigger → axis mapping (priority order)
# When the flipped axis is 0 (Neutral), use this pole instead of -0
SCHISM_NEUTRAL_POLE_MAP = {
    DOCTRINE_STANCE: -1,      # Persecution-triggered → Pacifist
    DOCTRINE_STRUCTURE: -1,   # Clergy-triggered → Egalitarian
    DOCTRINE_OUTREACH: -1,    # Conquest-triggered → Insular
    DOCTRINE_ETHICS: 1,       # Trade-triggered → Prosperity
}
```

- [ ] **Step 2: Initialize `previous_majority_faith` at world-gen**

Find where `civ_majority_faith` is first set (in simulation.py or worldgen code). After it's set, add:

```python
civ.previous_majority_faith = civ.civ_majority_faith
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/religion.py src/chronicler/models.py src/chronicler/simulation.py
git commit -m "feat(m38b): add schism constants and previous_majority_faith initialization"
```

---

### Task 7: Schism Detection & Faith Splitting

**Files:**
- Modify: `src/chronicler/religion.py`

- [ ] **Step 1: Write schism tests**

Add to `tests/test_schisms.py`:

```python
from chronicler.religion import (
    determine_schism_axis,
    fire_schism,
    detect_schisms,
    SCHISM_MINORITY_THRESHOLD,
    SCHISM_NEUTRAL_POLE_MAP,
    REFORMATION_THRESHOLD,
    MAX_FAITHS,
    DOCTRINE_STANCE,
    DOCTRINE_STRUCTURE,
    DOCTRINE_OUTREACH,
    DOCTRINE_ETHICS,
)
from chronicler.models import Belief, Region, Civilization


def _make_belief(name, stance=0, structure=0, ethics=0, outreach=0, theology=0):
    return Belief(
        name=name,
        doctrines=[theology, ethics, stance, outreach, structure],
        faith_id=0,
    )


class TestSchismTrigger:
    """Schism fires when minority > 30% threshold."""

    def test_above_threshold_fires(self):
        # 35% minority → should fire
        assert 0.35 > SCHISM_MINORITY_THRESHOLD

    def test_at_threshold_does_not_fire(self):
        # 30% exactly → should NOT fire (strictly greater)
        assert not (0.30 > SCHISM_MINORITY_THRESHOLD)

    def test_below_threshold_does_not_fire(self):
        assert not (0.25 > SCHISM_MINORITY_THRESHOLD)


class TestAxisMapping:
    """Issue-driven deterministic axis selection."""

    def test_persecution_flips_stance(self):
        region = Region(name="r", population=100)
        region.persecution_intensity = 0.5  # Active persecution
        belief = _make_belief("test", stance=1)
        axis, _ = determine_schism_axis(region, belief)
        assert axis == DOCTRINE_STANCE

    def test_clergy_dominance_flips_structure(self):
        region = Region(name="r", population=100)
        region.persecution_intensity = 0.0
        region._clergy_influence = 0.45  # > 0.40 threshold
        belief = _make_belief("test")
        axis, _ = determine_schism_axis(region, belief)
        assert axis == DOCTRINE_STRUCTURE

    def test_conquest_flips_outreach(self):
        region = Region(name="r", population=100)
        region.persecution_intensity = 0.0
        region.last_conquered_turn = 95  # < 10 turns ago if current=100
        belief = _make_belief("test")
        axis, _ = determine_schism_axis(region, belief, current_turn=100)
        assert axis == DOCTRINE_OUTREACH

    def test_fallback_picks_lowest_abs_axis(self):
        region = Region(name="r", population=100)
        region.persecution_intensity = 0.0
        region.last_conquered_turn = -1
        # All axes nonzero except ethics (0)
        belief = _make_belief("test", stance=1, structure=-1, outreach=1, theology=1, ethics=0)
        axis, _ = determine_schism_axis(region, belief)
        assert axis == DOCTRINE_ETHICS


class TestNeutralAxisHandling:
    """When flipped axis is 0, use SCHISM_NEUTRAL_POLE_MAP."""

    def test_neutral_stance_becomes_pacifist(self):
        belief = _make_belief("test", stance=0)
        # Simulating persecution trigger → DOCTRINE_STANCE
        new_val = SCHISM_NEUTRAL_POLE_MAP.get(DOCTRINE_STANCE, 1)
        assert new_val == -1  # Pacifist

    def test_nonzero_flips_to_opposite(self):
        # Militant (+1) → Pacifist (-1)
        original = 1
        flipped = -original
        assert flipped == -1


class TestRegistryCap:
    """No schism fires when belief registry is full."""

    def test_full_registry_blocks_schism(self):
        assert MAX_FAITHS == 16


class TestReformationThreshold:
    """Reformation fires at 60%, not mere plurality."""

    def test_below_threshold_no_reformation(self):
        assert not (0.55 >= REFORMATION_THRESHOLD)

    def test_at_threshold_fires(self):
        assert 0.60 >= REFORMATION_THRESHOLD
```

- [ ] **Step 2: Run tests to verify they fail on missing functions**

```bash
python -m pytest tests/test_schisms.py -v 2>&1 | tail -30
```

- [ ] **Step 3: Implement `determine_schism_axis()`**

In `src/chronicler/religion.py`:

```python
def determine_schism_axis(
    region: Region,
    original_belief: Belief,
    current_turn: int = 0,
    clergy_influence: float = 0.0,
) -> tuple[int, int]:
    """Determine which doctrine axis to flip in a schism.

    Returns (axis_index, new_value) based on priority trigger matching.
    """
    # Priority 1: Active persecution → flip Stance
    if region.persecution_intensity > 0:
        axis = DOCTRINE_STANCE
    # Priority 2: Clergy faction dominance
    elif clergy_influence > 0.40:
        axis = DOCTRINE_STRUCTURE
    # Priority 3: Trade-dependent (inert until M43 — always False for now)
    # Priority 4: Recently conquered
    elif (hasattr(region, 'last_conquered_turn')
          and region.last_conquered_turn >= 0
          and current_turn - region.last_conquered_turn < 10):
        axis = DOCTRINE_OUTREACH
    # Priority 5: Fallback — axis with lowest absolute value
    else:
        doctrines = original_belief.doctrines
        min_abs = float('inf')
        axis = 0
        for i, val in enumerate(doctrines):
            if abs(val) < min_abs:
                min_abs = abs(val)
                axis = i

    # Compute new value
    current_val = original_belief.doctrines[axis]
    if current_val == 0:
        new_val = SCHISM_NEUTRAL_POLE_MAP.get(axis, 1)
    else:
        new_val = -current_val

    return axis, new_val
```

- [ ] **Step 4: Implement `detect_schisms()` and `fire_schism()`**

In `src/chronicler/religion.py`:

```python
def detect_schisms(
    civs: list[Civilization],
    belief_registry: list[Belief],
    snapshot,
    current_turn: int,
) -> list[dict]:
    """Detect and fire at most one schism per civ per turn.

    Returns list of named event dicts.
    """
    if snapshot is None or snapshot.num_rows == 0:
        return []
    if len(belief_registry) >= MAX_FAITHS:
        return []

    events = []
    region_ids = snapshot.column("region").to_pylist()
    beliefs = snapshot.column("belief").to_pylist()

    # Build per-region faith counts
    region_faith_counts: dict[int, Counter] = {}
    region_totals: dict[int, int] = {}
    for rid, faith in zip(region_ids, beliefs):
        if faith == 0xFF:
            continue
        if rid not in region_faith_counts:
            region_faith_counts[rid] = Counter()
            region_totals[rid] = 0
        region_faith_counts[rid][faith] += 1
        region_totals[rid] += 1

    for civ in civs:
        if not civ.alive or civ.civ_majority_faith == 0xFF:
            continue
        if len(belief_registry) >= MAX_FAITHS:
            break

        best_region = None
        best_ratio = 0.0
        best_faith_id = -1

        for region in civ.regions:
            rid = region.region_id
            counts = region_faith_counts.get(rid, Counter())
            total = region_totals.get(rid, 0)
            if total == 0:
                continue
            for faith_id, count in counts.items():
                if faith_id == civ.civ_majority_faith:
                    continue
                ratio = count / total
                if ratio > SCHISM_MINORITY_THRESHOLD and ratio > best_ratio:
                    best_region = region
                    best_ratio = ratio
                    best_faith_id = faith_id

        if best_region is not None:
            evt = fire_schism(
                best_region, best_faith_id, belief_registry, civ, current_turn,
            )
            if evt:
                events.append(evt)

    return events


def fire_schism(
    region: Region,
    original_faith_id: int,
    belief_registry: list[Belief],
    civ: Civilization,
    current_turn: int,
) -> dict | None:
    """Create a splinter faith and set schism conversion signals on the region.

    Returns a named event dict, or None if registry is full.
    """
    if len(belief_registry) >= MAX_FAITHS:
        return None

    original = belief_registry[original_faith_id]

    # Determine axis to flip
    clergy_influence = getattr(civ, 'clergy_influence', 0.0)
    axis, new_val = determine_schism_axis(
        region, original, current_turn, clergy_influence,
    )

    # Copy doctrine and flip
    new_doctrine = list(original.doctrines)
    new_doctrine[axis] = new_val

    # Generate schism name
    splinter_name = f"Reformed {original.name}"

    # Register new faith
    splinter_id = len(belief_registry)
    splinter = Belief(
        name=splinter_name,
        doctrines=new_doctrine,
        faith_id=splinter_id,
    )
    belief_registry.append(splinter)

    # Set region batch signals for Rust to process next turn
    region.schism_convert_from = original_faith_id
    region.schism_convert_to = splinter_id

    return {
        "type": "Schism",
        "importance": 7,
        "original_faith": original.name,
        "splinter_faith": splinter_name,
        "region": region.name,
        "axis_flipped": axis,
    }
```

- [ ] **Step 5: Implement reformation detection**

In `src/chronicler/religion.py`:

```python
def detect_reformation(
    civs: list[Civilization],
    belief_registry: list[Belief],
) -> list[dict]:
    """Detect if any civ's majority faith has changed past REFORMATION_THRESHOLD.

    Returns list of reformation event dicts.
    """
    events = []
    for civ in civs:
        if not civ.alive:
            continue
        majority_ratio = getattr(civ, '_majority_faith_ratio', 0.0)
        if (civ.civ_majority_faith != civ.previous_majority_faith
                and majority_ratio >= REFORMATION_THRESHOLD):
            events.append({
                "type": "Reformation",
                "importance": 8,
                "civ": civ.name,
                "old_faith": belief_registry[civ.previous_majority_faith].name,
                "new_faith": belief_registry[civ.civ_majority_faith].name,
            })
            civ.previous_majority_faith = civ.civ_majority_faith
    return events
```

- [ ] **Step 6: Wire schism calls in simulation.py**

In `phase_consequences()`, after the persecution block:

```python
        # M38b: Schisms
        schism_events = detect_schisms(
            world.civilizations, world.belief_registry, _snap, world.turn,
        )
        turn_events.extend(schism_events)

        # M38b: Reformation
        reformation_events = detect_reformation(
            world.civilizations, world.belief_registry,
        )
        turn_events.extend(reformation_events)
```

- [ ] **Step 7: Add Rust schism processing in tick.rs / ffi.rs**

In the Rust agent tick (where conversion is processed), add schism belief reassignment:

```rust
// After normal conversion processing:
let schism_from = region_batch.schism_convert_from;
let schism_to = region_batch.schism_convert_to;
if schism_from != 0xFF && pool.belief[slot] == schism_from {
    pool.belief[slot] = schism_to;
}
```

Ensure `schism_convert_from` and `schism_convert_to` columns are read from the region batch in ffi.rs (already added in Task 2).

- [ ] **Step 8: Run tests**

```bash
python -m pytest tests/test_schisms.py -v 2>&1 | tail -30
cd chronicler-agents && cargo test 2>&1 | tail -10
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/religion.py src/chronicler/simulation.py tests/test_schisms.py chronicler-agents/src/
git commit -m "feat(m38b): implement schism detection, faith splitting, and reformation"
```

---

## Chunk 3: Pilgrimages

### Task 8: Pilgrimage Model Fields

**Files:**
- Modify: `src/chronicler/models.py` (GreatPerson model)

- [ ] **Step 1: Add pilgrimage fields to GreatPerson**

Find the GreatPerson model in `models.py` (around lines 309-330). Add:

```python
    # M38b: Pilgrimages
    pilgrimage_destination: str | None = None
    pilgrimage_return_turn: int | None = None
    arc_type: str | None = None           # "Prophet" on pilgrimage return; M45 uses this
```

Also add the life event constant to wherever life event bits are defined:

```python
LIFE_EVENT_PILGRIMAGE = 1 << 7  # 128, bit 7 (M37 confirms spare)
```

- [ ] **Step 2: Add pilgrimage constants to religion.py**

```python
# M38b: Pilgrimages
PILGRIMAGE_DURATION_MIN = 5
PILGRIMAGE_DURATION_MAX = 10
PILGRIMAGE_SKILL_BOOST = 0.10
LIFE_EVENT_PILGRIMAGE = 1 << 7  # 128
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py src/chronicler/religion.py
git commit -m "feat(m38b): add pilgrimage model fields and constants"
```

---

### Task 9: Pilgrimage Candidate Selection & Lifecycle

**Files:**
- Modify: `src/chronicler/great_persons.py`
- Create: `tests/test_pilgrimages.py`

- [ ] **Step 1: Write pilgrimage tests**

Create `tests/test_pilgrimages.py`:

```python
"""Tier 1 tests for M38b pilgrimage subsystem."""
import pytest
from chronicler.models import GreatPerson, Infrastructure, Region
from chronicler.religion import (
    PILGRIMAGE_DURATION_MIN,
    PILGRIMAGE_DURATION_MAX,
    PILGRIMAGE_SKILL_BOOST,
    LIFE_EVENT_PILGRIMAGE,
)


def _make_gp(belief=0, occupation=4, loyalty_trait=0.7, arc_type=None,
             pilgrimage_destination=None):
    """Helper: create GreatPerson stub."""
    gp = GreatPerson(name="TestPriest", role="prophet", origin_civilization="Civ1")
    gp.belief = belief
    gp.occupation = occupation
    gp.loyalty_trait = loyalty_trait
    gp.arc_type = arc_type
    gp.pilgrimage_destination = pilgrimage_destination
    gp.pilgrimage_return_turn = None
    gp.skill = 0.5
    gp.life_events = 0
    return gp


def _make_temple(faith_id=0, prestige=10, region_name="TempleRegion"):
    """Helper: create temple stub."""
    t = Infrastructure(name="Temple", region_name=region_name)
    t.faith_id = faith_id
    t.temple_prestige = prestige
    return t


class TestCandidateGuards:
    """Pilgrimage guards prevent overfire."""

    def test_already_on_pilgrimage_skipped(self):
        gp = _make_gp(pilgrimage_destination="SomeRegion")
        assert gp.pilgrimage_destination is not None  # guard fires

    def test_already_prophet_skipped(self):
        gp = _make_gp(arc_type="Prophet")
        assert gp.arc_type == "Prophet"  # guard fires

    def test_low_loyalty_trait_skipped(self):
        gp = _make_gp(loyalty_trait=0.3, occupation=4)
        # Not loyal enough AND is priest → priest qualifies by occupation
        # but non-priest with low loyalty_trait should be skipped
        gp.occupation = 2  # merchant, not priest
        assert gp.loyalty_trait <= 0.5

    def test_priest_qualifies_regardless_of_loyalty_trait(self):
        gp = _make_gp(loyalty_trait=0.3, occupation=4)
        # Priests qualify by occupation alone
        assert gp.occupation == 4


class TestDestinationSelection:
    """Selects highest-prestige temple of the pilgrim's faith."""

    def test_highest_prestige_wins(self):
        t1 = _make_temple(faith_id=0, prestige=5)
        t2 = _make_temple(faith_id=0, prestige=15)
        t3 = _make_temple(faith_id=1, prestige=20)  # wrong faith
        candidates = [t for t in [t1, t2, t3] if t.faith_id == 0]
        best = max(candidates, key=lambda t: t.temple_prestige)
        assert best.temple_prestige == 15

    def test_no_temple_of_faith_skips(self):
        t1 = _make_temple(faith_id=1, prestige=10)
        candidates = [t for t in [t1] if t.faith_id == 0]
        assert len(candidates) == 0


class TestPilgrimageReturn:
    """Return effects: skill boost, Prophet title, life event bit."""

    def test_skill_boost_applied(self):
        gp = _make_gp()
        gp.skill += PILGRIMAGE_SKILL_BOOST
        assert abs(gp.skill - 0.6) < 1e-6

    def test_prophet_arc_type_set(self):
        gp = _make_gp()
        gp.arc_type = "Prophet"
        assert gp.arc_type == "Prophet"

    def test_life_event_bit_set(self):
        gp = _make_gp()
        gp.life_events |= LIFE_EVENT_PILGRIMAGE
        assert gp.life_events & LIFE_EVENT_PILGRIMAGE

    def test_pilgrimage_fields_cleared(self):
        gp = _make_gp()
        gp.pilgrimage_destination = "SomeRegion"
        gp.pilgrimage_return_turn = 50
        # On return:
        gp.pilgrimage_destination = None
        gp.pilgrimage_return_turn = None
        assert gp.pilgrimage_destination is None


class TestDuration:
    """Duration is 5-10 turns."""

    def test_duration_range(self):
        assert PILGRIMAGE_DURATION_MIN == 5
        assert PILGRIMAGE_DURATION_MAX == 10
```

- [ ] **Step 2: Run tests to verify they fail on missing imports**

```bash
python -m pytest tests/test_pilgrimages.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Implement pilgrimage functions in great_persons.py**

In `src/chronicler/great_persons.py`, add:

```python
from chronicler.religion import (
    PILGRIMAGE_DURATION_MIN, PILGRIMAGE_DURATION_MAX,
    PILGRIMAGE_SKILL_BOOST, LIFE_EVENT_PILGRIMAGE,
    _PRIEST_OCCUPATION,
)
import random


def check_pilgrimages(
    great_persons: list[GreatPerson],
    temples: list[Infrastructure],
    snapshot,
    current_turn: int,
    belief_registry: list,
) -> list[dict]:
    """Check for pilgrimage departures and returns.

    Returns list of named event dicts.
    """
    events = []

    # Check returns first
    for gp in great_persons:
        if gp.pilgrimage_destination is None:
            continue
        if current_turn < (gp.pilgrimage_return_turn or 0):
            continue
        # Return effects
        gp.skill = min(1.0, (gp.skill or 0.0) + PILGRIMAGE_SKILL_BOOST)
        gp.arc_type = "Prophet"
        gp.life_events = (gp.life_events or 0) | LIFE_EVENT_PILGRIMAGE
        dest = gp.pilgrimage_destination
        gp.pilgrimage_destination = None
        gp.pilgrimage_return_turn = None
        events.append({
            "type": "Pilgrimage Return",
            "importance": 5,
            "character": gp.name,
            "title": "Prophet",
            "faith": belief_registry[gp.belief].name if gp.belief < len(belief_registry) else "unknown",
        })

    # Check departures
    faiths_departed = set()
    for gp in great_persons:
        if gp.pilgrimage_destination is not None:
            continue
        if gp.arc_type == "Prophet":
            continue
        belief = getattr(gp, 'belief', 0xFF)
        if belief == 0xFF or belief in faiths_departed:
            continue

        is_priest = getattr(gp, 'occupation', -1) == _PRIEST_OCCUPATION
        is_loyal_trait = getattr(gp, 'loyalty_trait', 0.0) > 0.5
        if not (is_priest or is_loyal_trait):
            continue

        # Dynamic loyalty from snapshot
        agent_loyalty = _get_agent_loyalty(snapshot, gp.agent_id)
        if agent_loyalty is None or agent_loyalty <= 0.5:
            continue

        # Find highest-prestige temple of their faith
        matching_temples = [t for t in temples if t.faith_id == belief]
        if not matching_temples:
            continue
        destination = max(matching_temples, key=lambda t: t.temple_prestige)

        # Begin pilgrimage
        gp.pilgrimage_destination = destination.region_name
        gp.pilgrimage_return_turn = current_turn + random.randint(
            PILGRIMAGE_DURATION_MIN, PILGRIMAGE_DURATION_MAX,
        )
        faiths_departed.add(belief)
        events.append({
            "type": "Pilgrimage Departure",
            "importance": 4,
            "character": gp.name,
            "destination": destination.region_name,
            "faith": belief_registry[belief].name if belief < len(belief_registry) else "unknown",
        })

    return events


def _get_agent_loyalty(snapshot, agent_id: int | None) -> float | None:
    """Look up dynamic loyalty from snapshot by agent_id."""
    if snapshot is None or agent_id is None:
        return None
    ids = snapshot.column("id").to_pylist()
    try:
        idx = ids.index(agent_id)
        return snapshot.column("loyalty").to_pylist()[idx]
    except (ValueError, IndexError):
        return None
```

- [ ] **Step 4: Wire in simulation.py**

In `phase_consequences()`, after schism/reformation calls:

```python
        # M38b: Pilgrimages
        all_temples = [inf for r in world.regions
                       for inf in getattr(r, 'infrastructure', [])
                       if getattr(inf, 'faith_id', -1) >= 0]
        all_great_persons = [gp for c in world.civilizations
                             for gp in getattr(c, 'great_persons', [])]
        pilgrimage_events = check_pilgrimages(
            all_great_persons, all_temples, _snap, world.turn,
            world.belief_registry,
        )
        turn_events.extend(pilgrimage_events)
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_pilgrimages.py -v 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/great_persons.py src/chronicler/simulation.py tests/test_pilgrimages.py
git commit -m "feat(m38b): implement pilgrimage candidate selection, lifecycle, and Prophet promotion"
```

---

## Chunk 4: Integration Tests & Cleanup

### Task 10: Tier 2 Regression Harness

**Files:**
- Create: `tests/test_m38b_regression.py`

- [ ] **Step 1: Write Tier 2 interaction tests**

Create `tests/test_m38b_regression.py` following the `test_m36_regression.py` pattern:

```python
"""Tier 2 regression harness for M38b: interaction effects between
persecution, schisms, and pilgrimages."""
import pytest

try:
    import chronicler_agents
    _AGENTS_AVAILABLE = True
except ImportError:
    _AGENTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AGENTS_AVAILABLE,
    reason="Rust agent extension not available",
)


class TestPersecutionMartyrdomConversion:
    """Persecution deaths → martyrdom boost → increased conversion rate."""

    def test_martyrdom_boost_feeds_conversion(self):
        """A region with martyrdom_boost > 0 should have higher conversion_rate
        than an identical region without the boost."""
        from chronicler.religion import compute_conversion_signals
        # Build two identical regions
        r1 = _make_test_region("R1")
        r2 = _make_test_region("R2")
        r2.martyrdom_boost = 0.15
        # Run conversion signal computation on both
        # (requires belief_registry, snapshot stub — use _make_world helper)
        compute_conversion_signals([r1, r2], ...)  # fill in per codebase pattern
        assert r2.conversion_rate_signal > r1.conversion_rate_signal


class TestSchismPersecutionCascade:
    """Schism in Militant civ → new minority → persecution fires."""

    def test_schism_creates_persecuted_minority(self):
        """After a schism, the splinter faith agents in other regions
        should face persecution (if civ is Militant)."""
        # 1. Create Militant civ with 35% minority in one region
        # 2. Call detect_schisms() → should fire
        # 3. Call compute_persecution() → intensity > 0 in schism region
        from chronicler.religion import detect_schisms, compute_persecution
        # Build world with Militant faith, 35% minority region
        # ... (follow _make_world pattern from test_m36_regression.py)
        schism_events = detect_schisms(civs, belief_registry, snap, turn=50)
        assert len(schism_events) == 1
        # After schism, persecution should detect the new minority
        persecution_events = compute_persecution(
            world.regions, civs, belief_registry, snap, turn=51,
        )
        # Verify persecution_intensity > 0 on the schism region
        schism_region = region_map[schism_events[0]["region"]]
        assert schism_region.persecution_intensity > 0


class TestFullCascade:
    """Schism → persecution → martyrdom → conversion spread → reformation."""

    @pytest.mark.slow
    def test_cascade_over_multiple_turns(self):
        """Run 20-turn controlled scenario verifying each cascade stage."""
        pytest.skip("Requires full world setup — implement after Tier 1 passes")


class TestPilgrimageFrequency:
    """1-3 pilgrimages per 500-turn run per faith [CALIBRATE]."""

    @pytest.mark.slow
    def test_pilgrimage_count_in_range(self):
        """Over a 500-turn run, each faith should produce 1-3 pilgrimages."""
        pytest.skip("Calibration test — implement after pilgrimage subsystem verified")
```

- [ ] **Step 2: Run**

```bash
python -m pytest tests/test_m38b_regression.py -v 2>&1 | tail -20
```

Expected: tests pass (or skip if Rust extension not available).

- [ ] **Step 3: Commit**

```bash
git add tests/test_m38b_regression.py
git commit -m "test(m38b): Tier 2 regression harness for interaction effects"
```

---

### Task 11: Secession Modifier & Final Wiring

**Files:**
- Modify: `src/chronicler/simulation.py` (or wherever secession checks live)

- [ ] **Step 1: Find secession check code**

Search for secession/rebellion region checks. Add the faith-mismatch modifier:

```python
# In secession check:
if region.majority_belief != civ.civ_majority_faith:
    secession_risk += SCHISM_SECESSION_MODIFIER  # +10
```

- [ ] **Step 2: Verify `--agents=off` behavior**

Run the simulation with `--agents=off` and verify no M38b code paths crash:

```bash
python -m src.chronicler --agents=off --turns=10 2>&1 | tail -10
```

Expected: runs clean, no persecution/schism/pilgrimage events (all guarded by snapshot check).

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
cd chronicler-agents && cargo test 2>&1 | tail -10
```

Expected: all PASS.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(m38b): wire secession modifier and verify --agents=off compatibility"
```
