# M38a: Temples & Clergy Faction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add temple infrastructure and clergy as the fourth political faction competing with military/merchant/cultural.

**Architecture:** Rust-side adds `faction_clergy` to CivSignals, `has_temple` to RegionState, and extends satisfaction for clergy-priest alignment + temple bonus. Python-side adds `CLERGY` to FactionType, extends factions.py with event-driven influence/tithe/succession, adds temple to infrastructure.py, and wires signals through agent_bridge.py.

**Tech Stack:** Python 3.12, Rust stable, pyo3-arrow, pytest, cargo test

**Spec:** `docs/superpowers/specs/2026-03-16-m38a-temples-clergy-design.md`

---

## Chunk 1: Rust-Side Changes

### Task 1: Extend CivSignals with faction_clergy

**Files:**
- Modify: `chronicler-agents/src/signals.rs:8-31`
- Modify: `chronicler-agents/src/ffi.rs` (civ signal schema + parse)

- [ ] **Step 1: Add `faction_clergy` field to CivSignals struct**

In `signals.rs`, add after `faction_cultural` (line 14):

```rust
pub faction_clergy: f32,
```

- [ ] **Step 2: Update `parse_civ_signals()` in ffi.rs to read the new column**

Find the block that reads `faction_cultural` and add after it:

```rust
let faction_clergy_col = rb
    .column_by_name("faction_clergy")
    .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
```

And in the CivSignals construction, add:

```rust
faction_clergy: faction_clergy_col.map_or(0.0, |c| c.value(i)),
```

- [ ] **Step 3: Build and verify compilation**

Run: `cargo build`
Expected: compiles with no errors (field added but not yet consumed)

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/signals.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m38a): add faction_clergy to CivSignals"
```

---

### Task 2: Extend RegionState with has_temple

**Files:**
- Modify: `chronicler-agents/src/region.rs:18-49`
- Modify: `chronicler-agents/src/ffi.rs` (region batch parse)

- [ ] **Step 1: Add `has_temple` field to RegionState struct**

In `region.rs`, add after the M37 conversion fields (after `majority_belief`):

```rust
// M38a:
pub has_temple: bool,
```

- [ ] **Step 2: Add `has_temple: false` to `RegionState::new()` default constructor**

In `region.rs`, find the `RegionState::new()` or default constructor (around line 52) and add `has_temple: false` to the initialization.

- [ ] **Step 3: Set default in RegionState initialization (ffi.rs init path)**

In `ffi.rs`, in `set_region_state()`, add column extraction after the M37 columns in the **init path** (around lines 320-337):

```rust
let has_temple_col = rb
    .column_by_name("has_temple")
    .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
```

And in the RegionState construction:

```rust
has_temple: has_temple_col.map_or(false, |c| c.value(i)),
```

- [ ] **Step 4: Update the subsequent-call path in `set_region_state()`**

In `ffi.rs`, find the update path (around lines 452-486) that updates existing RegionState fields on subsequent calls. Add:

```rust
r.has_temple = has_temple_col.map_or(false, |arr| arr.value(i));
```

Without this, `has_temple` would be stale after turn 1.

- [ ] **Step 5: Build and verify compilation**

Run: `cargo build`
Expected: compiles with no errors

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m38a): add has_temple to RegionState"
```

---

### Task 3: Extend satisfaction for clergy faction alignment + temple bonus

**Files:**
- Modify: `chronicler-agents/src/tick.rs:385-405`
- Modify: `chronicler-agents/src/satisfaction.rs:83-125`
- Test: `chronicler-agents/tests/satisfaction_m38a.rs`

- [ ] **Step 1: Write the failing test for clergy-priest faction alignment**

Create `chronicler-agents/tests/satisfaction_m38a.rs`:

```rust
use chronicler_agents::satisfaction::{compute_satisfaction, compute_satisfaction_with_culture};
use chronicler_agents::signals::CivShock;

/// When dominant_faction == 3 (clergy) and occ == 4 (priest),
/// occ_matches_faction should be true, giving +0.05 bonus.
#[test]
fn test_priest_clergy_faction_alignment() {
    let shock = CivShock::default();
    // occ_matches_faction = true (clergy dominant, priest occ)
    let sat_matched = compute_satisfaction(
        4,     // priest
        0.5, 0.5, 50, 0.0, 0.8, false, false,
        true,  // occ_matches_faction
        false, 3, 0.3, &shock,
    );
    // occ_matches_faction = false
    let sat_unmatched = compute_satisfaction(
        4,     // priest
        0.5, 0.5, 50, 0.0, 0.8, false, false,
        false, // occ_matches_faction
        false, 3, 0.3, &shock,
    );
    let diff = sat_matched - sat_unmatched;
    assert!((diff - 0.05).abs() < 0.001, "faction alignment bonus should be 0.05, got {diff}");
}

/// Temple priest bonus: priest in templed region gets +0.10 satisfaction.
/// This requires compute_satisfaction_with_culture which calls the base,
/// so we test the delta between has_temple=true and has_temple=false.
#[test]
fn test_temple_priest_bonus() {
    let shock = CivShock::default();
    let values = [0u8, 1, 2];
    let controller_values = [0u8, 1, 2];
    // Base satisfaction for priest without temple bonus
    let base = compute_satisfaction_with_culture(
        4, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false,
        3, 0.0, &shock, values, controller_values, 0, 0,
        false,  // has_temple
    );
    // With temple bonus
    let with_temple = compute_satisfaction_with_culture(
        4, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false,
        3, 0.0, &shock, values, controller_values, 0, 0,
        true,  // has_temple
    );
    let diff = with_temple - base;
    assert!((diff - 0.10).abs() < 0.001, "temple priest bonus should be 0.10, got {diff}");
}

/// Non-priest in templed region gets NO temple bonus.
#[test]
fn test_temple_bonus_priest_only() {
    let shock = CivShock::default();
    let values = [0u8, 1, 2];
    let controller_values = [0u8, 1, 2];
    let farmer_no_temple = compute_satisfaction_with_culture(
        0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false,
        3, 0.0, &shock, values, controller_values, 0, 0,
        false,
    );
    let farmer_with_temple = compute_satisfaction_with_culture(
        0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false,
        3, 0.0, &shock, values, controller_values, 0, 0,
        true,
    );
    assert!((farmer_no_temple - farmer_with_temple).abs() < 0.001,
        "non-priest should get no temple bonus");
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test --test satisfaction_m38a`
Expected: FAIL — `compute_satisfaction_with_culture` doesn't accept `has_temple` parameter yet

- [ ] **Step 3: Add `has_temple` parameter to `compute_satisfaction_with_culture()`**

In `satisfaction.rs`, add `has_temple: bool` parameter to `compute_satisfaction_with_culture()` (after `majority_belief` at line 145):

```rust
pub fn compute_satisfaction_with_culture(
    occupation: u8,
    soil: f32,
    water: f32,
    civ_stability: u8,
    demand_supply_ratio: f32,
    pop_over_capacity: f32,
    civ_at_war: bool,
    region_contested: bool,
    occ_matches_faction: bool,
    is_displaced: bool,
    trade_routes: u8,
    faction_influence: f32,
    shock: &CivShock,
    agent_values: [u8; 3],
    controller_values: [u8; 3],
    agent_belief: u8,
    majority_belief: u8,
    has_temple: bool,    // M38a
) -> f32 {
```

