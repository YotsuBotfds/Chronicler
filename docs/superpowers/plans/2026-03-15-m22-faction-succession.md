# M22: Factions & Succession Integration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three-faction internal politics (military/merchant/cultural) that bias action selection, shape succession outcomes, and create path dependence through nonlinear tipping points.

**Architecture:** New `factions.py` module contains all faction logic. Data model types live in `models.py`. Integration points are additive modifications to `succession.py`, `action_engine.py`, `politics.py`, and `simulation.py`. The faction tick runs in phase 10 (consequences) after event-generating phases so current-turn outcomes feed influence shifts.

**Tech Stack:** Python 3.13, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-15-m22-faction-succession-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/chronicler/models.py` | FactionType enum, FactionState model, new fields on Civilization + CivSnapshot |
| `src/chronicler/factions.py` (new) | All faction logic: influence, normalization, weight modifiers, power struggles, succession candidates, crisis resolution, tick orchestration |
| `src/chronicler/succession.py` | M17 succession state machine — additive modifications for faction modifiers |
| `src/chronicler/politics.py` | Secession region scoring + absorption safety net |
| `src/chronicler/action_engine.py` | Faction weight modifier in `compute_weights()` |
| `src/chronicler/simulation.py` | `tick_factions()` call in phase 10 |
| `src/chronicler/movements.py` | Parallel `Event` emission for `movement_adoption` |
| `src/chronicler/culture.py` | Rename `_upgrade_disposition` → public |
| `src/chronicler/main.py` | Populate `factions` in CivSnapshot |
| `tests/test_factions.py` (new) | Tests for all faction logic |

---

## Chunk 1: Foundation — Data Model, Prerequisites, Core Functions

### Task 1: Data Model

**Files:**
- Modify: `src/chronicler/models.py`
- Test: `tests/test_factions.py` (create)

- [ ] **Step 1: Write the failing test for FactionType and FactionState**

Create `tests/test_factions.py`:

```python
"""Tests for faction system — influence, power struggles, weight modifiers, succession."""
import pytest
from chronicler.models import FactionType, FactionState, Civilization, Leader, CivSnapshot


class TestFactionDataModel:
    def test_faction_type_values(self):
        assert FactionType.MILITARY.value == "military"
        assert FactionType.MERCHANT.value == "merchant"
        assert FactionType.CULTURAL.value == "cultural"

    def test_faction_state_defaults(self):
        fs = FactionState()
        assert fs.influence[FactionType.MILITARY] == pytest.approx(0.33)
        assert fs.influence[FactionType.MERCHANT] == pytest.approx(0.33)
        assert fs.influence[FactionType.CULTURAL] == pytest.approx(0.34)
        assert fs.power_struggle is False
        assert fs.power_struggle_turns == 0

    def test_civilization_has_factions(self):
        leader = Leader(name="Test", trait="bold", reign_start=0)
        civ = Civilization(
            name="TestCiv", population=50, military=40, economy=60,
            culture=30, stability=70, regions=["r1"], leader=leader,
        )
        assert isinstance(civ.factions, FactionState)
        assert civ.founded_turn == 0

    def test_civ_snapshot_has_factions(self):
        snap = CivSnapshot(
            population=50, military=40, economy=60, culture=30,
            stability=70, treasury=100, asabiya=0.5, tech_era="tribal",
            trait="bold", regions=["r1"], leader_name="Test", alive=True,
        )
        assert snap.factions is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestFactionDataModel -v`
Expected: FAIL with `ImportError` — FactionType/FactionState not defined yet.

- [ ] **Step 3: Add FactionType, FactionState, and new fields to models.py**

In `src/chronicler/models.py`, add after the existing `Disposition` enum:

```python
class FactionType(str, Enum):
    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"


class FactionState(BaseModel):
    influence: dict[FactionType, float] = Field(
        default_factory=lambda: {
            FactionType.MILITARY: 0.33,
            FactionType.MERCHANT: 0.33,
            FactionType.CULTURAL: 0.34,
        }
    )
    power_struggle: bool = False
    power_struggle_turns: int = 0
```

Add two new fields to the `Civilization` model (after existing fields):

```python
factions: FactionState = Field(default_factory=FactionState)
founded_turn: int = 0
```

Add one new field to `CivSnapshot`:

```python
factions: FactionState | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_factions.py::TestFactionDataModel -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All existing tests pass. Default values ensure backward compatibility.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_factions.py
git commit -m "feat(m22): add FactionType, FactionState, and Civilization.factions data model"
```

---

### Task 2: Prerequisites — movement_adoption Event + upgrade_disposition

**Files:**
- Modify: `src/chronicler/movements.py`
- Modify: `src/chronicler/culture.py`

- [ ] **Step 1: Add parallel Event emission for movement_adoption**

In `src/chronicler/movements.py`, in the `_process_spread()` function, after the existing `NamedEvent` append (around line 108-115), add a parallel `Event` to `world.events_timeline`:

```python
                    # Existing NamedEvent (keep as-is):
                    world.named_events.append(NamedEvent(
                        name=f"{civ.name} adopts {movement.id.replace('_', ' ')}",
                        event_type="movement_adoption",
                        turn=world.turn,
                        actors=[civ.name, movement.origin_civ],
                        description=f"{civ.name} adopts a {movement.value_affinity}-aligned movement from {movement.origin_civ}.",
                        importance=5,
                    ))
                    # M22: Add parallel Event for events_timeline scanning
                    world.events_timeline.append(Event(
                        turn=world.turn, event_type="movement_adoption",
                        actors=[civ.name, movement.origin_civ],
                        description=f"{civ.name} adopts a {movement.value_affinity}-aligned movement from {movement.origin_civ}.",
                        importance=5,
                    ))
```

Add `Event` to the imports at the top of `movements.py` if not already imported.

- [ ] **Step 2: Rename _upgrade_disposition in culture.py**

In `src/chronicler/culture.py`, rename `_upgrade_disposition` to `upgrade_disposition` (line 24). This is a simple underscore removal. Also update the internal call site at culture.py:56 (`rel.disposition = _upgrade_disposition(rel.disposition)` → `rel.disposition = upgrade_disposition(rel.disposition)`).

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. The rename and new event emission don't break existing behavior.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/movements.py src/chronicler/culture.py
git commit -m "feat(m22): add movement_adoption Event emission, make upgrade_disposition public"
```

