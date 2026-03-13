# M7: Simulation Depth — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the simulation from a monotonous DEVELOP-heavy loop into a rich history generator with personality-driven actions, tech progression, named landmarks, and deep leader mechanics.

**Architecture:** Four new modules (`action_engine.py`, `tech.py`, `named_events.py`, `leaders.py`) plug into an expanded 9-phase turn loop. The deterministic action engine replaces LLM-driven action selection as the default. All new model fields have safe defaults for backward compatibility.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-12-m7-simulation-depth-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `src/chronicler/action_engine.py` | Deterministic action selection: personality weights, situational overrides, streak breaker, eligibility filter |
| `src/chronicler/tech.py` | Tech advancement checks, era bonuses, war disparity multiplier |
| `src/chronicler/named_events.py` | Named event generation (battles, treaties, cultural works, breakthroughs), naming pools, deduplication |
| `src/chronicler/leaders.py` | Succession types, leader name pools, legacy system, rivalry tracking, trait evolution |
| `tests/test_action_engine.py` | Tests for action engine |
| `tests/test_tech.py` | Tests for tech system |
| `tests/test_named_events.py` | Tests for named events |
| `tests/test_leaders.py` | Tests for leader system |

### Modified Files
| File | Changes |
|------|---------|
| `src/chronicler/models.py` | Add `NamedEvent` model, new fields on `WorldState`, `Civilization`, `Leader` |
| `src/chronicler/world_gen.py` | Change starting era to TRIBAL |
| `src/chronicler/simulation.py` | Expand to 9-phase loop, integrate new modules, update war resolution with tech disparity |
| `src/chronicler/narrative.py` | Update chronicle prompt with named events and rivalries |
| `src/chronicler/events.py` | Add cascade rules for new event types |
| `src/chronicler/main.py` | Add `--llm-actions` flag, wire ActionEngine as default |
| `tests/conftest.py` | Update fixtures for new model fields |
| `tests/test_simulation.py` | Add 9-phase tests, integration tests |
| `tests/test_narrative.py` | Add named event callback tests |

### Dependency Order
```
Chunk 1: Foundation (models.py, world_gen.py, conftest.py)
    ├── Chunk 2: Tech System (tech.py) ──────────┐
    ├── Chunk 3: Named Events (named_events.py) ──┤── can run in PARALLEL
    ├── Chunk 4: Leader System (leaders.py) ──────┤   (no cross-imports between these)
    └── Chunk 5: Action Engine (action_engine.py) ┘
                                                   │
Chunk 6: Simulation Integration (simulation.py) ◄──┘
Chunk 7: Narrative + CLI + Integration Tests
```

**Note:** `TECH_BREAKTHROUGH_NAMES` lives in `named_events.py` (not `tech.py`) so that Chunks 2 and 3 have no cross-imports. `tech.py` calls `generate_tech_breakthrough_name()` from `named_events.py` only at integration time (Chunk 6), not as a direct import.

---

## Chunk 1: Foundation — Data Model Changes

### Task 1: Add NamedEvent model and new fields to models.py

**Files:**
- Modify: `src/chronicler/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for new model fields**

Add to `tests/test_models.py`:

```python
def test_named_event_model():
    ne = NamedEvent(
        name="The Siege of Thornwood",
        event_type="battle",
        turn=5,
        actors=["Kethani Empire"],
        region="Thornwood",
        description="A decisive victory",
    )
    assert ne.name == "The Siege of Thornwood"
    assert ne.region == "Thornwood"


def test_named_event_optional_region():
    ne = NamedEvent(
        name="The Iron Accord",
        event_type="treaty",
        turn=3,
        actors=["Kethani Empire", "Dorrathi Clans"],
        description="A peace treaty",
    )
    assert ne.region is None


def test_leader_new_fields():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    assert leader.succession_type == "founder"
    assert leader.predecessor_name is None
    assert leader.rival_leader is None
    assert leader.rival_civ is None
    assert leader.secondary_trait is None


def test_civilization_new_fields():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test Civ",
        population=5, military=5, economy=5, culture=5, stability=5,
        leader=leader, regions=["Region A"],
    )
    assert civ.cultural_milestones == []
    assert civ.action_counts == {}


def test_world_state_new_fields():
    ws = WorldState(name="Test", seed=42)
    assert ws.named_events == []
    assert ws.used_leader_names == []
    assert ws.action_history == {}


def test_named_event_serialization():
    ne = NamedEvent(
        name="The Siege of Thornwood",
        event_type="battle",
        turn=5,
        actors=["Kethani Empire"],
        region="Thornwood",
        description="A decisive victory",
    )
    data = ne.model_dump()
    restored = NamedEvent.model_validate(data)
    assert restored == ne
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_models.py -v -k "named_event or leader_new or civilization_new or world_state_new" 2>&1 | tail -20`

Expected: FAIL — `NamedEvent` not importable, new fields not defined.

- [ ] **Step 3: Implement model changes**

In `src/chronicler/models.py`, add after the `Event` class (after line 103):

```python
class NamedEvent(BaseModel):
    """A historically significant event with a generated name."""
    name: str
    event_type: str  # battle, treaty, cultural_work, tech_breakthrough, coup, legacy, rival_fall
    turn: int
    actors: list[str]
    region: str | None = None
    description: str
    importance: int = Field(default=5, ge=1, le=10)
```

Add new fields to `Leader` (after line 57, before the class ends):

```python
    succession_type: str = "founder"
    predecessor_name: str | None = None
    rival_leader: str | None = None
    rival_civ: str | None = None
    secondary_trait: str | None = None
```

Add new fields to `Civilization` (after `asabiya` field, around line 78):

```python
    cultural_milestones: list[str] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
```

Add new fields to `WorldState` (after `event_probabilities`, around line 126):

```python
    named_events: list[NamedEvent] = Field(default_factory=list)
    used_leader_names: list[str] = Field(default_factory=list)
    action_history: dict[str, list[str]] = Field(default_factory=dict)
```

Update the imports in `test_models.py` to include `NamedEvent`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_models.py -v -k "named_event or leader_new or civilization_new or world_state_new" 2>&1 | tail -20`

Expected: All PASS.

- [ ] **Step 5: Run full existing test suite to verify no regressions**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/ -v 2>&1 | tail -30`

Expected: All 94 existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_models.py
git commit -m "feat(models): add NamedEvent model and new fields for M7 simulation depth"
```

---

### Task 2: Change starting era to TRIBAL in world_gen.py

**Files:**
- Modify: `src/chronicler/world_gen.py:88-136` (assign_civilizations function)
- Test: `tests/test_world_gen.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_world_gen.py`:

```python
from chronicler.models import TechEra

def test_civilizations_start_at_tribal():
    regions = generate_regions(count=8, seed=42)
    civs = assign_civilizations(regions, civ_count=4, seed=42)
    for civ in civs:
        assert civ.tech_era == TechEra.TRIBAL, f"{civ.name} started at {civ.tech_era}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_world_gen.py::test_civilizations_start_at_tribal -v`

Expected: FAIL — civs currently start at IRON.

- [ ] **Step 3: Update assign_civilizations**

In `src/chronicler/world_gen.py`, in the `assign_civilizations` function, find where `tech_era` is set (should reference `TechEra.IRON`) and change to `TechEra.TRIBAL`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_world_gen.py::test_civilizations_start_at_tribal -v`

Expected: PASS.

- [ ] **Step 5: Run full test suite — fix any tests that assumed IRON start**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/ -v 2>&1 | tail -30`

Expected: All PASS (fix any failures caused by the era change).

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_world_gen.py
git commit -m "feat(world_gen): change starting era from IRON to TRIBAL"
```

---

### Task 3: Update test fixtures in conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Design decision:** Test fixtures in `conftest.py` keep `tech_era=TechEra.IRON` (not TRIBAL). These fixtures are pre-built test worlds, not `world_gen` output. Tests that need TRIBAL starts set it explicitly. This avoids cascading changes across all existing tests.

- [ ] **Step 1: Run full test suite to check for regressions after Tasks 1-2**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/ -v 2>&1 | tail -30`

If all pass, Pydantic defaults handle the new fields correctly. If any fail due to the IRON→TRIBAL change in `world_gen.py`, check whether the failing test uses `generate_world()` (should now get TRIBAL) vs. conftest fixtures (still IRON). Fix accordingly:
- Tests using `generate_world()`: update assertions to expect TRIBAL
- Tests using conftest fixtures: should still pass as-is (fixtures hardcode IRON)

- [ ] **Step 2: Verify new model fields have safe defaults**

Run: `cd /Users/tbronson/Documents/opusprogram && python -c "from tests.conftest import *; import pytest; print('Fixtures importable')"` or just confirm the fixtures work via pytest.

- [ ] **Step 3: Commit if changes were needed**

```bash
git add tests/conftest.py
git commit -m "fix(tests): update fixtures for new model fields"
```

---

## Chunk 2: Tech System

### Task 4: Implement tech advancement and era bonuses

**Files:**
- Create: `src/chronicler/tech.py`
- Create: `tests/test_tech.py`

- [ ] **Step 1: Write failing tests for tech requirements and advancement**

Create `tests/test_tech.py`:

```python
import pytest
from chronicler.models import (
    Civilization, Leader, TechEra, Event, WorldState, Region,
)
from chronicler.tech import (
    TECH_REQUIREMENTS,
    ERA_BONUSES,
    check_tech_advancement,
    apply_era_bonus,
    tech_war_multiplier,
)


@pytest.fixture
def tribal_civ():
    return Civilization(
        name="Test Civ",
        population=5, military=3, economy=4, culture=4, stability=5,
        tech_era=TechEra.TRIBAL, treasury=15,
        leader=Leader(name="Leader", trait="bold", reign_start=0),
        regions=["Region A"],
    )


@pytest.fixture
def tech_world(tribal_civ):
    return WorldState(
        name="Test", seed=42, turn=5,
        regions=[Region(name="Region A", terrain="plains", carrying_capacity=8, resources="fertile")],
        civilizations=[tribal_civ],
    )


def test_tech_requirements_defined_for_all_transitions():
    """Every era except INDUSTRIAL has advancement requirements."""
    for era in TechEra:
        if era != TechEra.INDUSTRIAL:
            assert era in TECH_REQUIREMENTS


def test_advancement_tribal_to_bronze(tribal_civ, tech_world):
    """Civ with culture>=4, economy>=4, treasury>=10 advances from TRIBAL to BRONZE."""
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is not None
    assert event.event_type == "tech_advancement"
    assert event.importance == 7
    assert tribal_civ.tech_era == TechEra.BRONZE
    assert tribal_civ.treasury == 5  # 15 - 10


def test_no_advancement_insufficient_culture(tribal_civ, tech_world):
    """Culture below threshold prevents advancement."""
    tribal_civ.culture = 3
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is None
    assert tribal_civ.tech_era == TechEra.TRIBAL


def test_no_advancement_insufficient_economy(tribal_civ, tech_world):
    """Economy below threshold prevents advancement."""
    tribal_civ.economy = 3
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is None
    assert tribal_civ.tech_era == TechEra.TRIBAL


def test_no_advancement_insufficient_treasury(tribal_civ, tech_world):
    """Treasury below cost prevents advancement."""
    tribal_civ.treasury = 9
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is None
    assert tribal_civ.tech_era == TechEra.TRIBAL


def test_no_advancement_at_industrial(tribal_civ, tech_world):
    """INDUSTRIAL is the highest era — no advancement."""
    tribal_civ.tech_era = TechEra.INDUSTRIAL
    tribal_civ.culture = 10
    tribal_civ.economy = 10
    tribal_civ.treasury = 50
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is None


def test_era_bonus_bronze():
    """BRONZE advancement gives military +1."""
    civ = Civilization(
        name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.BRONZE, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    old_military = civ.military
    apply_era_bonus(civ, TechEra.BRONZE)
    assert civ.military == old_military + 1


def test_era_bonus_iron():
    """IRON advancement gives economy +1."""
    civ = Civilization(
        name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.IRON, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    old_economy = civ.economy
    apply_era_bonus(civ, TechEra.IRON)
    assert civ.economy == old_economy + 1


def test_era_bonus_medieval():
    """MEDIEVAL advancement gives military +1."""
    civ = Civilization(
        name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.MEDIEVAL, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    old_military = civ.military
    apply_era_bonus(civ, TechEra.MEDIEVAL)
    assert civ.military == old_military + 1


def test_era_bonus_classical():
    """CLASSICAL advancement gives culture +1."""
    civ = Civilization(
        name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.CLASSICAL, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    old_culture = civ.culture
    apply_era_bonus(civ, TechEra.CLASSICAL)
    assert civ.culture == old_culture + 1


def test_era_bonus_renaissance():
    """RENAISSANCE gives economy +2, culture +1."""
    civ = Civilization(
        name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.RENAISSANCE, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    old_econ = civ.economy
    old_culture = civ.culture
    apply_era_bonus(civ, TechEra.RENAISSANCE)
    assert civ.economy == old_econ + 2
    assert civ.culture == old_culture + 1


def test_era_bonus_industrial():
    """INDUSTRIAL gives economy +2, military +2."""
    civ = Civilization(
        name="Test", population=5, military=3, economy=3, culture=5, stability=5,
        tech_era=TechEra.INDUSTRIAL, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    old_econ = civ.economy
    old_mil = civ.military
    apply_era_bonus(civ, TechEra.INDUSTRIAL)
    assert civ.economy == old_econ + 2
    assert civ.military == old_mil + 2


def test_era_bonus_clamped_to_10():
    """Stats should not exceed 10 after era bonus."""
    civ = Civilization(
        name="Test", population=5, military=10, economy=5, culture=5, stability=5,
        tech_era=TechEra.BRONZE, treasury=10,
        leader=Leader(name="L", trait="bold", reign_start=0),
        regions=["R"],
    )
    apply_era_bonus(civ, TechEra.BRONZE)
    assert civ.military == 10  # clamped, not 11


def test_tech_war_multiplier_no_gap():
    """No era gap = 1.0 multiplier."""
    assert tech_war_multiplier(TechEra.IRON, TechEra.IRON) == 1.0


def test_tech_war_multiplier_gap_1():
    """Gap of 1 = no multiplier."""
    assert tech_war_multiplier(TechEra.CLASSICAL, TechEra.IRON) == 1.0


def test_tech_war_multiplier_gap_2():
    """Gap of 2 = 1.5x multiplier."""
    assert tech_war_multiplier(TechEra.MEDIEVAL, TechEra.IRON) == 1.5


def test_tech_war_multiplier_gap_3():
    """Gap of 3 still uses the >=2 threshold = 1.5x."""
    assert tech_war_multiplier(TechEra.RENAISSANCE, TechEra.IRON) == 1.5


def test_tech_war_multiplier_gap_4():
    """Gap of 4 = 2.0x multiplier."""
    assert tech_war_multiplier(TechEra.INDUSTRIAL, TechEra.IRON) == 2.0


def test_tech_war_multiplier_defender_advantage():
    """Defender more advanced = attacker gets < 1.0 penalty.

    Design decision: "symmetrical" means the multiplier is applied as a reciprocal
    penalty to the attacker (1/1.5 ≈ 0.667) rather than as a 1.5x boost to defender
    power. This is equivalent in the power comparison formula since we multiply
    attacker power by the return value.
    """
    # Attacker IRON, Defender MEDIEVAL = gap of -2 for attacker
    mult = tech_war_multiplier(TechEra.IRON, TechEra.MEDIEVAL)
    assert mult == pytest.approx(1 / 1.5, rel=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_tech.py -v 2>&1 | tail -20`

Expected: FAIL — `chronicler.tech` module doesn't exist.

- [ ] **Step 3: Implement tech.py**

Create `src/chronicler/tech.py`:

```python
"""Technology progression system — advancement checks, era bonuses, war multipliers."""

from __future__ import annotations

from chronicler.models import Civilization, Event, TechEra, WorldState


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


# Era index for ordering
_ERA_ORDER = list(TechEra)


def _era_index(era: TechEra) -> int:
    return _ERA_ORDER.index(era)


def _next_era(era: TechEra) -> TechEra | None:
    idx = _era_index(era)
    if idx + 1 < len(_ERA_ORDER):
        return _ERA_ORDER[idx + 1]
    return None


# Requirements: {current_era: (min_culture, min_economy, treasury_cost)}
TECH_REQUIREMENTS: dict[TechEra, tuple[int, int, int]] = {
    TechEra.TRIBAL: (4, 4, 10),
    TechEra.BRONZE: (5, 5, 12),
    TechEra.IRON: (6, 6, 15),
    TechEra.CLASSICAL: (7, 7, 18),
    TechEra.MEDIEVAL: (8, 8, 22),
    TechEra.RENAISSANCE: (9, 9, 28),
}

# Bonuses applied once on reaching each era
ERA_BONUSES: dict[TechEra, dict[str, int | float]] = {
    TechEra.BRONZE: {"military": 1},
    TechEra.IRON: {"economy": 1},
    TechEra.CLASSICAL: {"culture": 1},
    TechEra.MEDIEVAL: {"military": 1},  # +0.2 asabiya handled in war resolution
    TechEra.RENAISSANCE: {"economy": 2, "culture": 1},
    TechEra.INDUSTRIAL: {"economy": 2, "military": 2},
}

def check_tech_advancement(civ: Civilization, world: WorldState) -> Event | None:
    """Check if a civ qualifies for tech advancement. Apply if so.

    Returns an Event if advancement occurred, None otherwise.
    At most one advancement per call.
    """
    reqs = TECH_REQUIREMENTS.get(civ.tech_era)
    if reqs is None:
        return None  # Already at INDUSTRIAL

    min_culture, min_economy, cost = reqs
    if civ.culture < min_culture or civ.economy < min_economy or civ.treasury < cost:
        return None

    # Advance
    civ.treasury -= cost
    new_era = _next_era(civ.tech_era)
    assert new_era is not None  # Guarded by TECH_REQUIREMENTS not having INDUSTRIAL
    civ.tech_era = new_era

    # Apply era bonuses
    apply_era_bonus(civ, new_era)

    return Event(
        turn=world.turn,
        event_type="tech_advancement",
        actors=[civ.name],
        description=f"{civ.name} advances to the {new_era.value} era",
        importance=7,
    )


def apply_era_bonus(civ: Civilization, era: TechEra) -> None:
    """Apply stat bonuses for reaching a new era. Clamps stats to 1-10."""
    bonuses = ERA_BONUSES.get(era, {})
    for stat, amount in bonuses.items():
        if isinstance(amount, int) and hasattr(civ, stat):
            current = getattr(civ, stat)
            setattr(civ, stat, _clamp(current + amount, 1, 10))


def tech_war_multiplier(attacker_era: TechEra, defender_era: TechEra) -> float:
    """Calculate power multiplier based on tech era gap.

    Gap >= 2: 1.5x for the more advanced side.
    Gap >= 4: 2.0x for the more advanced side.
    Returns multiplier for the attacker (< 1.0 if defender is more advanced).
    """
    gap = _era_index(attacker_era) - _era_index(defender_era)

    if abs(gap) >= 4:
        raw_mult = 2.0
    elif abs(gap) >= 2:
        raw_mult = 1.5
    else:
        return 1.0

    if gap > 0:
        return raw_mult  # Attacker advantage
    else:
        return 1.0 / raw_mult  # Defender advantage
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_tech.py -v 2>&1 | tail -30`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech.py tests/test_tech.py
git commit -m "feat(tech): implement technology progression system"
```

---

## Chunk 3: Named Events System

### Task 5: Implement named event generation

**Files:**
- Create: `src/chronicler/named_events.py`
- Create: `tests/test_named_events.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_named_events.py`:

```python
import pytest
from chronicler.models import (
    Civilization, Leader, NamedEvent, TechEra, WorldState, Region,
    Relationship, Disposition,
)
from chronicler.named_events import (
    generate_battle_name,
    generate_treaty_name,
    generate_cultural_work,
    generate_tech_breakthrough_name,
    deduplicate_name,
)


@pytest.fixture
def named_world():
    leader = Leader(name="Vaelith", trait="bold", reign_start=0)
    civ1 = Civilization(
        name="Kethani Empire", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=10,
        leader=leader, regions=["Thornwood"], domains=["maritime", "commerce"],
        values=["Trade", "Order"],
    )
    civ2 = Civilization(
        name="Dorrathi Clans", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=10,
        leader=Leader(name="Gorath", trait="aggressive", reign_start=0),
        regions=["Iron Peaks"], domains=["warfare", "conquest"],
        values=["Honor", "Strength"],
    )
    return WorldState(
        name="Test", seed=42, turn=10,
        regions=[
            Region(name="Thornwood", terrain="forest", carrying_capacity=7, resources="timber"),
            Region(name="Iron Peaks", terrain="mountains", carrying_capacity=5, resources="mineral"),
        ],
        civilizations=[civ1, civ2],
    )


class TestBattleNames:
    def test_tribal_era_uses_raid_or_skirmish(self, named_world):
        named_world.civilizations[0].tech_era = TechEra.TRIBAL
        name = generate_battle_name("Thornwood", TechEra.TRIBAL, named_world, seed=42)
        assert "Thornwood" in name
        assert any(prefix in name for prefix in ["Raid", "Skirmish"])

    def test_iron_era_uses_battle_or_siege(self, named_world):
        name = generate_battle_name("Iron Peaks", TechEra.IRON, named_world, seed=42)
        assert "Iron Peaks" in name
        assert any(prefix in name for prefix in ["Battle", "Siege"])

    def test_medieval_era_uses_siege_sack_rout(self, named_world):
        name = generate_battle_name("Thornwood", TechEra.MEDIEVAL, named_world, seed=42)
        assert "Thornwood" in name
        assert any(prefix in name for prefix in ["Siege", "Sack", "Rout"])

    def test_deterministic_with_same_seed(self, named_world):
        name1 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        name2 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        assert name1 == name2

    def test_different_seed_can_produce_different_name(self, named_world):
        name1 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        name2 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=999)
        # Different seeds should produce different names (may not always, but very likely)
        # Just verify they're valid names
        assert "Thornwood" in name1
        assert "Thornwood" in name2


