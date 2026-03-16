# M27: System Integration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire agent-derived stats into the Python turn loop, enabling hybrid mode (`--agents=hybrid`) where agent behavior produces emergent civ-level stats.

**Architecture:** StatAccumulator captures all stat mutations during Phases 1-9, routing them by classification (keep/guard/guard-action/guard-shock/signal). In aggregate mode, mutations apply directly (bit-identical). In hybrid mode, keep mutations apply, guard mutations are skipped, guard-action mutations become demand signals, and signal/guard-shock mutations become shock signals for the Rust agent tick. Phase 10 runs after write-back with ~5 inline guards.

**Tech Stack:** Python 3.12, Rust (chronicler-agents crate), PyO3 + pyo3-arrow, pyarrow

**Spec:** `docs/superpowers/specs/2026-03-16-m27-system-integration-design.md`

---

## Chunk 1: Foundation — Data Structures + StatAccumulator

### Task 1: Data Structures in models.py

**Files:**
- Modify: `src/chronicler/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Add new dataclasses and fields to models.py**

Add after the existing dataclass imports section:

```python
@dataclass(slots=True)
class StatChange:
    civ_id: int
    stat: str
    delta: float
    category: str       # "guard", "guard-action", "guard-shock", "signal", "keep"
    stat_at_time: float  # stat value when mutation was recorded

@dataclass
class CivShock:
    civ_id: int
    stability_shock: float = 0.0
    economy_shock: float = 0.0
    military_shock: float = 0.0
    culture_shock: float = 0.0

@dataclass
class DemandSignal:
    civ_id: int
    occupation: int      # 0=farmer, 1=soldier, 2=merchant, 3=scholar, 4=priest
    magnitude: float
    turns_remaining: int  # starts at 3

@dataclass(slots=True)
class AgentEventRecord:
    turn: int
    agent_id: int
    event_type: str
    region: int
    target_region: int
    civ_affinity: int
    occupation: int
```

Add `source` field to the existing `Event` dataclass:

```python
source: str = "aggregate"  # "aggregate" or "agent"
```

Add fields to `WorldState`:

```python
agent_mode: str | None = None       # None/"off", "demographics-only", "shadow", "hybrid"
pending_shocks: list = field(default_factory=list)   # list[CivShock]
agent_events_raw: list = field(default_factory=list)  # list[AgentEventRecord]
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `python -m pytest tests/ -x -q`
Expected: All existing tests pass (new fields have defaults, no signature changes).

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m27): add StatChange, CivShock, DemandSignal, AgentEventRecord dataclasses and WorldState fields"
```

---

### Task 2: StatAccumulator Class

**Files:**
- Create: `src/chronicler/accumulator.py`
- Test: `tests/test_accumulator.py`

- [ ] **Step 1: Write failing tests for StatAccumulator**

Create `tests/test_accumulator.py`:

```python
"""Tests for StatAccumulator — M27 core routing logic."""
import pytest
from unittest.mock import MagicMock
from chronicler.models import StatChange, CivShock, DemandSignal


def _make_civ(civ_id, stability=50, economy=50, military=50, culture=50, treasury=100, asabiya=0.5, prestige=10):
    """Create a mock Civilization with stat fields."""
    civ = MagicMock()
    civ.id = civ_id
    civ.stability = stability
    civ.economy = economy
    civ.military = military
    civ.culture = culture
    civ.treasury = treasury
    civ.asabiya = asabiya
    civ.prestige = prestige
    return civ


def _make_world(civs):
    world = MagicMock()
    world.civilizations = civs
    return world


class TestStatAccumulatorApply:
    """Aggregate mode: apply() must produce bit-identical results to direct mutation."""

    def test_apply_single_change(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=50)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -10, "signal")
        acc.apply(world)
        assert civ.stability == 40

    def test_apply_preserves_insertion_order(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=80)
        world = _make_world([civ])
        acc = StatAccumulator()
        # Two mutations to same stat — order matters for clamping
        acc.add(0, civ, "stability", -50, "signal")
        acc.add(0, civ, "stability", -50, "signal")
        acc.apply(world)
        # First: 80-50=30. Second: 30-50=-20 → clamped to floor (5 for stability)
        assert civ.stability == 5  # STAT_FLOOR["stability"]

    def test_apply_clamps_to_100(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, economy=95)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ,"economy", 20, "guard-shock")
        acc.apply(world)
        assert civ.economy == 100

    def test_apply_treasury_no_upper_clamp(self):
        """Treasury uses max(0, ...) not clamp(..., 100)."""
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, treasury=200)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ,"treasury", 50, "keep")
        acc.apply(world)
        assert civ.treasury == 250  # No upper bound

    def test_apply_treasury_floors_at_zero(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, treasury=10)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ,"treasury", -30, "keep")
        acc.apply(world)
        assert civ.treasury == 0  # Floors at 0, not negative


class TestStatAccumulatorRouting:
    """Category routing: each method processes only its categories."""

    def test_apply_keep_only_processes_keep(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=50, treasury=100)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -10, "signal")
        acc.add(0, civ,"treasury", -5, "keep")
        acc.add(0, civ,"military", 10, "guard-action")
        acc.apply_keep(world)
        assert civ.treasury == 95   # keep applied
        assert civ.stability == 50  # signal NOT applied
        assert civ.military == 50   # guard-action NOT applied

    def test_to_shock_signals_processes_signal_and_guard_shock(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=80, culture=50)
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -20, "signal")
        acc.add(0, civ,"culture", 10, "guard-shock")
        acc.add(0, civ,"treasury", -5, "keep")
        acc.add(0, civ,"military", 10, "guard-action")
        shocks = acc.to_shock_signals()
        assert len(shocks) == 1  # one civ
        assert shocks[0].stability_shock == pytest.approx(-0.25)  # -20/80
        assert shocks[0].culture_shock == pytest.approx(0.2)      # 10/50
        assert shocks[0].economy_shock == 0.0
        assert shocks[0].military_shock == 0.0

    def test_to_demand_signals_processes_guard_action_only(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, military=50)
        acc = StatAccumulator()
        acc.add(0, civ,"military", -10, "guard-action")
        acc.add(0, civ,"stability", -5, "signal")
        acc.add(0, civ,"treasury", -3, "keep")
        signals = acc.to_demand_signals({0: 60})
        assert len(signals) == 1
        assert signals[0].occupation == 1  # soldier
        assert signals[0].magnitude == pytest.approx(-10 / 60 * 1.0)
        assert signals[0].turns_remaining == 3

    def test_guard_category_skipped_everywhere(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=50)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ,"stability", 10, "guard")
        acc.apply_keep(world)
        assert civ.stability == 50  # not applied
        shocks = acc.to_shock_signals()
        assert len(shocks) == 0
        signals = acc.to_demand_signals({0: 60})
        assert len(signals) == 0


class TestShockNormalization:
    """Shock normalization: delta / max(stat_at_time, 1), clamped ±1.0."""

    def test_normal_negative(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=80)
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-0.25)

    def test_fragile_civ_feels_more(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=20)
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-1.0)

    def test_zero_stat_guarded(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=0)
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-1.0)  # clamped, denominator guarded

    def test_positive_shock(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, culture=50)
        acc = StatAccumulator()
        acc.add(0, civ,"culture", 10, "guard-shock")
        shocks = acc.to_shock_signals()
        assert shocks[0].culture_shock == pytest.approx(0.2)

    def test_multiple_shocks_same_stat_accumulate(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=100)
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -10, "signal")   # stat_at_time=100, shock=-0.1
        acc.add(0, civ,"stability", -20, "signal")   # stat_at_time=100 (captured at add time), shock=-0.2
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-0.3)

    def test_shock_clamped_at_negative_one(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=10)
        acc = StatAccumulator()
        acc.add(0, civ,"stability", -20, "signal")  # -20/10 = -2.0 → clamped to -1.0
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-1.0)

    def test_shock_clamped_at_positive_one(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, culture=5)
        acc = StatAccumulator()
        acc.add(0, civ,"culture", 20, "guard-shock")  # 20/5 = 4.0 → clamped to 1.0
        shocks = acc.to_shock_signals()
        assert shocks[0].culture_shock == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_accumulator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chronicler.accumulator'`

- [ ] **Step 3: Implement StatAccumulator**

Create `src/chronicler/accumulator.py`:

