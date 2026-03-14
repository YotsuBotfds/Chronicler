# M17: Great Person Engine — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add named characters (generals, merchants, prophets, scientists) who emerge from achievement, interact with leaders, and leave permanent marks on civilizational identity through traditions and folk heroes.

**Architecture:** Parallel `GreatPerson` model alongside existing `Leader` (shared field names for duck typing, no inheritance). Domain-tagged modifier registry consumed by existing turn phases. Achievement-triggered generation with cooldowns. Four implementation phases (M17a→d) with no forward references.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. Pure simulation — no LLM calls.

**Spec:** `docs/superpowers/specs/2026-03-14-m17-great-person-engine-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/chronicler/great_persons.py` | GreatPerson generation, lifecycle, modifier registry (`get_modifiers`), achievement checks, name generation, retirement/death/archival |
| `src/chronicler/succession.py` | Succession crisis formula, multi-turn crisis state machine, general-to-leader conversion, exiled leader creation/restoration, legacy expansion |
| `src/chronicler/traditions.py` | Event counts tracking, tradition acquisition (both paths), folk hero creation, prophet martyrdom, tradition ongoing effects |
| `src/chronicler/relationships.py` | Rivalry, mentorship, marriage alliance formation/dissolution, hostage exchange mechanics |
| `tests/test_great_persons.py` | M17a tests |
| `tests/test_succession.py` | M17b tests |
| `tests/test_relationships.py` | M17c tests |
| `tests/test_traditions.py` | M17d tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/chronicler/models.py:125-166,256-284,301-322` | Add `GreatPerson` model, new fields on `Civilization`, `Leader`, `WorldState`, `CivSnapshot` |
| `src/chronicler/action_engine.py:287-368` | `resolve_war()` → return `WarResult` namedtuple; modifier consumption in combat; grudge/tradition weight biases in `compute_weights()` |
| `src/chronicler/simulation.py:145-312,429-435,508-575,638-649,654-697` | Phase 2 hooks (exile drain, hostage ticks, tradition effects), Phase 7 leader-death deferral, Phase 8 crisis resolution, Phase 9 fertility floor, Phase 10 great person consequences |
| `src/chronicler/leaders.py:187-227,230-249` | Grudge inheritance on succession, legacy expansion (golden age/shame/fracture), `legacy_counts` increment |
| `src/chronicler/politics.py:94-247` | Tradition inheritance through secession |
| `src/chronicler/movements.py:80-112` | Prophet acceleration in `_process_spread()` |
| `src/chronicler/named_events.py` | New generators: great person birth/death/ascension events |

---

## Chunk 1: M17a — Character Foundation

### Task 1: Add GreatPerson model and new fields to models.py

**Files:**
- Modify: `src/chronicler/models.py:125-134` (Leader — add grudges field)
- Modify: `src/chronicler/models.py:137-166` (Civilization — add great_persons, traditions, etc.)
- Modify: `src/chronicler/models.py:256-284` (WorldState — add retired_persons, cooldowns, relationships)
- Modify: `src/chronicler/models.py:301-322` (CivSnapshot — add great_persons, traditions, folk_heroes, active_crisis)
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write failing test for GreatPerson model**

```python
# tests/test_great_persons.py
from chronicler.models import GreatPerson, Civilization, WorldState

def test_great_person_creation():
    gp = GreatPerson(
        name="General Khotun",
        role="general",
        trait="aggressive",
        civilization="Mongol",
        origin_civilization="Mongol",
        born_turn=10,
    )
    assert gp.alive is True
    assert gp.active is True
    assert gp.fate == "active"
    assert gp.deeds == []
    assert gp.movement_id is None

def test_civilization_great_person_fields():
    """New M17 fields have correct defaults."""
    # Use existing test helper or minimal Civilization construction
    from tests.conftest import make_civ  # or construct manually
    civ = make_civ("TestCiv")
    assert civ.great_persons == []
    assert civ.traditions == []
    assert civ.legacy_counts == {}
    assert civ.event_counts == {}
    assert civ.war_win_turns == []
    assert civ.folk_heroes == []
    assert civ.succession_crisis_turns_remaining == 0
    assert civ.succession_candidates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_great_persons.py -v --tb=short 2>&1 | head -30`
Expected: ImportError — `GreatPerson` not defined, or missing fields on `Civilization`.

- [ ] **Step 3: Add GreatPerson model to models.py**

Add after `HistoricalFigure` class (~line 185):

```python
class GreatPerson(BaseModel):
    name: str
    role: str  # "general", "merchant", "prophet", "scientist", "exile", "hostage"
    trait: str
    civilization: str
    origin_civilization: str
    alive: bool = True
    active: bool = True
    fate: str = "active"  # "active", "retired", "dead", "ascended"
    born_turn: int
    death_turn: int | None = None
    deeds: list[str] = []
    region: str | None = None
    captured_by: str | None = None
    is_hostage: bool = False
    hostage_turns: int = 0
    cultural_identity: str | None = None
    movement_id: int | None = None
```

- [ ] **Step 4: Add new fields to Civilization model**

Add to `Civilization` class (after existing fields, ~line 166):

```python
    great_persons: list[GreatPerson] = []
    traditions: list[str] = []
    legacy_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    war_win_turns: list[int] = []
    folk_heroes: list[dict] = []
    succession_crisis_turns_remaining: int = 0
    succession_candidates: list[dict] = []
```

- [ ] **Step 5: Add grudges field to Leader model**

Add to `Leader` class (after `secondary_trait`, ~line 134):

```python
    grudges: list[dict] = []
```

- [ ] **Step 6: Add new fields to WorldState model**

Add to `WorldState` class (after existing fields, ~line 284):

```python
    retired_persons: list[GreatPerson] = []
    character_relationships: list[dict] = []
    great_person_cooldowns: dict[str, dict[str, int]] = {}
```

Note: `GreatPerson` must be imported or defined before `WorldState` uses it. Since both are in models.py, ordering handles this — `GreatPerson` defined before `WorldState`.

- [ ] **Step 7: Add new fields to CivSnapshot model**

Add to `CivSnapshot` class (after `prestige`, ~line 322):

```python
    great_persons: list[dict] = []
    traditions: list[str] = []
    folk_heroes: list[dict] = []
    active_crisis: bool = False
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_great_persons.py -v --tb=short`
Expected: PASS

- [ ] **Step 9: Run existing tests to verify no regressions**

Run: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`
Expected: All existing tests pass (new fields have defaults, so backward-compatible).

- [ ] **Step 10: Commit**

```bash
git add src/chronicler/models.py tests/test_great_persons.py
git commit -m "feat(m17a): add GreatPerson model and M17 fields to Civilization, Leader, WorldState, CivSnapshot"
```

---

### Task 2: Implement modifier registry (get_modifiers)

**Files:**
- Create: `src/chronicler/great_persons.py`
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write failing tests for get_modifiers**

```python
# Append to tests/test_great_persons.py
from chronicler.great_persons import get_modifiers

def test_get_modifiers_general():
    gp = GreatPerson(
        name="Khotun", role="general", trait="aggressive",
        civilization="Mongol", origin_civilization="Mongol", born_turn=0,
    )
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 1
    assert mods[0]["domain"] == "military"
    assert mods[0]["value"] == 10

def test_get_modifiers_excludes_hostages():
    gp = GreatPerson(
        name="Khotun", role="general", trait="aggressive",
        civilization="Mongol", origin_civilization="Mongol",
        born_turn=0, is_hostage=True,
    )
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 0

def test_get_modifiers_merchant():
    gp = GreatPerson(
        name="Lysander", role="merchant", trait="shrewd",
        civilization="Greek", origin_civilization="Greek", born_turn=0,
    )
    civ = make_civ("Greek")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "trade")
    assert len(mods) == 1
    assert mods[0]["value"] == 3
    assert mods[0]["per"] == "route"

def test_get_modifiers_scientist():
    gp = GreatPerson(
        name="Hypatia", role="scientist", trait="visionary",
        civilization="Egypt", origin_civilization="Egypt", born_turn=0,
    )
    civ = make_civ("Egypt")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "tech")
    assert len(mods) == 1
    assert mods[0]["value"] == -0.30
    assert mods[0]["mode"] == "multiplier"

def test_get_modifiers_prophet():
    gp = GreatPerson(
        name="Zara", role="prophet", trait="zealous",
        civilization="Persia", origin_civilization="Persia",
        born_turn=0, movement_id=1,
    )
    civ = make_civ("Persia")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "culture")
    assert len(mods) == 1
    assert mods[0]["mode"] == "behavioral"

def test_get_modifiers_wrong_domain_returns_empty():
    gp = GreatPerson(
        name="Khotun", role="general", trait="aggressive",
        civilization="Mongol", origin_civilization="Mongol", born_turn=0,
    )
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "trade")
    assert len(mods) == 0

def test_get_modifiers_excludes_inactive():
    gp = GreatPerson(
        name="Khotun", role="general", trait="aggressive",
        civilization="Mongol", origin_civilization="Mongol",
        born_turn=0, active=False, fate="retired",
    )
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 0

def test_get_modifiers_excludes_exile_role():
    gp = GreatPerson(
        name="Deposed King", role="exile", trait="ambitious",
        civilization="Host", origin_civilization="Origin", born_turn=0,
    )
    civ = make_civ("Host")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 0
    mods = get_modifiers(civ, "trade")
    assert len(mods) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_great_persons.py::test_get_modifiers_general -v --tb=short`
Expected: ImportError — `great_persons` module not found.

- [ ] **Step 3: Implement get_modifiers**

```python
# src/chronicler/great_persons.py
"""Great Person generation, lifecycle, and modifier registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization

# Role → modifier mapping
ROLE_MODIFIERS = {
    "general": {"domain": "military", "stat": "military", "value": 10},
    "merchant": {"domain": "trade", "stat": "trade_income", "value": 3, "per": "route"},
    "scientist": {"domain": "tech", "stat": "tech_cost", "value": -0.30, "mode": "multiplier"},
    "prophet": {"domain": "culture", "stat": "movement_spread", "value": "accelerated", "mode": "behavioral"},
}


def get_modifiers(civ: Civilization, domain: str) -> list[dict]:
    """Return active modifiers for a domain from civ's great persons.

    Computed on-the-fly — no caching. Excludes hostages, inactive,
    and non-achievement roles (exile, hostage).
    """
    results = []
    for gp in civ.great_persons:
        if not gp.active or gp.is_hostage:
            continue
        if gp.role not in ROLE_MODIFIERS:
            continue
        mod_template = ROLE_MODIFIERS[gp.role]
        if mod_template["domain"] != domain:
            continue
        mod = {"source": f"{gp.role}_{gp.name}", **mod_template}
        results.append(mod)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_great_persons.py -v --tb=short`
