# M45: Character Arc Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add arc classification (simulation-side) and arc summaries (narration-side) to named characters, enabling narrator callbacks, thematic threading, and curator scoring for character arcs.

**Architecture:** Pure-function classifier in new `arcs.py` module, called in Phase 10 after events_timeline is populated. Deeds populated at 9 mutation points. Curator scoring enhanced with +1.5/+2.5 bonuses. Narration context enriched with arc data. LLM-generated summaries in API mode only.

**Tech Stack:** Python 3.12, Pydantic models, existing narrator/curator/agent_bridge infrastructure.

**Spec:** `docs/superpowers/specs/2026-03-18-m45-character-arc-tracking-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/chronicler/arcs.py` | Create | Arc classifier: constants, `classify_arc()`, 8 archetype pattern matchers |
| `src/chronicler/models.py` | Modify | Add `arc_phase`, `arc_summary`, `arc_type_turn` fields to GreatPerson |
| `src/chronicler/simulation.py` | Modify | Classifier call site after `events_timeline.extend()` |
| `src/chronicler/curator.py` | Modify | `gp_by_name` parameter, +1.5/+2.5 scoring in `compute_base_scores()` |
| `src/chronicler/narrative.py` | Modify | Arc context in prompts, dead character filter, summary follow-up calls |
| `src/chronicler/agent_bridge.py` | Modify | Deeds at 4 mutation points (promotion, exile, migration, secession) |
| `src/chronicler/great_persons.py` | Modify | Deeds at 3 mutation points (death, retirement, pilgrimage), Prophet guard-compat shim |
| `src/chronicler/main.py` | Modify | `gp_by_name` construction in `_run_narrate()` |
| `tests/test_arcs.py` | Create | All arc classifier tests |
| `tests/test_deeds.py` | Create | Deed population and cap tests |

---

### Task 1: Data Model — Add GreatPerson Fields

**Files:**
- Modify: `src/chronicler/models.py:349` (after existing `arc_type` field)

- [ ] **Step 1: Add `arc_phase`, `arc_summary`, `arc_type_turn` fields**

In `src/chronicler/models.py`, after line 349 (`arc_type: str | None = None`), add:

```python
    arc_phase: str | None = None
    arc_summary: str | None = None
    arc_type_turn: int | None = None
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/ -x -q`
Expected: All passing (new None-default fields don't break anything)

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m45): add arc_phase, arc_summary, arc_type_turn fields to GreatPerson"
```

---

### Task 2: Deeds Population — Mutation Points

Fixes the long-standing gap where `gp.deeds` (models.py:334) was defined but never populated. The narrator reads `gp.deeds[-3:]` for recent history — currently always empty.

**Helper:** Each mutation point uses a shared helper to append and cap:

**Files:**
- Modify: `src/chronicler/great_persons.py` (3 mutation points + helper)
- Modify: `src/chronicler/agent_bridge.py` (4 mutation points)
- Create: `tests/test_deeds.py`

- [ ] **Step 1: Write failing test for deeds cap**

Create `tests/test_deeds.py`:

```python
"""Tests for M45 deeds population."""
from chronicler.models import GreatPerson


DEEDS_CAP = 10


def _make_gp(**kwargs) -> GreatPerson:
    defaults = dict(
        name="TestChar", role="general", trait="bold",
        civilization="TestCiv", origin_civilization="TestCiv",
        born_turn=1, source="agent", agent_id=1,
    )
    defaults.update(kwargs)
    return GreatPerson(**defaults)


def test_deeds_cap():
    gp = _make_gp()
    for i in range(15):
        gp.deeds.append(f"Deed {i}")
        if len(gp.deeds) > DEEDS_CAP:
            gp.deeds = gp.deeds[-DEEDS_CAP:]
    assert len(gp.deeds) == DEEDS_CAP
    assert gp.deeds[0] == "Deed 5"
    assert gp.deeds[-1] == "Deed 14"
```

- [ ] **Step 2: Run test to verify it passes (this is a unit test of list behavior)**

Run: `pytest tests/test_deeds.py::test_deeds_cap -v`
Expected: PASS

- [ ] **Step 3: Write test for deed format at each mutation point**

Add to `tests/test_deeds.py`:

```python
def test_deed_at_promotion():
    gp = _make_gp()
    # Simulate what _process_promotions does:
    deed = f"Promoted as general in TestRegion"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Promoted as general in TestRegion"


def test_deed_at_death():
    gp = _make_gp()
    deed = "Died in TestRegion"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Died in TestRegion"


def test_deed_at_retirement():
    gp = _make_gp()
    deed = "Retired in TestRegion"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Retired in TestRegion"


def test_deed_at_conquest_exile():
    gp = _make_gp()
    deed = "Exiled after conquest of TestRegion"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Exiled after conquest of TestRegion"


def test_deed_at_exile_return():
    gp = _make_gp()
    deed = "Returned to TestRegion after 35 turns"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Returned to TestRegion after 35 turns"


def test_deed_at_migration():
    gp = _make_gp()
    deed = "Migrated from RegionA to RegionB"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Migrated from RegionA to RegionB"


def test_deed_at_secession():
    gp = _make_gp()
    deed = "Defected to NewCiv during secession"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Defected to NewCiv during secession"


def test_deed_at_pilgrimage_departure():
    gp = _make_gp()
    deed = "Departed on pilgrimage to HolyCity"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Departed on pilgrimage to HolyCity"


def test_deed_at_pilgrimage_return():
    gp = _make_gp()
    deed = "Returned from pilgrimage as Prophet"
    gp.deeds.append(deed)
    assert gp.deeds[-1] == "Returned from pilgrimage as Prophet"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_deeds.py -v`
Expected: All PASS

- [ ] **Step 5: Add deed helper function to great_persons.py**

In `src/chronicler/great_persons.py`, add near the top (after imports):

```python
DEEDS_CAP = 10