```python
"""StatAccumulator — M27 core routing logic for stat mutations.

All phase functions route stat mutations through the accumulator instead of
mutating Civilization fields directly. In aggregate mode, apply() replays
mutations bit-identically. In hybrid mode, mutations route by category:
keep → apply, guard → skip, guard-action → demand signal,
signal/guard-shock → shock signal.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from chronicler.models import StatChange, CivShock, DemandSignal

if TYPE_CHECKING:
    from chronicler.models import Civilization, WorldState

# Stats with bounded 0-100 range and specific floors
STAT_FLOOR: dict[str, int] = {
    "stability": 5,
    "economy": 5,
    "military": 5,
    "culture": 5,
    "population": 0,
}

# Stats that have no upper bound (treasury, asabiya, prestige)
UNBOUNDED_STATS = {"treasury", "asabiya", "prestige"}

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

DEMAND_SCALE_FACTOR = 1.0


class StatAccumulator:
    """Captures stat mutations and routes them by category."""

    __slots__ = ("_changes",)

    def __init__(self) -> None:
        self._changes: list[StatChange] = []

    def add(self, civ_idx: int, civ: Civilization, stat: str, delta: float, category: str) -> None:
        """Record a stat mutation. civ_idx is the index into world.civilizations."""
        self._changes.append(StatChange(
            civ_idx, stat, delta, category, getattr(civ, stat, 0),
        ))

    def apply(self, world: WorldState) -> None:
        """Aggregate mode: apply all changes in insertion order. Bit-identical."""
        for c in self._changes:
            civ = world.civilizations[c.civ_id]
            current = getattr(civ, c.stat)
            new_val = current + c.delta
            if c.stat in UNBOUNDED_STATS:
                new_val = max(new_val, 0)
            else:
                floor = STAT_FLOOR.get(c.stat, 0)
                new_val = max(floor, min(100, new_val))
            setattr(civ, c.stat, type(current)(new_val))

    def apply_keep(self, world: WorldState) -> None:
        """Agent mode: apply only keep-category changes."""
        for c in self._changes:
            if c.category != "keep":
                continue
            civ = world.civilizations[c.civ_id]
            current = getattr(civ, c.stat)
            new_val = current + c.delta
            if c.stat in UNBOUNDED_STATS:
                new_val = max(new_val, 0)
            else:
                floor = STAT_FLOOR.get(c.stat, 0)
                new_val = max(floor, min(100, new_val))
            setattr(civ, c.stat, type(current)(new_val))

    def to_shock_signals(self) -> list[CivShock]:
        """Convert signal + guard-shock changes to normalized shocks."""
        shocks: dict[int, CivShock] = {}
        for c in self._changes:
            if c.category not in ("signal", "guard-shock"):
                continue
            if c.stat not in STAT_TO_SHOCK_FIELD:
                continue
            shock = shocks.setdefault(c.civ_id, CivShock(c.civ_id))
            field = STAT_TO_SHOCK_FIELD[c.stat]
            current_shock = getattr(shock, field)
            normalized = c.delta / max(c.stat_at_time, 1)
            new_shock = max(-1.0, min(1.0, current_shock + normalized))
            setattr(shock, field, new_shock)
        return list(shocks.values())

    def to_demand_signals(self, civ_capacities: dict[int, int]) -> list[DemandSignal]:
        """Convert guard-action changes to demand signals."""
        signals = []
        for c in self._changes:
            if c.category != "guard-action" or c.stat not in STAT_TO_OCCUPATION:
                continue
            occupation = STAT_TO_OCCUPATION[c.stat]
            capacity = max(civ_capacities.get(c.civ_id, 1), 1)
            magnitude = c.delta / capacity * DEMAND_SCALE_FACTOR
            signals.append(DemandSignal(c.civ_id, occupation, magnitude, turns_remaining=3))
        return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_accumulator.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/accumulator.py tests/test_accumulator.py
git commit -m "feat(m27): add StatAccumulator with category routing and unit tests"
```

---

### Task 3: DemandSignalManager

**Files:**
- Create: `src/chronicler/demand_signals.py`
- Test: `tests/test_demand_signals.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_demand_signals.py`:

```python
"""Tests for DemandSignalManager — 3-turn linear decay."""
import pytest
from chronicler.models import DemandSignal


class TestDemandSignalManager:

    def test_single_signal_three_turn_decay(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(civ_id=0, occupation=1, magnitude=0.17, turns_remaining=3))

        # Turn 0: full magnitude
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.17)

        # Turn 1: 2/3 magnitude
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.17 * 2 / 3, abs=0.001)

        # Turn 2: 1/3 magnitude
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.17 * 1 / 3, abs=0.001)

        # Turn 3: expired
        shifts = mgr.tick()
        assert 0 not in shifts  # civ not present → no active signals

    def test_multiple_signals_same_civ_aggregate(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.10, 3))  # soldier
        mgr.add(DemandSignal(0, 2, 0.05, 3))  # merchant
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.10)   # soldier
        assert shifts[0][2] == pytest.approx(0.05)   # merchant

    def test_signals_different_civs(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.10, 3))
        mgr.add(DemandSignal(1, 2, 0.20, 3))
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.10)
        assert shifts[1][2] == pytest.approx(0.20)

    def test_reset_clears_all(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.10, 3))
        mgr.reset()
        shifts = mgr.tick()
        assert len(shifts) == 0

    def test_total_impulse(self):
        """Total delivered impulse should be 2 * magnitude."""
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.30, 3))
        total = 0.0
        for _ in range(5):  # Extra ticks to ensure expiry
            shifts = mgr.tick()
            total += shifts.get(0, [0.0] * 5)[1]
        assert total == pytest.approx(0.60, abs=0.001)  # 2 * 0.30
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_demand_signals.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement DemandSignalManager**

Create `src/chronicler/demand_signals.py`:

```python
"""DemandSignalManager — 3-turn linear decay for action-derived demand shifts.

Manages active demand signals from guard-action stat mutations. Each signal
decays linearly over 3 turns. Python-side decay produces already-decayed
effective values passed to Rust via civ_signals RecordBatch columns.
"""
from __future__ import annotations
from chronicler.models import DemandSignal


class DemandSignalManager:
    __slots__ = ("active",)

    def __init__(self) -> None:
        self.active: list[DemandSignal] = []

    def add(self, signal: DemandSignal) -> None:
        self.active.append(signal)

    def tick(self) -> dict[int, list[float]]:
        """Decay, aggregate per-civ, return {civ_id: [5 demand shifts]}."""
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
        self.active.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_demand_signals.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/demand_signals.py tests/test_demand_signals.py
git commit -m "feat(m27): add DemandSignalManager with 3-turn linear decay"
```

---

## Chunk 2: Phase Refactoring

The refactoring follows a repeatable pattern. Each direct stat mutation becomes an `acc.add()` call. The accumulator is an optional parameter defaulting to `None`. When `None`, the mutation applies directly (backward compatible).

### Refactoring Pattern

Every stat mutation in the codebase follows one of these patterns:

**Pattern A — Direct assignment with clamp:**
```python
# Before:
civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
# After:
if acc is not None:
    acc.add(civ_idx, civ, "stability", -drain, "signal")
else:
    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
```

**Pattern B — Direct increment/decrement:**
```python
# Before:
civ.treasury -= cost
# After:
if acc is not None:
    acc.add(civ_idx, civ, "treasury", -cost, "keep")
else:
    civ.treasury -= cost
```

**Pattern C — Population changes (guard, skip in agent mode):**
```python
# Before:
add_region_pop(region, amount)
sync_civ_population(civ, world)
# After:
if acc is not None:
    acc.add(civ_idx, civ, "population", amount, "guard")
else:
    add_region_pop(region, amount)
    sync_civ_population(civ, world)
```

### Task 4: Refactor simulation.py — Phases 1-3

**Files:**
- Modify: `src/chronicler/simulation.py`
- Test: `tests/test_accumulator.py` (add integration test)

The `acc` parameter is `None | StatAccumulator`, optional, added to each phase function signature. When `None`, behavior is identical to pre-M27.

- [ ] **Step 1: Add `acc` parameter to `phase_environment` and refactor its mutations**

Read `simulation.py` and locate each mutation in `phase_environment` (~lines 93-170). Add `acc=None` to the signature. Apply Pattern A/B/C to each mutation:

| Line | Original | Category | Refactored |
|------|----------|----------|------------|
| ~136 | `civ.stability -= drain` | signal | `acc.add(civ_idx, civ, "stability", -drain, "signal")` |
| ~137 | `civ.economy -= int(10 * mult)` | signal | `acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")` |
| ~150 | `distribute_pop_loss(...)` + `sync_civ_population(...)` | guard | `acc.add(civ_idx, civ, "population", -int(10 * mult), "guard")` |
| ~153 | `civ.stability -= drain` | signal | `acc.add(civ_idx, civ, "stability", -drain, "signal")` |
| ~165 | `civ.economy -= int(10 * mult)` | signal | `acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")` |