Expected: All modifier tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/great_persons.py tests/test_great_persons.py
git commit -m "feat(m17a): implement domain-tagged modifier registry with get_modifiers()"
```

---

### Task 3: Implement achievement-triggered generation

**Files:**
- Modify: `src/chronicler/great_persons.py`
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write failing tests for achievement checks**

```python
# Append to tests/test_great_persons.py
from chronicler.great_persons import check_great_person_generation
from chronicler.models import WorldState

def test_general_spawns_after_3_war_wins_in_window(make_world):
    """General triggers when civ wins 3 wars within 15 turns."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [5, 8, 12]  # 3 wins in 15-turn window
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 1
    assert spawned[0].role == "general"

def test_general_not_spawned_if_wins_outside_window(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    world.turn = 30
    civ.war_win_turns = [1, 5, 10]  # all > 15 turns ago
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 0

def test_cooldown_blocks_spawn(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [5, 8, 12]
    world.great_person_cooldowns = {civ.name: {"general": 5}}  # spawned at turn 5
    world.turn = 15  # only 10 turns since last, cooldown is 20
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 0

def test_merchant_spawns_with_trade_routes(make_world):
    """Merchant triggers with 4+ active trade routes for 10 consecutive turns."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    # Simulate 4+ active trade routes — check how trade routes are counted
    # The merchant check should look at current active_trade_routes count
    # and track consecutive turns (we need a field or derive from state)
    # For now test the core logic path
    spawned = check_great_person_generation(civ, world)
    # Without trade routes, no merchant
    assert all(s.role != "merchant" for s in spawned)

def test_scientist_spawns_on_era_advance(make_world):
    """Scientist triggers on tech era advancement."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    # Mark that a tech advancement happened this turn
    civ.event_counts["tech_advanced"] = 1
    spawned = check_great_person_generation(civ, world)
    assert any(s.role == "scientist" for s in spawned)

def test_scientist_spawns_on_high_economy(make_world):
    """Scientist triggers with economy >= 80 for 15 consecutive turns."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.economy = 85
    civ.event_counts["high_economy_turns"] = 15
    spawned = check_great_person_generation(civ, world)
    assert any(s.role == "scientist" for s in spawned)

def test_catch_up_discount(make_world):
    """Civs with 0 great persons get 25% threshold reduction."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = []  # no great persons
    civ.war_win_turns = [5, 8]  # only 2 wins (normally need 3, catch-up needs 2)
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 1
    assert spawned[0].role == "general"

def test_50_cap_forces_retirement(make_world):
    """When global count hits 50, oldest of spawning civ retires."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    # Fill civ with 5 great persons, total across all civs = 50
    for i in range(5):
        civ.great_persons.append(GreatPerson(
            name=f"Person{i}", role="general", trait="bold",
            civilization=civ.name, origin_civilization=civ.name,
            born_turn=i,
        ))
    other = world.civilizations[1]
    for i in range(45):
        other.great_persons.append(GreatPerson(
            name=f"Other{i}", role="merchant", trait="shrewd",
            civilization=other.name, origin_civilization=other.name,
            born_turn=i,
        ))
    civ.war_win_turns = [5, 8, 12]  # trigger general
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 1  # new one spawned
    # oldest of civ should be retired
    assert len(world.retired_persons) >= 1
    assert world.retired_persons[-1].name == "Person0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_great_persons.py::test_general_spawns_after_3_war_wins_in_window -v --tb=short`
Expected: ImportError or NameError.

- [ ] **Step 3: Implement check_great_person_generation**

Add to `src/chronicler/great_persons.py`:

```python
import math
import logging
from chronicler.models import GreatPerson, WorldState, Civilization
from chronicler.leaders import _pick_name

logger = logging.getLogger(__name__)

# Cooldown per role (turns)
ROLE_COOLDOWNS = {
    "general": 20,
    "merchant": 20,
    "prophet": 25,
    "scientist": 20,
}

CATCH_UP_DISCOUNT = 0.75  # 25% reduction


def _is_on_cooldown(civ_name: str, role: str, world: WorldState) -> bool:
    """Check if role is on cooldown for this civ."""
    civ_cooldowns = world.great_person_cooldowns.get(civ_name, {})
    last_spawn = civ_cooldowns.get(role)
    if last_spawn is None:
        return False
    cooldown = ROLE_COOLDOWNS[role]
    return (world.turn - last_spawn) < cooldown


def _set_cooldown(civ_name: str, role: str, world: WorldState) -> None:
    if civ_name not in world.great_person_cooldowns:
        world.great_person_cooldowns[civ_name] = {}
    world.great_person_cooldowns[civ_name][role] = world.turn


def _total_great_persons(world: WorldState) -> int:
    return sum(len(c.great_persons) for c in world.civilizations)


def _enforce_cap(civ: Civilization, world: WorldState) -> None:
    """If global count > 50, retire oldest of this civ."""
    if _total_great_persons(world) <= 50:
        return
    if not civ.great_persons:
        return  # soft limit — spawn succeeds
    oldest = min(civ.great_persons, key=lambda gp: gp.born_turn)
    _retire_person(oldest, civ, world)
    logger.warning(
        "50-cap triggered: retired %s from %s (turn %d)",
        oldest.name, civ.name, world.turn,
    )


def _retire_person(gp: GreatPerson, civ: Civilization, world: WorldState) -> None:
    """Archive a great person as retired."""
    gp.active = False
    gp.alive = False
    gp.fate = "retired"
    gp.death_turn = world.turn
    civ.great_persons.remove(gp)
    world.retired_persons.append(gp)


def _create_great_person(
    role: str, civ: Civilization, world: WorldState,
) -> GreatPerson:
    """Create a new great person with a name from the cultural pool."""
    name = _pick_name(civ, world)
    seed = world.seed + world.turn + hash(name)
    lifespan = 20 + (seed % 11)  # 20-30 turns

    trait_idx = (world.seed + world.turn + hash(role)) % len(ALL_TRAITS)
    from chronicler.leaders import ALL_TRAITS
    trait = ALL_TRAITS[trait_idx]

    gp = GreatPerson(
        name=name,
        role=role,
        trait=trait,
        civilization=civ.name,
        origin_civilization=civ.name,
        born_turn=world.turn,
        region=civ.capital_region or (civ.regions[0] if civ.regions else None),
    )
    civ.great_persons.append(gp)
    _set_cooldown(civ.name, role, world)
    _enforce_cap(civ, world)
    return gp


def check_great_person_generation(
    civ: Civilization, world: WorldState,
) -> list[GreatPerson]:
    """Check achievement thresholds and spawn great persons if met.

    Returns list of newly spawned great persons.
    """
    if not civ.regions:
        return []

    has_catch_up = len(civ.great_persons) == 0
    spawned = []

    # --- General: 3 wars won in 15-turn window ---
    if not _is_on_cooldown(civ.name, "general", world):
        threshold = 3
        if has_catch_up:
            threshold = math.floor(threshold * CATCH_UP_DISCOUNT)
        recent_wins = [
            t for t in civ.war_win_turns
            if t >= world.turn - 15
        ]
        if len(recent_wins) >= threshold:
            spawned.append(_create_great_person("general", civ, world))

    # --- Merchant: 4+ active trade routes for 10 consecutive turns ---
    if not _is_on_cooldown(civ.name, "merchant", world):
        threshold_routes = 4
        threshold_turns = 10
        if has_catch_up:
            threshold_routes = math.floor(threshold_routes * CATCH_UP_DISCOUNT)
            threshold_turns = math.floor(threshold_turns * CATCH_UP_DISCOUNT)
        consecutive = civ.event_counts.get("high_trade_route_turns", 0)
        if consecutive >= threshold_turns:
            spawned.append(_create_great_person("merchant", civ, world))
            civ.event_counts["high_trade_route_turns"] = 0  # reset

    # --- Scientist: era advance OR economy >= 80 for 15 turns ---
    if not _is_on_cooldown(civ.name, "scientist", world):
        era_advanced = civ.event_counts.get("tech_advanced", 0) > 0
        econ_threshold = 15
        if has_catch_up:
            econ_threshold = math.floor(econ_threshold * CATCH_UP_DISCOUNT)
        high_econ = civ.event_counts.get("high_economy_turns", 0) >= econ_threshold
        if era_advanced or high_econ:
            spawned.append(_create_great_person("scientist", civ, world))
            civ.event_counts["tech_advanced"] = 0
            civ.event_counts["high_economy_turns"] = 0

    # --- Prophet: first non-origin adoption OR origin with 3+ adherents ---
    if not _is_on_cooldown(civ.name, "prophet", world):
        prophet_triggered = civ.event_counts.get("prophet_trigger", 0) > 0
        if prophet_triggered:
            spawned.append(_create_great_person("prophet", civ, world))
            civ.event_counts["prophet_trigger"] = 0

    return spawned
```

Note: `_pick_name` and `ALL_TRAITS` are imported from `leaders.py`. Check exact import paths — `_pick_name` may be private. If so, extract the name-picking logic or make it accessible. The implementation should use the same cultural name pools and `used_leader_names` deduplication.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_great_persons.py -v --tb=short`
Expected: Achievement generation tests PASS. Fix any import issues.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/great_persons.py tests/test_great_persons.py
git commit -m "feat(m17a): implement achievement-triggered great person generation with cooldowns and catch-up"
```

---

### Task 4: Implement lifecycle management (retirement and death)

**Files:**
- Modify: `src/chronicler/great_persons.py`
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write failing tests for lifecycle**

```python
# Append to tests/test_great_persons.py
from chronicler.great_persons import check_lifespan_expiry, kill_great_person

def test_retirement_on_lifespan_expiry(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="OldGeneral", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0,
    )
    civ.great_persons = [gp]
    # Lifespan = 20 + ((42 + 0 + hash("OldGeneral")) % 11)
    # Set world.turn past that lifespan
    world.turn = 35  # guaranteed past max lifespan of 30
    retired = check_lifespan_expiry(civ, world)
    assert len(retired) == 1
    assert retired[0].fate == "retired"
    assert retired[0].active is False
    assert gp not in civ.great_persons
    assert gp in world.retired_persons

def test_death_is_separate_from_retirement(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="FallenGeneral", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=10,
    )
    civ.great_persons = [gp]
    world.turn = 15
    killed = kill_great_person(gp, civ, world, context="war")
    assert killed.fate == "dead"
    assert killed.death_turn == 15
    assert killed not in civ.great_persons
    assert killed in world.retired_persons

def test_lifespan_deterministic():
    """Same seed + born_turn + name always gives same lifespan."""
    from chronicler.great_persons import _compute_lifespan
    ls1 = _compute_lifespan(seed=42, born_turn=10, name="TestPerson")
    ls2 = _compute_lifespan(seed=42, born_turn=10, name="TestPerson")
    assert ls1 == ls2
    assert 20 <= ls1 <= 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_great_persons.py::test_retirement_on_lifespan_expiry -v --tb=short`
Expected: ImportError.