---

### Task 3: Core Faction Functions — Normalization, Shifts, Alignment

**Files:**
- Create: `src/chronicler/factions.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing tests for normalization and core helpers**

Append to `tests/test_factions.py`:

```python
from chronicler.factions import (
    normalize_influence,
    shift_faction_influence,
    get_dominant_faction,
    get_leader_faction_alignment,
    TRAIT_FACTION_MAP,
    FOCUS_FACTION_MAP,
)


class TestNormalization:
    def test_normalize_sums_to_one(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.5
        fs.influence[FactionType.MERCHANT] = 0.3
        fs.influence[FactionType.CULTURAL] = 0.2
        normalize_influence(fs)
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_normalize_enforces_floor(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.95
        fs.influence[FactionType.MERCHANT] = 0.04
        fs.influence[FactionType.CULTURAL] = 0.01
        normalize_influence(fs)
        assert fs.influence[FactionType.CULTURAL] >= 0.05
        assert fs.influence[FactionType.MERCHANT] >= 0.05
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_normalize_after_zero(self):
        """Floor prevents faction extinction."""
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 1.0
        fs.influence[FactionType.MERCHANT] = 0.0
        fs.influence[FactionType.CULTURAL] = 0.0
        normalize_influence(fs)
        assert fs.influence[FactionType.MERCHANT] >= 0.05
        assert fs.influence[FactionType.CULTURAL] >= 0.05


class TestCoreHelpers:
    def test_shift_faction_influence(self):
        fs = FactionState()
        shift_faction_influence(fs, FactionType.MILITARY, 0.10)
        assert fs.influence[FactionType.MILITARY] > 0.33
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_get_dominant_faction(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.6
        fs.influence[FactionType.MERCHANT] = 0.2
        fs.influence[FactionType.CULTURAL] = 0.2
        assert get_dominant_faction(fs) == FactionType.MILITARY

    def test_leader_alignment_military_trait(self):
        leader = Leader(name="Test", trait="aggressive", reign_start=0)
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.6
        fs.influence[FactionType.MERCHANT] = 0.2
        fs.influence[FactionType.CULTURAL] = 0.2
        # aggressive -> MILITARY, MILITARY influence is 0.6
        assert get_leader_faction_alignment(leader, fs) == pytest.approx(0.6)

    def test_leader_alignment_neutral_trait(self):
        leader = Leader(name="Test", trait="stubborn", reign_start=0)
        fs = FactionState()
        assert get_leader_faction_alignment(leader, fs) == pytest.approx(0.5)

    def test_trait_faction_map_covers_actual_traits(self):
        """All mapped traits exist in the game."""
        mapped = set(TRAIT_FACTION_MAP.keys())
        # These are from ALL_TRAITS in leaders.py
        actual_traits = {"ambitious", "cautious", "aggressive", "calculating",
                         "zealous", "opportunistic", "stubborn", "bold",
                         "shrewd", "visionary"}
        assert mapped.issubset(actual_traits)

    def test_focus_faction_map_covers_all_focuses(self):
        assert len(FOCUS_FACTION_MAP) == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestNormalization tests/test_factions.py::TestCoreHelpers -v`
Expected: FAIL with `ModuleNotFoundError` — `chronicler.factions` does not exist yet.

- [ ] **Step 3: Create factions.py with core functions**

Create `src/chronicler/factions.py`:

```python
"""M22: Faction system — influence, power struggles, weight modifiers, succession."""
from __future__ import annotations

from chronicler.models import (
    FactionType,
    FactionState,
    Civilization,
    Leader,
    Event,
)

# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

TRAIT_FACTION_MAP: dict[str, FactionType] = {
    "aggressive": FactionType.MILITARY,
    "bold": FactionType.MILITARY,
    "ambitious": FactionType.MILITARY,
    "cautious": FactionType.MERCHANT,
    "calculating": FactionType.MERCHANT,
    "shrewd": FactionType.MERCHANT,
    "visionary": FactionType.CULTURAL,
    "zealous": FactionType.CULTURAL,
}

FOCUS_FACTION_MAP: dict[str, FactionType] = {
    "navigation": FactionType.MERCHANT,
    "commerce": FactionType.MERCHANT,
    "banking": FactionType.MERCHANT,
    "agriculture": FactionType.MERCHANT,
    "mechanization": FactionType.MERCHANT,
    "railways": FactionType.MERCHANT,
    "networks": FactionType.MERCHANT,
    "metallurgy": FactionType.MILITARY,
    "fortification": FactionType.MILITARY,
    "naval_power": FactionType.MILITARY,
    "exploration": FactionType.MILITARY,
    "surveillance": FactionType.MILITARY,
    "scholarship": FactionType.CULTURAL,
    "printing": FactionType.CULTURAL,
    "media": FactionType.CULTURAL,
}

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def normalize_influence(factions: FactionState) -> None:
    """Normalize influence to sum=1.0 with 0.05 floor per faction."""
    total = sum(factions.influence.values())
    if total > 0:
        for ft in FactionType:
            factions.influence[ft] /= total
    for ft in FactionType:
        if factions.influence[ft] < 0.05:
            factions.influence[ft] = 0.05
    total = sum(factions.influence.values())
    for ft in FactionType:
        factions.influence[ft] /= total


def shift_faction_influence(
    factions: FactionState, faction_type: FactionType, amount: float,
) -> None:
    """Shift one faction's influence and re-normalize."""
    factions.influence[faction_type] += amount
    normalize_influence(factions)


def get_dominant_faction(factions: FactionState) -> FactionType:
    """Return the faction with highest influence."""
    return max(factions.influence, key=factions.influence.get)


def get_leader_faction_alignment(
    leader: Leader, factions: FactionState,
) -> float:
    """How well the leader's trait aligns with dominant faction (0.0–1.0)."""
    leader_faction = TRAIT_FACTION_MAP.get(leader.trait)
    if leader_faction is None:
        return 0.5
    return factions.influence.get(leader_faction, 0.33)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factions.py::TestNormalization tests/test_factions.py::TestCoreHelpers -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/factions.py tests/test_factions.py
git commit -m "feat(m22): core faction functions — normalization, shifts, alignment, mapping tables"
```

---

### Task 4: Event Scanning — Win Counting + Event Detection

**Files:**
- Modify: `src/chronicler/factions.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing tests for win counting**

Append to `tests/test_factions.py`:

```python
from chronicler.models import WorldState, Event
from chronicler.factions import count_faction_wins, _event_is_win


def _make_world(turn: int = 10, events: list[Event] | None = None) -> WorldState:
    """Minimal WorldState for testing."""
    world = WorldState(name="test", seed=42, turn=turn)
    if events:
        world.events_timeline = events
    return world


def _make_civ(name: str = "TestCiv") -> Civilization:
    leader = Leader(name="Leader", trait="bold", reign_start=0)
    return Civilization(
        name=name, population=50, military=40, economy=60,
        culture=30, stability=70, regions=["r1"], leader=leader,
    )


class TestWinCounting:
    def test_military_war_win_attacker(self):
        events = [Event(
            turn=5, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: attacker_wins.", importance=8,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 1

    def test_military_war_win_defender(self):
        events = [Event(
            turn=5, event_type="war", actors=["Enemy", "TestCiv"],
            description="Enemy attacked TestCiv: defender_wins.", importance=8,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 1

    def test_military_war_loss_not_counted(self):
        events = [Event(
            turn=5, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: defender_wins.", importance=8,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 0

    def test_military_expansion_success(self):
        events = [Event(
            turn=5, event_type="expand", actors=["TestCiv"],
            description="TestCiv expanded.", importance=6,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 1

    def test_merchant_trade_success(self):
        events = [Event(
            turn=5, event_type="trade", actors=["TestCiv", "Partner"],
            description="TestCiv traded.", importance=3,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MERCHANT, lookback=10) == 1

    def test_merchant_trade_failure_not_counted(self):
        events = [Event(
            turn=5, event_type="trade", actors=["TestCiv"],
            description="No partners.", importance=2,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MERCHANT, lookback=10) == 0

    def test_cultural_work(self):
        events = [Event(
            turn=5, event_type="cultural_work", actors=["TestCiv"],
            description="Cultural work.", importance=6,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.CULTURAL, lookback=10) == 1

    def test_cultural_movement_adoption(self):
        events = [Event(
            turn=5, event_type="movement_adoption", actors=["TestCiv", "Origin"],
            description="Adopted.", importance=5,
        )]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.CULTURAL, lookback=10) == 1

    def test_lookback_window_respected(self):
        events = [Event(
            turn=1, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: attacker_wins.", importance=8,
        )]
        world = _make_world(turn=20, events=events)
        civ = _make_civ()
        # Event at turn 1, lookback=10 from turn 20 -> min_turn=10, skipped
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestWinCounting -v`
Expected: FAIL with `ImportError` — `count_faction_wins` not defined yet.

- [ ] **Step 3: Implement win counting and event detection**

Add to `src/chronicler/factions.py`:

```python
# ---------------------------------------------------------------------------
# Event scanning
# ---------------------------------------------------------------------------

def _event_is_win(
    event: Event, civ: Civilization, faction_type: FactionType,
) -> bool:
    """Does this event count as a win for the given faction?"""
    if civ.name not in event.actors:
        return False
    if faction_type == FactionType.MILITARY:
        if event.event_type == "war" and len(event.actors) >= 2:
            is_attacker = event.actors[0] == civ.name
            if (is_attacker and "attacker_wins" in event.description) or \
               (not is_attacker and "defender_wins" in event.description):
                return True
        elif event.event_type == "expand" and event.importance >= 5:
            return True
    elif faction_type == FactionType.MERCHANT:
        if event.event_type == "trade" and len(event.actors) >= 2:
            return True
    elif faction_type == FactionType.CULTURAL:
        if event.event_type in ("cultural_work", "movement_adoption"):
            return True
    return False


def count_faction_wins(
    world, civ: Civilization, faction_type: FactionType, lookback: int = 10,
) -> int:
    """Count faction wins in recent events. Stateless — scans events_timeline."""
    min_turn = world.turn - lookback
    count = 0
    for event in world.events_timeline:
        if event.turn < min_turn:
            continue
        if _event_is_win(event, civ, faction_type):
            count += 1
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factions.py::TestWinCounting -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/factions.py tests/test_factions.py
git commit -m "feat(m22): event scanning — win counting and _event_is_win helper"
```

---

## Chunk 2: Integration — Weights, Power Struggles, Tick Orchestration

### Task 5: Action Weight Modifier

**Files:**
- Modify: `src/chronicler/factions.py`
- Modify: `src/chronicler/action_engine.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing tests for faction weight modifier**

Append to `tests/test_factions.py`:

```python
from chronicler.models import ActionType
from chronicler.factions import get_faction_weight_modifier, FACTION_WEIGHTS


class TestWeightModifier:
    def test_military_dominant_war_weight(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.6
        civ.factions.influence[FactionType.MERCHANT] = 0.2
        civ.factions.influence[FactionType.CULTURAL] = 0.2
        # 1.8 ^ 0.6 ≈ 1.43
        mod = get_faction_weight_modifier(civ, ActionType.WAR)
        assert mod == pytest.approx(1.8 ** 0.6, rel=0.01)

    def test_equal_influence_mild_bias(self):
        civ = _make_civ()
        # Default equal influence, CULTURAL is dominant at 0.34
        mod = get_faction_weight_modifier(civ, ActionType.WAR)
        # WAR for CULTURAL = 0.4, 0.4^0.34 ≈ 0.73
        assert mod == pytest.approx(0.4 ** 0.34, rel=0.01)

    def test_unlisted_action_returns_one(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.6
        civ.factions.influence[FactionType.MERCHANT] = 0.2
        civ.factions.influence[FactionType.CULTURAL] = 0.2
        # EXPLORE is in MILITARY table, but an action NOT in the table = 1.0
        # INVEST_CULTURE is not in MILITARY table -> 1.0^0.6 = 1.0
        mod = get_faction_weight_modifier(civ, ActionType.INVEST_CULTURE)
        assert mod == pytest.approx(1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestWeightModifier -v`
Expected: FAIL — `get_faction_weight_modifier` not defined.

- [ ] **Step 3: Implement get_faction_weight_modifier**

Add to `src/chronicler/factions.py`:

```python
from chronicler.models import ActionType

FACTION_WEIGHTS: dict[FactionType, dict[ActionType, float]] = {
    FactionType.MILITARY: {
        ActionType.WAR: 1.8, ActionType.EXPAND: 1.5,
        ActionType.DIPLOMACY: 0.6, ActionType.TRADE: 0.7,
    },
    FactionType.MERCHANT: {
        ActionType.TRADE: 1.8, ActionType.BUILD: 1.5,
        ActionType.EMBARGO: 1.3, ActionType.WAR: 0.5,
    },
    FactionType.CULTURAL: {
        ActionType.INVEST_CULTURE: 1.8, ActionType.DIPLOMACY: 1.5,
        ActionType.WAR: 0.4, ActionType.EXPAND: 0.6,
    },
}


def get_faction_weight_modifier(
    civ: Civilization, action: ActionType,
) -> float:
    """Dominant faction's weight for this action, scaled by influence."""
    dominant = get_dominant_faction(civ.factions)
    influence = civ.factions.influence[dominant]
    faction_weight = FACTION_WEIGHTS.get(dominant, {}).get(action, 1.0)
    return faction_weight ** influence
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factions.py::TestWeightModifier -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Integrate into compute_weights()**

In `src/chronicler/action_engine.py`, in the `compute_weights` method, insert after the tech focus `for` loop (ends around line 611) and before the streak history check (`history = self.world.action_history.get(...)` around line 613):

```python
        # M22: Faction weight modifier
        from chronicler.factions import get_faction_weight_modifier
        for action in ActionType:
            if weights[action] > 0:
                weights[action] *= get_faction_weight_modifier(civ, action)
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/factions.py src/chronicler/action_engine.py tests/test_factions.py
git commit -m "feat(m22): action weight integration — dominant faction exponentiation formula"
```

---

### Task 6: Power Struggles

**Files:**
- Modify: `src/chronicler/factions.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing tests for power struggle detection and resolution**

Append to `tests/test_factions.py`:

```python
from chronicler.factions import (
    check_power_struggle,
    get_struggling_factions,
    resolve_power_struggle,
)


class TestPowerStruggle:
    def test_trigger_when_close_and_above_threshold(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.36
        fs.influence[FactionType.MERCHANT] = 0.34
        fs.influence[FactionType.CULTURAL] = 0.30
        result = check_power_struggle(fs)
        assert result is not None
        assert FactionType.MILITARY in result
        assert FactionType.MERCHANT in result

    def test_no_trigger_when_gap_too_large(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.50
        fs.influence[FactionType.MERCHANT] = 0.30
        fs.influence[FactionType.CULTURAL] = 0.20
        assert check_power_struggle(fs) is None

    def test_no_trigger_when_below_threshold(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.50
        fs.influence[FactionType.MERCHANT] = 0.26
        fs.influence[FactionType.CULTURAL] = 0.24
        assert check_power_struggle(fs) is None

    def test_resolve_power_struggle_picks_winner(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.36
        civ.factions.influence[FactionType.MERCHANT] = 0.34
        civ.factions.influence[FactionType.CULTURAL] = 0.30
        civ.factions.power_struggle = True
        civ.factions.power_struggle_turns = 6
        # Add war win events for military
        events = [Event(
            turn=8, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: attacker_wins.", importance=8,
        )]
        world = _make_world(turn=10, events=events)
        result_events = resolve_power_struggle(civ, world)
        assert civ.factions.power_struggle is False
        assert civ.factions.power_struggle_turns == 0
        assert civ.factions.influence[FactionType.MILITARY] > 0.36
        assert len(result_events) == 1
        assert result_events[0].event_type == "power_struggle_resolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestPowerStruggle -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement power struggle functions**

Add to `src/chronicler/factions.py`:

```python
# ---------------------------------------------------------------------------
# Power struggles
# ---------------------------------------------------------------------------

def check_power_struggle(
    factions: FactionState,
) -> tuple[FactionType, FactionType] | None:
    """Detect power struggle: two factions within 0.05 and both above 0.30."""
    sorted_factions = sorted(
        factions.influence.items(), key=lambda x: x[1], reverse=True,
    )
    top, second = sorted_factions[0], sorted_factions[1]
    if top[1] - second[1] < 0.05 and second[1] > 0.30:
        return (top[0], second[0])
    return None


def get_struggling_factions(
    civ: Civilization,
) -> tuple[FactionType, FactionType]:
    """Return the two factions currently in a power struggle."""
    sorted_factions = sorted(
        civ.factions.influence.items(), key=lambda x: x[1], reverse=True,
    )
    return (sorted_factions[0][0], sorted_factions[1][0])


def resolve_win_tie(world, civ: Civilization,
                    contenders: tuple[FactionType, FactionType]) -> FactionType:
    """Break win count tie by most recent win. Still tied: military wins."""
    min_turn = world.turn - 10
    latest: dict[FactionType, int] = {ft: -1 for ft in contenders}
    for event in world.events_timeline:
        if event.turn < min_turn or civ.name not in event.actors:
            continue
        for ft in contenders:
            if _event_is_win(event, civ, ft):
                latest[ft] = max(latest[ft], event.turn)
    if latest[contenders[0]] != latest[contenders[1]]:
        return max(latest, key=latest.get)
    if FactionType.MILITARY in contenders:
        return FactionType.MILITARY
    return contenders[0]


def resolve_power_struggle(
    civ: Civilization, world,
) -> list[Event]:
    """Resolve power struggle — faction with more recent wins gets +0.15."""
    contenders = get_struggling_factions(civ)
    wins = {}
    for ft in contenders:
        wins[ft] = count_faction_wins(world, civ, ft, lookback=10)

    if wins[contenders[0]] != wins[contenders[1]]:
        winner = max(wins, key=wins.get)
    else:
        winner = resolve_win_tie(world, civ, contenders)

    turns = civ.factions.power_struggle_turns
    shift_faction_influence(civ.factions, winner, +0.15)
    civ.factions.power_struggle = False
    civ.factions.power_struggle_turns = 0
    return [Event(
        turn=world.turn, event_type="power_struggle_resolved",
        actors=[civ.name],
        description=f"{civ.name}: {winner.value} faction prevails after {turns} turns of infighting.",
        importance=7,
    )]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factions.py::TestPowerStruggle -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/factions.py tests/test_factions.py
git commit -m "feat(m22): power struggle detection, resolution, and win tie-breaking"
```

---

### Task 7: Faction Tick + Simulation Hookup

**Files:**
- Modify: `src/chronicler/factions.py`
- Modify: `src/chronicler/simulation.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing test for tick_factions**

Append to `tests/test_factions.py`:

```python
from chronicler.factions import tick_factions


class TestTickFactions:
    def test_tick_shifts_influence_on_war_win(self):
        civ = _make_civ()
        world = _make_world(turn=10, events=[Event(
            turn=10, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: attacker_wins.", importance=8,
        )])
        world.civilizations = [civ]
        mil_before = civ.factions.influence[FactionType.MILITARY]
        tick_factions(world)
        assert civ.factions.influence[FactionType.MILITARY] > mil_before

    def test_tick_skips_power_struggle_during_crisis(self):
        civ = _make_civ()
        civ.factions.power_struggle = True
        civ.factions.power_struggle_turns = 3
        civ.succession_crisis_turns_remaining = 2
        world = _make_world(turn=10)
        world.civilizations = [civ]
        tick_factions(world)
        # Power struggle timer should NOT increment during crisis
        assert civ.factions.power_struggle_turns == 3

    def test_tick_emits_dominance_shift_event(self):
        civ = _make_civ()
        # Set military dominant
        civ.factions.influence[FactionType.MILITARY] = 0.50
        civ.factions.influence[FactionType.MERCHANT] = 0.30
        civ.factions.influence[FactionType.CULTURAL] = 0.20
        # War loss event shifts away from military
        world = _make_world(turn=10, events=[Event(
            turn=10, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: defender_wins.", importance=8,
        )] * 5)  # 5 war losses: -0.50 MIL, +0.25 MER, +0.25 CUL
        world.civilizations = [civ]
        events = tick_factions(world)
        shift_events = [e for e in events if e.event_type == "faction_dominance_shift"]
        # After 5x -0.10 MIL, military should no longer be dominant
        assert len(shift_events) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestTickFactions -v`
Expected: FAIL — `tick_factions` not defined.

- [ ] **Step 3: Implement tick_factions**

Add to `src/chronicler/factions.py`:

```python
from chronicler.models import WorldState

# ---------------------------------------------------------------------------
# Influence shift table
# ---------------------------------------------------------------------------

_WAR_WIN_SHIFTS = {FactionType.MILITARY: 0.10}
_WAR_LOSS_SHIFTS = {
    FactionType.MILITARY: -0.10, FactionType.MERCHANT: 0.05, FactionType.CULTURAL: 0.05,
}
_TRADE_SHIFTS = {FactionType.MERCHANT: 0.08}
_BANKRUPTCY_SHIFTS = {FactionType.MERCHANT: -0.15, FactionType.CULTURAL: 0.05}
_CULTURAL_SHIFTS = {FactionType.CULTURAL: 0.08}
_EXPANSION_SHIFTS = {FactionType.MILITARY: 0.05, FactionType.MERCHANT: 0.03}
_FAMINE_SHIFTS = {
    FactionType.MILITARY: -0.03, FactionType.MERCHANT: -0.03, FactionType.CULTURAL: 0.06,
}

_GP_ROLE_FACTION = {
    "general": FactionType.MILITARY,
    "merchant": FactionType.MERCHANT,
    "prophet": FactionType.CULTURAL,
}


def _apply_event_shifts(civ: Civilization, world) -> None:
    """Scan current-turn events and apply influence shifts."""
    for event in world.events_timeline:
        if event.turn != world.turn:
            continue
        if civ.name not in event.actors:
            continue

        if event.event_type == "war" and len(event.actors) >= 2:
            is_attacker = event.actors[0] == civ.name
            won = (is_attacker and "attacker_wins" in event.description) or \
                  (not is_attacker and "defender_wins" in event.description)
            lost = (is_attacker and "defender_wins" in event.description) or \
                   (not is_attacker and "attacker_wins" in event.description)
            shifts = _WAR_WIN_SHIFTS if won else (_WAR_LOSS_SHIFTS if lost else {})
            for ft, amount in shifts.items():
                civ.factions.influence[ft] += amount

        elif event.event_type == "trade" and len(event.actors) >= 2:
            for ft, amount in _TRADE_SHIFTS.items():
                civ.factions.influence[ft] += amount

        elif event.event_type == "expand" and event.importance >= 5:
            for ft, amount in _EXPANSION_SHIFTS.items():
                civ.factions.influence[ft] += amount

        elif event.event_type in ("cultural_work", "movement_adoption"):
            for ft, amount in _CULTURAL_SHIFTS.items():
                civ.factions.influence[ft] += amount

        elif event.event_type == "famine":
            for ft, amount in _FAMINE_SHIFTS.items():
                civ.factions.influence[ft] += amount

        elif event.event_type == "tech_focus_selected":
            if civ.active_focus:
                matched = FOCUS_FACTION_MAP.get(civ.active_focus)
                if matched:
                    civ.factions.influence[matched] += 0.05

    # State-based checks (not event-driven)
    if civ.treasury <= 0:
        for ft, amount in _BANKRUPTCY_SHIFTS.items():
            civ.factions.influence[ft] += amount
    # Trade income > military cost: merchant faction gains
    if hasattr(civ, "last_income") and civ.last_income > civ.military:
        for ft, amount in _TRADE_SHIFTS.items():
            civ.factions.influence[ft] += amount


def _apply_gp_bonuses(civ: Civilization) -> None:
    """Apply per-turn GP faction bonuses."""
    for gp in civ.great_persons:
        if not (gp.alive and gp.active):
            continue
        faction = _GP_ROLE_FACTION.get(gp.role)
        if faction:
            civ.factions.influence[faction] += 0.03
        if gp.role == "scientist" and civ.active_focus:
            matched = FOCUS_FACTION_MAP.get(civ.active_focus)
            if matched:
                civ.factions.influence[matched] += 0.02


def tick_factions(world) -> list[Event]:
    """Main per-turn faction tick. Runs in phase 10 (consequences)."""
    events: list[Event] = []

    for civ in world.civilizations:
        if not civ.regions:
            continue

        old_dominant = get_dominant_faction(civ.factions)

        # 1. Apply event-based influence shifts
        _apply_event_shifts(civ, world)

        # 2. Apply GP per-turn bonuses
        _apply_gp_bonuses(civ)

        # 3. Normalize
        normalize_influence(civ.factions)

        # 4. Check dominance shift
        new_dominant = get_dominant_faction(civ.factions)
        if new_dominant != old_dominant:
            events.append(Event(
                turn=world.turn, event_type="faction_dominance_shift",
                actors=[civ.name],
                description=f"{civ.name}: {new_dominant.value} faction eclipses {old_dominant.value}.",
                importance=5,
            ))

        # 5. Power struggle processing
        if civ.succession_crisis_turns_remaining > 0:
            # Rule 2: Crisis pauses power struggle
            pass
        elif civ.factions.power_struggle:
            # Active struggle: tick timer, drain stability, check resolution
            civ.factions.power_struggle_turns += 1
            from chronicler.emergence import get_severity_multiplier
            drain = int(3 * get_severity_multiplier(civ))
            civ.stability = max(0, civ.stability - drain)
            if civ.factions.power_struggle_turns > 5:
                events.extend(resolve_power_struggle(civ, world))
        else:
            # Check for new power struggle
            contenders = check_power_struggle(civ.factions)
            if contenders:
                civ.factions.power_struggle = True
                civ.factions.power_struggle_turns = 0
                events.append(Event(
                    turn=world.turn, event_type="power_struggle_started",
                    actors=[civ.name],
                    description=f"{civ.name}: {contenders[0].value} and {contenders[1].value} factions vie for dominance.",
                    importance=6,
                ))

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factions.py::TestTickFactions -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Hook tick_factions into simulation.py**

In `src/chronicler/simulation.py`, in the `phase_consequences()` function, add:

```python
    from chronicler.factions import tick_factions
    turn_events.extend(tick_factions(world))
```

Add this at the end of `phase_consequences()`, after all existing consequence processing (movements, value drift, politics checks). The faction tick must run last in consequences so all event-generating systems have fired first.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/factions.py src/chronicler/simulation.py tests/test_factions.py
git commit -m "feat(m22): tick_factions orchestration + simulation phase 10 hookup"
```

---

## Chunk 3: Succession Integration + Secession Fix

### Task 8: Succession Integration — Candidates, Resolution, Grudges

**Files:**
- Modify: `src/chronicler/factions.py`
- Modify: `src/chronicler/succession.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing tests for candidate generation and crisis resolution**

Append to `tests/test_factions.py`:

```python
from chronicler.factions import (
    generate_faction_candidates,
    inherit_grudges_with_factions,
    FACTION_CANDIDATE_TYPE,
    GP_ROLE_TO_FACTION,
)


class TestCandidateGeneration:
    def test_internal_candidates_per_faction(self):
        civ = _make_civ()
        world = _make_world()
        world.civilizations = [civ]
        world.relationships = {}
        candidates = generate_faction_candidates(civ, world)
        # All 3 factions above 0.15 at defaults
        types = {c["faction"] for c in candidates}
        assert "military" in types
        assert "merchant" in types
        assert "cultural" in types

    def test_weak_faction_excluded(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.CULTURAL] = 0.10
        civ.factions.influence[FactionType.MILITARY] = 0.50
        civ.factions.influence[FactionType.MERCHANT] = 0.40
        world = _make_world()
        world.civilizations = [civ]
        world.relationships = {}
        candidates = generate_faction_candidates(civ, world)
        factions = {c["faction"] for c in candidates}
        assert "cultural" not in factions

    def test_candidate_type_mapping(self):
        assert FACTION_CANDIDATE_TYPE[FactionType.MILITARY] == "general"
        assert FACTION_CANDIDATE_TYPE[FactionType.MERCHANT] == "elected"
        assert FACTION_CANDIDATE_TYPE[FactionType.CULTURAL] == "heir"


class TestGrudgeInheritance:
    def test_same_faction_high_rate(self):
        old = Leader(name="Old", trait="aggressive", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 1.0}]
        new = Leader(name="New", trait="bold", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert len(new.grudges) == 1
        assert new.grudges[0]["intensity"] == pytest.approx(0.7)

    def test_different_faction_low_rate(self):
        old = Leader(name="Old", trait="aggressive", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 1.0}]
        new = Leader(name="New", trait="cautious", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert len(new.grudges) == 1
        assert new.grudges[0]["intensity"] == pytest.approx(0.3)

    def test_neutral_trait_default_rate(self):
        old = Leader(name="Old", trait="stubborn", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 1.0}]
        new = Leader(name="New", trait="opportunistic", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert new.grudges[0]["intensity"] == pytest.approx(0.5)

    def test_low_intensity_filtered(self):
        old = Leader(name="Old", trait="aggressive", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 0.01}]
        new = Leader(name="New", trait="cautious", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        # 0.01 * 0.3 = 0.003 < 0.01 threshold
        assert len(new.grudges) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestCandidateGeneration tests/test_factions.py::TestGrudgeInheritance -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement succession functions in factions.py**

Add to `src/chronicler/factions.py`:

```python
from chronicler.models import Disposition
import random

# ---------------------------------------------------------------------------
# Succession mapping tables
# ---------------------------------------------------------------------------

FACTION_CANDIDATE_TYPE: dict[FactionType, str] = {
    FactionType.MILITARY: "general",
    FactionType.MERCHANT: "elected",
    FactionType.CULTURAL: "heir",
}

GP_ROLE_TO_FACTION: dict[str, FactionType] = {
    "general": FactionType.MILITARY,
    "merchant": FactionType.MERCHANT,
    "prophet": FactionType.CULTURAL,
}

GP_SUCCESSION_TYPE: dict[str, str] = {
    "general": "general",
    "merchant": "elected",
    "prophet": "heir",
}


# ---------------------------------------------------------------------------
# Succession functions
# ---------------------------------------------------------------------------

def generate_faction_candidates(
    civ: Civilization, world,
) -> list[dict]:
    """Generate faction-weighted succession candidates."""
    candidates = []
    dominant = get_dominant_faction(civ.factions)

    for faction_type in FactionType:
        influence = civ.factions.influence[faction_type]
        if influence < 0.15:
            continue
        candidates.append({
            "type": FACTION_CANDIDATE_TYPE[faction_type],
            "faction": faction_type.value,
            "weight": influence,
            "backer_civ": None,
        })

    for other in world.civilizations:
        if other.name == civ.name or not other.regions:
            continue
        rel = world.relationships.get(other.name, {}).get(civ.name)
        if rel and rel.disposition in (Disposition.ALLIED, Disposition.FRIENDLY):
            other_dominant = get_dominant_faction(other.factions)
            candidates.append({
                "type": FACTION_CANDIDATE_TYPE[other_dominant],
                "faction": other_dominant.value,
                "weight": 0.1,
                "backer_civ": other.name,
            })

    if hasattr(civ, "great_persons"):
        for gp in civ.great_persons:
            if gp.alive and gp.active and gp.role in ("general", "merchant", "prophet"):
                gp_faction = GP_ROLE_TO_FACTION[gp.role]
                faction_boost = 0.10 if gp_faction == dominant else 0.0
                candidates.append({
                    "type": GP_SUCCESSION_TYPE[gp.role],
                    "faction": gp_faction.value,
                    "weight": civ.factions.influence[gp_faction] + faction_boost,
                    "backer_civ": None,
                    "great_person": gp.name,
                })

    return candidates


def resolve_crisis_with_factions(
    civ: Civilization, world,
) -> list[Event]:
    """Resolve succession crisis with faction-weighted candidate selection."""
    from chronicler.leaders import generate_successor, apply_leader_legacy
    from chronicler.succession import resolve_crisis, create_exiled_leader
    from chronicler.culture import upgrade_disposition

    rng = random.Random(world.seed + world.turn + hash(civ.name))
    events: list[Event] = []

    candidates = civ.succession_candidates
    if not candidates:
        return resolve_crisis(civ, world)

    if rng.random() < 0.10:
        winner = rng.choice(candidates)
    else:
        weights = [c["weight"] for c in candidates]
        winner = rng.choices(candidates, weights=weights, k=1)[0]

    force_type = winner["type"]
    old_leader = civ.leader
    old_leader.alive = False

    legacy_event = apply_leader_legacy(civ, old_leader, world)
    if legacy_event:
        events.append(legacy_event)

    new_leader = generate_successor(civ, world, seed=world.seed, force_type=force_type)

    # Override flat-rate grudge inheritance with faction-aware rates
    new_leader.grudges = []
    inherit_grudges_with_factions(old_leader, new_leader, civ.factions)

    civ.leader = new_leader

    winning_faction = FactionType(winner["faction"])
    shift_faction_influence(civ.factions, winning_faction, +0.15)

    if "great_person" in winner:
        gp = next((g for g in civ.great_persons if g.name == winner["great_person"]), None)
        if gp:
            new_leader.name = gp.name
            new_leader.trait = gp.trait
            gp.alive = False
            gp.fate = "ascended_to_leadership"

    if winner.get("backer_civ"):
        if civ.name in world.relationships and winner["backer_civ"] in world.relationships[civ.name]:
            rel = world.relationships[civ.name][winner["backer_civ"]]
            rel.disposition = upgrade_disposition(rel.disposition)

    create_exiled_leader(old_leader, civ, world)

    events.append(Event(
        turn=world.turn, event_type="succession_crisis_resolved",
        actors=[civ.name],
        description=(
            f"{civ.name} succession crisis resolved: {winning_faction.value} "
            f"faction prevails, {new_leader.name} takes power."
        ),
        importance=8,
    ))

    civ.succession_crisis_turns_remaining = 0
    civ.succession_candidates = []

    return events


def inherit_grudges_with_factions(
    old_leader: Leader, new_leader: Leader, factions: FactionState,
) -> None:
    """Faction-aware grudge inheritance: 0.7 same faction, 0.3 different, 0.5 neutral."""
    old_faction = TRAIT_FACTION_MAP.get(old_leader.trait)
    new_faction = TRAIT_FACTION_MAP.get(new_leader.trait)

    if old_faction and new_faction and old_faction == new_faction:
        inheritance_rate = 0.7
    elif old_faction != new_faction:
        inheritance_rate = 0.3
    else:
        inheritance_rate = 0.5

    for g in old_leader.grudges:
        inherited_intensity = g["intensity"] * inheritance_rate
        if inherited_intensity >= 0.01:
            new_leader.grudges.append({**g, "intensity": inherited_intensity})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factions.py::TestCandidateGeneration tests/test_factions.py::TestGrudgeInheritance -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Modify succession.py — crisis probability, trigger, resolve, exile**

In `src/chronicler/succession.py`:

**a) compute_crisis_probability** — add faction modifiers after the existing tradition modifiers (around line 50, before the final clamp):

```python
    # M22: Faction modifiers
    from chronicler.factions import get_leader_faction_alignment
    if civ.factions.power_struggle:
        modifiers *= 1.4
    alignment = get_leader_faction_alignment(civ.leader, civ.factions)
    if alignment > 0.5:
        modifiers *= 0.8
    elif alignment < 0.2:
        modifiers *= 1.3
```

**b) trigger_crisis** — replace the default candidate loop (lines 74-81) with:

```python
    from chronicler.factions import generate_faction_candidates
    civ.succession_candidates = generate_faction_candidates(civ, world)
```

**c) resolve_crisis** — in `simulation.py`, find the call `crisis_events = resolve_crisis(civ, world)` (around line 865). Replace `resolve_crisis` with `resolve_crisis_with_factions`:

```python
    from chronicler.factions import resolve_crisis_with_factions
    crisis_events = resolve_crisis_with_factions(civ, world)
```

Also update the import at the top of `simulation.py` (around line 59) — the `resolve_crisis` import from `succession` is no longer needed at this call site (but keep it if other code still references it).

**d) check_exile_restoration** — add faction alignment modifier (around line 270, after `base_prob` is calculated):

```python
    # M22: Faction alignment modifies restoration probability
    from chronicler.factions import GP_ROLE_TO_FACTION, get_dominant_faction
    exile_faction = GP_ROLE_TO_FACTION.get(gp.role)
    origin_dominant = get_dominant_faction(origin_civ.factions)
    if exile_faction and exile_faction == origin_dominant:
        base_prob *= 0.3
    elif exile_faction:
        base_prob *= 1.5
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. Succession tests should still pass since faction-weighted resolution produces compatible output.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/factions.py src/chronicler/succession.py src/chronicler/simulation.py tests/test_factions.py
git commit -m "feat(m22): succession integration — faction candidates, weighted resolution, grudge inheritance"
```

---

### Task 9: Secession Viability Fix

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_factions.py`

- [ ] **Step 1: Write failing test for secession scoring**

Append to `tests/test_factions.py`:

```python
from chronicler.factions import total_effective_capacity


class TestSecessionViability:
    def test_total_effective_capacity(self):
        """Helper sums capacity across civ regions."""
        from chronicler.models import Region
        regions = [
            Region(name="plains1", terrain="plains", carrying_capacity=50, resources="grain"),
            Region(name="desert1", terrain="desert", carrying_capacity=20, resources="none"),
        ]
        world = _make_world()
        world.regions = regions
        civ = _make_civ()
        civ.regions = ["plains1", "desert1"]
        cap = total_effective_capacity(civ, world)
        assert cap > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestSecessionViability -v`
Expected: FAIL — `total_effective_capacity` not defined.

- [ ] **Step 3: Add total_effective_capacity to factions.py**

Add to `src/chronicler/factions.py`:

```python
def total_effective_capacity(civ: Civilization, world) -> int:
    """Sum of effective_capacity across all civ-controlled regions."""
    from chronicler.terrain import effective_capacity
    region_map = {r.name: r for r in world.regions}
    return sum(
        effective_capacity(region_map[rn])
        for rn in civ.regions
        if rn in region_map
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_factions.py::TestSecessionViability -v`
Expected: PASS

- [ ] **Step 5: Modify politics.py — secession scoring and absorption**

In `src/chronicler/politics.py`:

**a) Secession region selection** — find the `sorted_regions` logic (around line 119-123). Replace:

```python
        def _dist_from_capital(rn: str, _civ=civ) -> int:
            d = graph_distance(world.regions, _civ.capital_region or _civ.regions[0], rn)
            return d if d >= 0 else 0

        sorted_regions = sorted(civ.regions, key=_dist_from_capital, reverse=True)
```

With:

```python
        region_map = {r.name: r for r in world.regions}

        def _secession_score(rn: str, _civ=civ) -> float:
            d = graph_distance(world.regions, _civ.capital_region or _civ.regions[0], rn)
            dist = d if d >= 0 else 0
            cap = effective_capacity(region_map[rn]) if rn in region_map else 0
            return dist * 0.7 + cap * 0.3

        sorted_regions = sorted(civ.regions, key=_secession_score, reverse=True)
```

Ensure `effective_capacity` is imported from `chronicler.terrain` at the top of `politics.py` (it may already be imported — check existing imports).

**b) Absorption safety net** — in `check_twilight_absorption()` in `politics.py` (around line 965), add a new condition alongside the existing twilight absorption checks. The existing function iterates civs and performs inline absorption (finds best absorber by cultural similarity, transfers regions). Add this block inside the civ loop, before or after the existing `decline_turns` check:

```python
        # M22: Absorb structurally unviable civs (capacity < 10 for 30+ turns of existence)
        from chronicler.factions import total_effective_capacity
        if total_effective_capacity(civ, world) < 10 and (world.turn - civ.founded_turn) > 30:
            # Reuse the same absorption logic as twilight: find best absorber,
            # transfer regions. The existing code in this function already has
            # the best_absorber selection and region transfer logic —
            # extract it into a helper or duplicate the ~10-line block.
            pass  # implementer: follow the same pattern as the existing absorption block below
```

The implementer should study the existing absorption block in `check_twilight_absorption()` (around lines 970-1000) which selects the nearest neighbor by cultural similarity and transfers regions. Apply the same logic here.

**c) Set founded_turn in secession** — in the secession logic in `politics.py`, find where `breakaway_civ = Civilization(...)` is constructed (around lines 191-210). After the construction and before or after `breakaway_civ.traditions = list(civ.traditions)` (around line 210), add:

```python
    breakaway_civ.founded_turn = world.turn
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/factions.py src/chronicler/politics.py tests/test_factions.py
git commit -m "feat(m22): secession viability — capacity-weighted region selection + absorption safety net"
```

---

### Task 10: CivSnapshot + Final Verification

**Files:**
- Modify: `src/chronicler/main.py`

- [ ] **Step 1: Populate factions in CivSnapshot**

In `src/chronicler/main.py`, find where `CivSnapshot` is created (search for `CivSnapshot(`). Add alongside the existing `tech_era=civ.tech_era`:

```python
    factions=civ.factions,
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 3: Run E2E test**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: PASS — faction system integrates without breaking the simulation loop.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/main.py
git commit -m "feat(m22): populate factions in CivSnapshot for analytics"
```

- [ ] **Step 5: Final verification — run simulation**

Run: `python -m chronicler --simulate-only --turns 50 --seed 42`
Expected: Simulation completes without errors. Faction events appear in the timeline.