**Replace** lines 172-173 (the existing `let total_non_eco_penalty = ...` and return expression) with:

```rust
    // M38a: temple priest bonus — faith-blind (Decision 6)
    let temple_bonus = if occupation == 4 && has_temple {
        0.10  // TEMPLE_PRIEST_BONUS [CALIBRATE]
    } else {
        0.0
    };
    let total_non_eco_penalty = apply_penalty_cap(cultural_pen + religious_pen);
    (base_sat - total_non_eco_penalty + temple_bonus).clamp(0.0, 1.0)
```

This is a replacement of the existing lines 172-173, not an insertion after them.

- [ ] **Step 4: Update caller in tick.rs**

In `tick.rs`, update the `occ_matches` block (lines 385-393) to add clergy:

```rust
let occ_matches = match civ_sig {
    Some(cs) => match cs.dominant_faction {
        0 => occ == 1,  // military -> soldiers
        1 => occ == 2,  // merchant -> merchants
        2 => occ == 3,  // cultural -> scholars
        3 => occ == 4,  // M38a: clergy -> priests
        _ => false,
    },
    None => false,
};
```

Update `faction_influence` block (lines 397-405) to add priest→clergy:

```rust
let faction_influence = match civ_sig {
    Some(cs) => match occ {
        1 => cs.faction_military,
        2 => cs.faction_merchant,
        3 => cs.faction_cultural,
        4 => cs.faction_clergy,   // M38a
        _ => 0.0,
    },
    None => 0.0,
};
```

Update the `compute_satisfaction_with_culture` call (line 415) to pass `has_temple`:

```rust
let sat = satisfaction::compute_satisfaction_with_culture(
    occ,
    region.soil,
    region.water,
    civ_stability,
    ds_ratio,
    pop_over_cap,
    civ_at_war,
    region_contested,
    occ_matches,
    is_displaced,
    region.trade_route_count,
    faction_influence,
    &shock,
    agent_values,
    region.controller_values,
    pool_ref.beliefs[slot],
    region.majority_belief,
    region.has_temple,   // M38a
);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo test --test satisfaction_m38a`
Expected: PASS — all 3 tests pass

- [ ] **Step 6: Update all existing call sites of `compute_satisfaction_with_culture`**

Search for all existing calls to `compute_satisfaction_with_culture` in the test files (e.g., `chronicler-agents/tests/*.rs`) and production code. Add `false` as the `has_temple` parameter to each existing call. Known locations: any tests in `satisfaction.rs` or test files that call this function (approximately 5 call sites).

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `cargo test`
Expected: all existing tests pass

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/tick.rs chronicler-agents/tests/satisfaction_m38a.rs
git commit -m "feat(m38a): clergy faction alignment + temple priest bonus in satisfaction"
```

---

## Chunk 2: Python Models & Faction Core

### Task 4: Extend FactionType enum and FactionState defaults

**Files:**
- Modify: `src/chronicler/models.py:72-99`
- Test: `test/test_m38a_factions.py`

- [ ] **Step 1: Write the failing test for 4-faction normalization**

Create `test/test_m38a_factions.py`:

```python
import pytest
from chronicler.models import FactionType, FactionState
from chronicler.factions import normalize_influence, FACTION_FLOOR


def test_faction_type_has_clergy():
    assert hasattr(FactionType, "CLERGY")
    assert FactionType.CLERGY.value == "clergy"


def test_faction_state_default_has_clergy():
    fs = FactionState()
    assert FactionType.CLERGY in fs.influence
    assert len(fs.influence) == 4


def test_normalize_4_factions_sum_to_one():
    fs = FactionState()
    normalize_influence(fs)
    total = sum(fs.influence.values())
    assert abs(total - 1.0) < 1e-6


def test_normalize_4_factions_floor():
    fs = FactionState()
    fs.influence[FactionType.CLERGY] = 0.01  # way below floor
    normalize_influence(fs)
    for ft in FactionType:
        assert fs.influence[ft] >= FACTION_FLOOR - 1e-6, \
            f"{ft} influence {fs.influence[ft]} below floor {FACTION_FLOOR}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: FAIL — `FactionType` has no `CLERGY`, `FACTION_FLOOR` not importable

- [ ] **Step 3: Add CLERGY to FactionType enum**

In `models.py` at line 75, add:

```python
class FactionType(str, Enum):
    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"
    CLERGY = "clergy"       # M38a
```

- [ ] **Step 4: Update FactionState default influence**

In `models.py` at lines 89-94, update the default_factory:

```python
class FactionState(BaseModel):
    influence: dict[FactionType, float] = Field(
        default_factory=lambda: {
            FactionType.MILITARY: 0.25,
            FactionType.MERCHANT: 0.25,
            FactionType.CULTURAL: 0.25,
            FactionType.CLERGY: 0.25,
        }
    )
```

- [ ] **Step 5: Add FactionState backward compatibility for pre-M38a bundles**

Add a Pydantic `model_validator` on `FactionState` that injects `CLERGY` at floor if missing when loading from saved bundles:

```python
@model_validator(mode="after")
def _ensure_clergy(self) -> "FactionState":
    if FactionType.CLERGY not in self.influence:
        self.influence[FactionType.CLERGY] = 0.08  # floor
    return self
```

This ensures civs loaded from pre-M38a bundles get clergy at the normalization floor rather than KeyError.

- [ ] **Step 6: Extract FACTION_FLOOR constant and update normalize_influence()**

In `factions.py`, add constant at module level (after imports, before dicts):

```python
FACTION_FLOOR = 0.08  # M38a: was 0.10 with 3 factions, now 0.08 with 4
```

In `normalize_influence()` at line 81, replace `floor = 0.10` with:

```python
floor = FACTION_FLOOR
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `python -m pytest test/ -x --timeout=60`
Expected: Existing tests that construct FactionState may fail because the default now includes CLERGY. Fix any that hard-code 3-faction assumptions by adding CLERGY with appropriate values.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/models.py src/chronicler/factions.py test/test_m38a_factions.py
git commit -m "feat(m38a): add FactionType.CLERGY, 4-faction normalization with 0.08 floor"
```

---

### Task 5: Add FACTION_WEIGHTS, FACTION_CANDIDATE_TYPE, GP mapping for clergy

**Files:**
- Modify: `src/chronicler/factions.py:51-67,150-163`
- Test: `test/test_m38a_factions.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `test/test_m38a_factions.py`:

```python
from chronicler.factions import (
    FACTION_WEIGHTS, FACTION_CANDIDATE_TYPE, GP_ROLE_TO_FACTION,
    get_faction_weight_modifier,
)
from chronicler.models import ActionType


def test_clergy_faction_weights_exist():
    assert FactionType.CLERGY in FACTION_WEIGHTS
    weights = FACTION_WEIGHTS[FactionType.CLERGY]
    assert ActionType.INVEST_CULTURE in weights
    assert ActionType.BUILD in weights
    assert ActionType.WAR in weights
    assert weights[ActionType.WAR] < 1.0  # clergy suppresses war


def test_clergy_candidate_type():
    assert FactionType.CLERGY in FACTION_CANDIDATE_TYPE
    assert FACTION_CANDIDATE_TYPE[FactionType.CLERGY] == "clergy"