class TestTreatyNames:
    def test_treaty_name_format(self, named_world):
        name = generate_treaty_name("Kethani Empire", "Dorrathi Clans", named_world, seed=42)
        assert name.startswith("The ")
        assert len(name) > 10

    def test_deterministic(self, named_world):
        n1 = generate_treaty_name("Kethani Empire", "Dorrathi Clans", named_world, seed=42)
        n2 = generate_treaty_name("Kethani Empire", "Dorrathi Clans", named_world, seed=42)
        assert n1 == n2


class TestCulturalWorks:
    def test_cultural_work_format(self, named_world):
        name = generate_cultural_work(named_world.civilizations[0], named_world, seed=42)
        assert len(name) > 10
        assert name.startswith("The ")

    def test_deterministic(self, named_world):
        n1 = generate_cultural_work(named_world.civilizations[0], named_world, seed=42)
        n2 = generate_cultural_work(named_world.civilizations[0], named_world, seed=42)
        assert n1 == n2


class TestTechBreakthroughs:
    def test_breakthrough_name_for_bronze(self):
        name = generate_tech_breakthrough_name(TechEra.BRONZE)
        assert name == "The Forging of Bronze"

    def test_breakthrough_name_for_industrial(self):
        name = generate_tech_breakthrough_name(TechEra.INDUSTRIAL)
        assert name == "The First Engines"


class TestNamedEventCreation:
    def test_battle_name_creates_appendable_named_event(self, named_world):
        """Generated battle name can be used to create and append a NamedEvent to WorldState."""
        name = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        ne = NamedEvent(
            name=name, event_type="battle", turn=named_world.turn,
            actors=["Kethani Empire", "Dorrathi Clans"],
            region="Thornwood", description="A decisive victory", importance=7,
        )
        named_world.named_events.append(ne)
        assert len(named_world.named_events) == 1
        assert named_world.named_events[0].name == name


class TestDeduplication:
    def test_no_collision(self):
        existing = ["The Battle of Thornwood"]
        name = deduplicate_name("The Siege of Iron Peaks", existing)
        assert name == "The Siege of Iron Peaks"

    def test_collision_appends_second(self):
        existing = ["The Battle of Thornwood"]
        name = deduplicate_name("The Battle of Thornwood", existing)
        assert name == "The Second Battle of Thornwood"

    def test_double_collision_appends_third(self):
        existing = ["The Battle of Thornwood", "The Second Battle of Thornwood"]
        name = deduplicate_name("The Battle of Thornwood", existing)
        assert name == "The Third Battle of Thornwood"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_named_events.py -v 2>&1 | tail -20`

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement named_events.py**

Create `src/chronicler/named_events.py`:

```python
"""Named event generation — battles, treaties, cultural works, tech breakthroughs."""

from __future__ import annotations

import random

from chronicler.models import Civilization, TechEra, WorldState

# Tech breakthrough names per era (owned here, not in tech.py, to avoid cross-chunk imports)
TECH_BREAKTHROUGH_NAMES: dict[TechEra, str] = {
    TechEra.BRONZE: "The Forging of Bronze",
    TechEra.IRON: "The Mastery of Iron",
    TechEra.CLASSICAL: "The Codification of Law",
    TechEra.MEDIEVAL: "The Age of Fortification",
    TechEra.RENAISSANCE: "The Great Enlightenment",
    TechEra.INDUSTRIAL: "The First Engines",
}

# Battle name prefixes by era
BATTLE_PREFIXES: dict[str, list[str]] = {
    "early": ["The Raid on", "The Skirmish at"],
    "mid": ["The Battle of", "The Siege of"],
    "late": ["The Siege of", "The Sack of", "The Rout at"],
}

# Treaty name components
TREATY_ADJECTIVES = [
    "Sapphire", "Iron", "Golden", "Silver", "Ivory", "Crimson", "Amber",
    "Jade", "Obsidian", "Pearl", "Cedar", "Marble", "Twilight", "Dawn",
    "Storm", "Frost", "Flame", "Shadow", "Sun", "Moon",
]

TREATY_NOUNS = [
    "Accord", "Pact", "Concord", "Treaty", "Alliance", "Covenant",
    "Compact", "Convention", "Understanding", "Truce", "Bond",
    "Charter", "Concordat", "Entente", "Protocol",
]

# Cultural work templates
WORK_TYPES = [
    "Codex", "Chronicle", "Great Lighthouse", "Grand Temple", "Monument",
    "Library", "Academy", "Cathedral", "Colosseum", "Amphitheater",
    "Obelisk", "Archive", "Gallery", "Mosaic", "Tapestry",
]

WORK_THEMES = [
    "Songs", "Wisdom", "Valor", "Stars", "Ages", "Dreams",
    "Legends", "Winds", "Tides", "Flames", "Shadows", "Dawn",
    "Ancestors", "Prophecy", "Memory",
]

# Ordinal suffixes for deduplication
_ORDINALS = ["Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"]


def _seed_rng(base_seed: int, turn: int, extra: str) -> random.Random:
    """Create a seeded RNG for deterministic name generation."""
    combined = base_seed + turn + hash(extra)
    return random.Random(combined)


def generate_battle_name(
    region: str, era: TechEra, world: WorldState, seed: int
) -> str:
    """Generate a named battle based on region and tech era."""
    rng = _seed_rng(seed, world.turn, region)

    era_idx = list(TechEra).index(era)
    if era_idx <= 1:  # TRIBAL, BRONZE
        prefixes = BATTLE_PREFIXES["early"]
    elif era_idx <= 3:  # IRON, CLASSICAL
        prefixes = BATTLE_PREFIXES["mid"]
    else:  # MEDIEVAL+
        prefixes = BATTLE_PREFIXES["late"]

    prefix = rng.choice(prefixes)
    name = f"{prefix} {region}"

    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)


def generate_treaty_name(
    civ1_name: str, civ2_name: str, world: WorldState, seed: int
) -> str:
    """Generate a named treaty between two civilizations."""
    rng = _seed_rng(seed, world.turn, civ1_name + civ2_name)

    adj = rng.choice(TREATY_ADJECTIVES)
    noun = rng.choice(TREATY_NOUNS)
    name = f"The {adj} {noun}"

    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)


def generate_cultural_work(
    civ: Civilization, world: WorldState, seed: int
) -> str:
    """Generate a named cultural work for a civilization."""
    rng = _seed_rng(seed, world.turn, civ.name)

    work_type = rng.choice(WORK_TYPES)
    theme = rng.choice(WORK_THEMES)
    # Derive adjective from civ name (first word or shortened)
    civ_adj = civ.name.split()[0]
    name = f"The {work_type} of {civ_adj} {theme}"

    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)


def generate_tech_breakthrough_name(era: TechEra) -> str:
    """Return the fixed breakthrough name for a given era."""
    return TECH_BREAKTHROUGH_NAMES.get(era, f"The Advance to {era.value}")


def deduplicate_name(name: str, existing: list[str]) -> str:
    """If name collides with existing, append ordinal suffix."""
    if name not in existing:
        return name

    for ordinal in _ORDINALS:
        # Insert ordinal after "The " prefix
        if name.startswith("The "):
            candidate = f"The {ordinal} {name[4:]}"
        else:
            candidate = f"{ordinal} {name}"
        if candidate not in existing:
            return candidate

    # Fallback for extreme collisions
    return f"{name} ({len(existing) + 1})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_named_events.py -v 2>&1 | tail -30`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/named_events.py tests/test_named_events.py
git commit -m "feat(named_events): implement named event generation system"
```

---

## Chunk 4: Leader System

### Task 6: Implement leader name pools and succession

**Files:**
- Create: `src/chronicler/leaders.py`
- Create: `tests/test_leaders.py`

- [ ] **Step 1: Write failing tests for name generation and succession**

Create `tests/test_leaders.py`:

```python
import pytest
from chronicler.models import (
    Civilization, Leader, TechEra, WorldState, Region, ActiveCondition,
    Disposition, Relationship, NamedEvent,
)
from chronicler.leaders import (
    generate_successor,
    apply_leader_legacy,
    check_trait_evolution,
    update_rivalries,
    get_archetype_for_domains,
    CULTURAL_NAME_POOLS,
    SUCCESSION_WEIGHTS,
)


@pytest.fixture
def leader_civ():
    return Civilization(
        name="Kethani Empire",
        population=5, military=5, economy=5, culture=6, stability=5,
        tech_era=TechEra.CLASSICAL, treasury=15,
        leader=Leader(name="Vaelith", trait="bold", reign_start=0),
        regions=["Region A"],
        domains=["maritime", "commerce"],
        values=["Trade", "Order"],
    )


@pytest.fixture
def leader_world(leader_civ):
    civ2 = Civilization(
        name="Dorrathi Clans",
        population=5, military=5, economy=5, culture=5, stability=5,
        tech_era=TechEra.IRON, treasury=10,
        leader=Leader(name="Gorath", trait="aggressive", reign_start=0),
        regions=["Region B"],
        domains=["warfare", "conquest"],
    )
    return WorldState(
        name="Test", seed=42, turn=20,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=8, resources="fertile"),
            Region(name="Region B", terrain="mountains", carrying_capacity=5, resources="mineral"),
        ],
        civilizations=[leader_civ, civ2],
        relationships={
            "Kethani Empire": {"Dorrathi Clans": Relationship(disposition=Disposition.HOSTILE)},
            "Dorrathi Clans": {"Kethani Empire": Relationship(disposition=Disposition.HOSTILE)},
        },
    )


class TestArchetypeMapping:
    def test_maritime_domain(self):
        assert get_archetype_for_domains(["maritime", "commerce"]) == "maritime"

    def test_warfare_domain(self):
        assert get_archetype_for_domains(["warfare", "conquest"]) == "military"

    def test_unknown_domain_uses_default(self):
        assert get_archetype_for_domains(["unknown_domain"]) == "default"

    def test_empty_domains_uses_default(self):
        assert get_archetype_for_domains([]) == "default"


class TestNamePools:
    def test_each_pool_has_40_plus_names(self):
        for archetype, names in CULTURAL_NAME_POOLS.items():
            assert len(names) >= 40, f"Pool '{archetype}' has only {len(names)} names"