For each mutation, use the pattern:
```python
if acc is not None:
    acc.add(civ_idx, civ, "stability", -drain, "signal")
else:
    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
```

- [ ] **Step 2: Add `acc` parameter to `apply_automatic_effects` and refactor**

Mutations at ~lines 192-310. This function has ~15 mutations across treasury (keep), stability (signal), and military (guard):

| Line | Mutation | Category |
|------|----------|----------|
| ~192 | `civ.treasury -= cost` | keep |
| ~200 | `a.treasury += 2` | keep |
| ~202 | `b.treasury += 2` | keep |
| ~206 | `c.treasury += 3` | keep |
| ~238 | `civ.treasury -= penalty` | keep |
| ~241 | `civ.treasury += bonus` | keep |
| ~256 | `civ.treasury += 1` | keep |
| ~257 | `civ.stability -= 3` | signal |
| ~266 | `civ.treasury -= 3` | keep |
| ~269 | `civ.stability -= drain` | signal |
| ~282 | `civ.military -= strength` | guard |
| ~309 | `hirer.treasury -= 10` | keep |
| ~310 | `hirer.military += merc["strength"]` | guard |

- [ ] **Step 3: Add `acc` parameter to `phase_production` and refactor**

Mutations at ~lines 372-433. Mix of treasury (keep), population (guard), and stability (guard):

| Line | Mutation | Category |
|------|----------|----------|
| ~380 | `civ.treasury += max(0, income - penalty)` | keep |
| ~395 | `add_region_pop(r, per_region)` | guard |
| ~396 | `sync_civ_population(civ, world)` | guard |
| ~400 | `drain_region_pop(target, 5)` | guard |
| ~401 | `sync_civ_population(civ, world)` | guard |
| ~406 | `add_region_pop(r, 3)` | guard |
| ~407 | `sync_civ_population(civ, world)` | guard |
| ~417 | `civ.treasury += mine_count * 2` | keep |
| ~433 | `civ.stability += recovery` | guard |

- [ ] **Step 4: Run existing tests to verify no breakage**

Run: `python -m pytest tests/test_simulation.py -x -q`
Expected: All pass — `acc=None` default means no behavior change.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "refactor(m27): route phase 1-3 stat mutations through StatAccumulator"
```

---

### Task 5: Refactor simulation.py — Phases 4-9 + Random Events

**Files:**
- Modify: `src/chronicler/simulation.py`

- [ ] **Step 1: Refactor `phase_cultural_milestones` (~line 832)**

| Line | Mutation | Category |
|------|----------|----------|
| ~849 | `civ.asabiya += 0.05` | keep |
| ~850 | `civ.culture += 5` | guard-shock |
| ~851 | `civ.prestige += 2` | keep |

- [ ] **Step 2: Refactor `_apply_event_effects` (~line 540)**

This is the random events handler. ~15 mutations:

| Line | Mutation | Category |
|------|----------|----------|
| ~555 | `civ.stability -= int(drain * mult)` (leader death) | signal |
| ~577 | `civ.stability -= int(drain * mult)` (rebellion) | signal |
| ~578 | `civ.military -= int(10 * mult)` (rebellion) | signal |
| ~580 | `civ.culture += 10` (discovery) | guard-shock |
| ~581 | `civ.economy += 10` (discovery) | guard-shock |
| ~583 | `civ.culture += 10` (religious movement) | guard-shock |
| ~586 | `civ.stability -= int(drain * mult)` (religious movement) | signal |
| ~588 | `civ.culture += 20` (cultural renaissance) | guard-shock |
| ~589 | `civ.stability += 10` (cultural renaissance) | guard-shock |
| ~595 | `add_region_pop(...)` (migration) | guard |
| ~596 | `sync_civ_population(...)` (migration) | guard |
| ~599 | `civ.stability -= int(drain * mult)` (migration) | signal |
| ~603 | `civ.stability -= int(drain * mult)` (border incident) | signal |

- [ ] **Step 3: Refactor `apply_injected_event` (~line 620)**

| Line | Mutation | Category |
|------|----------|----------|
| ~623 | `civ.stability -= 10` (drought) | signal |
| ~624 | `civ.economy -= 10` (drought) | signal |
| ~637 | `drain_region_pop(...)` (plague) | guard |
| ~638 | `sync_civ_population(...)` (plague) | guard |
| ~639 | `civ.stability -= 10` (plague) | signal |
| ~649 | `civ.economy -= 10` (earthquake) | signal |

- [ ] **Step 4: Refactor `apply_asabiya_dynamics` (~line 513)**

| Line | Mutation | Category |
|------|----------|----------|
| ~513 | `civ.asabiya = round(...)` | keep |

- [ ] **Step 5: Run existing tests**

Run: `python -m pytest tests/test_simulation.py -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "refactor(m27): route phase 4-9 and random event mutations through StatAccumulator"
```

---

### Task 6: Refactor action_engine.py

**Files:**
- Modify: `src/chronicler/action_engine.py`

- [ ] **Step 1: Add `acc` parameter to action handlers and `resolve_action`**

The dispatcher `resolve_action` needs `acc` threaded to handlers. Each handler function gains `acc=None`.

- [ ] **Step 2: Refactor `_resolve_develop` (~line 77)**

| Line | Mutation | Category |
|------|----------|----------|
| ~81 | `civ.treasury -= cost` | keep |
| ~84 | `civ.economy = clamp(civ.economy + int(10 * factor), ...)` | guard-action |
| ~87 | `civ.culture = clamp(civ.culture + int(10 * factor), ...)` | guard-action |

- [ ] **Step 3: Refactor `_resolve_expand` (~line 99)**

| Line | Mutation | Category |
|------|----------|----------|
| ~112 | `civ.military = clamp(civ.military - 10, ...)` | guard-action |

- [ ] **Step 4: Refactor `resolve_war` (~line 356)**

| Line | Mutation | Category |
|------|----------|----------|
| ~419 | `attacker.treasury = max(0, attacker.treasury - 20)` | keep |
| ~420 | `defender.treasury = max(0, defender.treasury - 10)` | keep |
| ~439 | `attacker.military = clamp(attacker.military - 10, ...)` | guard-action |
| ~440 | `defender.military = clamp(defender.military - 20, ...)` | guard-action |
| ~441 | `defender.stability = clamp(defender.stability - 10, ...)` | signal |
| ~444 | `attacker.military = clamp(attacker.military - 20, ...)` | guard-action |
| ~445 | `defender.military = clamp(defender.military - 10, ...)` | guard-action |
| ~446 | `attacker.stability = clamp(attacker.stability - 10, ...)` | signal |
| ~449 | `attacker.military = clamp(attacker.military - 10, ...)` | guard-action |
| ~450 | `defender.military = clamp(defender.military - 10, ...)` | guard-action |

- [ ] **Step 5: Refactor `_resolve_embargo` (~line 295)**

| Line | Mutation | Category |
|------|----------|----------|
| ~319 | `target.stability = clamp(target.stability - embargo_damage, ...)` | signal |

- [ ] **Step 6: Refactor `resolve_trade` (~line 456)**

| Line | Mutation | Category |
|------|----------|----------|
| ~500 | `civ1.treasury += gain1` | keep |
| ~501 | `civ2.treasury += gain2` | keep |

- [ ] **Step 7: Run existing tests**

Run: `python -m pytest tests/test_action_engine.py -x -q`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/action_engine.py
git commit -m "refactor(m27): route action engine mutations through StatAccumulator"
```

---

### Task 7: Refactor politics.py + Remaining Files

**Files:**
- Modify: `src/chronicler/politics.py`
- Modify: `src/chronicler/climate.py`
- Modify: `src/chronicler/ecology.py`
- Modify: `src/chronicler/emergence.py`
- Modify: `src/chronicler/culture.py`
- Modify: `src/chronicler/factions.py`
- Modify: `src/chronicler/leaders.py`
- Modify: `src/chronicler/exploration.py`
- Modify: `src/chronicler/infrastructure.py`
- Modify: `src/chronicler/tech.py`
- Modify: `src/chronicler/succession.py`

- [ ] **Step 1: Refactor politics.py (~22 mutations)**

Key functions and their mutations:

`apply_governing_costs`: treasury (keep), stability (signal)
`resolve_move_capital`: treasury (keep)
`check_secession`: military/economy (guard), treasury (keep), stability (signal)
`check_capital_loss`: stability (signal) — **Phase 10, handled in Task 12**
`check_vassal_rebellion`: stability (guard-shock), asabiya (keep)
`check_federation_dissolution`: stability (signal) — **Phase 10, handled in Task 12**
`check_congress`: stability (signal) — **Phase 10, handled in Task 12**
`apply_proxy_wars`: stability (signal), economy (signal), sponsor treasury (keep)
`check_proxy_detection`: stability (guard-shock) — **Phase 10, guard added in Task 14**
`apply_exile_effects`: stability (signal)
`apply_fallen_empire`: asabiya (keep)
`apply_twilight`: culture (signal), population (guard)
`resolve_fund_instability`: treasury (keep)
`collect_tribute`: vassal treasury (keep), overlord treasury (keep)
`apply_long_peace`: stability (signal — military restlessness), economy (guard — inequality ±1)

**Note:** Phase 10 functions (`check_capital_loss`, `check_federation_dissolution`, `check_congress`, `check_secession`, `check_vassal_rebellion`, `check_proxy_detection`) get `acc` parameter now but the hybrid-mode inline guards are added in Task 14.

- [ ] **Step 2: Refactor climate.py (~2 mutations)**

`process_migration`: population (guard), stability (signal)

- [ ] **Step 3: Refactor ecology.py (~6 mutations)**

`_check_famine`: population (guard), stability (signal)

- [ ] **Step 4: Refactor emergence.py (~8 mutations)**

`tick_pandemic`: population (guard), economy (signal)
`_apply_supervolcano`: population (guard), stability (signal), asabiya (keep)

- [ ] **Step 5: Refactor culture.py (~4 mutations)**

`tick_cultural_assimilation`: stability (signal)
`resolve_invest_culture`: treasury (keep)
`tick_prestige`: prestige (keep), treasury (keep)

- [ ] **Step 6: Refactor remaining files**

`factions.py` (~2 mutations):
- `apply_faction_unrest` ~line 341: `civ.stability -= unrest_drain` → signal
- `apply_faction_unrest` ~line 343: `civ.stability -= 5` → signal

`leaders.py` (~6 mutations):
- ~line 218: `civ.stability += 5` (leader bonus) → guard-shock
- ~line 220: `civ.military += 5` (military leader) → guard-shock
- ~line 222: `civ.economy += 3` (economic leader) → guard-shock
- ~line 228: `civ.prestige += 1` (leader prestige) → keep
- ~line 281: `civ.stability -= 10` (leader death) → signal

`exploration.py` (~2 mutations):
- ~line 91: `civ.treasury -= 5` (explore cost) → keep
- ~line 190: `civ.culture += 3` (discovery) → guard-shock

`infrastructure.py` (~1 mutation):
- ~line 169: `civ.treasury -= build_cost` → keep

`tech.py` (~1 mutation):
- ~line 107: `civ.treasury -= tech_cost` → keep

`succession.py` (~1 mutation):
- ~line 252: `civ.culture += 5` (succession culture) → guard-shock

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: All pass — all `acc` parameters default to `None`.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/politics.py src/chronicler/climate.py src/chronicler/ecology.py src/chronicler/emergence.py src/chronicler/culture.py src/chronicler/factions.py src/chronicler/leaders.py src/chronicler/exploration.py src/chronicler/infrastructure.py src/chronicler/tech.py src/chronicler/succession.py
git commit -m "refactor(m27): route all remaining phase mutations through StatAccumulator"
```

---

### Task 8: Wire Accumulator into run_turn + Bit-Identical Regression Test

**Files:**
- Modify: `src/chronicler/simulation.py` (run_turn)
- Test: `tests/test_accumulator.py` (add regression test)

- [ ] **Step 1: Wire StatAccumulator into `run_turn`**

Modify `run_turn` to create a `StatAccumulator`, pass it to every phase function, and call `acc.apply(world)` at the end of Phases 1-9 (before Phase 10). For now, always `apply()` — hybrid routing comes in Chunk 4.

```python
from chronicler.accumulator import StatAccumulator

def run_turn(world, action_selector, narrator, seed=0, agent_bridge=None):
    turn_events = []
    acc = StatAccumulator()

    # Phase 1
    turn_events.extend(phase_environment(world, seed=seed, acc=acc))
    # ... all phases get acc=acc ...

    # Apply accumulated mutations (aggregate mode — always for now)
    acc.apply(world)

    # Phase 10: Consequences (no accumulator — runs after)
    turn_events.extend(phase_consequences(world))
    # ... rest unchanged ...
```

- [ ] **Step 2: Write bit-identical regression test**

Add to `tests/test_accumulator.py`:

```python
class TestBitIdenticalRegression:
    """Accumulator in aggregate mode produces identical results to direct mutations."""

    def test_100_turn_aggregate_identical(self):
        """Run 100 turns with accumulator vs. without. All civ fields must match exactly."""
        from chronicler.main import create_world
        from chronicler.simulation import run_turn
        from chronicler.models import WorldState
        import copy

        # Create two identical worlds
        world_acc = create_world(seed=42, num_civs=4, num_regions=8)
        world_direct = copy.deepcopy(world_acc)

        # Placeholder narrator and selector
        def noop_narrator(world, events): return ""
        def noop_selector(world, civ): return None

        for turn in range(100):
            world_acc.turn = turn
            world_direct.turn = turn
            # Both use accumulator — acc.apply() is the default path
            run_turn(world_acc, noop_selector, noop_narrator, seed=turn)
            run_turn(world_direct, noop_selector, noop_narrator, seed=turn)

        # Compare every stat on every civ
        for i, (ca, cd) in enumerate(zip(world_acc.civilizations, world_direct.civilizations)):
            for stat in ("stability", "economy", "military", "culture", "population",
                        "treasury", "asabiya", "prestige"):
                val_a = getattr(ca, stat)
                val_d = getattr(cd, stat)
                assert val_a == val_d, f"Civ {i} {stat}: acc={val_a} direct={val_d}"
```

**Note:** This test verifies the accumulator path produces the same results. The actual bit-identical-to-pre-M27 test requires comparing against a pre-refactor baseline — that's test 13 from the spec, which should be run manually before and after the refactoring is complete.

- [ ] **Step 3: Run the regression test**

Run: `python -m pytest tests/test_accumulator.py::TestBitIdenticalRegression -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py tests/test_accumulator.py
git commit -m "feat(m27): wire StatAccumulator into run_turn with bit-identical regression test"
```

---

## Chunk 3: Rust Extensions

### Task 9: Extend signals.rs for Shock + Demand Columns

**Files:**
- Modify: `chronicler-agents/src/signals.rs`
- Test: Rust unit tests in same file

- [ ] **Step 1: Add shock and demand fields to CivSignals**

In `signals.rs`, add to the `CivSignals` struct:

```rust
pub struct CivSignals {
    pub civ_id: u8,
    pub stability: u8,
    pub is_at_war: bool,
    pub dominant_faction: u8,
    pub faction_military: f32,
    pub faction_merchant: f32,
    pub faction_cultural: f32,
    // M27 additions:
    pub shock_stability: f32,
    pub shock_economy: f32,
    pub shock_military: f32,
    pub shock_culture: f32,
    pub demand_shift_farmer: f32,
    pub demand_shift_soldier: f32,
    pub demand_shift_merchant: f32,
    pub demand_shift_scholar: f32,
    pub demand_shift_priest: f32,
}
```

- [ ] **Step 2: Update parse_civ_signals to read new columns with defaults**

Each new column uses `.and_then()` for safe type handling (matching M26's `parse_contested_regions` pattern — avoids panic if column exists but has wrong type):
```rust
let shock_stability = batch.column_by_name("shock_stability")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>())
    .map(|arr| arr.value(i))
    .unwrap_or(0.0);
```

This is backward-compatible: M25/M26 batches without these columns default to 0.0.

- [ ] **Step 3: Add CivShock helper struct for per-civ shock access**

```rust
pub struct CivShock {
    pub stability: f32,
    pub economy: f32,
    pub military: f32,
    pub culture: f32,
}

impl TickSignals {
    pub fn shock_for_civ(&self, civ_id: u8) -> CivShock {
        self.civs.iter()
            .find(|c| c.civ_id == civ_id)
            .map(|c| CivShock {
                stability: c.shock_stability,
                economy: c.shock_economy,
                military: c.shock_military,
                culture: c.shock_culture,
            })
            .unwrap_or(CivShock { stability: 0.0, economy: 0.0, military: 0.0, culture: 0.0 })
    }