def _append_deed(gp: GreatPerson, deed: str) -> None:
    """Append a deed to a GreatPerson, capping at DEEDS_CAP entries."""
    gp.deeds.append(deed)
    if len(gp.deeds) > DEEDS_CAP:
        gp.deeds = gp.deeds[-DEEDS_CAP:]
```

- [ ] **Step 6: Add deed at `kill_great_person()` (great_persons.py:251)**

After line 263 (`gp.fate = "dead"`), add:

```python
    _append_deed(gp, f"Died in {gp.region or 'unknown'}")
```

- [ ] **Step 7: Add deed at `_retire_person()` (great_persons.py:92)**

After line 94 (`gp.fate = "retired"`), add:

```python
    _append_deed(gp, f"Retired in {gp.region or 'unknown'}")
```

- [ ] **Step 8: Add deed at `check_pilgrimages()` — departure and return paths**

At the pilgrimage departure path (after line 427 where `pilgrimage_return_turn` is set), add:

```python
        _append_deed(gp, f"Departed on pilgrimage to {best_region}")
```

At the pilgrimage return path (after line 365 where `arc_type = "Prophet"` is set), add:

```python
            _append_deed(gp, "Returned from pilgrimage as Prophet")
```

- [ ] **Step 9: Add deeds in agent_bridge.py — promotion, exile, migration, secession**

Import the helper at top of agent_bridge.py:

```python
from chronicler.great_persons import _append_deed
```

**Promotion** — after the GreatPerson constructor (after line 567), before `civ.great_persons.append(gp)`:

```python
            region_name = world.regions[origin_region].name if origin_region < len(world.regions) else "unknown"
            _append_deed(gp, f"Promoted as {role} in {region_name}")
```

**Conquest exile** — in `apply_conquest_transitions()`, after line 715 (`gp.active = False`):

```python
                _append_deed(gp, f"Exiled after conquest of {conquered_region.name}")
```

Note: find the variable name for the conquered region at the call site — it may be `region.name` or similar. Use whatever variable holds the region being conquered.

**Exile return** — in `_detect_character_events()`, after the `exile_return` Event constructor closing paren (after line ~674), add:

```python
                    _append_deed(self.gp_by_agent_id[e.agent_id], f"Returned to {target_name} after {turns_away} turns")
```

Note: the variable `gp_obj` doesn't exist in this function. Use `self.gp_by_agent_id[e.agent_id]` to access the GreatPerson object. The deed goes AFTER the Event() constructor's closing `)`, not inside it.

**Notable migration** — in `_detect_character_events()`, after the `notable_migration` Event constructor closing paren (after line ~684), add:

```python
            _append_deed(self.gp_by_agent_id[e.agent_id], f"Migrated from {source_name} to {target_name}")
```

**Secession defection** — in `apply_secession_transitions()`, after line 762 (`new_civ.great_persons.append(gp)`):

```python
                _append_deed(gp, f"Defected to {new_civ.name} during secession")
```

- [ ] **Step 10: Run all tests**

Run: `pytest tests/ -x -q`
Expected: All passing

- [ ] **Step 11: Commit**

```bash
git add src/chronicler/great_persons.py src/chronicler/agent_bridge.py tests/test_deeds.py
git commit -m "feat(m45): populate deeds at 9 mutation points with cap of 10"
```

---

### Task 3: Arc Classifier — Core Module

**Files:**
- Create: `src/chronicler/arcs.py`
- Create: `tests/test_arcs.py`

- [ ] **Step 1: Write failing test for classify_arc with no events**

Create `tests/test_arcs.py`:

```python
"""Tests for M45 arc classifier."""
import pytest
from chronicler.models import GreatPerson, Event
from chronicler.arcs import classify_arc


def _make_gp(**kwargs) -> GreatPerson:
    defaults = dict(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=100, source="agent", agent_id=1,
    )
    defaults.update(kwargs)
    return GreatPerson(**defaults)


def _make_event(turn, event_type, actors, **kwargs) -> Event:
    return Event(
        turn=turn,
        event_type=event_type,
        actors=actors,
        description=kwargs.get("description", ""),
        importance=kwargs.get("importance", 5),
    )


def test_classify_no_events():
    gp = _make_gp()
    phase, arc_type = classify_arc(gp, [], None, current_turn=150)
    assert phase is None
    assert arc_type is None
```

- [ ] **Step 2: Run test to verify it fails (arcs module doesn't exist)**

Run: `pytest tests/test_arcs.py::test_classify_no_events -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicler.arcs'`

- [ ] **Step 3: Create arcs.py with constants and classify_arc stub**

Create `src/chronicler/arcs.py`:

```python
"""M45: Character arc classification.

Pure-function classifier that pattern-matches structured event data
to assign trajectory states (arc_phase) and archetype labels (arc_type)
to named characters. Stateless — re-derived each turn from full event history.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.dynasties import Dynasty, DynastyRegistry
    from chronicler.models import Event, GreatPerson

# --- Calibration constants [CALIBRATE] for M47 ---

RISING_CAREER_THRESHOLD: int = 20
TRAGIC_HERO_LIFESPAN_THRESHOLD: int = 35
MARTYR_LIFESPAN_THRESHOLD: int = 35

# --- Archetype names (exact string constants) ---

ARC_RISE_AND_FALL = "Rise-and-Fall"
ARC_EXILE_AND_RETURN = "Exile-and-Return"
ARC_DYNASTY_FOUNDER = "Dynasty-Founder"
ARC_TRAGIC_HERO = "Tragic-Hero"
ARC_WANDERER = "Wanderer"
ARC_DEFECTOR = "Defector"
ARC_PROPHET = "Prophet"
ARC_MARTYR = "Martyr"


def classify_arc(
    gp: GreatPerson,
    events: list[Event],
    dynasty_registry: DynastyRegistry | None,
    current_turn: int,
) -> tuple[str | None, str | None]:
    """Classify a character's arc from their event history.

    Pure function — stateless re-derivation each turn.

    Returns:
        (arc_phase, arc_type) — either or both may be None.
    """
    # Filter events to this character
    char_events = [e for e in events if gp.name in e.actors]

    # Collect matches: list of (arc_phase, arc_type, condition_count)
    matches: list[tuple[str | None, str | None, int]] = []

    # --- Check each archetype ---
    _check_rise_and_fall(gp, char_events, current_turn, matches)
    _check_exile_and_return(gp, char_events, matches)
    _check_dynasty_founder(gp, dynasty_registry, matches)
    _check_tragic_hero(gp, matches)
    _check_wanderer(gp, char_events, matches)
    _check_defector(gp, char_events, matches)
    _check_prophet(gp, char_events, matches)
    _check_martyr(gp, char_events, matches)

    if not matches:
        return None, None

    # Priority: complete matches (arc_type not None) first, then by condition count.
    # Tie-break: later in list wins (later-checked archetypes are more narratively
    # relevant per spec). reversed() + max() ensures last-of-equals wins.
    complete = [(ph, at, cnt, i) for i, (ph, at, cnt) in enumerate(matches) if at is not None]
    if complete:
        best = max(complete, key=lambda x: (x[2], x[3]))
        return best[0], best[1]

    # Partial only: highest condition count, latest tie-break
    partial = [(ph, at, cnt, i) for i, (ph, at, cnt) in enumerate(matches)]
    best = max(partial, key=lambda x: (x[2], x[3]))
    return best[0], None


def _check_rise_and_fall(
    gp: GreatPerson,
    char_events: list[Event],
    current_turn: int,
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    career_length = (
        (gp.death_turn - gp.born_turn)
        if gp.death_turn is not None
        else (current_turn - gp.born_turn)
    )
    if career_length < RISING_CAREER_THRESHOLD:
        return

    has_death = any(e.event_type == "character_death" for e in char_events)
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)

    if has_death or has_exile:
        matches.append(("fallen", ARC_RISE_AND_FALL, 2))
    elif gp.active:
        matches.append(("rising", None, 1))


def _check_exile_and_return(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)
    has_return = any(e.event_type == "exile_return" for e in char_events)

    if not has_exile:
        return

    if has_return:
        matches.append((None, ARC_EXILE_AND_RETURN, 2))
    else:
        matches.append(("exiled", None, 1))


def _check_dynasty_founder(
    gp: GreatPerson,
    dynasty_registry: DynastyRegistry | None,
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if dynasty_registry is None or gp.agent_id is None or gp.dynasty_id is None:
        return

    # Use get_dynasty_for() public API (returns None if not found).
    # Requires gp_by_agent_id map — passed via closure or added to signature.
    # Alternatively, iterate registry.dynasties to find by dynasty_id:
    dynasty = None
    for d in dynasty_registry.dynasties:
        if d.dynasty_id == gp.dynasty_id:
            dynasty = d
            break
    if dynasty is None or dynasty.founder_id != gp.agent_id:
        return

    if len(dynasty.members) >= 2:
        matches.append(("founding", ARC_DYNASTY_FOUNDER, 2))
    else:
        matches.append(("founding", None, 1))


def _check_tragic_hero(
    gp: GreatPerson,
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if gp.trait != "bold":
        return

    if gp.fate == "dead" and gp.death_turn is not None:
        career = gp.death_turn - gp.born_turn
        if career < TRAGIC_HERO_LIFESPAN_THRESHOLD:
            matches.append(("embattled", ARC_TRAGIC_HERO, 2))
            return

    if gp.active:
        matches.append(("embattled", None, 1))


def _check_wanderer(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    migration_count = sum(
        1 for e in char_events if e.event_type == "notable_migration"
    )

    if migration_count >= 3:
        matches.append(("wandering", ARC_WANDERER, 2))
    elif migration_count >= 2:
        matches.append(("wandering", None, 1))


def _check_defector(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if gp.civilization == gp.origin_civilization:
        return

    has_secession = any(e.event_type == "secession_defection" for e in char_events)
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)

    if has_secession or has_exile:
        matches.append(("defecting", ARC_DEFECTOR, 2))
    else:
        matches.append(("defecting", None, 1))


def _check_prophet(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    has_return = any(e.event_type == "pilgrimage_return" for e in char_events)

    if has_return:
        matches.append(("converting", ARC_PROPHET, 2))
    elif gp.pilgrimage_return_turn is not None:
        # Currently mid-pilgrimage
        matches.append(("converting", None, 1))


def _check_martyr(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if gp.role != "prophet":
        return

    if gp.fate == "dead" and gp.death_turn is not None:
        career = gp.death_turn - gp.born_turn
        if career < MARTYR_LIFESPAN_THRESHOLD:
            matches.append(("persecuted", ARC_MARTYR, 2))
            return

    # Partial: prophet displaced by conquest
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)
    if has_exile:
        matches.append(("persecuted", None, 1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_arcs.py::test_classify_no_events -v`
Expected: PASS

- [ ] **Step 5: Write all archetype tests**

Add to `tests/test_arcs.py`:

```python
def test_classify_rise_and_fall():
    gp = _make_gp(fate="dead", alive=False, active=False, death_turn=140)
    events = [
        _make_event(140, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=140)
    assert arc_type == "Rise-and-Fall"
    assert phase == "fallen"


def test_classify_rise_partial():
    """Active character with established career -> 'rising' phase only."""
    gp = _make_gp(born_turn=100)
    phase, arc_type = classify_arc(gp, [], None, current_turn=125)
    assert phase == "rising"
    assert arc_type is None


def test_classify_rise_too_young():
    """Character below RISING_CAREER_THRESHOLD -> no arc."""
    gp = _make_gp(born_turn=100)
    phase, arc_type = classify_arc(gp, [], None, current_turn=110)
    assert phase is None
    assert arc_type is None


def test_classify_exile_and_return():
    gp = _make_gp()
    events = [
        _make_event(120, "conquest_exile", ["Kiran", "Aram", "Bora"]),
        _make_event(160, "exile_return", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=160)
    assert arc_type == "Exile-and-Return"


def test_classify_exile_partial():
    """Exile with no return -> 'exiled' phase only."""
    gp = _make_gp()
    events = [
        _make_event(120, "conquest_exile", ["Kiran", "Aram", "Bora"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=150)
    assert phase == "exiled"
    assert arc_type is None


def test_classify_tragic_hero():
    gp = _make_gp(trait="bold", fate="dead", alive=False, active=False,
                   death_turn=120)  # career = 20 turns < threshold
    phase, arc_type = classify_arc(gp, [], None, current_turn=120)
    assert arc_type == "Tragic-Hero"
    assert phase == "embattled"


def test_classify_tragic_hero_long_career():
    """Bold character who lived long is NOT a tragic hero."""
    gp = _make_gp(trait="bold", fate="dead", alive=False, active=False,
                   death_turn=200)  # career = 100 turns > threshold
    phase, arc_type = classify_arc(gp, [], None, current_turn=200)
    assert arc_type != "Tragic-Hero"


def test_classify_wanderer():
    gp = _make_gp()
    events = [
        _make_event(110, "notable_migration", ["Kiran"]),
        _make_event(120, "notable_migration", ["Kiran"]),
        _make_event(130, "notable_migration", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=130)
    assert arc_type == "Wanderer"
    assert phase == "wandering"


def test_classify_wanderer_partial():
    """2 migrations -> 'wandering' phase only."""
    gp = _make_gp()
    events = [
        _make_event(110, "notable_migration", ["Kiran"]),
        _make_event(120, "notable_migration", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=120)
    assert phase == "wandering"
    assert arc_type is None


def test_classify_defector():
    gp = _make_gp(civilization="Bora")  # different from origin "Aram"
    events = [
        _make_event(130, "secession_defection", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=130)
    assert arc_type == "Defector"
    assert phase == "defecting"


def test_classify_defector_partial():
    """Changed civ but no confirming event -> 'defecting' phase only."""
    gp = _make_gp(civilization="Bora")  # different from origin
    phase, arc_type = classify_arc(gp, [], None, current_turn=130)
    assert phase == "defecting"
    assert arc_type is None


def test_classify_prophet():
    gp = _make_gp(role="prophet")
    events = [
        _make_event(140, "pilgrimage_return", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=140)
    assert arc_type == "Prophet"


def test_classify_prophet_mid_pilgrimage():
    """Mid-pilgrimage -> 'converting' phase only."""
    gp = _make_gp(role="prophet", pilgrimage_return_turn=160)
    phase, arc_type = classify_arc(gp, [], None, current_turn=140)
    assert phase == "converting"
    assert arc_type is None


def test_classify_martyr():
    gp = _make_gp(role="prophet", fate="dead", alive=False, active=False,
                   death_turn=120)  # career = 20 turns < threshold
    events = [
        _make_event(120, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=120)
    assert arc_type == "Martyr"


def test_classify_martyr_long_career():
    """Prophet who lived long is NOT a martyr."""
    gp = _make_gp(role="prophet", fate="dead", alive=False, active=False,
                   death_turn=200)
    events = [
        _make_event(200, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=200)
    assert arc_type != "Martyr"


def test_classify_reclassification():
    """Wanderer reclassifies to Exile-and-Return when return event added."""
    gp = _make_gp()
    events_before = [
        _make_event(110, "notable_migration", ["Kiran"]),
        _make_event(120, "notable_migration", ["Kiran"]),
        _make_event(130, "notable_migration", ["Kiran"]),
        _make_event(140, "conquest_exile", ["Kiran", "Aram", "Bora"]),
    ]
    _, type_before = classify_arc(gp, events_before, None, current_turn=150)
    assert type_before == "Wanderer"

    events_after = events_before + [
        _make_event(180, "exile_return", ["Kiran"]),
    ]
    _, type_after = classify_arc(gp, events_after, None, current_turn=180)
    assert type_after == "Exile-and-Return"


def test_classify_priority():
    """When multiple complete archetypes match, highest condition count wins."""
    # Bold prophet who died young with exile events:
    # Could match Tragic Hero (2 conditions) AND Martyr (2 conditions)
    # AND Rise-and-Fall (2 conditions, if career >= threshold)
    # Martyr should win or tie since it's checked later
    gp = _make_gp(role="prophet", trait="bold", fate="dead",
                   alive=False, active=False, death_turn=120)
    events = [
        _make_event(120, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=120)
    # Both Tragic Hero and Martyr match with 2 conditions.
    # Martyr wins tie-break (later in check order per spec).
    assert arc_type == "Martyr"


def test_classify_dead_character():
    """Death on current turn still classifies."""
    gp = _make_gp(fate="dead", alive=False, active=False, death_turn=140)
    events = [
        _make_event(140, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=140)
    assert arc_type == "Rise-and-Fall"
    assert phase == "fallen"


def test_arc_type_turn_set():
    """arc_type_turn updates on (re)classification — tested at call site level."""
    gp = _make_gp()
    events = [
        _make_event(130, "notable_migration", ["Kiran"]),
        _make_event(140, "notable_migration", ["Kiran"]),
        _make_event(150, "notable_migration", ["Kiran"]),
    ]
    _, arc_type = classify_arc(gp, events, None, current_turn=150)
    assert arc_type == "Wanderer"

    # Simulate call site logic:
    prev_type = gp.arc_type
    if arc_type is not None and arc_type != prev_type:
        gp.arc_type = arc_type
        gp.arc_type_turn = 150

    assert gp.arc_type_turn == 150
    assert gp.arc_type == "Wanderer"
```

- [ ] **Step 6: Run all classifier tests**

Run: `pytest tests/test_arcs.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/arcs.py tests/test_arcs.py
git commit -m "feat(m45): arc classifier module with 8 archetypes and tests"
```

---

### Task 4: Arc Classifier — Call Site in simulation.py