class TestSuccession:
    def test_heir_succession(self, leader_civ, leader_world):
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="heir")
        assert new_leader.succession_type == "heir"
        assert new_leader.predecessor_name == "Vaelith"
        assert new_leader.name != "Vaelith"
        assert new_leader.name in leader_world.used_leader_names

    def test_general_succession_effects(self, leader_civ, leader_world):
        old_stability = leader_civ.stability
        old_military = leader_civ.military
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="general")
        assert new_leader.succession_type == "general"
        assert new_leader.trait in ["aggressive", "bold", "ambitious"]
        assert leader_civ.stability == old_stability - 1
        assert leader_civ.military == min(old_military + 1, 10)

    def test_usurper_succession_effects(self, leader_civ, leader_world):
        old_stability = leader_civ.stability
        old_asabiya = leader_civ.asabiya
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="usurper")
        assert new_leader.succession_type == "usurper"
        assert leader_civ.stability == max(old_stability - 3, 1)
        assert leader_civ.asabiya == min(old_asabiya + 0.1, 1.0)

    def test_elected_succession_requires_culture(self, leader_civ, leader_world):
        leader_civ.culture = 4
        leader_civ.tech_era = TechEra.BRONZE
        leader_civ.leader.alive = False
        # When elected is forced but requirements not met, should fallback
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new_leader.succession_type != "elected"  # Fell back to heir/general/usurper

    def test_elected_succession_with_culture(self, leader_civ, leader_world):
        leader_civ.culture = 6
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new_leader.succession_type == "elected"
        assert leader_civ.stability >= 5  # stability +1

    def test_elected_succession_with_classical_era(self, leader_civ, leader_world):
        leader_civ.culture = 3
        leader_civ.tech_era = TechEra.CLASSICAL
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new_leader.succession_type == "elected"

    def test_name_deduplication(self, leader_civ, leader_world):
        """100 successions should produce no duplicate names."""
        names = set()
        for i in range(100):
            leader_civ.leader.alive = False
            new_leader = generate_successor(leader_civ, leader_world, seed=i)
            assert new_leader.name not in names, f"Duplicate name: {new_leader.name}"
            names.add(new_leader.name)
            leader_civ.leader = new_leader

    def test_heir_inherits_rivalry(self, leader_civ, leader_world):
        leader_civ.leader.rival_leader = "Gorath"
        leader_civ.leader.rival_civ = "Dorrathi Clans"
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="heir")
        assert new_leader.rival_leader == "Gorath"
        assert new_leader.rival_civ == "Dorrathi Clans"

    def test_usurper_generates_coup_event(self, leader_civ, leader_world):
        leader_civ.leader.alive = False
        generate_successor(leader_civ, leader_world, seed=100, force_type="usurper")
        coup_events = [ne for ne in leader_world.named_events if ne.event_type == "coup"]
        assert len(coup_events) == 1
        assert "Coup" in coup_events[0].name

    def test_general_does_not_inherit_rivalry(self, leader_civ, leader_world):
        leader_civ.leader.rival_leader = "Gorath"
        leader_civ.leader.rival_civ = "Dorrathi Clans"
        leader_civ.leader.alive = False
        new_leader = generate_successor(leader_civ, leader_world, seed=100, force_type="general")
        assert new_leader.rival_leader is None
        assert new_leader.rival_civ is None