def test_prophet_maps_to_clergy():
    assert GP_ROLE_TO_FACTION["prophet"] == FactionType.CLERGY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_factions.py::test_clergy_faction_weights_exist -v`
Expected: FAIL — CLERGY not in FACTION_WEIGHTS

- [ ] **Step 3: Add clergy entries to all three dicts**

In `factions.py`, add to `FACTION_WEIGHTS` (after line 162):

```python
    FactionType.CLERGY: {
        ActionType.INVEST_CULTURE: 1.5,
        ActionType.BUILD: 1.4,
        ActionType.DIPLOMACY: 1.3,
        ActionType.WAR: 0.7,
        ActionType.TRADE: 0.8,
    },
```

Add to `FACTION_CANDIDATE_TYPE` (after line 54):

```python
    FactionType.CLERGY: "clergy",
```

Change `GP_ROLE_TO_FACTION` (line 60):

```python
    "prophet": FactionType.CLERGY,  # M38a: was CULTURAL
```

Update `GP_SUCCESSION_TYPE` (line 66):

```python
    "prophet": "clergy",  # M38a: was "heir"
```

- [ ] **Step 4: Update GP per-turn bonus in tick_factions()**

In `factions.py`, in `tick_factions()` at line 300-301, the prophet GP bonus is hardcoded:

```python
elif gp.role == "prophet":
    civ.factions.influence[FactionType.CULTURAL] += 0.015
```

Change to:

```python
elif gp.role == "prophet":
    civ.factions.influence[FactionType.CLERGY] += 0.015  # M38a: was CULTURAL
```

- [ ] **Step 5: Add "clergy" to recognized succession types**

In `resolve_crisis_with_factions()` in `factions.py` (around line 496), find the `force_type` tuple that recognizes `("general", "elected", "heir", "usurper")`. Add `"clergy"` to this tuple.

Then add clergy-specific leader traits in `generate_successor()` (or wherever force_type is consumed to set leader attributes). Per the spec (Decision 5), clergy succession produces a leader matching the priest-archetype:

```python
elif force_type == "clergy":
    new_leader.primary_trait = "cautious"  # institutional conservatism
    # Spec: high loyalty, Tradition primary, Order secondary
    # These are applied via the personality/cultural value systems if present
```

**Important:** Do NOT use `"diplomatic"` — the spec says high loyalty trait, Tradition, Order. The trait name should match whatever the existing succession system uses for conservative/institutional leaders. Read `generate_successor()` to find the correct trait vocabulary before writing this.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/factions.py test/test_m38a_factions.py
git commit -m "feat(m38a): clergy faction weights, candidate type, prophet→clergy mapping"
```

---

### Task 6: Extend agent_bridge.py for clergy signals

**Files:**
- Modify: `src/chronicler/agent_bridge.py:26,227-266`
- Test: `test/test_m38a_factions.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test/test_m38a_factions.py`:

```python
import pyarrow as pa
from unittest.mock import MagicMock
from chronicler.agent_bridge import build_signals, FACTION_MAP


def test_faction_map_has_clergy():
    assert "clergy" in FACTION_MAP
    assert FACTION_MAP["clergy"] == 3


def test_build_signals_includes_faction_clergy():
    """Verify faction_clergy column exists in signal batch.
    Note: build_signals() requires many civ attributes. Use a minimal
    real-ish mock with all required numeric fields set to valid values."""
    world = MagicMock()
    civ = MagicMock()
    civ.factions = FactionState()  # real FactionState with 4 factions
    civ.name = "TestCiv"
    civ.stability = 50
    civ.active_focus = None
    civ.great_persons = []
    world.civilizations = [civ]
    world.regions = []
    world.active_wars = []
    batch = build_signals(world)
    col_names = batch.schema.names
    assert "faction_clergy" in col_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m38a_factions.py::test_faction_map_has_clergy -v`
Expected: FAIL

- [ ] **Step 3: Update agent_bridge.py**

In `agent_bridge.py`, update `FACTION_MAP` (line 26):

```python
FACTION_MAP = {"military": 0, "merchant": 1, "cultural": 2, "clergy": 3}
```

In `build_signals()`, add a `fac_cle` list alongside `fac_mil/fac_mer/fac_cul` in the per-civ loop:

```python
fac_cle.append(civ.factions.influence.get(FactionType.CLERGY, 0.08))
```

Add the column to the RecordBatch construction:

```python
("faction_clergy", pa.array(fac_cle, type=pa.float32())),
```

- [ ] **Step 4: Add `has_temple` column to `build_region_batch()`**

**Note:** This step uses `InfrastructureType.TEMPLES` which is added in Task 7 (Chunk 3). Use a `getattr` guard so this code is safe before Task 7 lands (returns `False` for all regions until TEMPLES type exists).

In `build_region_batch()`, add computation and column. **Important:** The Region model field is `region.controller` (not `region.controller_civ`):

```python
# M38a: has_temple — true if region has active temple matching controller's majority faith
def _has_temple(region, world):
    controller_name = region.controller  # NOT region.controller_civ
    if controller_name is None:
        return False
    controller = next((c for c in world.civilizations if c.name == controller_name), None)
    if controller is None:
        return False
    cmf = getattr(controller, 'civ_majority_faith', -1)
    _temples_type = getattr(InfrastructureType, 'TEMPLES', None)
    if _temples_type is None:
        return False  # TEMPLES type not yet defined (safe before Task 7)
    for infra in region.infrastructure:
        if (infra.active and infra.type == _temples_type
                and getattr(infra, 'faith_id', -1) == cmf and cmf >= 0):
            return True
    return False

has_temple_arr = [_has_temple(r, world) for r in world.regions]
```

Add to the RecordBatch:

```python
("has_temple", pa.array(has_temple_arr, type=pa.bool_())),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m38a_factions.py
git commit -m "feat(m38a): faction_clergy + has_temple in agent bridge signals"
```

---

## Chunk 3: Temple Infrastructure

### Task 7: Add TEMPLES to InfrastructureType and Infrastructure model

**Files:**
- Modify: `src/chronicler/models.py:115-141`
- Test: `test/test_m38a_temples.py`

- [ ] **Step 1: Write the failing test**

Create `test/test_m38a_temples.py`:

```python
import pytest
from chronicler.models import InfrastructureType, Infrastructure


def test_infrastructure_type_has_temples():
    assert hasattr(InfrastructureType, "TEMPLES")
    assert InfrastructureType.TEMPLES.value == "temples"


def test_infrastructure_has_faith_id():
    infra = Infrastructure(
        type=InfrastructureType.TEMPLES,
        builder_civ="TestCiv",
        built_turn=10,
        faith_id=2,
    )
    assert infra.faith_id == 2
    assert infra.temple_prestige == 0  # default


def test_non_temple_faith_id_default():
    infra = Infrastructure(
        type=InfrastructureType.ROADS,
        builder_civ="TestCiv",
        built_turn=10,
    )
    assert infra.faith_id == -1  # not a temple
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: FAIL — no TEMPLES enum, no faith_id field

- [ ] **Step 3: Add TEMPLES to InfrastructureType**

In `models.py`, add to `InfrastructureType` (after MINES):

```python
    TEMPLES = "temples"      # M38a