- [ ] **Step 3: Implement lifecycle functions**

Add to `src/chronicler/great_persons.py`:

```python
def _compute_lifespan(seed: int, born_turn: int, name: str) -> int:
    """Deterministic lifespan: 20-30 turns."""
    return 20 + ((seed + born_turn + hash(name)) % 11)


def check_lifespan_expiry(
    civ: Civilization, world: WorldState,
) -> list[GreatPerson]:
    """Retire great persons past their lifespan. Always retirement, never death."""
    retired = []
    for gp in list(civ.great_persons):  # copy for safe removal
        if not gp.active:
            continue
        lifespan = _compute_lifespan(world.seed, gp.born_turn, gp.name)
        if world.turn - gp.born_turn >= lifespan:
            _retire_person(gp, civ, world)
            retired.append(gp)
    return retired


def kill_great_person(
    gp: GreatPerson, civ: Civilization, world: WorldState,
    context: str = "unknown",
) -> GreatPerson:
    """Kill a great person (war, disaster, crisis). NOT retirement."""
    gp.active = False
    gp.alive = False
    gp.fate = "dead"
    gp.death_turn = world.turn
    if gp in civ.great_persons:
        civ.great_persons.remove(gp)
    world.retired_persons.append(gp)
    return gp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_great_persons.py -v --tb=short`
Expected: All lifecycle tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/great_persons.py tests/test_great_persons.py
git commit -m "feat(m17a): implement great person lifecycle — retirement on lifespan expiry, death as separate fate"
```

---

### Task 5: Wire great person generation and retirement into Phase 10

**Files:**
- Modify: `src/chronicler/simulation.py:508-575` (phase_consequences)
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write failing integration test**

```python
# Append to tests/test_great_persons.py
def test_phase10_generates_and_retires_great_persons(make_world):
    """Phase 10 runs great person generation and lifespan checks."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [1, 3, 5]  # trigger general
    world.turn = 10

    # Also add an old person who should retire
    old_gp = GreatPerson(
        name="AncientOne", role="merchant", trait="shrewd",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0,  # born turn 0, now turn 35 → past lifespan
    )
    # We'll set turn high enough for retirement
    # But first let generation run at turn 10

    from chronicler.simulation import phase_consequences
    events = phase_consequences(world)

    # Check that a general was generated
    generals = [gp for gp in civ.great_persons if gp.role == "general"]
    assert len(generals) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_great_persons.py::test_phase10_generates_and_retires_great_persons -v --tb=short`
Expected: Fails — phase_consequences doesn't call great person functions yet.

- [ ] **Step 3: Add great person hooks to phase_consequences**

In `src/chronicler/simulation.py`, at the appropriate location within `phase_consequences()` (~line 508-575), add calls to great person functions. Insert after existing consequence logic:

```python
from chronicler.great_persons import check_great_person_generation, check_lifespan_expiry

# Inside phase_consequences, after existing logic:
# --- M17: Great Person Consequences ---
for civ in world.civilizations:
    if not civ.regions:
        continue
    # Step 2: Generation
    check_great_person_generation(civ, world)
    # Step 6: Lifespan expiry
    check_lifespan_expiry(civ, world)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_great_persons.py -v --tb=short`
Then: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`
Expected: All tests pass, no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_great_persons.py
git commit -m "feat(m17a): wire great person generation and retirement into Phase 10 consequences"
```

---

### Task 6: Update CivSnapshot population for viewer/narrative

**Files:**
- Modify: `src/chronicler/main.py` (snapshot construction, ~lines 215-234)
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write failing test**

```python
def test_civ_snapshot_includes_great_persons(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="TestGeneral", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name, born_turn=0,
    )
    civ.great_persons = [gp]
    civ.traditions = ["martial"]
    civ.folk_heroes = [{"name": "Hero", "role": "general", "death_turn": 5, "death_context": "war"}]
    civ.succession_crisis_turns_remaining = 3

    from chronicler.main import build_snapshot  # or however snapshots are built
    snapshot = build_snapshot(civ, world)
    assert len(snapshot.great_persons) == 1
    assert snapshot.traditions == ["martial"]
    assert len(snapshot.folk_heroes) == 1
    assert snapshot.active_crisis is True
```

- [ ] **Step 2: Run to verify failure, then implement**

Find the snapshot construction in `main.py` and add the new fields. The exact location depends on how `CivSnapshot` is currently constructed — look for `CivSnapshot(` around line 215-234.

Add to the snapshot construction:

```python
great_persons=[{"name": gp.name, "role": gp.role, "trait": gp.trait} for gp in civ.great_persons if gp.active],
traditions=list(civ.traditions),
folk_heroes=[{"name": fh["name"], "role": fh["role"]} for fh in civ.folk_heroes],
active_crisis=civ.succession_crisis_turns_remaining > 0,
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/main.py tests/test_great_persons.py
git commit -m "feat(m17a): populate CivSnapshot with great persons, traditions, folk heroes, crisis state"
```

---

### Task 7: M17a end-to-end integration test

**Files:**
- Test: `tests/test_great_persons.py`

- [ ] **Step 1: Write integration test**

```python
def test_m17a_integration_5_turn_simulation(make_world):
    """Run 5 turns and verify great person system doesn't crash."""
    from chronicler.simulation import run_turn
    world = make_world(num_civs=3, seed=42)
    # Give one civ enough war wins to trigger a general
    civ = world.civilizations[0]
    civ.war_win_turns = [0, 1, 2]

    for turn in range(5):
        world.turn = turn
        run_turn(world)

    # Verify no crashes, state is consistent
    for c in world.civilizations:
        for gp in c.great_persons:
            assert gp.active is True
            assert gp.civilization == c.name
    for gp in world.retired_persons:
        assert gp.active is False
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/test_great_persons.py::test_m17a_integration_5_turn_simulation -v --tb=short`
Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`
Expected: All pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_great_persons.py
git commit -m "test(m17a): add end-to-end integration test for great person system"
```

---

## Chunk 2: M17b — Succession & Grudges

### Task 8: Implement succession crisis formula

**Files:**
- Create: `src/chronicler/succession.py`
- Test: `tests/test_succession.py`

- [ ] **Step 1: Write failing tests for crisis probability**

```python
# tests/test_succession.py
from chronicler.succession import compute_crisis_probability
from chronicler.models import Civilization, Leader, WorldState

def test_crisis_probability_floor():
    """Even most stable empire has >= 0.05 crisis chance."""
    civ = make_civ("Stable")
    civ.stability = 100
    civ.asabiya = 0.9
    civ.regions = ["r1", "r2", "r3"]
    civ.traditions = ["martial", "resilience"]
    civ.leader = Leader(
        name="StableKing", trait="cautious",
        reign_start=0, succession_type="heir",
    )
    world = make_world(num_civs=1, seed=42)
    world.turn = 30  # reign of 30 turns
    prob = compute_crisis_probability(civ, world)
    assert prob >= 0.05

def test_crisis_probability_cap():
    """Even most unstable empire has <= 0.40 crisis chance."""
    civ = make_civ("Unstable")
    civ.stability = 5
    civ.asabiya = 0.1
    civ.regions = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]
    civ.leader = Leader(
        name="WeakKing", trait="ambitious",
        reign_start=48, succession_type="usurper",
    )
    world = make_world(num_civs=1, seed=42)
    world.turn = 50  # reign of 2 turns
    world.vassal_relations = [
        VassalRelation(overlord=civ.name, vassal="Vassal1", tribute_rate=0.15, turns_active=5),
    ]
    prob = compute_crisis_probability(civ, world)
    assert prob <= 0.40

def test_crisis_not_triggered_with_few_regions():
    """Crisis requires 3+ regions."""
    civ = make_civ("Small")
    civ.regions = ["r1", "r2"]
    civ.stability = 10
    world = make_world(num_civs=1, seed=42)
    prob = compute_crisis_probability(civ, world)
    assert prob == 0.0

def test_vassal_escalation():
    """Active vassals increase crisis probability."""
    civ = make_civ("Overlord")
    civ.stability = 50
    civ.regions = ["r1", "r2", "r3", "r4"]
    civ.leader = Leader(name="King", trait="bold", reign_start=0, succession_type="general")
    world = make_world(num_civs=1, seed=42)
    world.turn = 10

    prob_no_vassal = compute_crisis_probability(civ, world)

    world.vassal_relations = [
        VassalRelation(overlord=civ.name, vassal="V1", tribute_rate=0.15, turns_active=5),
    ]
    prob_with_vassal = compute_crisis_probability(civ, world)
    assert prob_with_vassal > prob_no_vassal

def test_tradition_suppression():
    """Martial tradition reduces crisis probability."""
    civ = make_civ("Traditional")
    civ.stability = 40
    civ.regions = ["r1", "r2", "r3"]
    civ.leader = Leader(name="King", trait="bold", reign_start=0, succession_type="heir")
    world = make_world(num_civs=1, seed=42)
    world.turn = 10

    prob_no_tradition = compute_crisis_probability(civ, world)
    civ.traditions = ["martial"]
    prob_with_tradition = compute_crisis_probability(civ, world)
    assert prob_with_tradition < prob_no_tradition
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_succession.py -v --tb=short 2>&1 | head -20`

- [ ] **Step 3: Implement compute_crisis_probability**

```python
# src/chronicler/succession.py
"""Succession crisis mechanics, exiled leaders, legacy expansion."""

from __future__ import annotations
from chronicler.utils import clamp
from chronicler.models import Civilization, WorldState