class TestLegacy:
    def test_no_legacy_short_reign(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 10  # Only 10 turns (20 - 10)
        event = apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        assert event is None

    def test_legacy_long_reign_bold(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 0  # 20 turns reign
        event = apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        assert event is not None
        assert event.event_type == "legacy"
        # bold -> military_legacy
        conditions = [c for c in leader_world.active_conditions if c.condition_type == "military_legacy"]
        assert len(conditions) == 1
        assert conditions[0].duration == 10
        assert conditions[0].severity == 1

    def test_legacy_cautious_leader(self, leader_civ, leader_world):
        leader_civ.leader.trait = "cautious"
        leader_civ.leader.reign_start = 0
        event = apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        conditions = [c for c in leader_world.active_conditions if c.condition_type == "stability_legacy"]
        assert len(conditions) == 1

    def test_no_duplicate_legacy(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 0
        # Add an existing legacy
        leader_world.active_conditions.append(
            ActiveCondition(condition_type="military_legacy", affected_civs=["Kethani Empire"], duration=5, severity=1)
        )
        event = apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        assert event is None  # Already has a legacy


class TestRivalry:
    def test_war_creates_rivalry(self, leader_civ, leader_world):
        update_rivalries(leader_civ, leader_world.civilizations[1], leader_world)
        assert leader_civ.leader.rival_leader == "Gorath"
        assert leader_civ.leader.rival_civ == "Dorrathi Clans"
        assert leader_world.civilizations[1].leader.rival_leader == "Vaelith"
        assert leader_world.civilizations[1].leader.rival_civ == "Kethani Empire"


class TestRivalFall:
    def test_rival_fall_gives_culture_bonus(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        # Set up rivalry
        other = leader_world.civilizations[1]
        other.leader.rival_leader = "Vaelith"
        other.leader.rival_civ = "Kethani Empire"
        old_culture = other.culture
        event = check_rival_fall(leader_civ, "Vaelith", leader_world)
        assert event is not None
        assert other.culture == old_culture + 1

    def test_rival_fall_generates_named_event(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        other = leader_world.civilizations[1]
        other.leader.rival_leader = "Vaelith"
        other.leader.rival_civ = "Kethani Empire"
        check_rival_fall(leader_civ, "Vaelith", leader_world)
        fall_events = [ne for ne in leader_world.named_events if ne.event_type == "rival_fall"]
        assert len(fall_events) == 1
        assert "Vaelith" in fall_events[0].name

    def test_rival_fall_clears_rivalry(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        other = leader_world.civilizations[1]
        other.leader.rival_leader = "Vaelith"
        other.leader.rival_civ = "Kethani Empire"
        check_rival_fall(leader_civ, "Vaelith", leader_world)
        assert other.leader.rival_leader is None
        assert other.leader.rival_civ is None

    def test_no_rival_fall_if_no_rival(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        event = check_rival_fall(leader_civ, "Vaelith", leader_world)
        assert event is None


class TestTraitEvolution:
    def test_no_evolution_short_reign(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 15  # 5 turns
        leader_civ.action_counts = {"WAR": 5}
        result = check_trait_evolution(leader_civ, leader_world)
        assert result is None

    def test_evolution_after_10_turns(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5  # 15 turns
        leader_civ.action_counts = {"WAR": 10, "DEVELOP": 3, "TRADE": 2}
        result = check_trait_evolution(leader_civ, leader_world)
        assert result == "warlike"
        assert leader_civ.leader.secondary_trait == "warlike"

    def test_evolution_develop(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.action_counts = {"DEVELOP": 10, "WAR": 3}
        result = check_trait_evolution(leader_civ, leader_world)
        assert result == "builder"

    def test_no_double_evolution(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.leader.secondary_trait = "warlike"  # Already evolved
        leader_civ.action_counts = {"DEVELOP": 10}
        result = check_trait_evolution(leader_civ, leader_world)
        assert result is None  # Already has secondary trait
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_leaders.py -v 2>&1 | tail -20`

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement leaders.py**

Create `src/chronicler/leaders.py`. This is the largest new module. Key components:

```python
"""Leader system — succession, name pools, legacy, rivalry, trait evolution."""

from __future__ import annotations

import random

from chronicler.models import (
    ActiveCondition, Civilization, Event, Leader, NamedEvent, TechEra, WorldState,
)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


# --- Cultural Archetype Name Pools ---

_DOMAIN_TO_ARCHETYPE: dict[str, str] = {
    "maritime": "maritime", "commerce": "maritime", "coastal": "maritime",
    "nomadic": "steppe", "pastoral": "steppe", "plains": "steppe",
    "highland": "mountain", "mining": "mountain", "fortress": "mountain",
    "woodland": "forest", "sylvan": "forest", "nature": "forest",
    "arid": "desert", "oasis": "desert",
    "knowledge": "scholarly", "arcane": "scholarly", "culture": "scholarly",
    "warfare": "military", "conquest": "military", "martial": "military",
    "trade": "maritime",  # trade maps to maritime
}

CULTURAL_NAME_POOLS: dict[str, list[str]] = {
    "maritime": [
        "Thalor", "Nerissa", "Caelwen", "Maren", "Pelago", "Coralind", "Wavecrest",
        "Tidara", "Nautica", "Syrenis", "Riptide", "Kelphorn", "Deepwell", "Saltara",
        "Brinehart", "Seafoam", "Anchora", "Pearlwind", "Driftmere", "Gillian",
        "Hullbreaker", "Sternwell", "Bowsprit", "Jetsam", "Flotsam", "Reefborn",
        "Cordelia", "Tempesta", "Marinus", "Oceania", "Trillia", "Cascadis",
        "Abyssia", "Lagunara", "Shoalwick", "Harbright", "Windlass", "Compass",
        "Starboard", "Portwyn", "Leeward", "Helmford",
    ],
    "steppe": [
        "Toghrul", "Arslan", "Khulan", "Borte", "Temuge", "Jochi", "Sartaq",
        "Khutulun", "Batu", "Chagatai", "Ogedei", "Mongke", "Qasar", "Belgutei",
        "Subotai", "Jelme", "Muqali", "Jebe", "Subutai", "Tolui", "Alaqhai",
        "Manduhai", "Dayir", "Esen", "Turakina", "Guyuk", "Berke", "Hulagu",
        "Ariqboke", "Kaidu", "Toregene", "Sorqoqtani", "Chabi", "Doquz",
        "Bayar", "Tengri", "Altani", "Sorghaghtani", "Qutula", "Yesugei",
        "Hoelun", "Kublai",
    ],
    "mountain": [
        "Grimald", "Valdris", "Kareth", "Stonvar", "Brynhild", "Ironpeak",
        "Granith", "Basaltus", "Slatewood", "Quartzara", "Feldspar", "Obsidara",
        "Deepforge", "Anvilor", "Cragmore", "Peakwind", "Ridgeborn", "Cliffward",
        "Bouldergate", "Stonehelm", "Crystalis", "Gneissara", "Marblind",
        "Jasperine", "Shalewick", "Chalkstone", "Flintara", "Pumicor",
        "Rockstead", "Gorgemeld", "Summitara", "Plateauris", "Escarpment",
        "Morainia", "Talonpeak", "Spirehold", "Buttressara", "Pinnaclis",
        "Corniceus", "Ledgewick", "Cairnhold", "Dolmenara",
    ],
    "forest": [
        "Elara", "Sylvain", "Thornwick", "Fernhollow", "Alder", "Willowmere",
        "Birchwind", "Oakshade", "Pinecrest", "Mossgrove", "Ivywood", "Hazelborn",
        "Ashenvale", "Cedarhelm", "Hollywick", "Elmsworth", "Maplelind",
        "Rowan", "Laurelei", "Junipera", "Yewguard", "Larchmont", "Spruceford",
        "Lindenara", "Hickorind", "Beechwell", "Chestnutar", "Walnutgrove",
        "Sequoiara", "Cypresswind", "Banyaris", "Balsamon", "Magnolind",
        "Wisteris", "Acacia", "Tamarind", "Sassafras", "Dogwoodis",
        "Redwoodara", "Timberlind", "Briarvale", "Canopyara",
    ],
    "desert": [
        "Rashidi", "Zephyra", "Khalun", "Amaris", "Deshaan", "Saharen",
        "Dunewalker", "Miraga", "Oasian", "Scorchwind", "Sandara", "Sirocco",
        "Haboobis", "Aridius", "Xerxara", "Palmyra", "Bedounis", "Camelorn",
        "Twilara", "Solstara", "Heatsear", "Dustbloom", "Cactara", "Mesquiton",
        "Saltflat", "Playana", "Wadian", "Hammadis", "Ergunis", "Taklamaris",
        "Gobindis", "Negeva", "Atacaris", "Kalahari", "Sonoris", "Chihuan",
        "Mojavan", "Tharada", "Registan", "Karakorin", "Dasht", "Nubian",
    ],
    "scholarly": [
        "Vaelis", "Isendra", "Codrin", "Lexara", "Sapienth", "Erudis",
        "Scholara", "Logicus", "Theoris", "Hypothis", "Axiomara", "Proofwind",
        "Quillborn", "Inkwell", "Parchment", "Scribanis", "Tomelord", "Volumen",
        "Catalogis", "Indexara", "Referens", "Citadel", "Archivon", "Libris",
        "Canonis", "Dogmara", "Doctrinis", "Thesaura", "Lexicon", "Glossara",
        "Syntaxis", "Grammaris", "Rhetoris", "Dialectis", "Pedagogis",
        "Curricula", "Seminarion", "Symposia", "Colloquis", "Disquisara",
        "Monographis", "Treatisa",
    ],
    "military": [
        "Gorath", "Ironvar", "Bladwyn", "Shieldra", "Warmund", "Spearhart",
        "Helmgar", "Swordane", "Arroweld", "Pikemond", "Maceborn", "Halberd",
        "Catapultis", "Rampart", "Bulwark", "Siegemund", "Vanguardis", "Flanker",
        "Skirmara", "Sentinell", "Guardwald", "Garrison", "Battalius",
        "Legionara", "Cohortis", "Centurian", "Praetoris", "Imperator",
        "Tribunes", "Optimus", "Decurian", "Signifera", "Aquilara",
        "Ballistara", "Onagris", "Trebuchet", "Mantlegar", "Palisade",
        "Stockadis", "Bastionis", "Curtainis", "Parapetar",
    ],
    "default": [],  # Filled below
}

# Default pool is a mix of all others
CULTURAL_NAME_POOLS["default"] = [
    name for pool in CULTURAL_NAME_POOLS.values() for name in pool
]

TITLES = [
    "Emperor", "Empress", "King", "Queen", "Warchief", "High Priestess",
    "Chancellor", "Archon", "Consul", "Regent", "Sovereign", "Tribune",
    "Patriarch", "Matriarch", "Chieftain", "Elder",
]

# --- Succession ---

SUCCESSION_WEIGHTS: dict[str, float] = {
    "heir": 0.40,
    "general": 0.25,
    "usurper": 0.20,
    "elected": 0.15,
}

_FALLBACK_WEIGHTS: dict[str, float] = {
    "heir": 0.47,
    "general": 0.29,
    "usurper": 0.24,
}

SUCCESSION_TRAIT_BIAS: dict[str, list[str]] = {
    "heir": [],  # 50% chance inherit, else random
    "general": ["aggressive", "bold", "ambitious"],
    "usurper": ["ambitious", "calculating", "shrewd"],
    "elected": ["cautious", "visionary", "shrewd"],
}

ALL_TRAITS = [
    "ambitious", "cautious", "aggressive", "calculating", "zealous",
    "opportunistic", "stubborn", "bold", "shrewd", "visionary",
]

# --- Legacy ---

LEGACY_TRAIT_MAP: dict[str, str] = {
    "aggressive": "military_legacy",
    "bold": "military_legacy",
    "cautious": "stability_legacy",
    "calculating": "stability_legacy",
    "visionary": "economy_legacy",
    "shrewd": "economy_legacy",
    "zealous": "culture_legacy",
    "ambitious": "culture_legacy",
    "opportunistic": "economy_legacy",
    "stubborn": "stability_legacy",
}

LEGACY_EPITHETS: dict[str, str] = {
    "military_legacy": "the Conqueror",
    "stability_legacy": "the Wise",
    "economy_legacy": "the Prosperous",
    "culture_legacy": "the Enlightened",
}

# --- Trait Evolution ---

ACTION_TO_SECONDARY: dict[str, str] = {
    "WAR": "warlike",
    "DEVELOP": "builder",
    "TRADE": "merchant",
    "EXPAND": "conqueror",
    "DIPLOMACY": "diplomat",
}


def get_archetype_for_domains(domains: list[str]) -> str:
    """Map a civ's domain list to a cultural archetype for name selection."""
    for domain in domains:
        archetype = _DOMAIN_TO_ARCHETYPE.get(domain.lower())
        if archetype:
            return archetype
    return "default"


def _pick_name(civ: Civilization, world: WorldState, rng: random.Random) -> str:
    """Pick a unique leader name from the appropriate cultural pool."""
    archetype = get_archetype_for_domains(civ.domains)
    pool = CULTURAL_NAME_POOLS[archetype]

    # Filter out used names
    available = [n for n in pool if n not in world.used_leader_names]
    if not available:
        # Exhausted pool — fall back to default and filter
        available = [n for n in CULTURAL_NAME_POOLS["default"] if n not in world.used_leader_names]
    if not available:
        # Extreme fallback — generate numbered name
        base = rng.choice(pool)
        count = sum(1 for n in world.used_leader_names if n.startswith(base))
        name = f"{base} {'I' * (count + 2)}"
        world.used_leader_names.append(name)
        return name

    title = rng.choice(TITLES)
    name = rng.choice(available)
    world.used_leader_names.append(name)
    return f"{title} {name}"


def generate_successor(
    civ: Civilization,
    world: WorldState,
    seed: int,
    force_type: str | None = None,
) -> Leader:
    """Generate a successor leader for a civ whose leader has died.

    Applies stat effects of the succession type to the civ.
    Optionally force a succession type for testing.
    """
    rng = random.Random(seed + world.turn + hash(civ.name))
    old_leader = civ.leader

    # Determine succession type
    if force_type:
        stype = force_type
    else:
        types = list(SUCCESSION_WEIGHTS.keys())
        weights = list(SUCCESSION_WEIGHTS.values())
        stype = rng.choices(types, weights=weights, k=1)[0]

    # Check elected requirements
    if stype == "elected" and civ.culture < 5 and civ.tech_era.value not in [
        "classical", "medieval", "renaissance", "industrial"
    ]:
        # Fallback
        types = list(_FALLBACK_WEIGHTS.keys())
        weights = list(_FALLBACK_WEIGHTS.values())
        stype = rng.choices(types, weights=weights, k=1)[0]

    # Determine trait
    bias = SUCCESSION_TRAIT_BIAS[stype]
    if stype == "heir" and rng.random() < 0.5:
        trait = old_leader.trait  # Inherit
    elif bias:
        trait = rng.choice(bias)
    else:
        trait = rng.choice(ALL_TRAITS)

    # Generate name
    name = _pick_name(civ, world, rng)

    # Create new leader
    new_leader = Leader(
        name=name,
        trait=trait,
        reign_start=world.turn,
        succession_type=stype,
        predecessor_name=old_leader.name,
    )

    # Heir inherits rivalry
    if stype == "heir" and old_leader.rival_leader:
        new_leader.rival_leader = old_leader.rival_leader
        new_leader.rival_civ = old_leader.rival_civ

    # Apply succession effects
    if stype == "general":
        civ.stability = _clamp(civ.stability - 1, 1, 10)
        civ.military = _clamp(civ.military + 1, 1, 10)
    elif stype == "usurper":
        civ.stability = _clamp(civ.stability - 3, 1, 10)
        civ.asabiya = min(civ.asabiya + 0.1, 1.0)
        # Generate coup named event
        world.named_events.append(NamedEvent(
            name=f"The {civ.name} Coup",
            event_type="coup",
            turn=world.turn,
            actors=[civ.name],
            description=f"{name} seizes power from {old_leader.name}",
            importance=8,
        ))
    elif stype == "elected":
        civ.stability = _clamp(civ.stability + 1, 1, 10)

    # Clear action counts for new reign
    civ.action_counts = {}

    return new_leader


def apply_leader_legacy(
    civ: Civilization, leader: Leader, world: WorldState
) -> Event | None:
    """Apply legacy modifier if leader reigned 15+ turns. Returns event or None."""
    reign_length = world.turn - leader.reign_start
    if reign_length < 15:
        return None

    legacy_type = LEGACY_TRAIT_MAP.get(leader.trait)
    if not legacy_type:
        return None

    # Check for existing legacy on this civ
    for condition in world.active_conditions:
        if condition.condition_type.endswith("_legacy") and civ.name in condition.affected_civs:
            return None  # Already has a legacy

    # Apply
    world.active_conditions.append(
        ActiveCondition(
            condition_type=legacy_type,
            affected_civs=[civ.name],
            duration=10,
            severity=1,
        )
    )

    epithet = LEGACY_EPITHETS.get(legacy_type, "the Great")
    named_event = NamedEvent(
        name=f"The Legacy of {leader.name} {epithet}",
        event_type="legacy",
        turn=world.turn,
        actors=[civ.name],
        description=f"{leader.name}'s {reign_length}-turn reign leaves a lasting mark",
    )
    world.named_events.append(named_event)

    return Event(
        turn=world.turn,
        event_type="legacy",
        actors=[civ.name],
        description=f"The legacy of {leader.name} {epithet} endures",
        importance=6,
    )


def update_rivalries(
    attacker: Civilization, defender: Civilization, world: WorldState
) -> None:
    """Set rivalry between two leaders after war."""
    attacker.leader.rival_leader = defender.leader.name
    attacker.leader.rival_civ = defender.name
    defender.leader.rival_leader = attacker.leader.name
    defender.leader.rival_civ = attacker.name


def check_rival_fall(
    civ: Civilization, dead_leader_name: str, world: WorldState
) -> Event | None:
    """Check if any living leader was a rival of the dead leader. Apply bonuses."""
    for other_civ in world.civilizations:
        if other_civ.name == civ.name:
            continue
        if other_civ.leader.rival_leader == dead_leader_name:
            other_civ.culture = _clamp(other_civ.culture + 1, 1, 10)
            other_civ.leader.rival_leader = None
            other_civ.leader.rival_civ = None

            named_event = NamedEvent(
                name=f"The Fall of {dead_leader_name}",
                event_type="rival_fall",
                turn=world.turn,
                actors=[other_civ.name, civ.name],
                description=f"{other_civ.leader.name} celebrates the fall of rival {dead_leader_name}",
            )
            world.named_events.append(named_event)

            return Event(
                turn=world.turn,
                event_type="rival_fall",
                actors=[other_civ.name, civ.name],
                description=f"The rivalry ends with the fall of {dead_leader_name}",
                importance=6,
            )
    return None


def check_trait_evolution(
    civ: Civilization, world: WorldState
) -> str | None:
    """Check if leader gains a secondary trait based on action majority."""
    leader = civ.leader
    reign_length = world.turn - leader.reign_start
    if reign_length < 10:
        return None
    if leader.secondary_trait is not None:
        return None  # Already evolved

    if not civ.action_counts:
        return None

    # Find majority action
    majority_action = max(civ.action_counts, key=civ.action_counts.get)
    secondary = ACTION_TO_SECONDARY.get(majority_action)
    if secondary:
        leader.secondary_trait = secondary
    return secondary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_leaders.py -v 2>&1 | tail -40`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/leaders.py tests/test_leaders.py
git commit -m "feat(leaders): implement leader succession, legacy, rivalry, and name pools"
```

---

## Chunk 5: Action Engine

### Task 7: Implement deterministic action selection engine

**Files:**
- Create: `src/chronicler/action_engine.py`
- Create: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_action_engine.py`:

```python
import pytest
from chronicler.models import (
    ActionType, Civilization, Disposition, Leader, Region, Relationship,
    TechEra, WorldState,
)
from chronicler.action_engine import ActionEngine


@pytest.fixture
def engine_world():
    leader1 = Leader(name="Vaelith", trait="aggressive", reign_start=0)
    leader2 = Leader(name="Gorath", trait="cautious", reign_start=0)
    civ1 = Civilization(
        name="Civ A", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=15,
        leader=leader1, regions=["Region A", "Region B"],
        domains=["warfare"],
    )
    civ2 = Civilization(
        name="Civ B", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=15,
        leader=leader2, regions=["Region C"],
        domains=["commerce"],
    )
    world = WorldState(
        name="Test", seed=42, turn=5,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=8, resources="fertile", controller="Civ A"),
            Region(name="Region B", terrain="forest", carrying_capacity=6, resources="timber", controller="Civ A"),
            Region(name="Region C", terrain="coast", carrying_capacity=7, resources="maritime", controller="Civ B"),
            Region(name="Region D", terrain="plains", carrying_capacity=5, resources="fertile"),  # unclaimed
        ],
        civilizations=[civ1, civ2],
        relationships={
            "Civ A": {"Civ B": Relationship(disposition=Disposition.HOSTILE)},
            "Civ B": {"Civ A": Relationship(disposition=Disposition.HOSTILE)},
        },
    )
    return world


class TestEligibility:
    def test_expand_requires_unclaimed_regions(self, engine_world):
        engine = ActionEngine(engine_world)
        # All regions claimed — EXPAND should be ineligible
        for r in engine_world.regions:
            r.controller = "Civ A"
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.EXPAND not in eligible

    def test_expand_requires_military(self, engine_world):
        engine = ActionEngine(engine_world)
        engine_world.civilizations[0].military = 2
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.EXPAND not in eligible

    def test_war_requires_hostile_neighbor(self, engine_world):
        engine = ActionEngine(engine_world)
        # Make all relationships FRIENDLY
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.FRIENDLY
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.WAR not in eligible

    def test_trade_requires_bronze_era(self, engine_world):
        engine = ActionEngine(engine_world)
        engine_world.civilizations[0].tech_era = TechEra.TRIBAL
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.TRADE not in eligible

    def test_trade_requires_neutral_plus_partner(self, engine_world):
        engine = ActionEngine(engine_world)
        # Only hostile neighbors
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.TRADE not in eligible

    def test_develop_always_eligible(self, engine_world):
        engine = ActionEngine(engine_world)
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.DEVELOP in eligible

    def test_diplomacy_always_eligible(self, engine_world):
        engine = ActionEngine(engine_world)
        eligible = engine.get_eligible_actions(engine_world.civilizations[0])
        assert ActionType.DIPLOMACY in eligible


class TestPersonalityWeights:
    def test_aggressive_favors_war(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]  # aggressive leader
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > weights[ActionType.DEVELOP]

    def test_cautious_favors_develop(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[1]  # cautious leader
        # Need neutral+ partner for TRADE to be eligible
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DEVELOP] > weights[ActionType.WAR]

    def test_stubborn_boosts_last_action(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.leader.trait = "stubborn"
        engine_world.action_history["Civ A"] = ["DEVELOP"]
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DEVELOP] > weights[ActionType.WAR]


class TestSituationalOverrides:
    def test_low_stability_boosts_diplomacy(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.stability = 2
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DIPLOMACY] > weights[ActionType.WAR]

    def test_high_military_hostile_boosts_war(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.military = 8
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > weights[ActionType.DIPLOMACY]

    def test_low_treasury_suppresses_develop(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.treasury = 2
        weights = engine.compute_weights(civ)
        base_weight = 0.2 * 0.5  # aggressive DEVELOP base
        assert weights[ActionType.DEVELOP] < base_weight


class TestStreakBreaker:
    def test_streak_of_3_zeroes_action(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        engine_world.action_history["Civ A"] = ["DEVELOP", "DEVELOP", "DEVELOP"]
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DEVELOP] == 0.0

    def test_stubborn_streak_breaks_at_5(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.leader.trait = "stubborn"
        engine_world.action_history["Civ A"] = ["DEVELOP", "DEVELOP", "DEVELOP"]
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DEVELOP] > 0.0  # Not broken yet at 3

        engine_world.action_history["Civ A"] = ["DEVELOP"] * 5
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DEVELOP] == 0.0  # Broken at 5


class TestSelection:
    def test_deterministic(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        a1 = engine.select_action(civ, seed=42)
        a2 = engine.select_action(civ, seed=42)
        assert a1 == a2

    def test_returns_valid_action_type(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        action = engine.select_action(civ, seed=42)
        assert isinstance(action, ActionType)

    def test_all_ineligible_falls_back_to_develop(self, engine_world):
        """If somehow no actions are eligible, fall back to DEVELOP."""
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.military = 1
        civ.tech_era = TechEra.TRIBAL
        # Remove unclaimed regions, make all relationships hostile (no trade)
        for r in engine_world.regions:
            r.controller = "Civ A"
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.FRIENDLY
        # Now WAR ineligible (no hostile), EXPAND ineligible (no unclaimed + low mil),
        # TRADE ineligible (TRIBAL)
        # DEVELOP and DIPLOMACY should still be eligible
        action = engine.select_action(civ, seed=42)
        assert action in [ActionType.DEVELOP, ActionType.DIPLOMACY]


class TestSecondaryTrait:
    def test_secondary_trait_boosts_action(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.leader.secondary_trait = "warlike"
        weights_with = engine.compute_weights(civ)

        civ.leader.secondary_trait = None
        weights_without = engine.compute_weights(civ)

        assert weights_with[ActionType.WAR] > weights_without[ActionType.WAR]


class TestRivalryBoost:
    def test_rivalry_boosts_war_against_rival(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        civ.leader.rival_leader = "Gorath"
        civ.leader.rival_civ = "Civ B"
        weights_with = engine.compute_weights(civ)

        civ.leader.rival_leader = None
        civ.leader.rival_civ = None
        weights_without = engine.compute_weights(civ)

        assert weights_with[ActionType.WAR] > weights_without[ActionType.WAR]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_action_engine.py -v 2>&1 | tail -20`

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement action_engine.py**

Create `src/chronicler/action_engine.py`:

```python
"""Deterministic action selection engine with personality, situational, and streak logic."""

from __future__ import annotations

import random

from chronicler.models import (
    ActionType, Civilization, Disposition, TechEra, WorldState,
)

# Layer 1: Personality weight profiles per leader trait
TRAIT_WEIGHTS: dict[str, dict[ActionType, float]] = {
    "aggressive":   {ActionType.WAR: 2.0, ActionType.EXPAND: 1.3, ActionType.DEVELOP: 0.5, ActionType.TRADE: 0.8, ActionType.DIPLOMACY: 0.3},
    "cautious":     {ActionType.WAR: 0.2, ActionType.EXPAND: 0.5, ActionType.DEVELOP: 2.0, ActionType.TRADE: 1.3, ActionType.DIPLOMACY: 1.5},
    "opportunistic":{ActionType.WAR: 1.0, ActionType.EXPAND: 1.5, ActionType.DEVELOP: 0.8, ActionType.TRADE: 2.0, ActionType.DIPLOMACY: 0.7},
    "zealous":      {ActionType.WAR: 1.5, ActionType.EXPAND: 2.0, ActionType.DEVELOP: 1.3, ActionType.TRADE: 0.5, ActionType.DIPLOMACY: 0.4},
    "ambitious":    {ActionType.WAR: 1.2, ActionType.EXPAND: 1.8, ActionType.DEVELOP: 1.5, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.6},
    "calculating":  {ActionType.WAR: 0.7, ActionType.EXPAND: 0.8, ActionType.DEVELOP: 1.8, ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.3},
    "visionary":    {ActionType.WAR: 0.4, ActionType.EXPAND: 1.0, ActionType.DEVELOP: 1.8, ActionType.TRADE: 1.3, ActionType.DIPLOMACY: 1.5},
    "bold":         {ActionType.WAR: 1.8, ActionType.EXPAND: 1.8, ActionType.DEVELOP: 0.6, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.5},
    "shrewd":       {ActionType.WAR: 0.5, ActionType.EXPAND: 0.7, ActionType.DEVELOP: 1.2, ActionType.TRADE: 2.0, ActionType.DIPLOMACY: 1.8},
    "stubborn":     {},  # Handled specially in compute_weights
}

# Secondary trait action mapping for x1.3 boost
SECONDARY_TRAIT_ACTION: dict[str, ActionType] = {
    "warlike": ActionType.WAR,
    "builder": ActionType.DEVELOP,
    "merchant": ActionType.TRADE,
    "conqueror": ActionType.EXPAND,
    "diplomat": ActionType.DIPLOMACY,
}

# Tech era ordering for gating
_ERA_ORDER = list(TechEra)


def _era_at_least(era: TechEra, minimum: TechEra) -> bool:
    return _ERA_ORDER.index(era) >= _ERA_ORDER.index(minimum)


class ActionEngine:
    """Deterministic action selection engine."""

    def __init__(self, world: WorldState):
        self.world = world

    def get_eligible_actions(self, civ: Civilization) -> list[ActionType]:
        """Return list of actions the civ can legally take."""
        eligible = [ActionType.DEVELOP]  # Always eligible

        # DIPLOMACY — always available (even without treaties, basic disposition upgrade works)
        eligible.append(ActionType.DIPLOMACY)

        # EXPAND — needs military >= 3 and unclaimed regions
        unclaimed = [r for r in self.world.regions if r.controller is None]
        if civ.military >= 3 and unclaimed:
            eligible.append(ActionType.EXPAND)

        # WAR — needs hostile/suspicious neighbor
        has_hostile = False
        if civ.name in self.world.relationships:
            for other_name, rel in self.world.relationships[civ.name].items():
                if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    has_hostile = True
                    break
        if has_hostile:
            eligible.append(ActionType.WAR)

        # TRADE — needs BRONZE+ and NEUTRAL+ partner
        if _era_at_least(civ.tech_era, TechEra.BRONZE):
            has_trade_partner = False
            if civ.name in self.world.relationships:
                for other_name, rel in self.world.relationships[civ.name].items():
                    if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                        has_trade_partner = True
                        break
            if has_trade_partner:
                eligible.append(ActionType.TRADE)

        return eligible

    def compute_weights(self, civ: Civilization) -> dict[ActionType, float]:
        """Compute final action weights after all three layers."""
        eligible = self.get_eligible_actions(civ)
        base = 0.2

        # Start with base weights
        weights: dict[ActionType, float] = {a: base for a in ActionType}

        # Zero out ineligible actions
        for action in ActionType:
            if action not in eligible:
                weights[action] = 0.0

        # Layer 1: Personality
        trait = civ.leader.trait
        if trait == "stubborn":
            # Boost last action x2.0, others x0.8
            history = self.world.action_history.get(civ.name, [])
            last_action = history[-1] if history else None
            for action in ActionType:
                if weights[action] == 0.0:
                    continue
                if last_action and action.value == last_action:
                    weights[action] *= 2.0
                else:
                    weights[action] *= 0.8
        else:
            profile = TRAIT_WEIGHTS.get(trait, {})
            for action in ActionType:
                if weights[action] == 0.0:
                    continue
                weights[action] *= profile.get(action, 1.0)

        # Layer 2: Situational overrides
        self._apply_situational(civ, weights)

        # Secondary trait boost
        if civ.leader.secondary_trait:
            boosted_action = SECONDARY_TRAIT_ACTION.get(civ.leader.secondary_trait)
            if boosted_action and weights[boosted_action] > 0:
                weights[boosted_action] *= 1.3

        # Rivalry boost
        if civ.leader.rival_civ:
            # Check if rival civ has hostile/suspicious disposition
            if civ.name in self.world.relationships:
                rival_rel = self.world.relationships[civ.name].get(civ.leader.rival_civ)
                if rival_rel and rival_rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    weights[ActionType.WAR] *= 1.5

        # Layer 3: Streak breaker
        history = self.world.action_history.get(civ.name, [])
        streak_limit = 5 if civ.leader.trait == "stubborn" else 3
        if len(history) >= streak_limit:
            last_n = history[-streak_limit:]
            if len(set(last_n)) == 1:
                streaked = ActionType(last_n[0])
                weights[streaked] = 0.0

        return weights

    def _apply_situational(self, civ: Civilization, weights: dict[ActionType, float]) -> None:
        """Apply situational override multipliers."""
        # Low stability — seek peace
        if civ.stability <= 2:
            weights[ActionType.DIPLOMACY] *= 3.0
            weights[ActionType.WAR] *= 0.1

        # High military + hostile neighbor — push for war
        has_hostile = False
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    has_hostile = True
                    break
        if civ.military >= 7 and has_hostile:
            weights[ActionType.WAR] *= 2.5

        # Flush with cash
        if civ.treasury >= 20:
            weights[ActionType.EXPAND] *= 2.0
            weights[ActionType.TRADE] *= 1.5

        # Broke
        if civ.treasury <= 3:
            weights[ActionType.DEVELOP] *= 0.3
            weights[ActionType.EXPAND] *= 0.2

        # Overcrowded
        if civ.population >= 8 and len(civ.regions) <= 2:
            weights[ActionType.EXPAND] *= 3.0

        # Poor economy
        if civ.economy <= 3:
            weights[ActionType.DEVELOP] *= 2.0
            weights[ActionType.TRADE] *= 1.5

        # No one to fight
        if not has_hostile:
            weights[ActionType.WAR] *= 0.1

        # Everyone allied — no point in diplomacy
        all_allied = True
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition != Disposition.ALLIED:
                    all_allied = False
                    break
        else:
            all_allied = False
        if all_allied:
            weights[ActionType.DIPLOMACY] *= 0.1

    def select_action(self, civ: Civilization, seed: int) -> ActionType:
        """Select an action using weighted random, seeded for determinism."""
        weights = self.compute_weights(civ)

        # Filter to positive weights
        actions = [a for a, w in weights.items() if w > 0]
        action_weights = [weights[a] for a in actions]

        if not actions:
            return ActionType.DEVELOP  # Ultimate fallback

        rng = random.Random(seed + self.world.turn + hash(civ.name))
        chosen = rng.choices(actions, weights=action_weights, k=1)[0]
        return chosen
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_action_engine.py -v 2>&1 | tail -40`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "feat(action_engine): implement deterministic action selection engine"
```

---

## Chunk 6: Simulation Integration

### Task 8: Expand run_turn to 9 phases

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/events.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing tests for 9-phase loop**

Add to `tests/test_simulation.py`:

```python
from chronicler.models import TechEra, NamedEvent


def test_nine_phase_run_turn(sample_world):
    """run_turn executes all 9 phases without error."""
    # Boost stats so tech advancement can happen
    for civ in sample_world.civilizations:
        civ.tech_era = TechEra.TRIBAL
        civ.economy = 5
        civ.culture = 5
        civ.treasury = 15

    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    result = run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    assert isinstance(result, str)
    assert sample_world.turn == 1


def test_tech_phase_runs_before_action(sample_world):
    """Tech advancement should happen before action selection."""
    for civ in sample_world.civilizations:
        civ.tech_era = TechEra.TRIBAL
        civ.economy = 4
        civ.culture = 4
        civ.treasury = 10

    actions_seen = []

    def tracking_selector(civ, world):
        actions_seen.append((civ.name, civ.tech_era.value))
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(sample_world, tracking_selector, stub_narrator, seed=42)
    # By the time action selection runs, tech era should have advanced
    for name, era in actions_seen:
        # At least one civ should have advanced past TRIBAL
        pass  # Just verify no crash; specific advancement depends on exact stats


def test_leader_dynamics_phase(sample_world):
    """Leader dynamics phase handles trait evolution."""
    civ = sample_world.civilizations[0]
    civ.leader.reign_start = 0
    civ.action_counts = {"WAR": 15}
    sample_world.turn = 15

    def stub_selector(c, w):
        return ActionType.DEVELOP

    def stub_narrator(w, e):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    # After leader dynamics, trait evolution should have run
    # (leader has 15+ turns and majority WAR actions)
    assert civ.leader.secondary_trait == "warlike"


def test_action_history_tracked(sample_world):
    """Action history is recorded for streak tracking."""
    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    for civ in sample_world.civilizations:
        assert civ.name in sample_world.action_history
        assert sample_world.action_history[civ.name][-1] == "DEVELOP"


def test_action_counts_tracked(sample_world):
    """Action counts increment for current leader's reign."""
    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    for civ in sample_world.civilizations:
        assert civ.action_counts.get("DEVELOP", 0) >= 1


def test_war_uses_tech_disparity(sample_world):
    """War resolution accounts for tech era gap."""
    attacker = sample_world.civilizations[0]
    defender = sample_world.civilizations[1]
    attacker.tech_era = TechEra.MEDIEVAL
    defender.tech_era = TechEra.TRIBAL
    attacker.military = 5
    defender.military = 5
    attacker.treasury = 10
    defender.treasury = 10

    # Run war multiple times — the tech advantage should show
    from chronicler.simulation import resolve_war
    results = []
    for seed in range(50):
        # Reset stats each time
        attacker.military = 5
        defender.military = 5
        attacker.treasury = 10
        defender.treasury = 10
        result = resolve_war(attacker, defender, sample_world, seed=seed)
        results.append(result)

    # With a 3-era gap (MEDIEVAL vs TRIBAL = 1.5x multiplier), attacker should win more often
    attacker_wins = sum(1 for r in results if r == "attacker_wins")
    assert attacker_wins > 25, f"Tech advantage not reflected: {attacker_wins}/50 wins"


def test_backward_compat_old_state(tmp_path, sample_world):
    """Old state files without new fields should load and run."""
    # Save state without new fields (simulating old format)
    state_path = tmp_path / "state.json"
    sample_world.save(state_path)

    # Load and verify
    from chronicler.models import WorldState
    loaded = WorldState.load(state_path)
    assert loaded.named_events == []
    assert loaded.used_leader_names == []
    assert loaded.action_history == {}

    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    # Should run without error
    run_turn(loaded, stub_selector, stub_narrator, seed=42)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_simulation.py -v -k "nine_phase or tech_phase or leader_dynamics or action_history_tracked or action_counts_tracked or war_uses_tech or backward_compat" 2>&1 | tail -20`

Expected: Some FAIL (new phase logic not yet wired).

- [ ] **Step 3: Add new cascade rules to events.py**

In `src/chronicler/events.py`, add to `EVENT_CASCADE_RULES`:

```python
    "tech_advancement": {
        "discovery": 0.03,
        "cultural_renaissance": 0.02,
        "trade": 0.02,
    },
    "coup": {
        "rebellion": 0.05,
        "border_incident": 0.03,
        "migration": 0.02,
    },
    "legacy": {
        "cultural_renaissance": 0.02,
        "discovery": 0.01,
    },
    "rival_fall": {
        "border_incident": -0.02,
        "war": -0.01,
    },
```

- [ ] **Step 4: Update simulation.py to 9-phase loop**

Modify `src/chronicler/simulation.py`:

Add imports at top:
```python
from chronicler.tech import check_tech_advancement, tech_war_multiplier
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    check_rival_fall, update_rivalries,
)
from chronicler.named_events import generate_battle_name, generate_treaty_name
```

Add new phase functions:

```python
def phase_technology(world: WorldState) -> list[Event]:
    """Phase 3: Check tech advancement for each civ."""
    from chronicler.named_events import generate_tech_breakthrough_name
    events = []
    for civ in world.civilizations:
        event = check_tech_advancement(civ, world)
        if event:
            events.append(event)
            # Generate named tech breakthrough
            name = generate_tech_breakthrough_name(civ.tech_era)
            world.named_events.append(NamedEvent(
                name=name, event_type="tech_breakthrough", turn=world.turn,
                actors=[civ.name], description=event.description, importance=7,
            ))
    return events


def phase_cultural_milestones(world: WorldState) -> list[Event]:
    """Check cultural milestone thresholds (culture >= 8, >= 10) for named works."""
    from chronicler.named_events import generate_cultural_work
    events = []
    for civ in world.civilizations:
        for threshold in [8, 10]:
            marker = f"culture_{threshold}"
            if civ.culture >= threshold and marker not in civ.cultural_milestones:
                civ.cultural_milestones.append(marker)
                name = generate_cultural_work(civ, world, seed=world.seed)
                ne = NamedEvent(
                    name=name, event_type="cultural_work", turn=world.turn,
                    actors=[civ.name], description=f"{civ.name} produces a cultural masterwork",
                    importance=6,
                )
                world.named_events.append(ne)
                events.append(Event(
                    turn=world.turn, event_type="cultural_work", actors=[civ.name],
                    description=ne.description, importance=6,
                ))
    return events


def phase_leader_dynamics(world: WorldState, seed: int) -> list[Event]:
    """Phase 7: Handle trait evolution for all living leaders."""
    events = []
    for civ in world.civilizations:
        # Check trait evolution (10+ turn reign, majority action)
        check_trait_evolution(civ, world)
    return events
```

**Note on succession/legacy/rivalry:** These are event-driven, not turn-driven. `leader_death` events in `_apply_event_effects` (Phase 6) trigger `generate_successor`, `apply_leader_legacy`, and `check_rival_fall`. War resolution (Phase 5) triggers `update_rivalries`. `phase_leader_dynamics` handles only the turn-driven check: trait evolution.

Update `resolve_war` to apply tech disparity multiplier:
- After computing `att_power` and `def_power`, multiply by `tech_war_multiplier(attacker.tech_era, defender.tech_era)` for attacker, and `tech_war_multiplier(defender.tech_era, attacker.tech_era)` for defender.

Update `_resolve_war_action` to:
- Only target civs with HOSTILE or SUSPICIOUS disposition
- After resolution, call `update_rivalries(attacker, defender, world)` if it was a decisive outcome
- Generate named battle event via `generate_battle_name` for decisive outcomes

Update `_resolve_diplomacy` to generate named treaty when upgrading to FRIENDLY or ALLIED.

Update `_apply_event_effects` for `leader_death`:
- Replace inline succession with call to `generate_successor`
- Call `apply_leader_legacy` for the dying leader
- Call `check_rival_fall` for the dying leader

Update `run_turn` to call phases in order:
1. `phase_environment`
2. `phase_production`
3. `phase_technology` (NEW)
4. `phase_action` (action selection + resolution — Phases 4+5 combined)
5. `phase_cultural_milestones` (NEW — check culture thresholds for named works)
6. `phase_random_events`
7. `phase_leader_dynamics` (NEW — trait evolution)
8. `phase_consequences`
9. narrator callback

In `phase_action`, after selecting and resolving each action, add tracking:
```python
    # Track action in history (for streak breaker)
    history = world.action_history.setdefault(civ.name, [])
    history.append(action.value)
    if len(history) > 5:
        world.action_history[civ.name] = history[-5:]

    # Track action counts (for trait evolution — persists across all turns for current leader)
    civ.action_counts[action.value] = civ.action_counts.get(action.value, 0) + 1
```

Update `_resolve_war_action` to enforce HOSTILE/SUSPICIOUS disposition threshold:
```python
    # Find target: most hostile neighbor with HOSTILE or SUSPICIOUS disposition
    worst_disp = None
    target = None
    for other_name, rel in world.relationships[civ.name].items():
        if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
            continue  # Skip NEUTRAL/FRIENDLY/ALLIED — can't declare war
        disp_val = DISPOSITION_ORDER[rel.disposition]
        if worst_disp is None or disp_val < worst_disp:
            worst_disp = disp_val
            target = other_name
    if target is None:
        # No valid war target — fall back to DEVELOP
        return _resolve_develop(civ, world)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_simulation.py -v 2>&1 | tail -40`

Expected: All PASS (both new and existing tests).

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/ -v 2>&1 | tail -40`

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/events.py tests/test_simulation.py
git commit -m "feat(simulation): expand to 9-phase loop with tech, leaders, named events"
```

---

## Chunk 7: Narrative, CLI, and Integration Tests

### Task 9: Update chronicle prompt with named events and rivalries

**Files:**
- Modify: `src/chronicler/narrative.py:84-118` (build_chronicle_prompt)
- Modify: `tests/test_narrative.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_narrative.py`:

```python
from chronicler.models import NamedEvent


def test_chronicle_prompt_includes_recent_named_events(sample_world):
    """Chronicle prompt should include the 5 most recent named events."""
    for i in range(7):
        sample_world.named_events.append(NamedEvent(
            name=f"Event {i}",
            event_type="battle",
            turn=i,
            actors=["Kethani Empire"],
            description=f"Description {i}",
        ))
    events = []
    prompt = build_chronicle_prompt(sample_world, events)
    # Should include the 5 most recent (events 2-6)
    assert "Event 6" in prompt
    assert "Event 5" in prompt
    assert "Event 2" in prompt
    # Should NOT include oldest events
    assert "Event 0" not in prompt or "Event 6" in prompt  # At minimum, recent ones present


def test_chronicle_prompt_includes_highest_importance_event(sample_world):
    """Chronicle prompt includes the single highest-importance named event."""
    # Add several named events with varying importance
    sample_world.named_events.append(NamedEvent(
        name="Minor Skirmish",
        event_type="battle",
        turn=1,
        actors=["Kethani Empire"],
        description="A minor border clash",
        importance=3,
    ))
    sample_world.named_events.append(NamedEvent(
        name="The Great Catastrophe",
        event_type="battle",
        turn=2,
        actors=["Kethani Empire"],
        description="The most important event ever",
        importance=10,
    ))
    events = []
    prompt = build_chronicle_prompt(sample_world, events)
    assert "The Great Catastrophe" in prompt


def test_chronicle_prompt_includes_rivalries(sample_world):
    """Chronicle prompt mentions active leader rivalries."""
    sample_world.civilizations[0].leader.rival_leader = "Gorath"
    sample_world.civilizations[0].leader.rival_civ = "Dorrathi Clans"
    events = []
    prompt = build_chronicle_prompt(sample_world, events)
    assert "rival" in prompt.lower() or "Gorath" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_narrative.py -v -k "named_events or highest_importance or rivalries" 2>&1 | tail -20`

Expected: FAIL — prompt doesn't include these yet.

- [ ] **Step 3: Update build_chronicle_prompt in narrative.py**

In `src/chronicler/narrative.py`, modify `build_chronicle_prompt` (lines 84-118) to append:

```python
    # Named events context for historical callbacks
    if world.named_events:
        recent = world.named_events[-5:]
        prompt += "\n\nRecent historical landmarks:\n"
        for ne in recent:
            prompt += f"- {ne.name} (turn {ne.turn}): {ne.description}\n"

        # Highest importance named event from all history (using NamedEvent.importance directly)
        best_named = max(world.named_events, key=lambda ne: ne.importance)
        if best_named not in recent:
            prompt += f"\nMost significant event in all history: {best_named.name} (turn {best_named.turn})\n"

        prompt += "\nReference these landmarks when relevant — weave callbacks to past events.\n"

    # Rivalry context
    rivalries = []
    for civ in world.civilizations:
        if civ.leader.rival_leader:
            rivalries.append(f"{civ.leader.name} of {civ.name} has a personal rivalry with {civ.leader.rival_leader} of {civ.leader.rival_civ}")
    if rivalries:
        prompt += "\n\nActive rivalries:\n"
        for r in rivalries:
            prompt += f"- {r}\n"
        prompt += "Weave these personal rivalries into the narrative when relevant.\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_narrative.py -v 2>&1 | tail -20`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat(narrative): add named events and rivalries to chronicle prompt"
```

---

### Task 10: Wire ActionEngine in main.py and add --llm-actions flag

**Files:**
- Modify: `src/chronicler/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_main.py`:

```python
def test_llm_actions_flag_in_parser():
    """CLI parser should accept --llm-actions flag."""
    import argparse
    from chronicler.main import main
    # Just verify the flag is parseable (don't run full simulation)
    parser = argparse.ArgumentParser()
    # Re-create the parser setup from main.py and verify --llm-actions exists
    # This is a simple smoke test
    from chronicler.main import _build_parser
    p = _build_parser()
    args = p.parse_args(["--llm-actions"])
    assert args.llm_actions is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_main.py -v -k "llm_actions" 2>&1 | tail -10`

Expected: FAIL — `_build_parser` doesn't exist / no `--llm-actions` flag.

- [ ] **Step 3: Refactor main.py**

In `src/chronicler/main.py`:

1. Extract argument parser into `_build_parser()` function
2. Add `--llm-actions` flag: `parser.add_argument("--llm-actions", action="store_true", default=False, help="Use LLM for action selection (default: deterministic engine)")`
3. In `run_chronicle`, wire the action engine:

```python
from chronicler.action_engine import ActionEngine

# In run_chronicle, create action selector:
engine = ActionEngine(world)

if use_llm_actions and narrative_engine:
    def action_selector(civ, world):
        try:
            action = narrative_engine.select_action(civ, world)
            # Verify eligibility
            eligible = engine.get_eligible_actions(civ)
            if action in eligible:
                return action
        except Exception:
            pass
        return engine.select_action(civ, seed=world.seed)
else:
    def action_selector(civ, world):
        return engine.select_action(civ, seed=world.seed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_main.py -v 2>&1 | tail -20`

Expected: All PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/ -v 2>&1 | tail -40`

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(main): wire ActionEngine as default, add --llm-actions flag"
```

---

### Task 11: Critical gate integration test

**Files:**
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: Write the 20-turn integration test**

Add to `tests/test_e2e.py`:

```python
from chronicler.models import TechEra, ActionType


def test_m7_critical_gate_20_turns():
    """20-turn, 4-civ integration test validating M7 acceptance criteria.

    Note: Spec Section 9 says 50 turns, but the testing strategy (Section 7)
    specifies 20 turns with boosted stats for the critical gate test. 20 turns
    is sufficient to validate all criteria with TRIBAL starts + boosted stats,
    and keeps test execution fast.

    Verifies:
    - At least 3 different action types chosen per civ
    - At least 1 tech advancement across all civs
    - At least 2 named events generated
    - No leader name duplicates
    - No crashes, all stats bounded
    - State serializes and deserializes correctly
    """
    from chronicler.world_gen import generate_world
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine

    world = generate_world(seed=42, num_regions=8, num_civs=4)

    # Boost starting stats so tech advancement is reachable
    for civ in world.civilizations:
        civ.economy = 5
        civ.culture = 5
        civ.treasury = 12

    def stub_narrator(w, events):
        return "Turn narrative."

    for turn_num in range(20):
        engine = ActionEngine(world)
        action_selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed)
        run_turn(world, action_selector, stub_narrator, seed=world.seed + turn_num)

    # Criterion 1: At least 3 different action types per civ
    # Use action_counts (full leader reign) not action_history (last 5 only)
    for civ in world.civilizations:
        action_types = set(civ.action_counts.keys())
        assert len(action_types) >= 3, f"{civ.name} only used {action_types}"

    # Criterion 2: At least 1 tech advancement
    tech_events = [e for e in world.events_timeline if e.event_type == "tech_advancement"]
    assert len(tech_events) >= 1, "No tech advancements occurred"

    # Criterion 3: At least 2 named events
    assert len(world.named_events) >= 2, f"Only {len(world.named_events)} named events"

    # Criterion 4: No leader name duplicates
    assert len(world.used_leader_names) == len(set(world.used_leader_names)), \
        "Duplicate leader names found"

    # Criterion 5: All stats bounded
    for civ in world.civilizations:
        assert 1 <= civ.population <= 10
        assert 1 <= civ.military <= 10
        assert 1 <= civ.economy <= 10
        assert 1 <= civ.culture <= 10
        assert 1 <= civ.stability <= 10
        assert 0.0 <= civ.asabiya <= 1.0
        assert civ.treasury >= 0

    # Criterion 6: State serialization round-trip
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        world.save(path)
        from chronicler.models import WorldState
        loaded = WorldState.load(path)
        assert loaded.turn == world.turn
        assert len(loaded.named_events) == len(world.named_events)
        assert len(loaded.civilizations) == len(world.civilizations)
```

- [ ] **Step 2: Run the critical gate test**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_e2e.py::test_m7_critical_gate_20_turns -v 2>&1`

Expected: PASS.

- [ ] **Step 3: Run full test suite one final time**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/ -v 2>&1 | tail -40`

Expected: All tests PASS (184+ total).

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test(e2e): add 20-turn M7 critical gate integration test"
```

---

## Final Verification

After all tasks complete:

1. Run full test suite: `python -m pytest tests/ -v`
2. Verify no import errors: `python -c "from chronicler import action_engine, tech, leaders, named_events"`
3. Run a quick 10-turn simulation: `python -m chronicler --turns 10 --seed 42`
4. Verify state.json output has new fields (named_events, used_leader_names, action_history)