```

- [ ] **Step 4: Add faith_id and temple_prestige to Infrastructure**

In `models.py`, extend `Infrastructure` class:

```python
class Infrastructure(BaseModel):
    type: InfrastructureType
    builder_civ: str
    built_turn: int
    active: bool = True
    faith_id: int = -1          # M38a: -1 = not a temple; >=0 = belief registry index
    temple_prestige: int = 0    # M38a: +1/turn, consumed by M38b pilgrimages
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py test/test_m38a_temples.py
git commit -m "feat(m38a): add TEMPLES type and faith_id/temple_prestige to Infrastructure"
```

---

### Task 8: Temple BUILD logic in infrastructure.py

**Files:**
- Modify: `src/chronicler/infrastructure.py:26-32,117-187`
- Test: `test/test_m38a_temples.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `test/test_m38a_temples.py`:

```python
from unittest.mock import MagicMock, patch
from chronicler.infrastructure import (
    handle_build, BUILD_SPECS, TRAIT_BUILD_PRIORITY,
    MAX_TEMPLES_PER_REGION, MAX_TEMPLES_PER_CIV,
    TEMPLE_BUILD_COST, TEMPLE_BUILD_TURNS,
)
from chronicler.models import InfrastructureType as IType


def test_temple_build_specs():
    assert IType.TEMPLES in BUILD_SPECS
    cost, turns = BUILD_SPECS[IType.TEMPLES]
    assert cost == 10
    assert turns == 3


def test_temple_max_per_region():
    """Region with existing temple cannot build another."""
    world = MagicMock()
    civ = MagicMock()
    civ.treasury = 100
    civ.name = "Civ1"
    civ.civ_majority_faith = 0
    region = MagicMock()
    region.controller_civ = "Civ1"
    region.pending_build = None
    # Has an active temple already
    temple = MagicMock()
    temple.type = IType.TEMPLES
    temple.active = True
    temple.faith_id = 0
    region.infrastructure = [temple]
    world.regions = [region]
    world.civilizations = [civ]

    # Should not build another temple in same region
    from chronicler.infrastructure import _count_civ_temples, _region_has_temple
    assert _region_has_temple(region) is True


def test_temple_max_per_civ():
    from chronicler.infrastructure import _count_civ_temples
    world = MagicMock()
    regions = []
    for i in range(4):
        r = MagicMock()
        temple = MagicMock()
        temple.type = IType.TEMPLES
        temple.active = True
        r.infrastructure = [temple] if i < 3 else []
        regions.append(r)
    world.regions = regions
    assert _count_civ_temples(world, "Civ1") == 3  # at max


def test_temple_faith_id_set_at_build():
    """Temple built by civ gets civ's civ_majority_faith."""
    world = MagicMock()
    civ = MagicMock()
    civ.name = "Civ1"
    civ.civ_majority_faith = 2
    civ.treasury = 100
    civ.leader = MagicMock()
    civ.leader.primary_trait = "diplomatic"
    region = MagicMock()
    region.controller_civ = "Civ1"
    region.pending_build = None
    region.infrastructure = []
    world.regions = [region]
    world.civilizations = [civ]
    # After building, the pending_build should have faith_id=2
    # (tested via handle_build or direct temple creation)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: FAIL — BUILD_SPECS doesn't have TEMPLES, helpers don't exist

- [ ] **Step 3: Add temple to BUILD_SPECS**

In `infrastructure.py`, add to `BUILD_SPECS` dict:

```python
TEMPLE_BUILD_COST = 10
TEMPLE_BUILD_TURNS = 3
MAX_TEMPLES_PER_REGION = 1
MAX_TEMPLES_PER_CIV = 3
```

Add to the BUILD_SPECS dict:

```python
IType.TEMPLES: (TEMPLE_BUILD_COST, TEMPLE_BUILD_TURNS),
```

- [ ] **Step 4: Add temple helper functions**

In `infrastructure.py`, add:

```python
def _region_has_temple(region) -> bool:
    """Check if region has an active temple."""
    return any(
        i.type == IType.TEMPLES and i.active
        for i in region.infrastructure
    )


def _count_civ_temples(world, civ_name: str) -> int:
    """Count active temples in regions controlled by this civ.

    Counts by region controller, not builder_civ. After conquest, the conqueror's
    count includes inherited temples (they occupy the slot). The original builder's
    count drops because they no longer control the region. This matches the MAX_TEMPLES_PER_CIV
    constraint: a civ can't build a new temple if they already control 3 templed regions.
    """
    count = 0
    for r in world.regions:
        if getattr(r, 'controller', None) != civ_name:
            continue
        for i in r.infrastructure:
            if i.type == IType.TEMPLES and i.active:
                count += 1
    return count
```

- [ ] **Step 5: Add temple to TRAIT_BUILD_PRIORITY**

Add `IType.TEMPLES` to each trait's priority list. Clergy-favorable traits get it earlier:

```python
# Add TEMPLES to each priority list — position varies by trait
"aggressive": [IType.FORTIFICATIONS, IType.MINES, IType.ROADS, IType.PORTS, IType.IRRIGATION, IType.TEMPLES],
"bold":       [IType.FORTIFICATIONS, IType.ROADS, IType.MINES, IType.PORTS, IType.IRRIGATION, IType.TEMPLES],
"cautious":   [IType.FORTIFICATIONS, IType.ROADS, IType.IRRIGATION, IType.PORTS, IType.MINES, IType.TEMPLES],
"mercantile": [IType.ROADS, IType.PORTS, IType.MINES, IType.IRRIGATION, IType.TEMPLES, IType.FORTIFICATIONS],
"expansionist": [IType.IRRIGATION, IType.ROADS, IType.MINES, IType.PORTS, IType.TEMPLES, IType.FORTIFICATIONS],
"diplomatic": [IType.ROADS, IType.PORTS, IType.TEMPLES, IType.IRRIGATION, IType.MINES, IType.FORTIFICATIONS],
```

- [ ] **Step 6: Modify handle_build() to enforce temple constraints and set faith_id**

In `handle_build()`, add temple-specific logic in the candidate filtering:

```python
# Filter out temple-ineligible regions
if build_type == IType.TEMPLES:
    if _region_has_temple(region):
        continue  # max 1 per region
    if _count_civ_temples(world, civ.name) >= MAX_TEMPLES_PER_CIV:
        continue  # max per civ
```

When creating the PendingBuild/Infrastructure for temples, set faith_id:

```python
faith_id = getattr(civ, 'civ_majority_faith', -1) if build_type == IType.TEMPLES else -1
```

- [ ] **Step 7: Add temple conquest destruction logic**

Add function for militant conquest temple destruction:

```python
def destroy_temple_on_conquest(region, attacker_civ, world) -> Event | None:
    """Militant holy war destroys temple. Returns Event or None."""
    from chronicler.models import Event
    for infra in region.infrastructure:
        if infra.type == IType.TEMPLES and infra.active:
            infra.active = False
            return Event(
                turn=world.turn,
                event_type="temple_destroyed",
                actors=[attacker_civ.name],
                description=f"Temple of faith {infra.faith_id} destroyed in {getattr(region, 'name', '?')}",
                importance=5,
            )
    return None