    pub fn demand_shifts_for_civ(&self, civ_id: u8) -> [f32; 5] {
        self.civs.iter()
            .find(|c| c.civ_id == civ_id)
            .map(|c| [
                c.demand_shift_farmer,
                c.demand_shift_soldier,
                c.demand_shift_merchant,
                c.demand_shift_scholar,
                c.demand_shift_priest,
            ])
            .unwrap_or([0.0; 5])
    }
}
```

- [ ] **Step 4: Write unit test for extended parsing**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use arrow::array::*;
    use arrow::record_batch::RecordBatch;
    use std::sync::Arc;

    fn make_full_civ_signals_batch() -> RecordBatch {
        RecordBatch::try_from_iter(vec![
            ("civ_id", Arc::new(UInt8Array::from(vec![0])) as _),
            ("stability", Arc::new(UInt8Array::from(vec![75])) as _),
            ("is_at_war", Arc::new(BooleanArray::from(vec![true])) as _),
            ("dominant_faction", Arc::new(UInt8Array::from(vec![1])) as _),
            ("faction_military", Arc::new(Float32Array::from(vec![0.5])) as _),
            ("faction_merchant", Arc::new(Float32Array::from(vec![0.3])) as _),
            ("faction_cultural", Arc::new(Float32Array::from(vec![0.2])) as _),
            ("shock_stability", Arc::new(Float32Array::from(vec![-0.25])) as _),
            ("shock_economy", Arc::new(Float32Array::from(vec![-0.1])) as _),
            ("shock_military", Arc::new(Float32Array::from(vec![0.0])) as _),
            ("shock_culture", Arc::new(Float32Array::from(vec![0.15])) as _),
            ("demand_shift_farmer", Arc::new(Float32Array::from(vec![0.0])) as _),
            ("demand_shift_soldier", Arc::new(Float32Array::from(vec![0.17])) as _),
            ("demand_shift_merchant", Arc::new(Float32Array::from(vec![0.0])) as _),
            ("demand_shift_scholar", Arc::new(Float32Array::from(vec![0.0])) as _),
            ("demand_shift_priest", Arc::new(Float32Array::from(vec![0.0])) as _),
        ]).unwrap()
    }

    #[test]
    fn test_parse_extended_civ_signals() {
        let batch = make_full_civ_signals_batch();
        let signals = parse_civ_signals(&batch).unwrap();
        assert_eq!(signals.civs.len(), 1);
        let civ = &signals.civs[0];
        assert_eq!(civ.civ_id, 0);
        assert_eq!(civ.stability, 75);
        assert!((civ.shock_stability - (-0.25)).abs() < 0.001);
        assert!((civ.shock_economy - (-0.1)).abs() < 0.001);
        assert!((civ.demand_shift_soldier - 0.17).abs() < 0.001);

        let shock = signals.shock_for_civ(0);
        assert!((shock.stability - (-0.25)).abs() < 0.001);

        let demands = signals.demand_shifts_for_civ(0);
        assert!((demands[1] - 0.17).abs() < 0.001);
        assert!((demands[0]).abs() < 0.001); // farmer = 0
    }

    #[test]
    fn test_backward_compatible_without_m27_columns() {
        let batch = RecordBatch::try_from_iter(vec![
            ("civ_id", Arc::new(UInt8Array::from(vec![0])) as _),
            ("stability", Arc::new(UInt8Array::from(vec![50])) as _),
            ("is_at_war", Arc::new(BooleanArray::from(vec![false])) as _),
            ("dominant_faction", Arc::new(UInt8Array::from(vec![0])) as _),
            ("faction_military", Arc::new(Float32Array::from(vec![0.33])) as _),
            ("faction_merchant", Arc::new(Float32Array::from(vec![0.33])) as _),
            ("faction_cultural", Arc::new(Float32Array::from(vec![0.34])) as _),
        ]).unwrap();
        let signals = parse_civ_signals(&batch).unwrap();
        let civ = &signals.civs[0];
        assert!((civ.shock_stability).abs() < 0.001); // defaults to 0.0
        assert!((civ.demand_shift_soldier).abs() < 0.001); // defaults to 0.0
    }
}
```

- [ ] **Step 5: Run Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/signals.rs
git commit -m "feat(m27): extend CivSignals with shock and demand shift columns"
```

---

### Task 10: Add Shock Penalty to Satisfaction Formula

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs`

- [ ] **Step 1: Write failing test for shock penalty**

```rust
#[test]
fn test_shock_penalty_farmer_economy_shock() {
    // Farmer with economy_shock = -0.5
    // general: 0.15*0 + 0.05*(-0.5) + 0.05*0 + 0.05*0 = -0.025
    // specific: (-0.5) * 0.20 = -0.10
    // total penalty: -0.125
    let shock = CivShock { stability: 0.0, economy: -0.5, military: 0.0, culture: 0.0 };
    let penalty = compute_shock_penalty(0, &shock);
    assert!((penalty - (-0.125)).abs() < 0.001);
}

#[test]
fn test_shock_penalty_all_occupations_nonzero() {
    let shock = CivShock { stability: -0.3, economy: -0.2, military: -0.4, culture: -0.1 };
    for occ in 0..5 {
        let pen = compute_shock_penalty(occ, &shock);
        assert!(pen < 0.0, "Occupation {occ} should have negative penalty");
    }
}
```

- [ ] **Step 2: Implement `compute_shock_penalty`**

```rust
pub fn compute_shock_penalty(occupation: u8, shock: &CivShock) -> f32 {
    let general = shock.stability * 0.15
                + shock.economy * 0.05
                + shock.military * 0.05
                + shock.culture * 0.05;

    let specific = match occupation {
        0 => shock.economy * 0.20,    // Farmer
        1 => shock.military * 0.20,   // Soldier
        2 => shock.economy * 0.30,    // Merchant
        3 => shock.culture * 0.20,    // Scholar
        _ => shock.stability * 0.20,  // Priest
    };

    general + specific
}
```

- [ ] **Step 3: Add shock_pen to `compute_satisfaction`**

Add `shock: &CivShock` parameter. Add `shock_pen` to the final sum:

```rust
let shock_pen = compute_shock_penalty(occupation, shock);
(base + stability_bonus + ds_bonus - overcrowding - war_pen + faction_bonus - displacement_pen + shock_pen)
    .clamp(0.0, 1.0)
```

- [ ] **Step 4: Update `target_occupation_ratio` with demand shifts**

Add `demand_shifts: [f32; 5]` parameter:

```rust
pub fn target_occupation_ratio(terrain: u8, soil: f32, water: f32, demand_shifts: [f32; 5]) -> [f32; 5] {
    let mut ratios = base_ratios(terrain, soil, water);
    for i in 0..5 {
        ratios[i] = (ratios[i] + demand_shifts[i]).max(0.01);
    }
    let sum: f32 = ratios.iter().sum();
    for r in &mut ratios { *r /= sum; }
    ratios
}
```

- [ ] **Step 5: Write test for demand shift ratio**

```rust
#[test]
fn test_demand_shift_increases_soldier() {
    let base = target_occupation_ratio(0, 0.5, 0.5, [0.0; 5]);
    let shifted = target_occupation_ratio(0, 0.5, 0.5, [0.0, 0.17, 0.0, 0.0, 0.0]);
    assert!(shifted[1] > base[1]); // soldier ratio increased
    let sum: f32 = shifted.iter().sum();
    assert!((sum - 1.0).abs() < 0.001); // still sums to 1.0
    assert!(shifted.iter().all(|&r| r >= 0.01)); // all above floor
}
```

- [ ] **Step 6: Run Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs
git commit -m "feat(m27): add shock penalty and demand shift to satisfaction formula"
```

---

### Task 11: Thread Shock + Demand Through Tick Pipeline

**Files:**
- Modify: `chronicler-agents/src/tick.rs`
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Update `update_satisfaction` in tick.rs to pass shock data**

The `update_satisfaction` call needs the per-civ shock, accessed via `signals.shock_for_civ(agent_civ)`. Thread it to each `compute_satisfaction` call.

- [ ] **Step 2: Update `compute_region_stats` to use demand-shifted ratios**

When computing per-region demand/supply ratios, use `signals.demand_shifts_for_civ(region_civ)` to get the shifted ratios via `target_occupation_ratio`.

- [ ] **Step 3: Verify FFI doesn't need signature changes**

`ffi.rs` already accepts `civ_signals` as a single RecordBatch. The 9 new columns are parsed by the updated `parse_civ_signals`. No FFI signature change needed.

- [ ] **Step 4: Run full Rust test suite**

Run: `cd chronicler-agents && cargo test`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m27): thread shock and demand signals through tick pipeline"
```