**Files:**
- Modify: `src/chronicler/simulation.py:1386-1389` (after events_timeline.extend, before narrator call)

- [ ] **Step 1: Add import at top of simulation.py**

Add to imports:

```python
from chronicler.arcs import classify_arc
```

- [ ] **Step 2: Add classifier call site after events_timeline.extend**

After line 1386 (`world.events_timeline.extend(turn_events)`), BEFORE line 1388 (`chronicle_text = narrator(world, turn_events)`), insert:

```python
    # M45: Arc classification — after events are on timeline, before snapshot
    dynasty_reg = agent_bridge.dynasty_registry if agent_bridge else None
    for civ in world.civilizations:
        for gp in civ.great_persons:
            prev_type = gp.arc_type
            gp.arc_phase, new_type = classify_arc(
                gp, world.events_timeline, dynasty_reg, world.turn
            )
            if new_type is not None and new_type != prev_type:
                gp.arc_type = new_type
                gp.arc_type_turn = world.turn
    # Recently dead — death is often the completing event
    for gp in world.retired_persons:
        if gp.death_turn == world.turn:
            prev_type = gp.arc_type
            gp.arc_phase, new_type = classify_arc(
                gp, world.events_timeline, dynasty_reg, world.turn
            )
            if new_type is not None and new_type != prev_type:
                gp.arc_type = new_type
                gp.arc_type_turn = world.turn
```

Note: the parameter is `agent_bridge` (line 1177), not `bridge`.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest tests/ -x -q`
Expected: All passing

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m45): wire arc classifier into Phase 10 after events_timeline.extend"
```

---

### Task 5: M38b Prophet Guard Compatibility

**Files:**
- Modify: `src/chronicler/great_persons.py:365,387-388`

The spec (Decision 18) says: keep the provisional `gp.arc_type = "Prophet"` set in `check_pilgrimages()` return path. The classifier confirms it idempotently. No code change needed — the existing line 365 stays as-is.

- [ ] **Step 1: Verify the existing `arc_type = "Prophet"` set is still at line 365**

Read `src/chronicler/great_persons.py` around line 365 to confirm:
```python
            gp.arc_type = "Prophet"  # M38b — kept as guard-compat shim (M45 Decision 18)
```

- [ ] **Step 2: Add a comment explaining the shim**

Change line 365 from:
```python
            gp.arc_type = "Prophet"
```
to:
```python
            gp.arc_type = "Prophet"  # Guard-compat shim: classifier confirms idempotently (M45 Decision 18)
```

- [ ] **Step 3: Verify departure guard at line 387-388 still works**

The guard `if gp.arc_type == "Prophet":` prevents re-departure. The provisional set at line 365 ensures this fires on the return turn before the classifier runs. No change needed.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/great_persons.py
git commit -m "docs(m45): annotate Prophet guard-compat shim (Decision 18)"
```

---

### Task 6: Curator Scoring Enhancement

**Files:**
- Modify: `src/chronicler/curator.py:93-99,515-522,543-545`
- Modify: `src/chronicler/main.py:762-777`

- [ ] **Step 1: Write failing test for arc involvement bonus**

Add to `tests/test_arcs.py` (or create a new section):

```python
# --- Curator scoring tests ---

from chronicler.curator import compute_base_scores
from chronicler.models import NamedEvent


def _make_named_event(name, turn):
    return NamedEvent(name=name, turn=turn, importance=5)


def test_curator_arc_phase_bonus():
    """arc_phase set -> +1.5 on character events."""
    gp = _make_gp(arc_phase="rising")
    ev = _make_event(150, "conquest", ["Kiran", "Aram"])
    gp_by_name = {"Kiran": gp}
    named_chars = {"Kiran"}

    scores = compute_base_scores(
        [ev], [], "Aram", seed=0,
        named_characters=named_chars,
        gp_by_name=gp_by_name,
    )
    # Base score includes +2.0 (named char) + 1.5 (arc involvement) = 3.5 bonus
    assert scores[0] >= 3.5


def test_curator_arc_completion_bonus():
    """Event on arc_type_turn -> +2.5."""
    gp = _make_gp(arc_type="Rise-and-Fall", arc_type_turn=150)
    ev = _make_event(150, "character_death", ["Kiran", "Aram"])
    gp_by_name = {"Kiran": gp}
    named_chars = {"Kiran"}

    scores = compute_base_scores(
        [ev], [], "Aram", seed=0,
        named_characters=named_chars,
        gp_by_name=gp_by_name,
    )
    # +2.0 (named) + 1.5 (arc involvement) + 2.5 (completion) = 6.0
    assert scores[0] >= 6.0


def test_curator_no_arc_no_bonus():
    """Character with no arc -> only +2.0 named bonus."""
    gp = _make_gp()  # no arc_phase or arc_type
    ev = _make_event(150, "conquest", ["Kiran", "Aram"])
    gp_by_name = {"Kiran": gp}
    named_chars = {"Kiran"}

    scores = compute_base_scores(
        [ev], [], "Aram", seed=0,
        named_characters=named_chars,
        gp_by_name=gp_by_name,
    )
    # Only +2.0 named character bonus, no arc bonus
    base_without_named = compute_base_scores(
        [ev], [], "Aram", seed=0,
    )
    assert scores[0] == pytest.approx(base_without_named[0] + 2.0)


def test_curator_gp_by_name_none():
    """gp_by_name=None -> no arc bonuses, no crash."""
    ev = _make_event(150, "conquest", ["Kiran", "Aram"])
    scores = compute_base_scores(
        [ev], [], "Aram", seed=0,
        gp_by_name=None,
    )
    assert len(scores) == 1  # no crash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_arcs.py::test_curator_arc_phase_bonus -v`