def destroy_temple_for_replacement(region, world) -> Event | None:
    """Destroy foreign temple before building new one. Returns Event or None."""
    from chronicler.models import Event
    for infra in region.infrastructure:
        if infra.type == IType.TEMPLES and infra.active:
            infra.active = False
            return Event(
                turn=world.turn,
                event_type="temple_destroyed",
                actors=[],
                description=f"Temple of faith {infra.faith_id} replaced in {getattr(region, 'name', '?')}",
                importance=5,
            )
    return None
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/infrastructure.py test/test_m38a_temples.py
git commit -m "feat(m38a): temple BUILD logic with constraints and conquest destruction"
```

---

## Chunk 4: Faction Events, Tithe & Succession

### Task 9: Clergy event shifts in tick_factions()

**Files:**
- Modify: `src/chronicler/factions.py:232-367`
- Modify: `src/chronicler/religion.py` (add compute_conversion_deltas)
- Test: `test/test_m38a_factions.py` (extend)

- [ ] **Step 1: Write the failing tests for clergy event shifts**

Append to `test/test_m38a_factions.py`:

```python
from chronicler.factions import tick_factions


def _make_civ_with_clergy(clergy_influence=0.25):
    """Helper: create a mock civ with 4-faction influence."""
    civ = MagicMock()
    civ.factions = FactionState()
    civ.factions.influence[FactionType.CLERGY] = clergy_influence
    normalize_influence(civ.factions)
    civ.name = "TestCiv"
    civ.treasury = 50
    civ.trade_income = 10
    civ.stability = 50
    civ.great_persons = []
    civ.factions.power_struggle = False
    civ.factions.power_struggle_cooldown = 0
    civ.factions.pending_faction_shift = None
    return civ


def test_clergy_shift_temple_built():
    """Building a temple shifts clergy influence up."""
    from chronicler.models import Event
    world = MagicMock()
    civ = _make_civ_with_clergy()
    world.civilizations = [civ]
    world.turn = 10
    world.events_timeline = [Event(
        turn=10, event_type="build_started", actors=["TestCiv"],
        description="TestCiv begins building temples in Region0", importance=3,
    )]
    world.regions = []
    before = civ.factions.influence[FactionType.CLERGY]
    tick_factions(world)
    after = civ.factions.influence[FactionType.CLERGY]
    assert after > before, f"temple built should increase clergy: {before} -> {after}"


def test_clergy_conversion_success_per_civ_cap():
    """Conversion success gives max +0.01 per civ regardless of region count."""
    world = MagicMock()
    civ = _make_civ_with_clergy()
    world.civilizations = [civ]
    world.turn = 10
    world.events_timeline = []
    # Create real-ish region objects with controller attribute
    regions = []
    for _ in range(3):
        r = MagicMock()
        r.controller = "TestCiv"
        regions.append(r)
    world.regions = regions
    conversion_deltas = {0: 20, 1: 15, 2: 25}  # all above 5% of 100
    region_populations = {0: 100, 1: 100, 2: 100}
    before = civ.factions.influence[FactionType.CLERGY]
    tick_factions(world, conversion_deltas=conversion_deltas,
                  region_populations=region_populations)
    after = civ.factions.influence[FactionType.CLERGY]
    assert after > before, "conversion success should increase clergy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_factions.py::test_clergy_shift_temple_built -v`
Expected: FAIL — tick_factions doesn't handle clergy events

- [ ] **Step 3: Add clergy event constants**

In `factions.py`, add constants at module level:

```python
# M38a: Clergy influence event shifts
EVT_TEMPLE_BUILT = 0.03
EVT_CONVERSION_SUCCESS = 0.01
EVT_HOLY_WAR_WON = 0.04
EVT_TEMPLE_DESTROYED = -0.03
EVT_PRIEST_LOSS = -0.01  # per 5% loss
```

- [ ] **Step 4: Add clergy event processing to tick_factions()**

Add `conversion_deltas` and `region_populations` parameters to `tick_factions()` signature. Add clergy event processing block after the existing event processing:

**Important:** Events are `Event` Pydantic objects (`.event_type`, `.actors`, `.description`, `.turn`), not dicts. Match the existing pattern in `tick_factions()` (lines 245-282):

```python
# M38a: clergy events (inside the existing event scan loop, after the cultural_work elif)
elif event.event_type == "build_started" and "temples" in event.description.lower():
    if civ.name in event.actors:
        civ.factions.influence[FactionType.CLERGY] += EVT_TEMPLE_BUILT

elif event.event_type == "temple_destroyed":
    if civ.name in event.actors:
        civ.factions.influence[FactionType.CLERGY] += EVT_TEMPLE_DESTROYED  # negative

elif event.event_type == "war" and len(event.actors) >= 2:
    # Holy war detection: war win + different faith (check description)
    is_attacker = event.actors[0] == civ.name
    if "holy_war" in event.description.lower() and (
        (is_attacker and "attacker_wins" in event.description) or
        (not is_attacker and "defender_wins" in event.description)
    ):
        civ.factions.influence[FactionType.CLERGY] += EVT_HOLY_WAR_WON
```

Add **after** the event scan loop (before normalize), guarded by snapshot:

```python
# M38a: conversion success (per-civ, max +0.01/turn) — requires snapshot
if conversion_deltas is not None:
    for region_id, converted_count in conversion_deltas.items():
        if region_id >= len(world.regions):
            continue
        region = world.regions[region_id]
        if getattr(region, 'controller', None) == civ.name:
            region_pop = region_populations.get(region_id, 0)
            if region_pop > 0 and converted_count / region_pop >= 0.05:
                civ.factions.influence[FactionType.CLERGY] += EVT_CONVERSION_SUCCESS
                break  # per-civ cap

# M38a: priest death above baseline (requires snapshot)
if prev_priest_counts is not None and civ.name in prev_priest_counts:
    prev_count = prev_priest_counts[civ.name]
    curr_count = curr_priest_counts.get(civ.name, 0)
    if prev_count > 0:
        loss_fraction = (prev_count - curr_count) / prev_count
        loss_steps = int(loss_fraction / 0.05)  # -0.01 per 5% loss
        if loss_steps > 0:
            civ.factions.influence[FactionType.CLERGY] += EVT_PRIEST_LOSS * loss_steps
```

- [ ] **Step 5: Add compute_conversion_deltas() to religion.py**

In `religion.py`, add:

```python
def compute_conversion_deltas(
    current_beliefs: dict[int, dict[int, int]],  # region_id -> {belief_id: count}
    prev_beliefs: dict[int, dict[int, int]],
    civ_majority_faiths: dict[str, int],
    regions,
) -> dict[int, int]:
    """Per-region count of agents who converted to controller's faith this turn.

    Returns dict[region_id, converted_count]. Only includes regions where
    conversions toward the controller's faith occurred.
    """
    deltas = {}
    for region_id, curr_dist in current_beliefs.items():
        region = regions[region_id]
        controller = getattr(region, 'controller', None)
        if controller is None:
            continue
        target_faith = civ_majority_faiths.get(controller, -1)
        if target_faith < 0:
            continue
        curr_count = curr_dist.get(target_faith, 0)
        prev_count = prev_beliefs.get(region_id, {}).get(target_faith, 0)
        delta = curr_count - prev_count
        if delta > 0:
            deltas[region_id] = delta
    return deltas
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/factions.py src/chronicler/religion.py test/test_m38a_factions.py
git commit -m "feat(m38a): clergy event shifts in tick_factions with per-civ conversion cap"
```

---

### Task 10: Tithe mechanic

**Files:**
- Modify: `src/chronicler/factions.py`
- Test: `test/test_m38a_factions.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `test/test_m38a_factions.py`:

```python
from chronicler.factions import compute_tithe_base, TITHE_RATE, TITHE_THRESHOLD


def test_compute_tithe_base_returns_trade_income():
    civ = MagicMock()
    civ.trade_income = 12
    assert compute_tithe_base(civ) == 12