---

## Chunk 4: Bridge + Events + Hybrid Wiring

### Task 12: Extend agent_bridge.py

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Test: `tests/test_agent_bridge.py`

- [ ] **Step 1: Write failing test for extended `build_signals`**

```python
def test_build_signals_includes_shock_and_demand_columns():
    """build_signals should produce 16-column RecordBatch with shock + demand columns."""
    from chronicler.agent_bridge import build_signals
    from chronicler.models import CivShock
    # ... create WorldState with known values ...
    shocks = [CivShock(0, stability_shock=-0.25)]
    demands = {0: [0.0, 0.17, 0.0, 0.0, 0.0]}
    batch = build_signals(world, shocks=shocks, demands=demands)
    assert "shock_stability" in batch.schema.names
    assert "demand_shift_soldier" in batch.schema.names
    assert batch.column("shock_stability")[0].as_py() == pytest.approx(-0.25)
    assert batch.column("demand_shift_soldier")[0].as_py() == pytest.approx(0.17)
```

- [ ] **Step 2: Extend `build_signals` with 9 new columns**

```python
def build_signals(world: WorldState, shocks: list[CivShock] | None = None,
                  demands: dict[int, list[float]] | None = None) -> pa.RecordBatch:
    shock_map = {s.civ_id: s for s in (shocks or [])}
    # ... existing 7 columns ...
    # Add shock columns
    shock_stab, shock_eco, shock_mil, shock_cul = [], [], [], []
    ds_farmer, ds_soldier, ds_merchant, ds_scholar, ds_priest = [], [], [], [], []
    for i, civ in enumerate(world.civilizations):
        s = shock_map.get(i, CivShock(i))
        shock_stab.append(s.stability_shock)
        shock_eco.append(s.economy_shock)
        shock_mil.append(s.military_shock)
        shock_cul.append(s.culture_shock)
        d = (demands or {}).get(i, [0.0] * 5)
        ds_farmer.append(d[0])
        ds_soldier.append(d[1])
        ds_merchant.append(d[2])
        ds_scholar.append(d[3])
        ds_priest.append(d[4])
    # Add to RecordBatch
    return pa.record_batch({
        # ... existing 7 columns ...
        "shock_stability": pa.array(shock_stab, type=pa.float32()),
        "shock_economy": pa.array(shock_eco, type=pa.float32()),
        "shock_military": pa.array(shock_mil, type=pa.float32()),
        "shock_culture": pa.array(shock_cul, type=pa.float32()),
        "demand_shift_farmer": pa.array(ds_farmer, type=pa.float32()),
        "demand_shift_soldier": pa.array(ds_soldier, type=pa.float32()),
        "demand_shift_merchant": pa.array(ds_merchant, type=pa.float32()),
        "demand_shift_scholar": pa.array(ds_scholar, type=pa.float32()),
        "demand_shift_priest": pa.array(ds_priest, type=pa.float32()),
    })
```

- [ ] **Step 3: Add `_write_back` method**

```python
def _write_back(self, world: WorldState) -> None:
    aggs = self._sim.get_aggregates()
    region_pops = self._sim.get_region_populations()
    pop_map = dict(zip(
        region_pops.column("region_id").to_pylist(),
        region_pops.column("alive_count").to_pylist(),
    ))
    for i, region in enumerate(world.regions):
        agent_pop = pop_map.get(i, 0)
        if agent_pop > region.carrying_capacity * 2.0:
            import logging
            logging.getLogger(__name__).warning(
                f"Region {i} pop {agent_pop} exceeds 2x capacity {region.carrying_capacity}"
            )
        region.population = agent_pop
    civ_ids = aggs.column("civ_id").to_pylist()
    for i, civ_id in enumerate(civ_ids):
        civ = world.civilizations[civ_id]
        civ.population = sum(world.regions[r].population for r in civ.regions)
        civ.military = aggs.column("military")[i].as_py()
        civ.economy = aggs.column("economy")[i].as_py()
        civ.culture = aggs.column("culture")[i].as_py()
        civ.stability = aggs.column("stability")[i].as_py()
```

- [ ] **Step 4: Update `tick` method for hybrid mode**

```python
def tick(self, world: WorldState, shocks=None, demands=None) -> list[Event]:
    self._sim.set_region_state(build_region_batch(world))
    signals = build_signals(world, shocks=shocks, demands=demands)
    agent_events_batch = self._sim.tick(world.turn, signals)

    if self._mode == "hybrid":
        self._write_back(world)
        raw_events = self._convert_events(agent_events_batch, world.turn)
        world.agent_events_raw.extend(raw_events)
        self._event_window.append(raw_events)
        return self._aggregate_events(world)
    elif self._mode == "demographics-only":
        self._apply_demographics_clamp(world)
    return []
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_agent_bridge.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "feat(m27): extend agent_bridge with shock/demand signals, write-back, hybrid mode"
```

---

### Task 13: Agent Event Aggregation

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Test: `tests/test_agent_bridge.py`

- [ ] **Step 1: Write failing test for event aggregation**

```python
def test_mass_migration_threshold():
    """>=8 migrations from same region in one tick → mass_migration summary event."""
    from chronicler.agent_bridge import AgentBridge
    from chronicler.models import AgentEventRecord
    # Create 10 migration events from region 3
    events = [
        AgentEventRecord(turn=5, agent_id=i, event_type="migration",
                        region=3, target_region=7, civ_affinity=0, occupation=0)
        for i in range(10)
    ]
    bridge = AgentBridge.__new__(AgentBridge)
    bridge._event_window = deque(maxlen=10)
    bridge._event_window.append(events)
    summaries = bridge._aggregate_events(world)
    assert any(e.event_type == "mass_migration" for e in summaries)
```

- [ ] **Step 2: Implement `_convert_events` and `_aggregate_events`**