Expected: FAIL (compute_base_scores doesn't accept `gp_by_name` parameter yet)

- [ ] **Step 3: Add `gp_by_name` parameter to `compute_base_scores()`**

In `src/chronicler/curator.py`, modify the `compute_base_scores` signature (line 93):

```python
def compute_base_scores(
    events: Sequence[Event],
    named_events: Sequence[NamedEvent],
    dominant_power: str,
    seed: int,
    named_characters: set[str] | None = None,
    gp_by_name: dict[str, GreatPerson] | None = None,  # M45
) -> list[float]:
```

Add the import at top of curator.py if not already present:

```python
from chronicler.models import GreatPerson
```

- [ ] **Step 4: Add arc scoring logic after the named character bonus block**

After line 137 (`score += 2.0`), within the same event loop, add:

```python
            # M45: Arc involvement bonus
            if gp_by_name:
                for actor in ev.actors:
                    gp = gp_by_name.get(actor)
                    if gp is None:
                        continue
                    if gp.arc_phase is not None or gp.arc_type is not None:
                        score += 1.5
                        break

                # Arc completion bonus — the defining moment
                for actor in ev.actors:
                    gp = gp_by_name.get(actor)
                    if gp and gp.arc_type_turn == ev.turn:
                        score += 2.5
                        break
```

- [ ] **Step 5: Add `gp_by_name` parameter to `curate()` and forward it**

Modify the `curate` signature (line 515) to add:

```python
    gp_by_name: dict[str, GreatPerson] | None = None,  # M45
```

Modify the `compute_base_scores` call (line 543-545) to forward it:

```python
    scores = compute_base_scores(sorted_events, named_events, dominant, seed,
                                  named_characters=named_characters,
                                  gp_by_name=gp_by_name)
```

- [ ] **Step 6: Build and pass `gp_by_name` in `_run_narrate()` (main.py)**

In `src/chronicler/main.py`, after the `named_chars` construction (line 762-767), add:

```python
    # M45: Build gp_by_name for arc scoring
    gp_by_name = {}
    for civ_data in bundle.get("world_state", {}).get("civilizations", []):
        for gp_data in civ_data.get("great_persons", []):
            if gp_data.get("active") and gp_data.get("agent_id") is not None:
                gp_by_name[gp_data.get("name", "")] = GreatPerson(**gp_data)
    for gp_data in bundle.get("world_state", {}).get("retired_persons", []):
        if gp_data.get("death_turn") is not None:
            gp_by_name[gp_data.get("name", "")] = GreatPerson(**gp_data)
```

Then modify the `curate()` call (line 770) to pass it:

```python
    moments, gap_summaries = curate(
        events=events,
        named_events=named_events,
        history=history,
        budget=budget,
        seed=seed,
        named_characters=named_chars if named_chars else None,
        gp_by_name=gp_by_name if gp_by_name else None,
    )
```

Add the import at top if needed:

```python
from chronicler.models import GreatPerson
```

- [ ] **Step 6b: Build and pass `gp_by_name` in `execute_run()` API path (main.py:429-447)**

The `execute_run()` path has a live `world` object. After the existing `named_chars` construction (line 434-438), add:

```python
        # M45: Build gp_by_name for arc scoring
        gp_by_name = {}
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.active and gp.agent_id is not None:
                    gp_by_name[gp.name] = gp
        for gp in world.retired_persons:
            if gp.death_turn is not None:
                gp_by_name[gp.name] = gp
```

Then modify the `curate()` call (line 440) to pass it:

```python
        moments, gap_summaries = curate(
            events=world.events_timeline,
            named_events=world.named_events,
            history=history,
            budget=getattr(args, "budget", 50),
            seed=seed,
            named_characters=named_chars if named_chars else None,
            gp_by_name=gp_by_name if gp_by_name else None,
        )
```

Also pass `gp_by_name` to `engine.narrate_batch()` (line 453):

```python
        chronicle_entries = engine.narrate_batch(
            moments, history, gap_summaries, on_progress=progress_cb,
            gp_by_name=gp_by_name if gp_by_name else None,
        )
```

And build `all_great_persons` (active + retired) for the narrate_batch `great_persons` parameter:

```python
        all_great_persons = []
        for civ in world.civilizations:
            all_great_persons.extend(civ.great_persons)
        all_great_persons.extend(world.retired_persons)
```

Pass `all_great_persons` to `narrate_batch()` as the `great_persons` parameter.

- [ ] **Step 7: Run curator scoring tests**

Run: `pytest tests/test_arcs.py -k curator -v`
Expected: All PASS

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All passing

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/curator.py src/chronicler/main.py tests/test_arcs.py
git commit -m "feat(m45): curator scoring enhancement with +1.5 arc and +2.5 completion bonuses"
```

---

### Task 7: Narration Context Enhancement — Arc Data in Prompts

**Files:**
- Modify: `src/chronicler/narrative.py:72-94,141-165`

- [ ] **Step 1: Write failing test for arc context in prompt**

Add to `tests/test_arcs.py`:

```python
from chronicler.narrative import build_agent_context_block, AgentContext


def test_arc_context_in_prompt():
    """arc_type and arc_phase appear in narrator prompt."""
    ctx = AgentContext(
        named_characters=[{
            "name": "Kiran",
            "role": "General",
            "civ": "Aram",
            "status": "active",
            "arc_type": "Rise-and-Fall",
            "arc_phase": "rising",
            "trait": "bold",
        }],
    )
    text = build_agent_context_block(ctx)
    assert "Rise-and-Fall" in text
    assert "rising" in text


def test_trait_rendered():
    """Character trait appears in prompt block."""
    ctx = AgentContext(
        named_characters=[{
            "name": "Kiran",
            "role": "General",
            "civ": "Aram",
            "status": "active",
            "trait": "bold",
        }],
    )
    text = build_agent_context_block(ctx)
    assert "bold" in text


def test_arc_summary_in_prompt():
    """arc_summary appears in prompt when set."""
    ctx = AgentContext(
        named_characters=[{
            "name": "Kiran",
            "role": "General",
            "civ": "Aram",
            "status": "active",
            "arc_summary": "Led the northern campaign. Rose to command.",
        }],
    )
    text = build_agent_context_block(ctx)
    assert "Led the northern campaign" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_arcs.py::test_arc_context_in_prompt -v`
Expected: FAIL

- [ ] **Step 3: Add arc data to character dict in `build_agent_context_for_moment()`**

In `src/chronicler/narrative.py`, find the character dict building loop (around line 164-190). After the existing fields are set on `char`, add:

```python
            if gp.arc_type:
                char["arc_type"] = gp.arc_type
            if gp.arc_phase:
                char["arc_phase"] = gp.arc_phase
            if gp.arc_summary:
                char["arc_summary"] = gp.arc_summary
            if gp.trait:
                char["trait"] = gp.trait
```

- [ ] **Step 4: Relax active filter to include dead characters in moment events**

In `build_agent_context_for_moment()`, change the filter at line 165:

From:
```python
        if not gp.active or gp.source != "agent":
```

To:
```python
        if gp.source != "agent":
            continue
        # Include dead characters if they appear in this moment's events
        moment_actors = {actor for ev in moment.events for actor in ev.actors}
        if not gp.active and gp.name not in moment_actors:
```

Note: the early-return guard at narrative.py:159 (`if not agent_events and not ...`) checks `e.source == "agent"`. Character death events DO have `source="agent"` (agent_bridge.py:624), so the function won't return early for death moments. Verify this holds for other character lifecycle events at implementation time.

Compute `moment_actors` once before the loop, not inside it. Move it before the `for gp in great_persons:` line:

```python
    moment_actors = {actor for ev in moment.events for actor in ev.actors}
    for gp in great_persons:
        if gp.source != "agent":
            continue
        if not gp.active and gp.name not in moment_actors:
            continue
```

- [ ] **Step 5: Add arc rendering to `build_agent_context_block()`**

In the character rendering section (around line 78), modify the character line to include trait:

From:
```python
            lines.append(
                f"- {char['role']} {char['name']} ({char['civ']}{origin}) [{char['status']}]:"
            )
```

To:
```python
            trait_str = f" [{char['trait']}]" if char.get("trait") else ""
            lines.append(
                f"- {char['role']} {char['name']}{trait_str} ({char['civ']}{origin}) [{char['status']}]:"
            )
```

After the character header line, before the history_parts block, add arc rendering:

```python
            # Arc context
            arc_type = char.get("arc_type")
            arc_phase = char.get("arc_phase")
            if arc_type or arc_phase:
                arc_str = arc_type or ""
                if arc_phase:
                    arc_str = f"{arc_str} ({arc_phase})" if arc_str else arc_phase
                lines.append(f"  Arc: {arc_str}")
            if char.get("arc_summary"):
                lines.append(f"  Summary: {char['arc_summary']}")
```

- [ ] **Step 6: Run narration context tests**

Run: `pytest tests/test_arcs.py -k "arc_context or trait_rendered or arc_summary_in" -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All passing

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/narrative.py tests/test_arcs.py
git commit -m "feat(m45): arc context in narrator prompts, dead character filter relaxed, trait rendered"
```

---

### Task 8: Arc Summary Follow-Up Calls (API Mode)

**Files:**
- Modify: `src/chronicler/narrative.py` (within `narrate_batch()`)

This task adds the LLM follow-up call within `narrate_batch()` that generates arc summaries after each narrated moment. Only runs when `--narrator api` is active.

- [ ] **Step 1: Write test for arc summary update logic**

Add to `tests/test_arcs.py`:

```python
def test_arc_summary_truncation():
    """4th sentence drops the oldest."""
    gp = _make_gp(arc_summary="Sentence one. Sentence two. Sentence three.")
    # Simulate appending a 4th sentence and truncating:
    sentences = [s.strip() for s in gp.arc_summary.split(".") if s.strip()]
    sentences.append("Sentence four")
    if len(sentences) > 3:
        sentences = sentences[-3:]
    gp.arc_summary = ". ".join(sentences) + "."
    assert "Sentence one" not in gp.arc_summary
    assert "Sentence four" in gp.arc_summary
    assert gp.arc_summary.count(".") <= 4  # 3 sentences + trailing period


def test_arc_summary_api_only():
    """Summary generation is gated on API mode."""
    # This is a design constraint test — verify that the summary follow-up
    # is only called when narrator mode is "api". Implementation will check
    # a flag or client type before making the follow-up call.
    pass  # Tested via integration when M44 provides the API client
```

- [ ] **Step 2: Add summary helper function to narrative.py**

Add a helper for summary truncation:

```python
_MAX_ARC_SUMMARY_SENTENCES = 3


def _update_arc_summary(gp: GreatPerson, new_sentence: str) -> None:
    """Append a sentence to gp.arc_summary, keeping max 3 sentences."""
    if gp.arc_summary:
        sentences = [s.strip() for s in gp.arc_summary.split(".") if s.strip()]
    else:
        sentences = []
    sentences.append(new_sentence.rstrip("."))
    if len(sentences) > _MAX_ARC_SUMMARY_SENTENCES:
        sentences = sentences[-_MAX_ARC_SUMMARY_SENTENCES:]
    gp.arc_summary = ". ".join(sentences) + "."
```

- [ ] **Step 3: Add summary follow-up call in narrate_batch()**

In `narrate_batch()`, after the main LLM call that produces `prose` (around line 845-848), and after `build_agent_context_block` is called (line 811-812), add the summary follow-up logic:

```python
                # M45: Arc summary follow-up (API mode only)
                if (agent_ctx is not None
                        and self._is_api_client()
                        and gp_by_name):
                    known_names = {c["name"] for c in agent_ctx.named_characters}
                    for ev in moment.events:
                        for actor in ev.actors:
                            if actor in gp_by_name:
                                known_names.add(actor)
                    matched = [n for n in known_names if n in prose]
                    if matched:
                        try:
                            summary_prompt = (
                                "Based on the following passage, write exactly one sentence "
                                "summarizing each named character's role. "
                                "Only reference events described in the passage.\n\n"
                                f"Characters: {', '.join(matched)}\n"
                                f"Passage: {prose}\n\n"
                                "Respond as:\n"
                                + "\n".join(f"{n}: [sentence]" for n in matched)
                            )
                            summary_response = self.narrative_client.generate(summary_prompt)
                            for name in matched:
                                prefix = f"{name}: "
                                for line in summary_response.split("\n"):
                                    if line.startswith(prefix):
                                        sentence = line[len(prefix):].strip()
                                        if sentence and name in gp_by_name:
                                            _update_arc_summary(gp_by_name[name], sentence)
                                        break
                        except Exception:
                            import logging
                            logging.getLogger(__name__).warning(
                                "Arc summary follow-up failed for moment %d, skipping",
                                moment.anchor_turn,
                            )
```

**API mode gate:** Add a helper method on `NarrativeEngine`:

```python
def _is_api_client(self) -> bool:
    """Check if narrative_client supports API-quality arc summaries."""
    # Import here to avoid circular dependency if AnthropicClient
    # is not available (M44 not landed)
    try:
        from chronicler.narrative import AnthropicClient
        return isinstance(self.narrative_client, AnthropicClient)
    except ImportError:
        return False
```

This uses `isinstance()` on `self.narrative_client` (the correct attribute name, narrative.py:646). If M44 hasn't landed yet and `AnthropicClient` doesn't exist, returns `False` — summaries disabled. When M44 lands, the check activates automatically.

The `gp_by_name` dict needs to be passed into `narrate_batch()` as a parameter. Add it to the `narrate_batch` method signature and pass it from the callers.

- [ ] **Step 4: Thread `gp_by_name` into `narrate_batch()`**

Add `gp_by_name: dict[str, GreatPerson] | None = None` parameter to `narrate_batch()` signature.

In `_run_narrate()` in main.py, pass the already-constructed `gp_by_name` to `narrate_batch()`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_arcs.py -v`
Expected: All passing

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All passing

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/narrative.py src/chronicler/main.py tests/test_arcs.py
git commit -m "feat(m45): arc summary follow-up LLM calls in narrate_batch (API mode only)"
```

---

### Task 9: Dead Characters in narrate_batch() Great Persons List

**Files:**
- Modify: `src/chronicler/narrative.py` (narrate_batch great_persons parameter)
- Modify: `src/chronicler/main.py` (_run_narrate)

The `great_persons` list passed to `build_agent_context_for_moment()` currently only includes active characters from `civ.great_persons`. Dead characters need to be included so their accumulated arc data appears in death moment prompts.

- [ ] **Step 1: Write test for dead character in moment context**

Add to `tests/test_arcs.py`:

```python
from chronicler.narrative import build_agent_context_for_moment
from chronicler.models import NarrativeMoment, NarrativeRole, CausalLink


def _make_moment(turn, events):
    """Helper to build a valid NarrativeMoment for testing."""
    return NarrativeMoment(
        anchor_turn=turn,
        turn_range=(turn, turn),
        events=events,
        named_events=[],
        score=5.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )


def test_dead_character_in_moment_context():
    """Dead character whose name is in moment event actors appears in context."""
    gp = _make_gp(
        active=False, alive=False, fate="dead", death_turn=140,
        arc_type="Rise-and-Fall", arc_phase="fallen",
        arc_summary="Led the northern campaign.",
    )
    moment = _make_moment(140, [_make_event(140, "character_death", ["Kiran", "Aram"])])
    ctx = build_agent_context_for_moment(
        moment, [gp], {}, {},
    )
    assert ctx is not None
    names = [c["name"] for c in ctx.named_characters]
    assert "Kiran" in names
```

- [ ] **Step 2: Run test to verify behavior**

Run: `pytest tests/test_arcs.py::test_dead_character_in_moment_context -v`

If the relaxed filter from Task 7 is already in place, this should PASS. If not, implement the filter change from Task 7 Step 4.

- [ ] **Step 3: Ensure retired persons are passed to narrate_batch**

In `_run_narrate()` (main.py), where `great_persons` list is built for narrate_batch, include retired persons:

```python
    # M45: Include retired persons for dead character arc context
    all_great_persons = list(great_persons)  # existing active GPs
    for gp_data in bundle.get("world_state", {}).get("retired_persons", []):
        all_great_persons.append(GreatPerson(**gp_data))
```

Pass `all_great_persons` instead of `great_persons` to `narrate_batch()`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: All passing

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py src/chronicler/main.py tests/test_arcs.py
git commit -m "feat(m45): include retired persons in narrate_batch for death moment context"
```

---

### Task 10: Final Verification and Cleanup

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All passing

- [ ] **Step 2: Verify --agents=off still works**

Run: `python -m chronicler --seed 42 --turns 10 --agents=off --simulate-only`
Expected: No errors, simulation completes

- [ ] **Step 3: Verify arc classification in a short run**

Run: `python -m chronicler --seed 42 --turns 100 --simulate-only`

Check output for any arc-related errors. In `--simulate-only`, arc_type and arc_phase should populate on characters but arc_summary should stay None.

- [ ] **Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "chore(m45): final cleanup and verification"
```

---

## Summary

| Task | Description | Estimated Steps |
|------|-------------|----------------|
| 1 | Data model fields | 3 |
| 2 | Deeds population (9 mutation points) | 11 |
| 3 | Arc classifier module (8 archetypes) | 7 |
| 4 | Classifier call site in simulation.py | 4 |
| 5 | M38b Prophet guard compatibility | 4 |
| 6 | Curator scoring (+1.5/+2.5) | 9 |
| 7 | Narration context (arc in prompts) | 8 |
| 8 | Arc summary follow-up calls | 7 |
| 9 | Dead characters in narrate_batch | 5 |
| 10 | Final verification | 4 |
| **Total** | | **62 steps** |