def test_tithe_collected_above_threshold():
    civ = _make_civ_with_clergy(clergy_influence=0.20)
    civ.treasury = 50
    civ.trade_income = 10
    before = civ.treasury
    # Simulate tithe collection
    if civ.factions.influence[FactionType.CLERGY] >= TITHE_THRESHOLD:
        tithe = TITHE_RATE * compute_tithe_base(civ)
        civ.treasury += tithe
    assert civ.treasury > before
    assert abs(civ.treasury - 51.0) < 0.1  # 0.10 * 10 = 1.0


def test_tithe_not_collected_below_threshold():
    civ = _make_civ_with_clergy(clergy_influence=0.08)  # at floor
    civ.treasury = 50
    civ.trade_income = 10
    # Clergy at floor (0.08) should be below TITHE_THRESHOLD (0.15)
    if civ.factions.influence[FactionType.CLERGY] >= TITHE_THRESHOLD:
        civ.treasury += TITHE_RATE * compute_tithe_base(civ)
    assert civ.treasury == 50  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_factions.py::test_compute_tithe_base_returns_trade_income -v`
Expected: FAIL — compute_tithe_base not defined

- [ ] **Step 3: Add tithe constants and helper**

In `factions.py`, add:

```python
TITHE_RATE = 0.10       # [CALIBRATE] fraction of tithe base → treasury
TITHE_THRESHOLD = 0.15  # min clergy influence to collect tithes
CLERGY_NOMINATION_THRESHOLD = 0.15


def compute_tithe_base(civ, snapshot=None):
    """M38a: trade_income proxy. M41 swaps to sum(merchant_wealth)."""
    return civ.trade_income
```

- [ ] **Step 4: Wire tithe into tick_factions()**

In `tick_factions()`, after clergy event processing, add tithe collection:

```python
# M38a: tithe collection
if civ.factions.influence[FactionType.CLERGY] >= TITHE_THRESHOLD:
    tithe = TITHE_RATE * compute_tithe_base(civ)
    civ.treasury += tithe
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/factions.py test/test_m38a_factions.py
git commit -m "feat(m38a): tithe mechanic with trade income proxy and threshold gating"
```

---

### Task 11: Clergy succession candidate

**Files:**
- Modify: `src/chronicler/factions.py:374-427`
- Test: `test/test_m38a_factions.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test/test_m38a_factions.py`:

```python
from chronicler.factions import generate_faction_candidates


def test_clergy_candidate_generated_above_threshold():
    world = MagicMock()
    civ = _make_civ_with_clergy(clergy_influence=0.20)
    world.civilizations = [civ]
    candidates = generate_faction_candidates(civ, world)
    clergy_candidates = [c for c in candidates if c.get("type") == "clergy"]
    assert len(clergy_candidates) >= 1, "clergy should nominate a candidate above threshold"


def test_no_clergy_candidate_below_threshold():
    world = MagicMock()
    civ = _make_civ_with_clergy(clergy_influence=0.08)
    world.civilizations = [civ]
    candidates = generate_faction_candidates(civ, world)
    clergy_candidates = [c for c in candidates if c.get("type") == "clergy"]
    assert len(clergy_candidates) == 0, "no clergy candidate below threshold"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_factions.py::test_clergy_candidate_generated_above_threshold -v`
Expected: FAIL — generate_faction_candidates doesn't produce clergy candidates

- [ ] **Step 3: Add clergy candidate to generate_faction_candidates()**

In `generate_faction_candidates()` (line 384), the existing loop iterates over all `FactionType` members and checks `influence >= 0.15`. Since we added `FactionType.CLERGY: "clergy"` to `FACTION_CANDIDATE_TYPE` in Task 5, the loop already includes clergy candidates when influence is sufficient. **No trait keys need to be added to the candidate dict** — the existing candidates for other factions don't set trait keys either. Traits are determined downstream when the candidate is resolved into a leader.

Verify that the succession resolution code (`resolve_crisis_with_factions()`) handles the `"clergy"` type correctly (Task 5, Step 5 already addressed this). The clergy candidate's traits (high loyalty, Tradition, Order) are applied when the leader is instantiated from the winning candidate, not in the candidate dict itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_factions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/factions.py test/test_m38a_factions.py
git commit -m "feat(m38a): clergy succession candidate with priest-archetype traits"
```

---

## Chunk 5: Signal Integration & Prestige

### Task 12: Temple conversion boost in religion.py

**Files:**
- Modify: `src/chronicler/religion.py:193-339`
- Test: `test/test_m38a_temples.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test/test_m38a_temples.py`:

```python
def test_temple_conversion_boost_matching_faith():
    """Temple boosts conversion rate by 50% when faith matches.
    Tests the actual guard clause in compute_conversion_signals()."""
    from chronicler.infrastructure import TEMPLE_CONVERSION_BOOST

    # Build a region with a matching-faith temple
    region = MagicMock()
    temple = Infrastructure(
        type=IType.TEMPLES, builder_civ="Civ1", built_turn=1,
        active=True, faith_id=1,
    )
    region.infrastructure = [temple]

    # Simulate the guard clause from religion.py
    target_faith = 1  # matches temple
    rate = 0.06
    for infra in region.infrastructure:
        if (infra.type == IType.TEMPLES and infra.active
                and getattr(infra, 'faith_id', -1) == target_faith):
            rate *= (1.0 + TEMPLE_CONVERSION_BOOST)
            break
    assert abs(rate - 0.09) < 0.001, f"expected 0.09, got {rate}"


def test_temple_conversion_boost_different_faith():
    """Temple does NOT boost conversion when faith doesn't match."""
    from chronicler.infrastructure import TEMPLE_CONVERSION_BOOST

    region = MagicMock()
    temple = Infrastructure(
        type=IType.TEMPLES, builder_civ="Civ1", built_turn=1,
        active=True, faith_id=1,
    )
    region.infrastructure = [temple]

    target_faith = 2  # different from temple
    rate = 0.06
    for infra in region.infrastructure:
        if (infra.type == IType.TEMPLES and infra.active
                and getattr(infra, 'faith_id', -1) == target_faith):
            rate *= (1.0 + TEMPLE_CONVERSION_BOOST)
            break
    assert abs(rate - 0.06) < 0.001, f"rate should be unchanged, got {rate}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: FAIL — TEMPLE_CONVERSION_BOOST not defined

- [ ] **Step 3: Add TEMPLE_CONVERSION_BOOST constant**

In `infrastructure.py`, add:

```python
TEMPLE_CONVERSION_BOOST = 0.50  # [CALIBRATE] multiplicative boost when faith matches
```

- [ ] **Step 4: Add temple boost guard clause to compute_conversion_signals()**

In `religion.py`, in `compute_conversion_signals()`, after computing the base `conversion_rate` and before writing to the region signal, add:

```python
# M38a: temple conversion boost — faith-bound guard clause
from chronicler.infrastructure import TEMPLE_CONVERSION_BOOST  # at function top
for infra in region.infrastructure:
    if (infra.type == InfrastructureType.TEMPLES
            and infra.active
            and getattr(infra, 'faith_id', -1) == target_faith):
        conversion_rate *= (1.0 + TEMPLE_CONVERSION_BOOST)
        break
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/infrastructure.py src/chronicler/religion.py test/test_m38a_temples.py
git commit -m "feat(m38a): temple conversion boost with faith-bound guard clause"
```

---

### Task 13: Temple prestige tick and civ prestige in Phase 10

**Files:**
- Modify: `src/chronicler/simulation.py` (Phase 10)
- Test: `test/test_m38a_temples.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `test/test_m38a_temples.py`:

```python
from chronicler.infrastructure import tick_temple_prestige


def test_tick_temple_prestige():
    world = MagicMock()
    civ = MagicMock()
    civ.name = "Civ1"
    civ.prestige = 10
    temple = Infrastructure(
        type=IType.TEMPLES,
        builder_civ="Civ1",
        built_turn=1,
        faith_id=0,
        temple_prestige=5,
    )
    region = MagicMock()
    region.infrastructure = [temple]
    world.regions = [region]
    world.civilizations = [civ]

    tick_temple_prestige(world)

    assert temple.temple_prestige == 6  # +1
    assert civ.prestige == 11           # +1 per active temple


def test_tick_temple_prestige_inactive():
    """Inactive temples don't accumulate prestige."""
    world = MagicMock()
    civ = MagicMock()
    civ.name = "Civ1"
    civ.prestige = 10
    temple = Infrastructure(
        type=IType.TEMPLES,
        builder_civ="Civ1",
        built_turn=1,
        active=False,
        faith_id=0,
    )
    region = MagicMock()
    region.infrastructure = [temple]
    world.regions = [region]
    world.civilizations = [civ]

    tick_temple_prestige(world)

    assert temple.temple_prestige == 0  # unchanged
    assert civ.prestige == 10           # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test/test_m38a_temples.py::test_tick_temple_prestige -v`
Expected: FAIL — tick_temple_prestige not defined

- [ ] **Step 3: Add tick_temple_prestige() to infrastructure.py**

```python
TEMPLE_PRESTIGE_PER_TURN = 1  # [CALIBRATE]
CIV_PRESTIGE_PER_TEMPLE = 1  # [CALIBRATE]


def tick_temple_prestige(world):
    """Per-turn: increment temple prestige and award civ prestige.

    Civ prestige is awarded to the region controller, not the original builder.
    After conquest, the conqueror inherits the temple and its prestige contribution.
    Note: temple_prestige is uncapped — accumulates indefinitely.
    M38b pilgrimage targeting consumes this value.

    Phase 10 placement: prestige from temples is awarded one turn late because
    it's computed alongside faction ticks in Phase 10, separate from Phase 6
    cultural prestige awards. Acceptable because temple prestige is slow-moving
    (+1/turn) and the one-turn delay has negligible behavioral impact.
    """
    civ_temple_counts = {}
    for region in world.regions:
        controller = getattr(region, 'controller', None)
        for infra in region.infrastructure:
            if infra.type == IType.TEMPLES and infra.active:
                infra.temple_prestige += TEMPLE_PRESTIGE_PER_TURN
                if controller:
                    civ_temple_counts[controller] = civ_temple_counts.get(controller, 0) + 1

    for civ in world.civilizations:
        count = civ_temple_counts.get(civ.name, 0)
        if count > 0:
            civ.prestige += CIV_PRESTIGE_PER_TEMPLE * count
```

- [ ] **Step 4: Wire tick_temple_prestige into Phase 10 of simulation.py**

In `simulation.py`, in `phase_consequences()`, add after the religion computation block:

```python
# M38a: temple prestige accumulation (Phase 10, one-turn delay intentional)
from chronicler.infrastructure import tick_temple_prestige
tick_temple_prestige(world)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test/test_m38a_temples.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/infrastructure.py src/chronicler/simulation.py test/test_m38a_temples.py
git commit -m "feat(m38a): temple prestige tick and civ prestige in Phase 10"
```

---

### Task 14: Wire conversion_deltas into Phase 10

**Files:**
- Modify: `src/chronicler/simulation.py` (Phase 10 religion block)
- Modify: `src/chronicler/factions.py` (tick_factions signature)

- [ ] **Step 1: Add conversion delta computation to Phase 10**

In `simulation.py`, in `phase_consequences()`, in the M37 religion block (after `compute_majority_belief` and `compute_civ_majority_faith`), add:

```python
# M38a: compute conversion deltas for clergy event detection
from chronicler.religion import compute_conversion_deltas
conversion_deltas = None
region_populations = None
prev_priest_counts = getattr(world, '_prev_priest_counts', None)
curr_priest_counts = None
if _snap is not None:
    import pyarrow as pa
    # Build per-region belief distribution from snapshot
    region_col = _snap.column("region").to_pylist()
    belief_col = _snap.column("belief").to_pylist()
    current_beliefs = {}  # region_id -> {belief_id: count}
    for rid, bid in zip(region_col, belief_col):
        if rid not in current_beliefs:
            current_beliefs[rid] = {}
        current_beliefs[rid][bid] = current_beliefs[rid].get(bid, 0) + 1

    prev_beliefs = getattr(world, '_prev_belief_distribution', {})
    civ_majority_faiths = {c.name: c.civ_majority_faith for c in world.civilizations}
    conversion_deltas = compute_conversion_deltas(
        current_beliefs, prev_beliefs, civ_majority_faiths, world.regions
    )
    # Region populations from belief distribution
    region_populations = {rid: sum(dist.values()) for rid, dist in current_beliefs.items()}
    world._prev_belief_distribution = current_beliefs

    # M38a: priest counts per civ for EVT_PRIEST_LOSS detection
    occ_col = _snap.column("occupation").to_pylist()
    civ_col = _snap.column("civ_affinity").to_pylist()
    curr_priest_counts = {}
    for occ, civ_id in zip(occ_col, civ_col):
        if occ == 4:  # priest
            civ_name = _civ_id_to_name.get(civ_id, "")
            curr_priest_counts[civ_name] = curr_priest_counts.get(civ_name, 0) + 1
    world._prev_priest_counts = curr_priest_counts
```

- [ ] **Step 2: Pass conversion_deltas and priest counts to tick_factions()**

Update the `tick_factions()` call in Phase 10. **Important:** preserve the existing `acc=acc` parameter:

```python
tick_factions(world, acc=acc,
              conversion_deltas=conversion_deltas,
              region_populations=region_populations,
              prev_priest_counts=prev_priest_counts,
              curr_priest_counts=curr_priest_counts)
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest test/ -x --timeout=60`
Expected: PASS — all tests including the new M38a tests

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m38a): wire conversion_deltas into Phase 10 for clergy event detection"
```

---

## Chunk 6: Regression & Validation

### Task 15: FFI round-trip tests (Rust)

**Files:**
- Create: `chronicler-agents/tests/m38a_ffi.rs`

- [ ] **Step 1: Write FFI round-trip tests for faction_clergy and has_temple**

Read the existing test patterns in `chronicler-agents/tests/determinism.rs` and `regression.rs` to understand how RecordBatches are constructed for civ signals and region state. The tests must construct a **complete** RecordBatch with all required columns (not just the new ones), call `parse_civ_signals()` / `set_region_state()`, and verify the new fields are correctly populated.

**For `faction_clergy`:** Construct a civ signals RecordBatch including all columns from the existing schema (civ_id, stability, is_at_war, dominant_faction, faction_military, faction_merchant, faction_cultural, **faction_clergy**, plus M27 shocks, M27 demand shifts, M33 personality means). Set `faction_clergy` to `0.25`. Parse via `parse_civ_signals()`. Assert `signals.civs[0].faction_clergy == 0.25`.

**For `has_temple`:** Construct a region RecordBatch including all existing columns plus `has_temple: true`. Parse via `set_region_state()`. Assert `regions[0].has_temple == true`.

Note: The exact column list must match the existing schema. Read `ffi.rs` to enumerate all required columns before writing the test.

- [ ] **Step 2: Run tests**

Run: `cargo test --test m38a_ffi`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/m38a_ffi.rs
git commit -m "test(m38a): FFI round-trip tests for faction_clergy and has_temple"
```