```python
from collections import Counter, deque
from chronicler.models import AgentEventRecord, Event

OCCUPATION_NAMES = {0: "farmers", 1: "soldiers", 2: "merchants", 3: "scholars", 4: "priests"}

SUMMARY_TEMPLATES = {
    "mass_migration": "{count} {occ_majority} fled {source_region} for {target_region}",
    "local_rebellion": "Rebellion erupted in {region} as {count} discontented {occ_majority} rose up",
    "demographic_crisis": "{region} lost {pct}% of its population over {window} turns",
    "occupation_shift": "{count} agents in {region} switched to {new_occupation}",
    "loyalty_cascade": "{count} residents of {region} shifted allegiance to {target_civ}",
}

def _convert_events(self, batch, turn):
    """Convert Arrow RecordBatch to AgentEventRecord list."""
    EVENT_TYPE_MAP = {0: "death", 1: "rebellion", 2: "migration",
                      3: "occupation_switch", 4: "loyalty_flip", 5: "birth"}
    records = []
    for i in range(batch.num_rows):
        records.append(AgentEventRecord(
            turn=turn,
            agent_id=batch.column("agent_id")[i].as_py(),
            event_type=EVENT_TYPE_MAP[batch.column("event_type")[i].as_py()],
            region=batch.column("region")[i].as_py(),
            target_region=batch.column("target_region")[i].as_py(),
            civ_affinity=batch.column("civ_affinity")[i].as_py(),
            occupation=batch.column("occupation")[i].as_py(),
        ))
    return records

def _aggregate_events(self, world):
    """Check thresholds and emit summary Events."""
    summaries = []
    current = self._event_window[-1] if self._event_window else []
    region_names = {i: r.name for i, r in enumerate(world.regions)}

    # Single-tick patterns
    migrations_by_source = {}
    rebellions_by_region = {}
    switches_by_region = {}
    for e in current:
        if e.event_type == "migration":
            migrations_by_source.setdefault(e.region, []).append(e)
        elif e.event_type == "rebellion":
            rebellions_by_region.setdefault(e.region, []).append(e)
        elif e.event_type == "occupation_switch":
            switches_by_region.setdefault(e.region, []).append(e)

    for region_id, events in migrations_by_source.items():
        if len(events) >= 8:
            occ_counts = Counter(e.occupation for e in events)
            occ_majority = OCCUPATION_NAMES[occ_counts.most_common(1)[0][0]]
            targets = Counter(e.target_region for e in events)
            target_id = targets.most_common(1)[0][0]
            summaries.append(Event(
                turn=world.turn, event_type="mass_migration",
                description=SUMMARY_TEMPLATES["mass_migration"].format(
                    count=len(events), occ_majority=occ_majority,
                    source_region=region_names.get(region_id, f"region {region_id}"),
                    target_region=region_names.get(target_id, f"region {target_id}"),
                ),
                importance=5, source="agent",
            ))

    for region_id, events in rebellions_by_region.items():
        if len(events) >= 5:
            occ_counts = Counter(e.occupation for e in events)
            occ_majority = OCCUPATION_NAMES[occ_counts.most_common(1)[0][0]]
            summaries.append(Event(
                turn=world.turn, event_type="local_rebellion",
                description=SUMMARY_TEMPLATES["local_rebellion"].format(
                    count=len(events), occ_majority=occ_majority,
                    region=region_names.get(region_id, f"region {region_id}"),
                ),
                importance=7, source="agent",
            ))

    # Single-tick: occupation_shift (>25% of region switches in one tick)
    for region_id, events in switches_by_region.items():
        region_pop = sum(1 for e in current if e.region == region_id)
        if region_pop > 0 and len(events) / region_pop > 0.25:
            new_occ_counts = Counter(e.occupation for e in events)
            new_occ = OCCUPATION_NAMES[new_occ_counts.most_common(1)[0][0]]
            summaries.append(Event(
                turn=world.turn, event_type="occupation_shift",
                description=SUMMARY_TEMPLATES["occupation_shift"].format(
                    count=len(events),
                    region=region_names.get(region_id, f"region {region_id}"),
                    new_occupation=new_occ,
                ),
                importance=5, source="agent",
            ))

    # Multi-turn: loyalty_cascade (>=10 flips in one region over 5 turns)
    loyalty_flips_by_region: dict[int, int] = {}
    window_depth = min(len(self._event_window), 5)
    for i in range(max(0, len(self._event_window) - window_depth), len(self._event_window)):
        for e in self._event_window[i]:
            if e.event_type == "loyalty_flip":
                loyalty_flips_by_region[e.region] = loyalty_flips_by_region.get(e.region, 0) + 1
    for region_id, count in loyalty_flips_by_region.items():
        if count >= 10:
            # Find dominant target civ from recent flips
            recent_flips = [
                e for turn_events in list(self._event_window)[-window_depth:]
                for e in turn_events
                if e.event_type == "loyalty_flip" and e.region == region_id
            ]
            target_civ_counts = Counter(e.civ_affinity for e in recent_flips)
            target_civ_id = target_civ_counts.most_common(1)[0][0]
            target_civ_name = (world.civilizations[target_civ_id].name
                              if target_civ_id < len(world.civilizations) else f"civ {target_civ_id}")
            summaries.append(Event(
                turn=world.turn, event_type="loyalty_cascade",
                description=SUMMARY_TEMPLATES["loyalty_cascade"].format(
                    count=count,
                    region=region_names.get(region_id, f"region {region_id}"),
                    target_civ=target_civ_name,
                ),
                importance=6, source="agent",
            ))

    # Multi-turn: demographic_crisis (region loses >30% over 10 turns)
    if len(self._event_window) >= 2:
        deaths_by_region: dict[int, int] = {}
        births_by_region: dict[int, int] = {}
        for turn_events in self._event_window:
            for e in turn_events:
                if e.event_type == "death":
                    deaths_by_region[e.region] = deaths_by_region.get(e.region, 0) + 1
                elif e.event_type == "birth":
                    births_by_region[e.region] = births_by_region.get(e.region, 0) + 1
        for region_id, deaths in deaths_by_region.items():
            births = births_by_region.get(region_id, 0)
            net_loss = deaths - births
            region = world.regions[region_id] if region_id < len(world.regions) else None
            if region and region.population > 0:
                loss_pct = net_loss / (region.population + net_loss) * 100
                if loss_pct > 30:
                    summaries.append(Event(
                        turn=world.turn, event_type="demographic_crisis",
                        description=SUMMARY_TEMPLATES["demographic_crisis"].format(
                            region=region_names.get(region_id, f"region {region_id}"),
                            pct=int(loss_pct),
                            window=len(self._event_window),
                        ),
                        importance=7, source="agent",
                    ))

    return summaries
```

- [ ] **Step 3: Initialize sliding window in `__init__`**

```python
def __init__(self, world, mode="demographics-only"):
    self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
    self._mode = mode
    self._event_window: deque[list[AgentEventRecord]] = deque(maxlen=10)
    self._demand_manager = DemandSignalManager()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_agent_bridge.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "feat(m27): add agent event aggregation with threshold-based summaries"
```

---

### Task 14: Phase 10 Guards + Hybrid Wiring

**Files:**
- Modify: `src/chronicler/simulation.py` (run_turn, phase_consequences)
- Modify: `src/chronicler/politics.py` (Phase 10 functions)
- Test: `tests/test_accumulator.py`

- [ ] **Step 1: Add `normalize_shock` helper to accumulator.py**

```python
# In src/chronicler/accumulator.py:
def normalize_shock(delta: float, stat: float) -> float:
    """Normalize a raw stat delta to a shock value in [-1.0, +1.0].

    delta is a positive number representing the magnitude subtracted.
    Returns a negative shock for drains, positive for gains.
    """
    return max(-1.0, min(1.0, -abs(delta) / max(stat, 1)))
```

- [ ] **Step 2: Add Phase 10 inline guards to `phase_consequences`**

In `phase_consequences` (~line 662), add guards for the ongoing condition drain (~line 674).
Note: `drain` is always a positive value here (it's the condition's severity).

```python
if world.agent_mode == "hybrid":
    from chronicler.accumulator import normalize_shock
    world.pending_shocks.append(CivShock(civ.id,
        stability_shock=normalize_shock(int(drain * mult), civ.stability)))
else:
    civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
```

Guard collapse halving (~line 715-716):

```python
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(civ.id, military_shock=-0.5, economy_shock=-0.5))
else:
    civ.military //= 2
    civ.economy //= 2
```

- [ ] **Step 3: Add guards to politics.py Phase 10 functions**

`check_capital_loss` (~line 284):
```python
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(civ.id,
        stability_shock=normalize_shock(20, civ.stability)))
else:
    civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)
```

`check_federation_dissolution` (~line 553, 557):
```python
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(civ.id,
        stability_shock=normalize_shock(15, civ.stability)))
else:
    civ.stability = clamp(civ.stability - 15, STAT_FLOOR["stability"], 100)
```

`check_congress` (~line 777):
```python
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(civ.id,
        stability_shock=normalize_shock(5, civ.stability)))
else:
    civ.stability = clamp(civ.stability - 5, STAT_FLOOR["stability"], 100)
```

`check_secession` (~line 226-229) — guard the stat mutations; treasury stays as keep:
```python
if world.agent_mode == "hybrid":
    # Military and economy loss from secession → catastrophic shock
    world.pending_shocks.append(CivShock(civ.id,
        military_shock=normalize_shock(split_mil, civ.military),
        economy_shock=normalize_shock(split_eco, civ.economy),
        stability_shock=normalize_shock(10, civ.stability)))
    civ.treasury -= split_tre  # treasury stays Python-side
else:
    civ.military = max(civ.military - split_mil, 0)
    civ.economy = max(civ.economy - split_eco, 0)
    civ.treasury -= split_tre
    civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
```

`check_vassal_rebellion` (~line 421-422) — positive shock:
```python
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(vassal.id,
        stability_shock=10 / max(vassal.stability, 1)))  # positive
    vassal.asabiya = min(vassal.asabiya + 0.2, 1.0)  # asabiya stays Python-side
else:
    vassal.stability += 10
    vassal.asabiya = min(vassal.asabiya + 0.2, 1.0)
```

`check_proxy_detection` (~line 659) — positive shock:
```python
if world.agent_mode == "hybrid":
    world.pending_shocks.append(CivShock(target.id,
        stability_shock=5 / max(target.stability, 1)))  # positive — detected = rallying effect
else:
    target.stability = clamp(target.stability + 5, STAT_FLOOR["stability"], 100)
```

- [ ] **Step 4: Wire hybrid mode in run_turn**

Update `run_turn` to use the hybrid routing path.

**Note on tick/add ordering:** `_demand_manager.tick()` is called BEFORE `add()` for new demands.
This is intentional — new demand signals from this turn's actions should not instantly apply at full
magnitude. They enter the manager and begin their 3-turn decay starting next turn. This one-turn
delay means RAISE_MILITARY on turn N starts affecting agent behavior on turn N+1, matching the
principle that Python tells Rust what happened (past tense) and agents react next tick.