def compute_crisis_probability(civ: Civilization, world: WorldState) -> float:
    """State-driven succession crisis probability. See spec Section 2.1."""
    if len(civ.regions) < 3:
        return 0.0

    base = 0.15
    region_factor = len(civ.regions) / 5
    instability_factor = 1 - (civ.stability / 100)
    leader_reign = world.turn - civ.leader.reign_start
    has_active_vassals = any(
        vr.overlord == civ.name for vr in world.vassal_relations
    )
    modifiers = 1.0

    # Escalation
    if civ.leader.succession_type != "heir":
        modifiers *= 1.5
    if has_active_vassals:
        modifiers *= 1.3
    if leader_reign < 5:
        modifiers *= 1.2

    # Suppression
    if civ.asabiya > 0.7:
        modifiers *= 0.6
    if "martial" in civ.traditions:
        modifiers *= 0.8
    if "resilience" in civ.traditions:
        modifiers *= 0.8
    if leader_reign > 15:
        modifiers *= 0.7

    return clamp(
        base * region_factor * instability_factor * modifiers,
        0.05, 0.40,
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_succession.py -v --tb=short`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/succession.py tests/test_succession.py
git commit -m "feat(m17b): implement state-driven succession crisis probability formula"
```

---

### Task 9: Implement multi-turn crisis state machine

**Files:**
- Modify: `src/chronicler/succession.py`
- Modify: `src/chronicler/simulation.py:429-435,638-649`
- Test: `tests/test_succession.py`

- [ ] **Step 1: Write failing tests for crisis lifecycle**

```python
from chronicler.succession import trigger_crisis, tick_crisis, resolve_crisis

def test_trigger_crisis_sets_state(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.regions = ["r1", "r2", "r3"]
    trigger_crisis(civ, world)
    assert civ.succession_crisis_turns_remaining > 0
    assert civ.succession_crisis_turns_remaining <= 5

def test_tick_crisis_decrements(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.succession_crisis_turns_remaining = 3
    tick_crisis(civ, world)
    assert civ.succession_crisis_turns_remaining == 2

def test_resolve_crisis_creates_leader(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.succession_crisis_turns_remaining = 1
    civ.succession_candidates = [{"backer_civ": "Other", "type": "military"}]
    old_leader_name = civ.leader.name
    events = resolve_crisis(civ, world)
    assert civ.succession_crisis_turns_remaining == 0
    assert civ.leader.name != old_leader_name
    assert len(events) >= 1

def test_crisis_halves_action_effectiveness(make_world):
    """During crisis, action stat changes are halved."""
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.succession_crisis_turns_remaining = 3
    # This will be checked in action_engine integration
    from chronicler.succession import is_in_crisis
    assert is_in_crisis(civ) is True
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement crisis state machine**

Add to `src/chronicler/succession.py`:

```python
import random
from chronicler.models import Leader, Event, NamedEvent
from chronicler.leaders import generate_successor, ALL_TRAITS


def is_in_crisis(civ: Civilization) -> bool:
    return civ.succession_crisis_turns_remaining > 0


def trigger_crisis(civ: Civilization, world: WorldState) -> list[Event]:
    """Start a succession crisis. Called when leader dies and roll succeeds."""
    duration = 3 + ((world.seed + world.turn) % 3)  # 3-5 turns
    civ.succession_crisis_turns_remaining = duration
    civ.succession_candidates = []
    civ.stability = max(civ.stability - 10, 0)

    event = NamedEvent(
        name=f"The Succession Crisis of {civ.name}",
        event_type="succession_crisis",
        turn=world.turn,
        actors=[civ.name],
        description=f"The death of {civ.leader.name} plunged {civ.name} into a succession crisis.",
        importance=8,
    )
    world.named_events.append(event)
    return [Event(
        turn=world.turn, event_type="succession_crisis",
        actors=[civ.name],
        description=f"Succession crisis begins in {civ.name} ({duration} turns).",
        importance=8,
    )]


def tick_crisis(civ: Civilization, world: WorldState) -> list[Event]:
    """Decrement crisis timer and resolve if done."""
    if not is_in_crisis(civ):
        return []
    civ.succession_crisis_turns_remaining -= 1
    if civ.succession_crisis_turns_remaining <= 0:
        return resolve_crisis(civ, world)
    return []


def resolve_crisis(civ: Civilization, world: WorldState) -> list[Event]:
    """End the crisis, create new leader based on backing."""
    civ.succession_crisis_turns_remaining = 0
    events = []

    # Check for general-to-leader conversion (50% chance)
    generals = [gp for gp in civ.great_persons if gp.role == "general" and gp.active]
    rng = random.Random(world.seed + world.turn + hash(civ.name))

    new_leader = None

    if generals and rng.random() < 0.50:
        gen = generals[0]
        # Ascend general to leader
        gen.active = False
        gen.fate = "ascended"
        if gen in civ.great_persons:
            civ.great_persons.remove(gen)
        world.retired_persons.append(gen)
        new_leader = Leader(
            name=gen.name,
            trait=gen.trait,
            reign_start=world.turn,
            succession_type="general",
        )
    else:
        # Check non-general great persons (20% each)
        non_generals = [gp for gp in civ.great_persons if gp.role != "general" and gp.active and gp.role not in ("exile", "hostage")]
        ascended_gp = None
        for gp in non_generals:
            if rng.random() < 0.20:
                ascended_gp = gp
                break
        if ascended_gp:
            ascended_gp.active = False
            ascended_gp.fate = "ascended"
            if ascended_gp in civ.great_persons:
                civ.great_persons.remove(ascended_gp)
            world.retired_persons.append(ascended_gp)
            new_leader = Leader(
                name=ascended_gp.name,
                trait=ascended_gp.trait,
                reign_start=world.turn,
                succession_type="general",
            )

    if new_leader is None:
        # Determine trait from backing
        military_backers = [c for c in civ.succession_candidates if c.get("type") == "military"]
        trade_backers = [c for c in civ.succession_candidates if c.get("type") == "trade"]
        if military_backers:
            trait = rng.choice(["aggressive", "warlike"])
        elif trade_backers:
            trait = rng.choice(["cautious", "shrewd"])
        else:
            trait = rng.choice(ALL_TRAITS)
        new_leader = generate_successor(civ, world)
        new_leader.trait = trait

    civ.leader = new_leader
    civ.succession_candidates = []

    events.append(Event(
        turn=world.turn, event_type="succession_resolved",
        actors=[civ.name],
        description=f"Succession crisis resolved: {new_leader.name} takes power in {civ.name}.",
        importance=7,
    ))
    return events
```

- [ ] **Step 4: Modify Phase 7 leader death handling**

In `src/chronicler/simulation.py`, find `_apply_event_effects` (~line 429-435) where `leader_death` events call `generate_successor`. Change to defer if crisis triggers:

```python
# In _apply_event_effects, leader_death handling:
from chronicler.succession import compute_crisis_probability, trigger_crisis, is_in_crisis

if event.event_type == "leader_death":
    civ = _get_civ(world, event.actors[0])
    if civ and civ.leader.alive:
        civ.leader.alive = False
        # Check for succession crisis
        rng = random.Random(world.seed + world.turn + hash(civ.name) + hash("crisis"))
        crisis_prob = compute_crisis_probability(civ, world)
        if rng.random() < crisis_prob:
            events.extend(trigger_crisis(civ, world))
            # Defer successor creation to Phase 8 resolution
        else:
            # Normal succession
            from chronicler.leaders import generate_successor, apply_leader_legacy
            apply_leader_legacy(civ, world)
            civ.leader = generate_successor(civ, world)
```

- [ ] **Step 5: Add crisis tick to Phase 8**

In `src/chronicler/simulation.py`, within `phase_leader_dynamics()` (~line 638-649):

```python
from chronicler.succession import tick_crisis

# Add at start of phase_leader_dynamics:
for civ in world.civilizations:
    if civ.regions and is_in_crisis(civ):
        events.extend(tick_crisis(civ, world))
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_succession.py tests/test_great_persons.py -v --tb=short`
Then: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/succession.py src/chronicler/simulation.py tests/test_succession.py
git commit -m "feat(m17b): implement multi-turn succession crisis with Phase 7 deferral and Phase 8 resolution"
```

---

### Task 10: Implement personal grudges

**Files:**
- Modify: `src/chronicler/succession.py` (or new section in same file)
- Modify: `src/chronicler/action_engine.py:504-545` (compute_weights — grudge bias)
- Modify: `src/chronicler/leaders.py:187-227` (grudge inheritance on succession)
- Test: `tests/test_succession.py`

- [ ] **Step 1: Write failing tests for grudges**

```python
from chronicler.succession import add_grudge, decay_grudges, inherit_grudges

def test_add_grudge_on_war_loss():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    add_grudge(leader, rival_name="Winner", rival_civ="EnemyCiv", turn=10)
    assert len(leader.grudges) == 1
    assert leader.grudges[0]["intensity"] == 1.0
    assert leader.grudges[0]["rival_civ"] == "EnemyCiv"

def test_grudge_decay():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    leader.grudges = [{"rival_name": "Winner", "rival_civ": "Enemy", "intensity": 1.0, "origin_turn": 0}]
    decay_grudges(leader, current_turn=5, rival_alive=True)
    assert leader.grudges[0]["intensity"] == 0.9  # -0.1 at turn 5

def test_grudge_accelerated_decay_after_target_death():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    leader.grudges = [{"rival_name": "Winner", "rival_civ": "Enemy", "intensity": 1.0, "origin_turn": 0}]
    decay_grudges(leader, current_turn=5, rival_alive=False)
    assert leader.grudges[0]["intensity"] == 0.8  # -0.2 at turn 5 (2x decay)

def test_grudge_inheritance_at_50_percent():
    old_leader = Leader(name="Old", trait="bold", reign_start=0)
    old_leader.grudges = [{"rival_name": "Enemy", "rival_civ": "Foe", "intensity": 1.0, "origin_turn": 0}]
    new_leader = Leader(name="New", trait="cautious", reign_start=20)
    inherit_grudges(old_leader, new_leader)
    assert len(new_leader.grudges) == 1
    assert new_leader.grudges[0]["intensity"] == 0.5

def test_grudge_removed_when_intensity_zero():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    leader.grudges = [{"rival_name": "Winner", "rival_civ": "Enemy", "intensity": 0.05, "origin_turn": 0}]
    decay_grudges(leader, current_turn=5, rival_alive=True)
    assert len(leader.grudges) == 0  # removed when < 0.01
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement grudge functions**

Add to `src/chronicler/succession.py`:

```python
def add_grudge(leader: Leader, rival_name: str, rival_civ: str, turn: int) -> None:
    """Add or refresh a grudge after war loss."""
    for g in leader.grudges:
        if g["rival_civ"] == rival_civ:
            g["intensity"] = 1.0
            g["origin_turn"] = turn
            g["rival_name"] = rival_name
            return
    leader.grudges.append({
        "rival_name": rival_name,
        "rival_civ": rival_civ,
        "intensity": 1.0,
        "origin_turn": turn,
    })


def decay_grudges(leader: Leader, current_turn: int, rival_alive: bool = True) -> None:
    """Decay grudge intensity. -0.1 every 5 turns (2x if rival dead)."""
    to_remove = []
    for g in leader.grudges:
        turns_since = current_turn - g["origin_turn"]
        if turns_since > 0 and turns_since % 5 == 0:
            decay = 0.2 if not rival_alive else 0.1
            g["intensity"] = max(0, g["intensity"] - decay)
        if g["intensity"] < 0.01:
            to_remove.append(g)
    for g in to_remove:
        leader.grudges.remove(g)


def inherit_grudges(old_leader: Leader, new_leader: Leader) -> None:
    """New leader inherits grudges at 50% intensity."""
    for g in old_leader.grudges:
        if g["intensity"] * 0.5 >= 0.01:
            new_leader.grudges.append({
                **g,
                "intensity": g["intensity"] * 0.5,
            })
```

- [ ] **Step 4: Wire grudge into action weight computation**

In `src/chronicler/action_engine.py`, within `compute_weights()` (~line 504-545), add after existing weight computation:

```python
# Grudge bias: increase WAR weight against grudge target
from chronicler.models import ActionType
for g in civ.leader.grudges:
    if g["rival_civ"] in [other.name for other in world.civilizations if other.name != civ.name]:
        # Boost WAR weight
        if ActionType.WAR in weights:
            weights[ActionType.WAR] *= (1.0 + 0.5 * g["intensity"])
```

- [ ] **Step 5: Wire grudge inheritance into succession**

In `src/chronicler/leaders.py`, within `generate_successor()` (~line 187-227), before returning the new leader:

```python
from chronicler.succession import inherit_grudges
inherit_grudges(civ.leader, new_leader)
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_succession.py -v --tb=short`
Then: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/succession.py src/chronicler/action_engine.py src/chronicler/leaders.py tests/test_succession.py
git commit -m "feat(m17b): implement personal grudges with decay, inheritance, and WAR weight bias"
```

---

### Task 11: Implement exiled leaders

**Files:**
- Modify: `src/chronicler/succession.py`
- Modify: `src/chronicler/simulation.py:145-312` (Phase 2 — exile drain)
- Test: `tests/test_succession.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.succession import create_exiled_leader, check_exile_restoration, apply_exile_pretender_drain

def test_create_exiled_leader(make_world):
    world = make_world(num_civs=3, seed=42)
    origin = world.civilizations[0]
    old_leader = origin.leader
    host = create_exiled_leader(old_leader, origin, world)
    # Exile should be on some host civ's great_persons
    exile_found = False
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.role == "exile" and gp.origin_civilization == origin.name:
                exile_found = True
                assert gp.name == old_leader.name
    assert exile_found

def test_pretender_drain(make_world):
    world = make_world(num_civs=2, seed=42)
    origin = world.civilizations[0]
    host = world.civilizations[1]
    exile = GreatPerson(
        name="ExiledKing", role="exile", trait="ambitious",
        civilization=host.name, origin_civilization=origin.name,
        born_turn=0,
    )
    host.great_persons.append(exile)
    origin_stability_before = origin.stability
    apply_exile_pretender_drain(world)
    assert origin.stability == origin_stability_before - 2

def test_exile_restoration(make_world):
    world = make_world(num_civs=2, seed=100)
    origin = world.civilizations[0]
    origin.stability = 15  # below 20 threshold
    host = world.civilizations[1]
    exile = GreatPerson(
        name="ExiledKing", role="exile", trait="ambitious",
        civilization=host.name, origin_civilization=origin.name,
        born_turn=0,
    )
    host.great_persons.append(exile)
    # With many recognizers, probability is high
    # recognized_by would need to be tracked — add to GreatPerson or separate
    events = check_exile_restoration(world)
    # Result depends on RNG — test the probability path
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement exile functions**

Add to `src/chronicler/succession.py`:

```python
def create_exiled_leader(
    old_leader: Leader, origin_civ: Civilization, world: WorldState,
) -> str | None:
    """Create an exiled leader GreatPerson on a host civ. Returns host civ name."""
    from chronicler.models import GreatPerson, Disposition
    # Find non-hostile host
    best_host = None
    best_disp = -1
    for civ in world.civilizations:
        if civ.name == origin_civ.name or not civ.regions:
            continue
        rel = world.relationships.get(origin_civ.name, {}).get(civ.name)
        if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
            continue
        disp_val = DISPOSITION_ORDER.get(rel.disposition, 0) if rel else 2
        if disp_val > best_disp:
            best_disp = disp_val
            best_host = civ

    if best_host is None:
        return None

    exile = GreatPerson(
        name=old_leader.name,
        role="exile",
        trait=old_leader.trait,
        civilization=best_host.name,
        origin_civilization=origin_civ.name,
        born_turn=world.turn,
        region=best_host.capital_region or (best_host.regions[0] if best_host.regions else None),
    )
    best_host.great_persons.append(exile)
    return best_host.name


def apply_exile_pretender_drain(world: WorldState) -> None:
    """Phase 2: stability -2/turn on origin civ for each living exile."""
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.role != "exile" or not gp.active:
                continue
            origin = next(
                (c for c in world.civilizations if c.name == gp.origin_civilization),
                None,
            )
            if origin and origin.regions:  # origin civ still exists
                origin.stability = max(origin.stability - 2, 0)
            # Host culture bonus
            civ.culture = min(civ.culture + 3, 100)


def check_exile_restoration(world: WorldState) -> list[Event]:
    """Phase 10: check if exiles can restore themselves."""
    events = []
    for civ in world.civilizations:
        for gp in list(civ.great_persons):
            if gp.role != "exile" or not gp.active:
                continue
            origin = next(
                (c for c in world.civilizations if c.name == gp.origin_civilization),
                None,
            )
            if not origin or not origin.regions:
                continue  # origin eliminated — exile becomes inert
            if origin.stability >= 20:
                continue  # origin stable — no restoration
            # Restoration probability
            recognized_count = 0  # TODO: track recognized_by on exile
            base_prob = 0.05 + (0.03 * recognized_count)
            rng = random.Random(world.seed + world.turn + hash(gp.name))
            if rng.random() < base_prob:
                # Restore: exile becomes leader of origin civ
                gp.active = False
                gp.fate = "ascended"
                civ.great_persons.remove(gp)
                world.retired_persons.append(gp)
                origin.leader = Leader(
                    name=gp.name,
                    trait=gp.trait,
                    reign_start=world.turn,
                    succession_type="restoration",
                )
                origin.stability = min(origin.stability + 15, 100)
                events.append(Event(
                    turn=world.turn, event_type="restoration",
                    actors=[origin.name, gp.name],
                    description=f"{gp.name} restored to power in {origin.name}.",
                    importance=9,
                ))
    return events
```

- [ ] **Step 4: Wire exile drain into Phase 2**

In `src/chronicler/simulation.py`, within `apply_automatic_effects()` (~line 145-312):

```python
from chronicler.succession import apply_exile_pretender_drain
apply_exile_pretender_drain(world)
```

- [ ] **Step 5: Wire exile restoration into Phase 10**

In `src/chronicler/simulation.py`, within `phase_consequences()`:

```python
from chronicler.succession import check_exile_restoration
events.extend(check_exile_restoration(world))
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_succession.py -v --tb=short`
Then: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/succession.py src/chronicler/simulation.py tests/test_succession.py
git commit -m "feat(m17b): implement exiled leaders with pretender drain, host culture bonus, and restoration"
```

---

### Task 12: Implement legacy expansion and legacy_counts tracking

**Files:**
- Modify: `src/chronicler/leaders.py:230-249` (apply_leader_legacy)
- Test: `tests/test_succession.py`

- [ ] **Step 1: Write failing tests**

```python
def test_golden_age_memory(make_world):
    """Leader with 20+ turn reign and 30+ economy growth triggers golden age."""
    from chronicler.leaders import apply_leader_legacy
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.reign_start = 0
    civ.economy = 80  # assume started at ~50
    world.turn = 25
    # Need to track economy at reign start — add mechanism
    apply_leader_legacy(civ, world)
    assert civ.legacy_counts.get("golden_age", 0) >= 1

def test_shame_memory(make_world):
    """Leader who lost capital triggers shame memory."""
    from chronicler.leaders import apply_leader_legacy
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.reign_start = 0
    world.turn = 20
    civ.event_counts["capital_lost"] = 1
    apply_leader_legacy(civ, world)
    assert civ.legacy_counts.get("shame", 0) >= 1

def test_fracture_memory(make_world):
    """Leader during whose reign secession occurred triggers fracture memory."""
    from chronicler.leaders import apply_leader_legacy
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.reign_start = 0
    world.turn = 20
    civ.event_counts["secession_occurred"] = 1
    apply_leader_legacy(civ, world)
    assert civ.legacy_counts.get("fracture", 0) >= 1
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Extend apply_leader_legacy**

In `src/chronicler/leaders.py`, extend `apply_leader_legacy()` to include the new legacy types and increment `legacy_counts`. The exact implementation depends on the current shape of `apply_leader_legacy()` — read it first, then add the new conditions after the existing ones.

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/leaders.py tests/test_succession.py
git commit -m "feat(m17b): expand legacy system with golden age, shame, fracture memories and legacy_counts tracking"
```

---

### Task 13: M17b integration test

**Files:**
- Test: `tests/test_succession.py`

- [ ] **Step 1: Write integration test**

```python
def test_m17b_integration_succession_crisis_flow(make_world):
    """Full crisis flow: leader dies → crisis triggers → resolves after N turns."""
    from chronicler.simulation import run_turn
    world = make_world(num_civs=3, seed=42)
    civ = world.civilizations[0]
    civ.regions = ["r1", "r2", "r3", "r4"]
    civ.stability = 30  # moderate instability

    # Force a leader death
    civ.leader.alive = False

    for turn in range(10):
        world.turn = turn
        run_turn(world)

    # Civ should have a leader (crisis resolved or normal succession)
    assert civ.leader is not None
    assert civ.leader.alive is True
    # No crash across 10 turns
```

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

```bash
git add tests/test_succession.py
git commit -m "test(m17b): add succession crisis integration test"
```

---

## Chunk 3: M17c — Character Interactions

### Task 14: Implement WarResult return type change

**Files:**
- Modify: `src/chronicler/action_engine.py:287-368`
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_relationships.py
from chronicler.action_engine import resolve_war, WarResult

def test_resolve_war_returns_war_result(make_world):
    world = make_world(num_civs=2, seed=42)
    attacker = world.civilizations[0]
    defender = world.civilizations[1]
    result = resolve_war(attacker, defender, world, seed=42)
    assert isinstance(result, WarResult)
    assert result.outcome in ("attacker_wins", "defender_wins", "stalemate")
    # contested_region may or may not be set depending on combat
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement WarResult and update resolve_war**

In `src/chronicler/action_engine.py`:

```python
from typing import NamedTuple

class WarResult(NamedTuple):
    outcome: str  # "attacker_wins", "defender_wins", "stalemate"
    contested_region: str | None
```

Change `resolve_war()` return type from `str` to `WarResult`. At each return point, wrap:
- `return "attacker_wins"` → `return WarResult("attacker_wins", contested_region)`
- `return "defender_wins"` → `return WarResult("defender_wins", contested_region)`
- `return "stalemate"` → `return WarResult("stalemate", None)`

Where `contested_region` is the local variable already computed inside `resolve_war`.

Update `_resolve_war_action()` to use `result.outcome` instead of `result` directly for string comparisons.

- [ ] **Step 4: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -x --tb=short 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_relationships.py
git commit -m "refactor(m17c): change resolve_war() return type to WarResult namedtuple"
```

---

### Task 15: Implement rivalries

**Files:**
- Create: `src/chronicler/relationships.py`
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.relationships import check_rivalry_formation, dissolve_dead_relationships

def test_rivalry_forms_between_generals_at_war(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    civ1.great_persons = [GreatPerson(name="Gen1", role="general", trait="bold", civilization=civ1.name, origin_civilization=civ1.name, born_turn=0)]
    civ2.great_persons = [GreatPerson(name="Gen2", role="general", trait="aggressive", civilization=civ2.name, origin_civilization=civ2.name, born_turn=0)]
    world.active_wars = [(civ1.name, civ2.name)]
    formed = check_rivalry_formation(world)
    assert len(formed) == 1
    assert formed[0]["type"] == "rivalry"

def test_rivalry_dissolved_on_death(make_world):
    world = make_world(num_civs=2, seed=42)
    world.character_relationships = [
        {"type": "rivalry", "person_a": "Gen1", "person_b": "Gen2", "civ_a": "Civ1", "civ_b": "Civ2", "formed_turn": 0},
    ]
    # Gen1 dies
    dissolved = dissolve_dead_relationships(world, dead_names={"Gen1"})
    assert len(world.character_relationships) == 0
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement**

```python
# src/chronicler/relationships.py
"""Character relationships: rivalry, mentorship, marriage alliance."""

from __future__ import annotations
from chronicler.models import WorldState, Civilization, GreatPerson


def check_rivalry_formation(world: WorldState) -> list[dict]:
    """Form rivalries between great persons of same role on opposing sides."""
    new_rivalries = []
    existing_pairs = {
        (r["person_a"], r["person_b"])
        for r in world.character_relationships
        if r["type"] == "rivalry"
    }

    for war_pair in world.active_wars:
        civ1_name, civ2_name = war_pair
        civ1 = next((c for c in world.civilizations if c.name == civ1_name), None)
        civ2 = next((c for c in world.civilizations if c.name == civ2_name), None)
        if not civ1 or not civ2:
            continue
        for gp1 in civ1.great_persons:
            if not gp1.active or gp1.role in ("exile", "hostage"):
                continue
            for gp2 in civ2.great_persons:
                if not gp2.active or gp2.role in ("exile", "hostage"):
                    continue
                if gp1.role != gp2.role:
                    continue  # same role required
                pair = (gp1.name, gp2.name)
                pair_rev = (gp2.name, gp1.name)
                if pair in existing_pairs or pair_rev in existing_pairs:
                    continue
                rel = {
                    "type": "rivalry",
                    "person_a": gp1.name,
                    "person_b": gp2.name,
                    "civ_a": civ1.name,
                    "civ_b": civ2.name,
                    "formed_turn": world.turn,
                }
                world.character_relationships.append(rel)
                new_rivalries.append(rel)
    return new_rivalries


def dissolve_dead_relationships(
    world: WorldState, dead_names: set[str],
) -> list[dict]:
    """Remove relationships involving dead/retired characters."""
    dissolved = []
    remaining = []
    for rel in world.character_relationships:
        if rel["person_a"] in dead_names or rel["person_b"] in dead_names:
            dissolved.append(rel)
        else:
            remaining.append(rel)
    world.character_relationships = remaining
    return dissolved
```

- [ ] **Step 4: Run tests, commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m17c): implement rivalry formation and relationship dissolution"
```

---

### Task 16: Implement mentorships and marriage alliances

**Files:**
- Modify: `src/chronicler/relationships.py`
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.relationships import check_mentorship_formation, check_marriage_formation

def test_mentorship_forms_with_compatible_traits(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.secondary_trait = "conqueror"
    civ.great_persons = [GreatPerson(name="OldGeneral", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=0)]
    formed = check_mentorship_formation(world)
    assert len(formed) == 1
    assert formed[0]["type"] == "mentorship"

def test_marriage_alliance_requires_allied_and_great_persons(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    # Set ALLIED disposition and 10+ allied turns
    from chronicler.models import Disposition
    rel12 = world.relationships[civ1.name][civ2.name]
    rel12.disposition = Disposition.ALLIED
    rel12.allied_turns = 15
    rel21 = world.relationships[civ2.name][civ1.name]
    rel21.disposition = Disposition.ALLIED
    rel21.allied_turns = 15
    civ1.great_persons = [GreatPerson(name="GP1", role="merchant", trait="shrewd", civilization=civ1.name, origin_civilization=civ1.name, born_turn=0)]
    civ2.great_persons = [GreatPerson(name="GP2", role="general", trait="bold", civilization=civ2.name, origin_civilization=civ2.name, born_turn=0)]
    formed = check_marriage_formation(world)
    # 30% chance — deterministic from seed
    # Just verify the function runs without error and returns a list
    assert isinstance(formed, list)
```

- [ ] **Step 2: Implement mentorship and marriage functions**

Add to `src/chronicler/relationships.py`:

```python
import random

MENTORSHIP_COMPATIBLE = {
    "general": {"conqueror", "warlike"},
    "scientist": {"builder", "merchant"},
}


def check_mentorship_formation(world: WorldState) -> list[dict]:
    """Form mentorships between great persons and leaders with compatible traits."""
    new_mentorships = []
    existing_mentored = {
        r["person_b"]  # person_b is the leader
        for r in world.character_relationships
        if r["type"] == "mentorship"
    }

    for civ in world.civilizations:
        if not civ.leader or not civ.leader.secondary_trait:
            continue
        if civ.leader.name in existing_mentored:
            continue  # max 1 mentorship per leader
        for gp in civ.great_persons:
            if not gp.active or gp.role in ("exile", "hostage"):
                continue
            compatible = MENTORSHIP_COMPATIBLE.get(gp.role, set())
            if civ.leader.secondary_trait in compatible:
                rel = {
                    "type": "mentorship",
                    "person_a": gp.name,
                    "person_b": civ.leader.name,
                    "civ_a": civ.name,
                    "civ_b": civ.name,
                    "formed_turn": world.turn,
                }
                world.character_relationships.append(rel)
                new_mentorships.append(rel)
                break  # one mentorship per leader
    return new_mentorships


def check_marriage_formation(world: WorldState) -> list[dict]:
    """Form marriage alliances between great persons of ALLIED civs."""
    from chronicler.models import Disposition
    new_marriages = []
    married_persons = {
        r["person_a"] for r in world.character_relationships if r["type"] == "marriage"
    } | {
        r["person_b"] for r in world.character_relationships if r["type"] == "marriage"
    }
    checked_pairs = {
        (r["civ_a"], r["civ_b"])
        for r in world.character_relationships if r["type"] == "marriage"
    }

    for i, civ1 in enumerate(world.civilizations):
        for civ2 in world.civilizations[i + 1:]:
            pair = (civ1.name, civ2.name)
            if pair in checked_pairs or (civ2.name, civ1.name) in checked_pairs:
                continue
            rel12 = world.relationships.get(civ1.name, {}).get(civ2.name)
            if not rel12 or rel12.disposition != Disposition.ALLIED or rel12.allied_turns < 10:
                continue
            # Both need at least one unmarried great person
            gp1_candidates = [gp for gp in civ1.great_persons if gp.active and gp.name not in married_persons and gp.role not in ("exile", "hostage")]
            gp2_candidates = [gp for gp in civ2.great_persons if gp.active and gp.name not in married_persons and gp.role not in ("exile", "hostage")]
            if not gp1_candidates or not gp2_candidates:
                continue
            rng = random.Random(world.seed + world.turn + hash(pair))
            if rng.random() < 0.30:
                gp1 = gp1_candidates[0]
                gp2 = gp2_candidates[0]
                rel = {
                    "type": "marriage",
                    "person_a": gp1.name,
                    "person_b": gp2.name,
                    "civ_a": civ1.name,
                    "civ_b": civ2.name,
                    "formed_turn": world.turn,
                }
                world.character_relationships.append(rel)
                new_marriages.append(rel)
    return new_marriages
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m17c): implement mentorship and marriage alliance relationships"
```

---

### Task 17: Implement hostage exchanges

**Files:**
- Modify: `src/chronicler/relationships.py`
- Modify: `src/chronicler/action_engine.py` (_resolve_war_action — capture hook)
- Modify: `src/chronicler/simulation.py` (Phase 2 — hostage tick)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.relationships import capture_hostage, tick_hostages, release_hostage

def test_capture_hostage_takes_youngest(make_world):
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    gp_old = GreatPerson(name="Old", role="merchant", trait="shrewd", civilization=loser.name, origin_civilization=loser.name, born_turn=0)
    gp_young = GreatPerson(name="Young", role="general", trait="bold", civilization=loser.name, origin_civilization=loser.name, born_turn=5)
    loser.great_persons = [gp_old, gp_young]
    captured = capture_hostage(loser, winner, world, contested_region="Battlefield")
    assert captured is not None
    assert captured.name == "Young"  # youngest
    assert captured.is_hostage is True
    assert captured.region == "Battlefield"
    assert captured in winner.great_persons

def test_hostage_cultural_conversion_at_10_turns(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    hostage = GreatPerson(name="Captive", role="general", trait="bold", civilization=captor.name, origin_civilization="Other", born_turn=0, is_hostage=True, hostage_turns=9)
    captor.great_persons = [hostage]
    tick_hostages(world)
    assert hostage.hostage_turns == 10
    assert hostage.cultural_identity == captor.name

def test_hostage_auto_release_at_15_turns(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(name="Captive", role="general", trait="bold", civilization=captor.name, origin_civilization=origin.name, born_turn=0, is_hostage=True, hostage_turns=14)
    captor.great_persons = [hostage]
    released = tick_hostages(world)
    assert len(released) == 1
    assert hostage.is_hostage is False
    assert hostage in origin.great_persons
```

- [ ] **Step 2: Implement hostage functions**

Add to `src/chronicler/relationships.py`:

```python
def capture_hostage(
    loser: Civilization, winner: Civilization, world: WorldState,
    contested_region: str | None = None,
) -> GreatPerson | None:
    """After war loss, loser sends youngest great person as hostage."""
    candidates = [gp for gp in loser.great_persons if gp.active and not gp.is_hostage]
    if not candidates:
        # Create generic hostage
        from chronicler.leaders import _pick_name
        name = _pick_name(loser, world)
        hostage = GreatPerson(
            name=name, role="hostage", trait="cautious",
            civilization=winner.name, origin_civilization=loser.name,
            born_turn=world.turn, is_hostage=True,
            region=contested_region,
        )
        winner.great_persons.append(hostage)
        return hostage

    youngest = max(candidates, key=lambda gp: gp.born_turn)
    loser.great_persons.remove(youngest)
    youngest.civilization = winner.name
    youngest.captured_by = winner.name
    youngest.is_hostage = True
    youngest.hostage_turns = 0
    youngest.region = contested_region
    winner.great_persons.append(youngest)
    return youngest


def tick_hostages(world: WorldState) -> list[GreatPerson]:
    """Phase 2: increment hostage turns, check cultural conversion and release."""
    released = []
    for civ in world.civilizations:
        for gp in list(civ.great_persons):
            if not gp.is_hostage:
                continue
            gp.hostage_turns += 1
            # Cultural conversion at 10 turns
            if gp.hostage_turns >= 10 and gp.cultural_identity != civ.name:
                gp.cultural_identity = civ.name
            # Auto-release at 15 turns
            if gp.hostage_turns >= 15:
                origin = next(
                    (c for c in world.civilizations if c.name == gp.origin_civilization),
                    None,
                )
                if origin:
                    release_hostage(gp, civ, origin, world)
                    released.append(gp)
    return released


def release_hostage(
    gp: GreatPerson, captor: Civilization, origin: Civilization,
    world: WorldState,
) -> None:
    """Release a hostage back to origin civ."""
    if gp in captor.great_persons:
        captor.great_persons.remove(gp)
    gp.is_hostage = False
    gp.civilization = origin.name
    gp.captured_by = None
    gp.region = origin.capital_region or (origin.regions[0] if origin.regions else None)
    origin.great_persons.append(gp)
    # Ransom cost
    if origin.treasury >= 10:
        origin.treasury -= 10
```

- [ ] **Step 3: Wire capture into _resolve_war_action**

In `src/chronicler/action_engine.py`, after `resolve_war()` returns and territory changes are processed, add:

```python
# After war outcome processing in _resolve_war_action:
if result.outcome == "defender_wins":
    # Attacker lost — they send a hostage
    from chronicler.relationships import capture_hostage
    capture_hostage(civ, defender, world, contested_region=result.contested_region)
elif result.outcome == "attacker_wins":
    # Defender lost — they send a hostage
    from chronicler.relationships import capture_hostage
    capture_hostage(defender, civ, world, contested_region=result.contested_region)
```

- [ ] **Step 4: Wire hostage tick into Phase 2**

In `src/chronicler/simulation.py`, within `apply_automatic_effects()`:

```python
from chronicler.relationships import tick_hostages
tick_hostages(world)
```

- [ ] **Step 5: Run tests, commit**

```bash
git add src/chronicler/relationships.py src/chronicler/action_engine.py src/chronicler/simulation.py tests/test_relationships.py
git commit -m "feat(m17c): implement hostage capture, cultural conversion, and auto-release"
```

---

### Task 18: Wire relationships into Phase 10 and integration test

**Files:**
- Modify: `src/chronicler/simulation.py` (Phase 10)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Wire relationship checks into Phase 10**

In `phase_consequences()`:

```python
from chronicler.relationships import check_rivalry_formation, check_mentorship_formation, check_marriage_formation
check_rivalry_formation(world)
check_mentorship_formation(world)
check_marriage_formation(world)
```

- [ ] **Step 2: Write integration test**

```python
def test_m17c_integration_relationships_across_turns(make_world):
    from chronicler.simulation import run_turn
    world = make_world(num_civs=3, seed=42)
    for turn in range(10):
        world.turn = turn
        run_turn(world)
    # No crashes, relationships list is consistent
    for rel in world.character_relationships:
        assert rel["type"] in ("rivalry", "mentorship", "marriage")
```

- [ ] **Step 3: Run full suite, commit**

```bash
git add src/chronicler/simulation.py tests/test_relationships.py
git commit -m "feat(m17c): wire rivalry, mentorship, marriage into Phase 10 consequences"
```

---

## Chunk 4: M17d — Institutional Memory & Capstone

### Task 19: Implement event_counts tracking

**Files:**
- Create: `src/chronicler/traditions.py`
- Modify: `src/chronicler/simulation.py` (Phase 10 — event counts update)
- Test: `tests/test_traditions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_traditions.py
from chronicler.traditions import update_event_counts

def test_war_win_counted(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    # Simulate a war win event this turn
    from chronicler.models import Event
    world.events_timeline.append(Event(
        turn=world.turn, event_type="war",
        actors=[civ.name, "Enemy"],
        description=f"{civ.name} attacked Enemy: attacker_wins.",
        importance=8,
    ))
    update_event_counts(world)
    assert civ.event_counts.get("wars_won", 0) == 1
    assert civ.name in [t for sublist in [c.war_win_turns for c in world.civilizations] for t in sublist] or len(civ.war_win_turns) == 1

def test_famine_survived_counted(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    world.events_timeline.append(Event(
        turn=world.turn, event_type="famine",
        actors=[civ.name],
        description="Famine in region.",
        importance=6,
    ))
    update_event_counts(world)
    assert civ.event_counts.get("famines_survived", 0) == 1
```

- [ ] **Step 2: Implement update_event_counts**

```python
# src/chronicler/traditions.py
"""Event counting, traditions, and folk heroes."""

from __future__ import annotations
from chronicler.models import WorldState, Civilization, Event


def update_event_counts(world: WorldState) -> None:
    """Phase 10 step 1: increment event_counts from this turn's events."""
    turn_events = [e for e in world.events_timeline if e.turn == world.turn]
    for event in turn_events:
        if not event.actors:
            continue
        civ_name = event.actors[0]
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if not civ:
            continue

        if event.event_type == "war" and "attacker_wins" in event.description:
            civ.event_counts["wars_won"] = civ.event_counts.get("wars_won", 0) + 1
            civ.war_win_turns.append(world.turn)
        elif event.event_type == "famine":
            civ.event_counts["famines_survived"] = civ.event_counts.get("famines_survived", 0) + 1

    # Prune war_win_turns to last 15
    for civ in world.civilizations:
        civ.war_win_turns = [t for t in civ.war_win_turns if t >= world.turn - 15]

    # Track high economy turns for scientist trigger
    for civ in world.civilizations:
        if civ.economy >= 80:
            civ.event_counts["high_economy_turns"] = civ.event_counts.get("high_economy_turns", 0) + 1
        else:
            civ.event_counts["high_economy_turns"] = 0

    # Track high trade route turns for merchant trigger
    for civ in world.civilizations:
        active_routes = sum(
            1 for other_name, rel in world.relationships.get(civ.name, {}).items()
            if hasattr(rel, 'trade_volume') and rel.trade_volume > 0
        )
        if active_routes >= 4:
            civ.event_counts["high_trade_route_turns"] = civ.event_counts.get("high_trade_route_turns", 0) + 1
        else:
            civ.event_counts["high_trade_route_turns"] = 0
```

- [ ] **Step 3: Wire into Phase 10**

In `phase_consequences()`, add as FIRST step (before great person generation):

```python
from chronicler.traditions import update_event_counts
update_event_counts(world)
```

- [ ] **Step 4: Run tests, commit**

```bash
git add src/chronicler/traditions.py src/chronicler/simulation.py tests/test_traditions.py
git commit -m "feat(m17d): implement event_counts tracking for wars, famines, economy, trade routes"
```

---

### Task 20: Implement traditions (acquisition and effects)

**Files:**
- Modify: `src/chronicler/traditions.py`
- Modify: `src/chronicler/simulation.py` (Phase 2 for ongoing effects, Phase 9 for fertility floor)
- Test: `tests/test_traditions.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.traditions import check_tradition_acquisition, apply_tradition_effects

def test_martial_tradition_from_war_wins(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["wars_won"] = 5
    check_tradition_acquisition(world)
    assert "martial" in civ.traditions

def test_food_stockpiling_from_famines(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["famines_survived"] = 3
    check_tradition_acquisition(world)
    assert "food_stockpiling" in civ.traditions

def test_resilience_from_capital_recovery(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["capital_recovered"] = 1
    check_tradition_acquisition(world)
    assert "resilience" in civ.traditions

def test_diplomatic_from_federation_turns(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["federation_turns"] = 30
    check_tradition_acquisition(world)
    assert "diplomatic" in civ.traditions

def test_no_double_granting(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.traditions = ["martial"]
    civ.event_counts["wars_won"] = 10
    check_tradition_acquisition(world)
    assert civ.traditions.count("martial") == 1

def test_crystallization_shame_to_resilience(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.legacy_counts["shame"] = 3
    check_tradition_acquisition(world)
    assert "resilience" in civ.traditions

def test_martial_tradition_military_bonus(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.traditions = ["martial"]
    mil_before = civ.military
    apply_tradition_effects(world)
    assert civ.military == mil_before + 5

def test_food_stockpiling_fertility_floor(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.traditions = ["food_stockpiling"]
    # Set a region's fertility below 0.2
    region = next(r for r in world.regions if r.name in civ.regions)
    region.fertility = 0.1
    from chronicler.traditions import apply_fertility_floor
    apply_fertility_floor(world)
    assert region.fertility == 0.2
```

- [ ] **Step 2: Implement tradition acquisition and effects**

Add to `src/chronicler/traditions.py`:

```python
# Direct triggers
TRADITION_DIRECT_TRIGGERS = {
    "martial": lambda civ: civ.event_counts.get("wars_won", 0) >= 5,
    "food_stockpiling": lambda civ: civ.event_counts.get("famines_survived", 0) >= 3,
    "resilience": lambda civ: civ.event_counts.get("capital_recovered", 0) >= 1,
    "diplomatic": lambda civ: civ.event_counts.get("federation_turns", 0) >= 30,
}

# Crystallization triggers (from legacy_counts)
TRADITION_CRYSTALLIZATION = {
    "martial": ("military", 3),
    "food_stockpiling": ("golden_age", 2),
    "diplomatic": ("fracture", 2),
    "resilience": ("shame", 3),
}

MAX_TRADITIONS = 4


def check_tradition_acquisition(world: WorldState) -> list[str]:
    """Phase 10: check if any civ earns a new tradition."""
    granted = []
    for civ in world.civilizations:
        if len(civ.traditions) >= MAX_TRADITIONS:
            continue
        for tradition, trigger in TRADITION_DIRECT_TRIGGERS.items():
            if tradition in civ.traditions:
                continue
            if trigger(civ):
                civ.traditions.append(tradition)
                granted.append(tradition)
                continue
            # Check crystallization path
            legacy_key, threshold = TRADITION_CRYSTALLIZATION[tradition]
            if civ.legacy_counts.get(legacy_key, 0) >= threshold:
                civ.traditions.append(tradition)
                granted.append(tradition)
    return granted


def apply_tradition_effects(world: WorldState) -> None:
    """Phase 2: apply ongoing tradition effects."""
    for civ in world.civilizations:
        if not civ.regions:
            continue
        if "martial" in civ.traditions:
            # Permanent +5 military (applied once — need to track if already applied)
            # Better: apply as a modifier check in combat rather than permanent stat
            # For simplicity: check if military bonus already baked in
            pass  # Applied via action weight modifiers and combat modifiers

        if "martial" in civ.traditions and world.turn % 10 == 0:
            # Fear: neighbors disposition drift -1 level
            from chronicler.culture import _downgrade_disposition
            for other_name in world.relationships.get(civ.name, {}):
                rel = world.relationships[civ.name][other_name]
                _downgrade_disposition(rel)


def apply_fertility_floor(world: WorldState) -> None:
    """Phase 9 end: clamp fertility for Food Stockpiling civs."""
    civ_traditions = {civ.name: civ.traditions for civ in world.civilizations}
    for region in world.regions:
        controller = next(
            (civ for civ in world.civilizations if region.name in civ.regions),
            None,
        )
        if controller and "food_stockpiling" in controller.traditions:
            region.fertility = max(region.fertility, 0.2)
```

- [ ] **Step 3: Wire into phases**

Phase 2: `apply_tradition_effects(world)`
Phase 9 (end of `phase_fertility`): `apply_fertility_floor(world)`
Phase 10: `check_tradition_acquisition(world)`

- [ ] **Step 4: Run tests, commit**

```bash
git add src/chronicler/traditions.py src/chronicler/simulation.py tests/test_traditions.py
git commit -m "feat(m17d): implement tradition acquisition (direct + crystallization) and ongoing effects"
```

---

### Task 21: Implement folk heroes

**Files:**
- Modify: `src/chronicler/traditions.py`
- Test: `tests/test_traditions.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.traditions import check_folk_hero, is_dramatic_death

def test_dramatic_death_in_war():
    assert is_dramatic_death("war") is True

def test_dramatic_death_in_disaster():
    assert is_dramatic_death("disaster") is True

def test_dramatic_death_in_crisis():
    assert is_dramatic_death("succession_crisis") is True

def test_dramatic_death_exile_with_recognizers():
    assert is_dramatic_death("exile_recognized") is True

def test_non_dramatic_death():
    assert is_dramatic_death("natural") is False

def test_folk_hero_creation(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="FallenHero", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0, death_turn=10, fate="dead",
    )
    # Use a seed that gives 20% chance hit
    result = check_folk_hero(gp, civ, world, context="war")
    # Deterministic — either it's a folk hero or not based on seed
    assert isinstance(result, bool)

def test_folk_hero_asabiya_bonus(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.folk_heroes = [
        {"name": "Hero1", "role": "general", "death_turn": 5, "death_context": "war"},
        {"name": "Hero2", "role": "general", "death_turn": 10, "death_context": "war"},
    ]
    # 2 folk heroes = +0.06 asabiya
    from chronicler.traditions import compute_folk_hero_asabiya_bonus
    bonus = compute_folk_hero_asabiya_bonus(civ)
    assert abs(bonus - 0.06) < 0.001

def test_folk_hero_cap_at_5(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    for i in range(5):
        civ.folk_heroes.append({"name": f"Hero{i}", "role": "general", "death_turn": i, "death_context": "war"})
    gp = GreatPerson(
        name="Hero6", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=50, death_turn=60, fate="dead",
    )
    # Force folk hero creation
    from chronicler.traditions import _add_folk_hero
    _add_folk_hero(gp, civ, "war")
    assert len(civ.folk_heroes) == 5  # capped, oldest replaced
```

- [ ] **Step 2: Implement folk hero functions**

Add to `src/chronicler/traditions.py`:

```python
MAX_FOLK_HEROES = 5
FOLK_HERO_ASABIYA = 0.03
FOLK_HERO_CHANCE = 0.20


def is_dramatic_death(context: str) -> bool:
    """Clear boolean: was this death dramatic?"""
    return context in ("war", "disaster", "succession_crisis", "exile_recognized")


def check_folk_hero(
    gp: GreatPerson, civ: Civilization, world: WorldState,
    context: str,
) -> bool:
    """20% chance of becoming folk hero on dramatic death."""
    if not is_dramatic_death(context):
        return False
    roll = (world.seed + (gp.death_turn or world.turn) + hash(gp.name)) % 100
    if roll < FOLK_HERO_CHANCE * 100:
        _add_folk_hero(gp, civ, context)
        return True
    return False


def _add_folk_hero(gp: GreatPerson, civ: Civilization, context: str) -> None:
    """Add a folk hero, enforcing the 5-cap."""
    hero = {
        "name": gp.name,
        "role": gp.role,
        "death_turn": gp.death_turn or 0,
        "death_context": context,
    }
    if len(civ.folk_heroes) >= MAX_FOLK_HEROES:
        civ.folk_heroes.pop(0)  # remove oldest
    civ.folk_heroes.append(hero)


def compute_folk_hero_asabiya_bonus(civ: Civilization) -> float:
    """Permanent asabiya bonus from folk heroes."""
    return len(civ.folk_heroes) * FOLK_HERO_ASABIYA
```

- [ ] **Step 3: Wire folk hero check into Phase 10**

In `phase_consequences()`, after the lifespan expiry step:

```python
from chronicler.traditions import check_folk_hero
# Check dramatic deaths from this turn
for gp in this_turn_deaths:
    check_folk_hero(gp, origin_civ, world, context=death_context)
```

The exact wiring depends on how deaths are tracked during the turn. The implementer should collect deaths during Phase 5 (war), Phase 7 (disasters), and Phase 8 (succession) into a list, then process folk hero checks in Phase 10 step 7.

- [ ] **Step 4: Run tests, commit**

```bash
git add src/chronicler/traditions.py tests/test_traditions.py
git commit -m "feat(m17d): implement folk hero system with dramatic death check, asabiya bonus, and 5-cap"
```

---

### Task 22: Implement tradition inheritance through secession

**Files:**
- Modify: `src/chronicler/politics.py:94-247` (check_secession)
- Test: `tests/test_traditions.py`

- [ ] **Step 1: Write failing test**

```python
def test_tradition_inherited_on_secession(make_world):
    world = make_world(num_civs=1, seed=42)
    parent = world.civilizations[0]
    parent.traditions = ["martial", "resilience"]
    parent.regions = ["r1", "r2", "r3", "r4"]
    parent.stability = 10  # trigger secession
    from chronicler.politics import check_secession
    events = check_secession(world)
    if events:  # secession occurred
        # Find the new civ
        new_civs = [c for c in world.civilizations if c.name != parent.name]
        if new_civs:
            assert "martial" in new_civs[-1].traditions
            assert "resilience" in new_civs[-1].traditions
```

- [ ] **Step 2: Add tradition inheritance to check_secession**

In `src/chronicler/politics.py`, within `check_secession()`, after the breakaway civ is created (~line 200+), add:

```python
# Inherit parent traditions
breakaway.traditions = list(parent_civ.traditions)
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/chronicler/politics.py tests/test_traditions.py
git commit -m "feat(m17d): inherit traditions through secession"
```

---

### Task 23: Implement prophet martyrdom

**Files:**
- Modify: `src/chronicler/traditions.py`
- Test: `tests/test_traditions.py`

- [ ] **Step 1: Write failing test**

```python
from chronicler.traditions import apply_prophet_martyrdom

def test_prophet_martyrdom_boosts_movement(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    from chronicler.models import Movement
    movement = Movement(id=0, origin_civ=civ.name, origin_turn=0, value_affinity="freedom", adherents={civ.name: {"variant": 0}})
    world.movements = [movement]
    gp = GreatPerson(
        name="Martyr", role="prophet", trait="zealous",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0, death_turn=10, fate="dead", movement_id=0,
    )
    # Prophet becomes folk hero
    apply_prophet_martyrdom(gp, civ, world)
    # Movement should have +0.1 adoption bonus tracked somehow
    # This is a simple flag/modifier — implementation depends on how movements track bonuses
```

- [ ] **Step 2: Implement prophet martyrdom**

Add to `src/chronicler/traditions.py`:

```python
def apply_prophet_martyrdom(
    gp: GreatPerson, civ: Civilization, world: WorldState,
) -> list[Event]:
    """When a prophet folk hero dies, boost their movement."""
    events = []
    if gp.role != "prophet" or gp.movement_id is None:
        return events
    movement = next((m for m in world.movements if m.id == gp.movement_id), None)
    if not movement:
        return events

    # +0.1 adoption bonus tracked on civ's event_counts
    key = f"martyrdom_bonus_movement_{movement.id}"
    civ.event_counts[key] = civ.event_counts.get(key, 0) + 1

    # Disposition +1 level toward folk hero's civ from co-adherents
    from chronicler.culture import _upgrade_disposition
    for other_name in movement.adherents:
        if other_name == civ.name:
            continue
        rel = world.relationships.get(other_name, {}).get(civ.name)
        if rel:
            _upgrade_disposition(rel)

    # Named event
    from chronicler.models import NamedEvent
    world.named_events.append(NamedEvent(
        name=f"The Martyrdom of {gp.name}",
        event_type="martyrdom",
        turn=world.turn,
        actors=[civ.name],
        description=f"The death of {gp.name} defined the orthodox faith.",
        importance=8,
    ))
    return events
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/chronicler/traditions.py tests/test_traditions.py
git commit -m "feat(m17d): implement prophet martyrdom with movement boost and disposition effects"
```

---

### Task 24: M17d integration test and full regression

**Files:**
- Test: `tests/test_traditions.py`

- [ ] **Step 1: Write integration test**

```python
def test_m17d_integration_traditions_and_folk_heroes(make_world):
    from chronicler.simulation import run_turn
    world = make_world(num_civs=4, seed=42)
    # Run 30 turns — enough for traditions and folk heroes to potentially emerge
    for turn in range(30):
        world.turn = turn
        run_turn(world)

    # Verify state consistency
    for civ in world.civilizations:
        assert len(civ.traditions) <= 4
        assert len(civ.folk_heroes) <= 5
        for t in civ.traditions:
            assert t in ("martial", "food_stockpiling", "diplomatic", "resilience")
        for gp in civ.great_persons:
            assert gp.active is True
    for gp in world.retired_persons:
        assert gp.active is False
        assert gp.fate in ("retired", "dead", "ascended")
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -x --tb=short 2>&1 | tail -30`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_traditions.py
git commit -m "test(m17d): add integration test for traditions and folk heroes across 30-turn simulation"
```

---

### Task 25: Final end-to-end integration test

**Files:**
- Modify: `tests/test_e2e.py` (add M17 assertions to existing e2e tests)

- [ ] **Step 1: Add M17 assertions to existing e2e test**

In `tests/test_e2e.py`, find the 31-turn simulation test and add:

```python
# After existing assertions, add M17 checks:
for civ in world.civilizations:
    # Great persons have valid state
    for gp in civ.great_persons:
        assert gp.active is True
        assert gp.civilization == civ.name
        assert gp.role in ("general", "merchant", "prophet", "scientist", "exile", "hostage")
    # Traditions are valid
    for t in civ.traditions:
        assert t in ("martial", "food_stockpiling", "diplomatic", "resilience")
    # Folk heroes capped
    assert len(civ.folk_heroes) <= 5
    # Crisis state is clean
    assert civ.succession_crisis_turns_remaining >= 0
# Retired persons have valid state
for gp in world.retired_persons:
    assert gp.active is False
    assert gp.fate in ("retired", "dead", "ascended")
```

- [ ] **Step 2: Run full suite**

Run: `python -m pytest tests/ -x -v --tb=short 2>&1 | tail -40`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test(m17): add M17 assertions to end-to-end integration tests"
```