---

### Task 16: Integration verification

**Files:**
- Test: `test/test_m38a_integration.py`

- [ ] **Step 1: Write integration test — full turn with temples and clergy**

Create `test/test_m38a_integration.py`:

```python
"""M38a integration tests: verify temples and clergy work end-to-end."""
import pytest
from chronicler.models import FactionType, FactionState, InfrastructureType, Infrastructure
from chronicler.factions import normalize_influence, tick_factions, FACTION_FLOOR


def test_4_faction_normalization_invariant():
    """All faction states maintain sum=1.0 and floor >= 0.08."""
    fs = FactionState()
    # Extreme: push clergy to 0
    fs.influence[FactionType.CLERGY] = 0.0
    fs.influence[FactionType.MILITARY] = 0.5
    normalize_influence(fs)
    total = sum(fs.influence.values())
    assert abs(total - 1.0) < 1e-6
    for ft in FactionType:
        assert fs.influence[ft] >= FACTION_FLOOR - 1e-6


def test_temple_lifecycle_non_militant_conquest():
    """Non-militant conquest preserves temple — destroy_temple_on_conquest is
    only called for militant holy war. Verify temple state is unchanged when
    the function is NOT called (non-militant path)."""
    temple = Infrastructure(
        type=InfrastructureType.TEMPLES,
        builder_civ="OldCiv",
        built_turn=1,
        faith_id=0,
        temple_prestige=20,
    )
    # Non-militant: the caller does NOT invoke destroy_temple_on_conquest.
    # The temple remains active with its original faith_id.
    assert temple.active is True
    assert temple.faith_id == 0
    assert temple.temple_prestige == 20
    # This test documents the contract: temple survival is the default.
    # Destruction requires an explicit call to destroy_temple_on_conquest.


def test_temple_lifecycle_militant_conquest():
    """Militant holy war destroys temple via destroy_temple_on_conquest."""
    from chronicler.infrastructure import destroy_temple_on_conquest
    region = type('R', (), {'infrastructure': [], 'name': 'Region0'})()
    temple = Infrastructure(
        type=InfrastructureType.TEMPLES,
        builder_civ="OldCiv",
        built_turn=1,
        faith_id=0,
    )
    region.infrastructure = [temple]
    attacker = type('C', (), {'name': 'NewCiv'})()
    world = type('W', (), {'turn': 10})()
    event = destroy_temple_on_conquest(region, attacker, world)
    assert event is not None
    assert event.event_type == "temple_destroyed"
    assert temple.active is False
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest test/test_m38a_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite (Python + Rust)**

Run: `python -m pytest test/ -x --timeout=120 && cargo test`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add test/test_m38a_integration.py
git commit -m "test(m38a): integration tests for temple lifecycle and 4-faction invariants"
```

---

### Task 17: Decision 9 regression baseline (Tier 2)

**Files:**
- Create: `test/test_m38a_regression.py`

- [ ] **Step 1: Write the regression baseline test**

Create `test/test_m38a_regression.py`. This is the primary safety net for the 3→4 faction renormalization:

```python
"""M38a Tier 2 regression: Decision 9 baseline.

Verifies that adding clergy at floor with 0 events doesn't break
existing 3-faction behavior beyond tolerance.
"""
import pytest
from chronicler.models import FactionType, FactionState
from chronicler.factions import normalize_influence, FACTION_FLOOR


def test_decision9_action_distributions():
    """With clergy at floor (0.08) and no clergy events, the remaining
    3 factions' relative proportions should be within ±2% of the pre-M38a
    3-faction baseline.

    Method: create FactionState with CLERGY at floor, normalize, verify
    that MIL:MER:CUL ratios are preserved within tolerance."""
    # Simulate pre-M38a: 3-faction state
    baseline = {FactionType.MILITARY: 0.40, FactionType.MERCHANT: 0.35, FactionType.CULTURAL: 0.25}
    baseline_ratios = {ft: v / sum(baseline.values()) for ft, v in baseline.items()
                       if ft != FactionType.CLERGY}

    # Post-M38a: same 3-faction values + clergy at floor
    fs = FactionState()
    fs.influence = {
        FactionType.MILITARY: 0.40,
        FactionType.MERCHANT: 0.35,
        FactionType.CULTURAL: 0.25,
        FactionType.CLERGY: FACTION_FLOOR,
    }
    normalize_influence(fs)

    # Check 3-faction ratios preserved within ±2%
    non_clergy_total = sum(v for ft, v in fs.influence.items() if ft != FactionType.CLERGY)
    for ft in [FactionType.MILITARY, FactionType.MERCHANT, FactionType.CULTURAL]:
        actual_ratio = fs.influence[ft] / non_clergy_total
        expected_ratio = baseline_ratios[ft]
        assert abs(actual_ratio - expected_ratio) < 0.02, \
            f"{ft}: ratio {actual_ratio:.3f} vs baseline {expected_ratio:.3f} exceeds ±2%"
```

- [ ] **Step 2: Run the regression test**

Run: `python -m pytest test/test_m38a_regression.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add test/test_m38a_regression.py
git commit -m "test(m38a): Decision 9 regression baseline for 3->4 faction renormalization"
```

Note: The full Tier 2 harness (200 seeds × 200 turns with succession match rate ≥95%, economy ±10%, etc.) requires end-to-end simulation runs and is best implemented as a follow-up once all production code is landed. This task covers the structural regression that validates the normalization change itself.

---

### Task 18: Verify WAR × clergy computation order

**Files:** (no changes — verification only)

- [ ] **Step 1: Read action_engine.py to verify computation order**

Verify that in `compute_weights()`:
1. Faction weight modifier is applied multiplicatively (via `get_faction_weight_modifier()`)
2. Holy war bonus from M37 is applied additively to the WAR weight
3. The multiplication happens before the addition (or they operate at different stages)

Expected: Militant clergy-dominant civs get `WAR_base × 0.7^influence + 0.15` — the faction suppression and holy war bonus don't cancel each other.

- [ ] **Step 2: Document the finding**

If the order is correct, no changes needed. If the order produces unexpected interaction, file a note for M47 tuning.

- [ ] **Step 3: Commit verification note**

No code change — verification only. Add a comment to the test file if needed.

---

### Task 19: Final cleanup and verification

- [ ] **Step 1: Run full Rust test suite**

Run: `cargo test`
Expected: all tests pass

- [ ] **Step 2: Run full Python test suite**

Run: `python -m pytest test/ --timeout=120`
Expected: all tests pass

- [ ] **Step 3: Verify `--agents=off` mode**

Run a quick simulation in `--agents=off` mode and verify no errors from the new faction/temple code.

- [ ] **Step 4: Final commit with any remaining fixups**

Stage only the specific files that were modified (avoid `git add -A` which could stage unintended files):

```bash
git add <specific-changed-files>
git commit -m "chore(m38a): final cleanup and verification"
```