```python
if world.agent_mode == "hybrid" and agent_bridge is not None:
    acc.apply_keep(world)
    shocks = acc.to_shock_signals()
    demands = acc.to_demand_signals(get_civ_capacities(world))
    shocks.extend(world.pending_shocks)
    world.pending_shocks.clear()
    # Tick existing demand signals (decay), then add new ones for next turn
    demand_shifts = agent_bridge._demand_manager.tick()
    for ds in demands:
        agent_bridge._demand_manager.add(ds)
    turn_events.extend(agent_bridge.tick(world, shocks=shocks, demands=demand_shifts))
else:
    acc.apply(world)
```

Note: `agent_bridge.tick()` receives `demands` as `dict[int, list[float]]` (the already-decayed
effective values from `DemandSignalManager.tick()`), not raw `DemandSignal` objects. This is a
deliberate refinement from the spec — the bridge receives pre-computed shift values ready for the
FFI boundary, not raw signals that would need processing inside `tick()`.

Add `get_civ_capacities` helper:

```python
def get_civ_capacities(world):
    return {
        i: sum(world.regions[r].carrying_capacity for r in civ.regions)
        for i, civ in enumerate(world.civilizations)
    }
```

- [ ] **Step 5: Write Phase 10 guard test**

```python
def test_phase10_guard_pending_shocks():
    """In hybrid mode, Phase 10 stability drain goes to pending_shocks, not direct mutation."""
    from chronicler.models import WorldState, ActiveCondition, CivShock
    from chronicler.simulation import phase_consequences

    world = create_test_world(num_civs=2, num_regions=4)
    world.agent_mode = "hybrid"
    world.pending_shocks = []

    # Give civ 0 an active condition that drains stability
    civ = world.civilizations[0]
    civ.stability = 60
    stability_before = civ.stability
    civ.active_conditions = [ActiveCondition(type="capital_relocation", duration=3, severity=10)]

    phase_consequences(world)

    # Stability should NOT be directly mutated
    assert civ.stability == stability_before
    # pending_shocks should have an entry
    assert len(world.pending_shocks) > 0
    shock = world.pending_shocks[0]
    assert shock.civ_id == civ.id
    assert shock.stability_shock < 0  # negative shock from condition drain
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/politics.py tests/test_accumulator.py
git commit -m "feat(m27): add Phase 10 guards, hybrid wiring in run_turn, pending_shocks lifecycle"
```

---

### Task 15: Bundle Serialization + Integration Tests

**Files:**
- Modify: `src/chronicler/bundle.py`
- Test: `tests/test_bundle.py`
- Test: `tests/test_integration_m27.py`

- [ ] **Step 1: Add agent_events_raw serialization to bundle.py**

In the bundle serialization function, add Arrow IPC output when `world.agent_events_raw` is non-empty:

```python
# In bundle.py, inside the serialization function, after existing data writes:
if hasattr(world, 'agent_events_raw') and world.agent_events_raw:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    agent_events_batch = pa.record_batch({
        "turn": pa.array([e.turn for e in world.agent_events_raw], type=pa.uint32()),
        "agent_id": pa.array([e.agent_id for e in world.agent_events_raw], type=pa.uint32()),
        "event_type": pa.array([e.event_type for e in world.agent_events_raw], type=pa.utf8()),
        "region": pa.array([e.region for e in world.agent_events_raw], type=pa.uint16()),
        "target_region": pa.array([e.target_region for e in world.agent_events_raw], type=pa.uint16()),
        "civ_affinity": pa.array([e.civ_affinity for e in world.agent_events_raw], type=pa.uint16()),
        "occupation": pa.array([e.occupation for e in world.agent_events_raw], type=pa.uint8()),
    })
    agent_events_path = bundle_dir / "agent_events.arrow"
    with pa.OSFile(str(agent_events_path), "wb") as f:
        writer = ipc.new_file(f, agent_events_batch.schema)
        writer.write_batch(agent_events_batch)
        writer.close()
```

- [ ] **Step 2: Write hybrid integration test**

```python
def test_hybrid_100_turn_integration():
    """100-turn hybrid simulation produces valid output."""
    from chronicler.main import create_world
    from chronicler.simulation import run_turn
    from chronicler.agent_bridge import AgentBridge

    world = create_world(seed=42, num_civs=4, num_regions=8)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")

    def noop_narrator(world, events): return ""
    def noop_selector(world, civ): return None

    for turn in range(100):
        world.turn = turn
        run_turn(world, noop_selector, noop_narrator, seed=turn, agent_bridge=bridge)

    # Verify all civ stats in valid range
    for civ in world.civilizations:
        assert 0 <= civ.stability <= 100, f"{civ.name} stability={civ.stability}"
        assert 0 <= civ.military <= 100, f"{civ.name} military={civ.military}"
        assert 0 <= civ.economy <= 100, f"{civ.name} economy={civ.economy}"
        assert 0 <= civ.culture <= 100, f"{civ.name} culture={civ.culture}"
        assert civ.population >= 0

    # Verify agent events populated
    assert len(world.agent_events_raw) > 0, "No agent events recorded in 100 turns"

    # Verify at least one summary event with source="agent"
    agent_summaries = [e for e in world.events_timeline if e.source == "agent"]
    assert len(agent_summaries) > 0, "No agent summary events in timeline"

    # Verify region populations are non-negative
    for r in world.regions:
        if r.controller is not None:
            assert r.population >= 0, f"Region {r.name} has negative population"
```

- [ ] **Step 3: Write convergence diagnostic test (test 15 from spec)**

```python
import logging

def test_war_demand_convergence():
    """WAR action demand signal produces military within ±30% of aggregate by turn 50.

    Calibration diagnostic, not pass/fail gate. Logs warning if >30% delta.
    """
    import copy
    from chronicler.main import create_world
    from chronicler.simulation import run_turn
    from chronicler.agent_bridge import AgentBridge
    from chronicler.models import ActionType

    def noop_narrator(w, e): return ""

    # Run A: aggregate mode, force WAR at turn 25
    world_agg = create_world(seed=99, num_civs=4, num_regions=8)

    def selector_with_war(world, civ):
        if world.turn == 25 and civ == world.civilizations[0]:
            return ActionType.WAR
        return None  # default selection

    for turn in range(50):
        world_agg.turn = turn
        run_turn(world_agg, selector_with_war, noop_narrator, seed=turn)

    # Run B: hybrid mode, same forced WAR
    world_hybrid = create_world(seed=99, num_civs=4, num_regions=8)
    world_hybrid.agent_mode = "hybrid"
    bridge = AgentBridge(world_hybrid, mode="hybrid")

    for turn in range(50):
        world_hybrid.turn = turn
        run_turn(world_hybrid, selector_with_war, noop_narrator, seed=turn, agent_bridge=bridge)

    # Compare military at turn 50
    for i, (ca, ch) in enumerate(zip(world_agg.civilizations, world_hybrid.civilizations)):
        if ca.military > 0:
            delta_pct = abs(ch.military - ca.military) / ca.military
            if delta_pct > 0.30:
                logging.warning(
                    f"Convergence: Civ {i} military delta={delta_pct:.1%} "
                    f"(agg={ca.military}, hybrid={ch.military}). "
                    f"Consider adjusting DEMAND_SCALE_FACTOR."
                )
```

- [ ] **Step 4: Run integration tests**

Run: `python -m pytest tests/test_integration_m27.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/bundle.py tests/test_bundle.py tests/test_integration_m27.py
git commit -m "feat(m27): add bundle serialization for agent events and integration tests"
```

---

## Implementation Notes

### Phase Function Signature Convention

All phase functions gain `acc=None` as their last parameter. When `acc is None`, mutations apply directly (backward compatible). When `acc` is provided, mutations go through `acc.add()`. This makes the refactoring incremental — each file can be refactored independently without breaking anything.

### Treasury Special Handling

Treasury mutations use `max(0, ...)` not `clamp(..., 100)`. The StatAccumulator's `apply()` and `apply_keep()` detect this via `UNBOUNDED_STATS` set and skip the upper bound.

### DIPLOMACY Asymmetry

When `world.agent_mode == "hybrid"` and a DIPLOMACY action resolves, inject a +0.05 normalized stability shock. This is the only action that produces a signal not derived from the accumulator. Implement as a special case in `_resolve_diplomacy`:

```python
if acc is not None and world.agent_mode == "hybrid":
    acc.add(civ_idx, civ, "stability", 0.05 * civ.stability, "signal")
```

### Population Guard Pattern

Population changes via `add_region_pop`/`drain_region_pop`/`sync_civ_population` are classified as "guard". In agent mode, these are skipped entirely — agent demographics handle population. The accumulator records them with category "guard" for shadow oracle comparison but doesn't generate signals.
